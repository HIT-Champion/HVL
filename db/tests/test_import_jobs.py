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

"""Lô nạp (core.import_jobs, core.import_rows — migration 1792281602800) trên PostgreSQL + Hasura thật: chỉ vai trò
service của đúng đơn vị đọc, ghi; lô + dòng + dòng sổ import.created trong một mutation; ràng buộc của dòng và lô; câu
của vòng nền (giữ dòng bằng claim_id: vòng đã mất dòng không ghi được gì); đóng lô ghi import.finished đúng một lần
(trigger), kể cả khi hai vòng cùng đóng; sổ kiểm toán hiện số dòng, không hiện tên tệp; quyền gọi Action khi svc-files
đóng vai văn thư.

Các câu GraphQL và hàm ilike_exact lấy thẳng từ services/svc-files/src/svc_files/imports/store.py (đọc bằng ast, không
chép tay) — đổi câu ở đó thì test này chạy câu mới."""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import ADMIN_SECRET, GraphQLError, Service, SQLError, gql_raw, incoming, insert_file, received, sql

STORE = pathlib.Path(__file__).resolve().parents[2] / "services" / "svc-files" / "src" / "svc_files" / "imports" / \
    "store.py"


def _queries() -> dict[str, str]:
    """Hằng chuỗi cấp module của store.py (kể cả ghép bằng +), tính bằng ast — không nạp svc-files."""
    out: dict[str, str] = {}
    for node in ast.parse(STORE.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                value = eval(compile(ast.Expression(node.value), str(STORE), "eval"), {"__builtins__": {}}, dict(out))
            except Exception:  # noqa: BLE001 — hằng không phải chuỗi tính được (lớp, hàm, tên ngoài): bỏ qua
                continue
            if isinstance(value, str):
                out[node.targets[0].id] = value
    return out


def _function(name: str):
    """Một hàm thuần của store.py (chỉ dùng ``re``), dựng lại từ ast — không nạp svc-files."""
    (node,) = [n for n in ast.parse(STORE.read_text(encoding="utf-8")).body
               if isinstance(n, ast.FunctionDef) and n.name == name]
    scope: dict = {"re": re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(STORE), "exec"), scope)  # noqa: S102 — mã của repo
    return scope[name]


Q = _queries()
ilike_exact = _function("ilike_exact")
ADMIN = {"X-Hasura-Admin-Secret": ADMIN_SECRET}


def as_clerk_service(clerk) -> Service:
    """svc-files thay mặt văn thư: vai trò service, thuê ước của văn thư, người là văn thư (store.py)."""
    return Service(clerk.sub, "service", clerk.tenant)


def new_job(clerk, *, total: int = 2, key: str | None = None, **extra) -> dict:
    job = {"id": str(uuid.uuid4()), "kind": "incoming", "created_by": clerk.sub, "filename": "lo.ndjson",
           "format": "ndjson", "data_sha256": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
           "options": {"register": False}, "idempotency_key": key, "total": total, **extra}
    return job


def create(clerk, job: dict, rows: list[dict] | None = None) -> dict:
    if rows is None:
        rows = [{"job_id": job["id"], "line": n, "data": {"symbol": f"{n}/UB"}, "files": []}
                for n in range(1, job["total"] + 1)]
    audit = {"actor_id": clerk.sub, "actor_kind": "user", "request_id": f"req-{job['id'][:8]}",
             "action": "import.created", "entity": "core.import_jobs", "entity_id": job["id"],
             "diff": {"kind": "incoming", "format": "ndjson", "register": False, "total": job["total"], "failed": 0,
                      "filename": job["filename"]}}
    return as_clerk_service(clerk).gql(Q["CREATE"], {"job": job, "rows": rows, "audit": audit})


def get(clerk, job_id: str) -> list[dict]:
    return as_clerk_service(clerk).gql(Q["JOB"], {"id": job_id, "user": clerk.sub})["core_import_jobs"]


def test_queries_were_read_from_the_store():
    assert {"CREATE", "BY_KEY", "JOB", "JOBS", "OPEN_COUNT", "ROWS", "DUE", "OPEN_IDS", "ACTOR", "PENDING", "START",
            "CLAIM", "PROGRESS", "RELEASE", "STRANDED", "FINISH", "FAIL_PENDING", "RESCHEDULE", "COUNTS", "CLOSE",
            "EXISTING", "DOCUMENT", "CLAIMED", "PERSONAL_FILES", "DROP_FILES"} <= set(Q)
    assert "pending_rows: rows_aggregate" in Q["JOB"] and Q["FILES_ACTOR"] == "svc-files:import"
    assert ilike_exact("UBND_10%") == "UBND\\_10\\%"


