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

"""Theme đăng nhập Signet (platform/keycloak/themes/signet) và lệnh `moc realm theme`: realm dùng đúng thư mục theme,
theme chỉ có CSS, ảnh, phông kèm giấy phép, properties (không viết lại template FreeMarker của keycloak.v2), CSS không
tải gì từ ngoài, logo và phông trùng của Văn phòng điện tử, compose gắn thư mục chỉ đọc; lệnh chỉ đặt theme khi realm
còn dùng mặc định. Keycloak giả, không cần Docker, không đọc .env.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import copy
import importlib
import io
import json
import pathlib
import re
import sys
import types
import unittest
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
THEME = ROOT / "platform" / "keycloak" / "themes" / "signet"
LOGIN = THEME / "login"
SERVER = "http://127.0.0.1:8180/admin"
BASE = f"{SERVER}/realms/moc"
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
    """moc_env thật đọc .env lúc nạp: thay bằng bản giả có đúng biến tệp realm cần (như test_realm_clients.py)."""
    global tenants, realm_clients, moc
    for name in ("moc_env", "moc", "backup", "tenants", "realm_clients"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ENV = dict(ENV)
    stub.ROOT = ROOT
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


def properties(path: pathlib.Path) -> dict[str, str]:
    """Tệp .properties đơn giản như của theme: KHÓA=giá trị, bỏ dòng trống và chú thích #."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith(("#", "!")):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def realm_file() -> dict[str, Any]:
    return realm_clients.realm_from_text(realm_clients.REALM_FILE.read_text(encoding="utf-8"), ENV)


class ThemeFilesTest(unittest.TestCase):
    def test_realm_points_at_theme_folder(self) -> None:
        self.assertEqual(realm_file()["loginTheme"], THEME.name)
        self.assertTrue((LOGIN / "theme.properties").is_file())

    def test_extends_keycloak_v2_and_resources_exist(self) -> None:
        props = properties(LOGIN / "theme.properties")
        self.assertEqual(props["parent"], "keycloak.v2")
        styles = props["styles"].split()
        # CSS của theme cha đứng trước (Keycloak tìm css/styles.css lên tới keycloak.v2), CSS của Signet phủ sau
        self.assertEqual(styles[0], "css/styles.css")
        self.assertFalse((LOGIN / "resources" / styles[0]).exists())
        for rel in styles[1:] + props["favicons"].split():
            self.assertTrue((LOGIN / "resources" / rel).is_file(), rel)

    def test_only_css_images_fonts_and_properties(self) -> None:
        # không .ftl (template), không .js: chỉ đổi giao diện, luồng đăng nhập và mã của Keycloak giữ nguyên. Phông .ttf
        # đi kèm OFL.txt (giấy phép SIL OFL-1.1 buộc phát hành phông cùng giấy phép)
        files = [p for p in THEME.rglob("*") if p.is_file()]
        self.assertTrue(files)
        for path in files:
            if path.suffix == ".txt":
                self.assertEqual(path.name, "OFL.txt", path)
            else:
                self.assertIn(path.suffix, {".css", ".svg", ".png", ".ttf", ".properties"}, path)
        self.assertEqual({p.name for p in THEME.iterdir()}, {"login"})   # chỉ theme đăng nhập

    def test_fonts_are_the_office_fonts_with_licence(self) -> None:
        office = ROOT / "apps" / "office" / "public" / "fonts"
        fonts = sorted(LOGIN.rglob("*.ttf"))
        self.assertTrue(fonts)
        for font in fonts:
            self.assertTrue((font.parent / "OFL.txt").is_file(), font)
            same = office / font.relative_to(LOGIN / "resources" / "fonts")
            self.assertEqual(font.read_bytes(), same.read_bytes(), font)

    def test_css_loads_nothing_from_outside(self) -> None:
        for css in LOGIN.rglob("*.css"):
            text = re.sub(r"(?s)/\*.*?\*/", "", css.read_text(encoding="utf-8"))   # bỏ chú thích
            self.assertNotIn("@import", text, css)
            self.assertNotRegex(text, r"(?i)expression\(|javascript:", css)
            urls = re.findall(r"url\(\s*['\"]?([^'\")]+)", text)
            self.assertTrue(urls, css)
            for url in urls:
                self.assertNotRegex(url, r"^(?:[a-z]+:|//)", f"{css.name}: {url}")
                self.assertTrue((css.parent / url).resolve().is_file(), f"{css.name}: {url}")

    def test_logo_is_the_office_logo_and_has_no_script(self) -> None:
        logo = LOGIN / "resources" / properties(LOGIN / "theme.properties")["favicons"]
        self.assertEqual(logo.read_bytes(), (ROOT / "apps" / "office" / "public" / "favicon.svg").read_bytes())
        for svg in THEME.rglob("*.svg"):
            text = svg.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?i)<script|\son[a-z]+\s*=|href\s*=", svg)

    def test_compose_mounts_theme_read_only(self) -> None:
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        service = re.search(r"(?ms)^  keycloak:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n)", text)
        assert service is not None
        self.assertIn("- ./platform/keycloak/themes/signet:/opt/keycloak/themes/signet:ro\n", service.group(1))


