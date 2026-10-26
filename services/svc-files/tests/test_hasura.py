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


def test_file_location_runs_as_service_and_reports_restricted_documents():
    rec = Recorder((200, {"data": {"core_files_by_pk": {
        "object_key": f"tenant/{TENANT}/2026/10/{FILE}", "wrapped_dek": None,
        "restricted_links": [{"document_id": str(uuid.uuid4())}]}}}))
    loc = run(client(rec).file_location(tenant_id=TENANT, actor_id="u-van-thu", request_id="req-1", file_id=FILE))
    headers, body = rec.last
    assert headers["x-hasura-role"] == "service" and headers["x-hasura-tenant-id"] == str(TENANT)
    # chỉ lấy liên kết tới văn bản đang hạn chế, một dòng là đủ
    assert "document_files(where: {document: {restricted: {_eq: true}}}, limit: 1)" in body["query"]
    assert loc.restricted is True and loc.wrapped_dek is None and loc.object_key.endswith(str(FILE))
    rec.reply = (200, {"data": {"core_files_by_pk": {"object_key": "k", "wrapped_dek": None, "restricted_links": []}}})
    loc = run(client(rec).file_location(tenant_id=TENANT, actor_id="u", request_id="r", file_id=FILE))
    assert loc.restricted is False


@pytest.mark.parametrize("reply", [
    httpx2.ConnectError("không nối được"),
    (500, {"error": "lỗi máy chủ"}),
    (200, {"errors": [{"message": "database query error", "extensions": {"code": "unexpected"}}]}),
])
def test_other_failures_raise_hasura_error(reply):
    with pytest.raises(HasuraError) as exc:
        run(client(Recorder(reply)).file_location(tenant_id=TENANT, actor_id="u", request_id="r", file_id=FILE))
    assert not isinstance(exc.value, HasuraAuthError)


def test_action_errors_keep_their_field_errors():
    rec = Recorder((200, {"errors": [{"message": "Dữ liệu văn bản đến chưa hợp lệ", "extensions": {
        "code": "invalid", "fields": {"summary": "minLength", "issued_on": "format"}}}]}))
    with pytest.raises(HasuraError) as exc:
        run(client(rec).as_role("service", TENANT, "u", "r", "query { x }", {}))
    assert exc.value.code == "invalid" and exc.value.fields == {"summary": "minLength", "issued_on": "format"}
    rec = Recorder((200, {"errors": [{"message": "x", "extensions": {"code": "invalid", "fields": ["summary"]}}]}))
    with pytest.raises(HasuraError) as exc:
        run(client(rec).as_role("service", TENANT, "u", "r", "query { x }", {}))
    assert exc.value.fields is None         # không phải object trường → mã: bỏ


def test_act_as_plays_the_user_with_admin_secret_and_a_longer_timeout():
    rec = Recorder((200, {"data": {"receiveIncoming": {"document_id": str(FILE)}}}))
    out = run(client(rec).act_as(role="clerk", tenant_id=TENANT, user_id="u-van-thu", department_id="phong-1",
                                 request_id="lo-1:7", query="mutation { receiveIncoming }", variables={"d": {"a": 1}}))
    assert out == {"receiveIncoming": {"document_id": str(FILE)}}
    headers, body = rec.last
    assert headers["x-hasura-admin-secret"] == "bi-mat" and headers["x-hasura-role"] == "clerk"
    assert headers["x-hasura-tenant-id"] == str(TENANT) and headers["x-hasura-user-id"] == "u-van-thu"
    assert headers["x-hasura-department-id"] == "phong-1"
    assert headers["x-hasura-request-id"] == "lo-1:7" and headers["x-request-id"] == "lo-1:7"
    assert body["variables"] == {"d": {"a": 1}}
    # dài hơn hạn 30 giây Hasura chờ Action (actions.yaml), dài hơn HASURA_TIMEOUT_S của các câu khác
    assert rec.requests[-1].extensions["timeout"] == {"connect": 35.0, "read": 35.0, "write": 35.0, "pool": 35.0}
    run(client(rec).act_as(role="clerk", tenant_id=TENANT, user_id="u", department_id=None, request_id="r",
                           query="q", variables={}, timeout_s=5))
    headers, _ = rec.last
    assert "x-hasura-department-id" not in headers
    assert rec.requests[-1].extensions["timeout"]["read"] == 5


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


# --- lớp chữ và trợ lý hỏi đáp (F2.7, F4.2) -----------------------------------------------------------------------


def test_pending_texts_include_issued_files():
    rec = Recorder((200, {"data": {"core_files": []}}))
    run(client(rec).pending_texts(5))
    _, body = rec.last
    assert '{document_files: {role: {_in: ["main", "attachment", "issued"]}}}' in body["query"]


def test_pending_texts_never_include_files_of_restricted_documents():
    # hàng đợi duy nhất của vòng đọc chữ, kể cả OCR bản scan (#253): tệp mã hóa, tệp của văn bản hạn chế không vào
    rec = Recorder((200, {"data": {"core_files": []}}))
    run(client(rec).pending_texts(5))
    query = " ".join(rec.last[1]["query"].split())
    assert "{encrypted: {_eq: false}}" in query
    assert "{_not: {document_files: {document: {restricted: {_eq: true}}}}}" in query


