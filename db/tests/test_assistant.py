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

"""Trợ lý hỏi đáp trên kho văn bản (F4.2, migration 1792281602000): tác tử moc-assistant (vai trò Hasura agent) ghi
mỗi câu trả lời thành một dòng sổ assistant.answered về ai.questions — danh tính, thuê ước đặt sẵn từ phiên, không ghi
được sự kiện nào khác; màn Sổ kiểm toán thấy chế độ, số đoạn, số nguồn, mô hình, không thấy câu hỏi hay văn bản nguồn;
core.file_texts có ranh giới trang (page_starts) để trích dẫn ghi số trang. svc-files không chạy ở đây: test gửi đúng
các truy vấn của hợp đồng F4.2 (§3 sổ, §5.3 ChunkSources và AskDocuments, SaveText của F2.7 thêm page_starts)."""

from __future__ import annotations

import json
import uuid

import pytest
from conftest import (
    ADMIN_SECRET,
    Agent,
    GraphQLError,
    SQLError,
    User,
    World,
    gql_raw,
    incoming,
    insert_file,
    received,
    sql,
)

AGENT_ID = "moc-assistant"

# svc_files.assist.store (hợp đồng §6.4): một dòng sổ mỗi lượt hỏi, ghi xong mới trả lời
LOG = """mutation GhiSoTroLy($e: core_audit_log_insert_input!) {
  insert_core_audit_log(objects: [$e]) { affected_rows } }"""

AUDIT_VIEW = """query ($e: String!) {
  core_audit_log(where: {entity_id: {_eq: $e}, action: {_eq: "assistant.answered"}}, order_by: {id: asc}) {
    actor_id actor_kind action entity overview } }"""
INSERT_EVENT = """mutation ($o: core_audit_log_insert_input!) { insert_core_audit_log_one(object: $o) { id } }"""

# svc_files.hasura (F2.7) — lưu chữ của tệp bằng khóa quản trị, nay kèm ranh giới trang dạng mảng JSON
SAVE_TEXT = """mutation SaveText($o: core_file_texts_insert_input!) {
  insert_core_file_texts_one(object: $o, on_conflict: {constraint: file_texts_pkey, update_columns: []}) { file_id }
}"""

# Hợp đồng §5.3: nguồn của chỉ mục đoạn (khóa quản trị, mọi thuê ước) và hậu kiểm bằng token người hỏi
CHUNK_SOURCES = """
query ChunkSources($since: timestamptz!, $limit: Int!, $after: uuid!) {
  office_documents(where: {_and: [{id: {_gt: $after}}, {_or: [
      {updated_at: {_gte: $since}},
      {files: {role: {_in: ["main", "attachment", "issued"]}, file: {text: {extracted_at: {_gte: $since}}}}},
      {assignments: {assigned_at: {_gte: $since}}}]}]}, order_by: {id: asc}, limit: $limit) {
    id tenant_id direction status type_code symbol issuer_name issued_on summary restricted department_id created_by
    updated_at document_type { name }
    assignments(where: {status: {_neq: "cancelled"}}) { department_id user_id assigned_at }
    files(where: {role: {_in: ["main", "attachment", "issued"]}}, order_by: {added_at: asc}) {
      role file_id file { encrypted text { status pages content page_starts extracted_at } } } } }"""
ASK_DOCUMENTS = """
query AskDocuments($ids: [uuid!]!) {
  office_documents(where: {id: {_in: $ids}}) { id direction status type_code symbol issuer_name issued_on summary
    restricted document_type { name } } }"""

ASSIGN = """mutation ($o: office_assignments_insert_input!) { insert_office_assignments_one(object: $o) { id } }"""

# Ba trang, mỗi trang một dòng; page_starts = vị trí ký tự đầu mỗi trang trong content
PAGES = [
    "Điều 1. Sinh viên có điểm trung bình chung học kỳ từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt được xét.\n",
    "Điều 2. Mức học bổng loại khá bằng mức học phí của học kỳ.\n",
    "Điều 3. Hồ sơ nộp về Phòng Công tác sinh viên trước ngày 15/11/2026.",
]
CONTENT = "".join(PAGES)
STARTS = [sum(len(p) for p in PAGES[:i]) for i in range(len(PAGES))]


def agent(tenant: str, sub: str = AGENT_ID) -> Agent:
    return Agent(sub, "agent", tenant)


