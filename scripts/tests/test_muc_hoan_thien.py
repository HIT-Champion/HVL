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

"""Bảng mức hoàn thiện ghi đúng số hàm test (#285). docs/muc-hoan-thien.md ghi "<thư mục> `tệp` N" trong các bảng: tệp
đó có N hàm test, đếm tĩnh như §1 của chính tài liệu. Không có gì kiểm nên số lệch dần, có chỗ sai từ lúc viết
(`test_anchors.py` ghi 38, tệp có 28). Test đọc mọi dòng bảng và kiểm:
  * thư mục viết tắt như đầu tài liệu (svc-files, svc-workflow, db, scripts, office, ca-nhan, bang-tin, e2e), viết một
    lần thì áp cho các tệp sau nó trong cùng ô;
  * mỗi "`tệp` N" sau một thư mục là tệp có thật, có đúng N hàm test: Python `def test_` (cả async), giao diện
    (`.ts`, `.js`) `test(` hay `it(` đầu dòng, e2e `test(` sát lề;
  * số chỉ một phần tệp viết "`tệp` (N hàm về …)": không phải "`tệp` N" nên không bị kiểm.
Tổng ở §1 và số chạy trong CI đếm lại khi chốt bản phát hành, không kiểm ở đây.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import pathlib
import re
import unittest
from collections.abc import Callable

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "muc-hoan-thien.md"
DIRS = {
    "svc-files": "services/svc-files/tests",
    "svc-workflow": "services/svc-workflow/tests",
    "db": "db/tests",
    "scripts": "scripts/tests",
    "office": "apps/office/tests",
    "ca-nhan": "apps/ca-nhan/tests",
    "bang-tin": "apps/bang-tin/tests",
    "e2e": "tests/e2e",
}
# thư mục rồi khoảng trắng ("office: …" cũng được): không bắt `db` trong "job `db`" vì sau nó là dấu `
TOKEN = re.compile(r"(?<![\w`-])(" + "|".join(map(re.escape, DIRS)) + r"):?\s"
                   r"|`([\w./-]+\.(?:py|ts|js))`(?:\s+(\d+)\b)?")
CELL = re.compile(r"(?<!\\)\|")                       # "\|" trong ô (lệnh grep) không tách ô
PY = re.compile(r"^\s*(?:async\s+)?def test_", re.M)
UI = re.compile(r"^\s*(?:test|it)\(", re.M)
E2E = re.compile(r"^test\(", re.M)


def count(path: pathlib.Path) -> int | None:
    """Số hàm test của một tệp theo cách đếm ở §1; None nếu không có tệp."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return len(PY.findall(text))
    return len((E2E if path.name.endswith(".spec.ts") else UI).findall(text))


def problems(text: str, counter: Callable[[str], int | None]) -> tuple[list[tuple[int, str]], int]:
    """Chỗ ghi sai trong các bảng của tài liệu: ([(số dòng, lời báo)], số cặp "`tệp` N" đã kiểm).

    counter: đường dẫn từ gốc repo → số hàm test, None nếu không có tệp."""
    found, checked = [], 0
    for no, line in enumerate(text.split("\n"), 1):
        if not line.startswith("|"):
            continue
        for cell in CELL.split(line):
            folder = None                             # thư mục không áp sang ô khác
            for m in TOKEN.finditer(cell):
                if m.group(1):
                    folder = m.group(1)
                    continue
                name, written = m.group(2), m.group(3)
                if written is None or folder is None:
                    continue
                checked += 1
                path = f"{DIRS[folder]}/{name}"
                real = counter(path)
                if real is None:
                    found.append((no, f"{folder} `{name}`: không có tệp {path}"))
                elif real != int(written):
                    found.append((no, f"{folder} `{name}`: bảng ghi {written}, tệp có {real} hàm test"))
    return found, checked


