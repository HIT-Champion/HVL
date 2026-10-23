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

"""Kiểm một pull request theo docs/git_flow.md (workflow .github/workflows/pr.yml).

- Tiêu đề theo Conventional Commits, loại và phạm vi trong danh sách của mục 3, tối đa 72 ký tự, không chấm cuối: gộp
  bằng squash thì tiêu đề PR thành dòng đầu của commit trên develop.
- PR vào develop: nhánh nguồn `<loại>/<mô-tả>` chữ thường không dấu, hoặc `main` (gộp ngược sau bản vá nóng). Mô tả
  thiếu `Closes #N` / `Refs #N` thì chỉ nhắc: sửa chính tả, tài liệu nhỏ không cần issue.
- PR vào main chỉ để phát hành: nguồn là develop hoặc hotfix/X.Y.Z, tiêu đề `chore(release): vX.Y.Z` với X.Y.Z là mục
  phiên bản trên cùng của CHANGELOG.md, mục đó có dòng thay đổi (scripts/release-notes.sh) và thẻ vX.Y.Z chưa có.

Đọc GITHUB_BASE_REF, GITHUB_HEAD_REF (Actions tự đặt cho sự kiện pull_request), PR_TITLE, PR_BODY. Chạy tay:
  GITHUB_BASE_REF=develop GITHUB_HEAD_REF=feat/12-keycloak-realm PR_TITLE='feat(auth): …' python3 scripts/check_pr.py
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import unicodedata
from collections.abc import Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent
TYPES = ("feat", "fix", "perf", "refactor", "docs", "test", "build", "ci", "chore", "revert")
# docs/git_flow.md mục 3.3 — thêm phạm vi thì thêm ở cả hai nơi
SCOPES = ("gateway", "auth", "db", "workflow", "files", "realtime", "office", "ai", "data", "ops", "cli", "scripts",
          "e2e", "ci", "deps", "docs", "release")
MAX_TITLE = 72
TITLE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^()]*)\))?!?: \S")
BRANCH = re.compile(r"^(?P<type>[a-z]+)/[a-z0-9][a-z0-9.-]*$")
HOTFIX = re.compile(r"^hotfix/(?P<version>\d+\.\d+\.\d+)$")
VERSION_HEAD = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]")
ISSUE_REF = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs)\s+#\d+", re.IGNORECASE)


def latest_version(changelog: str) -> str | None:
    """Mục phiên bản trên cùng của CHANGELOG; khối chú thích HTML (mẫu cho bản kế tiếp) không tính."""
    comment = False
    for line in changelog.splitlines():
        if line.lstrip().startswith("<!--"):
            comment = True
        if comment:
            comment = "-->" not in line
            continue
        if m := VERSION_HEAD.match(line):
            return m["version"]
    return None


def title_errors(title: str) -> list[str]:
    errors = []
    if len(title) > MAX_TITLE:
        errors.append(f"Tiêu đề PR dài {len(title)} ký tự, tối đa {MAX_TITLE}")
    if title.endswith("."):
        errors.append("Tiêu đề PR không kết thúc bằng dấu chấm")
    m = TITLE.match(title)
    if m is None:
        errors.append("Tiêu đề PR không theo dạng '<loại>(<phạm vi>): <mô tả>' — docs/git_flow.md mục 3")
        return errors
    if m["type"] not in TYPES:
        errors.append(f"Loại '{m['type']}' không có trong danh sách: {', '.join(TYPES)}")
    if m["scope"] is not None and m["scope"] not in SCOPES:
        errors.append(f"Phạm vi '{m['scope']}' không có trong danh sách: {', '.join(SCOPES)} — docs/git_flow.md mục 3.3")
    return errors


def release_errors(head: str, title: str, changelog: str, tag_exists: Callable[[str], bool],
                   notes_ok: Callable[[str], bool]) -> list[str]:
    hotfix = HOTFIX.match(head)
    if head != "develop" and hotfix is None:
        return [f"main chỉ nhận PR phát hành từ develop hoặc hotfix/X.Y.Z, không nhận từ '{head}' — đổi nhánh đích "
                "của PR sang develop"]
    version = latest_version(changelog)
    if version is None:
        return ["CHANGELOG.md chưa có mục '## [X.Y.Z] - <ngày>' cho bản phát hành — chuyển các dòng của mục "
                "[Chưa phát hành] sang đó (docs/git_flow.md mục 6)"]
    errors = []
    if hotfix is not None and hotfix["version"] != version:
        errors.append(f"Nhánh {head} nhưng mục phiên bản trên cùng của CHANGELOG.md là [{version}]")
    if title != f"chore(release): v{version}":
        errors.append(f"PR phát hành đặt tiêu đề 'chore(release): v{version}'")
    if tag_exists(f"v{version}"):
        errors.append(f"Thẻ v{version} đã có (đã phát hành) — thêm mục phiên bản mới vào CHANGELOG.md")
    elif not notes_ok(version):
        errors.append(f"Mục [{version}] của CHANGELOG.md chưa có dòng thay đổi nào (scripts/release-notes.sh)")
    return errors


def check(base: str, head: str, title: str, body: str, changelog: str, tag_exists: Callable[[str], bool],
          notes_ok: Callable[[str], bool]) -> tuple[list[str], list[str]]:
    """(lỗi, nhắc nhở) của một PR từ `head` vào `base`."""
    errors = title_errors(title)
    warnings = []
    if base == "main":
        errors += release_errors(head, title, changelog, tag_exists, notes_ok)
    elif base == "develop" and head != "main":
        m = BRANCH.match(head)
        if m is None or m["type"] not in TYPES:
            errors.append(f"Nhánh nguồn '{head}' không đúng dạng <loại>/<số-issue>-<mô-tả> (chữ thường, không dấu; "
                          f"loại: {', '.join(TYPES)}) — docs/git_flow.md mục 2")
        if not ISSUE_REF.search(body):
            warnings.append("Mô tả PR chưa có 'Closes #<số-issue>' hay 'Refs #<số-issue>' (bỏ qua được với sửa chính "
                            "tả, tài liệu nhỏ)")
    return errors, warnings


def tag_exists(tag: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
                          capture_output=True, check=False).returncode == 0


def notes_ok(version: str) -> bool:
    return subprocess.run([str(ROOT / "scripts" / "release-notes.sh"), version, str(ROOT / "CHANGELOG.md")],
                          capture_output=True, check=False).returncode == 0


def main() -> int:
    base = os.environ.get("GITHUB_BASE_REF", "")
    head = os.environ.get("GITHUB_HEAD_REF", "")
    if not base or not head:
        print("Không phải pull request (thiếu GITHUB_BASE_REF, GITHUB_HEAD_REF): bỏ qua")
        return 0
    title = unicodedata.normalize("NFC", os.environ.get("PR_TITLE", "").strip())
    body = os.environ.get("PR_BODY", "")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    errors, warnings = check(base, head, title, body, changelog, tag_exists, notes_ok)
    for warning in warnings:
        print(f"::warning::{warning}")
    for error in errors:
        print(f"::error::{error}")
    if not errors:
        print(f"PR {head} → {base}: đúng quy trình")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
