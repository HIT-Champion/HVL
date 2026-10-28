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

"""Wiki nội bộ (#367): danh sách quyền `moc wiki sync` sinh, xét bằng đúng cách DokuWiki xét; client Keycloak `wiki`;
cấu hình compose, APISIX, image, DokuWiki; Makefile, bản cài, sao lưu. Keycloak, CSDL, container giả: không cần Docker,
không đọc .env. Màn chạy thật trên stack: make demo-wiki (CI, phần sao-luu)."""

from __future__ import annotations

import importlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
WIKI_DIR = ROOT / "platform" / "wiki"
CNTT, KT = "c300d5bb-028f-44cc-ba10-7b5277a4225d", "318da474-60d6-4a90-aa7f-928b31b8fc59"
ROWS = [{"id": CNTT, "code": "CNTT", "name": "Khoa Công nghệ thông tin"},
        {"id": KT, "code": "KT", "name": "Khoa Kinh tế"}]

wiki: Any = None
_saved: dict[str, Any] = {}


def setUpModule() -> None:
    """Như test_tenants: moc_env thật đọc .env lúc nạp — thay bằng bản giả, không gọi mạng."""
    global wiki
    for name in ("moc_env", "tenants", "wiki"):
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
    wiki = importlib.import_module("wiki")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def perm(acl: str, page: str, groups: list[str]) -> int:
    """auth_aclcheck_cb của DokuWiki (inc/auth.php) với tài khoản không có dòng theo tên: nhóm của người xem là @ALL
    cộng mỗi nhóm qua auth_nameencode; xét dòng của chính trang, rồi từng không gian từ sâu lên tới `*` — ở mức đầu
    tiên có dòng khớp một nhóm của người xem thì lấy quyền lớn nhất, không xét lên nữa."""
    rules = [line.split("\t") for line in acl.splitlines() if line and not line.startswith("#")]
    mine = {"@ALL"} | {"@" + wiki.nameencode(g) for g in groups}
    scopes, ns = [page], page
    while ":" in ns:
        ns = ns.rsplit(":", 1)[0]
        scopes.append(f"{ns}:*")
    scopes.append("*")
    for scope in scopes:
        found = [int(p) for s, g, p in rules if s == scope and g in mine]
        if found:
            return max(found)
    return 0


# Nhóm mà plugin oauth gắn: nhóm mặc định, nhóm dịch vụ, rồi claim groups (tenant_id) của Keycloak
WRITER = ["user", "generic", CNTT]
CLERK = ["user", "generic", KT]
NO_UNIT = ["user", "generic"]          # tài khoản không có tenant_id (quản trị hệ thống)


