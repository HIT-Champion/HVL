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

"""Quy trình Git (docs/git_flow.md): scripts/check_pr.py kiểm nhánh nguồn và tiêu đề PR, main chỉ nhận PR phát hành từ
develop hoặc hotfix/X.Y.Z có mục CHANGELOG và thẻ chưa có; release.yml dừng khi thẻ không nằm trên main (chạy thật lệnh
của bước trong một repo thử). Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = SCRIPTS.parent / ".github" / "workflows" / "release.yml"
spec = importlib.util.spec_from_file_location("check_pr", SCRIPTS / "check_pr.py")
check_pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_pr)

# repo thử không đọc cấu hình git của máy; bỏ mọi GIT_* thừa hưởng (chạy từ hook git thì chúng trỏ về repo thật)
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

Một dòng nhắc tới `<!--` trong chữ không mở khối chú thích.

## [Chưa phát hành]

## [0.2.0] - 2026-10-30

### Đã thêm
- Tính năng của 0.2.0.

## [0.1.0] - 2026-10-18

### Đã thêm
- Khung dự án.

<!-- Mẫu cho bản phát hành kế tiếp:
## [0.3.0] - YYYY-MM-DD
-->
"""
FEATURE_BODY = "Thêm bước duyệt.\n\nCloses #12\n"


def run(base: str, head: str, title: str, body: str = FEATURE_BODY, changelog: str = CHANGELOG,
        tags: tuple[str, ...] = ("v0.1.0",), notes: bool = True) -> tuple[list[str], list[str]]:
    return check_pr.check(base, head, title, body, changelog, lambda tag: tag in tags, lambda version: notes)


class TitleTest(unittest.TestCase):
    def test_conventional_titles_pass(self) -> None:
        for title in ("feat(workflow): thêm bước giám đốc duyệt khi số tiền vượt ngưỡng",
                      "fix: chặn tệp khi ClamAV không phản hồi", "docs(scripts): ghi cách chạy check_pr",
                      "feat(auth)!: bỏ client moc-cli"):
            with self.subTest(title=title):
                self.assertEqual(check_pr.title_errors(title), [])

    def test_bad_titles_say_why(self) -> None:
        cases = {
            "cập nhật": "không theo dạng",
            "feature(office): thêm nút": "Loại 'feature'",
            "feat(ui): thêm nút": "Phạm vi 'ui'",
            "feat(): thêm nút": "Phạm vi ''",
            "fix(office): sửa nút Duyệt.": "dấu chấm",
            "feat(office): " + "thêm " * 12: "tối đa 72",
        }
        for title, reason in cases.items():
            with self.subTest(title=title):
                self.assertIn(reason, " | ".join(check_pr.title_errors(title)))

    def test_length_counts_vietnamese_letters_not_bytes(self) -> None:
        title = "feat(office): " + "ữ" * 58      # 72 ký tự, hơn 72 byte
        self.assertEqual(len(title), 72)
        self.assertEqual(check_pr.title_errors(title), [])


class DevelopTest(unittest.TestCase):
    def test_feature_branch_with_issue_passes(self) -> None:
        self.assertEqual(run("develop", "feat/12-keycloak-realm", "feat(auth): thêm realm Keycloak"), ([], []))

    def test_branch_name_needs_type_and_plain_letters(self) -> None:
        for head in ("hoang-test", "feature-moi", "fix/sửa-lỗi-quét-virus", "feature/12-x", "Feat/12-x"):
            with self.subTest(head=head):
                errors, _ = run("develop", head, "fix(files): chặn tệp khi ClamAV không phản hồi")
                self.assertIn("không đúng dạng", " | ".join(errors))

    def test_missing_issue_link_only_warns(self) -> None:
        errors, warnings = run("develop", "docs/sua-chinh-ta", "docs: sửa chính tả README", body="")
        self.assertEqual(errors, [])
        self.assertIn("Closes #", warnings[0])

    def test_refs_also_links_the_issue(self) -> None:
        self.assertEqual(run("develop", "docs/12-api", "docs: ghi API", body="Refs #12")[1], [])

    def test_back_merge_from_main_is_allowed(self) -> None:
        self.assertEqual(run("develop", "main", "chore(release): gộp ngược v0.2.1 vào develop", body=""), ([], []))


