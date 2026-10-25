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

"""Cắm ứng dụng vào lõi bằng manifest, không sửa tệp nào của lõi: `moc app install | list | remove | sync`
(docs/them-ung-dung.md mục 1).

    python3 scripts/moc.py app install apps/bang-tin/app.yaml [--dry-run]
    python3 scripts/moc.py app list [--json]
    python3 scripts/moc.py app remove bang-tin [--dry-run]
    python3 scripts/moc.py app sync [--files] [--json]

Trạng thái mong muốn nằm trong `.moc-apps/` của thư mục chạy (ngoài git): bản ghi từng ứng dụng đã cài
(`apps/<tên>.json`: manifest đã kiểm, SQL migration, image) và các tệp dựng từ bản ghi + tệp lõi:
  - `apisix.yaml`: `platform/apisix/apisix.yaml` chép nguyên văn, chèn upstream và route của ứng dụng (trước route bắt
    mọi đường của app-office). Ghi đè TẠI CHỖ: APISIX gắn từng tệp, mỗi giây so mtime và tự nạp lại; tệp mới đổi tên
    vào chỗ thì container không thấy (inode cũ). Lúc đang ghi APISIX thấy thiếu dấu #END và giữ cấu hình cũ;
  - `hasura-metadata/`: `db/metadata` chép nguyên văn + bảng, quyền, quan hệ của ứng dụng + event trigger. Image
    cli-migrations của Hasura áp lại thư mục này mỗi lần khởi động: phần của ứng dụng sống qua khởi động lại;
  - `docker-compose.apps.yml`: tệp phủ — bind mount của apisix, hasura trỏ sang hai mục trên, bí mật header webhook cho
    hasura (env_file), service app-<tên> của từng ứng dụng. `COMPOSE_FILE` trong .env thêm tệp này;
  - `hasura.env`, `<tên>.env` (0600): bí mật sinh lúc cài — không nằm trong manifest, không in ra.
CSDL ghi trạng thái đã áp: `core.apps`, `core.app_migrations` (migration 1792281603200, có sổ kiểm toán).

Migration của ứng dụng chạy trên một phiên psql mà session user là vai trò CSDL riêng của ứng dụng
(`moc_appdb_<schema>`: không superuser, không CREATEROLE, BYPASSRLS, chỉ làm chủ schema của nó, không quyền gì trên
`core`, `office`, `personal`; LOGIN chỉ trong lúc chạy migration). RESET ROLE hay SQL động không leo lên được vai trò
khác; đối tượng tạo ra vẫn thuộc vai trò đó. Cuối mỗi migration, cùng giao dịch, `moc_app.migration_done()` kiểm các
đối tượng trong schema (không dựa vào bảng, hàm ngoài schema; hàm của ứng dụng thành SECURITY DEFINER) — vì Hasura đọc,
ghi bảng ứng dụng bằng superuser `moc`. Vẫn là ứng dụng ĐÃ TIN: container của nó ở mạng nội bộ `moc`. Gỡ ứng dụng không
xóa dữ liệu (schema, các dòng, vai trò CSDL còn nguyên).

Thoát 0: xong; 1: bị từ chối (manifest sai, xung đột) hoặc một bước lỗi — in rõ bước nào, sửa rồi chạy lại; 2: không gọi
được Signet (CSDL, Keycloak, Docker).
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import math
import os
import pathlib
import re
import secrets
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from typing import Any

import realm_clients
import tenants
import yaml_nho
from tenants import Unavailable

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPOSE = ["docker", "compose", "--profile", "core", "--profile", "app"]
STATE = ".moc-apps"
OVERLAY = f"{STATE}/docker-compose.apps.yml"
GATEWAY = f"{STATE}/apisix.yaml"
METADATA = f"{STATE}/hasura-metadata"
HASURA_ENV = f"{STATE}/hasura.env"
CORE_GATEWAY = "platform/apisix/apisix.yaml"
CORE_METADATA = "db/metadata"
SCHEMA = "scripts/app-manifest.schema.json"
FORMAT = 1                                   # định dạng bản ghi .moc-apps/apps/<tên>.json

# Danh sách trắng sự kiện của lõi: PHẢI trùng mảng trong core.app_events_publish() (migration 1792281603200; test kiểm)
EVENT_KINDS = ("office.document.received", "office.document.registered", "office.document.issued")
USER_ROLES = ("clerk", "staff", "manager", "director", "tenant_admin")    # moc_role trong realm
CORE_SCHEMAS = ("core", "office")             # quan hệ từ bảng ứng dụng chỉ được trỏ về đây (một chiều)
# Hasura chạy điều kiện trong quyền bằng quyền admin: `_exists` và điều kiện đi qua quan hệ sang lõi đọc được dữ liệu
# mọi đơn vị (kể cả văn bản hạn chế), quyền của bảng đích không áp. Qua quan hệ sang lõi chỉ nhận đúng luật đọc của lõi
# (trường `visible` = office.document_visible, chạy theo phiên người gọi)
CORE_READ_RULE = {"visible": {"_eq": True}}
RESERVED_SCHEMAS = {"core", "office", "personal", "public", "hdb_catalog", "information_schema", "flowable",
                    "keycloak", "topology", "cron", "graphql", "moc_app"}
RESERVED_NAMES = {"office", "ca-nhan", "core", "moc", "admin", "api", "svc"}
# Đường của lõi (platform/apisix/apisix.yaml), của ứng dụng có sẵn và trang của apps/office (test so với
# apps/office/app/pages): ứng dụng mới không được che
RESERVED_PATHS = {
    "/realms", "/resources", "/v1", "/v2", "/v1alpha1", "/api", "/realtime", "/admin", "/console", "/healthz",
    "/metrics", "/flowable-rest", "/status", "/ca-nhan", "/config", "/favicon",
    "/cam-bien", "/dang-nhap", "/dieu-hanh", "/gop-y", "/ho-so", "/hoi-dap", "/pha-he", "/so-dang-ky", "/so-do",
    "/so-kiem-toan", "/tim-kiem", "/trang-thai", "/tu-chan-doan", "/van-ban", "/van-ban-den", "/van-ban-di",
    "/xac-thuc", "/ung-dung",
}
# Biến môi trường do lõi đặt cho container ứng dụng; manifest không ghi đè được
PROVIDED_ENV = {"MOC_REALM", "MOC_APP_NAME", "MOC_APP_PATH", "MOC_KEYCLOAK_INTERNAL_URL", "MOC_GRAPHQL_INTERNAL_URL",
                "MOC_HOOK_SECRET", "MOC_CLIENT_ID", "MOC_CLIENT_SECRET"}
SECRET_NAME = re.compile(r"SECRET|PASSW|TOKEN|KEY|CREDENTIAL|PRIVATE", re.I)
MIGRATION_DIR = re.compile(r"([0-9]{1,20})_([a-z0-9_]{1,60})")
TENANT_VAR = "x-hasura-tenant-id"
MAX_SQL_BYTES = 1_000_000
HOOK_HEADER = "X-Moc-Hook-Secret"
DEFAULT_RETRY = {"num_retries": 5, "interval_sec": 10, "timeout_sec": 10}


class AppError(Exception):
    """Không làm được hoặc làm thì sai — viết cho người vận hành đọc (thoát 1)."""


class StepFailed(Exception):
    def __init__(self, number: int, total: int, name: str, error: Exception):
        super().__init__(f"bước {number}/{total} ({name}): {error}")
        self.error = error


def underscore(name: str) -> str:
    return name.replace("-", "_")


def hook_env(name: str) -> str:
    return f"MOC_APP_HOOK_{underscore(name).upper()}"


def service_role(name: str) -> str:
    return f"app_{underscore(name)}"


# ---------------------------------------------------------------------------------------- JSON Schema (tập con)

SCHEMA_KEYWORDS = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "properties", "required",
                   "additionalProperties", "items", "minItems", "maxItems", "uniqueItems", "enum", "pattern",
                   "minLength", "maxLength", "minimum", "maximum", "oneOf", "propertyNames", "maxProperties"}
_TYPES: dict[str, Callable[[Any], bool]] = {
    "object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str), "boolean": lambda v: isinstance(v, bool), "null": lambda v: v is None,
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


def schema_errors(value: Any, schema: dict[str, Any], root: dict[str, Any], where: str = "") -> list[str]:
    """Lỗi của value theo schema — chỉ các từ khóa trong SCHEMA_KEYWORDS (test kiểm scripts/app-manifest.schema.json
    không dùng từ khóa nào khác). where: đường tới giá trị, vd `events.kinds[0]`."""
    here = where or "(gốc)"
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ValueError(f"$ref không hỗ trợ: {ref}")
        return schema_errors(value, root["$defs"][ref.split("/")[-1]], root, where)
    if "oneOf" in schema:
        passing = [s for s in schema["oneOf"] if not schema_errors(value, s, root, where)]
        if len(passing) != 1:
            alts = [schema_errors(value, s, root, where) for s in schema["oneOf"]]
            best = min(alts, key=len)
            return best if len(passing) == 0 else [f"{here}: khớp nhiều hơn một dạng"]
    errors: list[str] = []
    kind = schema.get("type")
    if kind and not _TYPES[kind](value):
        return [f"{here}: phải là {kind}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{here}: phải là một trong {', '.join(map(str, schema['enum']))}"]
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", math.inf):
            errors.append(f"{here}: độ dài phải trong [{schema.get('minLength', 0)}, {schema.get('maxLength', '∞')}]")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):     # `$` của Python nhận "x\n"
            errors.append(f"{here}: {value!r} không khớp mẫu {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            errors.append(f"{here}: phải trong [{schema.get('minimum', '-∞')}, {schema.get('maximum', '∞')}]")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            errors.append(f"{here}: số phần tử phải trong [{schema.get('minItems', 0)}, {schema.get('maxItems', '∞')}]")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errors.append(f"{here}: có phần tử trùng")
        if "items" in schema:
            for i, item in enumerate(value):
                errors += schema_errors(item, schema["items"], root, f"{where}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{here}: thiếu {key}")
        if len(value) > schema.get("maxProperties", math.inf):
            errors.append(f"{here}: quá {schema['maxProperties']} khóa")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            path = f"{where}.{key}" if where else key
            if "propertyNames" in schema:
                errors += [e.replace(path, f"tên {path}") for e in schema_errors(key, schema["propertyNames"], root,
                                                                                    path)]
            if key in props:
                errors += schema_errors(item, props[key], root, path)
            elif extra is False:
                errors.append(f"{path}: khóa không được nhận")
            elif isinstance(extra, dict):
                errors += schema_errors(item, extra, root, path)
    return errors


# ---------------------------------------------------------------------------------------- đọc và kiểm manifest

def _inside(base: pathlib.Path, rel: str, what: str) -> pathlib.Path:
    path = (base / rel).resolve()
    if path != base and base not in path.parents:
        raise AppError(f"{what} {rel!r} nằm ngoài thư mục ứng dụng {base}")
    return path


def read_migrations(folder: pathlib.Path) -> list[dict[str, Any]]:
    """<số>_<tên>/up.sql theo thứ tự số → [{version, name, sha256, sql}]. Thư mục migration, từng thư mục con và từng
    up.sql phải nằm trong thư mục đó sau khi theo symlink (không đọc SQL của lõi hay chỗ khác)."""
    if not folder.is_dir():
        raise AppError(f"không có thư mục migration {folder}")
    folder = folder.resolve()
    out = []
    for entry in sorted(folder.iterdir()):
        if entry.name.startswith(".") or entry.is_file():
            continue
        m = MIGRATION_DIR.fullmatch(entry.name)
        up = entry / "up.sql"
        if not m or not up.is_file():
            raise AppError(f"migration {entry.name}: cần thư mục <số>_<tên> (chữ thường, số, _) có up.sql")
        real = up.resolve()
        if entry.resolve().parent != folder or real.parent != entry.resolve():
            raise AppError(f"migration {entry.name}: thư mục hoặc up.sql là symlink ra ngoài {folder}")
        raw = real.read_bytes()
        if len(raw) > MAX_SQL_BYTES:
            raise AppError(f"migration {entry.name}: up.sql lớn quá {MAX_SQL_BYTES // 1000} kB")
        try:
            sql = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise AppError(f"migration {entry.name}: up.sql không phải UTF-8") from None
        if "\x00" in sql or not sql.strip():
            raise AppError(f"migration {entry.name}: up.sql rỗng hoặc có ký tự NUL")
        out.append({"version": int(m.group(1)), "name": m.group(2), "sha256": hashlib.sha256(raw).hexdigest(),
                    "sql": sql})
    versions = [m["version"] for m in out]
    if len(set(versions)) != len(versions):
        raise AppError("hai migration cùng số phiên bản")
    return sorted(out, key=lambda m: m["version"])


def tree_hash(folder: pathlib.Path) -> str:
    """Băm thư mục dựng image (đường tương đối + nội dung từng tệp), bỏ node_modules, .git, __pycache__."""
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder)
        if {"node_modules", ".git", "__pycache__"} & set(rel.parts):
            continue
        h.update(str(rel).encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def tenant_scoped(expr: Any) -> bool:
    """Điều kiện Hasura có `tenant_id: {_eq: X-Hasura-Tenant-Id}` ở gốc hoặc trong `_and` ở gốc (lồng `_and` tiếp được).
    Trong `_or`, `_not`, `_exists` hay qua quan hệ thì không tính: ở đó điều kiện bị nới hoặc đổi nghĩa."""
    if not isinstance(expr, dict):
        return False
    cond = expr.get("tenant_id")
    if isinstance(cond, dict) and list(cond) == ["_eq"] and str(cond["_eq"]).lower() == TENANT_VAR:
        return True
    ands = expr.get("_and")
    return isinstance(ands, list) and any(tenant_scoped(e) for e in ands)


def _tenant_set(perm: dict[str, Any]) -> bool:
    return str((perm.get("set") or {}).get("tenant_id", "")).lower() == TENANT_VAR


def check_tables(m: dict[str, Any]) -> list[str]:
    """Bảng, quan hệ, quyền Hasura của ứng dụng: chỉ trong schema của nó, quan hệ một chiều về lõi, vai trò cho phép,
    vai trò người dùng phải lọc theo đơn vị."""
    errors: list[str] = []
    schema = m["database"]["schema"]
    roles = set(USER_ROLES) | ({service_role(m["name"])} if m.get("service_account") else set())
    seen: set[str] = set()
    tables = m.get("metadata", {}).get("tables", [])
    rels = {f"{t['table']['schema']}.{t['table']['name']}": _rel_targets(t) for t in tables}
    for t in tables:
        ref = f"{t['table']['schema']}.{t['table']['name']}"
        if t["table"]["schema"] != schema:
            errors.append(f"metadata: bảng {ref} không nằm trong schema {schema} của ứng dụng")
        if ref in seen:
            errors.append(f"metadata: bảng {ref} khai hai lần")
        seen.add(ref)
        for kind in ("object_relationships", "array_relationships"):
            for rel in t.get(kind, []):
                using = rel["using"]
                where = f"metadata: {ref} quan hệ {rel['name']}"
                if set(using) - {"foreign_key_constraint_on", "manual_configuration"} or len(using) != 1:
                    errors.append(f"{where}: chỉ nhận foreign_key_constraint_on hoặc manual_configuration")
                    continue
                if "manual_configuration" in using:
                    remote = (using["manual_configuration"] or {}).get("remote_table") or {}
                    target = remote.get("schema", "public")
                    if target != schema and target not in CORE_SCHEMAS:
                        errors.append(f"{where}: chỉ được trỏ về schema {schema} hoặc {', '.join(CORE_SCHEMAS)}")
                fk = using.get("foreign_key_constraint_on")
                if kind == "array_relationships" and isinstance(fk, dict):
                    target = (fk.get("table") or {}).get("schema", "public")
                    if target != schema:
                        errors.append(f"{where}: quan hệ mảng theo khóa ngoại chỉ trong schema {schema} (lõi không "
                                      "trỏ ngược về ứng dụng)")
        for kind in ("select_permissions", "insert_permissions", "update_permissions"):
            for p in t.get(kind, []):
                role, perm = p["role"], p["permission"]
                where = f"metadata: {ref} {kind[:-12]} của {role}"
                if role not in roles:
                    allowed = ", ".join(sorted(roles))
                    errors.append(f"{where}: vai trò không được dùng (chỉ {allowed}; vai trò app_… cần "
                                  "service_account: true)")
                    continue
                for key in ("filter", "check"):
                    errors += _rule_errors(perm.get(key), ref, rels, schema, f"{where} {key}")
                if role in USER_ROLES:
                    errors += _tenant_errors(kind, perm, where)
    return errors


def _rel_targets(t: dict[str, Any]) -> dict[str, str | None]:
    """Quan hệ của một bảng → bảng đích `schema.tên`; None khi manifest không nói (khóa ngoại một cột)."""
    out: dict[str, str | None] = {}
    for kind in ("object_relationships", "array_relationships"):
        for rel in t.get(kind, []):
            using = rel.get("using") or {}
            target = (using.get("manual_configuration") or {}).get("remote_table")
            fk = using.get("foreign_key_constraint_on")
            if target is None and isinstance(fk, dict):
                target = fk.get("table")
            out[rel["name"]] = f"{target.get('schema', 'public')}.{target.get('name')}" \
                if isinstance(target, dict) else None
    return out


def _rule_errors(expr: Any, table: str, rels: dict[str, dict[str, str | None]], schema: str,
                 where: str) -> list[str]:
    """Điều kiện trong quyền không đọc được dữ liệu lõi: cấm `_exists`; qua quan hệ không rõ đích hoặc sang lõi chỉ
    nhận CORE_READ_RULE; qua quan hệ sang bảng của ứng dụng thì kiểm tiếp theo quan hệ của bảng đó."""
    if isinstance(expr, list):
        return [e for x in expr for e in _rule_errors(x, table, rels, schema, where)]
    if not isinstance(expr, dict):
        return []
    errors: list[str] = []
    for key, value in expr.items():
        if key == "_exists":
            errors.append(f"{where}: không được dùng _exists (Hasura chạy bằng quyền admin, đọc được bảng của lõi)")
        elif key in ("_and", "_or", "_not"):
            errors += _rule_errors(value, table, rels, schema, where)
        elif key.endswith("_aggregate") and key[:-10] in rels.get(table, {}):
            # điều kiện tổng hợp `<quan hệ mảng>_aggregate: {count: {predicate, filter}}` cũng chạy bằng quyền admin
            target = rels[table][key[:-10]]
            if target is None or target.split(".")[0] != schema:
                errors.append(f"{where}: không được dùng {key} qua quan hệ sang lõi hoặc không rõ bảng đích")
            elif isinstance(value, dict):
                for spec in value.values():
                    if isinstance(spec, dict):
                        errors += _rule_errors(spec.get("filter"), target, rels, schema, where)
        elif key in rels.get(table, {}):
            target = rels[table][key]
            if target is not None and target.split(".")[0] == schema:
                errors += _rule_errors(value, target, rels, schema, where)
            elif value != CORE_READ_RULE:
                errors.append(f"{where}: qua quan hệ {key} (sang lõi hoặc khóa ngoại không rõ bảng đích) chỉ nhận "
                              "visible: {_eq: true} — điều kiện khác chạy bằng quyền admin, đọc được dữ liệu đơn vị "
                              "khác; lọc theo bảng của ứng dụng thì khai quan hệ bằng manual_configuration")
    return errors


def _tenant_errors(kind: str, perm: dict[str, Any], where: str) -> list[str]:
    """Vai trò người dùng: đọc, sửa chỉ dòng của đơn vị mình; thêm, sửa xong dòng vẫn là của đơn vị mình."""
    rule = "tenant_id: {_eq: X-Hasura-Tenant-Id} ở gốc hoặc trong _and ở gốc (cách ly đơn vị)"
    if kind == "insert_permissions":
        ok = _tenant_set(perm) or tenant_scoped(perm.get("check"))
        return [] if ok else [f"{where}: set tenant_id: X-Hasura-Tenant-Id, hoặc check có {rule}"]
    errors = [] if tenant_scoped(perm.get("filter")) else [f"{where}: filter phải có {rule}"]
    if kind == "update_permissions" and "tenant_id" in (perm.get("columns") or []) \
            and not (_tenant_set(perm) or tenant_scoped(perm.get("check"))):
        errors.append(f"{where}: sửa được tenant_id thì check phải có {rule}")
    return errors


def check_manifest(m: dict[str, Any], base: pathlib.Path, schema: dict[str, Any]) -> list[str]:
    errors = schema_errors(m, schema, schema)
    if errors:
        return errors
    name, path, db_schema = m["name"], m["path"], m["database"]["schema"]
    if name in RESERVED_NAMES:
        errors.append(f"name: {name!r} là tên giữ chỗ của lõi")
    if path in RESERVED_PATHS:
        errors.append(f"path: {path} trùng đường của lõi hoặc trang của Văn phòng điện tử")
    if db_schema in RESERVED_SCHEMAS or db_schema.startswith("pg_"):
        errors.append(f"database.schema: {db_schema!r} là schema của lõi hoặc hệ thống")
    for key in ("title", "description"):
        if re.search(r"[\x00-\x1f\x7f]", m.get(key, "")):
            errors.append(f"{key}: không được có ký tự điều khiển, xuống dòng")
    for key in m.get("environment", {}):
        if key in PROVIDED_ENV or key.startswith("MOC_APP_"):
            errors.append(f"environment.{key}: biến do lõi đặt, không ghi đè được")
        elif SECRET_NAME.search(key):
            errors.append(f"environment.{key}: tên giống bí mật — manifest không chứa bí mật; bí mật do lệnh sinh "
                          "lúc cài (MOC_HOOK_SECRET, MOC_CLIENT_SECRET)")
    test = m.get("healthcheck", {}).get("test")
    if test and test[0] not in ("CMD", "CMD-SHELL"):
        errors.append("healthcheck.test: phần tử đầu phải là CMD hoặc CMD-SHELL")
    if "events" in m and m["events"]["webhook"]["port"] == m["port"]:
        errors.append("events.webhook.port: phải khác port của trang (cổng webhook không có route qua APISIX)")
    if "build" in m["image"]:
        try:
            folder = _inside(base, m["image"]["build"], "image.build")
            if not (folder / "Dockerfile").is_file():
                errors.append(f"image.build: {folder} không có Dockerfile")
        except AppError as exc:
            errors.append(str(exc))
    return errors + check_tables(m)


def load_manifest(path: pathlib.Path, *, root: pathlib.Path = ROOT) -> dict[str, Any]:
    """Đọc, kiểm app.yaml → bản ghi đã chuẩn hóa (chưa có image tag nếu dựng từ thư mục). Sai thì AppError liệt kê
    mọi lỗi."""
    path = path.resolve()
    if not path.is_file():
        raise AppError(f"không có tệp manifest {path}")
    base = path.parent
    raw = path.read_bytes()
    try:
        manifest = yaml_nho.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml_nho.YamlError) as exc:
        raise AppError(f"{path.name}: {exc}") from None
    if not isinstance(manifest, dict):
        raise AppError(f"{path.name}: cần một ánh xạ ở gốc")
    schema = json.loads((root / SCHEMA).read_text(encoding="utf-8"))
    errors = check_manifest(manifest, base, schema)
    if errors:
        raise AppError(f"{path.name} chưa đúng ({len(errors)} lỗi):\n  - " + "\n  - ".join(errors))
    folder = manifest["database"].get("migrations")
    migrations = read_migrations(_inside(base, folder, "database.migrations")) if folder else []
    build = str(_inside(base, manifest["image"]["build"], "image.build")) if "build" in manifest["image"] else None
    events = None
    if "events" in manifest:
        events = {"kinds": sorted(manifest["events"]["kinds"]), "port": manifest["events"]["webhook"]["port"],
                  "path": manifest["events"]["webhook"]["path"],
                  "retry": {**DEFAULT_RETRY, **manifest["events"].get("retry", {})}}
    return {
        "format": FORMAT, "name": manifest["name"], "title": manifest["title"],
        "description": manifest.get("description", ""), "version": manifest["version"], "path": manifest["path"],
        "port": manifest["port"], "build": build, "image": manifest["image"].get("ref"),
        "healthcheck": manifest.get("healthcheck"), "memory": manifest.get("memory", "256m"),
        "read_only": manifest.get("read_only", True),
        "environment": manifest.get("environment", {}), "schema": manifest["database"]["schema"],
        "migrations": migrations, "tables": manifest.get("metadata", {}).get("tables", []),
        "service_account": bool(manifest.get("service_account")), "events": events,
        "manifest": manifest, "manifest_sha256": hashlib.sha256(raw).hexdigest(), "source": str(path),
    }


# ---------------------------------------------------------------------------------------- sinh tệp (hàm thuần)

def gateway_text(core: str, apps: list[dict[str, Any]]) -> str:
    """Tệp chạy của APISIX: tệp lõi nguyên văn; upstream của ứng dụng chèn ngay sau `upstreams:`, route chèn ngay trước
    route `app-office` (bắt mọi đường, priority -10). Không ứng dụng nào: trả đúng tệp lõi."""
    if not apps:
        return core
    lines = core.splitlines(keepends=True)
    try:
        up = next(i for i, ln in enumerate(lines) if ln.rstrip("\r\n") == "upstreams:")
        routes = next(i for i, ln in enumerate(lines) if ln.rstrip("\r\n") == "routes:")
        office = next(i for i in range(routes, len(lines)) if lines[i].rstrip("\r\n") == "  - id: app-office")
    except StopIteration:
        raise AppError(f"{CORE_GATEWAY}: không thấy mốc `upstreams:`, `routes:` hoặc route `app-office` — tệp lõi đổi "
                       "cấu trúc, cần sửa scripts/ung_dung.py") from None
    if core.rstrip()[-4:] != "#END":
        raise AppError(f"{CORE_GATEWAY}: thiếu dấu #END ở cuối")
    for app in apps:
        if re.search(rf"^\s*- id: app-{re.escape(app['name'])}\s*$", core, re.M):
            raise AppError(f"{CORE_GATEWAY} đã có id app-{app['name']} — ứng dụng này là một phần của lõi")
    ups, rts = [], []
    for app in sorted(apps, key=lambda a: a["name"]):
        n = app["name"]
        ups.append(f"  # moc app install: {n} (.moc-apps/apps/{n}.json)\n  - id: app-{n}\n    type: roundrobin\n"
                   f"    nodes:\n      \"app-{n}:{app['port']}\": 1\n")
        rts.append(f"  # moc app install: {n} — trang tĩnh, không cần token; dữ liệu đi qua route của lõi ở trên\n"
                   f"  - id: app-{n}\n    uris: [\"{app['path']}\", \"{app['path']}/*\"]\n    methods: [GET, HEAD]\n"
                   f"    upstream_id: app-{n}\n\n")
    return "".join(lines[:up + 1] + ups + lines[up + 1:office] + rts + lines[office:])


def table_file(app: dict[str, Any], table: dict[str, Any]) -> str:
    return f"app_{underscore(app['name'])}__{table['table']['schema']}_{table['table']['name']}.yaml"


def event_trigger(app: dict[str, Any]) -> dict[str, Any]:
    """Thân sự kiện chuẩn của Hasura, không request_transform: Hasura v2.51 ghi cả yêu cầu gốc (kèm header bí mật) vào
    nhật ký container khi trigger có transform (đã đo). Mọi loại trong danh sách trắng đều tới; ứng dụng tự bỏ loại
    không nghe (MOC_APP_EVENT_KINDS). session_variables là null: lõi xóa người làm trước khi ghi core.app_events."""
    ev = app["events"]
    return {
        "name": service_role(app["name"]),
        "definition": {"enable_manual": False, "insert": {"columns": "*"}},
        "retry_conf": ev["retry"],
        "webhook": f"http://app-{app['name']}:{ev['port']}{ev['path']}",
        "headers": [{"name": HOOK_HEADER, "value_from_env": hook_env(app["name"])}],
    }


GENERATED = "# Sinh bởi moc app (scripts/ung_dung.py) từ .moc-apps/apps/ — đừng sửa tay: moc app sync dựng lại\n"


def metadata_tree(core: dict[str, bytes], apps: list[dict[str, Any]]) -> dict[str, bytes]:
    """Thư mục metadata trộn: mọi tệp của db/metadata nguyên văn; thêm một tệp mỗi bảng ứng dụng (JSON — là YAML hợp lệ)
    và một dòng !include trong tables.yaml; event trigger thêm thành khóa event_triggers cuối core_app_events.yaml."""
    out = dict(core)
    tables_key = "databases/default/tables/tables.yaml"
    events_key = "databases/default/tables/core_app_events.yaml"
    if tables_key not in out:
        raise AppError(f"{CORE_METADATA}: thiếu {tables_key}")
    includes = []
    for app in sorted(apps, key=lambda a: a["name"]):
        for table in app["tables"]:
            name = table_file(app, table)
            out[f"databases/default/tables/{name}"] = (GENERATED + json.dumps(table, ensure_ascii=False, indent=2)
                                                       + "\n").encode()
            includes.append(f'- "!include {name}"\n')
    if includes:
        text = out[tables_key].decode()
        out[tables_key] = (text + ("" if text.endswith("\n") else "\n") + "# moc app install\n"
                           + "".join(includes)).encode()
    triggers = [event_trigger(a) for a in sorted(apps, key=lambda a: a["name"]) if a.get("events")]
    if triggers:
        if events_key not in out:
            raise AppError(f"{CORE_METADATA}: thiếu {events_key} (migration 1792281603200 chưa có trong lõi?)")
        text = out[events_key].decode()
        current = yaml_nho.loads(text)
        if not isinstance(current, dict) or "event_triggers" in current:
            raise AppError(f"{events_key} của lõi đã có event_triggers — cần sửa scripts/ung_dung.py để gộp")
        out[events_key] = (text + ("" if text.endswith("\n") else "\n") + "# moc app install\nevent_triggers: "
                           + json.dumps(triggers, ensure_ascii=False) + "\n").encode()
    return out


def literal(value: Any) -> str:
    """Giá trị của manifest vào tệp phủ: compose nội suy ${…} từ .env của lõi (khóa quản trị Hasura, mật khẩu CSDL…) —
    $$ để container nhận đúng nguyên văn."""
    return str(value).replace("$", "$$")


def overlay(apps: list[dict[str, Any]]) -> dict[str, Any]:
    """Tệp phủ compose. Thay bind mount theo đích (compose gộp volumes theo đường trong container), cộng env_file.
    Chỉ giá trị lõi tự đặt (MOC_REALM) được compose nội suy; mọi chuỗi lấy từ manifest đều thoát $."""
    services: dict[str, Any] = {
        "apisix": {"volumes": [f"./{GATEWAY}:/usr/local/apisix/conf/apisix.yaml:ro"]},
        "hasura": {"volumes": [f"./{METADATA}:/hasura-metadata:ro"], "env_file": [HASURA_ENV]},
    }
    for app in sorted(apps, key=lambda a: a["name"]):
        n = app["name"]
        svc: dict[str, Any] = {
            "image": app["image"], "pull_policy": "never" if app.get("build") else "missing",
            "profiles": ["app"], "restart": "unless-stopped", "networks": ["moc"],
            "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
            "read_only": app.get("read_only", True), "tmpfs": ["/tmp"], "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "mem_limit": app["memory"], "cpus": 1.0,
            "environment": {**{k: literal(v) for k, v in app["environment"].items()},
                            "MOC_REALM": "${MOC_REALM:-moc}", "MOC_APP_NAME": n,
                            "MOC_APP_PATH": app["path"], "MOC_KEYCLOAK_INTERNAL_URL": "http://keycloak:8080",
                            "MOC_GRAPHQL_INTERNAL_URL": "http://hasura:8080/v1/graphql"},
            "env_file": [f"{STATE}/{n}.env"],
        }
        if app.get("events"):
            svc["environment"]["MOC_APP_EVENT_KINDS"] = ",".join(app["events"]["kinds"])
        if app.get("healthcheck"):
            check = dict(app["healthcheck"])
            check["test"] = [literal(part) for part in check.get("test", [])]
            svc["healthcheck"] = check
        services[f"app-{n}"] = svc
    return {"services": services}


def env_text(values: dict[str, str]) -> str:
    return GENERATED + "".join(f"{k}={v}\n" for k, v in sorted(values.items()))


def parse_env(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            out[key.strip()] = value.strip()
    return out


def compose_files(current: str | None, *, with_overlay: bool) -> str | None:
    """Giá trị COMPOSE_FILE sau khi thêm/bỏ tệp phủ ứng dụng; giữ mục khác (tệp phủ log tập trung…). None: không đặt."""
    entries = [e for e in (current or "docker-compose.yml").split(":") if e]
    has = OVERLAY in entries
    if with_overlay and not has:
        entries.append(OVERLAY)
    elif not with_overlay and has:
        entries.remove(OVERLAY)
    value = ":".join(entries)
    return None if current is None and value == "docker-compose.yml" else value


# ---------------------------------------------------------------------------------------- trạng thái trên đĩa

def _write_atomic(path: pathlib.Path, data: bytes, mode: int = 0o644) -> bool:
    if path.exists() and path.read_bytes() == data and (path.stat().st_mode & 0o777) == mode:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data) if data else None
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    return True


def write_in_place(path: pathlib.Path, data: bytes) -> bool:
    """Ghi đè tệp đang được gắn vào container (bind mount một tệp): giữ inode, cắt về 0 rồi ghi một lượt, fsync, đặt
    mtime lớn hơn mtime cũ ít nhất một giây (APISIX so mtime theo giây). Chưa có tệp thì tạo mới."""
    if not path.exists():
        return _write_atomic(path, data)
    if path.read_bytes() == data:
        return False
    old = path.stat().st_mtime
    fd = os.open(path, os.O_WRONLY)
    try:
        os.ftruncate(fd, 0)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    stamp = max(time.time(), math.floor(old) + 1)
    os.utime(path, (stamp, stamp))
    return True


class State:
    """Thư mục .moc-apps/ của một thư mục chạy Signet (mã nguồn hoặc bản cài)."""

    def __init__(self, root: pathlib.Path = ROOT, *, env_file: pathlib.Path | None = None):
        self.root = root
        self.dir = root / STATE
        self.env_file = env_file or root / (".e" + "nv")

    # bản ghi ---------------------------------------------------------------------------------------------------
    def records(self) -> dict[str, dict[str, Any]]:
        folder = self.dir / "apps"
        if not folder.is_dir():
            return {}
        out = {}
        for path in sorted(folder.glob("*.json")):
            rec = json.loads(path.read_text(encoding="utf-8"))
            if rec.get("format") != FORMAT:
                raise AppError(f"{path}: định dạng bản ghi {rec.get('format')} không đọc được (cần {FORMAT})")
            out[rec["name"]] = rec
        return out

    def active(self) -> list[dict[str, Any]]:
        return [r for r in self.records().values() if not r.get("removing")]

    def save(self, rec: dict[str, Any]) -> None:
        self.dir.mkdir(exist_ok=True)
        _write_atomic(self.dir / "apps" / f"{rec['name']}.json",
                      (json.dumps(rec, ensure_ascii=False, indent=2) + "\n").encode())

    def drop(self, name: str) -> None:
        for path in (self.dir / "apps" / f"{name}.json", self.dir / f"{name}.env"):
            with contextlib.suppress(FileNotFoundError):
                path.unlink()

    # bí mật ----------------------------------------------------------------------------------------------------
    def secrets(self, name: str) -> dict[str, str]:
        path = self.dir / f"{name}.env"
        return parse_env(path.read_text(encoding="utf-8")) if path.exists() else {}

    def ensure_secrets(self, rec: dict[str, Any], *, dry_run: bool = False) -> list[str]:
        """Sinh bí mật còn thiếu (giữ bí mật đã có) → tên biến vừa sinh."""
        have = self.secrets(rec["name"])
        want = dict(have)
        if rec.get("events") and not want.get("MOC_HOOK_SECRET"):
            want["MOC_HOOK_SECRET"] = secrets.token_urlsafe(32)
        if rec.get("service_account"):
            want["MOC_CLIENT_ID"] = f"app-{rec['name']}-svc"
            if not want.get("MOC_CLIENT_SECRET"):
                want["MOC_CLIENT_SECRET"] = secrets.token_urlsafe(32)
        made = sorted(k for k in want if k not in have and k != "MOC_CLIENT_ID")
        if not dry_run:
            _write_atomic(self.dir / f"{rec['name']}.env", env_text(want).encode(), 0o600)
        return made

    # tệp dựng ra ------------------------------------------------------------------------------------------------
    def core_metadata(self) -> dict[str, bytes]:
        base = self.root / CORE_METADATA
        return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}

    def derived(self) -> dict[str, bytes]:
        """Nội dung mọi tệp dựng ra (đường tương đối với thư mục chạy), trừ tệp bí mật của từng ứng dụng."""
        apps = self.active()
        gateway = gateway_text((self.root / CORE_GATEWAY).read_text(encoding="utf-8"), apps)
        out = {GATEWAY: gateway.encode()}
        for rel, data in metadata_tree(self.core_metadata(), apps).items():
            out[f"{METADATA}/{rel}"] = data
        out[OVERLAY] = (GENERATED + json.dumps(overlay(apps), ensure_ascii=False, indent=2) + "\n").encode()
        return out

    def write(self, *, dry_run: bool = False) -> list[str]:
        """Dựng lại mọi tệp từ bản ghi + tệp lõi, chỉ ghi tệp có nội dung khác → danh sách tệp đã (sẽ) đổi."""
        if not self.dir.is_dir():
            return []
        changed = []
        want = self.derived()
        hooks = {hook_env(r["name"]): self.secrets(r["name"]).get("MOC_HOOK_SECRET", "")
                 for r in self.active() if r.get("events")}
        hasura_env = env_text({k: v for k, v in hooks.items() if v}).encode()
        current_meta = {str(p.relative_to(self.root)) for p in (self.root / METADATA).rglob("*") if p.is_file()} \
            if (self.root / METADATA).is_dir() else set()
        for rel, data in want.items():
            path = self.root / rel
            if path.exists() and path.read_bytes() == data:
                continue
            changed.append(rel)
            if not dry_run:
                (write_in_place if rel == GATEWAY else _write_atomic)(path, data)
        env_path = self.root / HASURA_ENV
        if not env_path.exists() or env_path.read_bytes() != hasura_env:
            changed.append(HASURA_ENV)
            if not dry_run:
                _write_atomic(env_path, hasura_env, 0o600)
        for rel in sorted(current_meta - set(want)):
            changed.append(f"{rel} (bỏ)")
            if not dry_run:
                (self.root / rel).unlink()
        for rec in self.active():
            if not (self.dir / f"{rec['name']}.env").exists():
                changed.append(f"{STATE}/{rec['name']}.env")
                if not dry_run:
                    self.ensure_secrets(rec)
        if self.env_file.exists():
            current = parse_env(self.env_file.read_text(encoding="utf-8")).get("COMPOSE_FILE")
            value = compose_files(current, with_overlay=True)
            if value != current:
                changed.append(f"COMPOSE_FILE trong {self.env_file.name}")
                if not dry_run:
                    set_env_value(self.env_file, "COMPOSE_FILE", value or "")
        return changed

    def stale(self) -> list[str]:
        """Tệp dựng ra đang khác với cái lẽ ra phải có (vd lõi vừa đổi mà chưa sync)."""
        return [rel for rel, data in self.derived().items()
                if not (self.root / rel).exists() or (self.root / rel).read_bytes() != data]


def set_env_value(path: pathlib.Path, key: str, value: str) -> None:
    """Đặt KHÓA=giá trị trong .env (thay dòng đang có, không thì thêm cuối); giữ quyền của tệp, không in gì."""
    lines = path.read_text(encoding="utf-8").splitlines()
    idx = [i for i, ln in enumerate(lines) if ln.startswith(f"{key}=")]
    line = f"{key}={value}"
    if idx:
        lines[idx[-1]] = line
    else:
        lines += ["", "# moc app: tệp phủ compose của ứng dụng đã cài (docs/them-ung-dung.md), giữ các mục khác", line]
    mode = path.stat().st_mode & 0o777
    _write_atomic(path, ("\n".join(lines) + "\n").encode(), mode)


# ---------------------------------------------------------------------------------------- gọi hệ thống

APPLY_METADATA = (
    "set -e; rm -rf /tmp/moc-apps; mkdir -p /tmp/moc-apps/metadata; cp -a /hasura-metadata/. /tmp/moc-apps/metadata/;"
    " cd /tmp/moc-apps; printf 'version: 3\\nendpoint: http://localhost:8080\\nmetadata_directory: metadata\\n'"
    " > config.yaml; hasura-cli metadata apply --skip-update-check 2>&1")
CALL_METADATA = ('curl -sS -H "X-Hasura-Admin-Secret: $HASURA_GRAPHQL_ADMIN_SECRET" -H "Content-Type: application/json"'
                 " --data-binary @- http://127.0.0.1:8080/v1/metadata")


def _tail(text: str, n: int = 4) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " / ".join(lines[-n:])


class System:
    """Docker, compose, CSDL, Hasura, Keycloak của một thư mục chạy. Test thay từng phần (exec, db, kc)."""

    def __init__(self, root: pathlib.Path = ROOT, *, exec_prefix: dict[str, list[str]] | None = None,
                 db: Any = None, kc: Any = None):
        self.root = root
        self._exec = exec_prefix or {}
        self._db = db
        self._kc = kc

    def env(self) -> dict[str, str]:
        """Biến môi trường cho docker compose: Makefile có thể đã export COMPOSE_FILE (log tập trung) — thêm tệp phủ ứng
        dụng vào đó; không export thì compose đọc COMPOSE_FILE trong .env (State.write giữ cho đúng)."""
        env = dict(os.environ)
        if "COMPOSE_FILE" in env and (self.root / OVERLAY).exists():
            env["COMPOSE_FILE"] = compose_files(env["COMPOSE_FILE"], with_overlay=True) or "docker-compose.yml"
        return env

    def run(self, cmd: list[str], *, input: str | None = None, timeout: float = 900) -> str:
        try:
            proc = subprocess.run(cmd, cwd=self.root, env=self.env(), input=input, capture_output=True, text=True,
                                  encoding="utf-8", timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Unavailable(f"không chạy được {' '.join(cmd[:3])}: {exc}") from None
        if proc.returncode != 0:
            raise AppError(f"{' '.join(cmd[:4])}… thoát {proc.returncode}: {_tail(proc.stderr or proc.stdout)}")
        return proc.stdout

    def compose(self, *args: str, timeout: float = 900) -> str:
        return self.run([*COMPOSE, *args], timeout=timeout)

    def exec(self, service: str, *cmd: str, input: str | None = None, timeout: float = 300) -> str:
        prefix = self._exec.get(service) or [*COMPOSE, "exec", "-T", service]
        return self.run([*prefix, *cmd], input=input, timeout=timeout)

    @property
    def db(self) -> Any:
        if self._db is None:
            self._db = tenants.database()
        return self._db

    @property
    def kc(self) -> Any:
        if self._kc is None:
            self._kc = tenants.connect()
        return self._kc

    def client_secret_ok(self, client_id: str, secret: str) -> bool | None:
        """Bí mật trong .moc-apps có còn đúng với client dịch vụ không: thử lấy token client credentials qua cổng quản
        trị nội bộ (127.0.0.1, như moc tenant). None: không gọi được Keycloak."""
        import moc_env
        url = f"{moc_env.KEYCLOAK_ADMIN_URL}/realms/{moc_env.REALM}/protocol/openid-connect/token"
        try:
            moc_env.call_json("POST", url, form={"grant_type": "client_credentials", "client_id": client_id,
                                                 "client_secret": secret})
            return True
        except moc_env.HTTPError as exc:
            return False if exc.status in (400, 401) else None
        except OSError:
            return None

    def image_exists(self, ref: str) -> bool:
        try:
            self.run(["docker", "image", "inspect", "--format", "{{.Id}}", ref], timeout=60)
            return True
        except AppError:
            return False

    def metadata(self, body: dict[str, Any]) -> Any:
        out = self.exec("hasura", "sh", "-c", CALL_METADATA, input=json.dumps(body))
        try:
            data = json.loads(out)
        except ValueError:
            raise AppError(f"Hasura trả lời lạ: {out[:200]}") from None
        if isinstance(data, dict) and data.get("error"):
            raise AppError(f"Hasura từ chối {body.get('type')}: {data.get('error')}")
        return data

    def apply_metadata(self) -> str:
        return self.exec("hasura", "sh", "-c", APPLY_METADATA, timeout=180)


# ---------------------------------------------------------------------------------------- CSDL

DB_READY_SQL = "select json_build_object('ready', to_regclass('core.app_migrations') is not null)"
DB_STATE_SQL = """
select json_build_object(
  'app', (select row_to_json(a) from (select name, schema_name, removed_at from core.apps where name = :'name') a),
  'schema_owner', (select a.name from core.apps a where a.schema_name = :'schema' and a.name <> :'name'),
  'path_owner', (select a.name from core.apps a where a.path = :'path' and a.name <> :'name' and a.removed_at is null),
  'schema_exists', exists (select 1 from pg_namespace where nspname = :'schema'),
  'applied', coalesce((select json_object_agg(version::text, sha256) from core.app_migrations
                       where app = :'name'), '{}'::json))
