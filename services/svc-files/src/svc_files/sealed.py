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

"""Văn bản hạn chế (F3.7): tệp lưu mã hóa, chỉ giải mã trong bộ nhớ của svc-files, bản xem có dấu tên người xem.

Mỗi tệp một khóa dữ liệu AES-256 riêng do két OpenBao cấp (``transit/datakey/plaintext/moc-files``): két trả khóa rõ
và khóa đã bọc. Tệp được mã hóa AES-256-GCM trong bộ nhớ; kho đối tượng chỉ nhận bản mã, CSDL chỉ giữ khóa đã bọc
(``core.files.wrapped_dek``, dạng ``vault:v1:…``); khóa rõ bỏ ngay. Đọc: két mở khóa đã bọc (``transit/decrypt``),
giải mã trong bộ nhớ, kiểm băm của bản rõ, đóng dấu tên người xem lên từng trang rồi trả về — bản rõ không ghi xuống
đĩa (thư mục tạm của svc-files là tmpfs). svc-files không lấy được khóa gốc ``moc-files``: chỉ két mở được khóa đã
bọc, nên mất két (volume ``openbao_data``) là mất tệp — két nằm trong bản sao lưu.

Bản mã: ``MOC1`` + nonce 12 byte + AES-GCM(khóa, nonce, bản rõ, AAD = id đơn vị ‖ id tệp) — chép bản mã sang một
dòng ``core.files`` khác thì không mở được.

Không dùng cho bí mật nhà nước (Luật Bảo vệ bí mật nhà nước 2018 đòi hỏi hệ thống, mật mã được cấp phép riêng).

PDF do người dùng tải lên: như pdftext.py, ocr.py, svc-files không mở nó trong tiến trình của mình. Kiểm lúc tải lên
(``run_check_pdf``) và đóng dấu lúc xem (``run_watermark``) chạy chính tệp này thành tiến trình con (``python -I
sealed.py``, không cần gói svc_files) có RLIMIT_AS, RLIMIT_CPU, hạn thời gian; quá hạn thì giết cả nhóm. Bản rõ, bản có
dấu chỉ đi qua ống stdin/stdout, không xuống đĩa; tiến trình con không ghi nhật ký (stderr bỏ đi). Trần số trang
(``MOC_RESTRICTED_MAX_PAGES``) chặn tệp hàng vạn trang tí hon làm mỗi lần xem tốn hàng phút.

Phòng đọc hồ sơ đã nộp lưu (F3.8, ``GET /api/case-files/{id}/archive/files/{file_id}``) đóng dấu tệp trong gói lạnh
bằng đúng đường này, chỉ khác chữ trên lớp dấu (``kind="archive"``, STAMP_LINES).
"""

from __future__ import annotations

import asyncio
import base64
import errno
import html
import io
import json
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx2
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from httpx2 import USE_CLIENT_DEFAULT
from pypdf import PageObject, PdfReader, PdfWriter, Transformation

MAGIC = b"MOC1"
NONCE = 12
VN = timezone(timedelta(hours=7))
MAX_STAMPS = 8          # số cỡ trang khác nhau được dựng lớp dấu riêng; nhiều hơn thì co giãn lớp dấu đầu tiên
MEMORY_MB = 1024        # RLIMIT_AS của tiến trình con (WeasyPrint + pypdf lúc rảnh ~260 MB bộ nhớ ảo)
EXIT_MEMORY = 3         # mã thoát của tiến trình con khi hết bộ nhớ cả lúc ghi kết quả (không ghi nổi dòng JSON)
CHECK_TIMEOUT_S = 20.0  # hạn kiểm PDF lúc tải lên
STAMP_TIMEOUT_S = 30.0  # hạn đóng dấu lúc xem: cộng thời gian chờ lượt vẫn dưới 60 giây của APISIX
# lý do PDF không nhận, không đóng dấu được — tiến trình con chỉ trả mã, lời báo do svc-files đặt
REASONS = {
    "not_pdf": "không phải tệp PDF",
    "password": "PDF có mật khẩu",
    "no_pages": "PDF không có trang nào",
    "too_many_pages": "PDF nhiều trang quá",
    "corrupt": "không đọc được PDF",
    "timeout": "PDF quá nặng, đọc không kịp thời gian cho phép",
    "memory": "PDF quá nặng, vượt giới hạn bộ nhớ",
}