class FakeKeycloak:
    """GET /admin/serverinfo (theme đăng nhập có trên máy chủ), GET, PUT realm của Keycloak 26; ghi lại mọi lần gọi.
    ignore_put: Keycloak trả 204 mà không đổi gì."""

    def __init__(self, realm: dict[str, Any], themes: tuple[str, ...] = ("base", "keycloak", "keycloak.v2", "signet"),
                 *, status: int | None = None, ignore_put: bool = False):
        self.rep = copy.deepcopy(realm)
        self.themes = themes
        self.status = status
        self.ignore_put = ignore_put
        self.calls: list[tuple[str, str, Any]] = []

    def writes(self) -> list[tuple[str, str, Any]]:
        return [c for c in self.calls if c[0] != "GET"]

    def __call__(self, method: str, url: str, body: Any = None, *, headers: dict[str, str] | None = None,
                 form: Any = None) -> tuple[Any, dict[str, str]]:
        assert headers and headers["Authorization"] == "Bearer tok"
        self.calls.append((method, url, copy.deepcopy(body)))
        if self.status:
            raise FakeHTTPError(self.status, json.dumps({"error": "HTTP 403 Forbidden"}))
        if url == f"{SERVER}/serverinfo" and method == "GET":
            return {"themes": {"login": [{"name": n, "locales": ["en", "vi"]} for n in self.themes],
                               "account": [{"name": "keycloak.v3"}]}}, {}
        if url == BASE and method == "GET":
            return copy.deepcopy(self.rep), {}
        if url == BASE and method == "PUT":
            if not self.ignore_put:
                self.rep = copy.deepcopy(body)
            return None, {}
        raise AssertionError(f"chưa giả lập: {method} {url}")


# realm nạp từ tệp trước khi có theme: không có loginTheme; các trường khác phải được gửi lại nguyên vẹn
OLD_REALM = {"id": "a1b2", "realm": "moc", "displayName": "Signet", "enabled": True, "organizationsEnabled": True,
             "internationalizationEnabled": True, "supportedLocales": ["vi", "en"], "defaultLocale": "vi",
             "oauth2DeviceCodeLifespan": 600, "attributes": {"cibaExpiresIn": "120"}}


def run_moc(kc: Any, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    client = tenants.Keycloak("http://127.0.0.1:8180", "moc", "tok", call=kc, http_error=FakeHTTPError)
    with mock.patch.object(tenants, "connect", return_value=client), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = moc.main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class RealmThemeTest(unittest.TestCase):
    def test_sets_theme_on_old_realm_sending_whole_realm(self) -> None:
        kc = FakeKeycloak(OLD_REALM)
        code, out, err = run_moc(kc, "realm", "theme")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("vừa đặt signet", out)
        self.assertEqual(kc.writes(), [("PUT", BASE, {**OLD_REALM, "loginTheme": "signet"})])
        # chạy lại: không ghi gì thêm
        code, out, _ = run_moc(kc, "realm", "theme")
        self.assertEqual(code, 0)
        self.assertIn("realm đã dùng signet", out)
        self.assertEqual(len(kc.writes()), 1)

    def test_empty_theme_counts_as_default(self) -> None:
        kc = FakeKeycloak({**OLD_REALM, "loginTheme": ""})
        self.assertEqual(run_moc(kc, "realm", "theme")[0], 0)
        self.assertEqual(kc.rep["loginTheme"], "signet")

    def test_dry_run_json_writes_nothing(self) -> None:
        kc = FakeKeycloak(OLD_REALM)
        code, out, _ = run_moc(kc, "realm", "theme", "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"theme": "signet", "current": "", "action": "set", "dry_run": True})
        self.assertEqual(kc.writes(), [])

    def test_keeps_theme_chosen_by_admin(self) -> None:
        kc = FakeKeycloak({**OLD_REALM, "loginTheme": "keycloak"})
        code, out, _ = run_moc(kc, "realm", "theme", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["action"], "kept")
        self.assertEqual(kc.writes(), [])
        self.assertIn("giữ nguyên", run_moc(kc, "realm", "theme")[1])

    def test_theme_folder_not_mounted(self) -> None:
        # container keycloak dựng từ compose cũ: máy chủ không có theme signet → không đặt, chỉ đường sửa
        kc = FakeKeycloak(OLD_REALM, themes=("base", "keycloak", "keycloak.v2"))
        code, _, err = run_moc(kc, "realm", "theme")
        self.assertEqual(code, 1)
        self.assertIn("docker compose up -d --wait keycloak", err)
        self.assertEqual(kc.writes(), [])
        self.assertEqual(kc.calls[0][1], f"{SERVER}/serverinfo")   # serverinfo nằm ngoài đường của realm

    def test_keycloak_ignores_update(self) -> None:
        code, _, err = run_moc(FakeKeycloak(OLD_REALM, ignore_put=True), "realm", "theme")
        self.assertEqual(code, 1)
        self.assertIn("không nhận loginTheme signet", err)

    def test_realm_file_without_theme_refused(self) -> None:
        with self.assertRaisesRegex(tenants.TenantError, "loginTheme"):
            realm_clients.sync_theme(None, {"realm": "moc"})

    def test_refused_and_unavailable(self) -> None:
        code, _, err = run_moc(FakeKeycloak(OLD_REALM, status=403), "realm", "theme")
        self.assertEqual(code, 1)
        self.assertIn("403", err)

        def down(*args: Any, **kwargs: Any) -> Any:
            raise ConnectionRefusedError(111, "Connection refused")

        code, _, err = run_moc(down, "realm", "theme")
        self.assertEqual(code, 2)
        self.assertIn("make ps", err)


if __name__ == "__main__":
    unittest.main()
