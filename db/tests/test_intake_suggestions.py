# Copyright 2026 Mộc Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Đọc văn bản đến (F4.1, migration 1792281601900): tác tử moc-doc-reader (vai trò Hasura agent) lưu gợi ý của một tệp
và dòng sổ intake.suggested trong cùng một yêu cầu; thuê ước, danh tính tác tử đặt sẵn từ phiên; tệp mã hóa, tệp của
văn bản hạn chế không có gợi ý; không vai trò người dùng nào thấy bảng; màn Sổ kiểm toán thấy cách đọc, không thấy giá
trị đọc được; view office.v_intake_accuracy đếm gợi ý văn thư giữ nguyên. svc-files không chạy ở đây: test gửi đúng
các truy vấn của svc_files.docread.store (hợp đồng F4.1 §2)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pytest
from conftest import (
    INSERT_DOC,
    Agent,
    GraphQLError,
    Service,
    SQLError,
    User,
    World,
    incoming,
    insert_file,
    received,
    sql,
)

AGENT_ID = "moc-doc-reader"

# Đúng ba truy vấn svc-files gửi bằng vai trò agent (GoiYDaCo, LuuGoiY, GhiSoTacTu)
CACHED = """query ($id: uuid!) { office_intake_suggestions_by_pk(file_id: $id) { file_id status method pages fields
  warnings summary_source model duration_ms read_at } }"""
SAVE = """mutation ($o: office_intake_suggestions_insert_input!, $e: core_audit_log_insert_input!) {
  insert_office_intake_suggestions_one(object: $o, on_conflict: {constraint: intake_suggestions_pkey, update_columns:
    [requested_by, status, method, pages, fields, warnings, summary_source, model, duration_ms]}) { file_id read_at }
  insert_core_audit_log(objects: [$e]) { affected_rows } }"""
LOG = """mutation ($e: core_audit_log_insert_input!) { insert_core_audit_log(objects: [$e]) { affected_rows } }"""

# Chỉ phần gợi ý của LuuGoiY: kiểm ràng buộc từng cột mà không ghi thêm dòng sổ
SAVE_ONE = """mutation ($o: office_intake_suggestions_insert_input!) {
  insert_office_intake_suggestions_one(object: $o, on_conflict: {constraint: intake_suggestions_pkey, update_columns:
    [requested_by, status, method, pages, fields, warnings, summary_source, model, duration_ms]}) { file_id read_at }
}"""

AUDIT_VIEW = """query ($e: String!) {
  core_audit_log(where: {entity_id: {_eq: $e}, action: {_eq: "intake.suggested"}}, order_by: {id: asc}) {
    actor_id actor_kind action entity overview } }"""
INSERT_EVENT = """mutation ($o: core_audit_log_insert_input!) { insert_core_audit_log_one(object: $o) { id } }"""

ACCURACY = "{ office_v_intake_accuracy { field confidence suggested kept } }"
ACCURACY_SUM = "{ office_v_intake_accuracy_aggregate { aggregate { sum { suggested kept } } } }"

FIELDS = {
    "symbol": {"value": "123/QĐ-UBND", "confidence": "high", "source": "rule"},
    "issued_on": {"value": "2026-10-15", "confidence": "high", "source": "rule"},
    "issuer_name": {"value": "Ủy ban nhân dân tỉnh Mẫu", "confidence": "medium", "source": "rule"},
    "type_code": {"value": "QĐ", "confidence": "high", "source": "rule"},
    "urgency": {"value": "khan", "confidence": "high", "source": "rule"},
    "summary": {"value": "Quyết định ban hành Quy chế thử nghiệm", "confidence": "medium", "source": "model"},
}
FOUND = "symbol,issued_on,issuer_name,type_code,urgency,summary"


def agent(tenant: str, sub: str = AGENT_ID) -> Agent:
    return Agent(sub, "agent", tenant)


def suggestion(file_id: str, clerk: User, **overrides) -> dict:
    """Gợi ý như svc-files lưu sau một lần đọc (§2 của hợp đồng); tenant_id, agent_id, read_at không gửi."""
    row = {"file_id": file_id, "requested_by": clerk.sub, "status": "ok", "method": "text", "pages": 1,
           "fields": FIELDS, "warnings": ["future_date"], "summary_source": "model", "model": "qwen3:1.7b",
           "duration_ms": 8123}
    row.update(overrides)
    return row


