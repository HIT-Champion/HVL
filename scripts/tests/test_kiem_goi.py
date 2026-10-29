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

"""Kiểm gói trước khi phát hành (scripts/kiem_goi.py; release.sh và .github/workflows/release.yml gọi) trên gói
`git archive` thật của một repo tạm mang các tệp phát hành thật (kiem_goi.py, license-header.sh, release.sh, Makefile,
VERSION, .gitattributes, LICENSE, NOTICE, LICENSES/, REUSE.toml): gói sạch qua cả `release.sh` lẫn `make release`;
tệp cấm (môi trường thật, khóa riêng theo tên và nội dung, tài liệu nội bộ, node_modules, dữ liệu chạy) bị chặn, mỗi
chỗ báo một lần, và release.sh gỡ thẻ vừa gắn, xóa gói; export-ignore loại được tệp; thiếu header, tệp REUSE.toml không
khai, thiếu LICENSE/NOTICE/LICENSES; .sha256 sai, thư mục gốc sai, VERSION chưa điền hay lệch thẻ; symlink, "..",
tệp quá trần; bước workflow chạy thật và đứng giữa bước đóng gói và bước tạo Release; install.sh lấy phiên bản từ
VERSION khi cài từ gói. Không mạng, không Docker. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
KIEM = SCRIPTS / "kiem_goi.py"
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
spec = importlib.util.spec_from_file_location("kiem_goi", KIEM)
kiem_goi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kiem_goi)

# repo thử không đọc cấu hình git của máy (khóa ký thẻ, hook, tệp bỏ qua chung…), tên người gắn thẻ cố định; bỏ mọi
# GIT_* thừa hưởng — chạy từ hook git thì GIT_DIR, GIT_INDEX_FILE trỏ về repo thật
GIT_ENV = {
    **{k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "GITHUB_ACTIONS"},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    # không chạy bảo trì tự động sau commit/push: nó có thể tách nền và còn ghi vào objects/ lúc test xóa kho tạm
    # (CI git 2.55: "Directory not empty: 'objects'", xem test_moc_neo.GIT_ENV)
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "maintenance.auto",
    "GIT_CONFIG_VALUE_0": "false",
    "GIT_AUTHOR_NAME": "thu",
    "GIT_AUTHOR_EMAIL": "thu@example.invalid",
    "GIT_COMMITTER_NAME": "thu",
    "GIT_COMMITTER_EMAIL": "thu@example.invalid",
}
REPO_FILES = ["scripts/kiem_goi.py", "scripts/license-header.sh", "scripts/release.sh", "scripts/release-notes.sh",
              "Makefile", "VERSION", ".gitattributes", "LICENSE", "NOTICE", "LICENSES/Apache-2.0.txt",
              "LICENSES/LicenseRef-Logos.txt", "LICENSES/LicenseRef-VN-SHTT-Dieu-15.txt", "REUSE.toml"]
HEADER = "".join(KIEM.read_text(encoding="utf-8").splitlines(keepends=True)[:15])
# Tên tệp môi trường và khối PEM ghép từ mảnh: tệp test này cũng nằm trong gói phát hành, không được tự bị chặn
ENV = ".e" + "nv"
PEM_KEY = ("-----BEGIN " + "PRIVATE KEY-----\nMIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEA\n"
           "-----END " + "PRIVATE KEY-----\n")
CERT = "-----BEGIN CERTIFICATE-----\nMIIBszCCAV2gAwIBAgIUJ\n-----END CERTIFICATE-----\n"
# Khai REUSE cho tệp thử; khối REUSE-Ignore: reuse lint không đọc nhầm thành khai giấy phép của tệp test này
# REUSE-IgnoreStart
SPDX = "# SPDX-FileCopyrightText: 2026 Signet Team\n# SPDX-License-Identifier: Apache-2.0\n"
# REUSE-IgnoreEnd
CHANGELOG = """# Lịch sử thay đổi

## [Chưa phát hành]

## [0.2.0] - 2026-10-30

