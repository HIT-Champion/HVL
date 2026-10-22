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

"""Gọi svc-files để dựng bản phát hành của văn bản đi (PDF có số, mã QR, SHA-256), để chép bản phát hành sang
đơn vị nhận khi liên thông văn bản trong hệ thống (F3.12), và để tìm văn bản đến tương tự cho tác tử gợi ý giao việc
(F4.3).

svc-files không tin mạng nội bộ (zero-trust): mỗi yêu cầu mang token của tài khoản dịch vụ svc-workflow, lấy
từ Keycloak bằng client credentials — cùng client dùng để đọc danh bạ, không thêm bí mật nào.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import httpx2

from .hasura import Actor


class FilesError(Exception):
    """svc-files không trả lời hoặc từ chối. code: ``detail.code`` trong thân lỗi của svc-files, nếu đọc được."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _detail_code(r: httpx2.Response) -> str | None:
    try:
        body = r.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    code = detail.get("code") if isinstance(detail, dict) else None
    return str(code) if code else None


# svc-files từ chối chép (409): dòng liên thông không còn chờ, văn bản chưa phát hành, văn bản hạn chế hoặc tệp đã mã
# hóa, tệp đã sang kho lạnh, băm của byte đọc ra không khớp
DISPATCH_REFUSALS = frozenset({"not_pending", "not_issued", "restricted", "cold", "integrity"})
# 422: trạm quét chặn bản phát hành lúc chép (mẫu mã độc mới, giới hạn quét đổi) — chép lại cũng bị chặn
DISPATCH_BLOCKED = frozenset({"infected", "unscannable"})
# thử lại cũng ra đúng lỗi đó: dòng liên thông thành failed thay vì chờ mãi (dòng chờ còn chặn nộp lưu văn bản gửi)
DISPATCH_FINAL = (DISPATCH_REFUSALS - {"not_pending"}) | DISPATCH_BLOCKED