def test_service_creates_job_rows_and_audit_in_one_mutation(world):
    job = new_job(world.clerk_a, total=3)
    out = create(world.clerk_a, job)
    assert out["insert_core_import_rows"] == {"affected_rows": 3}
    (got,) = get(world.clerk_a, job["id"])
    assert got["tenant_id"] == world.tenant_a and got["status"] == "queued" and got["created_by"] == world.clerk_a.sub
    assert got["pending_rows"]["aggregate"]["count"] == 3 and got["run_after"]
    assert sql(f"select tenant_id from core.import_rows where job_id = '{job['id']}' group by 1") == [[world.tenant_a]]
    # đơn vị khác, người khác cùng đơn vị (câu JOB lọc người tạo) không thấy
    assert as_clerk_service(world.clerk_b).gql(Q["JOB"], {"id": job["id"], "user": world.clerk_a.sub}) == {
        "core_import_jobs": []}
    assert as_clerk_service(world.clerk_a).gql(Q["JOB"], {"id": job["id"], "user": world.director_a.sub}) == {
        "core_import_jobs": []}
    audit = sql(f"select tenant_id, actor_id, actor_kind, action from core.audit_log where entity = 'core.import_jobs' "
                f"and entity_id = '{job['id']}'")
    assert audit == [[world.tenant_a, world.clerk_a.sub, "user", "import.created"]]
    # hai bảng không có trigger sổ kiểm toán: không có dòng insert của từng dòng
    assert sql(f"select count(*) from core.audit_log where entity = 'core.import_rows' and entity_id like "
               f"'{job['id']}%'") == [["0"]]


def test_one_bad_row_rolls_back_the_whole_creation(world):
    job = new_job(world.clerk_a)
    rows = [{"job_id": job["id"], "line": 1, "data": {"a": 1}, "files": []},
            {"job_id": job["id"], "line": 2, "data": None, "files": []}]          # pending mà không có dữ liệu
    with pytest.raises(GraphQLError):
        create(world.clerk_a, job, rows)
    assert get(world.clerk_a, job["id"]) == []
    assert sql(f"select count(*) from core.audit_log where entity_id = '{job['id']}'") == [["0"]]


@pytest.mark.parametrize("who", ["clerk_a", "director_a", "staff_a1", "admin_a"])
def test_user_roles_do_not_see_the_tables(world, who):
    body = getattr(world, who).raw("{ core_import_jobs { id } core_import_rows { line } }")
    assert body["errors"][0]["extensions"]["code"] == "validation-failed"


def test_idempotency_key_is_unique_per_creator(world):
    key = f"lo-{world.tag}"
    create(world.clerk_a, new_job(world.clerk_a, key=key))
    with pytest.raises(GraphQLError, match="import_jobs_key") as exc:
        create(world.clerk_a, new_job(world.clerk_a, key=key))
    assert exc.value.errors[0]["extensions"]["code"] == "constraint-violation"
    other = world.director_a          # người khác cùng đơn vị, cùng khóa: lô khác (chỉ để thử ràng buộc)
    create(other, new_job(other, key=key))
    for _ in range(2):                # không khóa: bao nhiêu lô cũng được
        create(world.clerk_a, new_job(world.clerk_a))
    found = as_clerk_service(world.clerk_a).gql(Q["BY_KEY"], {"user": world.clerk_a.sub, "key": key})
    assert len(found["core_import_jobs"]) == 1
    with pytest.raises(GraphQLError):
        create(world.clerk_a, new_job(world.clerk_a, key="có dấu cách"))


def _job_sql(world, **cols) -> str:
    base = {"id": f"'{uuid.uuid4()}'", "tenant_id": f"'{world.tenant_a}'", "kind": "'incoming'",
            "created_by": f"'{world.clerk_a.sub}'", "filename": "'lo.csv'", "format": "'csv'",
            "data_sha256": f"'{'a' * 64}'", "total": "2"}
    base.update(cols)
    return f"insert into core.import_jobs ({', '.join(base)}) values ({', '.join(base.values())}) returning id"