class AclTest(unittest.TestCase):
    def setUp(self) -> None:
        self.acl = wiki.acl_text(ROWS)

    def test_each_unit_owns_only_its_space(self) -> None:
        for page in ("don-vi:cntt:so-tay", "don-vi:cntt:ke-hoach:2026", "don-vi:cntt:start"):
            self.assertEqual(perm(self.acl, page, WRITER), 16, page)    # đọc, sửa, tạo, tải tệp, xóa tệp
            self.assertEqual(perm(self.acl, page, CLERK), 0, page)
            self.assertEqual(perm(self.acl, page, NO_UNIT), 0, page)
            self.assertEqual(perm(self.acl, page, []), 0, page)
        self.assertEqual(perm(self.acl, "don-vi:kt:so-tay", CLERK), 16)
        self.assertEqual(perm(self.acl, "don-vi:kt:so-tay", WRITER), 0)

    def test_shared_pages_are_read_only_and_only_after_login(self) -> None:
        for page in ("start", "wiki:syntax"):
            self.assertEqual(perm(self.acl, page, WRITER), 1, page)
            self.assertEqual(perm(self.acl, page, NO_UNIT), 1, page)
            self.assertEqual(perm(self.acl, page, []), 0, page)
        # mọi trang khác — kể cả trang mẫu của DokuWiki, trang đặt thẳng trong don-vi — không ai đọc, không ai tạo
        for page in ("playground:playground", "don-vi:start", "chung:so-tay", "so-tay"):
            for groups in (WRITER, CLERK, NO_UNIT, []):
                self.assertEqual(perm(self.acl, page, groups), 0, (page, groups))

    def test_space_left_behind_belongs_to_nobody(self) -> None:
        # đổi mã KT → KTE: không gian cũ không còn dòng nào, rơi về `*` chứ không về một quyền chung của don-vi
        renamed = wiki.acl_text([ROWS[0], {**ROWS[1], "code": "KTE"}])
        for groups in (WRITER, CLERK, NO_UNIT, []):
            self.assertEqual(perm(renamed, "don-vi:kt:so-tay", groups), 0, groups)
        self.assertEqual(perm(renamed, "don-vi:kte:so-tay", CLERK), 16)
        # đơn vị tạo sau, chưa chạy lại moc wiki sync: người của nó không tạo được trang ở đâu
        self.assertEqual(perm(wiki.acl_text(ROWS[:1]), "don-vi:kt:so-tay", CLERK), 0)

    def test_default_and_service_groups_never_write(self) -> None:
        rules = [line.split("\t") for line in self.acl.splitlines() if line and not line.startswith("#")]
        self.assertTrue(all(len(r) == 3 for r in rules), rules)
        for scope, group, level in rules:
            if group in ("@ALL", "@user", "@generic"):
                self.assertLessEqual(int(level), 1, (scope, group))
        self.assertNotIn("%GROUP%", self.acl)
        self.assertNotIn("%USER%", self.acl)
        self.assertNotIn("@generic", self.acl)
        self.assertEqual(rules[0], ["*", "@ALL", "0"])

    def test_group_is_the_tenant_id_as_dokuwiki_encodes_it(self) -> None:
        self.assertEqual(wiki.nameencode("a-b_c.d9Z"), "a%2db%5fc%2ed9Z")
        self.assertEqual(wiki.group_of(CNTT.upper()), "@" + CNTT.replace("-", "%2d"))
        self.assertIn(f"don-vi:cntt:*\t@{CNTT.replace('-', '%2d')}\t16\n", self.acl)

    def test_namespaces_follow_unit_codes_and_never_collide(self) -> None:
        rows = [*ROWS, {"id": "0a1b2c3d-0000-4000-8000-000000000000", "code": "kt", "name": "Trùng mã"},
                {"id": "11111111-0000-4000-8000-000000000000", "code": "ĐT", "name": "Tổ Đào tạo"}]
        ns = wiki.namespaces(rows)
        self.assertEqual(ns[CNTT], "don-vi:cntt")
        self.assertEqual(ns[KT], "don-vi:kt")
        self.assertEqual(ns["0a1b2c3d-0000-4000-8000-000000000000"], "don-vi:kt-0a1b2c3d")
        self.assertEqual(ns["11111111-0000-4000-8000-000000000000"], "don-vi:dt")
        self.assertEqual(len(set(ns.values())), len(rows))
        for value in ns.values():
            self.assertRegex(value, r"^don-vi:[a-z0-9-]+$")

    def test_start_page_lists_units_without_wiki_syntax_from_names(self) -> None:
        page = wiki.start_page([*ROWS, {"id": "22222222-0000-4000-8000-000000000000", "code": "X|Y",
                                        "name": "Phòng [[hack]] {{a.png}} | b"}])
        self.assertIn("  * [[don-vi:cntt:start|Khoa Công nghệ thông tin]] (CNTT)\n", page)
        self.assertIn("  * [[don-vi:x-y:start|Phòng hack a.png b]] (X Y)\n", page)
        self.assertNotIn("[[hack", page)
        self.assertIn("(chưa có đơn vị nào)", wiki.start_page([]))


