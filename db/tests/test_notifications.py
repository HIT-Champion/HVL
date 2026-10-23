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

"""Thông báo từng người (core.notifications): chỉ dịch vụ ghi, mỗi người chỉ thấy và đánh dấu của mình."""

from __future__ import annotations

import pytest

from conftest import GraphQLError, sql

NOTIFY = """
mutation ($rows: [core_notifications_insert_input!]!) {
  insert_core_notifications(objects: $rows,
                            on_conflict: {constraint: notifications_once, update_columns: []}) {
    returning { id user_id kind }
  }
}"""

MINE = """
{
  core_notifications(order_by: {id: desc}) { id kind document_id data read_at }
  core_notifications_aggregate(where: {read_at: {_is_null: true}}) { aggregate { count } }
}"""


@pytest.fixture(scope="module")
def people(world):
    """Người nhận phải có trong danh bạ core.users (khóa ngoại)."""
    rows = [
        {"id": u.sub, "department_id": u.department, "username": u.sub, "full_name": u.sub, "role": u.role}
        for u in (world.director_a, world.manager_a1, world.staff_a1, world.staff_a2)
    ]
    world.service_a.gql(
        """mutation ($o: [core_users_insert_input!]!) {
          insert_core_users(objects: $o, on_conflict: {constraint: users_pkey, update_columns: [role]}) { affected_rows }
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


def notify(service, user_id: str, key: str, kind: str = "task.assigned", **data) -> list[dict]:
    rows = [{"user_id": user_id, "kind": kind, "key": key, "data": data}]
    return service.gql(NOTIFY, {"rows": rows})["insert_core_notifications"]["returning"]


def test_service_writes_and_owner_reads(people):
    w = people
    created = notify(w.service_a, w.manager_a1.sub, "task:t-1:assigned", form_key="vbdi.duyetPhong")
    assert [r["kind"] for r in created] == ["task.assigned"]

    mine = w.manager_a1.gql(MINE)
    assert [n["data"]["form_key"] for n in mine["core_notifications"]] == ["vbdi.duyetPhong"]
    assert mine["core_notifications_aggregate"]["aggregate"]["count"] == 1
    # người khác cùng đơn vị, kể cả lãnh đạo, không thấy thông báo của người này
    assert w.director_a.gql(MINE)["core_notifications"] == []
    assert w.staff_a1.gql(MINE)["core_notifications"] == []


def test_same_key_is_sent_once(people):
    w = people
    assert len(notify(w.service_a, w.staff_a1.sub, "task:t-2:overdue", kind="task.overdue")) == 1
    # gọi lại sau lỗi, timer bắn lần nữa: không thêm dòng, không trả dòng nào để đẩy lại
    assert notify(w.service_a, w.staff_a1.sub, "task:t-2:overdue", kind="task.overdue") == []
    assert len(notify(w.service_a, w.staff_a2.sub, "task:t-2:overdue", kind="task.overdue")) == 1
    count = sql(f"select count(*) from core.notifications where key = 'task:t-2:overdue' and tenant_id = '{w.tenant_a}'")
    assert count == [["2"]]


def test_owner_marks_read_only_own_and_only_read_at(people):
    w = people
    nid = notify(w.service_a, w.staff_a2.sub, "doc:d-1:issued", kind="document.issued", symbol="05/TB-CNTT")[0]["id"]

    # người khác đánh dấu: không khớp bộ lọc, không đổi gì
    other = w.staff_a1.gql(
        """mutation ($id: bigint!, $at: timestamptz!) {
          update_core_notifications_by_pk(pk_columns: {id: $id}, _set: {read_at: $at}) { id }
        }""",
        {"id": nid, "at": "2026-10-19T10:00:00+07:00"},
    )
    assert other["update_core_notifications_by_pk"] is None

    done = w.staff_a2.gql(
        """mutation ($id: bigint!, $at: timestamptz!) {
          update_core_notifications_by_pk(pk_columns: {id: $id}, _set: {read_at: $at}) { id read_at }
        }""",
        {"id": nid, "at": "2026-10-19T10:00:00+07:00"},
    )
    assert done["update_core_notifications_by_pk"]["read_at"]

    # không sửa được nội dung, không tự tạo thông báo, không xóa
    with pytest.raises(GraphQLError):
        w.staff_a2.gql(
            "mutation ($id: bigint!) { update_core_notifications_by_pk(pk_columns: {id: $id}, _set: {kind: \"task.assigned\"}) { id } }",
            {"id": nid},
        )
    with pytest.raises(GraphQLError):
        w.staff_a2.gql(
            "mutation { insert_core_notifications_one(object: {user_id: \"x\", kind: \"task.assigned\", key: \"k\"}) { id } }"
        )
    with pytest.raises(GraphQLError):
        w.staff_a2.gql("mutation { delete_core_notifications(where: {}) { affected_rows } }")


def test_tenant_isolation_and_directory_link(people):
    w = people
    # dịch vụ của đơn vị B không gửi được cho người của đơn vị A: khóa ngoại (tenant_id, user_id) chặn
    with pytest.raises(GraphQLError):
        notify(w.service_b, w.staff_a1.sub, "task:t-3:assigned")
    # người không có trong danh bạ cũng không nhận được
    with pytest.raises(GraphQLError):
        notify(w.service_a, "nguoi-la", "task:t-4:assigned")
    notify(w.service_b, w.clerk_b.sub, "task:t-5:assigned")
    assert w.clerk_b.gql(MINE)["core_notifications_aggregate"]["aggregate"]["count"] == 1
    assert "t-5" not in str(w.manager_a1.gql(MINE))


def test_kind_and_key_are_checked(people):
    w = people
    with pytest.raises(GraphQLError):
        notify(w.service_a, w.staff_a1.sub, "k-1", kind="Việc mới")
    with pytest.raises(GraphQLError):
        notify(w.service_a, w.staff_a1.sub, "")
    with pytest.raises(GraphQLError):
        w.service_a.gql(NOTIFY, {"rows": [{"user_id": w.staff_a1.sub, "kind": "task.assigned", "key": "k-2",
                                           "data": ["không", "phải", "đối tượng"]}]})


def test_not_in_audit_chain(people):
    w = people
    notify(w.service_a, w.director_a.sub, "task:t-6:escalated", kind="task.escalated")
    assert sql("select count(*) from core.audit_log where entity = 'core.notifications'") == [["0"]]