"""
# Cài lại không đổi gì thì không ghi gì (không thêm dòng sổ kiểm toán)
REGISTER_SQL = """
begin;
set local moc.actor = 'moc app';
set local moc.actor_kind = 'system';
insert into core.apps (name, title, path, schema_name, version, manifest, manifest_sha256)
values (:'name', :'title', :'path', :'schema', :'version', convert_from(decode(:'manifest', 'base64'), 'UTF8')::jsonb,
        :'sha')
on conflict (name) do update set title = excluded.title, path = excluded.path, version = excluded.version,
  manifest = excluded.manifest, manifest_sha256 = excluded.manifest_sha256, removed_at = null, updated_at = now()
  where core.apps.schema_name = excluded.schema_name
    and (core.apps.title, core.apps.path, core.apps.version, core.apps.manifest, core.apps.manifest_sha256,
         core.apps.removed_at) is distinct from
        (excluded.title, excluded.path, excluded.version, excluded.manifest, excluded.manifest_sha256,
         null::timestamptz);
select json_build_object('ok', exists (select 1 from core.apps where name = :'name' and schema_name = :'schema'));
commit;
"""
# Vai trò CSDL của mỗi ứng dụng: chỉ đăng nhập được (LOGIN) lúc chạy migration, không quyền gì ngoài schema của nó
APP_ROLE = re.compile(r"moc_appdb_[a-z][a-z0-9_]*")
ROLE_ATTRS = "nologin nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls connection limit 2"
APP_ROLES_SQL = "select rolname from pg_roles where rolname ~ '^moc_appdb_[a-z][a-z0-9_]*$' order by 1;"
# Vai trò CSDL riêng của ứng dụng (tên, schema đã kiểm bằng mẫu ^[a-z][a-z0-9_]*$): làm chủ schema, chỉ thêm quyền gọi
# moc_app.migration_done (migration 1792281603200). Chạy lại được; không superuser, không là thành viên vai trò nào
ROLE_SQL = """
begin;
do $moc$ begin
  if not exists (select 1 from pg_roles where rolname = '{role}') then
    create role "{role}";
  end if;
