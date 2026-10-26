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

"""Phông Be Vietnam Pro lấy từ gói npm @fontsource/be-vietnam-pro lúc dựng, không nằm trong repo (#305, PoF #5):
  * cây mã nguồn không có tệp phông nào (.ttf, .otf, .woff, .woff2);
  * ba nơi dùng phông (Văn phòng điện tử, Không gian cá nhân, theme đăng nhập của Keycloak) ghim cùng một phiên bản
    chính xác của gói trong package.json và package-lock.json, tệp khóa ghi giấy phép OFL-1.1;
  * chỗ nạp CSS trỏ đúng tệp bước dựng tạo ra; theme đăng nhập: dịch vụ chạy một lần keycloak-fonts chép phông vào
    volume keycloak_fonts, keycloak gắn volume đè lên thư mục giữ chỗ của theme và chờ dịch vụ đó xong; lệnh chép thay
    bản cũ;
  * reconciler không chạy lại dịch vụ chạy một lần đã xong (không thì lượt nào cũng "chạy lại keycloak-fonts", hệ thống
    không bao giờ khớp khai báo), chạy lại khi nó thoát lỗi.
Không cần Docker, mạng hay node_modules. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
PACKAGE = "@fontsource/be-vietnam-pro"
FONT_DIRS = {"office": ROOT / "apps" / "office", "ca-nhan": ROOT / "apps" / "ca-nhan",
             "keycloak": ROOT / "platform" / "keycloak" / "fonts"}
FONTS_IMAGE = FONT_DIRS["keycloak"]
THEME_FONTS = "/opt/keycloak/themes/signet/login/resources/fonts/be-vietnam-pro"
SKIP_DIRS = {".git", "node_modules", ".nuxt", ".output", "dist", ".venv", "venv", "__pycache__", "test-results"}

spec = importlib.util.spec_from_file_location("reconcile_phong", SCRIPTS / "reconcile.py")
reconcile: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def service_block(name: str) -> str:
    text = read(ROOT / "docker-compose.yml")
    m = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|^[a-z])", text)
    assert m is not None, name
    return m.group(1)


class NoFontInRepoTest(unittest.TestCase):
    def test_source_tree_has_no_font_file(self) -> None:
        found = []
        for top, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            found += [os.path.join(top, f) for f in files if f.lower().endswith((".ttf", ".otf", ".woff", ".woff2"))]
        self.assertEqual(found, [])

    def test_same_exact_version_everywhere(self) -> None:
        versions = set()
        for name, folder in FONT_DIRS.items():
            wanted = json.loads(read(folder / "package.json"))["dependencies"][PACKAGE]
            self.assertRegex(wanted, r"^\d+\.\d+\.\d+$", name)                # ghim đúng một bản, không ^ hay ~
            lock = json.loads(read(folder / "package-lock.json"))
            self.assertEqual(lock["packages"][""]["dependencies"][PACKAGE], wanted, name)
            entry = lock["packages"][f"node_modules/{PACKAGE}"]
            self.assertEqual(entry["version"], wanted, name)
            self.assertEqual(entry["license"], "OFL-1.1", name)
            self.assertTrue(entry["integrity"].startswith("sha512-"), name)
            self.assertTrue(entry["resolved"].startswith("https://registry.npmjs.org/"), name)
            versions.add(wanted)
        self.assertEqual(len(versions), 1, versions)


class StylesheetTest(unittest.TestCase):
    def test_office_imports_package_css_for_four_weights(self) -> None:
        config = read(FONT_DIRS["office"] / "nuxt.config.ts")
        for weight in (400, 500, 600, 700):
            self.assertIn(f"'{PACKAGE}/{weight}.css',", config)
        self.assertNotIn("@font-face", read(FONT_DIRS["office"] / "app" / "assets" / "css" / "main.css"))

    def test_static_builds_make_the_css_they_link(self) -> None:
        for name in ("ca-nhan", "keycloak"):
            dockerfile = read(FONT_DIRS[name] / "Dockerfile")
            self.assertIn(f"p=node_modules/{PACKAGE};", dockerfile, name)
            self.assertIn("for w in 400 500 600 700; do", dockerfile, name)
            self.assertIn('cp "$p/LICENSE"', dockerfile, name)                  # OFL-1.1 đi cùng tệp phông
            self.assertRegex(dockerfile, r'cat "\$p/\$w\.css"; echo; \} >> /?fonts/be-vietnam-pro\.css', name)
            self.assertRegex(dockerfile, r'cp "\$p"/files/be-vietnam-pro-\*-"\$w"-normal\.woff\* /?fonts/files/;', name)
        ca_nhan = FONT_DIRS["ca-nhan"]
        self.assertIn("COPY --from=build /src/fonts/ /usr/share/nginx/html/ca-nhan/fonts/be-vietnam-pro/\n",
                      read(ca_nhan / "Dockerfile"))
        html = read(ca_nhan / "public" / "index.html")
        font_css = html.index('href="/ca-nhan/fonts/be-vietnam-pro/be-vietnam-pro.css"')
        self.assertLess(font_css, html.index('href="/ca-nhan/style.css"'))
        self.assertNotIn("@font-face", read(ca_nhan / "public" / "style.css"))


class KeycloakFontVolumeTest(unittest.TestCase):
    def test_one_shot_service_copies_into_named_volume(self) -> None:
        block = service_block("keycloak-fonts")
        for line in ("build: ./platform/keycloak/fonts", "image: moc/keycloak-fonts:${MOC_VERSION:-dev}",
                     "profiles: [core]", 'restart: "no"', "network_mode: none", "read_only: true",
                     "cap_drop: [ALL]", "- keycloak_fonts:/theme-fonts"):
            self.assertIn(f"    {line}\n" if not line.startswith("-") else f"      {line}\n", block, line)
        self.assertNotIn("<<: *common", block)              # x-common: restart unless-stopped, mạng moc
        self.assertRegex(read(ROOT / "docker-compose.yml"), r"(?m)^volumes:\n(?:.*\n)*?  keycloak_fonts:\n")

    def test_keycloak_mounts_volume_and_waits_for_copy(self) -> None:
        block = service_block("keycloak")
        self.assertIn("      - ./platform/keycloak/themes/signet:/opt/keycloak/themes/signet:ro\n", block)
        self.assertIn(f"      - keycloak_fonts:{THEME_FONTS}:ro\n", block)
        self.assertIn("      keycloak-fonts: {condition: service_completed_successfully}\n", block)
        # điểm gắn nằm trong bind mount chỉ đọc: thư mục phải có sẵn trong theme
        mount = ROOT / "platform" / "keycloak" / THEME_FONTS.replace("/opt/keycloak/", "")
        self.assertTrue((mount / "README.md").is_file(), mount)

    def test_image_paths_match_script(self) -> None:
        dockerfile = read(FONTS_IMAGE / "Dockerfile")
        script = read(FONTS_IMAGE / "copy-fonts.sh")
        self.assertIn("COPY --from=build /fonts /fonts\n", dockerfile)
        self.assertIn('ENTRYPOINT ["sh", "/copy-fonts.sh"]\n', dockerfile)
        self.assertIn("\nSRC=/fonts\nDST=/theme-fonts\n", script)
        self.assertEqual(dockerfile.count("FROM node:24.20.0-slim@sha256:"), 2)   # không thêm image thượng nguồn
        # không chạy root: thư mục gắn volume thuộc node trước khi đổi user
        last = dockerfile[dockerfile.rindex("FROM "):]
        self.assertLess(last.index("chown node:node /theme-fonts"), last.index("\nUSER node\n"))
        self.assertLess(last.index("\nUSER node\n"), last.index("ENTRYPOINT"))

    @unittest.skipUnless(shutil.which("sh"), "cần sh")
    def test_copy_replaces_old_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = pathlib.Path(tmp, "fonts"), pathlib.Path(tmp, "theme-fonts")
            (src / "files").mkdir(parents=True)
            (src / "be-vietnam-pro.css").write_text("moi", encoding="utf-8")
            (src / "files" / "a-400-normal.woff2").write_bytes(b"\x00moi")
            (dst / "files").mkdir(parents=True)
            (dst / "be-vietnam-pro.css").write_text("cu", encoding="utf-8")
            (dst / "files" / "bo-400-normal.woff2").write_bytes(b"cu")             # bản cũ, không còn trong image
            script = read(FONTS_IMAGE / "copy-fonts.sh").replace("\nSRC=/fonts\nDST=/theme-fonts\n",
                                                                  f"\nSRC={src}\nDST={dst}\n")
            proc = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            got = sorted(str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file())
            self.assertEqual(got, ["be-vietnam-pro.css", "files/a-400-normal.woff2"])
            self.assertEqual((dst / "be-vietnam-pro.css").read_text(encoding="utf-8"), "moi")
            self.assertIn("2 tệp phông", proc.stdout)

    @unittest.skipUnless(shutil.which("sh") and os.geteuid() != 0, "cần sh, không chạy root")
    def test_copy_stops_with_hint_when_volume_not_writable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = pathlib.Path(tmp, "fonts"), pathlib.Path(tmp, "theme-fonts")
            src.mkdir()
            (src / "be-vietnam-pro.css").write_text("moi", encoding="utf-8")
            dst.mkdir(mode=0o555)                     # như volume tạo lúc image còn chạy root
            script = read(FONTS_IMAGE / "copy-fonts.sh").replace("\nSRC=/fonts\nDST=/theme-fonts\n",
                                                                  f"\nSRC={src}\nDST={dst}\n")
            try:
                proc = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=False)
            finally:
                dst.chmod(0o755)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("xóa volume keycloak_fonts", proc.stderr)
            self.assertEqual(list(dst.iterdir()), [])


def compose_stub(services: dict[str, Any], containers: list[dict[str, Any]], calls: list[list[str]]):
    def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        out = ""
        if "config" in cmd:
            out = json.dumps({"services": services})
        elif "ps" in cmd:
            out = "\n".join(json.dumps(c) for c in containers)
        return subprocess.CompletedProcess(cmd, 0, out, "")
    return run


class ReconcileOneShotTest(unittest.TestCase):
    SERVICES = {"keycloak-fonts": {},
                "keycloak": {"depends_on": {"keycloak-fonts": {"condition": "service_completed_successfully"}}}}

    def heal(self, fonts: dict[str, Any]) -> tuple[dict[str, Any], list[list[str]]]:
        rows = [{"Service": "keycloak", "State": "running", "Health": "healthy", "ExitCode": 0},
                {"Service": "keycloak-fonts", **fonts}]
        calls: list[list[str]] = []
        report: dict[str, Any] = {"actions": [], "problems": []}
        with mock.patch.object(reconcile, "_run", compose_stub(self.SERVICES, rows, calls)):
            reconcile.heal(report)
        return report, [c for c in calls if "up" in c]

    def test_finished_one_shot_is_left_alone(self) -> None:
        report, ups = self.heal({"State": "exited", "ExitCode": 0, "Status": "Exited (0) 2 hours ago"})
        self.assertEqual(ups, [])
        self.assertEqual(report["actions"], [])

    def test_failed_one_shot_runs_again(self) -> None:
        report, ups = self.heal({"State": "exited", "ExitCode": 1, "Status": "Exited (1) 1 minute ago"})
        self.assertEqual(len(ups), 1)
        self.assertEqual(ups[0][-1], "keycloak-fonts")
        self.assertIn("chạy lại keycloak-fonts (đã dừng: Exited (1) 1 minute ago)", report["actions"])
        # lượt nào cũng thoát lỗi thì người vận hành phải thấy, không chỉ nằm trong actions
        self.assertEqual(len(report["problems"]), 1)
        self.assertIn("keycloak-fonts chạy một lần mà thoát lỗi (Exited (1) 1 minute ago)", report["problems"][0])

    def test_stopped_long_running_service_still_restarted(self) -> None:
        services = {"centrifugo": {}}
        rows = [{"Service": "centrifugo", "State": "exited", "ExitCode": 0, "Status": "Exited (0)"}]
        calls: list[list[str]] = []
        report: dict[str, Any] = {"actions": [], "problems": []}
        with mock.patch.object(reconcile, "_run", compose_stub(services, rows, calls)):
            reconcile.heal(report)
        self.assertIn("chạy lại centrifugo (đã dừng: Exited (0))", report["actions"])


if __name__ == "__main__":
    unittest.main()
