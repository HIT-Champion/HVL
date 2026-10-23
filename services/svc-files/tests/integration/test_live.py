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

"""Đầu-cuối: svc-files với ClamAV, SeaweedFS, Meilisearch, PostgreSQL + Hasura thật (schema và quyền từ db/).

Cách dựng ở README.md, mục "Test tích hợp". Token ký RS256 bằng khóa riêng trong tệp
MOC_IT_JWT_PRIVATE_KEY; Hasura được dựng với khóa công khai tương ứng.

    MOC_IT=1 MOC_IT_JWT_PRIVATE_KEY=… pytest -m integration
"""

import hashlib
import io
import json
import os
import struct
import time
import urllib.request
import uuid
import zipfile
import zlib

import boto3
import jwt
import pypdf
import pytest
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fastapi.testclient import TestClient

from conftest import EICAR, ISSUER, StaticKeys, text_pdf
from svc_files.app import create_app
from svc_files.auth import HASURA_CLAIMS, TokenVerifier
from svc_files.config import Settings

KEY_FILE = os.environ.get("MOC_IT_JWT_PRIVATE_KEY", "")
HASURA_URL = os.environ.get("MOC_IT_HASURA_URL", "http://127.0.0.1:18080")
ADMIN_SECRET = os.environ.get("MOC_IT_HASURA_ADMIN_SECRET", "it-admin-secret")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MOC_IT") != "1" or not KEY_FILE,
                       reason="đặt MOC_IT=1 và MOC_IT_JWT_PRIVATE_KEY để chạy test đầu-cuối với Hasura"),
]

PDF = b"%PDF-1.7\n% cong van den\n" + os.urandom(150_000)


def _post(path: str, body: dict, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(HASURA_URL + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def sql(statement: str) -> list[list[str]]:
    body = _post("/v2/query", {"type": "run_sql", "args": {"source": "default", "sql": statement}},
                 {"X-Hasura-Admin-Secret": ADMIN_SECRET})
    return body["result"][1:]


@pytest.fixture(scope="module")
def private_key():
    with open(KEY_FILE, "rb") as fh:
        return load_pem_private_key(fh.read(), password=None)


@pytest.fixture(scope="module")
def tenants() -> tuple[str, str]:
    tag = uuid.uuid4().hex[:6].upper()
    a = sql(f"insert into core.tenants (code, name) values ('FA{tag}', 'Khoa thử A') returning id")[0][0]
    b = sql(f"insert into core.tenants (code, name) values ('FB{tag}', 'Khoa thử B') returning id")[0][0]
    return a, b


@pytest.fixture(scope="module")
def token(private_key):
    def make(sub: str, role: str, tenant: str, department: str | None = None) -> str:
        now = int(time.time())
        ns = {"x-hasura-allowed-roles": [role], "x-hasura-default-role": role,
              "x-hasura-user-id": sub, "x-hasura-tenant-id": tenant}
        if department:
            ns["x-hasura-department-id"] = department
        claims = {"iss": ISSUER, "sub": sub, "iat": now, "exp": now + 600, HASURA_CLAIMS: ns}
        return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "it"})

    return make


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    return Settings.from_env({
        "MOC_OIDC_ISSUER": ISSUER,
        "MOC_OIDC_JWKS_URL": "http://unused/jwks",
        "SEAWEEDFS_S3_ACCESS_KEY": os.environ.get("SEAWEEDFS_S3_ACCESS_KEY", "it"),
        "SEAWEEDFS_S3_SECRET_KEY": os.environ.get("SEAWEEDFS_S3_SECRET_KEY", "it"),
        "SEAWEEDFS_S3_ENDPOINT": os.environ.get("SEAWEEDFS_S3_ENDPOINT", "http://127.0.0.1:18333"),
        "CLAMAV_HOST": os.environ.get("CLAMAV_HOST", "127.0.0.1"),
        "CLAMAV_PORT": os.environ.get("CLAMAV_PORT", "13310"),
        "MOC_FILES_BUCKET": "moc-files-it",
        "HASURA_URL": HASURA_URL,
        "HASURA_ADMIN_SECRET": ADMIN_SECRET,
        "MEILISEARCH_URL": os.environ.get("MOC_IT_MEILISEARCH_URL", "http://127.0.0.1:17700"),
        "MEILISEARCH_API_KEY": os.environ.get("MOC_IT_MEILISEARCH_KEY", "it-meili-master-key-0123456789"),
        "MOC_SEARCH_INDEX": f"documents-it-{uuid.uuid4().hex[:8]}",   # chỉ mục riêng cho mỗi lần chạy
        "MOC_SEARCH_SYNC_INTERVAL_S": "0",                            # test tự gọi sync_once
        "MOC_TEXT_INTERVAL_S": "0",                                   # test tự gọi run_once
    })