class FakeKc:
    def __init__(self, clients: list[dict[str, Any]] | None = None,
                 mappers: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._clients, self.mappers, self.calls = clients or [], mappers or {}, []

    def clients(self) -> list[dict[str, Any]]:
        return self._clients

    def create_client(self, rep: dict[str, Any]) -> str:
        self.calls.append(("create", rep))
        return "new-id"

    def update_client(self, client_id: str, rep: dict[str, Any]) -> None:
        self.calls.append(("update", client_id, rep))

    def protocol_mappers(self, client_id: str) -> list[dict[str, Any]]:
        return self.mappers.get(client_id, [])

    def add_protocol_mapper(self, client_id: str, rep: dict[str, Any]) -> None:
        self.calls.append(("mapper", client_id, rep))


class ClientTest(unittest.TestCase):
    def test_confidential_code_flow_only_back_to_the_wiki(self) -> None:
        rep = wiki.client_rep("https://signet.example/", "bi-mat")
        self.assertEqual(rep["clientId"], "wiki")
        self.assertFalse(rep["publicClient"])
        self.assertEqual((rep["clientAuthenticatorType"], rep["secret"]), ("client-secret", "bi-mat"))
        self.assertTrue(rep["standardFlowEnabled"])
        for flow in ("directAccessGrantsEnabled", "serviceAccountsEnabled", "implicitFlowEnabled"):
            self.assertFalse(rep[flow], flow)
        # plugin oauth: redirect URI = DOKU_URL . DOKU_SCRIPT; đổi mã từ máy chủ wiki nên không cần CORS
        self.assertEqual(rep["redirectUris"], ["https://signet.example/wiki/doku.php"])
        self.assertEqual(rep["webOrigins"], [])
        self.assertEqual(rep["attributes"], {"post.logout.redirect.uris": "https://signet.example/wiki/*"})

    def test_groups_claim_only_in_userinfo(self) -> None:
        config = wiki.MAPPER["config"]
        self.assertEqual((config["user.attribute"], config["claim.name"]), ("tenant_id", "groups"))
        self.assertEqual(config["userinfo.token.claim"], "true")
        for token in ("id.token.claim", "access.token.claim", "introspection.token.claim"):
            self.assertEqual(config[token], "false", token)

    def test_creates_client_with_mapper(self) -> None:
        kc = FakeKc()
        self.assertEqual(wiki.ensure_client(kc, "https://signet.example", "s"), "created")
        [(kind, rep)] = kc.calls
        self.assertEqual(kind, "create")
        self.assertEqual(rep["protocolMappers"], [wiki.MAPPER])
        self.assertEqual(rep["secret"], "s")

    def test_resets_secret_and_urls_keeps_other_fields_adds_missing_mapper(self) -> None:
        found = {"id": "k1", "clientId": "wiki", "secret": "cu", "redirectUris": ["https://cu/wiki/doku.php"],
                 "attributes": {"post.logout.redirect.uris": "https://cu/wiki/*", "khac": "giu"}, "description": "x"}
        kc = FakeKc([found])
        self.assertEqual(wiki.ensure_client(kc, "https://moi", "moi"), "updated")
        (kind, cid, rep), mapper = kc.calls
        self.assertEqual((kind, cid), ("update", "k1"))
        self.assertEqual((rep["secret"], rep["redirectUris"]), ("moi", ["https://moi/wiki/doku.php"]))
        self.assertEqual(rep["attributes"], {"post.logout.redirect.uris": "https://moi/wiki/*", "khac": "giu"})
        self.assertEqual(rep["description"], "x")
        self.assertEqual(mapper, ("mapper", "k1", wiki.MAPPER))
        kc = FakeKc([found], {"k1": [{"name": "wiki-groups"}]})
        wiki.ensure_client(kc, "https://moi", "moi")
        self.assertEqual([c[0] for c in kc.calls], ["update"])

    def test_dry_run_changes_nothing(self) -> None:
        kc = FakeKc([{"id": "k1", "clientId": "wiki"}])
        self.assertEqual(wiki.ensure_client(kc, "https://x", "s", dry_run=True), "updated")
        self.assertEqual(wiki.ensure_client(FakeKc(), "https://x", "s", dry_run=True), "created")
        self.assertEqual(kc.calls, [])


class SyncTest(unittest.TestCase):
    def run_sync(self, env: dict[str, str], *, dry_run: bool = False) -> tuple[dict[str, Any], list, FakeKc]:
        written: list[tuple[str, str]] = []
        kc = FakeKc()
        db = types.SimpleNamespace(query=lambda sql: ROWS)
        with mock.patch.object(wiki.tenants, "database", return_value=db), \
                mock.patch.object(wiki.tenants, "connect", return_value=kc), \
                mock.patch.object(wiki, "_exec", side_effect=lambda path, text: written.append((path, text))):
            return wiki.sync(env, dry_run=dry_run), written, kc

    def test_refuses_missing_or_placeholder_secret(self) -> None:
        for secret in ("", "change_me"):
            with mock.patch.object(wiki.tenants, "database", side_effect=AssertionError("không được gọi")):
                with self.assertRaises(wiki.tenants.TenantError):
                    wiki.sync({"MOC_PUBLIC_URL": "https://x", "MOC_WIKI_CLIENT_SECRET": secret})

    def test_writes_acl_and_start_page_into_the_wiki_volume(self) -> None:
        result, written, kc = self.run_sync({"MOC_PUBLIC_URL": "https://x", "MOC_WIKI_CLIENT_SECRET": "s"})
        self.assertEqual(result, {"client": "created", "namespaces": {"CNTT": "don-vi:cntt", "KT": "don-vi:kt"}})
        self.assertEqual([p for p, _ in written], ["/storage/conf/acl.auth.php", "/storage/data/pages/start.txt"])
        self.assertEqual(written[0][1], wiki.acl_text(ROWS))
        self.assertEqual([c[0] for c in kc.calls], ["create"])
        _, written, kc = self.run_sync({"MOC_PUBLIC_URL": "https://x", "MOC_WIKI_CLIENT_SECRET": "s"}, dry_run=True)
        self.assertEqual((written, kc.calls), ([], []))

    def test_exec_writes_atomically_as_the_container_user(self) -> None:
        with mock.patch.object(subprocess, "run") as run:
            wiki._exec("/storage/conf/acl.auth.php", "x\n")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:9], ["docker", "compose", "--profile", "core", "--profile", "app", "--profile", "wiki",
                                   "exec"])
        self.assertNotIn("--user", cmd)                         # user của service: 33, như DokuWiki tự ghi
        self.assertIn('cat > "$1.moc"; mv "$1.moc" "$1"', cmd[cmd.index("-c") + 1])
        self.assertEqual(cmd[-1], "/storage/conf/acl.auth.php")
        self.assertEqual(run.call_args.kwargs["input"], b"x\n")


