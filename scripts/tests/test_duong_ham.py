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


if __name__ == "__main__":
    unittest.main()