@pytest.fixture(scope="module")
def app_client(live_settings, private_key):
    verifier = TokenVerifier(ISSUER, "http://unused/jwks", keys=StaticKeys(private_key.public_key()))
    with TestClient(create_app(live_settings, verifier=verifier)) as c:
        yield c


def s3_client(settings: Settings):
    return boto3.client("s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region,
                        aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key)


def bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def upload(client, tok: str, name: str, data: bytes):
    return client.post("/api/files", headers=bearer(tok), files={"file": (name, data, "application/pdf")})


def gql(tok: str, query: str, variables: dict) -> dict:
    body = _post("/v1/graphql", {"query": query, "variables": variables}, bearer(tok))
    assert "errors" not in body, body
    return body["data"]


def receive(tenant: str, clerk: str, doc: dict, files: tuple[str, ...] = ()) -> str:
    """Văn bản đến kèm tệp như Action receiveIncoming ghi: vai trò service thay mặt văn thư. Stack test này
    (db/tests/stack.sh) không có svc-workflow, mà văn thư không còn quyền ghi thẳng bảng văn bản, tệp (F2.2)."""
    links = [{"file_id": f, "role": "main" if i == 0 else "attachment", "added_by": clerk} for i, f in enumerate(files)]
    body = _post("/v1/graphql", {
        "query": "mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }",
        "variables": {"o": {**doc, "direction": "in", "status": "received", "created_by": clerk,
                            "files": {"data": links}}},
    }, {"X-Hasura-Admin-Secret": ADMIN_SECRET, "X-Hasura-Role": "service", "X-Hasura-Tenant-Id": tenant,
        "X-Hasura-User-Id": clerk})
    assert "errors" not in body, body
    return body["data"]["insert_office_documents_one"]["id"]


def test_ready_with_hasura(app_client):
    r = app_client.get("/readyz")
    assert r.status_code == 200, r.text
    assert r.json()["hasura"] is True and r.json()["status"] == "ready"


def test_upload_is_recorded_and_owner_downloads_it(app_client, live_settings, tenants, token):
    clerk = token("van-thu-a", "clerk", tenants[0])
    r = upload(app_client, clerk, "Công văn đến số 45.pdf", PDF)
    assert r.status_code == 201, r.text
    file_id = r.json()["id"]

    digest = hashlib.sha256(PDF).hexdigest()
    row = sql(f"""select tenant_id, created_by, filename, encode(sha256, 'hex'), object_key
                  from core.files where id = '{file_id}'""")
    assert row[0][:4] == [tenants[0], "van-thu-a", "Công văn đến số 45.pdf", digest]

    obj = s3_client(live_settings).get_object(Bucket=live_settings.bucket, Key=row[0][4])
    assert obj["Body"].read() == PDF
    assert obj["Metadata"]["sha256"] == digest
    assert obj["ContentType"] == "application/pdf"

    got = app_client.get(f"/api/files/{file_id}", headers=bearer(clerk))
    assert got.status_code == 200, got.text
    assert got.content == PDF
    assert "Cong van den so 45.pdf" in got.headers["content-disposition"]


