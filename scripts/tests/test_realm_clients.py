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

"""scripts/realm_clients.py và lệnh `moc realm clients`: thay biến trong moc-realm.json như Keycloak, chỉ chọn client
của ứng dụng trên trình duyệt, chỉ thêm client còn thiếu, chạy lại không tạo trùng. Keycloak giả, không cần Docker,
không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import copy
import importlib
import io
import json
import pathlib
import sys
import types
import unittest
import urllib.parse
import uuid
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8180/admin/realms/moc"
ENV = {"MOC_PUBLIC_URL": "https://signet.example"}

tenants: Any = None
realm_clients: Any = None
moc: Any = None
_saved: dict[str, Any] = {}


class FakeHTTPError(Exception):
    def __init__(self, status: int, body: str = ""):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp: thay bằng bản giả có đúng biến tệp realm cần."""
    global tenants, realm_clients, moc
    for name in ("moc_env", "moc", "backup", "tenants", "realm_clients"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ENV = dict(ENV)
    stub.ROOT = SCRIPTS.parent
    stub.REALM = "moc"
    stub.KEYCLOAK_ADMIN_URL = "http://127.0.0.1:8180"
    stub.PUBLIC_URL = ENV["MOC_PUBLIC_URL"]
    stub.HTTPError = FakeHTTPError

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng")

    stub.call_json = no_network
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    tenants = importlib.import_module("tenants")
    realm_clients = importlib.import_module("realm_clients")
    moc = importlib.import_module("moc")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


class FakeKeycloak:
    """GET, POST /clients của Keycloak 26 (phân trang first/max, 409 khi trùng clientId); ghi lại mọi lần gọi."""

    def __init__(self, *client_ids: str, status: int | None = None):
        self.clients = [{"id": str(uuid.uuid4()), "clientId": c} for c in client_ids]
        self.calls: list[tuple[str, str, Any]] = []
        self.status = status

    def writes(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p, _ in self.calls if m != "GET"]

    def __call__(self, method: str, url: str, body: Any = None, *, headers: dict[str, str] | None = None,
                 form: Any = None) -> tuple[Any, dict[str, str]]:
        assert url.startswith(BASE), url
        assert headers and headers["Authorization"] == "Bearer tok"
        parts = urllib.parse.urlsplit(url)
        path, q = parts.path[len("/admin/realms/moc"):], dict(urllib.parse.parse_qsl(parts.query))
        self.calls.append((method, path, copy.deepcopy(body)))
        if self.status:
            raise FakeHTTPError(self.status, json.dumps({"error": "HTTP 403 Forbidden"}))
        if path == "/clients" and method == "GET":
            start = int(q.get("first", 0))
            return copy.deepcopy(self.clients[start:start + int(q.get("max", 10))]), {}
        if path == "/clients" and method == "POST":
            if any(c["clientId"] == body["clientId"] for c in self.clients):
                raise FakeHTTPError(409, json.dumps({"errorMessage": "Client app-ca-nhan already exists"}))
            cid = str(uuid.uuid4())
            self.clients.append({**copy.deepcopy(body), "id": cid})
            return None, {"Location": f"{BASE}/clients/{cid}"}
        raise AssertionError(f"chưa giả lập: {method} {url}")


# Client Keycloak tự có trong mọi realm, cộng các client của tệp realm
BUILT_IN = ("account", "account-console", "admin-cli", "broker", "realm-management", "security-admin-console")


def client(kc: FakeKeycloak) -> Any:
    return tenants.Keycloak("http://127.0.0.1:8180", "moc", "tok", call=kc, http_error=FakeHTTPError)


def run_moc(kc: FakeKeycloak, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(tenants, "connect", return_value=client(kc)), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = moc.main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def realm_file(env: dict[str, str] | None = None) -> dict[str, Any]:
    return realm_clients.realm_from_text(realm_clients.REALM_FILE.read_text(encoding="utf-8"),
                                         ENV if env is None else env)


class SubstituteTest(unittest.TestCase):
    def test_env_default_and_escaping(self) -> None:
        text = '{"a": "${X}/p", "b": ${FLAG:true}, "c": "${MISSING}", "d": "${Y:mặc định}"}'
        got = realm_clients.realm_from_text(text, {"X": 'https://h"\\', "Y": "có"})
        self.assertEqual(got, {"a": 'https://h"\\/p', "b": True, "c": "${MISSING}", "d": "có"})
        self.assertEqual(realm_clients.realm_from_text(text, {"X": "u"})["d"], "mặc định")

    def test_realm_file_parses(self) -> None:
        # tệp thật có ${MOC_CLI_CLIENT_ENABLED:true} không nằm trong chuỗi: chỉ đọc được sau khi thay
        with self.assertRaises(json.JSONDecodeError):
            json.loads(realm_clients.REALM_FILE.read_text(encoding="utf-8"))
        self.assertEqual(realm_file()["realm"], "moc")


class SelectTest(unittest.TestCase):
    def test_only_browser_apps(self) -> None:
        apps = {c["clientId"]: c for c in realm_clients.browser_apps(realm_file())}
        self.assertEqual(set(apps), {"app-office", "app-ca-nhan"})
        self.assertEqual(apps["app-ca-nhan"]["redirectUris"], ["https://signet.example/ca-nhan/*"])
        self.assertEqual(apps["app-ca-nhan"]["attributes"]["pkce.code.challenge.method"], "S256")

    def test_cli_and_service_clients_excluded(self) -> None:
        rest = {c["clientId"]: c for c in realm_file()["clients"]}
        self.assertFalse(realm_clients.browser_app(rest["moc-cli"]))        # luồng mật khẩu
        self.assertFalse(realm_clients.browser_app(rest["svc-workflow"]))   # client bí mật, tài khoản dịch vụ
        implicit = {"clientId": "x", "publicClient": True, "implicitFlowEnabled": True}
        self.assertFalse(realm_clients.browser_app(implicit))

    def test_missing_public_url_refused(self) -> None:
        with self.assertRaisesRegex(tenants.TenantError, "MOC_PUBLIC_URL"):
            realm_clients.browser_apps(realm_file({}))


class SyncTest(unittest.TestCase):
    def test_adds_only_missing_app(self) -> None:
        # bản cài dựng trước khi có app-ca-nhan
        kc = FakeKeycloak(*BUILT_IN, "app-office", "moc-cli", "svc-workflow")
        result = realm_clients.sync(client(kc), realm_file())
        self.assertEqual(result, {"present": ["app-office"], "created": ["app-ca-nhan"]})
        self.assertEqual(kc.writes(), [("POST", "/clients")])
        sent = kc.calls[-1][2]
        want = next(c for c in realm_file()["clients"] if c["clientId"] == "app-ca-nhan")
        self.assertEqual(sent, want)   # đúng như tệp realm: mapper claim Hasura, PKCE, địa chỉ chuyển hướng
        self.assertEqual({m["name"] for m in sent["protocolMappers"]},
                         {m["name"] for m in next(c for c in realm_file()["clients"]
                                                  if c["clientId"] == "app-office")["protocolMappers"]})
        # chạy lại: không tạo trùng, không sửa gì
        again = realm_clients.sync(client(kc), realm_file())
        self.assertEqual(again, {"present": ["app-office", "app-ca-nhan"], "created": []})
        self.assertEqual(kc.writes(), [("POST", "/clients")])

    def test_never_recreates_removed_cli_or_service_client(self) -> None:
        kc = FakeKeycloak(*BUILT_IN, "app-office", "app-ca-nhan")   # quản trị đã gỡ moc-cli, svc-workflow
        self.assertEqual(realm_clients.sync(client(kc), realm_file())["created"], [])
        self.assertEqual(kc.writes(), [])

    def test_paging(self) -> None:
        kc = FakeKeycloak(*(f"c{i}" for i in range(tenants.PAGE * 2 + 3)), "app-office", "app-ca-nhan")
        self.assertEqual(realm_clients.sync(client(kc), realm_file())["created"], [])


class CommandTest(unittest.TestCase):
    def test_dry_run_json(self) -> None:
        kc = FakeKeycloak(*BUILT_IN, "app-office")
        code, out, _ = run_moc(kc, "realm", "clients", "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"present": ["app-office"], "created": ["app-ca-nhan"], "dry_run": True})
        self.assertEqual(kc.writes(), [])

    def test_text(self) -> None:
        kc = FakeKeycloak(*BUILT_IN, "app-office")
        code, out, _ = run_moc(kc, "realm", "clients")
        self.assertEqual(code, 0)
        self.assertIn("vừa thêm app-ca-nhan; đã có app-office", out)
        code, out, _ = run_moc(kc, "realm", "clients")
        self.assertIn("app-office, app-ca-nhan — đã có đủ", out)

    def test_refused_and_unavailable(self) -> None:
        code, _, err = run_moc(FakeKeycloak(status=403), "realm", "clients")
        self.assertEqual(code, 1)
        self.assertIn("403", err)

        def down(*args: Any, **kwargs: Any) -> Any:
            raise ConnectionRefusedError(111, "Connection refused")

        code, _, err = run_moc(down, "realm", "clients")   # type: ignore[arg-type]
        self.assertEqual(code, 2)
        self.assertIn("make ps", err)


if __name__ == "__main__":
    unittest.main()
