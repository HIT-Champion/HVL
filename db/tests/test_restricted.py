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

"""Văn bản hạn chế (F3.7): tệp mã hóa, danh sách người được xem, thông báo và sổ kiểm toán không lộ nội dung."""

from __future__ import annotations

import pytest

from conftest import GraphQLError, SQLError, User, incoming, insert_file, received, sql, visible_ids

GRANT = """mutation ($d: uuid!, $u: String!) {
  office_grant_document_access(args: {document_id: $d, user_id: $u}) { document_id user_id granted_by }
}"""

REVOKE = """mutation ($d: uuid!, $u: String!) {
  office_revoke_document_access(args: {document_id: $d, user_id: $u}) { user_id }
}"""

VIEWERS = """query ($d: uuid!) {
  office_document_acl(where: {document_id: {_eq: $d}}, order_by: {user_id: asc}) { user_id granted_by user { full_name } }
}"""

NOTIFY = """mutation ($rows: [core_notifications_insert_input!]!) {
  insert_core_notifications(objects: $rows) { returning { id data } }
}"""

# Đúng mutation svc-workflow gửi khi tự cấp quyền xem cho người nhận việc (svc_workflow/hasura.py SHARE)
SHARE = """mutation ($rows: [office_document_acl_insert_input!]!) {
  insert_office_document_acl(objects: $rows, on_conflict: {constraint: document_acl_pkey, update_columns: []}) {
    affected_rows }
}"""

FILE = """query ($f: uuid!) { core_files_by_pk(id: $f) { id } }"""

OVERVIEW = """query ($e: String!) {
  core_audit_log(where: {entity_id: {_eq: $e}}, order_by: {id: asc}) { action entity overview }
}"""


@pytest.fixture(scope="module")
def people(world):
    """Người được cấp quyền xem và người nhận thông báo phải có trong danh bạ core.users."""
    rows = [
        {"id": u.sub, "department_id": u.department, "username": u.sub, "full_name": f"Tên {u.sub}", "role": u.role}
        for u in (world.clerk_a, world.director_a, world.manager_a1, world.staff_a1, world.staff_a2)
    ]
    rows.append({"id": f"nghi-viec-{world.tag}", "username": f"nghi-viec-{world.tag}", "full_name": "Đã nghỉ",
                 "role": "staff", "enabled": False})
    world.service_a.gql(
        """mutation ($o: [core_users_insert_input!]!) {
          insert_core_users(objects: $o, on_conflict: {constraint: users_pkey, update_columns: [role, enabled]}) {
            affected_rows }
        }""",
        {"o": rows},
    )
    world.service_b.gql(
        """mutation ($o: [core_users_insert_input!]!) {
          insert_core_users(objects: $o, on_conflict: {constraint: users_pkey, update_columns: [role]}) { affected_rows }
        }""",
        {"o": [{"id": world.clerk_b.sub, "username": "vt-b", "full_name": "Văn thư B", "role": "clerk"}]},
    )
    return world


def _attach(world, doc_id: str, file_id: str, role: str = "main") -> None:
    sql(f"insert into office.document_files (tenant_id, document_id, file_id, role, added_by) "
        f"values ('{world.tenant_a}', '{doc_id}', '{file_id}', '{role}', '{world.clerk_a.sub}')")


# --- tệp của văn bản hạn chế ---------------------------------------------------------------------------------

def test_restricted_documents_take_only_encrypted_files(world):
    secret = received(world.clerk_a, incoming(world.tag, 401, restricted=True))
    plain = insert_file(world.service_a, world.clerk_a)
    with pytest.raises(SQLError, match="document_files_sealed: văn bản hạn chế chỉ gắn tệp"):
        _attach(world, secret["id"], plain)
    _attach(world, secret["id"], insert_file(world.service_a, world.clerk_a, encrypted=True))

    open_doc = received(world.clerk_a, incoming(world.tag, 402))
    with pytest.raises(SQLError, match="document_files_sealed: tệp đã mã hóa chỉ gắn vào văn bản hạn chế"):
        _attach(world, open_doc["id"], insert_file(world.service_a, world.clerk_a, encrypted=True))
    _attach(world, open_doc["id"], plain)


