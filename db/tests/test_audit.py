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
import os
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import INSERT_DOC, SQLError, User, incoming, sql, visible_ids

# Phần kiểm từ bên ngoài CSDL của lệnh `moc audit verify` (scripts/audit_chain.py, chỉ dùng thư viện chuẩn)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
from audit_chain import DOCUMENTS_SQL, HEAD_SQL, NOW_SQL, ROWS_SQL, check  # noqa: E402


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


# --- Kiểm từ bên ngoài CSDL và mốc neo (lệnh `moc audit verify`) --------------------------------------------


def outside(*anchors: dict, **options):
    # Test chạy tuần tự, không ai ghi sổ chen giữa các câu, nên không cần một giao dịch như scripts/moc.py
    head = json.loads(sql(HEAD_SQL)[0][0])
    rows = (json.loads(r[0]) for r in sql(ROWS_SQL))
    return check(rows, head, anchors, [json.loads(r[0]) for r in sql(DOCUMENTS_SQL)], **options)


def anchor_now() -> dict:
    """Mốc của đầu chuỗi hiện tại, như svc-files chép ra bucket lạnh."""
    head = json.loads(sql(HEAD_SQL)[0][0])
    return {"audit_id": head["id"], "hash": head["hash"], "source": "bucket thử"}


def problems(report) -> list[tuple[str, int | None]]:
    return [(p.kind, p.audit_id) for p in report.problems]


def test_outside_check_agrees_with_the_database(world):
    world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 105)})
    report = outside(anchor_now())
    assert report.ok, report.problems
    assert report.rows == report.last_id == int(sql("select last_id from core.audit_head")[0][0])
    assert report.anchors == {"bucket thử": {"checked": 1, "matched": 1}} and report.unanchored == 0


def test_outside_check_points_at_the_edited_row(world):
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 106)})["insert_office_documents_one"]
    target, original = sql(f"""select id, diff::text from core.audit_log
                               where entity_id = '{doc["id"]}' order by id desc limit 1""")[0]
    forged = json.loads(original)
    forged["summary"] = [None, "Nội dung đã bị sửa sau khi ghi sổ"]
    patch = "alter table core.audit_log disable trigger audit_no_change; " \
            "update core.audit_log set diff = '{diff}'::jsonb where id = {id}; " \
            "alter table core.audit_log enable trigger audit_no_change"
    try:
        sql(patch.format(diff=json.dumps(forged, ensure_ascii=False).replace("'", "''"), id=target))
        report = outside()
        assert problems(report) == [("hash", int(target))]
        assert f"office.documents {doc['id']}" in report.problems[0].message
    finally:
        sql(patch.format(diff=original.replace("'", "''"), id=target))
    assert outside().ok


def test_rewritten_chain_fools_the_database_but_not_the_anchor(world):
    """Superuser sửa một dòng rồi tính lại hash cả chuỗi phía sau: core.audit_verify() vẫn báo nguyên vẹn, mốc neo
    thì lệch, và khoảng dòng bị viết lại nằm giữa mốc còn khớp và mốc bị lệch."""
    before = anchor_now()
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 107)})["insert_office_documents_one"]
    target = int(sql(f"select max(id) from core.audit_log where entity_id = '{doc['id']}'")[0][0])
    world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 108)})
    after = anchor_now()
    world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 109)})      # thêm dòng sau mốc
    rewrite = f"""
      alter table core.audit_log disable trigger audit_no_change;
      create table public._audit_backup as select id, diff, prev_hash, hash from core.audit_log where id >= {target};
      do $$
      declare
        r core.audit_log;
        prev bytea := (select hash from core.audit_log where id = {target} - 1);
      begin
        for r in select * from core.audit_log where id >= {target} order by id loop
          if r.id = {target} then
            r.diff := jsonb_set(r.diff, '{{summary}}', '[null, "Trích yếu đã bị đổi"]');
          end if;
          r.prev_hash := prev;
          r.hash := core.audit_hash(r);
          update core.audit_log set diff = r.diff, prev_hash = r.prev_hash, hash = r.hash where id = r.id;
          prev := r.hash;
        end loop;
        update core.audit_head set last_hash = prev;
      end $$;
      alter table core.audit_log enable trigger audit_no_change"""
    restore = """
      alter table core.audit_log disable trigger audit_no_change;
      update core.audit_log l set diff = b.diff, prev_hash = b.prev_hash, hash = b.hash
        from public._audit_backup b where l.id = b.id;
      update core.audit_head set last_hash = (select hash from core.audit_log order by id desc limit 1);
      drop table public._audit_backup;
      alter table core.audit_log enable trigger audit_no_change"""
    try:
        sql(rewrite)
        assert verify() == []                        # kiểm trong CSDL bị qua mặt
        report = outside(before, after)
        assert problems(report) == [("anchor", after["audit_id"])]
        assert report.rewritten == (before["audit_id"] + 1, after["audit_id"])
        assert before["audit_id"] < target <= after["audit_id"]
    finally:
        sql(restore)
    assert verify() == [] and outside(before, after).ok


