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

import hashlib
import uuid

import pytest

from conftest import TENANT_A
from svc_files.app import content_disposition

PDF = b"%PDF-1.7\n% quyet dinh\n" + bytes(range(256)) * 600  # > 1 khúc 64 KB


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def upload(client, token: str, name: str = "Quyết định số 12/QĐ-ĐHCN.pdf", data: bytes = PDF) -> str:
    r = client.post("/api/files", headers=auth(token), files={"file": (name, data, "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_uploader_downloads_own_file(client, make_token):
    token = make_token(sub="u-van-thu")
    file_id = upload(client, token)
    r = client.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-length"] == str(len(PDF))
    assert r.headers["etag"] == f'"{hashlib.sha256(PDF).hexdigest()}"'
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["content-disposition"].startswith("attachment;")


def test_other_user_gets_404_until_file_is_shared(client, make_token, hasura):
    file_id = upload(client, make_token(sub="u-van-thu"))
    other = make_token(sub="u-hieu-truong")
    r = client.get(f"/api/files/{file_id}", headers=auth(other))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"

    hasura.shared.add(uuid.UUID(file_id))          # vd tệp được gắn vào văn bản người kia được đọc
    assert client.get(f"/api/files/{file_id}", headers=auth(other)).status_code == 200


def test_other_tenant_gets_404(client, make_token, hasura):
    file_id = upload(client, make_token())
    hasura.shared.add(uuid.UUID(file_id))
    stranger = make_token(sub="u-khac", tenant=str(uuid.uuid4()))
    assert client.get(f"/api/files/{file_id}", headers=auth(stranger)).status_code == 404


def test_unknown_file_is_404(client, make_token):
    assert client.get(f"/api/files/{uuid.uuid4()}", headers=auth(make_token())).status_code == 404


def test_download_needs_token(client, make_token):
    file_id = upload(client, make_token())
    r = client.get(f"/api/files/{file_id}")
    assert r.status_code == 401


def test_token_rejected_by_hasura_is_401(client, make_token, hasura):
    token = make_token()
    file_id = upload(client, token)
    hasura.reject_tokens = True
    r = client.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_database_down_is_503(client, make_token, hasura):
    token = make_token()
    file_id = upload(client, token)
    hasura.down = True
    assert client.get(f"/api/files/{file_id}", headers=auth(token)).status_code == 503


def test_missing_object_is_503_not_partial_content(client, make_token, store):
    token = make_token()
    file_id = upload(client, token)
    store.objects.clear()
    r = client.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "storage_unavailable"


def test_lookup_uses_token_tenant_not_request_data(client, make_token, hasura):
    """Vị trí tệp luôn tra theo thuê ước trong token đã kiểm, không theo tham số client gửi."""
    file_id = upload(client, make_token())
    row = hasura.files[uuid.UUID(file_id)]
    assert row["tenant_id"] == TENANT_A
    r = client.get(f"/api/files/{file_id}?tenant_id={uuid.uuid4()}", headers=auth(make_token()))
    assert r.status_code == 200


@pytest.mark.parametrize(
    ("name", "ascii_part", "utf8_part"),
    [
        ("Quyết định số 12.pdf", 'filename="Quyet dinh so 12.pdf"', "filename*=UTF-8''Quy%E1%BA%BFt%20%C4%91%E1%BB%8Bnh"),
        ('a"b\\c.pdf', 'filename="abc.pdf"', "filename*=UTF-8''a%22b%5Cc.pdf"),
        ("Đơn.docx", 'filename="Don.docx"', "filename*=UTF-8''%C4%90%C6%A1n.docx"),
        ("文件.pdf", 'filename=".pdf"', "filename*=UTF-8''%E6%96%87%E4%BB%B6.pdf"),
        # tên có ; = ' (WAF cho qua, F3.15): phần UTF-8 mã hóa hết, không tách được tiêu đề
        ("a;b=c'd.pdf", "filename=\"a;b=c'd.pdf\"", "filename*=UTF-8''a%3Bb%3Dc%27d.pdf"),
    ],
)
def test_content_disposition(name, ascii_part, utf8_part):
    header = content_disposition(name)
    assert header.startswith("attachment; ")
    assert ascii_part in header
    assert utf8_part in header
    assert "\n" not in header and "\r" not in header
