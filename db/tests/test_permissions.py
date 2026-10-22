# Copyright 2026 Signet Team
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

"""Quyền theo vai trò và cách ly thuê ước qua GraphQL — docs/mo-hinh-du-lieu.md §3."""

from __future__ import annotations

import pytest
from conftest import (
    INSERT_DOC,
    GraphQLError,
    User,
    gql_raw,
    incoming,
    insert_file,
    make_token,
    outgoing,
    received,
    visible_ids,
)

UPDATE_DOC = """
mutation ($id: uuid!, $set: office_documents_set_input!) {
  update_office_documents(where: {id: {_eq: $id}}, _set: $set) { affected_rows }
}"""

ATTACH = """
mutation ($o: office_document_files_insert_input!) {
  insert_office_document_files_one(object: $o) { document_id file_id role added_by }
}"""


# --- ghi trực tiếp: cột đặt sẵn từ token, không tin dữ liệu client gửi -----------------------------


def test_clerk_writes_incoming_only_through_the_action(world):
    """Văn bản đến chỉ vào qua Action receiveIncoming: svc-workflow kiểm lại theo schemas/van-ban-den.json (F2.2),
    tự đặt đơn vị, người tạo, chiều, trạng thái. Văn thư ghi thẳng bảng thì không có mutation nào để gọi."""
    with pytest.raises(GraphQLError, match="insert_office_documents_one"):
        world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 1)})
    doc = received(world.clerk_a, incoming(world.tag, 2))
    with pytest.raises(GraphQLError, match="update_office_documents"):
        world.clerk_a.gql(UPDATE_DOC, {"id": doc["id"], "set": {"summary": "Về việc sửa thẳng không qua Action"}})


def test_staff_draft_is_outgoing_of_own_department(world):
    doc = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(1)})["insert_office_documents_one"]
    assert (doc["direction"], doc["status"]) == ("out", "draft")
    assert doc["department_id"] == world.dept_a1


def test_staff_cannot_create_incoming(world):
    with pytest.raises(GraphQLError):
        world.staff_a1.gql(INSERT_DOC, {"o": incoming(world.tag, 3)})


def test_manager_and_director_have_no_direct_insert(world):
    for user in (world.manager_a1, world.director_a):
        with pytest.raises(GraphQLError, match="insert_office_documents_one|no mutations exist"):
            user.gql(INSERT_DOC, {"o": outgoing(2)})


def test_staff_edits_only_own_draft(world):
    doc = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(3)})["insert_office_documents_one"]
    change = {"summary": "Thông báo lịch họp giao ban tháng 11 (sửa lần 2)"}
    assert world.staff_a1b.gql(UPDATE_DOC, {"id": doc["id"], "set": change})["update_office_documents"]["affected_rows"] == 0
    assert world.staff_a1.gql(UPDATE_DOC, {"id": doc["id"], "set": change})["update_office_documents"]["affected_rows"] == 1


# --- đọc: ai thấy văn bản nào ---------------------------------------------------------------------


def test_tenants_are_isolated(world):
    doc = received(world.clerk_a, incoming(world.tag, 6))
    assert doc["id"] in visible_ids(world.clerk_a)
    assert doc["id"] not in visible_ids(world.clerk_b)
    by_pk = world.clerk_b.gql("query ($id: uuid!) { office_documents_by_pk(id: $id) { id } }", {"id": doc["id"]})
    assert by_pk["office_documents_by_pk"] is None

    tenants = world.clerk_b.gql("{ core_tenants { id } }")["core_tenants"]
    assert tenants == [{"id": world.tenant_b}]
    departments = {d["id"] for d in world.clerk_b.gql("{ office_departments { id } }")["office_departments"]}
    assert departments == {world.dept_b1}


def test_session_headers_from_client_are_ignored(world):
    """Ở chế độ JWT, Hasura chỉ tin claim trong token; tiêu đề X-Hasura-Tenant-Id do client gửi bị bỏ qua."""
    doc = received(world.clerk_a, incoming(world.tag, 7))
    body = world.clerk_b.raw("{ office_documents { id } }", **{"X-Hasura-Tenant-Id": world.tenant_a})
    assert doc["id"] not in {d["id"] for d in body["data"]["office_documents"]}