def event(ask_id: str, asker: User, **diff) -> dict:
    """Dòng sổ assistant.answered (hợp đồng §3): chỉ giá trị vô hướng, không câu hỏi, câu trả lời, đoạn trích."""
    body = {"user_id": asker.sub, "ask_id": ask_id, "mode": "extract", "status": "answered", "answer_source": "extract",
            "hits": 5, "cited": 2, "documents": f"{uuid.uuid4()},{uuid.uuid4()}", "semantic": True, "model": None,
            "embed_model": "qwen3-embedding:0.6b", "duration_ms": 142, "warnings": ""}
    body.update(diff)
    return {"request_id": f"req-{ask_id[:8]}", "action": "assistant.answered", "entity": "ai.questions",
            "entity_id": ask_id, "diff": body}


def ledger(ask_id: str) -> list[list[str]]:
    return sql("select tenant_id, actor_id, actor_kind, request_id, action, entity from core.audit_log "
               f"where entity_id = '{ask_id}' order by id")


def admin(query: str, variables: dict | None = None) -> dict:
    """Như svc-files gọi bằng khóa quản trị (vòng chỉ mục nền)."""
    body = gql_raw(query, variables, headers={"X-Hasura-Admin-Secret": ADMIN_SECRET})
    if "errors" in body:
        raise GraphQLError(body["errors"])
    return body["data"]


def attach(tenant: str, doc_id: str, file_id: str, by: str, role: str = "main") -> None:
    sql("insert into office.document_files (tenant_id, document_id, file_id, role, added_by) "
        f"values ('{tenant}', '{doc_id}', '{file_id}', '{role}', '{by}')")


def save_text(file_id: str, tenant: str, **overrides) -> dict:
    row = {"file_id": file_id, "tenant_id": tenant, "status": "ok", "pages": len(PAGES), "content": CONTENT,
           "note": None, "page_starts": STARTS}
    row.update(overrides)
    return admin(SAVE_TEXT, {"o": row})


def stored_starts(file_id: str) -> list[list[str]]:
    return sql(f"select status, page_starts::text from core.file_texts where file_id = '{file_id}'")


# --- dòng sổ của trợ lý ---------------------------------------------------------------------------------------------


def test_agent_records_each_answer_under_its_own_identity(world: World):
    ask_id = str(uuid.uuid4())
    assistant = agent(world.tenant_a)
    assert assistant.gql(LOG, {"e": event(ask_id, world.clerk_a)}) == {"insert_core_audit_log": {"affected_rows": 1}}
    # lượt generate gửi lại ask_id: hai dòng cùng entity_id, cùng người ghi
    assistant.gql(LOG, {"e": event(ask_id, world.clerk_a, mode="generate", answer_source="model",
                                   model="qwen3:1.7b", duration_ms=18230)})
    row = [world.tenant_a, AGENT_ID, "agent", f"req-{ask_id[:8]}", "assistant.answered", "ai.questions"]
    assert ledger(ask_id) == [row, row]
    assert sql("select audit_id, problem from core.audit_verify()") == []


def test_identity_kind_and_tenant_come_from_the_session(world: World):
    ask_id = str(uuid.uuid4())
    assistant = agent(world.tenant_a)
    for column, value in (("actor_id", world.clerk_a.sub), ("actor_kind", "user"), ("tenant_id", world.tenant_b)):
        body = assistant.raw(LOG, {"e": {**event(ask_id, world.clerk_a), column: value}})
        assert "errors" in body and column in body["errors"][0]["message"], column
    assert ledger(ask_id) == []
    agent(world.tenant_b).gql(LOG, {"e": event(ask_id, world.clerk_b)})
    assert [r[:3] for r in ledger(ask_id)] == [[world.tenant_b, AGENT_ID, "agent"]]


@pytest.mark.parametrize(("action", "entity"), [
    ("assistant.answered", "core.files"),
    ("assistant.answered", "office.documents"),
    ("intake.suggested", "ai.questions"),
    ("insert", "ai.questions"),
    ("file.decrypted", "ai.questions"),
])
def test_agent_writes_only_answers_about_questions(world: World, action: str, entity: str):
    ask_id = str(uuid.uuid4())
    body = agent(world.tenant_a).raw(LOG, {"e": {**event(ask_id, world.clerk_a), "action": action, "entity": entity}})
    assert "errors" in body and "permission" in body["errors"][0]["message"], (action, entity)
    assert ledger(ask_id) == []


