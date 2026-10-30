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

"""Robot của flow Node-RED (#366): vai trò `tu_dong` chỉ đọc văn bản không hạn chế của đơn vị mình, không có nội dung,
người tạo, người nhận; không ghi được gì, không đọc danh bạ hay thông báo. Thông báo đi qua Action notifyFromFlow
(svc-workflow, test riêng ở services/svc-workflow/tests)."""

from __future__ import annotations

import pytest

from conftest import GraphQLError, User, incoming, received, visible_ids


@pytest.fixture(scope="module")
def robot(world) -> User:
    """Token như mapper claim cố định của `moc tu-dong robot add` gắn (scripts/tu_dong.py): sub là clientId."""
    return User(f"tu-dong-robot-a-{world.tag}", "tu_dong", world.tenant_a)


@pytest.fixture(scope="module")
def docs(world) -> dict[str, str]:
    return {
        "open": received(world.clerk_a, incoming(world.tag, 9601, urgency="hoa_toc"))["id"],
        "restricted": received(world.clerk_a, incoming(world.tag, 9602, restricted=True))["id"],
        "other_unit": received(world.clerk_b, incoming(world.tag, 9603))["id"],
    }


def test_reads_only_open_documents_of_its_unit(robot, docs) -> None:
    seen = visible_ids(robot)
    assert docs["open"] in seen
    assert docs["restricted"] not in seen
    assert docs["other_unit"] not in seen


def test_sees_what_the_sample_flows_need(robot, docs) -> None:
    rows = robot.gql("""query ($id: uuid!) {
      office_documents(where: {id: {_eq: $id}}) { symbol summary urgency status due_on registered_at department_id }
      office_documents_aggregate(where: {urgency: {_eq: "hoa_toc"}}) { aggregate { count } }
    }""", {"id": docs["open"]})
    assert rows["office_documents"][0]["urgency"] == "hoa_toc"
    assert rows["office_documents_aggregate"]["aggregate"]["count"] >= 1


@pytest.mark.parametrize("field", ["body", "created_by", "recipients", "restricted", "tenant_id"])
def test_no_content_people_or_flags(robot, field) -> None:
    with pytest.raises(GraphQLError):
        robot.gql(f"{{ office_documents {{ id {field} }} }}")


@pytest.mark.parametrize("query", [
    "{ core_users { id } }",
    "{ core_notifications { id } }",
    "{ office_document_acl { user_id } }",
    "{ office_assignments { id } }",
])
def test_no_directory_notifications_or_other_tables(robot, query) -> None:
    with pytest.raises(GraphQLError):
        robot.gql(query)


@pytest.mark.parametrize("mutation", [
    """mutation ($u: String!, $t: uuid!) { insert_core_notifications_one(object: {user_id: $u, tenant_id: $t,
         kind: "flow.message", key: "x", data: {}}) { id } }""",
    """mutation ($u: String!, $t: uuid!) { update_office_documents(where: {tenant_id: {_eq: $t}},
         _set: {summary: $u}) { affected_rows } }""",
])
def test_writes_nothing(world, robot, mutation) -> None:
    with pytest.raises(GraphQLError):
        robot.gql(mutation, {"u": world.director_a.sub, "t": world.tenant_a})
