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

"""Ghi chú phát hành (scripts/release-notes.sh, dùng ở release.sh và .github/workflows/release.yml): lấy đúng mục
"## [X.Y.Z]" của CHANGELOG; khối mẫu trong chú thích HTML không tính; thiếu mục, hay mục chỉ có tiêu đề nhóm, thì
lỗi chứ không ra ghi chú rỗng. Không phát hành lại: release.sh dừng trước khi gắn khi thẻ đã có trên origin hay ở máy,
không hỏi được origin cũng dừng; release.yml dừng khi thẻ đã có Release, kể cả nháp (chạy lệnh của bước với gh giả), và
báo lỗi khi action không tải lên đủ hai tệp. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "release-notes.sh"
RELEASE = SCRIPT.parent / "release.sh"
WORKFLOW = SCRIPT.parent.parent / ".github" / "workflows" / "release.yml"
# repo thử không đọc cấu hình git của máy (khóa ký thẻ, hook…), tên người gắn thẻ cố định; bỏ mọi GIT_* thừa hưởng —
# chạy từ hook git thì GIT_DIR, GIT_INDEX_FILE trỏ về repo thật và lệnh git của test sẽ ghi vào đó
GIT_ENV = {
    **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "thu",
    "GIT_AUTHOR_EMAIL": "thu@example.invalid",
    "GIT_COMMITTER_NAME": "thu",
    "GIT_COMMITTER_EMAIL": "thu@example.invalid",
}

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


class NoReReleaseTest(unittest.TestCase):
    """release.sh trên một repo tạm có origin là repo bare cục bộ."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        self.repo = root / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(RELEASE, self.repo / "scripts" / "release.sh")
        shutil.copy(SCRIPT, self.repo / "scripts" / "release-notes.sh")
        (self.repo / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
        (self.repo / ".gitignore").write_text("dist/\n", encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-qm", "khởi tạo")
        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)], env=GIT_ENV, check=True)
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "-q", "origin", "main")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, env=GIT_ENV, capture_output=True, text=True,
                              check=True).stdout

    def release(self, version: str = "0.2.0") -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "scripts/release.sh", version], cwd=self.repo, env=GIT_ENV,
                              capture_output=True, text=True)

    def assert_nothing_made(self, proc: subprocess.CompletedProcess[str], message: str) -> None:
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn(message, proc.stderr)
        self.assertFalse((self.repo / "dist").exists())

    def test_new_version_is_tagged_and_packed(self) -> None:
        proc = self.release()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.git("tag", "-l").split(), ["v0.2.0"])
        self.assertTrue((self.repo / "dist" / "moc-0.2.0.tar.gz").is_file())
        self.assertTrue((self.repo / "dist" / "moc-0.2.0.tar.gz.sha256").is_file())

    def test_tag_already_on_origin_stops_before_tagging(self) -> None:
        # thẻ đã đẩy từ máy khác: máy này chưa có, gắn được thẻ cục bộ nhưng đẩy lên sẽ là phát hành lại
        self.git("tag", "-a", "v0.2.0", "-m", "đã phát hành")
        self.git("push", "-q", "origin", "v0.2.0")
        self.git("tag", "-d", "v0.2.0")
        self.assert_nothing_made(self.release(), "đã có trên origin")
        self.assertEqual(self.git("tag", "-l"), "")

    def test_local_tag_stops(self) -> None:
        # lần trước gắn thẻ rồi dừng giữa chừng: chưa đẩy, gợi ý gỡ thẻ chứ không bảo lên phiên bản
        self.git("tag", "-a", "v0.2.0", "-m", "gắn dở")
        proc = self.release()
        self.assert_nothing_made(proc, "đã có ở máy này nhưng chưa đẩy lên origin")
        self.assertIn("git tag -d v0.2.0", proc.stderr)

    def test_tag_on_both_sides_is_released(self) -> None:
        self.git("tag", "-a", "v0.2.0", "-m", "đã phát hành")
        self.git("push", "-q", "origin", "v0.2.0")
        self.assert_nothing_made(self.release(), "đã có trên origin")

    def test_unreachable_origin_stops(self) -> None:
        self.git("remote", "set-url", "origin", str(self.origin.parent / "khong-co.git"))
        self.assert_nothing_made(self.release(), "không hỏi được origin")
        self.assertEqual(self.git("tag", "-l"), "")

    def test_without_origin_still_releases(self) -> None:
        # gói nguồn giải nén rồi git init (không có remote): không có gì để kiểm, vẫn phát hành được
        self.git("remote", "remove", "origin")
        self.assertEqual(self.release().returncode, 0)

    def test_other_version_is_not_blocked(self) -> None:
        self.git("tag", "-a", "v0.1.0", "-m", "bản cũ")
        self.git("push", "-q", "origin", "v0.1.0")
        self.assertEqual(self.release("0.2.0").returncode, 0)


