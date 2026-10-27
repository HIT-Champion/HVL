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

"""Kênh thông báo người dùng tự bật (SMS, Zalo, #365): phần chung của svc-workflow, chạy cả khi tắt Văn phòng.

- Action ``myChannels``, ``setMyChannel`` (``/actions/channels/{name}``): mỗi người chỉ xem, bật, tắt kênh của chính
  mình; chỉ kênh bản cài đã cấu hình (``Router.personal``) mới hiện — chưa cấu hình kênh nào thì danh sách rỗng, giao
  diện không hiện mục Kênh thông báo. SMS bật được khi danh bạ có số điện thoại (thuộc
  tính ``phone_number`` của Keycloak do quản trị nhập, directory.py).
- Zalo phải liên kết trước: bật Zalo sinh một mã 8 ký tự hạn ``LINK_TTL``, người dùng nhắn mã đó cho bot Zalo của đơn
  vị; vòng ``listen`` đọc tin của bot (``getUpdates``, long polling — bot không được đặt webhook), tìm mã trên mọi
  đơn vị, ghi ``zalo_chat_id`` rồi trả lời trong Zalo. Tắt Zalo thì xóa chat_id: muốn bật lại phải liên kết lại.

Nhật ký không có số điện thoại, chat_id, mã liên kết hay nội dung tin nhắn (F4.4).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
import secrets
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, Self

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .channels import Failure, Router, ZaloBot
from .config import Settings
from .hasura import Actor, HasuraClient, HasuraError
from .parts import action_doc, action_error, error_doc

log = logging.getLogger("svc_workflow")

ACTOR = "svc-workflow"
ROLES = frozenset({"clerk", "staff", "manager", "director", "tenant_admin"})
# không có I, O, 0, 1 dễ đọc nhầm; 32 ký tự × 8 = 40 bit, khớp ràng buộc notification_subscriptions.link_code
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE = re.compile(r"[A-HJ-NP-Z2-9]{8}")
LINK_TTL = timedelta(minutes=15)
HINT_EVERY = timedelta(minutes=10)  # mỗi chat nhận lời nhắc cách dùng tối đa một lần trong khoảng này
POLL_S = 30                         # long polling của getUpdates
MAX_BACKOFF_S = 300.0

LINKED = "Đã liên kết Zalo với tài khoản Signet: thông báo sẽ gửi tới đây. Tắt ở mục Kênh thông báo trên Signet."
BAD_CODE = "Mã không đúng hoặc đã hết hạn. Tạo mã mới ở mục Kênh thông báo trên Signet rồi gửi lại."
HINT = ("Đây là bot thông báo của Signet. Để nhận thông báo qua Zalo, gửi mã liên kết 8 ký tự hiện ở mục Kênh thông "
        "báo trên Signet.")

MINE = """query Mine($user: String!) {
  core_users(where: {id: {_eq: $user}}) { phone }
  core_notification_subscriptions(where: {user_id: {_eq: $user}}) {
    channel enabled link_code link_expires_at
  }
}"""

SAVE = """mutation Save($row: core_notification_subscriptions_insert_input!) {
  insert_core_notification_subscriptions_one(object: $row, on_conflict: {
    constraint: notification_subscriptions_pkey, update_columns: [enabled, zalo_chat_id, link_code, link_expires_at]
  }) { channel }
}"""

# vòng đọc tin của bot: một bot cho cả bản cài, nên tìm mã trên mọi đơn vị (khóa quản trị, chỉ đọc)
FIND_CODE = """query FindCode($code: String!) {
  core_notification_subscriptions(where: {channel: {_eq: "zalo"}, link_code: {_eq: $code}}) {
    tenant_id user_id link_expires_at
  }
}"""

# ghi trong đơn vị của dòng tìm được, chỉ khi mã chưa đổi (người dùng vừa tạo mã mới, hay vừa tắt Zalo)
LINK = """mutation Link($user: String!, $code: String!, $chat: String!) {
  update_core_notification_subscriptions(
    where: {user_id: {_eq: $user}, channel: {_eq: "zalo"}, link_code: {_eq: $code}},
    _set: {enabled: true, zalo_chat_id: $chat, link_code: null, link_expires_at: null}
  ) { affected_rows }
}"""

CHANNELS_DOC = action_doc({
    "200": {"description": "Danh sách MyChannel: mỗi kênh cá nhân bản cài đã cấu hình một dòng "
                           "(db/metadata/actions.graphql)"},
    "400": error_doc("Sai định dạng Action, hoặc kênh chưa được cấu hình trên bản cài"),
    "401": error_doc("Thiếu hoặc sai X-Moc-Action-Secret: không phải Hasura gọi"),
    "403": error_doc("Vai trò không được dùng Action này"),
    "409": error_doc("Tài khoản chưa có trong danh bạ của đơn vị, hoặc chưa có số điện thoại để bật SMS"),
    "500": error_doc("Lỗi không mong đợi; câu trả về có mã yêu cầu để tra nhật ký"),
    "503": error_doc("Chưa gọi được CSDL, thử lại sau"),
})


class ChannelError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def masked(phone: str | None) -> str | None:
    """Số cho người dùng nhận ra là số của mình: mã nước và ba số cuối, vd +84••••••678."""
    return f"{phone[:3]}{'•' * (len(phone) - 6)}{phone[-3:]}" if phone else None


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


class Channels:
    """Kênh cá nhân: hai Action và vòng liên kết Zalo, theo khuôn ``parts.Part``."""

    def __init__(self, settings: Settings, hasura: HasuraClient, router: Router | None, *,
                 clock: Callable[[], datetime] | None = None, codes: Callable[[], str] = new_code) -> None:
        self.settings = settings
        self.hasura = hasura
        self.router = router
        self._clock = clock or (lambda: datetime.now(UTC))
        self._codes = codes
        self._hinted: dict[str, datetime] = {}     # chat_id → lần nhắc gần nhất (chỉ trong bộ nhớ)

    @classmethod
    def build(cls, settings: Settings, hasura: HasuraClient, router: Router | None) -> Self:
        return cls(settings, hasura, router)

    @property
    def personal(self) -> tuple[str, ...]:
        return self.router.personal if self.router is not None else ()

    def jobs(self) -> list[Coroutine[Any, Any, None]]:
        """Vòng liên kết Zalo, chỉ khi có bot."""
        bot = self.router.zalo_bot if self.router is not None and "zalo" in self.personal else None
        return [self.listen(bot)] if bot is not None else []

    async def aclose(self) -> None:
        """Bot Zalo, máy khách HTTP của SMS thuộc Router; app đóng Router sau các phần."""

    # --- Action ------------------------------------------------------------------------------------------------------

    async def mine(self, actor: Actor) -> list[dict[str, Any]]:
        if not self.personal:
            return []
        data = await self.hasura.as_service(actor, MINE, {"user": actor.user_id})
        users = data["core_users"]
        phone = users[0].get("phone") if users else None
        rows = {r["channel"]: r for r in data["core_notification_subscriptions"]}
        now = self._clock()
        result = []
        for channel in self.personal:
            row = rows.get(channel) or {}
            item: dict[str, Any] = {"channel": channel, "enabled": bool(row.get("enabled")), "phone": None,
                                    "link_code": None, "link_expires_at": None, "bot_url": None}
            if channel == "sms":
                item["phone"] = masked(phone)
            else:
                expires = _time(row.get("link_expires_at"))
                if row.get("link_code") and expires is not None and expires > now:
                    item["link_code"], item["link_expires_at"] = row["link_code"], expires.isoformat()
                zalo = self.router.zalo if self.router is not None else None
                item["bot_url"] = (zalo.bot_url if zalo else "") or None
            result.append(item)
        return result

    async def set(self, actor: Actor, channel: str, enabled: bool) -> list[dict[str, Any]]:
        if channel not in self.personal:
            raise ChannelError(400, "channel_off", "Bản cài này chưa bật kênh thông báo đó")
        data = await self.hasura.as_service(actor, MINE, {"user": actor.user_id})
        if not data["core_users"]:
            raise ChannelError(409, "not_synced", "Tài khoản chưa có trong danh bạ của đơn vị, thử lại sau ít phút")
        current = next((r for r in data["core_notification_subscriptions"] if r["channel"] == channel), {})
        row: dict[str, Any] = {"user_id": actor.user_id, "channel": channel, "enabled": False, "zalo_chat_id": None,
                               "link_code": None, "link_expires_at": None}
        if channel == "sms":
            if enabled and not data["core_users"][0].get("phone"):
                raise ChannelError(409, "no_phone", "Danh bạ chưa có số điện thoại của tài khoản này: nhờ quản trị "
                                                    "thêm rồi bật lại")
            row["enabled"] = enabled
            await self.hasura.as_service(actor, SAVE, {"row": row})
        elif enabled and current.get("enabled"):
            pass                            # đã liên kết: giữ nguyên chat_id
        elif enabled:
            await self._new_code(actor, row)
        else:
            await self.hasura.as_service(actor, SAVE, {"row": row})
        log.info(json.dumps({"event": "core.channel.set", "channel": channel, "enabled": enabled,
                             "user_id": actor.user_id, "tenant_id": str(actor.tenant_id),
                             "request_id": actor.request_id}))
        return await self.mine(actor)

    async def _new_code(self, actor: Actor, row: dict[str, Any]) -> None:
        """Mã liên kết mới (thay mã cũ); trùng mã đang dùng ở đâu đó (chỉ mục duy nhất) thì sinh lại."""
        for attempt in range(3):
            row = {**row, "link_code": self._codes(), "link_expires_at": (self._clock() + LINK_TTL).isoformat()}
            try:
                await self.hasura.as_service(actor, SAVE, {"row": row})
                return
            except HasuraError as exc:
                if exc.code != "constraint-violation" or attempt == 2:
                    raise

    def install(self, app: FastAPI) -> None:
        settings = self.settings

        @app.post("/actions/channels/{name}",
                     summary="Kênh thông báo của chính người gọi (SMS, Zalo): myChannels, setMyChannel",
                     openapi_extra=CHANNELS_DOC)
        async def channels_action(name: str, request: Request) -> JSONResponse:
            given = request.headers.get("x-moc-action-secret", "")
            if not hmac.compare_digest(given.encode(), settings.action_secret.encode()):
                return action_error(401, "unauthorized", "Chỉ Hasura được gọi")
            try:
                body: dict[str, Any] = await request.json()
                session = {k.lower(): v for k, v in (body.get("session_variables") or {}).items()}
                payload = body.get("input") or {}
                if (body.get("action") or {}).get("name") != name:
                    return action_error(400, "bad_request", "Tên Action không khớp đường dẫn")
                actor = Actor.from_session(session, request.state.request_id)
            except (ValueError, KeyError, TypeError, AttributeError):
                return action_error(400, "bad_request", "Yêu cầu không đúng định dạng Action")
            if actor.role not in ROLES:
                return action_error(403, "forbidden", "Vai trò không được dùng thao tác này")
            try:
                if name == "myChannels":
                    result = await self.mine(actor)
                elif name == "setMyChannel":
                    channel, enabled = payload.get("channel"), payload.get("enabled")
                    if not isinstance(channel, str) or not isinstance(enabled, bool):
                        return action_error(400, "bad_request", "Thiếu kênh hoặc trạng thái bật, tắt")
                    result = await self.set(actor, channel, enabled)
                else:
                    return action_error(400, "bad_request", "Không có Action này")
            except ChannelError as exc:
                return action_error(exc.status, exc.code, exc.message)
            except HasuraError as exc:
                log.warning(json.dumps({"event": "core.channel.action_failed", "action": name, "code": exc.code,
                                        "request_id": actor.request_id}))
                return action_error(503, "unavailable", "Chưa ghi được, thử lại sau")
            except Exception:  # noqa: BLE001 — không để lộ chi tiết nội bộ cho client
                log.exception(json.dumps({"event": "core.channel.action_failed", "action": name,
                                          "request_id": actor.request_id}))
                return action_error(500, "internal",
                                    "Lỗi không mong đợi; đã ghi nhật ký với mã " + (actor.request_id or "?"))
            return JSONResponse(result)

    # --- liên kết Zalo -----------------------------------------------------------------------------------------------

    async def listen(self, bot: ZaloBot) -> None:
        """Đọc tin nhắn cho bot suốt vòng đời app; lỗi (token sai, bot có webhook, mất mạng) thì chờ lâu dần."""
        delay = 2.0
        while True:
            try:
                updates = await bot.updates(POLL_S)
                delay = 2.0
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
                error = exc.reason if isinstance(exc, Failure) else type(exc).__name__
                log.warning(json.dumps({"event": "core.channel.zalo_poll_failed", "error": error}))
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_BACKOFF_S)
                continue
            for update in updates:
                try:
                    await self.link(bot, update)
                except Exception as exc:  # noqa: BLE001 — một tin lỗi không chặn tin khác
                    error = exc.reason if isinstance(exc, Failure) else type(exc).__name__
                    log.warning(json.dumps({"event": "core.channel.zalo_link_failed", "error": error}))

    async def _hint(self, bot: ZaloBot, chat_id: str) -> bool:
        """Nhắc cách dùng, mỗi chat tối đa một lần trong HINT_EVERY: tin rác không làm bot trả lời dồn."""
        now = self._clock()
        last = self._hinted.get(chat_id)
        if last is not None and now - last < HINT_EVERY:
            return False
        if len(self._hinted) >= 1000:                 # giữ bộ nhớ có hạn: bỏ các chat đã qua khoảng chờ
            self._hinted = {k: v for k, v in self._hinted.items() if now - v < HINT_EVERY}
        self._hinted[chat_id] = now
        await bot.send(chat_id, HINT)
        return True

    async def link(self, bot: ZaloBot, update: dict[str, Any]) -> str:
        """Một tin nhắn cho bot → ``linked`` | ``bad_code`` | ``hint`` | ``ignored`` (đã trả lời trong Zalo)."""
        message = update.get("message") if update.get("event_name") == "message.text.received" else None
        chat = (message or {}).get("chat") or {}
        chat_id, text = str(chat.get("id") or ""), (message or {}).get("text")
        # chỉ trò chuyện riêng với bot (thiếu chat_type cũng bỏ qua): mã đọc trong nhóm thì người khác cũng thấy;
        # chat_id dài hơn cột thì bỏ qua
        if not 0 < len(chat_id) <= 64 or not isinstance(text, str) or chat.get("chat_type") != "PRIVATE":
            return "ignored"
        code = re.sub(r"[\s-]", "", text).upper()
        if not CODE.fullmatch(code):
            return "hint" if await self._hint(bot, chat_id) else "ignored"
        found = (await self.hasura.as_system(FIND_CODE, {"code": code}))["core_notification_subscriptions"]
        expires = _time(found[0].get("link_expires_at")) if found else None
        linked = 0
        if found and expires is not None and expires > self._clock():
            actor = Actor(ACTOR, uuid.UUID(found[0]["tenant_id"]), "service", None)
            done = await self.hasura.as_service(actor, LINK, {"user": found[0]["user_id"], "code": code,
                                                              "chat": chat_id})
            linked = done["update_core_notification_subscriptions"]["affected_rows"]
        if not linked:
            await bot.send(chat_id, BAD_CODE)
            return "bad_code"
        log.info(json.dumps({"event": "core.channel.zalo_linked", "user_id": found[0]["user_id"],
                             "tenant_id": found[0]["tenant_id"]}))
        await bot.send(chat_id, LINKED)
        return "linked"
