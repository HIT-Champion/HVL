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

"""Ký số PAdES bản phát hành (F4.5, chỉ minh họa): két giả có transit (khóa RSA sinh trong test, ký PKCS#1 v1.5) và
PKI (CA sinh trong test cấp chứng thư cho CSR) — đường ký thật của pyHanko, tự kiểm, phân loại khi kiểm, CLI."""

import asyncio
import base64
import hashlib
import io
import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx2
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText

from conftest import TENANT_A, text_pdf
from svc_files import signing
from svc_files.app import create_app
from svc_files.config import Settings
from svc_files.hasura import HasuraClient
from svc_files.render import Letter, render_pdf
from svc_files.sealed import Vault, VaultError
from svc_files.signing import (
    DocumentSigner, SignatureRecord, SigningError, SigningUnavailable, key_name, signer_cn, verify_pdf,
)

TENANT_B = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")
CA_CN = "CA nội bộ Mộc - MẪU, chỉ minh họa"
SIGNER = "Khoa Công nghệ thông tin, Trường Đại học Thử"     # tên đơn vị, cơ quan chủ quản của FakeHasura.add_letter
DOC_SIGNING = x509.ObjectIdentifier("1.3.6.1.4.1.311.10.3.12")


# --- két giả: PKI và transit -------------------------------------------------------------------------------------


def _name(cn: str) -> x509.Name:
    # cryptography chặn CN quá 64 byte UTF-8: PKI giả cũng kiểm luôn rằng svc-files không xin CN dài hơn
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mộc - PKI nội bộ, chỉ minh họa"),
                      x509.NameAttribute(NameOID.COUNTRY_NAME, "VN")])


def _pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode()


class FakePki:
    """CA một tầng như ``pki/root/generate/internal``; cấp chứng thư lá như role moc-van-thu (KU, EKU, CN)."""

    def __init__(self, cn: str = CA_CN) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        self.cert = (x509.CertificateBuilder().subject_name(_name(cn)).issuer_name(_name(cn))
                     .public_key(self.key.public_key()).serial_number(x509.random_serial_number())
                     .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=3650))
                     .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                     .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False),
                                    critical=True)
                     .add_extension(x509.SubjectKeyIdentifier.from_public_key(self.key.public_key()), critical=False)
                     .sign(self.key, hashes.SHA256()))
        self.pem = _pem(self.cert)

    def issue(self, public_key, cn: str, days: int = 365) -> x509.Certificate:
        now = datetime.now(UTC)
        return (x509.CertificateBuilder().subject_name(_name(cn)).issuer_name(self.cert.subject)
                .public_key(public_key).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(seconds=30)).not_valid_after(now + timedelta(days=days))
                .add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False),
                               critical=True)
                .add_extension(x509.ExtendedKeyUsage([DOC_SIGNING]), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()),
                               critical=False)
                .sign(self.key, hashes.SHA256()))