def event(file_id: str, clerk: User, **diff) -> dict:
    """Dòng sổ intake.suggested: chỉ siêu dữ liệu, giá trị vô hướng, không có giá trị của trường nào."""
    body = {"user_id": clerk.sub, "file_id": file_id, "status": "ok", "method": "text", "pages": 1, "found": FOUND,
            "summary_source": "model", "model": "qwen3:1.7b", "duration_ms": 8123, "reason": None}
    body.update(diff)
    return {"request_id": f"req-{file_id[:8]}", "action": "intake.suggested", "entity": "core.files",
            "entity_id": file_id, "diff": body}


def stored(file_id: str) -> list[list[str]]:
    return sql("select tenant_id, requested_by, agent_id, status, method, pages, summary_source, model "
               f"from office.intake_suggestions where file_id = '{file_id}'")


def ledger(file_id: str) -> list[list[str]]:
    return sql("select tenant_id, actor_id, actor_kind, request_id, action, entity from core.audit_log "
               f"where entity = 'core.files' and entity_id = '{file_id}' and action = 'intake.suggested' order by id")


def count(file_id: str) -> str:
    return sql(f"select count(*) from office.intake_suggestions where file_id = '{file_id}'")[0][0]


def attach(tenant: str, doc_id: str, file_id: str, by: str, role: str = "main") -> str:
    return ("insert into office.document_files (tenant_id, document_id, file_id, role, added_by) "
            f"values ('{tenant}', '{doc_id}', '{file_id}', '{role}', '{by}')")


# Văn bản hạn chế có từ trước F3.7 có thể mang tệp rõ. Nay trigger document_files_sealed và documents_restricted_sealed
# (migration 1792281601600) chặn hai đường dưới; tắt chúng trong cùng giao dịch để kiểm phần dọn gợi ý vẫn đúng cho
# dữ liệu cũ (như test_file_texts.py).
def legacy(statement: str, trigger: str, table: str) -> None:
    sql(f"alter table {table} disable trigger {trigger}; {statement}; alter table {table} enable trigger {trigger}")


# --- lưu, đọc lại ---------------------------------------------------------------------------------------------------


