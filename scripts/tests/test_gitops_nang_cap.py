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

"""GitOps chế độ nang-cap (scripts/reconcile.py, MOC_GITOPS_MODE=nang-cap, #344): repo git thật trong thư mục tạm,
nhánh deploy là commit gộp `deploy vX.Y.Z` như docs/van-hanh.md; scripts/nang_cap.sh trong repo là bản giả ghi lại
lệnh được gọi. Kiểm: lượt đầu nhận bản đang chạy khi cây trùng thẻ (không gọi nang); MOC_GITOPS_FOLLOW=release chỉ
nâng khi có thẻ vX.Y.Z mới trên nhánh (bỏ qua commit chưa gắn thẻ, bản -rc, thẻ ngoài nhánh) và kiểm chữ ký của thẻ;
nâng gọi `nang` với đúng phiên
bản thẻ; lỗi sau khi sao lưu thì gọi `lui` với mã nguồn commit cũ, .env lúc trước và đúng lượt sao lưu; lỗi trước
khi sao lưu thì không lùi; để trống MOC_GITOPS_MODE thì vẫn đi đường install.sh cũ; `moc backup` gọi từ reconciler
(MOC_OPS_LOCKED=1) không đợi khóa reconciler đang giữ, lệnh khác vẫn đợi. Không cần Docker. Chạy: python3
-m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import fcntl
import importlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reconcile_nang_cap", SCRIPTS / "reconcile.py")
reconcile: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)

# nang_cap.sh giả: ghi "<lệnh> <tham số> | MOC_VERSION | MOC_OPS_LOCKED | tệp đánh dấu của mã nguồn" vào $GHI_LAI;
# `nang` in dòng lượt sao lưu khi có $LUOT_GIA, thoát $THOAT_NANG; `lui` thoát $THOAT_LUI
FAKE_NANG_CAP = """#!/bin/sh
src=$(cd "$(dirname "$0")/.." && pwd)
[ "$1" = lui ] && src=$3
echo "$* | $MOC_VERSION | ${MOC_OPS_LOCKED:-} | $(cat "$src/BAN" 2>/dev/null) | $(cat "$src/.env" 2>/dev/null)" \\
  >> "$GHI_LAI"
case "$1" in
  nang) [ -z "${LUOT_GIA:-}" ] || echo "lượt sao lưu $LUOT_GIA; .env lúc trước: x"; exit "${THOAT_NANG:-0}" ;;
  lui) exit "${THOAT_LUI:-0}" ;;
