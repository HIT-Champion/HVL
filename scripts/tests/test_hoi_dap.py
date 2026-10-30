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

"""Hỏi đáp trên kho văn bản (F4.2): hàm chấm của make do-hoi-dap (scripts/demo.py) trên kết quả giả, và bộ mẫu
seed/hoi-dap khớp scripts/hoi_dap_mau.py, scripts/seed_documents.py, seed/users.csv. Không cần Docker, không đọc
.env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib
import importlib.util
import json
import pathlib
import sys
import types
import unicodedata
import unittest
from collections import Counter
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
SAMPLES = ROOT / "seed" / "hoi-dap"

demo: Any = None
mau: Any = None
seed: Any = None
_saved: dict[str, Any] = {}


class FakeHTTPError(Exception):
    def __init__(self, status: int, body: str = "", url: str = ""):
        super().__init__(f"HTTP {status} {url}: {body}")
        self.status = status
        self.body = body


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp (thiếu thì thoát): thay bằng bản giả chỉ có những gì demo.py, seed_documents.py
    nhập; mọi lời gọi mạng, Docker đều là lỗi."""
    global demo, mau, seed
    for name in ("moc_env", "demo", "hoi_dap_mau", "seed_documents"):
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
    mau = importlib.import_module("hoi_dap_mau")
    seed = importlib.import_module("seed_documents")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


def src(symbol: str | None, page: int | None = 1, *, kind: str = "page", role: str = "main", summary: str = "",
        cited: bool = True) -> dict[str, Any]:
    """Một nguồn như POST /api/documents/ask trả (hợp đồng F4.2 §7), chỉ các trường hàm chấm đọc."""
    return {"n": 1, "symbol": symbol, "summary": summary, "kind": kind, "page": None if kind == "meta" else page,
            "file_role": None if kind == "meta" else role, "issuer_name": "Trường Đại học Mẫu", "cited": cited}


def result(status: str, sources: list[dict], text: str | None = None, **extra: Any) -> dict[str, Any]:
    answer = None if text is None else {"text": text, "source": extra.pop("source", "extract"),
                                        "model": extra.pop("model", None)}
    return {"ask_id": "a", "status": status, "answer": answer, "sources": sources, "semantic": False,
            "ai_available": False, "warnings": extra.pop("warnings", []), "duration_ms": extra.pop("ms", 120)}


POSITIVE = {"id": "q01", "user": "vanthu", "question": "Phải đăng ký tối thiểu bao nhiêu tín chỉ?",
            "expect": [{"symbol": "15/QĐ-ĐHM", "page": 1}], "keywords": ["15 tín chỉ"]}
GUARDED = {"id": "q19", "user": "giangvienktpm", "question": "Điều kiện xét học bổng?", "expect": "none",
           "forbid": ["15/QĐ-ĐHM", "88/CTSV"]}
INTRO_PATH = "services/svc-files/src/svc_files/assist/gioi_thieu/vi.md#lam-duoc-gi"
INTRO = {"id": "g01", "user": "vanthu", "loai": "gioi_thieu", "route": "gioi_thieu", "question": "Bạn làm được gì?",
         "expect": [{"guide": INTRO_PATH}]}
AWAY = {"id": "o01", "user": "vanthu", "loai": "ngoai_pham_vi", "route": "ngoai_pham_vi", "question": "Thời tiết?",
        "expect": "none"}


def guide_src(path: str) -> dict[str, Any]:
    return {**src(None, None, kind="guide"), "path": path}


def routed(status: str, sources: list[dict], text: str | None = None, *, route: str, rewritten: str | None = None,
           **extra: Any) -> dict[str, Any]:
    return {**result(status, sources, text, **extra), "route": route, "rewritten": rewritten}