def test_cut_tail_with_moved_head_is_caught_by_the_anchor(world):
    """Xóa các dòng cuối rồi lùi cả đầu chuỗi: trong CSDL không còn dấu vết, mốc neo thì trỏ vào dòng đã mất."""
    world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 110)})
    tip = anchor_now()
    cols = "id, tenant_id, occurred_at, actor_id, actor_kind, request_id, action, entity, entity_id, diff, prev_hash, hash"
    toggle = "alter table core.audit_log {on} trigger audit_no_change; alter table core.audit_log {on} trigger audit_chain"
    try:
        sql(f"{toggle.format(on='disable')}; "
            f"create table public._audit_tail as select {cols} from core.audit_log where id = {tip['audit_id']}; "
            f"delete from core.audit_log where id = {tip['audit_id']}; "
            f"update core.audit_head set last_id = {tip['audit_id']} - 1, "
            f"  last_hash = (select hash from core.audit_log where id = {tip['audit_id']} - 1); "
            f"{toggle.format(on='enable')}")
        assert verify() == []
        assert problems(outside(tip)) == [("anchor_missing", tip["audit_id"])]
    finally:
        sql(f"{toggle.format(on='disable')}; "
            f"insert into core.audit_log ({cols}) select {cols} from public._audit_tail on conflict do nothing; "
            f"update core.audit_head set last_id = {tip['audit_id']}, last_hash = decode('{tip['hash']}', 'hex'); "
            f"drop table public._audit_tail; {toggle.format(on='enable')}")
    assert verify() == [] and outside(tip).ok


def test_document_hash_swapped_without_trigger_is_caught(world):
    """Đổi content_sha256 (để một tệp giả "khớp" ở cổng xác thực) khi tắt trigger: hash không còn khớp sổ."""
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 111)})["insert_office_documents_one"]
    real, fake = os.urandom(32).hex(), os.urandom(32).hex()
    sql(f"update office.documents set content_sha256 = '\\x{real}' where id = '{doc['id']}'")   # ghi sổ bình thường
    assert outside().ok
    swap = "alter table office.documents disable trigger audit; " \
           "update office.documents set content_sha256 = '\\x{sha}' where id = '{id}'; " \
           "alter table office.documents enable trigger audit"
    try:
        sql(swap.format(sha=fake, id=doc["id"]))
        report = outside()
        assert [p.kind for p in report.problems] == ["document"]
        assert doc["id"] in report.problems[0].message
    finally:
        sql(swap.format(sha=real, id=doc["id"]))
    sql(f"update office.documents set content_sha256 = null where id = '{doc['id']}'")
    assert outside().ok


def test_anchor_row_with_nothing_outside_is_flagged(world):
    """Bảng tra cứu ghi đã neo mà ngoài CSDL không có mốc đó: mốc bị xóa khỏi kho, hoặc dòng tra cứu thêm giả."""
    tip = anchor_now()
    claimed = {**tip, "location": "s3://moc-cold/anchors/thu"}
    assert outside(tip, recorded=[claimed]).ok
    assert problems(outside(recorded=[claimed])) == [("anchor_unbacked", tip["audit_id"])]


