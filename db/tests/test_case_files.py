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

"""Hồ sơ công việc (F3.8): chuyên viên, tổ trưởng lập và đóng hồ sơ của phòng mình; chỉ văn bản đã xử lý xong, không
hạn chế, mình đọc được và thuộc phòng mình mới vào hồ sơ; ngày đóng do CSDL đặt; người dùng không tự chuyển hồ sơ sang
"đã nộp lưu"; hàm nộp lưu chỉ khóa quản trị gọi được, lệch với gói thì không đổi gì; hồ sơ đã nộp lưu không sửa được."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from conftest import ADMIN_SECRET, GraphQLError, Service, SQLError, User, World, gql_raw, insert_file, sql

CREATE = """
mutation ($o: office_case_files_insert_input!) {
  insert_office_case_files_one(object: $o) { id tenant_id department_id status created_by }
}"""
ADD = """
mutation ($o: office_case_file_documents_insert_input!) {
  insert_office_case_file_documents_one(object: $o) { case_file_id document_id tenant_id added_by }
}"""
CLOSE = """
mutation ($id: uuid!, $set: office_case_files_set_input!) {
  update_office_case_files(where: {id: {_eq: $id}}, _set: $set) { affected_rows }
}"""
LIST = "{ office_case_files { id code closed_on } }"
ARCHIVE = """
mutation ($p: jsonb!) { office_archive_case_file(args: {p: $p}) { id status archive_key } }"""


def _one(statement: str) -> str:
    return sql(statement)[0][0]


def _doc(world: World, *, direction: str = "in", status: str = "done", restricted: bool = False,
         assignee=None) -> str:
    """Văn bản đến giao cho `assignee` (mặc định staff_a1) cùng phòng của người đó, hoặc văn bản đi của phòng đó."""
    assignee = assignee or world.staff_a1
    department = assignee.department
    n = int.from_bytes(os.urandom(3), "big")
    if direction == "in":
        reg = _one(f"insert into office.registers (tenant_id, direction, year) values ('{world.tenant_a}', 'in', 2026)"
                   " on conflict (tenant_id, direction, year) do update set year = excluded.year returning id")
        doc = _one(
            "insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, "
            "summary, restricted, register_id, register_number, registered_at, created_by) values "
            f"('{world.tenant_a}', 'in', '{status}', 'CV', '{n}/UBND-VP', 'UBND tỉnh', '2026-08-20', "
            f"'Văn bản đến thử hồ sơ số {n}', {str(restricted).lower()}, '{reg}', {n}, now(), "
            f"'{world.clerk_a.sub}') returning id")
        sql(f"insert into office.assignments (tenant_id, document_id, department_id, user_id, role, assigned_by) "
            f"values ('{world.tenant_a}', '{doc}', '{department}', '{assignee.sub}', 'lead', '{world.director_a.sub}')")
        return doc
    reg = _one(f"insert into office.registers (tenant_id, direction, year) values ('{world.tenant_a}', 'out', 2026)"
               " on conflict (tenant_id, direction, year) do update set year = excluded.year returning id")
    sha = hashlib.sha256(os.urandom(16)).hexdigest()
    code = base64.b32encode(os.urandom(10)).decode()[:10]
    return _one(
        "insert into office.documents (tenant_id, direction, status, type_code, symbol, summary, issued_on, "
        "register_id, register_number, content_sha256, verify_code, signer_id, department_id, created_by) values "
        f"('{world.tenant_a}', 'out', 'issued', 'TB', '{n}/TB-ĐT', 'Thông báo thử hồ sơ số {n}', '2026-09-15', "
        f"'{reg}', {n}, '\\x{sha}', '{code}', 'lanh-dao', '{department}', '{world.staff_a1.sub}') returning id")


def _case_file(world: World, user=None) -> dict:
    user = user or world.staff_a1
    code = f"HS-{uuid.uuid4().hex[:8]}"
    return user.gql(CREATE, {"o": {"year": 2026, "code": code, "title": f"Hồ sơ tuyển sinh {code}",
                                   "retention_years": 10}})["insert_office_case_files_one"]


def _closed(world: World, *docs: str) -> dict:
    cf = _case_file(world)
    for doc in docs or (_doc(world),):
        world.staff_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": doc}})
    world.staff_a1.gql(CLOSE, {"id": cf["id"], "set": {"status": "closed"}})
    return cf


def _admin(query: str, variables: dict) -> dict:
    return gql_raw(query, variables, headers={"X-Hasura-Admin-Secret": ADMIN_SECRET,
                                              "X-Hasura-User-Id": "svc-files:archive"})


def test_staff_creates_case_file_of_own_department(world: World):
    cf = _case_file(world)
    assert (cf["tenant_id"], cf["department_id"], cf["status"], cf["created_by"]) == (
        world.tenant_a, world.dept_a1, "open", world.staff_a1.sub)
    ids = lambda u: {r["id"] for r in u.gql(LIST)["office_case_files"]}   # noqa: E731
    assert cf["id"] in ids(world.staff_a1b) and cf["id"] in ids(world.manager_a1)
    assert cf["id"] in ids(world.clerk_a) and cf["id"] in ids(world.director_a)
    assert cf["id"] not in ids(world.staff_a2) and cf["id"] not in ids(world.clerk_b)   # phòng khác, đơn vị khác


def test_only_finished_unrestricted_documents_join(world: World):
    cf = _case_file(world)
    for doc in (_doc(world), _doc(world, direction="out")):
        row = world.staff_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": doc}})
        assert row["insert_office_case_file_documents_one"]["added_by"] == world.staff_a1.sub
    with pytest.raises(GraphQLError, match="xử lý xong"):
        world.staff_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": _doc(world, status="in_progress")}})
    # văn bản hạn chế: chuyên viên không đọc được nên Hasura đã chặn; trigger chặn cả đường ghi thẳng CSDL
    with pytest.raises(SQLError, match="hạn chế"):
        sql(f"insert into office.case_file_documents (tenant_id, case_file_id, document_id, added_by) values "
            f"('{world.tenant_a}', '{cf['id']}', '{_doc(world, restricted=True)}', 'x')")
    with pytest.raises(GraphQLError):           # hồ sơ của phòng khác
        world.staff_a2.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": _doc(world)}})


def test_cannot_file_documents_of_other_departments(world: World):
    # đưa được văn bản phòng khác vào hồ sơ của mình là đọc được nó qua phòng đọc sau khi nộp lưu
    cf = _case_file(world)
    for doc in (_doc(world, assignee=world.staff_a2), _doc(world, direction="out", assignee=world.staff_a2)):
        with pytest.raises(GraphQLError):
            world.staff_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": doc}})
    unassigned = _doc(world)
    sql(f"delete from office.assignments where document_id = '{unassigned}'")
    with pytest.raises(GraphQLError):           # văn bản đến chưa giao cho ai: chuyên viên không đọc được
        world.staff_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": unassigned}})
    # giao cho phòng A1 mà chưa giao cho người: tổ trưởng A1 đưa vào hồ sơ được, chuyên viên A1 thì không đọc được
    to_dept = _doc(world)
    sql(f"update office.assignments set user_id = null where document_id = '{to_dept}'")
    with pytest.raises(GraphQLError):
        world.staff_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": to_dept}})
    world.manager_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": to_dept}})


def test_users_close_but_never_archive(world: World):
    cf = _case_file(world)
    with pytest.raises(GraphQLError, match="chưa có văn bản"):
        world.staff_a1.gql(CLOSE, {"id": cf["id"], "set": {"status": "closed"}})
    world.staff_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": _doc(world)}})
    with pytest.raises(GraphQLError):           # chỉ job nộp lưu chuyển sang archived
        world.staff_a1.gql(CLOSE, {"id": cf["id"], "set": {"status": "archived"}})
    with pytest.raises(GraphQLError):           # ngày đóng do CSDL đặt: lùi ngày là ép nộp lưu ngay
        world.staff_a1.gql(CLOSE, {"id": cf["id"], "set": {"status": "closed", "closed_on": "2020-01-01"}})
    closed = world.manager_a1.gql(CLOSE, {"id": cf["id"], "set": {"status": "closed"}})
    assert closed["update_office_case_files"]["affected_rows"] == 1
    today = (datetime.now(timezone.utc) + timedelta(hours=7)).date().isoformat()
    [row] = [r for r in world.staff_a1.gql(LIST)["office_case_files"] if r["id"] == cf["id"]]
    assert row["closed_on"] == today
    # đã đóng: không sửa, không thêm văn bản, không mở lại, không đổi ngày đóng
    again = world.staff_a1.gql(CLOSE, {"id": cf["id"], "set": {"title": "Đổi tên sau khi đóng"}})
    assert again["update_office_case_files"]["affected_rows"] == 0
    with pytest.raises(GraphQLError, match="đã đóng"):
        world.staff_a1.gql(ADD, {"o": {"case_file_id": cf["id"], "document_id": _doc(world)}})
    with pytest.raises(SQLError, match="không mở lại"):
        sql(f"update office.case_files set status = 'open', closed_on = null where id = '{cf['id']}'")
    with pytest.raises(SQLError, match="ngày đóng"):
        sql(f"update office.case_files set closed_on = '2020-01-01' where id = '{cf['id']}'")
    with pytest.raises(GraphQLError):           # thời hạn bảo quản: 1–100 năm hoặc vĩnh viễn (null)
        world.staff_a1.gql(CREATE, {"o": {"year": 2026, "code": f"HS-{uuid.uuid4().hex[:8]}",
                                          "title": "Hồ sơ thời hạn quá dài", "retention_years": 9000}})


def test_archive_function_is_admin_only_and_all_or_nothing(world: World):
    doc = _doc(world, direction="out")
    file_id = insert_file(world.service_a, world.staff_a1)
    sql(f"insert into office.document_files (tenant_id, document_id, file_id, role, added_by) values "
        f"('{world.tenant_a}', '{doc}', '{file_id}', 'issued', 'x')")
    sql(f"insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind) values "
        f"('{world.tenant_a}', '{doc}', 'office.document.issued', 'x', 'user')")
    events = [int(r[0]) for r in sql(f"select id from office.document_events where document_id = '{doc}'")]
    assignments = int(_one(f"select count(*) from office.assignments where document_id = '{doc}'"))
    cf = _closed(world, doc)
    key = f"cold/{world.tenant_a}/case/{cf['id']}/"
    p = {"id": cf["id"], "archive_key": key, "archive_sha256": hashlib.sha256(b"m").hexdigest(), "bucket": "moc-cold",
         "documents": [doc], "events": events, "links": [{"document_id": doc, "file_id": file_id}],
         "cold_files": [file_id], "files": 1}
    for user in (world.staff_a1, world.manager_a1, world.director_a, world.service_a):
        with pytest.raises(GraphQLError):       # không vai trò nào gọi được, kể cả service
            user.gql(ARCHIVE, {"p": p})
    audit = f"select count(*) from core.audit_log where action = 'case_file.archived' and entity_id = '{cf['id']}'"
    # gói lệch CSDL (thiếu một dòng thời gian sinh sau lúc chụp) → không đổi gì
    body = _admin(ARCHIVE, {"p": {**p, "events": events[:-1]}})
    assert "errors" in body and "đổi trong lúc nộp lưu" in str(body["errors"])
    assert _one(f"select status from office.case_files where id = '{cf['id']}'") == "closed"
    assert _one(audit) == "0"
    body = _admin(ARCHIVE, {"p": p})
    assert body["data"]["office_archive_case_file"] == [{"id": cf["id"], "status": "archived", "archive_key": key}]
    assert _one(f"select status from office.documents where id = '{doc}'") == "archived"
    assert _one(f"select count(*) from office.document_events where document_id = '{doc}'") == "0"
    assert _one(f"select count(*) from office.document_files where document_id = '{doc}'") == "0"
    assert int(_one(f"select count(*) from office.assignments where document_id = '{doc}'")) == assignments
    assert _one(f"select storage_tier from core.files where id = '{file_id}'") == "cold"
    assert _one(audit) == "1"
    # lần hai (vd hai lượt nộp lưu cùng lúc): bị từ chối, sổ kiểm toán không thêm dòng nào
    body = _admin(ARCHIVE, {"p": {**p, "archive_sha256": hashlib.sha256(b"khac").hexdigest()}})
    assert "errors" in body and "không còn ở trạng thái đã đóng" in str(body["errors"])
    assert _one(audit) == "1"
    # tệp đã nộp lưu chỉ còn trong bucket lạnh: không gắn lại vào dự thảo (tệp còn nóng thì gắn được)
    draft = _one("insert into office.documents (tenant_id, direction, status, type_code, summary, department_id, "
                 f"created_by) values ('{world.tenant_a}', 'out', 'draft', 'TB', 'Dự thảo thử gắn tệp đã nộp lưu', "
                 f"'{world.dept_a1}', '{world.staff_a1.sub}') returning id")
    attach = """mutation ($o: office_document_files_insert_input!) {
      insert_office_document_files_one(object: $o) { file_id } }"""
    hot = insert_file(world.service_a, world.staff_a1)
    world.staff_a1.gql(attach, {"o": {"document_id": draft, "file_id": hot, "role": "attachment"}})
    with pytest.raises(GraphQLError):
        world.staff_a1.gql(attach, {"o": {"document_id": draft, "file_id": file_id, "role": "attachment"}})
    with pytest.raises(SQLError, match="kho lạnh"):    # trigger chặn cả đường ghi thẳng CSDL
        sql(f"insert into office.document_files (tenant_id, document_id, file_id, role, added_by) values "
            f"('{world.tenant_a}', '{draft}', '{file_id}', 'attachment', 'x')")


def test_archived_is_frozen(world: World):
    cf = _closed(world)
    key = f"cold/{world.tenant_a}/case/{cf['id']}/"
    sql(f"update office.case_files set status = 'archived', archived_at = now(), archive_key = '{key}', "
        f"archive_sha256 = '\\x{hashlib.sha256(b'manifest').hexdigest()}' where id = '{cf['id']}'")
    with pytest.raises(SQLError, match="đã nộp lưu"):     # kể cả superuser CSDL
        sql(f"update office.case_files set title = 'Sửa sau khi nộp lưu' where id = '{cf['id']}'")
    rows = sql(f"select action from core.audit_log where entity = 'office.case_files' and entity_id = '{cf['id']}'"
               " order by id")
    assert [r[0] for r in rows] == ["insert", "update", "update"]


AUDIT_VIEW = """query ($e: String!) {
  core_audit_log(where: {entity_id: {_eq: $e}}, order_by: {id: asc}) { action entity overview }
}"""


def test_audit_shows_case_file_code_and_package_hash_not_title(world: World):
    cf = _closed(world)
    digest = hashlib.sha256(b"manifest").hexdigest()
    world.service_a.gql(
        """mutation ($o: core_audit_log_insert_input!) { insert_core_audit_log_one(object: $o) { id } }""",
        {"o": {"actor_id": "svc-files:archive", "actor_kind": "system", "action": "case_file.archived",
               "entity": "office.case_files", "entity_id": cf["id"],
               "diff": {"code": "HS-01", "archive_key": f"cold/{world.tenant_a}/case/{cf['id']}/",
                        "archive_sha256": digest, "bucket": "moc-cold", "documents": 3, "files": 2}}},
    )
    created, closed, archived = world.director_a.gql(AUDIT_VIEW, {"e": cf["id"]})["core_audit_log"]
    assert created["overview"]["retention_years"] == [None, 10] and created["overview"]["code"][1].startswith("HS-")
    assert "title" in created["overview"] and created["overview"]["title"] is None     # tên hồ sơ: chỉ biết có đổi
    assert closed["overview"]["status"] == ["open", "closed"] and closed["overview"]["closed_on"][0] is None
    assert archived["action"] == "case_file.archived"
    assert {k: v for k, v in archived["overview"].items() if v is not None} == {
        "code": "HS-01", "archive_sha256": digest, "documents": 3, "files": 2}


TIMES = "{ office_v_processing_time { month documents total_hours with_due on_time } }"
ACCURACY = "{ office_v_intake_accuracy { field confidence suggested kept } }"


def test_archiving_keeps_dashboard_and_intake_figures():
    """Nộp lưu gỡ dòng thời gian, liên kết tệp của văn bản, mà dashboard điều hành (v_processing_time) lấy lúc xong từ
    dòng thời gian, số đo đọc văn bản đến (v_intake_accuracy) nối gợi ý với văn bản qua liên kết tệp bản chính. Bản giữ
    lại lúc nộp lưu (migration 1792281602300) giữ nguyên mọi con số. Đơn vị riêng nên số đếm biết trước; một văn bản
    cùng tháng không nộp lưu để thấy số cộng đúng cả hai nguồn."""
    tag = uuid.uuid4().hex[:6].upper()
    tenant = _one(f"insert into core.tenants (code, name) values ('N{tag}', 'Đơn vị thử nộp lưu') returning id")
    dept = _one(f"insert into office.departments (tenant_id, code, name) values ('{tenant}', 'ĐT', 'Phòng Đào tạo') "
                "returning id")
    reg = _one(f"insert into office.registers (tenant_id, direction, year) values ('{tenant}', 'in', 2025) "
               "returning id")
    clerk, director = User(f"van-thu-{tag}", "clerk", tenant), User(f"lanh-dao-{tag}", "director", tenant)
    svc = Service(f"svc-{tag}", "service", tenant)

    def incoming_done(n: int, due: str) -> str:              # vào sổ 06/01/2025 8 giờ, đã xử lý xong
        return _one(
            "insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, "
            "summary, register_id, register_number, registered_at, due_on, created_by) values "
            f"('{tenant}', 'in', 'done', 'CV', '{n}/UBND-VP', 'UBND tỉnh', '2025-01-02', "
            f"'Văn bản đến thử nộp lưu số {n}', '{reg}', {n}, '2025-01-06 08:00+07', {due}, '{clerk.sub}') "
            "returning id")

    def event(doc: str, kind: str, at: str) -> None:
        sql(f"insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, created_at) "
            f"values ('{tenant}', '{doc}', '{kind}', 'chuyen-vien', 'user', '{at}')")

    def attach(doc: str, role: str, fields: dict) -> str:   # tệp, gợi ý tác tử đã đọc, liên kết vào văn bản
        file_id = insert_file(svc, clerk)
        sql("insert into office.intake_suggestions (file_id, tenant_id, requested_by, agent_id, status, method, "
            f"pages, fields, duration_ms) values ('{file_id}', '{tenant}', '{clerk.sub}', 'moc-doc-reader', 'ok', "
            f"'text', 1, '{json.dumps(fields, ensure_ascii=False)}', 10)")
        sql(f"insert into office.document_files (tenant_id, document_id, file_id, role, added_by) "
            f"values ('{tenant}', '{doc}', '{file_id}', '{role}', '{clerk.sub}')")
        return file_id

    def guess(value: str, confidence: str) -> dict:
        return {"value": value, "confidence": confidence, "source": "rule"}

    # nộp lưu: báo xong 07/01 rồi cho lưu 08/01 (lần cuối là lúc xong) — 48 giờ, đúng hạn 10/01
    archived = incoming_done(1, "'2025-01-10'")
    event(archived, "office.document.processed", "2025-01-07 08:00+07")
    event(archived, "office.document.filed", "2025-01-08 08:00+07")
    main = attach(archived, "main", {"symbol": guess("1/UBND-VP", "high"), "summary": guess("Khác hẳn", "low")})
    extra = attach(archived, "attachment", {"symbol": guess("99/UBND-VP", "high")})     # đính kèm: không tính
    # không nộp lưu: xong 09/01 — 72 giờ, không có hạn; văn thư sửa số ký hiệu gợi ý
    staying = incoming_done(2, "null")
    event(staying, "office.document.processed", "2025-01-09 08:00+07")
    attach(staying, "main", {"symbol": guess("7/UBND-VP", "high")})

    def figures() -> tuple[list, list]:
        accuracy = sorted((r["field"], r["confidence"], r["suggested"], r["kept"])
                          for r in director.gql(ACCURACY)["office_v_intake_accuracy"])
        return director.gql(TIMES)["office_v_processing_time"], accuracy

    expected = ([{"month": "2025-01-01", "documents": 2, "total_hours": 120.0, "with_due": 1, "on_time": 1}],
                [("summary", "low", 1, 0), ("symbol", "high", 2, 1)])
    assert figures() == expected

    cf = _one(f"insert into office.case_files (tenant_id, department_id, year, code, title, created_by) values "
              f"('{tenant}', '{dept}', 2025, 'HS-{tag}', 'Hồ sơ thử nộp lưu giữ số liệu', 'chuyen-vien') returning id")
    sql(f"insert into office.case_file_documents (tenant_id, case_file_id, document_id, added_by) "
        f"values ('{tenant}', '{cf}', '{archived}', 'chuyen-vien')")
    sql(f"update office.case_files set status = 'closed' where id = '{cf}'")
    events = [int(r[0]) for r in sql(f"select id from office.document_events where document_id = '{archived}'")]
    body = _admin(ARCHIVE, {"p": {
        "id": cf, "archive_key": f"cold/{tenant}/case/{cf}/", "archive_sha256": hashlib.sha256(b"m").hexdigest(),
        "bucket": "moc-cold", "documents": [archived], "events": events,
        "links": [{"document_id": archived, "file_id": f} for f in (main, extra)], "cold_files": [main, extra],
        "files": 2}})
    assert "errors" not in body and body["data"]["office_archive_case_file"][0]["status"] == "archived", body
    # chi tiết đã rời OLTP như trước, chỉ còn bản giữ lại
    assert _one(f"select count(*) from office.document_events where document_id = '{archived}'") == "0"
    assert _one(f"select count(*) from office.document_files where document_id = '{archived}'") == "0"
    assert sql("select finished_at = '2025-01-08 08:00+07', main_file_ids = array['" + main + "']::uuid[] "
               f"from office.archived_document_facts where document_id = '{archived}'") == [["t", "t"]]

    assert figures() == expected