def test_agent_saves_suggestion_and_ledger_row_in_one_request(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    reader = agent(world.tenant_a)
    data = reader.gql(SAVE, {"o": suggestion(file_id, world.clerk_a), "e": event(file_id, world.clerk_a)})
    assert data["insert_office_intake_suggestions_one"]["file_id"] == file_id
    assert data["insert_core_audit_log"] == {"affected_rows": 1}
    # thuê ước, danh tính tác tử lấy từ phiên; văn thư bấm đọc là requested_by
    assert stored(file_id) == [[world.tenant_a, world.clerk_a.sub, AGENT_ID, "ok", "text", "1", "model", "qwen3:1.7b"]]
    assert ledger(file_id) == [[world.tenant_a, AGENT_ID, "agent", f"req-{file_id[:8]}", "intake.suggested",
                                "core.files"]]
    # lần bấm sau: svc-files trả bản đã lưu (cached), không ghi sổ
    cached = reader.gql(CACHED, {"id": file_id})["office_intake_suggestions_by_pk"]
    assert cached["fields"] == FIELDS and cached["warnings"] == ["future_date"]
    assert (cached["status"], cached["method"], cached["pages"], cached["summary_source"], cached["model"],
            cached["duration_ms"]) == ("ok", "text", 1, "model", "qwen3:1.7b", 8123)
    assert cached["read_at"] == data["insert_office_intake_suggestions_one"]["read_at"]
    assert sql("select audit_id, problem from core.audit_verify()") == []


def test_reading_again_overwrites_the_saved_suggestion(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    first = agent(world.tenant_a).gql(SAVE, {"o": suggestion(file_id, world.clerk_a),
                                             "e": event(file_id, world.clerk_a)})
    first_at = first["insert_office_intake_suggestions_one"]["read_at"]
    # "Đọc lại" (force): OCR không ra trường nào; tác tử khác tên (MOC_AGENT_ID) thì agent_id theo phiên mới
    again = suggestion(file_id, world.clerk_a, status="empty", method="ocr", fields={}, warnings=["low_text"],
                       summary_source="none", model=None, duration_ms=30120)
    second = agent(world.tenant_a, f"{AGENT_ID}-2").gql(SAVE, {"o": again, "e": event(
        file_id, world.clerk_a, status="empty", method="ocr", found="", summary_source="none", model=None,
        duration_ms=30120)})
    assert second["insert_office_intake_suggestions_one"]["file_id"] == file_id
    assert stored(file_id) == [[world.tenant_a, world.clerk_a.sub, f"{AGENT_ID}-2", "empty", "ocr", "1", "none",
                                "NULL"]]
    assert sql(f"select read_at > '{first_at}'::timestamptz, fields::text, warnings::text "
               f"from office.intake_suggestions where file_id = '{file_id}'") == [["t", "{}", '["low_text"]']]
    assert len(ledger(file_id)) == 2                                 # mỗi lần đọc thật một dòng sổ


@pytest.mark.parametrize("column", ["tenant_id", "agent_id", "read_at"])
def test_agent_cannot_choose_tenant_identity_or_time(world: World, column: str):
    file_id = insert_file(world.service_a, world.clerk_a)
    value = {"tenant_id": world.tenant_b, "agent_id": "gia-mao", "read_at": "2026-01-01T00:00:00+07:00"}[column]
    body = agent(world.tenant_a).raw(SAVE_ONE, {"o": {**suggestion(file_id, world.clerk_a), column: value}})
    assert "errors" in body and column in body["errors"][0]["message"]
    # đọc lại cũng không đổi được các cột đó
    body = agent(world.tenant_a).raw(
        "mutation ($o: office_intake_suggestions_insert_input!) { insert_office_intake_suggestions_one(object: $o, "
        f"on_conflict: {{constraint: intake_suggestions_pkey, update_columns: [{column}]}}) {{ file_id }} }}",
        {"o": suggestion(file_id, world.clerk_a)})
    assert "errors" in body
    assert stored(file_id) == []


def test_other_tenant_cannot_save_or_read_suggestions_of_a_file(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    other = agent(world.tenant_b)
    with pytest.raises(GraphQLError, match="foreign key"):          # tệp không thuộc đơn vị trong phiên
        other.gql(SAVE_ONE, {"o": suggestion(file_id, world.clerk_b)})
    agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(file_id, world.clerk_a)})
    assert other.gql(CACHED, {"id": file_id})["office_intake_suggestions_by_pk"] is None
    # ghi đè từ đơn vị khác: quyền update lọc theo thuê ước, dòng của đơn vị A giữ nguyên
    body = other.raw(SAVE_ONE, {"o": suggestion(file_id, world.clerk_b, status="empty", fields={})})
    assert "errors" in body or body["data"]["insert_office_intake_suggestions_one"] is None
    assert stored(file_id) == [[world.tenant_a, world.clerk_a.sub, AGENT_ID, "ok", "text", "1", "model", "qwen3:1.7b"]]


@pytest.mark.parametrize(("column", "value"), [
    ("fields", {"signer": {"value": "Nguyễn Văn A", "confidence": "high", "source": "rule"}}),   # khóa lạ
    ("fields", [{"value": "123/QĐ-UBND", "confidence": "high", "source": "rule"}]),              # không phải đối tượng
    ("fields", {"summary": {"value": "Về việc " + "x" * 17000, "confidence": "low", "source": "rule"}}),  # quá 16 KB
    ("warnings", {"future_date": True}),                                                         # không phải mảng
    ("status", "unreadable"),            # đọc hỏng chỉ ghi dòng sổ, không lưu gợi ý
    ("method", "model"),
    ("summary_source", "guess"),
    ("pages", 201),
    ("duration_ms", -1),
    ("requested_by", ""),
    ("model", "m" * 101),
])
def test_suggestion_shape_is_checked(world: World, column: str, value: object):
    file_id = insert_file(world.service_a, world.clerk_a)
    with pytest.raises(GraphQLError, match=f"intake_suggestions_{column}_check"):
        agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(file_id, world.clerk_a, **{column: value})})
    assert stored(file_id) == []