@pytest.mark.parametrize("cols", [
    {"ok": "2", "failed": "1"},                                              # đếm quá tổng
    {"status": "'done'", "ok": "2"},                                         # done mà chưa có finished_at
    {"status": "'done'", "ok": "1", "finished_at": "now()"},                 # đóng mà số đếm không khớp tổng
    {"status": "'running'", "finished_at": "now()"},
    {"kind": "'outgoing'"}, {"format": "'xlsx'"}, {"data_sha256": "'ABC'"},
    {"archive_sha256": f"'{'b' * 64}'"},                                     # có băm zip mà không có cỡ
    {"total": "0"}, {"note": "repeat('x', 501)"}, {"idempotency_key": "'a b'"},
])
def test_job_constraints(world, cols):
    with pytest.raises(SQLError):
        sql(_job_sql(world, **cols))


def test_closed_job_with_matching_counts_is_accepted(world):
    sql(_job_sql(world, status="'done'", ok="1", duplicate="1", finished_at="now()"))


@pytest.mark.parametrize("cols", [
    {"data": "null"},                                                        # chờ mà không có dữ liệu
    {"status": "'ok'", "done_at": "now()"},                                  # xong mà còn dữ liệu
    {"status": "'failed'", "data": "null", "done_at": "now()"},              # lỗi mà không có mã
    {"status": "'failed'", "data": "null", "code": "'Bad-Code'", "done_at": "now()"},
    {"status": "'ok'", "data": "null"},                                      # xong mà không có done_at
    {"files": "array_fill('a'::text, array[21])"},
    {"attempts": "21"}, {"line": "0"}, {"data": "'[1]'"}, {"message": "repeat('x', 501)"},
])
def test_row_constraints(world, cols):
    (job_id,) = sql(_job_sql(world))[0]
    base = {"job_id": f"'{job_id}'", "tenant_id": f"'{world.tenant_a}'", "line": "1", "data": "'{\"a\": 1}'"}
    base.update(cols)
    with pytest.raises(SQLError):
        sql(f"insert into core.import_rows ({', '.join(base)}) values ({', '.join(base.values())})")


def test_rows_stay_in_the_tenant_of_their_job_and_go_with_it(world):
    (job_id,) = sql(_job_sql(world))[0]
    with pytest.raises(SQLError):
        sql(f"insert into core.import_rows (job_id, tenant_id, line, data) values ('{job_id}', '{world.tenant_b}', 1,"
            " '{}')")
    sql(f"insert into core.import_rows (job_id, tenant_id, line, data) values ('{job_id}', '{world.tenant_a}', 1,"
        " '{}')")
    sql(f"delete from core.import_jobs where id = '{job_id}'")
    assert sql(f"select count(*) from core.import_rows where job_id = '{job_id}'") == [["0"]]


def test_service_of_another_tenant_cannot_write_rows_of_a_job(world):
    job = new_job(world.clerk_a)
    create(world.clerk_a, job)
    svc_b = as_clerk_service(world.clerk_b)
    assert svc_b.gql(Q["CLAIM"], {"id": job["id"], "line": 1, "attempts": 0, "now": "2026-10-23T09:00:00+07:00",
                                  "until": "2026-10-23T09:05:00+07:00", "claim": str(uuid.uuid4()), "bump": 1}) == {
        "update_core_import_rows": {"returning": []}}
    assert svc_b.gql(Q["RELEASE"], {"id": job["id"], "line": 1, "claim": str(uuid.uuid4())}) == {
        "update_core_import_rows": {"affected_rows": 0}}
    assert svc_b.gql(Q["RESCHEDULE"], {"id": job["id"], "set": {"note": "x"}}) == {
        "update_core_import_jobs": {"affected_rows": 0}}
    # thêm dòng vào lô của đơn vị khác: preset tenant_id của B không khớp khóa ngoại (job_id, tenant_id)
    with pytest.raises(GraphQLError):
        svc_b.gql("mutation ($o: core_import_rows_insert_input!) { insert_core_import_rows_one(object: $o) { line } }",
                  {"o": {"job_id": job["id"], "line": 9, "data": {"a": 1}}})
    # service không đổi được thuê ước, người tạo, tổng của lô
    with pytest.raises(GraphQLError):
        as_clerk_service(world.clerk_a).gql(Q["RESCHEDULE"], {"id": job["id"], "set": {"total": 1}})


def _claimed(out: dict) -> list[int]:
    return [r["line"] for r in out["update_core_import_rows"]["returning"]]


