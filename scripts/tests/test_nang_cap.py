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

"""Kịch bản nâng cấp (scripts/nang_cap.sh) ở những phần chạy được không cần Docker: từ chối trước khi đụng vào bản
cài (không phải bản cài, mã nguồn cũ không rõ phiên bản, lượt sao lưu không có, thiếu RAM, reconciler đang chạy —
docker không được gọi lần nào); phần kiểm chạy hết các mục và chỉ thử lại smoke một lần khi trượt đúng ở bước hỏi
đáp. Lệnh docker, curl, free, systemctl là bản giả ghi lại lời gọi; đường nâng, nâng két, lùi thật chạy ở
.github/workflows/nang-cap.yml. Workflow chỉ gọi lệnh con có thật, bộ lọc tệp của nó bắt đúng đường nâng cấp.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "nang_cap.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "nang-cap.yml"

# Lệnh giả: ghi "<tên> <tham số>" vào $FAKE_LOG; hành vi theo biến FAKE_*
FAKES = {
    "docker": """
        echo "docker $*" >> "$FAKE_LOG"
        case "$*" in
          "ps -q --filter "*) echo c0ffee ;;
          "compose ps --format "*) echo "postgres healthy"; echo "apisix " ;;
        esac
    """,
    "curl": """
        echo "curl $*" >> "$FAKE_LOG"
        case "$*" in
          */api/status) printf '{"version": "%s", "status": "ok"}' "$FAKE_STATUS_VERSION" ;;
          *) exit 22 ;;
        esac
    """,
    "free": """
        echo "               total        used        free      shared  buff/cache   available"
        echo "Mem:           16000        6000        1000         100        9000   ${FAKE_RAM_MB:-8000}"
    """,
    "systemctl": """
        echo "systemctl $*" >> "$FAKE_LOG"
        [ "${FAKE_TIMER:-off}" = on ]
    """,
    "make": """
        echo "make $*" >> "$FAKE_LOG"
    """,
}

# Lệnh của bản cài giả: moc.py (backup list, realm, audit), smoke.py (trượt theo $FAKE_SMOKE), moc_env.py
MOC_PY = """
import json, os, sys
args = sys.argv[1:]
if args[:2] == ["backup", "list"]:
    print(json.dumps({"runs": [{"run": "20261025-191948", "complete": True},
                               {"run": "20261025-180000", "complete": False}]}))
elif args[:3] == ["realm", "clients", "--dry-run"]:
    print(json.dumps({"present": ["app-office"], "created": [], "dry_run": True}))
elif args[:2] == ["realm", "theme"]:
    sys.exit(2)  # bản cũ chưa có lệnh này
elif args[:2] == ["audit", "verify"]:
    print("sổ kiểm toán khớp")
else:
    sys.exit(f"moc.py giả: không biết {args}")
"""
SMOKE_PY = """
import os, pathlib, sys
runs = pathlib.Path(os.environ["FAKE_LOG"]).with_name("smoke-runs")
n = int(runs.read_text()) + 1 if runs.exists() else 1
runs.write_text(str(n))
mode = os.environ.get("FAKE_SMOKE", "ok")
if mode == "ok" or (mode == "ask-once" and n > 1):
    print("  ✓ luồng chính")
    sys.exit(0)
if mode in ("ask-once", "ask-always"):
    print("Hỏi đáp trên kho văn bản (F4.2)")
    print("  ✗ sau 121 giây trợ lý chưa trả câu trích ở trang 2 công văn hai trang: {}")
else:
    print("  ✗ văn thư không đăng nhập được")
