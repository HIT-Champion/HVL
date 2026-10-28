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

"""Tự động hóa bằng Node-RED (#366): client Keycloak `tu-dong`, vai trò operator, robot của đơn vị (`moc tu-dong`);
hai flow mẫu; settings.js, image, compose, route, Makefile. Keycloak, docker, moc.py giả: không cần Docker, không đọc
.env. settings.js nạp thật lúc dựng image (platform/tu-dong/kiem-tra.cjs); màn chạy thật trên stack: make
demo-tu-dong (CI)."""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import pathlib
import re
import shutil
import sys
import types
import unittest
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
TU_DONG_DIR = ROOT / "platform" / "tu-dong"
sys.path.insert(0, str(SCRIPTS / "tests"))

import test_wiki  # noqa: E402  (make giả, khối service của wiki; import cả module để test của nó không chạy ở đây)

service_block = test_wiki.service_block

tu_dong: Any = None
_saved: dict[str, Any] = {}


def setUpModule() -> None:
    """Như test_tenants: moc_env thật đọc .env lúc nạp — thay bằng bản giả, không gọi mạng."""
    global tu_dong
    for name in ("moc_env", "tenants", "tu_dong"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ENV = {}
    stub.ROOT = ROOT
    stub.REALM = "moc"
    stub.KEYCLOAK_ADMIN_URL = "http://127.0.0.1:8180"
    stub.PUBLIC_URL = "https://signet.example"
    stub.HTTPError = type("HTTPError", (Exception,), {})

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng")

    stub.call_json = no_network
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    tu_dong = importlib.import_module("tu_dong")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class FakeKc:
    """Keycloak giả: client, mapper, vai trò client, tài khoản và vai trò đã gán."""

    realm_name = "moc"

    def __init__(self, clients: list[dict[str, Any]] | None = None) -> None:
        self._clients = clients or []
        self.mappers: dict[str, list[dict[str, Any]]] = {}
        self.roles: dict[str, list[dict[str, Any]]] = {}
        self.users = {"quantri": {"id": "u1", "username": "quantri"}, "vanthu": {"id": "u2", "username": "vanthu"}}
        self.granted: set[str] = set()
        self.calls: list[tuple[Any, ...]] = []

    def clients(self) -> list[dict[str, Any]]:
        return self._clients

    def create_client(self, rep: dict[str, Any]) -> str:
        self.calls.append(("create", rep))
        self._clients.append({**rep, "id": "k-new"})
        return "k-new"

    def update_client(self, client_id: str, rep: dict[str, Any]) -> None:
        self.calls.append(("update", client_id, rep))

    def delete_client(self, client_id: str) -> None:
        self.calls.append(("delete", client_id))
        self._clients = [c for c in self._clients if c["id"] != client_id]

    def client_secret(self, client_id: str, *, regenerate: bool = False) -> str:
        self.calls.append(("secret", client_id, regenerate))
        return "bi-mat-moi" if regenerate else "bi-mat"

    def update_protocol_mapper(self, client_id: str, mapper_id: str, rep: dict[str, Any]) -> None:
        self.calls.append(("mapper-put", client_id, mapper_id, rep))

    def protocol_mappers(self, client_id: str) -> list[dict[str, Any]]:
        return self.mappers.get(client_id, [])

    def add_protocol_mapper(self, client_id: str, rep: dict[str, Any]) -> None:
        self.calls.append(("mapper", client_id, rep))

    def client_roles(self, client_id: str) -> list[dict[str, Any]]:
        return self.roles.get(client_id, [])

    def create_client_role(self, client_id: str, rep: dict[str, Any]) -> None:
        self.calls.append(("role", client_id, rep))
        self.roles.setdefault(client_id, []).append({**rep, "id": "r1"})

    def client_role_users(self, client_id: str, role: str) -> list[dict[str, Any]]:
        return [u for u in self.users.values() if u["id"] in self.granted]

    def find_user(self, username: str) -> dict[str, Any] | None:
        return self.users.get(username)

    def grant_client_roles(self, user_id: str, client_id: str, roles: list[dict[str, Any]], *,
                           revoke: bool = False) -> None:
        self.calls.append(("revoke" if revoke else "grant", user_id, client_id, [r["name"] for r in roles]))
        (self.granted.discard if revoke else self.granted.add)(user_id)


def ready_kc() -> FakeKc:
    kc = FakeKc([{"id": "k1", "clientId": "tu-dong"}])
    kc.roles["k1"] = [{"id": "r1", "name": "operator"}]
    return kc


class ClientTest(unittest.TestCase):
    def test_public_code_flow_with_pkce_back_to_node_red(self) -> None:
        rep = tu_dong.client_rep("https://signet.example/")
        self.assertEqual(rep["clientId"], "tu-dong")
        self.assertTrue(rep["publicClient"])
        self.assertTrue(rep["standardFlowEnabled"])
        for flow in ("directAccessGrantsEnabled", "serviceAccountsEnabled", "implicitFlowEnabled"):
            self.assertFalse(rep[flow], flow)
        # đường callback của adminAuth.type "strategy" trong Node-RED (editor-api lib/auth/index.js)
        self.assertEqual(rep["redirectUris"], ["https://signet.example/tu-dong/auth/strategy/callback"])
        self.assertEqual(rep["webOrigins"], [])
        self.assertEqual(rep["attributes"], {"pkce.code.challenge.method": "S256"})

    def test_roles_go_only_into_the_id_token(self) -> None:
        config = tu_dong.MAPPER["config"]
        self.assertEqual(tu_dong.MAPPER["protocolMapper"], "oidc-usermodel-client-role-mapper")
        self.assertEqual(config["usermodel.clientRoleMapping.clientId"], "tu-dong")
        self.assertEqual(config["claim.name"], "resource_access.${client_id}.roles")
        self.assertEqual(config["id.token.claim"], "true")
        for token in ("access.token.claim", "userinfo.token.claim", "introspection.token.claim"):
            self.assertEqual(config[token], "false", token)

    def test_creates_client_with_mapper_and_role(self) -> None:
        kc = FakeKc()
        self.assertEqual(tu_dong.ensure_client(kc, "https://signet.example"), "created")
        (kind, rep), role = kc.calls
        self.assertEqual(kind, "create")
        self.assertEqual(rep["protocolMappers"], [tu_dong.MAPPER])
        self.assertEqual(role, ("role", "k-new", tu_dong.ROLE_REP))
        self.assertEqual(tu_dong.ROLE_REP["name"], "operator")

    def test_updates_urls_keeps_other_fields_adds_missing_mapper_and_role(self) -> None:
        found = {"id": "k1", "clientId": "tu-dong", "redirectUris": ["https://cu/tu-dong/auth/strategy/callback"],
                 "attributes": {"pkce.code.challenge.method": "plain", "khac": "giu"}, "description": "x"}
        kc = FakeKc([found])
        self.assertEqual(tu_dong.ensure_client(kc, "https://moi"), "updated")
        (kind, cid, rep), mapper, role = kc.calls
        self.assertEqual((kind, cid), ("update", "k1"))
        self.assertEqual(rep["redirectUris"], ["https://moi/tu-dong/auth/strategy/callback"])
        self.assertEqual(rep["attributes"], {"pkce.code.challenge.method": "S256", "khac": "giu"})
        self.assertEqual(rep["description"], "x")
        self.assertEqual(mapper, ("mapper", "k1", tu_dong.MAPPER))
        self.assertEqual(role[0], "role")
        kc = ready_kc()
        kc.mappers["k1"] = [{"name": "tu-dong-roles"}]
        tu_dong.ensure_client(kc, "https://moi")
        self.assertEqual([c[0] for c in kc.calls], ["update"])

    def test_dry_run_changes_nothing(self) -> None:
        kc = ready_kc()
        self.assertEqual(tu_dong.ensure_client(kc, "https://x", dry_run=True), "updated")
        self.assertEqual(tu_dong.ensure_client(FakeKc(), "https://x", dry_run=True), "created")
        self.assertEqual(kc.calls, [])
        result = tu_dong.sync({"MOC_PUBLIC_URL": "https://x", "MOC_TU_DONG_SECRET": "k" * 32}, dry_run=True,
                              kc=FakeKc())
        self.assertEqual(result, {"client": "created", "operators": []})


class OperatorTest(unittest.TestCase):
    def test_grant_then_revoke_only_when_needed(self) -> None:
        kc = ready_kc()
        self.assertEqual(tu_dong.set_operator(kc, "quantri"), "added")
        self.assertEqual(tu_dong.set_operator(kc, "quantri"), "unchanged")
        self.assertEqual(tu_dong.operators(kc), ["quantri"])
        self.assertEqual(tu_dong.set_operator(kc, "vanthu", revoke=True), "unchanged")
        self.assertEqual(tu_dong.set_operator(kc, "quantri", revoke=True), "removed")
        self.assertEqual(tu_dong.operators(kc), [])
        self.assertEqual(kc.calls, [("grant", "u1", "k1", ["operator"]), ("revoke", "u1", "k1", ["operator"])])

    def test_unknown_user_or_missing_client_is_refused(self) -> None:
        with self.assertRaisesRegex(tu_dong.tenants.TenantError, "không có tài khoản ai-do"):
            tu_dong.set_operator(ready_kc(), "ai-do")
        with self.assertRaisesRegex(tu_dong.tenants.TenantError, "make tu-dong-up"):
            tu_dong.set_operator(FakeKc(), "quantri")
        with self.assertRaisesRegex(tu_dong.tenants.TenantError, "make tu-dong-up"):
            tu_dong.operators(FakeKc([{"id": "k1", "clientId": "tu-dong"}]))

    def test_secret_must_be_set_and_long(self) -> None:
        for env in ({}, {"MOC_TU_DONG_SECRET": "change_me"}, {"MOC_TU_DONG_SECRET": "k" * 31}):
            with self.assertRaisesRegex(tu_dong.tenants.TenantError, "MOC_TU_DONG_SECRET"):
                tu_dong.check_secret(env)
        tu_dong.check_secret({"MOC_TU_DONG_SECRET": "k" * 32})

    def test_cli_parses_sync_and_operator(self) -> None:
        import argparse
        parser = argparse.ArgumentParser()
        tu_dong.add_parser(parser.add_subparsers(dest="group"))
        args = parser.parse_args(["tu-dong", "operator", "add", "quantri"])
        self.assertEqual((args.action, args.username, args.run), ("add", "quantri", tu_dong.cmd_operator))
        self.assertEqual(parser.parse_args(["tu-dong", "sync", "--dry-run"]).run, tu_dong.cmd_sync)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["tu-dong", "operator", "grant", "quantri"])


