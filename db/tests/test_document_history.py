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

"""Lịch sử thay đổi của văn bản (F3.5): ai đọc được văn bản thì xem được các dòng sổ kiểm toán về nó — chính văn bản,
giao việc, tệp — chỉ qua `overview` (không có trích yếu, không có hash); phòng khác, đơn vị khác không thấy."""

from __future__ import annotations

import pytest
from conftest import GraphQLError, World, insert_file, sql
from test_case_files import _doc

HISTORY = """query ($d: uuid!) { office_document_history(where: {document_id: {_eq: $d}}, order_by: {id: asc}) {
  document_id action entity actor_id overview } }"""


def test_readers_see_history_of_their_documents_only(world: World):
    doc = _doc(world, status="in_progress")
    sql(f"update office.documents set status = 'done' where id = '{doc}'")
    rows = world.staff_a1.gql(HISTORY, {"d": doc})["office_document_history"]
    assert [(r["action"], r["entity"]) for r in rows][:3] == [
        ("insert", "office.documents"), ("insert", "office.assignments"), ("update", "office.documents")]
    assert rows[2]["overview"]["status"] == ["in_progress", "done"]
    # trích yếu là cột nội dung: lịch sử chỉ cho biết có, không có giá trị
    assert "Văn bản đến thử hồ sơ" not in str(rows)
    assert world.director_a.gql(HISTORY, {"d": doc})["office_document_history"]
    for user in (world.staff_a2, world.clerk_b):        # phòng khác không đọc được văn bản, đơn vị khác
        assert user.gql(HISTORY, {"d": doc})["office_document_history"] == []
    with pytest.raises(GraphQLError):                    # chuỗi hash chỉ ở màn Sổ kiểm toán của lãnh đạo
        world.staff_a1.gql("{ office_document_history { hash } }")


def test_history_covers_files_but_not_access_lists_or_other_documents(world: World):
    doc, other = _doc(world), _doc(world)
    file_id = insert_file(world.service_a, world.staff_a1, name="ho-so-mat.pdf")
    sql(f"insert into office.document_files (tenant_id, document_id, file_id, role, added_by) values "
        f"('{world.tenant_a}', '{doc}', '{file_id}', 'attachment', '{world.staff_a1.sub}')")
    sql(f"insert into office.document_acl (tenant_id, document_id, user_id, granted_by) values "
        f"('{world.tenant_a}', '{doc}', '{world.staff_a1b.sub}', '{world.director_a.sub}')")
    rows = world.staff_a1.gql(HISTORY, {"d": doc})["office_document_history"]
    assert {r["document_id"] for r in rows} == {doc}            # dòng của văn bản khác không lọt vào
    assert ("insert", "office.document_files") in {(r["action"], r["entity"]) for r in rows}
    assert "ho-so-mat" not in str(rows)                          # tên tệp là cột nội dung
    # danh sách được xem văn bản hạn chế không nằm trong lịch sử: không lộ ai khác cũng có tên
    assert "office.document_acl" not in {r["entity"] for r in rows}
    assert other not in str(rows)


def test_restricted_history_only_for_those_who_read_it(world: World):
    # văn bản hạn chế (văn thư A tạo, giao cho chuyên viên A1): lãnh đạo, người được giao mà chưa có tên trong danh sách
    # được xem đều không thấy lịch sử; cấp quyền xem thì thấy
    secret = _doc(world, restricted=True)
    for user in (world.director_a, world.staff_a1, world.staff_a1b):
        assert user.gql(HISTORY, {"d": secret})["office_document_history"] == []
    sql(f"insert into office.document_acl (tenant_id, document_id, user_id, granted_by) values "
        f"('{world.tenant_a}', '{secret}', '{world.staff_a1.sub}', '{world.director_a.sub}')")
    assert world.staff_a1.gql(HISTORY, {"d": secret})["office_document_history"]
    assert world.clerk_a.gql(HISTORY, {"d": secret})["office_document_history"]       # người tạo