end $moc$;
alter role "{role}" with """ + ROLE_ATTRS + """ password null;
create schema if not exists "{schema}" authorization "{role}";
grant usage on schema moc_app to "{role}";
grant execute on function moc_app.migration_done(text, bigint, text, text) to "{role}";
select json_build_object('ok', (select nspowner::regrole::text from pg_namespace where nspname = '{schema}')
                               = '{role}');
commit;
"""
LOGIN_SQL = 'alter role "{role}" {login};\nselect json_build_object(\'ok\', true);\n'
# Chạy trên phiên mà session user là vai trò của ứng dụng (psql -U, socket Unix trong container postgres). SQL của ứng
# dụng gửi dạng base64, giải mã trong CSDL rồi EXECUTE: psql không diễn giải lệnh `\` nào; COMMIT trong đó bị từ chối
MIGRATE_SQL = """
begin;
set local search_path to "{schema}";
do $moc$ begin execute convert_from(decode('{sql}', 'base64'), 'UTF8'); end $moc$;
set local moc.actor = 'moc app';
set local moc.actor_kind = 'system';
select moc_app.migration_done(:'name', {version}, :'mname', :'sha');
commit;
"""
# Bảng khai trong metadata mà CSDL chưa có (gõ nhầm tên): báo ở bước CSDL, trước khi ghi tệp chạy, áp metadata
MISSING_TABLES_SQL = """
select coalesce(json_agg(x.s || '.' || x.t order by x.s, x.t), '[]'::json)
  from json_to_recordset(:'tables'::json) as x(s text, t text)
 where to_regclass(format('%I.%I', x.s, x.t)) is null