CNTT = "c300d5bb-028f-44cc-ba10-7b5277a4225d"


class FakeDb:
    def query(self, sql: str) -> list[dict[str, Any]]:
        assert sql == tu_dong.tenants.TENANTS_SQL
        return [{"id": CNTT, "code": "CNTT"}, {"id": "t-kt", "code": "KT"}]


class RobotTest(unittest.TestCase):
    """moc tu-dong robot: mỗi đơn vị một client confidential, chỉ client_credentials, claim Hasura cố định."""

    def test_client_credentials_only_no_full_scope(self) -> None:
        rep = tu_dong.robot_rep("CNTT")
        self.assertEqual(rep["clientId"], "tu-dong-robot-cntt")
        self.assertEqual((rep["publicClient"], rep["serviceAccountsEnabled"], rep["fullScopeAllowed"]),
                         (False, True, False))
        self.assertFalse(rep["standardFlowEnabled"] or rep["implicitFlowEnabled"] or rep["directAccessGrantsEnabled"])
        self.assertEqual((rep["redirectUris"], rep["webOrigins"]), ([], []))

    def test_fixed_hasura_claims_in_the_access_token_only(self) -> None:
        mappers = {m["name"]: m for m in tu_dong.robot_mappers("CNTT", CNTT)}
        claims = {m["config"]["claim.name"]: m["config"]["claim.value"] for m in mappers.values()}
        ns = "https://hasura\\.io/jwt/claims."
        self.assertEqual(claims, {ns + "x-hasura-user-id": "tu-dong-robot-cntt", ns + "x-hasura-tenant-id": CNTT,
                                  ns + "x-hasura-default-role": "tu_dong",
                                  ns + "x-hasura-allowed-roles": '["tu_dong"]'})
        self.assertEqual(mappers["hasura-allowed-roles"]["config"]["jsonType.label"], "JSON")
        for m in mappers.values():
            self.assertEqual(m["protocolMapper"], "oidc-hardcoded-claim-mapper")
            self.assertEqual((m["config"]["access.token.claim"], m["config"]["id.token.claim"],
                              m["config"]["userinfo.token.claim"]), ("true", "false", "false"))
        realm = read(ROOT / "platform" / "keycloak" / "realm" / "moc-realm.json")
        self.assertIn('"claim.name": "https://hasura\\\\.io/jwt/claims.x-hasura-tenant-id"', realm)

    def test_add_creates_then_resets_drifted_fields_and_mappers(self) -> None:
        kc = FakeKc([{"id": "k1", "clientId": "tu-dong"}])
        out = tu_dong.add_robot(kc, "CNTT", db=FakeDb())
        self.assertEqual(out, {"client_id": "tu-dong-robot-cntt", "code": "CNTT", "tenant_id": CNTT,
                               "result": "created", "secret": "bi-mat"})
        self.assertEqual(kc.calls[0][1]["protocolMappers"], tu_dong.robot_mappers("CNTT", CNTT))
        kc.calls.clear()
        kc._clients[-1].update(fullScopeAllowed=True, directAccessGrantsEnabled=True, description="cũ")
        drifted = {**tu_dong.robot_mappers("CNTT", "t-khac")[1], "id": "m2"}
        kc.mappers["k-new"] = [{**tu_dong.robot_mappers("CNTT", CNTT)[0], "id": "m1"}, drifted]
        self.assertEqual(tu_dong.add_robot(kc, "CNTT", db=FakeDb())["result"], "updated")
        update = kc.calls[0]
        self.assertEqual((update[0], update[1], update[2]["fullScopeAllowed"], update[2]["directAccessGrantsEnabled"]),
                         ("update", "k-new", False, False))
        self.assertEqual(kc.calls[1], ("mapper-put", "k-new", "m2",
                                       {**tu_dong.robot_mappers("CNTT", CNTT)[1], "id": "m2"}))
        self.assertEqual([c[2]["name"] for c in kc.calls if c[0] == "mapper"],
                         ["hasura-default-role", "hasura-allowed-roles"])
        self.assertEqual(kc.calls[-1], ("secret", "k-new", False))

    def test_unknown_unit_is_refused_before_touching_keycloak(self) -> None:
        kc = FakeKc()
        with self.assertRaisesRegex(tu_dong.tenants.TenantError, "không có đơn vị mã XYZ"):
            tu_dong.add_robot(kc, "XYZ", db=FakeDb())
        self.assertEqual(kc.calls, [])

    def test_rotate_list_remove(self) -> None:
        kc = FakeKc([{"id": "k1", "clientId": "tu-dong"},
                     {"id": "k2", "clientId": "tu-dong-robot-kt", "enabled": False},
                     {"id": "k3", "clientId": "tu-dong-robot-cntt", "enabled": True}])
        kc.mappers["k3"] = [{**tu_dong.robot_mappers("CNTT", CNTT)[1], "id": "m"}]
        self.assertEqual(tu_dong.robots(kc), [
            {"client_id": "tu-dong-robot-cntt", "tenant_id": CNTT, "enabled": True},
            {"client_id": "tu-dong-robot-kt", "tenant_id": None, "enabled": False}])
        self.assertEqual(tu_dong.rotate_robot(kc, "CNTT")["secret"], "bi-mat-moi")
        self.assertEqual(kc.calls, [("secret", "k3", True)])
        with self.assertRaisesRegex(tu_dong.tenants.TenantError, "robot add ĐT"):
            tu_dong.rotate_robot(kc, "ĐT")
        self.assertEqual(tu_dong.remove_robot(kc, "CNTT"), "removed")
        self.assertEqual(tu_dong.remove_robot(kc, "CNTT"), "unchanged")
        self.assertEqual([c["clientId"] for c in kc.clients()], ["tu-dong", "tu-dong-robot-kt"])

    def test_cli_parses_robot(self) -> None:
        import argparse
        parser = argparse.ArgumentParser()
        tu_dong.add_parser(parser.add_subparsers(dest="group"))
        args = parser.parse_args(["tu-dong", "robot", "add", "CNTT", "--json"])
        self.assertEqual((args.action, args.code, args.json, args.run), ("add", "CNTT", True, tu_dong.cmd_robot))
        self.assertIsNone(parser.parse_args(["tu-dong", "robot", "list"]).code)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["tu-dong", "robot", "add", "a/b"])


