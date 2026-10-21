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

"""Client Hasura: tiêu đề gửi đi đúng cho từng cách gọi, lỗi được phân loại đúng."""

import asyncio
import json
import uuid
from datetime import UTC, datetime

import httpx2
import pytest

from svc_files.hasura import HasuraAuthError, HasuraClient, HasuraError

TENANT = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000a")
FILE = uuid.UUID("3c4d0000-0000-4000-8000-000000000001")


class Recorder:
    def __init__(self, reply) -> None:
        self.reply = reply
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        status, body = self.reply
        return httpx2.Response(status, json=body)

    @property
    def last(self) -> tuple[dict[str, str], dict]:
        req = self.requests[-1]
        return {k.lower(): v for k, v in req.headers.items()}, json.loads(req.content)


def run(coro):
    return asyncio.run(coro)


def client(rec: Recorder) -> HasuraClient:
    return HasuraClient("http://hasura:8080", "bi-mat", transport=httpx2.MockTransport(rec))


def test_insert_file_runs_as_service_with_session_from_token():
    rec = Recorder((200, {"data": {"insert_core_files_one": {"id": str(FILE)}}}))
    run(client(rec).insert_file(
        tenant_id=TENANT, actor_id="u-van-thu", request_id="req-1", file_id=FILE,
        object_key=f"tenant/{TENANT}/2026/10/{FILE}", filename="Công văn.pdf", mime_type="application/pdf",
        size_bytes=10, sha256_hex="ab" * 32, scanned_at=datetime(2026, 10, 18, 2, 0, tzinfo=UTC),
    ))
    headers, body = rec.last
    assert headers["x-hasura-admin-secret"] == "bi-mat"
    assert headers["x-hasura-role"] == "service"
    assert headers["x-hasura-tenant-id"] == str(TENANT)
    assert headers["x-hasura-user-id"] == "u-van-thu"
    assert headers["x-hasura-request-id"] == "req-1"
    row = body["variables"]["o"]
    assert row["sha256"] == "\\x" + "ab" * 32
    assert "tenant_id" not in row and "created_by" not in row   # Hasura đặt từ phiên


def test_user_lookup_forwards_token_and_never_sends_admin_secret():
    rec = Recorder((200, {"data": {"core_files_by_pk": {
        "id": str(FILE), "filename": "a.pdf", "mime_type": "application/pdf", "size_bytes": 10,
        "sha256": "\\x" + "cd" * 32}}}))
    meta = run(client(rec).visible_file("token-cua-nguoi-dung", FILE))
    headers, _ = rec.last
    assert headers["authorization"] == "Bearer token-cua-nguoi-dung"
    assert "x-hasura-admin-secret" not in headers
    assert "x-hasura-role" not in headers
    assert meta.sha256 == "cd" * 32 and meta.size_bytes == 10


def test_user_lookup_returns_none_when_not_visible():
    rec = Recorder((200, {"data": {"core_files_by_pk": None}}))
    assert run(client(rec).visible_file("t", FILE)) is None


def test_role_without_file_permission_is_treated_as_not_visible():
    rec = Recorder((200, {"errors": [{"message": "field 'core_files_by_pk' not found in type: 'query_root'",
                                      "extensions": {"code": "validation-failed"}}]}))
    assert run(client(rec).visible_file("t", FILE)) is None


def test_rejected_token_raises_auth_error():
    rec = Recorder((200, {"errors": [{"message": "Could not verify JWT: JWTExpired",
                                      "extensions": {"code": "invalid-jwt"}}]}))
    with pytest.raises(HasuraAuthError):
        run(client(rec).visible_file("t", FILE))


@pytest.mark.parametrize("reply", [
    httpx2.ConnectError("không nối được"),
    (500, {"error": "lỗi máy chủ"}),
    (200, {"errors": [{"message": "database query error", "extensions": {"code": "unexpected"}}]}),
])
def test_other_failures_raise_hasura_error(reply):
    with pytest.raises(HasuraError) as exc:
        run(client(Recorder(reply)).file_location(tenant_id=TENANT, actor_id="u", request_id="r", file_id=FILE))
    assert not isinstance(exc.value, HasuraAuthError)


def test_log_event_sends_details_as_jsonb():
    rec = Recorder((200, {"data": {"insert_core_audit_log": {"affected_rows": 1}}}))
    run(client(rec).log_event(tenant_id=TENANT, actor_id="u-1", request_id="r-1", action="file.rejected",
                              entity="core.files", entity_id="ab" * 32, details={"signature": "Eicar"}))
    headers, body = rec.last
    assert headers["x-hasura-role"] == "service"
    assert body["variables"]["o"]["diff"] == {"signature": "Eicar"}
    assert body["variables"]["o"]["action"] == "file.rejected"
    assert body["variables"]["o"]["actor_kind"] == "user"


def test_dispatch_source_reads_with_admin_secret_and_returns_hex_hashes():
    rec = Recorder((200, {"data": {"office_dispatches_by_pk": {
        "id": "d-1", "tenant_id": str(TENANT), "to_tenant_id": "t-2", "status": "pending", "file_id": str(FILE),
        "source_sha256": "\\x" + "ab" * 32,
        "document": {"id": "doc-1", "status": "issued", "restricted": False, "content_sha256": "\\x" + "ab" * 32,
                     "files": [{"file": {"id": "f-1", "object_key": "k", "filename": "a.pdf",
                                         "mime_type": "application/pdf", "size_bytes": 10, "sha256": "\\x" + "ab" * 32,
                                         "encrypted": False, "storage_tier": "hot"}}]},
    }}}))
    row = run(client(rec).dispatch_source(uuid.uuid4()))
    headers, _ = rec.last
    assert headers["x-hasura-admin-secret"] == "bi-mat" and "x-hasura-role" not in headers
    assert row["source_sha256"] == row["document"]["content_sha256"] == row["document"]["issued"][0]["sha256"] \
        == "ab" * 32
    assert "files" not in row["document"]


def test_ping():
    assert run(client(Recorder((200, {}))).ping()) is True
    assert run(client(Recorder(httpx2.ConnectError("x"))).ping()) is False
