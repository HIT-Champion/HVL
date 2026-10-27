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

"""Chia OpenAPI cho trang Swagger (apps/tai-lieu-api/chia_openapi.py) trên đúng docs/api/openapi/ trong git: mọi đường
qua cổng thuộc đúng một bộ; đường của svc-files trong bộ lõi đúng bằng các đường còn lại khi tắt Văn phòng điện tử
(CORE_API của services/svc-files/tests/test_office_flag.py); đường nội bộ không lên trang; mọi đường trên trang có route
APISIX; mọi kiểu được nhắc tới đều có. Không cần Docker. Chạy: python3 -m unittest discover -s apps/tai-lieu-api/tests
(make test)."""

from __future__ import annotations

import ast
import copy
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from typing import Any

APP = pathlib.Path(__file__).resolve().parent.parent
ROOT = APP.parent.parent
sys.path.insert(0, str(APP))

import chia_openapi as chia  # noqa: E402

OPENAPI = ROOT / "docs" / "api" / "openapi"


def specs() -> dict[str, dict[str, Any]]:
    return {s: json.loads((OPENAPI / f"{s}.json").read_text(encoding="utf-8")) for s in chia.SERVICES}


def core_api() -> list[str]:
    """CORE_API trong test cờ MOC_OFFICE_ENABLED của svc-files: đường còn lại khi tắt Văn phòng."""
    tree = ast.parse((ROOT / "services" / "svc-files" / "tests" / "test_office_flag.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "CORE_API" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("test_office_flag.py không còn CORE_API")


def gateway_patterns() -> list[re.Pattern[str]]:
    """Đường của các route APISIX tới svc-files, svc-workflow (dấu * của APISIX khớp mọi đuôi)."""
    text = (ROOT / "platform" / "apisix" / "apisix.yaml").read_text(encoding="utf-8").split("\nroutes:", 1)[1]
    out = []
    for block in text.split("\n  - id: ")[1:]:
        if not re.search(r"\n    upstream_id: svc-(files|workflow)\n", block):
            continue
        many = re.search(r"\n    uris: \[(.*?)\]", block, re.S)
        uris = re.findall(r'"([^"]+)"', many.group(1)) if many else re.findall(r"\n    uri: (\S+)", block)
        out += [re.compile("^" + re.escape(u).replace(r"\*", ".*") + "$") for u in uris]
    return out


class Split(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs = chia.split(specs())

    def test_every_gateway_path_in_exactly_one_set(self) -> None:
        source = specs()
        public = {p for s in source.values() for p in s["paths"] if p.startswith("/api/")}
        loi, van_phong = (set(self.docs[n]["paths"]) for n in ("loi", "van-phong"))
        self.assertEqual(loi | van_phong, public)
        self.assertEqual(loi & van_phong, set())

    def test_core_files_paths_are_those_left_when_office_is_off(self) -> None:
        files = set(specs()["svc-files"]["paths"])
        self.assertEqual({p for p in self.docs["loi"]["paths"] if p in files}, set(core_api()))

    def test_internal_paths_are_not_on_the_page(self) -> None:
        on_page = {p for doc in self.docs.values() for p in doc["paths"]}
        internal = {p for s in specs().values() for p in s["paths"] if not p.startswith("/api/")}
        self.assertTrue({"/actions/{name}", "/ot/notify/{tenant}"} <= internal)
        self.assertEqual(on_page & internal, set())

    def test_every_path_on_the_page_has_a_gateway_route(self) -> None:
        patterns = gateway_patterns()
        self.assertTrue(patterns)
        for doc in self.docs.values():
            for path in doc["paths"]:
                sample = re.sub(r"\{[^}]+\}", "x", path)
                with self.subTest(path=path):
                    self.assertTrue(any(p.match(sample) for p in patterns), f"{path}: không route nào của cổng")
        for path in ("/actions/registerIncoming", "/ot/notify/x"):
            self.assertFalse(any(p.match(path) for p in patterns), path)

    def test_operations_tagged_and_refs_resolve(self) -> None:
        for name, doc in self.docs.items():
            tags = [t["name"] for t in doc["tags"]]
            text = json.dumps(doc)
            for ref in set(re.findall(r'"#/components/schemas/([^"]+)"', text)):
                self.assertIn(ref, doc["components"]["schemas"], f"{name}: thiếu kiểu {ref}")
            for path, item in doc["paths"].items():
                for method, op in item.items():
                    if method in chia.HTTP_METHODS:
                        self.assertEqual(len(op["tags"]), 1, f"{name} {method} {path}")
                        self.assertIn(op["tags"][0], tags)
            self.assertIn("HTTPBearer", doc["components"]["securitySchemes"])
            self.assertEqual(doc["info"]["title"], chia.INFO[name][0])

    def test_new_path_must_be_placed(self) -> None:
        source = specs()
        source["svc-files"] = copy.deepcopy(source["svc-files"])
        source["svc-files"]["paths"]["/api/moi"] = {"get": {"responses": {}}}
        with self.assertRaisesRegex(ValueError, "/api/moi: chưa xếp vào bộ nào"):
            chia.split(source)
        del source["svc-files"]["paths"]["/api/moi"]
        del source["svc-files"]["paths"]["/api/status"]
        with self.assertRaisesRegex(ValueError, "/api/status: không còn trong OpenAPI"):
            chia.split(source)

    def test_main_writes_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(chia.main([str(OPENAPI), tmp]), 0)
            self.assertEqual(sorted(p.name for p in pathlib.Path(tmp).iterdir()), ["loi.json", "van-phong.json"])
            self.assertEqual(json.loads((pathlib.Path(tmp) / "loi.json").read_text(encoding="utf-8")),
                             self.docs["loi"])
            self.assertIn("loi.json: 11 đường", out.getvalue())


if __name__ == "__main__":
    unittest.main()
