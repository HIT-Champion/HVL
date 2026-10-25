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

"""Lô văn bản đến mẫu (scripts/nap_lo_mau.py, make demo-nap-lo): tất định, seed/nap-lo/van-ban-den.csv đúng bằng bản
sinh, dòng sai cố ý đúng như bảng BAD, bộ đọc của svc-files (imports/parse.py, chỉ thư viện chuẩn) đọc ra đúng số dòng.
Không cần Docker, không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import email.parser
import email.policy
import importlib
import importlib.util
import io
import json
import pathlib
import re
import sys
import types
import unicodedata
import unittest
import zipfile
from datetime import date
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
PARSE = ROOT / "services" / "svc-files" / "src" / "svc_files" / "imports" / "parse.py"
TYPES_SQL = ROOT / "db" / "migrations" / "default" / "1792281600300_document_types" / "up.sql"

mau: Any = None
parse: Any = None
demo: Any = None
_saved: dict[str, Any] = {}


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp: thay bằng bản giả chỉ có những gì demo.py nhập, mọi lời gọi mạng là lỗi.
    parse.py của svc-files nạp thẳng từ tệp (chỉ thư viện chuẩn)."""
    global mau, parse, demo
    for name in ("moc_env", "demo", "nap_lo_mau"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng, Docker")

    stub.ENV, stub.ROOT, stub.PUBLIC_URL, stub.EICAR = {}, ROOT, "http://localhost:8080", b""
    stub.HTTPError = type("HTTPError", (Exception,), {})
    stub.Session = type("Session", (), {"__init__": no_network})
    for name in ("call_json", "compose", "request", "text_pdf", "user_token"):
        setattr(stub, name, no_network)
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    mau = importlib.import_module("nap_lo_mau")
    demo = importlib.import_module("demo")
    spec = importlib.util.spec_from_file_location("nap_lo_parse", PARSE)
    parse = importlib.util.module_from_spec(spec)
    sys.modules["nap_lo_parse"] = parse          # dataclass cần tìm thấy module của mình
    spec.loader.exec_module(parse)


def tearDownModule() -> None:
    sys.modules.pop("nap_lo_parse", None)
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    if str(SCRIPTS) in sys.path:
        sys.path.remove(str(SCRIPTS))


def columns() -> Any:
    return parse.Columns(required=("type_code", "symbol", "issuer_name", "issued_on", "summary"),
                         optional=("urgency", "due_on", "restricted", "file_ids"),
                         booleans=frozenset({"restricted"}), lists=frozenset({"file_ids"}))


class Rows(unittest.TestCase):
    def test_deterministic_and_tag_changes_only_symbols(self) -> None:
        a, b, tagged = mau.rows(), mau.rows(), mau.rows("X1Y2")
        self.assertEqual(a, b)
        self.assertEqual(len(a), mau.COUNT)
        for plain, t in zip(a, tagged, strict=True):
            self.assertEqual({k: v for k, v in plain.items() if k != "symbol"},
                             {k: v for k, v in t.items() if k != "symbol"})
            self.assertRegex(t["symbol"], r"^\d+-X1Y2/")

    def test_rows_are_clean_except_the_intended_ones(self) -> None:
        catalog = set(re.findall(r"\('([^']+)',\s+'", TYPES_SQL.read_text(encoding="utf-8")))
        rows = mau.rows()
        keys = set()
        for n, row in enumerate(rows, 1):
            for value in row.values():
                for text in value if isinstance(value, list) else [value]:
                    self.assertTrue(unicodedata.is_normalized("NFC", text), (n, text))
            self.assertNotIn("due_on", row)
            if n == mau.BAD_TYPE:
                self.assertEqual(row["type_code"], "XX")
            else:
                self.assertIn(row["type_code"], catalog, n)
            if n == mau.BAD_DATE:
                self.assertEqual(row["issued_on"], "2026-02-30")
            else:
                self.assertTrue(date(2026, 1, 1) <= date.fromisoformat(row["issued_on"]) <= date(2026, 10, 23), n)
            self.assertEqual(len(row["summary"]) < 10, n == mau.SHORT, n)
            self.assertLessEqual(len(row["symbol"]), 50)
            key = (row["symbol"], row["issuer_name"].lower(), row["issued_on"])
            self.assertEqual(key in keys, n == mau.DUPLICATE, n)
            keys.add(key)
        with_files = sum(1 for r in rows if r.get("files"))
        self.assertTrue(mau.COUNT // 4 <= with_files <= mau.COUNT // 2, with_files)
        self.assertEqual(rows[mau.MISSING - 1]["files"], [mau.MISSING_NAME])
        self.assertEqual(rows[mau.INFECTED - 1]["files"], [mau.EICAR_NAME])
        self.assertEqual(sum(1 for r in rows if mau.EICAR_NAME in (r.get("files") or [])), 1)

    def test_expected_counts_follow_the_bad_table(self) -> None:
        self.assertEqual(dict(mau.expected()), {"ok": 193, "duplicate": 1, "failed": 6})
        self.assertEqual(sum(mau.expected().values()), mau.COUNT)
        self.assertEqual(len(set(mau.BAD)), 7)


class Formats(unittest.TestCase):
    def test_committed_csv_is_the_generator_output(self) -> None:
        self.assertEqual((ROOT / "seed" / "nap-lo" / "van-ban-den.csv").read_text(encoding="utf-8"),
                         mau.csv_text(mau.rows()), "seed/nap-lo/van-ban-den.csv khác bản sinh — chạy make nap-lo-mau")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(mau.main(["--check"]), 0)
        self.assertIn("khớp bản sinh", out.getvalue())

    def test_ndjson_reads_back_with_one_broken_line(self) -> None:
        rows = mau.rows("T")
        got = parse.parse(mau.ndjson(rows), "ndjson", columns(), max_rows=1000)
        self.assertEqual(len(got), mau.COUNT)
        self.assertEqual([(r.line, r.code) for r in got if r.failed], [(mau.BAD_JSON, "bad_json")])
        for r in got:
            if not r.failed:
                expect = rows[r.line - 1]
                self.assertEqual(r.data, {k: v for k, v in expect.items() if k != "files"})
                self.assertEqual(r.files, expect.get("files", []))
        self.assertEqual(parse.parse(mau.ndjson(rows[:3], broken=None), "ndjson", columns(), max_rows=3)[2].data,
                         {k: v for k, v in rows[2].items() if k != "files"})

    def test_csv_reads_back_with_one_short_row(self) -> None:
        rows = mau.rows()
        got = parse.parse(mau.csv_text(rows).encode(), "csv", columns(), max_rows=1000)
        self.assertEqual(len(got), mau.COUNT)
        # hàng như Excel: tiêu đề là 1
        self.assertEqual([(r.line, r.code) for r in got if r.failed], [(mau.BAD_JSON + 1, "bad_line")])
        ok = [r for r in got if not r.failed]
        self.assertEqual(ok[0].data, {k: v for k, v in rows[0].items() if k != "files"})
        self.assertEqual(sum(1 for r in ok if r.files), sum(1 for r in rows if r.get("files")) - (
            1 if rows[mau.BAD_JSON - 1].get("files") else 0))
        five = parse.parse(mau.csv_text(rows[:5], broken=None).encode(), "csv", columns(), max_rows=5)
        self.assertFalse(any(r.failed for r in five))

    def test_archive_has_every_named_file_but_the_missing_one(self) -> None:
        rows = mau.rows()
        eicar = b"chuoi-thay-the-eicar"
        blob = mau.archive(rows, eicar=eicar, pdf=lambda name: f"%PDF {name}".encode())
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = set(zf.namelist())
            self.assertEqual(zf.read(mau.EICAR_NAME), eicar)
            self.assertEqual(zf.read("tep/0003.pdf"), b"%PDF tep/0003.pdf")
        wanted = {n for r in rows for n in r.get("files") or []}
        self.assertEqual(names, wanted - {mau.MISSING_NAME})
        # chuỗi EICAR không nằm trong bộ sinh: người gọi đưa vào
        self.assertNotIn(b"ANTIVIRUS-TEST-FILE", (SCRIPTS / "nap_lo_mau.py").read_bytes())

    def test_multipart_body_round_trips(self) -> None:
        body, content_type = mau.multipart([("data", "lo.ndjson", "application/x-ndjson", b'{"a": 1}\n'),
                                            ("archive", "tep.zip", "application/zip", b"PK\x03\x04\r\n--x")])
        msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            f"Content-Type: {content_type}\r\n\r\n".encode() + body)
        parts = [(p.get_param("name", header="content-disposition"), p.get_filename(), p.get_content_type(),
                  p.get_payload(decode=True)) for p in msg.iter_parts()]
        self.assertEqual(parts, [("data", "lo.ndjson", "application/x-ndjson", b'{"a": 1}\n'),
                                 ("archive", "tep.zip", "application/zip", b"PK\x03\x04\r\n--x")])


class Demo(unittest.TestCase):
    @staticmethod
    def rows_as_api_returns() -> list[dict[str, Any]]:
        out = []
        for n, (code, fields) in mau.BAD.items():
            dup = code == "duplicate"
            out.append({"line": n, "status": "duplicate" if dup else "failed", "code": None if dup else code,
                        "message": "lý do", "fields": fields})
        return out

    def test_row_problems_accepts_exactly_the_bad_table(self) -> None:
        self.assertEqual(demo.row_problems(self.rows_as_api_returns()), [])

    def test_row_problems_names_each_difference(self) -> None:
        rows = self.rows_as_api_returns()
        rows = [r for r in rows if r["line"] != mau.MISSING]
        next(r for r in rows if r["line"] == mau.SHORT)["fields"] = {"summary": "maxLength"}
        next(r for r in rows if r["line"] == mau.INFECTED)["code"] = "unscannable"
        rows.append({"line": 5, "status": "failed", "code": "internal", "message": "lỗi lạ", "fields": None})
        problems = demo.row_problems(rows)
        self.assertEqual(len(problems), 4, problems)
        self.assertTrue(any(p.startswith("dòng 5 không có trong bảng") for p in problems))
        self.assertTrue(any(f"dòng {mau.MISSING} mong đợi missing_attachment" in p for p in problems))
        self.assertTrue(any(f"dòng {mau.SHORT}:" in p and "maxLength" in p for p in problems))
        self.assertTrue(any(f"dòng {mau.INFECTED}:" in p and "unscannable" in p for p in problems))

    def test_scene_is_registered(self) -> None:
        self.assertIs(demo.DEMOS["nap-lo"], demo.nap_lo)
        self.assertIn("python3 scripts/demo.py nap-lo", demo.__doc__)

    def test_bad_table_is_documented_for_the_demo(self) -> None:
        """Mã lỗi trong BAD là mã svc-files thật trả (README svc-files liệt kê)."""
        readme = (ROOT / "services" / "svc-files" / "README.md").read_text(encoding="utf-8")
        for code, _ in mau.BAD.values():
            self.assertIn(f"`{code}`", readme, code)
        json.dumps(mau.BAD)


if __name__ == "__main__":
    unittest.main()