class FakeBao:
    """Két giả trả lời đúng các đường svc-files gọi. Công tắc: pki_missing (chưa bật PKI), forbidden (policy cũ),
    down (không nối được), transit_down (chỉ transit không nối được), bad_request (transit/sign trả 400), wrong_key
    (PKI cấp chứng thư cho khóa khác), bad_signature (transit ký bằng khóa khác: chữ ký không khớp chứng thư), no_role
    (PKI dựng dở: có CA, chưa có role — pki/sign trả 400 "unknown role")."""

    def __init__(self, pki: FakePki, keys: list[rsa.RSAPrivateKey]) -> None:
        self.pki = pki
        self._pool = list(keys)
        self.keys: dict[str, dict] = {}            # tên khóa → {"versions": {v: khóa riêng}, "chains": {v: PEM}}
        self.calls: list[tuple[str, str]] = []
        self.pki_missing = self.forbidden = self.down = self.transit_down = self.bad_request = False
        self.wrong_key = self.bad_signature = self.no_role = False
        self.cert_days = 365

    def count(self, method: str, pattern: str) -> int:
        return sum(1 for m, path in self.calls if m == method and re.fullmatch(pattern, path))

    def _key_info(self, name: str) -> dict:
        k = self.keys[name]
        versions = {str(v): {"name": "rsa-3072", "certificate_chain": k["chains"].get(v, ""),
                             "public_key": priv.public_key().public_bytes(
                                 serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
                    for v, priv in k["versions"].items()}
        return {"name": name, "type": "rsa-3072", "exportable": False, "latest_version": max(k["versions"]),
                "keys": versions}

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        method, path = request.method, request.url.path
        self.calls.append((method, path))
        if self.down or (self.transit_down and path.startswith("/v1/transit/")):
            raise httpx2.ConnectError("không nối được két")
        if path == "/v1/auth/approle/login":
            return httpx2.Response(200, json={"auth": {"client_token": "t", "lease_duration": 3600}})
        if path == "/v1/pki/ca/pem":            # không cần token
            return httpx2.Response(404) if self.pki_missing else httpx2.Response(200, text=self.pki.pem)
        if request.headers.get("x-vault-token") != "t":
            return httpx2.Response(403, json={"errors": ["permission denied"]})
        if path.startswith("/v1/transit/export/") or (
                self.forbidden and re.match(r"/v1/(transit/(keys|sign)/moc-ky-so-|pki/sign/)", path)):
            return httpx2.Response(403, json={"errors": ["permission denied"]})
        body = json.loads(request.content) if request.content else {}
        if method == "POST" and path.startswith("/v1/pki/sign/"):
            if self.pki_missing or path != f"/v1/pki/sign/{signing.ROLE}":
                return httpx2.Response(404, json={"errors": ["no handler for route"]})
            if self.no_role:
                return httpx2.Response(400, json={"errors": [f"unknown role: {signing.ROLE}"]})
            csr = x509.load_pem_x509_csr(body["csr"].encode())
            assert csr.is_signature_valid and body["exclude_cn_from_sans"] is True and body["format"] == "pem"
            public = self._pool[-1].public_key() if self.wrong_key else csr.public_key()
            cert = self.pki.issue(public, body["common_name"], self.cert_days)
            return httpx2.Response(200, json={"data": {
                "certificate": _pem(cert), "issuing_ca": self.pki.pem, "ca_chain": [self.pki.pem],
                "serial_number": ":".join(f"{b:02x}" for b in cert.serial_number.to_bytes(20, "big").lstrip(b"\0")),
                "expiration": int(cert.not_valid_after_utc.timestamp())}})
        if m := re.fullmatch(r"/v1/transit/keys/([^/]+)(?:/(csr|set-certificate))?", path):
            name, action = m.groups()
            if action is None and method == "GET":
                return httpx2.Response(200, json={"data": self._key_info(name)}) if name in self.keys \
                    else httpx2.Response(404, json={"errors": []})
            if action is None:
                assert body == {"type": "rsa-3072"}
                if name not in self.keys:
                    self.keys[name] = {"versions": {1: self._pool[len(self.keys) % len(self._pool)]}, "chains": {}}
                return httpx2.Response(200, json={"data": self._key_info(name)})
            priv = self.keys[name]["versions"][body["version"]]
            if action == "csr":
                csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([])).sign(priv, hashes.SHA256())
                return httpx2.Response(200, json={"data": {"name": name, "csr": csr.public_bytes(
                    serialization.Encoding.PEM).decode()}})
            leaf = x509.load_pem_x509_certificates(body["certificate_chain"].encode())[0]
            assert leaf.public_key() == priv.public_key()        # OpenBao cũng kiểm lá khớp phiên bản khóa
            self.keys[name]["chains"][body["version"]] = body["certificate_chain"]
            return httpx2.Response(200, json={"data": {"name": name, "certificate_chain": body["certificate_chain"]}})
        if m := re.fullmatch(r"/v1/transit/sign/([^/]+)/sha2-256", path):
            if self.bad_request:
                return httpx2.Response(400, json={"errors": ["lỗi giả"]})
            assert body["signature_algorithm"] == "pkcs1v15"
            v = body["key_version"]
            priv = self._pool[-1] if self.bad_signature else self.keys[m.group(1)]["versions"][v]
            sig = priv.sign(base64.b64decode(body["input"]), padding.PKCS1v15(), hashes.SHA256())
            return httpx2.Response(200, json={"data": {"signature": f"vault:v{v}:{base64.b64encode(sig).decode()}",
                                                       "key_version": v}})
        return httpx2.Response(404, json={"errors": []})


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(scope="module")
def pki() -> FakePki:
    return FakePki()


@pytest.fixture(scope="module")
def rsa_pool() -> list[rsa.RSAPrivateKey]:
    return [rsa.generate_private_key(public_exponent=65537, key_size=3072) for _ in range(3)]


@pytest.fixture
def bao(pki, rsa_pool) -> FakeBao:
    return FakeBao(pki, rsa_pool)


def real_vault(bao, tmp, *, slow: bool = False) -> Vault:
    """Vault thật nói chuyện với két giả. slow: mỗi lần gọi nhường event loop như qua mạng thật."""
    (tmp / "role_id").write_text("role\n")
    (tmp / "secret_id").write_text("secret\n")

    async def later(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(0.001)
        return bao(request)

    return Vault("http://openbao:8200", role_id_file=str(tmp / "role_id"), secret_id_file=str(tmp / "secret_id"),
                 transport=httpx2.MockTransport(later if slow else bao))


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def signer(bao, clock, tmp_path) -> DocumentSigner:
    return DocumentSigner(real_vault(bao, tmp_path), monotonic=clock)


def one_page_pdf() -> bytes:
    """PDF một trang có luồng nội dung, ghi lại bằng pypdf."""
    out = io.BytesIO()
    PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf("05/TB-CNTT Ve viec hop giao ban")))).write(out)
    return out.getvalue()