class FlowMauTest(unittest.TestCase):
    """platform/tu-dong/flow-mau.json: hai flow mẫu nhập vào trình soạn; chạy thật trên stack ở make demo-tu-dong."""

    flow = json.loads(read(TU_DONG_DIR / "flow-mau.json"))
    nodes = {n["id"]: n for n in flow}
    code = "\n".join(n.get("func", "") for n in flow)

    def test_one_tab_only_allowed_node_types(self) -> None:
        self.assertEqual(len(self.nodes), len(self.flow))
        tabs = [n for n in self.flow if n["type"] == "tab"]
        self.assertEqual([t["id"] for t in tabs], ["moc-flow-mau"])
        self.assertTrue(all(n.get("z") == "moc-flow-mau" for n in self.flow if n["type"] != "tab"))
        allowed = {"tab", "group", "comment", "inject", "link in", "link out", "link call", "function", "http request",
                   "catch", "debug"}
        self.assertLessEqual({n["type"] for n in self.flow}, allowed)

    def test_robot_secret_is_a_credential_never_shipped(self) -> None:
        env = {e["name"]: e for e in self.nodes["moc-flow-mau"]["env"]}
        self.assertEqual(env["ROBOT_SECRET"], {"name": "ROBOT_SECRET", "type": "cred"})
        self.assertEqual((env["ROBOT_ID"]["value"], env["SIGNET_GATEWAY"]["value"]), ("", "http://apisix:9080"))
        self.assertNotIn('"credentials"', read(TU_DONG_DIR / "flow-mau.json"))
        debug = self.nodes["moc-mau-loi-debug"]
        self.assertEqual((debug["complete"], debug["targetType"]), ("error", "msg"))   # không in msg (có token)

    def test_schedules(self) -> None:
        self.assertEqual(self.nodes["moc-mau-han-inject"]["crontab"], "00 07 * * *")   # TZ của container: giờ VN
        self.assertEqual(self.nodes["moc-mau-hoa-toc-inject"]["repeat"], "60")

    def test_reads_only_columns_the_robot_role_has(self) -> None:
        meta = read(ROOT / "db" / "metadata" / "databases" / "default" / "tables" / "office_documents.yaml")
        block = re.search(r"- role: tu_dong\n\s+permission:\n\s+columns: \[(.*?)\]", meta, re.S).group(1)
        allowed = {c.strip() for c in block.split(",")}
        queries = re.findall(r"office_documents\(([\s\S]*?)\n\s*\) \{([^}]*)\}", self.code)
        self.assertEqual(len(queries), 2)
        for where, fields in queries:
            used = set(fields.split()) | set(re.findall(r"(\w+): \{_", where))
            self.assertLessEqual(used, allowed)

    def test_notifies_directors_once_per_key(self) -> None:
        self.assertEqual(self.code.count("notifyFromFlow(roles: $roles"), 2)
        han, hoa_toc = self.nodes["moc-mau-han-soan"]["func"], self.nodes["moc-mau-hoa-toc-tach"]["func"]
        self.assertIn("roles: ['director'], title, text: lines.join('\\n'), key: 'han:' + today", han)
        self.assertNotIn("document_id: d.id", han)       # danh sách gộp không gắn văn bản
        for part in ("roles: ['director'],", "document_id: d.id,", "key: 'hoa-toc:' + d.id,"):
            self.assertIn(part, hoa_toc)


