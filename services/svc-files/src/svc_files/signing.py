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

"""Ký số PAdES bản phát hành văn bản đi (F4.5) bằng PKI nội bộ trong két OpenBao — CHỈ MINH HỌA.

Khóa ký của mỗi đơn vị là khóa transit ``moc-ky-so-<đơn vị>`` (RSA-3072) do két sinh và giữ: svc-files không bao giờ
cầm khóa riêng, chỉ gửi phần thuộc tính đã ký sang ``transit/sign`` (két ghi sổ từng lần ký; policy không cho xuất
khóa). Chứng thư của khóa do CA nội bộ một tầng của két cấp: svc-files xin CSR từ chính transit, ``pki/sign`` theo role
``moc-van-thu`` với CN = tên đơn vị, rồi gắn chuỗi chứng thư vào phiên bản khóa. pyHanko dựng chữ ký PAdES B-B (chữ ký
chứng nhận không cho sửa, ô ký ẩn ``MocKySo``); bản đã ký được tự kiểm lại bằng đúng CA của két trước khi lưu.

Không có dấu thời gian tin cậy (giờ ký là giờ tự khai), không có thông tin kiểm dài hạn, không thu hồi (CRL/OCSP). CA
không nằm trong danh sách tin cậy công cộng nên trình đọc PDF báo "chưa tin cậy" — đúng như mong đợi. Không có giá trị
pháp lý như chữ ký số công cộng.

Kiểm một tệp: ``python -m svc_files.signing verify [--ca TỆP] < van-ban.pdf`` — mã thoát 0 hợp lệ, 1 đã sửa / không
khớp / CA lạ / không có chữ ký, 2 không đọc được tệp hoặc không lấy được CA.

pyHanko nạp khi cần (như WeasyPrint ở render.py): khởi động svc-files và các test khác không phải trả ~0,5 s.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
import unicodedata
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from .sealed import Vault, VaultError

if TYPE_CHECKING:
    from asn1crypto import x509

KEY_PREFIX = "moc-ky-so-"       # khóa transit của từng đơn vị: moc-ky-so-<id đơn vị>
ROLE = "moc-van-thu"            # role PKI cấp chứng thư ký văn bản (platform/openbao/start.sh)
FIELD = "MocKySo"               # ô ký ẩn
LEVEL = "PAdES-B-B"
RETRY_OFF_S = 300.0             # két thiếu PKI / từ chối: phát hành không ký, chừng ấy giây sau mới dò lại
CN_MAX = 64                     # ub-common-name (RFC 5280), đếm theo byte UTF-8 như cryptography và nhiều bộ kiểm
ILLUSTRATIVE = "PKI nội bộ Signet (MẪU), chỉ minh họa, không có giá trị pháp lý như chữ ký số công cộng"
VN = ZoneInfo("Asia/Ho_Chi_Minh")

Status = Literal["valid", "modified", "broken", "untrusted", "unsigned", "unreadable"]
MESSAGES: dict[str, str] = {
    "valid": f"Chữ ký hợp lệ — {ILLUSTRATIVE}.",
    "modified": "Văn bản đã bị sửa sau khi ký: chữ ký còn đúng cho phần đã ký, phần thêm vào sau đó ({n} byte) "
                "không được ký.",
    "broken": "Chữ ký không khớp nội dung: tệp đã bị sửa trong phần đã ký.",
    "untrusted": "Chữ ký đúng về mật mã nhưng chứng thư không do CA nội bộ Signet cấp.",
    "unsigned": "Tệp không có chữ ký số.",
    "unreadable": "Không đọc được tệp như PDF.",
}
EXIT_CODES: dict[str, int] = {"valid": 0, "modified": 1, "broken": 1, "untrusted": 1, "unsigned": 1, "unreadable": 2}
NO_CA = "Không lấy được chứng thư CA nội bộ từ két"

log = logging.getLogger("svc_files")


class SigningUnavailable(Exception):
    """Két không trả lời (mạng, 5xx, hết giờ): /internal/issue trả 503 signing_unavailable, không lưu gì."""


class SigningOff(Exception):
    """Két chưa có PKI (``no_pki``) hoặc policy cũ từ chối (``forbidden``): phát hành không ký, dò lại sau."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"ký số tắt: {reason}")
        self.reason = reason


