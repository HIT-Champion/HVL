# Copyright 2026 Mộc Team
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

"""Gợi ý giao việc (F4.3): khuôn seed/giao-viec/lich-su.json, nhãn các ca nhất quán với dữ liệu mẫu, hàm đo của make
do-giao-viec (scripts/demo.py) trên dòng evaluate giả, và lệnh đo thoát 1 khi căn cứ là văn bản hạn chế. Không cần
Docker, không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import pathlib
import re
import sys
import types
import unicodedata
import unittest
import uuid
from collections import Counter
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
HISTORY = ROOT / "seed" / "giao-viec" / "lich-su.json"
VI = ROOT / "services" / "svc-files" / "src" / "svc_files" / "assist" / "vi.py"

demo: Any = None
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
    global demo, seed
    for name in ("moc_env", "demo", "seed_documents"):
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
    seed = importlib.import_module("seed_documents")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


def load_history() -> dict[str, Any]:
    return json.loads(HISTORY.read_text(encoding="utf-8"))


def users() -> dict[str, list[str]]:
    """seed/users.csv: username → [username, họ, tên, vai trò, tenant, phòng]."""
    return {line.split(",")[0]: line.split(",") for line in (ROOT / "seed" / "users.csv").read_text(
        encoding="utf-8").splitlines() if line and not line.startswith("#")}


def managed_units() -> set[str]:
    """Mã đơn vị (ĐT, KTPM…) có lãnh đạo phòng — svc-workflow chỉ cho giao đơn vị có manager (409 no_manager)."""
    code = {dept: c for c, dept in seed.DEPT.items()}
    return {code[u[5]] for u in users().values() if u[3] == "manager" and u[5] in code}


def user_unit(username: str) -> str:
    code = {dept: c for c, dept in seed.DEPT.items()}
    return code[users()[username][5]]


# --- câu tìm như svc-files (assist/vi.py + similar.subject_text), chỉ để đối chiếu nhãn — không chạy Meilisearch ----
PREFIXES = ("về việc", "v/v:", "v/v", "thông báo", "kế hoạch", "giấy mời", "quyết định", "công văn", "tờ trình")
_vi = VI.read_text(encoding="utf-8")
STOPWORDS = frozenset(re.search(r'STOPWORDS = frozenset\("""(.*?)"""', _vi, re.S).group(1).split())
TOKEN_RE = re.compile(re.search(r'TOKEN_RE = re\.compile\(r"(.*?)"\)', _vi).group(1))


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def subject(summary: str) -> str:
    """Bỏ một tiền tố khuôn mẫu ở đầu và token "việc", như similar.subject_text (hợp đồng F4.3 §4)."""
    text = " ".join(unicodedata.normalize("NFC", summary).split())
    for prefix in PREFIXES:
        if text.lower().startswith(prefix):
            text = text[len(prefix):].lstrip(" :")
            break
    return " ".join(t for t in text.split() if t.lower() != "việc")


def tokens(summary: str) -> list[str]:
    out: list[str] = []
    for token in TOKEN_RE.findall(subject(summary)):
        low = token.lower()
        if low not in STOPWORDS and (len(low) >= 2 or low[0].isdigit()) and fold(low) not in out:
            out.append(fold(low))
    return out


def query_terms(summary: str) -> list[str]:
    """Tối đa 10 term đầu — Meilisearch chỉ xét chừng ấy (vi.keyword_query)."""
    return tokens(summary)[:10]


def labelled_corpus(data: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(số ký hiệu, trích yếu, đơn vị chủ trì) của mọi văn bản đã giao có thể làm căn cứ: seed CNTT (make seed), kho
    hỏi đáp (make demo-hoi-dap), lịch sử giao việc."""
    docs = [(s.symbol, s.summary, s.lead) for s in seed.CNTT if s.stop in ("directed", "assigned", "done")]
    qa = json.loads((ROOT / "seed" / "hoi-dap" / "cau-hoi.json").read_text(encoding="utf-8"))
    docs += [(d["symbol"], d["summary"], d["assign"]["lead"]) for d in qa["documents"] if d["assign"]]
    docs += [(d["symbol"], d["summary"], d["lead"]) for d in data["history"]]
    docs += [(d["symbol"], d["summary"], user_unit(d["lead_user"])) for d in data["people"]]
    return docs


