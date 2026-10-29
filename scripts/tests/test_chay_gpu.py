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

"""Chạy mô hình bằng GPU (#442, MOC_AI_DEVICE, docker-compose.gpu.yml): tệp phủ chỉ cấp GPU NVIDIA cho ollama, không
đổi gì khác; mặc định cpu thì compose y như cũ; Makefile và make install chỉ thêm tệp phủ vào COMPOSE_FILE khi
MOC_AI_DEVICE=gpu, đứng trước tệp phủ log tập trung; scripts/co-gpu.sh in gpu chỉ khi có cả GPU lẫn runtime nvidia của
Docker. Kiểm chữ (không có PyYAML), make và bash trong thư mục tạm với nvidia-smi, docker giả; không gọi Docker thật.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "tests"))

from test_cai_phien_ban import DOCKER, INSTALL  # noqa: E402

OVERLAY = ROOT / "docker-compose.gpu.yml"
CO_GPU = ROOT / "scripts" / "co-gpu.sh"


def without_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))


class ComposeTest(unittest.TestCase):
    def test_overlay_only_reserves_nvidia_gpus_for_ollama(self) -> None:
        self.assertEqual(without_comments(OVERLAY.read_text(encoding="utf-8")), "\n".join([
            "services:",
            "  ollama:",
            "    deploy:",
            "      resources:",
            "        reservations:",
            "          devices:",
            "            - driver: nvidia",
            "              count: all",
            "              capabilities: [gpu]",
        ]))

    def test_default_compose_does_not_ask_for_a_gpu(self) -> None:
        compose = without_comments((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        self.assertNotRegex(compose, r"nvidia|capabilities:|gpus:")

    def test_env_example_defaults_to_cpu(self) -> None:
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^MOC_AI_DEVICE=(.*)$", example, re.M), ["cpu"])

    def test_installed_with_the_detector(self) -> None:
        runtime = re.search(r"^RUNTIME=\((.*?)\)", INSTALL.read_text(encoding="utf-8"), re.S | re.M).group(1).split()
        self.assertIn("docker-compose.gpu.yml", runtime)
        self.assertIn("scripts/co-gpu.sh", runtime)
        self.assertTrue(os.access(CO_GPU, os.X_OK), "chmod +x scripts/co-gpu.sh")


@unittest.skipUnless(shutil.which("make"), "cần GNU Make")
class MakefileTest(unittest.TestCase):
    """COMPOSE_FILE mà Makefile export (make chạy trong thư mục tạm, không gọi Docker)."""

    def compose_file(self, env: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(ROOT / "Makefile", tmp)
            (pathlib.Path(tmp) / ("." + "env")).write_text(env, encoding="utf-8")
            (pathlib.Path(tmp) / "in.mk").write_text("in-bien:\n\t@echo \"[$$COMPOSE_FILE]\"\n", encoding="utf-8")
            proc = subprocess.run(["make", "-s", "-f", "Makefile", "-f", "in.mk", "in-bien"], cwd=tmp,
                                  capture_output=True, text=True,
                                  env={k: v for k, v in {**os.environ, "MAKEFLAGS": ""}.items() if k != "COMPOSE_FILE"})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout.strip()

    def test_overlay_only_when_device_is_gpu(self) -> None:
        self.assertEqual(self.compose_file(""), "[]")
        self.assertEqual(self.compose_file("MOC_AI_DEVICE=cpu\n"), "[]")
        self.assertEqual(self.compose_file("MOC_AI_DEVICE=gpu\n"), "[docker-compose.yml:docker-compose.gpu.yml]")
        # dòng sau thắng như sed … | tail -n 1 của các biến khác
        self.assertEqual(self.compose_file("MOC_AI_DEVICE=gpu\nMOC_AI_DEVICE=cpu\n"), "[]")

    def test_gpu_overlay_comes_before_the_logs_overlay(self) -> None:
        self.assertEqual(self.compose_file("MOC_AI_DEVICE=gpu\nMOC_EXTRA_PROFILES=logs\n"),
                         "[docker-compose.yml:docker-compose.gpu.yml:platform/logs/docker-compose.logs.yml]")
        self.assertEqual(self.compose_file("MOC_AI_DEVICE=cpu\nMOC_EXTRA_PROFILES=logs\n"),
                         "[docker-compose.yml:platform/logs/docker-compose.logs.yml]")


def fake_bin(folder: pathlib.Path, *, gpus: str | None, runtimes: str | None) -> pathlib.Path:
    """nvidia-smi giả (None: lỗi như máy không có driver) và docker giả cho ``docker info`` (None: lỗi như Docker
    chưa chạy)."""
    folder.mkdir(parents=True, exist_ok=True)
    smi = f"printf '%s\\n' '{gpus}'" if gpus is not None else "echo 'NVIDIA-SMI has failed' >&2; exit 9"
    info = f"echo '{runtimes}'" if runtimes is not None else "echo 'Cannot connect to the Docker daemon' >&2; exit 1"
    for name, body in (("nvidia-smi", smi), ("docker", f'[ "$1" = info ] || exit 1\n{info}')):
        (folder / name).write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
        (folder / name).chmod(0o755)
    return folder


GPU_LINE = "GPU 0: Quadro M4000 (UUID: GPU-00000000-0000-0000-0000-000000000000)"
RUNTIMES = '{"io.containerd.runc.v2":{"path":"runc"},"nvidia":{"path":"nvidia-container-runtime"}}'


class CoGpuTest(unittest.TestCase):
    def run_script(self, **fake: str | None) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = fake_bin(pathlib.Path(tmp) / "bin", **fake)
            return subprocess.run(["bash", str(CO_GPU)], capture_output=True, text=True, timeout=30,
                                  env={"PATH": f"{bin_dir}:/usr/bin:/bin", "LANG": "C.UTF-8"})

    def assert_prints(self, expected: str, **fake: str | None) -> None:
        proc = self.run_script(**fake)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, expected + "\n", ""))

    def test_gpu_and_nvidia_runtime(self) -> None:
        self.assert_prints("gpu", gpus=GPU_LINE, runtimes=RUNTIMES)

    def test_gpu_without_the_container_toolkit(self) -> None:
        self.assert_prints("cpu", gpus=GPU_LINE, runtimes='{"runc":{"path":"runc"}}')

    def test_no_driver_or_no_docker(self) -> None:
        self.assert_prints("cpu", gpus=None, runtimes=RUNTIMES)
        self.assert_prints("cpu", gpus="No devices were found", runtimes=RUNTIMES)
        self.assert_prints("cpu", gpus=GPU_LINE, runtimes=None)


class InstallTest(unittest.TestCase):
    """make install ghi COMPOSE_FILE của bản cài theo MOC_AI_DEVICE; chỉ cảnh báo, không đổi MOC_AI_DEVICE thay người
    vận hành. Cây mã nguồn tạm, docker giả như test_cai_phien_ban.py."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.src = self.tmp / "signet-1.3.0"
        (self.src / "scripts").mkdir(parents=True)
        shutil.copy2(INSTALL, self.src / "scripts" / "install.sh")
        runtime = re.search(r"^RUNTIME=\((.*?)\)", INSTALL.read_text(encoding="utf-8"), re.S | re.M).group(1)
        for rel in runtime.split():
            path = self.src / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if "." in path.name:
                path.write_text("")
            else:
                path.mkdir(exist_ok=True)
        shutil.copy2(CO_GPU, self.src / "scripts" / "co-gpu.sh")
        (self.src / "docker-compose.yml").write_text(
            "services:\n  apisix:\n    build: ./x\n    image: moc/apisix:${MOC_VERSION:-dev}\n")
        (self.src / "VERSION").write_text("v1.3.0\n")
        self.bin = self.tmp / "bin"
        self.machine(gpus=None)
        self.dest = self.tmp / "moc"

    def machine(self, *, gpus: str | None) -> None:
        """nvidia-smi giả (máy chạy test có thể có GPU thật) và docker giả của test_cai_phien_ban.py có runtime
        nvidia trong docker info."""
        fake_bin(self.bin, gpus=gpus, runtimes=None)
        info = f"  \"ps \"*) ;;\n  info*) echo '{RUNTIMES}' ;;"
        (self.bin / "docker").write_text(DOCKER.replace('  "ps "*) ;;', info))

    def install(self, env: str) -> tuple[subprocess.CompletedProcess, str]:
        (self.src / ".env").write_text("POSTGRES_PASSWORD=thu\n" + env)
        proc = subprocess.run(["bash", str(self.src / "scripts" / "install.sh"), "install", str(self.dest)],
                              capture_output=True, text=True, timeout=60,
                              env={"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.tmp), "LANG": "C.UTF-8",
                                   "GIT_CEILING_DIRECTORIES": str(self.tmp), "FAKE_DIR": str(self.tmp)})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc, (self.dest / ".env").read_text(encoding="utf-8")

    def test_gpu_writes_the_overlay_and_warns_when_the_machine_cannot(self) -> None:
        proc, env = self.install("MOC_AI_DEVICE=gpu\n")      # nvidia-smi lỗi: chưa có driver
        self.assertIn("\nCOMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml\n", env)
        self.assertIn("MOC_AI_DEVICE=gpu nhưng chưa thấy GPU NVIDIA", proc.stderr)
        self.assertIn("\nMOC_AI_DEVICE=gpu\n", env)

    def test_cpu_leaves_compose_file_alone_and_hints_when_a_gpu_is_usable(self) -> None:
        self.machine(gpus=GPU_LINE)
        proc, env = self.install("MOC_AI_DEVICE=cpu\n")
        self.assertNotIn("COMPOSE_FILE=", env)
        self.assertIn("Máy có GPU NVIDIA dùng được trong Docker: đặt MOC_AI_DEVICE=gpu", proc.stdout)

    def test_switching_back_to_cpu_drops_the_overlay(self) -> None:
        self.install("MOC_AI_DEVICE=gpu\n")
        installed = self.dest / ".env"
        installed.write_text(installed.read_text().replace("MOC_AI_DEVICE=gpu", "MOC_AI_DEVICE=cpu"))
        _, env = self.install("")
        self.assertIn("\nCOMPOSE_FILE=docker-compose.yml\n", env)


if __name__ == "__main__":
    unittest.main()