def test_background_round_trip(world):
    clerk = world.clerk_a
    svc = as_clerk_service(clerk)
    job = new_job(clerk, total=3)
    create(clerk, job)
    assert svc.gql(Q["START"], {"id": job["id"], "at": "2026-10-23T09:00:00+07:00"})["update_core_import_jobs"] == {
        "affected_rows": 1}
    now, until = "2026-10-23T09:00:00+07:00", "2026-10-23T09:05:00+07:00"
    c1, c2, c3 = (str(uuid.uuid4()) for _ in range(3))

    def lines_pending(at: str) -> list[int]:
        return [r["line"] for r in svc.gql(Q["PENDING"], {"id": job["id"], "limit": 5, "now": at})["core_import_rows"]]

    pending = svc.gql(Q["PENDING"], {"id": job["id"], "limit": 2, "now": now})["core_import_rows"]
    assert [(r["line"], r["attempts"], r["result"]) for r in pending] == [(1, 0, None), (2, 0, None)]
    # nhận dòng là một cập nhật có điều kiện, trả dòng sau khi nhận: cùng attempts lần thứ hai không ăn
    claim = {"id": job["id"], "line": 1, "attempts": 0, "now": now, "until": until, "claim": c1, "bump": 1}
    got = svc.gql(Q["CLAIM"], claim)["update_core_import_rows"]["returning"]
    assert got == [{"line": 1, "data": {"symbol": "1/UB"}, "files": [], "attempts": 1, "result": None}]
    assert _claimed(svc.gql(Q["CLAIM"], {**claim, "claim": c2})) == []
    # dòng đang được giữ: vòng khác không thấy (PENDING), không nhận được (CLAIM) tới khi quá hạn giữ
    assert lines_pending(now) == [2, 3]
    held = {**claim, "attempts": 1, "now": "2026-10-23T09:04:59+07:00", "until": "2026-10-23T09:10:00+07:00",
            "claim": c2}
    assert _claimed(svc.gql(Q["CLAIM"], held)) == []
    # vòng giữ lưu tiến độ (đúng mã lượt giữ) trước khi hết hạn
    progress = {"id": job["id"], "line": 1, "claim": c1, "result": {"file_ids": ["f0"]}, "until": until}
    assert svc.gql(Q["PROGRESS"], progress)["update_core_import_rows"] == {"affected_rows": 1}
    late = {**held, "now": "2026-10-23T09:05:01+07:00"}
    assert lines_pending(late["now"]) == [1, 2, 3]
    # quá hạn: vòng khác nhận lại — thấy tiến độ vòng trước vừa lưu (không lưu lại tệp đó)
    got = svc.gql(Q["CLAIM"], late)["update_core_import_rows"]["returning"]
    assert [(r["line"], r["attempts"], r["result"]) for r in got] == [(1, 2, {"file_ids": ["f0"]})]
    assert sql(f"select attempts, claimed_until = '2026-10-23T09:10:00+07:00', claim_id = '{c2}' from "
               f"core.import_rows where job_id = '{job['id']}' and line = 1") == [["2", "t", "t"]]
    # vòng cũ (mã c1) đã mất dòng: lưu tiến độ, thả, ghi kết quả đều không ăn
    done = {"status": "ok", "data": None, "code": None, "message": None, "fields": None,
            "done_at": "2026-10-23T09:00:01+07:00"}
    assert svc.gql(Q["PROGRESS"], {**progress, "result": {"file_ids": ["f0", "f9"]}})["update_core_import_rows"] == {
        "affected_rows": 0}
    assert svc.gql(Q["RELEASE"], {"id": job["id"], "line": 1, "claim": c1})["update_core_import_rows"] == {
        "affected_rows": 0}
    assert svc.gql(Q["FINISH"], {"id": job["id"], "line": 1, "claim": c1, "set": {**done, "status": "duplicate"}})[
        "update_core_import_rows"] == {"affected_rows": 0}
    assert sql(f"select status, result::text from core.import_rows where job_id = '{job['id']}' and line = 1") == [
        ["pending", '{"file_ids": ["f0"]}']]
    # lõi bận: thả dòng vừa nhận — dòng hiện lại ngay
    assert _claimed(svc.gql(Q["CLAIM"], {**claim, "line": 2, "claim": c3})) == [2]
    assert lines_pending(now) == [3]
    assert svc.gql(Q["RELEASE"], {"id": job["id"], "line": 2, "claim": c3})["update_core_import_rows"] == {
        "affected_rows": 1}
    assert lines_pending(now) == [2, 3]
    assert sql(f"select claimed_until is null and claim_id is null from core.import_rows where job_id = '{job['id']}' "
               "and line = 2") == [["t"]]
    assert _claimed(svc.gql(Q["CLAIM"], {**claim, "line": 2, "attempts": 1, "claim": c3})) == [2]
    doc = str(uuid.uuid4())
    svc.gql(Q["PROGRESS"], {"id": job["id"], "line": 1, "claim": c2, "result": {"file_ids": ["f1"], "document_id": doc},
                            "until": until})
    svc.gql(Q["PROGRESS"], {"id": job["id"], "line": 2, "claim": c3, "result": {"file_ids": ["f2"]}, "until": until})
    # dòng còn chờ đã lưu tệp (để gỡ tệp khi hủy cả lô)
    assert [(r["line"], r["result"]["file_ids"]) for r in svc.gql(Q["STRANDED"], {"id": job["id"]})[
        "core_import_rows"]] == [(1, ["f1"]), (2, ["f2"])]
    assert svc.gql(Q["FINISH"], {"id": job["id"], "line": 1, "claim": c2, "set": done})["update_core_import_rows"] == {
        "affected_rows": 1}
    # dòng đã xong: ghi lần nữa không ăn (status = pending trong điều kiện)
    assert svc.gql(Q["FINISH"], {"id": job["id"], "line": 1, "claim": c2,
                                 "set": {**done, "status": "failed", "code": "x"}})["update_core_import_rows"] == {
        "affected_rows": 0}
    assert [r["line"] for r in svc.gql(Q["STRANDED"], {"id": job["id"]})["core_import_rows"]] == [2]
    assert as_clerk_service(world.clerk_b).gql(Q["STRANDED"], {"id": job["id"]})["core_import_rows"] == []
    # văn bản đã có dòng nhận: dòng khác hỏi thì thấy, chính dòng đó hỏi thì không
    assert svc.gql(Q["CLAIMED"], {"doc": {"document_id": doc}, "id": job["id"], "line": 2})[
        "core_import_rows_aggregate"]["aggregate"]["count"] == 1
    assert svc.gql(Q["CLAIMED"], {"doc": {"document_id": doc}, "id": job["id"], "line": 1})[
        "core_import_rows_aggregate"]["aggregate"]["count"] == 0
    assert as_clerk_service(world.clerk_b).gql(Q["CLAIMED"], {"doc": {"document_id": doc}, "id": job["id"],
                                                              "line": 2})["core_import_rows_aggregate"]["aggregate"][
        "count"] == 0
    failed = {"status": "failed", "data": None, "code": "actor_revoked", "message": "khóa", "done_at": done["done_at"]}
    assert svc.gql(Q["FAIL_PENDING"], {"id": job["id"], "set": failed})["update_core_import_rows"] == {
        "affected_rows": 2}
    # cả lô bị hủy khi vòng khác đang giữ dòng 2: vòng đó lưu tiến độ không ăn
    assert svc.gql(Q["PROGRESS"], {"id": job["id"], "line": 2, "claim": c3, "result": {}, "until": until})[
        "update_core_import_rows"] == {"affected_rows": 0}
    counts = svc.gql(Q["COUNTS"], {"id": job["id"]})
    assert {k: v["aggregate"]["count"] for k, v in counts.items()} == {"pending": 0, "ok": 1, "duplicate": 0,
                                                                       "failed": 2}
    close = {"status": "done", "finished_at": done["done_at"], "run_after": done["done_at"], "note": None, "ok": 1,
             "duplicate": 0, "failed": 2}
    assert svc.gql(Q["CLOSE"], {"id": job["id"], "set": close}) == {"update_core_import_jobs": {"affected_rows": 1}}
    (got,) = get(clerk, job["id"])
    assert (got["status"], got["ok"], got["failed"]) == ("done", 1, 2)
    # dòng sổ import.finished do trigger ghi, cùng giao dịch đóng lô: người là văn thư (service), mã yêu cầu là id lô
    (finished,) = sql(f"select tenant_id, actor_id, actor_kind, request_id, diff::text from core.audit_log "
                      f"where entity = 'core.import_jobs' and entity_id = '{job['id']}' and action = 'import.finished'")
    assert finished[:4] == [world.tenant_a, clerk.sub, "service", job["id"]]
    assert json.loads(finished[4]) == {"kind": "incoming", "format": "ndjson", "register": False, "total": 3, "ok": 1,
                                       "duplicate": 0, "failed": 2}
    # đóng rồi thì không hẹn lại, không đóng lại, không ghi sổ lần hai
    assert svc.gql(Q["CLOSE"], {"id": job["id"], "set": close}) == {"update_core_import_jobs": {"affected_rows": 0}}
    assert svc.gql(Q["RESCHEDULE"], {"id": job["id"], "set": {"note": "x"}})["update_core_import_jobs"] == {
        "affected_rows": 0}
    sql(f"update core.import_jobs set status = 'done', note = 'sửa tay' where id = '{job['id']}'")
    assert sql(f"select count(*) from core.audit_log where entity_id = '{job['id']}' "
               "and action = 'import.finished'") == [["1"]]
    rows = svc.gql(Q["ROWS"], {"id": job["id"], "statuses": ["ok", "failed"], "after": 0, "limit": 10})
    assert [(r["line"], r["status"], r["code"]) for r in rows["core_import_rows"]] == [
        (1, "ok", None), (2, "failed", "actor_revoked"), (3, "failed", "actor_revoked")]
    listed = svc.gql(Q["JOBS"], {"user": clerk.sub, "limit": 50})["core_import_jobs"]
    assert job["id"] in {j["id"] for j in listed}