def step_script(name: str) -> str:
    """Khối `run: |` của bước `name` trong release.yml, bỏ thụt lề (không có PyYAML)."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    i = lines.index(f"      - name: {name}")
    while lines[i].strip() != "run: |":
        i += 1
    indent = len(lines[i]) - len(lines[i].lstrip()) + 2
    body = []
    for line in lines[i + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body).strip() + "\n"


# gh giả: chỉ hiểu `gh api … --jq <bộ lọc>`, áp bộ lọc lên danh sách Release trong $FAKE_RELEASES như gh --jq
FAKE_GH = """#!/usr/bin/env bash
[ -z "${FAKE_GH_FAIL:-}" ] || { echo "gh: $FAKE_GH_FAIL" >&2; exit 1; }
echo "$*" >> "$FAKE_GH_CALLS"
while [ $# -gt 0 ]; do [ "$1" = --jq ] && filter="$2"; shift; done
jq -r "$filter" "$FAKE_RELEASES"
"""


@unittest.skipUnless(shutil.which("jq"), "cần jq (runner ubuntu của GitHub có sẵn)")
class WorkflowNoReReleaseTest(unittest.TestCase):
    """release.yml: chạy thật lệnh của bước "Chặn phát hành lại" (bash -e như runner) với gh giả, và bước kiểm gói."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        (self.dir / "gh").write_text(FAKE_GH, encoding="utf-8")
        (self.dir / "gh").chmod(0o755)

    def guard(self, releases: list[dict], fail: str = "") -> subprocess.CompletedProcess[str]:
        (self.dir / "releases.json").write_text(json.dumps(releases), encoding="utf-8")
        env = {**os.environ, "PATH": f"{self.dir}:{os.environ['PATH']}", "GITHUB_REPOSITORY": "HIT-Champion/HVL",
               "GITHUB_REF_NAME": "v0.2.0", "FAKE_RELEASES": str(self.dir / "releases.json"),
               "FAKE_GH_CALLS": str(self.dir / "calls"), "FAKE_GH_FAIL": fail}
        return subprocess.run(["bash", "-e", "-c", step_script("Chặn phát hành lại")], env=env, capture_output=True,
                              text=True)

    @staticmethod
    def release(tag: str, draft: bool = False) -> dict:
        return {"tag_name": tag, "draft": draft, "html_url": f"https://github.com/HIT-Champion/HVL/releases/{tag}"}

    def test_new_tag_passes_and_lists_every_page(self) -> None:
        proc = self.guard([self.release("v0.1.0"), self.release("v0.2.0-rc.1", draft=True), self.release("v0.2.00")])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        calls = (self.dir / "calls").read_text(encoding="utf-8")
        self.assertIn("--paginate", calls)
        self.assertIn("repos/HIT-Champion/HVL/releases?per_page=100", calls)

    def test_published_release_stops(self) -> None:
        proc = self.guard([self.release("v0.1.0"), self.release("v0.2.0")])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("::error::v0.2.0 đã có Release (đã đăng https://github.com/HIT-Champion/HVL/releases/v0.2.0)",
                      proc.stdout)

    def test_draft_left_by_deleted_tag_stops(self) -> None:
        # xóa thẻ của Release đã đăng → GitHub chuyển Release thành nháp; releases/tags/<thẻ> không thấy nháp
        proc = self.guard([self.release("v0.2.0", draft=True)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("(nháp https://", proc.stdout)

    def test_gh_error_stops(self) -> None:
        proc = self.guard([], fail="HTTP 502")
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((self.dir / "calls").exists())

    def test_guard_runs_before_release_action(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        guard = text.index("name: Chặn phát hành lại")
        self.assertLess(guard, text.index("name: Sinh gói nguồn .tar.gz"))
        self.assertLess(guard, text.index("softprops/action-gh-release@"))

    def assets(self, value: str | None) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k != "ASSETS"} | ({} if value is None else {"ASSETS": value})
        return subprocess.run(["bash", "-e", "-c", step_script("Kiểm gói đã tải lên")], env=env, capture_output=True,
                              text=True)

    def test_upload_check_needs_both_files(self) -> None:
        self.assertEqual(self.assets('[{"name": "moc-0.2.0.tar.gz"}, {"name": "moc-0.2.0.tar.gz.sha256"}]')
                         .returncode, 0)
        skipped = self.assets('[{"name": "moc-0.2.0.tar.gz.sha256"}]')
        self.assertEqual(skipped.returncode, 1)
        self.assertIn("Chỉ tải lên 1/2 tệp", skipped.stdout)
        self.assertEqual(self.assets(None).returncode, 1)

    def test_action_does_not_overwrite_assets(self) -> None:
        action = WORKFLOW.read_text(encoding="utf-8").split("softprops/action-gh-release@", 1)[1]
        self.assertIn("overwrite_files: false", action)
        self.assertIn("fail_on_unmatched_files: true", action)
        self.assertIn("ASSETS: ${{ steps.gh_release.outputs.assets }}", action)


if __name__ == "__main__":
    unittest.main()
