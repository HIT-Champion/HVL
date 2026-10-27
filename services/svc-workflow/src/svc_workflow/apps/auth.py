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

"""Kiểm JWT Keycloak cho API quy trình của ứng dụng (``/api/workflow/{app}/…``), như ``svc-files/auth.py``.

APISIX đã kiểm token ở biên (route ``svc-workflow``, plugin openid-connect), dịch vụ vẫn kiểm lại (zero-trust): chữ
ký theo JWKS của realm, ``iss``, hạn. Thêm một điều: ``azp`` (client cấp token) phải là ``app-<tên>`` — client công
khai ``moc app install`` tạo cho trang của đúng ứng dụng đó. Token của Văn phòng điện tử hay của ứng dụng khác không
dùng được ở đây, nên ứng dụng này không đọc, không làm được việc của ứng dụng kia. Người dùng, thuê ước, phòng, vai trò
lấy từ claim Hasura do mapper của realm đặt (mo-hinh-du-lieu.md §3), không lấy từ dữ liệu client gửi lên.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import jwt

HASURA_CLAIMS = "https://hasura.io/jwt/claims"
ALGORITHMS = ["RS256", "PS256", "ES256"]


class AuthError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AppUser:
    """Người gọi API quy trình qua trang của một ứng dụng."""

    user_id: str
    tenant_id: uuid.UUID
    role: str
    department_id: uuid.UUID | None
    client: str

    @property
    def groups(self) -> list[str]:
        """Nhóm ứng viên Flowable của người này, đúng hai dạng BPMN của ứng dụng được dùng (apps/bpmn.py):
        ``t:<thuê ước>:<vai trò>`` và ``t:<thuê ước>:d:<phòng>:<vai trò>``. Bao trùm ``hasura.Actor.groups`` của
        Văn phòng (lãnh đạo đơn vị, văn thư theo đơn vị; lãnh đạo phòng theo phòng)."""
        if not self.role:
            return []
        out = [f"t:{self.tenant_id}:{self.role}"]
        if self.department_id:
            out.append(f"t:{self.tenant_id}:d:{self.department_id}:{self.role}")
        return out


def default_role(claim: object, roles: tuple[str, ...]) -> str:
    """Vai trò mặc định nếu nằm trong allowed-roles; thiếu claim thì vai trò duy nhất; còn lại rỗng (như svc-files)."""
    if isinstance(claim, str) and claim:
        return claim if claim in roles else ""
    return roles[0] if len(roles) == 1 else ""


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class TokenVerifier:
    def __init__(self, issuer: str, jwks_url: str, *, keys: SigningKeySource | None = None,
                 leeway_s: int = 30) -> None:
        self.issuer = issuer
        self.leeway_s = leeway_s
        self._keys = keys or jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5)

    def verify(self, token: str, app: str) -> AppUser:
        claims = self._decode(token)
        client = str(claims.get("azp") or "")
        if client != f"app-{app}":
            raise AuthError(403, "wrong_client", f"Token không phải của ứng dụng {app} (cần đăng nhập qua trang của "
                                                 f"ứng dụng, client app-{app})")
        ns = claims.get(HASURA_CLAIMS)
        if not isinstance(ns, dict):
            ns = {}
        try:
            tenant_id = uuid.UUID(str(ns.get("x-hasura-tenant-id")))
        except ValueError as exc:
            raise AuthError(403, "no_tenant", "Tài khoản chưa được gán đơn vị (tenant_id)") from exc
        raw_roles = ns.get("x-hasura-allowed-roles") or []
        roles = tuple(str(r) for r in raw_roles) if isinstance(raw_roles, list) else ()
        try:
            dept = uuid.UUID(str(ns["x-hasura-department-id"])) if ns.get("x-hasura-department-id") else None
        except ValueError:
            dept = None
        return AppUser(user_id=str(ns.get("x-hasura-user-id") or claims["sub"]), tenant_id=tenant_id,
                       role=default_role(ns.get("x-hasura-default-role"), roles), department_id=dept, client=client)

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            key = self._keys.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=ALGORITHMS, issuer=self.issuer, leeway=self.leeway_s,
                              options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False})
        except jwt.PyJWKClientConnectionError as exc:
            raise AuthError(503, "jwks_unavailable", "Không lấy được khóa công khai của Keycloak") from exc
        except jwt.PyJWTError as exc:
            raise AuthError(401, "invalid_token", "Token không hợp lệ hoặc đã hết hạn") from exc
