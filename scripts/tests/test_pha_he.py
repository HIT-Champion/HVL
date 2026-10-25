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


"""Màn demo (iii) phả hệ (make demo-pha-he, scripts/demo.py): bước 5 in phả hệ báo cáo — khung nhìn của trang Điều hành
← bảng, từ office.report_lineage. Chạy cả màn trên Hasura giả (một lượt nộp lưu đủ 4 bước, đúng khuôn
svc_files.lineage): in đúng nguồn của 4 khung nhìn, dừng khi thiếu khung nhìn hay thời gian xử lý không dẫn về dòng
thời gian. Không cần Docker, không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import importlib
import io
import pathlib
import sys
import types
import unittest
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent

demo: Any = None
_saved: dict[str, Any] = {}


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
    stub.HTTPError = type("HTTPError", (Exception,), {})
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


def edge(report: str, source: str, depth: int = 1, consumer: str | None = None) -> dict[str, Any]:
    return {"report": report, "consumer": consumer or report, "source": source, "source_kind": "table", "depth": depth}


# Đúng các cạnh office.report_lineage trả trên CSDL thật cho 4 khung nhìn của trang Điều hành (db/tests)
CATALOG = [
    edge("office.v_document_counts", "office.documents"),
    edge("office.v_overdue_by_department", "office.documents"), edge("office.v_overdue_by_department", "core.users"),
    edge("office.v_overdue_by_department", "office.departments"),
    edge("office.v_overdue_by_department", "office.assignments"),
    edge("office.v_processing_time", "office.documents"), edge("office.v_processing_time", "office.document_events"),
    edge("office.v_processing_time", "office.archived_document_facts"),
    edge("office.v_outgoing_by_month", "office.documents"),
]
RUN = "5b0c2c4e-1111-4000-8000-000000000001"
COLD = "s3://moc-cold/cold/t/case/c/"
PG = "postgres://postgres:5432/moc."


def step(name: str, inputs: list[str], outputs: list[str], event: dict | None = None) -> dict[str, Any]:
    return {"run_id": f"{name}-run", "parent_run_id": RUN, "job": f"moc.case_file.archive.{name}",
            "event_type": "COMPLETE", "inputs": inputs, "outputs": outputs, "quality_ok": True if event else None,
            "event": event or {}}


TABLES = [f"{COLD}{n}-{'a' * 64}.parquet" for n in ("documents", "assignments", "events")]
CHECKS = {"assertions": [{"assertion": "row_count_equals_source", "success": True},
                         {"assertion": "not_null", "column": "id", "success": True}]}
EVENTS = [
    {"run_id": RUN, "parent_run_id": None, "job": "moc.case_file.archive", "event_type": "START", "inputs": [],
     "outputs": [], "quality_ok": None, "event": {"schemaURL": "https://openlineage.io/spec/2-0-2/OpenLineage.json"
                                                  "#/$defs/RunEvent", "producer": "https://github.com/x/svc-files",
                                                  "job": {"namespace": "moc"}}},
    step("files", ["s3://moc-files/tenant/t/f1"], [f"{COLD}files/{'b' * 64}"]),
    step("tables", [f"{PG}office.documents", f"{PG}office.assignments", f"{PG}office.document_events"], TABLES,
         {"outputs": [{"namespace": "s3://moc-cold", "name": t.removeprefix("s3://moc-cold/"),
                       "facets": {"dataQualityAssertions": CHECKS},
                       "outputFacets": {"outputStatistics": {"rowCount": 2}}} for t in TABLES]}),
    step("manifest", [*TABLES, f"{COLD}files/{'b' * 64}"], [f"{COLD}manifest-{'c' * 64}.json"]),
    step("commit", [f"{COLD}manifest-{'c' * 64}.json"],
         [f"{PG}office.documents", f"{PG}office.archived_document_facts", f"{PG}core.audit_log"]),
]


class Director:
    """Hasura giả trả lời đúng các truy vấn của màn (iii) cho lãnh đạo đơn vị."""

    def __init__(self, catalog: list[dict[str, Any]]):
        self.catalog = catalog
        self.queries: list[str] = []

    def gql(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        self.queries.append(query)
        if query == demo.LINEAGE_RUNS:
            return {"core_lineage_events": [{"run_id": RUN, "outputs": EVENTS[4]["outputs"]}]}
        if query == demo.LINEAGE_OF:
            assert variables == {"run": RUN}
            return {"core_lineage_events": EVENTS}
        if query == demo.QUALITY_FAILED:
            return {"core_lineage_events_aggregate": {"aggregate": {"count": 0}}}
        if query == demo.REPORT_LINEAGE:
            return {"office_report_lineage": self.catalog}
        raise AssertionError(f"truy vấn lạ: {query}")


def run_screen(catalog: list[dict[str, Any]]) -> tuple[str, Director]:
    director = Director(catalog)
    out = io.StringIO()
    with mock.patch.object(demo, "Session", lambda username: director), contextlib.redirect_stdout(out):
        demo.pha_he()
    return out.getvalue(), director


class ReportSourcesTest(unittest.TestCase):
    def test_nearest_first_and_nested_views_named(self) -> None:
        rows = [edge("office.v_x", "office.registers", 2, "office.issued_documents"),
                {**edge("office.v_x", "office.issued_documents"), "source_kind": "view"},
                edge("office.v_x", "office.documents", 2, "office.issued_documents"),
                edge("office.v_a", "office.feedback")]
        self.assertEqual(demo.report_sources(rows), {
            "office.v_a": ["office.feedback"],
            "office.v_x": ["office.issued_documents", "office.documents (qua office.issued_documents)",
                           "office.registers (qua office.issued_documents)"]})
        self.assertEqual(demo.report_sources([]), {})


class ScreenTest(unittest.TestCase):
    def test_step_five_prints_the_board_views_and_their_tables(self) -> None:
        text, director = run_screen(CATALOG)
        self.assertIn("\n5. Phả hệ báo cáo", text)
        self.assertIn("· office.v_processing_time ← office.archived_document_facts, office.document_events, "
                      "office.documents", text)
        self.assertIn("· office.v_overdue_by_department ← core.users, office.assignments, office.departments, "
                      "office.documents", text)
        self.assertIn("4 khung nhìn báo cáo office.v_*, 9 cạnh", text)
        # lượt nộp lưu khai bảng số liệu giữ lại ở bước commit: in thêm nối thời gian xử lý ← nộp lưu
        self.assertIn("office.archived_document_facts ← bước commit", text)
        self.assertEqual(director.queries.count(demo.REPORT_LINEAGE), 1)

    def test_older_run_without_kept_facts_is_not_an_error(self) -> None:
        commit = EVENTS[4]
        old = {**commit, "outputs": [o for o in commit["outputs"] if "archived_document_facts" not in o]}
        with mock.patch.object(sys.modules[__name__], "EVENTS", [*EVENTS[:4], old]):
            text, _ = run_screen(CATALOG)
        self.assertIn("4 khung nhìn báo cáo", text)
        self.assertNotIn("← bước commit", text)

    def test_stops_when_a_board_view_or_the_timeline_is_missing(self) -> None:
        without = [e for e in CATALOG if e["report"] != "office.v_outgoing_by_month"]
        with self.assertRaisesRegex(demo.DemoFailed, "v_outgoing_by_month"):
            run_screen(without)
        no_events = [e for e in CATALOG if e["source"] != "office.document_events"]
        with self.assertRaisesRegex(demo.DemoFailed, "dòng thời gian"):
            run_screen(no_events)


if __name__ == "__main__":
    unittest.main()