class MatchTest(unittest.TestCase):
    def test_symbol_and_page(self) -> None:
        want = {"symbol": "15/QĐ-ĐHM", "page": 2}
        self.assertTrue(demo.matches(src("15/QĐ-ĐHM", 2), want))
        self.assertTrue(demo.matches(src(" 15/qđ-đhm ", 2), want), "khác hoa thường, khoảng trắng vẫn là một số")
        self.assertFalse(demo.matches(src("15/QĐ-ĐHM", 1), want), "đúng văn bản, sai trang")
        self.assertFalse(demo.matches(src("16/QĐ-ĐHM", 2), want))
        self.assertFalse(demo.matches(src("15/QĐ-ĐHM", kind="meta"), want), "đoạn trích yếu không có trang")
        self.assertTrue(demo.matches(src("15/QĐ-ĐHM", 2, role="attachment"), want), "tài liệu kèm theo vẫn tính")
        self.assertTrue(demo.matches(src("15/QĐ-ĐHM", kind="meta"), {"symbol": "15/QĐ-ĐHM"}), "đáp án không ghi trang")
        self.assertFalse(demo.matches(src(None, 2), {"symbol": ""}))

    def test_summary_contains(self) -> None:
        want = {"summary_contains": "họp giao ban tháng 11", "page": 1}
        notice = "Thông báo lịch HỌP GIAO BAN  tháng 11 năm 2026"
        self.assertTrue(demo.matches(src("05/TB-CNTT", 1, summary=notice), want),
                        "không phân biệt hoa thường, khoảng trắng")
        nfd = unicodedata.normalize("NFD", notice)
        self.assertTrue(demo.matches(src(None, 1, summary=nfd), want), "NFD và NFC là cùng chữ")
        self.assertFalse(demo.matches(src("05/TB-CNTT", 2, summary=notice), want))
        self.assertFalse(demo.matches(src("05/TB-CNTT", 1, summary="Thông báo lịch họp giao ban tháng 12"), want))

    def test_guide(self) -> None:
        want = {"guide": "docs/huong-dan/viec-chung.md#đơn-nghỉ-phép"}
        self.assertTrue(demo.matches(guide_src(want["guide"]), want))
        self.assertFalse(demo.matches(guide_src("docs/huong-dan/lanh-dao-phong.md#duyệt-đơn-nghỉ-phép"), want))
        self.assertFalse(demo.matches({**src("15/QĐ-ĐHM", 1), "path": want["guide"]}, want), "chỉ nguồn guide")
        self.assertFalse(demo.matches(guide_src(want["guide"]), {"symbol": "15/QĐ-ĐHM"}))

    def test_rank_forbidden_keywords(self) -> None:
        sources = [src("88/CTSV"), src("15/QĐ-ĐHM", 3), src("15/QĐ-ĐHM", 1)]
        self.assertEqual(demo.hit_rank(sources, POSITIVE["expect"]), 3)
        self.assertIsNone(demo.hit_rank(sources[:2], POSITIVE["expect"]))
        self.assertIsNone(demo.hit_rank(sources, "none"))
        self.assertEqual(demo.forbidden(sources, ["88/CTSV"]), ["88/CTSV · tr. 1"])
        self.assertEqual(demo.forbidden(sources, ["53/PA-ĐHM"]), [])
        self.assertTrue(demo.keywords_in("“Đăng ký tối thiểu 15\nTÍN  chỉ” [1]", ["15 tín chỉ"]))
        self.assertTrue(demo.keywords_in(unicodedata.normalize("NFD", "15 tín chỉ"), ["15 tín chỉ"]))
        self.assertFalse(demo.keywords_in("15 tín", ["15 tín chỉ"]))
        self.assertFalse(demo.keywords_in("bất kỳ", []), "không có từ khóa thì không tính là có")
        self.assertFalse(demo.keywords_in(None, ["3,2"]))

    def test_source_label(self) -> None:
        self.assertEqual(demo.source_label(src("88/CTSV", 1)), "88/CTSV · tr. 1")
        self.assertEqual(demo.source_label(src("88/CTSV", 2, role="attachment")), "88/CTSV · tài liệu kèm theo, tr. 2")
        self.assertEqual(demo.source_label(src("88/CTSV", kind="meta")), "88/CTSV · trích yếu")
        self.assertEqual(demo.source_label(src(None, 1, summary="Thông báo lịch họp giao ban")),
                         "Thông báo lịch họp giao ban · tr. 1")


