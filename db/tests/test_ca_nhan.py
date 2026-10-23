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

"""Không gian cá nhân P.A.R.A (apps/ca-nhan, migration 1792281602500_personal_space, metadata personal_items.yaml):
schema riêng của ứng dụng thứ hai trên lõi. Mỗi người chỉ thấy, chỉ xếp, chỉ chuyển tệp của chính mình — thuê ước và
chủ đặt sẵn từ token; không xếp được tệp người khác tải lên, tệp mã hóa, tệp của đơn vị khác (trigger items_guard, khóa
ngoại kèm thuê ước, cả khi ghi thẳng CSDL); chỉ bốn thư mục; không ai xóa; mỗi lần xếp, chuyển một dòng sổ kiểm toán
qua core.audit() của lõi, lãnh đạo xem sổ không thấy tên thư mục; quản trị đơn vị không có không gian cá nhân."""

from __future__ import annotations

import pytest
from conftest import GraphQLError, User, World, insert_file, sql

PLACE = """mutation ($file: uuid!, $para: String!) {
  insert_personal_items_one(object: {file_id: $file, para: $para}) { file_id para created_at updated_at } }"""
MOVE = """mutation ($file: uuid!, $para: String!) {
  update_personal_items_by_pk(pk_columns: {file_id: $file}, _set: {para: $para}) { file_id para created_at updated_at }
}"""
MINE = """{ personal_items(order_by: {updated_at: desc}) {
  file_id para created_at updated_at file { filename mime_type size_bytes scanned_at } } }"""
AUDIT_VIEW = """query ($e: String!) {
  core_audit_log(where: {entity: {_eq: "personal.items"}, entity_id: {_eq: $e}}, order_by: {id: asc}) {
    action entity_id actor_id actor_kind overview } }"""


def mine(user: User) -> dict[str, dict]:
    return {i["file_id"]: i for i in user.gql(MINE)["personal_items"]}


def placed(world: World, owner: User, name: str = "ke-hoach.pdf", para: str = "projects") -> str:
    file_id = insert_file(world.service_a if owner.tenant == world.tenant_a else world.service_b, owner, name)
    owner.gql(PLACE, {"file": file_id, "para": para})
    return file_id


def test_owner_places_lists_moves(world: World) -> None:
    owner = world.staff_a1
    file_id = insert_file(world.service_a, owner, "de-cuong-hoc-phan.pdf")
    row = owner.gql(PLACE, {"file": file_id, "para": "projects"})["insert_personal_items_one"]
    assert row["para"] == "projects" and row["created_at"] == row["updated_at"]
    # thuê ước, chủ do Hasura đặt từ token
    assert sql(f"select tenant_id, owner_id from personal.items where file_id = '{file_id}'") == [
        [world.tenant_a, owner.sub]]
    item = mine(owner)[file_id]
    assert item["file"] == {"filename": "de-cuong-hoc-phan.pdf", "mime_type": "application/pdf", "size_bytes": 1024,
                            "scanned_at": item["file"]["scanned_at"]}
    moved = owner.gql(MOVE, {"file": file_id, "para": "archives"})["update_personal_items_by_pk"]
    assert moved["para"] == "archives"
    assert moved["created_at"] == row["created_at"] and moved["updated_at"] > row["updated_at"]


def test_clerk_manager_director_have_a_space_too(world: World) -> None:
    for user in (world.clerk_a, world.manager_a1, world.director_a):
        file_id = placed(world, user, para="areas")
        assert mine(user)[file_id]["para"] == "areas"


def test_others_do_not_see_or_move(world: World) -> None:
    file_id = placed(world, world.staff_a1)
    for other in (world.staff_a1b, world.manager_a1, world.director_a, world.clerk_a, world.clerk_b):
        assert file_id not in mine(other), other.sub
        assert other.gql(MOVE, {"file": file_id, "para": "resources"})["update_personal_items_by_pk"] is None
    assert mine(world.staff_a1)[file_id]["para"] == "projects"