class SigningError(Exception):
    """pyHanko lỗi, tự kiểm không đạt, két trả 400 hay dữ liệu lạ: phát hành không ký."""


def key_name(tenant_id: uuid.UUID) -> str:
    return f"{KEY_PREFIX}{tenant_id}"


def signer_cn(name: str, parent: str | None) -> str:
    """CN chứng thư của đơn vị: "<đơn vị>, <cơ quan chủ quản>"; quá 64 byte UTF-8 thì chỉ tên đơn vị, vẫn quá thì cắt
    (không cắt giữa một ký tự). Tiếng Việt có dấu tốn 2–3 byte mỗi chữ: "Khoa Công nghệ thông tin, Trường Đại học
    Công nghiệp" 52 ký tự nhưng 67 byte nên CN chỉ là "Khoa Công nghệ thông tin"."""
    name = unicodedata.normalize("NFC", name.strip())
    full = f"{name}, {unicodedata.normalize('NFC', parent.strip())}" if parent else name
    for cn in (full, name):
        if len(cn.encode()) <= CN_MAX:
            return cn
    ellipsis = "…"
    return name.encode()[:CN_MAX - len(ellipsis.encode())].decode("utf-8", "ignore").rstrip() + ellipsis


@dataclass(frozen=True)
class SigningKey:
    name: str
    version: int
    cn: str
    cert: x509.Certificate      # asn1crypto, chứng thư lá gắn vào phiên bản khóa
    ca: x509.Certificate
    serial: str                 # hex thường, không ":"
    cert_sha256: bytes
    not_after: datetime


@dataclass(frozen=True)
class SignatureRecord:
    """Đúng các cột của core.file_signatures, trừ file_id và tenant_id."""

    level: str
    signed_at: datetime         # giờ tự khai trong chữ ký (UTC)
    signer_name: str
    ca_name: str
    serial: str
    cert_sha256: str            # hex
    not_after: datetime
    key_name: str
    key_version: int


@dataclass(frozen=True)
class Verdict:
    status: Status
    message: str                # câu tiếng Việt in ở dòng đầu của CLI
    signer: str | None = None
    ca: str | None = None
    serial: str | None = None
    signed_at: datetime | None = None
    coverage: str | None = None             # tên SignatureCoverageLevel của pyHanko
    docmdp_ok: bool | None = None
    appended_bytes: int = 0                 # số byte sau cuối khoảng ký
    expired_now: bool = False               # chứng thư hết hạn lúc kiểm, hợp lệ tại giờ ký tự khai