def test_reading_incoming_files_is_still_recorded(world: World):
    # quyền của tác tử đọc văn bản đến (F4.1) giữ nguyên sau khi thêm nhánh của trợ lý
    file_id = insert_file(world.service_a, world.clerk_a)
    reader = agent(world.tenant_a, "moc-doc-reader")
    reader.gql(LOG, {"e": {"request_id": f"req-{file_id[:8]}", "action": "intake.suggested", "entity": "core.files",
                           "entity_id": file_id, "diff": {"user_id": world.clerk_a.sub, "file_id": file_id,
                                                          "status": "ok", "method": "text", "pages": 1}}})
    # tệp vừa thêm đã có dòng sổ `insert` của chính nó — chỉ so dòng của tác tử
    assert [r for r in ledger(file_id) if r[2] == "agent"] == [
        [world.tenant_a, "moc-doc-reader", "agent", f"req-{file_id[:8]}", "intake.suggested", "core.files"]]


def test_assistant_has_no_other_rights(world: World):
    assistant = agent(world.tenant_a)
    doc = received(world.clerk_a, incoming(world.tag, 4201))
    for query in ("{ office_documents { id } }", "{ core_files { id } }", "{ office_document_files { file_id } }",
                  "{ core_file_texts { content page_starts } }", "{ core_audit_log { id } }",
                  "{ office_assignments { id } }"):
        assert "errors" in assistant.raw(query), query
    body = assistant.raw("mutation ($id: uuid!) { update_office_documents_by_pk(pk_columns: {id: $id}, "
                         '_set: {summary: "Về việc trợ lý tự sửa văn bản"}) { id } }', {"id": doc["id"]})
    assert "errors" in body
    assert sql(f"select summary from office.documents where id = '{doc['id']}'") == [
        [incoming(world.tag, 4201)["summary"]]]


def test_ledger_view_shows_how_it_answered_not_what(world: World):
    ask_id = str(uuid.uuid4())
    sources = f"{uuid.uuid4()},{uuid.uuid4()}"
    # svc-files không bao giờ đưa câu hỏi, câu trả lời vào diff; cố tình nhét vào thì màn xem sổ chỉ có tên khóa
    leaked = {"question": "Điều kiện xét học bổng khuyến khích học tập là gì?",
              "answer": "“…từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt.” [1]", "symbol": "88/CTSV",
              "excerpt": "Sinh viên có điểm trung bình chung học kỳ từ 3,2", "method": "text"}
    agent(world.tenant_a).gql(LOG, {"e": event(ask_id, world.clerk_a, mode="generate", model="qwen3:1.7b",
                                               warnings="model_timeout", documents=sources, **leaked)})
    for viewer in (world.director_a, world.admin_a):
        [row] = viewer.gql(AUDIT_VIEW, {"e": ask_id})["core_audit_log"]
        assert (row["actor_id"], row["actor_kind"], row["action"], row["entity"]) == (
            AGENT_ID, "agent", "assistant.answered", "ai.questions")
        assert row["overview"] == {
            "user_id": world.clerk_a.sub, "ask_id": ask_id, "mode": "generate", "status": "answered",
            "answer_source": "extract", "hits": 5, "cited": 2, "semantic": True, "model": "qwen3:1.7b",
            "embed_model": "qwen3-embedding:0.6b", "duration_ms": 142, "warnings": "model_timeout",
            # id văn bản nguồn: chỉ vai trò service đọc được (qua diff); khóa của F4.1 không hiện ở dòng này
            "documents": None, "question": None, "answer": None, "symbol": None, "excerpt": None, "method": None}
        assert "errors" in viewer.raw("{ core_audit_log { diff } }"), viewer.role
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert other.gql(AUDIT_VIEW, {"e": ask_id})["core_audit_log"] == []
    [row] = world.service_a.gql("query ($e: String!) { core_audit_log(where: {entity_id: {_eq: $e}}) { diff } }",
                                {"e": ask_id})["core_audit_log"]
    assert row["diff"]["documents"] == sources


