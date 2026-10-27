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

"""Màn make demo-quy-trinh (scripts/demo.py quy-trinh, #301) — phần không cần Signet đang chạy: ba tài khoản mẫu đúng
vai, đúng phòng theo seed/users.csv; dữ liệu sai và mã lỗi chờ đợi trùng ca thử dùng chung của form; đơn mẫu hợp lệ;
bản BPMN độc có scriptTask nằm trên đường đi; lời gọi API như trang; đăng nhập qua mật khẩu rồi mã TOTP; bước CI và
lệnh make. Không cần Docker, không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib
import json
import pathlib
import re
import sys
import tempfile
import types
import unicodedata
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
APP = ROOT / "apps" / "nghi-phep"
BPMN_NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"

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
    for name in ("moc_env", "demo", "demo_ca_nhan"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng, Docker")

    stub.ENV = {"MOC_DEMO_PASSWORD": "mat-khau-thu", "MOC_DEMO_TOTP_SECRET": "khoa-thu"}
    stub.ROOT = ROOT
    stub.PUBLIC_URL = "http://localhost:8080"
    stub.EICAR = b""
    stub.HTTPError = FakeHTTPError
    stub.Session = type("Session", (), {"__init__": no_network})
    for name in ("call_json", "compose", "request", "text_pdf", "user_token"):
        setattr(stub, name, no_network)
    stub.totp_at = lambda secret, counter: f"{secret}:{counter}"
    stub._otp_counter = lambda username: 7
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


def users() -> dict[str, list[str]]:
    """seed/users.csv: username → [username, họ, tên, vai trò, tenant, phòng]."""
    return {line.split(",")[0]: line.split(",") for line in (ROOT / "seed" / "users.csv").read_text(
        encoding="utf-8").splitlines() if line and not line.startswith("#")}


def cases(name: str) -> dict[str, Any]:
    return json.loads((APP / "forms" / f"{name}.cases.json").read_text(encoding="utf-8"))


class Scenario(unittest.TestCase):
    def test_seed_accounts_play_their_parts(self) -> None:
        u = users()
        staff, manager, other = u[demo.QT_STAFF], u[demo.QT_MANAGER], u[demo.QT_OTHER]
        self.assertEqual((staff[3], manager[3], other[3]), ("staff", "manager", "manager"))
        # cùng đơn vị: trưởng phòng khác không thấy việc vì khác phòng, không phải vì khác đơn vị
        self.assertEqual({staff[4], manager[4], other[4]}, {staff[4]})
        self.assertEqual(staff[5], manager[5])
        self.assertNotEqual(staff[5], other[5])
        self.assertNotEqual(other[5], "-")
        # phòng của người gửi chỉ có một trưởng phòng mẫu, chính là người duyệt
        same = [r[0] for r in u.values() if r[5] == staff[5] and r[3] == "manager"]
        self.assertEqual(same, [demo.QT_MANAGER])

    def test_wrong_data_and_codes_match_the_shared_form_cases(self) -> None:
        don = cases("don")
        expected = {json.dumps(c["error"], sort_keys=True) for c in don["invalid"]}
        self.assertIn(json.dumps(demo.QT_BAD_RANGE, sort_keys=True), expected)
        enum_case = next(c for c in don["invalid"] if c.get("set", {}).get("loai") == demo.QT_WRONG_TYPE)
        self.assertEqual(enum_case["error"], demo.QT_BAD_TYPE)
        duyet = cases("duyet")
        wrong = next(c for c in duyet["invalid"] if c.get("set", {}).get("quyetDinh") == demo.QT_WRONG_DECISION)
        self.assertEqual(wrong["error"], demo.QT_BAD_DECISION)
        schema = json.loads((APP / "forms" / "duyet.json").read_text(encoding="utf-8"))
        self.assertIn("dong-y", schema["properties"]["quyetDinh"]["enum"])
        self.assertEqual((demo.QT_FORM_DON, demo.QT_FORM_DUYET, demo.QT_PROCESS),
                         ("nghi-phep.don", "nghi-phep.duyet", "nghi-phep.don"))

    def test_leave_request_is_valid_and_bad_range_reverses_it(self) -> None:
        schema = json.loads((APP / "forms" / "don.json").read_text(encoding="utf-8"))
        req = demo.leave_request(date(2026, 10, 26), "ABC123")
        self.assertEqual(req["tuNgay"], "2026-11-02")
        self.assertEqual(req["denNgay"], "2026-11-04")
        self.assertLessEqual(set(req), set(schema["properties"]))
        self.assertLessEqual(set(schema["required"]), set(req))
        self.assertIn(req["loai"], schema["properties"]["loai"]["enum"])
        self.assertEqual(req["lyDo"], unicodedata.normalize("NFC", req["lyDo"]))
        self.assertEqual(req["lyDo"], req["lyDo"].strip())
        self.assertLessEqual(len(req["lyDo"]), schema["properties"]["lyDo"]["maxLength"])
        self.assertIn("ABC123", req["lyDo"])
        bad = demo.bad_range(req)
        self.assertEqual((bad["tuNgay"], bad["denNgay"]), (req["denNgay"], req["tuNgay"]))
        self.assertLess(bad["denNgay"], bad["tuNgay"])
        self.assertEqual(req["tuNgay"], "2026-11-02", "bad_range không được sửa đơn gốc")

    def test_poison_bpmn_puts_a_script_task_on_the_path(self) -> None:
        xml = (APP / "workflow" / "don-nghi-phep.bpmn20.xml").read_text(encoding="utf-8")
        self.assertNotIn("scriptTask", xml)
        poisoned = demo.poison_bpmn(xml)
        process = ET.fromstring(poisoned.encode()).find(f"{BPMN_NS}process")
        scripts = process.findall(f"{BPMN_NS}scriptTask")
        self.assertEqual(len(scripts), 1)
        flows = {(f.get("sourceRef"), f.get("targetRef")) for f in process.findall(f"{BPMN_NS}sequenceFlow")}
        self.assertIn(("guiDon", "chayMa"), flows)
        self.assertIn(("chayMa", "duyet"), flows)
        self.assertNotIn(("guiDon", "duyet"), flows)
        with self.assertRaises(ValueError):
            demo.poison_bpmn("<definitions/>")

    def test_poison_copy_changes_only_the_bpmn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = demo.poison_copy(pathlib.Path(tmp) / "nghi-phep")
            self.assertEqual(manifest.read_bytes(), (APP / "app.yaml").read_bytes())
            self.assertFalse((manifest.parent / "tests").exists())
            bpmn = (manifest.parent / "workflow" / "don-nghi-phep.bpmn20.xml").read_text(encoding="utf-8")
            self.assertIn("<scriptTask ", bpmn)
            for rel in ("Dockerfile", "server.py", "forms/don.json", "forms/duyet.json", "public/index.html"):
                self.assertEqual((manifest.parent / rel).read_bytes(), (APP / rel).read_bytes(), rel)


class Calls(unittest.TestCase):
    def test_api_call_like_the_page(self) -> None:
        sent: list[tuple[str, str, Any, dict[str, str]]] = []

        def request(method: str, url: str, *, data: Any = None, headers: Any = None, timeout: float = 60) -> Any:
            sent.append((method, url, data, headers))
            return 201, {}, b'{"id": "p1"}'

        with mock.patch.object(demo, "request", request):
            self.assertEqual(demo.qt_call("tok", "POST", "/processes/nghi-phep.don", {"loai": "om"}),
                             (201, {"id": "p1"}))
            demo.qt_call("tok", "GET", "/tasks")
        method, url, data, headers = sent[0]
        self.assertEqual(url, "http://localhost:8080/api/workflow/nghi-phep/processes/nghi-phep.don")
        self.assertEqual(json.loads(data), {"data": {"loai": "om"}})
        self.assertEqual((headers["Authorization"], headers["Content-Type"]), ("Bearer tok", "application/json"))
        self.assertIsNone(sent[1][2])
        self.assertNotIn("Content-Type", sent[1][3])

        def refused(*args: Any, **kwargs: Any) -> Any:
            raise FakeHTTPError(422, '{"errors": {"denNgay": "x-moc-range"}}')

        with mock.patch.object(demo, "request", refused):
            self.assertEqual(demo.qt_call("tok", "POST", "/processes/x", {}), (422, {"errors": QT_RANGE}))
        with mock.patch.object(demo, "request", lambda *a, **k: (_ for _ in ()).throw(FakeHTTPError(502, "<html>"))):
            self.assertEqual(demo.qt_call("tok", "GET", "/tasks"), (502, None))
        with mock.patch.object(demo, "request", lambda *a, **k: (200, {}, b'{"id": 1}')):
            with self.assertRaises(demo.DemoFailed):
                demo.qt_list("tok", "/tasks")
        self.assertEqual(demo.task_of([{"processId": "a"}, {"processId": "b", "id": "t"}], "b"), {"processId": "b",
                                                                                                "id": "t"})
        self.assertIsNone(demo.task_of(None, "b"))

    def test_login_types_password_then_totp(self) -> None:
        """Như trang: code + PKCE S256, response_mode=fragment; trang mật khẩu rồi trang mã TOTP; state phải khớp."""
        opened: list[tuple[str, dict[str, list[str]]]] = []
        exchanged: list[tuple[str, str, str, str]] = []

        class Resp:
            def __init__(self, url: str, body: str = ""):
                self.url, self.body = url, body

            def geturl(self) -> str:
                return self.url

            def read(self) -> bytes:
                return self.body.encode()

        class Opener:
            def open(self, url: str, timeout: float = 0, data: bytes | None = None) -> Resp:
                form = urllib.parse.parse_qs(data.decode()) if data else {}
                opened.append((url, form))
                if data is None:
                    self.query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                    return Resp("http://localhost:8080/realms/moc/login-actions/authenticate?x=1",
                                '<form id="kc-form-login" action="/realms/moc/dang-nhap?a=1&amp;b=2">'
                                '<input name="username"><input name="password" type="password"></form>')
                if "password" in form:
                    return Resp("http://localhost:8080/realms/moc/login-actions/authenticate?x=2",
                                '<form id="kc-otp-login-form" action="/realms/moc/otp"><input name="otp"></form>')
                state = self.query["state"][0]
                return Resp(f"http://localhost:8080/nghi-phep/dang-nhap#state={state}&code=ma-cap-quyen")

        fake = types.ModuleType("demo_ca_nhan")
        fake.Browser = lambda: types.SimpleNamespace(opener=Opener())
        fake.exchange = lambda client, uri, code, verifier: exchanged.append((client, uri, code, verifier)) or {
            "access_token": "tok-app"}
        with mock.patch.dict(sys.modules, {"demo_ca_nhan": fake}):
            self.assertEqual(demo.qt_login("truongbmktpm"), "tok-app")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(opened[0][0]).query)
        self.assertEqual(query["client_id"], ["app-nghi-phep"])
        self.assertEqual(query["response_mode"], ["fragment"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["redirect_uri"], ["http://localhost:8080/nghi-phep/dang-nhap"])
        self.assertEqual(opened[1][0], "http://localhost:8080/realms/moc/dang-nhap?a=1&b=2")
        self.assertEqual(opened[1][1], {"username": ["truongbmktpm"], "password": ["mat-khau-thu"]})
        self.assertEqual(opened[2][1], {"otp": ["khoa-thu:7"]})
        client, uri, code, verifier = exchanged[0]
        self.assertEqual((client, code), ("app-nghi-phep", "ma-cap-quyen"))
        self.assertEqual(uri, "http://localhost:8080/nghi-phep/dang-nhap")
        import base64
        import hashlib
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge"], [challenge])


QT_RANGE = {"denNgay": "x-moc-range"}


class Wiring(unittest.TestCase):
    def test_make_target_and_ci_step(self) -> None:
        self.assertIs(demo.DEMOS["quy-trinh"], demo.quy_trinh)
        make = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(make, r"\ndemo-quy-trinh: \$\(ENV_FILE\) ## .+\n\t@python3 scripts/demo\.py quy-trinh\n")
        phony = " ".join(re.findall(r"^\.PHONY:(.*(?:\\\n.*)*)", make, re.M))
        self.assertIn("demo-quy-trinh", phony.split())
        self.assertIn("\t@python3 -m unittest discover -s apps/nghi-phep/tests\n", make)
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        steps = re.findall(r"^      - name: (.+)$", ci, re.M)
        install = steps.index("Cắm ứng dụng bằng một lệnh (make demo-cai-ung-dung)")
        self.assertEqual(steps[install + 1], "Quy trình của ứng dụng qua lõi (make demo-quy-trinh)")
        block = ci.split("      - name: Quy trình của ứng dụng qua lõi (make demo-quy-trinh)\n", 1)[1]
        self.assertTrue(block.startswith("        if: matrix.phan == 'luong-chinh'\n"
                                         "        run: make demo-quy-trinh\n"))


if __name__ == "__main__":
    unittest.main()
