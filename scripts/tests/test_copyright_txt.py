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

"""COPYRIGHT.txt (#346): bảng phần mềm thượng nguồn sinh từ DEPENDENCIES.md. Bản trong git phải đúng bằng bản sinh lại,
nên thêm, bỏ hay nâng một thành phần trong DEPENDENCIES.md mà quên `make copyright` thì test đỏ. Mỗi image trong
docker-compose.yml phải có dòng trong bảng, để COPYRIGHT.txt không thiếu thứ đang chạy. Không cần Docker, không đọc
.env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib
import pathlib
import re
import sys
import unittest
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent

copyright_txt: Any = None


def setUpModule() -> None:
    global copyright_txt
    sys.path.insert(0, str(SCRIPTS))
    copyright_txt = importlib.import_module("copyright_txt")


def tearDownModule() -> None:
    sys.path.remove(str(SCRIPTS))


def rows() -> list[dict[str, str]]:
    source = (ROOT / "DEPENDENCIES.md").read_text(encoding="utf-8")
    return [r for _, group in copyright_txt.components(source) for r in group]


class CopyrightFile(unittest.TestCase):
    def test_copyright_in_git_matches_dependencies(self) -> None:
        page = ROOT / "COPYRIGHT.txt"
        self.assertTrue(page.exists(), "thiếu COPYRIGHT.txt: chạy make copyright")
        self.assertEqual(page.read_text(encoding="utf-8"),
                         copyright_txt.render((ROOT / "DEPENDENCIES.md").read_text(encoding="utf-8")),
                         "COPYRIGHT.txt cũ so với DEPENDENCIES.md: chạy make copyright")

    def test_every_component_has_version_license_description_and_homepage(self) -> None:
        listed = rows()
        self.assertGreater(len(listed), 50)
        for r in listed:
            with self.subTest(component=r["ten"]):
                self.assertTrue(r["phien_ban"] and r["giay_phep"], r)
                # Tên trong DEPENDENCIES.md viết thành liên kết tới trang chủ của dự án
                self.assertRegex(r["trang_chu"], r"^https://\S+( https://\S+)*$")
                # Vế đầu của cột Vai trò là mô tả: phải tự đứng được, không chỉ là "CI"
                self.assertGreaterEqual(len(r["mo_ta"]), 5, r["vai_tro"])

    def test_only_components_in_use(self) -> None:
        # Thành phần dự kiến hay đã bỏ nằm ở mục "Thành phần đã cân nhắc nhưng không dùng", không ở bảng đang dùng
        for r in rows():
            self.assertNotRegex(r["vai_tro"], r"(?i)chưa đưa vào|dự kiến|\(Could\)", r["ten"])

    def test_every_compose_image_is_listed(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        loaded = " ".join(r["cach_nap"] for r in rows())
        images = set(re.findall(r"^\s*image:\s*['\"]?([^\s'\"#]+)", compose, re.M))
        third_party = {i.split("@")[0] for i in images if not i.startswith("moc/") and "${" not in i}
        self.assertGreater(len(third_party), 10)
        for image in sorted(third_party):
            self.assertIn(image, loaded, f"{image} chạy trong docker-compose.yml nhưng DEPENDENCIES.md chưa ghi")


class Helpers(unittest.TestCase):
    def test_description_is_the_first_clause_of_the_role(self) -> None:
        d = copyright_txt.description
        self.assertEqual(d("Định danh tập trung: SSO, MFA"), "Định danh tập trung")
        self.assertEqual(d("Quét bí mật lộ trong lịch sử commit (CI)"), "Quét bí mật lộ trong lịch sử commit")
        self.assertEqual(d("Két bí mật — thay Vault; không lưu khóa"), "Két bí mật")
        self.assertEqual(d("Chạy `make seed`, `make smoke`"), "Chạy make seed, make smoke")

    def test_license_keeps_short_notes_only(self) -> None:
        lic = copyright_txt.license_text
        self.assertEqual(lic("BSD-3-Clause (truststore: MIT)"), "BSD-3-Clause (truststore: MIT)")
        self.assertEqual(lic("Apache-2.0 (đã kiểm model card và tệp LICENSE trên Hugging Face của đúng cỡ 1.7B)"),
                         "Apache-2.0")

    def test_version_and_links(self) -> None:
        self.assertEqual(copyright_txt.version("5.5.0 (gói Debian trixie `tesseract-ocr` 5.5.0-1+b1)"), "5.5.0")
        self.assertEqual(copyright_txt.plain("[Coraza](https://coraza.io) + [OWASP CRS](https://coreruleset.org)"),
                         "Coraza + OWASP CRS")

    def test_table_wraps_inside_columns(self) -> None:
        row = {"ten": "pyHanko (+ pyhanko-certvalidator, asn1crypto, tzlocal)", "phien_ban": "0.37.0",
               "giay_phep": "MIT", "mo_ta": "Ký số PAdES bản phát hành bằng khóa trong Transit, kiểm chữ ký",
               "trang_chu": "https://a.example https://b.example"}
        lines = copyright_txt.table([row])
        self.assertGreater(len(lines), 1)
        start = sum(copyright_txt.WIDTHS) + len(copyright_txt.GAP) * len(copyright_txt.WIDTHS)
        self.assertEqual([line[start:] for line in lines[:2]], ["https://a.example", "https://b.example"])
        # svc-workflow không bị ngắt ở gạch nối
        wrapped = copyright_txt.table([dict(row, mo_ta="Hộp thư thử cho thông báo email của svc-workflow")])
        self.assertTrue(any("svc-workflow" in line for line in wrapped))


if __name__ == "__main__":
    unittest.main()
