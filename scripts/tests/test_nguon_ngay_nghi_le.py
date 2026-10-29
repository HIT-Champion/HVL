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

"""Nguồn công khai B (#427, scripts/nguon_ngay_nghi_le.py): bản chụp seed/du-lieu-mo/ngay-nghi-le khớp manifest
(SHA-256, byte) và khớp bảng PAGES/FIXED; lấy mới bằng trang giả kiểm đủ ngày, thiếu ngày thì lỗi; lỗi thì giữ bản chụp cũ.
Không gọi mạng. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
SNAPSHOT = ROOT / "seed" / "du-lieu-mo" / "ngay-nghi-le"
MANIFEST_KEYS = {"source", "name", "publisher", "home_url", "reuse_basis", "licence", "fetched_at", "max_age_days",
                 "files"}
FILE_KEYS = {"file", "url", "sha256", "bytes", "fetched_at", "meta"}

nguon = None


def setUpModule() -> None:
    global nguon
    sys.path.insert(0, str(SCRIPTS))
    nguon = importlib.import_module("nguon_ngay_nghi_le")


def tearDownModule() -> None:
    sys.path.remove(str(SCRIPTS))


def _page(spec: dict, drop: str | None = None) -> bytes:
    """Trang giả: mỗi chuỗi cần kiểm nằm trong một đoạn đủ dài, kèm script và tiêu đề ngắn bị bỏ."""
    paras = [f"<p>Theo thông báo, cán bộ công chức được nghỉ từ ngày {n} theo lịch đã công bố.</p>"
             for item in spec["items"] for n in item[5] if n != drop]
    return ("<html><script>var x = '16/02/2026';</script><h1>Lịch nghỉ</h1>" + "".join(paras) + "</html>").encode()


def _fake_fetch(drop: str | None = None):
    pages = {spec["url"]: _page(spec, drop) for spec in nguon.PAGES}
    return lambda url: pages[url]


def _flat(text: str) -> str:
    return " ".join(text.split())


class SnapshotTest(unittest.TestCase):
    """Bản chụp trong repo là thứ svc-workflow đọc khi không có mạng."""

    def setUp(self) -> None:
        self.manifest = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))

    def test_manifest_follows_the_shared_contract(self) -> None:
        self.assertEqual(set(self.manifest), MANIFEST_KEYS)
        self.assertEqual(self.manifest["source"], nguon.NGUON)
        self.assertEqual(self.manifest["name"], nguon.TEN)
        self.assertIn("Điều 15", self.manifest["reuse_basis"])
        for entry in self.manifest["files"]:
            self.assertEqual(set(entry), FILE_KEYS)
            self.assertTrue(entry["url"].startswith("https://baochinhphu.vn/"), entry["url"])

    def test_every_file_matches_its_sha256_and_nothing_else_is_there(self) -> None:
        listed = {e["file"] for e in self.manifest["files"]}
        on_disk = {p.relative_to(SNAPSHOT).as_posix() for p in SNAPSHOT.rglob("*") if p.is_file()}
        self.assertEqual(on_disk - {"manifest.json"}, listed)
        for entry in self.manifest["files"]:
            data = (SNAPSHOT / entry["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"], entry["file"])
            self.assertEqual(len(data), entry["bytes"], entry["file"])
        self.assertLess(sum(p.stat().st_size for p in SNAPSHOT.rglob("*") if p.is_file()), 3_000_000)

    def test_the_data_file_is_what_build_makes_from_the_table(self) -> None:
        pages = {spec["url"]: _page(spec) for spec in nguon.PAGES}
        data, _ = nguon.build(pages, self.manifest["fetched_at"])
        snap = json.loads((SNAPSHOT / nguon.DATA_FILE).read_text(encoding="utf-8"))
        self.assertEqual(snap, data)

    def test_each_quote_names_its_source_and_holds_every_date(self) -> None:
        for spec in nguon.PAGES:
            text = (SNAPSHOT / spec["file"]).read_text(encoding="utf-8")
            self.assertIn(spec["url"], text)
            for item in spec["items"]:
                for needle in item[5]:
                    self.assertIn(needle, _flat(text), f"{spec['file']}: {needle}")
            self.assertTrue(all(len(line) <= nguon.WIDTH for line in text.splitlines() if "://" not in line))


class TableTest(unittest.TestCase):
    def test_days_off_are_real_dates_and_make_up_days_are_saturdays(self) -> None:
        for spec in nguon.PAGES:
            for kind, first, last, *_ in spec["items"]:
                self.assertLessEqual(date.fromisoformat(first), date.fromisoformat(last))
                if kind == "work":
                    self.assertEqual(date.fromisoformat(first).weekday(), 5, first)
        for mmdd, _, basis in nguon.FIXED:
            date.fromisoformat(f"2028-{mmdd}")
            self.assertTrue(basis)


class FetchTest(unittest.TestCase):
    def test_lay_writes_quotes_and_data_with_matching_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            manifest = nguon.lay(folder, fetch=_fake_fetch())
            self.assertEqual(set(manifest), MANIFEST_KEYS)
            self.assertEqual(len(manifest["files"]), len(nguon.PAGES) + 1)
            for entry in manifest["files"]:
                data = (folder / entry["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            text = (folder / nguon.PAGES[0]["file"]).read_text(encoding="utf-8")
            self.assertNotIn("var x", text)
            self.assertNotIn("Lịch nghỉ\n", text)

    def test_a_page_that_lost_a_date_fails_with_its_url(self) -> None:
        spec = nguon.PAGES[-1]
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, spec["url"]):
            nguon.lay(pathlib.Path(tmp), fetch=_fake_fetch(drop=spec["items"][1][5][0]))

    def test_main_keeps_the_old_snapshot_when_fetching_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "ngay-nghi-le"
            target.mkdir()
            (target / "manifest.json").write_text("{}", encoding="utf-8")
            err = io.StringIO()
            with mock.patch.object(nguon, "lay", side_effect=OSError("mất mạng")), contextlib.redirect_stderr(err):
                self.assertEqual(nguon.main([str(target)]), 1)
            self.assertIn("Giữ bản chụp cũ", err.getvalue())
            self.assertEqual((target / "manifest.json").read_text(encoding="utf-8"), "{}")

    def test_main_replaces_the_snapshot_after_a_good_fetch(self) -> None:
        real = nguon.lay
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "ngay-nghi-le"
            target.mkdir()
            (target / "cu.txt").write_text("cũ", encoding="utf-8")
            with mock.patch.object(nguon, "lay", lambda d: real(d, fetch=_fake_fetch())), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(nguon.main([str(target)]), 0)
            self.assertFalse((target / "cu.txt").exists())
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual({e["file"] for e in manifest["files"]},
                             {nguon.DATA_FILE} | {spec["file"] for spec in nguon.PAGES})


if __name__ == "__main__":
    unittest.main()
