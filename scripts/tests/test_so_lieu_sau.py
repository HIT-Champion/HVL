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

"""Số đo "sau" của đặc tả §8 (F4.6): hàm của make do-so-lieu-sau (scripts/demo.py) — chọn văn bản cần tìm lại, thứ
hạng, trung vị, đổi giờ; bảng đúng 4 dòng, cột "trước" toàn "chưa đo", dòng số bước chuyển tay không có số; lệnh chạy
trên API giả ghi đúng out/so-lieu-sau.json, thoát 1 khi không đủ 5 văn bản hoặc một lần tìm không ra. Thêm: seed đánh
dấu hai đơn vị mẫu (CSDL của job db trống nên kiểm ở đây). Không cần Docker, không đọc .env. Chạy: python3 -m unittest
discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import pathlib
import re
import sys
import tempfile
import types
import unittest
import urllib.parse
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
SEED_TENANTS = ("c300d5bb-028f-44cc-ba10-7b5277a4225d", "318da474-60d6-4a90-aa7f-928b31b8fc59")

demo: Any = None
_saved: dict[str, Any] = {}


class FakeHTTPError(Exception):
    def __init__(self, status: int, body: str = "", url: str = ""):
        super().__init__(f"HTTP {status} {url}: {body}")
        self.status = status
        self.body = body


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp (thiếu thì thoát): thay bằng bản giả; mọi lời gọi mạng, Docker đều là lỗi."""
    global demo
    for name in ("moc_env", "demo"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng, Docker")

    stub.ENV = {}
    stub.ROOT = ROOT
    stub.PUBLIC_URL = "http://localhost:8080"
    stub.EICAR = b""
    stub.HTTPError = FakeHTTPError
    stub.Session = type("Session", (), {"__init__": no_network})
    for name in ("call_json", "compose", "request", "text_pdf", "user_token"):
        setattr(stub, name, no_network)
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    demo = importlib.import_module("demo")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


SYMBOLS = ["01/UBND-VP", " 01/UBND-VP ", "15/SGDĐT", None, "7/ĐHCN", "", "88/CTSV", "3/TB", "9/KH"]
DOCS = [{"id": f"d{i}", "symbol": s} for i, s in enumerate(SYMBOLS)]


def views(*, sample: bool = True, empty: bool = False) -> dict[str, Any]:
    """Dữ liệu như Hasura trả cho lãnh đạo đơn vị (số khớp db/tests/test_success_metrics.py)."""
    if empty:
        return {"core_tenants": [{"code": "MOI", "name": "Đơn vị mới"}], "office_v_time_to_assign": [],
                "office_v_overdue_rate": [], "office_v_feedback_summary": [], "office_documents": DOCS}
    assign = {"sample": sample, "arrived": 8, "assigned": 5, "median_hours": 4.0, "p90_hours": 17.6, "handled": 4,
              "handled_median_hours": 8.5, "handled_p90_hours": 19.5, "waiting": 2}
    overdue = {"sample": sample, "judged": 5, "on_time": 2, "late": 3, "late_open": 1, "pending": 1}
    return {
        "core_tenants": [{"code": "CNTT", "name": "Khoa Công nghệ thông tin"}],
        "office_v_time_to_assign": [{**assign, "month": "2026-10-01", "arrived": 2}, {**assign, "month": None},
                                    {**assign, "month": "2026-09-01", "arrived": 6}],
        "office_v_overdue_rate": [{**overdue, "month": None}, {**overdue, "month": "2026-09-01", "judged": 4}],
        "office_v_feedback_summary": [{"sample": sample, "feedback": 4, "rating_total": 14, "with_comment": 2}],
        "office_documents": DOCS,
    }


class Leader:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.auth = {"Authorization": "Bearer thu"}
        self.queries: list[str] = []

    def gql(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        self.queries.append(query)
        return self.data


def searcher(miss: str | None = None, calls: list[str] | None = None):
    """/api/search giả: văn bản cần tìm đứng thứ 2 (sau một văn bản khác cùng số); miss: số ký hiệu không tìm ra."""
    by_symbol = {(d["symbol"] or "").strip(): d["id"] for d in reversed(DOCS)}

    def call_json(method: str, url: str, body: Any = None, *, headers: dict | None = None, form: Any = None):
        assert method == "GET" and headers == {"Authorization": "Bearer thu"}, (method, headers)
        parsed = urllib.parse.urlsplit(url)
        assert parsed.path == "/api/search", url
        params = urllib.parse.parse_qs(parsed.query)
        q = params["q"][0]
        if calls is not None:
            calls.append(q)
        hits = [{"id": "khac"}] + ([] if q == miss else [{"id": by_symbol[q]}])
        return {"hits": hits, "next_cursor": None}, {}

    return call_json


class PureTest(unittest.TestCase):
    def test_targets_oldest_first_one_per_symbol(self) -> None:
        self.assertEqual(demo.sl_targets(DOCS), [
            {"document_id": "d0", "symbol": "01/UBND-VP"}, {"document_id": "d2", "symbol": "15/SGDĐT"},
            {"document_id": "d4", "symbol": "7/ĐHCN"}, {"document_id": "d6", "symbol": "88/CTSV"},
            {"document_id": "d7", "symbol": "3/TB"}])
        self.assertEqual(len(demo.sl_targets(DOCS[:4])), 2)
        self.assertEqual(demo.sl_targets([]), [])

    def test_rank_and_median(self) -> None:
        hits = [{"id": "x"}, {"id": "a"}]
        self.assertEqual(demo.sl_rank(hits, "x"), 1)
        self.assertEqual(demo.sl_rank(hits, "a"), 2)
        self.assertIsNone(demo.sl_rank(hits, "z"))
        self.assertEqual(demo.sl_median([30.0, 10.0, 20.0]), 20.0)
        self.assertEqual(demo.sl_median([40.0, 10.0, 30.0, 20.0]), 25.0)
        self.assertIsNone(demo.sl_median([]))

    def test_hours_like_the_metrics_page(self) -> None:
        """Cùng ngưỡng với fmtDuration (apps/office/app/utils/metrics.ts): giây, phút, giờ (dưới 48), ngày."""
        cases = [(0, "0 giây"), (3 / 3600, "3 giây"), (0.5, "30 phút"), (1, "1 giờ"), (19.2, "19,2 giờ"),
                 (47.9, "47,9 giờ"), (72, "3 ngày"), (-2, "0 giây"), (None, "—"), (float("nan"), "—"),
                 (float("inf"), "—")]
        for hours, text in cases:
            self.assertEqual(demo.sl_hours(hours), text, hours)
        self.assertEqual(demo.sl_number(17.6), "17,6")
        self.assertEqual(demo.sl_number(4.0), "4")


class TableTest(unittest.TestCase):
    def report(self, data: dict[str, Any], runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if runs is None:
            runs = [{"document_id": f"d{i}", "symbol": f"{i}/X", "ms": float(ms), "rank": 1}
                    for i, ms in enumerate((40, 12, 25, 18, 90))]
        return demo.sl_report(data, runs, measured_at="2026-10-23T10:00:00+00:00")

    def rows(self, table: str) -> list[list[str]]:
        lines = table.splitlines()
        self.assertEqual(lines[0], "| Chỉ số | Trước | Sau | Cách đo |")
        return [[c.strip() for c in line.strip("|").split("|")] for line in lines[2:]]

    def test_four_rows_before_not_measured_handoffs_without_numbers(self) -> None:
        rows = self.rows(demo.sl_table(self.report(views())))
        self.assertEqual([r[0] for r in rows], list(demo.SL_NAMES.values()))
        self.assertEqual(len(rows), 4)
        self.assertEqual({r[1] for r in rows}, {"chưa đo"})
        self.assertNotRegex(" ".join(rows[3]), r"\d")
        self.assertIn("định tính", rows[3][2])
        self.assertEqual(rows[0][2], "trung vị 4 giờ, p90 17,6 giờ (5 văn bản đã giao, 2 còn chờ)")
        self.assertTrue(rows[1][2].startswith("60 % (3/5 văn bản; trong đó 1 chưa xong đã qua hạn; 1 chưa tới hạn"))
        self.assertTrue(rows[2][2].startswith("trung vị 25 ms, chậm nhất 90 ms (5 lần, tìm thấy 5/5) — độ trễ"))
        self.assertIn("độ trễ hệ thống qua APISIX, không gồm thời gian người gõ, đọc", rows[2][2])

    def test_no_data_is_not_zero(self) -> None:
        rows = self.rows(demo.sl_table(self.report(views(empty=True), runs=[])))
        self.assertEqual([r[2] for r in rows[:3]], ["chưa có dữ liệu", "chưa có dữ liệu", "chưa đo được"])
        report = self.report(views(empty=True), runs=[])
        self.assertIsNone(report["overdue_rate"]["late_pct"])
        self.assertEqual(report["feedback"], {"count": 0, "average": None, "with_comment": 0})
        self.assertFalse(report["tenant"]["sample"])

    def test_report_shape(self) -> None:
        report = self.report(views())
        self.assertEqual(set(report), {"measured_at", "account", "tenant", "before", "time_to_assign",
                                       "overdue_rate", "search", "handoffs", "feedback"})
        self.assertEqual(report["tenant"], {"code": "CNTT", "name": "Khoa Công nghệ thông tin", "sample": True})
        self.assertEqual(report["before"], "chưa đo")
        self.assertEqual([m["month"] for m in report["time_to_assign"]["months"]], ["2026-09-01", "2026-10-01"])
        self.assertIsNone(report["time_to_assign"]["all"]["month"])
        self.assertNotIn("sample", report["time_to_assign"]["all"])
        self.assertEqual(report["overdue_rate"]["late_pct"], 60)
        self.assertEqual(report["search"]["kind"], "độ trễ hệ thống")
        self.assertEqual((report["search"]["median_ms"], report["search"]["max_ms"], report["search"]["found"]),
                         (25.0, 90.0, 5))
        self.assertEqual(report["handoffs"], {"kind": "định tính", "value": None, "doc": "docs/so-lieu-sau.md"})
        self.assertEqual(report["feedback"], {"count": 4, "average": 3.5, "with_comment": 2})

    def test_problems(self) -> None:
        self.assertEqual(demo.sl_problems(self.report(views())), [])
        runs = [{"document_id": "d1", "symbol": "1/X", "ms": 5.0, "rank": None}]
        problems = demo.sl_problems(self.report(views(), runs))
        self.assertEqual(len(problems), 2)
        self.assertIn("chỉ có 1 văn bản", problems[0])
        self.assertIn("không thấy văn bản d1", problems[1])


class DoSoLieuSauTest(unittest.TestCase):
    """make do-so-lieu-sau trên API giả: thoát 0 và ghi JSON khi đủ 5 lần tìm ra; thoát 1 khi thiếu văn bản, tìm hụt."""

    def run_main(self, data: dict[str, Any], **search: Any) -> tuple[int, str, str, dict | None, Leader]:
        leader = Leader(data)
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with mock.patch.object(demo, "who", side_effect=lambda username: leader), \
                    mock.patch.object(demo, "call_json", side_effect=searcher(**search)), \
                    mock.patch.object(demo, "ROOT", root), \
                    mock.patch.object(demo, "SL_JSON", root / "out" / "so-lieu-sau.json"), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = demo.main(["do-so-lieu-sau"])
            path = root / "out" / "so-lieu-sau.json"
            saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return code, out.getvalue(), err.getvalue(), saved, leader

    def test_pass_writes_json(self) -> None:
        calls: list[str] = []
        code, out, err, saved, leader = self.run_main(views(), calls=calls)
        self.assertEqual(code, 0, err)
        self.assertEqual(calls, ["01/UBND-VP", "15/SGDĐT", "7/ĐHCN", "88/CTSV", "3/TB"])   # lần lượt, cũ nhất trước
        self.assertIn("| Thời gian tìm lại một văn bản cũ | chưa đo | trung vị", out)
        self.assertIn("Dữ liệu mẫu (make seed)", out)
        self.assertIn("Đã ghi out/so-lieu-sau.json", out)
        self.assertEqual(saved["account"], "truongkhoa")
        self.assertEqual([r["rank"] for r in saved["search"]["runs"]], [2] * 5)
        self.assertEqual(set(saved["search"]["runs"][0]), {"document_id", "symbol", "ms", "rank"})
        self.assertTrue(all(r["ms"] >= 0 for r in saved["search"]["runs"]))
        self.assertRegex(saved["measured_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")
        self.assertEqual(len(leader.queries), 1)

    def test_real_unit_has_no_sample_line(self) -> None:
        code, out, err, saved, _ = self.run_main(views(sample=False))
        self.assertEqual(code, 0, err)
        self.assertNotIn("Dữ liệu mẫu", out)
        self.assertFalse(saved["tenant"]["sample"])

    def test_fewer_than_five_documents_fails(self) -> None:
        data = {**views(), "office_documents": DOCS[:5]}
        code, _, err, saved, _ = self.run_main(data)
        self.assertEqual(code, 1)
        self.assertIn("chỉ có 3 văn bản đến có số ký hiệu", err)
        self.assertEqual(len(saved["search"]["runs"]), 3)          # vẫn ghi lại lần đo để xem

    def test_search_miss_fails(self) -> None:
        code, _, err, saved, _ = self.run_main(views(), miss="88/CTSV")
        self.assertEqual(code, 1)
        self.assertIn("tìm “88/CTSV” không thấy văn bản d6 trong 20 kết quả đầu", err)
        self.assertEqual(saved["search"]["found"], 4)

    def test_empty_views_are_not_an_error(self) -> None:
        code, out, err, _, _ = self.run_main(views(empty=True))
        self.assertEqual(code, 0, err)
        self.assertIn("| Thời gian từ khi văn bản đến tới khi được giao xử lý | chưa đo | chưa có dữ liệu |", out)


class WiringTest(unittest.TestCase):
    def test_query_reads_only_counts_and_unrestricted_documents(self) -> None:
        query = demo.SL_QUERY
        for view in ("office_v_time_to_assign", "office_v_overdue_rate", "office_v_feedback_summary"):
            self.assertIn(view, query)
        self.assertIn('restricted: {_eq: false}', query)
        self.assertIn('status: {_neq: "cancelled"}', query)
        self.assertIn("order_by: [{created_at: asc}, {id: asc}], limit: 25", query)
        self.assertNotRegex(query, r"\bcomment\b|office_feedback\s*[({]")   # không đọc nội dung góp ý

    def test_account_is_a_seed_director(self) -> None:
        users = {line.split(",")[0]: line.split(",") for line in (ROOT / "seed" / "users.csv").read_text(
            encoding="utf-8").splitlines() if line and not line.startswith("#")}
        self.assertEqual(users[demo.SL_ACCOUNT][3], "director")
        self.assertEqual(users[demo.SL_ACCOUNT][4], SEED_TENANTS[0])

    def test_demos_and_make_target(self) -> None:
        self.assertIs(demo.DEMOS["do-so-lieu-sau"], demo.do_so_lieu_sau)
        self.assertIn("python3 scripts/demo.py do-so-lieu-sau", demo.__doc__)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        phony = re.search(r"^\.PHONY:((?:.*\\\n)*.*)$", makefile, re.M).group(1).replace("\\\n", " ")
        self.assertIn("do-so-lieu-sau", phony.split())
        self.assertRegex(makefile, r"(?m)^do-so-lieu-sau: .*## .*out/so-lieu-sau\.json")
        self.assertRegex(makefile, r"scripts/demo\.py do-so-lieu-sau\b")
        self.assertIn("out/", (ROOT / ".gitignore").read_text(encoding="utf-8").split())

    def test_seed_marks_both_sample_tenants(self) -> None:
        """make seed đặt core.tenants.sample_data = true cho hai đơn vị mẫu, cả khi nạp lại (on conflict); migration
        1792281602750 đánh dấu sẵn hai đơn vị đã nạp trước nó. CSDL của job db trống nên không kiểm được ở db/tests."""
        sql = (ROOT / "seed" / "tenants.sql").read_text(encoding="utf-8")
        insert = re.search(r"insert into core\.tenants \(([^)]*)\) values\n(.*?)\non conflict \(id\) do update set "
                           r"(.*?);", sql, re.S)
        self.assertIsNotNone(insert)
        columns = [c.strip() for c in insert.group(1).split(",")]
        self.assertEqual(columns[-1], "sample_data")
        rows = [r for r in insert.group(2).splitlines() if r.strip()]
        self.assertEqual(len(rows), 2)
        for tenant, row in zip(SEED_TENANTS, rows):
            self.assertIn(f"'{tenant}'", row)
            self.assertRegex(row, r", true\),?$")
        self.assertIn("sample_data = true", insert.group(3))
        migration = (ROOT / "db" / "migrations" / "default" / "1792281602750_success_metrics" / "up.sql").read_text(
            encoding="utf-8")
        marked = re.search(r"update core\.tenants set sample_data = true\s+where id in \(([^)]*)\)", migration)
        self.assertEqual(set(re.findall(r"'([0-9a-f-]{36})'", marked.group(1))), set(SEED_TENANTS))


if __name__ == "__main__":
    unittest.main()