class SettingsTest(unittest.TestCase):
    """platform/tu-dong/settings.js: đọc chữ (kiem-tra.cjs nạp thật lúc dựng image)."""

    text = read(TU_DONG_DIR / "settings.js")

    def test_same_client_role_and_path_as_moc_tu_dong(self) -> None:
        self.assertIn(f"const CLIENT_ID = '{tu_dong.CLIENT_ID}'", self.text)
        self.assertIn(f"const ROLE = '{tu_dong.ROLE}'", self.text)
        self.assertIn(f"httpAdminRoot: '{tu_dong.BASE.rstrip('/')}'", self.text)
        self.assertIn("callbackURL: `${PUBLIC_URL}/tu-dong/auth/strategy/callback`", self.text)

    def test_roles_read_from_the_verified_id_token_only(self) -> None:
        self.assertIn("roles(claims).includes(ROLE)", self.text)
        self.assertNotIn("access_token", self.text)

    def test_locked_down(self) -> None:
        for needle in ("httpNodeRoot: false", "functionExternalModules: false",
                       "nodesExcludes: ['90-exec.js', '10-file.js', '23-watch.js']",
                       "palette: { allowInstall: false, allowUpload: false }", "modules: { allowInstall: false }",
                       "autoInstall: false", "diagnostics: { enabled: false", "runtimeState: { enabled: false",
                       "telemetry: { enabled: false", "projects: { enabled: false }",
                       "delete process.env.MOC_TU_DONG_SECRET", "credentialSecret: SECRET"):
            self.assertIn(needle, self.text)
        # chỉ một cách đăng nhập: Keycloak; không tài khoản, mật khẩu riêng của Node-RED
        self.assertIn("type: 'strategy'", self.text)
        self.assertNotRegex(self.text, r"password\s*:")


