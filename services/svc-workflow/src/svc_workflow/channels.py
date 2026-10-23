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

"""Định tuyến thông báo đa kênh: ngoài chuông trên web, gửi thêm qua email (SMTP) và webhook khi được cấu hình.

Chuông trên web (``core.notifications`` + Centrifugo, notify.py) giữ nguyên. Lúc ghi thông báo, ``Notifier`` hỏi
``Router.route`` kênh ngoài nào cần gửi và ghi vào cột ``channels``; trigger CSDL tạo một dòng
``core.notification_deliveries`` ``pending`` cho mỗi kênh trong cùng giao dịch — hộp thư đi nằm trong CSDL như liên
thông (dispatch.py): thông báo đã lưu thì chắc chắn có dòng chờ gửi, dịch vụ dừng giữa chừng không làm mất thư. Vòng
nền ``Router.serve`` gửi các dòng đến hạn, ngoài luồng nghiệp vụ:

  - email: tới địa chỉ của người nhận trong danh bạ (``core.users``, đồng bộ từ Keycloak) đọc lúc gửi; chưa có email
    hoặc tài khoản đã khóa thì ``skipped``;
  - webhook: một tin cho mỗi sự kiện (gắn vào thông báo của người nhận đầu tiên theo id), dạng ``json``
    (``{"text": …}`` của incoming webhook Mattermost, Slack) hoặc ``ntfy`` (thân là chữ, tiêu đề và liên kết trong tham
    số). Webhook là kênh chung của cả đơn vị nên không ghi tên người, không ghi ý kiến, và văn bản hạn chế không bao giờ
    lên webhook — biết có văn bản là đã lộ (F3.7).

Câu chữ như chuông trên web (``apps/office/app/locales/vi.json``; test giữ hai bên khớp nhau). Lỗi tạm (mạng, máy chủ
thư bận, HTTP 5xx, 408, 429) thì thử lại sau 30 s·2^lần, tối đa ``MAX_ATTEMPTS`` lần rồi ``failed``; lỗi chắc chắn
(máy chủ thư từ chối người nhận hay nội dung bằng mã 5xx, HTTP 4xx khác) thì ``failed`` ngay. Gửi xong mà chưa kịp ghi
kết quả (dịch vụ dừng, Hasura lỗi) thì lần sau gửi lại: ít nhất một lần, không phải đúng một lần. Thư mang
``Message-ID`` cố định theo dòng nên hộp thư nhận ra bản lặp.

Nhật ký và ``last_error`` không có thông tin cá nhân hay bí mật (F4.4): chỉ id dòng, kênh, loại thông báo, số lần, tên
lớp lỗi và mã SMTP/HTTP — không địa chỉ email, không tên người, không URL webhook (khóa nằm trong đường dẫn). Lỗi của
smtplib mang nguyên địa chỉ người nhận, lỗi của httpx2 mang URL, nên không bao giờ ghi ``str(exc)``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import smtplib
import ssl
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx2

from .hasura import Actor, HasuraClient, HasuraError

log = logging.getLogger("svc_workflow")

ACTOR = "svc-workflow"
# Loại thông báo svc-workflow gửi (notify.py, sla.py, workflow.py, dispatch.py, ot.py)
KINDS = ("task.assigned", "task.overdue", "task.escalated", "document.issued", "document.processed",
         "document.overdue", "document.incoming", "ot.alarm")
SMTP_PORTS = {"starttls": 587, "ssl": 465, "none": 25}
WEBHOOK_FORMATS = ("json", "ntfy")
MAX_ATTEMPTS = 5
BATCH = 20
BACKOFF_FIRST = timedelta(seconds=30)
BACKOFF_MAX = timedelta(hours=1)

# Câu chữ của chuông trên web (vi.json: task.*, notify.*)
FORMS = {
    "vbden.chiDao": "Cho ý kiến chỉ đạo",
    "vbden.phanCong": "Phân công xử lý",
    "vbden.xuLy": "Xử lý văn bản",
    "vbdi.duyetPhong": "Duyệt dự thảo cấp phòng",
    "vbdi.duyetDonVi": "Duyệt và ký văn bản",
    "vbdi.chinhSua": "Sửa dự thảo theo ý kiến",
    "vbdi.phatHanh": "Cấp số và phát hành",
}
TITLES = {
    "task.assigned": "Việc mới: {task}",
    "task.overdue": "Quá hạn: {task}",
    "task.escalated": "{name} chưa làm xong «{task}» đúng hạn",
    "document.issued": "Đã phát hành văn bản {symbol}",
    "document.processed": "{name} đã báo kết quả xử lý",
    "document.overdue": "Văn bản quá hạn giải quyết ({due})",
    "ot.alarm": "Cảnh báo nhiệt độ {name}: {value} °C — đã có dự thảo báo cáo sự cố",
    "document.incoming": "Văn bản đến liên thông từ {name}",
}
SOMEONE = "Người được giao"
RESTRICTED = "Văn bản hạn chế"
NOTE = "Ý kiến: {note}"

DUE = """
query DueDeliveries($now: timestamptz!, $limit: Int!) {
  core_notification_deliveries(where: {status: {_eq: "pending"}, next_attempt_at: {_lte: $now}},
                               order_by: {id: asc}, limit: $limit) {
    id tenant_id channel attempts
    notification { kind document_id data created_at }
    recipient { full_name email enabled }
  }
}"""

# khóa lạc quan theo số lần: bản sao khác vừa ghi kết quả thì không ghi đè
FINISH = """
mutation DeliveryDone($id: bigint!, $attempts: Int!, $set: core_notification_deliveries_set_input!) {
  update_core_notification_deliveries(where: {id: {_eq: $id}, status: {_eq: "pending"}, attempts: {_eq: $attempts}},
                                      _set: $set) { affected_rows }
}"""


def backoff(attempts: int) -> timedelta:
    """Chờ trước lần thử sau: 30 giây, 1 phút, 2 phút… tối đa 1 giờ. attempts: số lần đã thử trước lần vừa lỗi."""
    return min(BACKOFF_FIRST * 2 ** min(max(attempts, 0), 10), BACKOFF_MAX)


# --- câu chữ ---------------------------------------------------------------------------------------------------------

def _number(value: Any) -> str:
    """Như fmtNumber của giao diện (vi-VN, tối đa hai chữ số thập phân): 36.5 → 36,5; 1234.5 → 1.234,5."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(n):
        return "—"
    whole, _, frac = f"{abs(n):,.2f}".partition(".")
    frac = frac.rstrip("0")
    text = whole.replace(",", ".") + ("," + frac if frac else "")
    return ("-" if n < 0 and text != "0" else "") + text


