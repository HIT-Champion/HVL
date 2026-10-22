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

"""Đăng nhập kèm mã TOTP của kịch bản dòng lệnh (moc_env.user_login — smoke.py, demo.py, seed_documents.py): Keycloak 26
trả cùng một lỗi 400 cho mã đã dùng và mật khẩu sai, nên mã vừa bị dùng ngoài sổ (trình duyệt, e2e chạy từ thư mục mã
nguồn khi kịch bản chạy từ bản cài) phải được thử lại bằng mã kế tiếp. Không cần Docker, không đọc .env: moc_env thật nạp
từ bản chép kèm .env giả, đồng hồ và lời gọi mạng giả, sổ mã ở thư mục tạm. Chạy: python3 -m unittest discover -s
scripts/tests (make test)."""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import tempfile
import types
import unittest
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
REJECTED = '{"error":"invalid_grant","error_description":"Invalid user credentials"}'

env: Any = None
_tmp: tempfile.TemporaryDirectory | None = None


def setUpModule() -> None:
    """moc_env thật đọc .env ở thư mục gốc lúc nạp: nạp bản chép trong thư mục tạm có .env giả (tên module riêng)."""
    global env, _tmp
    _tmp = tempfile.TemporaryDirectory()
    root = pathlib.Path(_tmp.name)
    (root / "scripts").mkdir()
    shutil.copy(SCRIPTS / "moc_env.py", root / "scripts" / "moc_env.py")
    (root / ".env").write_text("MOC_PUBLIC_URL=https://moc.example.vn\nMOC_DEMO_PASSWORD=mat-khau-gia\n"
                               "MOC_DEMO_TOTP_SECRET=totp-demo-gia-tri\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("moc_env_dang_nhap", root / "scripts" / "moc_env.py")
    env = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(env)


def tearDownModule() -> None:
    if _tmp is not None:
        _tmp.cleanup()


class UserLoginRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = {name: getattr(env, name) for name in ("time", "call_json", "_OTP_USED")}
        self.addCleanup(lambda: [setattr(env, name, value) for name, value in self.saved.items()])
        # sổ mã riêng của test: không ghi vào sổ chung của máy (tempdir/.otp-used.json)
        env._OTP_USED = pathlib.Path(_tmp.name) / f"otp-{self.id()}.json"
        self.now = 1_790_000_000.0          # giây thứ 20 của một khoảng 30 giây
        env.time = types.SimpleNamespace(time=lambda: self.now, sleep=self.advance)
        self.calls: list[tuple[float, str]] = []

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def script(self, *outcomes: Any) -> None:
        """Lời gọi token thứ i: outcomes[i] là HTTPError thì ném, không thì trả về."""
        queue = list(outcomes)

        def call_json(method: str, url: str, body: Any = None, *, headers: Any = None, form: Any = None) -> Any:
            self.calls.append((self.now, form.get("otp", "")))
            outcome = queue.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        env.call_json = call_json

    def rejected(self) -> Exception:
        return env.HTTPError(400, REJECTED, "token")

    def valid_codes(self, at: float) -> set[str]:
        """Mã Keycloak nhận lúc at (nếu chưa dùng): khoảng hiện tại và một khoảng mỗi bên (otpPolicyLookAheadWindow)."""
        step = int(at // env.TOTP_PERIOD)
        return {env.totp_at(env.ENV["MOC_DEMO_TOTP_SECRET"], c) for c in (step - 1, step, step + 1)}

    def test_code_used_elsewhere_retries_with_the_next_code(self) -> None:
        ok = ({"access_token": "t"}, {})
        self.script(self.rejected(), ok)
        self.assertEqual(env.user_login("vanthu"), ok)
        self.assertEqual(len({code for _, code in self.calls}), 2, "mỗi lần thử phải là một mã khác")

    def test_all_valid_codes_used_elsewhere_waits_for_the_next_window(self) -> None:
        # e2e vừa đăng nhập văn thư liên tiếp: cả ba mã đang hiệu lực đã bị dùng ngoài sổ
        start = self.now
        ok = ({"access_token": "t"}, {})
        self.script(self.rejected(), self.rejected(), self.rejected(), ok)
        self.assertEqual(env.user_login("vanthu"), ok)
        codes = [code for _, code in self.calls]
        self.assertEqual(len(set(codes)), 4, "mỗi lần thử phải là một mã khác")
        self.assertEqual(set(codes[:3]), self.valid_codes(start), "ba lần đầu dùng hết các mã đang hiệu lực")
        for at, code in self.calls:
            self.assertIn(code, self.valid_codes(at), "mã gửi lúc Keycloak chưa nhận (chưa tới khoảng của nó)")
        # hai lần sai cách nhau dưới 1 giây thì Keycloak khóa tài khoản một phút
        self.assertTrue(all(b - a > 1 for (a, _), (b, _) in zip(self.calls, self.calls[1:])))

    def test_gives_up_after_four_codes(self) -> None:
        self.script(*(self.rejected() for _ in range(4)))
        with self.assertRaises(env.HTTPError) as caught:
            env.user_login("vanthu")
        self.assertEqual(caught.exception.status, 400)
        self.assertIn("bốn mã TOTP", str(caught.exception))
        self.assertEqual(len(self.calls), 4)

    def test_other_errors_are_not_retried(self) -> None:
        for error in (env.HTTPError(401, '{"error":"invalid_client"}', "token"),
                      env.HTTPError(400, '{"error":"unauthorized_client"}', "token")):
            with self.subTest(status=error.status):
                self.calls.clear()
                self.script(error)
                with self.assertRaises(env.HTTPError):
                    env.user_login("vanthu")
                self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