class ShapeTest(unittest.TestCase):
    """Khuôn lich-su.json như hợp đồng F4.3 §9."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_history()

    def test_keys(self) -> None:
        self.assertEqual(self.data["version"], 1)
        self.assertEqual(set(self.data), {"version", "note", "history", "people", "cases", "bait"})

    def test_symbols(self) -> None:
        d = self.data
        symbols = [x["symbol"] for x in [*d["history"], *d["people"], *d["cases"], d["bait"]]]
        self.assertEqual(len(symbols), len(set(symbols)), "số ký hiệu trùng")
        self.assertTrue(all(s.endswith("-GVM") for s in symbols), "đuôi -GVM: không trùng make seed, kho hỏi đáp")
        others = {s.symbol for s in [*seed.CNTT, *seed.KT]}
        self.assertFalse(set(symbols) & others)

    def test_documents(self) -> None:
        d = self.data
        units = managed_units()
        self.assertGreaterEqual(len(d["history"]), 20)
        for doc in [*d["history"], *d["people"], *d["cases"], d["bait"]]:
            self.assertIn(doc["type_code"], seed.TYPE_NAMES, doc["symbol"])
            self.assertTrue(doc["issuer_name"] and doc["summary"], doc["symbol"])
        for doc in [*d["history"], d["bait"]]:
            self.assertIn(doc["lead"], units, f"{doc['symbol']}: đơn vị chủ trì phải có lãnh đạo phòng")
            self.assertIn(doc["lead"], demo.UNIT_NAMES)
        for doc in [*d["history"], *d["people"], d["bait"]]:
            self.assertIsInstance(doc["due_in"], int)
            self.assertTrue(1 <= doc["due_in"] <= 60, doc["symbol"])
        everyone = users()
        for doc in d["people"]:
            self.assertIn(everyone[doc["lead_user"]][3], ("staff", "manager"), "giao thẳng người xử lý văn bản")
            self.assertIn(user_unit(doc["lead_user"]), units)
            self.assertNotIn("lead", doc)
        self.assertEqual(len(d["people"]), 2)
        topics = Counter(doc["topic"] for doc in d["history"])
        self.assertTrue(all(n >= 3 for n in topics.values()), f"mỗi cụm ≥ 3 văn bản: {topics}")
        self.assertEqual({user_unit(p["lead_user"]) for p in d["people"]}, units, "thử người → phòng ở mọi đơn vị")

    def test_restricted(self) -> None:
        d = self.data
        self.assertIs(d["bait"]["restricted"], True)
        self.assertFalse(any(doc.get("restricted") for doc in [*d["history"], *d["people"], *d["cases"]]),
                         "đúng một văn bản hạn chế: mồi")
        # mồi gần như trùng cụm học bổng của Tổ Đào tạo nhưng giao đơn vị khác: lọt vào căn cứ là thấy ngay
        hoc_bong = next(c for c in d["cases"] if c["key"] == "hoc-bong")
        self.assertNotEqual(d["bait"]["lead"], hoc_bong["expect"]["lead"])
        self.assertGreaterEqual(len(set(query_terms(d["bait"]["summary"])) & set(query_terms(hoc_bong["summary"]))), 5)

    def test_cases(self) -> None:
        cases = self.data["cases"]
        keys = [c["key"] for c in cases]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(6 <= len(cases) <= 8)
        self.assertIn("hoc-bong", keys, "demo.py giao-viec bước 3 dùng ca này")
        self.assertEqual(sum(c["expect"] == {"status": "none"} for c in cases), 1, "đúng một ca không liên quan")
        units = managed_units()
        for c in cases:
            self.assertTrue(set(c["expect"]) in ({"lead"}, {"status"}), c["key"])
            if "lead" in c["expect"]:
                self.assertIn(c["expect"]["lead"], units)
            # hợp đồng §9: seed CNTT giao "nộp đề thi kết thúc học phần" cho KTPM, kho hỏi đáp giao "thi kết thúc học
            # phần" cho ĐT — chủ đề mâu thuẫn, không làm ca có nhãn
            self.assertNotIn("thi ket thuc hoc phan", fold(c["summary"]), c["key"])
        self.assertEqual({c["expect"]["lead"] for c in cases if "lead" in c["expect"]}, units, "ca cho mọi đơn vị")


class ConsistencyTest(unittest.TestCase):
    """Nhãn các ca không mâu thuẫn với dữ liệu tác tử sẽ thấy: trong các văn bản đã giao (seed CNTT, kho hỏi đáp, lịch
    sử) chung ≥ 2 từ riêng với ca, đơn vị chiếm đa số phải là nhãn. "Từ riêng": bỏ từ có ở hơn 1/4 số văn bản (năm,
    học, sinh viên, 2026…) — các từ đó văn bản nào cũng có, Meilisearch cũng xếp chúng sau."""

    GENERIC = 0.25

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_history()
        cls.docs = labelled_corpus(cls.data)
        df = Counter(t for _, summary, _ in cls.docs for t in set(tokens(summary)))
        cls.generic = {t for t, n in df.items() if n > cls.GENERIC * len(cls.docs)}

    def shared(self, summary: str) -> list[tuple[str, str, int]]:
        q = set(query_terms(summary)) - self.generic
        return [(symbol, lead, len(q & (set(tokens(text)) - self.generic))) for symbol, text, lead in self.docs]

    def test_generic_terms_are_few(self) -> None:
        self.assertLessEqual(len(self.generic), 12, sorted(self.generic))

    def test_labelled_cases(self) -> None:
        for c in self.data["cases"]:
            if "lead" not in c["expect"]:
                continue
            votes = Counter(lead for _, lead, n in self.shared(c["summary"]) if n >= 2)
            want = c["expect"]["lead"]
            self.assertGreater(votes[want], sum(votes.values()) - votes[want], f"{c['key']}: {dict(votes)}")

    def test_unrelated_case(self) -> None:
        c = next(c for c in self.data["cases"] if c["expect"] == {"status": "none"})
        close = [(symbol, n) for symbol, _, n in self.shared(c["summary"]) if n >= 3]
        self.assertEqual(close, [], "ca không liên quan lại giống văn bản đã giao")

    def test_bait_would_mislead(self) -> None:
        """Mồi hạn chế giống cụm học bổng tới mức nếu lọt vào căn cứ thì sẽ là căn cứ mạnh của ca hoc-bong."""
        bait = set(tokens(self.data["bait"]["summary"])) - self.generic
        case = next(c for c in self.data["cases"] if c["key"] == "hoc-bong")
        self.assertGreaterEqual(len(set(query_terms(case["summary"])) - self.generic & bait), 4)

    def test_no_orphan_terms(self) -> None:
        """Meilisearch (matchingStrategy frequency) luôn giữ từ hiếm nhất của câu tìm: từ chỉ có ở chính văn bản thì
        không văn bản nào khác khớp. Mỗi từ trong 10 từ đầu của văn bản -GVM phải có ở văn bản khác (seed CNTT + -GVM,
        không tính kho hỏi đáp vì có thể chưa nạp) — trừ ca không liên quan, cố ý không giống gì."""
        d = self.data
        corpus = [(s.symbol, s.summary) for s in seed.CNTT]
        corpus += [(x["symbol"], x["summary"]) for x in [*d["history"], *d["people"], *d["cases"]]]
        orphans = {}
        for symbol, summary in corpus:
            if not symbol.endswith("-GVM") or any(c["symbol"] == symbol and "status" in c["expect"] for c in d["cases"]):
                continue
            others = set().union(*(set(tokens(s)) for sym, s in corpus if sym != symbol))
            missing = [t for t in query_terms(summary) if t not in others]
            if missing:
                orphans[symbol] = missing
        self.assertEqual(orphans, {})


def row(doc: str, actual: str | None, status: str = "suggested", unit: str | None = None, *, ranking: list | None = None,
        confidence: str | None = "high", due: int | None = None, days: int | None = None, ms: int = 100,
        evidence: list | None = None, reason: str | None = None) -> dict[str, Any]:
    """Một dòng stdout của python -m svc_workflow.advisor evaluate (hợp đồng F4.3 §5.2)."""
    return {"document_id": doc, "actual": {"department_id": actual, "days": days}, "status": status, "reason": reason,
            "department_id": unit if status == "suggested" else None, "ranking": ranking or [],
            "confidence": confidence if status == "suggested" else None, "due_days": due,
            "evidence": evidence or [], "semantic": False, "duration_ms": ms}


DT, KTPM = "5cc372aa-304d-4574-896c-4f3e781a2ce7", "7ee31261-b14c-4c42-8e1b-9a7e99935412"


class MetricsTest(unittest.TestCase):
    def rows(self) -> list[dict[str, Any]]:
        return [
            row("a", DT, unit=DT, ranking=[DT, KTPM], due=10, days=12, ms=100),
            row("b", DT, unit=KTPM, ranking=[KTPM, DT], confidence="medium", due=14, days=10, ms=200),
            row("c", KTPM, "none", reason="low_confidence", ranking=[DT, KTPM], ms=50),
            row("d", KTPM, "failed", reason="unavailable", ms=3000),
            row("e", KTPM, unit=KTPM, ranking=[KTPM], confidence="low", days=14, ms=150),
            row("f", None, unit=DT, ranking=[DT], ms=80),             # không có đáp án: không tính vào tổng
        ]

    def test_metrics(self) -> None:
        m = demo.metrics(self.rows())
        self.assertEqual((m["rows"], m["total"], m["suggested"]), (6, 5, 3))
        self.assertAlmostEqual(m["coverage"], 0.6)
        # top-1: none, failed là sai; top-2, top-3 theo ranking (vẫn tính khi none)
        self.assertEqual((m["top1"], m["top2"], m["top3"]), (2, 4, 4))
        self.assertAlmostEqual(m["top1_rate"], 0.4)
        self.assertEqual(m["by_confidence"], {"high": {"n": 1, "correct": 1}, "medium": {"n": 1, "correct": 0},
                                              "low": {"n": 1, "correct": 1}})
        self.assertEqual(m["outcomes"], {"none/low_confidence": 1, "failed/unavailable": 1})
        self.assertEqual((m["due_compared"], m["due_mae"], m["due_within1"]), (2, 3.0, 0))
        self.assertEqual((m["p50_ms"], m["p95_ms"]), (100, 3000))
        self.assertEqual((m["units"], m["majority"]), (2, 0.6))

    def test_failed_rows_are_wrong(self) -> None:
        """evaluate trả failed kèm mã lỗi (restricted, not_found, timeout, unavailable) — không bao giờ là đúng."""
        rows = [row(str(i), DT, "failed", reason=r) for i, r in enumerate(("restricted", "not_found", "timeout"))]
        m = demo.metrics(rows)
        self.assertEqual((m["total"], m["top1"], m["top3"], m["coverage"]), (3, 0, 0, 0.0))
        self.assertEqual(demo.gv_verdict(m, [])[0], f"top-1 0/3 (0%) dưới ngưỡng {demo.MIN_TOP1:.0%}")

    def test_empty(self) -> None:
        m = demo.metrics([])
        self.assertEqual((m["total"], m["top1_rate"], m["p50_ms"], m["due_mae"]), (0, 0.0, None, None))
        self.assertEqual(demo.gv_verdict(m, []), ["evaluate không trả dòng nào có đáp án"])

    def test_verdict(self) -> None:
        good = demo.metrics([row(str(i), DT, unit=DT, ranking=[DT]) for i in range(5)])
        self.assertEqual(demo.gv_verdict(good, []), [])
        problems = demo.gv_verdict(good, ["17/CTSV-GVM → x"])
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("căn cứ là văn bản hạn chế"))

    def test_table(self) -> None:
        lines = demo.gv_table(self.rows(), {"a": "17/CTSV-GVM"}).splitlines()
        self.assertEqual(len(lines), 2 + len(self.rows()))
        self.assertEqual({line.count("|") for line in lines}, {9})
        self.assertIn("| 17/CTSV-GVM | ĐT | ✓ ĐT | cao | ĐT, KTPM | 10 / 12 | 0 | 100 |", lines[2])
        self.assertIn("✗ failed/unavailable", lines[5])


class AuditTest(unittest.TestCase):
    DIFF = {"outcome": "suggested", "outcome_reason": None, "department_id": DT, "due_days": 10,
            "confidence": "high", "evidence": 4, "candidates": 12, "semantic": False, "duration_ms": 183}

    def test_clean(self) -> None:
        rows = [["d1", "moc-assigner", "agent", json.dumps(self.DIFF)]]
        self.assertEqual(demo.audit_problems(rows, {"hoc-bong": "d1"}, {"d1": ["học", "bổng", "301/CTSV-GVM-AB12CD"]}),
                         [])

    def test_problems(self) -> None:
        leaky = {**self.DIFF, "summary": "xét cấp học bổng"}
        rows = [["d1", "moc-assigner", "agent", json.dumps(leaky, ensure_ascii=False)],
                ["d1", "vanthu", "user", json.dumps(self.DIFF)]]
        problems = demo.audit_problems(rows, {"a": "d1", "b": "d2"}, {"d1": demo.summary_words("Về việc xét học bổng")})
        self.assertIn("a: 2 dòng (cần 1)", problems)
        self.assertIn("b: 0 dòng (cần 1)", problems)
        self.assertIn("d1: người thực hiện vanthu/user", problems)
        self.assertIn("d1: khóa lạ ['summary']", problems)
        self.assertTrue(any("diff có chữ của văn bản" in p and "bổng" in p for p in problems), problems)

    def test_uuid_does_not_count_as_text(self) -> None:
        """Mã lần chạy là hex: trùng tình cờ với id phòng trong diff không phải rò chữ."""
        rows = [["d1", "moc-assigner", "agent", json.dumps(self.DIFF)]]
        self.assertEqual(demo.audit_problems(rows, {"a": "d1"}, {"d1": ["5cc372aa"]}), [])

    def test_summary_words(self) -> None:
        self.assertEqual(demo.summary_words("Về việc xét cấp học bổng học kỳ II năm 2026–2027"),
                         ["việc", "xét", "cấp", "học", "bổng", "học", "năm"])


class DoGiaoViecTest(unittest.TestCase):
    """make do-giao-viec trên evaluate giả: thoát 0 khi đạt, 1 khi có căn cứ hạn chế (cả mồi) hoặc top-1 thấp."""

    def run_main(self, rows_for: Any, *, sealed: set[str] = frozenset()) -> tuple[int, str, str]:
        data = load_history()
        docs = [data["bait"], *data["history"], *data["people"]]
        ids = {d["symbol"]: str(uuid.uuid5(uuid.NAMESPACE_URL, d["symbol"])) for d in docs}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(demo, "load_history", return_value=(ids, 0)), \
                mock.patch.object(demo, "wait_history_indexed", return_value=0.0), \
                mock.patch.object(demo, "gv_tenant", return_value="c300d5bb-028f-44cc-ba10-7b5277a4225d"), \
                mock.patch.object(demo, "run_evaluate", side_effect=lambda tenant, documents: rows_for(data, ids)), \
                mock.patch.object(demo, "valid_units", return_value=2), \
                mock.patch.object(demo, "suggestion_latency", return_value=(12, 2.1, 4.0)), \
                mock.patch.object(demo, "stored_leaks", return_value=0), \
                mock.patch.object(demo, "restricted_among", side_effect=lambda found: set(found) & set(sealed)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = demo.main(["do-giao-viec"])
        return code, out.getvalue(), err.getvalue()

    @staticmethod
    def correct(data: dict[str, Any], ids: dict[str, str], evidence: list[str] | None = None) -> list[dict]:
        rows = []
        for d in [*data["history"], *data["people"]]:
            unit = seed.DEPT[d["lead"] if "lead" in d else user_unit(d["lead_user"])]
            rows.append(row(ids[d["symbol"]], unit, unit=unit, ranking=[unit], due=d["due_in"], days=d["due_in"],
                            evidence=evidence or [ids[data["history"][0]["symbol"]]]))
        return rows

    def test_pass(self) -> None:
        code, out, err = self.run_main(self.correct)
        self.assertEqual(code, 0, err)
        self.assertIn("top-1: 29/29 (100%", out)
        self.assertIn("2 đơn vị có lãnh đạo phòng", out)
        self.assertIn("✓ không căn cứ nào là văn bản hạn chế", out)

    def test_restricted_evidence_fails(self) -> None:
        leaked = "0b0e5d3c-1f6e-4c5b-9b0e-6a2f3f0a9d11"
        code, _, err = self.run_main(lambda data, ids: self.correct(data, ids, [leaked]), sealed={leaked})
        self.assertEqual(code, 1)
        self.assertIn("căn cứ là văn bản hạn chế", err)

    def test_bait_evidence_fails(self) -> None:
        def with_bait(data: dict[str, Any], ids: dict[str, str]) -> list[dict]:
            return self.correct(data, ids, [ids[data["bait"]["symbol"]]])

        code, _, err = self.run_main(with_bait)
        self.assertEqual(code, 1)
        self.assertIn("căn cứ là văn bản hạn chế", err)

    def test_low_top1_fails(self) -> None:
        def mostly_none(data: dict[str, Any], ids: dict[str, str]) -> list[dict]:
            rows = self.correct(data, ids)
            return [r if i % 3 == 0 else row(r["document_id"], r["actual"]["department_id"], "none",
                                               reason="no_similar") for i, r in enumerate(rows)]

        code, _, err = self.run_main(mostly_none)
        self.assertEqual(code, 1)
        self.assertIn("dưới ngưỡng", err)


class WiringTest(unittest.TestCase):
    def test_demos_and_make_targets(self) -> None:
        self.assertIs(demo.DEMOS["giao-viec"], demo.giao_viec)
        self.assertIs(demo.DEMOS["do-giao-viec"], demo.do_giao_viec)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        phony = re.search(r"^\.PHONY:((?:.*\\\n)*.*)$", makefile, re.M).group(1).replace("\\\n", " ")
        for target, man in (("demo-giao-viec", "giao-viec"), ("do-giao-viec", "do-giao-viec")):
            self.assertRegex(makefile, rf"(?m)^{target}: .*## ")
            self.assertRegex(makefile, rf"scripts/demo\.py {man}\b")
            self.assertIn(target, phony.split())


if __name__ == "__main__":
    unittest.main()