def test_role_header_must_be_an_allowed_role(world):
    body = world.clerk_a.raw("{ office_documents { id } }", **{"X-Hasura-Role": "director"})
    assert "errors" in body


def test_request_without_token_is_rejected():
    body = gql_raw("{ office_document_types { code } }", headers={})
    assert "errors" in body


def test_expired_token_is_rejected(world):
    token = make_token(world.clerk_a.sub, "clerk", world.tenant_a, ttl=-120)
    body = gql_raw("{ office_document_types { code } }", headers={"Authorization": f"Bearer {token}"})
    assert "errors" in body


def test_outgoing_draft_visible_within_department_only(world):
    doc = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(4)})["insert_office_documents_one"]
    for user in (world.staff_a1, world.staff_a1b, world.manager_a1, world.director_a, world.clerk_a):
        assert doc["id"] in visible_ids(user), user.sub
    for user in (world.staff_a2, world.manager_a2, world.clerk_b):
        assert doc["id"] not in visible_ids(user), user.sub


def test_assignment_grants_visibility(world):
    doc = received(world.clerk_a, incoming(world.tag, 8))
    assert doc["id"] not in visible_ids(world.manager_a2)
    assert doc["id"] not in visible_ids(world.staff_a2)

    assign = """mutation ($o: office_assignments_insert_input!) { insert_office_assignments_one(object: $o) { id } }"""
    world.service_a.gql(assign, {"o": {"document_id": doc["id"], "department_id": world.dept_a2, "role": "lead",
                                       "instruction": "Phòng TCHC chủ trì", "assigned_by": world.director_a.sub}})
    assert doc["id"] in visible_ids(world.manager_a2)
    assert doc["id"] not in visible_ids(world.staff_a2)

    world.service_a.gql(assign, {"o": {"document_id": doc["id"], "user_id": world.staff_a2.sub, "role": "support",
                                       "assigned_by": world.manager_a2.sub}})
    assert doc["id"] in visible_ids(world.staff_a2)
    rows = world.staff_a2.gql("query ($id: uuid!) { office_assignments(where: {document_id: {_eq: $id}}) { role } }",
                              {"id": doc["id"]})["office_assignments"]
    assert sorted(r["role"] for r in rows) == ["lead", "support"]


def test_restricted_document_needs_acl(world):
    doc = received(world.clerk_a, incoming(world.tag, 9, restricted=True))
    assert doc["id"] in visible_ids(world.clerk_a)          # người tạo vẫn thấy
    assert doc["id"] not in visible_ids(world.director_a)

    world.service_a.gql(
        """mutation ($o: office_document_acl_insert_input!) { insert_office_document_acl_one(object: $o) { user_id } }""",
        {"o": {"document_id": doc["id"], "user_id": world.director_a.sub, "granted_by": world.clerk_a.sub}},
    )
    assert doc["id"] in visible_ids(world.director_a)


def test_tenant_admin_cannot_read_documents_but_manages_departments(world):
    body = world.admin_a.raw("{ office_documents { id } }")
    assert "not found" in body["errors"][0]["message"]

    dept = world.admin_a.gql(
        """mutation { insert_office_departments_one(object: {code: "KHTC", name: "Phòng Kế hoạch – Tài chính"}) { id } }"""
    )["insert_office_departments_one"]
    assert dept["id"] in {d["id"] for d in world.staff_a1.gql("{ office_departments { id } }")["office_departments"]}


def test_service_requires_tenant_session_variable(world):
    from conftest import ADMIN_SECRET

    body = gql_raw("{ office_documents { id } }",
                   headers={"X-Hasura-Admin-Secret": ADMIN_SECRET, "X-Hasura-Role": "service"})
    assert "errors" in body


# --- tệp ------------------------------------------------------------------------------------------


