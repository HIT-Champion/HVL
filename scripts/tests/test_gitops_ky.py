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

"""GitOps chỉ áp commit đã ký (scripts/reconcile.py, MOC_GITOPS_ALLOWED_SIGNERS): repo git và khóa SSH thật trong thư
mục tạm — commit ký bằng khóa trong danh sách được áp; khóa lạ, không ký, chữ ký OpenPGP (dù gpg của người dùng báo tốt)
thì không, và Signet không bị dừng (apply không được gọi). Không cần Docker. Chạy: python3 -m unittest discover -s
scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reconcile_ky", SCRIPTS / "reconcile.py")
reconcile: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)

# gpg giả "tin mọi chữ ký" — như người chạy reconciler có sẵn khóa OpenPGP trong keyring
FAKE_GPG = """#!/bin/sh
cat > /dev/null
echo "[GNUPG:] NEWSIG"
echo "[GNUPG:] GOODSIG 0123456789ABCDEF Ai do <ai@do>"
echo "[GNUPG:] VALIDSIG 0123456789ABCDEF0123456789ABCDEF01234567 2026-10-22 1790000000 0 4 0 1 10 00 0123456789ABCDEF0123456789ABCDEF01234567"
echo "[GNUPG:] TRUST_ULTIMATE 0 pgp"
exit 0
"""
FAKE_PGP_SIG = ("-----BEGIN PGP SIGNATURE-----\n\niQEzBAABCAAdFiEE\n=abcd\n-----END PGP SIGNATURE-----")


@unittest.skipUnless(shutil.which("ssh-keygen") and shutil.which("git"), "cần git, ssh-keygen")
class SignedGitopsTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        # git không đọc cấu hình của máy chạy test; cấu hình "người dùng" là tệp riêng của test
        self.user_config = self.tmp / "gitconfig"
        self.user_config.write_text("", encoding="utf-8")
        saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
        os.environ.update(GIT_CONFIG_GLOBAL=str(self.user_config), GIT_CONFIG_NOSYSTEM="1")
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])
        for name in ("duoc-phep", "la"):
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(self.tmp / name)],
                           check=True)
        pub = (self.tmp / "duoc-phep.pub").read_text().split()
        self.signers = self.tmp / "allowed_signers"
        self.signers.write_text(f'vuong@moc namespaces="git" {pub[0]} {pub[1]}\n', encoding="utf-8")
        self.origin = self.tmp / "origin"
        self.git(self.origin.parent, "init", "-q", "-b", "deploy", str(self.origin))
        self.commit("khởi tạo", key="duoc-phep")

    def git(self, cwd: pathlib.Path, *args: str) -> str:
        return subprocess.run(["git", "-c", "user.name=nhap", "-c", "user.email=nhap@local", *args], cwd=cwd,
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, message: str, key: str | None) -> str:
        sign = ["-c", "gpg.format=ssh", "-c", f"user.signingkey={self.tmp / key}"] if key else []
        subprocess.run(["git", "-c", "user.name=nhap", "-c", "user.email=nhap@local", *sign, "commit", "-q",
                        "--allow-empty", *(["-S"] if key else []), "-m", message], cwd=self.origin, check=True)
        return self.git(self.origin, "rev-parse", "HEAD")

    def pgp_commit(self) -> str:
        """Commit mang chữ ký OpenPGP (giả): ghi thẳng đối tượng commit có tiêu đề gpgsig."""
        head = self.git(self.origin, "rev-parse", "HEAD")
        tree = self.git(self.origin, "rev-parse", "HEAD^{tree}")
        sig = "\n ".join(FAKE_PGP_SIG.split("\n"))
        body = (f"tree {tree}\nparent {head}\nauthor nhap <nhap@local> 1790000000 +0700\n"
                f"committer nhap <nhap@local> 1790000000 +0700\ngpgsig {sig}\n\nký OpenPGP\n")
        obj = subprocess.run(["git", "hash-object", "-t", "commit", "-w", "--stdin"], cwd=self.origin, input=body,
                             check=True, capture_output=True, text=True).stdout.strip()
        self.git(self.origin, "update-ref", "refs/heads/deploy", obj)
        return obj

    def verify(self, commit: str) -> None:
        git = ["git", "-C", str(self.origin), "-c", f"safe.directory={self.origin}"]
        reconcile.verify_signature(git, commit, str(self.signers))

    def test_allowed_key_passes(self) -> None:
        self.verify(self.commit("ký đúng", key="duoc-phep"))

    def test_unknown_key_unsigned_and_missing_list_are_rejected(self) -> None:
        for label, commit in (("khóa lạ", self.commit("khóa lạ", key="la")),
                              ("không ký", self.commit("không ký", key=None))):
            with self.subTest(label), self.assertRaises(reconcile.ReconcileError):
                self.verify(commit)
        git = ["git", "-C", str(self.origin)]
        with self.assertRaisesRegex(reconcile.ReconcileError, "không có tệp"):
            reconcile.verify_signature(git, "HEAD", str(self.tmp / "khong-co"))

    def test_openpgp_signature_rejected_even_if_user_gpg_trusts_it(self) -> None:
        fake = self.tmp / "gpg-gia"
        fake.write_text(FAKE_GPG, encoding="utf-8")
        fake.chmod(0o755)
        self.user_config.write_text(f"[gpg]\n\tprogram = {fake}\n", encoding="utf-8")
        commit = self.pgp_commit()
        # chứng minh ca thử có nghĩa: không có danh sách thì git tin chữ ký này
        self.assertEqual(subprocess.run(["git", "verify-commit", commit], cwd=self.origin,
                                        capture_output=True).returncode, 0)
        with self.assertRaises(reconcile.ReconcileError):
            self.verify(commit)

    def test_gitops_does_not_stop_moc_for_unsigned_commit(self) -> None:
        root = self.tmp / "opt-moc"
        root.mkdir()
        (root / reconcile.MANIFEST).write_text("", encoding="utf-8")
        src = self.tmp / "moc-src"
        self.git(self.tmp, "clone", "-q", "-b", "deploy", str(self.origin), str(src))
        applied: list[str] = []
        saved = {n: getattr(reconcile, n) for n in ("ROOT", "apply", "installed_files", "setting")}
        self.addCleanup(lambda: [setattr(reconcile, n, v) for n, v in saved.items()])
        reconcile.ROOT = root
        reconcile.apply = lambda git, src, target, previous: applied.append(target)
        reconcile.installed_files = lambda: {}
        settings = {"MOC_GITOPS_DIR": str(src), "MOC_GITOPS_ALLOWED_SIGNERS": str(self.signers)}
        reconcile.setting = lambda name, default="": settings.get(name, default)

        unsigned = self.commit("đẩy không ký", key=None)
        report: dict[str, Any] = {"commit": None, "applied": None, "actions": [], "problems": []}
        with self.assertRaisesRegex(reconcile.ReconcileError, unsigned[:12]):
            reconcile.gitops(report)
        self.assertEqual(applied, [], "commit chưa ký: không được dừng Signet để cài")

        signed = self.commit("ký đúng", key="duoc-phep")
        with contextlib.redirect_stdout(io.StringIO()):
            reconcile.gitops(report)
        self.assertEqual(applied, [signed])


if __name__ == "__main__":
    unittest.main()
