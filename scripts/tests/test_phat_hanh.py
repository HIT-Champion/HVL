# Copyright 2026 Mộc Team
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

"""Ghi chú phát hành (scripts/release-notes.sh, dùng ở release.sh và .github/workflows/release.yml): lấy đúng mục
"## [X.Y.Z]" của CHANGELOG; khối mẫu trong chú thích HTML không tính; thiếu mục, hay mục chỉ có tiêu đề nhóm, thì
lỗi chứ không ra ghi chú rỗng. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "release-notes.sh"

CHANGELOG = """# Nhật ký thay đổi

## [Chưa phát hành]

### Đã thêm
- Việc chưa phát hành.

## [0.2.0] - 2026-10-30

### Đã thêm
- Tính năng của 0.2.0.

### Đã sửa lỗi
- Lỗi của 0.2.0.

## [0.1.0] - 2026-10-18

### Đã thêm
- Khung dự án.

<!-- Mẫu cho bản phát hành kế tiếp:
## [0.3.0] - YYYY-MM-DD
### Đã thêm
### Đã sửa lỗi
-->
"""


class ReleaseNotesTest(unittest.TestCase):
    def notes(self, version: str, text: str = CHANGELOG) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "CHANGELOG.md"
            path.write_text(text, encoding="utf-8")
            return subprocess.run(["bash", str(SCRIPT), version, str(path)], capture_output=True, text=True)

    def test_takes_exactly_one_section(self) -> None:
        proc = self.notes("0.2.0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "### Đã thêm\n- Tính năng của 0.2.0.\n\n### Đã sửa lỗi\n- Lỗi của 0.2.0.\n")

    def test_last_section_stops_before_template_comment(self) -> None:
        proc = self.notes("0.1.0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "### Đã thêm\n- Khung dự án.\n")

    def test_template_heading_in_comment_is_not_a_release(self) -> None:
        proc = self.notes("0.3.0")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertIn("chưa có mục '## [0.3.0]'", proc.stderr)

    def test_missing_or_heading_only_section_fails(self) -> None:
        self.assertEqual(self.notes("0.9.0").returncode, 1)
        empty = CHANGELOG.replace("- Tính năng của 0.2.0.\n", "").replace("- Lỗi của 0.2.0.\n", "")
        self.assertEqual(self.notes("0.2.0", empty).returncode, 1)

    def test_version_dots_are_literal(self) -> None:
        # "0.2.0" không được khớp "0a2b0"; "0.1.1" không được khớp mục "0.1.10"
        odd = CHANGELOG.replace("## [0.2.0]", "## [0a2b0]").replace("## [0.1.0]", "## [0.1.10]")
        self.assertEqual(self.notes("0.2.0", odd).returncode, 1)
        self.assertEqual(self.notes("0.1.1", odd).returncode, 1)


if __name__ == "__main__":
    unittest.main()
