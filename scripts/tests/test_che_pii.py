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

"""Che thông tin cá nhân (F4.4): hàm thuần của make demo-che-pii (scripts/demo.py) — cách viết của giá trị giả lập,
dò lọt trong nhật ký, dòng truy cập, lý do màn đỏ — trên nhật ký giả; lá đơn giả lập khớp bộ che thật của svc-files
(services/svc-files/src/svc_files/pii.py, chỉ thư viện chuẩn) nếu có trong cây mã. Không cần Docker, không đọc .env.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib
import importlib.util
import json
import pathlib
import re
import sys
import types
import unittest
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
PII = ROOT / "services" / "svc-files" / "src" / "svc_files" / "pii.py"

demo: Any = None
pii: Any = None
_saved: dict[str, Any] = {}


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp (thiếu thì thoát): thay bằng bản giả chỉ có những gì demo.py nhập; mọi lời gọi
    mạng, Docker đều là lỗi. pii.py nạp thẳng từ tệp (không cần cài svc-files), không có thì các ca đối chiếu bỏ qua."""
    global demo, pii
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
    if PII.is_file():
        spec = importlib.util.spec_from_file_location("_pii_che_pii", PII)
        pii = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = pii             # dataclass tra module của lớp lúc tạo lớp
        spec.loader.exec_module(pii)


def tearDownModule() -> None:
    sys.modules.pop("_pii_che_pii", None)
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    if str(SCRIPTS) in sys.path:
        sys.path.remove(str(SCRIPTS))


def access(path: str, status: int = 200) -> dict[str, str]:
    """Một dòng truy cập mỗi dịch vụ, đúng định dạng sau F4.4: APISIX, nginx ghi đường dẫn đã cắt ở dấu ? (cả trường
    đích upstream của APISIX), không Referer; uvicorn ghi …?…."""
    return {
        "apisix": f'172.18.0.1 - - [22/Oct/2026:10:00:00 +0700] localhost:8080 "GET {path} HTTP/1.1" {status} 512'
                  f' 0.012 "Mozilla/5.0" 172.18.0.9:8000 200 0.010 "http://svc-files:8000{path}"',
        "svc-files": f'172.18.0.5:51234 - "GET {path}?… HTTP/1.1" {status} OK',
        "app-office": f'172.18.0.5 - - [22/Oct/2026:10:00:00 +0700] "GET {path} HTTP/1.1" {status} 1043 "Mozilla/5.0"'
                      ' "172.18.0.1"',
    }


def clean_logs() -> dict[str, str]:
    """Nhật ký của một lượt chạy đạt: đủ dòng truy cập, tên tệp đã che, dòng sự kiện JSON chữ có dấu."""
    search, page = access("/api/search"), access("/tim-kiem")
    rejected = json.dumps({"event": "core.file.rejected", "request_id": "r1", "filename": "don-[SĐT].txt",
                           "sha256": "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f",
                           "size_bytes": 68}, ensure_ascii=False)
    asked = json.dumps({"event": "office.assist.asked", "request_id": "r2", "mode": "extract", "q_length": 83,
                        "hits": 3, "duration_ms": 1792281602100}, ensure_ascii=False)
    return {
        "apisix": "\n".join([search["apisix"], page["apisix"],
                             access("/api/files")["apisix"].replace("GET", "POST")]),
        "svc-files": "\n".join([json.dumps({"event": "core.search", "q_length": 12, "hits": 1}), search["svc-files"],
                                rejected, asked, '172.18.0.5:51234 - "POST /api/files HTTP/1.1" 422 Unprocessable']),
        "app-office": page["app-office"],
        "svc-workflow": '{"event": "office.action.ok", "action": "receiveIncoming", "document_id": '
                        '"c300d5bb-1234-4abc-8def-000000000001"}',
    }