class ImageTest(unittest.TestCase):
    def test_image_pinned_and_settings_checked_at_build(self) -> None:
        text = read(TU_DONG_DIR / "Dockerfile")
        self.assertRegex(text, r"\nFROM nodered/node-red:5\.0\.8-minimal@sha256:[0-9a-f]{64}\n")
        self.assertIn("npm ci --omit=dev --ignore-scripts", text)
        self.assertIn("RUN node kiem-tra.cjs && rm kiem-tra.cjs", text)
        # chạy bằng user của image, không phải root
        self.assertEqual(re.findall(r"\nUSER (\S+)", text)[-1], "node-red")
        self.assertIn('CMD ["--settings", "/moc/settings.js"]', text)

    def test_dependencies_pinned_with_integrity_and_open_licences(self) -> None:
        pkg = json.loads(read(TU_DONG_DIR / "package.json"))
        lock = json.loads(read(TU_DONG_DIR / "package-lock.json"))
        self.assertEqual(pkg["dependencies"], {"openid-client": "6.8.8"})
        packages = {k: v for k, v in lock["packages"].items() if k}
        self.assertEqual(sorted(k.rsplit("node_modules/", 1)[-1] for k in packages),
                         ["jose", "oauth4webapi", "openid-client"])
        for name, meta in packages.items():
            self.assertRegex(meta.get("integrity", ""), r"^sha512-", name)
            self.assertEqual(meta.get("license"), "MIT", name)
            self.assertTrue(meta.get("resolved", "").startswith("https://registry.npmjs.org/"), name)



