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

"""scripts/yaml_nho.py: tập con YAML đủ cho manifest ứng dụng và db/metadata; ngoài tập con thì báo lỗi có số dòng,
không đoán. Có PyYAML thì so từng tệp db/metadata + apps/*/app.yaml với PyYAML (không có thì bỏ qua ca đó).
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import yaml_nho  # noqa: E402

loads = yaml_nho.loads


class Subset(unittest.TestCase):
    def test_block_and_flow(self) -> None:
        text = """
# chú thích
a: 1
b: -2.5
c: true
d: ~
e: chữ có dấu # chú thích sau
f: "nháy kép \\"x\\" \\u0041\\n"
g: 'nháy đơn ''y'' # không phải chú thích'
h: [1, "hai", {k: v, l: [3]}]
i:
  - x
  - k: 1
    l: 2
  - [a, b]
j: {m: w,
    o: [p,
        q]}
k: 2026-10-25
l: ""
m: []
n: {}
"""
        self.assertEqual(loads(text), {
            "a": 1, "b": -2.5, "c": True, "d": None, "e": "chữ có dấu", "f": 'nháy kép "x" A\n',
            "g": "nháy đơn 'y' # không phải chú thích", "h": [1, "hai", {"k": "v", "l": [3]}],
            "i": ["x", {"k": 1, "l": 2}, ["a", "b"]], "j": {"m": "w", "o": ["p", "q"]}, "k": "2026-10-25",
            "l": "", "m": [], "n": {}})

    def test_anchor_alias_are_independent_copies(self) -> None:
        data = loads("a: &x {k: [1]}\nb: *x\nc:\n  - &y v\n  - *y\n")
        self.assertEqual(data, {"a": {"k": [1]}, "b": {"k": [1]}, "c": ["v", "v"]})
        data["b"]["k"].append(2)
        self.assertEqual(data["a"], {"k": [1]})

    def test_nested_aliases_have_a_node_budget(self) -> None:
        bomb = "a: &a [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]\n"
        for i in range(1, 8):                          # 7 tầng × 10: hàng chục triệu nút nếu cứ chép
            prev = "a" if i == 1 else f"b{i - 1}"
            bomb += f"b{i}: &b{i} [" + ", ".join([f"*{prev}"] * 10) + "]\n"
        with self.assertRaisesRegex(yaml_nho.YamlError, "quá 10000 nút"):
            loads(bomb)
        block = "a: &a\n  - x\n" + "".join(f"k{i}: *a\n" for i in range(6000))
        with self.assertRaisesRegex(yaml_nho.YamlError, "quá 10000 nút"):
            loads(block)
        self.assertEqual(len(loads("a: &a [1]\n" + "".join(f"k{i}: *a\n" for i in range(100)))), 101)

    def test_json_is_accepted(self) -> None:
        value = {"table": {"schema": "s", "name": "t"}, "x": [1, 2.5, None, True, "a: b # c"], "y": "\"q\" {{ $b }}"}
        self.assertEqual(loads("# đầu\n" + json.dumps(value, ensure_ascii=False, indent=2)), value)
        self.assertEqual(loads("k: " + json.dumps([value], ensure_ascii=False)), {"k": [value]})

    def test_outside_subset_is_an_error_with_line(self) -> None:
        cases = {
            "a: |\n  x\n": "dòng 1",
            "a: >\n  x\n": "dòng 1",
            "a: !!str 1\n": "dòng 1",
            "a: 1\n<<: *x\n": "dòng 2",
            "a: 1\n---\nb: 2\n": "dòng 2",
            "a:\n\t- 1\n": "dòng 2",
            "a: 1\na: 2\n": "trùng",
            "a: yes\n": "mập mờ",
            "a: 010\n": "số 0",
            "a: [1, 2\n": "không đóng",
            "a: \"x\n": "dòng 1",
            "a: *khong_co\n": "khong_co",
        }
        for text, needle in cases.items():
            with self.subTest(text=text), self.assertRaisesRegex(yaml_nho.YamlError, needle):
                loads(text)


class SameAsPyYaml(unittest.TestCase):
    def test_metadata_and_manifests(self) -> None:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            self.skipTest("không có PyYAML để so")
        files = sorted((REPO / "db" / "metadata").rglob("*.yaml")) + sorted((REPO / "apps").glob("*/app.yaml"))
        self.assertGreater(len(files), 20)
        for path in files:
            with self.subTest(path=str(path.relative_to(REPO))):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(loads(text), yaml.safe_load(text))


if __name__ == "__main__":
    unittest.main()