class SealError(Exception):
    """Bản mã hỏng, sai khóa hoặc không thuộc tệp này; hoặc PDF không đọc được để đóng dấu.

    reason: một khóa của REASONS khi lỗi là của tệp PDF (kiểm, đóng dấu)."""

    def __init__(self, message: str, *, reason: str = "corrupt") -> None:
        super().__init__(message)
        self.reason = reason


class VaultError(Exception):
    """Két chưa sẵn sàng hoặc từ chối. status: mã HTTP két trả; None khi không gọi hoặc không đăng nhập được két."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _aad(tenant_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    return tenant_id.bytes + file_id.bytes


def seal(plain: bytes, key: bytes, tenant_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    nonce = os.urandom(NONCE)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plain, _aad(tenant_id, file_id))


def unseal(blob: bytes, key: bytes, tenant_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + NONCE + 16:
        raise SealError("không phải bản mã của Signet")
    nonce = blob[len(MAGIC):len(MAGIC) + NONCE]
    try:
        return AESGCM(key).decrypt(nonce, blob[len(MAGIC) + NONCE:], _aad(tenant_id, file_id))
    except (InvalidTag, ValueError) as exc:  # sai khóa, bản mã bị sửa, của tệp khác; khóa sai độ dài
        raise SealError("bản mã không khớp khóa hoặc tệp") from exc


class Vault:
    """Khóa dữ liệu từ transit của két. Đăng nhập AppRole khi cần (token 1 giờ, giữ trong bộ nhớ, dùng lại tới gần
    hết hạn); đọc lại role_id/secret_id mỗi lần đăng nhập vì két cấp secret_id mới mỗi lần khởi động.

    Ký số (F4.5, signing.py): khóa ký từng đơn vị trong transit (tạo, xin CSR, gắn chứng thư, ký), chứng thư từ PKI
    nội bộ của két. Không có hàm xuất khóa: policy của svc-files cũng không cho."""

    def __init__(self, addr: str, *, role_id_file: str, secret_id_file: str, key: str = "moc-files",
                 timeout_s: float = 5.0, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self.key = key
        self._files = (Path(role_id_file), Path(secret_id_file))
        self._http = httpx2.AsyncClient(base_url=addr.rstrip("/"), timeout=timeout_s, transport=transport)
        self._token: str | None = None
        self._until = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        """Két đã khởi tạo và đã mở khóa (``/v1/sys/health``, không cần token) — trang trạng thái hệ thống."""
        try:
            r = await self._http.get("/v1/sys/health", params={"standbyok": "true"})
        except httpx2.HTTPError:
            return False
        return r.status_code == 200

    async def _login(self) -> str:
        try:
            role_id, secret_id = (p.read_text().strip() for p in self._files)
        except OSError as exc:
            raise VaultError(f"không đọc được thông tin đăng nhập két: {exc}") from None
        r = await self._http.post("/v1/auth/approle/login", json={"role_id": role_id, "secret_id": secret_id})
        if r.status_code != 200:   # không mang status: như két chưa sẵn sàng (vừa khởi động lại, secret_id mới)
            raise VaultError(f"két từ chối đăng nhập AppRole: HTTP {r.status_code}")
        auth = r.json()["auth"]
        self._token = str(auth["client_token"])
        self._until = time.monotonic() + max(30.0, float(auth.get("lease_duration") or 0) * 0.8)
        return self._token

    async def _request(self, method: str, path: str, body: dict[str, object] | None = None, *, auth: bool = True,
                       raw: bool = False, timeout_s: float | None = None) -> Any:
        """Gọi két. raw: trả nguyên thân (text), không thì trường ``data`` của JSON. Thân không phải 200 thì
        VaultError mang mã HTTP; 403 khi có token thì đăng nhập lại và thử một lần (token bị thu hồi)."""
        timeout = USE_CLIENT_DEFAULT if timeout_s is None else timeout_s
        try:
            for attempt in (1, 2):
                headers = {}
                if auth:
                    async with self._lock:
                        token = self._token if self._token and time.monotonic() < self._until else await self._login()
                    headers["X-Vault-Token"] = token
                r = await self._http.request(method, path, json=body, headers=headers, timeout=timeout)
                if r.status_code == 403 and auth and attempt == 1:  # token bị thu hồi (két khởi động lại): đăng nhập
                    self._token = None
                    continue
                if r.status_code != 200:
                    raise VaultError(f"két trả HTTP {r.status_code} ở {path}", status=r.status_code)
                if raw:
                    return r.text
                data = r.json()["data"]
                if not isinstance(data, dict):
                    raise VaultError(f"két trả dữ liệu lạ ở {path}", status=r.status_code)
                return data
        except httpx2.HTTPError as exc:
            raise VaultError(f"không gọi được két: {type(exc).__name__}") from None
        except (KeyError, TypeError, ValueError) as exc:  # thân trả về không phải JSON đúng dạng
            raise VaultError(f"két trả dữ liệu lạ ở {path}: {type(exc).__name__}", status=200) from None
        raise VaultError("két từ chối sau khi đăng nhập lại", status=403)

    async def datakey(self) -> tuple[bytes, str]:
        """Khóa dữ liệu mới → (khóa rõ 32 byte, khóa đã bọc ``vault:v1:…``)."""
        data = await self._request("POST", f"/v1/transit/datakey/plaintext/{self.key}", {"bits": 256})
        try:
            key, wrapped = base64.b64decode(str(data["plaintext"]), validate=True), str(data["ciphertext"])
        except (KeyError, ValueError) as exc:
            raise VaultError(f"két trả khóa dữ liệu lạ: {type(exc).__name__}") from None
        if len(key) != 32 or not wrapped.startswith("vault:v"):
            raise VaultError("két trả khóa dữ liệu không đúng dạng")
        return key, wrapped

    async def unwrap(self, wrapped: str) -> bytes:
        """Khóa đã bọc → khóa rõ; két ghi sổ mỗi lần mở."""
        data = await self._request("POST", f"/v1/transit/decrypt/{self.key}", {"ciphertext": wrapped})
        try:
            return base64.b64decode(str(data["plaintext"]), validate=True)
        except (KeyError, ValueError) as exc:
            raise VaultError(f"két trả khóa rõ lạ: {type(exc).__name__}") from None

    # --- ký số (F4.5) ----------------------------------------------------------------------------------------

    async def pki_ca_pem(self) -> str:
        """Chứng thư CA nội bộ (PEM), không cần token. Chưa dựng CA: két trả 204/403/404 — VaultError mang mã đó."""
        return str(await self._request("GET", "/v1/pki/ca/pem", auth=False, raw=True))

    async def transit_key(self, name: str) -> dict[str, Any] | None:
        """Thông tin khóa transit (``latest_version``, ``keys.<v>.{public_key, certificate_chain}``); chưa có: None."""
        try:
            return await self._request("GET", f"/v1/transit/keys/{name}")
        except VaultError as exc:
            if exc.status == 404:
                return None
            raise

    async def transit_create_key(self, name: str) -> None:
        """Tạo khóa ký RSA-3072 (két sinh khóa, không cho xuất). Đã có thì két chỉ cảnh báo, không lỗi."""
        await self._request("POST", f"/v1/transit/keys/{name}", {"type": "rsa-3072"}, timeout_s=30.0)

    async def transit_csr(self, name: str, version: int) -> str:
        """CSR do chính khóa transit ký (chủ thể rỗng: CN do role PKI đặt)."""
        data = await self._request("POST", f"/v1/transit/keys/{name}/csr", {"version": version})
        return str(data["csr"])

    async def pki_sign(self, role: str, csr: str, cn: str) -> dict[str, Any]:
        """Cấp chứng thư cho CSR theo role → ``certificate``, ``issuing_ca``, ``serial_number``, ``expiration``."""
        return await self._request("POST", f"/v1/pki/sign/{role}", {
            "csr": csr, "common_name": cn, "exclude_cn_from_sans": True, "format": "pem"})

    async def transit_set_certificate(self, name: str, version: int, chain: str) -> None:
        """Gắn chuỗi chứng thư (lá rồi CA, PEM) vào đúng phiên bản khóa."""
        await self._request("POST", f"/v1/transit/keys/{name}/set-certificate",
                            {"version": version, "certificate_chain": chain})

    async def transit_sign(self, name: str, data: bytes, *, version: int) -> bytes:
        """Chữ ký RSA PKCS#1 v1.5 trên SHA-256(data) bằng đúng phiên bản khóa; két ghi sổ từng lần ký."""
        out = await self._request("POST", f"/v1/transit/sign/{name}/sha2-256", {
            "input": base64.b64encode(data).decode(), "signature_algorithm": "pkcs1v15", "key_version": version})
        prefix, _, sig = str(out.get("signature") or "").rpartition(":")
        if prefix != f"vault:v{version}":
            raise VaultError(f"két ký bằng phiên bản khóa khác ({prefix or 'không rõ'})", status=200)
        try:
            return base64.b64decode(sig, validate=True)
        except ValueError:
            raise VaultError("két trả chữ ký không đúng dạng", status=200) from None