def test_assistant_keys_show_only_on_answers_and_older_keys_stay(world: World):
    # khóa của F3.12 (lần gửi liên thông) vẫn trong danh sách chung; ask_id, hits… chỉ có giá trị ở dòng
    # assistant.answered
    entity_id = f"lt-{world.tag}-f42"
    shown = {"to_tenant_id": [None, world.tenant_b], "incoming_document_id": [None, "van-ban-den"],
             "source_id": [None, "van-ban-gui"], "attempts": [0, 1],
             "delivered_at": [None, "2026-10-21T10:00:00+07:00"]}
    hidden = {"last_error": [None, "svc-files 503"], "ask_id": [None, "x"], "mode": [None, "extract"],
              "hits": [0, 5], "semantic": [False, True], "warnings": [None, "model_timeout"]}
    world.service_a.gql(INSERT_EVENT, {"o": {
        "actor_id": "svc-workflow", "actor_kind": "service", "action": "update", "entity": "office.dispatches",
        "entity_id": entity_id, "diff": {**shown, **hidden}}})
    [[text]] = sql(f"select core.audit_overview(a)::text from core.audit_log a where a.entity_id = '{entity_id}'")
    assert json.loads(text) == {**shown, **dict.fromkeys(hidden)}

    # dòng intake.suggested (F4.1): khóa của tác tử đọc văn bản vẫn hiện, khóa của trợ lý thì không
    file_id = insert_file(world.service_a, world.clerk_a)
    intake = {"user_id": world.clerk_a.sub, "file_id": file_id, "status": "ok", "method": "ocr", "pages": 2,
              "found": "symbol", "summary_source": "rule", "model": None, "duration_ms": 900, "reason": None}
    agent(world.tenant_a, "moc-doc-reader").gql(LOG, {"e": {
        "action": "intake.suggested", "entity": "core.files", "entity_id": file_id,
        "diff": {**intake, "ask_id": "x", "hits": 3, "cited": 1, "answer_source": "model"}}})
    [[text]] = sql("select core.audit_overview(a)::text from core.audit_log a "
                   f"where a.entity_id = '{file_id}' and a.action = 'intake.suggested'")
    assert json.loads(text) == {**intake, "ask_id": None, "hits": None, "cited": None, "answer_source": None}


# --- ranh giới trang của lớp chữ PDF --------------------------------------------------------------------------------