class ScoreTest(unittest.TestCase):
    def test_positive(self) -> None:
        got = result("answered", [src("15/QĐ-ĐHM", 1)], "“… tối thiểu 15 tín chỉ …” [1]")
        row = demo.score(POSITIVE, got, 0.4, restricted=["53/PA-ĐHM"])
        self.assertEqual((row["correct"], row["rank"], row["keywords"], row["forbidden"]), (True, 1, True, []))
        late = result("answered", [src("A"), src("B"), src("C"), src("15/QĐ-ĐHM", 1)], "15 tín chỉ")
        self.assertFalse(demo.score(POSITIVE, late, 0.4, restricted=[])["correct"], "nguồn đúng ở hạng 4")
        nothing = demo.score(POSITIVE, result("no_evidence", []), 0.2, restricted=[])
        self.assertEqual((nothing["correct"], nothing["keywords"], nothing["top"]), (False, False, []))

    def test_negative_and_forbidden(self) -> None:
        refused = demo.score(GUARDED, result("no_evidence", []), 0.1, restricted=["53/PA-ĐHM"])
        self.assertEqual((refused["correct"], refused["keywords"], refused["forbidden"], refused["guarded"]),
                         (True, None, [], True))
        leaked = demo.score(GUARDED, result("answered", [src("88/CTSV")], "3,2"), 0.1, restricted=[])
        self.assertEqual((leaked["correct"], leaked["forbidden"]), (False, ["88/CTSV · tr. 1"]))
        other = demo.score(GUARDED, result("passages_only", [src("47/KHCN")]), 0.1, restricted=[])
        self.assertEqual((other["correct"], other["forbidden"]), (True, []),
                         "chỉ đoạn liên quan trong văn bản được xem, không câu trả lời: vẫn là từ chối")
        wrong = demo.score(GUARDED, result("answered", [src("47/KHCN")], "câu nào đó"), 0.1, restricted=[])
        self.assertEqual((wrong["correct"], wrong["forbidden"]), (False, []), "trả lời câu âm: sai, không phải lộ")
        failed = demo.score(GUARDED, {"status": "lỗi 503 busy"}, 0.0, restricted=[])
        self.assertFalse(failed["correct"])
        sealed = demo.score(POSITIVE, result("answered", [src("15/QĐ-ĐHM", 1), src("53/PA-ĐHM")], "15 tín chỉ"), 0.1,
                            restricted=["53/PA-ĐHM"])
        self.assertEqual(sealed["forbidden"], ["53/PA-ĐHM · tr. 1"], "văn bản hạn chế bị cấm ở mọi câu")

    def test_routes(self) -> None:
        got = routed("answered", [guide_src(INTRO_PATH)], "“Tôi tìm …” [1]", route="gioi_thieu")
        row = demo.score(INTRO, got, 0.1, restricted=[])
        self.assertEqual((row["loai"], row["route"], row["route_ok"], row["correct"]), ("gioi_thieu", "gioi_thieu",
                                                                                         True, True))
        searched = demo.score(INTRO, routed("answered", [src("15/QĐ-ĐHM", 1)], "…", route="van_ban"), 0.1,
                              restricted=[])
        self.assertEqual((searched["route_ok"], searched["correct"]), (False, False))
        follow = {**POSITIVE, "id": "n01", "loai": "noi_tiep", "route": "van_ban", "previous": "Câu trước?"}
        spliced = routed("answered", [src("15/QĐ-ĐHM", 1)], "15 tín chỉ", route="van_ban", rewritten="Câu ghép")
        self.assertEqual(demo.score(follow, spliced, 0.1, restricted=[])["route_ok"], True)
        alone = demo.score(follow, {**spliced, "rewritten": None}, 0.1, restricted=[])
        self.assertEqual((alone["route_ok"], alone["correct"]), (False, True), "tìm trúng nhưng không ghép câu")
        fixed = routed("no_evidence", [], "Câu này nằm ngoài phạm vi của tôi.", source="fixed", route="ngoai_pham_vi")
        away = demo.score(AWAY, fixed, 0.1, restricted=[])
        self.assertEqual((away["route_ok"], away["correct"]), (True, True))
        self.assertFalse(demo.score(AWAY, routed("no_evidence", [], route="van_ban"), 0.1, restricted=[])["route_ok"],
                         "từ chối vì không tìm thấy, không phải vì ngoài phạm vi")
        old = demo.score(POSITIVE, result("answered", [src("15/QĐ-ĐHM", 1)], "15 tín chỉ"), 0.1, restricted=[])
        self.assertEqual((old["loai"], old["route_ok"]), ("van_ban", True), "câu không ghi loại là van_ban")

    def test_data_routes(self) -> None:
        """Đường dữ liệu (#441): đúng khi câu có số và mọi số, bộ lọc bằng đáp án đếm thẳng qua GraphQL."""
        want = {"data": "documents", "directions": ["in"], "from": "2026-10-01", "to": "2026-11-01", "type_code": None}
        q = {"id": "d01", "user": "vanthu", "loai": "dem_van_ban", "route": "dem_van_ban", "question": "Bao nhiêu?",
             "expect": [want]}
        direct = {"counts": {"in": 3}, "type_code": None, "from": "2026-10-01", "to": "2026-11-01"}
        data = {"kind": "documents", **direct}
        got = {**routed("answered", [], "Có 3 văn bản đến …", source="data", route="dem_van_ban"), "data": data}
        row = demo.score(q, got, 0.1, restricted=[], direct=direct)
        self.assertEqual((row["route_ok"], row["correct"]), (True, True))
        wrong = demo.score(q, {**got, "data": {**data, "counts": {"in": 2}}}, 0.1, restricted=[], direct=direct)
        self.assertFalse(wrong["correct"], "số khác số đếm thẳng")
        shifted = demo.score(q, {**got, "data": {**data, "from": "2026-09-01"}}, 0.1, restricted=[], direct=direct)
        self.assertFalse(shifted["correct"], "đếm sai khoảng ngày")
        self.assertFalse(demo.score(q, got, 0.1, restricted=[], direct=None)["correct"], "chưa đếm thẳng được")
        searched = demo.score(q, routed("passages_only", [src("15/QĐ-ĐHM", 1)], route="van_ban"), 0.1, restricted=[],
                              direct=direct)
        self.assertEqual((searched["route_ok"], searched["correct"]), (False, False))
        self.assertEqual(demo.direct_where("in", want), {"_and": [
            {"direction": {"_eq": "in"}},
            {"registered_at": {"_gte": "2026-10-01T00:00:00+07:00", "_lt": "2026-11-01T00:00:00+07:00"}}]})
        self.assertEqual(demo.direct_where("out", {**want, "type_code": "QĐ"}), {"_and": [
            {"direction": {"_eq": "out"}}, {"type_code": {"_eq": "QĐ"}},
            {"issued_on": {"_gte": "2026-10-01", "_lt": "2026-11-01"}}]})
        self.assertEqual(demo.direct_where("in", {**want, "from": None, "to": None}),
                         {"_and": [{"direction": {"_eq": "in"}}]})

    def test_direct_tasks_count_like_the_deadline_calendar(self) -> None:
        class Asker:
            def gql(self, query: str, variables: dict | None = None) -> dict:
                return {"myTasks": [{"id": "a", "due_on": "2026-10-27"}, {"id": "b", "due_on": "2026-10-30"},
                                    {"id": "c", "due_on": "2026-11-01"}, {"id": "d", "due_on": "2026-11-02"},
                                    {"id": "e", "due_on": None}]}
        got = demo.direct_data(Asker(), {"data": "tasks"}, demo.date(2026, 10, 30))
        self.assertEqual(got, {"tasks": 5, "overdue": 1, "today": 1, "soon": 1, "no_due": 1})

    def test_model(self) -> None:
        written = result("answered", [src("15/QĐ-ĐHM", 1), src("88/CTSV", cited=False)], "Cần 15 tín chỉ [1].",
                         source="model", model="qwen3:1.7b")
        m = demo.score_model(POSITIVE, written, 9.0, restricted=[])
        self.assertEqual((m["by_model"], m["keywords"], m["cites"], m["name"]), (True, True, True, "qwen3:1.7b"))
        wrong_cite = result("answered", [src("15/QĐ-ĐHM", 1, cited=False), src("88/CTSV")], "15 tín chỉ [2]",
                            source="model")
        self.assertFalse(demo.score_model(POSITIVE, wrong_cite, 9.0, restricted=[])["cites"])
        fallback = result("answered", [src("15/QĐ-ĐHM", 1)], "“15 tín chỉ” [1]", warnings=["model_rejected"])
        m = demo.score_model(POSITIVE, fallback, 9.0, restricted=[])
        self.assertEqual((m["by_model"], m["keywords"], m["cites"], m["warnings"]), (False, False, False,
                                                                                     ["model_rejected"]))

    def test_percentile(self) -> None:
        self.assertEqual(demo.percentile([4, 1, 3, 2], 50), 2)
        self.assertEqual(demo.percentile([4, 1, 3, 2], 95), 4)
        self.assertEqual(demo.percentile([7.5], 95), 7.5)
        self.assertIsNone(demo.percentile([], 50))
        self.assertEqual(demo.percentile(list(range(1, 21)), 95), 19)