# --- PDF: kiểm lúc tải lên, đóng dấu người xem lúc đọc -----------------------------------------------------------
# check_pdf, watermark đọc ngay trong tiến trình hiện tại — chỉ gọi trong tiến trình con hoặc với tệp tin cậy (test);
# svc-files gọi run_check_pdf, run_watermark.

def _out_of_memory(exc: BaseException) -> bool:
    """Lỗi vì hết bộ nhớ (vượt RLIMIT_AS): MemoryError của Python, hoặc lệnh hệ thống trả ENOMEM (mmap, tạo luồng).
    Không đoán theo lời báo lỗi: tệp hỏng có lời báo nhắc "alloc" vẫn là tệp hỏng."""
    return isinstance(exc, MemoryError) or (isinstance(exc, OSError) and exc.errno == errno.ENOMEM)


def _unreadable(exc: Exception, message: str) -> SealError:
    return SealError(f"{message}: {type(exc).__name__}", reason="memory" if _out_of_memory(exc) else "corrupt")


def check_pdf(data: bytes, max_pages: int | None = None) -> int:
    """Số trang nếu là PDF đọc được, không mật khẩu, không quá ``max_pages`` trang — tệp của văn bản hạn chế phải
    đóng dấu được khi xem."""
    if not data.startswith(b"%PDF-"):
        raise SealError("không phải tệp PDF", reason="not_pdf")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise SealError("PDF có mật khẩu", reason="password")
        pages = len(reader.pages)        # tệp không mã hóa: pypdf duyệt cây trang, số trang thật chứ không tin /Count
    except SealError:
        raise
    except Exception as exc:  # noqa: BLE001 — pypdf gặp tệp hỏng có thể ném đủ loại lỗi
        raise _unreadable(exc, "không đọc được PDF") from exc
    if pages == 0:
        raise SealError("PDF không có trang nào", reason="no_pages")
    if max_pages is not None and pages > max_pages:
        raise SealError(f"PDF có {pages} trang, quá {max_pages} trang", reason="too_many_pages")
    return pages