def test_uploader_sees_own_file_until_attached(world):
    file_id = insert_file(world.service_a, world.clerk_a)
    files = lambda u: {f["id"] for f in u.gql("{ core_files { id } }")["core_files"]}  # noqa: E731
    assert file_id in files(world.clerk_a)
    assert file_id not in files(world.director_a)
    assert file_id not in files(world.clerk_b)

    # gắn khi tiếp nhận, như Action receiveIncoming ghi
    doc = received(world.clerk_a, {**incoming(world.tag, 10), "files": {"data": [
        {"file_id": file_id, "role": "main", "added_by": world.clerk_a.sub}]}})
    links = world.clerk_a.gql("query ($d: uuid!) { office_document_files(where: {document_id: {_eq: $d}}) { added_by } }",
                              {"d": doc["id"]})["office_document_files"]
    assert links == [{"added_by": world.clerk_a.sub}]
    assert file_id in files(world.director_a)
    assert file_id not in files(world.clerk_b)


def test_files_hide_storage_details_from_users(world):
    body = world.clerk_a.raw("{ core_files { object_key } }")
    assert "errors" in body
    body = world.clerk_a.raw("{ core_files { wrapped_dek } }")
    assert "errors" in body


def test_cannot_attach_someone_elses_file(world):
    file_id = insert_file(world.service_a, world.clerk_a)
    draft = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(5)})["insert_office_documents_one"]
    with pytest.raises(GraphQLError, match="check constraint|permission"):
        world.staff_a1.gql(ATTACH, {"o": {"document_id": draft["id"], "file_id": file_id, "role": "draft"}})


def test_cannot_attach_to_draft_past_first_step(world):
    file_id = insert_file(world.service_a, world.staff_a1)
    draft = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(11)})["insert_office_documents_one"]
    world.service_a.gql(UPDATE_DOC, {"id": draft["id"], "set": {"status": "in_review"}})
    with pytest.raises(GraphQLError, match="check constraint|permission"):
        world.staff_a1.gql(ATTACH, {"o": {"document_id": draft["id"], "file_id": file_id, "role": "attachment"}})


def test_staff_cannot_attach_as_issued(world):
    file_id = insert_file(world.service_a, world.staff_a1)
    draft = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(12)})["insert_office_documents_one"]
    with pytest.raises(GraphQLError, match="check constraint|permission"):
        world.staff_a1.gql(ATTACH, {"o": {"document_id": draft["id"], "file_id": file_id, "role": "issued"}})


def test_staff_can_detach_from_own_draft(world):
    file_id = insert_file(world.service_a, world.staff_a1)
    draft = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(13)})["insert_office_documents_one"]
    world.staff_a1.gql(ATTACH, {"o": {"document_id": draft["id"], "file_id": file_id, "role": "attachment"}})
    gone = world.staff_a1.gql(
        """mutation ($d: uuid!, $f: uuid!) {
             delete_office_document_files(where: {document_id: {_eq: $d}, file_id: {_eq: $f}}) { affected_rows } }""",
        {"d": draft["id"], "f": file_id},
    )
    assert gone["delete_office_document_files"]["affected_rows"] == 1


def test_clerk_has_no_direct_write_on_document_files(world):
    """Tệp của văn bản đến gắn qua Action receiveIncoming (đủ kiểm: tối đa 20 tệp, một bản chính, đúng người tải),
    nên văn thư không gắn, không gỡ thẳng được — kể cả vào văn bản hạn chế mình không thấy."""
    file_id = insert_file(world.service_a, world.clerk_a)
    doc = received(world.clerk_a, incoming(world.tag, 14, restricted=True))
    with pytest.raises(GraphQLError, match="insert_office_document_files_one"):
        world.clerk_a.gql(ATTACH, {"o": {"document_id": doc["id"], "file_id": file_id, "role": "main"}})
    with pytest.raises(GraphQLError, match="delete_office_document_files"):
        world.clerk_a.gql("mutation ($d: uuid!) { delete_office_document_files(where: {document_id: {_eq: $d}}) "
                          "{ affected_rows } }", {"d": doc["id"]})


def test_user_without_department_claim_sees_no_department_documents(world):
    """Thiếu department_id trong token thì không thấy văn bản theo phòng — không lỗi, không lộ."""
    lost = User(f"thieu-phong-{world.tag}", "staff", world.tenant_a, None)
    draft = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(6)})["insert_office_documents_one"]
    assert draft["id"] not in visible_ids(lost)