class SpellingTests(unittest.TestCase):
    def test_every_documented_form_is_listed(self):
        forms = set(demo.spellings(demo.PII_DEMO))
        expected = {
            # CCCD: liền, 3-3-3-3, 4-4-4, chấm, gạch, mã hóa URL
            "001205000017", "001 205 000 017", "0012 0500 0017", "001.205.000.017", "001-205-000-017",
            # di động: như đã viết, liền, chấm, gạch, 3-3-4, +84 / (+84) / 0084 / 84, %20, dấu cộng của form
            "0912 345 678", "0912345678", "0912.345.678", "0912-345-678", "091 234 5678", "+84912345678",
            "+84 912 345 678", "(+84) 912 345 678", "0084912345678", "84912345678", "0912%20345%20678",
            "0912+345+678", "%2B84%20912%20345%20678",
            # máy bàn: như đã viết, liền, mã vùng không ngoặc, +84
            "(024) 3000 0000", "02430000000", "024 3000 0000", "024.3000.0000", "+84 24 3000 0000", "+842430000000",
            # email: như đã viết và %40 (chuỗi truy vấn)
            "nguyenvanb@example.com", "nguyenvanb%40example.com",
            # số tài khoản: như đã viết, liền
            "0011 0041 23456", "0011004123456", "0011.0041.23456",
        }
        self.assertEqual(expected - forms, set())

    def test_forms_are_unique_and_never_empty(self):
        forms = demo.spellings(demo.PII_DEMO)
        self.assertEqual(len(forms), len(set(forms)))
        self.assertTrue(all(len(f) >= 10 for f in forms), [f for f in forms if len(f) < 10])
        self.assertGreater(len(forms), 60)

    def test_forms_of_each_value_contain_its_digits_or_address(self):
        # mỗi cách viết là của một trong năm giá trị: bỏ mã hóa, ký tự phân cách và mã nước thì ra đúng chữ số gốc
        digits = {re.sub(r"\D", "", v) for v in demo.PII_DEMO.values() if "@" not in v}
        for form in demo.spellings(demo.PII_DEMO):
            if "@" in form or "%40" in form:
                self.assertIn("nguyenvanb", form.casefold())
                continue
            bare = re.sub(r"\D", "", form.replace("%20", " ").replace("%2B", "+").replace("%28", "(").replace("%29", ")"))
            national = {"0" + bare[len(cc):] for cc in ("0084", "84") if bare.startswith(cc)}
            self.assertTrue({bare, *national} & digits, form)


class LeakTests(unittest.TestCase):
    def setUp(self):
        self.forms = demo.spellings(demo.PII_DEMO)

    def test_finds_values_inside_log_lines(self):
        cases = [
            ('{"event": "core.file.rejected", "filename": "don-0912345678.txt"}', "0912345678"),
            ('10.0.0.1 - - "GET /api/search?q=001205000017 HTTP/1.1" 200', "001205000017"),
            ('"GET /tim-kiem?q=0912%20345%20678 HTTP/1.1" 200', "0912%20345%20678"),
            ('"GET /hoi-dap?q=NguyenVanB%40Example.com HTTP/1.1"', "nguyenvanb%40example.com"),
            ("ValueError: CCCD 001 205 000 017 sai", "001 205 000 017"),
            ("lien he (+84) 912 345 678 hoac 024.3000.0000", "(+84) 912 345 678"),
            ("STK 0011004123456.", "0011004123456"),
            ("Email: NGUYENVANB@EXAMPLE.COM", "nguyenvanb@example.com"),
        ]
        for text, form in cases:
            with self.subTest(text=text):
                self.assertIn(form, demo.leaks(text, self.forms))

    def test_masked_lines_and_longer_numbers_are_not_leaks(self):
        for text in ('{"filename": "don-[SĐT].txt"}', "CCCD [CCCD], liên hệ [SĐT-1], [EMAIL-1], STK [STK-1]",
                     '"GET /api/search?… HTTP/1.1" 200', "mốc 10912345678000 và 90011004123456",
                     "uuid c300d5bb-1234-4abc-8def-000000000017", "0912 345 67", "nguyenvanb@example.org",
                     "001205000018"):
            with self.subTest(text=text):
                self.assertEqual(demo.leaks(text, self.forms), [])

    def test_clean_run_has_no_problem(self):
        self.assertEqual(demo.log_problems(clean_logs(), self.forms), [])

    def test_each_fault_is_reported_by_service(self):
        faults = {
            "svc-workflow: lọt": ("svc-workflow", "\nValueError: số 0912.345.678 không hợp lệ"),
            "svc-files: lọt": ("svc-files", '\n{"event": "core.file.rejected", "filename": "don-0912345678.txt"}'),
            "apisix: lọt": ("apisix", '\n1.2.3.4 - - [x] h "GET /api/search?q=001205000017 HTTP/1.1" 200'),
            "app-office: 1 dòng còn chuỗi truy vấn": ("app-office", '\n"GET /tim-kiem?q=abc HTTP/1.1" 200'),
        }
        for want, (service, extra) in faults.items():
            with self.subTest(want=want):
                logs = clean_logs()
                logs[service] += extra
                problems = demo.log_problems(logs, self.forms)
                self.assertTrue(any(p.startswith(want) for p in problems), problems)

    def test_missing_access_lines_and_masked_name_are_problems(self):
        logs = clean_logs()
        logs["app-office"] = ""
        logs["svc-files"] = logs["svc-files"].replace("don-[SĐT].txt", "don-x.txt")
        problems = demo.log_problems(logs, self.forms)
        self.assertTrue(any(p.startswith("app-office: không có dòng truy cập /tim-kiem") for p in problems), problems)
        self.assertTrue(any("core.file.rejected" in p for p in problems), problems)
        # thiếu nhật ký của cả một dịch vụ cũng là lỗi, không lặng lẽ đạt
        logs = clean_logs()
        del logs["apisix"]
        problems = demo.log_problems(logs, self.forms)
        self.assertEqual(sum(p.startswith("apisix: không có dòng truy cập") for p in problems), 2, problems)

    def test_masked_name_escaped_by_json_ascii_still_counts(self):
        logs = clean_logs()
        logs["svc-files"] = logs["svc-files"].replace("don-[SĐT].txt", "don-[S\\u0110T].txt")
        self.assertEqual(demo.log_problems(logs, self.forms), [])