def _date(value: Any) -> str:
    """Như fmtDate của giao diện cho cột ngày: 2026-10-23 → 23/10/2026."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    return f"{m[3]}/{m[2]}/{m[1]}" if m else "—"


def _one_line(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class Text:
    title: str
    detail: str
    note: str


def describe(kind: str, data: dict[str, Any], *, names: bool = True) -> Text:
    """Câu thông báo như ``describeNotification`` của giao diện. names=False (webhook): không tên người, ý kiến."""
    d = data or {}
    form = str(d.get("form_key") or "")
    task = FORMS.get(form, form)
    doc = RESTRICTED if d.get("restricted") else " — ".join(str(d[k]) for k in ("symbol", "summary") if d.get(k))
    note = NOTE.format(note=d["note"]) if d.get("note") and names else ""

    def who(key: str) -> str:
        return str(d.get(key) or SOMEONE) if names else SOMEONE

    template = TITLES.get(kind)
    if kind in ("task.assigned", "task.overdue"):
        title = template.format(task=task)
    elif kind == "task.escalated":
        title = template.format(task=task, name=who("assignee_name"))
    elif kind == "document.issued":
        title = template.format(symbol=d.get("symbol") or "")
        doc = doc if d.get("restricted") else str(d.get("summary") or "")
    elif kind == "document.processed":
        title = template.format(name=who("by_name"))
    elif kind == "document.overdue":
        title = template.format(due=_date(d.get("due_on")))
    elif kind == "ot.alarm":
        title = template.format(name=d.get("name") or "", value=_number(d.get("temperature")))
    elif kind == "document.incoming":
        title = template.format(name=d.get("from_name") or "")
    else:
        title = kind
    return Text(_one_line(title), doc, note)


# --- cấu hình kênh ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    tls: str                    # starttls | ssl | none
    sender: str                 # MOC_SMTP_FROM, có thể kèm tên: "Signet <signet@don-vi.vn>"
    user: str = ""
    password: str = field(default="", repr=False)
    timeout_s: float = 15.0


@dataclass(frozen=True)
class WebhookConfig:
    url: str = field(repr=False)    # khóa của webhook nằm trong đường dẫn: không in, không ghi nhật ký
    format: str = "json"            # json | ntfy
    timeout_s: float = 10.0


class Skip(Exception):
    """Không gửi được và không thử lại: chưa có địa chỉ, kênh đã tắt, văn bản hạn chế trên webhook."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Failure(Exception):
    """Gửi lỗi. reason không có địa chỉ, URL; final: lỗi chắc chắn, thử lại cũng vậy."""

    def __init__(self, reason: str, *, final: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.final = final


def send_smtp(cfg: SmtpConfig, msg: EmailMessage) -> None:
    """Gửi một thư bằng smtplib (thư viện chuẩn) — chặn, nên Router gọi trong luồng riêng."""
    context = ssl.create_default_context()
    if cfg.tls == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout_s, context=context)
    else:
        client = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout_s)
    with client:
        if cfg.tls == "starttls":
            client.starttls(context=context)
        if cfg.user:
            client.login(cfg.user, cfg.password)
        client.send_message(msg)


