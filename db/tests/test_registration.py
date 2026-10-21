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

"""Cấp số đến (office.register_incoming), danh bạ core.users và quyền gọi Action."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import INSERT_DOC, GraphQLError, Service, incoming, received, sql

REGISTER = """
mutation ($id: uuid!) {
  office_register_incoming(args: {document_id: $id}) { id status register_number registered_at }
}"""


def receive(world, n: int) -> str:
    return received(world.clerk_a, incoming(world.tag, n))["id"]


def register(service: Service, doc_id: str) -> dict:
    return service.gql(REGISTER, {"id": doc_id})["office_register_incoming"][0]


def as_clerk(service: Service, clerk) -> Service:
    """svc-workflow thay mặt văn thư: người thực hiện trên sổ kiểm toán là văn thư."""
    return Service(clerk.sub, "service", service.tenant)


def test_numbers_are_consecutive_and_recorded(world):
    svc = as_clerk(world.service_a, world.clerk_a)
    first = register(svc, receive(world, 9101))
    second = register(svc, receive(world, 9102))
    assert first["status"] == "registered" and first["registered_at"]
    assert second["register_number"] == first["register_number"] + 1

    events = sql(f"select kind, actor_id, data->>'register_number' from office.document_events "
                 f"where document_id = '{first['id']}'")
    assert events == [["office.document.registered", world.clerk_a.sub, str(first["register_number"])]]


def test_registering_twice_does_not_take_a_second_number(world):
    svc = as_clerk(world.service_a, world.clerk_a)
    doc = receive(world, 9103)
    first = register(svc, doc)
    again = register(svc, doc)
    assert again["register_number"] == first["register_number"]
    last = sql(f"select last_number from office.registers r join office.documents d on d.register_id = r.id "
               f"where d.id = '{doc}'")[0][0]
    assert int(last) >= first["register_number"]
    assert sql(f"select count(*) from office.document_events where document_id = '{doc}'") == [["1"]]


def test_parallel_registrations_get_distinct_consecutive_numbers(world):
    svc = as_clerk(world.service_a, world.clerk_a)
    docs = [receive(world, 9200 + i) for i in range(12)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        numbers = sorted(r["register_number"] for r in pool.map(lambda d: register(svc, d), docs))
    assert numbers == list(range(numbers[0], numbers[0] + 12))


def test_other_tenant_cannot_register(world):
    doc = receive(world, 9104)
    with pytest.raises(GraphQLError, match="không có văn bản"):
        register(world.service_b, doc)
    assert sql(f"select status from office.documents where id = '{doc}'") == [["received"]]


def test_outgoing_document_cannot_be_registered_as_incoming(world):
    draft = world.staff_a1.gql(INSERT_DOC, {"o": {"type_code": "TB", "summary": "Dự thảo thông báo không vào sổ đến"}})
    with pytest.raises(GraphQLError, match="chỉ văn bản đến"):
        register(world.service_a, draft["insert_office_documents_one"]["id"])


@pytest.mark.parametrize("who", ["clerk_a", "director_a", "staff_a1"])
def test_users_cannot_call_the_function_directly(world, who):
    body = getattr(world, who).raw(REGISTER, {"id": str(uuid.uuid4())})
    assert "errors" in body and "office_register_incoming" in body["errors"][0]["message"]


def test_register_incoming_action_is_only_offered_to_clerks(world):
    query = "mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }"
    for user in (world.director_a, world.staff_a1, world.manager_a1, world.admin_a):
        body = user.raw(query, {"id": str(uuid.uuid4())})
        assert "registerIncoming" in body["errors"][0]["message"], user.role
    # văn thư được gọi: Hasura chuyển sang svc-workflow (ở đây không chạy) chứ không báo thiếu trường
    body = world.clerk_a.raw(query, {"id": str(uuid.uuid4())})
    assert "not found in type" not in body["errors"][0]["message"]


def test_directory_is_per_tenant_and_read_only(world):
    upsert = """
    mutation ($o: [core_users_insert_input!]!) {
      insert_core_users(objects: $o, on_conflict: {constraint: users_pkey,
        update_columns: [full_name, role, department_id, enabled]}) { affected_rows }
    }"""
    sub = f"kc-{world.tag}-lan"
    world.service_a.gql(upsert, {"o": [{"id": sub, "username": f"lan{world.tag}", "full_name": "Nguyễn Thị Lan",
                                        "role": "staff", "department_id": world.dept_a1}]})
    world.service_a.gql(upsert, {"o": [{"id": sub, "username": f"lan{world.tag}", "full_name": "Nguyễn Thị Lan",
                                        "role": "manager", "department_id": world.dept_a1}]})

    seen = world.staff_a2.gql("{ core_users { id full_name role } }")["core_users"]
    assert {"id": sub, "full_name": "Nguyễn Thị Lan", "role": "manager"} in seen
    assert sub not in {u["id"] for u in world.clerk_b.gql("{ core_users { id } }")["core_users"]}

    body = world.clerk_a.raw('mutation { update_core_users(where: {}, _set: {role: "director"}) { affected_rows } }')
    assert "errors" in body
    changes = sql(f"select action from core.audit_log where entity = 'core.users' and entity_id = '{sub}' order by id")
    assert changes == [["insert"], ["update"]]


# --- chống ghi đôi: quy trình chỉ gắn khi văn bản chưa có, một việc chỉ ghi một lần -----------------------

CLAIM_PROCESS = """
mutation ($id: uuid!, $pid: String!) {
  update_office_documents(where: {id: {_eq: $id}, process_id: {_is_null: true}}, _set: {process_id: $pid}) {
    affected_rows
  }
}"""

DIRECT = """
mutation ($a: office_assignments_insert_input!, $e: office_document_events_insert_input!) {
  insert_office_assignments_one(object: $a) { id }
  insert_office_document_events_one(object: $e) { id }
}"""

EVENT = """
mutation ($e: office_document_events_insert_input!) { insert_office_document_events_one(object: $e) { id } }"""


def test_process_is_linked_only_while_empty(world):
    svc = as_clerk(world.service_a, world.clerk_a)
    doc = register(svc, receive(world, 9105))["id"]
    claim = {"id": doc, "pid": f"p-{world.tag}-1"}
    assert world.service_b.gql(CLAIM_PROCESS, claim)["update_office_documents"]["affected_rows"] == 0
    assert svc.gql(CLAIM_PROCESS, claim)["update_office_documents"]["affected_rows"] == 1
    # lần gọi chen sau (bấm đúp, job đối soát) không ghi đè: nó theo phiên đã gắn và hủy phiên của mình
    assert svc.gql(CLAIM_PROCESS, {**claim, "pid": f"p-{world.tag}-2"})["update_office_documents"]["affected_rows"] == 0
    assert sql(f"select process_id from office.documents where id = '{doc}'") == [[claim["pid"]]]


def test_a_task_is_written_once(world):
    svc = Service(world.director_a.sub, "service", world.tenant_a)
    doc = register(as_clerk(world.service_a, world.clerk_a), receive(world, 9106))["id"]
    task = f"t-{uuid.uuid4()}"
    event = {"document_id": doc, "kind": "office.document.directed", "actor_id": world.director_a.sub,
             "actor_kind": "user", "data": {"task_id": task}}
    lead = {"document_id": doc, "instruction": "Giao Phòng Đào tạo chủ trì", "assigned_by": world.director_a.sub,
            "role": "lead", "department_id": world.dept_a1}
    svc.gql(DIRECT, {"a": lead, "e": event})
    # lần ghi thứ hai của cùng việc (hai lần gọi chen nhau): bị chặn, phân công trong cùng giao dịch cũng không ghi
    with pytest.raises(GraphQLError, match="document_events_task_once"):
        svc.gql(DIRECT, {"a": {**lead, "role": "support", "department_id": world.dept_a2}, "e": event})
    assert sql(f"select role from office.assignments where document_id = '{doc}'") == [["lead"]]
    # nhắc hạn của cùng việc mang khóa khác, ghi nhiều lần được; sự kiện không gắn việc cũng vậy
    for _ in range(2):
        svc.gql(EVENT, {"e": {**event, "kind": "office.task.overdue", "data": {"sla_task_id": task}}})
        svc.gql(EVENT, {"e": {**event, "kind": "office.document.overdue", "data": {}}})
    kinds = sql(f"select kind from office.document_events where document_id = '{doc}' and kind <> "
                f"'office.document.registered' order by id")
    assert [k for (k,) in kinds] == ["office.document.directed"] + ["office.task.overdue",
                                                                     "office.document.overdue"] * 2
