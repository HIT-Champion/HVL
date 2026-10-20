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

"""Phả hệ dữ liệu (F3.9): svc-files ghi sự kiện OpenLineage bằng khóa quản trị; lãnh đạo, văn thư xem phả hệ của đơn
vị mình; không ai sửa, xóa được (kể cả ghi thẳng CSDL); vai trò khác không thấy."""

from __future__ import annotations

import json
import uuid

import pytest
from conftest import GraphQLError, SQLError, World, sql

LIST = "{ core_lineage_events(order_by: {id: asc}) { run_id job event_type outputs quality_ok } }"


def _event(tenant: str | None, job: str = "moc.case_file.archive", ok: bool | None = None) -> str:
    run = str(uuid.uuid4())
    event = {"eventType": "COMPLETE", "run": {"runId": run}, "job": {"namespace": "moc", "name": job}}
    tenant_sql = f"'{tenant}'" if tenant else "null"
    ok_sql = "null" if ok is None else str(ok).lower()
    sql("insert into core.lineage_events (tenant_id, run_id, job, event_type, event_time, outputs, quality_ok, event) "
        f"values ({tenant_sql}, '{run}', '{job}', 'COMPLETE', now(), array['s3://moc-cold/cold/x/manifest.json'], "
        f"{ok_sql}, '{json.dumps(event)}'::jsonb)")
    return run


def test_director_and_clerk_see_lineage_of_own_tenant_only(world: World):
    mine, other, platform = _event(world.tenant_a, ok=True), _event(world.tenant_b), _event(None)
    for user in (world.director_a, world.clerk_a):
        runs = {r["run_id"] for r in user.gql(LIST)["core_lineage_events"]}
        assert mine in runs and other not in runs and platform not in runs
    assert other in {r["run_id"] for r in world.clerk_b.gql(LIST)["core_lineage_events"]}
    for user in (world.staff_a1, world.manager_a1, world.admin_a):
        with pytest.raises(GraphQLError):
            user.gql(LIST)


def test_nobody_writes_or_rewrites_lineage(world: World):
    run = _event(world.tenant_a, ok=False)
    insert = """mutation ($o: core_lineage_events_insert_input!) { insert_core_lineage_events_one(object: $o) { id } }"""
    row = {"run_id": str(uuid.uuid4()), "job": "x", "event_type": "COMPLETE", "event_time": "2026-10-20T00:00:00Z",
           "event": {}}
    for user in (world.director_a, world.clerk_a, world.staff_a1, world.service_a):
        with pytest.raises(GraphQLError):
            user.gql(insert, {"o": row})
    # kể cả ghi thẳng CSDL: một bước trượt kiểm chất lượng không được "sửa" thành đạt
    with pytest.raises(SQLError, match="chỉ thêm"):
        sql(f"update core.lineage_events set quality_ok = true where run_id = '{run}'")
    with pytest.raises(SQLError, match="chỉ thêm"):
        sql(f"delete from core.lineage_events where run_id = '{run}'")