class SummaryTest(unittest.TestCase):
    def rows(self, hits: int, misses: int, *, leak: bool = False) -> list[dict]:
        good = result("answered", [src("15/QĐ-ĐHM", 1)], "15 tín chỉ")
        bad = result("answered", [src("31/HD-ĐHM", 1)], "200.000 đồng")
        out = [demo.score({**POSITIVE, "id": f"p{i}"}, good, 1.0, restricted=[]) for i in range(hits)]
        out += [demo.score({**POSITIVE, "id": f"m{i}"}, bad, 2.0, restricted=[]) for i in range(misses)]
        refused = result("answered", [src("88/CTSV")], "3,2") if leak else result("no_evidence", [])
        out.append(demo.score(GUARDED, refused, 0.5, restricted=["53/PA-ĐHM"]))
        return out

    def test_pass(self) -> None:
        s = demo.summarize(self.rows(8, 2))
        self.assertEqual((s["positives"], s["recall"], s["keywords"], s["negatives"], s["refused"], s["no_evidence"],
                          s["guarded"]), (10, 8, 8, 1, 1, 1, 1))
        self.assertEqual((s["p50"], s["p95"], s["server_p50"], s["model"]), (1.0, 2.0, 120, None))
        self.assertEqual(demo.verdict(s), [])

    def test_recall_below_threshold(self) -> None:
        problems = demo.verdict(demo.summarize(self.rows(7, 3)))
        self.assertEqual(len(problems), 1)
        self.assertIn("recall@3 7/10", problems[0])

    def test_forbidden_source_always_fails(self) -> None:
        s = demo.summarize(self.rows(10, 0, leak=True))
        self.assertEqual(s["recall"], 10)
        self.assertEqual(s["violations"], ["q19 (giangvienktpm): 88/CTSV · tr. 1"])
        self.assertTrue(demo.verdict(s)[0].startswith("nguồn bị cấm"))

    def test_types_and_route_errors(self) -> None:
        rows = self.rows(10, 0)
        good = routed("answered", [guide_src(INTRO_PATH)], "“Tôi …” [1]", route="gioi_thieu")
        rows.append(demo.score(INTRO, good, 0.1, restricted=[]))
        rows.append(demo.score({**INTRO, "id": "g02"}, {**good, "route": "van_ban"}, 0.1, restricted=[]))
        rows.append(demo.score({**INTRO, "id": "g03"}, {**good, "sources": []}, 0.1, restricted=[]))
        s = demo.summarize(rows)
        self.assertEqual((s["positives"], s["recall"], s["negatives"]), (10, 10, 1), "recall chỉ trên câu van_ban")
        self.assertEqual(s["by_type"], {"van_ban": {"asked": 11, "route_ok": 11, "correct": 11},
                                        "gioi_thieu": {"asked": 3, "route_ok": 2, "correct": 2}})
        self.assertEqual(demo.verdict(s), ["đường sai — g02 (gioi_thieu): van_ban",
                                           "sai câu trả lời tất định — g03"])

    def test_model_totals_and_table(self) -> None:
        rows = self.rows(2, 1)
        written = result("answered", [src("15/QĐ-ĐHM", 1)], "Cần 15 tín chỉ [1].", source="model", model="qwen3:1.7b")
        rows[0]["model"] = demo.score_model(POSITIVE, written, 8.0, restricted=["53/PA-ĐHM"])
        leaked = result("answered", [src("53/PA-ĐHM")], "XANH LAM [1]", source="model")
        rows[1]["model"] = demo.score_model(POSITIVE, leaked, 12.0, restricted=["53/PA-ĐHM"])
        s = demo.summarize(rows)
        self.assertEqual({k: s["model"][k] for k in ("asked", "by_model", "positives", "keywords", "cites", "names",
                                                     "negatives", "neg_answered")},
                         {"asked": 2, "by_model": 2, "positives": 2, "keywords": 1, "cites": 1, "names": ["qwen3:1.7b"],
                          "negatives": 0, "neg_answered": 0})
        self.assertEqual(s["violations"], ["p1 (vanthu, generate): 53/PA-ĐHM · tr. 1"])
        table = demo.result_table(rows).splitlines()
        self.assertEqual(len(table), 2 + len(rows))
        self.assertEqual({line.count("|") for line in table}, {12}, "mọi dòng cùng số cột (thêm 4 cột mô hình)")
        self.assertIn("✓ #1", table[2])
        self.assertIn("✗", table[4])
        plain = demo.result_table(self.rows(1, 0)).splitlines()
        self.assertEqual({line.count("|") for line in plain}, {8})
        self.assertIn("no_evidence", plain[-1])


