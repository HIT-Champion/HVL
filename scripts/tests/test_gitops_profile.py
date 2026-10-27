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

"""Reconciler dùng đúng các profile của bản cài (scripts/reconcile.py, compose()): core, app cùng MOC_EXTRA_PROFILES
trong .env. Cờ --profile của docker compose đè COMPOSE_PROFILES của .env: thiếu profile thêm thì `down` lúc áp commit
để sót cloudflared (tunnel) còn chạy từ thư mục cài, install.sh từ chối cài lại. Không cần Docker: ghi lại lệnh thay
vì chạy. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reconcile_profile", SCRIPTS / "reconcile.py")
reconcile: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)


def profiles(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd[:-1]) if arg == "--profile"]


class ExtraProfilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings: dict[str, str] = {}
        saved = {n: getattr(reconcile, n) for n in ("setting", "_run", "checkout", "check_gateway_env")}
        self.addCleanup(lambda: [setattr(reconcile, n, v) for n, v in saved.items()])
        reconcile.setting = lambda name, default="": self.settings.get(name, default)

    def test_core_and_app_without_extra_profiles(self) -> None:
        self.assertEqual(profiles(reconcile.compose()), ["core", "app"])

    def test_extra_profiles_from_env_file(self) -> None:
        self.settings["MOC_EXTRA_PROFILES"] = " tunnel, ai,,app "
        self.assertEqual(profiles(reconcile.compose()), ["core", "app", "tunnel", "ai"])

    def test_apply_stops_and_starts_extra_profiles(self) -> None:
        self.settings["MOC_EXTRA_PROFILES"] = "tunnel,ai"
        calls: list[list[str]] = []

        def run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        reconcile._run = run
        reconcile.checkout = lambda git, src, commit: {"MOC_VERSION": commit}
        reconcile.check_gateway_env = lambda src, env: None
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp)
            (src / "scripts").mkdir()
            (src / "scripts" / "install.sh").write_text("", encoding="utf-8")
            reconcile.apply([], src, "abc123", None)
        compose = [c for c in calls if c[:2] == ["docker", "compose"]]
        self.assertEqual([c[2 + 2 * len(profiles(c))] for c in compose], ["build", "down", "up"])
        for c in compose:
            self.assertEqual(profiles(c), ["core", "app", "tunnel", "ai"], c)


if __name__ == "__main__":
    unittest.main()