### Đã thêm
- Tính năng của 0.2.0.
"""


class PackageRepo(unittest.TestCase):
    """Repo tạm có các tệp phát hành thật và một tệp mã có header; gói đóng bằng git archive như release.sh."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.repo = self.tmp / "repo"
        for rel in REPO_FILES:
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, self.repo / rel)
        self.write("CHANGELOG.md", CHANGELOG)
        self.write(".gitignore", "dist/\n")
        self.write("app/main.py", HEADER + "\nprint('Signet')\n")
        self.git("init", "-q", "-b", "main")
        self.commit()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, env=GIT_ENV, capture_output=True, text=True,
                              check=True).stdout

    def write(self, rel: str, content: str | bytes) -> pathlib.Path:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def commit(self, message: str = "thay đổi") -> None:
        # không dùng tệp bỏ qua chung của máy (core.excludesFile mặc định ~/.config/git/ignore): tệp cấm phải vào được
        self.git("-c", f"core.excludesFile={os.devnull}", "add", "-A")
        self.git("commit", "-qm", message)

    def pack(self, version: str = "0.2.0", ref: str | None = None, prefix: str | None = None) -> pathlib.Path:
        """Gói signet-<version>.tar.gz + .sha256 trong dist/ như release.sh; mặc định đóng từ thẻ v<version>, chưa có
        thì gắn."""
        if ref is None:
            ref = f"v{version}"
            if not self.git("tag", "-l", ref):
                self.git("tag", "-a", ref, "-m", f"Signet {version}")
        (self.repo / "dist").mkdir(exist_ok=True)
        package = self.repo / "dist" / f"signet-{version}.tar.gz"
        self.git("archive", "--format=tar.gz", f"--prefix={prefix or f'signet-{version}/'}", "-o", str(package), ref)
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        package.with_name(package.name + ".sha256").write_text(f"{digest}  {package.name}\n", encoding="utf-8")
        return package

    def kiem(self, package: pathlib.Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(KIEM), str(package), *args], env=env or GIT_ENV,
                              capture_output=True, text=True)

    @staticmethod
    def reported(proc: subprocess.CompletedProcess[str]) -> dict[str, str]:
        """Chỗ bị báo → lý do, từ các dòng "  - <chỗ>: <lý do>"."""
        lines = [line[4:] for line in proc.stdout.splitlines() if line.startswith("  - ")]
        return dict(line.split(": ", 1) for line in lines)

    def assert_passes(self, package: pathlib.Path) -> subprocess.CompletedProcess[str]:
        proc = self.kiem(package)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(f"Gói {package.name} đạt:", proc.stdout)
        return proc

    def assert_blocked(self, package: pathlib.Path, *messages: str) -> subprocess.CompletedProcess[str]:
        proc = self.kiem(package)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(f"Gói {package.name} KHÔNG được phát hành", proc.stdout)
        for message in messages:
            self.assertIn(message, proc.stdout)
        return proc