async def sign_one(s: DocumentSigner, pdf: bytes, tenant: uuid.UUID = TENANT_A, org: str = "Khoa Công nghệ thông tin",
                   parent: str | None = "Trường Đại học Thử") -> tuple[bytes, SignatureRecord]:
    assert await s.ready()
    return await s.sign(pdf, tenant_id=tenant, org_name=org, parent_name=parent, place_name="Hà Nội",
                        symbol="05/TB-CNTT", verify_url="https://moc.example/xac-thuc/ABCDE23456")


@pytest.fixture(scope="module")
def signed(pki, rsa_pool, tmp_path_factory) -> bytes:
    s = DocumentSigner(real_vault(FakeBao(pki, rsa_pool), tmp_path_factory.mktemp("bao")))
    return asyncio.run(sign_one(s, one_page_pdf()))[0]


@pytest.fixture
def levels():
    """(mức, sự kiện JSON) của logger svc_files."""
    records: list[tuple[int, dict]] = []

    class Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append((record.levelno, json.loads(record.getMessage())))

    logger, handler = logging.getLogger("svc_files"), Grab()
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield records
    logger.removeHandler(handler)
    logger.setLevel(level)


def events(records: list[tuple[int, dict]], name: str) -> list[dict]:
    return [e for _, e in records if e["event"] == name]


# --- /internal/issue ký trước khi băm ------------------------------------------------------------------------------


@pytest.fixture
def rendered(monkeypatch):
    """Thay WeasyPrint bằng PDF một trang (pypdf), ghi lại văn bản được dựng."""
    seen: list[Letter] = []

    def fake(letter: Letter) -> bytes:
        seen.append(letter)
        return one_page_pdf()

    monkeypatch.setattr("svc_files.app.render_pdf", fake)
    return seen


@pytest.fixture
def sclient(settings, scanner, store, verifier, hasura, meili, vault, signer, rendered):
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                     vault=vault, signer=signer)
    with TestClient(app) as c:
        yield c


def issue(client, make_token, doc_id, tenant=TENANT_A):
    token = make_token(azp="svc-workflow", tenant=None)
    return client.post("/internal/issue", headers={"Authorization": f"Bearer {token}"},
                       json={"tenant_id": str(tenant), "document_id": doc_id, "actor_id": "u-van-thu"})


def test_issue_signs_before_hashing(sclient, hasura, store, scanner, bao, pki, make_token, levels):
    r = issue(sclient, make_token, hasura.add_letter(TENANT_A))
    assert r.status_code == 201
    out = r.json()
    (stored,) = store.objects.values()
    pdf = stored["data"]
    row = hasura.files[uuid.UUID(out["file_id"])]
    # băm trả svc-workflow = băm byte đã lưu = băm ghi CSDL = băm tệp trạm quét nhận — đều là bản đã ký
    assert out["sha256"] == hashlib.sha256(pdf).hexdigest() == row["sha256_hex"] == stored["sha256"]
    assert scanner.scanned == pdf and out["size_bytes"] == len(pdf) == row["size_bytes"]
    verdict = asyncio.run(verify_pdf(pdf, pki.pem))
    assert verdict.status == "valid" and verdict.signer == SIGNER and verdict.ca == CA_CN
    record: SignatureRecord = row["signature"]
    assert record.level == "PAdES-B-B" and record.signer_name == SIGNER and record.ca_name == CA_CN
    assert record.serial == verdict.serial and re.fullmatch(r"[0-9a-f]{2,64}", record.serial)
    assert record.key_name == f"moc-ky-so-{TENANT_A}" and record.key_version == 1
    assert record.signed_at.utcoffset() == timedelta(0) and record.not_after > datetime.now(UTC) + timedelta(days=360)
    leaf = x509.load_pem_x509_certificates(bao.keys[record.key_name]["chains"][1].encode())[0]
    assert record.cert_sha256 == hashlib.sha256(leaf.public_bytes(serialization.Encoding.DER)).hexdigest()
    # pyHanko chạy thử để ước chỗ trống không gọi két: đúng một lần ký
    assert bao.count("POST", r"/v1/transit/sign/moc-ky-so-.*/sha2-256") == 1
    assert bao.count("POST", r"/v1/transit/export/.*") == 0
    (rendered_ev,) = events(levels, "office.document.rendered")
    (signed_ev,) = events(levels, "office.document.signed")
    assert rendered_ev["signed"] is True and signed_ev["file_id"] == out["file_id"]
    assert signed_ev["key_name"] == record.key_name and signed_ev["serial"] == record.serial
    assert isinstance(signed_ev["duration_ms"], int)
    assert events(levels, "office.signing.key_created") and events(levels, "office.signing.certificate_issued")
    # nhật ký không mang trích yếu hay nội dung
    assert "họp giao ban" not in json.dumps([e for _, e in levels], ensure_ascii=False)