def test_director_sees_file_once_attached_to_a_document(app_client, tenants, token):
    clerk = token("van-thu-a", "clerk", tenants[0])
    director = token("hieu-truong-a", "director", tenants[0])
    file_id = upload(app_client, clerk, "Giấy mời họp.pdf", PDF).json()["id"]
    assert app_client.get(f"/api/files/{file_id}", headers=bearer(director)).status_code == 404

    receive(tenants[0], "van-thu-a", {"type_code": "GM", "symbol": f"{uuid.uuid4().hex[:4]}/GM-SGD",
                                      "issuer_name": "Sở GD&ĐT", "issued_on": "2026-10-16",
                                      "summary": "Mời dự họp triển khai nhiệm vụ năm học"}, files=(file_id,))

    got = app_client.get(f"/api/files/{file_id}", headers=bearer(director))
    assert got.status_code == 200 and got.content == PDF


def test_other_tenant_and_tenant_admin_get_404(app_client, tenants, token):
    file_id = upload(app_client, token("van-thu-a", "clerk", tenants[0]), "a.pdf", PDF).json()["id"]
    for tok in (token("van-thu-b", "clerk", tenants[1]), token("quan-tri-a", "tenant_admin", tenants[0])):
        assert app_client.get(f"/api/files/{file_id}", headers=bearer(tok)).status_code == 404


def test_eicar_is_blocked_and_chained_into_audit_log(app_client, tenants, token):
    r = upload(app_client, token("van-thu-a", "clerk", tenants[0]), "hoa-don.pdf", EICAR)
    assert r.status_code == 422, r.text
    rows = sql(f"""select tenant_id, actor_id, diff ->> 'signature' from core.audit_log
                   where action = 'file.rejected' and entity_id = '{hashlib.sha256(EICAR).hexdigest()}'
                     and tenant_id = '{tenants[0]}'""")
    assert len(rows) == 1
    assert rows[0][1] == "van-thu-a" and "Eicar" in rows[0][2]
    assert sql("select * from core.audit_verify()") == []


def _crc_table() -> list[int]:
    table = []
    for n in range(256):
        for _ in range(8):
            n = (n >> 1) ^ 0xEDB88320 if n & 1 else n >> 1
        table.append(n)
    return table


CRC = _crc_table()


def zip_with_password(name: str, data: bytes, password: bytes) -> bytes:
    """Zip một tệp có mật khẩu, mã hóa ZipCrypto như phần lớn công cụ nén — zipfile đọc được kiểu này, không ghi được."""
    keys = [0x12345678, 0x23456789, 0x34567890]

    def update(c: int) -> None:
        keys[0] = (keys[0] >> 8) ^ CRC[(keys[0] ^ c) & 0xFF]
        keys[1] = ((keys[1] + (keys[0] & 0xFF)) * 134775813 + 1) & 0xFFFFFFFF
        keys[2] = (keys[2] >> 8) ^ CRC[(keys[2] ^ (keys[1] >> 24)) & 0xFF]

    def encrypt(plain: bytes) -> bytes:
        out = bytearray()
        for c in plain:
            t = (keys[2] | 2) & 0xFFFF
            out.append(c ^ (((t * (t ^ 1)) >> 8) & 0xFF))
            update(c)
        return bytes(out)

    for c in password:
        update(c)
    crc = zlib.crc32(data)
    body = encrypt(os.urandom(11) + bytes([crc >> 24]) + data)        # 12 byte đầu ZipCrypto, rồi tệp (không nén)
    fname = name.encode()
    local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 1, 0, 0, 0, crc, len(body), len(data), len(fname), 0)
    central = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 1, 0, 0, 0, crc, len(body), len(data),
                          len(fname), 0, 0, 0, 0, 0, 0)
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(central) + len(fname), len(local) + len(fname) + len(body), 0)
    return local + fname + body + central + fname + end


def locked_pdf(user_password: str, owner_password: str) -> bytes:
    writer = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(text_pdf("Bang diem hoc ky 1"))))
    writer.encrypt(user_password=user_password, owner_password=owner_password, algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def nested_zip(depth: int) -> bytes:
    data = text_pdf("Bao cao tong ket")
    for level in range(depth):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"lop-{level}.zip" if level else "bao-cao.pdf", data)
        data = buf.getvalue()
    return data


