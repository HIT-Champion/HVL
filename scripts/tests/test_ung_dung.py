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

"""scripts/ung_dung.py và lệnh `moc app`: kiểm manifest trước mọi bước; tệp chạy APISIX (tệp lõi nguyên văn + phần của
ứng dụng, ghi tại chỗ); thư mục metadata trộn; tệp phủ compose; COMPOSE_FILE; migration chưa áp; dry-run không ghi gì;
chạy lại không tạo trùng; lỗi giữa chừng báo đúng bước rồi chạy lại hoàn tất; gỡ giữ dữ liệu. CSDL, Keycloak, Docker
giả, không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import copy
import importlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import types
import argparse
import unittest
import unittest.mock
from contextlib import redirect_stdout
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
APP = REPO / "apps" / "bang-tin" / "app.yaml"
PUBLIC = "https://signet.example"

u: Any = None
yaml_nho: Any = None
_saved: dict[str, Any] = {}


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp: thay bằng bản giả."""
    global u, yaml_nho
    for name in ("moc_env", "tenants", "realm_clients", "ung_dung", "yaml_nho"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ENV = {"MOC_PUBLIC_URL": PUBLIC}
    stub.ROOT = REPO
    stub.REALM = "moc"
    stub.KEYCLOAK_ADMIN_URL = "http://127.0.0.1:8180"
    stub.PUBLIC_URL = PUBLIC

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng")

    stub.call_json = no_network
    stub.HTTPError = type("HTTPError", (Exception,), {})
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    u = importlib.import_module("ung_dung")
    yaml_nho = importlib.import_module("yaml_nho")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


def manifest() -> dict[str, Any]:
    return yaml_nho.loads(APP.read_text(encoding="utf-8"))


def schema() -> dict[str, Any]:
    return json.loads((REPO / u.SCHEMA).read_text(encoding="utf-8"))


def errors_of(m: dict[str, Any]) -> list[str]:
    return u.check_manifest(m, APP.parent, schema())


def record(**changes: Any) -> dict[str, Any]:
    rec = u.load_manifest(APP, root=REPO)
    rec["image"] = "moc/app-bang-tin:1.0.0-abcdefabcdef"
    rec.update(changes)
    return rec


class ManifestRules(unittest.TestCase):
    def test_sample_app_is_valid(self) -> None:
        self.assertEqual(errors_of(manifest()), [])
        rec = u.load_manifest(APP, root=REPO)
        self.assertEqual(rec["schema"], "bang_tin")
        self.assertEqual([m["version"] for m in rec["migrations"]], [1])
        self.assertEqual(rec["events"]["kinds"], ["office.document.issued", "office.document.registered"])
        self.assertTrue(rec["build"].endswith("apps/bang-tin"))

    def test_schema_uses_only_supported_keywords(self) -> None:
        def walk(node: Any, under_properties: bool = False) -> set[str]:
            found: set[str] = set()
            if isinstance(node, dict):
                for k, v in node.items():
                    if not under_properties:
                        found.add(k)
                    found |= walk(v, k in ("properties", "$defs"))
            elif isinstance(node, list):
                for v in node:
                    found |= walk(v)
            return found
        self.assertLessEqual(walk(schema()), u.SCHEMA_KEYWORDS)

    def test_event_whitelist_same_in_code_schema_and_migration(self) -> None:
        enum = schema()["properties"]["events"]["properties"]["kinds"]["items"]["enum"]
        self.assertEqual(tuple(enum), u.EVENT_KINDS)
        sql = (REPO / "db/migrations/default/1792281603200_app_registry/up.sql").read_text(encoding="utf-8")
        arrays = re.findall(r"(?:in \(|array\[)([^)\]]*)[)\]]", sql)
        lists = [tuple(re.findall(r"'([a-z_.]+)'", a)) for a in arrays if "office.document" in a]
        self.assertEqual(len(lists), 2)                     # CHECK của bảng và mảng trong hàm trigger
        for kinds in lists:
            self.assertEqual(kinds, u.EVENT_KINDS)

    def test_reserved_paths_cover_office_pages(self) -> None:
        pages = REPO / "apps" / "office" / "app" / "pages"
        names = {p.stem for p in pages.iterdir()} - {"index"}
        self.assertLessEqual({f"/{n}" for n in names}, u.RESERVED_PATHS)

    def check(self, change, *needles: str) -> None:
        m = manifest()
        change(m)
        found = "\n".join(errors_of(m))
        for needle in needles:
            self.assertIn(needle, found)

    def test_rules(self) -> None:
        tin = lambda m: m["metadata"]["tables"][0]                          # noqa: E731
        cases = [
            (lambda m: m.update(path="/van-ban-den"), "trùng đường của lõi"),
            (lambda m: m.update(path="/api"), "trùng đường của lõi"),
            (lambda m: m.update(name="office"), "tên giữ chỗ"),
            (lambda m: m["database"].update(schema="core"), "schema của lõi"),
            (lambda m: m["database"].update(schema="pg_x"), "schema của lõi"),
            (lambda m: m.update(title="Bảng\ntin"), "ký tự điều khiển"),
            (lambda m: m.update(extra=1), "extra: khóa không được nhận"),
            (lambda m: m.update(image={"ref": "python:3.13-slim"}), "image"),
            (lambda m: m.update(image={"build": "../ca-nhan"}), "nằm ngoài thư mục ứng dụng"),
            (lambda m: m.update(environment={"API_TOKEN": "x"}), "giống bí mật"),
            (lambda m: m.update(environment={"MOC_HOOK_SECRET": "x"}), "biến do lõi đặt"),
            (lambda m: m["events"]["webhook"].update(port=8080), "phải khác port"),
            (lambda m: m["events"].update(kinds=["office.document.signed"]), "events.kinds[0]"),
            (lambda m: m.update(healthcheck={"test": ["sh", "-c", "true"]}), "CMD hoặc CMD-SHELL"),
            (lambda m: tin(m)["table"].update(schema="office"), "không nằm trong schema bang_tin"),
            (lambda m: tin(m).update(delete_permissions=[]), "delete_permissions: khóa không được nhận"),
            (lambda m: tin(m).update(event_triggers=[]), "event_triggers: khóa không được nhận"),
            (lambda m: tin(m)["object_relationships"][0]["using"]["manual_configuration"]["remote_table"].update(
                schema="personal"), "chỉ được trỏ về schema"),
            (lambda m: tin(m)["select_permissions"][0].update(role="service"), "vai trò không được dùng"),
            (lambda m: tin(m)["select_permissions"][0].update(role="admin"), "vai trò không được dùng"),
            (lambda m: tin(m)["select_permissions"][0]["permission"].update(filter={}), "X-Hasura-Tenant-Id"),
            (lambda m: m.pop("service_account"), "app_bang_tin: vai trò không được dùng"),
            # `$` của re.search nhận chuỗi có xuống dòng cuối: kiểm bằng fullmatch
            (lambda m: m.update(name="office\n"), "name: 'office\\n' không khớp mẫu"),
            (lambda m: m.update(path="/api\n"), "path: '/api\\n' không khớp mẫu"),
            (lambda m: m["database"].update(schema="core\n"), "không khớp mẫu"),
        ]
        for change, needle in cases:
            with self.subTest(needle=needle):
                self.check(change, needle)

    def test_insert_by_user_role_must_set_tenant(self) -> None:
        def change(m: dict[str, Any]) -> None:
            m["metadata"]["tables"][0]["insert_permissions"].append(
                {"role": "staff", "permission": {"columns": ["kind"], "check": {}}})
        self.check(change, "set tenant_id: X-Hasura-Tenant-Id")

    def test_tenant_filter_checked_by_structure_not_by_text(self) -> None:
        eq = {"tenant_id": {"_eq": "X-Hasura-Tenant-Id"}}
        for good in (eq, {"tenant_id": {"_eq": "x-hasura-tenant-id"}, "kind": {"_eq": "a"}},
                     {"_and": [{"kind": {"_eq": "a"}}, eq]}, {"_and": [{"_and": [eq]}]},
                     {"_and": [eq], "_or": [{"kind": {"_eq": "a"}}, {}]}):
            with self.subTest(good=good):
                self.assertTrue(u.tenant_scoped(good))
        for bad in ({}, {"_or": [eq, {}]}, {"_not": eq}, {"tenant_id": {"_neq": "X-Hasura-Tenant-Id"}},
                    {"tenant_id": {"_eq": "X-Hasura-Tenant-Id", "_is_null": False}},
                    {"document": eq}, {"_exists": {"_table": {"schema": "core", "name": "tenants"}, "_where": eq}},
                    {"_and": [{"_or": [eq, {}]}]}, {"x": "X-Hasura-Tenant-Id"}, [eq]):
            with self.subTest(bad=bad):
                self.assertFalse(u.tenant_scoped(bad))
        def leak(m: dict[str, Any]) -> None:
            m["metadata"]["tables"][0]["select_permissions"][0]["permission"]["filter"] = {"_or": [eq, {}]}
        self.check(leak, "filter phải có tenant_id: {_eq: X-Hasura-Tenant-Id}")

    def test_update_of_tenant_column_must_stay_in_tenant(self) -> None:
        eq = {"tenant_id": {"_eq": "X-Hasura-Tenant-Id"}}

        def change(m: dict[str, Any]) -> None:
            m["metadata"]["tables"][0]["update_permissions"] = [
                {"role": "staff", "permission": {"columns": ["tenant_id"], "filter": eq, "check": {}}}]
        self.check(change, "sửa được tenant_id thì check phải có")

    def test_array_relationship_by_fk_stays_in_app_schema(self) -> None:
        def change(m: dict[str, Any]) -> None:
            m["metadata"]["tables"][0]["array_relationships"] = [{"name": "x", "using": {"foreign_key_constraint_on": {
                "table": {"schema": "core", "name": "files"}, "column": "id"}}}]
        self.check(change, "quan hệ mảng theo khóa ngoại")

    def test_permission_rules_cannot_read_core_data(self) -> None:
        # Hasura chạy điều kiện trong quyền bằng quyền admin: hai bộ lọc dưới đây (tái hiện trên Hasura v2.51) dò được
        # văn bản hạn chế của đơn vị khác dù vai trò không có quyền gì trên office.documents
        eq = {"tenant_id": {"_eq": "X-Hasura-Tenant-Id"}}
        docs = {"schema": "office", "name": "documents"}
        exists = {"_exists": {"_table": docs, "_where": {"restricted": {"_eq": True}, "title": {"_like": "Mật%"}}}}
        guess = {"docs": {"restricted": {"_eq": True}, "title": {"_cgt": ["$", "guess"]}}}
        manual = {"name": "docs", "using": {"manual_configuration": {"remote_table": docs,
                                                                    "column_mapping": {"target_tenant": "tenant_id"}}}}
        own = {"schema": "bang_tin", "name": "nhom"}

        def table(m: dict[str, Any]) -> dict[str, Any]:
            t = m["metadata"]["tables"][0]
            t["array_relationships"] = [manual]
            t["object_relationships"] += [
                {"name": "nhom", "using": {"manual_configuration": {"remote_table": own,
                                                                   "column_mapping": {"kind": "kind"}}}},
                {"name": "goc", "using": {"foreign_key_constraint_on": "document_id"}}]
            m["metadata"]["tables"].append({"table": own, "object_relationships": [{"name": "van_ban", "using": {
                "manual_configuration": {"remote_table": docs, "column_mapping": {"document_id": "id"}}}}]})
            return t

        def user_filter(rule: dict[str, Any]) -> Any:
            def change(m: dict[str, Any]) -> None:
                table(m)["select_permissions"][1]["permission"] = {"columns": ["kind"], "filter": {"_and": [eq, rule]}}
            return change

        for rule, needle in ((exists, "staff filter: không được dùng _exists"),
                             (guess, "staff filter: qua quan hệ docs"),
                             ({"_not": {"document": {"restricted": {"_eq": False}}}}, "qua quan hệ document"),
                             ({"_or": [{"document": {"_and": [{"visible": {"_eq": True}}]}}]}, "quan hệ document"),
                             ({"goc": {"title": {"_like": "Mật%"}}}, "qua quan hệ goc"),
                             ({"nhom": {"van_ban": {"title": {"_like": "Mật%"}}}}, "qua quan hệ van_ban"),
                             ({"nhom": {"_exists": exists["_exists"]}}, "không được dùng _exists"),
                             ({"docs_aggregate": {"count": {"predicate": {"_gt": 0}, "filter": {
                                 "title": {"_like": "Mật%"}}}}}, "không được dùng docs_aggregate"),
                             ({"nhom_aggregate": {"count": {"predicate": {"_gt": 0}, "filter": {
                                 "van_ban": {"title": {"_like": "Mật%"}}}}}}, "qua quan hệ van_ban")):
            with self.subTest(rule=rule):
                self.check(user_filter(rule), needle)

        def service(m: dict[str, Any]) -> None:
            table(m)["insert_permissions"][0]["permission"]["check"] = exists
        self.check(service, "app_bang_tin check: không được dùng _exists")

        def insert_guess(m: dict[str, Any]) -> None:
            table(m)["insert_permissions"].append({"role": "manager", "permission": {
                "columns": ["kind"], "set": {"tenant_id": "X-Hasura-Tenant-Id"}, "check": guess}})
        self.check(insert_guess, "manager check: qua quan hệ docs")

        # luật đọc của lõi và điều kiện trên bảng của chính ứng dụng vẫn được
        visible = {"visible": {"_eq": True}}
        for rule in ({"docs": visible}, {"goc": visible}, {"nhom": {"kind": {"_eq": "x"}, "van_ban": visible}},
                     {"kind": {"_ceq": "kind"}}):
            with self.subTest(ok=rule):
                m = manifest()
                user_filter(rule)(m)
                self.assertEqual(u.check_tables(m), [])

    def test_load_reports_every_error_at_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "app.yaml"
            bad.write_text("name: X\ntitle: t\nversion: 1\npath: /api\nimage: {build: .}\nport: 80\n"
                           "database: {schema: core}\n", encoding="utf-8")
            with self.assertRaises(u.AppError) as ctx:
                u.load_manifest(bad, root=REPO)
        text = str(ctx.exception)
        for needle in ("name:", "version:", "port:"):
            self.assertIn(needle, text)

    def test_yaml_outside_subset_is_an_error_not_a_guess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "app.yaml"
            bad.write_text("name: bang-tin\ndescription: |\n  nhiều dòng\n", encoding="utf-8")
            with self.assertRaisesRegex(u.AppError, "dòng 2"):
                u.load_manifest(bad, root=REPO)


class Migrations(unittest.TestCase):
    def make(self, tmp: str, files: dict[str, str]) -> pathlib.Path:
        base = pathlib.Path(tmp)
        for rel, text in files.items():
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_text(text, encoding="utf-8")
        return base

    def test_order_by_number_and_bad_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = self.make(tmp, {"10_b/up.sql": "create table s.b ();", "2_a/up.sql": "create table s.a ();",
                                   "README.md": "không phải migration"})
            self.assertEqual([m["name"] for m in u.read_migrations(base)], ["a", "b"])
        bad = [("x_1/up.sql", "select 1;", "cần thư mục"), ("1_x/up.sql", "  ", "rỗng"),
               ("1_x\n/up.sql", "select 1;", "cần thư mục")]
        for rel, sql, needle in bad:
            with self.subTest(needle=needle), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(u.AppError, needle):
                    u.read_migrations(self.make(tmp, {rel: sql}))
        with tempfile.TemporaryDirectory() as tmp:           # không còn chặn bằng chữ: vai trò CSDL mới là ranh giới
            base = self.make(tmp, {"1_x/up.sql": "reset role; create function s.f() returns int language sql "
                                                 "security definer as 'select 1';"})
            self.assertEqual(len(u.read_migrations(base)), 1)

    def test_symlinks_inside_migrations_cannot_leave_folder(self) -> None:
        core = REPO / "db/migrations/default/1792281600200_office_schema"
        with tempfile.TemporaryDirectory() as tmp:
            base = self.make(tmp, {"app/migrations/1_a/up.sql": "select 1;", "ngoai/2_b/up.sql": "select 2;"})
            folder = base / "app" / "migrations"
            (folder / "2_b").symlink_to(base / "ngoai" / "2_b")
            with self.assertRaisesRegex(u.AppError, "symlink ra ngoài"):
                u.read_migrations(folder)
            (folder / "2_b").unlink()
            (folder / "3_c").mkdir()
            (folder / "3_c" / "up.sql").symlink_to(core / "up.sql")
            with self.assertRaisesRegex(u.AppError, "symlink ra ngoài"):
                u.read_migrations(folder)
            (folder / "3_c" / "up.sql").unlink()
            (folder / "3_c" / "that.sql").write_text("select 3;", encoding="utf-8")
            (folder / "3_c" / "up.sql").symlink_to(folder / "3_c" / "that.sql")      # trong cùng thư mục: được
            self.assertEqual([m["version"] for m in u.read_migrations(folder)], [1, 3])

    def test_pending_and_changed(self) -> None:
        rec = record()
        m = rec["migrations"][0]
        self.assertEqual(u.pending_migrations(rec, {}), [m])
        self.assertEqual(u.pending_migrations(rec, {"1": m["sha256"]}), [])
        with self.assertRaisesRegex(u.AppError, "nội dung đã đổi"):
            u.pending_migrations(rec, {"1": "0" * 64})

    def test_script_runs_as_app_role_and_checks_before_commit(self) -> None:
        rec = record()
        script = u.migrate_script(rec, rec["migrations"][0])
        order = ["begin;", 'set local search_path to "bang_tin"', "execute convert_from(decode(",
                 "select moc_app.migration_done(:'name', 1, :'mname', :'sha')", "commit;"]
        positions = [script.index(s) for s in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("create table bang_tin.tin", script)      # SQL của ứng dụng chỉ đi dạng base64
        self.assertNotIn("\\", script)                               # không có lệnh psql nào
        for word in ("set role", "reassign", "insert into core", "grant"):
            self.assertNotIn(word, script.lower())                  # phiên của ứng dụng không làm gì thay lõi
        role = u.ROLE_SQL.format(role=u.db_role("bang_tin"), schema="bang_tin")
        for needle in ('create role "moc_appdb_bang_tin"', "nosuperuser nocreatedb nocreaterole noinherit",
                       "nobypassrls", 'create schema if not exists "bang_tin" authorization "moc_appdb_bang_tin"',
                       "grant execute on function moc_app.migration_done"):
            self.assertIn(needle, role)
        self.assertNotRegex(role, r"grant (usage|select|references)[^;]* (core|office|personal)\b")
        self.assertLessEqual(len(u.db_role("a" * 50)), 63)

    def test_migration_done_checks_in_core_migration(self) -> None:
        sql = (REPO / "db/migrations/default/1792281603200_app_registry/up.sql").read_text(encoding="utf-8")
        body = sql[sql.index("create function moc_app.migration_done"):]
        for needle in ("session_user::text <> 'moc_appdb_' || v_schema", "pg_shdepend",
                       "':(funcid|aggfnoid|winfnoid|relid|seqid) ([0-9]+)'", "ev_action", "adbin", "conbin",
                       "security_invoker", "pg_cast", "alter routine %s security definer",
                       "insert into core.app_migrations"):
            self.assertIn(needle, body)
        self.assertLess(body.index("alter routine"), body.index("insert into core.app_migrations"))
        self.assertIn("revoke all on function moc_app.migration_done(text, bigint, text, text) from public", sql)
        self.assertIn('set "hasura.user" = \'null\'', sql)          # sự kiện không mang người làm

    def test_database_error_shows_the_error_line(self) -> None:
        # lỗi trong khối DO: psql in ERROR trước rồi CONTEXT nhiều dòng — người cài phải thấy lý do, không chỉ câu SQL
        stderr = ('psql:<stdin>:4: ERROR:  permission denied for schema office\n'
                  'CONTEXT:  SQL statement "create view a.v as select d.id\n'
                  'from office.documents d"\nPL/pgSQL function inline_code_block line 1 at EXECUTE\n')
        self.assertEqual(u.tenants._tail(stderr), "psql:<stdin>:4: ERROR:  permission denied for schema office")
        self.assertEqual(u.tenants._tail("a\nb\nc\nd\n"), "b / c / d")


class Gateway(unittest.TestCase):
    UPSTREAM = re.compile(r"  # moc app install: [^\n]*\n  - id: app-[a-z0-9-]+\n    type: roundrobin\n    nodes:\n"
                          r"      [^\n]*\n")
    ROUTE = re.compile(r"  # moc app install: [^\n]*\n  - id: app-[a-z0-9-]+\n    uris: [^\n]*\n    methods: [^\n]*\n"
                       r"    upstream_id: [^\n]*\n\n")

    def setUp(self) -> None:
        self.core = (REPO / u.CORE_GATEWAY).read_text(encoding="utf-8")

    def strip(self, text: str) -> str:
        """Bỏ đúng các khối đã chèn → phải còn lại tệp lõi, từng byte."""
        return self.ROUTE.sub("", self.UPSTREAM.sub("", text))

    def test_no_app_is_byte_identical(self) -> None:
        self.assertEqual(u.gateway_text(self.core, []), self.core)

    def test_core_kept_verbatim_route_before_catch_all(self) -> None:
        text = u.gateway_text(self.core, [record()])
        self.assertEqual(self.strip(text), self.core)
        self.assertTrue(text.rstrip().endswith("#END"))
        lines = text.splitlines()
        app_route = max(i for i, ln in enumerate(lines) if ln == "  - id: app-bang-tin")
        office = lines.index("  - id: app-office", lines.index("routes:"))
        self.assertEqual(app_route, office - 5)
        self.assertGreater(app_route, lines.index("  - id: chan"))
        self.assertEqual(lines[lines.index("upstreams:") + 2], "  - id: app-bang-tin")
        self.assertIn('    uris: ["/bang-tin", "/bang-tin/*"]', lines)
        self.assertNotIn("8081", text)                              # cổng webhook không có route

    def test_unknown_core_blocks_survive(self) -> None:
        """Như bản WAF của việc 88: global rule lạ, chuỗi nhiều dòng có chữ giống mốc — vẫn chép nguyên văn."""
        extra = ("      coraza-waf:\n        conf:\n          directives_map:\n            moc:\n"
                 "              - SecRuleEngine On\n      serverless-pre-function:\n        functions:\n"
                 "          - |\n            routes:\n              - id: app-office\n")
        core = self.core.replace("      prometheus: {}\n", "      prometheus: {}\n" + extra)
        self.assertIn("coraza-waf", core)
        text = u.gateway_text(core, [record()])
        self.assertEqual(self.strip(text), core)
        lines = text.splitlines()
        self.assertGreater(lines.index("  - id: app-bang-tin", lines.index("routes:")), lines.index("routes:"))

    def test_missing_markers_fail_loudly(self) -> None:
        for broken in (self.core.replace("\nroutes:\n", "\nduong:\n"), self.core.replace("  - id: app-office\n", ""),
                       self.core.replace("#END", "")):
            with self.subTest(), self.assertRaises(u.AppError):
                u.gateway_text(broken, [record()])

    def test_write_in_place_keeps_inode_and_bumps_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "apisix.yaml"
            path.write_text(self.core, encoding="utf-8")
            inode, before = path.stat().st_ino, path.stat().st_mtime
            self.assertTrue(u.write_in_place(path, u.gateway_text(self.core, [record()]).encode()))
            self.assertEqual(path.stat().st_ino, inode)
            self.assertGreaterEqual(int(path.stat().st_mtime), int(before) + 1)
            mid = path.stat().st_mtime
            self.assertTrue(u.write_in_place(path, self.core.encode()))     # ghi lần hai ngay trong cùng giây
            self.assertGreaterEqual(int(path.stat().st_mtime), int(mid) + 1)
            self.assertFalse(u.write_in_place(path, self.core.encode()))
            self.assertEqual(path.read_text(encoding="utf-8"), self.core)


class Metadata(unittest.TestCase):
    def setUp(self) -> None:
        self.core = u.State(REPO).core_metadata()

    def test_no_app_identical(self) -> None:
        self.assertEqual(u.metadata_tree(self.core, []), self.core)

    def test_only_additions_to_core(self) -> None:
        rec = record()
        tree = u.metadata_tree(self.core, [rec])
        changed = {k for k in self.core if tree[k] != self.core[k]}
        self.assertEqual(changed, {"databases/default/tables/tables.yaml",
                                   "databases/default/tables/core_app_events.yaml"})
        for key in changed:
            self.assertTrue(tree[key].startswith(self.core[key]))           # chỉ thêm vào cuối
        new = set(tree) - set(self.core)
        self.assertEqual(new, {"databases/default/tables/app_bang_tin__bang_tin_tin.yaml"})
        table = yaml_nho.loads(tree[next(iter(new))].decode())
        self.assertEqual(table, rec["tables"][0])
        events = yaml_nho.loads(tree["databases/default/tables/core_app_events.yaml"].decode())
        trigger = events["event_triggers"][0]
        self.assertEqual(trigger["webhook"], "http://app-bang-tin:8081/su-kien")
        self.assertEqual(trigger["headers"], [{"name": "X-Moc-Hook-Secret", "value_from_env": "MOC_APP_HOOK_BANG_TIN"}])
        self.assertNotIn("value", trigger["headers"][0])                     # bí mật không nằm trong metadata
        includes = yaml_nho.loads(tree["databases/default/tables/tables.yaml"].decode())
        self.assertIn("!include app_bang_tin__bang_tin_tin.yaml", includes)

    def test_event_trigger_has_no_request_transform(self) -> None:
        trigger = u.event_trigger(record())
        self.assertNotIn("request_transform", trigger)      # Hasura 2.51 ghi cả header bí mật vào nhật ký khi có
        self.assertEqual(trigger["definition"], {"enable_manual": False, "insert": {"columns": "*"}})

    def test_core_event_triggers_not_overwritten(self) -> None:
        core = dict(self.core)
        key = "databases/default/tables/core_app_events.yaml"
        core[key] += b"event_triggers: []\n"
        with self.assertRaisesRegex(u.AppError, "đã có event_triggers"):
            u.metadata_tree(core, [record()])


class Compose(unittest.TestCase):
    def test_compose_files(self) -> None:
        o = u.OVERLAY
        logs = "docker-compose.yml:platform/logs/docker-compose.logs.yml"
        self.assertEqual(u.compose_files(None, with_overlay=True), f"docker-compose.yml:{o}")
        self.assertEqual(u.compose_files(logs, with_overlay=True), f"{logs}:{o}")
        self.assertEqual(u.compose_files(f"{logs}:{o}", with_overlay=True), f"{logs}:{o}")
        self.assertEqual(u.compose_files(f"{logs}:{o}", with_overlay=False), logs)
        self.assertIsNone(u.compose_files(None, with_overlay=False))

    def test_overlay(self) -> None:
        data = u.overlay([record()])
        self.assertEqual(data["services"]["apisix"]["volumes"],
                         ["./.moc-apps/apisix.yaml:/usr/local/apisix/conf/apisix.yaml:ro"])
        self.assertEqual(data["services"]["hasura"]["volumes"], ["./.moc-apps/hasura-metadata:/hasura-metadata:ro"])
        app = data["services"]["app-bang-tin"]
        self.assertEqual((app["profiles"], app["networks"], app["pull_policy"]), (["app"], ["moc"], "never"))
        self.assertTrue(app["read_only"])
        self.assertEqual((app["cap_drop"], app["mem_limit"], app["cpus"]), (["ALL"], "96m", 1.0))
        self.assertEqual(app["security_opt"], ["no-new-privileges:true"])
        self.assertNotIn("ports", app)                                      # chỉ APISIX mở cổng ra ngoài
        self.assertEqual(app["env_file"], [".moc-apps/bang-tin.env"])
        self.assertNotRegex(json.dumps(app["environment"]), "SECRET")
        self.assertEqual(app["environment"]["MOC_APP_EVENT_KINDS"], "office.document.issued,office.document.registered")

    def test_manifest_values_are_not_interpolated(self) -> None:
        rec = record(environment={"ADMIN": "${HASURA_ADMIN_SECRET}", "PGURL": "postgres://moc:$POSTGRES_PASSWORD@x",
                                  "GIA": "100$"},
                     healthcheck={"test": ["CMD-SHELL", "echo ${POSTGRES_PASSWORD}"], "interval": "15s"})
        app = u.overlay([rec])["services"]["app-bang-tin"]
        self.assertEqual(app["environment"]["ADMIN"], "$${HASURA_ADMIN_SECRET}")
        self.assertEqual(app["environment"]["PGURL"], "postgres://moc:$$POSTGRES_PASSWORD@x")
        self.assertEqual(app["environment"]["MOC_REALM"], "${MOC_REALM:-moc}")      # lõi đặt: vẫn nội suy
        self.assertEqual(app["healthcheck"]["test"], ["CMD-SHELL", "echo $${POSTGRES_PASSWORD}"])
        if not shutil.which("docker"):
            self.skipTest("không có docker: bỏ phần docker compose config")
        with tempfile.TemporaryDirectory() as tmp:            # compose thật đọc tệp phủ thật, .env có giá trị giả
            root = pathlib.Path(tmp)
            (root / "docker-compose.yml").write_text("services:\n  hasura:\n    image: busybox\n  apisix:\n"
                                                     "    image: busybox\nnetworks:\n  moc: {}\n", encoding="utf-8")
            (root / (".e" + "nv")).write_text("HASURA_ADMIN_SECRET=GIA-khoa\nPOSTGRES_PASSWORD=GIA-mk\n",
                                             encoding="utf-8")
            (root / ".moc-apps").mkdir()
            (root / u.OVERLAY).write_text(json.dumps(u.overlay([rec])), encoding="utf-8")
            (root / u.HASURA_ENV).write_text("", encoding="utf-8")
            (root / u.STATE / "bang-tin.env").write_text("", encoding="utf-8")
            proc = subprocess.run(["docker", "compose", "-f", "docker-compose.yml", "-f", u.OVERLAY, "--profile",
                                   "app", "config", "--format", "json"], cwd=root, capture_output=True, text=True)
            if proc.returncode != 0:
                self.skipTest(f"docker compose config không chạy được: {proc.stderr.strip()[-200:]}")
            svc = json.loads(proc.stdout)["services"]["app-bang-tin"]
        # `config` in lại dạng đã thoát ($$) — tức compose coi là chữ, không lấy từ .env
        self.assertIn(svc["environment"]["ADMIN"], ("${HASURA_ADMIN_SECRET}", "$${HASURA_ADMIN_SECRET}"))
        self.assertNotIn("GIA-", json.dumps(svc))


class FakeDB:
    """Đủ để chạy các câu của ung_dung: trạng thái core.apps, core.app_migrations, vai trò CSDL trong bộ nhớ."""

    def __init__(self) -> None:
        self.apps: dict[str, dict[str, Any]] = {}
        self.applied: dict[str, dict[str, str]] = {}
        self.schemas: set[str] = {"core", "office", "personal"}
        self.tables: set[str] = set()
        self.roles: dict[str, bool] = {}                 # vai trò → LOGIN?
        self.scripts: list[str] = []
        self.users: list[str] = []                       # vai trò của từng câu (moc hoặc vai trò ứng dụng)
        self.user = "moc"
        self.fail_on: str | None = None
        self.parent: FakeDB | None = None

    def as_user(self, user: str) -> FakeDB:
        other = FakeDB.__new__(FakeDB)
        other.__dict__ = self.__dict__.copy()
        other.user, other.parent = user, self
        return other

    def root(self) -> FakeDB:
        return self.parent or self

    def query(self, sql: str, **v: str) -> Any:
        db = self.root()
        db.scripts.append(sql)
        db.users.append(self.user)
        if db.fail_on and db.fail_on in sql:
            raise u.Unavailable("psql: không nối được")
        if sql == u.DB_READY_SQL:
            return {"ready": True}
        if sql == u.DB_STATE_SQL:
            owner = next((n for n, a in db.apps.items() if a["schema_name"] == v["schema"] and n != v["name"]), None)
            path = next((n for n, a in db.apps.items() if a.get("path") == v["path"] and n != v["name"]
                         and not a["removed_at"]), None)
            return {"app": db.apps.get(v["name"]), "schema_owner": owner, "path_owner": path,
                    "schema_exists": v["schema"] in db.schemas, "applied": db.applied.get(v["name"], {})}
        if sql == u.REGISTER_SQL:
            db.apps[v["name"]] = {"name": v["name"], "schema_name": v["schema"], "path": v["path"], "removed_at": None}
            return {"ok": True}
        if "create schema if not exists" in sql:
            assert self.user == "moc"
            db.roles.setdefault(re.search(r'create role "([a-z_0-9]+)"', sql).group(1), False)
            db.schemas.add(re.search(r'create schema if not exists "([a-z_0-9]+)"', sql).group(1))
            return {"ok": True}
        if sql.startswith("alter role"):
            role, login = re.match(r'alter role "([a-z_0-9]+)" (login|nologin);', sql).groups()
            db.roles[role] = login == "login"
            return {"ok": True}
        if "select moc_app.migration_done" in sql:
            assert self.user.startswith("moc_appdb_") and db.roles[self.user], "phải chạy bằng vai trò ứng dụng"
            db.tables.add("bang_tin.tin")
            db.applied.setdefault(v["name"], {})[re.search(r"migration_done\(:'name', (\d+)", sql).group(1)] = v["sha"]
            return {"ok": True}
        if sql == u.MISSING_TABLES_SQL:
            return [f"{t['s']}.{t['t']}" for t in json.loads(v["tables"]) if f"{t['s']}.{t['t']}" not in db.tables]
        if sql == u.REMOVED_SQL:
            db.apps[v["name"]]["removed_at"] = "2026-10-25"
            return {"ok": True}
        if sql == u.APPS_SQL:
            return [{**a, "title": "t", "path": "/p", "version": "1", "migrations": 1} for a in db.apps.values()]
        raise AssertionError(f"câu chưa giả lập: {sql[:80]}")


class FakeKC:
    def __init__(self) -> None:
        self.clients_: list[dict[str, Any]] = []
        self.writes: list[tuple[str, str]] = []
        self.fail = False

    def clients(self) -> list[dict[str, Any]]:
        if self.fail:
            raise u.tenants.KeycloakError(403, "GET", "/clients", '{"error": "HTTP 403 Forbidden"}')
        return copy.deepcopy(self.clients_)

    def create_client(self, rep: dict[str, Any]) -> str:
        assert rep["clientId"] not in {c["clientId"] for c in self.clients_}, "tạo trùng"
        cid = f"id-{len(self.writes)}"
        self.clients_.append({**rep, "id": cid})
        self.writes.append(("create", rep["clientId"]))
        return cid

    def delete_client(self, cid: str) -> None:
        self.writes.append(("delete", next(c["clientId"] for c in self.clients_ if c["id"] == cid)))
        self.clients_ = [c for c in self.clients_ if c["id"] != cid]

    def update_client(self, cid: str, rep: dict[str, Any]) -> None:
        self.writes.append(("update", rep["clientId"]))
        self.clients_ = [copy.deepcopy(rep) if c["id"] == cid else c for c in self.clients_]


def fake_system(root: pathlib.Path) -> Any:
    """System với Docker, Hasura giả (lớp con dựng lúc chạy: ung_dung chỉ nạp sau khi đã thay moc_env)."""

    class FakeSystem(u.System):
        def __init__(self, root: pathlib.Path):
            super().__init__(root, db=FakeDB(), kc=FakeKC())
            self.calls: list[list[str]] = []
            self.images: set[str] = set()
            self.applied = 0
            self.broken_once = False                 # lần áp metadata kế tiếp báo không nhất quán

        def run(self, cmd: list[str], *, input: str | None = None, timeout: float = 900) -> str:
            self.calls.append(cmd)
            if cmd[:2] == ["docker", "build"]:
                self.images.add(cmd[cmd.index("-t") + 1])
            return ""

        def image_exists(self, ref: str) -> bool:
            return ref in self.images

        def client_secret_ok(self, client_id: str, secret: str) -> bool | None:
            return True

        def apply_metadata(self) -> str:
            self.applied += 1
            return "Metadata applied"

        def metadata(self, body: dict[str, Any]) -> Any:
            if body["type"] == "get_inconsistent_metadata":
                if self.broken_once:
                    self.broken_once = False
                    return {"is_consistent": False, "inconsistent_objects": [{"reason": "no such table/view"}]}
                return {"is_consistent": True, "inconsistent_objects": []}
            apps = u.State(self.root).active()
            tree = u.metadata_tree(u.State(self.root).core_metadata(), apps)
            tables = [yaml_nho.loads(tree[k].decode()) for k in tree if "/app_" in k]
            triggers = yaml_nho.loads(tree["databases/default/tables/core_app_events.yaml"].decode()).get(
                "event_triggers", [])
            tables.append({"table": {"schema": "core", "name": "app_events"}, "event_triggers": triggers})
            return {"metadata": {"sources": [{"name": "default", "tables": tables}]}}

    return FakeSystem(root)


class Flow(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        for rel in ("platform/apisix/apisix.yaml", "db/metadata", "scripts/app-manifest.schema.json",
                    "platform/keycloak/realm/moc-realm.json"):
            src, dst = REPO / rel, self.tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            (shutil.copytree if src.is_dir() else shutil.copy)(src, dst)
        self.env = self.tmp / (".e" + "nv")
        self.env.write_text(f"MOC_PUBLIC_URL={PUBLIC}\nPOSTGRES_PASSWORD=khong-dung\n", encoding="utf-8")
        os.chmod(self.env, 0o600)
        self.state = u.State(self.tmp)
        self.system = fake_system(self.tmp)
        self.lines: list[str] = []

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def install(self, **kw: Any) -> dict[str, Any]:
        return u.install(APP, state=self.state, system=self.system, out=self.lines.append, **kw)

    def snapshot(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.tmp)): p.read_bytes() for p in sorted(self.tmp.rglob("*")) if p.is_file()}

    def test_dry_run_changes_nothing(self) -> None:
        before = self.snapshot()
        self.install(dry_run=True)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.system.kc.writes, [])
        self.assertFalse([s for s in self.system.db.scripts if s not in (u.DB_READY_SQL, u.DB_STATE_SQL)])
        self.assertFalse([c for c in self.system.calls if c[:2] in (["docker", "build"], ["docker", "compose"])])
        plan = "\n".join(self.lines)
        for needle in ("2/8 image: sẽ dựng", "3/8 CSDL: sẽ ghi core.apps; sẽ áp 1 migration: 1_tin",
                       "5/8 Keycloak: sẽ thêm app-bang-tin, thêm app-bang-tin-svc", "8/8 Hasura: sẽ áp"):
            self.assertIn(needle, plan)

    def test_install_then_again_creates_nothing_new(self) -> None:
        self.install()
        kc, db = self.system.kc, self.system.db
        self.assertEqual(kc.writes, [("create", "app-bang-tin"), ("create", "app-bang-tin-svc")])
        self.assertEqual(set(db.applied["bang-tin"]), {"1"})
        self.assertIn("bang_tin", db.schemas)
        gateway = (self.tmp / u.GATEWAY).read_text(encoding="utf-8")
        self.assertIn("  - id: app-bang-tin", gateway)
        self.assertIn(f"COMPOSE_FILE=docker-compose.yml:{u.OVERLAY}", self.env.read_text(encoding="utf-8"))
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)
        secrets_file = self.tmp / u.STATE / "bang-tin.env"
        self.assertEqual(secrets_file.stat().st_mode & 0o777, 0o600)
        values = u.parse_env(secrets_file.read_text(encoding="utf-8"))
        self.assertEqual(set(values), {"MOC_HOOK_SECRET", "MOC_CLIENT_ID", "MOC_CLIENT_SECRET"})
        hasura_env = u.parse_env((self.tmp / u.HASURA_ENV).read_text(encoding="utf-8"))
        self.assertEqual(hasura_env, {"MOC_APP_HOOK_BANG_TIN": values["MOC_HOOK_SECRET"]})
        out = "\n".join(self.lines)
        self.assertNotIn(values["MOC_HOOK_SECRET"], out)
        self.assertNotIn(values["MOC_CLIENT_SECRET"], out)
        up = [c for c in self.system.calls if "up" in c]
        self.assertEqual(up[-1][-3:], ["apisix", "hasura", "app-bang-tin"])
        self.assertIn("--no-deps", up[-1])
        pairs = list(zip(db.scripts, db.users, strict=True))
        self.assertEqual({who for q, who in pairs if "select moc_app.migration_done" in q},
                         {"moc_appdb_bang_tin"})                      # migration: phiên của vai trò ứng dụng
        self.assertEqual({who for q, who in pairs if "migration_done" not in q}, {"moc"})
        self.assertEqual(db.roles, {"moc_appdb_bang_tin": False})      # xong thì NOLOGIN

        snap, writes, scripts = self.snapshot(), list(kc.writes), len(db.scripts)
        self.lines.clear()
        self.install()
        self.assertEqual(self.snapshot(), snap)                       # tệp, bí mật giữ nguyên
        self.assertEqual(kc.writes, writes)                            # không tạo client trùng
        self.assertFalse([s for s in db.scripts[scripts:] if "app_migrations (app" in s])
        self.assertIn("không có migration mới", "\n".join(self.lines))
        self.assertIn("đã khớp", "\n".join(self.lines))

    def test_failure_names_the_step_and_rerun_completes(self) -> None:
        self.system.kc.fail = True
        with self.assertRaises(u.StepFailed) as ctx:
            self.install()
        self.assertIn("bước 5/8 (Keycloak)", str(ctx.exception))
        self.assertEqual(set(self.system.db.applied["bang-tin"]), {"1"})       # bước trước đã xong
        self.system.kc.fail = False
        self.lines.clear()
        self.install()
        self.assertEqual([w for w, _ in self.system.kc.writes], ["create", "create"])
        self.assertIn("8/8 Hasura: metadata đã áp: 1 bảng ứng dụng, 1 event trigger, nhất quán", "\n".join(self.lines))

    def test_step_8_failure_restores_runtime_files(self) -> None:
        before = self.snapshot()
        self.system.broken_once = True
        with self.assertRaises(u.StepFailed) as ctx:
            self.install()
        text = str(ctx.exception)
        self.assertIn("bước 8/8 (Hasura)", text)
        self.assertIn("đã trả tệp chạy và metadata Hasura về như trước lần cài này, nhất quán", text)
        self.assertFalse((self.tmp / u.STATE / "apps" / "bang-tin.json").exists())
        self.assertEqual((self.tmp / u.GATEWAY).read_bytes(), (self.tmp / u.CORE_GATEWAY).read_bytes())
        self.assertIn([*u.COMPOSE, "rm", "--stop", "--force", "app-bang-tin"], self.system.calls)
        self.assertEqual(self.system.applied, 2)                    # áp hỏng, rồi áp lại bản trước
        self.assertNotEqual(self.snapshot(), before)                 # .moc-apps có (tệp phủ trống ứng dụng, bí mật)
        self.lines.clear()
        self.install()                                               # sửa xong chạy lại: hoàn tất
        self.assertIn("8/8 Hasura: metadata đã áp", "\n".join(self.lines))

    def test_declared_table_missing_fails_at_database_step(self) -> None:
        self.system.db.tables.add("bang_tin.tin")
        rec_tables = u.load_manifest(APP, root=REPO)["tables"]
        self.assertEqual([t["table"]["name"] for t in rec_tables], ["tin"])
        orig = u.load_manifest

        def typo(path: pathlib.Path, *, root: pathlib.Path = REPO) -> dict[str, Any]:
            rec = orig(path, root=root)
            rec["tables"] = [{**rec["tables"][0], "table": {"schema": "bang_tin", "name": "tinn"}}]
            return rec
        with unittest.mock.patch.object(u, "load_manifest", typo), self.assertRaises(u.StepFailed) as ctx:
            self.install()
        self.assertIn("bước 3/8 (CSDL)", str(ctx.exception))
        self.assertIn("bang_tin.tinn", str(ctx.exception))
        self.assertFalse((self.tmp / u.STATE).exists())             # chưa ghi tệp chạy nào
        self.assertEqual(self.system.applied, 0)

    def test_path_change_updates_public_client(self) -> None:
        self.install()
        orig = u.load_manifest

        def moved(path: pathlib.Path, *, root: pathlib.Path = REPO) -> dict[str, Any]:
            return {**orig(path, root=root), "path": "/tin-don-vi"}
        self.lines.clear()
        with unittest.mock.patch.object(u, "load_manifest", moved):
            self.install()
        client = next(c for c in self.system.kc.clients_ if c["clientId"] == "app-bang-tin")
        self.assertEqual(client["redirectUris"], [f"{PUBLIC}/tin-don-vi/*"])
        self.assertEqual(client["baseUrl"], "/tin-don-vi/")
        self.assertEqual(client["attributes"]["post.logout.redirect.uris"], f"{PUBLIC}/tin-don-vi/*")
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")       # giữ phần khác
        self.assertEqual(self.system.kc.writes[2:], [("update", "app-bang-tin")])
        self.assertIn("sửa app-bang-tin (attributes, baseUrl, redirectUris)", "\n".join(self.lines))
        self.assertIn('uris: ["/tin-don-vi", "/tin-don-vi/*"]', (self.tmp / u.GATEWAY).read_text(encoding="utf-8"))

    def test_half_install_listed_as_error_and_removable(self) -> None:
        self.system.kc.fail = True
        with self.assertRaises(u.StepFailed):
            self.install()                                    # bước 3 đã ghi core.apps, bước 5 lỗi
        self.system.kc.fail = False
        self.assertFalse((self.tmp / u.STATE / "apps").exists())
        buf = io.StringIO()
        with redirect_stdout(buf), unittest.mock.patch.object(u, "_system_and_state",
                                                              lambda: (self.system, self.state)):
            u.cmd_list(argparse.Namespace(json=False))
        self.assertIn("LỖI: cài dở", buf.getvalue())
        self.assertNotIn("đã gỡ", buf.getvalue())
        u.remove("bang-tin", state=self.state, system=self.system, out=self.lines.append)
        self.assertEqual(self.system.db.apps["bang-tin"]["removed_at"], "2026-10-25")
        with self.assertRaisesRegex(u.AppError, "không có ứng dụng"):
            u.remove("bang-tin", state=self.state, system=self.system, out=self.lines.append)

    def test_lost_secret_file_rebuilds_service_client(self) -> None:
        self.install()
        (self.tmp / u.STATE / "bang-tin.env").unlink()
        self.install()
        self.assertEqual(self.system.kc.writes[2:], [("delete", "app-bang-tin-svc"), ("create", "app-bang-tin-svc")])

    def test_remove_keeps_data(self) -> None:
        self.install()
        self.lines.clear()
        u.remove("bang-tin", state=self.state, system=self.system, out=self.lines.append)
        db = self.system.db
        self.assertEqual(db.apps["bang-tin"]["removed_at"], "2026-10-25")
        self.assertEqual(set(db.applied["bang-tin"]), {"1"})
        self.assertFalse([s for s in db.scripts if re.search(r"\b(drop|delete|truncate)\b", s, re.I)])
        self.assertEqual(self.system.kc.writes[2:], [("delete", "app-bang-tin"), ("delete", "app-bang-tin-svc")])
        core = (self.tmp / u.CORE_GATEWAY).read_bytes()
        self.assertEqual((self.tmp / u.GATEWAY).read_bytes(), core)   # không còn ứng dụng: giống hệt tệp lõi
        self.assertFalse((self.tmp / u.STATE / "apps" / "bang-tin.json").exists())
        self.assertEqual(u.parse_env((self.tmp / u.HASURA_ENV).read_text(encoding="utf-8")), {})
        self.assertIn([*u.COMPOSE, "rm", "--stop", "--force", "app-bang-tin"], self.system.calls)
        with self.assertRaisesRegex(u.AppError, "không có ứng dụng"):
            u.remove("bang-tin", state=self.state, system=self.system, out=self.lines.append)

    def test_other_app_cannot_take_path_or_schema(self) -> None:
        self.install()
        other = record(name="bang-tin-2")
        self.state.save({**other, "path": "/khac", "schema": "bang_tin"})
        with self.assertRaisesRegex(u.AppError, "đã dùng đường"):
            self.install()

    def test_sync_files_rebuilds_after_core_change(self) -> None:
        self.install()
        gateway = self.tmp / u.GATEWAY
        inode = gateway.stat().st_ino
        core = self.tmp / u.CORE_GATEWAY
        core.write_text(core.read_text(encoding="utf-8").replace("  - id: chan\n", "  # đổi\n  - id: chan\n"),
                        encoding="utf-8")
        self.assertEqual(self.state.stale(), [u.GATEWAY])
        result = u.sync(state=self.state, system=self.system, files_only=True, out=self.lines.append)
        self.assertEqual(result["changed"], [u.GATEWAY])
        self.assertIn("  # đổi\n", gateway.read_text(encoding="utf-8"))
        self.assertEqual(gateway.stat().st_ino, inode)                     # vẫn tệp container đang gắn
        self.assertEqual(u.sync(state=self.state, system=self.system, files_only=True)["changed"], [])

    def test_sync_without_state_dir_does_nothing(self) -> None:
        self.assertEqual(u.sync(state=self.state, system=self.system)["changed"], [])
        self.assertFalse((self.tmp / u.STATE).exists())
        self.assertNotIn("COMPOSE_FILE", self.env.read_text(encoding="utf-8"))


