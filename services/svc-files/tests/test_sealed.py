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

"""Văn bản hạn chế (F3.7): tệp lưu mã hóa, giải mã trong bộ nhớ, bản xem có dấu tên người xem, mỗi lần mở vào sổ."""

import asyncio
import base64
import dataclasses
import functools
import hashlib
import io
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx2
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from conftest import EICAR, TENANT_A, text_pdf
from svc_files import sealed
from svc_files.app import create_app
from svc_files.config import ConfigError
from svc_files.sealed import SealError, Vault, VaultError

SECRET = text_pdf("NOI DUNG HAN CHE so 7", pages=2)
VIEWER = {"name": "Nguyễn Văn An", "preferred_username": "vanthu"}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def upload(client, token, data: bytes = SECRET, *, name: str = "Công văn mật.pdf", mime: str = "application/pdf",
           restricted: bool = True):
    return client.post("/api/files" + ("?restricted=true" if restricted else ""), headers=auth(token),
                       files={"file": (name, data, mime)})


def page_text(pdf: bytes) -> list[str]:
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages]


# --- mã hóa ----------------------------------------------------------------------------------------------------------

def test_seal_roundtrip_is_bound_to_tenant_and_file():
    key, tenant, file_id = b"k" * 32, uuid.uuid4(), uuid.uuid4()
    blob = sealed.seal(SECRET, key, tenant, file_id)
    assert blob.startswith(b"MOC1") and b"NOI DUNG" not in blob and b"%PDF" not in blob
    assert sealed.unseal(blob, key, tenant, file_id) == SECRET
    assert sealed.seal(SECRET, key, tenant, file_id) != blob          # nonce mới mỗi lần
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    for bad in ((blob, key, tenant, uuid.uuid4()), (blob, key, uuid.uuid4(), file_id), (blob, b"x" * 32, tenant, file_id),
                (tampered, key, tenant, file_id), (SECRET, key, tenant, file_id), (blob, b"short", tenant, file_id)):
        with pytest.raises(SealError):
            sealed.unseal(*bad)


def test_check_pdf_accepts_readable_unlocked_pdfs_only():
    assert sealed.check_pdf(SECRET) == 2
    locked = io.BytesIO()
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(SECRET)))
    writer.encrypt("mat-khau")
    writer.write(locked)
    for bad in (b"MZ\x90\x00 khong phai pdf", b"%PDF-1.7 hong", locked.getvalue(), text_pdf("x", pages=0)):
        with pytest.raises(SealError):
            sealed.check_pdf(bad)


def test_watermark_stamps_every_page_with_viewer_and_time():
    a5_landscape = PdfWriter(clone_from=PdfReader(io.BytesIO(SECRET)))
    a5_landscape.pages[1].mediabox.upper_right = (595, 420)
    src = io.BytesIO()
    a5_landscape.write(src)
    out = sealed.watermark(src.getvalue(), "Nguyễn Văn An (vanthu)", datetime(2026, 10, 20, 3, 15, tzinfo=UTC))
    reader = PdfReader(io.BytesIO(out))
    assert [tuple(round(float(x)) for x in p.mediabox.upper_right) for p in reader.pages] == [(595, 842), (595, 420)]
    for text in page_text(out):
        assert "NOI DUNG HAN CHE so 7" in text
        assert "Nguyễn Văn An (vanthu)" in text and "10:15 20/10/2026" in text   # giờ Việt Nam
        assert "VĂN BẢN HẠN CHẾ" in text


def test_watermark_escapes_the_viewer_name():
    out = sealed.watermark(SECRET, "<b>An</b> & Bình", datetime(2026, 10, 20, tzinfo=UTC))
    assert "<b>An</b> & Bình" in page_text(out)[0]


# --- tải lên ---------------------------------------------------------------------------------------------------------

def test_restricted_upload_stores_only_ciphertext(client, make_token, hasura, store, vault):
    r = upload(client, make_token(sub="u-van-thu"))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["encrypted"] is True and out["size_bytes"] == len(SECRET)
    assert out["sha256"] == hashlib.sha256(SECRET).hexdigest()       # băm của bản rõ: kiểm lại sau khi giải mã
    (obj,) = store.objects.values()
    assert obj["data"].startswith(b"MOC1") and b"NOI DUNG" not in obj["data"] and b"%PDF" not in obj["data"]
    assert obj["content_type"] == "application/octet-stream"
    assert obj["sha256"] == hashlib.sha256(obj["data"]).hexdigest()
    row = hasura.files[uuid.UUID(out["id"])]
    assert row["wrapped_dek"] in vault.keys and row["size_bytes"] == len(SECRET)
    assert row["mime_type"] == "application/pdf"