class ConfigTest(unittest.TestCase):
    def test_compose_service_off_by_default_unprivileged_apps_network_only(self) -> None:
        compose = read(ROOT / "docker-compose.yml")
        block = service_block(compose, "tu-dong")
        for line in ("profiles: [tu-dong]", "networks: [apps]", "read_only: true", "cap_drop: [ALL]",
                     "security_opt: [no-new-privileges:true]", "build: ./platform/tu-dong", "- tu_dong_data:/data",
                     "MOC_TU_DONG_SECRET: ${MOC_TU_DONG_SECRET:-}",
                     "fetch('http://127.0.0.1:1880/tu-dong/auth/login')"):
            self.assertIn(line, block)
        self.assertNotIn("ports:", block)                       # chỉ tới được qua APISIX
        self.assertIn("\n  tu_dong_data:\n", compose[compose.index("\nvolumes:\n"):])
        self.assertIn("- tu_dong_data:/data/tu-dong", service_block(compose, "restic"))

    def test_route_behind_the_gateway_and_reserved(self) -> None:
        apisix = read(ROOT / "platform" / "apisix" / "apisix.yaml")
        route = apisix[apisix.index("  - id: tu-dong\n    uris:"):]
        route = route[:route.index("\n\n")]
        for line in ('uris: ["/tu-dong", "/tu-dong/*"]', "upstream_id: tu-dong", "enable_websocket: true"):
            self.assertIn(line, route)
        self.assertNotIn("proxy-rewrite", route)                # Node-RED chạy sẵn dưới /tu-dong/ (httpAdminRoot)
        self.assertIn('"/wiki", "/tu-dong",', read(SCRIPTS / "ung_dung.py"))     # RESERVED_PATHS: ứng dụng không che

    def test_env_make_install_backup_ci(self) -> None:
        self.assertRegex(read(ROOT / (".e" + "nv.example")), r"\nMOC_TU_DONG_SECRET=change_me\n")
        make = read(ROOT / "Makefile")
        for target in ("tu-dong-env:", "tu-dong-up:", "tu-dong-down:", "demo-tu-dong:"):
            self.assertIn(f"\n{target}", make)
        self.assertEqual(make.count("--profile iot --profile iot-sim --profile tu-dong \\\n"), 2)  # make down, reset
        runtime = re.search(r"^RUNTIME=\((.*?)\)", read(SCRIPTS / "install.sh"), re.M | re.S).group(1).split()
        for rel in ("scripts/tu_dong.py", "scripts/demo_tu_dong.py", "platform/tu-dong/flow-mau.json"):
            self.assertIn(rel, runtime)
        self.assertIn("|| extra_build+=(--profile tu-dong)", read(SCRIPTS / "install.sh"))
        self.assertIn("    tu_dong.add_parser(groups)\n", read(SCRIPTS / "moc.py"))
        backup = read(SCRIPTS / "backup.py")
        self.assertIn('"tu_dong": ("tu-dong", "/data/tu-dong", ', backup)
        # volume tạo mới lúc khôi phục: gốc /data phải về lại user node-red, không thì Node-RED không ghi được gì
        self.assertIn('ROOT_OWNER = {"tu_dong": "1000:0"}', backup)
        self.assertRegex(backup, r'"--entrypoint",\s+"chown", "restic", ROOT_OWNER\[key\], path\]')
        ci = read(ROOT / ".github" / "workflows" / "ci.yml")
        for line in ("make demo-tu-dong", "moc_wiki_data moc_tu_dong_data",
                     "python3 scripts/demo_tu_dong.py --sau-khoi-phuc"):
            self.assertIn(line, ci)