def test_pdf_signature_metadata(sclient, hasura, store, make_token):
    issue(sclient, make_token, hasura.add_letter(TENANT_A))
    (stored,) = store.objects.values()
    sig = PdfReader(io.BytesIO(stored["data"])).trailer["/Root"]["/AcroForm"]["/Fields"][0]
    value = sig["/V"]
    assert sig["/T"] == signing.FIELD and value["/SubFilter"] == "/ETSI.CAdES.detached"
    assert value["/Reason"] == "Phát hành văn bản 05/TB-CNTT" and value["/Location"] == "Hà Nội"
    assert value["/ContactInfo"] == "https://moc.example/xac-thuc/ABCDE23456" and value["/Name"] == SIGNER
    # chữ ký chứng nhận, không cho sửa (DocMDP P=1)
    assert value["/Reference"][0]["/TransformParams"]["/P"] == 1
    assert sig.get("/Rect") in (None, [0, 0, 0, 0])     # ô ký ẩn


def test_restricted_documents_are_not_signed(sclient, hasura, store, vault, bao, make_token):
    r = issue(sclient, make_token, hasura.add_letter(TENANT_A, restricted=True))
    assert r.status_code == 201
    row = hasura.files[uuid.UUID(r.json()["file_id"])]
    assert row["signature"] is None and row["wrapped_dek"] in vault.keys
    assert not [c for c in bao.calls if "/transit/" in c[1]]


def test_vault_without_pki_issues_unsigned_then_retries_after_five_minutes(
        settings, scanner, store, verifier, hasura, meili, vault, signer, bao, clock, rendered, make_token, levels):
    bao.pki_missing = True
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                     vault=vault, signer=signer)
    with TestClient(app) as client:
        first = issue(client, make_token, hasura.add_letter(TENANT_A))
        assert first.status_code == 201 and hasura.files[uuid.UUID(first.json()["file_id"])]["signature"] is None
        assert signer.state == "off:no_pki"
        (disabled,) = events(levels, "office.signing.disabled")     # một lần cho một lượt dò
        assert disabled["reason"] == "no_pki"
        bao.pki_missing = False
        clock.t += 299
        assert issue(client, make_token, hasura.add_letter(TENANT_A)).status_code == 201
        assert bao.count("GET", "/v1/pki/ca/pem") == 1             # chưa tới hạn dò lại
        clock.t += 2
        third = issue(client, make_token, hasura.add_letter(TENANT_A))
        assert third.status_code == 201 and signer.state == "ready"
        assert hasura.files[uuid.UUID(third.json()["file_id"])]["signature"] is not None
    assert [f["signature"] is not None for f in hasura.files.values()] == [False, False, True]
    assert not [c for c in bao.calls[:2] if "/transit/" in c[1]]


def test_policy_without_signing_rights_issues_unsigned(sclient, hasura, store, bao, pki, make_token, levels):
    bao.forbidden = True
    r = issue(sclient, make_token, hasura.add_letter(TENANT_A))
    assert r.status_code == 201
    (stored,) = store.objects.values()
    assert hasura.files[uuid.UUID(r.json()["file_id"])]["signature"] is None
    assert stored["data"] == one_page_pdf()        # đúng bản dựng, không có lớp ký dở
    assert asyncio.run(verify_pdf(stored["data"], pki.pem)).status == "unsigned"
    assert [e["reason"] for e in events(levels, "office.signing.disabled")] == ["forbidden"]
    assert events(levels, "office.document.sign_failed")


@pytest.mark.parametrize("when", ["probe", "sign"])
def test_vault_not_answering_is_503_and_stores_nothing(
        settings, scanner, store, verifier, hasura, meili, vault, signer, bao, rendered, make_token, levels, when):
    if when == "probe":
        bao.down = True             # cả pki/ca/pem cũng không trả lời
    else:
        bao.transit_down = True     # dò CA được, két mất kết nối khi tạo khóa
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                     vault=vault, signer=signer)
    with TestClient(app) as client:
        r = issue(client, make_token, hasura.add_letter(TENANT_A))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "signing_unavailable"
    assert not store.objects and not hasura.files and not scanner.scanned
    assert any(level == logging.ERROR for level, e in levels if e["event"] == "office.document.sign_failed")


def test_pyhanko_failure_issues_unsigned_and_logs_an_error(sclient, hasura, store, monkeypatch, levels, make_token):
    class Boom:
        def __init__(self, *a, **kw) -> None:
            pass

        async def async_sign_pdf(self, *a, **kw):
            raise ValueError("PDF lạ")

    monkeypatch.setattr("pyhanko.sign.signers.PdfSigner", Boom)
    r = issue(sclient, make_token, hasura.add_letter(TENANT_A))
    assert r.status_code == 201 and hasura.files[uuid.UUID(r.json()["file_id"])]["signature"] is None
    (failed,) = [(level, e) for level, e in levels if e["event"] == "office.document.sign_failed"]
    assert failed[0] == logging.ERROR and "PDF lạ" in failed[1]["error"]
    assert events(levels, "office.document.rendered")[0]["signed"] is False