def test_plain_upload_is_unchanged(client, make_token, store):
    r = upload(client, make_token(), restricted=False)
    assert r.status_code == 201 and r.json()["encrypted"] is False
    (obj,) = store.objects.values()
    assert obj["data"] == SECRET


# PDF phải nhập mật khẩu mới mở: ClamAV thật (AlertEncrypted) chặn trước bước này — 422 unscannable, xem
# test_upload và test tích hợp. Trạm quét giả ở đây không báo, nên check_pdf vẫn là lớp chặn sau (415)
@pytest.mark.parametrize(("data", "mime"), [
    (b"van ban thuong", "text/plain"),
    (SECRET, "image/png"),
    (b"%PDF-1.7 hong", "application/pdf"),
])
def test_restricted_upload_takes_readable_pdf_only(client, make_token, hasura, store, data, mime):
    r = upload(client, make_token(), data, mime=mime)
    assert r.status_code == 415 and r.json()["detail"]["code"] == "restricted_pdf_only"
    assert not store.objects and not hasura.files


def test_restricted_upload_is_still_scanned(client, make_token, store):
    r = upload(client, make_token(), b"%PDF-1.7 " + EICAR)
    assert r.status_code == 422 and not store.objects


def test_restricted_upload_stores_nothing_when_vault_is_down(client, make_token, hasura, store, vault):
    vault.down = True
    r = upload(client, make_token())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "vault_unavailable"
    assert not store.objects and not hasura.files


def test_restricted_upload_needs_a_configured_vault(settings, scanner, store, verifier, hasura, meili, make_token):
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili)
    with TestClient(app) as c:
        r = upload(c, make_token())
        assert r.status_code == 503 and r.json()["detail"]["code"] == "vault_unavailable"
        assert upload(c, make_token(), restricted=False).status_code == 201


# --- xem -------------------------------------------------------------------------------------------------------------

def test_viewer_gets_a_stamped_copy_and_each_view_is_audited(client, make_token, hasura, vault):
    token = make_token(sub="u-van-thu", **VIEWER)
    file_id = upload(client, token).json()["id"]
    r = client.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "no-store" and "etag" not in r.headers
    assert r.headers["content-disposition"].startswith("attachment;")
    texts = page_text(r.content)
    assert len(texts) == 2 and all("NOI DUNG HAN CHE so 7" in t and "Nguyễn Văn An (vanthu)" in t for t in texts)
    (event,) = [e for e in hasura.events if e["action"] == "file.decrypted"]
    assert event["entity"] == "core.files" and event["entity_id"] == file_id and event["actor_id"] == "u-van-thu"
    assert event["details"]["watermark"] == "Nguyễn Văn An (vanthu)"
    assert vault.unwrapped == [hasura.files[uuid.UUID(file_id)]["wrapped_dek"]]


def test_each_reader_sees_their_own_name(client, make_token, hasura):
    file_id = upload(client, make_token(sub="u-van-thu", **VIEWER)).json()["id"]
    other = make_token(sub="u-truong-khoa", name="Trần Thị Bình", preferred_username="truongkhoa")
    assert client.get(f"/api/files/{file_id}", headers=auth(other)).status_code == 404
    hasura.shared.add(uuid.UUID(file_id))                  # vd được thêm vào danh sách xem văn bản hạn chế
    r = client.get(f"/api/files/{file_id}", headers=auth(other))
    assert r.status_code == 200
    assert "Trần Thị Bình (truongkhoa)" in page_text(r.content)[0] and "Nguyễn Văn An" not in page_text(r.content)[0]


def test_viewer_without_name_claims_is_stamped_with_their_id(client, make_token):
    token = make_token(sub="u-van-thu")
    file_id = upload(client, token).json()["id"]
    assert "u-van-thu" in page_text(client.get(f"/api/files/{file_id}", headers=auth(token)).content)[0]


def test_nothing_is_returned_when_the_view_cannot_be_audited(client, make_token, hasura):
    token = make_token()
    file_id = upload(client, token).json()["id"]
    hasura.fail_events = True
    r = client.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 503 and b"NOI DUNG" not in r.content


