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

"""Trang Release của một phiên bản (.github/workflows/release.yml gọi): dòng chỉ gói chính thức, phần tóm tắt viết
ngay dưới tiêu đề "## [X.Y.Z]" của CHANGELOG.md (nếu có), rồi toàn bộ ghi chép thay đổi gập trong <details> — trang
ngắn, ai cần thì bấm mở.

- GitHub tự gắn "Source code (zip)" vào mọi Release và không gỡ được, mà PoF #3 trừ điểm định dạng không mở: dòng đầu
  chỉ rõ gói của đội là moc-X.Y.Z.tar.gz, kèm tên tệp SBOM CycloneDX moc-X.Y.Z.cdx.json (make sbom).
- Mô tả Release hiện mỗi dấu xuống dòng thành một dòng mới: dòng tiếp nối của một đoạn hay một gạch đầu dòng
  (CHANGELOG ngắt dòng ở 120 ký tự) được nối lại. Liên kết tương đối trỏ về tệp ở thẻ vX.Y.Z.
- Mục lấy bằng scripts/release-notes.sh: thiếu mục, hay mục không có dòng thay đổi nào, thì lỗi như release.sh.

  python3 scripts/release_body.py 1.1.0 [CHANGELOG.md] > notes.md
  gh release edit v1.1.0 --notes-file notes.md                       # sửa tay trang Release đã đăng
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# dòng mở khối mới, không nối vào dòng trước: gạch đầu dòng, tiêu đề, thẻ HTML, bảng
BLOCK = re.compile(r"^\s*(?:[-*+] |\d+[.)] |#|<|\|)")
ITEM = re.compile(r"^[-*+] ")
LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)\s]+)\)")


def unwrap(text: str) -> str:
    """Nối dòng tiếp nối vào dòng trước nó; dòng trống, tiêu đề, gạch đầu dòng mới giữ nguyên."""
    lines: list[str] = []
    for line in text.splitlines():
        prev = lines[-1] if lines else ""
        if prev.strip() and not prev.lstrip().startswith("#") and line.strip() and not BLOCK.match(line):
            lines[-1] = f"{prev} {line.strip()}"
        else:
            lines.append(line.rstrip())
    return "\n".join(lines)


def body(version: str, notes: str, repo_url: str) -> str:
    """Nội dung trang Release từ `notes` — phần dưới tiêu đề "## [X.Y.Z]" như release-notes.sh in ra."""
    notes = LINK.sub(lambda m: f"]({repo_url}/blob/v{version}/{m[1]})", notes)
    lines = notes.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith("### ")), len(lines))
    summary, changes = "\n".join(lines[:first]).strip(), "\n".join(lines[first:]).strip()
    parts = [f'**Gói phát hành chính thức: `moc-{version}.tar.gz`** (định dạng mở), kiểm bằng '
             f'`sha256sum -c moc-{version}.tar.gz.sha256`; danh mục thành phần kèm giấy phép (SBOM CycloneDX): '
             f'`moc-{version}.cdx.json`. "Source code (zip)" và "Source code (tar.gz)" do GitHub tự gắn vào mọi bản '
             'phát hành, không phải gói của đội.']
    if summary:
        parts.append(unwrap(summary))
    if changes:
        items = sum(1 for line in lines[first:] if ITEM.match(line))
        # dòng trống sau <summary> và trước </details>: không có thì GitHub không dựng markdown bên trong
        parts.append(f"<details>\n<summary>Toàn bộ ghi chép thay đổi của {version} ({items} mục)</summary>\n\n"
                     f"{unwrap(changes)}\n\n</details>")
    return "\n\n".join(parts) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("Sử dụng: release_body.py <phiên-bản> [CHANGELOG.md]", file=sys.stderr)
        return 2
    version = argv[1]
    changelog = argv[2] if len(argv) == 3 else str(ROOT / "CHANGELOG.md")
    proc = subprocess.run([str(ROOT / "scripts" / "release-notes.sh"), version, changelog], capture_output=True,
                          text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return 1
    repo_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                f"{os.environ.get('GITHUB_REPOSITORY', 'HIT-Champion/HVL')}")
    sys.stdout.buffer.write(body(version, proc.stdout, repo_url).encode())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
