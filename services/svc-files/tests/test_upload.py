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

import hashlib
import re
import uuid

import pytest

from conftest import EICAR, LOCKED_ZIP, TENANT_A
from svc_files.app import clean_filename, clean_mime

PDF = b"%PDF-1.7\n% cong van mau\n" + b"x" * 1000


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_clean_file_is_scanned_stored_and_recorded(client, make_token, scanner, store, hasura):
    r = client.post(
        "/api/files",
        headers={**auth(make_token(sub="u-van-thu")), "X-Request-Id": "req-123"},
        files={"file": ("Công văn 123.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert body["size_bytes"] == len(PDF)
    assert body["filename"] == "Công văn 123.pdf"
    assert body["mime_type"] == "application/pdf"
    assert "object_key" not in body
    assert scanner.scanned == PDF

    (key,) = store.objects
    assert re.fullmatch(rf"tenant/{TENANT_A}/\d{{4}}/\d{{2}}/{body['id']}", key)
    assert store.objects[key]["data"] == PDF
    assert store.objects[key]["sha256"] == body["sha256"]

    row = hasura.files[uuid.UUID(body["id"])]
    assert row["tenant_id"] == TENANT_A
    assert row["created_by"] == "u-van-thu"
    assert row["request_id"] == "req-123"
    assert row["object_key"] == key
    assert row["sha256_hex"] == body["sha256"]
    assert r.headers["X-Request-Id"] == "req-123"


def test_database_down_removes_stored_object(client, make_token, store, hasura):
    hasura.down = True
    r = client.post("/api/files", headers=auth(make_token()), files={"file": ("a.pdf", PDF)})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "database_unavailable"
    assert store.objects == {} and len(store.deleted) == 1


def test_unknown_tenant_is_reported_as_such(client, make_token, store, hasura):
    hasura.fail_code = "constraint-violation"
    r = client.post("/api/files", headers=auth(make_token()), files={"file": ("a.pdf", PDF)})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_tenant"
    assert store.objects == {}


def test_infected_file_is_rejected_and_audited(client, make_token, store, hasura):
    r = client.post("/api/files", headers=auth(make_token(sub="u-1")), files={"file": ("hoa-don.pdf.exe", EICAR)})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "infected"
    assert r.json()["detail"]["signature"] == "Eicar-Test-Signature"
    assert store.objects == {} and hasura.files == {}

    (event,) = hasura.events
    assert event["action"] == "file.rejected"
    assert event["tenant_id"] == TENANT_A and event["actor_id"] == "u-1"
    assert event["entity_id"] == hashlib.sha256(EICAR).hexdigest()
    assert event["details"]["filename"] == "hoa-don.pdf.exe"
    assert event["details"]["signature"] == "Eicar-Test-Signature"


def test_password_protected_file_is_blocked_as_unscannable(client, make_token, store, hasura):
    data = LOCKED_ZIP + b"\x00" * 64
    r = client.post("/api/files", headers=auth(make_token(sub="u-1")), files={"file": ("bang-diem.zip", data)})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "unscannable" and detail["signature"] == "Heuristics.Encrypted.Zip"
    assert "mật khẩu" in detail["message"]
    assert store.objects == {} and hasura.files == {}
    (event,) = hasura.events                       # vẫn là một lần chặn ở cửa ngõ, có trong sổ kiểm toán
    assert event["action"] == "file.rejected" and event["details"]["signature"] == "Heuristics.Encrypted.Zip"


def test_infected_file_is_still_blocked_when_audit_fails(client, make_token, store, hasura):
    hasura.down = True
    r = client.post("/api/files", headers=auth(make_token()), files={"file": ("eicar.com", EICAR)})
    assert r.status_code == 422
    assert store.objects == {}


def test_scanner_down_means_nothing_is_stored(client, make_token, scanner, store):
    scanner.down = True
    r = client.post("/api/files", headers=auth(make_token()), files={"file": ("a.pdf", PDF)})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "scanner_unavailable"
    assert store.objects == {}


def test_missing_token_is_rejected_before_reading_body(client, scanner, store):
    r = client.post("/api/files", files={"file": ("a.pdf", PDF)})
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert scanner.scanned == b"" and store.objects == {}


def test_token_without_tenant_is_forbidden(client, make_token):
    r = client.post("/api/files", headers=auth(make_token(tenant=None)), files={"file": ("a.pdf", PDF)})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "no_tenant"


def test_expired_token_is_rejected(client, make_token):
    r = client.post("/api/files", headers=auth(make_token(ttl=-3600)), files={"file": ("a.pdf", PDF)})
    assert r.status_code == 401


def test_too_large_file_is_rejected(client, make_token, store):
    big = b"0" * (1024 * 1024 + 1)  # giới hạn trong test là 1 MB
    r = client.post("/api/files", headers=auth(make_token()), files={"file": ("big.bin", big)})
    assert r.status_code == 413
    assert store.objects == {}


def test_empty_file_is_rejected(client, make_token, store):
    r = client.post("/api/files", headers=auth(make_token()), files={"file": ("rong.pdf", b"")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "empty_file"


def test_missing_file_field(client, make_token):
    r = client.post("/api/files", headers=auth(make_token()), data={"note": "không có tệp"})
    assert r.status_code == 400


def test_readyz(client, scanner, hasura):
    assert client.get("/readyz").status_code == 200
    scanner.down = True
    r = client.get("/readyz")
    assert r.status_code == 503 and r.json()["clamav"] is False
    scanner.down, hasura.down = False, True
    r = client.get("/readyz")
    assert r.status_code == 503 and r.json()["hasura"] is False


def test_readyz_search_down_is_degraded_not_unready(client, meili):
    meili.down = True
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded" and r.json()["search"] is False


def test_openapi_documents_upload_body(client):
    op = client.get("/openapi.json").json()["paths"]["/api/files"]["post"]
    assert "multipart/form-data" in op["requestBody"]["content"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\vt\\Báo cáo.docx", "Báo cáo.docx"),
        ("Co\u0302ng va\u0306n.pdf", "Công văn.pdf"),  # NFD (macOS) -> NFC
        ("a\x00b\x1fc.pdf", "abc.pdf"),
        ("..", "tep-khong-ten"),
        (None, "tep-khong-ten"),
        ("x" * 300, "x" * 255),
    ],
)
def test_clean_filename(raw, expected):
    assert clean_filename(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("application/pdf", "application/pdf"),
        ("Text/Plain; charset=utf-8", "text/plain"),
        ("", "application/octet-stream"),
        ("<script>", "application/octet-stream"),
    ],
)
def test_clean_mime(raw, expected):
    assert clean_mime(raw) == expected