def test_files_the_scanner_cannot_open_are_blocked(app_client, tenants, token):
    """ClamAV có AlertEncrypted, AlertExceedsMax (như docker-compose.yml): tệp có mật khẩu, lồng quá sâu bị chặn."""
    clerk = token("van-thu-a", "clerk", tenants[0])
    secret = zip_with_password("bang-diem.pdf", text_pdf("Bang diem"), b"mk2026")
    assert zipfile.ZipFile(io.BytesIO(secret)).read("bang-diem.pdf", pwd=b"mk2026").startswith(b"%PDF")
    cases = {
        "bang-diem.zip": (secret, "Heuristics.Encrypted.Zip"),
        "bang-diem.pdf": (locked_pdf("mk2026", "chu-so-huu"), "Heuristics.Encrypted.PDF"),
        "nen-nhieu-lop.zip": (nested_zip(25), "Heuristics.Limits.Exceeded"),
    }
    for name, (data, prefix) in cases.items():
        r = upload(app_client, clerk, name, data)
        assert r.status_code == 422, (name, r.text)
        detail = r.json()["detail"]
        assert detail["code"] == "unscannable" and detail["signature"].startswith(prefix), (name, detail)
        (row,) = sql(f"""select diff ->> 'signature' from core.audit_log where action = 'file.rejected'
                         and entity_id = '{hashlib.sha256(data).hexdigest()}' and tenant_id = '{tenants[0]}'""")
        assert row[0] == detail["signature"]
    # PDF chỉ khóa quyền sửa, in (không cần mật khẩu để mở — kiểu văn bản cơ quan hay gửi): vẫn quét được, nhận
    r = upload(app_client, clerk, "quyet-dinh.pdf", locked_pdf("", "chu-so-huu"))
    assert r.status_code == 201, r.text
    r = upload(app_client, clerk, "bao-cao.zip", nested_zip(3))
    assert r.status_code == 201, r.text


def test_unknown_tenant_is_refused_and_leaves_no_object(app_client, live_settings, token):
    ghost = str(uuid.uuid4())
    r = upload(app_client, token("ai-do", "clerk", ghost), "a.pdf", PDF)
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "unknown_tenant"
    listed = s3_client(live_settings).list_objects_v2(Bucket=live_settings.bucket, Prefix=f"tenant/{ghost}/")
    assert listed.get("KeyCount", 0) == 0


# --- tìm kiếm ------------------------------------------------------------------------------------


def sync_index(client) -> None:
    indexer = client.app.state.indexer
    client.portal.call(indexer.sync_once)
    client.portal.call(client.app.state.meili.wait, indexer.last_task)


def found(client, tok: str, q: str, **params) -> list[str]:
    r = client.get("/api/search", headers=bearer(tok), params={"q": q, **params})
    assert r.status_code == 200, r.text
    return [h["id"] for h in r.json()["hits"]]


def test_search_respects_tenant_and_role(app_client, tenants, token):
    a, b = tenants
    tag = uuid.uuid4().hex[:6]
    dept_1 = sql(f"insert into office.departments (tenant_id, code, name) values ('{a}', 'P1{tag}', 'Phòng 1') returning id")[0][0]
    dept_2 = sql(f"insert into office.departments (tenant_id, code, name) values ('{a}', 'P2{tag}', 'Phòng 2') returning id")[0][0]
    clerk_a = token("van-thu-a", "clerk", a)
    director_a = token("hieu-truong-a", "director", a)
    staff_1 = token("chuyen-vien-1", "staff", a, dept_1)
    staff_2 = token("chuyen-vien-2", "staff", a, dept_2)
    admin_a = token("quan-tri-a", "tenant_admin", a)
    clerk_b = token("van-thu-b", "clerk", b)

    insert = """mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }"""
    incoming = receive(a, "van-thu-a", {
        "type_code": "CV", "symbol": f"45/UBND-{tag}", "issuer_name": "Ủy ban nhân dân tỉnh Hưng Yên",
        "issued_on": "2026-10-15", "summary": "Về việc tuyển sinh đại học chính quy năm 2026"})
    draft = gql(staff_1, insert, {"o": {
        "type_code": "KH", "summary": "Dự thảo kế hoạch tuyển sinh sau đại học"}})["insert_office_documents_one"]["id"]
    other = receive(b, "van-thu-b", {
        "type_code": "CV", "symbol": f"46/UBND-{tag}", "issuer_name": "Ủy ban nhân dân tỉnh Hưng Yên",
        "issued_on": "2026-10-15", "summary": "Về việc tuyển sinh đại học chính quy năm 2026"})
    sync_index(app_client)

    assert set(found(app_client, director_a, "tuyen sinh")) == {incoming, draft}   # gõ không dấu
    assert found(app_client, clerk_b, "tuyển sinh") == [other]
    assert found(app_client, staff_1, "tuyen sinh") == [draft]
    assert found(app_client, staff_2, "tuyen sinh") == []
    assert found(app_client, admin_a, "tuyen sinh") == []
    assert found(app_client, clerk_a, f"45/UBND-{tag}") == [incoming]               # theo số ký hiệu
    assert found(app_client, director_a, "tuyen sinh", direction="out") == [draft]