class SettledLogsTests(unittest.TestCase):
    """APISIX xả nhật ký truy cập sau tới 3 giây: bước 6 đợi đủ thời gian xả rồi đọc lại tới khi có đủ dòng truy cập."""

    def setUp(self):
        self.now = 100.0
        self.slept: list[float] = []
        self.reads = 0
        clock = types.SimpleNamespace(monotonic=lambda: self.now, sleep=self.sleep)
        self._saved = (demo.time, demo.service_logs)
        demo.time = clock

    def tearDown(self):
        demo.time, demo.service_logs = self._saved

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def serve(self, *answers: dict[str, str]):
        def read(since: str, *services: str) -> dict[str, str]:
            self.assertEqual(services, demo.PII_LOGGED)
            self.reads += 1
            return answers[min(self.reads, len(answers)) - 1]
        demo.service_logs = read

    def test_waits_for_flush_then_rereads_until_access_lines_appear(self):
        late = clean_logs()
        early = dict(late, apisix="")             # đệm APISIX chưa xả
        self.serve(early, late)
        self.assertEqual(demo.settled_logs("2026-10-22T00:00:00Z", last_request=self.now), late)
        self.assertEqual(self.slept[0], demo.LOG_FLUSH_S)
        self.assertEqual(self.reads, 2)

    def test_gives_up_after_timeout_and_returns_last_read(self):
        missing = dict(clean_logs(), apisix="")
        self.serve(missing)
        got = demo.settled_logs("2026-10-22T00:00:00Z", last_request=self.now - 60, timeout_s=5)
        self.assertEqual(got, missing)
        self.assertEqual(self.slept[0], 0.0)      # yêu cầu cuối đã lâu: không đợi thêm
        self.assertLessEqual(sum(self.slept), 6)
        self.assertTrue(any(p.startswith("apisix: không có dòng truy cập") for p in demo.log_problems(got, [])))


