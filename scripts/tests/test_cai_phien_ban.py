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

"""make install trên máy chưa từng chạy make up (#186): Makefile truyền MOC_VERSION rỗng, install.sh tự lấy phiên bản
từ tệp VERSION, dựng image thẻ đó và bước kiểm cuối phải tìm đúng thẻ đó — không phải thẻ dev mà compose suy ra khi
biến môi trường rỗng đè lên .env của bản cài. Chạy scripts/install.sh thật trong một cây mã nguồn tạm với docker giả
theo đúng thứ tự ưu tiên của compose (biến môi trường đã đặt, kể cả rỗng, thắng .env).
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

INSTALL = pathlib.Path(__file__).resolve().parent.parent / "install.sh"

# docker giả: một dịch vụ apisix dựng từ mã nguồn, image moc/apisix:${MOC_VERSION:-dev}
DOCKER = r"""#!/usr/bin/env bash
case "$*" in
  *"config --format json"*)
    if grep -q 'build:' docker-compose.yml; then
      echo '{"services": {"apisix": {"build": {"context": "x"}, "volumes": []}}}'
    else
      echo '{"services": {"apisix": {"volumes": []}}}'
    fi ;;
  *" build"*) printf '%s' "${MOC_VERSION:-dev}" > "$FAKE_DIR/built" ;;
  *"config --images"*)
    if [ "${MOC_VERSION+đặt}" = đặt ]; then tag=${MOC_VERSION:-dev}
    else tag=$(sed -n 's/^MOC_VERSION=//p' .env | tail -n 1); tag=${tag:-dev}; fi
    echo "moc/apisix:$tag" ;;
  "image inspect "*) [ "$3" = "moc/apisix:$(cat "$FAKE_DIR/built")" ] ;;
  "ps "*) ;;
  *) echo "docker giả: không biết $*" >&2; exit 1 ;;
esac
"""


class InstallVersionTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.src = self.tmp / "signet-1.2.0"
        (self.src / "scripts").mkdir(parents=True)
        shutil.copy2(INSTALL, self.src / "scripts" / "install.sh")
        # mọi tệp chạy install.sh chép sang bản cài (RUNTIME) phải có trong cây mã nguồn
        runtime = re.search(r"^RUNTIME=\((.*?)\)", INSTALL.read_text(encoding="utf-8"), re.S | re.M).group(1)
        for rel in runtime.split():
            path = self.src / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if "." in path.name:
                path.write_text("")
            else:
                path.mkdir(exist_ok=True)
        (self.src / "docker-compose.yml").write_text(
            "services:\n  apisix:\n    build: ./x\n    image: moc/apisix:${MOC_VERSION:-dev}\n")
        (self.src / ".env").write_text("POSTGRES_PASSWORD=thu\n")
        # gói phát hành: git archive điền thẻ vào dòng cuối VERSION
        (self.src / "VERSION").write_text("$Format:%(describe)$\nv1.2.0\n")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "docker").write_text(DOCKER)
        (bin_dir / "docker").chmod(0o755)
        self.env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(self.tmp), "LANG": "C.UTF-8",
                    "GIT_CEILING_DIRECTORIES": str(self.tmp), "FAKE_DIR": str(self.tmp)}
        self.dest = self.tmp / "moc"

    def install(self, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.src / "scripts" / "install.sh"), "install", str(self.dest)],
                              env={**self.env, **env}, capture_output=True, text=True, timeout=60)

    def test_empty_moc_version_from_make(self) -> None:
        # Makefile: MOC_VERSION="$(MOC_VERSION)" ./scripts/install.sh … — biến có đặt, giá trị rỗng
        proc = self.install(MOC_VERSION="")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Đã cài Signet 1.2.0", proc.stdout)
        self.assertEqual((self.tmp / "built").read_text(), "1.2.0")
        self.assertIn("MOC_VERSION=1.2.0\n", (self.dest / ".env").read_text())

    def test_moc_version_set_by_hand(self) -> None:
        proc = self.install(MOC_VERSION="1.1.0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((self.tmp / "built").read_text(), "1.1.0")
        self.assertIn("MOC_VERSION=1.1.0\n", (self.dest / ".env").read_text())

    def test_missing_image_is_still_caught(self) -> None:
        # bước kiểm vẫn có tác dụng: image đúng thẻ không có (vd dựng hỏng) thì báo thiếu
        fake = self.tmp / "bin" / "docker"
        fake.write_text(fake.read_text().replace('printf \'%s\' "${MOC_VERSION:-dev}"', "printf 'khac'"))
        proc = self.install(MOC_VERSION="")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("thiếu image moc/apisix:1.2.0", proc.stderr)


if __name__ == "__main__":
    unittest.main()
