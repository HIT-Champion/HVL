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

"""Test schema và quyền trên PostgreSQL + Hasura thật (dựng bằng db/tests/stack.sh).

Token ký HS256 bằng khóa chỉ dùng cho test — Hasura của bản chạy thật kiểm token Keycloak (RS256) qua
JWKS, nhưng đọc cùng một khối claim nên quyền được kiểm đúng như thật. Chỉ dùng thư viện chuẩn để gọi
HTTP và ký token, nên chỉ cần cài pytest.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

import pytest

HASURA_URL = os.environ.get("MOC_IT_HASURA_URL", "http://127.0.0.1:18080")
ADMIN_SECRET = os.environ.get("MOC_IT_HASURA_ADMIN_SECRET", "it-admin-secret")
JWT_KEY = os.environ.get("MOC_IT_JWT_KEY", "it-only-hs256-key-not-for-production-0123456789").encode()
ISSUER = os.environ.get("MOC_IT_ISSUER", "https://moc.example/realms/moc")
CLAIMS = "https://hasura.io/jwt/claims"


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MOC_IT") == "1":
        return
    skip = pytest.mark.skip(reason="cần PostgreSQL + Hasura đang chạy: db/tests/stack.sh up, rồi đặt MOC_IT=1")
    for item in items:
        item.add_marker(skip)


class GraphQLError(Exception):
    def __init__(self, errors: list[dict]):
        super().__init__("; ".join(e.get("message", "?") for e in errors))
        self.errors = errors


class SQLError(Exception):
    pass


def _post(path: str, body: dict, headers: dict[str, str]) -> tuple[int, dict]:
    req = urllib.request.Request(
        HASURA_URL + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def sql(statement: str) -> list[list[str]]:
    """Chạy SQL bằng quyền quản trị Hasura (run_sql), trả các dòng kết quả, bỏ dòng tiêu đề."""
    status, body = _post(
        "/v2/query",
        {"type": "run_sql", "args": {"source": "default", "sql": statement}},
        {"X-Hasura-Admin-Secret": ADMIN_SECRET},
    )
    if status != 200:
        internal = body.get("internal", {}).get("error", {})
        raise SQLError(internal.get("message") or body.get("error") or str(body))
    rows = body.get("result") or []
    return rows[1:]


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_token(sub: str, role: str, tenant: str | None, department: str | None = None,
               *, roles: list[str] | None = None, ttl: int = 300) -> str:
    now = int(time.time())
    hasura = {
        "x-hasura-allowed-roles": roles or [role],
        "x-hasura-default-role": role,
        "x-hasura-user-id": sub,
    }
    if tenant is not None:
        hasura["x-hasura-tenant-id"] = tenant
    if department is not None:
        hasura["x-hasura-department-id"] = department
    claims = {"sub": sub, "iss": ISSUER, "iat": now, "exp": now + ttl, CLAIMS: hasura}
    head = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64url(json.dumps(claims).encode())
    sig = b64url(hmac.new(JWT_KEY, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def gql_raw(query: str, variables: dict | None = None, *, headers: dict[str, str]) -> dict:
    _, body = _post("/v1/graphql", {"query": query, "variables": variables or {}}, headers)
    return body


@dataclass(frozen=True)
class User:
    sub: str
    role: str
    tenant: str
    department: str | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + make_token(self.sub, self.role, self.tenant, self.department)}

    def raw(self, query: str, variables: dict | None = None, **extra_headers: str) -> dict:
        return gql_raw(query, variables, headers={**self.headers, **extra_headers})

    def gql(self, query: str, variables: dict | None = None) -> dict:
        body = self.raw(query, variables)
        if "errors" in body:
            raise GraphQLError(body["errors"])
        return body["data"]


@dataclass(frozen=True)
class Service(User):
    """svc-workflow / svc-files: khóa quản trị + vai trò service + thuê ước của yêu cầu đang xử lý."""

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-Hasura-Admin-Secret": ADMIN_SECRET,
            "X-Hasura-Role": "service",
            "X-Hasura-Tenant-Id": self.tenant,
            "X-Hasura-User-Id": self.sub,
        }


@dataclass(frozen=True)
class Agent(Service):
    """Tác tử đọc văn bản đến trong svc-files (F4.1): khóa quản trị + vai trò agent + thuê ước của văn thư bấm đọc;
    sub là danh tính tác tử (MOC_AGENT_ID, mặc định moc-doc-reader)."""

    @property
    def headers(self) -> dict[str, str]:
        return {**super().headers, "X-Hasura-Role": "agent"}


@dataclass(frozen=True)
class World:
    tenant_a: str
    tenant_b: str
    dept_a1: str
    dept_a2: str
    dept_b1: str
    clerk_a: User
    director_a: User
    manager_a1: User
    manager_a2: User
    staff_a1: User
    staff_a1b: User
    staff_a2: User
    admin_a: User
    clerk_b: User
    service_a: Service
    service_b: Service
    tag: str


def _new_tenant(tag: str, label: str) -> str:
    return sql(f"insert into core.tenants (code, name) values ('{label}{tag}', 'Đơn vị thử {label}') returning id")[0][0]


def _new_department(tenant: str, code: str, name: str) -> str:
    return sql(
        f"insert into office.departments (tenant_id, code, name) values ('{tenant}', '{code}', '{name}') returning id"
    )[0][0]


@pytest.fixture(scope="session")
def world() -> World:
    tag = uuid.uuid4().hex[:6].upper()
    ta, tb = _new_tenant(tag, "A"), _new_tenant(tag, "B")
    a1 = _new_department(ta, "ĐT", "Phòng Đào tạo")
    a2 = _new_department(ta, "TCHC", "Phòng Tổ chức – Hành chính")
    b1 = _new_department(tb, "ĐT", "Phòng Đào tạo")

    def user(name: str, role: str, tenant: str, dept: str | None = None) -> User:
        return User(f"{name}-{tag}", role, tenant, dept)

    return World(
        tenant_a=ta, tenant_b=tb, dept_a1=a1, dept_a2=a2, dept_b1=b1,
        clerk_a=user("van-thu-a", "clerk", ta),
        director_a=user("hieu-truong-a", "director", ta),
        manager_a1=user("truong-phong-dt", "manager", ta, a1),
        manager_a2=user("truong-phong-tchc", "manager", ta, a2),
        staff_a1=user("chuyen-vien-dt-1", "staff", ta, a1),
        staff_a1b=user("chuyen-vien-dt-2", "staff", ta, a1),
        staff_a2=user("chuyen-vien-tchc", "staff", ta, a2),
        admin_a=user("quan-tri-a", "tenant_admin", ta),
        clerk_b=user("van-thu-b", "clerk", tb),
        service_a=Service(f"svc-{tag}", "service", ta),
        service_b=Service(f"svc-{tag}", "service", tb),
        tag=tag,
    )


INSERT_DOC = """
mutation ($o: office_documents_insert_input!) {
  insert_office_documents_one(object: $o) { id tenant_id direction status created_by department_id }
}"""


def received(clerk: User, doc: dict) -> dict:
    """Văn bản đến như Action receiveIncoming ghi (F2.2): vai trò service thay mặt văn thư, người tạo là văn thư.

    Văn thư không còn quyền ghi thẳng bảng văn bản; stack test này không có svc-workflow nên ghi như svc-workflow
    ghi. Phần kiểm của svc-workflow có test riêng (services/svc-workflow/tests/test_intake.py).
    """
    svc = Service(clerk.sub, "service", clerk.tenant)
    row = {**doc, "direction": "in", "status": "received", "created_by": clerk.sub}
    return svc.gql(INSERT_DOC, {"o": row})["insert_office_documents_one"]


def incoming(tag: str, n: int, **overrides) -> dict:
    doc = {
        "type_code": "CV",
        "symbol": f"{n}/UBND-VP{tag}",
        "issuer_name": "UBND tỉnh Hưng Yên",
        "issued_on": "2026-10-15",
        "summary": f"Về việc triển khai chuyển đổi số năm học 2026–2027 (thử {n})",
    }
    doc.update(overrides)
    return doc


def outgoing(n: int, **overrides) -> dict:
    doc = {"type_code": "TB", "summary": f"Thông báo lịch họp giao ban tháng 11 (dự thảo {n})"}
    doc.update(overrides)
    return doc


def visible_ids(user: User) -> set[str]:
    return {d["id"] for d in user.gql("{ office_documents { id } }")["office_documents"]}


def insert_file(service: Service, owner: User, name: str = "cong-van.pdf", *, encrypted: bool = False) -> str:
    """Giả lập svc-files: tệp đã qua ClamAV, người tải lên là owner; encrypted = tải lên ở chế độ hạn chế (F3.7)."""
    file_id = str(uuid.uuid4())
    svc = Service(owner.sub, "service", service.tenant)
    svc.gql(
        """mutation ($o: core_files_insert_input!) { insert_core_files_one(object: $o) { id } }""",
        {"o": {
            "id": file_id,
            "object_key": f"tenant/{service.tenant}/2026/10/{file_id}",
            "filename": name,
            "mime_type": "application/pdf",
            "size_bytes": 1024,
            "sha256": "\\x" + hashlib.sha256(file_id.encode()).hexdigest(),
            "scanned_at": "2026-10-18T09:00:00+07:00",
            **({"encrypted": True, "wrapped_dek": "vault:v1:thu"} if encrypted else {}),
        }},
    )
    return file_id