@unittest.skipUnless(shutil.which("make"), "cần GNU Make")
class MakefileTest(unittest.TestCase):
    """make up, make tu-dong-up với docker và moc.py giả (bộ chạy của test_wiki)."""

    run_make = test_wiki.MakefileTest.run_make

    def test_make_up_with_tu_dong_profile_fills_secret_and_syncs(self) -> None:
        env, docker, moc, _ = self.run_make("up", "MOC_PUBLIC_URL=https://x\nMOC_EXTRA_PROFILES=tu-dong\n")
        self.assertRegex(env, r"\nMOC_TU_DONG_SECRET=[0-9a-f]{48}\n")
        self.assertIn("compose --profile core --profile app --profile tu-dong up -d --build --wait", docker)
        self.assertEqual(moc, "tu-dong sync\n")
        again, _, _, _ = self.run_make("up", env)
        self.assertEqual(again.count("MOC_TU_DONG_SECRET="), 1)

    def test_tu_dong_up_starts_only_node_red_then_syncs(self) -> None:
        env, docker, moc, out = self.run_make("tu-dong-up", "MOC_PUBLIC_URL=https://x\nMOC_EXTRA_PROFILES=\n")
        self.assertRegex(env, r"\nMOC_TU_DONG_SECRET=[0-9a-f]{48}\n")
        self.assertEqual(docker, "compose --profile core --profile app --profile tu-dong up -d --build --wait tu-dong")
        self.assertEqual(moc, "tu-dong sync\n")
        self.assertIn("MOC_EXTRA_PROFILES", out)                # nhắc cách bật lâu dài


if __name__ == "__main__":
    unittest.main()