def test_two_closers_log_import_finished_once(world):
    """Hai vòng nền (hai tiến trình svc-files) cùng thấy lô hết dòng chờ và cùng gửi CLOSE: lô done một lần, sổ đúng một
    dòng import.finished — lệnh sau đợi khóa dòng của lệnh trước, đọc lại thì lô đã done, không đổi gì."""
    clerk = world.clerk_a
    for _ in range(3):
        job = new_job(clerk, total=1)
        create(clerk, job, [{"job_id": job["id"], "line": 1, "data": None, "files": [], "status": "failed",
                             "code": "bad_json", "done_at": "2026-10-23T09:00:00+07:00"}])
        close = {"status": "done", "finished_at": "2026-10-23T09:00:01+07:00", "run_after": "2026-10-23T09:00:01+07:00",
                 "note": None, "ok": 0, "duplicate": 0, "failed": 1}
        with ThreadPoolExecutor(2) as pool:
            outs = list(pool.map(lambda _: as_clerk_service(clerk).gql(Q["CLOSE"], {"id": job["id"], "set": close}),
                                 range(2)))
        assert sorted(o["update_core_import_jobs"]["affected_rows"] for o in outs) == [0, 1]
        assert sql(f"select count(*) from core.audit_log where entity_id = '{job['id']}' "
                   "and action = 'import.finished'") == [["1"]]
    assert sql("select audit_id, problem from core.audit_verify()") == []      # chuỗi băm vẫn liền