def test_cannot_place_someone_elses_file(world: World) -> None:
    file_id = insert_file(world.service_a, world.staff_a1)
    with pytest.raises(GraphQLError, match="chỉ đặt được tệp chính mình tải lên"):
        world.staff_a1b.gql(PLACE, {"file": file_id, "para": "resources"})
    # upsert cũng qua trigger trước khi chạm dòng của người khác
    world.staff_a1.gql(PLACE, {"file": file_id, "para": "projects"})
    upsert = """mutation ($file: uuid!) { insert_personal_items_one(object: {file_id: $file, para: "archives"},
      on_conflict: {constraint: items_pkey, update_columns: [para]}) { para } }"""
    with pytest.raises(GraphQLError):
        world.staff_a1b.gql(upsert, {"file": file_id})
    assert mine(world.staff_a1)[file_id]["para"] == "projects"


def test_cannot_place_encrypted_file(world: World) -> None:
    file_id = insert_file(world.service_a, world.staff_a1, encrypted=True)
    with pytest.raises(GraphQLError, match="không mã hóa"):
        world.staff_a1.gql(PLACE, {"file": file_id, "para": "projects"})


def test_cannot_place_file_of_another_tenant(world: World) -> None:
    # cùng sub ở hai đơn vị (vd tài khoản bị chuyển đơn vị): tệp của đơn vị B không vào được không gian ở đơn vị A
    sub = f"chuyen-don-vi-{world.tag}"
    file_id = insert_file(world.service_b, User(sub, "staff", world.tenant_b))
    with pytest.raises(GraphQLError):
        User(sub, "staff", world.tenant_a).gql(PLACE, {"file": file_id, "para": "projects"})


def test_only_the_folder_can_change(world: World) -> None:
    file_id = placed(world, world.staff_a1)
    with pytest.raises(GraphQLError):   # cột không được cấp
        world.staff_a1.gql("""mutation ($f: uuid!) { insert_personal_items_one(object: {file_id: $f, para: "areas",
          owner_id: "nguoi-khac"}) { para } }""", {"f": insert_file(world.service_a, world.staff_a1)})
    with pytest.raises(GraphQLError):
        world.staff_a1.gql("""mutation ($f: uuid!) { update_personal_items_by_pk(pk_columns: {file_id: $f},
          _set: {owner_id: "nguoi-khac"}) { para } }""", {"f": file_id})
    # ghi thẳng CSDL cũng không đổi được chủ, tệp
    with pytest.raises(Exception, match="chỉ đổi được thư mục"):
        sql(f"update personal.items set owner_id = 'nguoi-khac' where file_id = '{file_id}'")


def test_four_folders_only(world: World) -> None:
    file_id = insert_file(world.service_a, world.staff_a1)
    with pytest.raises(GraphQLError, match="items_para"):
        world.staff_a1.gql(PLACE, {"file": file_id, "para": "thung-rac"})
    world.staff_a1.gql(PLACE, {"file": file_id, "para": "resources"})
    with pytest.raises(GraphQLError, match="items_para"):
        world.staff_a1.gql(MOVE, {"file": file_id, "para": "Projects"})


def test_nobody_deletes(world: World) -> None:
    file_id = placed(world, world.staff_a1)
    for user in (world.staff_a1, world.director_a):
        with pytest.raises(GraphQLError, match="delete_personal_items"):
            user.gql("""mutation ($f: uuid!) { delete_personal_items_by_pk(file_id: $f) { file_id } }""",
                     {"f": file_id})
    assert file_id in mine(world.staff_a1)


def test_audit_rows_without_folder_names(world: World) -> None:
    owner = world.staff_a1
    file_id = placed(world, owner)
    owner.gql(MOVE, {"file": file_id, "para": "archives"})
    rows = sql(f"select action, actor_id, actor_kind, diff -> 'para' from core.audit_log "
               f"where entity = 'personal.items' and entity_id = '{file_id}' order by id")
    assert rows == [["insert", owner.sub, "user", '[null, "projects"]'],
                    ["update", owner.sub, "user", '["projects", "archives"]']]
    seen = world.director_a.gql(AUDIT_VIEW, {"e": file_id})["core_audit_log"]
    assert [r["action"] for r in seen] == ["insert", "update"]
    assert all("para" in r["overview"] and r["overview"]["para"] is None for r in seen)   # chỉ tên cột
    assert seen[0]["overview"]["file_id"] == file_id
    director_b = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert director_b.gql(AUDIT_VIEW, {"e": file_id})["core_audit_log"] == []   # sổ của đơn vị khác


def test_tenant_admin_has_no_space(world: World) -> None:
    with pytest.raises(GraphQLError, match="personal_items"):
        world.admin_a.gql(MINE)