sys.exit(1)
"""


class Sandbox:
    """Bản cài giả trong thư mục tạm, PATH chứa lệnh giả; run() chạy nang_cap.sh."""

    def __init__(self, tmp: pathlib.Path) -> None:
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.bin.mkdir()
        for name, body in FAKES.items():
            path = self.bin / name
            path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
            path.chmod(0o755)
        self.log = tmp / "calls.log"
        self.log.touch()
        self.dest = tmp / "moc"
        (self.dest / "scripts").mkdir(parents=True)
        (self.dest / ".moc-install").write_text("docker-compose.yml\n")
        (self.dest / "VERSION").write_text("Signet 1.2.0\nmã nguồn: abc1234\n")
        (self.dest / "scripts" / "moc.py").write_text(MOC_PY)
        (self.dest / "scripts" / "smoke.py").write_text(SMOKE_PY)
        (self.dest / "scripts" / "moc_env.py").write_text('PUBLIC_URL = "http://moc.invalid"\n')
        self.old = tmp / "signet-1.1.0"
        (self.old / "scripts").mkdir(parents=True)
        (self.old / "scripts" / "install.sh").write_text("#!/bin/sh\n")

    def run(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        full = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.tmp), "LANG": "C.UTF-8",
                "GIT_CEILING_DIRECTORIES": str(self.tmp), "FAKE_LOG": str(self.log),
                "FAKE_STATUS_VERSION": "1.2.0", **env}
        return subprocess.run(["bash", str(SCRIPT), *args], env=full, capture_output=True, text=True, timeout=60)

    def calls(self, prefix: str = "") -> list[str]:
        return [line for line in self.log.read_text().splitlines() if line.startswith(prefix)]


class BeforeTouchingTest(unittest.TestCase):
    """Mọi lần từ chối đều trước lệnh docker đầu tiên: bản cài không bị dừng, không bị cài đè."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.box = Sandbox(pathlib.Path(tmp.name))

    def refused(self, proc: subprocess.CompletedProcess, message: str, code: int = 1) -> None:
        self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
        self.assertIn(message, proc.stderr)
        self.assertEqual(self.box.calls("docker"), [], "không được gọi docker trước khi kiểm xong")
        self.assertEqual(self.box.calls("make"), [])

    def test_usage(self) -> None:
        for args in ([], ["nang"], ["lam-gi"], ["lui", str(self.box.dest), str(self.box.old)]):
            with self.subTest(args=args):
                self.refused(self.box.run(*args), "Dùng:", code=2)

    def test_not_an_installation(self) -> None:
        for cmd in ("nang", "ket", "kiem"):
            with self.subTest(cmd=cmd):
                self.refused(self.box.run(cmd, str(self.box.tmp)), "không phải bản cài Signet")

    def test_old_source_must_be_signet(self) -> None:
        self.refused(self.box.run("lui", str(self.box.dest), str(self.box.tmp), "20261025-191948"),
                     "không phải thư mục mã nguồn Signet")

    def test_old_package_without_version_needs_moc_version(self) -> None:
        proc = self.box.run("lui", str(self.box.dest), str(self.box.old), "20261025-191948")
        self.refused(proc, "đặt MOC_VERSION")
        self.assertIn("MOC_VERSION=1.1.0", proc.stderr)

    def test_backup_run_must_exist_and_be_complete(self) -> None:
        for run in ("20261024-000000", "20261025-180000"):
            with self.subTest(run=run):
                proc = self.box.run("lui", str(self.box.dest), str(self.box.old), run, MOC_VERSION="1.1.0")
                self.refused(proc, f"không có lượt {run} trọn vẹn")

    def test_version_file_of_package_is_enough(self) -> None:
        # gói từ 1.2.0: dòng thẻ trong VERSION (git archive điền) — qua bước phiên bản, dừng ở bước sau (RAM)
        (self.box.old / "VERSION").write_text("$Format:%(describe)$\nv1.1.0\n")
        proc = self.box.run("lui", str(self.box.dest), str(self.box.old), "20261025-191948", FAKE_RAM_MB="900")
        self.refused(proc, "RAM trống 900 MiB")

    def test_running_reconciler_blocks(self) -> None:
        proc = self.box.run("lui", str(self.box.dest), str(self.box.old), "20261025-191948", MOC_VERSION="1.1.0",
                            FAKE_TIMER="on")
        self.refused(proc, "moc-reconcile.timer đang chạy")

    def test_upgrade_needs_the_running_installation(self) -> None:
        # nang sao lưu bằng chính bản đang chạy: không có container nào của bản cài thì dừng trước khi dựng hay cài
        fake = self.box.bin / "docker"
        fake.write_text('#!/bin/sh\necho "docker $*" >> "$FAKE_LOG"\n')
        proc = self.box.run("nang", str(self.box.dest))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("Signet không chạy từ", proc.stderr)
        self.assertEqual([c.split(" --filter")[0] for c in self.box.calls("docker")], ["docker ps -q"])
        self.assertEqual(self.box.calls("make"), [])