def test_due_and_open_ids_read_every_tenant_with_the_admin_secret(world):
    a, b = new_job(world.clerk_a, total=1), new_job(world.clerk_b, total=1)
    create(world.clerk_a, a)
    create(world.clerk_b, b)
    sql(f"update core.import_jobs set run_after = '2000-01-01T00:00:00Z' where id = '{a['id']}'")
    sql(f"update core.import_jobs set run_after = '2000-01-01T00:01:00Z' where id = '{b['id']}'")
    due = gql_raw(Q["DUE"], {"now": "2000-01-01T00:00:30Z"}, headers=ADMIN)["data"]["core_import_jobs"]
    assert [(j["id"], j["tenant_id"], j["created_by"]) for j in due] == [(a["id"], world.tenant_a, world.clerk_a.sub)]
    assert due[0]["options"] == {"register": False} and due[0]["archive_bytes"] is None
    sql(f"update core.import_jobs set run_after = '2100-01-01T00:00:00Z' where id = '{a['id']}'")
    due = gql_raw(Q["DUE"], {"now": "2000-01-01T00:01:30Z"}, headers=ADMIN)["data"]["core_import_jobs"]
    assert [j["id"] for j in due] == [b["id"]]
    assert gql_raw(Q["DUE"], {"now": "1999-12-31T00:00:00Z"}, headers=ADMIN)["data"]["core_import_jobs"] == []
    ids = {j["id"] for j in gql_raw(Q["OPEN_IDS"], {}, headers=ADMIN)["data"]["core_import_jobs"]}
    assert {a["id"], b["id"]} <= ids
    open_a = as_clerk_service(world.clerk_a).gql(Q["OPEN_COUNT"], {})["core_import_jobs_aggregate"]["aggregate"]
    assert open_a["count"] >= 1