def test_search_finds_text_inside_pdfs(app_client, tenants, token):
    """F2.7: đọc lớp chữ PDF đã gắn vào văn bản (truy vấn thật của svc-files trên Hasura thật), tìm theo nội dung."""
    a, _ = tenants
    tag = uuid.uuid4().hex[:8].upper()
    clerk = token("van-thu-a", "clerk", a)
    director = token("hieu-truong-a", "director", a)

    def pdf_file(*lines: str) -> str:
        r = upload(app_client, clerk, "cong-van.pdf", text_pdf(*lines))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    main = pdf_file(f"De nghi bo sung chung chi NOIDUNG{tag}", "Han nop truoc ngay 30/11")
    secret_file = pdf_file(f"Danh sach nang luong MATKIN{tag}")
    # văn bản hạn chế chỉ gắn tệp tải lên ở chế độ hạn chế (F3.7, ràng buộc document_files_sealed); stack này không có
    # két để mã hóa thật nên chỉ đánh dấu — đủ cho điều cần kiểm ở đây: không đọc chữ tệp của văn bản hạn chế
    sql(f"update core.files set encrypted = true, wrapped_dek = 'vault:v1:thu' where id = '{secret_file}' "
        "returning id")
    loose = pdf_file(f"Tep chua gan LOOSE{tag}")
    doc = receive(a, "van-thu-a", {
        "type_code": "CV", "symbol": f"77/PDF-{tag}", "issuer_name": "Phòng Đào tạo", "issued_on": "2026-10-15",
        "summary": "Về việc rà soát danh sách sinh viên"}, (main,))
    receive(a, "van-thu-a", {
        "type_code": "CV", "symbol": f"78/PDF-{tag}", "issuer_name": "Phòng Tổ chức", "issued_on": "2026-10-15",
        "summary": "Về việc nâng lương trước hạn", "restricted": True}, (secret_file,))

    extractor = app_client.app.state.extractor
    while app_client.portal.call(extractor.run_once) == extractor.batch:
        pass
    texts = {r[0]: r[1:] for r in sql(f"""select file_id, status, content from core.file_texts
                                           where file_id in ('{main}', '{secret_file}', '{loose}')""")}
    assert texts[main][0] == "ok" and f"NOIDUNG{tag}" in texts[main][1]
    assert secret_file not in texts and loose not in texts        # văn bản hạn chế, tệp chưa gắn: không đọc chữ

    sync_index(app_client)
    r = app_client.get("/api/search", headers=bearer(director), params={"q": f"noidung{tag}"})
    assert [(h["id"], h["matched_content"]) for h in r.json()["hits"]] == [(doc, True)]
    assert found(app_client, director, "ra soat danh sach sinh vien") == [doc]
    # mọi từ phải khớp: Meilisearch thật mặc định sẽ bớt từ cuối và trả về văn bản chỉ khớp một phần
    assert found(app_client, director, f"noidung{tag} khongcotrongvanban") == []

    # không vai trò người dùng nào đọc được bảng chữ
    for tok in (clerk, director, token("quan-tri-a", "tenant_admin", a)):
        assert "errors" in _post("/v1/graphql", {"query": "{ core_file_texts { content } }"}, bearer(tok))
        body = _post("/v1/graphql", {"query": "{ core_files { text { content } } }"}, bearer(tok))
        assert "errors" in body
