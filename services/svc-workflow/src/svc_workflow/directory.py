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

"""Đồng bộ danh bạ Keycloak → core.users.

Keycloak là nguồn sự thật về người dùng; bảng core.users chỉ để giao diện chọn người được giao việc và hiện
tên trên dòng thời gian. Mỗi lượt: đọc toàn bộ người dùng của realm (tài khoản dịch vụ svc-workflow, quyền
view-users), so với bảng theo từng thuê ước, chỉ ghi dòng thay đổi — sổ kiểm toán không bị nhiễu.
Người bị xóa hoặc khóa trong Keycloak thì đánh dấu enabled = false, không xóa dòng (dòng thời gian cũ
vẫn hiện được tên). Số điện thoại (thuộc tính ``phone_number``, cho kênh SMS #365) đưa về dạng E.164; số không đọc
được thì để trống, như chưa nhập.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import defaultdict
from typing import Any

import httpx2

from .hasura import TENANT_USERS, UPSERT_USERS, Actor, HasuraClient, HasuraError

ROLES = {"clerk", "staff", "manager", "director", "tenant_admin"}
PAGE = 100
E164 = re.compile(r"\+[1-9][0-9]{7,14}")      # khớp ràng buộc users_phone của core.users

log = logging.getLogger("svc_workflow")


class DirectoryError(Exception):
    pass


def _first(attrs: dict[str, list[str]], name: str) -> str | None:
    values = attrs.get(name) or []
    return values[0] if values else None


def phone(value: str | None) -> str | None:
    """Số điện thoại nhập tay → E.164. Số bắt đầu bằng 0 là số trong nước (+84); 00 là tiền tố gọi quốc tế."""
    digits = re.sub(r"[\s.()-]", "", value or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("0"):
        digits = "+84" + digits[1:]
    return digits if E164.fullmatch(digits) else None


def to_row(user: dict[str, Any]) -> tuple[uuid.UUID, dict[str, Any]] | None:
    """Người dùng Keycloak → (thuê ước, dòng core.users); None nếu chưa gán đơn vị hoặc vai trò."""
    attrs = user.get("attributes") or {}
    role = _first(attrs, "moc_role")
    try:
        tenant = uuid.UUID(_first(attrs, "tenant_id") or "")
    except ValueError:
        return None
    if role not in ROLES:
        return None
    dept = _first(attrs, "department_id")
    try:
        dept = str(uuid.UUID(dept)) if dept else None
    except ValueError:
        dept = None
    name = " ".join(p for p in (user.get("firstName"), user.get("lastName")) if p) or user["username"]
    return tenant, {
        "id": user["id"],
        "department_id": dept,
        "username": user["username"],
        "full_name": name,
        "email": user.get("email"),
        "phone": phone(_first(attrs, "phone_number")),
        "role": role,
        "enabled": bool(user.get("enabled", True)),
    }


class Directory:
    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        hasura: HasuraClient,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.hasura = hasura
        self._http = httpx2.AsyncClient(base_url=keycloak_url, timeout=15, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _token(self) -> str:
        r = await self._http.post(
            f"/realms/{self.realm}/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": self.client_id,
                  "client_secret": self.client_secret},
        )
        if r.status_code != 200:
            raise DirectoryError(f"Keycloak từ chối tài khoản dịch vụ: HTTP {r.status_code}")
        return r.json()["access_token"]

    async def fetch_users(self) -> list[dict[str, Any]]:
        try:
            headers = {"Authorization": f"Bearer {await self._token()}"}
            users: list[dict[str, Any]] = []
            while True:
                r = await self._http.get(
                    f"/admin/realms/{self.realm}/users",
                    params={"first": len(users), "max": PAGE, "briefRepresentation": "false"},
                    headers=headers,
                )
                if r.status_code != 200:
                    raise DirectoryError(f"Không đọc được danh bạ Keycloak: HTTP {r.status_code}")
                page = r.json()
                users.extend(page)
                if len(page) < PAGE:
                    return users
        except httpx2.HTTPError as exc:
            raise DirectoryError(f"Không gọi được Keycloak: {exc}") from exc

    async def sync_once(self) -> int:
        """Một lượt đồng bộ; trả về số dòng đã ghi."""
        wanted: dict[uuid.UUID, dict[str, dict[str, Any]]] = defaultdict(dict)
        for user in await self.fetch_users():
            mapped = to_row(user)
            if mapped:
                tenant, row = mapped
                wanted[tenant][row["id"]] = row
        written = 0
        for tenant, rows in wanted.items():
            actor = Actor("svc-workflow", tenant, "service", None)
            try:
                current = {u["id"]: u for u in (await self.hasura.as_service(actor, TENANT_USERS))["core_users"]}
                changed = [r for r in rows.values() if current.get(r["id"]) != r]
                changed += [{**u, "enabled": False} for uid, u in current.items() if uid not in rows and u["enabled"]]
                if changed:
                    await self.hasura.as_service(actor, UPSERT_USERS, {"rows": changed})
                    written += len(changed)
            except HasuraError as exc:
                # thường là thuê ước chưa có trong core.tenants: bỏ qua thuê ước đó, không dừng cả lượt
                log.warning(json.dumps({"event": "core.directory.tenant_failed", "tenant_id": str(tenant),
                                        "error": str(exc)}, ensure_ascii=False))
        return written

    async def run(self, interval_s: float) -> None:
        while True:
            try:
                count = await self.sync_once()
                if count:
                    log.info(json.dumps({"event": "core.directory.synced", "users": count}))
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết; lượt sau thử lại
                log.warning(json.dumps({"event": "core.directory.sync_failed", "error": str(exc)}, ensure_ascii=False))
            await asyncio.sleep(interval_s)