class MainTest(unittest.TestCase):
    def test_release_from_develop_passes(self) -> None:
        self.assertEqual(run("main", "develop", "chore(release): v0.2.0", body=""), ([], []))

    def test_feature_branch_cannot_target_main(self) -> None:
        errors, _ = run("main", "feat/12-keycloak-realm", "feat(auth): thêm realm Keycloak")
        self.assertIn("đổi nhánh đích", " | ".join(errors))

    def test_release_title_must_name_the_changelog_version(self) -> None:
        errors, _ = run("main", "develop", "chore(release): v0.3.0")
        self.assertIn("'chore(release): v0.2.0'", " | ".join(errors))

    def test_already_released_version_is_refused(self) -> None:
        errors, _ = run("main", "develop", "chore(release): v0.2.0", tags=("v0.1.0", "v0.2.0"))
        self.assertIn("Thẻ v0.2.0 đã có", " | ".join(errors))

    def test_version_without_entries_is_refused(self) -> None:
        errors, _ = run("main", "develop", "chore(release): v0.2.0", notes=False)
        self.assertIn("chưa có dòng thay đổi", " | ".join(errors))

    def test_no_version_section_is_refused(self) -> None:
        changelog = "# Nhật ký thay đổi\n\n## [Chưa phát hành]\n\n- Việc mới.\n"
        errors, _ = run("main", "develop", "chore(release): v0.2.0", changelog=changelog)
        self.assertIn("chưa có mục '## [X.Y.Z]", " | ".join(errors))

    def test_template_in_comment_is_not_a_version(self) -> None:
        changelog = "## [Chưa phát hành]\n\n<!--\n## [0.9.0] - 2026-10-xx\n-->\n"
        self.assertIsNone(check_pr.latest_version(changelog))
        self.assertEqual(check_pr.latest_version(CHANGELOG), "0.2.0")

    def test_hotfix_version_must_match_changelog(self) -> None:
        changelog = CHANGELOG.replace("## [0.2.0]", "## [0.2.1] - 2026-11-02\n\n### Đã sửa lỗi\n- Lỗi gấp.\n\n## [0.2.0]")
        tags = ("v0.1.0", "v0.2.0")
        self.assertEqual(run("main", "hotfix/0.2.1", "chore(release): v0.2.1", changelog=changelog, tags=tags),
                         ([], []))
        errors, _ = run("main", "hotfix/0.2.2", "chore(release): v0.2.1", changelog=changelog, tags=tags)
        self.assertIn("Nhánh hotfix/0.2.2", " | ".join(errors))


class MainEntryTest(unittest.TestCase):
    """Chạy check_pr.py như workflow pr.yml: đọc biến môi trường, in chú thích ::error:: / ::warning::."""

    def entry(self, **env: str) -> subprocess.CompletedProcess[str]:
        clean = {k: v for k, v in os.environ.items() if k not in ("GITHUB_BASE_REF", "GITHUB_HEAD_REF")}
        return subprocess.run([sys.executable, str(SCRIPTS / "check_pr.py")], env={**clean, **env},
                              capture_output=True, text=True)

    def test_not_a_pull_request_is_skipped(self) -> None:
        proc = self.entry()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("bỏ qua", proc.stdout)

    def test_errors_and_warnings_become_annotations(self) -> None:
        proc = self.entry(GITHUB_BASE_REF="develop", GITHUB_HEAD_REF="hoang-test", PR_TITLE="update", PR_BODY="")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("::error::Tiêu đề PR không theo dạng", proc.stdout)
        self.assertIn("::error::Nhánh nguồn 'hoang-test'", proc.stdout)
        self.assertIn("::warning::Mô tả PR chưa có", proc.stdout)

    def test_title_is_normalised_before_counting(self) -> None:
        decomposed = "feat(office): " + "ữ" * 58      # "ữ" viết tách dấu: 174 điểm mã, 72 ký tự sau NFC
        proc = self.entry(GITHUB_BASE_REF="develop", GITHUB_HEAD_REF="feat/1-x", PR_TITLE=decomposed,
                          PR_BODY="Closes #1")
        self.assertEqual(proc.returncode, 0, proc.stdout)


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


class TagOnMainTest(unittest.TestCase):
    """release.yml, bước "Thẻ nằm trên main": thẻ trên main (kể cả thẻ có chú thích) qua, thẻ trên develop dừng."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("commit", "-q", "--allow-empty", "-m", "chore(release): v0.2.0")
        self.git("tag", "-a", "v0.2.0", "-m", "Signet 0.2.0")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("switch", "-q", "-c", "develop")
        self.git("commit", "-q", "--allow-empty", "-m", "feat: việc chưa phát hành")
        self.git("tag", "v0.3.0")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, env=GIT_ENV, check=True, capture_output=True)

    def step(self, tag: str) -> subprocess.CompletedProcess[str]:
        env = {**GIT_ENV, "GITHUB_REF": f"refs/tags/{tag}", "GITHUB_REF_NAME": tag}
        return subprocess.run(["bash", "-e", "-c", step_script("Thẻ nằm trên main")], cwd=self.repo, env=env,
                              capture_output=True, text=True)

    def test_tag_on_main_passes(self) -> None:
        proc = self.step("v0.2.0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_tag_off_main_stops(self) -> None:
        proc = self.step("v0.3.0")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("::error::Thẻ v0.3.0 không nằm trên main", proc.stdout)


if __name__ == "__main__":
    unittest.main()
