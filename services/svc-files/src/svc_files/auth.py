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

"""Kiểm JWT do Keycloak cấp.

APISIX đã kiểm token ở biên, nhưng dịch vụ vẫn kiểm lại (zero-trust): mạng nội bộ
không được coi là tin cậy. Thuê ước và người dùng lấy từ claim của Hasura
(mo-hinh-du-lieu.md §3), không bao giờ lấy từ dữ liệu client gửi lên.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
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
class Principal:
    user_id: str
    tenant_id: uuid.UUID
    roles: tuple[str, ...]
    department_id: str | None = None
    # Tên hiển thị (claim name, preferred_username của Keycloak): in lên bản xem văn bản hạn chế (F3.7)
    display_name: str = ""
    # Token gốc, để hỏi Hasura thay mặt người dùng (quyền do Hasura quyết, không viết lại ở đây).
    token: str = field(default="", repr=False, compare=False)


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class TokenVerifier:
    def __init__(
        self,
        issuer: str,
        jwks_url: str,
        audience: str | None = None,
        *,
        keys: SigningKeySource | None = None,
        leeway_s: int = 30,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.leeway_s = leeway_s
        self._keys = keys or jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5)

    def verify(self, token: str) -> Principal:
        claims = self._decode(token)
        ns = claims.get(HASURA_CLAIMS)
        if not isinstance(ns, dict):
            ns = {}
        tenant_raw = ns.get("x-hasura-tenant-id")
        try:
            tenant_id = uuid.UUID(str(tenant_raw))
        except ValueError as exc:
            raise AuthError(403, "no_tenant", "Tài khoản chưa được gán đơn vị (tenant_id)") from exc

        roles = ns.get("x-hasura-allowed-roles") or []
        name = " ".join(str(claims.get("name") or "").split())[:120]
        login = " ".join(str(claims.get("preferred_username") or "").split())[:60]
        display = f"{name} ({login})" if name and login and login != name else name or login
        return Principal(
            user_id=str(ns.get("x-hasura-user-id") or claims["sub"]),
            tenant_id=tenant_id,
            roles=tuple(str(r) for r in roles) if isinstance(roles, list) else (),
            department_id=ns.get("x-hasura-department-id"),
            display_name=display,
            token=token,
        )

    def verify_service(self, token: str, clients: frozenset[str]) -> str:
        """Token tài khoản dịch vụ (client credentials của Keycloak): trả client_id nếu được phép gọi API nội bộ.

        Người dùng không lấy được token mang client_id của dịch vụ khi không có bí mật của client đó.
        """
        claims = self._decode(token)
        client = claims.get("azp") or claims.get("client_id")
        if client not in clients:
            raise AuthError(403, "not_a_service", "Chỉ dịch vụ nội bộ được gọi")
        return str(client)

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            key = self._keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway_s,
                options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": self.audience is not None},
            )
        except jwt.PyJWKClientConnectionError as exc:
            raise AuthError(503, "jwks_unavailable", "Không lấy được khóa công khai của Keycloak") from exc
        except jwt.PyJWTError as exc:
            raise AuthError(401, "invalid_token", "Token không hợp lệ hoặc đã hết hạn") from exc
        return claims
