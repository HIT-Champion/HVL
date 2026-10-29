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

"""Trợ lý hỏi đáp viết câu trả lời qua API ngoài chuẩn OpenAI (#430) ở phần điều phối: mặc định tắt (ollama), khóa
MOC_ASK_API_KEY đi qua két (bí mật tùy chọn của svc-files trong platform/openbao/start.sh), không nằm trong biến môi
trường của container svc-files. Kiểm chữ và chạy hàm shell bằng sh (không có PyYAML, không cần Docker).
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
REQUIRED = {"SEAWEEDFS_S3_ACCESS_KEY": "a", "SEAWEEDFS_S3_SECRET_KEY": "b", "HASURA_ADMIN_SECRET": "c",
            "MEILI_MASTER_KEY": "d"}
STORED = {"SEAWEEDFS_S3_ACCESS_KEY": "a", "SEAWEEDFS_S3_SECRET_KEY": "b", "HASURA_ADMIN_SECRET": "c",
          "MEILISEARCH_API_KEY": "d"}


class ComposeTest(unittest.TestCase):
    def test_off_by_default_and_key_only_through_the_vault(self) -> None:
        # bỏ dòng chú thích: chỉ xét khai báo
        block = "\n".join(x for x in service_block("svc-files").splitlines() if not x.lstrip().startswith("#"))
        self.assertIn("MOC_ASK_API: ${MOC_ASK_API:-ollama}", block)
        self.assertIn("MOC_ASK_API_URL: ${MOC_ASK_API_URL:-}", block)
        self.assertNotIn("MOC_ASK_API_KEY", block)
        self.assertIn("MOC_ASK_API_KEY: ${MOC_ASK_API_KEY:-}", service_block("openbao"))

    def test_env_example_documents_the_three_variables(self) -> None:
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        values = dict(re.findall(r"^(MOC_ASK_API[A-Z_]*)=(.*)$", text, re.M))
        self.assertEqual(values, {"MOC_ASK_API": "ollama", "MOC_ASK_API_URL": "", "MOC_ASK_API_KEY": ""})
        self.assertIn("rời máy chủ", text)       # cảnh báo: văn bản đã che vẫn đi ra ngoài


@unittest.skipUnless(shutil.which("sh"), "cần sh")
class VaultSecretTest(unittest.TestCase):
    """secrets_of svc-files của start.sh: khóa API ngoài là bí mật tùy chọn."""

    def secrets(self, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        text = (ROOT / "platform" / "openbao" / "start.sh").read_text(encoding="utf-8")
        funcs = re.findall(r"^(?:secrets_json|secrets_of)\(\) \{\n.*?^\}\n", text, re.M | re.S)
        self.assertEqual(len(funcs), 2)
        script = "set -eu\nlog() { echo \"$*\" >&2; }\ndie() { log \"$*\"; exit 1; }\n" + "".join(funcs)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "secrets.sh"
            path.write_text(script + 'secrets_of "$1"\n', encoding="utf-8")
            return subprocess.run(["sh", str(path), "svc-files"], capture_output=True, text=True,
                                  env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **env})

    def test_key_left_out_when_empty(self) -> None:
        for env in (REQUIRED, {**REQUIRED, "MOC_ASK_API_KEY": ""}):
            proc = self.secrets(env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout), STORED)

    def test_key_stored_when_set(self) -> None:
        proc = self.secrets({**REQUIRED, "MOC_ASK_API_KEY": 'th"u\\1'})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {**STORED, "MOC_ASK_API_KEY": 'th"u\\1'})


if __name__ == "__main__":
    unittest.main()