def test_save_text_sends_page_starts_as_a_json_array():
    rec = Recorder((200, {"data": {"insert_core_file_texts_one": {"file_id": str(FILE)}}}))
    run(client(rec).save_text(file_id=str(FILE), tenant_id=str(TENANT), status="ok", pages=2, content="ab\ncd",
                              note=None, page_starts=[0, 3]))
    headers, body = rec.last
    assert headers["x-hasura-admin-secret"] == "bi-mat" and "x-hasura-role" not in headers
    assert body["variables"]["o"]["page_starts"] == [0, 3]
    run(client(rec).save_text(file_id=str(FILE), tenant_id=str(TENANT), status="empty", pages=1, content="",
                              note=None))
    assert rec.last[1]["variables"]["o"]["page_starts"] is None


def test_chunk_sources_reads_every_tenant_with_admin_secret():
    rec = Recorder((200, {"data": {"office_documents": [{"id": "d-1"}]}}))
    rows = run(client(rec).chunk_sources(datetime(2026, 10, 21, tzinfo=UTC), 20, str(uuid.UUID(int=0))))
    headers, body = rec.last
    assert rows == [{"id": "d-1"}]
    assert headers["x-hasura-admin-secret"] == "bi-mat" and "x-hasura-role" not in headers
    assert body["variables"] == {"since": "2026-10-21T00:00:00+00:00", "limit": 20, "after": str(uuid.UUID(int=0))}
    query = body["query"]
    assert "{assignments: {assigned_at: {_gte: $since}}}" in query          # giao việc mới cũng là thay đổi
    assert 'assignments(where: {status: {_neq: "cancelled"}})' in query
    assert "page_starts" in query and "restricted" in query and "encrypted" in query


def test_ask_documents_forwards_the_user_token():
    rec = Recorder((200, {"data": {"office_documents": [
        {"id": "d-1", "restricted": False, "document_type": {"name": "Công văn"}}]}}))
    got = run(client(rec).ask_documents("token-nguoi-hoi", ["d-1", "d-2"]))
    headers, body = rec.last
    assert headers["authorization"] == "Bearer token-nguoi-hoi" and "x-hasura-admin-secret" not in headers
    assert body["variables"] == {"ids": ["d-1", "d-2"]} and "restricted" in body["query"]
    assert list(got) == ["d-1"]


def test_ask_documents_for_a_role_without_documents_is_empty_and_rejected_token_raises():
    rec = Recorder((200, {"errors": [{"message": "field not found", "extensions": {"code": "validation-failed"}}]}))
    assert run(client(rec).ask_documents("t", ["d-1"])) == {}
    rec = Recorder((200, {"errors": [{"message": "JWTExpired", "extensions": {"code": "invalid-jwt"}}]}))
    with pytest.raises(HasuraAuthError):
        run(client(rec).ask_documents("t", ["d-1"]))


def test_ask_documents_service_runs_as_service_of_the_tenant_and_skips_restricted():
    rec = Recorder((200, {"data": {"office_documents": []}}))
    run(client(rec).ask_documents_service(TENANT, ["d-1"]))
    headers, body = rec.last
    assert headers["x-hasura-role"] == "service" and headers["x-hasura-tenant-id"] == str(TENANT)
    assert "{restricted: {_eq: false}}" in body["query"]


def test_archived_case_files_ask_with_the_user_token_and_return_hex_hashes():
    key = f"cold/{TENANT}/case/c-1/"
    rec = Recorder((200, {"data": {"office_case_files": [
        {"id": "c-1", "code": "HS-01", "archive_key": key, "archive_sha256": "\\x" + "ef" * 32},
        {"id": "c-2", "code": "HS-02", "archive_key": None, "archive_sha256": None}]}}))
    got = run(client(rec).archived_case_files("token-lanh-dao"))
    headers, body = rec.last
    assert headers["authorization"] == "Bearer token-lanh-dao" and "x-hasura-admin-secret" not in headers
    assert '{status: {_eq: "archived"}}' in body["query"]
    assert got == [{"id": "c-1", "code": "HS-01", "archive_key": key, "archive_sha256": "ef" * 32}]
    # lãnh đạo đơn vị đọc được hồ sơ: validation-failed là metadata hỏng, ra như lỗi CSDL (503), không thành kho trống
    rec = Recorder((200, {"errors": [{"message": "field not found", "extensions": {"code": "validation-failed"}}]}))
    with pytest.raises(HasuraError) as exc:
        run(client(rec).archived_case_files("t"))
    assert exc.value.code == "validation-failed" and not isinstance(exc.value, HasuraAuthError)
    rec = Recorder((200, {"errors": [{"message": "JWTExpired", "extensions": {"code": "invalid-jwt"}}]}))
    with pytest.raises(HasuraAuthError):
        run(client(rec).archived_case_files("t"))