def test_restriction_is_fixed_once_a_file_is_attached(world):
    secret = received(world.clerk_a, incoming(world.tag, 403, restricted=True))
    _attach(world, secret["id"], insert_file(world.service_a, world.clerk_a, encrypted=True))
    with pytest.raises(SQLError, match="documents_restricted_sealed"):     # bản rõ không còn ở đâu để gỡ mã hóa
        sql(f"update office.documents set restricted = false where id = '{secret['id']}'")
    sql(f"update office.documents set summary = summary || ' (sửa)' where id = '{secret['id']}'")   # cột khác: được

    empty = received(world.clerk_a, incoming(world.tag, 404))
    sql(f"update office.documents set restricted = true where id = '{empty['id']}'")   # chưa có tệp: đổi tự do
    sql(f"update office.documents set restricted = false where id = '{empty['id']}'")


def test_encrypted_files_need_a_wrapped_key(world):
    with pytest.raises(GraphQLError, match="files_encryption_key"):
        world.service_a.gql(
            """mutation ($o: core_files_insert_input!) { insert_core_files_one(object: $o) { id } }""",
            {"o": {"object_key": f"tenant/{world.tenant_a}/2026/10/x", "filename": "a.pdf", "mime_type": "application/pdf",
                   "size_bytes": 1, "sha256": "\\x" + "00" * 32, "scanned_at": "2026-10-18T09:00:00+07:00",
                   "encrypted": True}},
        )


def test_restricted_document_is_never_public(world):
    """Trang tra cứu công khai (F2.10) hiện trích yếu của văn bản is_public: văn bản hạn chế không bao giờ như vậy."""
    secret = received(world.clerk_a, incoming(world.tag, 405, restricted=True))
    with pytest.raises(SQLError, match="documents_restricted_private"):
        sql(f"update office.documents set is_public = true where id = '{secret['id']}'")
    public = received(world.clerk_a, incoming(world.tag, 406))
    sql(f"update office.documents set is_public = true where id = '{public['id']}'")
    with pytest.raises(SQLError, match="documents_restricted_private"):     # đã công khai thì không chuyển hạn chế
        sql(f"update office.documents set restricted = true where id = '{public['id']}'")


# --- danh sách người được xem ------------------------------------------------------------------------------------

def test_clerk_grants_and_revokes_viewers(people):
    w = people
    doc = received(w.clerk_a, incoming(w.tag, 410, restricted=True))
    assert doc["id"] not in visible_ids(w.director_a)

    granted = w.clerk_a.gql(GRANT, {"d": doc["id"], "u": w.director_a.sub})["office_grant_document_access"]
    assert granted == [{"document_id": doc["id"], "user_id": w.director_a.sub, "granted_by": w.clerk_a.sub}]
    assert doc["id"] in visible_ids(w.director_a)

    # cấp lại: không lỗi, giữ người cấp lần đầu
    again = w.director_a.gql(GRANT, {"d": doc["id"], "u": w.director_a.sub})["office_grant_document_access"]
    assert again[0]["granted_by"] == w.clerk_a.sub

    viewers = w.director_a.gql(VIEWERS, {"d": doc["id"]})["office_document_acl"]
    assert [v["user_id"] for v in viewers] == [w.director_a.sub]
    assert viewers[0]["user"]["full_name"]                       # tên lấy từ danh bạ để màn văn bản hiện

    assert w.clerk_a.gql(REVOKE, {"d": doc["id"], "u": w.director_a.sub})["office_revoke_document_access"] == [
        {"user_id": w.director_a.sub}]
    assert doc["id"] not in visible_ids(w.director_a)
    # gỡ người không có tên: không lỗi, không gì thay đổi
    assert w.clerk_a.gql(REVOKE, {"d": doc["id"], "u": w.staff_a1.sub})["office_revoke_document_access"] == []

    actions = sql(f"select action, actor_id from core.audit_log where entity = 'office.document_acl' "
                  f"and entity_id = '{doc['id']}/{w.director_a.sub}' order by id")
    assert actions == [["insert", w.clerk_a.sub], ["delete", w.clerk_a.sub]]


def test_acl_does_not_replace_the_role_rule(people):
    """Có tên trong danh sách vẫn phải có quyền theo vai trò: lãnh đạo phòng khác chưa được giao thì vẫn không thấy."""
    w = people
    doc = received(w.clerk_a, incoming(w.tag, 411, restricted=True))
    w.clerk_a.gql(GRANT, {"d": doc["id"], "u": w.manager_a1.sub})
    assert doc["id"] not in visible_ids(w.manager_a1)


