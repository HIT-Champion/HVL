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
"""

from __future__ import annotations

import asyncio
import base64
import html
import io
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx2
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pypdf import PageObject, PdfReader, PdfWriter, Transformation

MAGIC = b"MOC1"
NONCE = 12
VN = timezone(timedelta(hours=7))
MAX_STAMPS = 8          # số cỡ trang khác nhau được dựng lớp dấu riêng; nhiều hơn thì co giãn lớp dấu đầu tiên


class SealError(Exception):
    """Bản mã hỏng, sai khóa hoặc không thuộc tệp này; hoặc PDF không đọc được để đóng dấu."""


class VaultError(Exception):
    """Két chưa sẵn sàng hoặc từ chối."""


def _aad(tenant_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    return tenant_id.bytes + file_id.bytes


def seal(plain: bytes, key: bytes, tenant_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    nonce = os.urandom(NONCE)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plain, _aad(tenant_id, file_id))


def unseal(blob: bytes, key: bytes, tenant_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + NONCE + 16:
        raise SealError("không phải bản mã của Mộc")
    nonce = blob[len(MAGIC):len(MAGIC) + NONCE]
    try:
        return AESGCM(key).decrypt(nonce, blob[len(MAGIC) + NONCE:], _aad(tenant_id, file_id))
    except (InvalidTag, ValueError) as exc:  # sai khóa, bản mã bị sửa, của tệp khác; khóa sai độ dài
        raise SealError("bản mã không khớp khóa hoặc tệp") from exc


class Vault:
    """Khóa dữ liệu từ transit của két. Đăng nhập AppRole khi cần (token 1 giờ, giữ trong bộ nhớ, dùng lại tới gần
    hết hạn); đọc lại role_id/secret_id mỗi lần đăng nhập vì két cấp secret_id mới mỗi lần khởi động."""

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

    async def _login(self) -> str:
        try:
            role_id, secret_id = (p.read_text().strip() for p in self._files)
        except OSError as exc:
            raise VaultError(f"không đọc được thông tin đăng nhập két: {exc}") from None
        r = await self._http.post("/v1/auth/approle/login", json={"role_id": role_id, "secret_id": secret_id})
        if r.status_code != 200:
            raise VaultError(f"két từ chối đăng nhập AppRole: HTTP {r.status_code}")
        auth = r.json()["auth"]
        self._token = str(auth["client_token"])
        self._until = time.monotonic() + max(30.0, float(auth.get("lease_duration") or 0) * 0.8)
        return self._token

    async def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        try:
            for attempt in (1, 2):
                async with self._lock:
                    token = self._token if self._token and time.monotonic() < self._until else await self._login()
                r = await self._http.post(path, json=body, headers={"X-Vault-Token": token})
                if r.status_code == 403 and attempt == 1:  # token bị thu hồi (két khởi động lại): đăng nhập lại
                    self._token = None
                    continue
                if r.status_code != 200:
                    raise VaultError(f"két trả HTTP {r.status_code} ở {path}")
                data = r.json()["data"]
                if not isinstance(data, dict):
                    raise VaultError(f"két trả dữ liệu lạ ở {path}")
                return data
        except httpx2.HTTPError as exc:
            raise VaultError(f"không gọi được két: {type(exc).__name__}") from None
        except (KeyError, TypeError, ValueError) as exc:  # thân trả về không phải JSON đúng dạng
            raise VaultError(f"két trả dữ liệu lạ ở {path}: {type(exc).__name__}") from None
        raise VaultError("két từ chối sau khi đăng nhập lại")

    async def datakey(self) -> tuple[bytes, str]:
        """Khóa dữ liệu mới → (khóa rõ 32 byte, khóa đã bọc ``vault:v1:…``)."""
        data = await self._post(f"/v1/transit/datakey/plaintext/{self.key}", {"bits": 256})
        try:
            key, wrapped = base64.b64decode(str(data["plaintext"]), validate=True), str(data["ciphertext"])
        except (KeyError, ValueError) as exc:
            raise VaultError(f"két trả khóa dữ liệu lạ: {type(exc).__name__}") from None
        if len(key) != 32 or not wrapped.startswith("vault:v"):
            raise VaultError("két trả khóa dữ liệu không đúng dạng")
        return key, wrapped

    async def unwrap(self, wrapped: str) -> bytes:
        """Khóa đã bọc → khóa rõ; két ghi sổ mỗi lần mở."""
        data = await self._post(f"/v1/transit/decrypt/{self.key}", {"ciphertext": wrapped})
        try:
            return base64.b64decode(str(data["plaintext"]), validate=True)
        except (KeyError, ValueError) as exc:
            raise VaultError(f"két trả khóa rõ lạ: {type(exc).__name__}") from None


# --- PDF: kiểm lúc tải lên, đóng dấu người xem lúc đọc -----------------------------------------------------------

def check_pdf(data: bytes) -> int:
    """Số trang nếu là PDF đọc được, không mật khẩu — tệp của văn bản hạn chế phải đóng dấu được khi xem."""
    if not data.startswith(b"%PDF-"):
        raise SealError("không phải tệp PDF")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise SealError("PDF có mật khẩu")
        pages = len(reader.pages)
    except SealError:
        raise
    except Exception as exc:  # noqa: BLE001 — pypdf gặp tệp hỏng có thể ném đủ loại lỗi
        raise SealError(f"không đọc được PDF: {type(exc).__name__}") from exc
    if pages == 0:
        raise SealError("PDF không có trang nào")
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
<div class="line top">VĂN BẢN HẠN CHẾ — bản giải mã cho {who}, {when}</div>
<div class="line bottom">Không sao chép, chuyển tiếp. Không dùng cho bí mật nhà nước. Mỗi lần xem đều ghi vào sổ kiểm toán.</div>
</body></html>"""


def watermark(pdf: bytes, who: str, at: datetime) -> bytes:
    """Đóng dấu tên người xem, giờ xem lên mọi trang của bản PDF đã giải mã (trong bộ nhớ)."""
    from weasyprint import HTML  # nạp chậm: chỉ đường xem văn bản hạn chế cần

    when = at.astimezone(VN).strftime("%H:%M %d/%m/%Y")
    stamps: dict[tuple[float, float], PageObject] = {}

    def stamp(w: float, h: float) -> PageObject:  # lớp dấu đúng cỡ trang (trang ngang không bị méo chữ)
        if (w, h) not in stamps:
            if len(stamps) >= MAX_STAMPS:
                return next(iter(stamps.values()))
            page = HTML(string=OVERLAY.format(who=html.escape(who), when=when, w=w, h=h)).write_pdf()
            stamps[(w, h)] = PdfReader(io.BytesIO(page)).pages[0]
        return stamps[(w, h)]

    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted:
            raise SealError("PDF có mật khẩu, không đóng dấu được")
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
        raise SealError(f"không đóng dấu được PDF: {type(exc).__name__}") from exc
    return out.getvalue()