def test_vault_down_on_read_is_503(client, make_token, vault):
    token = make_token()
    file_id = upload(client, token).json()["id"]
    vault.down = True
    r = client.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "vault_unavailable"


def test_tampered_or_swapped_ciphertext_is_refused(client, make_token, hasura, store):
    token = make_token()
    a, b = (uuid.UUID(upload(client, token).json()["id"]) for _ in range(2))
    key_a, key_b = hasura.files[a]["object_key"], hasura.files[b]["object_key"]
    # bản mã của tệp b chép đè lên chỗ của tệp a: khóa của a không mở được, và AAD (id tệp) cũng khác
    store.objects[key_a] = dict(store.objects[key_b])
    r = client.get(f"/api/files/{a}", headers=auth(token))
    assert r.status_code == 500 and r.json()["detail"]["code"] == "sealed_corrupt"
    data = store.objects[key_b]["data"]
    store.objects[key_b]["data"] = data[:-1] + bytes([data[-1] ^ 1])
    assert client.get(f"/api/files/{b}", headers=auth(token)).status_code == 500
    assert not [e for e in hasura.events if e["action"] == "file.decrypted"]


def test_encrypted_files_never_stream_ciphertext(client, make_token, hasura, store):
    """Dòng CSDL có khóa đã bọc nhưng cờ encrypted không về (vd vai trò không đọc cột): vẫn đi đường giải mã."""
    token = make_token()
    file_id = uuid.UUID(upload(client, token).json()["id"])
    original = hasura.visible_file

    async def without_flag(tok, fid):
        meta = await original(tok, fid)
        return meta and type(meta)(meta.id, meta.filename, meta.mime_type, meta.size_bytes, meta.sha256)

    hasura.visible_file = without_flag
    r = client.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and not r.content.startswith(b"MOC1")


# --- giới hạn: tiến trình con, trần số trang, chờ lượt ---------------------------------------------------------------

def app_with(settings, scanner, store, verifier, hasura, meili, vault, **changes):
    return create_app(dataclasses.replace(settings, **changes), scanner=scanner, store=store, verifier=verifier,
                      hasura=hasura, meili=meili, vault=vault)


def test_page_cap_setting(settings):
    assert settings.restricted_max_pages == 500
    with pytest.raises(ConfigError):
        dataclasses.replace(settings, restricted_max_pages=0)


def test_check_pdf_refuses_more_pages_than_the_cap():
    assert sealed.check_pdf(SECRET, max_pages=2) == 2
    with pytest.raises(SealError) as e:
        sealed.check_pdf(SECRET, max_pages=1)
    assert e.value.reason == "too_many_pages"


def test_child_process_checks_and_stamps_like_in_process():
    at = datetime(2026, 10, 20, 3, 15, tzinfo=UTC)
    assert asyncio.run(sealed.run_check_pdf(SECRET, max_pages=500)) == 2
    out = asyncio.run(sealed.run_watermark(SECRET, "Nguyễn Văn An (vanthu)", at, max_pages=500))
    assert page_text(out) == page_text(sealed.watermark(SECRET, "Nguyễn Văn An (vanthu)", at))
    assert all("NOI DUNG HAN CHE so 7" in t and "10:15 20/10/2026" in t for t in page_text(out))


@pytest.mark.parametrize(("call", "reason"), [
    (lambda: sealed.run_check_pdf(SECRET, max_pages=1), "too_many_pages"),
    (lambda: sealed.run_check_pdf(b"%PDF-1.7 hong", max_pages=500), "corrupt"),
    (lambda: sealed.run_check_pdf(SECRET, max_pages=500, timeout_s=0.001), "timeout"),
    (lambda: sealed.run_watermark(SECRET, "An", datetime.now(UTC), max_pages=1), "too_many_pages"),
    # 32 MB không đủ cho WeasyPrint: tiến trình con hết bộ nhớ, svc-files chỉ nhận một lỗi có lý do
    (lambda: sealed.run_watermark(SECRET, "An", datetime.now(UTC), max_pages=500, memory_mb=32), "memory"),
])
def test_child_failures_are_seal_errors_with_a_reason(call, reason):
    with pytest.raises(SealError) as e:
        asyncio.run(call())
    assert e.value.reason == reason and str(e.value)


