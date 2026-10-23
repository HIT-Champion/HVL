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

"""Đơn vị (thuê ước) và Keycloak Organizations (F3.12): `moc tenant create | list | check`, dùng chung với make seed.

Một đơn vị của Signet gồm:
  - một dòng core.tenants (mã viết trong ký hiệu văn bản, tên, thông tin in trên văn bản đi) và các phòng trong
    office.departments — ghi bằng psql trong container postgres với `set local moc.actor`, nên sổ kiểm toán ghi ai làm;
  - một Organization trong Keycloak: alias suy từ mã (ĐT → dt), thuộc tính tenant_id = id của đơn vị; mọi tài khoản có
    thuộc tính tenant_id đó là thành viên, và không là thành viên Organization nào khác. Organization là lớp quản lý
    thành viên và quản trị; token vẫn lấy đơn vị từ thuộc tính tenant_id của tài khoản (mapper claim Hasura không đổi)
    — claim `organization` của Keycloak là danh sách alias, nằm ngoài namespace Hasura;
  - một tài khoản quản trị đơn vị (tenant_admin, không thuộc phòng nào), mật khẩu tạm: lần đầu đăng nhập phải đổi mật
    khẩu và cài TOTP.

Chạy lại được: đơn vị tra theo mã (giữ id cũ), phòng theo (đơn vị, mã), Organization theo thuộc tính tenant_id, tài
khoản theo tên đăng nhập. Đã có thì giữ, không đặt lại mật khẩu (trừ khi có --reset-password). Mọi xung đột (alias, tên
đăng nhập của đơn vị khác…) được kiểm trước khi ghi gì.

Module không đọc .env lúc nạp: CSDL (`database()`) và Keycloak (`connect()`) chỉ mở khi lệnh cần — test thay hai hàm
này bằng bản giả.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import re
import secrets
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

COMPOSE = ["docker", "compose", "--profile", "core", "--profile", "app"]
CODE = re.compile(r"^[^\s/-]{1,20}$")            # CHECK của core.tenants.code và office.departments.code
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,254}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
ALIAS = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
NGSI = re.compile(r"^[A-Za-z0-9]{1,20}$")
ROLES = {"clerk", "staff", "manager", "director", "tenant_admin"}   # moc_role trong user profile của realm
ADMIN_ACTIONS = ["UPDATE_PASSWORD", "CONFIGURE_TOTP"]
# Email mặc định của quản trị đơn vị: <tên đăng nhập>@<alias>.moc.example, cùng kiểu tài khoản mẫu (seed.py). Keycloak
# không cho sửa hồ sơ của thành viên Organization thiếu email (OrganizationMemberValidator: "Email not set")
PLACEHOLDER_DOMAIN = "moc.example"
PAGE = 100


class TenantError(Exception):
    """Không làm được, hoặc làm thì sai — thông báo viết cho người vận hành đọc (thoát 1)."""


class Unavailable(Exception):
    """Không gọi được CSDL hoặc Keycloak: không kết luận được gì (thoát 2)."""


class KeycloakError(TenantError):
    def __init__(self, status: int, method: str, path: str, body: str):
        try:
            data = json.loads(body)
            detail = data.get("errorMessage") or data.get("error_description") or data.get("error") or body
        except (ValueError, AttributeError):
            detail = body
        hint = ""
        if status == 404 and "not enabled" in str(detail):
            hint = " — realm chưa bật Organizations: chạy python3 scripts/moc.py tenant create … hoặc make seed"
        super().__init__(f"Keycloak từ chối {method} {path or '/'}: HTTP {status} {str(detail)[:300]}{hint}")
        self.status = status


# --- tên, mã ----------------------------------------------------------------------------------------------------------

def alias_for(code: str) -> str:
    """Alias Organization của một đơn vị: mã viết thường, bỏ dấu tiếng Việt (ĐT → dt, KTCK → ktck); ký tự khác chữ, số
    ASCII thành '-'. Mã không còn chữ, số ASCII nào thì "t" + 16 ký tự hex băm của mã, như ngsi_tenant."""
    plain = unicodedata.normalize("NFD", code.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in plain if not unicodedata.combining(c)).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")
    return slug or "t" + hashlib.sha256(code.encode()).hexdigest()[:16]


def ngsi_tenant(code: str) -> str:
    """Tenant NGSI-LD của đơn vị — cùng quy tắc với svc_workflow.ot.ngsi_tenant (chỉ để in ra, không gọi broker)."""
    return code if NGSI.match(code) else "t" + hashlib.sha256(code.encode()).hexdigest()[:16]


def generate_password() -> str:
    """Mật khẩu tạm: 4 nhóm 4 ký tự (bỏ ký tự dễ nhầm 0/O, 1/l/I), khoảng 92 bit — đủ length(10) and notUsername."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


def split_name(full: str) -> tuple[str, str]:
    """"Ngô Văn Tín" → ("Ngô Văn", "Tín"): firstName là họ và đệm, lastName là tên — như seed/users.csv."""
    words = full.split()
    return " ".join(words[:-1]), words[-1]


def first(attrs: dict[str, list[str]] | None, name: str) -> str | None:
    values = (attrs or {}).get(name) or []
    return values[0] if values else None


def _uuid(value: str | None) -> str | None:
    """UUID dạng chuẩn (chữ thường); giá trị không phải UUID thì giữ nguyên để còn báo ra."""
    if value is None:
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        return value


def org_tenant(org: dict[str, Any]) -> str | None:
    return _uuid(first(org.get("attributes"), "tenant_id"))


def user_tenant(user: dict[str, Any]) -> str | None:
    return _uuid(first(user.get("attributes"), "tenant_id"))


# --- kiểu tham số dòng lệnh (argparse) ------------------------------------------------------------------------------

def code_arg(value: str) -> str:
    value = value.strip()
    if not CODE.match(value):
        raise argparse.ArgumentTypeError("mã không có dấu cách, '/', '-', tối đa 20 ký tự (vd KTCK)")
    return value