class WaitPiiAnswerTests(unittest.TestCase):
    """Bước 4 đợi trang của lá đơn vào chỉ mục đoạn. Trên bản cài mới nguồn "trích yếu" (vào chỉ mục lúc tiếp nhận,
    không có số điện thoại) có trước: chưa tính là xong."""

    DOC = "c300d5bb-1234-4abc-8def-000000000002"

    def setUp(self):
        self.now = 100.0
        self.asked = 0
        self._saved = (demo.time, demo.ask)
        demo.time = types.SimpleNamespace(monotonic=lambda: self.now, sleep=self.sleep)

    def tearDown(self):
        demo.time, demo.ask = self._saved

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def serve(self, *answers: dict[str, Any]) -> None:
        def ask(session: Any, question: str) -> tuple[dict[str, Any], None]:
            self.assertEqual(question, demo.PII_QUESTION)
            self.asked += 1
            return answers[min(self.asked, len(answers)) - 1], None
        demo.ask = ask

    def answer(self, *kinds: str) -> dict[str, Any]:
        return {"status": "answered", "sources": [
            {"document_id": self.DOC, "kind": kind, "page": 1 if kind == "page" else None} for kind in kinds]}

    def test_summary_source_alone_keeps_waiting_for_the_page(self):
        summary, page = self.answer("meta"), self.answer("meta", "page")
        self.serve(summary, summary, page)
        self.assertIs(demo.wait_pii_answer(object(), self.DOC, 90), page)
        self.assertEqual(self.asked, 3)

    def test_times_out_when_only_the_summary_is_indexed(self):
        self.serve(self.answer("meta"))
        with self.assertRaises(demo.DemoFailed):
            demo.wait_pii_answer(object(), self.DOC, 10)


class AccessLineTests(unittest.TestCase):
    def test_access_line_formats(self):
        sample = access("/api/search")
        for service, line in sample.items():
            with self.subTest(service=service):
                self.assertEqual(demo.access_lines(line, "/api/search"), [line])
        # nginx còn ghi $uri (try_files đã đổi /tim-kiem thành /index.html): không phải dòng của trang Tìm kiếm
        spa = '1.2.3.4 - - [x] "GET /index.html HTTP/1.1" 200 1043 "Mozilla/5.0" "-"'
        self.assertEqual(demo.access_lines(spa, "/tim-kiem"), [])
        logs = clean_logs()
        logs["app-office"] = spa
        problems = demo.log_problems(logs, demo.spellings(demo.PII_DEMO))
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith("app-office: không có dòng truy cập /tim-kiem"), problems)

    def test_other_paths_and_event_lines_are_not_access_lines(self):
        text = "\n".join(['"GET /api/search-khac HTTP/1.1" 200', '"GET /api/searchx?q=1 HTTP/1.1" 200',
                          '{"event": "core.search", "path": "/api/search"}', "GET/api/search",
                          '"GET /x/api/search HTTP/1.1" 200'])
        self.assertEqual(demo.access_lines(text, "/api/search"), [])
        self.assertEqual(len(demo.access_lines('"GET /api/search HTTP/1.1"\n"HEAD /api/search?… HTTP/1.1"',
                                               "/api/search")), 2)


class LogEventTests(unittest.TestCase):
    def test_json_events_only(self):
        text = "\n".join([
            '172.18.0.5:51234 - "POST /api/documents/ask HTTP/1.1" 200 OK',
            json.dumps({"event": "office.assist.asked", "mode": "extract", "masked": 0}),
            "{không phải JSON",
            json.dumps({"event": "office.assist.asked", "mode": "generate", "masked": 7}, ensure_ascii=False),
            json.dumps({"event": "office.assist.pii_at_egress", "masked": 1}),
            json.dumps(["office.assist.asked"]),
        ])
        asked = demo.log_events(text, "office.assist.asked")
        self.assertEqual([(e["mode"], e["masked"]) for e in asked], [("extract", 0), ("generate", 7)])
        self.assertEqual(len(demo.log_events(text, "office.assist.pii_at_egress")), 1)
        self.assertEqual(demo.log_events("", "office.assist.asked"), [])