def smtp_failure(exc: Exception) -> Failure:
    """Lỗi smtplib → Failure chỉ có tên lớp lỗi và mã SMTP (str(exc) của smtplib chứa địa chỉ người nhận)."""
    name = type(exc).__name__
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = sorted({code for code, _ in exc.recipients.values()})
        return Failure(f"{name} {','.join(map(str, codes))}".strip(), final=bool(codes) and min(codes) >= 500)
    if isinstance(exc, smtplib.SMTPResponseException):
        # 5xx khi nhận nội dung thư (DATA): máy chủ từ chối chính thư này. 5xx ở bước khác (đăng nhập, người gửi) là
        # cấu hình sai — thử lại vài lần trong khi người vận hành sửa
        return Failure(f"{name} {exc.smtp_code}", final=isinstance(exc, smtplib.SMTPDataError) and exc.smtp_code >= 500)
    return Failure(name)


class Router:
    """Chọn kênh ngoài cho từng thông báo lúc ghi, và gửi các dòng chờ ở vòng nền."""

    def __init__(self, hasura: HasuraClient, *, smtp: SmtpConfig | None = None, webhook: WebhookConfig | None = None,
                 public_url: str = "", email_kinds: tuple[str, ...] = (), webhook_kinds: tuple[str, ...] = (),
                 transport: httpx2.AsyncBaseTransport | None = None, clock: Callable[[], datetime] | None = None,
                 mailer: Callable[[SmtpConfig, EmailMessage], None] = send_smtp) -> None:
        self.hasura = hasura
        self.smtp = smtp
        self.webhook = webhook
        self.public_url = public_url.rstrip("/")
        self.email_kinds = frozenset(email_kinds)
        self.webhook_kinds = frozenset(webhook_kinds)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._mailer = mailer
        self._http = (httpx2.AsyncClient(timeout=webhook.timeout_s, transport=transport, follow_redirects=False)
                      if webhook else None)
        self._wake: asyncio.Event | None = None

    @classmethod
    def from_settings(cls, hasura: HasuraClient, settings: Any) -> Router | None:
        """None khi không cấu hình kênh nào: mọi thứ như trước, chỉ có chuông trên web."""
        smtp = (SmtpConfig(settings.smtp_host, settings.smtp_port or SMTP_PORTS[settings.smtp_tls], settings.smtp_tls,
                           settings.smtp_from, settings.smtp_user, settings.smtp_password)
                if settings.smtp_host else None)
        webhook = (WebhookConfig(settings.notify_webhook_url, settings.notify_webhook_format)
                   if settings.notify_webhook_url else None)
        if smtp is None and webhook is None:
            return None
        return cls(hasura, smtp=smtp, webhook=webhook, public_url=settings.public_url,
                   email_kinds=settings.notify_email_kinds, webhook_kinds=settings.notify_webhook_kinds)

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    # --- lúc ghi thông báo -----------------------------------------------------------------------------------------

    def route(self, kind: str, data: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
        """Đặt cột ``channels`` cho các dòng sắp ghi (đã xếp theo người nhận) → có kênh ngoài nào không.

        Email: mỗi người nhận một thư. Webhook: một tin cho cả sự kiện, gắn vào dòng đầu — dòng đó đã có (gọi lại
        Action, timer bắn lại) thì sự kiện đã lên webhook rồi."""
        email = self.smtp is not None and (not self.email_kinds or kind in self.email_kinds)
        hook = (self.webhook is not None and (not self.webhook_kinds or kind in self.webhook_kinds)
                and not (data or {}).get("restricted"))
        for i, row in enumerate(rows):
            channels = (["email"] if email else []) + (["webhook"] if hook and i == 0 else [])
            if channels:
                row["channels"] = channels
        return bool(rows) and (email or hook)

    def wake(self) -> None:
        """Có dòng chờ mới: vòng nền gửi ngay, không đợi hết chu kỳ."""
        if self._wake is not None:
            self._wake.set()

    # --- vòng nền ---------------------------------------------------------------------------------------------------

    async def serve(self, interval_s: float) -> None:
        self._wake = asyncio.Event()
        while True:
            self._wake.clear()
            count = 0
            try:
                count = await self.run()
                if count:
                    log.info(json.dumps({"event": "core.notification.deliveries_handled", "count": count}))
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
                error = f"{type(exc).__name__}: {exc}" if isinstance(exc, HasuraError) else type(exc).__name__
                log.warning(json.dumps({"event": "core.notification.deliveries_failed", "error": error},
                                       ensure_ascii=False))
            if count >= BATCH:
                continue                    # còn dòng đến hạn: lấy tiếp ngay
            try:
                await asyncio.wait_for(self._wake.wait(), interval_s)
            except TimeoutError:
                pass

    async def run(self) -> int:
        """Một lượt: gửi tối đa ``BATCH`` dòng đến hạn, mọi đơn vị → số dòng đã lấy."""
        now = self._clock()
        rows = (await self.hasura.as_system(DUE, {"now": now.isoformat(), "limit": BATCH}))[
            "core_notification_deliveries"]
        for row in rows:
            # một dòng lỗi không chặn dòng khác; dòng vẫn pending, lượt sau thử lại
            try:
                await self._deliver(row, now)
            except Exception as exc:  # noqa: BLE001
                log.warning(json.dumps({"event": "core.notification.delivery_error", "delivery_id": row.get("id"),
                                        "channel": row.get("channel"), "error": type(exc).__name__}))
        return len(rows)

    async def _deliver(self, row: dict[str, Any], now: datetime) -> str:
        note = row.get("notification") or {}
        kind, channel, attempts = note.get("kind", ""), row["channel"], int(row["attempts"])
        base = {"delivery_id": row["id"], "channel": channel, "kind": kind}
        try:
            if channel == "email":
                await self._email(row, note)
            elif channel == "webhook":
                await self._webhook(note)
            else:
                raise Skip("Kênh không còn được hỗ trợ")
        except Skip as skip:
            await self._finish(row, {"status": "skipped", "last_error": skip.reason})
            log.info(json.dumps({"event": "core.notification.delivery_skipped", **base, "reason": skip.reason},
                                ensure_ascii=False))
            return "skipped"
        except Failure as failure:
            tried = attempts + 1
            final = failure.final or tried >= MAX_ATTEMPTS
            change: dict[str, Any] = {"attempts": tried, "last_error": failure.reason[:200]}
            if final:
                change["status"] = "failed"
            else:
                change["next_attempt_at"] = (now + backoff(attempts)).isoformat()
            await self._finish(row, change)
            log.warning(json.dumps({"event": "core.notification.delivery_failed", **base, "attempts": tried,
                                    "error": failure.reason, "final": final}, ensure_ascii=False))
            return "failed" if final else "retry"
        await self._finish(row, {"status": "sent", "attempts": attempts + 1, "last_error": None,
                                 "sent_at": self._clock().isoformat()})
        log.info(json.dumps({"event": "core.notification.delivered", **base, "attempts": attempts + 1}))
        return "sent"

    async def _finish(self, row: dict[str, Any], change: dict[str, Any]) -> None:
        actor = Actor(ACTOR, uuid.UUID(row["tenant_id"]), "service", None)
        await self.hasura.as_service(actor, FINISH, {"id": row["id"], "attempts": row["attempts"], "set": change})

    def _link(self, note: dict[str, Any]) -> str:
        doc = note.get("document_id")
        return f"{self.public_url}/van-ban/{doc}" if doc and self.public_url else ""

    # --- email -------------------------------------------------------------------------------------------------------

    async def _email(self, row: dict[str, Any], note: dict[str, Any]) -> None:
        cfg = self.smtp
        if cfg is None:
            raise Skip("Kênh email đã tắt")
        person = row.get("recipient")
        if not person or not person.get("enabled"):
            raise Skip("Người nhận đã khóa hoặc không còn trong danh bạ")
        if not person.get("email"):
            raise Skip("Người nhận chưa có email trong danh bạ")
        try:
            msg = self.message(row["id"], note, person["full_name"], person["email"])
        except (ValueError, IndexError, TypeError) as exc:     # địa chỉ, tên không dựng được tiêu đề thư
            raise Skip("Địa chỉ email trong danh bạ không hợp lệ") from exc
        try:
            await asyncio.to_thread(self._mailer, cfg, msg)
        except (smtplib.SMTPException, OSError) as exc:        # OSError: không nối được, hết giờ, lỗi TLS
            raise smtp_failure(exc) from None

    def message(self, delivery_id: int, note: dict[str, Any], name: str, address: str) -> EmailMessage:
        cfg = self.smtp
        assert cfg is not None
        text = describe(note.get("kind", ""), note.get("data") or {})
        user, _, domain = address.strip().rpartition("@")
        if not user or not domain:
            raise ValueError("địa chỉ thiếu phần trước hoặc sau @")
        msg = EmailMessage()
        msg["Subject"] = f"[Signet] {text.title}"
        msg["From"] = cfg.sender
        msg["To"] = Address(display_name=_one_line(name), username=user, domain=domain)
        msg["Date"] = format_datetime(self._clock())
        # cố định theo dòng: gửi lại sau lỗi ghi kết quả thì hộp thư nhận ra bản lặp
        sender_domain = parseaddr(cfg.sender)[1].rpartition("@")[2] or "signet.invalid"
        msg["Message-ID"] = f"<signet.{delivery_id}.{_stamp(note.get('created_at'))}@{sender_domain}>"
        msg["Auto-Submitted"] = "auto-generated"   # RFC 3834: hộp thư không tự trả lời thư này
        lines = [f"Chào {name},", "", text.title, *(x for x in (text.detail, text.note) if x)]
        link = self._link(note)
        if link:
            lines += ["", f"Mở trên Signet: {link}"]
        lines += ["", "—", "Thư tự động của Signet, không trả lời thư này. Thông báo cũng có ở chuông trên trang web."]
        msg.set_content("\n".join(lines))
        return msg

    # --- webhook -----------------------------------------------------------------------------------------------------

    async def _webhook(self, note: dict[str, Any]) -> None:
        cfg, http = self.webhook, self._http
        if cfg is None or http is None:
            raise Skip("Kênh webhook đã tắt")
        data = note.get("data") or {}
        # CSDL gọt thông báo khi văn bản chuyển sang hạn chế (trigger notifications_restricted): xét lại lúc gửi
        if data.get("restricted"):
            raise Skip("Văn bản hạn chế không gửi lên webhook")
        text = describe(note.get("kind", ""), data, names=False)
        link = self._link(note)
        try:
            if cfg.format == "ntfy":
                # ntfy: thân là nội dung, tiêu đề và liên kết khi bấm đi trong tham số (tiêu đề HTTP chỉ nhận latin-1)
                params = {"title": f"Signet · {text.title}", **({"click": link} if link else {})}
                r = await http.post(_with_query(cfg.url, params), content=(text.detail or text.title).encode(),
                                    headers={"Content-Type": "text/plain; charset=utf-8"})
            else:
                body = "\n".join(x for x in (f"Signet · {text.title}", text.detail, link) if x)
                r = await http.post(cfg.url, json={"text": body})
        except httpx2.HTTPError as exc:
            raise Failure(type(exc).__name__) from None
        if 200 <= r.status_code < 300:
            return
        transient = r.status_code in (408, 429) or r.status_code >= 500
        raise Failure(f"HTTP {r.status_code}", final=not transient)


def _stamp(created_at: Any) -> str:
    try:
        return str(int(datetime.fromisoformat(str(created_at)).timestamp()))
    except ValueError:
        return "0"


def _with_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True) + list(params.items())
    return urlunsplit(parts._replace(query=urlencode(query)))