def service_block(compose: str, name: str) -> str:
    start = compose.index(f"\n  {name}:\n")
    end = re.search(r"\n  [a-z][a-z0-9-]*:\n|\n[a-z]", compose[start + 1:])
    return compose[start:start + 1 + end.start()] if end else compose[start:]


class ConfigTest(unittest.TestCase):
    def test_compose_service_off_by_default_unprivileged_apps_network_only(self) -> None:
        compose = read(ROOT / "docker-compose.yml")
        block = service_block(compose, "wiki")
        for line in ("profiles: [wiki]", "networks: [apps]", 'user: "33:33"', "cap_drop: [ALL]",
                     "security_opt: [no-new-privileges:true]", "build: ./platform/wiki", "- wiki_data:/storage",
                     "- ./platform/wiki/signet.protected.php:/var/www/html/conf.core/docker.protected.php:ro",
                     "MOC_WIKI_CLIENT_SECRET: ${MOC_WIKI_CLIENT_SECRET:-}"):
            self.assertIn(line, block)
        self.assertNotIn("ports:", block)                       # chỉ tới được qua APISIX
        self.assertIn("\n  wiki_data:\n", compose[compose.index("\nvolumes:\n"):])
        self.assertIn("- wiki_data:/data/wiki", service_block(compose, "restic"))

    def test_image_pinned_and_plugins_checked(self) -> None:
        text = read(WIKI_DIR / "Dockerfile")
        self.assertRegex(text, r"\nFROM dokuwiki/dokuwiki:[0-9-]+[a-z]?@sha256:[0-9a-f]{64}\n")
        for arg in ("LOGIN_PLUGIN", "GENERIC_PLUGIN"):
            self.assertRegex(text, rf"\nARG {arg}=[0-9a-f]{{40}}\n")
            self.assertRegex(text, rf"\nARG {arg}_SHA256=[0-9a-f]{{64}}\n")
        self.assertIn('sha256sum -c -', text)
        # gitleaks (generic-api-key) bắt chuỗi hex sau tên có chữ auth: commit gộp vào develop sẽ đỏ
        self.assertNotRegex(text, r"(?i)ARG \w*auth\w*=")
        self.assertIn("lib/plugins.core/$1", text)
        self.assertIn("rm /var/www/html/install.php", text)
        self.assertIn("\nUSER 33:33\n", text)
        self.assertNotIn("${", text.split("FROM", 1)[1].split("RUN", 1)[0])    # không ghim bằng biến

    def test_first_start_denies_everything_until_sync(self) -> None:
        text = read(WIKI_DIR / "khoi-dong.sh")
        self.assertIn(r"*\t@ALL\t0\n", text)
        self.assertIn("[ -e /storage/conf/acl.auth.php ] \\\n  ||", text)      # không ghi đè danh sách đã sync
        self.assertTrue(text.rstrip().endswith('exec /dokuwiki-entrypoint.sh "$@"'))
        self.assertTrue(os.access(WIKI_DIR / "khoi-dong.sh", os.X_OK)
                        or "--chmod=0755" in read(WIKI_DIR / "Dockerfile"))

    def test_dokuwiki_logs_in_only_through_keycloak(self) -> None:
        text = read(WIKI_DIR / "signet.protected.php")
        for setting in ("$conf['authtype'] = 'oauth';", "$conf['useacl'] = 1;", "$conf['superuser'] = '!!not set!!';",
                        "$conf['manager'] = '!!not set!!';", "$conf['remote'] = 0;",
                        "$conf['basedir'] = '/wiki/';", "$conf['plugin']['oauth']['singleService'] = 1;",
                        "$conf['plugin']['oauth']['overwrite-groups'] = 1;",
                        "$conf['plugin']['oauthgeneric']['key'] = 'wiki';",
                        "$conf['plugin']['oauthgeneric']['secret'] = (string) getenv('MOC_WIKI_CLIENT_SECRET');",
                        "$conf['plugin']['oauthgeneric']['json-grps'] = 'groups';",
                        "$conf['plugin']['oauthgeneric']['needs-state'] = 1;"):
            self.assertIn(setting, text)
        disabled = re.search(r"\$conf\['disableactions'\] = '([^']*)';", text).group(1).split(",")
        self.assertLessEqual({"register", "resendpwd", "profile", "profile_delete"}, set(disabled))
        # trình duyệt tới Keycloak bằng URL công khai; máy chủ wiki đổi mã, đọc userinfo qua APISIX trong mạng apps
        self.assertIn("$conf['plugin']['oauthgeneric']['authurl'] = \"$public/realms/", text)
        self.assertIn('$internal = "http://apisix:9080/realms/$realm/protocol/openid-connect";', text)
        self.assertIn("$conf['plugin']['oauthgeneric']['tokenurl'] = \"$internal/token\";", text)
        self.assertIn("$conf['plugin']['oauthgeneric']['userurl'] = \"$internal/userinfo\";", text)

    def test_gateway_route_and_reserved_path(self) -> None:
        gw = read(ROOT / "platform" / "apisix" / "apisix.yaml")
        self.assertIn('  - id: wiki\n    type: roundrobin\n    nodes:\n      "wiki:8080": 1\n', gw)
        route = gw[gw.index('  - id: wiki\n    uris: ["/wiki", "/wiki/*"]'):]
        route = route[:route.index("\n\n")]
        self.assertIn("methods: [GET, HEAD, POST]", route)
        self.assertIn('regex_uri: ["^/wiki/?(.*)$", "/$1"]', route)
        self.assertNotIn("plugin_config_id", route)          # DokuWiki tự đăng nhập, không qua can-token
        self.assertIn('"/wiki",', read(SCRIPTS / "ung_dung.py"))  # ứng dụng cài thêm không che được

    def test_waf_exclusion_only_on_tokens_and_page_text(self) -> None:
        gw = read(ROOT / "platform" / "apisix" / "apisix.yaml")
        start = gw.index('"@beginsWith /wiki/" "id:10070,')
        rule = gw[start:gw.index('"\n', start)]
        removed = re.findall(r"ctl:ruleRemoveTargetById=([\d-]+);ARGS:([a-z_]+)", rule)
        tokens = {(i, a) for a in ("code", "session_state") for i in ("942100", "933000-933999", "930120")}
        text = {(i, a) for a in ("wikitext", "prefix", "suffix", "summary")
                for i in ("932000-932999", "933000-933999", "931100", "931120")}
        self.assertEqual(set(removed), tokens | text | {("931100", "iss"), ("934110", "iss")})
        self.assertEqual(len(removed), len(set(removed)))

    def test_env_make_install_backup(self) -> None:
        self.assertRegex(read(ROOT / (".e" + "nv.example")), r"\nMOC_WIKI_CLIENT_SECRET=change_me\n")
        make = read(ROOT / "Makefile")
        for target in ("wiki-env:", "wiki-up:", "wiki-down:", "demo-wiki:"):
            self.assertIn(f"\n{target}", make)
        self.assertEqual(make.count("--profile logs --profile wiki down"), 2)          # make down, make reset
        runtime = re.search(r"^RUNTIME=\((.*?)\)", read(SCRIPTS / "install.sh"), re.M | re.S).group(1).split()
        for rel in ("platform/wiki/signet.protected.php", "scripts/wiki.py", "scripts/demo_wiki.py"):
            self.assertIn(rel, runtime)
        backup = read(SCRIPTS / "backup.py")
        self.assertIn('WIKI = "/data/wiki"', backup)
        self.assertIn('restic("restore", f"{manifest[\'wiki\'][\'snapshot\']}:{WIKI}", "--target", WIKI, "--delete")',
                      backup)