class LetterTests(unittest.TestCase):
    def test_letter_is_ascii_one_page_with_every_value(self):
        lines = demo.pii_letter("A1B2C3")
        text = "\n".join(lines)
        self.assertTrue(text.isascii())
        self.assertLessEqual(len(lines), 50)
        self.assertTrue(all(len(line) <= 80 for line in lines), [line for line in lines if len(line) > 80])
        for value in demo.PII_DEMO.values():
            self.assertIn(value, text)
        # các số không được che, và chân trang giả lập
        for phrase in ("cap ngay 05/3/2021", "02 ban sao", "sinh nam 2005", "Ma ho so: A1B2C3"):
            self.assertIn(phrase, text)
        self.assertEqual(lines[-1], "Van ban gia lap de chay thu Moc, khong phai van ban that.")

    def test_question_and_metadata_carry_no_personal_data(self):
        forms = demo.spellings(demo.PII_DEMO)
        for text in (demo.PII_QUESTION, demo.PII_SUMMARY, demo.PII_SYMBOL, demo.PII_ISSUER):
            self.assertEqual(demo.leaks(text, forms), [], text)
        self.assertEqual(demo.leaks(demo.PII_FILE_MASKED, forms), [])
        self.assertEqual(demo.leaks(demo.PII_FILE, forms), ["0912345678"])

    def test_the_phone_sentence_shares_most_terms_with_the_question(self):
        # trợ lý chọn câu có nhiều từ của câu hỏi nhất (so trên chữ bỏ dấu): câu có số điện thoại phải hơn hẳn tiêu đề
        # và câu "cấp 02 bản sao…" — nếu không, câu trích ở bước 4 không có số điện thoại
        def words(s: str) -> set[str]:
            import unicodedata
            folded = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
            return set(re.findall(r"[a-z]+", "".join(c for c in folded if not unicodedata.combining(c)).casefold()))

        question = words(demo.PII_QUESTION) - {"cua", "la", "gi", "sao"}          # từ dừng của svc-files assist/vi.py
        lines = demo.pii_letter("A1B2C3")
        scores = {line: len(question & words(line)) for line in lines}
        phone_line = next(line for line in lines if demo.PII_DEMO["phone"] in line)
        self.assertTrue(all(n < scores[phone_line] for line, n in scores.items() if line != phone_line), scores)


@unittest.skipIf(not PII.is_file(), "không có services/svc-files (thư mục cài)")
class MaskerAgreementTests(unittest.TestCase):
    """Màn demo và bộ che của svc-files phải nói cùng một thứ: mọi giá trị giả lập bị che ở mọi cách viết bộ che hứa
    che, lá đơn ra đúng năm nhãn, tên tệp EICAR ra đúng tên đã che, mẫu nhãn giống hệt."""

    def test_label_patterns_match(self):
        self.assertEqual(demo.MASK_LABEL_RE.pattern, pii.LABEL_RE.pattern)

    def test_letter_masks_to_five_labels_and_keeps_other_numbers(self):
        text = "\n".join(demo.pii_letter("123456"))
        masked = pii.mask(text, year=2026)
        self.assertEqual(masked.counts(), {"cccd": 1, "phone": 2, "email": 1, "account": 1})
        self.assertEqual(demo.leaks(masked.text, demo.spellings(demo.PII_DEMO)), [])
        self.assertEqual(len(demo.MASK_LABEL_RE.findall(masked.text)), len(demo.PII_DEMO))
        for phrase in ("cap ngay 05/3/2021", "02 ban sao", "sinh nam 2005", "Ma ho so: 123456"):
            self.assertIn(phrase, masked.text)

    def test_file_name_masks_as_expected(self):
        self.assertEqual(pii.mask_text(demo.PII_FILE), demo.PII_FILE_MASKED)

    def test_every_plain_form_is_masked_in_a_sentence(self):
        # chuỗi truy vấn đã mã hóa (%20, %40, dấu cộng) thì bộ che không thấy — vì vậy nhật ký truy cập bỏ cả chuỗi
        # truy vấn; "84…" không dấu cộng là cách viết bộ che không hứa che. Số tài khoản chỉ che khi có từ khóa
        forms = [f for f in demo.spellings(demo.PII_DEMO)
                 if "%" not in f and "+" not in f.lstrip("+").replace("(+84)", "") and not f.startswith("84")]
        self.assertGreater(len(forms), 30)
        for form in forms:
            digits = re.sub(r"\D", "", form)
            sentence = f"Số tài khoản {form} nhé" if digits.startswith("0011") else f"Liên hệ {form} nhé"
            with self.subTest(form=form):
                self.assertEqual(demo.leaks(pii.mask_text(sentence), [form]), [], pii.mask_text(sentence))


if __name__ == "__main__":
    unittest.main()