esac
"""


@unittest.skipUnless(shutil.which("git") and shutil.which("tar"), "cần git, tar")
class UpgradeModeTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        config = self.tmp / "gitconfig"
        config.write_text("", encoding="utf-8")
        self.calls = self.tmp / "goi.txt"
        env = {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false", "GHI_LAI": str(self.calls),
               "LUOT_GIA": "", "THOAT_NANG": "0", "THOAT_LUI": "0"}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])

        self.origin = self.tmp / "origin"
        self.git(self.tmp, "init", "-q", "-b", "develop", str(self.origin))
        (self.origin / "scripts").mkdir()
        (self.origin / "scripts" / "nang_cap.sh").write_text(FAKE_NANG_CAP, encoding="utf-8")
        self.release("1.0.0")
        self.git(self.origin, "switch", "-q", "-c", "deploy", "v1.0.0")
        self.deploy("1.0.0")

        self.root = self.tmp / "opt-moc"
        self.root.mkdir()
        (self.root / reconcile.MANIFEST).write_text("", encoding="utf-8")
        (self.root / ".env").write_text("BI_MAT=truoc\n", encoding="utf-8")
        self.installed("1.0.0")
        self.src = self.tmp / "moc-src"
        self.git(self.tmp, "clone", "-q", "-b", "deploy", str(self.origin), str(self.src))

        saved_attrs = {n: getattr(reconcile, n) for n in ("ROOT", "apply", "installed_files", "setting")}
        self.addCleanup(lambda: [setattr(reconcile, n, v) for n, v in saved_attrs.items()])
        reconcile.ROOT = self.root
        reconcile.installed_files = lambda: {}
        self.settings = {"MOC_GITOPS_DIR": str(self.src), "MOC_GITOPS_MODE": "nang-cap"}
        reconcile.setting = lambda name, default="": self.settings.get(name, default)
        self.applied: list[str] = []
        reconcile.apply = lambda git, src, target, previous: self.applied.append(target)

    def git(self, cwd: pathlib.Path, *args: str) -> str:
        return subprocess.run(["git", "-c", "user.name=nhap", "-c", "user.email=nhap@local", *args], cwd=cwd,
                              check=True, capture_output=True, text=True).stdout.strip()

    def release(self, version: str) -> None:
        """Commit trên develop (tệp BAN ghi phiên bản) rồi gắn thẻ vX.Y.Z, như một lần phát hành."""
        current = self.git(self.origin, "branch", "--show-current")
        if current != "develop":
            self.git(self.origin, "switch", "-q", "develop")
        (self.origin / "BAN").write_text(version, encoding="utf-8")
        self.git(self.origin, "add", "-A")
        self.git(self.origin, "commit", "-q", "-m", f"phát hành {version}")
        self.git(self.origin, "tag", "-a", f"v{version}", "-m", f"Signet {version}")
        if current != "develop":
            self.git(self.origin, "switch", "-q", current)

    def deploy(self, version: str) -> str:
        """Đưa thẻ lên nhánh deploy như docs/van-hanh.md: commit gộp --no-ff, cây trùng thẻ."""
        self.git(self.origin, "switch", "-q", "deploy")
        self.git(self.origin, "merge", "-q", "--no-ff", f"v{version}", "-m", f"deploy v{version}")
        return self.git(self.origin, "rev-parse", "HEAD")

    def installed(self, version: str) -> None:
        (self.root / "VERSION").write_text(f"Signet {version}\ncài lúc 2026-10-31\n", encoding="utf-8")

    def gitops(self) -> dict[str, Any]:
        report: dict[str, Any] = {"commit": None, "applied": None, "actions": [], "problems": []}
        with contextlib.redirect_stdout(io.StringIO()):
            reconcile.gitops(report)
        return report

    def recorded(self) -> list[list[str]]:
        if not self.calls.exists():
            return []
        return [[part.strip() for part in line.split("|")] for line in self.calls.read_text().splitlines()]

    def state(self) -> dict[str, Any]:
        return json.loads((self.src / ".git" / reconcile.STATE).read_text(encoding="utf-8"))

    def test_first_run_adopts_running_release_without_reinstalling(self) -> None:
        report = self.gitops()
        self.assertEqual(self.recorded(), [], "bản đang chạy đúng thẻ của deploy: không dừng trang để cài lại")
        self.assertIn("nhận bản đang chạy (Signet 1.0.0", report["actions"][0])
        self.assertEqual(self.state()["commit"], self.git(self.origin, "rev-parse", "deploy"))
        self.assertEqual(self.gitops()["actions"], [], "lượt sau: đã khớp, không làm gì")

    def test_first_run_upgrades_when_running_version_differs(self) -> None:
        self.installed("0.9.0")
        report = self.gitops()
        self.assertEqual([c[0] for c in self.recorded()], [f"nang {self.root}"])
        self.assertTrue(report["applied"])

    def test_upgrade_uses_release_version_of_deploy_merge(self) -> None:
        self.gitops()
        self.release("1.1.0")
        target = self.deploy("1.1.0")
        self.gitops()
        command, version, locked, ban, _env = self.recorded()[0]
        self.assertEqual(command, f"nang {self.root}")
        self.assertEqual(version, "1.1.0", "commit gộp deploy: MOC_VERSION là thẻ, không phải 1.1.0-1-g…")
        self.assertEqual((locked, ban), ("1", "1.1.0"))
        self.assertEqual(self.state()["commit"], target)

    def test_failure_after_backup_rolls_back_to_previous_commit(self) -> None:
        self.gitops()
        previous = self.state()["commit"]
        self.release("1.1.0")
        target = self.deploy("1.1.0")
        os.environ.update({"LUOT_GIA": "20261031-120000", "THOAT_NANG": "1"})
        with self.assertRaisesRegex(reconcile.ReconcileError, f"đã lùi về {previous[:12]}.*20261031-120000"):
            self.gitops()
        nang, lui = self.recorded()
        self.assertEqual(nang[0], f"nang {self.root}")
        old = self.src / ".git" / "moc-lui"
        self.assertEqual(lui, [f"lui {self.root} {old} 20261031-120000", "1.0.0", "1", "1.0.0", "BI_MAT=truoc"],
                         "lùi: mã nguồn commit cũ, phiên bản thẻ cũ, .env lúc trước, đúng lượt sao lưu")
        self.assertEqual(self.state().get("failed"), target, "không thử lại commit lỗi mỗi phút")
        self.assertEqual(self.state()["commit"], previous)
        self.assertIn("nang_cap.sh lui", (self.src / ".git" / reconcile.UPGRADE_LOG).read_text(encoding="utf-8"))

    def test_failure_before_backup_does_not_roll_back(self) -> None:
        self.gitops()
        self.release("1.1.0")
        self.deploy("1.1.0")
        os.environ["THOAT_NANG"] = "1"
        with self.assertRaisesRegex(reconcile.ReconcileError, "trước khi sao lưu, bản cũ vẫn chạy"):
            self.gitops()
        self.assertEqual([c[0].split()[0] for c in self.recorded()], ["nang"])

    def test_failed_rollback_is_reported(self) -> None:
        self.gitops()
        self.release("1.1.0")
        self.deploy("1.1.0")
        os.environ.update({"LUOT_GIA": "r1", "THOAT_NANG": "1", "THOAT_LUI": "1"})
        with self.assertRaisesRegex(reconcile.ReconcileError, "cũng lỗi"):
            self.gitops()

    def test_default_mode_keeps_install_path(self) -> None:
        self.settings["MOC_GITOPS_MODE"] = ""
        self.gitops()
        self.assertEqual(self.recorded(), [], "để trống MOC_GITOPS_MODE: không gọi nang_cap.sh")
        self.assertEqual(self.applied, [self.git(self.origin, "rev-parse", "deploy")], "không nhận bản đang chạy")

    def on_main(self, version: str, tag: str | None = None, key: pathlib.Path | None = None) -> str:
        """Commit trên main (tệp BAN), gắn thẻ nếu có — thẻ ký SSH bằng `key` nếu có."""
        self.git(self.origin, "switch", "-q", "main")
        (self.origin / "BAN").write_text(version, encoding="utf-8")
        self.git(self.origin, "add", "-A")
        self.git(self.origin, "commit", "-q", "-m", f"main {version}")
        if tag:
            sign = ["-c", "gpg.format=ssh", "-c", f"user.signingkey={key}", "tag", "-s"] if key else ["tag", "-a"]
            self.git(self.origin, *sign, tag, "-m", tag)
        return self.git(self.origin, "rev-parse", "HEAD")

    def follow_main(self) -> None:
        self.git(self.origin, "branch", "main", "v1.0.0")
        self.settings.update({"MOC_GITOPS_BRANCH": "main", "MOC_GITOPS_FOLLOW": "release"})

    def test_follow_release_applies_only_new_release_tags_on_branch(self) -> None:
        self.follow_main()
        self.assertIn("nhận bản đang chạy (Signet 1.0.0", self.gitops()["actions"][0])
        self.on_main("1.0.1-dev")                                       # commit chưa gắn thẻ
        self.on_main("1.1.0-rc.1", tag="v1.1.0-rc.1")                   # bản thử
        self.release("9.9.9")                                           # thẻ trên develop, chưa vào main
        self.assertEqual((self.gitops()["actions"], self.recorded()), ([], []),
                         "chưa có thẻ phát hành mới trên main: không nâng")
        target = self.on_main("1.1.0", tag="v1.1.0")
        report = self.gitops()
        command, version, _locked, ban, _env = self.recorded()[0]
        self.assertEqual((command, version, ban), (f"nang {self.root}", "1.1.0", "1.1.0"))
        self.assertIn("thẻ v1.1.0", report["applied"])
        self.assertEqual(self.state()["commit"], target)

    @unittest.skipUnless(shutil.which("ssh-keygen"), "cần ssh-keygen")
    def test_follow_release_checks_tag_signature(self) -> None:
        key = self.tmp / "khoa"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "phat-hanh", "-f", str(key)], check=True)
        pub = (self.tmp / "khoa.pub").read_text().split()
        signers = self.tmp / "allowed_signers"
        signers.write_text(f'hoang@hvl namespaces="git" {pub[0]} {pub[1]}\n', encoding="utf-8")
        self.follow_main()
        self.settings["MOC_GITOPS_ALLOWED_SIGNERS"] = str(signers)
        self.installed("0.9.0")
        self.git(self.origin, "tag", "-d", "v1.0.0")
        self.on_main("1.1.0", tag="v1.1.0")                             # thẻ không ký
        with self.assertRaisesRegex(reconcile.ReconcileError, "không ký bằng khóa"):
            self.gitops()
        self.assertEqual(self.recorded(), [])
        self.on_main("1.1.1", tag="v1.1.1", key=key)                    # thẻ ký đúng khóa
        self.gitops()
        self.assertEqual([c[1] for c in self.recorded()], ["1.1.1"])

    def test_unknown_mode_is_rejected(self) -> None:
        for name, value in (("MOC_GITOPS_MODE", "tu-dong"), ("MOC_GITOPS_FOLLOW", "main")):
            with self.subTest(name), mock.patch.dict(self.settings, {name: value}), \
                    self.assertRaisesRegex(reconcile.ReconcileError, name):
                self.gitops()
        self.assertEqual((self.recorded(), self.applied), ([], []))


class BackupLockTest(unittest.TestCase):
    """scripts/backup.py _guard: khóa chung trên thư mục chạy Signet đang bị giữ (như reconciler đang nâng)."""

    def setUp(self) -> None:
        # moc_env thật đọc .env lúc nạp (thiếu thì thoát): nạp backup với bản giả, trả sys.modules như cũ sau test
        names = ("moc_env", "backup", "ung_dung", "tenants", "audit_chain")
        saved = {n: sys.modules.pop(n, None) for n in names}
        self.addCleanup(lambda: [sys.modules.pop(n, None) if m is None else sys.modules.__setitem__(n, m)
                                 for n, m in saved.items()])
        stub = types.ModuleType("moc_env")
        stub.ENV, stub.ROOT = {}, SCRIPTS.parent
        sys.modules["moc_env"] = stub
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        self.backup = importlib.import_module("backup")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root, self.repo = pathlib.Path(tmp.name) / "opt-moc", pathlib.Path(tmp.name) / "kho"
        root.mkdir()
        self.repo.mkdir()
        patcher = mock.patch.object(self.backup, "ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)
        held = os.open(root, os.O_RDONLY)                 # mở riêng: flock của _guard đụng khóa này như tiến trình khác
        self.addCleanup(os.close, held)
        fcntl.flock(held, fcntl.LOCK_EX)

    def test_reconciler_call_does_not_wait_for_its_own_lock(self) -> None:
        with mock.patch.dict(os.environ, {"MOC_OPS_LOCKED": "1"}), self.backup._guard(self.repo):
            pass

    def test_other_callers_still_wait_then_give_up(self) -> None:
        clock = iter(range(0, 10**6, 1000))
        with mock.patch.dict(os.environ, {"MOC_OPS_LOCKED": ""}), \
                mock.patch.object(self.backup.time, "monotonic", lambda: next(clock)), \
                mock.patch.object(self.backup.time, "sleep", lambda _s: None), \
                self.assertRaisesRegex(self.backup.BackupError, "giữ khóa quá 30 phút"), \
                self.backup._guard(self.repo):
            pass


if __name__ == "__main__":
    unittest.main()