def test_unexpected_error_while_signing_issues_unsigned(sclient, hasura, store, monkeypatch, levels, make_token):
    async def boom(*a, **kw):
        raise RuntimeError("lỗi lạ")

    monkeypatch.setattr(signing, "verify_pdf", boom)    # vd két trả dữ liệu lạ, nạp thư viện lỗi: không được 500
    r = issue(sclient, make_token, hasura.add_letter(TENANT_A))
    assert r.status_code == 201 and hasura.files[uuid.UUID(r.json()["file_id"])]["signature"] is None
    (stored,) = store.objects.values()
    assert stored["data"] == one_page_pdf()
    assert "RuntimeError: lỗi lạ" in events(levels, "office.document.sign_failed")[0]["error"]


def test_half_built_pki_turns_signing_off_instead_of_failing_every_issue(sclient, hasura, bao, signer, make_token,
                                                                         levels):
    bao.no_role = True              # setup_pki tạo được CA rồi lỗi khi ghi role: pki/ca/pem có, pki/sign trả 400
    for _ in range(2):
        r = issue(sclient, make_token, hasura.add_letter(TENANT_A))
        assert r.status_code == 201 and hasura.files[uuid.UUID(r.json()["file_id"])]["signature"] is None
    assert signer.state == "off:no_pki"
    assert bao.count("POST", r"/v1/pki/sign/.*") == 1      # lần hai không gọi két, đợi RETRY_OFF_S
    assert [e["reason"] for e in events(levels, "office.signing.disabled")] == ["no_pki"]


@pytest.mark.parametrize("switch", ["bad_request", "wrong_key", "bad_signature"])
def test_vault_errors_and_wrong_certificates_issue_unsigned(sclient, hasura, store, bao, make_token, levels, switch):
    setattr(bao, switch, True)
    r = issue(sclient, make_token, hasura.add_letter(TENANT_A))
    assert r.status_code == 201 and hasura.files[uuid.UUID(r.json()["file_id"])]["signature"] is None
    (stored,) = store.objects.values()
    assert stored["data"] == one_page_pdf()       # không lưu bản ký hỏng
    if switch == "wrong_key":       # chứng thư không mang khóa của transit: không gắn vào khóa
        assert bao.count("POST", r"/v1/transit/keys/.*/set-certificate") == 0
    if switch == "bad_signature":   # tự kiểm sau khi ký bắt được
        assert "tự kiểm chữ ký không đạt: broken" in events(levels, "office.document.sign_failed")[0]["error"]


def test_signing_disabled_by_config(settings, scanner, store, verifier, hasura, meili, vault, signer, bao, rendered,
                                    make_token):
    off = Settings.from_env({**_env(settings), "MOC_SIGN_ENABLED": "false"})
    app = create_app(off, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili, vault=vault,
                     signer=signer)
    assert app.state.signer is None
    with TestClient(app) as client:
        r = issue(client, make_token, hasura.add_letter(TENANT_A))
    assert r.status_code == 201 and hasura.files[uuid.UUID(r.json()["file_id"])]["signature"] is None
    assert not bao.calls


def _env(settings: Settings) -> dict[str, str]:
    return {"MOC_OIDC_ISSUER": settings.oidc_issuer, "MOC_OIDC_JWKS_URL": "http://unused/jwks",
            "SEAWEEDFS_S3_ACCESS_KEY": "test", "SEAWEEDFS_S3_SECRET_KEY": "test", "HASURA_ADMIN_SECRET": "test",
            "MEILISEARCH_API_KEY": "test", "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_ASK_ENABLED": "false",
            "MOC_ASK_SYNC_INTERVAL_S": "0", "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0",
            "MOC_AI_URL": ""}


def test_signer_is_built_only_for_a_configured_vault(settings, scanner, store, verifier, hasura, meili):
    common = dict(scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili)
    with_vault = Settings.from_env({**_env(settings), "MOC_OPENBAO_ADDR": "http://openbao:8200"})
    assert isinstance(create_app(with_vault, **common).state.signer, DocumentSigner)
    assert create_app(settings, **common).state.signer is None
    assert create_app(Settings.from_env({**_env(settings), "MOC_OPENBAO_ADDR": "http://openbao:8200",
                                         "MOC_SIGN_ENABLED": "false"}), **common).state.signer is None


def test_one_key_and_certificate_per_tenant(bao, clock, tmp_path):
    signer = DocumentSigner(real_vault(bao, tmp_path, slow=True), monotonic=clock)
    pdf = one_page_pdf()

    async def scenario():
        await sign_one(signer, pdf)
        await sign_one(signer, pdf)
        # hai đơn vị khác chạy song song lần đầu: mỗi đơn vị vẫn một khóa, một chứng thư
        await asyncio.gather(sign_one(signer, pdf, TENANT_B, "Phòng Đào tạo"),
                             sign_one(signer, pdf, TENANT_B, "Phòng Đào tạo"))

    asyncio.run(scenario())
    assert bao.count("POST", f"/v1/transit/keys/{key_name(TENANT_A)}") == 1
    assert bao.count("POST", f"/v1/transit/keys/{key_name(TENANT_B)}") == 1
    assert bao.count("POST", "/v1/pki/sign/moc-van-thu") == 2
    assert bao.count("POST", r"/v1/transit/sign/moc-ky-so-.*/sha2-256") == 4
    assert bao.count("GET", "/v1/pki/ca/pem") == 1


