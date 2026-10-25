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

"""Ký tự điều khiển hai chiều (LRE, RLE, PDF, LRO, RLO, LRI, RLI, FSI, PDI) không được viết thẳng trong mã: chúng làm
mã hiện ra khác với mã chạy (Trojan Source, CVE-2021-42574). Kiểm lại luật SonarQube ``text:S6389`` ngay trong make
test, không cần SonarQube: duyệt services/, apps/, scripts/ (đúng ``sonar.sources``), mọi tệp đọc được bằng UTF-8, kể
cả tệp test. Mã cần các ký tự này (lọc ký tự vô hình, ca thử) thì viết mã thoát, vd ``"\\u202e"``.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCOPE = ("services", "apps", "scripts")
# thư mục sinh ra hoặc tải về, không phải mã của repo (đã có trong .gitignore)
SKIP = {".git", "node_modules", ".nuxt", ".output", "dist", "build", ".venv", "venv", "__pycache__", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "coverage"}
# U+202A–U+202E, U+2066–U+2069; dựng bằng chr() để chính tệp này không chứa ký tự nào
BIDI = {chr(c): f"U+{c:04X}" for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}


def scan(root: pathlib.Path) -> tuple[int, list[str]]:
    """→ (số tệp văn bản đã đọc, các chỗ vi phạm dạng ``tệp:dòng: U+…``)."""
    read, found = 0, []
    for top in SCOPE:
        for folder, dirs, files in os.walk(root / top):
            dirs[:] = sorted(d for d in dirs if d not in SKIP)
            for name in sorted(files):
                path = pathlib.Path(folder, name)
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue                    # tệp nhị phân (ảnh, PDF, phông chữ), liên kết hỏng
                read += 1
                # tách theo \n, không dùng splitlines(): U+2028, U+2029 trong mã cũng là "hết dòng" với splitlines
                for no, line in enumerate(text.split("\n"), 1):
                    marks = sorted({BIDI[c] for c in line if c in BIDI})
                    if marks:
                        found.append(f"{path.relative_to(root).as_posix()}:{no}: {', '.join(marks)}")
    return read, found


class BidiTest(unittest.TestCase):
    def test_no_bidi_control_characters_in_code(self) -> None:
        read, found = scan(ROOT)
        self.assertGreater(read, 200)           # duyệt thật cây mã (khoảng 270 tệp), không đạt suông
        self.assertEqual(found, [], "ký tự điều khiển hai chiều viết thẳng, thay bằng mã thoát:\n" + "\n".join(found))

    def test_scan_reports_file_and_line_and_skips_generated_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "apps" / "node_modules").mkdir(parents=True)
            (root / "services").mkdir()
            (root / "apps" / "a.ts").write_text("const x = 1\nconst s = 'abc" + chr(0x202E) + "'\n", encoding="utf-8")
            (root / "apps" / "node_modules" / "b.js").write_text(chr(0x2066), encoding="utf-8")
            (root / "services" / "c.py").write_text("x = 1\u2028y = '" + chr(0x2067) + "'\n", encoding="utf-8")
            (root / "services" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
            self.assertEqual(scan(root), (2, ["services/c.py:1: U+2067", "apps/a.ts:2: U+202E"]))


if __name__ == "__main__":
    unittest.main()