def _log(event: str, level: int = logging.INFO, **fields: object) -> None:
    log.log(level, json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def _vault_failure(exc: VaultError) -> Exception:
    """Lỗi két → cách phát hành: không trả lời thì 503, từ chối thì tắt ký số, còn lại phát hành không ký."""
    if exc.status is None or exc.status >= 500:
        return SigningUnavailable(str(exc))
    if exc.status == 403:
        return SigningOff("forbidden")
    return SigningError(str(exc))


# --- chứng thư (asn1crypto, đi kèm pyHanko) -----------------------------------------------------------------

def _load_certs(pem: str) -> list[x509.Certificate]:
    from asn1crypto import pem as asn1_pem
    from asn1crypto import x509 as asn1_x509

    certs = [asn1_x509.Certificate.load(der) for kind, _, der in asn1_pem.unarmor(pem.encode(), multiple=True)
             if kind == "CERTIFICATE"]
    for cert in certs:
        cert.native  # noqa: B018 — giải mã hết ngay: DER hỏng thì lỗi ở đây, không phải giữa lúc ký
    if not certs:
        raise ValueError("không có chứng thư PEM nào")
    return certs


def _rsa_numbers(spki: Any) -> dict[str, int]:
    """Số mũ, mô-đun của khóa công khai RSA (keys.PublicKeyInfo) — so khóa không phụ thuộc cách mã hóa DER."""
    return dict(spki["public_key"].parsed.native)


def _public_key(pem: str) -> dict[str, int]:
    from asn1crypto import keys
    from asn1crypto import pem as asn1_pem

    _, _, der = asn1_pem.unarmor(pem.encode())
    return _rsa_numbers(keys.PublicKeyInfo.load(der))


def _cn(name: Any) -> str:
    value = name.native.get("common_name") or ""
    return str(value[-1] if isinstance(value, list) else value)


def _serial_hex(cert: x509.Certificate) -> str:
    h = f"{cert.serial_number:x}"
    return h if len(h) % 2 == 0 else "0" + h


# --- ký -----------------------------------------------------------------------------------------------------

@cache
def _transit_signer_class() -> type:
    from asn1crypto.algos import SignedDigestAlgorithm
    from pyhanko.sign.signers.pdf_cms import Signer
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    class TransitSigner(Signer):
        """Signer của pyHanko ký bằng khóa transit: phần thuộc tính đã ký gửi sang két, két băm SHA-256 và ký
        PKCS#1 v1.5 bằng đúng phiên bản khóa có chứng thư."""

        def __init__(self, vault: Vault, key: SigningKey) -> None:
            super().__init__(signing_cert=key.cert, cert_registry=SimpleCertificateStore.from_certs([key.ca]),
                             signature_mechanism=SignedDigestAlgorithm({"algorithm": "sha256_rsa"}))
            self._vault = vault
            self._key = key

        async def async_sign_raw(self, data: bytes, digest_algorithm: str, dry_run: bool = False) -> bytes:
            if digest_algorithm != "sha256":
                raise SigningError(f"chỉ ký SHA-256, pyHanko xin {digest_algorithm}")
            if dry_run:     # pyHanko ước chỗ trống cho chữ ký: không gọi két
                return bytes(self._key.cert.public_key.bit_size // 8)
            try:
                return await self._vault.transit_sign(self._key.name, data, version=self._key.version)
            except VaultError as exc:
                raise _vault_failure(exc) from exc

    return TransitSigner


def preload() -> None:
    """Nạp pyHanko trước (svc-files gọi trong luồng phụ lúc khởi động): lần phát hành đầu không chặn event loop."""
    _transit_signer_class()
    import pyhanko.sign.signers  # noqa: F401
    import pyhanko.sign.validation  # noqa: F401


def __getattr__(name: str) -> Any:
    if name == "TransitSigner":     # lớp con của Signer pyHanko: chỉ dựng khi có người hỏi tới
        return _transit_signer_class()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class DocumentSigner:
    """Ký bản phát hành bằng khóa transit của đơn vị. Một bộ cho cả tiến trình: nhớ CA của két và khóa từng đơn vị;
    hai lần phát hành đầu của một đơn vị chạy song song vẫn chỉ tạo một khóa, xin một chứng thư.

    ``state``: ``unknown`` (chưa dò) · ``ready`` · ``off:no_pki`` (két chưa có CA nội bộ) · ``off:forbidden`` (policy
    của két chưa cho svc-files dùng khóa ký). Đang tắt thì RETRY_OFF_S giây sau mới dò lại.

    Bản tối thiểu: chứng thư chỉ xin khi phiên bản khóa chưa có (sống 1 năm), chưa tự cấp lại khi sắp hết hạn hay đơn
    vị đổi tên. Tự kiểm không đạt thì quên khóa đã nhớ của đơn vị: xoay khóa transit (token quản trị) thì lần ký kế
    tiếp đọc lại khóa và xin chứng thư cho phiên bản mới."""

    def __init__(self, vault: Vault, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._vault = vault
        self._monotonic = monotonic
        self.state = "unknown"
        self._off_at = 0.0
        self._ca: x509.Certificate | None = None
        self._ca_pem = ""
        self._keys: dict[str, SigningKey] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._probe = asyncio.Lock()

    def _off(self, reason: str) -> None:
        self.state, self._off_at = f"off:{reason}", self._monotonic()
        _log("office.signing.disabled", logging.WARNING, reason=reason, retry_s=RETRY_OFF_S)

    def _waiting(self) -> bool:
        return self.state.startswith("off:") and self._monotonic() - self._off_at < RETRY_OFF_S

    async def ready(self) -> bool:
        """Có ký được không. Dò ``pki/ca/pem`` lần đầu và khi đã tắt đủ lâu; két không trả lời: SigningUnavailable."""
        if self.state == "ready":
            return True
        if self._waiting():
            return False
        async with self._probe:
            if self.state == "ready":
                return True
            if self._waiting():
                return False
            try:
                pem = (await self._vault.pki_ca_pem()).strip()
            except VaultError as exc:
                if exc.status is None or exc.status >= 500:
                    raise SigningUnavailable(str(exc)) from exc
                self._off("no_pki")     # 204 (mount chưa có CA), 403/404 (chưa bật PKI): két cũ chưa nâng cấp
                return False
            try:
                ca = _load_certs(pem)[0]
            except ValueError:
                self._off("no_pki")
                return False
            if pem != self._ca_pem:     # két có CA khác lần trước (dựng lại): khóa nhớ trước đó không dùng nữa
                self._keys.clear()
            self._ca, self._ca_pem, self.state = ca, pem, "ready"
            _log("office.signing.ready", ca=_cn(ca.subject), serial=_serial_hex(ca))
            return True

    async def sign(self, pdf: bytes, *, tenant_id: uuid.UUID, org_name: str, parent_name: str | None,
                   place_name: str | None, symbol: str, verify_url: str) -> tuple[bytes, SignatureRecord]:
        """PDF đã ký (một lần cập nhật bổ sung, chữ ký chứng nhận) và dòng core.file_signatures của nó."""
        ca, ca_pem = self._ca, self._ca_pem
        if self.state != "ready" or ca is None:
            raise SigningError("bộ ký chưa sẵn sàng")
        try:
            key = await self._key_for(tenant_id, signer_cn(org_name, parent_name), ca)
            signed = await self._sign_pdf(pdf, key, place_name=place_name, symbol=symbol, verify_url=verify_url)
            verdict = await verify_pdf(signed, ca_pem)
        except SigningOff as exc:
            self._off(exc.reason)
            raise
        except (SigningUnavailable, SigningError):
            raise
        except Exception as exc:  # noqa: BLE001 — két trả dữ liệu lạ, nạp thư viện lỗi…: phát hành không ký, không 500
            raise SigningError(f"lỗi ngoài dự kiến khi ký: {type(exc).__name__}: {exc}") from exc
        if verdict.status != "valid" or verdict.signed_at is None:
            self._keys.pop(key.name, None)     # vd chứng thư đã hết hạn: lần sau đọc lại khóa từ két
            raise SigningError(f"tự kiểm chữ ký không đạt: {verdict.status} — {verdict.message}")
        return signed, SignatureRecord(
            level=LEVEL, signed_at=verdict.signed_at.astimezone(UTC), signer_name=key.cn, ca_name=_cn(ca.subject),
            serial=key.serial, cert_sha256=key.cert_sha256.hex(), not_after=key.not_after, key_name=key.name,
            key_version=key.version)

    async def _key_for(self, tenant_id: uuid.UUID, cn: str, ca: x509.Certificate) -> SigningKey:
        name = key_name(tenant_id)
        async with self._locks.setdefault(name, asyncio.Lock()):
            if (key := self._keys.get(name)) is not None:
                return key
            try:
                key = await self._load_key(name, cn, ca)
            except VaultError as exc:
                raise _vault_failure(exc) from exc
            self._keys[name] = key
            return key

    async def _load_key(self, name: str, cn: str, ca: x509.Certificate) -> SigningKey:
        info = await self._vault.transit_key(name)
        if info is None:    # lần ký đầu của đơn vị: két sinh khóa RSA-3072 (máy dev: < 0,5 giây)
            await self._vault.transit_create_key(name)
            _log("office.signing.key_created", key_name=name)
            if (info := await self._vault.transit_key(name)) is None:
                raise SigningError(f"két không thấy khóa {name} vừa tạo")
        try:
            version = int(info["latest_version"])
            entry = info["keys"][str(version)]
            public = _public_key(str(entry["public_key"]))
            chain = str(entry.get("certificate_chain") or "")
        except (KeyError, TypeError, ValueError) as exc:
            raise SigningError(f"két trả thông tin khóa {name} lạ: {type(exc).__name__}") from None
        issued = not chain
        if issued:  # phiên bản khóa chưa có chứng thư: CSR do chính transit ký → CA nội bộ cấp → gắn vào khóa
            csr = await self._vault.transit_csr(name, version)
            try:
                got = await self._vault.pki_sign(ROLE, csr, cn)
            except VaultError as exc:
                # chưa có role moc-van-thu (két trả 400 "unknown role", có bản trả 404), role từ chối CN: PKI dựng dở
                # — tắt ký số rồi dò lại sau RETRY_OFF_S, không gọi két mỗi lần phát hành
                if exc.status in (400, 404):
                    raise SigningOff("no_pki") from exc
                raise
            chain = f"{str(got.get('certificate') or '').strip()}\n{str(got.get('issuing_ca') or '').strip()}"
        try:
            cert = _load_certs(chain)[0]
        except ValueError as exc:
            raise SigningError(f"chuỗi chứng thư của {name} không đọc được: {exc}") from None
        if _rsa_numbers(cert.public_key) != public:
            raise SigningError(f"chứng thư của {name} v{version} không mang khóa công khai của transit")
        if issued:
            await self._vault.transit_set_certificate(name, version, chain)
            _log("office.signing.certificate_issued", key_name=name, key_version=version, serial=_serial_hex(cert),
                 not_after=cert.not_valid_after)
        return SigningKey(name=name, version=version, cn=_cn(cert.subject), cert=cert, ca=ca, serial=_serial_hex(cert),
                          cert_sha256=hashlib.sha256(cert.dump()).digest(), not_after=cert.not_valid_after)

    async def _sign_pdf(self, pdf: bytes, key: SigningKey, *, place_name: str | None, symbol: str,
                        verify_url: str) -> bytes:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
        from pyhanko.sign.fields import MDPPerm, SigSeedSubFilter

        meta = signers.PdfSignatureMetadata(
            field_name=FIELD, md_algorithm="sha256", subfilter=SigSeedSubFilter.PADES, certify=True,
            docmdp_permissions=MDPPerm.NO_CHANGES, reason=f"Phát hành văn bản {symbol}", location=place_name,
            name=key.cn, contact_info=verify_url)
        out = BytesIO()
        try:
            writer = IncrementalPdfFileWriter(BytesIO(pdf))
            await signers.PdfSigner(meta, signer=_transit_signer_class()(self._vault, key)).async_sign_pdf(
                writer, output=out)
        except (SigningUnavailable, SigningOff, SigningError):
            raise
        except Exception as exc:  # noqa: BLE001 — pyHanko gặp PDF lạ có thể ném đủ loại lỗi
            raise SigningError(f"pyHanko không ký được: {type(exc).__name__}: {exc}") from exc
        return out.getvalue()


# --- kiểm ---------------------------------------------------------------------------------------------------

async def verify_pdf(pdf: bytes, ca_pem: str, *, now: datetime | None = None) -> Verdict:
    """Kiểm chữ ký ở ô MocKySo (không có thì chữ ký đầu tiên), chỉ tin đúng CA ``ca_pem``, không tải gì từ mạng.

    Luôn truyền trust_roots tường minh nên pyHanko không bao giờ nạp danh sách tin cậy của hệ thống (oscrypto)."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import async_validate_pdf_signature
    from pyhanko.sign.validation.status import SignatureCoverageLevel
    from pyhanko_certvalidator import ValidationContext

    ca = _load_certs(ca_pem)[0]

    def context(moment: datetime | None) -> Any:
        return ValidationContext(trust_roots=[ca], allow_fetching=False, revocation_mode="soft-fail", moment=moment)

    try:
        sigs = PdfFileReader(BytesIO(pdf), strict=False).embedded_signatures
    except Exception:  # noqa: BLE001 — không phải PDF, PDF hỏng
        return Verdict("unreadable", MESSAGES["unreadable"])
    if not sigs:
        return Verdict("unsigned", MESSAGES["unsigned"])
    sig = next((s for s in sigs if s.field_name == FIELD), sigs[0])
    try:
        byte_range = [int(x) for x in sig.byte_range]
        appended = max(0, len(pdf) - (byte_range[2] + byte_range[3]))
        status = await async_validate_pdf_signature(sig, context(now))
    except Exception:  # noqa: BLE001 — khối chữ ký hỏng tới mức không giải mã được
        return Verdict("broken", MESSAGES["broken"])

    cert = status.signing_cert
    seen = {"signer": _cn(cert.subject), "ca": _cn(cert.issuer), "serial": _serial_hex(cert),
            "signed_at": status.signer_reported_dt, "coverage": status.coverage.name if status.coverage else None,
            "docmdp_ok": status.docmdp_ok, "appended_bytes": appended}
    if not (status.intact and status.valid):
        return Verdict("broken", MESSAGES["broken"], **seen)
    expired_now = False
    if not status.trusted:
        # Chứng thư hết hạn ở thời điểm kiểm: hợp lệ nếu đạt tại giờ ký tự khai (không có dấu thời gian tin cậy)
        signed_at = status.signer_reported_dt
        if signed_at is not None and (now or datetime.now(UTC)) > cert.not_valid_after:
            try:
                expired_now = (await async_validate_pdf_signature(sig, context(signed_at))).trusted
            except Exception:  # noqa: BLE001 — như lần kiểm đầu
                expired_now = False
        if not expired_now:
            return Verdict("untrusted", MESSAGES["untrusted"], **seen)
    if status.coverage != SignatureCoverageLevel.ENTIRE_FILE or status.docmdp_ok is False or appended > 0:
        return Verdict("modified", MESSAGES["modified"].format(n=appended), expired_now=expired_now, **seen)
    return Verdict("valid", MESSAGES["valid"], expired_now=expired_now, **seen)


# --- dòng lệnh: python -m svc_files.signing verify --------------------------------------------------------------

def _read_ca(path: str | None) -> str | None:
    """Chứng thư CA từ tệp, không thì từ két (``pki/ca/pem`` không cần token); không được thì None."""
    try:
        if path:
            with open(path, encoding="utf-8") as f:
                pem = f.read()
        else:
            addr = os.environ.get("MOC_OPENBAO_ADDR", "").rstrip("/")
            if not addr.startswith(("http://", "https://")):
                return None
            with urllib.request.urlopen(f"{addr}/v1/pki/ca/pem", timeout=10) as r:  # noqa: S310 — chỉ http(s)
                if r.status != 200:
                    return None
                pem = r.read().decode("utf-8")
        _load_certs(pem)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return pem


def _report(v: Verdict) -> list[str]:
    lines = [v.message]
    if v.signer is not None:
        lines += [f"Ký bởi: {v.signer}", f"CA: {v.ca}", f"Số sê-ri: {v.serial}"]
        if v.signed_at is not None:
            when = v.signed_at.astimezone(VN).strftime("%H:%M:%S ngày %d/%m/%Y (giờ Việt Nam)")
            lines.append(f"Ký lúc (tự khai, không có dấu thời gian tin cậy): {when}")
    if v.status == "valid":
        lines.append("Phủ toàn bộ tệp, không có sửa đổi sau khi ký")
        if v.expired_now:
            lines.append("Chứng thư đã hết hạn; hợp lệ tại giờ ký tự khai.")
    elif v.signer is not None:
        lines.append(f"Ghi chú: {ILLUSTRATIVE}.")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m svc_files.signing",
                                     description=f"Kiểm chữ ký số PDF của Signet — {ILLUSTRATIVE}.")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="kiểm chữ ký của tệp PDF đọc từ stdin, chỉ tin CA nội bộ của két")
    verify.add_argument("--ca", metavar="TỆP",
                        help="chứng thư CA (PEM); mặc định lấy từ két: $MOC_OPENBAO_ADDR/v1/pki/ca/pem")
    args = parser.parse_args(argv)
    # pyHanko ghi traceback (vd SuspiciousModification khi tệp có lớp sửa, ExpiredError) ra stderr qua logging; kết
    # luận đã in ở stdout nên chỉ để lại lỗi thật sự nghiêm trọng
    for noisy in ("pyhanko", "pyhanko_certvalidator"):
        logging.getLogger(noisy).setLevel(logging.CRITICAL)
    ca_pem = _read_ca(args.ca)
    if ca_pem is None:
        print(NO_CA)
        return 2
    try:
        verdict = asyncio.run(verify_pdf(sys.stdin.buffer.read(), ca_pem))
    except Exception as exc:  # noqa: BLE001 — lỗi lạ không được lẫn với mã 1 "đã sửa / không khớp"
        print(f"Không kiểm được chữ ký: lỗi ngoài dự kiến ({type(exc).__name__}: {exc}).")
        return 2
    print("\n".join(_report(verdict)))
    return EXIT_CODES[verdict.status]


if __name__ == "__main__":
    sys.exit(main())