# --- văn bản hạn chế ------------------------------------------------------------------------------------------------


def test_encrypted_files_never_get_suggestions(world: World):
    file_id = insert_file(world.service_a, world.clerk_a, encrypted=True)
    with pytest.raises(GraphQLError, match="intake_suggestions_sealed"):
        agent(world.tenant_a).gql(SAVE, {"o": suggestion(file_id, world.clerk_a), "e": event(file_id, world.clerk_a)})
    assert stored(file_id) == [] and ledger(file_id) == []          # một giao dịch: dòng sổ cũng không ghi
    with pytest.raises(SQLError, match="intake_suggestions_sealed"):   # kể cả ghi thẳng CSDL
        sql("insert into office.intake_suggestions (file_id, tenant_id, requested_by, agent_id, status, method, pages, "
            f"duration_ms) values ('{file_id}', '{world.tenant_a}', '{world.clerk_a.sub}', '{AGENT_ID}', 'ok', 'text', "
            "1, 10)")


def test_files_of_restricted_documents_never_get_suggestions(world: World):
    secret = received(world.clerk_a, incoming(world.tag, 4101, restricted=True))
    file_id = insert_file(world.service_a, world.clerk_a)            # tệp rõ có từ trước F3.7
    legacy(attach(world.tenant_a, secret["id"], file_id, world.clerk_a.sub), "document_files_sealed",
           "office.document_files")
    with pytest.raises(GraphQLError, match="intake_suggestions_sealed"):
        agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(file_id, world.clerk_a)})
    assert count(file_id) == "0"


def test_restricting_a_document_drops_suggestions_already_saved(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(file_id, world.clerk_a)})
    doc = received(world.clerk_a, incoming(world.tag, 4102))
    sql(attach(world.tenant_a, doc["id"], file_id, world.clerk_a.sub))
    assert count(file_id) == "1"                     # văn bản thường: gợi ý vẫn giữ để đo độ chính xác
    sql(f"update office.documents set summary = summary || ' (sửa)' where id = '{doc['id']}'")
    assert count(file_id) == "1"                     # sửa trường khác: giữ nguyên
    with pytest.raises(SQLError, match="documents_restricted_sealed"):   # tệp rõ không tự mã hóa lại được
        sql(f"update office.documents set restricted = true where id = '{doc['id']}'")
    legacy(f"update office.documents set restricted = true where id = '{doc['id']}'", "documents_restricted_sealed",
           "office.documents")
    assert count(file_id) == "0"


def test_attaching_a_read_file_to_a_restricted_document_drops_its_suggestion(world: World):
    secret = received(world.clerk_a, incoming(world.tag, 4103, restricted=True))
    file_id = insert_file(world.service_a, world.clerk_a)
    agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(file_id, world.clerk_a)})
    with pytest.raises(SQLError, match="document_files_sealed"):
        sql(attach(world.tenant_a, secret["id"], file_id, world.clerk_a.sub))
    assert count(file_id) == "1"
    legacy(attach(world.tenant_a, secret["id"], file_id, world.clerk_a.sub), "document_files_sealed",
           "office.document_files")
    assert count(file_id) == "0"


def test_suggestions_follow_their_file(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(file_id, world.clerk_a)})
    sql(f"delete from core.files where id = '{file_id}'")
    assert count(file_id) == "0"


# --- ai thấy gì, ai ghi được gì -------------------------------------------------------------------------------------


def test_no_user_role_reads_or_writes_suggestions(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(file_id, world.clerk_a)})
    for user in (world.clerk_a, world.director_a, world.manager_a1, world.staff_a1, world.admin_a):
        assert "errors" in user.raw("{ office_intake_suggestions { file_id fields } }"), user.role
        assert "errors" in user.raw(CACHED, {"id": file_id}), user.role
        assert "errors" in user.raw(SAVE_ONE, {"o": suggestion(file_id, user)}), user.role
    assert stored(file_id)[0][2:4] == [AGENT_ID, "ok"]


