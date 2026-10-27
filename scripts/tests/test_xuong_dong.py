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

"""Xuống dòng LF ở mọi bản checkout (#244). Git for Windows mặc định core.autocrlf=true: thiếu `eol=lf` trong
.gitattributes thì mọi tệp chữ ra CRLF, script .sh hỏng ở "#!/bin/sh\\r" trong container Linux, test đọc nguồn của Văn
phòng, Không gian cá nhân hỏng (#230). Giả lập checkout trên Windows bằng `git cat-file --filters` với
core.autocrlf=true, không cần máy Windows. Gói phát hành không có .git thì bỏ qua.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WINDOWS = ("-c", "core.autocrlf=true", "-c", "core.eol=crlf")


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *WINDOWS, *args], input=data, capture_output=True,
                          check=True).stdout


def tracked() -> dict[str, str]:
    """Tệp đang theo dõi → kiểu xuống dòng trong index (lf, crlf, mixed, none; -text là tệp nhị phân)."""
    kinds = {}
    for entry in git("ls-files", "--eol", "-z").split(b"\0"):
        if entry:
            info, _, path = entry.decode().partition("\t")
            kinds[path] = info.split()[0].removeprefix("i/")
    return kinds


def attrs(paths: list[str], *names: str) -> dict[str, dict[str, str]]:
    """Giá trị thuộc tính git của từng tệp (set, unset, unspecified hay giá trị như auto, lf)."""
    out = git("check-attr", "-z", "--stdin", *names, data=b"".join(p.encode() + b"\0" for p in paths)).split(b"\0")
    values: dict[str, dict[str, str]] = {}
    for i in range(0, len(out) - 2, 3):
        path, name, value = (part.decode() for part in out[i:i + 3])
        values.setdefault(path, {})[name] = value
    return values


@unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "không phải bản checkout git (gói phát hành)")
class LineEndingTest(unittest.TestCase):
    def test_text_files_check_out_with_lf(self) -> None:
        kinds = tracked()
        self.assertEqual([p for p, kind in kinds.items() if kind in ("crlf", "mixed")], [], "index có tệp CRLF")
        text = [p for p, kind in kinds.items() if kind != "-text"]
        self.assertGreater(len(text), 500)
        wrong = [p for p, a in attrs(text, "text", "eol").items() if a["eol"] != "lf" or a["text"] != "auto"]
        self.assertEqual(wrong, [], ".gitattributes: thiếu '* text=auto eol=lf' hay có dòng đè lên")

    def test_binary_files_are_never_converted(self) -> None:
        binary = [p for p, kind in tracked().items() if kind == "-text"]
        self.assertTrue(binary)
        loose = [p for p, a in attrs(binary, "text").items() if a["text"] != "unset"]
        self.assertEqual(loose, [], "tệp nhị phân chưa khai: thêm '*.<đuôi> binary' vào .gitattributes")

    def test_windows_checkout_keeps_lf(self) -> None:
        for path in ("scripts/install.sh", "platform/apisix/kiem-moi-truong.sh", "Makefile", "docker-compose.yml",
                     "apps/office/app/utils/errors.ts", "apps/ca-nhan/public/app.js"):
            with self.subTest(path=path):
                content = git("cat-file", "--filters", f":{path}")
                self.assertIn(b"\n", content)
                self.assertNotIn(b"\r", content)


if __name__ == "__main__":
    unittest.main()