class WaitIndexedTest(unittest.TestCase):
    """Bước đợi chỉ mục chỉ xong khi một trang của văn bản có trong nguồn: trích yếu vào chỉ mục lúc tiếp nhận, trước
    khi chữ các trang được đọc — bản cài mới mà dừng đợi lúc đó thì các câu hỏi sau thiếu đoạn trả lời."""

    DATA = {"questions": [POSITIVE], "documents": [{"symbol": "15/QĐ-ĐHM"}]}

    def setUp(self) -> None:
        self.now, self.asked = 100.0, 0
        self._saved = (demo.time, demo.ask, demo.who)
        demo.time = types.SimpleNamespace(monotonic=lambda: self.now, sleep=self.sleep)
        demo.who = lambda user: user

    def tearDown(self) -> None:
        demo.time, demo.ask, demo.who = self._saved

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def serve(self, *answers: dict[str, Any]) -> None:
        def ask(session: Any, question: str) -> tuple[dict[str, Any], None]:
            self.assertEqual((session, question), (POSITIVE["user"], POSITIVE["question"]))
            self.asked += 1
            return answers[min(self.asked, len(answers)) - 1], None
        demo.ask = ask

    def test_summary_source_alone_keeps_waiting(self) -> None:
        meta = result("passages_only", [src("15/QĐ-ĐHM", kind="meta")])
        self.serve(meta, meta, result("answered", [src("15/QĐ-ĐHM", kind="meta"), src("15/QĐ-ĐHM", 1)]))
        demo.wait_indexed(self.DATA, 90)
        self.assertEqual(self.asked, 3)

    def test_times_out_when_only_the_summary_is_indexed(self) -> None:
        self.serve(result("passages_only", [src("15/QĐ-ĐHM", kind="meta")]))
        with self.assertRaises(demo.DemoFailed):
            demo.wait_indexed(self.DATA, 10)