OVERLAY = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>
@page {{ size: {w}pt {h}pt; margin: 0; }}
html, body {{ margin: 0; font-family: "Liberation Sans", sans-serif; }}
.big {{ position: absolute; top: 42%; left: -10%; width: 120%; text-align: center; transform: rotate(-30deg);
        font-size: 24pt; font-weight: bold; color: rgba(170, 0, 0, 0.16); }}
.line {{ position: absolute; left: 10mm; right: 10mm; font-size: 7.5pt; color: rgba(130, 0, 0, 0.75); text-align: center; }}
.top {{ top: 4mm; }} .bottom {{ bottom: 4mm; }}
</style></head><body>
<div class="big">{who}<br>{when}</div>
<div class="line top">{top}</div>
<div class="line bottom">{bottom}</div>
</body></html>"""

# Chữ của lớp dấu theo loại bản xem: văn bản hạn chế (F3.7) và tệp trong phòng đọc hồ sơ đã nộp lưu (F3.8). Dòng trên
# có {who}, {when} (tên đã thoát HTML); dòng dưới cố định
STAMP_LINES = {
    "restricted": ("VĂN BẢN HẠN CHẾ — bản giải mã cho {who}, {when}",
                   "Không sao chép, chuyển tiếp. Không dùng cho bí mật nhà nước. "
                   "Mỗi lần xem đều ghi vào sổ kiểm toán."),
    "archive": ("PHÒNG ĐỌC — bản xem tài liệu lưu trữ cho {who}, {when}",
                "Chỉ để xem, không thay bản lưu trữ. Không sao chép, chuyển tiếp. "
                "Mỗi lần xem đều ghi vào sổ kiểm toán."),
}


def watermark(pdf: bytes, who: str, at: datetime, max_pages: int | None = None, kind: str = "restricted") -> bytes:
    """Đóng dấu tên người xem, giờ xem lên mọi trang của bản PDF đã giải mã (trong bộ nhớ). Quá ``max_pages`` trang
    (tệp tải lên trước khi có trần, hoặc trần vừa hạ) thì dừng trước khi chép trang nào. ``kind``: một khóa của
    STAMP_LINES — chữ của lớp dấu."""
    from weasyprint import HTML  # nạp chậm: chỉ đường xem văn bản hạn chế, phòng đọc cần

    when = at.astimezone(VN).strftime("%H:%M %d/%m/%Y")
    top, bottom = STAMP_LINES[kind]
    who_html = html.escape(who)
    stamps: dict[tuple[float, float], PageObject] = {}

    def stamp(w: float, h: float) -> PageObject:  # lớp dấu đúng cỡ trang (trang ngang không bị méo chữ)
        if (w, h) not in stamps:
            if len(stamps) >= MAX_STAMPS:
                return next(iter(stamps.values()))
            page = HTML(string=OVERLAY.format(who=who_html, when=when, w=w, h=h, bottom=bottom,
                                              top=top.format(who=who_html, when=when))).write_pdf()
            stamps[(w, h)] = PdfReader(io.BytesIO(page)).pages[0]
        return stamps[(w, h)]

    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted:
            raise SealError("PDF có mật khẩu, không đóng dấu được", reason="password")
        if max_pages is not None and len(reader.pages) > max_pages:
            raise SealError(f"PDF quá {max_pages} trang, không đóng dấu", reason="too_many_pages")
        writer = PdfWriter(clone_from=reader)
        for page in writer.pages:
            box = page.mediabox
            width, height = float(box.width), float(box.height)
            overlay = stamp(round(width, 1), round(height, 1))
            ow, oh = float(overlay.mediabox.width), float(overlay.mediabox.height)
            page.merge_transformed_page(overlay, Transformation().scale(width / ow, height / oh)
                                        .translate(float(box.left), float(box.bottom)))
        out = io.BytesIO()
        writer.write(out)
    except SealError:
        raise
    except Exception as exc:  # noqa: BLE001 — pypdf gặp tệp hỏng có thể ném đủ loại lỗi
        raise _unreadable(exc, "không đóng dấu được PDF") from exc
    return out.getvalue()


# --- tiến trình con -------------------------------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    """``python -I sealed.py check <max_pages> <memory_mb> <cpu_s>`` hoặc ``… stamp <max_pages> <memory_mb> <cpu_s>
    <tên người xem, JSON> <giờ xem, ISO> [loại dấu]``; PDF qua stdin. Ra stdout: một dòng JSON (``status`` ok kèm
    ``pages`` với check · failed kèm ``reason``), stamp ok thì sau dòng đó là bản có dấu. Loại dấu: khóa của
    STAMP_LINES, thiếu thì ``restricted``."""
    import resource

    op = argv[1]
    max_pages, memory_mb, cpu_s = (int(a) for a in argv[2:5])
    if op == "stamp":
        # nạp WeasyPrint trước khi đặt trần: dưới trần, dlopen thư viện pango không ánh xạ nổi lại báo "cannot open
        # shared object file" (OSError, không phải MemoryError) — hết bộ nhớ thành "tệp hỏng". Trần tính cả phần đã nạp
        import weasyprint  # noqa: F401
    memory = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    body = b""
    try:  # mọi việc sau khi đặt trần đều trong try: MemoryError không lọt ra thành mã thoát 1 ("corrupt")
        data = sys.stdin.buffer.read()
        if op == "check":
            head: dict[str, Any] = {"status": "ok", "pages": check_pdf(data, max_pages)}
        else:
            body = watermark(data, json.loads(argv[5]), datetime.fromisoformat(argv[6]), max_pages,
                             argv[7] if len(argv) > 7 else "restricted")
            head = {"status": "ok"}
    except SealError as exc:
        head = {"status": "failed", "reason": exc.reason}
    except Exception as exc:  # noqa: BLE001 — tệp hỏng kiểu gì cũng chỉ là "không đọc được"
        head = {"status": "failed", "reason": "memory" if _out_of_memory(exc) else "corrupt"}
    sys.stdout.buffer.write(json.dumps(head).encode() + b"\n")
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()
    return 0


# --- trong svc-files ------------------------------------------------------------------------------------------------

def _failed(reason: str, max_pages: int) -> SealError:
    message = f"PDF quá {max_pages} trang" if reason == "too_many_pages" else REASONS[reason]
    return SealError(message, reason=reason)


def _exit_reason(returncode: int | None) -> str:
    """Lý do khi tiến trình con không thoát 0. Chết vì tín hiệu: SIGXCPU (hết RLIMIT_CPU) → timeout, tín hiệu khác →
    memory. Khác ocr.py (tesseract đọc thẳng tệp, sập là tệp hỏng): ở đây tệp chỉ qua pypdf (Python thuần, zlib), mã C
    (pango, fontconfig của WeasyPrint) chỉ vẽ lớp dấu của mình — sập ở đó là hết bộ nhớ dưới RLIMIT_AS: GLib dừng bằng
    SIGABRT hay SIGTRAP tùy bản dựng, có khi SIGSEGV sau một malloc hỏng. EXIT_MEMORY → memory; mã khác → corrupt."""
    if returncode is not None and returncode < 0:
        return "timeout" if -returncode == signal.SIGXCPU else "memory"
    return "memory" if returncode == EXIT_MEMORY else "corrupt"


async def _isolated(op: str, data: bytes, extra: list[str], *, max_pages: int, timeout_s: float,
                    memory_mb: int) -> tuple[dict[str, Any], bytes]:
    """Chạy tệp này thành tiến trình con có giới hạn → (dòng JSON đầu, phần còn lại của stdout). Tệp không đọc được,
    quá nặng (hết giờ, hết CPU, hết bộ nhớ, tiến trình con sập), kết quả sai dạng: SealError mang ``reason``."""
    # nhập ở đây, không ở đầu tệp: tiến trình con chạy tệp này như script, không có gói svc_files
    from .docread.ocr import _kill_group

    timeout_s = max(timeout_s, 0.001)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-I", __file__, op, str(max_pages), str(memory_mb), str(int(timeout_s) + 5), *extra,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(data), timeout_s)
    except TimeoutError:
        _kill_group(proc)
        await proc.wait()
        raise _failed("timeout", max_pages) from None
    finally:
        # hết giờ, yêu cầu bị hủy, hay xong bình thường: không để tiến trình con chạy tiếp
        _kill_group(proc)
    rc = proc.returncode
    if rc != 0:
        raise _failed(_exit_reason(rc), max_pages)
    # kết quả của tiến trình con đọc tệp không tin cậy: kiểm dạng trước khi dùng
    line, _, body = out.partition(b"\n")
    try:
        head: dict[str, Any] = json.loads(line)
        status, reason = head["status"], head.get("reason")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise _failed("corrupt", max_pages) from None
    if status == "failed" and isinstance(reason, str) and reason in REASONS:
        raise _failed(reason, max_pages)
    if status != "ok":
        raise _failed("corrupt", max_pages)
    return head, body


async def run_check_pdf(data: bytes, *, max_pages: int, timeout_s: float = CHECK_TIMEOUT_S,
                        memory_mb: int = MEMORY_MB) -> int:
    """check_pdf trong tiến trình con có giới hạn → số trang. Không nhận được: SealError mang ``reason``."""
    head, _ = await _isolated("check", data, [], max_pages=max_pages, timeout_s=timeout_s, memory_mb=memory_mb)
    pages = head.get("pages")
    if type(pages) is not int or not 1 <= pages <= max_pages:
        raise _failed("corrupt", max_pages)
    return pages


async def run_watermark(pdf: bytes, who: str, at: datetime, *, max_pages: int, timeout_s: float = STAMP_TIMEOUT_S,
                        memory_mb: int = MEMORY_MB, kind: str = "restricted") -> bytes:
    """watermark trong tiến trình con có giới hạn; bản rõ vào qua stdin, bản có dấu ra qua stdout. Không đóng dấu
    được: SealError mang ``reason``. ``kind``: chữ của lớp dấu (STAMP_LINES) — phòng đọc hồ sơ nộp lưu dùng
    ``archive``."""
    if kind not in STAMP_LINES:
        raise ValueError(f"không có loại dấu {kind}")
    _, out = await _isolated("stamp", pdf, [json.dumps(who), at.isoformat(), kind], max_pages=max_pages,
                             timeout_s=timeout_s, memory_mb=memory_mb)
    if not out.startswith(b"%PDF-"):
        raise _failed("corrupt", max_pages)
    return out


if __name__ == "__main__":
    try:
        sys.exit(_main(sys.argv))
    except MemoryError:  # hết bộ nhớ cả lúc ghi kết quả: báo bằng mã thoát, việc này không cần cấp phát
        os._exit(EXIT_MEMORY)