def test_duplicate_lookup_matches_the_intake_dedup_rule(world):
    clerk, tag = world.clerk_a, world.tag
    doc = received(clerk, incoming(tag, 840, issuer_name="UBND tỉnh Hưng_Yên 100%"))
    job = new_job(clerk)
    create(clerk, job)
    svc = as_clerk_service(clerk)
    # store.existing() gửi ilike_exact(cơ quan ban hành): \ % _ được thoát, không phân biệt hoa thường
    ilike = ilike_exact("ubnd TỈNH hưng_yên 100%")
    assert ilike == "ubnd TỈNH hưng\\_yên 100\\%"
    found = svc.gql(Q["EXISTING"], {"symbol": f"840/UBND-VP{tag}", "issuer": ilike, "issued": "2026-10-15"})
    assert [d["id"] for d in found["office_documents"]] == [doc["id"]]
    assert found["office_documents"][0]["created_by"] == clerk.sub
    # đã thoát thì % và _ không còn là ký tự đại diện: "UBND%" (tiền tố) và "UBND_tỉnh…" (_ thay dấu cách) không khớp
    # văn bản vừa tạo — chưa thoát thì cả hai đều khớp
    for issuer in ("UBND%", "UBND_tỉnh Hưng_Yên 100%"):
        assert svc.gql(Q["EXISTING"], {"symbol": f"840/UBND-VP{tag}", "issuer": issuer, "issued": "2026-10-15"})[
            "office_documents"] == found["office_documents"]
        assert svc.gql(Q["EXISTING"], {"symbol": f"840/UBND-VP{tag}", "issuer": ilike_exact(issuer),
                                       "issued": "2026-10-15"})["office_documents"] == []
    # đơn vị khác không thấy
    assert as_clerk_service(world.clerk_b).gql(Q["EXISTING"], {"symbol": f"840/UBND-VP{tag}", "issuer": ilike,
                                                               "issued": "2026-10-15"})["office_documents"] == []
    got = svc.gql(Q["DOCUMENT"], {"id": doc["id"]})["office_documents_by_pk"]
    assert got["id"] == doc["id"] and got["register_number"] is None


def test_drop_files_removes_only_unattached_files_of_the_row_owner(world):
    clerk, tag = world.clerk_a, world.tag
    loose, personal, attached = (insert_file(world.service_a, clerk, f"lo-{n}.pdf") for n in range(3))
    sealed = insert_file(world.service_a, clerk, "han-che.pdf", encrypted=True)
    by_other = insert_file(world.service_a, world.staff_a1, "nguoi-khac.pdf")
    in_other_tenant = insert_file(world.service_b, world.clerk_b, "don-vi-khac.pdf")
    received(clerk, {**incoming(tag, 842), "files": {"data": [
        {"file_id": attached, "role": "main", "added_by": clerk.sub}]}})
    sql(f"insert into personal.items (file_id, tenant_id, owner_id, para) values ('{personal}', '{world.tenant_a}', "
        f"'{clerk.sub}', 'resources')")
    sql(f"insert into core.file_texts (file_id, tenant_id, status, content) values ('{loose}', '{world.tenant_a}', "
        "'ok', 'chữ của tệp')")
    job = new_job(clerk)
    create(clerk, job)
    rid = f"{job['id']}:7"
    headers = {**ADMIN, "X-Hasura-User-Id": Q["FILES_ACTOR"], "X-Hasura-Request-Id": rid}
    asked = [loose, personal, attached, sealed, by_other, in_other_tenant]
    kept = gql_raw(Q["PERSONAL_FILES"], {"ids": asked}, headers=headers)["data"]["personal_items"]
    assert [k["file_id"] for k in kept] == [personal]
    ids = [i for i in asked if i != personal]
    body = gql_raw(Q["DROP_FILES"], {"ids": ids, "tenant": world.tenant_a, "user": clerk.sub}, headers=headers)
    assert "errors" not in body, body
    gone = body["data"]["delete_core_files"]["returning"]
    # chỉ tệp của đúng người, đúng đơn vị, chưa gắn văn bản; kể cả tệp mã hóa của văn bản hạn chế chưa tạo được
    assert sorted(f["id"] for f in gone) == sorted([loose, sealed])
    assert {f["id"]: f["object_key"] for f in gone}[loose] == f"tenant/{world.tenant_a}/2026/10/{loose}"
    quoted = ", ".join(f"'{i}'" for i in asked)
    assert {r[0] for r in sql(f"select id from core.files where id in ({quoted})")} == {
        personal, attached, by_other, in_other_tenant}
    assert sql(f"select count(*) from core.file_texts where file_id = '{loose}'") == [["0"]]   # xóa theo tệp
    # sổ kiểm toán: người là svc-files:import, actor_kind system, mã yêu cầu của dòng
    assert sql(f"select actor_id, actor_kind, request_id from core.audit_log where entity = 'core.files' "
               f"and entity_id = '{loose}' and action = 'delete'") == [["svc-files:import", "system", rid]]
    # tệp đã gắn văn bản: kể cả khi bỏ điều kiện trong câu, khóa ngoại của office.document_files vẫn chặn
    with pytest.raises(SQLError):
        sql(f"delete from core.files where id = '{attached}'")
    # vai trò service (và vai trò người dùng) không có quyền xóa core.files
    denied = as_clerk_service(clerk).raw(Q["DROP_FILES"], {"ids": [by_other], "tenant": world.tenant_a,
                                                           "user": world.staff_a1.sub})
    assert "errors" in denied