def test_text_keeps_where_each_page_starts(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    assert save_text(file_id, world.tenant_a) == {"insert_core_file_texts_one": {"file_id": file_id}}
    assert stored_starts(file_id) == [["ok", "{" + ",".join(map(str, STARTS)) + "}"]]
    text = admin("query ($id: uuid!) { core_files_by_pk(id: $id) { text { pages page_starts } } }",
                 {"id": file_id})["core_files_by_pk"]["text"]
    assert text == {"pages": 3, "page_starts": STARTS}
    # đọc lại không ghi đè (F2.7: mỗi tệp đọc một lần)
    save_text(file_id, world.tenant_a, page_starts=[0])
    assert stored_starts(file_id)[0][1] == "{" + ",".join(map(str, STARTS)) + "}"


@pytest.mark.parametrize(("status", "content", "starts"), [
    ("ok", CONTENT, None),                          # dòng đọc trước F4.2: cả nội dung là một "trang" không số
    ("ok", CONTENT, [0]),                           # một trang
    ("ok", CONTENT, [0, 0, STARTS[1]]),             # trang 1 trống: cùng vị trí với trang sau
    ("ok", CONTENT, [0, len(CONTENT)]),             # trang cuối trống
    ("ok", CONTENT, [0] * 200),
    ("empty", "", None),                            # bản scan: không có trang nào để trích
    ("failed", "", None),
])
def test_page_starts_that_fit_the_text_are_saved(world: World, status: str, content: str, starts):
    file_id = insert_file(world.service_a, world.clerk_a)
    save_text(file_id, world.tenant_a, status=status, content=content, page_starts=starts,
              pages=None if status == "failed" else 3)
    assert stored_starts(file_id) == [[status, "NULL" if starts is None else "{" + ",".join(map(str, starts)) + "}"]]


def test_page_starts_beyond_the_text_are_refused_through_hasura(world: World):
    file_id = insert_file(world.service_a, world.clerk_a)
    with pytest.raises(GraphQLError, match="file_texts_page_starts"):    # tên ràng buộc tới được svc-files
        save_text(file_id, world.tenant_a, page_starts=[0, len(CONTENT) + 1])
    assert stored_starts(file_id) == []


@pytest.mark.parametrize(("status", "content", "starts"), [
    ("ok", CONTENT, f"'{{5,{STARTS[1]}}}'"),                   # trang đầu không bắt đầu ở 0
    ("ok", CONTENT, f"'{{0,{len(CONTENT) + 1}}}'"),            # vượt độ dài chữ
    ("ok", CONTENT, "array_fill(0, array[201])"),              # quá 200 trang
    ("ok", CONTENT, "'{}'"),
    ("ok", CONTENT, "'{0,NULL}'"),                             # so sánh với null ra null: phải chặn riêng
    ("ok", CONTENT, f"'{{0,NULL,{STARTS[2]}}}'"),
    ("empty", "", "'{0}'"),                                    # không có chữ thì không có trang
    ("failed", "", "'{0}'"),
])
def test_page_starts_must_fit_the_text(world: World, status: str, content: str, starts: str):
    file_id = insert_file(world.service_a, world.clerk_a)
    with pytest.raises(SQLError, match="file_texts_page_starts"):
        sql("insert into core.file_texts (file_id, tenant_id, status, pages, content, page_starts) "
            f"values ('{file_id}', '{world.tenant_a}', '{status}', 3, '{content}', {starts})")
    assert stored_starts(file_id) == []


def test_texts_of_restricted_documents_are_still_skipped(world: World):
    secret = received(world.clerk_a, incoming(world.tag, 4202, restricted=True))
    file_id = insert_file(world.service_a, world.clerk_a, encrypted=True)
    attach(world.tenant_a, secret["id"], file_id, world.clerk_a.sub)
    assert save_text(file_id, world.tenant_a) == {"insert_core_file_texts_one": None}   # bỏ qua, không báo lỗi
    assert stored_starts(file_id) == []


# --- truy vấn của chỉ mục đoạn và hậu kiểm --------------------------------------------------------------------------


def chunk_sources(since: str) -> list[dict]:
    rows, after = [], "00000000-0000-0000-0000-000000000000"
    while True:
        page = admin(CHUNK_SOURCES, {"since": since, "limit": 50, "after": after})["office_documents"]
        rows += page
        if len(page) < 50:
            return rows
        after = page[-1]["id"]


def test_chunk_sources_carry_pages_and_permission_attributes(world: World):
    [[since]] = sql("select to_char(now() at time zone 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')")
    doc = received(world.clerk_a, incoming(world.tag, 4211))
    secret = received(world.clerk_a, incoming(world.tag, 4212, restricted=True))
    plain = insert_file(world.service_a, world.clerk_a)
    sealed = insert_file(world.service_a, world.clerk_a, encrypted=True)
    attach(world.tenant_a, doc["id"], plain, world.clerk_a.sub)
    attach(world.tenant_a, secret["id"], sealed, world.clerk_a.sub)
    save_text(plain, world.tenant_a)
    save_text(sealed, world.tenant_a)
    lead = world.service_a.gql(ASSIGN, {"o": {"document_id": doc["id"], "department_id": world.dept_a1,
                                              "role": "lead", "assigned_by": world.director_a.sub}})
    world.service_a.gql(ASSIGN, {"o": {"document_id": doc["id"], "department_id": world.dept_a1,
                                       "parent_id": lead["insert_office_assignments_one"]["id"],
                                       "user_id": world.staff_a1.sub, "role": "support",
                                       "assigned_by": world.manager_a1.sub}})
    rows = {r["id"]: r for r in chunk_sources(since)}
    found = rows[doc["id"]]
    assert (found["tenant_id"], found["direction"], found["restricted"], found["created_by"]) == (
        world.tenant_a, "in", False, world.clerk_a.sub)
    assert found["document_type"]["name"]
    pairs = sorted(((a["department_id"], a["user_id"]) for a in found["assignments"]), key=lambda a: a[1] or "")
    assert pairs == [(world.dept_a1, None), (world.dept_a1, world.staff_a1.sub)]
    [f] = found["files"]
    assert (f["role"], f["file_id"], f["file"]["encrypted"]) == ("main", plain, False)
    assert (f["file"]["text"]["status"], f["file"]["text"]["page_starts"]) == ("ok", STARTS)
    # văn bản hạn chế vẫn được đọc ra (để vòng chỉ mục xóa đoạn của nó) nhưng không có chữ nào
    hidden = rows[secret["id"]]
    assert hidden["restricted"] is True and hidden["files"][0]["file"]["text"] is None


def test_ask_documents_answers_with_the_askers_rights(world: World):
    doc = received(world.clerk_a, incoming(world.tag, 4221))
    secret = received(world.clerk_a, incoming(world.tag, 4222, restricted=True))
    ids = [doc["id"], secret["id"]]

    def seen(user: User) -> dict[str, bool]:
        return {r["id"]: r["restricted"] for r in user.gql(ASK_DOCUMENTS, {"ids": ids})["office_documents"]}

    # người tạo đọc được văn bản hạn chế: svc-files bỏ đoạn của văn bản `restricted` dù Hasura trả về
    assert seen(world.clerk_a) == {doc["id"]: False, secret["id"]: True}
    assert seen(world.director_a) == {doc["id"]: False}
    for user in (world.manager_a1, world.staff_a1, world.clerk_b):
        assert seen(user) == {}, user.sub
    world.service_a.gql(ASSIGN, {"o": {"document_id": doc["id"], "department_id": world.dept_a1, "role": "lead",
                                       "assigned_by": world.director_a.sub}})
    assert seen(world.manager_a1) == {doc["id"]: False}
    assert seen(world.staff_a1) == {}               # giao cho phòng, chưa phân công cho người
    assert "errors" in world.admin_a.raw(ASK_DOCUMENTS, {"ids": ids})