class CountTest(unittest.TestCase):
    def test_counts_like_section_one(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / "test_a.py").write_text("def test_a():\n    pass\n\nasync def test_b():\n    pass\n\n"
                                              "class T:\n    def test_c(self):\n        pass\n\ndef helper_test_d():\n")
            (folder / "a.test.ts").write_text("test('a', () => {})\n  it('b', () => {})\ndescribe('c', () => {\n"
                                              "  test('d', () => {})\n})\nawait test.step('e')\n")
            (folder / "a.spec.ts").write_text("test('a', async () => {\n  await test.step('b', async () => {})\n})\n"
                                              "  test('lồng trong describe, §1 không đếm')\n")
            self.assertEqual(count(folder / "test_a.py"), 3)
            self.assertEqual(count(folder / "a.test.ts"), 3)
            (folder / "a.test.js").write_text((folder / "a.test.ts").read_text())   # ca-nhan, bang-tin
            self.assertEqual(count(folder / "a.test.js"), 3)
            self.assertEqual(count(folder / "a.spec.ts"), 1)
            self.assertIsNone(count(folder / "test_khong_co.py"))


class ProblemsTest(unittest.TestCase):
    """problems() trên bảng viết tay với số đếm giả: bắt đúng chỗ sai, bỏ qua chỗ không phải "`tệp` N"."""

    FILES = {"services/svc-files/tests/test_a.py": 4, "services/svc-files/tests/test_b.py": 2,
             "db/tests/test_c.py": 7, "apps/office/tests/d.test.ts": 3, "tests/e2e/e.spec.ts": 1}

    def check(self, text: str) -> tuple[list[str], int]:
        found, checked = problems(text, self.FILES.get)
        return [f"{no}: {msg}" for no, msg in found], checked

    def test_correct_counts_pass(self) -> None:
        row = "| F1 | x | Hoàn thiện | svc-files `test_a.py` 4, `test_b.py` 2; db `test_c.py` 7 | e2e `e.spec.ts` 1 |"
        self.assertEqual(self.check(row), ([], 4))
        # "office:" rồi chữ khác vẫn đặt thư mục cho tệp sau
        self.assertEqual(self.check("| F2 | office: một test trong `d.test.ts` kiểm …; `d.test.ts` 3 |"), ([], 1))

    def test_wrong_count_and_missing_file_name_the_line(self) -> None:
        text = "đoạn văn\n\n| a | b |\n|---|---|\n| F1 | svc-files `test_a.py` 38; db `test_x.py` 2 |"
        self.assertEqual(self.check(text), (["5: svc-files `test_a.py`: bảng ghi 38, tệp có 4 hàm test",
                                             "5: db `test_x.py`: không có tệp db/tests/test_x.py"], 2))

    def test_partial_counts_and_mentions_are_skipped(self) -> None:
        self.assertEqual(self.check("| F1 | svc-files `test_a.py` (17 hàm về token) | e2e `e.spec.ts` (2 test) |"),
                         ([], 0))
        # tệp không sau thư mục nào, thư mục ở ô khác, "job `db`", dòng ngoài bảng: không kiểm
        self.assertEqual(self.check("| F1 | db | `test_c.py` 9 | job `db` `test_c.py` 9 |\nsvc-files `test_a.py` 9"),
                         ([], 0))

    def test_escaped_pipe_stays_in_its_cell(self) -> None:
        row = r"| office | `grep -hE '^\s*(test\|it)\('` | office `d.test.ts` 5 |"
        self.assertEqual(self.check(row), (["1: office `d.test.ts`: bảng ghi 5, tệp có 3 hàm test"], 1))


class DocTest(unittest.TestCase):
    maxDiff = None                                    # in đủ mọi dòng sai, không cắt

    def test_matrix_counts_match_the_test_files(self) -> None:
        found, checked = problems(DOC.read_text(encoding="utf-8"), lambda rel: count(ROOT / rel))
        self.assertEqual([f"docs/muc-hoan-thien.md:{no}: {msg}" for no, msg in found], [],
                         "thêm, bớt hàm test thì sửa số trong bảng ở cùng pull request")
        # cận dưới: bộ đọc bảng hỏng thì đỏ thay vì qua mà không kiểm gì (26/10: 97 cặp)
        self.assertGreaterEqual(checked, 90, f"chỉ đọc được {checked} cặp `tệp` N")


if __name__ == "__main__":
    unittest.main()