def test_existing_key_with_certificate_is_reused_after_restart(signer, bao, clock, tmp_path):
    asyncio.run(sign_one(signer, one_page_pdf()))
    again = DocumentSigner(real_vault(bao, tmp_path), monotonic=clock)     # svc-files khởi động lại
    _, record = asyncio.run(sign_one(again, one_page_pdf()))
    assert bao.count("POST", f"/v1/transit/keys/{key_name(TENANT_A)}") == 1
    assert bao.count("POST", "/v1/pki/sign/moc-van-thu") == 1 and record.key_version == 1


def test_signing_with_weasyprint_pdf(signer, pki):
    """pyHanko ký được đúng PDF WeasyPrint dựng (xref stream, đối tượng nén); đo thời gian ký + tự kiểm."""
    try:
        import weasyprint  # noqa: F401
    except OSError:
        pytest.skip("máy này thiếu thư viện Pango của WeasyPrint (image svc-files có sẵn)")
    pdf = render_pdf(Letter(
        org_name="Khoa Công nghệ thông tin", org_code="CNTT", type_code="TB", type_name="Thông báo", in_symbol=True,
        summary="Về việc họp giao ban", body="Đoạn một.\nĐoạn hai.", recipients=["Các bộ môn"], dept_code="ĐT",
        parent_name="Trường Đại học Thử", place_name="Hà Nội", symbol="05/TB-CNTT", issued_on=date(2026, 10, 19),
        verify_code="ABCDE23456", verify_url="https://moc.example/xac-thuc/ABCDE23456"))
    runs = 5

    async def scenario() -> list[float]:
        spent = []
        for _ in range(runs):
            started = time.perf_counter()
            out, _ = await sign_one(signer, pdf)
            spent.append(time.perf_counter() - started)
            assert (await verify_pdf(out, pki.pem)).status == "valid"
        return spent

    assert pdf.startswith(b"%PDF-") and len(pdf) > 5000
    spent = asyncio.run(scenario())
    # xem bằng pytest -s: số đo ghi vào báo cáo tích hợp (két thật thêm một lượt mạng tới transit/sign)
    print(f"\n[F4.5] ký PDF WeasyPrint ({len(pdf)} byte), kể cả tự kiểm, két giả: lần đầu {spent[0] * 1000:.0f} ms"
          f" (có tạo khóa, xin chứng thư), các lần sau trung bình {sum(spent[1:]) / (runs - 1) * 1000:.0f} ms")


# --- tên khóa, CN ---------------------------------------------------------------------------------------------


def test_key_name_and_signer_cn():
    assert key_name(TENANT_A) == "moc-ky-so-6f1c0d2e-0000-4000-8000-00000000000a"
    assert signer_cn("Khoa Công nghệ thông tin", "Trường Đại học Thử") == SIGNER          # 58 byte
    assert signer_cn("Phòng Đào tạo", None) == "Phòng Đào tạo"
    # 52 ký tự nhưng 67 byte UTF-8: chỉ tên đơn vị
    assert signer_cn("Khoa Công nghệ thông tin", "Trường Đại học Công nghiệp") == "Khoa Công nghệ thông tin"
    cut = signer_cn("Trung tâm " + "Nghiên cứu ứng dụng " * 5, None)
    assert cut.endswith("…") and 60 <= len(cut.encode()) <= 64 and cut.startswith("Trung tâm Nghiên cứu")
    assert signer_cn("Khoa Co\u0302ng nghe\u0323\u0302", None) == "Khoa Công nghệ"         # NFD (macOS) → NFC


def test_long_names_fit_the_certificate(signer):
    _, record = asyncio.run(sign_one(signer, one_page_pdf(), parent="Trường Đại học Công nghiệp"))
    assert record.signer_name == "Khoa Công nghệ thông tin"


# --- kiểm chữ ký ----------------------------------------------------------------------------------------------


def _incremental_edit(pdf: bytes) -> bytes:
    writer = PdfWriter(io.BytesIO(pdf), incremental=True)
    writer.add_annotation(page_number=0, annotation=FreeText(text="Đã sửa sau khi ký", rect=(50, 550, 200, 650)))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _flip_in_stream(pdf: bytes) -> bytes:
    i = pdf.index(b"stream") + 8 + 6       # trong luồng nội dung đầu tiên (thuộc khoảng đã ký)
    return pdf[:i] + bytes([pdf[i] ^ 0x01]) + pdf[i + 1:]


