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

"""Cloudflare Tunnel (F1.9, profile tunnel): dịch vụ cloudflared chỉ chạy khi bật profile, không mở cổng, image ghim
digest, token từ tệp ngoài repo; MOC_EXTRA_PROFILES trong .env đi cùng mọi lệnh compose của Makefile; route Keycloak
gửi cổng 443 khi proxy tin cậy nói https mà không gửi X-Forwarded-Port. Kiểm chữ (không có PyYAML, không cần Docker).
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def service_block(name: str) -> str:
    """Khối của một dịch vụ trong docker-compose.yml: từ dòng `  <name>:` tới dịch vụ kế tiếp."""
    lines = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    start = lines.index(f"  {name}:")
    end = start + 1
    while end < len(lines) and not re.match(r"(  )?[A-Za-z#]", lines[end]):
        end += 1
    return "\n".join(lines[start:end])


class CloudflaredServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.block = service_block("cloudflared")

    def test_only_in_tunnel_profile_and_no_port(self) -> None:
        self.assertIn("profiles: [tunnel]", self.block)
        self.assertNotIn("ports:", self.block)
        self.assertNotIn("network_mode", self.block)

    def test_pinned_image_and_no_autoupdate(self) -> None:
        self.assertRegex(self.block, r"image: cloudflare/cloudflared:\d{4}\.\d+\.\d+@sha256:[0-9a-f]{64}\n")
        self.assertIn('command: ["tunnel", "--no-autoupdate", "run"]', self.block)

    def test_token_from_file_outside_repo(self) -> None:
        self.assertIn('env_file: ["${MOC_TUNNEL_TOKEN_FILE:-/home/moc/cloudflared-tunnel}"]', self.block)
        self.assertNotIn("environment:", self.block)    # token không nằm trong compose hay .env của dự án


@unittest.skipUnless(shutil.which("make"), "cần GNU Make")
class ExtraProfilesTest(unittest.TestCase):
    """Makefile đọc MOC_EXTRA_PROFILES của .env; make -n chỉ in lệnh, không gọi Docker."""

    def compose_line(self, env: str | None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(ROOT / "Makefile", tmp)
            if env is not None:
                (pathlib.Path(tmp) / ("." + "env")).write_text(env, encoding="utf-8")
            proc = subprocess.run(["make", "-n", "-s", "ps"], cwd=tmp, capture_output=True, text=True,
                                  env={**os.environ, "MAKEFLAGS": ""})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout.strip()

    def test_no_extra_profiles_by_default(self) -> None:
        self.assertEqual(self.compose_line("MOC_EXTRA_PROFILES=\n"), "docker compose --profile core --profile app ps")
        self.assertEqual(self.compose_line(None), "docker compose --profile core --profile app ps")

    def test_extra_profiles_follow_env(self) -> None:
        line = self.compose_line("MOC_PUBLIC_URL=https://x\nMOC_EXTRA_PROFILES=tunnel,iot\n")
        self.assertEqual(line, "docker compose --profile core --profile app --profile tunnel --profile iot ps")


class KeycloakForwardedPortTest(unittest.TestCase):
    """Cloudflare không gửi X-Forwarded-Port: route Keycloak đặt 443 khi proto https từ proxy tin cậy."""

    def test_map_sets_443_only_for_trusted_https_without_port(self) -> None:
        text = (ROOT / "platform" / "apisix" / "config.yaml").read_text(encoding="utf-8")
        start = text.index("geo $realip_remote_addr $moc_proxy_tin_cay {")
        geo = text[start:text.index("\n    }", start)]    # "}" đầu tiên là của ${{…}}
        self.assertIn("default 0;", geo)
        # cùng dải với apisix.trusted_addresses: tin cậy ở đây đúng là tin cậy ở APISIX
        self.assertIn("${{MOC_TRUSTED_PROXY:=127.0.0.1/32}} 1;", geo)
        start = text.index('map "$moc_proxy_tin_cay:$original_x_forwarded_proto:$original_x_forwarded_port"'
                           " $moc_cong_chuyen_tiep {")
        body = text[start:text.index("\n    }", start)]
        self.assertRegex(body, r'"1:https:"\s+443;')
        self.assertRegex(body, r'"~\^1:\[\^:\]\*:\(\?<moc_cong_goc>\.\+\)\$"\s+\$moc_cong_goc;')
        self.assertRegex(body, r"default\s+\$var_x_forwarded_port;")
        # APISIX giữ $http_x_forwarded_* ở giá trị thô của client: dùng chúng là tin cả tiêu đề giả
        self.assertNotIn("$http_x_forwarded", body)

    def test_every_keycloak_route_uses_the_port(self) -> None:
        text = (ROOT / "platform" / "apisix" / "apisix.yaml").read_text(encoding="utf-8")
        self.assertIn("X-Forwarded-Port: $moc_cong_chuyen_tiep", text)
        routes = text.split("\nroutes:\n", 1)[1].split("\n  - id: ")
        keycloak = [r for r in routes if "upstream_id: keycloak" in r]
        self.assertEqual(len(keycloak), 3)
        for route in keycloak:
            self.assertIn("plugin_config_id: cong-keycloak", route, route.splitlines()[0])


# /proc/net/route của APISIX: eth0 ở mạng moc (172.18.0.0/16, route mặc định qua 172.18.0.1), eth1 ở mạng apps
# (172.19.0.0/16, internal: không có route mặc định). Hex, byte thấp trước
ROUTE_HEADER = "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
ROUTE_APPS = "eth1\t000013AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0\n"
ROUTE_MOC = ("eth0\t00000000\t010012AC\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
             "eth0\t000012AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0\n")


class TrustedProxyAutoTest(unittest.TestCase):
    """#211: MOC_TRUSTED_PROXY=auto → dải của mạng moc, đọc lúc APISIX khởi động; không bao giờ gồm mạng apps, nơi
    container ứng dụng có thể gửi X-Forwarded-For giả."""

    def run_entrypoint(self, routes: str, value: str | None, *args: str) -> subprocess.CompletedProcess[str]:
        script = (ROOT / "platform" / "apisix" / "kiem-moi-truong.sh").read_text(encoding="utf-8")
        self.assertIn("< /proc/net/route", script)
        self.assertIn('\nexec /docker-entrypoint.sh "$@"\n', script)
        with tempfile.TemporaryDirectory() as tmp:
            table = pathlib.Path(tmp) / "route"
            table.write_text(ROUTE_HEADER + routes, encoding="utf-8")
            dry = script.replace("/proc/net/route", str(table)).replace(
                'exec /docker-entrypoint.sh "$@"', 'echo "CHAY ${MOC_TRUSTED_PROXY-chua-dat}"')
            env = {"PATH": "/usr/bin:/bin"} | ({} if value is None else {"MOC_TRUSTED_PROXY": value})
            return subprocess.run(["sh", "-s", "--", *args], input=dry, capture_output=True, text=True, env=env)

    def test_auto_trusts_the_network_with_the_default_route_only(self) -> None:
        for routes in (ROUTE_APPS + ROUTE_MOC, ROUTE_MOC + ROUTE_APPS):
            run = self.run_entrypoint(routes, "auto")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, "CHAY 172.18.0.0/16\n")
            self.assertIn("MOC_TRUSTED_PROXY=auto → 172.18.0.0/16", run.stderr)

    def test_auto_without_default_route_stops(self) -> None:
        # không lùi về 172.16.0.0/12 hay giá trị nào khác: APISIX không khởi động, lỗi ở docker compose logs apisix
        run = self.run_entrypoint(ROUTE_APPS, "auto")
        self.assertEqual(run.returncode, 64)
        self.assertNotIn("CHAY", run.stdout)
        self.assertIn("MOC_TRUSTED_PROXY=auto", run.stderr)

    def test_other_values_pass_unchanged(self) -> None:
        for value, shown in (("172.16.0.0/12", "172.16.0.0/12"), ("127.0.0.1/32", "127.0.0.1/32"),
                             (None, "chua-dat")):
            run = self.run_entrypoint(ROUTE_MOC, value)
            self.assertEqual((run.returncode, run.stdout), (0, f"CHAY {shown}\n"), run.stderr)

    def test_check_only_on_the_host_does_not_read_routes(self) -> None:
        # make up, reconciler GitOps chạy --chi-kiem trên máy chủ: route của máy chủ không phải route của container
        run = self.run_entrypoint("", "auto", "--chi-kiem")
        self.assertEqual((run.returncode, run.stdout, run.stderr), (0, "", ""))

    def test_apps_network_is_internal_and_apisix_is_on_moc(self) -> None:
        # điều kiện để mạng có route mặc định của APISIX đúng là mạng moc
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("networks: [moc, apps]", service_block("apisix"))
        self.assertRegex(compose, r"\n  apps:\n    driver: bridge\n    internal: true\n")
        self.assertRegex(compose, r"\n  moc:\n    driver: bridge\n")

    def test_env_example_and_ci_use_auto_behind_a_proxy(self) -> None:
        env = (ROOT / (".e" + "nv.example")).read_text(encoding="utf-8")
        self.assertIn("\nMOC_TRUSTED_PROXY=127.0.0.1/32\n", env)        # máy dev: không tin ai
        self.assertIn("MOC_TRUSTED_PROXY=auto", env)
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("s#^MOC_TRUSTED_PROXY=.*#MOC_TRUSTED_PROXY=auto#", ci)
        self.assertNotIn("172.16.0.0/12", ci)
        guide = (ROOT / "docs" / "trien-khai.md").read_text(encoding="utf-8")
        self.assertIn("s#^MOC_TRUSTED_PROXY=.*#MOC_TRUSTED_PROXY=auto#", guide)


if __name__ == "__main__":
    unittest.main()