def test_revoked_viewer_loses_encrypted_files_they_created_too(people):
    """Tệp mã hóa đã gắn vào văn bản chỉ theo quyền đọc văn bản, kể cả với người tạo dòng tệp (bản phát hành do
    svc-files dựng thay người bấm phát hành): bị gỡ tên là hết tải. Tệp chưa gắn thì người tải lên vẫn thấy."""
    w = people
    doc = received(w.clerk_a, incoming(w.tag, 418, restricted=True))
    w.clerk_a.gql(GRANT, {"d": doc["id"], "u": w.director_a.sub})
    mine = insert_file(w.service_a, w.director_a, encrypted=True)
    assert w.director_a.gql(FILE, {"f": mine})["core_files_by_pk"]
    _attach(w, doc["id"], mine)
    assert w.director_a.gql(FILE, {"f": mine})["core_files_by_pk"]

    w.clerk_a.gql(REVOKE, {"d": doc["id"], "u": w.director_a.sub})
    assert w.director_a.gql(FILE, {"f": mine})["core_files_by_pk"] is None
    assert w.clerk_a.gql(FILE, {"f": mine})["core_files_by_pk"]

    plain = insert_file(w.service_a, w.director_a)                 # tệp thường: người tải lên vẫn thấy như trước
    _attach(w, received(w.clerk_a, incoming(w.tag, 407))["id"], plain)
    assert w.director_a.gql(FILE, {"f": plain})["core_files_by_pk"]


def test_workflow_shares_with_task_holders_and_repeats_safely(people):
    """svc-workflow (vai trò service) thêm người nhận việc vào danh sách; thêm lại người đã có thì bỏ qua, giữ người
    cấp lần đầu — chạy lại sau mỗi bước quy trình mà không lỗi."""
    w = people
    doc = received(w.clerk_a, incoming(w.tag, 417, restricted=True))
    row = {"document_id": doc["id"], "user_id": w.director_a.sub, "granted_by": w.clerk_a.sub}
    assert w.service_a.gql(SHARE, {"rows": [row]})["insert_office_document_acl"]["affected_rows"] == 1
    again = [{**row, "granted_by": w.manager_a1.sub},
             {"document_id": doc["id"], "user_id": w.staff_a1.sub, "granted_by": w.manager_a1.sub}]
    assert w.service_a.gql(SHARE, {"rows": again})["insert_office_document_acl"]["affected_rows"] == 1
    viewers = w.clerk_a.gql(VIEWERS, {"d": doc["id"]})["office_document_acl"]
    assert sorted((v["user_id"], v["granted_by"]) for v in viewers) == sorted(
        [(w.director_a.sub, w.clerk_a.sub), (w.staff_a1.sub, w.manager_a1.sub)])
    assert doc["id"] in visible_ids(w.director_a)
    # dịch vụ đang phục vụ đơn vị khác không thêm được người vào văn bản của đơn vị này
    assert "errors" in w.service_b.raw(SHARE, {"rows": [{**row, "user_id": w.clerk_b.sub}]})


@pytest.mark.parametrize(("who", "n"), [("staff_a1", 412), ("manager_a1", 415), ("admin_a", 416)])
def test_only_clerk_and_director_manage_viewers(people, who, n):
    w = people
    doc = received(w.clerk_a, incoming(w.tag, n, restricted=True))
    caller: User = getattr(w, who)
    for mutation in (GRANT, REVOKE):
        assert "errors" in caller.raw(mutation, {"d": doc["id"], "u": w.director_a.sub})
    assert "errors" in caller.raw(VIEWERS, {"d": doc["id"]})
    assert doc["id"] not in visible_ids(w.director_a)


