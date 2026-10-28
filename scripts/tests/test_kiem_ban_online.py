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

"""Kiểm bản online qua HTTPS (scripts/kiem_ban_online.py, .github/workflows/ban-online.yml) trên một site giả, không
mạng: bản lành đạt cả năm mục; chứng chỉ sắp hết hạn, bắt tay TLS lỗi, TLS cũ, HTTP không chuyển sang HTTPS, trạng thái
down, lệch phiên bản, URL http:// hay :9080 của Keycloak, thiếu header bảo mật đều là lỗi; thành phần suy giảm chỉ
cảnh báo; mọi mục đều chạy và lỗi liệt kê hết; địa chỉ sai bị từ chối trước khi gọi mạng. Bản dev theo develop phải
dựng từ một commit đã nêu (--commit). Workflow chạy hằng ngày, chạy tay, chạy trên PR đổi chính nó, truyền thẻ phát
hành mới nhất cho kịch bản, đầu develop cùng các commit gộp trong 30 phút cho job bản dev. Lượt ngay sau Release
đợi bản online nâng tay (--wait-minutes, đồng hồ giả), lịch và chạy tay thì không đợi.
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import re
import ssl
import sys
import time
import unittest
from typing import Any
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "kiem_ban_online.py"
WORKFLOW = ROOT / ".github" / "workflows" / "ban-online.yml"

spec = importlib.util.spec_from_file_location("kiem_ban_online", SCRIPT)
kiem = importlib.util.module_from_spec(spec)
sys.modules["kiem_ban_online"] = kiem     # @dataclass tra module của lớp trong sys.modules
spec.loader.exec_module(kiem)

BASE = "https://signet.example"
HEAD = "2e1ba0c" + "4" * 33
OLDER = "88a3417" + "5" * 33
DAY = 86400


def not_after(days: float) -> str:
    return time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() + days * DAY))


class FakeSite:
    """Bản online lành; từng thuộc tính đổi được để giả một kiểu hỏng."""

    def __init__(self) -> None:
        self.cert: dict[str, Any] = {"notAfter": not_after(60),
                                     "issuer": ((("organizationName", "Let's Encrypt"),),)}
        self.tls = "TLSv1.3"
        self.handshake: OSError | None = None
        self.status: dict[str, Any] = {"status": "ok", "version": "1.2.0", "components": [
            {"id": "postgres", "label": "CSDL", "status": "ok"}, {"id": "ollama", "label": "Mô hình", "status": "off"}]}
        self.replies: dict[str, kiem.Reply] = {}
        self.unreachable: set[str] = set()
        self.calls: list[str] = []

    def certificate(self) -> tuple[dict[str, Any], str]:
        if self.handshake:
            raise self.handshake
        return self.cert, self.tls

    def get(self, url: str) -> kiem.Reply:
        self.calls.append(url)
        if url in self.unreachable:
            raise ConnectionRefusedError("connection refused")
        if url in self.replies:
            return self.replies[url]
        if url == "http://signet.example/":
            return kiem.Reply(301, {"location": f"{BASE}/"})
        if url == f"{BASE}/api/status":
            return kiem.Reply(200, {"content-type": "application/json"}, json.dumps(self.status).encode())
        if url == f"{BASE}/realms/moc/.well-known/openid-configuration":
            body = {"issuer": f"{BASE}/realms/moc",
                    "authorization_endpoint": f"{BASE}/realms/moc/protocol/openid-connect/auth",
                    "token_endpoint": f"{BASE}/realms/moc/protocol/openid-connect/token"}
            return kiem.Reply(200, {}, json.dumps(body).encode())
        if url == f"{BASE}/":
            return kiem.Reply(200, {"content-security-policy": "default-src 'self'",
                                    "x-content-type-options": "nosniff"})
        return kiem.Reply(404, {})


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.site = FakeSite()
        # Trên GitHub Actions lỗi in thành ::error::; các ca dưới kiểm cách in ở máy, trừ ca chú thích tự đặt lại biến
        env = mock.patch.dict("os.environ")
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GITHUB_ACTIONS", None)

    def run_check(self, *args: str, url: str = BASE) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = kiem.main([url, *args], site=lambda host, port: self.site)
        return code, out.getvalue()

    def assert_fails(self, item: str, why: str, *args: str) -> str:
        code, out = self.run_check("--version", "1.2.0", *args)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, rf"  - {re.escape(item)}: .*{why}")
        return out

    def test_healthy_site_passes_every_check(self) -> None:
        code, out = self.run_check("--version", "v1.2.0")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("✓ "), 5, out)
        self.assertIn("đạt mọi mục kiểm", out)
        self.assertIn("http://signet.example/", self.site.calls)

    def test_certificate_close_to_expiry(self) -> None:
        self.site.cert["notAfter"] = not_after(10)
        self.assert_fails("chứng chỉ", r"chỉ còn \d+ ngày \(dưới 14\)")
        code, _ = self.run_check("--min-days", "7")
        self.assertEqual(code, 0)

    def test_failed_handshake_and_old_tls(self) -> None:
        self.site.handshake = ssl.SSLCertVerificationError(1, "certificate has expired")
        self.assert_fails("chứng chỉ", "bắt tay TLS lỗi: .*expired")
        self.site.handshake = None
        self.site.tls = "TLSv1.1"
        self.assert_fails("chứng chỉ", "TLSv1.1, cần TLS 1.2")

    def test_http_must_redirect_to_https(self) -> None:
        cases = {"không chuyển": kiem.Reply(200, {}),
                 "chuyển sang http": kiem.Reply(301, {"location": "http://signet.example/"}),
                 "chuyển sang máy khác": kiem.Reply(302, {"location": "https://signet.example.evil/"})}
        for name, reply in cases.items():
            with self.subTest(name):
                self.site.replies["http://signet.example/"] = reply
                self.assert_fails("HTTP chuyển sang HTTPS", "cần chuyển về https://signet.example")

    def test_status_down_or_wrong_version(self) -> None:
        self.site.status["version"] = "1.1.0"
        self.assert_fails("/api/status", "chạy bản 1.1.0, bản phát hành mới nhất là 1.2.0")
        self.site.status.update(status="down", version="1.2.0")
        self.site.status["components"][0]["status"] = "down"
        self.assert_fails("/api/status", r"status down \(CSDL: down\)")
        self.site.replies[f"{BASE}/api/status"] = kiem.Reply(502, {}, b"<html>Bad gateway</html>")
        self.assert_fails("/api/status", "trả 502, không phải JSON")

    def test_dev_build_must_come_from_one_of_the_commits(self) -> None:
        for running in ("2e1ba0c", HEAD[:12], "0.1.0-328-g2e1ba0c", "88a3417"):
            with self.subTest(running):
                self.site.status["version"] = running
                code, out = self.run_check("--commit", HEAD, "--commit", OLDER)
                self.assertEqual(code, 0, out)
        for running in ("dev", "1.2.0", "2e1ba0d", "2e1ba0", None):
            with self.subTest(running):
                self.site.status["version"] = running
                code, out = self.run_check("--commit", HEAD, "--commit", OLDER)
                self.assertEqual(code, 1, out)
                self.assertIn(f"  - /api/status: chạy bản {running}, không dựng từ commit {HEAD[:12]} (hay 1 commit"
                              " trước đó)", out)

    def test_commit_is_a_full_sha_and_excludes_version(self) -> None:
        for args in (["--commit", HEAD[:7]], ["--commit", HEAD.upper()], ["--commit", HEAD, "--version", "1.2.0"]):
            with self.subTest(args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stop:
                    self.run_check(*args)
                self.assertEqual(stop.exception.code, 2)
        self.assertEqual(self.site.calls, [])

    def clock(self) -> tuple[list[float], mock.Mock]:
        """Đồng hồ giả cho --wait-minutes: time.sleep chỉ cộng giờ, không đợi thật."""
        now = [0.0]
        monotonic = mock.patch.object(kiem.time, "monotonic", side_effect=lambda: now[0])
        monotonic.start()
        self.addCleanup(monotonic.stop)
        sleep = mock.patch.object(kiem.time, "sleep", side_effect=lambda s: now.__setitem__(0, now[0] + s))
        self.addCleanup(sleep.stop)
        return now, sleep.start()

    def test_waits_for_the_upgrade_after_a_release(self) -> None:
        # nâng tay: lúc đầu bản cũ, giữa chừng Signet dừng (không gọi được, rồi 502 của proxy), sau đó lên bản mới
        status = f"{BASE}/api/status"
        self.site.status["version"] = "1.1.0"
        steps = [lambda: self.site.unreachable.add(status),
                 lambda: (self.site.unreachable.clear(), self.site.replies.update({status: kiem.Reply(502, {}, b"")})),
                 lambda: (self.site.replies.clear(), self.site.status.update(version="1.2.0"))]
        _, slept = self.clock()
        slept.side_effect = lambda s: steps.pop(0)()
        code, out = self.run_check("--version", "1.2.0", "--wait-minutes", "60")
        self.assertEqual(code, 0, out)
        self.assertEqual([c.args for c in slept.call_args_list], [(30,)] * 3)
        self.assertEqual(re.findall(r"… bản online đang chạy (\S+),", out), ["1.1.0", "None", "None"])
        self.assertIn("✓ /api/status: status ok, bản 1.2.0", out)

    def test_wait_for_a_dev_build_uses_the_commits(self) -> None:
        self.site.status["version"] = "88a3417"
        _, slept = self.clock()
        slept.side_effect = lambda s: self.site.status.update(version="0.1.0-329-g2e1ba0c")
        code, out = self.run_check("--commit", HEAD, "--wait-minutes", "20")
        self.assertEqual((code, slept.call_count), (0, 1), out)

    def test_wait_gives_up_and_the_status_check_fails(self) -> None:
        self.site.status["version"] = "1.1.0"
        _, slept = self.clock()
        code, out = self.run_check("--version", "1.2.0")       # lịch, chạy tay: không đợi
        self.assertEqual((code, slept.call_count), (1, 0), out)
        code, out = self.run_check("--version", "1.2.0", "--wait-minutes", "1")
        self.assertEqual((code, slept.call_count), (1, 2), out)     # hỏi lúc 0, 30, 60 giây
        self.assertIn("… đợi hết 1 phút, bản online vẫn chạy 1.1.0", out)
        self.assertIn("  - /api/status: chạy bản 1.1.0, bản phát hành mới nhất là 1.2.0", out)

    def test_wait_needs_a_target_and_a_non_negative_time(self) -> None:
        for args in (["--wait-minutes", "5"], ["--version", "1.2.0", "--wait-minutes", "-1"]):
            with self.subTest(args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stop:
                    self.run_check(*args)
                self.assertEqual(stop.exception.code, 2)
        self.assertEqual(self.site.calls, [])

    def test_degraded_component_only_warns(self) -> None:
        self.site.status["status"] = "degraded"
        self.site.status["components"][0]["status"] = "degraded"
        code, out = self.run_check("--version", "1.2.0")
        self.assertEqual(code, 0, out)
        self.assertIn("! /api/status: thành phần không ok: CSDL: degraded", out)
        self.assertNotIn("Mô hình", out)       # off theo cấu hình (chưa bật profile ai) không phải lỗi

    def test_keycloak_must_see_https_behind_the_proxy(self) -> None:
        realm = f"{BASE}/realms/moc"
        cases = [
            # MOC_PUBLIC_URL sai: mọi URL đều http://
            (r"issuer http://signet\.example/realms/moc", {
                "issuer": "http://signet.example/realms/moc",
                "authorization_endpoint": "http://signet.example/realms/moc/protocol/openid-connect/auth",
                "token_endpoint": "http://signet.example/realms/moc/protocol/openid-connect/token"}),
            # proxy không gửi X-Forwarded-Port (Cloudflare): issuer đúng, token_endpoint có :9080 (docs mục 6)
            (r"token_endpoint https://signet\.example:9080/", {
                "issuer": realm, "authorization_endpoint": f"{realm}/protocol/openid-connect/auth",
                "token_endpoint": "https://signet.example:9080/realms/moc/protocol/openid-connect/token"}),
        ]
        for why, body in cases:
            with self.subTest(why):
                self.site.replies[f"{realm}/.well-known/openid-configuration"] = kiem.Reply(
                    200, {}, json.dumps(body).encode())
                out = self.assert_fails("Keycloak sau proxy", why)
                self.assertNotIn("authorization_endpoint https://", out)    # URL đúng không bị kể là sai

    def test_security_headers_survive_the_proxy(self) -> None:
        self.site.replies[f"{BASE}/"] = kiem.Reply(200, {"x-content-type-options": "nosniff"})
        self.assert_fails("header bảo mật", "thiếu Content-Security-Policy$")
        self.site.replies[f"{BASE}/"] = kiem.Reply(200, {"content-security-policy": "default-src 'self'"})
        self.assert_fails("header bảo mật", "thiếu X-Content-Type-Options: nosniff")

    def test_every_check_runs_and_all_failures_are_listed(self) -> None:
        self.site.handshake = ssl.SSLCertVerificationError(1, "hostname mismatch")
        self.site.unreachable.add("http://signet.example/")
        self.site.status["version"] = "1.1.0"
        code, out = self.run_check("--version", "1.2.0")
        self.assertEqual(code, 1, out)
        self.assertIn("3 mục trượt", out)
        self.assertRegex(out, r"  - chứng chỉ: bắt tay TLS lỗi: .*hostname mismatch")
        self.assertIn("  - HTTP chuyển sang HTTPS: http://signet.example/ không trả lời: connection refused", out)
        self.assertIn("  - /api/status: chạy bản 1.1.0", out)
        self.assertEqual(out.count("✓ "), 2, out)     # Keycloak, header vẫn được kiểm

    def test_errors_and_warnings_become_annotations_on_github(self) -> None:
        self.site.status["version"] = "1.1.0"
        with mock.patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            code, out = self.run_check("--version", "1.2.0")
            self.assertEqual(code, 1)
            self.assertIn(f"::error::{BASE}: /api/status: chạy bản 1.1.0", out)
            self.assertNotIn("  - ", out)
            self.site.status.update(status="degraded", version="1.2.0")
            self.site.status["components"][0]["status"] = "degraded"
            code, out = self.run_check("--version", "1.2.0")
        self.assertEqual(code, 0, out)
        self.assertIn(f"::warning::{BASE}: /api/status: thành phần không ok: CSDL: degraded", out)

    def test_only_a_bare_https_origin_is_accepted(self) -> None:
        for url in ("http://signet.example", "https://signet.example/app", "signet.example", "https://"):
            with self.subTest(url), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stop:
                    self.run_check(url=url)
                self.assertEqual(stop.exception.code, 2)
        self.assertEqual(self.site.calls, [])

    def test_port_is_kept_in_the_expected_urls(self) -> None:
        seen: list[tuple[str, int]] = []

        def site(host: str, port: int) -> FakeSite:
            seen.append((host, port))
            return self.site

        with contextlib.redirect_stdout(io.StringIO()):
            kiem.main(["https://signet.example:8443/"], site=site)
        self.assertEqual(seen, [("signet.example", 8443)])
        self.assertIn("https://signet.example:8443/api/status", self.site.calls)


class WorkflowTest(unittest.TestCase):
    text = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_daily_by_hand_and_on_its_own_changes(self) -> None:
        self.assertRegex(self.text, r"(?m)^  schedule:\n    - cron: '[0-9]+ [0-9]+ \* \* \*'")
        self.assertRegex(self.text, r"(?m)^  workflow_dispatch:$")
        paths = re.search(r"(?m)^    paths:\n((?:      - .*\n)+)", self.text)
        self.assertIsNotNone(paths)
        listed = {line.strip()[2:] for line in paths[1].splitlines()}
        self.assertEqual(listed, {".github/workflows/ban-online.yml", "scripts/kiem_ban_online.py"})
        for path in listed:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_runs_right_after_a_successful_release(self) -> None:
        # Tên trong `workflows:` phải đúng `name:` của release.yml: đổi một bên mà quên bên kia thì lượt này im lặng
        self.assertRegex(self.text, r"(?m)^  workflow_run:\n    workflows: \[Release\]\n    types: \[completed\]$")
        release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertRegex(release, r"(?m)^name: Release$")
        self.assertIn("if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'",
                      self.text)
        # Bản phát hành do GITHUB_TOKEN tạo không gọi được workflow khác, `release:` sẽ không bao giờ chạy
        self.assertNotRegex(self.text, r"(?m)^  release:")

    def test_checks_the_latest_release_tag(self) -> None:
        self.assertIn('python3 scripts/kiem_ban_online.py "$ONLINE_URL" --version "${TAG#v}" --wait-minutes'
                      ' "$WAIT_MINUTES"', self.text)
        self.assertIn("permissions:\n  contents: read", self.text)

    def test_waits_for_the_upgrade_only_right_after_a_release(self) -> None:
        # lượt sau Release đợi bản online nâng tay; lịch, chạy tay kiểm ngay. Job phải sống lâu hơn lúc đợi
        job = self.text[self.text.index("\n  kiem:\n"):self.text.index("\n  kiem-dev:\n")]
        after = r"\$\{\{ github\.event_name == 'workflow_run' && (\d+) \|\| (\d+) \}\}"
        wait = re.search(rf"WAIT_MINUTES: {after}", job)
        timeout = re.search(rf"timeout-minutes: {after}", job)
        self.assertIsNotNone(wait, job)
        self.assertIsNotNone(timeout, job)
        self.assertEqual(wait[2], "0")
        self.assertGreaterEqual(int(timeout[1]), int(wait[1]) + 10)
        self.assertEqual(timeout[2], "10")

    def test_dev_job_checks_recent_develop_commits(self) -> None:
        job = self.text[self.text.index("\n  kiem-dev:\n"):]
        self.assertIn("if: github.event_name != 'workflow_run'\n", job)
        self.assertIn("git fetch -q --no-tags --depth 20 origin develop", job)
        self.assertIn("git log --first-parent -n 20 --format='%H %ct' FETCH_HEAD", job)
        self.assertIn('[ "$at" -ge $((now - 1800)) ] || break', job)
        self.assertIn('python3 scripts/kiem_ban_online.py "$DEV_URL" "${args[@]}"', job)
        self.assertIn("vars.MOC_DEV_URL || 'https://signet-dev.htechcs.com'", self.text)

    def test_checkout_is_pinned_like_ci(self) -> None:
        pin = re.compile(r"uses: actions/checkout@([0-9a-f]{40})")
        ci = pin.findall((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
        self.assertEqual(set(pin.findall(self.text)), {ci[0]})


if __name__ == "__main__":
    unittest.main()
