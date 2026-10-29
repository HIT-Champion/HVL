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

"""Dữ liệu công khai (#424, scripts/du_lieu_mo.py, scripts/nguon_cong_bao_gddt.py): bản chụp đã commit khớp manifest và
khuôn của hợp đồng; kiểm phát hiện sai băm, thiếu tệp, tên tệp lạ, dữ liệu cũ; lấy lỗi thì giữ bản cũ; trang Công báo
đọc đúng; lô văn bản đến sinh từ bản chụp qua được bộ đọc của svc-files (imports/parse.py). Không gọi mạng, không cần
Docker, không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import pathlib
import re
import shutil
import sys
import tempfile
import types
import unittest
import zipfile
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
SNAPSHOT = ROOT / "seed" / "du-lieu-mo" / "cong-bao-gddt"
PARSE = ROOT / "services" / "svc-files" / "src" / "svc_files" / "imports" / "parse.py"
MIGRATIONS = ROOT / "db" / "migrations" / "default"

dlm: Any = None
nguon: Any = None
parse: Any = None


def setUpModule() -> None:
    global dlm, nguon, parse
    sys.path.insert(0, str(SCRIPTS))
    dlm = importlib.import_module("du_lieu_mo")
    nguon = importlib.import_module("nguon_cong_bao_gddt")
    spec = importlib.util.spec_from_file_location("du_lieu_mo_parse", PARSE)
    parse = importlib.util.module_from_spec(spec)
    sys.modules["du_lieu_mo_parse"] = parse      # dataclass cần tìm thấy module của mình
    spec.loader.exec_module(parse)


def tearDownModule() -> None:
    sys.modules.pop("du_lieu_mo_parse", None)
    if str(SCRIPTS) in sys.path:
        sys.path.remove(str(SCRIPTS))


def manifest() -> dict[str, Any]:
    return json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))


def page(symbol: str = "26/2026/TT-BGDĐT", summary: str = "Quy định chuẩn nghề nghiệp giảng viên đại học") -> str:
    """Phần trang văn bản Công báo mà bộ đọc dùng (khuôn của trang thật, 30/10/2026), chữ có thực thể HTML."""
    def row(name: str, value: str) -> str:
        return (f'<div class="row"> <span class="name"> {name} </span> <div class="value">\n'
                f'<span class="child-value"> {value} </span> </div> </div>')
    return "\n".join([
        row("Loại văn bản", "Th&#xF4;ng t&#x1B0;"), row("Số, ký hiệu", symbol),
        row("Cơ quan ban hành", "B&#x1ED8; GI&#xC1;O D&#x1EE4;C V&#xC0; &#x110;&#xC0;O T&#x1EA0;O"),
        row("Ngày ban hành", "09/04/2026"), row("Trích yếu", summary), row("Người ký", "NGƯỜI KÝ"),
        '<a href="/van-ban/x/64302.htm" title="Công báo số 249 ngày 2026-04-26" class="item">Số 249</a>',
        '<a href="https://g7.cdnchinhphu.vn/api/download/stream?Url=abc~~&amp;file_name=2026_249.docx">docx</a>',
        '<a href="https://g7.cdnchinhphu.vn/api/download/stream?Url=def~~&amp;file_name=2026_249.pdf">pdf</a>',
    ])


class Snapshot(unittest.TestCase):
    def test_committed_snapshot_matches_its_manifest(self) -> None:
        got = dlm.check(SNAPSHOT)
        self.assertEqual(got["problems"], [])
        self.assertIn(got["state"], ("ok", "stale"))
        total = sum(p.stat().st_size for p in SNAPSHOT.glob("*.pdf"))
        self.assertLessEqual(total, dlm.MAX_BYTES)

    def test_manifest_follows_the_contract(self) -> None:
        m = manifest()
        self.assertEqual(m["source"], nguon.NGUON)
        self.assertEqual(m["name"], nguon.TEN)
        self.assertIsNone(m["licence"])
        self.assertIn("Điều 15", m["reuse_basis"])
        self.assertIn("congbao.chinhphu.vn", m["reuse_basis"])
        self.assertEqual([f["file"] for f in m["files"]], [name for _, name, _ in nguon.VAN_BAN])
        self.assertEqual(sorted(p.name for p in SNAPSHOT.glob("*.pdf")), sorted(f["file"] for f in m["files"]))
        for f, (slug, _, symbol) in zip(m["files"], nguon.VAN_BAN, strict=True):
            meta = f["meta"]
            self.assertEqual(set(meta), {"symbol", "issuer_name", "issued_on", "type_code", "summary", "page_url",
                                         "gazette"})
            self.assertEqual(meta["symbol"], symbol)
            self.assertEqual(meta["page_url"], f"https://congbao.chinhphu.vn/van-ban/{slug}.htm")
            self.assertTrue(f["url"].startswith(nguon.DOWNLOAD_HOST), f["url"])
            self.assertRegex(meta["gazette"], r"^Công báo số \d+ ngày \d{2}/\d{2}/\d{4}$")
            self.assertTrue((SNAPSHOT / f["file"]).read_bytes().startswith(b"%PDF-"))

    def test_document_type_exists_in_the_catalog(self) -> None:
        sql = (MIGRATIONS / "1792281604000_document_type_tt" / "up.sql").read_text(encoding="utf-8")
        self.assertIn(f"('{nguon.TYPE_CODE}', 'Thông tư', true)", sql)
        self.assertTrue({f["meta"]["type_code"] for f in manifest()["files"]} == {nguon.TYPE_CODE})

    def test_licence_is_declared_for_the_pdfs(self) -> None:
        reuse = (ROOT / "REUSE.toml").read_text(encoding="utf-8")
        self.assertIn('"seed/du-lieu-mo/cong-bao-gddt/*.pdf"', reuse)
        self.assertIn('SPDX-License-Identifier = "LicenseRef-VN-SHTT-Dieu-15"', reuse)
        self.assertTrue((ROOT / "LICENSES" / "LicenseRef-VN-SHTT-Dieu-15.txt").is_file())

    def test_registered_in_moc_and_make(self) -> None:
        self.assertIn("du_lieu_mo.add_parser(groups)", (SCRIPTS / "moc.py").read_text(encoding="utf-8"))
        self.assertIn("du_lieu_mo.nap()", (SCRIPTS / "seed.py").read_text(encoding="utf-8"))
        make = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(make, r"(?m)^du-lieu-mo:.*\n\t@python3 scripts/du_lieu_mo.py kiem$")
        self.assertIn("./seed/du-lieu-mo:/srv/du-lieu-mo:ro", (ROOT / "docker-compose.yml").read_text())


class Check(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.dir = self.tmp / "cong-bao-gddt"
        shutil.copytree(SNAPSHOT, self.dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def write(self, m: dict[str, Any]) -> None:
        (self.dir / "manifest.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

    def test_changed_byte_missing_file_and_wrong_size_are_broken(self) -> None:
        first = self.dir / manifest()["files"][0]["file"]
        data = bytearray(first.read_bytes())
        data[-1] ^= 1
        first.write_bytes(bytes(data))
        (self.dir / manifest()["files"][1]["file"]).unlink()
        got = dlm.check(self.dir)
        self.assertEqual(got["state"], "broken")
        self.assertTrue(any("SHA-256 không khớp" in p for p in got["problems"]), got["problems"])
        self.assertTrue(any("không có tệp" in p for p in got["problems"]), got["problems"])
        first.write_bytes(bytes(data) + b"x")
        self.assertTrue(any("cỡ" in p for p in dlm.check(self.dir)["problems"]))

    def test_names_outside_the_folder_and_bad_manifests_are_broken(self) -> None:
        for name in ("../manifest.json", "a/../b.pdf", "/b.pdf", "a/b/c.pdf", "a/.b.pdf", "manifest.json", ".an.pdf",
                     "TT.PDF"):
            m = manifest()
            m["files"][0]["file"] = name
            self.write(m)
            self.assertEqual(dlm.check(self.dir)["state"], "broken", name)
        (self.dir / "manifest.json").write_text("{", encoding="utf-8")
        self.assertEqual(dlm.check(self.dir)["state"], "broken")
        for key, value in (("source", "khac"), ("fetched_at", "2026-10-30T02:00:00"), ("max_age_days", 0),
                           ("files", [])):
            m = manifest()
            m[key] = value
            self.write(m)
            self.assertEqual(dlm.check(self.dir)["state"], "broken", key)

    def test_one_subfolder_is_allowed(self) -> None:
        # khuôn của nguồn ngay-nghi-le: câu trích ở trich/*.txt
        m = manifest()
        name = m["files"][0]["file"]
        (self.dir / "trich").mkdir()
        (self.dir / name).rename(self.dir / "trich" / name)
        m["files"][0]["file"] = f"trich/{name}"
        self.write(m)
        self.assertEqual(dlm.check(self.dir)["problems"], [])

    def test_old_snapshot_is_stale_not_broken(self) -> None:
        at = datetime.fromisoformat(manifest()["fetched_at"])
        self.assertEqual(dlm.check(self.dir, at + timedelta(days=400))["state"], "ok")
        got = dlm.check(self.dir, at + timedelta(days=401))
        self.assertEqual((got["state"], got["age_days"], got["problems"]), ("stale", 401, []))

    def test_kiem_exits_1_only_when_broken(self) -> None:
        with mock.patch.object(dlm, "DIR", self.tmp), mock.patch.object(dlm, "ROOT", self.tmp.parent):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(dlm.main(["kiem"]), 0)
            self.assertIn("cong-bao-gddt: ok", out.getvalue())
            (self.dir / manifest()["files"][0]["file"]).unlink()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(dlm.main(["kiem", "--json"]), 1)


class Lay(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.dir = self.tmp / "cong-bao-gddt"
        shutil.copytree(SNAPSHOT, self.dir)
        (self.dir / "cu.pdf").write_bytes(b"%PDF-cu")
        old = manifest()
        old["files"].append({"file": "cu.pdf", "url": "https://x", "sha256": "0" * 64, "bytes": 7, "meta": {}})
        (self.dir / "manifest.json").write_text(json.dumps(old), encoding="utf-8")
        self.before = {p.name: p.read_bytes() for p in self.dir.iterdir()}

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def run_lay(self, fake: Any) -> int:
        mod = types.SimpleNamespace(NGUON="cong-bao-gddt", lay=fake)
        with (mock.patch.object(dlm, "DIR", self.tmp), mock.patch.object(dlm, "ROOT", self.tmp.parent),
              mock.patch.object(dlm, "sources", lambda: {"cong-bao-gddt": mod}),
              contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
            return dlm.main(["lay"])

    def test_source_error_or_bad_files_keep_the_old_snapshot(self) -> None:
        def offline(_: pathlib.Path) -> dict[str, Any]:
            raise OSError("nguồn ngừng hoạt động")

        def wrong_hash(folder: pathlib.Path) -> dict[str, Any]:
            m = manifest()
            for f in m["files"]:
                (folder / f["file"]).write_bytes(b"%PDF-khac")
            return m

        for fake in (offline, wrong_hash):
            self.assertEqual(self.run_lay(fake), 1, fake.__name__)
            self.assertEqual({p.name: p.read_bytes() for p in self.dir.iterdir()}, self.before)

    def test_new_snapshot_replaces_files_keeps_readme_drops_unlisted(self) -> None:
        def fresh(folder: pathlib.Path) -> dict[str, Any]:
            m = manifest()
            for f in m["files"]:
                shutil.copyfile(SNAPSHOT / f["file"], folder / f["file"])
            m["fetched_at"] = "2026-10-31T09:00:00+07:00"
            return m

        self.assertEqual(self.run_lay(fresh), 0)
        self.assertFalse((self.dir / "cu.pdf").exists())
        self.assertEqual((self.dir / "README.md").read_bytes(), self.before["README.md"])
        fetched = json.loads((self.dir / "manifest.json").read_text())["fetched_at"]
        self.assertEqual(fetched, "2026-10-31T09:00:00+07:00")
        self.assertEqual(dlm.check(self.dir)["problems"], [])
        self.assertEqual([p.name for p in self.dir.iterdir() if p.name.startswith(".")], [])

    def test_files_in_a_subfolder_are_written_there(self) -> None:
        def nested(folder: pathlib.Path) -> dict[str, Any]:
            m = manifest()
            (folder / "trich").mkdir()
            for f in m["files"]:
                shutil.copyfile(SNAPSHOT / f["file"], folder / "trich" / f["file"])
                f["file"] = f"trich/{f['file']}"
            return m

        self.assertEqual(self.run_lay(nested), 0)
        self.assertEqual(dlm.check(self.dir)["problems"], [])
        self.assertEqual(sorted(p.name for p in self.dir.glob("*.pdf")), [])      # bản cũ ở gốc đã xóa
        self.assertEqual([p.name for p in self.dir.rglob(".*")], [])


class Page(unittest.TestCase):
    def test_reads_symbol_date_summary_gazette_and_pdf_link(self) -> None:
        got = nguon.parse(page(summary="ban hành Quy chế tuyển sinh trình độ đại học"), "26/2026/TT-BGDĐT")
        self.assertEqual(got["pdf_url"],
                         "https://g7.cdnchinhphu.vn/api/download/stream?Url=def~~&file_name=2026_249.pdf")
        self.assertEqual(got["meta"], {
            "symbol": "26/2026/TT-BGDĐT", "issuer_name": "Bộ Giáo dục và Đào tạo", "issued_on": "2026-04-09",
            "type_code": "TT", "summary": "Ban hành Quy chế tuyển sinh trình độ đại học",
            "gazette": "Công báo số 249 ngày 26/04/2026"})

    def test_other_document_or_changed_layout_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "không phải văn bản"):
            nguon.parse(page(symbol="27/2026/TT-BGDĐT"), "26/2026/TT-BGDĐT")
        with self.assertRaisesRegex(ValueError, "trích yếu"):
            nguon.parse(page(summary="ngắn"), "26/2026/TT-BGDĐT")
        with self.assertRaisesRegex(ValueError, "liên kết PDF"):
            nguon.parse(re.sub(r"<a href=\"https://g7[^>]*pdf\">pdf</a>", "", page()), "26/2026/TT-BGDĐT")
        with self.assertRaisesRegex(ValueError, "không phải văn bản"):
            nguon.parse("<html>đổi giao diện</html>", "26/2026/TT-BGDĐT")

    def test_tls_keeps_full_chain_verification(self) -> None:
        with mock.patch.object(nguon, "_get", side_effect=OSError("không mạng")):
            ctx = nguon.tls_context()
        self.assertFalse(ctx.verify_flags & nguon.ssl.VERIFY_X509_PARTIAL_CHAIN)
        self.assertEqual(ctx.verify_mode, nguon.ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)


class Batch(unittest.TestCase):
    def test_batch_reads_back_in_svc_files_and_matches_the_zip(self) -> None:
        m = manifest()
        data, archive, key = dlm.batch(m, SNAPSHOT)
        columns = parse.Columns(required=("type_code", "symbol", "issuer_name", "issued_on", "summary"),
                                optional=("urgency", "due_on", "restricted", "file_ids"),
                                booleans=frozenset({"restricted"}), lists=frozenset({"file_ids"}))
        rows = parse.parse(data, "csv", columns, max_rows=100)
        self.assertEqual([r.code for r in rows], [None] * len(m["files"]))
        for row, f in zip(rows, m["files"], strict=True):
            self.assertEqual(row.files, [f["file"]])
            self.assertEqual(row.data["symbol"], f["meta"]["symbol"])
            self.assertTrue(10 <= len(row.data["summary"]) <= 500)
            self.assertLessEqual(len(row.data["symbol"]), 50)
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            self.assertEqual(sorted(zf.namelist()), sorted(f["file"] for f in m["files"]))
            for f in m["files"]:
                self.assertEqual(zf.read(f["file"]), (SNAPSHOT / f["file"]).read_bytes())
        self.assertRegex(key, r"^du-lieu-mo-cong-bao-gddt-[0-9a-f]{24}$")
        self.assertEqual(dlm.batch(m, SNAPSHOT)[2], key)     # gửi lại cùng bản chụp: cùng khóa, không thành lô mới

    def test_only_documents_are_imported(self) -> None:
        # nguồn chỉ có dữ liệu (ngay-nghi-le: svc-workflow đọc tại chỗ) không thành văn bản đến
        m = manifest()
        self.assertEqual(dlm.documents(m), m["files"])
        m["files"].append({"file": "ngay-nghi.json", "url": "https://baochinhphu.vn/", "sha256": "0" * 64,
                           "bytes": 2, "meta": {"kind": "data"}})
        m["files"][0]["meta"] = {"kind": "quote", "documents": ["Thông báo 9441/TB-BNV"]}
        docs = dlm.documents(m)
        self.assertEqual([f["file"] for f in docs], [f["file"] for f in manifest()["files"][1:]])
        rows = dlm.batch(m, SNAPSHOT)[0].decode().splitlines()
        self.assertEqual(len(rows), 1 + len(docs))


if __name__ == "__main__":
    unittest.main()
