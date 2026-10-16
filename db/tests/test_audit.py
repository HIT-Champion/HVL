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

"""Sổ kiểm toán chuỗi băm: ghi tự động, chỉ ghi thêm, phát hiện sửa lén (F2.12)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import INSERT_DOC, SQLError, incoming, sql


def verify() -> list[list[str]]:
    return sql("select audit_id, problem from core.audit_verify()")


def last_audit(entity: str, entity_id: str) -> dict:
    row = sql(f"""select actor_id, actor_kind, action, diff::text, tenant_id from core.audit_log
                  where entity = '{entity}' and entity_id = '{entity_id}' order by id desc limit 1""")[0]
    return {"actor_id": row[0], "actor_kind": row[1], "action": row[2], "diff": json.loads(row[3]), "tenant_id": row[4]}


def test_chain_is_intact():
    assert verify() == []


def test_user_change_is_recorded_with_actor_from_token(world):
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 101)})["insert_office_documents_one"]
    entry = last_audit("office.documents", doc["id"])
    assert entry["actor_id"] == world.clerk_a.sub
    assert entry["actor_kind"] == "user"
    assert entry["action"] == "insert"
    assert entry["tenant_id"] == world.tenant_a
    assert entry["diff"]["status"] == [None, "received"]


def test_service_change_is_recorded_as_service(world):
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 102)})["insert_office_documents_one"]
    world.service_a.gql(
        """mutation ($id: uuid!) { update_office_documents_by_pk(pk_columns: {id: $id}, _set: {status: "cancelled"}) { id } }""",
        {"id": doc["id"]},
    )
    entry = last_audit("office.documents", doc["id"])
    assert (entry["actor_kind"], entry["action"]) == ("service", "update")
    assert entry["diff"]["status"] == ["received", "cancelled"]
    assert "summary" not in entry["diff"]          # chỉ ghi cột thay đổi (cùng updated_at)


def test_service_logs_rejected_file_event(world):
    """svc-files ghi sự kiện tệp bị ClamAV chặn — không có dòng core.files tương ứng."""
    row = world.service_a.gql(
        """mutation ($o: core_audit_log_insert_input!) { insert_core_audit_log_one(object: $o) { id tenant_id hash } }""",
        {"o": {"actor_id": world.clerk_a.sub, "actor_kind": "user", "action": "file.rejected", "entity": "core.files",
               "entity_id": "-", "diff": {"filename": "hoa-don.pdf.exe", "signature": "Eicar-Signature"}}},
    )["insert_core_audit_log_one"]
    assert row["tenant_id"] == world.tenant_a
    assert row["hash"].startswith("\\x") and len(row["hash"]) == 2 + 64


def test_service_cannot_choose_chain_fields(world):
    body = world.service_a.raw(
        """mutation { insert_core_audit_log_one(object: {actor_id: "x", actor_kind: "user", action: "a", entity: "e",
                       entity_id: "1", diff: {}, hash: "\\\\x00"}) { id } }"""
    )
    assert "errors" in body


def test_audit_log_is_append_only():
    with pytest.raises(SQLError, match="chỉ được ghi thêm"):
        sql("update core.audit_log set actor_id = 'ai-do' where id = 1")
    with pytest.raises(SQLError, match="chỉ được ghi thêm"):
        sql("delete from core.audit_log where id = 1")
    with pytest.raises(SQLError, match="chỉ được ghi thêm"):
        sql("truncate core.audit_log cascade")


def test_tampering_is_detected_even_by_superuser(world):
    """Superuser tắt trigger rồi sửa một dòng: core.audit_verify() chỉ đúng dòng đó."""
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 103)})["insert_office_documents_one"]
    target, original = sql(f"""select id, diff::text from core.audit_log
                               where entity_id = '{doc["id"]}' order by id desc limit 1""")[0]
    forged = json.loads(original)
    forged["summary"] = [None, "Nội dung đã bị sửa sau khi ghi sổ"]
    patch = "alter table core.audit_log disable trigger audit_no_change; " \
            "update core.audit_log set diff = '{diff}'::jsonb where id = {id}; " \
            "alter table core.audit_log enable trigger audit_no_change"
    try:
        sql(patch.format(diff=json.dumps(forged, ensure_ascii=False).replace("'", "''"), id=target))
        assert verify() == [[target, "hash"]]
    finally:
        sql(patch.format(diff=original.replace("'", "''"), id=target))
    assert verify() == []


def test_deleting_the_tail_is_detected(world):
    world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 104)})
    cols = "id, tenant_id, occurred_at, actor_id, actor_kind, request_id, action, entity, entity_id, diff, prev_hash, hash"
    last = sql("select max(id) from core.audit_log")[0][0]
    toggle = "alter table core.audit_log {on} trigger audit_no_change; alter table core.audit_log {on} trigger audit_chain"
    try:
        sql(f"{toggle.format(on='disable')}; "
            f"create table public._audit_tail as select {cols} from core.audit_log where id = {last}; "
            f"delete from core.audit_log where id = {last}; {toggle.format(on='enable')}")
        assert verify() == [[last, "head"]]       # đầu chuỗi vẫn trỏ vào dòng đã mất
    finally:
        sql(f"{toggle.format(on='disable')}; "
            f"insert into core.audit_log ({cols}) select {cols} from public._audit_tail on conflict do nothing; "
            f"drop table public._audit_tail; {toggle.format(on='enable')}")
    assert verify() == []


def test_concurrent_writers_keep_one_chain(world):
    """20 yêu cầu ghi song song qua Hasura vẫn cho một chuỗi liền, không rẽ nhánh."""
    before = int(sql("select last_id from core.audit_head")[0][0])

    def create(i: int) -> None:
        world.admin_a.gql(
            "mutation ($c: String!) { insert_office_departments_one(object: {code: $c, name: \"Phòng thử song song\"}) { id } }",
            {"c": f"SS{world.tag}{i}"},
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(create, range(20)))

    assert int(sql("select last_id from core.audit_head")[0][0]) == before + 20
    assert verify() == []