class ReleaseScriptTest(PackageRepo):
    """release.sh và make release ở máy: kiểm gói ngay sau khi đóng; gói hỏng thì không để lại thẻ hay gói."""

    def release(self, *cmd: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(list(cmd) or ["bash", "scripts/release.sh", "0.2.0"], cwd=self.repo, env=GIT_ENV,
                              capture_output=True, text=True)

    def test_clean_package_is_checked_and_kept(self) -> None:
        proc = self.release()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("==> Kiểm gói trước khi phát hành", proc.stdout)
        self.assertIn("Gói signet-0.2.0.tar.gz đạt:", proc.stdout)
        self.assertIn("VERSION v0.2.0", proc.stdout)
        self.assertEqual(self.git("tag", "-l").split(), ["v0.2.0"])
        with tarfile.open(self.repo / "dist" / "signet-0.2.0.tar.gz") as tar:
            version = tar.extractfile("signet-0.2.0/VERSION").read().decode()
        self.assertTrue(version.endswith("\nv0.2.0\n"), version[-40:])

    @unittest.skipUnless(shutil.which("make"), "cần make")
    def test_make_release_runs_the_check(self) -> None:
        proc = self.release("make", "release", "VERSION=0.2.0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Gói signet-0.2.0.tar.gz đạt:", proc.stdout)
        self.assertTrue((self.repo / "dist" / "signet-0.2.0.tar.gz.sha256").is_file())

    def test_bad_package_untags_and_removes_package(self) -> None:
        self.write("TEAM.local.md", "# Ghi chú nội bộ\n")
        self.write(f"deploy/{ENV}", "MOC_DB_PASSWORD=khong-phat-hanh\n")
        self.commit("lỡ commit tệp nội bộ")
        proc = self.release()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertEqual(self.reported(proc), {
            "TEAM.local.md": "tài liệu nội bộ của đội (*.local*, COMMIT.md), không đưa ra ngoài",
            f"deploy/{ENV}": "tệp môi trường thật, có bí mật — chỉ phát hành tệp mẫu *.example",
        })
        self.assertIn("đã gỡ thẻ v0.2.0 ở máy và xóa gói", proc.stderr)
        self.assertEqual(self.git("tag", "-l"), "")
        self.assertEqual(list((self.repo / "dist").iterdir()), [])
        # sửa xong chạy lại được ngay, không vướng chốt "thẻ đã có ở máy này"
        self.git("rm", "-q", "TEAM.local.md", f"deploy/{ENV}")
        self.commit("gỡ tệp nội bộ")
        self.assertEqual(self.release().returncode, 0)


class ForbiddenFilesTest(PackageRepo):
    def test_each_forbidden_place_is_reported_once(self) -> None:
        forbidden = {
            ENV: "tệp môi trường thật",
            f"services/svc-files/{ENV}.production": "tệp môi trường thật",
            f"platform/prod{ENV}": "tệp môi trường thật",
            "deploy/id_ed25519": "khóa riêng hay kho khóa",
            "platform/tls/server.key": "khóa riêng hay kho khóa",
            "platform/tls/keystore.p12": "khóa riêng hay kho khóa",
            "platform/tls/tls.pem": "có khối khóa riêng PEM",
            "docs/ghi-chu.txt": "có khối khóa riêng PEM",
            ".netrc": "tệp thông tin đăng nhập",
            "TEAM.local.md": "tài liệu nội bộ của đội",
            "COMMIT.md": "tài liệu nội bộ của đội",
            "docker-compose.dev.local.yml": "tài liệu nội bộ của đội",
            "publics/": "bản lưu tài liệu của BTC",
            "apps/office/node_modules/": "thư mục phụ thuộc hay bộ đệm",
            "scripts/__pycache__/": "thư mục phụ thuộc hay bộ đệm",
            "app/.venv/": "thư mục phụ thuộc hay bộ đệm",
            "backups/": "dữ liệu chạy của hệ thống",
            "app/cache.sqlite3": "tệp CSDL hay dữ liệu chạy",
            "app/old.pyc": "mã Python đã biên dịch",
        }
        contents = {"platform/tls/tls.pem": CERT + PEM_KEY, "docs/ghi-chu.txt": "khóa tạm:\n" + PEM_KEY}
        for rel in forbidden:
            if rel.endswith("/"):
                # hai tệp trong cùng thư mục: báo một lần cho cả thư mục
                self.write(rel + "a.js", "x\n")
                self.write(rel + "sub/b.js", "y\n")
            else:
                self.write(rel, contents.get(rel, "bí mật\n"))
        # được phát hành: tệp mẫu môi trường, thư mục data không ở gốc, .pem chỉ có chứng thư công khai
        self.write(f"{ENV}.example", HEADER + "\nMOC_DB_PASSWORD=\n")
        self.write("seed/data/don-vi.csv", "ma,ten\n1,CNTT\n")
        self.write("platform/tls/ca.pem", SPDX + CERT)
        self.commit()
        proc = self.assert_blocked(self.pack())
        reported = self.reported(proc)
        self.assertEqual(sorted(reported), sorted(forbidden), proc.stdout)
        for rel, reason in forbidden.items():
            self.assertIn(reason, reported[rel], rel)

    def test_unit_rules(self) -> None:
        allowed = [f"{ENV}.example", f"apps/office/{ENV}.example", "seed/data/x.csv", "docs/anh/locale.png",
                   "scripts/moc_env.py", "deploy/id_rsa.pub", "platform/logs/vector.yaml", "monkey.txt"]
        for rel in allowed:
            self.assertIsNone(kiem_goi.forbidden(rel), rel)
        self.assertEqual(kiem_goi.forbidden("a/node_modules/b/c.js")[0], "a/node_modules/")
        self.assertEqual(kiem_goi.forbidden(ENV + "rc")[0], ENV + "rc")

    def test_export_ignore_keeps_a_tracked_file_out(self) -> None:
        # tệp vẫn theo dõi trong git nhưng không vào gói: git archive tôn trọng export-ignore của commit được đóng gói
        self.write("TEAM.local.md", "# Ghi chú nội bộ\n")
        with (self.repo / ".gitattributes").open("a", encoding="utf-8") as f:
            f.write("TEAM.local.md export-ignore\n")
        self.commit()
        package = self.pack()
        self.assert_passes(package)
        with tarfile.open(package) as tar:
            self.assertNotIn("signet-0.2.0/TEAM.local.md", tar.getnames())


class LicenseTest(PackageRepo):
    def test_missing_header_and_undeclared_file(self) -> None:
        self.write("app/khong_header.py", "print('thiếu header')\n")
        self.write("app/static/font.woff2", b"wOF2\x00\x01")
        # tệp đi kèm .license (REUSE) thì không cần REUSE.toml khai
        self.write("app/static/logo.webp", b"RIFF\x00WEBP")
        self.write("app/static/logo.webp.license", SPDX)
        self.commit()
        proc = self.assert_blocked(self.pack())
        self.assertEqual(self.reported(proc), {
            "app/khong_header.py": "thiếu header giấy phép Apache-2.0 (scripts/license-header.sh)",
            "app/static/font.woff2": "không có SPDX-License-Identifier và bản quyền trong tệp, REUSE.toml cũng không "
                                     "khai",
        })

    def test_license_files_are_required(self) -> None:
        self.git("rm", "-q", "LICENSE", "NOTICE", "LICENSES/LicenseRef-Logos.txt")
        self.commit()
        self.assert_blocked(self.pack(), "thiếu LICENSE (toàn văn giấy phép)", "thiếu NOTICE",
                            "LICENSES/LicenseRef-Logos.txt: thiếu toàn văn giấy phép LicenseRef-Logos")

    def test_license_header_outside_git_does_not_pass_empty(self) -> None:
        # thư mục không có .git (gói giải nén): trước đây git ls-files ra rỗng và lượt kiểm qua mà không xét gì
        pkg = self.tmp / "goi"
        (pkg / "app").mkdir(parents=True)
        (pkg / "app" / "a.py").write_text("print(1)\n", encoding="utf-8")
        proc = subprocess.run(["bash", str(SCRIPTS / "license-header.sh"), "check", str(pkg)], capture_output=True,
                              text=True, env=GIT_ENV)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("THIẾU header giấy phép: app/a.py", proc.stdout)

    def test_reuse_glob(self) -> None:
        self.assertTrue(kiem_goi.reuse_glob("**.md").fullmatch("docs/a/b.md"))
        self.assertTrue(kiem_goi.reuse_glob("**.md").fullmatch("README.md"))
        logo = kiem_goi.reuse_glob("docs/anh/logo/*.png")
        self.assertTrue(logo.fullmatch("docs/anh/logo/apisix.png"))
        self.assertFalse(logo.fullmatch("docs/anh/logo/cu/apisix.png"))
        self.assertFalse(kiem_goi.reuse_glob("NOTICE").fullmatch("NOTICE.bak"))
        self.assertTrue(kiem_goi.reuse_glob("a\\*.txt").fullmatch("a*.txt"))
        self.assertFalse(kiem_goi.reuse_glob("a\\*.txt").fullmatch("ab.txt"))


class IntegrityTest(PackageRepo):
    def test_checksum_must_match_and_name_the_package(self) -> None:
        package = self.pack()
        sums = package.with_name(package.name + ".sha256")
        good = sums.read_text(encoding="utf-8")
        sums.write_text(("0" * 64) + good[64:], encoding="utf-8")
        self.assert_blocked(package, "băm SHA-256 của signet-0.2.0.tar.gz không khớp")
        sums.write_text(good.replace(package.name, "dist/" + package.name), encoding="utf-8")
        self.assert_blocked(package, "sha256sum -c sẽ không thấy gói")
        sums.write_text(good + good, encoding="utf-8")
        self.assert_blocked(package, "phải có đúng một dòng")
        sums.unlink()
        self.assert_blocked(package, "thiếu signet-0.2.0.tar.gz.sha256 cạnh gói")

    def test_root_directory_must_be_signet_version(self) -> None:
        self.assert_blocked(self.pack(prefix="moc-0.2.0/"),
                            "gói phải có đúng một thư mục gốc signet-0.2.0/ (gói có: moc-0.2.0/)")

    def test_version_file_must_be_filled_with_the_tag(self) -> None:
        self.git("tag", "-a", "v0.2.0", "-m", "Signet 0.2.0")
        self.write("app/them.py", HEADER)
        self.commit("sau thẻ")
        # đóng gói commit sau thẻ dưới tên 0.2.0: VERSION ghi v0.2.0-1-g…
        self.assert_blocked(self.pack(ref="HEAD"), "VERSION ghi 'v0.2.0-1-g", "gói không đóng từ thẻ v0.2.0?")

    def test_newest_tag_of_the_commit_fills_version(self) -> None:
        # bản thử v0.2.0-rc.1 rồi bản chính v0.2.0 trên cùng commit: git describe chọn thẻ có chú thích mới hơn
        subprocess.run(["git", "tag", "-a", "v0.2.0-rc.1", "-m", "rc"], cwd=self.repo, check=True,
                       env={**GIT_ENV, "GIT_COMMITTER_DATE": "2026-10-01T00:00:00+07:00"})
        self.assert_passes(self.pack())

    def test_version_file_without_export_subst(self) -> None:
        attrs = self.repo / ".gitattributes"
        attrs.write_text(attrs.read_text(encoding="utf-8").replace("VERSION export-subst\n", ""), encoding="utf-8")
        self.commit()
        self.assert_blocked(self.pack(), "VERSION chưa được git archive điền thẻ")

    def test_symlink_is_rejected(self) -> None:
        (self.repo / "app" / "lien-ket").symlink_to("/etc/passwd")
        self.commit()
        self.assert_blocked(self.pack(), "signet-0.2.0/app/lien-ket: không phải tệp thường hay thư mục")

    def test_path_escaping_root_is_rejected_before_extracting(self) -> None:
        package = self.pack()
        crafted = self.tmp / "signet-0.2.0.tar.gz"
        with tarfile.open(package) as src, tarfile.open(crafted, "w:gz") as dst:
            for member in src.getmembers():
                dst.addfile(member, src.extractfile(member) if member.isfile() else None)
            evil = tarfile.TarInfo("signet-0.2.0/../thoat-ra.txt")
            evil.size = 3
            dst.addfile(evil, io.BytesIO(b"xin"))
        digest = hashlib.sha256(crafted.read_bytes()).hexdigest()
        crafted.with_name(crafted.name + ".sha256").write_text(f"{digest}  {crafted.name}\n", encoding="utf-8")
        self.assert_blocked(crafted, "signet-0.2.0/../thoat-ra.txt: đường dẫn thoát ra ngoài")
        self.assertFalse((self.tmp / "thoat-ra.txt").exists())

    def test_large_file_over_limit(self) -> None:
        self.write("seed/video.mp4", b"\0" * 4096)
        self.commit()
        package = self.pack()
        out = io.StringIO()
        old = kiem_goi.MAX_FILE
        kiem_goi.MAX_FILE = 1024
        # gọi trong tiến trình: bỏ GITHUB_ACTIONS (runner đặt sẵn) để lỗi in dạng "  - …" như ở máy
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
        try:
            with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, env, clear=True):
                code = kiem_goi.main([str(package)])
        finally:
            kiem_goi.MAX_FILE = old
        self.assertEqual(code, 1)
        self.assertRegex(out.getvalue(), r"  - seed/video\.mp4: [0-9.]+ MiB, vượt trần [0-9.]+ MiB cho một tệp")
        self.assertNotIn("không có SPDX-License-Identifier", out.getvalue())

    def test_real_limits(self) -> None:
        # ngưỡng ghi trong mã và PLAN: 5 MiB một tệp, 100 MiB cả gói giải nén
        self.assertEqual(kiem_goi.MAX_FILE, 5 * 2**20)
        self.assertEqual(kiem_goi.MAX_TOTAL, 100 * 2**20)

    def test_usage_errors(self) -> None:
        package = self.pack()
        self.assertEqual(self.kiem(package, "--version", "0.3.0").returncode, 2)
        renamed = package.with_name("moc-0.2.0.tar.gz")
        shutil.copy(package, renamed)
        self.assertEqual(self.kiem(renamed).returncode, 2)
        self.assertEqual(self.kiem(package.with_name("signet-9.9.9.tar.gz")).returncode, 2)

    def test_corrupt_archive(self) -> None:
        package = self.pack()
        package.write_bytes(b"khong phai gzip")
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        package.with_name(package.name + ".sha256").write_text(f"{digest}  {package.name}\n", encoding="utf-8")
        self.assert_blocked(package, "không đọc được gói .tar.gz")

    def test_github_annotations(self) -> None:
        self.write("TEAM.local.md", "x\n")
        self.commit()
        proc = self.kiem(self.pack(), env={**GIT_ENV, "GITHUB_ACTIONS": "true"})
        self.assertEqual(proc.returncode, 1)
        self.assertIn("::error::signet-0.2.0.tar.gz: TEAM.local.md: tài liệu nội bộ của đội", proc.stdout)


