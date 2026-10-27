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

"""docs/api/rest-<dịch vụ>.md (#308): trang đọc được sinh từ docs/api/openapi/<dịch vụ>.json. Bản trong git phải đúng
bằng bản sinh lại từ tệp OpenAPI trong git, nên sửa OpenAPI mà quên sinh lại trang thì test đỏ ngay ở job test đơn vị,
không phải đợi CI dựng cả hệ thống (`make api-docs --check`). Không cần Docker, không đọc .env (moc_env giả như
test_demo_tat_van_phong.py). Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib
import json
import pathlib
import sys
import types
import unittest
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
API = ROOT / "docs" / "api"

api_docs: Any = None
_saved: dict[str, Any] = {}


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp (thiếu thì thoát): thay bằng bản giả, không gọi mạng, không gọi Docker."""
    global api_docs
    for name in ("moc_env", "api_docs"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ROOT = ROOT

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng hay Docker")

    stub.Session = stub.compose = no_network
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    api_docs = importlib.import_module("api_docs")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


def spec(service: str) -> dict:
    return json.loads((API / "openapi" / f"{service}.json").read_text(encoding="utf-8"))


class RestPages(unittest.TestCase):
    def test_pages_in_git_match_openapi(self) -> None:
        for service in api_docs.SERVICES:
            with self.subTest(service=service):
                page = API / f"rest-{service}.md"
                self.assertTrue(page.exists(), f"thiếu docs/api/rest-{service}.md: chạy make api-docs")
                self.assertEqual(page.read_text(encoding="utf-8"), api_docs.rest_file(service, spec(service)),
                                 f"docs/api/rest-{service}.md cũ so với openapi/{service}.json: chạy make api-docs")

    def test_every_operation_and_type_has_a_heading(self) -> None:
        for service in api_docs.SERVICES:
            s = spec(service)
            page = api_docs.rest_file(service, s)
            for path, item in s["paths"].items():
                for method in item:
                    if method in api_docs.HTTP_METHODS:
                        self.assertIn(f"\n## `{method.upper()} {path}`\n", page)
            for name in s["components"]["schemas"]:
                self.assertIn(f"\n### `{name}`\n", page)

    def test_no_line_opens_a_markdown_block_by_accident(self) -> None:
        for service in api_docs.SERVICES:
            prose = [line for line in api_docs.rest_file(service, spec(service)).splitlines()
                     if line and not line.startswith(("#", "|", ">"))]
            for line in prose:
                self.assertIsNone(api_docs.BLOCK_START.match(line), line)


class Helpers(unittest.TestCase):
    def test_prose_wraps_at_120_and_keeps_list_markers_inline(self) -> None:
        text = "chữ " * 29 + "- không phải danh sách, " + "1. cũng không phải, " * 8
        lines = api_docs.prose(text)
        self.assertGreater(len(lines), 1)
        self.assertEqual(" ".join(lines), " ".join(text.split()))
        for line in lines[1:]:
            self.assertIsNone(api_docs.BLOCK_START.match(line), line)

    def test_cell_is_one_line_and_escapes_pipes(self) -> None:
        self.assertEqual(api_docs.cell("a | b\n  c"), "a \\| b c")
        self.assertEqual(api_docs.cell(None), "")

    def test_schema_type(self) -> None:
        t = api_docs.schema_type
        self.assertEqual(t({"$ref": "#/components/schemas/AskIn"}), "AskIn")
        self.assertEqual(t({"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]}),
                         "string (date) hoặc null")
        self.assertEqual(t({"type": "array", "items": {"$ref": "#/components/schemas/Hit"}}), "Hit[]")
        self.assertEqual(t({"enum": ["in", "out"]}), '"in", "out"')
        self.assertEqual(t({"type": "object", "additionalProperties": {"type": "integer"}}),
                         "object (giá trị integer)")
        self.assertEqual(t({}), "any")

    def test_field_description_carries_the_default(self) -> None:
        self.assertEqual(api_docs.described({"description": "Số dòng", "default": 50}), "Số dòng. Mặc định `50`.")
        self.assertEqual(api_docs.described({"default": False}), "Mặc định `false`.")


if __name__ == "__main__":
    unittest.main()