"""
REMOVED_SQL = """
begin;
set local moc.actor = 'moc app';
set local moc.actor_kind = 'system';
update core.apps set removed_at = now(), updated_at = now() where name = :'name' and removed_at is null;
select json_build_object('ok', true);
commit;
"""
APPS_SQL = """
select coalesce(json_agg(row_to_json(a) order by a.name), '[]'::json) from (
  select a.name, a.title, a.path, a.schema_name, a.version, a.installed_at, a.removed_at,
         (select count(*) from core.app_migrations m where m.app = a.name) as migrations
    from core.apps a) a
"""


def b64(text: str) -> str:
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def db_state(system: System, rec: dict[str, Any]) -> dict[str, Any]:
    if not (system.db.query(DB_READY_SQL) or {}).get("ready"):
        raise AppError("CSDL chưa có core.apps, core.app_migrations (migration 1792281603200) — lõi chưa cập nhật? "
                       "Chạy make up để Hasura áp migration rồi chạy lại")
    return system.db.query(DB_STATE_SQL, name=rec["name"], schema=rec["schema"], path=rec["path"])


def db_role(schema: str) -> str:
    """Vai trò CSDL của ứng dụng (≤ 63 ký tự: schema tối đa 50)."""
    return f"moc_appdb_{schema}"


def recreate_roles_sql(roles: list[str]) -> str:
    """Cho `moc backup restore` sang máy mới: vai trò thuộc cả máy chủ PostgreSQL, pg_dump một CSDL không chép, mà bản
    dump có ALTER … OWNER TO, GRANT … TO chúng. Tạo vai trò còn thiếu, đúng thuộc tính lúc cài; quyền nằm trong dump."""
    for role in roles:
        if not APP_ROLE.fullmatch(role):
            raise AppError(f"tên vai trò ứng dụng lạ: {role!r}")
    return "".join(f"do $moc$ begin if not exists (select 1 from pg_roles where rolname = '{role}') then\n"
                   f"  create role \"{role}\" {ROLE_ATTRS};\nend if; end $moc$;\n" for role in roles)


def pending_migrations(rec: dict[str, Any], applied: dict[str, str]) -> list[dict[str, Any]]:
    """Migration chưa áp; migration đã áp mà nội dung đổi thì từ chối (không áp lại, không bỏ qua im lặng)."""
    changed = [m for m in rec["migrations"]
               if str(m["version"]) in applied and applied[str(m["version"])] != m["sha256"]]
    if changed:
        names = ", ".join(f"{m['version']}_{m['name']}" for m in changed)
        raise AppError(f"migration đã áp nhưng nội dung đã đổi: {names} — không sửa migration đã áp, thêm migration "
                       "mới")
    return [m for m in rec["migrations"] if str(m["version"]) not in applied]


def migrate_script(rec: dict[str, Any], m: dict[str, Any]) -> str:
    """SQL một migration cho phiên của vai trò ứng dụng: SQL của ứng dụng dạng base64, moc_app.migration_done() kiểm
    rồi ghi core.app_migrations cùng giao dịch."""
    return MIGRATE_SQL.format(schema=rec["schema"], sql=b64(m["sql"]), version=int(m["version"]))


def run_migrations(system: System, rec: dict[str, Any], todo: list[dict[str, Any]]) -> None:
    role = db_role(rec["schema"])
    if not (system.db.query(ROLE_SQL.format(role=role, schema=rec["schema"])) or {}).get("ok"):
        raise AppError(f"schema {rec['schema']} đã có nhưng không thuộc vai trò {role} — không cài chồng lên được")
    if not todo:
        return
    system.db.query(LOGIN_SQL.format(role=role, login="login"))
    try:
        app_db = system.db.as_user(role)
        for m in todo:
            app_db.query(migrate_script(rec, m), name=rec["name"], mname=m["name"], sha=m["sha256"])
    finally:
        system.db.query(LOGIN_SQL.format(role=role, login="nologin"))


def step_database(system: System, rec: dict[str, Any], *, dry_run: bool) -> str:
    st = db_state(system, rec)
    if st.get("schema_owner"):
        raise AppError(f"schema {rec['schema']} đã thuộc ứng dụng {st['schema_owner']}")
    if st.get("path_owner"):
        raise AppError(f"đường {rec['path']} đang thuộc ứng dụng {st['path_owner']} — chọn đường khác")
    if st.get("app") and st["app"]["schema_name"] != rec["schema"]:
        raise AppError(f"ứng dụng {rec['name']} đã cài với schema {st['app']['schema_name']} — không đổi schema được")
    if st.get("schema_exists") and not st.get("app"):
        raise AppError(f"schema {rec['schema']} đã có trong CSDL nhưng không phải của ứng dụng này — chọn tên khác")
    todo = pending_migrations(rec, st.get("applied") or {})
    names = ", ".join(f"{m['version']}_{m['name']}" for m in todo)
    if dry_run:
        head = "sẽ ghi core.apps" if not st.get("app") or st["app"].get("removed_at") else "core.apps đã có"
        role = f" (vai trò CSDL {db_role(rec['schema'])})" if todo else ""
        return f"{head}; {f'sẽ áp {len(todo)} migration: {names}' if todo else 'không có migration mới'}{role}"
    manifest = json.dumps(rec["manifest"], ensure_ascii=False, sort_keys=True)
    ok = system.db.query(REGISTER_SQL, name=rec["name"], title=rec["title"], path=rec["path"], schema=rec["schema"],
                         version=rec["version"], manifest=b64(manifest), sha=rec["manifest_sha256"])
    if not (ok or {}).get("ok"):
        raise AppError("không ghi được core.apps")
    run_migrations(system, rec, todo)
    tables = [{"s": t["table"]["schema"], "t": t["table"]["name"]} for t in rec["tables"]]
    missing = system.db.query(MISSING_TABLES_SQL, tables=json.dumps(tables)) if tables else []
    if missing:
        raise AppError(f"manifest khai bảng mà CSDL không có: {', '.join(missing)} — gõ nhầm tên, hoặc thiếu migration "
                       "tạo bảng đó (chưa ghi tệp chạy, chưa đổi metadata)")
    role = db_role(rec["schema"])
    return (f"đã áp {len(todo)} migration bằng vai trò {role}: {names}" if todo
            else "core.apps đã ghi, không có migration mới")


# ---------------------------------------------------------------------------------------- Keycloak

def public_client(rec: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    """Client công khai của trang: chép client mẫu app-office (5 mapper, PKCE S256, không luồng mật khẩu), chỉ cho
    chuyển hướng dưới đường của ứng dụng."""
    realm = realm_clients.realm_from_text(realm_clients.REALM_FILE.read_text(encoding="utf-8"), env)
    template = next((c for c in realm.get("clients", []) if c.get("clientId") == "app-office"), None)
    if template is None or not realm_clients.browser_app(template):
        raise AppError("moc-realm.json không có client mẫu app-office đúng dạng")
    client = copy.deepcopy(template)
    client.pop("id", None)
    public = env["MOC_PUBLIC_URL"].rstrip("/")
    client.update({"clientId": f"app-{rec['name']}", "name": f"Signet — {rec['title']}", "baseUrl": f"{rec['path']}/",
                   "rootUrl": public, "redirectUris": [f"{public}{rec['path']}/*"]})
    client["attributes"] = {**client.get("attributes", {}), "pkce.code.challenge.method": "S256",
                            "post.logout.redirect.uris": f"{public}{rec['path']}/*"}
    if not realm_clients.browser_app(client):
        raise AssertionError("client công khai không còn đúng dạng ứng dụng trên trình duyệt")
    return client


def _claim(name: str, claim: str, value: str, json_type: str = "String") -> dict[str, Any]:
    return {"name": name, "protocol": "openid-connect", "protocolMapper": "oidc-hardcoded-claim-mapper",
            "consentRequired": False,
            "config": {"claim.name": f"https://hasura\\.io/jwt/claims.{claim}", "claim.value": value,
                       "jsonType.label": json_type, "access.token.claim": "true", "id.token.claim": "false",
                       "userinfo.token.claim": "false", "introspection.token.claim": "true"}}


def service_client(rec: dict[str, Any], secret: str) -> dict[str, Any]:
    """Danh tính dịch vụ: chỉ client credentials; token mang vai trò Hasura riêng app_<tên>, không đơn vị, không
    người."""
    role = service_role(rec["name"])
    return {"clientId": f"app-{rec['name']}-svc", "name": f"Signet — {rec['title']} (dịch vụ)", "enabled": True,
            "protocol": "openid-connect", "publicClient": False, "clientAuthenticatorType": "client-secret",
            "secret": secret, "standardFlowEnabled": False, "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False, "serviceAccountsEnabled": True, "frontchannelLogout": False,
            "attributes": {"access.token.lifespan": "300"},
            "protocolMappers": [_claim("hasura-default-role", "x-hasura-default-role", role),
                                _claim("hasura-allowed-roles", "x-hasura-allowed-roles", json.dumps([role]), "JSON"),
                                _claim("hasura-user-id", "x-hasura-user-id", f"app:{rec['name']}")]}


def wanted_clients(rec: dict[str, Any], env: dict[str, str], secrets_: dict[str, str]) -> list[dict[str, Any]]:
    out = [public_client(rec, env)]
    if rec.get("service_account"):
        out.append(service_client(rec, secrets_.get("MOC_CLIENT_SECRET", "")))
    return out


PUBLIC_FIELDS = ("name", "rootUrl", "baseUrl", "redirectUris")


def client_drift(have: dict[str, Any], want: dict[str, Any]) -> dict[str, Any]:
    """Trường của client công khai đi theo manifest (đường, tên) mà client đang có khác → phần cần sửa."""
    changes = {k: want[k] for k in PUBLIC_FIELDS if have.get(k) != want.get(k)}
    logout = want["attributes"]["post.logout.redirect.uris"]
    if (have.get("attributes") or {}).get("post.logout.redirect.uris") != logout:
        changes["attributes"] = {**(have.get("attributes") or {}), "post.logout.redirect.uris": logout}
    return changes


def step_keycloak(system: System, rec: dict[str, Any], env: dict[str, str], secrets_: dict[str, str], *,
                  new_secret: bool, dry_run: bool) -> str:
    have = {c.get("clientId"): c for c in system.kc.clients()}
    done = []
    for client in wanted_clients(rec, env, secrets_):
        cid = client["clientId"]
        stale = cid in have and client.get("serviceAccountsEnabled") and (
            new_secret or (not dry_run and system.client_secret_ok(cid, client["secret"]) is False))
        if cid in have and not client.get("serviceAccountsEnabled"):
            changes = client_drift(have[cid], client)
            if changes:                       # đổi `path` (hoặc tiêu đề): chuyển hướng, đăng xuất theo đường mới
                if not dry_run:
                    system.kc.update_client(have[cid]["id"], {**have[cid], **changes})
                done.append(f"sửa {cid} ({', '.join(sorted(changes))})")
            continue
        if cid in have and not stale:
            continue
        if cid in have:                       # bí mật trong .moc-apps khác bí mật của client: dựng lại client dịch vụ
            if not dry_run:
                system.kc.delete_client(have[cid]["id"])
            done.append(f"dựng lại {cid}")
        else:
            done.append(f"thêm {cid}")
        if not dry_run:
            system.kc.create_client(client)
    if not done:
        return "client đã có: " + ", ".join(c["clientId"] for c in wanted_clients(rec, env, secrets_))
    return ("sẽ " if dry_run else "đã ") + ", ".join(done)


# ---------------------------------------------------------------------------------------- Hasura

def hasura_check(system: System, apps: list[dict[str, Any]], gone: list[dict[str, Any]] = ()) -> str:
    """Sau khi áp: bảng của ứng dụng được track, trigger có mặt; của ứng dụng đã gỡ thì không; không gì không nhất
    quán."""
    md = system.metadata({"type": "export_metadata", "version": 2, "args": {}})["metadata"]
    tables = {(t["table"]["schema"], t["table"]["name"]): t for s in md.get("sources", []) for t in s.get("tables", [])}
    triggers = {e["name"] for t in tables.values() for e in t.get("event_triggers", [])}
    problems = []
    for app in apps:
        for t in app["tables"]:
            if (t["table"]["schema"], t["table"]["name"]) not in tables:
                problems.append(f"bảng {t['table']['schema']}.{t['table']['name']} chưa được track")
        if app.get("events") and service_role(app["name"]) not in triggers:
            problems.append(f"thiếu event trigger {service_role(app['name'])}")
    for app in gone:
        if service_role(app["name"]) in triggers:
            problems.append(f"event trigger {service_role(app['name'])} còn")
        problems += [f"bảng {t['table']['schema']}.{t['table']['name']} còn được track" for t in app["tables"]
                     if (t["table"]["schema"], t["table"]["name"]) in tables]
    bad = system.metadata({"type": "get_inconsistent_metadata", "args": {}})
    for obj in bad.get("inconsistent_objects", []):
        problems.append(f"không nhất quán: {str(obj.get('reason', obj))[:160]}")
    if problems:
        raise AppError("metadata Hasura sau khi áp: " + "; ".join(problems))
    n = sum(len(a["tables"]) for a in apps)
    return f"metadata đã áp: {n} bảng ứng dụng, {sum(1 for a in apps if a.get('events'))} event trigger, nhất quán"


# ---------------------------------------------------------------------------------------- khóa, chạy từng bước

@contextlib.contextmanager
def ops_lock(root: pathlib.Path, wait_s: float = 120) -> Iterator[None]:
    """Khóa chung với moc backup, reconciler, install.sh (flock trên thư mục chạy). Lệnh gọi từ chính các lệnh đó
    (MOC_OPS_LOCKED=1) thì đã giữ khóa."""
    if os.environ.get("MOC_OPS_LOCKED") == "1":
        yield
        return
    fd = os.open(root, os.O_RDONLY)
    deadline = time.monotonic() + wait_s
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AppError("đang có lệnh khác trên thư mục này (reconciler, sao lưu, cài đặt) — đợi xong rồi "
                                   "chạy lại") from None
                time.sleep(1)
        yield
    finally:
        os.close(fd)


def run_steps(steps: list[tuple[str, Callable[[], str]]], out: Callable[[str], None], *, first: int = 1,
              total: int | None = None, dry_run: bool = False) -> None:
    """Chạy lần lượt, in `số/tổng tên: kết quả`. Lỗi → StepFailed nói rõ bước nào. dry_run: bước không kiểm được vì
    Signet chưa chạy thì ghi lại rồi đi tiếp (kế hoạch vẫn in đủ)."""
    total = total or first + len(steps) - 1
    for i, (name, fn) in enumerate(steps, first):
        try:
            result = fn()
        except Unavailable as exc:
            if not dry_run:
                raise StepFailed(i, total, name, exc) from exc
            result = f"không kiểm được ({exc})"
        except (AppError, tenants.TenantError) as exc:
            raise StepFailed(i, total, name, exc) from exc
        out(f"  {i}/{total} {name}: {result}")


def compose_env_values(root: pathlib.Path) -> dict[str, str]:
    import moc_env
    return moc_env.ENV if root == moc_env.ROOT else parse_env((root / (".e" + "nv")).read_text(encoding="utf-8"))


def ensure_image(system: System, rec: dict[str, Any], *, dry_run: bool) -> str:
    ref = rec["image"]
    if system.image_exists(ref):
        return f"đã có {ref}"
    if rec.get("build"):
        if not pathlib.Path(rec["build"]).is_dir():
            raise AppError(f"không còn thư mục dựng {rec['build']} — cài lại từ manifest: moc app install …")
        if not dry_run:
            system.run(["docker", "build", "-q", "-t", ref, rec["build"]], timeout=1800)
        return f"{'sẽ dựng' if dry_run else 'đã dựng'} {ref}"
    if not dry_run:
        system.run(["docker", "pull", "-q", ref], timeout=1800)
    return f"{'sẽ tải' if dry_run else 'đã tải'} {ref}"


def up_services(system: System, names: list[str], *, dry_run: bool) -> str:
    """compose up chỉ các dịch vụ này: cấu hình không đổi thì compose không tạo lại; apisix, hasura chỉ tạo lại khi bind
    mount (lần đầu gắn tệp phủ) hoặc bí mật header đổi. Hasura tạo lại thì tự áp metadata trộn lúc khởi động."""
    if dry_run:
        return "sẽ docker compose up -d --no-deps " + " ".join(names) + " (chỉ tạo lại dịch vụ có cấu hình đổi)"
    system.compose("up", "-d", "--no-deps", "--wait", "--wait-timeout", "300", *names, timeout=600)
    return "đang chạy: " + ", ".join(names)


# ---------------------------------------------------------------------------------------- các lệnh

def install(manifest: pathlib.Path, *, state: State, system: System, dry_run: bool = False,
            out: Callable[[str], None] = print) -> dict[str, Any]:
    rec = load_manifest(manifest, root=state.root)
    if rec.get("build"):
        rec["image"] = f"moc/app-{rec['name']}:{rec['version']}-{tree_hash(pathlib.Path(rec['build']))[:12]}"
    others = {r["name"]: r for r in state.active() if r["name"] != rec["name"]}
    for other in others.values():
        if other["path"] == rec["path"] or other["schema"] == rec["schema"]:
            raise AppError(f"ứng dụng {other['name']} đã dùng đường {other['path']} / schema {other['schema']}")
    old = state.records().get(rec["name"])
    old_json = state.dir / "apps" / f"{rec['name']}.json"
    old_bytes = old_json.read_bytes() if old_json.exists() else None
    out(f"{'Kế hoạch cài' if dry_run else 'Cài'} {rec['name']} {rec['version']} — {rec['title']} ở {rec['path']}/"
        f"{' (đã cài, chạy lại: chỉ làm phần còn thiếu)' if old and not old.get('removing') else ''}")
    out("  1/8 manifest: hợp lệ"
        f" ({len(rec['migrations'])} migration, {len(rec['tables'])} bảng"
        f"{', nghe ' + ', '.join(rec['events']['kinds']) if rec.get('events') else ''})")
    env = compose_env_values(state.root)
    made: list[str] = []

    def secrets_step() -> str:
        made.extend(state.ensure_secrets(rec, dry_run=dry_run))
        return (("sẽ sinh " if dry_run else "đã sinh ") + ", ".join(made)) if made else "đã có (giữ nguyên)"

    def files_step() -> str:
        if not dry_run:
            state.save(rec)
            changed = state.write()
        else:
            changed = sorted(set(_preview(state, rec)))
        return (f"{'sẽ đổi' if dry_run else 'đã ghi'} {len(changed)} tệp: " + ", ".join(_short(changed))) \
            if changed else "đã khớp"

    def keycloak_step() -> str:
        return step_keycloak(system, rec, env, state.secrets(rec["name"]) if not dry_run else
                             {"MOC_CLIENT_SECRET": "…"}, new_secret="MOC_CLIENT_SECRET" in made, dry_run=dry_run)

    def undo() -> str:
        """Bước 8 lỗi: trả bản ghi, tệp chạy (route, metadata trộn, tệp phủ) về như trước lần cài này rồi áp lại
        metadata — Hasura không giữ phần hỏng, ứng dụng khác cài sau không vướng. CSDL, client giữ (chạy lại dùng
        tiếp)."""
        try:
            if old_bytes is None:
                system.compose("rm", "--stop", "--force", f"app-{rec['name']}", timeout=180)
                old_json.unlink(missing_ok=True)
            else:
                _write_atomic(old_json, old_bytes)
            state.write()
            system.apply_metadata()
            bad = system.metadata({"type": "get_inconsistent_metadata", "args": {}}).get("inconsistent_objects")
            return ("đã trả tệp chạy và metadata Hasura về như trước lần cài này"
                    + (f", còn {len(bad)} chỗ không nhất quán" if bad else ", nhất quán"))
        except (AppError, Unavailable) as exc:
            return f"không trả về được ({exc}) — gỡ: python3 scripts/moc.py app remove {rec['name']}"

    def hasura_step() -> str:
        if dry_run:
            return "sẽ áp thư mục metadata trộn (hasura-cli metadata apply trong container), kiểm bảng, trigger"
        try:
            system.apply_metadata()
            return hasura_check(system, state.active())
        except AppError as exc:
            raise AppError(f"{exc} — {undo()}") from exc

    steps = [
        ("image", lambda: ensure_image(system, rec, dry_run=dry_run)),
        ("CSDL", lambda: step_database(system, rec, dry_run=dry_run)),
        ("bí mật", secrets_step),
        ("Keycloak", keycloak_step),
        ("tệp chạy", files_step),
        ("container", lambda: up_services(system, ["apisix", "hasura", f"app-{rec['name']}"], dry_run=dry_run)),
        ("Hasura", hasura_step),
    ]
    with ops_lock(state.root):
        run_steps(steps, out, first=2, dry_run=dry_run)
    return {"name": rec["name"], "dry_run": dry_run, "image": rec["image"], "secrets_created": made}


def _preview(state: State, rec: dict[str, Any]) -> list[str]:
    """Tệp sẽ đổi nếu cài rec (không ghi gì): dựng State tạm trong bộ nhớ."""
    class Preview(State):
        def active(self_inner) -> list[dict[str, Any]]:
            return [r for r in State.active(state) if r["name"] != rec["name"]] + [rec]
    p = Preview(state.root, env_file=state.env_file)
    changed = [rel for rel, data in p.derived().items()
               if not (state.root / rel).exists() or (state.root / rel).read_bytes() != data]
    return changed + [f"{STATE}/apps/{rec['name']}.json"]


def _short(paths: list[str]) -> list[str]:
    meta = [p for p in paths if p.startswith(METADATA)]
    rest = [p for p in paths if not p.startswith(METADATA)]
    return rest + ([f"{METADATA}/ ({len(meta)} tệp)"] if meta else [])


def _remove_keycloak(system: System, name: str, *, dry_run: bool) -> str:
    ids = {f"app-{name}", f"app-{name}-svc"}
    found = [c for c in system.kc.clients() if c.get("clientId") in ids]
    if not dry_run:
        for c in found:
            system.kc.delete_client(c["id"])
    return (("sẽ xóa " if dry_run else "đã xóa ") + ", ".join(c["clientId"] for c in found)) if found \
        else "không còn client"


def _remove_half_install(name: str, row: dict[str, Any], *, system: System, state: State, dry_run: bool,
                         out: Callable[[str], None]) -> dict[str, Any]:
    """Lần cài đầu hỏng trước khi ghi tệp chạy (vd migration lỗi ở bước 3): core.apps có dòng, .moc-apps không có
    bản ghi. Không có route, container, metadata nào để gỡ: chỉ client (nếu đã tạo) và đánh dấu đã gỡ — trả đường cho
    ứng dụng khác; schema, dữ liệu, migration đã áp giữ nguyên."""
    out(f"{'Kế hoạch dọn' if dry_run else 'Dọn'} {name} (cài dở, chưa có bản ghi trong {STATE}/apps/) — schema "
        f"{row.get('schema_name')} giữ nguyên")

    def db_step() -> str:
        if dry_run:
            return "sẽ ghi core.apps.removed_at"
        system.db.query(REMOVED_SQL, name=name)
        return "core.apps.removed_at đã ghi"

    with ops_lock(state.root):
        run_steps([("Keycloak", lambda: _remove_keycloak(system, name, dry_run=dry_run)), ("CSDL", db_step)], out,
                  dry_run=dry_run)
    return {"name": name, "dry_run": dry_run, "half_install": True}


def remove(name: str, *, state: State, system: System, dry_run: bool = False,
           out: Callable[[str], None] = print) -> dict[str, Any]:
    rec = state.records().get(name)
    if rec is None:
        row = next((r for r in (system.db.query(APPS_SQL) or []) if r.get("name") == name), None)
        if row is None or row.get("removed_at"):
            raise AppError(f"không có ứng dụng {name} trong {STATE}/apps/ (moc app list để xem)")
        return _remove_half_install(name, row, system=system, state=state, dry_run=dry_run, out=out)
    out(f"{'Kế hoạch gỡ' if dry_run else 'Gỡ'} {name} — dữ liệu, schema {rec['schema']} giữ nguyên (không xóa)")

    def container_step() -> str:
        if rec.get("removing"):              # lần gỡ trước đã qua bước này; tệp phủ không còn service để gọi tên
            return "đã dừng ở lần gỡ trước"
        if dry_run:
            return f"sẽ dừng, xóa container app-{name}"
        system.compose("rm", "--stop", "--force", f"app-{name}", timeout=180)
        return f"đã dừng, xóa container app-{name}"

    def files_step() -> str:
        if dry_run:
            return f"sẽ bỏ route {rec['path']}, bảng và trigger khỏi tệp chạy"
        state.save({**rec, "removing": True})
        changed = state.write()
        return f"đã ghi {len(changed)} tệp: " + ", ".join(_short(changed)) if changed else "đã khớp"

    def hasura_step() -> str:
        if dry_run:
            return "sẽ áp metadata không còn bảng, trigger của ứng dụng"
        up_services(system, ["apisix", "hasura"], dry_run=False)
        system.apply_metadata()
        return hasura_check(system, state.active(), gone=[rec])

    def keycloak_step() -> str:
        return _remove_keycloak(system, name, dry_run=dry_run)

    def db_step() -> str:
        if dry_run:
            return f"sẽ ghi core.apps.removed_at; KHÔNG xóa schema {rec['schema']} và dữ liệu"
        system.db.query(REMOVED_SQL, name=name)
        state.drop(name)
        state.write()
        return f"core.apps.removed_at đã ghi; schema {rec['schema']} và dữ liệu giữ nguyên"

    steps = [("container", container_step), ("tệp chạy", files_step), ("Hasura", hasura_step),
             ("Keycloak", keycloak_step), ("CSDL", db_step)]
    with ops_lock(state.root):
        run_steps(steps, out, dry_run=dry_run)
    return {"name": name, "dry_run": dry_run}


def sync(*, state: State, system: System, files_only: bool = False, out: Callable[[str], None] = print) -> dict:
    """Đưa mọi thứ dựng ra về khớp bản ghi. files_only: chỉ tệp (không cần CSDL, Keycloak, Docker — install.sh gọi khi
    Signet đang dừng; reconciler gọi mỗi lượt)."""
    apps = state.active()
    result: dict[str, Any] = {"apps": [a["name"] for a in apps], "changed": [], "actions": []}
    if not state.dir.is_dir():
        return result
    with ops_lock(state.root):
        made = {rec["name"]: state.ensure_secrets(rec) for rec in apps}
        result["changed"] = state.write()
        if files_only or not apps:
            return result
        env = compose_env_values(state.root)
        for rec in apps:
            result["actions"].append(f"{rec['name']}: {ensure_image(system, rec, dry_run=False)}")
            result["actions"].append(f"{rec['name']}: {step_database(system, rec, dry_run=False)}")
            result["actions"].append(f"{rec['name']}: " + step_keycloak(
                system, rec, env, state.secrets(rec["name"]), new_secret="MOC_CLIENT_SECRET" in made[rec["name"]],
                dry_run=False))
        up_services(system, ["apisix", "hasura", *(f"app-{a['name']}" for a in apps)], dry_run=False)
        system.apply_metadata()
        result["actions"].append(hasura_check(system, apps))
    for line in result["actions"]:
        out(f"  {line}")
    return result


# ---------------------------------------------------------------------------------------- argparse

def _system_and_state() -> tuple[System, State]:
    return System(ROOT), State(ROOT)


def _fail(exc: Exception, args: argparse.Namespace) -> int:
    code = 2 if isinstance(getattr(exc, "error", exc), Unavailable) else 1
    message = str(exc)
    if isinstance(exc, StepFailed):
        cmd = {"install": f"install {getattr(args, 'manifest', '')}", "remove": f"remove {getattr(args, 'name', '')}",
               "sync": "sync"}.get(args.cmd, args.cmd)
        message += f"\nSửa rồi chạy lại: python3 scripts/moc.py app {cmd} (chạy lại chỉ làm phần còn thiếu)"
    if code == 2:
        message += ". Signet có đang chạy không? (make ps)"
    if getattr(args, "json", False):
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    else:
        print(f"✗ {message}", file=sys.stderr)
    return code


def cmd_install(args: argparse.Namespace) -> int:
    system, state = _system_and_state()
    try:
        result = install(args.manifest, state=state, system=system, dry_run=args.dry_run)
    except (AppError, StepFailed, Unavailable, tenants.TenantError) as exc:
        return _fail(exc, args)
    print("Chỉ là kế hoạch, chưa thay đổi gì." if args.dry_run else
          f"✓ Đã cài {result['name']}. Gỡ: python3 scripts/moc.py app remove {result['name']} (giữ dữ liệu)")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    system, state = _system_and_state()
    try:
        remove(args.name, state=state, system=system, dry_run=args.dry_run)
    except (AppError, StepFailed, Unavailable, tenants.TenantError) as exc:
        return _fail(exc, args)
    print("Chỉ là kế hoạch, chưa thay đổi gì." if args.dry_run else
          f"✓ Đã gỡ {args.name}: route, client, trigger, container không còn; dữ liệu giữ nguyên")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    system, state = _system_and_state()
    quiet: Callable[[str], None] = (lambda _line: None) if args.json else print
    try:
        result = sync(state=state, system=system, files_only=args.files, out=quiet)
    except (AppError, StepFailed, Unavailable, tenants.TenantError) as exc:
        return _fail(exc, args)
    if args.json:
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    elif result["changed"]:
        print(f"✓ dựng lại {len(result['changed'])} tệp ứng dụng: " + ", ".join(_short(result["changed"])))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    system, state = _system_and_state()
    try:
        records = state.records()
        stale = state.stale() if state.dir.is_dir() else []
    except AppError as exc:
        return _fail(exc, args)
    rows, db_error = [], None
    try:
        rows = system.db.query(APPS_SQL) or []
    except (Unavailable, tenants.TenantError) as exc:
        db_error = str(exc)
    by_name = {r["name"]: r for r in rows}
    apps = []
    for name in sorted(set(records) | set(by_name)):
        rec, row = records.get(name), by_name.get(name)
        apps.append({"name": name, "title": (rec or row or {}).get("title"), "path": (rec or row or {}).get("path"),
                     "version": (rec or row or {}).get("version"), "image": (rec or {}).get("image"),
                     "installed": bool(rec and not rec.get("removing")), "removing": bool(rec and rec.get("removing")),
                     "events": (rec or {}).get("events", {}) and rec["events"]["kinds"],
                     "migrations": f"{(row or {}).get('migrations', '?')}/{len((rec or {}).get('migrations', []))}",
                     "db": "gỡ" if row and row.get("removed_at") else ("có" if row else "chưa ghi"),
                     "schema": (rec or {}).get("schema") or (row or {}).get("schema_name")})
    if args.json:
        print(json.dumps({"apps": apps, "stale": stale, "db_error": db_error}, ensure_ascii=False, default=str))
        return 0
    if not apps:
        print("Chưa cài ứng dụng nào bằng manifest. Cài: python3 scripts/moc.py app install apps/<thư mục>/app.yaml")
    for a in apps:
        if a["installed"]:
            state_ = "đã cài"
        elif a["removing"]:
            state_ = "đang gỡ dở — chạy lại moc app remove"
        elif a["db"] == "gỡ":
            state_ = f"đã gỡ (dữ liệu trong schema {a['schema']} còn)"
        else:
            state_ = (f"LỖI: cài dở, chưa xong — chạy lại moc app install <manifest>, hoặc moc app remove {a['name']} "
                      "để bỏ (giữ dữ liệu)")
        print(f"{a['name']} {a['version'] or ''} — {a['title']} ({a['path']}/): {state_}")
        if a["installed"]:
            ev = f"; nghe {', '.join(a['events'])}" if a["events"] else ""
            print(f"  image {a['image']}; schema {a['schema']}; migration đã áp {a['migrations']} "
                  f"(CSDL: {a['db']}){ev}")
    if stale:
        print(f"⚠ {len(stale)} tệp dựng ra khác lõi hiện tại (lõi vừa đổi?): python3 scripts/moc.py app sync")
    if db_error:
        print(f"⚠ không đọc được CSDL: {db_error}")
    return 0


def add_parser(groups: Any) -> None:
    """Nhóm `app` của scripts/moc.py."""
    a = groups.add_parser("app", help="ứng dụng cắm vào lõi bằng manifest (docs/them-ung-dung.md)").add_subparsers(
        dest="cmd", required=True)
    i = a.add_parser("install", help="cài (hoặc hoàn tất lần cài dở) một ứng dụng từ apps/<thư mục>/app.yaml")
    i.add_argument("manifest", type=pathlib.Path, metavar="APP.YAML")
    i.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch từng bước, không thay đổi gì")
    i.set_defaults(run=cmd_install)
    ls = a.add_parser("list", help="ứng dụng đã cài, migration đã áp, tệp dựng ra có khớp lõi không")
    ls.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    ls.set_defaults(run=cmd_list)
    r = a.add_parser("remove", help="gỡ route, client, trigger, container của ứng dụng; GIỮ dữ liệu")
    r.add_argument("name", metavar="TÊN")
    r.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch từng bước, không thay đổi gì")
    r.set_defaults(run=cmd_remove)
    s = a.add_parser("sync", help="dựng lại tệp chạy, áp lại migration/client/metadata còn thiếu theo bản ghi")
    s.add_argument("--files", action="store_true", help="chỉ dựng lại tệp (không cần Signet đang chạy)")
    s.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    s.set_defaults(run=cmd_sync)
