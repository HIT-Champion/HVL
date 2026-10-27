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

"""Thông báo đa kênh (email, webhook, SMS, Zalo) của svc-workflow ở phần điều phối: mặc định tắt, mật khẩu SMTP, URL
webhook, mật khẩu cổng SMS, token bot Zalo đi qua két (bí mật tùy chọn của platform/openbao/start.sh), hộp thư thử
Mailpit chỉ ở profile mail, giao diện chỉ mở ở 127.0.0.1. Kiểm chữ và chạy hàm shell bằng sh (không có PyYAML,
không cần Docker).
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

from test_duong_ham import ROOT, service_block

ENV_EXAMPLE = ROOT / ("." + "env.example")
REQUIRED = {"HASURA_ADMIN_SECRET": "a", "MOC_ACTION_SECRET": "b", "FLOWABLE_ADMIN_PASSWORD": "c",
            "CENTRIFUGO_API_KEY": "d", "MOC_DIRECTORY_CLIENT_SECRET": "e"}


class MailpitServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.block = service_block("mailpit")

    def test_only_in_mail_profile(self) -> None:
        self.assertIn("profiles: [mail]", self.block)
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertEqual(compose.count("profiles: [mail]"), 1)

    def test_pinned_image_and_quiet(self) -> None:
        self.assertRegex(self.block, r"image: axllent/mailpit:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}\n")
        self.assertIn('MP_DISABLE_VERSION_CHECK: "true"', self.block)

    def test_ui_only_on_loopback_and_smtp_not_published(self) -> None:
        ports = re.findall(r'^\s+- "(.+)"$', self.block, re.M)
        self.assertEqual(ports, ["127.0.0.1:${MOC_MAIL_UI_PORT:-8025}:8025"])
        self.assertNotIn("1025:", self.block)


class WorkflowSettingsTest(unittest.TestCase):
    def test_channels_off_by_default(self) -> None:
        # bỏ dòng chú thích: chỉ xét khai báo
        block = "\n".join(x for x in service_block("svc-workflow").splitlines() if not x.lstrip().startswith("#"))
        self.assertIn("MOC_SMTP_HOST: ${MOC_SMTP_HOST:-}", block)
        self.assertNotIn("MOC_NOTIFY_WEBHOOK_URL", block)  # URL có khóa: chỉ qua két
        self.assertNotIn("MOC_SMTP_PASSWORD", block)
        self.assertNotIn("MOC_SMS_GATEWAY_PASSWORD", block)
        self.assertNotIn("MOC_ZALO_BOT_TOKEN", block)      # token nằm trong đường dẫn API: chỉ qua két
        self.assertIn("MOC_SMS_GATEWAY_URL: ${MOC_SMS_GATEWAY_URL:-}", block)
        self.assertNotIn("mailpit", block)                 # không phụ thuộc hộp thư thử
        values = dict(re.findall(r"^(MOC_(?:SMTP|NOTIFY|SMS|ZALO)_[A-Z_]+)=(.*)$",
                                 ENV_EXAMPLE.read_text(encoding="utf-8"), re.M))
        for name in ("MOC_SMTP_HOST", "MOC_NOTIFY_WEBHOOK_URL", "MOC_SMTP_PASSWORD", "MOC_SMS_GATEWAY_URL",
                     "MOC_SMS_GATEWAY_PASSWORD", "MOC_ZALO_BOT_TOKEN"):
            self.assertEqual(values[name], "", name)

    def test_secrets_reach_the_vault_container_only(self) -> None:
        block = service_block("openbao")
        self.assertIn("MOC_SMTP_PASSWORD: ${MOC_SMTP_PASSWORD:-}", block)
        self.assertIn("MOC_NOTIFY_WEBHOOK_URL: ${MOC_NOTIFY_WEBHOOK_URL:-}", block)
        self.assertIn("MOC_SMS_GATEWAY_PASSWORD: ${MOC_SMS_GATEWAY_PASSWORD:-}", block)
        self.assertIn("MOC_ZALO_BOT_TOKEN: ${MOC_ZALO_BOT_TOKEN:-}", block)


@unittest.skipUnless(shutil.which("sh"), "cần sh")
class OptionalSecretsTest(unittest.TestCase):
    """secrets_of svc-workflow của start.sh: bí mật bắt buộc thiếu thì dừng; bí mật tùy chọn rỗng thì bỏ qua."""

    def secrets(self, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        text = (ROOT / "platform" / "openbao" / "start.sh").read_text(encoding="utf-8")
        funcs = re.findall(r"^(?:secrets_json|secrets_of)\(\) \{\n.*?^\}\n", text, re.M | re.S)
        self.assertEqual(len(funcs), 2)
        script = "set -eu\nlog() { echo \"$*\" >&2; }\ndie() { log \"$*\"; exit 1; }\n" + "".join(funcs)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "secrets.sh"
            path.write_text(script + 'secrets_of "$1"\n', encoding="utf-8")
            return subprocess.run(["sh", str(path), "svc-workflow"], capture_output=True, text=True,
                                  env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **env})

    def test_optional_secrets_left_out_when_empty(self) -> None:
        proc = self.secrets({**REQUIRED, "MOC_SMTP_PASSWORD": ""})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), REQUIRED)

    def test_optional_secrets_escaped_when_set(self) -> None:
        url = 'https://chat.example.com/hooks/k"\\1'
        optional = {"MOC_SMTP_PASSWORD": "mk", "MOC_NOTIFY_WEBHOOK_URL": url, "MOC_SMS_GATEWAY_PASSWORD": "sms$1",
                    "MOC_ZALO_BOT_TOKEN": "123:token-bot"}
        proc = self.secrets({**REQUIRED, **optional})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {**REQUIRED, **optional})

    def test_required_secret_still_stops(self) -> None:
        proc = self.secrets({k: v for k, v in REQUIRED.items() if k != "CENTRIFUGO_API_KEY"})
        self.assertEqual(proc.returncode, 1)
        self.assertIn("thiếu biến môi trường CENTRIFUGO_API_KEY", proc.stderr)


if __name__ == "__main__":
    unittest.main()
