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

"""make demo-tat-van-phong (#328): không dựng lại svc-files, svc-workflow mà một thư mục khác đã dựng — bản cài cùng
project compose `moc` khi quên đặt COMPOSE_PROJECT_NAME. Không cần Docker, không đọc .env (moc_env giả như
test_moc_neo.py). Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import importlib
import io
import pathlib
import subprocess
import sys
import types
import unittest
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent

demo: Any = None
_saved: dict[str, Any] = {}


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp (thiếu thì thoát): thay bằng bản giả chỉ có những gì kịch bản cần."""
    global demo
    for name in ("moc_env", "demo_tat_van_phong"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ROOT = ROOT
    stub.PUBLIC_URL = "https://signet.example"
    stub.HTTPError = RuntimeError

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng")

    stub.call_json = stub.Session = no_network
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    demo = importlib.import_module("demo_tat_van_phong")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


class FakeDocker:
    """``docker compose ps -q`` trả các id trong ``dirs``; ``docker inspect`` trả thư mục đã dựng từng container."""

    def __init__(self, dirs: dict[str, str]) -> None:
        self.dirs = dirs
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args[:2] == ["docker", "inspect"]:
            out = "".join(self.dirs[i] + "\n" for i in args[4:])
        elif "ps" in args:
            out = "".join(i + "\n" for i in self.dirs)
        else:
            raise AssertionError(f"lệnh không được chạy trước khi kiểm thư mục: {args}")
        return subprocess.CompletedProcess(args, 0, out, "")


class StartedElsewhereTest(unittest.TestCase):
    def check(self, dirs: dict[str, str]) -> tuple[str | None, FakeDocker]:
        docker = FakeDocker(dirs)
        with mock.patch.object(demo.subprocess, "run", docker):
            return demo.started_elsewhere(), docker

    def test_stack_built_here_goes_ahead(self) -> None:
        # CI, stack thử moc-<việc>: container dựng từ chính thư mục mã nguồn
        found, docker = self.check({"a1": str(ROOT), "b2": str(ROOT / "scripts" / "..")})
        self.assertIsNone(found)
        self.assertEqual(docker.calls[0][-3:], ["-q", "svc-files", "svc-workflow"])

    def test_nothing_running_goes_ahead(self) -> None:
        # chưa có container: màn demo tự báo ở bước 1 (cổng không trả lời), không có gì để thay nhầm
        found, docker = self.check({})
        self.assertIsNone(found)
        self.assertEqual(len(docker.calls), 1)          # không có id thì không inspect

    def test_install_dir_stops_before_any_change(self) -> None:
        found, _ = self.check({"a1": str(ROOT), "b2": "/opt/moc"})
        self.assertEqual(found, "/opt/moc")
        with mock.patch.object(demo.subprocess, "run", FakeDocker({"a1": "/opt/moc"})) as docker, \
                self.assertRaisesRegex(demo.DemoFailed, "dựng từ /opt/moc, không phải từ thư mục này.*"
                                       "COMPOSE_PROJECT_NAME=moc-thu"), contextlib.redirect_stdout(io.StringIO()):
            demo.run()
        self.assertEqual(len(docker.calls), 2)          # ps, inspect — không up, không gọi Signet


if __name__ == "__main__":
    unittest.main()