def text_arg(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise argparse.ArgumentTypeError("không được để trống")
    return value


def org_ident_arg(value: str) -> str:
    value = value.strip()
    if len(value) != 13:
        raise argparse.ArgumentTypeError("mã định danh theo QCVN 102 có đúng 13 ký tự")
    return value


def department_arg(value: str) -> tuple[str, str]:
    code, sep, name = value.partition("=")
    code, name = code.strip(), " ".join(name.split())
    if not sep or not name or not CODE.match(code):
        raise argparse.ArgumentTypeError('cần dạng MÃ=Tên, vd "VP=Văn phòng khoa"; mã không có dấu cách, "/", "-"')
    return code, name


def username_arg(value: str) -> str:
    value = value.strip().lower()
    if not USERNAME.match(value):
        raise argparse.ArgumentTypeError("tên đăng nhập 3–255 ký tự: chữ thường không dấu, số, '.', '_', '-'")
    return value


def person_arg(value: str) -> str:
    words = value.split()
    if len(words) < 2:
        raise argparse.ArgumentTypeError('cần họ và tên, ít nhất hai chữ, vd "Ngô Văn Tín"')
    return " ".join(words)


def email_arg(value: str) -> str:
    value = value.strip()
    if not EMAIL.match(value):
        raise argparse.ArgumentTypeError("địa chỉ email không hợp lệ")
    return value


def domain_arg(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if not DOMAIN.match(value):
        raise argparse.ArgumentTypeError("tên miền không hợp lệ, vd ck.truong.edu.vn")
    return value


def alias_arg(value: str) -> str:
    value = value.strip()
    if not ALIAS.match(value):
        raise argparse.ArgumentTypeError("alias: chữ thường không dấu, số, '-'; bắt đầu bằng chữ hoặc số")
    return value


@dataclass
class Spec:
    """Một đơn vị như người vận hành khai trong `moc tenant create`."""
    code: str
    name: str
    admin: str
    parent_name: str | None = None
    place_name: str | None = None
    head_title: str | None = None
    org_ident: str | None = None
    departments: list[tuple[str, str]] = field(default_factory=list)
    admin_name: str | None = None
    admin_email: str | None = None
    alias: str | None = None
    domains: list[str] = field(default_factory=list)
    reset_password: bool = False

    def validate(self) -> None:
        codes = [c for c, _ in self.departments]
        twice = sorted({c for c in codes if codes.count(c) > 1})
        if twice:
            raise TenantError(f"phòng khai hai lần: {', '.join(twice)}")


# --- CSDL -------------------------------------------------------------------------------------------------------------

_TENANT_JSON = """(select json_build_object('id', t.id, 'code', t.code, 'name', t.name, 'org_ident', t.org_ident,
                                     'parent_name', t.parent_name, 'place_name', t.place_name, 'head_title', t.head_title)
            from core.tenants t where t.code = :'code')"""

# Một đơn vị theo mã, các phòng của nó, và đơn vị khác đang giữ mã định danh. Biến psql: code, org_ident ('' nếu không có)
STATE_SQL = f"""
select json_build_object(
  'tenant', {_TENANT_JSON},
  'departments', coalesce((select json_agg(json_build_object('code', p.code, 'name', p.name) order by p.code)
                           from office.departments p join core.tenants t on t.id = p.tenant_id
                           where t.code = :'code'), '[]'),
  'org_ident_owner', (select t.code from core.tenants t
                      where t.org_ident = nullif(:'org_ident', '') and t.code <> :'code'))::text;
"""

# Thêm hoặc cập nhật đơn vị (theo mã: giữ id cũ) và phòng (theo đơn vị + mã) trong một giao dịch; tham số tùy chọn không
# khai thì giữ giá trị cũ. Không xóa phòng nào. Sửa không đổi giá trị thì trigger không ghi sổ. Biến psql: actor, id (dùng
# khi đơn vị chưa có), code, name, org_ident, parent_name, place_name, head_title ('' = không khai), departments (JSON)
WRITE_SQL = """
begin;
set local moc.actor = :'actor';
insert into core.tenants as t (id, code, name, org_ident, parent_name, place_name, head_title)
values (:'id', :'code', :'name', nullif(:'org_ident', ''), nullif(:'parent_name', ''), nullif(:'place_name', ''),
        nullif(:'head_title', ''))
on conflict (code) do update set
  name = excluded.name,
  org_ident = coalesce(excluded.org_ident, t.org_ident),
  parent_name = coalesce(excluded.parent_name, t.parent_name),
  place_name = coalesce(excluded.place_name, t.place_name),
  head_title = coalesce(excluded.head_title, t.head_title);
insert into office.departments as p (tenant_id, code, name)
select t.id, d.code, d.name
from core.tenants t, jsonb_to_recordset(:'departments'::jsonb) as d(code text, name text)
where t.code = :'code'
on conflict (tenant_id, code) do update set name = excluded.name;
""" + STATE_SQL + "commit;\n"

_TENANTS_JSON = """coalesce((select json_agg(json_build_object(
    'id', t.id, 'code', t.code, 'name', t.name,
    'departments', coalesce((select json_agg(p.code order by p.code) from office.departments p
                             where p.tenant_id = t.id), '[]'),
    'users', (select count(*) from core.users u where u.tenant_id = t.id and u.enabled),
    'documents', (select count(*) from office.documents d where d.tenant_id = t.id))
  order by t.created_at, t.code) from core.tenants t), '[]')"""

# moc tenant list
TENANTS_SQL = f"select {_TENANTS_JSON}::text;\n"

# moc tenant check: đơn vị và danh bạ core.users (bản sao Keycloak do svc-workflow đồng bộ)
CHECK_SQL = f"""
select json_build_object(
  'tenants', {_TENANTS_JSON},
  'users', coalesce((select json_agg(json_build_object('id', u.id, 'tenant_id', u.tenant_id, 'username', u.username,
                                                       'enabled', u.enabled) order by u.username)
                     from core.users u), '[]'))::text;
"""

# Danh bạ đã có tài khoản này của đơn vị chưa. Biến psql: user_id, tenant_id
SYNCED_SQL = """
select json_build_object('synced', exists(select 1 from core.users u
                                          where u.id = :'user_id' and u.tenant_id = :'tenant_id'::uuid
                                            and u.enabled))::text;
"""


def _tail(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " / ".join(lines[-3:])


class Database:
    """psql trong container postgres, như moc audit, moc backup: không mở thêm cổng, không cần mật khẩu ngoài .env."""

    def __init__(self) -> None:
        from moc_env import ENV, ROOT
        self.root = ROOT
        self.base = [*COMPOSE, "exec", "-T", "postgres", "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                     "-U", ENV.get("POSTGRES_USER", "moc"), "-d", ENV.get("POSTGRES_DB", "moc")]

    def query(self, sql: str, **variables: str) -> Any:
        """Chạy sql (biến psql dạng :'tên', luôn được trích dẫn đúng) → JSON mà câu select cuối in ra. psql -q không in
        gì khác ra stdout; json_agg có thể xuống dòng giữa các phần tử nên đọc cả stdout, không chỉ dòng cuối."""
        cmd = [*self.base, *(a for k, v in variables.items() for a in ("-v", f"{k}={v}")), "-f", "-"]
        try:
            proc = subprocess.run(cmd, cwd=self.root, input=sql, capture_output=True, text=True, encoding="utf-8")
        except OSError as exc:
            raise Unavailable(f"không chạy được docker compose: {exc}") from None
        if proc.returncode == 3:        # psql: câu lệnh SQL lỗi (ON_ERROR_STOP) — giao dịch đã hủy
            raise TenantError(f"CSDL từ chối: {_tail(proc.stderr)}")
        if proc.returncode != 0:
            raise Unavailable(f"không đọc được CSDL: {_tail(proc.stderr) or 'psql lỗi'}")
        out = proc.stdout.strip()
        try:
            return json.loads(out) if out else None
        except ValueError:
            raise Unavailable(f"CSDL trả kết quả lạ: {out[:200]}") from None


def database() -> Database:
    return Database()


# --- Keycloak ---------------------------------------------------------------------------------------------------------

class Keycloak:
    """Admin REST của realm qua cổng quản trị nội bộ (127.0.0.1:KEYCLOAK_ADMIN_PORT), không qua APISIX.

    call: như moc_env.call_json(method, url, body, headers=…) → (dữ liệu, header); lỗi HTTP là http_error (có .status,
    .body). Lỗi mạng (OSError) thành Unavailable."""

    def __init__(self, base_url: str, realm: str, token: str, *, call: Callable[..., tuple[Any, dict[str, str]]],
                 http_error: type[Exception]):
        self.base = f"{base_url.rstrip('/')}/admin/realms/{realm}"
        self.realm_name = realm
        self._auth = {"Authorization": f"Bearer {token}"}
        self._call = call
        self._http_error = http_error

    def _req(self, method: str, path: str, body: Any = None, *,
             query: dict[str, Any] | None = None) -> tuple[Any, dict[str, str]]:
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        try:
            return self._call(method, url, body, headers=self._auth)
        except self._http_error as exc:
            raise KeycloakError(getattr(exc, "status", 0), method, path, getattr(exc, "body", str(exc))) from None
        except OSError as exc:
            raise Unavailable(f"không gọi được Keycloak ({self.base}): {exc}") from None

    def _all(self, path: str, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while True:
            page, _ = self._req("GET", path, query={**(query or {}), "first": len(out), "max": PAGE})
            out.extend(page or [])
            if len(page or []) < PAGE:
                return out

    @staticmethod
    def _created_id(headers: dict[str, str]) -> str:
        location = next((v for k, v in headers.items() if k.lower() == "location"), "")
        if not location:
            raise TenantError("Keycloak tạo xong nhưng không trả Location — không biết id vừa tạo")
        return location.rstrip("/").rsplit("/", 1)[-1]

    def realm(self) -> dict[str, Any]:
        return self._req("GET", "")[0]

    def enable_organizations(self) -> bool:
        """Bật Organizations cho realm (realm nạp từ tệp trước F3.12 chưa bật). True nếu vừa bật."""
        rep = self.realm()
        if rep.get("organizationsEnabled"):
            return False
        # Gửi lại nguyên bản vừa đọc, như trang quản trị: thân chỉ có một trường thì Keycloak đặt lại vài thiết lập vắng
        # mặt (thời hạn device code, CIBA) về mặc định
        self._req("PUT", "", {**rep, "organizationsEnabled": True})
        if not self.realm().get("organizationsEnabled"):
            raise TenantError("Keycloak không bật được Organizations cho realm — tính năng organization bị tắt trên "
                              "máy chủ (KC_FEATURES_DISABLED)?")
        return True

    def organizations(self) -> list[dict[str, Any]]:
        # bản đầy đủ: bản rút gọn (mặc định) không có attributes, mà tenant_id nằm ở đó
        return self._all("/organizations", {"briefRepresentation": "false"})

    def create_organization(self, rep: dict[str, Any]) -> str:
        return self._created_id(self._req("POST", "/organizations", rep)[1])

    def update_organization(self, org_id: str, rep: dict[str, Any]) -> None:
        # PUT thay cả attributes và domains: luôn gửi bản đầy đủ vừa đọc, đã sửa
        self._req("PUT", f"/organizations/{org_id}", rep)

    def members(self, org_id: str) -> list[dict[str, Any]]:
        return self._all(f"/organizations/{org_id}/members")

    def add_member(self, org_id: str, user_id: str) -> bool:
        """Thêm tài khoản có sẵn (thành viên unmanaged). False nếu đã là thành viên."""
        try:
            self._req("POST", f"/organizations/{org_id}/members", user_id)   # thân là chuỗi JSON: id tài khoản
        except KeycloakError as exc:
            if exc.status == 409:
                return False
            raise
        return True

    def users(self) -> list[dict[str, Any]]:
        return self._all("/users", {"briefRepresentation": "false"})

    def find_user(self, username: str) -> dict[str, Any] | None:
        found, _ = self._req("GET", "/users", query={"exact": "true", "username": username,
                                                     "briefRepresentation": "false"})
        return next((u for u in found or [] if u.get("username") == username), None)

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        found, _ = self._req("GET", "/users", query={"exact": "true", "email": email})
        return next((u for u in found or [] if (u.get("email") or "").lower() == email.lower()), None)

    def create_user(self, rep: dict[str, Any]) -> str:
        return self._created_id(self._req("POST", "/users", rep)[1])

    def reset_password(self, user_id: str, value: str) -> None:
        """Mật khẩu tạm: Keycloak tự thêm yêu cầu đổi mật khẩu ở lần đăng nhập kế tiếp."""
        self._req("PUT", f"/users/{user_id}/reset-password", {"type": "password", "value": value, "temporary": True})

    # client của ứng dụng: realm_clients.py thêm client còn thiếu vào realm đã nạp từ trước
    def clients(self) -> list[dict[str, Any]]:
        return self._all("/clients")

    def create_client(self, rep: dict[str, Any]) -> str:
        return self._created_id(self._req("POST", "/clients", rep)[1])


def admin_token() -> str:
    """Token quản trị Keycloak (realm master, KEYCLOAK_ADMIN_* trong .env), qua cổng quản trị nội bộ."""
    import moc_env
    try:
        data, _ = moc_env.call_json(
            "POST", f"{moc_env.KEYCLOAK_ADMIN_URL}/realms/master/protocol/openid-connect/token",
            form={"grant_type": "password", "client_id": "admin-cli",
                  "username": moc_env.ENV.get("KEYCLOAK_ADMIN_USER", "admin"),
                  "password": moc_env.ENV["KEYCLOAK_ADMIN_PASSWORD"]})
    except moc_env.HTTPError as exc:
        raise TenantError(f"Keycloak từ chối tài khoản quản trị KEYCLOAK_ADMIN_USER: HTTP {exc.status}") from None
    except OSError as exc:
        raise Unavailable(f"không gọi được Keycloak ở {moc_env.KEYCLOAK_ADMIN_URL}: {exc}") from None
    return data["access_token"]


def connect(token: str | None = None) -> Keycloak:
    import moc_env
    return Keycloak(moc_env.KEYCLOAK_ADMIN_URL, moc_env.REALM, token or admin_token(), call=moc_env.call_json,
                    http_error=moc_env.HTTPError)


# --- kế hoạch: tính việc phải làm từ trạng thái hiện có, chưa ghi gì -------------------------------------------------

def plan_organization(orgs: list[dict[str, Any]], tenant_id: str | None, code: str, name: str, *,
                      alias: str | None = None, domains: Iterable[str] = ()) -> tuple[str, dict[str, Any]]:
    """(việc, Organization sau khi làm), việc ∈ created | updated | kept. Xung đột thì TenantError."""
    domains = list(domains)
    mine = [o for o in orgs if tenant_id and org_tenant(o) == tenant_id]
    if len(mine) > 1:
        raise TenantError(f"đơn vị {code} có {len(mine)} Organization cùng tenant_id "
                          f"({', '.join(o.get('alias', '?') for o in mine)}) — giữ một, xóa bản thừa trong trang quản "
                          "trị Keycloak rồi chạy lại")
    own_id = mine[0].get("id") if mine else None
    others = [o for o in orgs if own_id is None or o.get("id") != own_id]
    # Keycloak bắt tên Organization khác nhau; hai đơn vị trùng tên (Khoa Kinh tế của hai trường) thì thêm mã
    org_name = name if all(o.get("name") != name for o in others) else f"{name} ({code})"
    if any(o.get("name") == org_name for o in others):
        raise TenantError(f"Keycloak đã có Organization tên {org_name!r} — đổi tên đơn vị hoặc tên Organization kia")
    taken = {d.get("name"): o for o in others for d in o.get("domains") or []}
    for d in domains:
        if d in taken:
            raise TenantError(f"tên miền {d} đã gắn với Organization {taken[d].get('alias')}")
    if mine:
        org = dict(mine[0])
        if alias and org.get("alias") != alias:
            raise TenantError(f"Organization của {code} đã có alias {org.get('alias')}; Keycloak không cho đổi alias")
        have = [d.get("name") for d in org.get("domains") or []]
        new_domains = [{"name": d, "verified": False} for d in domains if d not in have]
        changed = org.get("name") != org_name or bool(new_domains)
        org.update(name=org_name, domains=[*(org.get("domains") or []), *new_domains])
        return ("updated" if changed else "kept"), org
    alias = alias or alias_for(code)
    clash = next((o for o in orgs if o.get("alias") == alias), None)
    if clash:
        owner = org_tenant(clash)
        raise TenantError(f"alias {alias} đã thuộc Organization {clash.get('name')!r} "
                          f"({'tenant_id ' + owner if owner else 'không gắn đơn vị nào'}) — chọn alias khác: --alias")
    return "created", {"name": org_name, "alias": alias, "enabled": True,
                       "description": f"Đơn vị {code} trong Signet (core.tenants)",
                       "attributes": {"tenant_id": [tenant_id] if tenant_id else []},
                       "domains": [{"name": d} for d in domains]}


def apply_organization(kc: Keycloak, action: str, org: dict[str, Any]) -> dict[str, Any]:
    if action == "created":
        return {**org, "id": kc.create_organization(org)}
    if action == "updated":
        kc.update_organization(org["id"], org)
    return org


def plan_admin(found: dict[str, Any] | None, tenant_id: str | None, spec: Spec, alias: str,
               email_owner: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """(việc, tài khoản), việc ∈ created | reset | kept. Không chiếm tài khoản của đơn vị khác hay chưa gắn đơn vị."""
    if found:
        owner = user_tenant(found)
        if owner is None or owner != tenant_id:
            where = f"đơn vị khác (tenant_id {owner})" if owner else "chưa gắn đơn vị nào"
            raise TenantError(f"tài khoản {spec.admin} đã có trong Keycloak và {where} — chọn tên đăng nhập khác (--admin)")
        role = first(found.get("attributes"), "moc_role")
        if role != "tenant_admin":
            raise TenantError(f"tài khoản {spec.admin} của đơn vị này đang có vai trò {role or '(chưa có)'}, không phải "
                              "tenant_admin — đổi vai trò trong trang quản trị Keycloak nếu đúng ý, hoặc chọn tên khác")
        return ("reset" if spec.reset_password else "kept"), found
    first_name, last_name = split_name(spec.admin_name) if spec.admin_name else ("Quản trị", spec.name)
    domain = spec.domains[0] if spec.domains else f"{alias}.{PLACEHOLDER_DOMAIN}"
    email = spec.admin_email or f"{spec.admin}@{domain}"
    if email_owner and email_owner.get("username") != spec.admin:
        raise TenantError(f"email {email} đã là của tài khoản {email_owner.get('username')} (realm không cho trùng email)"
                          " — khai email khác: --admin-email")
    return "created", {
        "username": spec.admin, "enabled": True, "firstName": first_name, "lastName": last_name, "email": email,
        "emailVerified": False,
        "attributes": {"tenant_id": [tenant_id] if tenant_id else [], "moc_role": ["tenant_admin"]},
        "requiredActions": list(ADMIN_ACTIONS),
    }


def apply_admin(kc: Keycloak, action: str, user: dict[str, Any], tenant_id: str) -> tuple[str, str | None]:
    """→ (id tài khoản, mật khẩu tạm vừa đặt hoặc None). Mật khẩu chỉ đi trong thân yêu cầu tới Keycloak."""
    if action == "created":
        password = generate_password()
        rep = {**user, "attributes": {**user["attributes"], "tenant_id": [tenant_id]},
               "credentials": [{"type": "password", "value": password, "temporary": True}]}
        return kc.create_user(rep), password
    if action == "reset":
        password = generate_password()
        kc.reset_password(user["id"], password)
        return user["id"], password
    return user["id"], None


def sync_members(kc: Keycloak, org_id: str | None, tenant_id: str | None, users: list[dict[str, Any]], *,
                 dry_run: bool = False) -> tuple[int, list[str]]:
    """Thêm vào Organization mọi tài khoản có tenant_id của đơn vị mà chưa là thành viên. Không gỡ ai: tài khoản lạc
    Organization do `moc tenant check` chỉ ra. → (số thành viên trước đó, tên đăng nhập vừa thêm)."""
    members = kc.members(org_id) if org_id else []
    have = {m.get("id") for m in members}
    missing = [u for u in users if tenant_id and user_tenant(u) == tenant_id and u.get("id") not in have]
    if not dry_run:
        for u in missing:
            kc.add_member(org_id, u["id"])
    return len(members), sorted(u["username"] for u in missing)


def organize(kc: Keycloak, tenants: list[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    """Mỗi đơn vị một Organization (tạo hoặc giữ), mọi tài khoản của đơn vị là thành viên — make seed dùng.
    → (vừa bật Organizations cho realm, kết quả từng đơn vị)."""
    enabled = kc.enable_organizations()
    orgs, users = kc.organizations(), kc.users()
    out = []
    for t in tenants:
        action, org = plan_organization(orgs, t["id"], t["code"], t["name"])
        org = apply_organization(kc, action, org)
        if action == "created":
            orgs.append(org)
        count, added = sync_members(kc, org["id"], t["id"], users)
        out.append({"code": t["code"], "alias": org["alias"], "status": action, "members": count + len(added),
                    "added": added})
    return enabled, out


def facts(tenant_id: str | None, code: str) -> dict[str, list[str]]:
    """Những gì một đơn vị mới tự có, và những gì dùng chung có chủ ý (in sau `tenant create`)."""
    tid = tenant_id or "<id>"
    return {
        "automatic": [
            "sổ đăng ký văn bản đến, văn bản đi: tự tạo khi văn thư vào sổ, cấp số lần đầu mỗi năm",
            "danh bạ core.users: svc-workflow chép tài khoản có tenant_id của đơn vị từ Keycloak mỗi 15 giây",
            f"NGSI-LD: svc-workflow tự giữ subscription cảnh báo cảm biến trong tenant {ngsi_tenant(code)} (khi bật "
            "profile iot)",
            "tìm kiếm: chỉ mục Meilisearch chung, mọi truy vấn lọc theo tenant_id lấy từ token, không từ tham số",
            f"tệp: khóa đối tượng tenant/{tid}/…; tệp văn bản hạn chế mã hóa gắn với đơn vị và tệp",
        ],
        "shared": [
            f"một bucket tệp nóng: ràng buộc files_object_key_tenant của CSDL buộc mọi tệp nằm dưới tenant/{tid}/ của "
            "đúng đơn vị",
            f"một bucket lạnh khóa ghi (S3 Object Lock): gói nộp lưu nằm dưới cold/{tid}/; mốc neo sổ kiểm toán là của "
            "cả nền tảng",
            "một khóa transit OpenBao: mỗi tệp một khóa dữ liệu riêng, AES-GCM với AAD = id đơn vị ‖ id tệp — bản mã "
            "chép sang đơn vị khác không mở được",
        ],
    }


def _actor() -> str:
    try:
        return f"os:{getpass.getuser()}"
    except (KeyError, OSError):
        return "os:?"


def _wait_directory(db: Any, user_id: str, tenant_id: str, timeout_s: float, sleep: Callable[[float], None],
                    clock: Callable[[], float]) -> int | None:
    """Đợi svc-workflow chép tài khoản vào core.users → số giây đã đợi; None nếu quá hạn."""
    start = clock()
    while True:
        if db.query(SYNCED_SQL, user_id=user_id, tenant_id=tenant_id)["synced"]:
            return round(clock() - start)
        if clock() - start >= timeout_s:
            return None
        sleep(2)


def create(spec: Spec, kc: Keycloak, db: Any, *, dry_run: bool = False, wait_s: float = 90,
           sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Thêm hoặc cập nhật một đơn vị. Bật Organizations cho realm nếu chưa bật (không đổi token; cần để thấy cả
    Organization tạo từ trước khi tính năng bị tắt), đọc và kiểm mọi xung đột, rồi mới ghi: CSDL → Organization → quản
    trị đơn vị → thành viên → đợi danh bạ. Dừng giữa chừng thì chạy lại là đi tiếp. --dry-run không bật gì: realm chưa
    bật thì kế hoạch không thấy được Organization cũ."""
    spec.validate()
    state = db.query(STATE_SQL, code=spec.code, org_ident=spec.org_ident or "")
    if state["org_ident_owner"]:
        raise TenantError(f"mã định danh {spec.org_ident} đã là của đơn vị {state['org_ident_owner']}")
    before = state["tenant"]
    tenant_id = before["id"] if before else None

    realm = kc.realm()
    orgs_enabled = bool(realm.get("organizationsEnabled"))
    if not orgs_enabled and not dry_run:
        kc.enable_organizations()
    orgs = kc.organizations() if orgs_enabled or not dry_run else []
    org_action, org = plan_organization(orgs, tenant_id, spec.code, spec.name, alias=spec.alias, domains=spec.domains)
    found = kc.find_user(spec.admin)
    email_owner = None
    if not found:
        planned_email = plan_admin(None, tenant_id, spec, org["alias"])[1]["email"]
        email_owner = kc.find_by_email(planned_email)
    admin_action, admin = plan_admin(found, tenant_id, spec, org["alias"], email_owner)

    fields = {"name": spec.name, "org_ident": spec.org_ident, "parent_name": spec.parent_name,
              "place_name": spec.place_name, "head_title": spec.head_title}
    if before is None:
        tenant_status = "created"
    elif any(v is not None and before.get(k) != v for k, v in fields.items()):
        tenant_status = "updated"
    else:
        tenant_status = "kept"
    old_depts = {d["code"]: d["name"] for d in state["departments"]}
    departments = [{"code": c, "name": n,
                    "status": "created" if c not in old_depts else "updated" if old_depts[c] != n else "kept"}
                   for c, n in spec.departments]
    departments += [{"code": c, "name": n, "status": "existing"} for c, n in old_depts.items()
                    if c not in dict(spec.departments)]

    password = None
    synced: dict[str, Any] = {"synced": None, "seconds": None, "timeout": wait_s}
    if dry_run:
        users = kc.users() if tenant_id else []
        members_before, added = sync_members(kc, org.get("id"), tenant_id, users, dry_run=True)
        if admin_action == "created":
            added = sorted({*added, spec.admin})
        admin_id = admin.get("id")
    else:
        after = db.query(WRITE_SQL, actor=_actor(), id=tenant_id or str(uuid.uuid4()), code=spec.code, name=spec.name,
                         org_ident=spec.org_ident or "", parent_name=spec.parent_name or "",
                         place_name=spec.place_name or "", head_title=spec.head_title or "",
                         departments=json.dumps([{"code": c, "name": n} for c, n in spec.departments],
                                                ensure_ascii=False))
        tenant_id = after["tenant"]["id"]
        # tính lại với id thật của đơn vị (đơn vị mới: lần đầu chưa có id) rồi mới ghi
        org_action, org = plan_organization(orgs, tenant_id, spec.code, spec.name, alias=spec.alias,
                                            domains=spec.domains)
        org = apply_organization(kc, org_action, org)
        admin_action, admin = plan_admin(found, tenant_id, spec, org["alias"], email_owner)
        admin_id, password = apply_admin(kc, admin_action, admin, tenant_id)
        members_before, added = sync_members(kc, org["id"], tenant_id, kc.users())
        if wait_s > 0:
            seconds = _wait_directory(db, admin_id, tenant_id, wait_s, sleep, clock)
            synced = {"synced": seconds is not None, "seconds": seconds, "timeout": wait_s}

    result = {
        "ok": synced["synced"] is not False,
        "dry_run": dry_run,
        "tenant": {"id": tenant_id, "code": spec.code, "name": spec.name, "status": tenant_status,
                   "ngsi_tenant": ngsi_tenant(spec.code)},
        "departments": departments,
        # enable: realm chưa bật Organizations, lệnh này bật (dry-run: sẽ bật)
        "realm": {"name": kc.realm_name, "enable": not orgs_enabled},
        "organization": {"id": org.get("id"), "alias": org["alias"], "name": org["name"], "status": org_action,
                         "tenant_id": tenant_id, "domains": [d.get("name") for d in org.get("domains") or []],
                         "members": members_before + len(added), "added": added},
        "admin": {"username": spec.admin, "id": admin_id, "status": admin_action, "role": "tenant_admin",
                  "email": admin.get("email"),
                  "required_actions": list(ADMIN_ACTIONS) if admin_action == "created" else
                  admin.get("requiredActions", []),
                  "temporary_password": password},
        "directory": synced,
        **facts(tenant_id, spec.code),
    }
    return result


# --- kiểm tra ---------------------------------------------------------------------------------------------------------

@dataclass
class CheckReport:
    tenants: list[dict[str, Any]]
    problems: list[str]
    notes: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def consistency(tenants: list[dict[str, Any]], orgs: list[dict[str, Any]], members: dict[str, list[dict[str, Any]]],
                kc_users: list[dict[str, Any]], core_users: list[dict[str, Any]],
                codes: Iterable[str] = ()) -> CheckReport:
    """Đối chiếu core.tenants, Organization, thành viên và danh bạ core.users. codes: chỉ kiểm các đơn vị này.

    - mỗi đơn vị có đúng một Organization mang thuộc tính tenant_id của nó;
    - mọi tài khoản Keycloak có tenant_id là thành viên Organization của đơn vị đó, không thuộc Organization nào khác;
      thành viên Organization của đơn vị phải có tenant_id của đơn vị;
    - danh bạ core.users khớp Keycloak (id, đơn vị, tên đăng nhập, còn hoạt động)."""
    codes = set(codes)
    problems: list[tuple[set[str], str]] = []     # (mã các đơn vị bị ảnh hưởng, lời giải thích)
    notes: list[str] = []
    by_id = {t["id"]: t for t in tenants}
    by_code = {t["code"]: t for t in tenants}
    for c in sorted(codes - by_code.keys()):
        problems.append(({c}, f"không có đơn vị mã {c} trong core.tenants"))
    selected = [t for t in tenants if not codes or t["code"] in codes]
    chosen = {t["id"] for t in selected}

    def code_of(tid: str | None) -> str:
        return by_id[tid]["code"] if tid in by_id else "?"

    home: dict[str, dict[str, Any]] = {}
    for t in selected:
        mine = [o for o in orgs if org_tenant(o) == t["id"]]
        if not mine:
            problems.append(({t["code"]}, f"{t['code']}: chưa có Organization nào mang tenant_id {t['id']} — chạy: "
                                          f"python3 scripts/moc.py tenant create --code {t['code']} … (chạy lại được)"))
        elif len(mine) > 1:
            problems.append(({t["code"]}, f"{t['code']}: {len(mine)} Organization cùng tenant_id "
                                          f"({', '.join(o.get('alias', '?') for o in mine)}) — giữ một, xóa bản thừa"))
        else:
            home[t["id"]] = mine[0]
    if not codes:
        for o in orgs:
            tid = org_tenant(o)
            if tid is None:
                notes.append(f"Organization {o.get('alias')} không mang tenant_id: không thuộc Signet, bỏ qua")
            elif tid not in by_id:
                problems.append((set(), f"Organization {o.get('alias')} mang tenant_id {tid} không có trong "
                                        "core.tenants"))

    orgs_of: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for o in orgs:
        for m in members.get(o.get("id"), []):
            orgs_of[m.get("id")].append(o)
    accounts: dict[str, int] = defaultdict(int)
    for u in kc_users:
        name, tid = u.get("username"), user_tenant(u)
        org = home.get(tid) if tid else None
        # Organization của đơn vị khác (hoặc của đơn vị mà tài khoản không mang tenant_id) có tài khoản này
        stray = [o for o in orgs_of[u["id"]] if org_tenant(o) != tid]
        hit = {code_of(org_tenant(o)) for o in stray if org_tenant(o) in chosen}
        if tid in chosen:
            accounts[tid] += 1
            code = by_id[tid]["code"]
            if org and org.get("id") not in {o.get("id") for o in orgs_of[u["id"]]}:
                problems.append(({code}, f"{name} ({code}): chưa là thành viên Organization {org.get('alias')} — "
                                         f"chạy lại python3 scripts/moc.py tenant create --code {code} … (đơn vị mẫu: "
                                         "make seed)"))
            if stray:
                problems.append(({code} | hit, f"{name} ({code}): còn là thành viên Organization khác: "
                                               f"{', '.join(o.get('alias', '?') for o in stray)} — gỡ ra"))
            if org and not u.get("email"):
                notes.append(f"{name} ({code}): chưa có email — Keycloak không cho sửa hồ sơ thành viên Organization "
                             "thiếu email")
            if first(u.get("attributes"), "moc_role") not in ROLES:
                notes.append(f"{name} ({code}): chưa có moc_role hợp lệ — không vào được Signet, danh bạ bỏ qua")
        elif hit:
            why = f"thuộc đơn vị {code_of(tid)} (tenant_id {tid})" if tid else "không có thuộc tính tenant_id"
            problems.append((hit, f"{name}: là thành viên Organization "
                                  f"{', '.join(o.get('alias', '?') for o in stray if org_tenant(o) in chosen)} nhưng "
                                  f"{why} — gỡ khỏi Organization hoặc sửa tenant_id"))
        if tid is not None and tid not in by_id and not codes:
            problems.append((set(), f"{name}: tenant_id {tid} không có trong core.tenants"))

    users_by_id = {u["id"]: u for u in kc_users}
    core_by_id = {r["id"]: r for r in core_users}
    for u in kc_users:
        tid = user_tenant(u)
        if tid not in chosen or first(u.get("attributes"), "moc_role") not in ROLES:
            continue
        code, name = by_id[tid]["code"], u.get("username")
        row = core_by_id.get(u["id"])
        if row is None:
            problems.append(({code}, f"{name} ({code}): chưa có trong danh bạ core.users — svc-workflow đồng bộ mỗi 15 "
                                     "giây; còn thiếu thì xem docker compose logs svc-workflow"))
        elif (_uuid(row["tenant_id"]), row["username"], bool(row["enabled"])) != (tid, name,
                                                                                  bool(u.get("enabled", True))):
            problems.append(({code}, f"{name} ({code}): danh bạ core.users lệch Keycloak (đơn vị, tên đăng nhập hoặc "
                                     "trạng thái) — đợi một lượt đồng bộ của svc-workflow rồi kiểm lại"))
    for r in core_users:
        tid = _uuid(r["tenant_id"])
        if tid not in chosen or not r["enabled"]:
            continue
        u = users_by_id.get(r["id"])
        if u is None or user_tenant(u) != tid or first(u.get("attributes"), "moc_role") not in ROLES:
            code = by_id[tid]["code"]
            problems.append(({code}, f"{r['username']} ({code}): còn hoạt động trong danh bạ core.users nhưng Keycloak "
                                     "không còn tài khoản này ở đơn vị — đợi một lượt đồng bộ của svc-workflow"))

    bad = {c for affected, _ in problems for c in affected}
    summary = []
    for t in selected:
        org = home.get(t["id"])
        summary.append({"code": t["code"], "id": t["id"], "name": t["name"],
                        "organization": org.get("alias") if org else None,
                        "members": len(members.get(org.get("id"), [])) if org else 0,
                        "accounts": accounts[t["id"]], "ok": t["code"] not in bad})
    return CheckReport(summary, [m for _, m in problems], notes)


# --- lệnh -------------------------------------------------------------------------------------------------------------

STATUS = {"created": "tạo mới", "updated": "cập nhật", "kept": "giữ nguyên", "existing": "đã có, giữ nguyên",
          "reset": "giữ, đặt lại mật khẩu tạm"}
PLANNED = {"created": "sẽ tạo", "updated": "sẽ cập nhật", "kept": "giữ nguyên", "existing": "đã có, giữ nguyên",
           "reset": "giữ, sẽ đặt lại mật khẩu tạm"}


def _emit(args: argparse.Namespace, message: str, code: int) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    else:
        print(f"✗ {message}", file=sys.stderr)
    return code


def render_create(r: dict[str, Any]) -> None:
    words = PLANNED if r["dry_run"] else STATUS
    t, org, admin = r["tenant"], r["organization"], r["admin"]
    if r["dry_run"]:
        print(f"Kế hoạch thêm đơn vị {t['code']} — {t['name']} (--dry-run: chưa thay đổi gì)")
    else:
        print(f"Đơn vị {t['code']} — {t['name']}")
    print(f"  ✓ core.tenants: {words[t['status']]}, id {t['id'] or '(sinh khi tạo)'}")
    if r["departments"]:
        print("  ✓ phòng: " + "; ".join(f"{d['code']} {d['name']} ({words[d['status']]})" for d in r["departments"]))
    else:
        print("  · chưa có phòng nào: thêm bằng --department \"MÃ=Tên\" (chạy lại lệnh)")
    realm = r["realm"]
    if not realm["enable"]:
        print(f"  ✓ Keycloak: realm {realm['name']} đã bật Organizations")
    else:
        print(f"  ✓ Keycloak: realm {realm['name']} " + ("sẽ bật Organizations" if r["dry_run"]
                                                         else "vừa bật Organizations"))
    added = f" (thêm: {', '.join(org['added'])})" if org["added"] else ""
    print(f"  ✓ Organization {org['alias']} \"{org['name']}\": {words[org['status']]}, thuộc tính tenant_id = "
          f"{org['tenant_id'] or '(id đơn vị)'}; {org['members']} thành viên{added}")
    print(f"  ✓ quản trị đơn vị {admin['username']}: {words[admin['status']]} — vai trò tenant_admin, không thuộc phòng "
          f"nào, email {admin['email'] or '(như cũ)'}")
    if admin["status"] in ("created", "reset"):
        print("      lần đầu đăng nhập phải đổi mật khẩu" + (" và cài TOTP" if admin["status"] == "created" else ""))
    if admin["temporary_password"]:
        print(f"      Mật khẩu tạm (chỉ in lần này, không lưu ở đâu khác): {admin['temporary_password']}")
    d = r["directory"]
    if d["synced"]:
        print(f"  ✓ danh bạ core.users: svc-workflow đã chép {admin['username']} (sau {d['seconds']} giây)")
    elif d["synced"] is False:
        print(f"  ✗ danh bạ core.users: sau {d['timeout']:.0f} giây chưa có {admin['username']} — svc-workflow có chạy "
              "không? (docker compose logs svc-workflow). Lệnh chạy lại được")
    elif not r["dry_run"]:
        print("  · không đợi danh bạ (--wait 0): svc-workflow chép tài khoản trong vòng 15 giây")
    print("Tự có, không phải làm thêm:")
    for line in r["automatic"]:
        print(f"  · {line}")
    print("Dùng chung có chủ ý, không tách theo đơn vị:")
    for line in r["shared"]:
        print(f"  · {line}")
    if not r["dry_run"]:
        first_login = (f"{admin['username']} đăng nhập Signet, đổi mật khẩu" + (", cài TOTP. " if admin["status"] == "created"
                                                                              else ". ")
                       if admin["status"] in ("created", "reset") else "")
        print(f"Tiếp theo: {first_login}Tài khoản khác của đơn vị tạo trong trang quản trị Keycloak (tenant_id = "
              f"{t['id']}, department_id, moc_role) rồi chạy lại lệnh này để đưa vào Organization. Kiểm: "
              f"python3 scripts/moc.py tenant check {t['code']}")


def cmd_create(args: argparse.Namespace) -> int:
    spec = Spec(code=args.code, name=args.name, admin=args.admin, parent_name=args.parent_name,
                place_name=args.place_name, head_title=args.head_title, org_ident=args.org_ident,
                departments=list(args.department), admin_name=args.admin_name, admin_email=args.admin_email,
                alias=args.alias, domains=list(args.domain), reset_password=args.reset_password)
    try:
        result = create(spec, connect(), database(), dry_run=args.dry_run, wait_s=max(args.wait, 0))
    except TenantError as exc:
        return _emit(args, str(exc), 1)
    except Unavailable as exc:
        return _emit(args, f"{exc}. Signet có đang chạy không? (make ps)", 2)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        render_create(result)
    return 0 if result["ok"] else 1


def _keycloak_view(with_users: bool = True) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]],
                                                      list[dict[str, Any]], bool]:
    """Organization (bản đầy đủ), thành viên từng Organization, tài khoản, realm đã bật Organizations chưa."""
    kc = connect()
    users = kc.users() if with_users else []
    if not kc.realm().get("organizationsEnabled"):
        return [], {}, users, False
    orgs = kc.organizations()
    return orgs, {o["id"]: kc.members(o["id"]) for o in orgs}, users, True


def cmd_list(args: argparse.Namespace) -> int:
    try:
        rows = database().query(TENANTS_SQL)
    except (TenantError, Unavailable) as exc:
        return _emit(args, f"{exc}. Signet có đang chạy không? (make ps)", 2)
    error = None
    orgs: list[dict[str, Any]] = []
    members: dict[str, list[dict[str, Any]]] = {}
    try:
        orgs, members, _, _ = _keycloak_view(with_users=False)
    except (TenantError, Unavailable) as exc:
        error = str(exc)
    for row in rows:
        mine = [o for o in orgs if org_tenant(o) == row["id"]]
        row["organizations"] = [{"alias": o.get("alias"), "id": o.get("id"), "members": len(members.get(o["id"], []))}
                                for o in mine]
    if args.json:
        print(json.dumps({"tenants": rows, "keycloak_error": error}, ensure_ascii=False))
        return 2 if error else 0
    if not rows:
        print("Chưa có đơn vị nào. Thêm: python3 scripts/moc.py tenant create --code … --name … --admin …")
    for row in rows:
        print(f"{row['code']} — {row['name']}")
        print(f"  id {row['id']}")
        depts = ", ".join(row["departments"]) or "chưa có"
        print(f"  phòng ({len(row['departments'])}): {depts} · người dùng: {row['users']} · văn bản: {row['documents']}")
        if error:
            continue
        if row["organizations"]:
            print("  Organization: " + "; ".join(f"{o['alias']}, {o['members']} thành viên" for o in row["organizations"]))
        else:
            print("  Organization: chưa có (python3 scripts/moc.py tenant check để xem cách sửa)")
    if error:
        print(f"⚠ không đọc được Keycloak: {error}", file=sys.stderr)
        return 2
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        data = database().query(CHECK_SQL)
        orgs, members, users, enabled = _keycloak_view()
    except (TenantError, Unavailable) as exc:
        return _emit(args, f"{exc}. Signet có đang chạy không? (make ps)", 2)
    report = consistency(data["tenants"], orgs, members, users, data["users"], args.codes)
    if not enabled:
        report.problems.insert(0, "realm chưa bật Organizations — chạy make seed (đơn vị mẫu) hoặc "
                                  "python3 scripts/moc.py tenant create … cho từng đơn vị")
    if args.json:
        print(json.dumps({"ok": report.ok, "tenants": report.tenants, "problems": report.problems,
                          "notes": report.notes}, ensure_ascii=False))
        return 0 if report.ok else 1
    print("Đơn vị và Keycloak Organizations")
    for t in report.tenants:
        if t["ok"]:
            print(f"  ✓ {t['code']}: Organization {t['organization']}, {t['members']} thành viên, "
                  f"{t['accounts']} tài khoản của đơn vị; danh bạ khớp")
    for note in report.notes:
        print(f"  · {note}")
    for problem in report.problems:
        print(f"  ✗ {problem}")
    print("Khớp." if report.ok else f"Lệch: {len(report.problems)} lỗi.")
    return 0 if report.ok else 1