class DispatchFileError(FilesError):
    """svc-files chưa chép được tệp phát hành sang đơn vị nhận.

    code: một mã trong DISPATCH_REFUSALS (409), DISPATCH_BLOCKED (422), ``unavailable`` (503, không gọi được) hoặc
    ``http_<mã>``.
    message: câu tiếng Việt ngắn, ghi vào ``last_error`` của dòng liên thông — người dùng thấy ở thẻ "Liên thông".
    """

    def __init__(self, code: str, message: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(message, status)
        self.code = code
        self.message = message
        self.detail = detail  # nguyên văn để ghi nhật ký, không đưa ra giao diện


class ServiceToken:
    """Access token của tài khoản dịch vụ; dùng lại tới gần lúc hết hạn.

    Hạn tính theo giờ thật (``time.time``) như ``exp`` của token, không theo ``time.monotonic``: đồng hồ monotonic đứng
    yên khi máy ngủ hay VM bị tạm dừng, thức dậy token đã hết hạn mà vẫn tưởng còn."""

    def __init__(self, keycloak_url: str, realm: str, client_id: str, client_secret: str, *,
                 transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._path = f"/realms/{realm}/protocol/openid-connect/token"
        self._form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
        self._http = httpx2.AsyncClient(base_url=keycloak_url, timeout=15, transport=transport)
        self._token = ""
        self._expires_at = 0.0
        self._lock = asyncio.Lock()          # nhiều lời gọi cùng lúc thấy token hết hạn: chỉ một lần hỏi Keycloak

    async def aclose(self) -> None:
        await self._http.aclose()

    def forget(self, token: str) -> None:
        """Bỏ ``token`` nếu vẫn đang giữ nó (lời gọi khác có thể đã lấy token mới): lần ``get`` sau lấy token mới."""
        if self._token == token:
            self._token = ""

    async def get(self) -> str:
        async with self._lock:
            if self._token and time.time() < self._expires_at:
                return self._token
            try:
                r = await self._http.post(self._path, data=self._form)
            except httpx2.HTTPError as exc:
                raise FilesError(f"Không gọi được Keycloak: {exc}") from exc
            if r.status_code != 200:
                raise FilesError(f"Keycloak từ chối tài khoản dịch vụ: HTTP {r.status_code}", r.status_code)
            body = r.json()
            self._token = body["access_token"]
            # trừ hao 30 giây: token không hết hạn giữa đường
            self._expires_at = time.time() + max(float(body.get("expires_in", 60)) - 30, 0)
            return self._token


class FilesClient:
    def __init__(self, base_url: str, token: ServiceToken, *, timeout_s: float = 60.0,
                 transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._token = token
        self._http = httpx2.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._token.aclose()

    async def _post(self, path: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> httpx2.Response:
        """POST kèm token dịch vụ. svc-files trả 401 — token hết hạn sớm hơn ta tính (đồng hồ bị chỉnh, khóa Keycloak
        đổi) — thì bỏ token, lấy token mới, gửi lại đúng một lần: 401 nghĩa là svc-files chưa làm gì. Lỗi mạng
        (``httpx2.HTTPError``) đi thẳng lên để từng hàm báo theo cách của nó."""
        for attempt in (1, 2):
            token = await self._token.get()
            r = await self._http.post(path, headers={**(headers or {}), "Authorization": f"Bearer {token}"}, json=body)
            if r.status_code != 401 or attempt == 2:
                break
            self._token.forget(token)
        return r

    async def issue(self, actor: Actor, document_id: str) -> dict[str, Any]:
        """Dựng PDF phát hành từ dữ liệu trong CSDL, quét, lưu → {file_id, sha256, size_bytes}."""
        headers = {"X-Request-Id": actor.request_id} if actor.request_id else {}
        try:
            r = await self._post("/internal/issue", {
                "tenant_id": str(actor.tenant_id),
                "document_id": str(uuid.UUID(document_id)),
                "actor_id": actor.user_id,
            }, headers)
        except httpx2.HTTPError as exc:
            raise FilesError(f"Không gọi được svc-files: {exc}") from exc
        if r.status_code != 201:
            raise FilesError(f"svc-files trả {r.status_code}: {r.text[:300]}", r.status_code)
        return r.json()

    async def similar(self, tenant_id: uuid.UUID, document_id: str, *, limit: int = 15) -> dict[str, Any]:
        """Tác tử gợi ý giao việc (F4.3): văn bản đến tương tự văn bản này đã giao xử lý →
        ``{document_id, hits: [{document_id, score}], terms, semantic, duration_ms}``.

        svc-files tự đọc trích yếu bằng vai trò service và chỉ trả id với điểm (đã loại chính nó, văn bản hạn chế, văn
        bản chưa giao) — không chữ nào của văn bản đi qua đây. Lỗi: ``FilesError`` có ``status`` và ``code`` (404
        ``not_found``, 409 ``not_incoming``/``restricted``, 503 ``assistant_disabled``/``search_unavailable``…).
        """
        try:
            r = await self._post("/internal/similar-documents", {
                "tenant_id": str(tenant_id),
                "document_id": str(uuid.UUID(document_id)),
                "limit": limit,
            })
        except httpx2.HTTPError as exc:
            raise FilesError(f"Không gọi được svc-files: {exc}") from exc
        if r.status_code != 200:
            raise FilesError(f"svc-files trả {r.status_code}: {r.text[:300]}", r.status_code, _detail_code(r))
        return r.json()

    async def dispatch_file(self, dispatch_id: str, *, actor_id: str = "svc-workflow") -> dict[str, Any]:
        """Liên thông (F3.12): chép tệp phát hành của văn bản nguồn sang thuê ước nhận → {file_id, sha256, size_bytes}.

        svc-files tự đọc dòng liên thông và tệp phát hành bằng khóa quản trị: bên gọi chỉ nói dòng nào, không chỉ
        định được tệp. Bản sao mang id định trước trong dòng (``dispatches.file_id``) nên gọi lại không chép hai lần —
        201 lần đầu, 200 khi đã có.
        """
        try:
            r = await self._post("/internal/dispatch-file", {
                "dispatch_id": str(uuid.UUID(dispatch_id)),
                "actor_id": actor_id,
            })
        except httpx2.HTTPError as exc:
            raise DispatchFileError("unavailable", "Chưa gọi được dịch vụ tệp, sẽ thử lại",
                                    detail=f"Không gọi được svc-files: {exc}") from exc
        if r.status_code in (200, 201):
            return r.json()
        try:
            body = r.json()
        except ValueError:
            body = None
        detail = body.get("detail") if isinstance(body, dict) else None
        detail = detail if isinstance(detail, dict) else {}
        text = f"svc-files trả {r.status_code}: {r.text[:300]}"
        if r.status_code == 409 and detail.get("code") in DISPATCH_REFUSALS:
            message = str(detail.get("message") or detail["code"])[:300]
            raise DispatchFileError(str(detail["code"]), message, 409, text)
        if r.status_code == 422 and detail.get("code") in DISPATCH_BLOCKED:
            raise DispatchFileError(str(detail["code"]), "Trạm quét mã độc chặn bản phát hành khi chép sang đơn vị nhận",
                                    422, text)
        if r.status_code == 503:
            raise DispatchFileError("unavailable", "Kho tệp hoặc trạm quét chưa sẵn sàng, sẽ thử lại", 503, text)
        raise DispatchFileError(f"http_{r.status_code}", f"Dịch vụ tệp trả lỗi {r.status_code}, sẽ thử lại",
                                r.status_code, text)
