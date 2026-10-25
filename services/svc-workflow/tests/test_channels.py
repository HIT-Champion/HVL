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

"""Định tuyến thông báo đa kênh (channels.py): cấu hình, chọn kênh lúc ghi, gửi email qua một máy chủ SMTP nhỏ chạy
thật trên 127.0.0.1, webhook tới http.server cục bộ, thử lại có giới hạn, nhật ký không có thông tin cá nhân.

Địa chỉ email, tên người trong tệp này là giả lập (miền example.com dành cho ví dụ, RFC 2606).
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import email
import email.policy
import io
import json
import logging
import socketserver
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from conftest import DOC, LONG_AGO, SCHEMAS, TENANT, actor
from svc_workflow import channels
from svc_workflow.app import create_app
from svc_workflow.channels import (
    FORMS,
    KINDS,
    MAX_ATTEMPTS,
    NOTE,
    RESTRICTED,
    SOMEONE,
    TITLES,
    Router,
    SmtpConfig,
    WebhookConfig,
    describe,
    send_smtp,
)
from svc_workflow.config import ConfigError, Settings
from svc_workflow.notify import Notifier

EMAIL = "lethihoa@example.com"          # giả lập
NAME = "Lê Thị Hoa"                     # giả lập
SECRET = "bi-mat-webhook-77"            # phần khóa trong đường dẫn webhook (giả lập)
VI = Path(__file__).resolve().parents[3] / "apps" / "office" / "app" / "locales" / "vi.json"
ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": "bi-mat-action", "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_DIRECTORY_SYNC_INTERVAL_S": "0", "MOC_RECONCILE_INTERVAL_S": "0",
    "MOC_PROCESSES_DIR": "/khong-co", "MOC_SCHEMAS_DIR": str(SCHEMAS),
}
BRIEF = {"form_key": "vbdi.duyetPhong", "task_id": "t-1", "symbol": "12/TB-CNTT",
         "summary": "Thông báo lịch họp giao ban tháng 11"}


def run(coro):
    return asyncio.run(coro)


# --- cấu hình -----------------------------------------------------------------------------------------------------

def test_without_channel_settings_nothing_changes(hasura):
    settings = Settings.from_env(ENV)
    assert Router.from_settings(hasura, settings) is None
    app = create_app(settings, hasura=hasura, flowable=object(), directory=_NoDirectory())  # type: ignore[arg-type]
    assert app.state.router is None
    # thông báo ghi đúng như trước: không có cột channels
    run(Notifier(hasura).send(actor("director", "u-director"), ["u-staff-dt"], "task.assigned", "k", DOC, BRIEF))
    assert "channels" not in hasura.notifications[0]


@pytest.mark.parametrize(("tls", "port"), [("starttls", 587), ("ssl", 465), ("none", 25)])
def test_smtp_port_follows_tls_mode(hasura, tls, port):
    env = {**ENV, "MOC_SMTP_HOST": "mail.example.com", "MOC_SMTP_FROM": "Signet <signet@example.com>",
           "MOC_SMTP_TLS": tls, "MOC_SMTP_PORT": ""}
    router = Router.from_settings(hasura, Settings.from_env(env))
    assert router is not None and router.smtp is not None and router.webhook is None
    assert (router.smtp.port, router.smtp.tls) == (port, tls)
    custom = Router.from_settings(hasura, Settings.from_env({**env, "MOC_SMTP_PORT": "1025"}))
    assert custom is not None and custom.smtp is not None and custom.smtp.port == 1025


@pytest.mark.parametrize(("extra", "message"), [
    ({"MOC_SMTP_HOST": "mail.example.com"}, "MOC_SMTP_FROM"),
    ({"MOC_SMTP_HOST": "mail.example.com", "MOC_SMTP_FROM": "signet"}, "MOC_SMTP_FROM"),
    ({"MOC_SMTP_TLS": "tls"}, "MOC_SMTP_TLS"),
    ({"MOC_SMTP_PORT": "70000"}, "MOC_SMTP_PORT"),
    ({"MOC_NOTIFY_WEBHOOK_URL": f"ftp://chat.example.com/hooks/{SECRET}"}, "MOC_NOTIFY_WEBHOOK_URL"),
    ({"MOC_NOTIFY_WEBHOOK_FORMAT": "xml"}, "MOC_NOTIFY_WEBHOOK_FORMAT"),
    ({"MOC_NOTIFY_EMAIL_KINDS": "task.overdue, task.lost"}, "task.lost"),
    ({"MOC_NOTIFY_INTERVAL_S": "-1"}, "MOC_NOTIFY_INTERVAL_S"),
])
def test_wrong_channel_settings_stop_at_startup(extra, message):
    with pytest.raises(ConfigError, match=message) as err:
        Settings.from_env({**ENV, **extra})
    assert SECRET not in str(err.value)


def test_secrets_stay_out_of_repr():
    settings = Settings.from_env({**ENV, "MOC_SMTP_HOST": "mail.example.com", "MOC_SMTP_FROM": "signet@example.com",
                                  "MOC_SMTP_USER": "signet", "MOC_SMTP_PASSWORD": "mat-khau-smtp",
                                  "MOC_NOTIFY_WEBHOOK_URL": f"https://chat.example.com/hooks/{SECRET}",
                                  "MOC_NOTIFY_EMAIL_KINDS": "task.overdue,task.escalated"})
    assert settings.notify_email_kinds == ("task.overdue", "task.escalated")
    router = Router.from_settings(object(), settings)  # type: ignore[arg-type]
    assert router is not None
    for text in (repr(settings), repr(router.smtp), repr(router.webhook)):
        assert "mat-khau-smtp" not in text and SECRET not in text


# --- chọn kênh lúc ghi --------------------------------------------------------------------------------------------

def make_router(hasura: Any = None, **kwargs: Any) -> Router:
    kwargs.setdefault("smtp", SmtpConfig("127.0.0.1", 25, "none", "Signet <signet@example.com>"))
    return Router(hasura, public_url="https://signet.example.com", **kwargs)


def test_email_for_everyone_webhook_once_per_event():
    router = make_router(webhook=WebhookConfig("https://chat.example.com/hooks/x"))
    rows = [{"user_id": "a"}, {"user_id": "b"}]
    assert router.route("task.assigned", BRIEF, rows)
    assert [r["channels"] for r in rows] == [["email", "webhook"], ["email"]]


def test_restricted_documents_never_reach_the_webhook():
    router = make_router(webhook=WebhookConfig("https://chat.example.com/hooks/x"))
    rows = [{"user_id": "a"}]
    router.route("task.overdue", {"form_key": "vbden.xuLy", "restricted": True}, rows)
    assert rows[0]["channels"] == ["email"]


def test_kinds_route_each_channel():
    router = make_router(webhook=WebhookConfig("https://chat.example.com/hooks/x"),
                         email_kinds=("task.overdue",), webhook_kinds=("task.escalated", "ot.alarm"))
    rows = [{"user_id": "a"}]
    assert not router.route("task.assigned", BRIEF, rows) and "channels" not in rows[0]
    router.route("task.overdue", BRIEF, rows)
    assert rows[0]["channels"] == ["email"]
    rows = [{"user_id": "a"}]
    router.route("task.escalated", BRIEF, rows)
    assert rows[0]["channels"] == ["webhook"]


def test_notifier_writes_channels_and_wakes_the_loop(hasura):
    router = make_router()
    woken: list[bool] = []
    router.wake = lambda: woken.append(True)  # type: ignore[method-assign]
    n = Notifier(hasura, router=router)
    sent = run(n.send(actor("director", "u-director"), ["u-staff-dt", "u-manager-dt"], "task.assigned",
                      "task:t-1:assigned", DOC, BRIEF))
    assert sent == ["u-manager-dt", "u-staff-dt"] and woken == [True]
    assert [x["channels"] for x in hasura.notifications] == [["email"], ["email"]]
    # gọi lại cùng khóa: không ghi thêm, không đánh thức vòng nền
    assert run(n.send(actor("director", "u-director"), ["u-staff-dt"], "task.assigned", "task:t-1:assigned", DOC,
                      BRIEF)) == []
    assert woken == [True]


# --- câu chữ ------------------------------------------------------------------------------------------------------

def test_texts_match_the_web_bell():
    vi = json.loads(VI.read_text(encoding="utf-8"))
    forms = {f"{group}.{k}": v for group, items in vi["task"].items() for k, v in items.items()}
    assert FORMS == forms
    keys = {"task.assigned": "taskAssigned", "task.overdue": "taskOverdue", "task.escalated": "taskEscalated",
            "document.issued": "documentIssued", "document.processed": "documentProcessed",
            "document.overdue": "documentOverdue", "ot.alarm": "otAlarm", "document.incoming": "documentIncoming"}
    assert set(keys) == set(KINDS) == set(TITLES)
    for kind, key in keys.items():
        assert TITLES[kind] == vi["notify"][key], kind
    assert (SOMEONE, RESTRICTED, NOTE.replace("{note}", "{note}")) == (
        vi["notify"]["someone"], vi["notify"]["restricted"], vi["notify"]["note"])


def test_describe_like_the_bell_and_without_names_for_the_webhook():
    text = describe("task.escalated", {**BRIEF, "assignee_name": NAME, "note": "Gấp"})
    assert text.title == f"{NAME} chưa làm xong «Duyệt dự thảo cấp phòng» đúng hạn"
    assert text.detail == "12/TB-CNTT — Thông báo lịch họp giao ban tháng 11" and text.note == "Ý kiến: Gấp"
    shared = describe("task.escalated", {**BRIEF, "assignee_name": NAME, "note": "Gấp"}, names=False)
    assert NAME not in shared.title + shared.detail and shared.note == ""
    assert describe("task.overdue", {"form_key": "vbden.xuLy", "restricted": True}).detail == "Văn bản hạn chế"
    assert describe("document.overdue", {"due_on": "2026-10-23"}).title == "Văn bản quá hạn giải quyết (23/10/2026)"
    assert describe("ot.alarm", {"name": "Phòng máy\n1", "temperature": 1234.5}).title == (
        "Cảnh báo nhiệt độ Phòng máy 1: 1.234,5 °C — đã có dự thảo báo cáo sự cố")
    assert describe("document.issued", {"symbol": "05/TB", "summary": "Lịch họp"}).detail == "Lịch họp"


# --- gửi: Hasura giả của hộp thư đi --------------------------------------------------------------------------------

class Outbox:
    """Hasura giả cho vòng nền: trả dòng đến hạn (DueDeliveries), ghi kết quả (DeliveryDone) như quyền service."""

    def __init__(self, *rows: dict[str, Any]) -> None:
        self.rows = {r["id"]: r for r in rows}
        self.results: list[dict[str, Any]] = []

    async def as_system(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        assert "query DueDeliveries" in query
        now = datetime.fromisoformat(variables["now"])
        due = [r for r in self.rows.values() if r["status"] == "pending" and r["next_attempt_at"] <= now]
        keys = ("id", "tenant_id", "channel", "attempts", "notification", "recipient")
        return {"core_notification_deliveries": [{k: copy.deepcopy(r[k]) for k in keys}
                                                 for r in due[:variables["limit"]]]}

    async def as_service(self, actor_, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        assert "mutation DeliveryDone" in query
        row = self.rows[variables["id"]]
        affected = int(str(actor_.tenant_id) == row["tenant_id"] and row["status"] == "pending"
                       and row["attempts"] == variables["attempts"])
        if affected:
            change = dict(variables["set"])
            if "next_attempt_at" in change:
                change["next_attempt_at"] = datetime.fromisoformat(change["next_attempt_at"])
            row.update(change)
            self.results.append({"id": row["id"], **variables["set"]})
        return {"update_core_notification_deliveries": {"affected_rows": affected}}


def due(id_: int = 1, channel: str = "email", *, kind: str = "task.overdue", data: dict[str, Any] | None = None,
        recipient: dict[str, Any] | None = None, attempts: int = 0) -> dict[str, Any]:
    return {"id": id_, "tenant_id": str(TENANT), "channel": channel, "attempts": attempts, "status": "pending",
            "next_attempt_at": LONG_AGO,
            "notification": {"kind": kind, "document_id": DOC, "data": BRIEF if data is None else data,
                             "created_at": "2026-10-23T02:00:00+00:00"},
            "recipient": {"full_name": NAME, "email": EMAIL, "enabled": True} if recipient is None else recipient}


# --- máy chủ SMTP nhỏ trên 127.0.0.1 -----------------------------------------------------------------------------

class _Smtp(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _SmtpHandler)
        self.messages: list[tuple[str, list[str], bytes]] = []
        self.rcpt_reply = "250 2.1.5 OK"
        self.data_reply = "250 2.0.0 OK"


class _SmtpHandler(socketserver.StreamRequestHandler):
    """Đủ lệnh để smtplib gửi một thư không TLS: EHLO, MAIL, RCPT, DATA, RSET, QUIT."""

    def reply(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self) -> None:
        server: _Smtp = self.server  # type: ignore[assignment]
        self.reply("220 thu.example.com ESMTP")
        sender, rcpts, lines, in_data = "", [], [], False
        for raw in self.rfile:
            if in_data:
                if raw in (b".\r\n", b".\n"):
                    in_data = False
                    server.messages.append((sender, rcpts, b"".join(lines)))
                    self.reply(server.data_reply)
                else:
                    lines.append(raw[1:] if raw.startswith(b"..") else raw)
                continue
            cmd = raw.decode().strip()
            verb = cmd.split(" ", 1)[0].upper()
            if verb in ("EHLO", "HELO"):
                self.reply("250-thu.example.com")
                self.reply("250 8BITMIME")
            elif verb == "MAIL":
                sender = _addr(cmd)
                self.reply("250 2.1.0 OK")
            elif verb == "RCPT":
                code = server.rcpt_reply
                if code.startswith("2"):
                    rcpts.append(_addr(cmd))
                self.reply(code)
            elif verb == "DATA":
                self.reply("354 Kết thúc bằng một dấu chấm".encode("ascii", "replace").decode())
                in_data = True
            elif verb == "RSET":
                rcpts, lines = [], []
                self.reply("250 OK")
            elif verb == "QUIT":
                self.reply("221 Bye")
                return
            else:
                self.reply("502 5.5.2 Không hỗ trợ".encode("ascii", "replace").decode())


def _addr(cmd: str) -> str:
    return cmd[cmd.index("<") + 1:cmd.index(">")]


@pytest.fixture
def smtp_server() -> Iterator[_Smtp]:
    server = _Smtp()
    thread = threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def smtp_router(outbox: Outbox, server: _Smtp, clock, **kwargs: Any) -> Router:
    port = server.server_address[1]
    return make_router(outbox, smtp=SmtpConfig("127.0.0.1", port, "none", "Signet <signet@example.com>",
                                               timeout_s=5), clock=clock, **kwargs)


def test_email_reaches_the_server_with_link_and_fixed_message_id(smtp_server, clock):
    outbox = Outbox(due())
    assert run(smtp_router(outbox, smtp_server, clock).run()) == 1
    ((sender, rcpts, raw),) = smtp_server.messages
    assert sender == "signet@example.com" and rcpts == [EMAIL]
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    assert str(msg["Subject"]) == "[Signet] Quá hạn: Duyệt dự thảo cấp phòng"
    assert msg["To"].addresses[0].display_name == NAME and msg["Auto-Submitted"] == "auto-generated"
    assert msg["Message-ID"].startswith("<signet.1.") and msg["Message-ID"].endswith("@example.com>")
    body = msg.get_content()
    assert f"Chào {NAME}," in body and "12/TB-CNTT — Thông báo lịch họp giao ban tháng 11" in body
    assert f"https://signet.example.com/van-ban/{DOC}" in body
    assert outbox.results == [{"id": 1, "status": "sent", "attempts": 1, "last_error": None,
                               "sent_at": clock().isoformat()}]
    # lượt sau không còn gì
    assert run(smtp_router(outbox, smtp_server, clock).run()) == 0


def test_temporary_refusal_is_retried_with_backoff_then_fails(smtp_server, clock):
    smtp_server.rcpt_reply = "451 4.7.1 Thử lại sau".encode("ascii", "replace").decode()
    outbox = Outbox(due())
    router = smtp_router(outbox, smtp_server, clock)
    run(router.run())
    row = outbox.rows[1]
    assert (row["status"], row["attempts"], row["last_error"]) == ("pending", 1, "SMTPRecipientsRefused 451")
    assert row["next_attempt_at"] == clock() + timedelta(seconds=30)
    assert run(router.run()) == 0                            # chưa tới hạn thử lại
    waits = []
    for _ in range(MAX_ATTEMPTS - 1):
        waits.append(row["next_attempt_at"] - clock())
        clock.now = row["next_attempt_at"]
        run(router.run())
    assert waits == [timedelta(seconds=30 * 2 ** i) for i in range(MAX_ATTEMPTS - 1)]
    assert (row["status"], row["attempts"]) == ("failed", MAX_ATTEMPTS)
    assert smtp_server.messages == []


def test_permanent_refusal_fails_at_once(smtp_server, clock):
    smtp_server.rcpt_reply = f"550 5.1.1 <{EMAIL}>: Recipient address rejected"
    outbox = Outbox(due())
    run(smtp_router(outbox, smtp_server, clock).run())
    row = outbox.rows[1]
    assert (row["status"], row["attempts"], row["last_error"]) == ("failed", 1, "SMTPRecipientsRefused 550")


def test_unreachable_server_is_retried(clock):
    with socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler) as probe:
        port = probe.server_address[1]          # cổng vừa đóng: không ai nghe
    outbox = Outbox(due())
    router = make_router(outbox, smtp=SmtpConfig("127.0.0.1", port, "none", "signet@example.com", timeout_s=2),
                         clock=clock)
    run(router.run())
    row = outbox.rows[1]
    assert (row["status"], row["attempts"], row["last_error"]) == ("pending", 1, "ConnectionRefusedError")


@pytest.mark.parametrize(("recipient", "reason"), [
    ({"full_name": NAME, "email": None, "enabled": True}, "Người nhận chưa có email trong danh bạ"),
    ({"full_name": NAME, "email": EMAIL, "enabled": False}, "Người nhận đã khóa hoặc không còn trong danh bạ"),
    ({"full_name": NAME, "email": "khong-co-a-cong", "enabled": True}, "Địa chỉ email trong danh bạ không hợp lệ"),
])
def test_recipients_without_a_usable_address_are_skipped(smtp_server, clock, recipient, reason):
    outbox = Outbox(due(recipient=recipient))
    run(smtp_router(outbox, smtp_server, clock).run())
    assert outbox.results == [{"id": 1, "status": "skipped", "last_error": reason}]
    assert smtp_server.messages == []


def test_channel_turned_off_after_queueing_is_skipped(clock):
    outbox = Outbox(due(), due(2, "webhook"))
    run(make_router(outbox, smtp=None, clock=clock).run())
    assert [(r["id"], r["status"], r["last_error"]) for r in outbox.results] == [
        (1, "skipped", "Kênh email đã tắt"), (2, "skipped", "Kênh webhook đã tắt")]


class _FakeSmtp:
    """smtplib.SMTP / SMTP_SSL giả: ghi lại thứ tự lệnh để kiểm STARTTLS trước đăng nhập."""

    calls: list[tuple[Any, ...]] = []

    def __init__(self, host: str, port: int, timeout: float, context: Any = None) -> None:
        type(self).calls.append(("connect", type(self).__name__, host, port, context is not None))

    def __enter__(self) -> _FakeSmtp:
        return self

    def __exit__(self, *exc: object) -> None:
        type(self).calls.append(("quit",))

    def starttls(self, context: Any = None) -> None:
        type(self).calls.append(("starttls", context is not None))

    def login(self, user: str, password: str) -> None:
        type(self).calls.append(("login", user, password))

    def send_message(self, msg: Any) -> dict:
        type(self).calls.append(("send", msg["To"].addresses[0].addr_spec))
        return {}


class _FakeSsl(_FakeSmtp):
    pass


@pytest.mark.parametrize(("tls", "expected"), [
    ("starttls", [("connect", "_FakeSmtp", "mail.example.com", 587, False), ("starttls", True),
                  ("login", "signet", "mat-khau"), ("send", EMAIL), ("quit",)]),
    ("ssl", [("connect", "_FakeSsl", "mail.example.com", 465, True), ("login", "signet", "mat-khau"),
             ("send", EMAIL), ("quit",)]),
])
def test_starttls_and_ssl(monkeypatch, clock, tls, expected):
    _FakeSmtp.calls = []
    monkeypatch.setattr(channels.smtplib, "SMTP", _FakeSmtp)
    monkeypatch.setattr(channels.smtplib, "SMTP_SSL", _FakeSsl)
    cfg = SmtpConfig("mail.example.com", channels.SMTP_PORTS[tls], tls, "signet@example.com", "signet", "mat-khau")
    outbox = Outbox(due())
    run(make_router(outbox, smtp=cfg, clock=clock).run())
    assert _FakeSmtp.calls == expected and outbox.rows[1]["status"] == "sent"
    msg = make_router(smtp=cfg, clock=clock).message(1, due()["notification"], NAME, EMAIL)
    send_smtp(cfg, msg)                         # gọi thẳng như trong luồng riêng
    assert _FakeSmtp.calls[len(expected):] == expected


def test_plain_connection_never_carries_the_smtp_login(monkeypatch, clock):
    # MOC_SMTP_TLS=none mà có MOC_SMTP_USER: không nối, không đăng nhập (mật khẩu sẽ đi dạng rõ). Thư báo lỗi gửi như
    # mọi lỗi khác: last_error, dòng nhật ký delivery_failed, thử lại theo nhịp thường trong khi sửa cấu hình
    _FakeSmtp.calls = []
    monkeypatch.setattr(channels.smtplib, "SMTP", _FakeSmtp)
    monkeypatch.setattr(channels.smtplib, "SMTP_SSL", _FakeSsl)
    cfg = SmtpConfig("mail.example.com", 25, "none", "signet@example.com", "signet", "mat-khau-smtp")
    outbox = Outbox(due())
    router = make_router(outbox, smtp=cfg, clock=clock)
    with raw_log() as stream:
        run(router.run())
    assert _FakeSmtp.calls == []
    row = outbox.rows[1]
    assert (row["status"], row["attempts"], row["last_error"]) == ("pending", 1, channels.PLAIN_LOGIN)
    assert row["next_attempt_at"] == clock() + timedelta(seconds=30)
    (line,) = [json.loads(x) for x in stream.getvalue().splitlines()]
    assert (line["event"], line["error"], line["final"]) == ("core.notification.delivery_failed",
                                                              channels.PLAIN_LOGIN, False)
    assert "mat-khau-smtp" not in stream.getvalue()
    msg = router.message(1, due()["notification"], NAME, EMAIL)
    with pytest.raises(channels.Failure):
        send_smtp(cfg, msg)                     # gọi thẳng như trong luồng riêng: cũng không nối
    assert _FakeSmtp.calls == []
    # không có tài khoản thì none gửi như trước (relay nội bộ, Mailpit), không đăng nhập
    send_smtp(SmtpConfig("mail.example.com", 25, "none", "signet@example.com"), msg)
    assert _FakeSmtp.calls == [("connect", "_FakeSmtp", "mail.example.com", 25, False), ("send", EMAIL), ("quit",)]


def test_plain_login_settings_warn_once_at_startup(hasura, flowable):
    from fastapi.testclient import TestClient

    env = {**ENV, "MOC_SMTP_HOST": "mail.example.com", "MOC_SMTP_FROM": "signet@example.com", "MOC_SMTP_TLS": "none",
           "MOC_SMTP_USER": "nguoi-gui-thu", "MOC_SMTP_PASSWORD": "mat-khau-smtp", "MOC_NOTIFY_INTERVAL_S": "0",
           "MOC_SLA_POLL_INTERVAL_S": "0", "MOC_SUGGEST_POLL_INTERVAL_S": "0"}
    settings = Settings.from_env(env)           # không chặn khởi động: bản đang chạy vẫn lên, chỉ kênh email báo lỗi
    assert len(settings.warnings()) == 1
    with raw_log() as stream:
        app = create_app(settings, hasura=hasura, flowable=flowable, directory=_NoDirectory())  # type: ignore[arg-type]
        with TestClient(app):
            pass
    warned = [line["message"] for line in map(json.loads, stream.getvalue().splitlines())
              if line["event"] == "config.warning"]
    assert len(warned) == 1 and warned[0].startswith("MOC_SMTP_TLS=none mà có MOC_SMTP_USER")
    assert "mat-khau-smtp" not in stream.getvalue() and "nguoi-gui-thu" not in stream.getvalue()
    # không tài khoản, hoặc có mã hóa, hoặc kênh email tắt: không cảnh báo
    for extra in ({"MOC_SMTP_USER": ""}, {"MOC_SMTP_TLS": "starttls"}, {"MOC_SMTP_TLS": "ssl"}, {"MOC_SMTP_HOST": ""}):
        assert Settings.from_env({**env, **extra}).warnings() == []


# --- webhook tới http.server cục bộ --------------------------------------------------------------------------------

class _Hook(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _HookHandler)
        self.requests: list[tuple[str, dict[str, str], bytes]] = []
        self.status = 200


class _HookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 — tên do http.server đặt
        server: _Hook = self.server  # type: ignore[assignment]
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        server.requests.append((self.path, dict(self.headers), body))
        self.send_response(server.status)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def hook_server() -> Iterator[_Hook]:
    server = _Hook()
    thread = threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def hook_url(server: _Hook, query: str = "") -> str:
    return f"http://127.0.0.1:{server.server_address[1]}/hooks/{SECRET}{query}"


def test_webhook_json_has_text_without_names(hook_server, clock):
    data = {**BRIEF, "assignee_name": NAME, "note": "Ý kiến riêng"}
    outbox = Outbox(due(1, "webhook", kind="task.escalated", data=data))
    router = make_router(outbox, smtp=None, webhook=WebhookConfig(hook_url(hook_server)), clock=clock)
    run(router.run())
    run(router.aclose())
    ((path, headers, body),) = hook_server.requests
    assert path == f"/hooks/{SECRET}" and headers["Content-Type"] == "application/json"
    text = json.loads(body)["text"]
    assert text.splitlines() == ["Signet · Người được giao chưa làm xong «Duyệt dự thảo cấp phòng» đúng hạn",
                                 "12/TB-CNTT — Thông báo lịch họp giao ban tháng 11",
                                 f"https://signet.example.com/van-ban/{DOC}"]
    assert NAME not in text and "Ý kiến riêng" not in text
    assert outbox.rows[1]["status"] == "sent"


def test_webhook_ntfy_body_and_query(hook_server, clock):
    outbox = Outbox(due(1, "webhook", kind="task.assigned"))
    router = make_router(outbox, smtp=None, webhook=WebhookConfig(hook_url(hook_server, "?priority=high"), "ntfy"),
                         clock=clock)
    run(router.run())
    run(router.aclose())
    ((path, headers, body),) = hook_server.requests
    url = urlsplit(path)
    assert url.path == f"/hooks/{SECRET}" and headers["Content-Type"] == "text/plain; charset=utf-8"
    assert parse_qs(url.query) == {"priority": ["high"], "title": ["Signet · Việc mới: Duyệt dự thảo cấp phòng"],
                                   "click": [f"https://signet.example.com/van-ban/{DOC}"]}
    assert body.decode() == "12/TB-CNTT — Thông báo lịch họp giao ban tháng 11"


@pytest.mark.parametrize(("status", "outcome"), [(500, ("pending", "HTTP 500")), (429, ("pending", "HTTP 429")),
                                                 (404, ("failed", "HTTP 404")), (301, ("failed", "HTTP 301"))])
def test_webhook_status_decides_retry(hook_server, clock, status, outcome):
    hook_server.status = status
    outbox = Outbox(due(1, "webhook"))
    router = make_router(outbox, smtp=None, webhook=WebhookConfig(hook_url(hook_server)), clock=clock)
    run(router.run())
    run(router.aclose())
    row = outbox.rows[1]
    assert (row["status"], row["last_error"], row["attempts"]) == (*outcome, 1)


def test_restricted_on_the_way_is_not_posted(hook_server, clock):
    # văn bản chuyển sang hạn chế sau lúc xếp hàng: CSDL đã gọt thông báo, lúc gửi xét lại
    outbox = Outbox(due(1, "webhook", data={"form_key": "vbden.xuLy", "restricted": True}))
    router = make_router(outbox, smtp=None, webhook=WebhookConfig(hook_url(hook_server)), clock=clock)
    run(router.run())
    run(router.aclose())
    assert hook_server.requests == [] and outbox.rows[1]["status"] == "skipped"


# --- vòng nền ---------------------------------------------------------------------------------------------------

def test_serve_wakes_on_new_notifications(clock):
    class Counting(Outbox):
        runs = 0

        async def as_system(self, query, variables=None):
            Counting.runs += 1
            return await super().as_system(query, variables)

    router = make_router(Counting(), clock=clock)

    async def scenario() -> int:
        task = asyncio.create_task(router.serve(60))
        await asyncio.sleep(0.05)
        router.wake()
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return Counting.runs

    assert run(scenario()) == 2                     # lượt đầu, rồi lượt do wake — không đợi 60 giây


def test_one_broken_row_does_not_stop_the_others(smtp_server, clock):
    broken = due(1)
    broken["tenant_id"] = "khong-phai-uuid"
    outbox = Outbox(broken, due(2))
    run(smtp_router(outbox, smtp_server, clock).run())
    assert outbox.rows[2]["status"] == "sent" and outbox.rows[1]["status"] == "pending"


# --- nhật ký không có thông tin cá nhân, bí mật (F4.4) -----------------------------------------------------------

@contextlib.contextmanager
def raw_log() -> Iterator[io.StringIO]:
    """Dòng nhật ký đúng như mã ghi, chưa qua bộ che PII: gỡ tạm bộ lọc mà các lần create_app trước gắn vào logger."""
    log = logging.getLogger("svc_workflow")
    stream, saved = io.StringIO(), log.filters[:]
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    level = log.level
    log.filters.clear()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        log.removeHandler(handler)
        log.filters[:] = saved
        log.setLevel(level)


def test_failures_log_no_address_name_or_webhook_url(smtp_server, clock):
    smtp_server.rcpt_reply = f"550 5.1.1 <{EMAIL}>: Recipient address rejected"

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"không nối được {request.url}")

    outbox = Outbox(due(1, data={**BRIEF, "assignee_name": NAME}, kind="task.escalated"),
                    due(2, "webhook", data={**BRIEF, "assignee_name": NAME}, kind="task.escalated"),
                    due(3, recipient={"full_name": NAME, "email": None, "enabled": True}))
    router = smtp_router(outbox, smtp_server, clock,
                         webhook=WebhookConfig(f"https://chat.example.com/hooks/{SECRET}"),
                         transport=httpx2.MockTransport(refuse))
    with raw_log() as stream:
        run(router.run())
        run(router.aclose())
    text = stream.getvalue()
    events = [json.loads(line)["event"] for line in text.splitlines()]
    assert events == ["core.notification.delivery_failed", "core.notification.delivery_failed",
                      "core.notification.delivery_skipped"]
    for value in (EMAIL, NAME, SECRET, "chat.example.com"):
        assert value not in text
        assert all(value not in str(r.get("last_error")) for r in outbox.results)
    failed = [json.loads(line) for line in text.splitlines()][:2]
    assert [(f["channel"], f["error"], f["final"]) for f in failed] == [
        ("email", "SMTPRecipientsRefused 550", True), ("webhook", "ConnectError", False)]


def test_success_log_has_ids_only(smtp_server, clock):
    outbox = Outbox(due())
    with raw_log() as stream:
        run(smtp_router(outbox, smtp_server, clock).run())
    (line,) = stream.getvalue().splitlines()
    assert json.loads(line) == {"event": "core.notification.delivered", "delivery_id": 1, "channel": "email",
                                "kind": "task.overdue", "attempts": 1}


class _NoDirectory:
    async def aclose(self) -> None: ...


def test_app_starts_the_loop_only_when_configured(hasura, flowable, smtp_server):
    from fastapi.testclient import TestClient

    env = {**ENV, "MOC_SMTP_HOST": "127.0.0.1", "MOC_SMTP_PORT": str(smtp_server.server_address[1]),
           "MOC_SMTP_TLS": "none", "MOC_SMTP_FROM": "signet@example.com",
           "MOC_PUBLIC_URL": "https://signet.example.com/",
           "MOC_SLA_POLL_INTERVAL_S": "0", "MOC_SUGGEST_POLL_INTERVAL_S": "0"}
    app = create_app(Settings.from_env(env), hasura=hasura, flowable=flowable,
                     directory=_NoDirectory())  # type: ignore[arg-type]
    router = app.state.router
    assert isinstance(router, Router) and router.public_url == "https://signet.example.com"
    assert app.state.workflow.notifier.router is router
    with TestClient(app):
        pass                                        # vòng nền chạy rồi dừng cùng ứng dụng, không treo
    assert datetime.now(UTC) > LONG_AGO
