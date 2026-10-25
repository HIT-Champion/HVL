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

"""Cách ly mạng ứng dụng khỏi lõi: container ứng dụng (app-office, app-ca-nhan, ứng dụng cài bằng `moc app install`)
chỉ ở mạng `apps` (internal), nơi chỉ có APISIX — tới lõi duy nhất qua cổng. Hasura giao sự kiện tới ứng dụng qua cổng
hook 9081 của APISIX: có trong node_listen, không publish, route hook chỉ khớp ở cổng đó. Kiểm chữ docker-compose.yml,
platform/apisix/config.yaml và tệp do scripts/ung_dung.py sinh (không có PyYAML, không cần Docker, không đọc .env).
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib
import pathlib
import re
import sys
import types
import unittest
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "tests"))

from test_duong_ham import service_block  # noqa: E402

COMPOSE = ROOT / "docker-compose.yml"
CONFIG = ROOT / "platform" / "apisix" / "config.yaml"
APP = ROOT / "apps" / "bang-tin" / "app.yaml"
APPS_NET = {"apisix", "app-office", "app-ca-nhan"}        # đúng các service của docker-compose.yml ở mạng apps
CORE_HOSTS = ("keycloak", "hasura", "postgres", "svc-files", "svc-workflow", "openbao", "seaweedfs", "centrifugo",
              "meilisearch", "flowable", "clamav", "ollama", "scorpio")

u: Any = None
_saved: dict[str, Any] = {}


def setUpModule() -> None:
    """Như test_ung_dung: moc_env thật đọc .env lúc nạp — thay bằng bản giả, không gọi mạng."""
    global u
    for name in ("moc_env", "tenants", "realm_clients", "ung_dung", "yaml_nho"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ENV = {"MOC_PUBLIC_URL": "https://signet.example"}
    stub.ROOT = ROOT
    stub.REALM = "moc"
    stub.KEYCLOAK_ADMIN_URL = "http://127.0.0.1:8180"
    stub.PUBLIC_URL = "https://signet.example"

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng")

    stub.call_json = no_network
    stub.HTTPError = type("HTTPError", (Exception,), {})
    sys.modules["moc_env"] = stub
    u = importlib.import_module("ung_dung")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def without_comments(text: str) -> str:
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())


def compose_lines() -> list[str]:
    return COMPOSE.read_text(encoding="utf-8").splitlines()


def service_names() -> list[str]:
    lines = compose_lines()
    start, end = lines.index("services:"), lines.index("networks:")
    return [m.group(1) for ln in lines[start + 1:end] if (m := re.match(r"  ([a-z0-9-]+):$", ln))]


def networks_of(block: str) -> list[str] | None:
    """Giá trị `networks:` của một khối dịch vụ (dạng [a, b]); None: không khai — kế thừa x-common hoặc không mạng."""
    text = without_comments(block)
    if re.search(r"^ {4}networks:\s*$", text, re.M):
        raise AssertionError("networks dạng khối: test chỉ đọc dạng [a, b] — viết lại dạng đó")
    m = re.search(r"^ {4}networks: \[([^\]]*)\]\s*$", text, re.M)
    return [x.strip() for x in m.group(1).split(",") if x.strip()] if m else None


def effective_networks(name: str) -> list[str]:
    block = service_block(name)
    own = networks_of(block)
    if own is not None:
        return own
    if "network_mode:" in without_comments(block):
        return []
    common = "\n".join(compose_lines()[compose_lines().index("x-common: &common"):])
    common = common[:common.index("\n\n")]
    self_common = re.search(r"^  networks: \[([^\]]*)\]$", common, re.M)
    assert self_common and "<<: *common" in block, f"{name}: không rõ mạng"
    return [x.strip() for x in self_common.group(1).split(",")]


def network_settings(name: str) -> list[str]:
    lines = compose_lines()
    i = lines.index(f"  {name}:", lines.index("networks:"))
    out = []
    for line in lines[i + 1:]:
        if not line.startswith("    "):
            break
        out.append(line.strip())
    return out


def list_items(block: str, key: str) -> list[str]:
    lines = without_comments(block).splitlines()
    start = next(i for i, x in enumerate(lines) if x.strip() == f"{key}:")
    items = []
    for line in lines[start + 1:]:
        if not line.lstrip().startswith("- "):
            break
        items.append(line.strip()[2:].strip())
    return items


def node_listen() -> list[int]:
    lines = without_comments(CONFIG.read_text(encoding="utf-8")).splitlines()
    i = lines.index("  node_listen:")
    ports = []
    for line in lines[i + 1:]:
        m = re.match(r"^ {4}- (\d+)\s*$", line)
        if not m:
            break
        ports.append(int(m.group(1)))
    return ports


def blocks(text: str, section: str) -> dict[str, str]:
    """id → khối của từng mục trong `upstreams:` hoặc `routes:` (tệp chạy của APISIX)."""
    body = text[text.index(f"\n{section}:\n") + len(section) + 2:]
    body = body[:m.start()] if (m := re.search(r"^[A-Za-z_]", body, re.M)) else body
    return {m.group(1): m.group(0) for m in re.finditer(r"^  - id: (\S+)\n(?:(?: {4}.*)?\n)*", body, re.M)}


def record(**changes: Any) -> dict[str, Any]:
    rec = u.load_manifest(APP, root=ROOT)
    rec["image"] = "moc/app-bang-tin:1.0.0-abcdefabcdef"
    rec.update(changes)
    return rec


class ComposeNetworks(unittest.TestCase):
    def test_apps_only_on_apps_network(self) -> None:
        for name in ("app-office", "app-ca-nhan"):
            self.assertEqual(networks_of(service_block(name)), ["apps"], name)    # ghi đè x-common (mạng moc)
            self.assertNotIn("ports:", service_block(name), name)

    def test_gateway_on_core_and_apps_networks(self) -> None:
        self.assertEqual(networks_of(service_block("apisix")), ["moc", "apps"])

    def test_apps_network_is_internal(self) -> None:
        self.assertEqual(network_settings("apps"), ["driver: bridge", "internal: true"])

    def test_no_other_service_joins_apps(self) -> None:
        names = service_names()
        self.assertLessEqual(APPS_NET, set(names))
        on_apps = {n for n in names if "apps" in effective_networks(n)}
        self.assertEqual(on_apps, APPS_NET)
        self.assertEqual(effective_networks("hasura"), ["moc"])        # Hasura gọi ứng dụng chỉ qua cổng hook
        for name in APPS_NET - {"apisix"}:
            self.assertNotIn("moc", effective_networks(name), name)
        logs = without_comments((ROOT / "platform" / "logs" / "docker-compose.logs.yml").read_text(encoding="utf-8"))
        self.assertNotIn("networks", logs)                              # tệp phủ log không nối mạng nào


class HookListener(unittest.TestCase):
    def test_hook_port_listened_but_not_published(self) -> None:
        listen = node_listen()
        self.assertEqual(listen, [9080, u.HOOK_PORT])
        self.assertEqual(u.HOOK_URL, f"http://apisix:{u.HOOK_PORT}")
        self.assertEqual(u.GATEWAY_URL, f"http://apisix:{listen[0]}")
        ports = list_items(service_block("apisix"), "ports")
        self.assertEqual(ports, ["${MOC_HTTP_PORT:-8080}:9080"])         # chỉ cổng công khai
        self.assertFalse(any(str(u.HOOK_PORT) in p for p in ports))

    def test_hook_routes_only_match_on_hook_listener(self) -> None:
        rec = record()
        core = (ROOT / u.CORE_GATEWAY).read_text(encoding="utf-8")
        text = u.gateway_text(core, [rec])
        routes, upstreams = blocks(text, "routes"), blocks(text, "upstreams")
        hook = u.hook_id("bang-tin")
        self.assertEqual(upstreams[hook].splitlines()[1:], ["    type: roundrobin", "    nodes:",
                                                             f'      "app-bang-tin:{rec["events"]["port"]}": 1'])
        self.assertEqual(routes[hook].rstrip("\n").splitlines()[1:], [
            "    uri: /su-kien/bang-tin",                                      # đúng một đường, không *
            "    methods: [POST]",
            f'    vars: [["server_port", "==", "{u.HOOK_PORT}"]]',            # cổng công khai 9080 không khớp
            f"    upstream_id: {hook}",
            "    plugins:", "      proxy-rewrite:",
            f'        uri: "{rec["events"]["path"]}"'])                       # viết lại về đúng webhook của manifest
        # chỉ route hook tới cổng webhook; mọi route khác (lõi, trang) không có vars cổng và không trỏ upstream này
        self.assertEqual([i for i, b in routes.items() if f"upstream_id: {hook}\n" in b], [hook])
        self.assertEqual([i for i, b in routes.items() if "server_port" in b], [hook])
        self.assertNotIn(str(rec["events"]["port"]), upstreams["app-bang-tin"])
        # ở cổng công khai, POST /su-kien/<tên> không khớp route nào của lõi (404); đường giữ chỗ, ứng dụng không lấy
        self.assertIn(u.HOOK_PREFIX, u.RESERVED_PATHS)
        for rid, b in blocks(core, "routes").items():
            uris = re.findall(r'"(/[^"]*)"', b) + re.findall(r"^ {4}uri: (\S+)$", b, re.M)
            uris += re.findall(r"^ {6}- (/\S+)$", b, re.M)
            hit = [p for p in uris if p == "/su-kien/bang-tin" or (p.endswith("/*") and
                                                                   "/su-kien/bang-tin".startswith(p[:-1]))]
            if hit:
                self.assertRegex(b, r"\n {4}methods: \[GET, HEAD\]\n", rid)

    def test_event_trigger_goes_through_hook_listener(self) -> None:
        trigger = u.event_trigger(record())
        self.assertEqual(trigger["webhook"], f"{u.HOOK_URL}{u.hook_uri('bang-tin')}")
        self.assertEqual(trigger["headers"], [{"name": "X-Moc-Hook-Secret", "value_from_env": "MOC_APP_HOOK_BANG_TIN"}])


class GeneratedOverlay(unittest.TestCase):
    def test_installed_app_only_on_apps_and_calls_core_through_gateway(self) -> None:
        services = u.overlay([record()])["services"]
        app = services["app-bang-tin"]
        self.assertEqual(app["networks"], ["apps"])
        self.assertNotIn("ports", app)
        env = app["environment"]
        self.assertEqual(env["MOC_KEYCLOAK_INTERNAL_URL"], "http://apisix:9080")
        self.assertEqual(env["MOC_GRAPHQL_INTERNAL_URL"], "http://apisix:9080/v1/graphql")
        for key, value in env.items():
            if "://" in str(value):
                self.assertRegex(value, r"^http://apisix:9080(/|$)", key)
            for host in CORE_HOSTS:
                self.assertNotIn(f"{host}:", str(value), key)
        # tệp phủ không đổi mạng của lõi: apisix, hasura giữ mạng trong docker-compose.yml
        self.assertNotIn("networks", services["apisix"])
        self.assertNotIn("networks", services["hasura"])


if __name__ == "__main__":
    unittest.main()
