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


"""Hàm thuần của make demo-it-ot (#432): đọc lịch sử đo từ NGSI-LD temporal API của Scorpio. moc_env thay bằng bản giả
(như test_log_tap_trung): không mạng, không Docker. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

AT = ("2026-10-30T02:20:00Z", "2026-10-30T02:20:01Z")


class NgsiPointsTest(unittest.TestCase):
    demo = None
    saved: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        for name in ("moc_env", "demo"):
            cls.saved[name] = sys.modules.pop(name, None)
        stub = types.ModuleType("moc_env")

        def no_network(*args, **kwargs):
            raise AssertionError("test không được gọi mạng, Docker")

        stub.ENV, stub.ROOT, stub.PUBLIC_URL, stub.EICAR = {}, ROOT, "http://localhost:8080", b""
        stub.HTTPError = type("HTTPError", (Exception,), {})
        stub.Session = type("Session", (), {"__init__": no_network})
        for name in ("call_json", "compose", "request", "text_pdf", "user_token"):
            setattr(stub, name, no_network)
        sys.modules["moc_env"] = stub
        cls.demo = importlib.import_module("demo")

    @classmethod
    def tearDownClass(cls) -> None:
        for name, module in cls.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_a_list_of_readings(self) -> None:
        history = {"id": "urn:ngsi-ld:TemperatureSensor:x", "temperature": [
            {"type": "Property", "value": 24, "observedAt": AT[0]},
            {"type": "Property", "value": 29, "observedAt": AT[1]}]}
        self.assertEqual(self.demo.ngsi_points(history, "temperature"), {(24, AT[0]), (29, AT[1])})

    def test_a_single_reading_comes_as_an_object(self) -> None:
        # JSON-LD rút gọn: lịch sử mới có một lần đo thì không còn là danh sách — lỗi của run 40937902919
        history = {"id": "urn:ngsi-ld:TemperatureSensor:x",
                   "temperature": {"type": "Property", "value": 24, "observedAt": AT[0]}}
        self.assertEqual(self.demo.ngsi_points(history, "temperature"), {(24, AT[0])})

    def test_nothing_usable_is_empty(self) -> None:
        for history in (None, "lỗi", [], {}, {"temperature": "24"}, {"temperature": ["24", None]}):
            self.assertEqual(self.demo.ngsi_points(history, "temperature"), set(), history)


if __name__ == "__main__":
    unittest.main()
