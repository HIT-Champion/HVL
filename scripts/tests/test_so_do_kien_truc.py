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

"""Sơ đồ kiến trúc của README (scripts/so_do_kien_truc.py): SVG hợp lệ ở cả hai thứ tiếng, đủ logo và có ghi nguồn,
GIF lặp khép kín (khung sau một vòng trùng khung đầu), README trỏ đúng ảnh. Ghép GIF cần Chromium và FFmpeg nên không
chạy ở đây. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest
import xml.etree.ElementTree as ET
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
spec = importlib.util.spec_from_file_location("so_do_kien_truc", SCRIPTS / "so_do_kien_truc.py")
so_do: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(so_do)
SVG = "{http://www.w3.org/2000/svg}"


class SoDoKienTruc(unittest.TestCase):
    def test_svg_hop_le_ca_hai_thu_tieng(self):
        so_logo = sum(len(v) for v in so_do.LOGO.values())
        for lang in ("vi", "en"):
            for khung in (None, 1.2):
                with self.subTest(lang=lang, khung=khung):
                    svg = so_do.ve(lang, khung)
                    root = ET.fromstring(svg)
                    self.assertEqual(root.tag, f"{SVG}svg")
                    self.assertEqual(root.findtext(f"{SVG}title"), so_do.T[lang]["title"])
                    self.assertEqual(len(root.findall(f"{SVG}image")), so_logo)
                    # logo nhúng thẳng vào tệp: GitHub không tải tài nguyên ngoài của SVG trong thẻ <img>
                    self.assertNotIn("file:", svg)
                    self.assertNotIn(str(ROOT), svg)

    def test_hai_thu_tieng_cung_khoa(self):
        self.assertEqual(so_do.T["vi"].keys(), so_do.T["en"].keys())

    def test_logo_du_va_co_ghi_nguon(self):
        dung = {n for names in so_do.LOGO.values() for n in names}
        co = {p.stem for p in so_do.THU_MUC_LOGO.glob("*.png")}
        self.assertEqual(dung, co, "logo thiếu tệp, hoặc tệp logo không dùng tới")
        nguon = (so_do.THU_MUC_LOGO / "NGUON.md").read_text(encoding="utf-8")
        for n in sorted(dung):
            with self.subTest(logo=n):
                self.assertTrue((so_do.THU_MUC_LOGO / f"{n}.png").read_bytes().startswith(b"\x89PNG"))
                self.assertIn(f"`{n}.png`", nguon)

    def test_vong_lap_khep_kin(self):
        self.assertAlmostEqual(so_do.SO_KHUNG * so_do.BUOC, so_do.XUNG)
        self.assertAlmostEqual(so_do.XUNG / so_do.NET, round(so_do.XUNG / so_do.NET))
        self.assertAlmostEqual(so_do.NET / so_do.BUOC, round(so_do.NET / so_do.BUOC))
        for lang in ("vi", "en"):
            with self.subTest(lang=lang):
                self.assertEqual(so_do.ve(lang, 0), so_do.ve(lang, so_do.SO_KHUNG * so_do.BUOC))
                self.assertNotEqual(so_do.ve(lang, 0), so_do.ve(lang, so_do.BUOC))

    def test_vi_tri_tren_duong(self):
        path = "M0,0 H10 V10"
        self.assertEqual(so_do.vi_tri(path, 0), (0, 0))
        self.assertEqual(so_do.vi_tri(path, 0.5), (10, 0))
        self.assertEqual(so_do.vi_tri(path, 0.75), (10, 5))
        self.assertEqual(so_do.vi_tri(path, 1), (10, 10))
        self.assertEqual([so_do.do_mo(p) for p in (0, 0.05, 0.5, 1)], [0, 1, 1, 0])

    def test_readme_tro_dung_anh(self):
        for readme, gif in (("README.md", "kien-truc-tong-the.gif"), ("README.en.md", "kien-truc-tong-the.en.gif")):
            with self.subTest(readme=readme):
                self.assertIn(f"docs/anh/{gif}", (ROOT / readme).read_text(encoding="utf-8"))
                self.assertTrue((ROOT / "docs" / "anh" / gif).read_bytes().startswith(b"GIF89a"))


if __name__ == "__main__":
    unittest.main()
