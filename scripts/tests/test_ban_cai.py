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

"""Bản cài (`make install` → scripts/install.sh) chỉ chép các tệp trong RUNTIME: mọi script Python được chép phải chạy
được ở /opt/moc, tức mọi module cục bộ (scripts/<tên>.py) nó import — kể cả import trong hàm — cũng có trong RUNTIME.
Thiếu nap_lo_mau.py từng làm mọi lệnh demo.py ở bản online dừng với ModuleNotFoundError (#174).
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import ast
import pathlib
import re
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent


def runtime() -> list[str]:
    install = (SCRIPTS / "install.sh").read_text(encoding="utf-8")
    return re.search(r"^RUNTIME=\((.*?)\)", install, re.M | re.S).group(1).split()


def local_imports(path: pathlib.Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return {n for n in names if (SCRIPTS / f"{n}.py").exists()}


class RuntimeTest(unittest.TestCase):
    def test_every_installed_script_has_its_local_imports(self) -> None:
        files = runtime()
        scripts = [rel for rel in files if rel.startswith("scripts/") and rel.endswith(".py")]
        missing = sorted((rel, f"scripts/{name}.py") for rel in scripts
                         for name in local_imports(ROOT / rel) if f"scripts/{name}.py" not in files)
        self.assertEqual(missing, [], "thêm vào RUNTIME của scripts/install.sh")

    def test_demo_brings_the_sample_batch(self) -> None:
        # demo.py import nap_lo_mau ở đầu tệp; nap_lo_mau đọc seed/nap-lo/van-ban-den.csv — cả thư mục seed được chép
        self.assertIn("nap_lo_mau", local_imports(SCRIPTS / "demo.py"))
        self.assertIn("scripts/nap_lo_mau.py", runtime())
        self.assertIn("seed", runtime())
        self.assertTrue((ROOT / "seed" / "nap-lo" / "van-ban-den.csv").is_file())

    def test_runtime_entries_exist(self) -> None:
        self.assertEqual([rel for rel in runtime() if not (ROOT / rel).exists()], [])

    def test_every_make_demo_script_is_installed(self) -> None:
        # Bản cài không có Makefile: màn make demo-… chạy bằng python3 scripts/<tệp>.py trong /opt/moc
        # (docs/demo-script.md, Phương án dự phòng). Thiếu demo_tat_van_phong.py từng làm màn đó không có ở bản cài
        make = (ROOT / "Makefile").read_text(encoding="utf-8")
        recipes = re.findall(r"^demo-[\w-]+:.*\n((?:\t.*\n)+)", make, re.M)
        used = sorted({f"scripts/{name}.py" for recipe in recipes
                       for name in re.findall(r"python3 scripts/(\w+)\.py", recipe)})
        self.assertIn("scripts/demo_tat_van_phong.py", used)
        self.assertEqual([rel for rel in used if rel not in runtime()], [], "thêm vào RUNTIME của scripts/install.sh")


if __name__ == "__main__":
    unittest.main()
