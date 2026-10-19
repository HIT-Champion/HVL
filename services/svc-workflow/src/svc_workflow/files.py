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

"""Gọi svc-files để dựng bản phát hành của văn bản đi (PDF có số, mã QR, SHA-256).

svc-files không tin mạng nội bộ (zero-trust): mỗi yêu cầu mang token của tài khoản dịch vụ svc-workflow, lấy
từ Keycloak bằng client credentials — cùng client dùng để đọc danh bạ, không thêm bí mật nào.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx2

from .hasura import Actor


class FilesError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ServiceToken:
    """Access token của tài khoản dịch vụ; dùng lại tới gần lúc hết hạn."""

    def __init__(self, keycloak_url: str, realm: str, client_id: str, client_secret: str, *,
                 transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._path = f"/realms/{realm}/protocol/openid-connect/token"
        self._form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
        self._http = httpx2.AsyncClient(base_url=keycloak_url, timeout=15, transport=transport)
        self._token = ""
        self._expires_at = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self) -> str:
        if self._token and time.monotonic() < self._expires_at:
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
        self._expires_at = time.monotonic() + max(float(body.get("expires_in", 60)) - 30, 0)
        return self._token


class FilesClient:
    def __init__(self, base_url: str, token: ServiceToken, *, timeout_s: float = 60.0,
                 transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._token = token
        self._http = httpx2.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._token.aclose()

    async def issue(self, actor: Actor, document_id: str) -> dict[str, Any]:
        """Dựng PDF phát hành từ dữ liệu trong CSDL, quét, lưu → {file_id, sha256, size_bytes}."""
        headers = {"Authorization": f"Bearer {await self._token.get()}"}
        if actor.request_id:
            headers["X-Request-Id"] = actor.request_id
        try:
            r = await self._http.post("/internal/issue", headers=headers, json={
                "tenant_id": str(actor.tenant_id),
                "document_id": str(uuid.UUID(document_id)),
                "actor_id": actor.user_id,
            })
        except httpx2.HTTPError as exc:
            raise FilesError(f"Không gọi được svc-files: {exc}") from exc
        if r.status_code != 201:
            raise FilesError(f"svc-files trả {r.status_code}: {r.text[:300]}", r.status_code)
        return r.json()