def step_script(name: str) -> str:
    """Khối `run:` (một dòng hay `run: |`) của bước `name` trong release.yml, bỏ thụt lề (không có PyYAML)."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    i = lines.index(f"      - name: {name}")
    while not lines[i].strip().startswith("run:"):
        i += 1
    if lines[i].strip() != "run: |":
        return lines[i].strip().removeprefix("run:").strip() + "\n"
    indent = len(lines[i]) - len(lines[i].lstrip()) + 2
    body = []
    for line in lines[i + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body).strip() + "\n"


class WorkflowStepTest(PackageRepo):
    """release.yml, bước "Kiểm gói trước khi phát hành": chạy thật lệnh của bước, đứng đúng chỗ."""

    def step(self, version: str = "0.2.0") -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "-e", "-c", step_script("Kiểm gói trước khi phát hành")], cwd=self.repo,
                              env={**GIT_ENV, "V": version, "GITHUB_ACTIONS": "true"}, capture_output=True, text=True)

    def test_step_checks_the_built_package(self) -> None:
        self.pack()
        proc = self.step()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Gói signet-0.2.0.tar.gz đạt:", proc.stdout)
        with (self.repo / "dist" / "signet-0.2.0.tar.gz").open("ab") as f:
            f.write(b"\0")
        proc = self.step()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("::error::signet-0.2.0.tar.gz: băm SHA-256", proc.stdout)

    def test_step_sits_between_packing_and_release(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        step = text.index("name: Kiểm gói trước khi phát hành")
        self.assertLess(text.index("name: Sinh gói nguồn .tar.gz"), step)
        self.assertLess(step, text.index("name: Sinh SBOM CycloneDX (make sbom)"))
        self.assertLess(step, text.index("softprops/action-gh-release@"))
        self.assertIn('kiem_goi.py "dist/signet-$V.tar.gz" --version "$V"', step_script("Kiểm gói trước khi phát hành"))


class InstallVersionTest(PackageRepo):
    """install.sh: cài từ gói lấy phiên bản ở VERSION (git archive điền); bản clone vẫn dùng git describe."""

    def src_version(self, src: pathlib.Path) -> str:
        text = (SCRIPTS / "install.sh").read_text(encoding="utf-8")
        func = re.search(r"^src_version\(\) \{\n.*?^\}\n", text, re.M | re.S)[0]
        # không tìm repo git ở thư mục cha của thư mục tạm
        env = {**GIT_ENV, "GIT_CEILING_DIRECTORIES": str(self.tmp)}
        proc = subprocess.run(["bash", "-c", f'set -euo pipefail\nSRC="$1"\n{func}src_version', "_", str(src)],
                              env=env, capture_output=True, text=True, check=True)
        return proc.stdout.strip()

    def test_extracted_package_knows_its_version(self) -> None:
        with tarfile.open(self.pack()) as tar:
            tar.extractall(self.tmp / "giai-nen", filter="data")
        self.assertEqual(self.src_version(self.tmp / "giai-nen" / "signet-0.2.0"), "0.2.0")

    def test_clone_uses_git_describe(self) -> None:
        self.git("tag", "-a", "v0.3.0", "-m", "Signet 0.3.0")
        self.assertEqual(self.src_version(self.repo), "0.3.0")

    def test_template_without_git_is_dev(self) -> None:
        bare = self.tmp / "khong-git"
        bare.mkdir()
        shutil.copy(ROOT / "VERSION", bare / "VERSION")
        self.assertEqual(self.src_version(bare), "dev")


if __name__ == "__main__":
    unittest.main()
