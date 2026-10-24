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

"""ImportStore trên HasuraClient thật (MockTransport): câu của API và của vòng nền chạy bằng vai trò service trong đúng
đơn vị; chỉ hai câu tìm lô (mọi đơn vị) dùng khóa quản trị không vai trò. Câu GraphQL chạy thật ở
db/tests/test_import_jobs.py."""

import asyncio
import json
import uuid
from datetime import UTC, datetime

import httpx2
import pytest

from svc_files.hasura import HasuraClient, HasuraError
from svc_files.imports.store import ImportStore, KeyTaken, ilike_exact, view

TENANT = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000a")
JOB = {"id": "8d0c0000-0000-4000-8000-000000000001", "tenant_id": str(TENANT), "created_by": "u-van-thu"}


class Hasura:
    def __init__(self, *replies) -> None:
        self.replies = list(replies)
        self.requests: list[tuple[dict[str, str], dict]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(({k.lower(): v for k, v in request.headers.items()}, json.loads(request.content)))
        return httpx2.Response(200, json=self.replies.pop(0))

    def store(self) -> ImportStore:
        return ImportStore(HasuraClient("http://hasura:8080", "bi-mat", transport=httpx2.MockTransport(self)))


def run(coro):
    return asyncio.run(coro)


def test_create_writes_job_rows_and_audit_as_service_of_the_tenant():
    h = Hasura({"data": {"insert_core_import_jobs_one": {"id": JOB["id"]},
                         "insert_core_import_rows": {"affected_rows": 1},
                         "insert_core_audit_log": {"affected_rows": 1}}})
    run(h.store().create({"id": JOB["id"], "total": 1}, [{"line": 1, "data": {"a": 1}, "files": []}],
                         {"action": "import.created"}, tenant_id=TENANT, user="u-van-thu", rid="req-1"))
    ((headers, body),) = h.requests
    assert headers["x-hasura-admin-secret"] == "bi-mat" and headers["x-hasura-role"] == "service"
    assert headers["x-hasura-tenant-id"] == str(TENANT) and headers["x-hasura-user-id"] == "u-van-thu"
    assert headers["x-hasura-request-id"] == "req-1"
    # lô, dòng, dòng sổ import.created: một mutation, một giao dịch
    for field in ("insert_core_import_jobs_one", "insert_core_import_rows", "insert_core_audit_log"):
        assert field in body["query"]
    assert body["variables"]["rows"] == [{"line": 1, "data": {"a": 1}, "files": []}]


def test_idempotency_key_race_is_key_taken_other_constraints_are_not():
    err = {"errors": [{"message": 'Uniqueness violation. duplicate key value violates unique constraint '
                                  '"import_jobs_key"', "extensions": {"code": "constraint-violation"}}]}
    with pytest.raises(KeyTaken):
        run(Hasura(err).store().create({}, [], {}, tenant_id=TENANT, user="u", rid="r"))
    other = {"errors": [{"message": 'violates foreign key constraint "import_jobs_tenant_id_fkey"',
                         "extensions": {"code": "constraint-violation"}}]}
    with pytest.raises(HasuraError) as exc:
        run(Hasura(other).store().create({}, [], {}, tenant_id=TENANT, user="u", rid="r"))
    assert not isinstance(exc.value, KeyTaken) and exc.value.code == "constraint-violation"


def test_due_and_open_ids_use_the_admin_secret_without_a_role():
    h = Hasura({"data": {"core_import_jobs": [JOB]}}, {"data": {"core_import_jobs": [{"id": "a"}, {"id": "b"}]}})
    store = h.store()
    assert run(store.due(datetime(2026, 10, 23, 1, 0, tzinfo=UTC))) == JOB
    assert run(store.open_ids()) == {"a", "b"}
    for headers, _ in h.requests:
        assert headers["x-hasura-admin-secret"] == "bi-mat" and "x-hasura-role" not in headers
    assert h.requests[0][1]["variables"] == {"now": "2026-10-23T01:00:00+00:00"}


def test_background_queries_run_as_service_of_the_job_with_row_request_ids():
    row = {"line": 7, "data": {"a": 1}, "files": [], "attempts": 3, "result": {"file_ids": ["f1"]}}
    h = Hasura({"data": {"update_core_import_rows": {"returning": [row]}}},
               {"data": {"office_documents": []}},
               {"data": {"core_import_rows_aggregate": {"aggregate": {"count": 0}}}},
               {"data": {"update_core_import_rows": {"returning": []}}})
    store = h.store()
    now, until = datetime(2026, 10, 23, 1, 0, tzinfo=UTC), datetime(2026, 10, 23, 1, 5, tzinfo=UTC)
    # nhận dòng trả dòng như đang có trong CSDL (tiến độ vòng giữ trước kịp lưu); vòng khác đã nhận thì None
    assert run(store.claim(JOB, 7, 2, now=now, until=until, claim_id="c-1")) == row
    assert run(store.existing(JOB, 7, symbol="1/UB", issuer="UBND 100%_x", issued_on="2026-10-15")) is None
    assert run(store.claimed(JOB, 7, "doc-1")) is False
    assert run(store.claim(JOB, 7, 20, now=now, until=until, claim_id="c-2", bump=0)) is None
    for headers, _ in h.requests:
        assert headers["x-hasura-role"] == "service" and headers["x-hasura-tenant-id"] == str(TENANT)
        assert headers["x-hasura-user-id"] == "u-van-thu" and headers["x-hasura-request-id"] == f"{JOB['id']}:7"
    # nhận dòng: attempts khớp và chưa ai giữ (hoặc quá hạn giữ) — một lệnh cập nhật có điều kiện, giữ tới until
    assert h.requests[0][1]["variables"] == {"id": JOB["id"], "line": 7, "attempts": 2,
                                             "now": "2026-10-23T01:00:00+00:00", "until": "2026-10-23T01:05:00+00:00",
                                             "claim": "c-1", "bump": 1}
    assert "claimed_until: {_lt: $now}" in h.requests[0][1]["query"]
    assert "claim_id: $claim" in h.requests[0][1]["query"] and "returning" in h.requests[0][1]["query"]
    assert h.requests[1][1]["variables"]["issuer"] == "UBND 100\\%\\_x"
    assert h.requests[2][1]["variables"]["doc"] == {"document_id": "doc-1"}
    assert (h.requests[3][1]["variables"]["claim"], h.requests[3][1]["variables"]["bump"]) == ("c-2", 0)


@pytest.mark.parametrize("affected", [1, 0])
def test_row_writes_hold_only_with_the_claim_id(affected):
    # lưu tiến độ, ghi kết quả, thả dòng: điều kiện có claim_id — vòng đã mất dòng nhận về 0 dòng đổi (False)
    reply = {"data": {"update_core_import_rows": {"affected_rows": affected}}}
    h = Hasura(reply, reply, reply)
    store = h.store()
    until = datetime(2026, 10, 23, 1, 5, tzinfo=UTC)
    assert run(store.progress(JOB, 7, {"file_ids": ["f1"]}, until=until, claim_id="c-1")) is bool(affected)
    assert run(store.finish(JOB, 7, {"status": "ok"}, claim_id="c-1")) is bool(affected)
    run(store.release(JOB, 7, claim_id="c-1"))
    for _, body in h.requests:
        assert body["variables"]["claim"] == "c-1" and "claim_id: {_eq: $claim}" in body["query"]


@pytest.mark.parametrize("affected", [1, 0])
def test_close_only_changes_an_open_job_and_leaves_the_audit_entry_to_the_trigger(affected):
    h = Hasura({"data": {"update_core_import_jobs": {"affected_rows": affected}}})
    assert run(h.store().close(JOB, {"status": "done"})) is bool(affected)
    ((_, body),) = h.requests
    assert 'status: {_neq: "done"}' in body["query"] and "audit" not in body["query"]
    assert body["variables"] == {"id": JOB["id"], "set": {"status": "done"}}


def test_drop_files_uses_the_admin_secret_with_strict_conditions_and_keeps_personal_files():
    kept = "11111111-0000-4000-8000-000000000001"
    gone = "22222222-0000-4000-8000-000000000002"
    h = Hasura({"data": {"personal_items": [{"file_id": kept}]}},
               {"data": {"delete_core_files": {"returning": [{"id": gone, "object_key": "tenant/a/x"}]}}})
    out = run(h.store().drop_files(JOB, 4, [kept, gone]))
    assert out == [{"id": gone, "object_key": "tenant/a/x"}]
    for headers, _ in h.requests:
        # vai trò service không xóa được core.files: khóa quản trị không vai trò, người trong sổ là svc-files:import
        assert headers["x-hasura-admin-secret"] == "bi-mat" and "x-hasura-role" not in headers
        assert headers["x-hasura-user-id"] == "svc-files:import" and headers["x-hasura-request-id"] == f"{JOB['id']}:4"
    (_, ask), (_, drop) = h.requests
    assert ask["variables"] == {"ids": [kept, gone]}
    assert drop["variables"] == {"ids": [gone], "tenant": str(TENANT), "user": "u-van-thu"}
    for cond in ("tenant_id: {_eq: $tenant}", "created_by: {_eq: $user}", "_not: {document_files: {}}"):
        assert cond in drop["query"]
    # mọi tệp đều đã đặt vào không gian cá nhân: không gọi câu xóa
    h = Hasura({"data": {"personal_items": [{"file_id": kept}]}})
    assert run(h.store().drop_files(JOB, 4, [kept])) == [] and len(h.requests) == 1


def test_view_uses_the_snapshot_once_done():
    running = {"status": "running", "ok": 0, "duplicate": 0, "failed": 0, "options": {"register": True},
               "pending_rows": {"aggregate": {"count": 2}}, "ok_rows": {"aggregate": {"count": 3}},
               "duplicate_rows": {"aggregate": {"count": 1}}, "failed_rows": {"aggregate": {"count": 4}}}
    assert {k: view(running)[k] for k in ("pending", "ok", "duplicate", "failed", "register")} == {
        "pending": 2, "ok": 3, "duplicate": 1, "failed": 4, "register": True}
    done = {**running, "status": "done", "ok": 7, "duplicate": 2, "failed": 1, "options": {}}
    out = view(done)
    assert (out["pending"], out["ok"], out["duplicate"], out["failed"], out["register"]) == (0, 7, 2, 1, False)
    assert not any(k.endswith("_rows") for k in out)


def test_ilike_exact_escapes_wildcards():
    assert ilike_exact(r"UB_ND 10% \ x") == r"UB\_ND 10\% \\ x"