def test_restricted_upload_over_the_page_cap_is_refused(settings, scanner, store, verifier, hasura, meili, vault,
                                                        make_token):
    with TestClient(app_with(settings, scanner, store, verifier, hasura, meili, vault, restricted_max_pages=1)) as c:
        r = upload(c, make_token())
    assert r.status_code == 415
    detail = r.json()["detail"]
    assert (detail["code"], detail["reason"]) == ("restricted_pdf_only", "too_many_pages")
    assert "tối đa 1 trang" in detail["message"]
    assert not store.objects and not hasura.files


def test_too_heavy_restricted_upload_is_a_clean_415(client, make_token, store, hasura, monkeypatch):
    monkeypatch.setattr("svc_files.app.run_check_pdf", functools.partial(sealed.run_check_pdf, timeout_s=0.001))
    r = upload(client, make_token())
    assert r.status_code == 415
    assert (r.json()["detail"]["code"], r.json()["detail"]["reason"]) == ("restricted_pdf_only", "timeout")
    assert not store.objects and not hasura.files


@pytest.mark.parametrize(("limits", "reason"), [({"timeout_s": 0.001}, "timeout"), ({"memory_mb": 32}, "memory")])
def test_view_that_cannot_be_stamped_is_a_clean_422(client, make_token, hasura, monkeypatch, log_records, limits,
                                                    reason):
    token = make_token()
    file_id = upload(client, token).json()["id"]
    monkeypatch.setattr("svc_files.app.run_watermark", functools.partial(sealed.run_watermark, **limits))
    r = client.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 422 and b"NOI DUNG" not in r.content
    assert (r.json()["detail"]["code"], r.json()["detail"]["reason"]) == ("unstampable", reason)
    assert not [e for e in hasura.events if e["action"] == "file.decrypted"]
    (event,) = [e for e in log_records if e["event"] == "core.file.stamp_failed"]
    assert event["file_id"] == file_id and event["reason"] == reason


def test_file_over_a_lowered_page_cap_is_not_stamped(client, settings, scanner, store, verifier, hasura, meili, vault,
                                                     make_token):
    """Tệp tải lên trước khi có trần (hoặc trước khi hạ trần): không đóng dấu, không trả bản rõ."""
    token = make_token()
    file_id = upload(client, token).json()["id"]
    with TestClient(app_with(settings, scanner, store, verifier, hasura, meili, vault, restricted_max_pages=1)) as c:
        r = c.get(f"/api/files/{file_id}", headers=auth(token))
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "too_many_pages"
    assert not [e for e in hasura.events if e["action"] == "file.decrypted"]


def test_busy_sealing_slots_answer_503_with_retry_after(client, make_token, store, monkeypatch):
    token = make_token()
    file_id = upload(client, token).json()["id"]
    entered, release = threading.Semaphore(0), threading.Event()

    async def slow_stamp(pdf, who, at, *, max_pages):
        entered.release()
        await asyncio.to_thread(release.wait, 10)
        return pdf

    monkeypatch.setattr("svc_files.app.run_watermark", slow_stamp)
    monkeypatch.setattr("svc_files.app.SEALING_QUEUE_S", 0.1)
    with ThreadPoolExecutor(2) as pool:
        views = [pool.submit(client.get, f"/api/files/{file_id}", headers=auth(token)) for _ in range(2)]
        try:
            assert entered.acquire(timeout=10) and entered.acquire(timeout=10)   # hai lượt đang đóng dấu
            r = client.get(f"/api/files/{file_id}", headers=auth(token))
            assert r.status_code == 503 and r.headers["retry-after"] == "10"
            assert r.json()["detail"]["code"] == "busy"
            before = dict(store.objects)
            r = upload(client, token)                   # kiểm lúc tải lên dùng chung hai lượt đó
            assert r.status_code == 503 and r.json()["detail"]["code"] == "busy" and store.objects == before
        finally:
            release.set()
        assert [v.result().status_code for v in views] == [200, 200]
    assert client.get(f"/api/files/{file_id}", headers=auth(token)).status_code == 200   # lượt đã trả lại


# --- phát hành văn bản đi hạn chế ------------------------------------------------------------------------------------