def test_grant_refuses_what_the_caller_cannot_see_or_should_not_do(people):
    w = people
    doc = received(w.clerk_a, incoming(w.tag, 413, restricted=True))

    def error(caller: User, query: str, user_id: str, doc_id: str = doc["id"]) -> str:
        body = caller.raw(query, {"d": doc_id, "u": user_id})
        return body["errors"][0]["message"] if "errors" in body else ""

    assert "không có văn bản" in error(w.director_a, GRANT, w.director_a.sub)        # lãnh đạo chưa có tên tự cấp
    assert "không có văn bản" in error(w.clerk_b, GRANT, w.clerk_b.sub)              # đơn vị khác
    assert "không có người dùng" in error(w.clerk_a, GRANT, w.clerk_b.sub)           # người của đơn vị khác
    assert "không có người dùng" in error(w.clerk_a, GRANT, f"nghi-viec-{w.tag}")    # tài khoản đã khóa
    assert "không có người dùng" in error(w.clerk_a, GRANT, "khong-ton-tai")
    assert "không tự gỡ" in error(w.clerk_a, REVOKE, w.clerk_a.sub)

    open_doc = received(w.clerk_a, incoming(w.tag, 414))
    assert "văn bản không hạn chế" in error(w.clerk_a, GRANT, w.director_a.sub, open_doc["id"])
    assert sql(f"select count(*) from office.document_acl where document_id in ('{doc['id']}', '{open_doc['id']}')") \
        == [["0"]]


# --- thông báo ------------------------------------------------------------------------------------------------

def _notify(w, doc_id: str, key: str) -> dict:
    rows = [{"user_id": w.director_a.sub, "kind": "task.assigned", "key": key, "document_id": doc_id,
             "data": {"form_key": "vbden.chiDao", "summary": "Danh sách nâng lương", "symbol": "12/QĐ-ĐHHY",
                      "issuer_name": "Bộ Nội vụ", "note": "Xem gấp", "urgency": "khan", "direction": "in"}}]
    return w.service_a.gql(NOTIFY, {"rows": rows})["insert_core_notifications"]["returning"][0]["data"]


def test_notifications_about_restricted_documents_carry_no_content(people):
    w = people
    secret = received(w.clerk_a, incoming(w.tag, 420, restricted=True))
    data = _notify(w, secret["id"], f"t:{w.tag}:420")
    assert data == {"form_key": "vbden.chiDao", "urgency": "khan", "direction": "in", "restricted": True}

    open_doc = received(w.clerk_a, incoming(w.tag, 421))
    assert _notify(w, open_doc["id"], f"t:{w.tag}:421")["summary"] == "Danh sách nâng lương"


def test_restricting_a_document_strips_notifications_already_sent(people):
    w = people
    doc = received(w.clerk_a, incoming(w.tag, 422))
    _notify(w, doc["id"], f"t:{w.tag}:422")
    sql(f"update office.documents set restricted = true where id = '{doc['id']}'")
    stored = sql(f"select data ->> 'summary', data ->> 'restricted' from core.notifications "
                 f"where document_id = '{doc['id']}'")
    assert stored == [["NULL", "true"]]               # run_sql in null là NULL


# --- sổ kiểm toán -------------------------------------------------------------------------------------------

def test_audit_overview_hides_values_of_restricted_documents_the_viewer_cannot_read(people):
    w = people
    doc = received(w.clerk_a, incoming(w.tag, 430, restricted=True, urgency="khan"))
    w.clerk_a.gql(GRANT, {"d": doc["id"], "u": w.staff_a1.sub})

    for viewer in (w.director_a, w.admin_a):
        row = viewer.gql(OVERVIEW, {"e": doc["id"]})["core_audit_log"][0]
        assert row["entity"] == "office.documents" and row["action"] == "insert"       # vẫn biết ai làm gì
        assert set(row["overview"]) >= {"status", "urgency"}                           # cột nào đổi
        assert row["overview"]["status"] is None and row["overview"]["urgency"] is None
        acl = viewer.gql(OVERVIEW, {"e": f"{doc['id']}/{w.staff_a1.sub}"})["core_audit_log"][0]
        assert acl["overview"]["user_id"] is None

    w.clerk_a.gql(GRANT, {"d": doc["id"], "u": w.director_a.sub})
    row = w.director_a.gql(OVERVIEW, {"e": doc["id"]})["core_audit_log"][0]
    assert row["overview"]["status"] == [None, "received"]
    assert row["overview"]["urgency"] == [None, "khan"]
    assert row["overview"]["summary"] is None                                       # nội dung vẫn ẩn như mọi văn bản
    assert w.admin_a.gql(OVERVIEW, {"e": doc["id"]})["core_audit_log"][0]["overview"]["status"] is None