def test_verify_classifies_every_case(signed, pki):
    other = FakePki("CA khác")

    def check(pdf: bytes, ca: str = pki.pem, **kw):
        return asyncio.run(verify_pdf(pdf, ca, **kw))

    v = check(signed)
    assert (v.status, v.signer, v.ca, v.coverage, v.docmdp_ok, v.appended_bytes, v.expired_now) == \
        ("valid", SIGNER, CA_CN, "ENTIRE_FILE", True, 0, False)
    assert v.signed_at is not None and abs(v.signed_at - datetime.now(UTC)) < timedelta(minutes=5)
    tail = check(signed + b"\n% them sau khi ky\n")
    assert tail.status == "modified" and tail.appended_bytes == 19 and "(19 byte)" in tail.message
    edited = check(_incremental_edit(signed))
    assert edited.status == "modified" and edited.docmdp_ok is False and edited.appended_bytes > 0
    assert check(_flip_in_stream(signed)).status == "broken"
    assert check(signed, other.pem).status == "untrusted"
    assert check(one_page_pdf()).status == "unsigned"
    assert check(b"khong phai pdf").status == "unreadable"
    later = check(signed, now=datetime.now(UTC) + timedelta(days=400))     # chứng thư lá sống 1 năm
    assert later.status == "valid" and later.expired_now
    # luôn truyền trust_roots: không bao giờ nạp danh sách tin cậy của hệ thống
    assert "oscrypto" not in sys.modules


# --- dòng lệnh -------------------------------------------------------------------------------------------------


@pytest.fixture
def cli(monkeypatch, capsys, tmp_path, pki):
    ca = tmp_path / "ca.pem"
    ca.write_text(pki.pem)

    def run(pdf: bytes, *args: str) -> tuple[int, list[str]]:
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(pdf)))
        code = signing.main(["verify", *(args or ("--ca", str(ca)))])
        out = capsys.readouterr()
        assert out.err == ""        # kết luận ở stdout; traceback của pyHanko không lọt ra stderr
        return code, out.out.splitlines()

    return run


def test_cli_exit_codes_and_messages(cli, signed, monkeypatch):
    code, lines = cli(signed)
    assert code == 0 and lines[0] == ("Chữ ký hợp lệ — PKI nội bộ Mộc (MẪU), chỉ minh họa, không có giá trị pháp lý "
                                      "như chữ ký số công cộng.")
    assert f"Ký bởi: {SIGNER}" in lines and f"CA: {CA_CN}" in lines
    assert any(line.startswith("Ký lúc (tự khai, không có dấu thời gian tin cậy): ") for line in lines)
    assert lines[-1] == "Phủ toàn bộ tệp, không có sửa đổi sau khi ký"
    code, lines = cli(_incremental_edit(signed))
    assert code == 1 and lines[0].startswith("Văn bản đã bị sửa sau khi ký: chữ ký còn đúng cho phần đã ký")
    assert lines[-1].startswith("Ghi chú: PKI nội bộ Mộc (MẪU), chỉ minh họa")
    code, lines = cli(_flip_in_stream(signed))
    assert code == 1 and lines[0] == "Chữ ký không khớp nội dung: tệp đã bị sửa trong phần đã ký."
    assert cli(one_page_pdf()) == (1, ["Tệp không có chữ ký số."])
    assert cli(b"rac") == (2, ["Không đọc được tệp như PDF."])
    monkeypatch.delenv("MOC_OPENBAO_ADDR", raising=False)
    assert cli(signed, "--ca", "/khong/co/tep.pem") == (2, ["Không lấy được chứng thư CA nội bộ từ két"])