def test_issued_pdf_of_a_restricted_letter_is_sealed(client, hasura, store, make_token, monkeypatch):
    monkeypatch.setattr("svc_files.app.render_pdf", lambda letter: SECRET)
    doc = hasura.add_letter(TENANT_A, restricted=True)
    r = client.post("/internal/issue", headers=auth(make_token(azp="svc-workflow", tenant=None)),
                    json={"tenant_id": str(TENANT_A), "document_id": doc, "actor_id": "u-van-thu"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["sha256"] == hashlib.sha256(SECRET).hexdigest() and out["size_bytes"] == len(SECRET)
    (obj,) = store.objects.values()
    assert obj["data"].startswith(b"MOC1") and b"NOI DUNG" not in obj["data"]
    assert hasura.files[uuid.UUID(out["file_id"])]["wrapped_dek"]


# --- client két ------------------------------------------------------------------------------------------------------

class FakeBao:
    """OpenBao giả qua MockTransport: AppRole, transit datakey/decrypt; có thể thu hồi token giữa chừng."""

    def __init__(self) -> None:
        self.logins = 0
        self.valid: set[str] = set()
        self.paths: list[str] = []
        self.fail: int | None = None

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        self.paths.append(path)
        if self.fail:
            return httpx2.Response(self.fail, json={"errors": ["sealed"]})
        if path == "/v1/auth/approle/login":
            body = json.loads(request.content)
            if body != {"role_id": "role", "secret_id": "secret"}:
                return httpx2.Response(400, json={"errors": ["invalid"]})
            self.logins += 1
            token = f"t{self.logins}"
            self.valid.add(token)
            return httpx2.Response(200, json={"auth": {"client_token": token, "lease_duration": 3600}})
        if request.headers.get("x-vault-token") not in self.valid:
            return httpx2.Response(403, json={"errors": ["permission denied"]})
        if path == "/v1/transit/datakey/plaintext/moc-files":
            return httpx2.Response(200, json={"data": {"plaintext": base64.b64encode(b"k" * 32).decode(),
                                                       "ciphertext": "vault:v1:abc"}})
        if path == "/v1/transit/decrypt/moc-files":
            assert json.loads(request.content) == {"ciphertext": "vault:v1:abc"}
            return httpx2.Response(200, json={"data": {"plaintext": base64.b64encode(b"k" * 32).decode()}})
        return httpx2.Response(404)


@pytest.fixture
def creds(tmp_path):
    (tmp_path / "role_id").write_text("role\n")
    (tmp_path / "secret_id").write_text("secret\n")
    return {"role_id_file": str(tmp_path / "role_id"), "secret_id_file": str(tmp_path / "secret_id")}


def test_vault_logs_in_once_and_relogs_after_revocation(creds):
    bao = FakeBao()
    vault = Vault("http://openbao:8200", transport=httpx2.MockTransport(bao), **creds)

    async def scenario():
        assert await vault.datakey() == (b"k" * 32, "vault:v1:abc")
        assert await vault.unwrap("vault:v1:abc") == b"k" * 32
        assert bao.logins == 1                     # token dùng lại
        bao.valid.clear()                          # két khởi động lại: token cũ bị thu hồi
        assert await vault.unwrap("vault:v1:abc") == b"k" * 32
        assert bao.logins == 2
        await vault.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("fail", [503, 500])
def test_vault_errors_are_vault_errors(creds, fail):
    bao = FakeBao()
    bao.fail = fail
    vault = Vault("http://openbao:8200", transport=httpx2.MockTransport(bao), **creds)
    with pytest.raises(VaultError):
        asyncio.run(vault.datakey())


def test_vault_unreachable_or_missing_credentials(creds, tmp_path):
    def refuse(request):
        raise httpx2.ConnectError("không nối được")

    with pytest.raises(VaultError):
        asyncio.run(Vault("http://openbao:8200", transport=httpx2.MockTransport(refuse), **creds).datakey())
    with pytest.raises(VaultError):
        asyncio.run(Vault("http://openbao:8200", role_id_file=str(tmp_path / "khong-co"),
                          secret_id_file=creds["secret_id_file"], transport=httpx2.MockTransport(FakeBao())).datakey())


def test_vault_rejects_malformed_keys(creds):
    def odd(request):
        if request.url.path.endswith("/login"):
            return httpx2.Response(200, json={"auth": {"client_token": "t", "lease_duration": 60}})
        return httpx2.Response(200, json={"data": {"plaintext": base64.b64encode(b"ngan").decode(),
                                                   "ciphertext": "khong-phai-vault"}})

    with pytest.raises(VaultError):
        asyncio.run(Vault("http://openbao:8200", transport=httpx2.MockTransport(odd), **creds).datakey())