class SamplesTest(unittest.TestCase):
    """seed/hoi-dap/cau-hoi.json là đầu ra của hoi_dap_mau.py; câu hỏi đủ loại như hợp đồng F4.2 §10."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads((SAMPLES / "cau-hoi.json").read_text(encoding="utf-8"))
        cls.users = {line.split(",")[0]: line.split(",") for line in (ROOT / "seed" / "users.csv").read_text(
            encoding="utf-8").splitlines() if line and not line.startswith("#")}

    def test_generated(self) -> None:
        self.assertEqual((SAMPLES / "cau-hoi.json").read_text(encoding="utf-8"),
                         json.dumps(mau.questions_json(), ensure_ascii=False, indent=2) + "\n",
                         "cau-hoi.json khác bản sinh — chạy lại make hoi-dap-mau")
        self.assertEqual(self.data["version"], 1)

    def test_files(self) -> None:
        total = 0
        for d in self.data["documents"]:
            data = (SAMPLES / d["file"]).read_bytes()
            total += len(data)
            self.assertTrue(data.startswith(b"%PDF-"), d["file"])
            self.assertTrue(d["symbol"].endswith("-ĐHM"), "không trùng số ký hiệu của make seed")
            self.assertEqual(d["issuer_name"], "Trường Đại học Mẫu")
            for leak in mau.LEAKS:
                self.assertNotIn(leak, data, f"{d['file']} lộ đường dẫn máy")
        self.assertLessEqual(total, 1024 * 1024)
        self.assertEqual(sorted(p.name for p in SAMPLES.glob("*.pdf")),
                         sorted(d["file"] for d in self.data["documents"]))

    def test_documents(self) -> None:
        docs = self.data["documents"]
        self.assertEqual([d["restricted"] for d in docs].count(True), 1)
        self.assertGreaterEqual(sum(d["pages"] >= 2 for d in docs if not d["restricted"]), 5)
        for d in docs:
            assign = d["assign"]
            if assign is None:
                continue
            self.assertIn(assign["lead"], seed.DEPT)
            self.assertIn(assign["lead"], demo.UNIT_NAMES)
            # svc-workflow từ chối chỉ đạo khi đơn vị chủ trì chưa có lãnh đạo phòng (Văn phòng khoa của seed chưa có)
            self.assertIn(assign["lead"], demo.MANAGERS, "đơn vị chủ trì phải có lãnh đạo phòng")
            if assign["handler"]:
                self.assertEqual(self.users[demo.MANAGERS[assign["lead"]]][3], "manager")
                self.assertIn(assign["handler"], self.users)
                self.assertEqual(self.users[assign["handler"]][5], seed.DEPT[assign["lead"]],
                                 "người xử lý thuộc đơn vị chủ trì")

    def test_questions(self) -> None:
        everything = self.data["questions"]
        self.assertEqual(len({q["id"] for q in everything}), len(everything))
        for q in everything:
            self.assertIn(q["user"], self.users)
            self.assertIn(self.users[q["user"]][3], ("clerk", "staff", "manager", "director"), "vai trò được hỏi")
        # câu hỏi về nội dung văn bản; các loại khác: test_question_types
        qs = [q for q in everything if q["loai"] in ("van_ban", "noi_tiep")]
        docs = {d["symbol"]: d for d in self.data["documents"]}
        sealed = [s for s, d in docs.items() if d["restricted"]]
        positives = [q for q in qs if isinstance(q["expect"], list)]
        negatives = [q for q in qs if q["expect"] == "none"]
        self.assertEqual(len(positives) + len(negatives), len(qs))
        self.assertGreaterEqual(len(positives), 10)
        self.assertGreaterEqual(len(negatives), 2)
        for q in positives:
            self.assertTrue(q["keywords"], q["id"])
            for want in q["expect"]:
                self.assertIsInstance(want["page"], int)
                if "symbol" in want and want["symbol"] in docs:
                    self.assertLessEqual(want["page"], docs[want["symbol"]]["pages"])
                    self.assertNotIn(want["symbol"], sealed)
            self.assertTrue(all(demo.flat(k) in demo.flat(q["evidence"]) for k in q["keywords"]), q["id"])
        targets = {w.get("symbol") or w.get("summary_contains") for q in positives for w in q["expect"]}
        self.assertTrue({"88/CTSV", "131/ĐT-ĐH"} <= targets, "câu hỏi về văn bản mẫu của make seed")
        self.assertTrue(any(q["expect"] != "none" and "summary_contains" in q["expect"][0] for q in qs),
                        "câu hỏi về văn bản đi đã phát hành")
        self.assertTrue(any(set(q.get("forbid", [])) & set(sealed) for q in negatives), "câu nội dung văn bản hạn chế")
        ktpm = [q for q in qs if q["user"] == "giangvienktpm"]
        self.assertTrue(any(q["expect"] == "none" and q.get("forbid") for q in ktpm), "câu quyền bị cấm")
        self.assertTrue(any(q["expect"] != "none" and docs[q["expect"][0]["symbol"]]["assign"]["lead"] == "KTPM"
                            for q in ktpm), "câu quyền về văn bản giao Bộ môn KTPM")
        for q in qs:
            self.assertTrue(demo.keywords_in(q.get("evidence") or "", q.get("keywords") or []) or q["expect"] == "none")
        for name in ("q01", "q02", "q10", "q14", "q18"):
            self.assertIn(name, {q["id"] for q in qs}, "demo.py hoi-dap dùng câu này")

    def test_question_types(self) -> None:
        """Loại câu và đường bộ định tuyến phải chọn (#423): bộ cũ giữ 19 câu van_ban, ≥ 5 câu mỗi loại mới; chỉ câu nối
        tiếp có câu trước; đáp án guide trỏ tới mục có thật. Đường đi qua API: test_assist_routes_api.py (svc-files)."""
        qs = self.data["questions"]
        counts = Counter(q["loai"] for q in qs)
        self.assertEqual(set(counts), set(mau.ROUTES))
        self.assertEqual(counts["van_ban"], 19, "bộ cũ giữ nguyên để recall@3 so được với số đo trước")
        for loai in ("noi_tiep", "gioi_thieu", "huong_dan", "ngoai_pham_vi", "viec_cua_toi", "dem_van_ban"):
            self.assertGreaterEqual(counts[loai], 5, loai)
        for q in qs:
            self.assertEqual(q["route"], mau.ROUTES[q["loai"]], q["id"])
            self.assertEqual("previous" in q, q["loai"] == "noi_tiep", q["id"])
            wants = q["expect"] if isinstance(q["expect"], list) else []
            self.assertEqual(any("guide" in w for w in wants), q["loai"] in ("gioi_thieu", "huong_dan"), q["id"])
            self.assertEqual(any("data" in w for w in wants), q["loai"] in demo.DATA_TYPES, q["id"])
            self.assertEqual(q["expect"] == "none", q["loai"] == "ngoai_pham_vi" or q["id"] in ("q17", "q18", "q19"))
            for want in wants:
                if "guide" not in want:
                    continue
                path, anchor = want["guide"].split("#")
                lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
                slugs = {"-".join("".join(c for c in line.lstrip("#").strip().lower() if c.isalnum() or c == " ")
                                  .split()) for line in lines if line.startswith("#")}
                self.assertTrue(anchor in slugs or any(f"{{#{anchor}}}" in line for line in lines), q["id"])

    def test_seed_evidence(self) -> None:
        """Câu trả lời về văn bản của make seed có nguyên văn trong nội dung seed_documents.py in ra PDF (một trang)."""
        bodies = {s.symbol: s.body for s in seed.CNTT}
        issued = {d.summary: d for d in seed.OUT_CNTT if d.stop == "issued"}
        for q in self.data["questions"]:
            if q["expect"] == "none":
                continue
            for want in q["expect"]:
                if want.get("symbol") in bodies:
                    body = bodies[want["symbol"]]
                elif "summary_contains" in want:
                    found = [d for s, d in issued.items() if demo.flat(want["summary_contains"]) in demo.flat(s)]
                    self.assertEqual(len(found), 1, f"{q['id']}: đúng một văn bản đi đã phát hành khớp trích yếu")
                    body = found[0].body
                else:
                    continue
                self.assertEqual(want["page"], 1)
                self.assertIn(demo.flat(q["evidence"]), demo.flat(body), q["id"])

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "cần pypdf (môi trường test svc-files)")
    def test_open_data_evidence(self) -> None:
        """Câu về nguồn công khai A (#446): câu bằng chứng có trên đúng trang của tệp PDF bản Công báo mà make seed nạp
        (số ký hiệu lấy từ manifest.json như du_lieu_mo.py)."""
        import pypdf

        folder = ROOT / "seed" / "du-lieu-mo" / "cong-bao-gddt"
        files = {f["meta"]["symbol"]: folder / f["file"]
                 for f in json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["files"]}
        asked = [q for q in self.data["questions"] if q["expect"] != "none" and q["expect"][0].get("symbol") in files]
        self.assertGreaterEqual(len(asked), 3)
        for q in asked:
            want = q["expect"][0]
            text = pypdf.PdfReader(files[want["symbol"]]).pages[want["page"] - 1].extract_text()
            self.assertIn(demo.flat(q["evidence"]), demo.flat(text), q["id"])

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "cần pypdf (môi trường test svc-files)")
    def test_pdf_pages(self) -> None:
        files = {p.name: p.read_bytes() for p in SAMPLES.glob("*.pdf")}
        self.assertEqual(mau.verify(files), [])


if __name__ == "__main__":
    unittest.main()