def test_cli_unexpected_error_is_exit_2_not_modified(cli, signed, monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("lỗi lạ")

    monkeypatch.setattr(signing, "verify_pdf", boom)
    assert cli(signed) == (2, ["Không kiểm được chữ ký: lỗi ngoài dự kiến (RuntimeError: lỗi lạ)."])


def test_cli_as_a_module_keeps_stderr_clean(signed, pki, tmp_path):
    """Như lệnh bọc của demo, smoke: python -m svc_files.signing verify, tệp ở stdin, đọc dòng đầu và mã thoát."""
    import os
    import pathlib
    import subprocess

    (tmp_path / "ca.pem").write_text(pki.pem)
    src = pathlib.Path(signing.__file__).parents[1]
    run = subprocess.run([sys.executable, "-m", "svc_files.signing", "verify", "--ca", str(tmp_path / "ca.pem")],
                         input=_incremental_edit(signed), capture_output=True, timeout=120,
                         env={**os.environ, "PYTHONPATH": str(src)})
    assert run.returncode == 1
    assert run.stdout.decode().splitlines()[0].startswith("Văn bản đã bị sửa sau khi ký: chữ ký còn đúng")
    assert run.stderr == b""     # pyHanko ghi traceback SuspiciousModification qua logging: CLI đã hạ mức


def test_cli_rejects_a_foreign_ca(cli, signed, tmp_path):
    other = tmp_path / "khac.pem"
    other.write_text(FakePki("CA khác").pem)
    code, lines = cli(signed, "--ca", str(other))
    assert code == 1 and lines[0] == "Chữ ký đúng về mật mã nhưng chứng thư không do CA nội bộ Mộc cấp."


# --- cổng xác thực ------------------------------------------------------------------------------------------------


def test_verify_api_carries_the_signature(client, hasura):
    hasura.add_letter(TENANT_A, status="issued", content_sha256="cd" * 32, signature_level="PAdES-B-B",
                      signed_at="2026-10-23T03:12:45+00:00", signer_name=SIGNER, signer_ca=CA_CN,
                      certificate_serial="3f9a01")
    hasura.add_letter(TENANT_A, status="issued", content_sha256="ef" * 32, verify_code="ZZZZZ22222")
    body = client.get("/api/verify/ABCDE23456").json()
    assert body["document"]["signature"] == {
        "level": "PAdES-B-B", "signer": SIGNER, "ca": CA_CN, "serial": "3f9a01", "signed_at": "2026-10-23T03:12:45Z",
        "illustrative": True,
    }
    assert client.get("/api/verify", params={"sha256": "ef" * 32}).json()["document"]["signature"] is None
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert "VerifiedSignature" in schema and "signature" in schema["VerifiedDocument"]["properties"]


# --- két và Hasura -----------------------------------------------------------------------------------------------


def test_vault_errors_carry_the_http_status(tmp_path):
    replies = {"/v1/transit/keys/a": 404, "/v1/transit/keys/b": 500, "/v1/transit/keys/c": 403}

    def bao(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/login"):
            return httpx2.Response(200, json={"auth": {"client_token": "t", "lease_duration": 3600}})
        return httpx2.Response(replies.get(request.url.path, 204))

    async def scenario():
        vault = real_vault(bao, tmp_path)
        assert await vault.transit_key("a") is None
        for name, status in (("b", 500), ("c", 403)):
            with pytest.raises(VaultError) as err:
                await vault.transit_key(name)
            assert err.value.status == status
        with pytest.raises(VaultError) as err:      # mount PKI chưa có CA: két trả 204 rỗng
            await vault.pki_ca_pem()
        assert err.value.status == 204

        def refuse(request):
            raise httpx2.ConnectError("không nối được")

        with pytest.raises(VaultError) as err:
            await real_vault(refuse, tmp_path).pki_ca_pem()
        assert err.value.status is None

    asyncio.run(scenario())


def test_transit_sign_checks_the_key_version(tmp_path):
    def bao(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/login"):
            return httpx2.Response(200, json={"auth": {"client_token": "t", "lease_duration": 3600}})
        assert json.loads(request.content)["key_version"] == 2
        return httpx2.Response(200, json={"data": {"signature": "vault:v1:" + base64.b64encode(b"x").decode()}})

    with pytest.raises(VaultError):
        asyncio.run(real_vault(bao, tmp_path).transit_sign("moc-ky-so-x", b"du lieu", version=2))


def test_transit_signer_is_a_pyhanko_signer_loaded_lazily():
    from pyhanko.sign.signers.pdf_cms import Signer

    from svc_files.signing import TransitSigner
    assert issubclass(TransitSigner, Signer)
    with pytest.raises(AttributeError):
        signing.KhongCo  # noqa: B018


def test_signature_maps_vault_failures():
    assert isinstance(signing._vault_failure(VaultError("x")), SigningUnavailable)
    assert isinstance(signing._vault_failure(VaultError("x", status=502)), SigningUnavailable)
    assert signing._vault_failure(VaultError("x", status=403)).reason == "forbidden"
    assert isinstance(signing._vault_failure(VaultError("x", status=400)), SigningError)


def test_signed_file_is_inserted_with_its_signature_in_one_mutation():
    sent: list[dict] = []

    def hasura(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json={"data": {"insert_core_files_one": {"id": "x"},
                                                   "insert_core_file_signatures": {"affected_rows": 1}}})

    file_id = uuid.uuid4()
    record = SignatureRecord(level="PAdES-B-B", signed_at=datetime(2026, 10, 23, 3, 12, 45, tzinfo=UTC),
                             signer_name=SIGNER, ca_name=CA_CN, serial="3f9a01", cert_sha256="ab" * 32,
                             not_after=datetime(2027, 10, 23, tzinfo=UTC), key_name=key_name(TENANT_A), key_version=1)
    client = HasuraClient("http://hasura:8080", "bi-mat", transport=httpx2.MockTransport(hasura))
    asyncio.run(client.insert_file(
        tenant_id=TENANT_A, actor_id="u-van-thu", request_id="r", file_id=file_id, object_key="k", filename="a.pdf",
        mime_type="application/pdf", size_bytes=10, sha256_hex="cd" * 32, scanned_at=datetime.now(UTC),
        signature=record))
    (body,) = sent
    assert "insert_core_file_signatures" in body["query"] and "insert_core_files_one" in body["query"]
    s = body["variables"]["s"]
    assert s == {"file_id": str(file_id), "level": "PAdES-B-B", "signed_at": "2026-10-23T03:12:45+00:00",
                 "signer_name": SIGNER, "ca_name": CA_CN, "serial": "3f9a01", "cert_sha256": "\\x" + "ab" * 32,
                 "not_after": "2027-10-23T00:00:00+00:00", "key_name": key_name(TENANT_A), "key_version": 1}
    assert "tenant_id" not in s       # Hasura đặt từ phiên