def test_agent_has_no_other_rights(world: World):
    reader = agent(world.tenant_a)
    doc = received(world.clerk_a, incoming(world.tag, 4104))
    for query in ("{ office_documents { id } }", "{ core_files { id } }", "{ office_document_files { file_id } }",
                  "{ core_file_texts { content } }", "{ core_audit_log { id } }", "{ office_document_types { code } }"):
        assert "errors" in reader.raw(query), query
    for mutation, variables in (
        (INSERT_DOC, {"o": incoming(world.tag, 4105)}),
        ("mutation ($id: uuid!) { update_office_documents_by_pk(pk_columns: {id: $id}, "
         '_set: {summary: "Về việc tác tử tự sửa văn bản"}) { id } }', {"id": doc["id"]}),
        ("mutation { delete_office_intake_suggestions(where: {}) { affected_rows } }", {}),
    ):
        assert "errors" in reader.raw(mutation, variables), mutation
    assert sql(f"select summary from office.documents where id = '{doc['id']}'") == [[incoming(world.tag, 4104)[
        "summary"]]]


def test_agent_ledger_rows_always_carry_its_identity(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    reader = agent(world.tenant_a)
    # đọc hỏng (422): chỉ dòng sổ, không gợi ý
    failed = event(file_id, world.clerk_a, status="unreadable", found="", summary_source="none", model=None,
                   reason="password")
    assert reader.gql(LOG, {"e": failed})["insert_core_audit_log"] == {"affected_rows": 1}
    assert ledger(file_id) == [[world.tenant_a, AGENT_ID, "agent", f"req-{file_id[:8]}", "intake.suggested",
                                "core.files"]]
    # người ghi, loại người ghi, thuê ước không gửi lên được
    for column, value in (("actor_id", world.clerk_a.sub), ("actor_kind", "user"), ("tenant_id", world.tenant_b)):
        body = reader.raw(LOG, {"e": {**event(file_id, world.clerk_a), column: value}})
        assert "errors" in body and column in body["errors"][0]["message"], column
    # chỉ sự kiện intake.suggested về một tệp
    for column, value in (("action", "file.decrypted"), ("action", "insert"), ("entity", "office.documents")):
        body = reader.raw(LOG, {"e": {**event(file_id, world.clerk_a), column: value}})
        assert "errors" in body and "permission" in body["errors"][0]["message"], (column, value)
    assert len(ledger(file_id)) == 1
    assert sql(f"select count(*) from core.audit_log where entity_id = '{file_id}' and actor_id = '{AGENT_ID}'") == [
        ["1"]]


def test_ledger_view_shows_how_the_agent_read_not_what_it_read(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    # svc-files không bao giờ đưa giá trị vào diff; cố tình nhét vào thì màn xem sổ vẫn chỉ có tên khóa
    leaked = {"summary": "Về việc tăng cường kỷ luật", "symbol": "123/QĐ-UBND", "issuer_name": "Ủy ban nhân dân"}
    agent(world.tenant_a).gql(LOG, {"e": event(file_id, world.clerk_a, **leaked)})
    for viewer in (world.director_a, world.admin_a):
        [row] = viewer.gql(AUDIT_VIEW, {"e": file_id})["core_audit_log"]
        assert (row["actor_id"], row["actor_kind"], row["action"], row["entity"]) == (
            AGENT_ID, "agent", "intake.suggested", "core.files")
        assert row["overview"] == {
            "user_id": world.clerk_a.sub, "file_id": file_id, "status": "ok", "method": "text", "pages": 1,
            "found": FOUND, "summary_source": "model", "model": "qwen3:1.7b", "duration_ms": 8123, "reason": None,
            "summary": None, "symbol": None, "issuer_name": None}
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert other.gql(AUDIT_VIEW, {"e": file_id})["core_audit_log"] == []


def test_intake_keys_show_only_on_intake_rows_and_dispatch_keys_stay(world: World):
    # khóa của F3.12 (lần gửi liên thông) vẫn trong danh sách chung; method, found… chỉ có giá trị ở dòng
    # intake.suggested
    entity_id = f"lt-{world.tag}"
    shown = {"to_tenant_id": [None, world.tenant_b], "incoming_document_id": [None, "van-ban-den"],
             "source_id": [None, "van-ban-gui"], "attempts": [0, 1],
             "delivered_at": [None, "2026-10-21T10:00:00+07:00"]}
    hidden = {"last_error": [None, "svc-files 503"], "method": [None, "ocr"], "found": [None, "symbol"]}
    world.service_a.gql(INSERT_EVENT, {"o": {
        "actor_id": "svc-workflow", "actor_kind": "service", "action": "update", "entity": "office.dispatches",
        "entity_id": entity_id, "diff": {**shown, **hidden}}})
    [[text]] = sql(f"select core.audit_overview(a)::text from core.audit_log a where a.entity_id = '{entity_id}'")
    assert json.loads(text) == {**shown, **dict.fromkeys(hidden)}


@pytest.fixture(scope="module")
def tenant_x(world: World) -> str:
    """Đơn vị riêng để đổi tên dưới nhiều phiên giả lập (không đổi tên đơn vị A mà test khác so)."""
    return sql(f"insert into core.tenants (code, name) values ('X{world.tag}', 'Đơn vị thử tác tử') returning id")[0][0]


@pytest.mark.parametrize(("role", "kind"), [("agent", "agent"), ("service", "service"), ("admin", "system"),
                                            ("clerk", "user")])
def test_audit_trigger_names_the_kind_of_actor_from_the_hasura_role(world: World, tenant_x: str, role: str, kind: str):
    # phiên Hasura giả lập bằng biến hasura.user, như Hasura đặt trong mỗi giao dịch của GraphQL
    actor = f"{role}-{world.tag}"
    session = json.dumps({"x-hasura-role": role, "x-hasura-user-id": actor})
    sql("do $$ begin "
        f"perform set_config('hasura.user', '{session}', true); "
        f"update core.tenants set name = 'Đơn vị thử tác tử ({role})' where id = '{tenant_x}'; "
        "end $$")
    assert sql("select actor_id, actor_kind from core.audit_log where entity = 'core.tenants' "
               f"and entity_id = '{tenant_x}' order by id desc limit 1") == [[actor, kind]]


# --- độ chính xác trên dữ liệu thật ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    tenant: str
    clerk: User
    director: User
    admin: User


@pytest.fixture(scope="module")
def unit() -> Unit:
    """Một đơn vị riêng (không dùng chung đơn vị A của các test khác), nên số đếm của view biết trước."""
    tag = uuid.uuid4().hex[:6].upper()
    [[tenant]] = sql(f"insert into core.tenants (code, name) values ('G{tag}', 'Đơn vị thử đọc văn bản') returning id")
    u = Unit(tenant, User(f"van-thu-{tag}", "clerk", tenant), User(f"hieu-truong-{tag}", "director", tenant),
             User(f"quan-tri-{tag}", "tenant_admin", tenant))
    files = Service(f"svc-{tag}", "service", tenant)
    reader = agent(tenant)

    def intake(fields: dict, doc: dict | None, *, role: str = "main", cancel: bool = False) -> None:
        file_id = insert_file(files, u.clerk)
        reader.gql(SAVE_ONE, {"o": suggestion(file_id, u.clerk, fields=fields)})
        if doc is None:                              # văn thư chưa lưu văn bản
            return
        doc_id = doc["id"] if "id" in doc else received(u.clerk, doc)["id"]
        sql(attach(tenant, doc_id, file_id, u.clerk.sub, role))
        if cancel:
            sql(f"update office.documents set status = 'cancelled' where id = '{doc_id}'")

    # 1. giữ nguyên cả sáu trường; số ký hiệu khác khoảng trắng, hoa thường, cơ quan khác hoa thường, khoảng trắng
    intake({"symbol": {"value": "12 /qđ-ubnd", "confidence": "high", "source": "rule"},
            "issued_on": {"value": "2026-10-15", "confidence": "high", "source": "rule"},
            "issuer_name": {"value": "ỦY BAN NHÂN DÂN  TỈNH MẪU", "confidence": "medium", "source": "rule"},
            "type_code": {"value": "QĐ", "confidence": "high", "source": "rule"},
            "urgency": {"value": "khan", "confidence": "high", "source": "rule"},
            "summary": {"value": "Quyết định ban hành Quy chế thử nghiệm đọc văn bản", "confidence": "medium",
                        "source": "model"}},
           {"type_code": "QĐ", "symbol": "12/QĐ-UBND", "issuer_name": "Ủy ban nhân dân tỉnh Mẫu",
            "issued_on": "2026-10-15", "urgency": "khan",
            "summary": "Quyết định ban hành Quy chế thử nghiệm đọc văn bản"})
    # 2. văn thư sửa số ký hiệu và trích yếu, giữ ngày
    second = received(u.clerk, {"type_code": "TB", "symbol": "14/TB-UBND", "issuer_name": "Ủy ban nhân dân tỉnh Mẫu",
                                "issued_on": "2026-10-16", "summary": "Thông báo lịch họp giao ban tháng 11"})
    intake({"symbol": {"value": "13/TB-UBND", "confidence": "high", "source": "rule"},
            "issued_on": {"value": "2026-10-16", "confidence": "high", "source": "rule"},
            "summary": {"value": "Thông báo lịch họp", "confidence": "low", "source": "rule"}}, second)
    # không tính: tệp đính kèm (không phải bản chính), văn bản đã hủy, tệp chưa vào văn bản nào
    intake({"symbol": {"value": "99/TB-UBND", "confidence": "high", "source": "rule"}}, second, role="attachment")
    intake({"symbol": {"value": "15/TB-UBND", "confidence": "high", "source": "rule"}},
           {"type_code": "TB", "symbol": "15/TB-UBND", "issuer_name": "Ủy ban nhân dân tỉnh Mẫu",
            "issued_on": "2026-10-16", "summary": "Thông báo đã hủy vì tiếp nhận nhầm"}, cancel=True)
    intake({"symbol": {"value": "16/TB-UBND", "confidence": "high", "source": "rule"}}, None)
    return u


def test_postgres_lowercases_vietnamese():
    # view so cơ quan ban hành không phân biệt hoa thường bằng lower(), như chỉ mục documents_in_dedup. Sai ở đây thì
    # locale của image postgres không hạ được chữ Việt: so trong kịch bản đo (scripts/demo.py do-doc-van-ban) thay view
    assert sql("select lower('ỦY BAN NHÂN DÂN TỈNH MẪU') = 'ủy ban nhân dân tỉnh mẫu', upper('qđ') = 'QĐ'") == [
        ["t", "t"]]


def test_accuracy_counts_suggestions_the_clerk_kept(unit: Unit):
    for viewer in (unit.director, unit.admin):
        rows = viewer.gql(ACCURACY)["office_v_intake_accuracy"]
        assert sorted((r["field"], r["confidence"], r["suggested"], r["kept"]) for r in rows) == [
            ("issued_on", "high", 2, 2),
            ("issuer_name", "medium", 1, 1),
            ("summary", "low", 1, 0),
            ("summary", "medium", 1, 1),
            ("symbol", "high", 2, 1),
            ("type_code", "high", 1, 1),
            ("urgency", "high", 1, 1),
        ], viewer.role
        assert viewer.gql(ACCURACY_SUM)["office_v_intake_accuracy_aggregate"]["aggregate"]["sum"] == {
            "suggested": 9, "kept": 7}


def test_accuracy_is_for_leaders_of_the_unit_only(world: World, unit: Unit):
    assert "errors" in unit.clerk.raw(ACCURACY)
    for user in (world.staff_a1, world.manager_a1, world.clerk_a):
        assert "errors" in user.raw(ACCURACY), user.role
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)   # đơn vị B chưa lưu gợi ý nào
    assert other.gql(ACCURACY)["office_v_intake_accuracy"] == []


def test_accuracy_leaves_out_restricted_documents(unit: Unit):
    # chạy sau hai test trên (đổi dữ liệu của đơn vị): văn bản bật hạn chế (dữ liệu cũ) thì gợi ý của tệp bị xóa,
    # ra khỏi số đếm
    [[doc_id]] = sql(f"select id from office.documents where tenant_id = '{unit.tenant}' and symbol = '12/QĐ-UBND'")
    legacy(f"update office.documents set restricted = true where id = '{doc_id}'", "documents_restricted_sealed",
           "office.documents")
    rows = unit.director.gql(ACCURACY)["office_v_intake_accuracy"]
    assert sorted((r["field"], r["confidence"], r["suggested"], r["kept"]) for r in rows) == [
        ("issued_on", "high", 1, 1), ("summary", "low", 1, 0), ("symbol", "high", 1, 0)]