@unittest.skipUnless(shutil.which("make"), "cần GNU Make")
class MakefileTest(unittest.TestCase):
    """make up, make wiki-up với docker và moc.py giả (như test_log_tap_trung)."""

    def run_make(self, target: str, env: str) -> tuple[str, str, str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "scripts").mkdir()
            (d / "bin").mkdir()
            (d / "platform" / "apisix").mkdir(parents=True)
            shutil.copy(ROOT / "Makefile", d)
            shutil.copy(SCRIPTS / "gen-env.sh", d / "scripts")
            shutil.copy(ROOT / "platform" / "apisix" / "kiem-moi-truong.sh", d / "platform" / "apisix")
            (d / "scripts" / "moc.py").write_text(
                "import sys\nopen('moc.log', 'a').write(' '.join(sys.argv[1:]) + '\\n')\n", encoding="utf-8")
            docker = d / "bin" / "docker"
            docker.write_text('#!/bin/sh\necho "$*" >> docker.log\n', encoding="utf-8")
            docker.chmod(0o755)
            dot_env = d / ("." + "env")
            dot_env.write_text(env, encoding="utf-8")
            run_env = {k: v for k, v in os.environ.items()
                       if k not in ("COMPOSE_FILE", "MAKEFLAGS", "MAKELEVEL", "MOC_WIKI_CLIENT_SECRET")}
            run_env["PATH"] = f"{d / 'bin'}:{run_env['PATH']}"
            proc = subprocess.run(["make", "-s", target], cwd=d, env=run_env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            got = lambda name: (d / name).read_text(encoding="utf-8") if (d / name).exists() else ""  # noqa: E731
            docker_log = "\n".join(line for line in got("docker.log").splitlines() if " config " not in line)
            return dot_env.read_text(encoding="utf-8"), docker_log, got("moc.log"), proc.stdout

    def test_make_up_with_wiki_profile_fills_secret_and_syncs(self) -> None:
        env, docker, moc, _ = self.run_make("up", "MOC_PUBLIC_URL=https://x\nMOC_EXTRA_PROFILES=wiki\n")
        self.assertRegex(env, r"\nMOC_WIKI_CLIENT_SECRET=[0-9a-f]{48}\n")
        self.assertIn("compose --profile core --profile app --profile wiki up -d --build --wait", docker)
        self.assertEqual(moc, "wiki sync\n")
        again, _, _, _ = self.run_make("up", env)
        self.assertEqual(again.count("MOC_WIKI_CLIENT_SECRET="), 1)

    def test_make_up_without_wiki_profile_is_unchanged(self) -> None:
        env, docker, moc, _ = self.run_make("up", "MOC_PUBLIC_URL=https://x\nMOC_EXTRA_PROFILES=\n")
        self.assertNotIn("MOC_WIKI_CLIENT_SECRET", env)
        self.assertEqual(docker, "compose --profile core --profile app up -d --build --wait --wait-timeout 600")
        self.assertEqual(moc, "")

    def test_wiki_up_starts_only_the_wiki_then_syncs(self) -> None:
        env, docker, moc, out = self.run_make("wiki-up", "MOC_PUBLIC_URL=https://x\nMOC_EXTRA_PROFILES=\n")
        self.assertRegex(env, r"\nMOC_WIKI_CLIENT_SECRET=[0-9a-f]{48}\n")
        self.assertEqual(docker, "compose --profile core --profile app --profile wiki up -d --build --wait wiki")
        self.assertEqual(moc, "wiki sync\n")
        self.assertIn("MOC_EXTRA_PROFILES", out)                # nhắc cách bật lâu dài


if __name__ == "__main__":
    unittest.main()