def test_actor_lookup_reads_the_directory_of_the_tenant(world):
    svc = as_clerk_service(world.clerk_a)
    svc.gql("""mutation ($o: core_users_insert_input!) {
      insert_core_users_one(object: $o, on_conflict: {constraint: users_pkey, update_columns: [enabled]}) { id } }""",
            {"o": {"id": world.clerk_a.sub, "username": f"vt-a-{world.tag}", "full_name": "Văn thư A",
                   "role": "clerk"}})
    assert svc.gql(Q["ACTOR"], {"id": world.clerk_a.sub})["core_users"] == [{"enabled": True, "role": "clerk"}]
    assert as_clerk_service(world.clerk_b).gql(Q["ACTOR"], {"id": world.clerk_a.sub})["core_users"] == []


def test_audit_overview_shows_counts_but_not_the_file_name(world):
    job = new_job(world.clerk_a, filename="danh-sach-mat.ndjson")
    create(world.clerk_a, job)
    (row,) = sql(f"select core.audit_overview(a)::text from core.audit_log a where entity = 'core.import_jobs' "
                 f"and entity_id = '{job['id']}'")
    overview = json.loads(row[0])
    assert {k: v for k, v in overview.items() if v is not None} == {"kind": "incoming", "format": "ndjson",
                                                                     "register": False, "total": 2, "failed": 0}
    assert overview.get("filename") is None
    # các sự kiện khác giữ nguyên như 1792281602100: file.rejected vẫn chỉ hiện mẫu mã độc, cỡ
    sql(f"insert into core.audit_log (tenant_id, actor_id, actor_kind, action, entity, entity_id, diff) values "
        f"('{world.tenant_a}', 'u', 'user', 'file.rejected', 'core.files', 'x{world.tag}', "
        "'{\"filename\": \"a.exe\", \"signature\": \"Eicar\", \"size_bytes\": 68}')")
    (row,) = sql(f"select core.audit_overview(a)::text from core.audit_log a where entity_id = 'x{world.tag}'")
    assert {k: v for k, v in json.loads(row[0]).items() if v is not None} == {"signature": "Eicar", "size_bytes": 68}


def test_receive_incoming_as_clerk_reaches_the_action_handler(world):
    """svc-files gọi Action bằng khóa quản trị + X-Hasura-Role: clerk (hasura.act_as): Hasura cho gọi và chuyển sang
    svc-workflow (stack test không có nên lỗi gọi webhook), không phải lỗi quyền; với vai trò không được gọi thì lỗi
    quyền như khi dùng token."""
    query = "mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }"

    def act(role: str) -> dict:
        return gql_raw(query, {"d": {}}, headers={**ADMIN, "X-Hasura-Role": role, "X-Hasura-Tenant-Id": world.tenant_a,
                                                  "X-Hasura-User-Id": world.clerk_a.sub})

    body = act("clerk")
    assert "not found in type" not in body["errors"][0]["message"]
    assert body["errors"][0]["extensions"]["code"] != "validation-failed"
    for role in ("staff", "director", "service"):
        body = act(role)
        assert body["errors"][0]["extensions"]["code"] == "validation-failed", role