class ChecksTest(unittest.TestCase):
    """kiem: chạy hết các mục, báo mục trượt; smoke chỉ thử lại một lần, chỉ khi trượt ở bước hỏi đáp."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.box = Sandbox(pathlib.Path(tmp.name))

    def smoke_runs(self) -> int:
        runs = self.box.log.with_name("smoke-runs")
        return int(runs.read_text()) if runs.exists() else 0

    def test_all_pass(self) -> None:
        proc = self.box.run("kiem", str(self.box.dest))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Mọi mục kiểm đều đạt.", proc.stdout)
        self.assertEqual(self.smoke_runs(), 1)
        self.assertIn("curl -fsS --max-time 30 http://moc.invalid/api/status", self.box.calls("curl"))

    def test_question_answering_timeout_is_retried_once(self) -> None:
        proc = self.box.run("kiem", str(self.box.dest), FAKE_SMOKE="ask-once")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("THỬ LẠI một lần", proc.stdout)
        self.assertEqual(self.smoke_runs(), 2)

    def test_retry_happens_only_once(self) -> None:
        proc = self.box.run("kiem", str(self.box.dest), FAKE_SMOKE="ask-always")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.smoke_runs(), 2)
        self.assertIn("Trượt: smoke;", proc.stdout)

    def test_other_smoke_failures_are_not_retried(self) -> None:
        proc = self.box.run("kiem", str(self.box.dest), FAKE_SMOKE="login")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.smoke_runs(), 1)
        self.assertNotIn("THỬ LẠI", proc.stdout)

    def test_every_check_runs_and_failures_are_listed(self) -> None:
        # trang trạng thái báo phiên bản khác bản đã cài, một dịch vụ chưa khỏe: vẫn chạy sổ kiểm toán và smoke
        fake = self.box.bin / "docker"
        fake.write_text(fake.read_text().replace('echo "apisix "', 'echo "apisix unhealthy"'))
        proc = self.box.run("kiem", str(self.box.dest), FAKE_STATUS_VERSION="1.1.0")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Trượt: phiên bản 1.2.0 trên trang trạng thái; dịch vụ khỏe;", proc.stdout)
        self.assertIn("apisix unhealthy", proc.stdout)
        self.assertIn("sổ kiểm toán khớp", proc.stdout)
        self.assertEqual(self.smoke_runs(), 1)


class WorkflowTest(unittest.TestCase):
    text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_calls_existing_subcommands_in_order(self) -> None:
        subcommands = re.findall(r"^  ([a-z]+)\)", SCRIPT.read_text(encoding="utf-8"), re.M)
        called = re.findall(r"scripts/nang_cap\.sh ([a-z]+) ", self.text)
        self.assertEqual(called, ["nang", "ket", "kiem", "lui"])
        self.assertLessEqual(set(called), set(subcommands))

    def test_path_filter(self) -> None:
        parts = re.findall(r"duong\+?='([^']*)'", self.text)
        self.assertGreater(len(parts), 1)
        pattern = re.compile("".join(parts))
        for path in ("db/migrations/default/1792281603500_x/up.sql", "db/metadata/actions.yaml",
                     "platform/openbao/start.sh", "platform/keycloak/realm/moc-realm.json", "docker-compose.yml",
                     ".env.example", "scripts/nang_cap.sh", "scripts/install.sh", "scripts/backup.py",
                     ".github/workflows/nang-cap.yml"):
            with self.subTest(path=path):
                self.assertTrue(pattern.search(path), path)
        for path in ("docs/van-hanh.md", "scripts/smoke.py", "apps/office/app/pages/cam-bien.vue",
                     "platform/keycloak/themes/signet/login/theme.properties", "scripts/install.sh.bak"):
            with self.subTest(path=path):
                self.assertIsNone(pattern.search(path), path)


if __name__ == "__main__":
    unittest.main()