class Keycloak(unittest.TestCase):
    def test_public_client_like_app_office(self) -> None:
        c = u.public_client(record(), {"MOC_PUBLIC_URL": PUBLIC})
        self.assertEqual(c["clientId"], "app-bang-tin")
        self.assertTrue(u.realm_clients.browser_app(c))
        self.assertEqual(c["redirectUris"], [f"{PUBLIC}/bang-tin/*"])
        self.assertEqual(c["attributes"]["post.logout.redirect.uris"], f"{PUBLIC}/bang-tin/*")
        self.assertEqual(c["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertEqual(len(c["protocolMappers"]), 5)
        self.assertNotIn("id", c)

    def test_service_client_only_client_credentials(self) -> None:
        c = u.service_client(record(), "bi-mat")
        self.assertFalse(u.realm_clients.browser_app(c))                  # moc realm clients không đụng tới
        self.assertTrue(c["serviceAccountsEnabled"])
        self.assertFalse(c["standardFlowEnabled"] or c["directAccessGrantsEnabled"] or c["implicitFlowEnabled"])
        claims = {m["config"]["claim.name"].split(".")[-1]: m["config"] for m in c["protocolMappers"]}
        self.assertEqual(claims["x-hasura-default-role"]["claim.value"], "app_bang_tin")
        self.assertEqual(json.loads(claims["x-hasura-allowed-roles"]["claim.value"]), ["app_bang_tin"])
        self.assertEqual(claims["x-hasura-allowed-roles"]["jsonType.label"], "JSON")
        self.assertNotIn("x-hasura-tenant-id", claims)


class Cli(unittest.TestCase):
    def test_app_group(self) -> None:
        import argparse
        parser = argparse.ArgumentParser()
        u.add_parser(parser.add_subparsers(dest="group", required=True))
        args = parser.parse_args(["app", "install", "apps/bang-tin/app.yaml", "--dry-run"])
        self.assertEqual((args.cmd, args.dry_run, args.run), ("install", True, u.cmd_install))
        self.assertEqual(parser.parse_args(["app", "remove", "bang-tin"]).run, u.cmd_remove)
        self.assertTrue(parser.parse_args(["app", "sync", "--files", "--json"]).files)
        self.assertTrue(parser.parse_args(["app", "list", "--json"]).json)
        moc = (SCRIPTS / "moc.py").read_text(encoding="utf-8")
        self.assertIn("ung_dung.add_parser(groups)", moc)

    def test_failure_message_and_exit_code(self) -> None:
        import argparse
        args = argparse.Namespace(cmd="install", manifest="apps/bang-tin/app.yaml", json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = u._fail(u.StepFailed(5, 8, "Keycloak", u.AppError("HTTP 403")), args)
        self.assertEqual(code, 1)
        msg = json.loads(buf.getvalue())["error"]
        self.assertIn("bước 5/8 (Keycloak): HTTP 403", msg)
        self.assertIn("app install apps/bang-tin/app.yaml", msg)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(u._fail(u.StepFailed(3, 8, "CSDL", u.Unavailable("psql")), args), 2)


if __name__ == "__main__":
    unittest.main()