def test_anchor_written_after_the_read_waits_for_the_next_check(world):
    """Mốc neo ghi sau lúc đọc CSDL chưa có dòng của nó trong lần đọc: bỏ qua, không báo chuỗi bị cắt. Mốc trỏ
    quá cuối chuỗi mà có từ trước lúc đọc thì vẫn là chuỗi bị cắt."""
    last = json.loads(sql(HEAD_SQL)[0][0])["id"]
    now = json.loads(sql(NOW_SQL)[0][0])["now"]
    ahead = {"audit_id": last + 5, "hash": "ab" * 32, "source": "bucket thử"}
    report = outside({**ahead, "anchored_at": "2999-01-01T00:00:00+00:00"}, as_of=now)
    assert report.ok and report.later == 1
    assert problems(outside({**ahead, "anchored_at": "2026-01-01T00:00:00+00:00"}, as_of=now)) \
        == [("anchor_missing", last + 5)]


def test_service_event_shaped_like_a_document_change_is_not_a_hash(world):
    """Dịch vụ tự ghi sự kiện (diff không phải [cũ, mới]) vào đúng văn bản: không bị đọc nhầm thành hash văn bản."""
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 114)})["insert_office_documents_one"]
    real = os.urandom(32).hex()
    sql(f"update office.documents set content_sha256 = '\\x{real}' where id = '{doc['id']}'")
    world.service_a.gql(
        """mutation ($o: core_audit_log_insert_input!) { insert_core_audit_log_one(object: $o) { id } }""",
        {"o": {"actor_id": world.clerk_a.sub, "actor_kind": "user", "action": "document.note",
               "entity": "office.documents", "entity_id": doc["id"], "diff": {"content_sha256": "x"}}},
    )
    assert outside().ok
    sql(f"update office.documents set content_sha256 = null where id = '{doc['id']}'")


# --- Màn "Sổ kiểm toán": lãnh đạo, quản trị đơn vị xem sổ của đơn vị mình ------------------------------------

AUDIT_VIEW = """query ($e: String!) {
  core_audit_log(where: {entity_id: {_eq: $e}}, order_by: {id: asc}) { id action entity actor_id hash overview }
  core_audit_anchors_aggregate { aggregate { max { audit_id } } }
}"""


def test_director_sees_who_changed_what_but_not_the_content(world):
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 112, restricted=True)})["insert_office_documents_one"]
    assert doc["id"] not in visible_ids(world.director_a)          # văn bản hạn chế: lãnh đạo không đọc được
    sql(f"update office.documents set content_sha256 = '\\x{os.urandom(32).hex()}' where id = '{doc['id']}'")
    for viewer in (world.director_a, world.admin_a):
        row, hashed = viewer.gql(AUDIT_VIEW, {"e": doc["id"]})["core_audit_log"]
        assert (row["action"], row["entity"], row["actor_id"]) == ("insert", "office.documents", world.clerk_a.sub)
        assert row["overview"]["status"] == [None, "received"]      # cột không chứa nội dung: có giá trị
        assert row["overview"]["summary"] is None and "summary" in row["overview"]   # nội dung: chỉ biết là có đổi
        assert row["overview"]["symbol"] is None
        # có hash là tra được văn bản ở cổng xác thực công khai: hash cũng ẩn
        assert "content_sha256" in hashed["overview"] and hashed["overview"]["content_sha256"] is None


def test_audit_view_has_no_raw_diff_and_stays_in_the_tenant(world):
    doc = world.clerk_a.gql(INSERT_DOC, {"o": incoming(world.tag, 113)})["insert_office_documents_one"]
    assert "errors" in world.director_a.raw("{ core_audit_log(limit: 1) { diff } }")
    assert "errors" in world.director_a.raw("{ core_audit_head { last_id } }")
    for outsider in (world.clerk_a, world.manager_a1, world.staff_a1):
        assert "errors" in outsider.raw("{ core_audit_log(limit: 1) { id } }")
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert other.gql(AUDIT_VIEW, {"e": doc["id"]})["core_audit_log"] == []


def test_director_sees_how_far_the_chain_is_anchored(world):
    last = int(sql("select last_id from core.audit_head")[0][0])
    sql(f"""insert into core.audit_anchors (audit_id, hash, location)
            select id, hash, 's3://moc-cold/anchors/thu-' || id from core.audit_log where id = {last}""")
    try:
        data = world.director_a.gql(AUDIT_VIEW, {"e": "-"})
        assert data["core_audit_anchors_aggregate"]["aggregate"]["max"]["audit_id"] >= last
        assert "errors" in world.director_a.raw("{ core_audit_anchors { location hash } }")
    finally:
        sql("delete from core.audit_anchors where location like 's3://moc-cold/anchors/thu-%'")
