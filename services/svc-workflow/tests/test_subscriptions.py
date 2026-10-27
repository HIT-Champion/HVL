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

"""Kênh cá nhân SMS, Zalo (subscriptions.py, #365): Action myChannels, setMyChannel; liên kết Zalo bằng mã dùng một
lần qua tin nhắn cho bot; phần này chạy cả khi tắt Văn phòng; nhật ký không có số điện thoại, chat_id, mã.

Số điện thoại, chat_id, token trong tệp này là giả lập.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import OTHER, SCHEMAS, TENANT, Clock, actor
from svc_workflow import subscriptions
from svc_workflow.app import create_app
from svc_workflow.channels import Failure, Router, SmsConfig, ZaloConfig
from svc_workflow.config import Settings
from svc_workflow.hasura import HasuraError
from svc_workflow.subscriptions import BAD_CODE, HINT, LINK_TTL, LINKED, Channels
from test_channels import raw_log

SECRET = "bi-mat-action"
PHONE = "+84912345678"                  # giả lập
CHAT = "zl-chat-5566"                   # giả lập
TOKEN = "1234567890:token-bot-gia-lap"  # giả lập
ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": SECRET, "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_DIRECTORY_SYNC_INTERVAL_S": "0", "MOC_RECONCILE_INTERVAL_S": "0",
    "MOC_PROCESSES_DIR": "/khong-co", "MOC_SCHEMAS_DIR": str(SCHEMAS), "MOC_NOTIFY_INTERVAL_S": "0",
    "MOC_SLA_POLL_INTERVAL_S": "0", "MOC_SUGGEST_POLL_INTERVAL_S": "0",
}


def run(coro):
    return asyncio.run(coro)


class Store:
    """Hasura giả cho core.users, core.notification_subscriptions: quyền service lọc theo đơn vị của phiên."""

    def __init__(self) -> None:
        self.users: dict[tuple[str, str], dict[str, Any]] = {
            (str(TENANT), "u-1"): {"phone": PHONE}, (str(TENANT), "u-2"): {"phone": None},
            (str(OTHER), "u-9"): {"phone": None},
        }
        self.subs: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.collide = 0                # số lần SAVE kế tiếp có mã liên kết bị trùng chỉ mục duy nhất
        self.calls: list[str] = []

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None: ...

    def _rows(self, tenant: str, user: str) -> list[dict[str, Any]]:
        return [dict(r, channel=c) for (t, u, c), r in self.subs.items() if (t, u) == (tenant, user)]

    async def as_service(self, actor_, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        v, tenant = variables or {}, str(actor_.tenant_id)
        assert actor_.user_id
        if "query Mine" in query:
            self.calls.append("Mine")
            user = self.users.get((tenant, v["user"]))
            return {"core_users": [dict(user)] if user else [],
                    "core_notification_subscriptions": self._rows(tenant, v["user"])}
        if "mutation Save" in query:
            self.calls.append("Save")
            row = dict(v["row"])
            if row.get("link_code") and self.collide:
                self.collide -= 1
                raise HasuraError("Uniqueness violation", "constraint-violation")
            key = (tenant, row.pop("user_id"), row.pop("channel"))
            assert row["enabled"] is False or key[2] == "sms" or row["zalo_chat_id"]   # ràng buộc ..._linked
            self.subs[key] = row
            return {"insert_core_notification_subscriptions_one": {"channel": key[2]}}
        if "mutation Link" in query:
            self.calls.append("Link")
            key = (tenant, v["user"], "zalo")
            row = self.subs.get(key)
            if row is None or row.get("link_code") != v["code"]:
                return {"update_core_notification_subscriptions": {"affected_rows": 0}}
            row.update(enabled=True, zalo_chat_id=v["chat"], link_code=None, link_expires_at=None)
            return {"update_core_notification_subscriptions": {"affected_rows": 1}}
        raise AssertionError(query)

    async def as_system(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        assert "query FindCode" in query
        self.calls.append("FindCode")
        found = [{"tenant_id": t, "user_id": u, "link_expires_at": r["link_expires_at"]}
                 for (t, u, c), r in self.subs.items() if c == "zalo" and r.get("link_code") == variables["code"]]
        return {"core_notification_subscriptions": found}


class Bot:
    """Bot Zalo giả: ghi tin đã gửi, trả tin người dùng nhắn theo hàng đợi."""

    def __init__(self, *batches: list[dict[str, Any]] | Exception) -> None:
        self.batches = list(batches)
        self.sent: list[tuple[str, str]] = []

    async def send(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))

    async def updates(self, wait_s: int = 30) -> list[dict[str, Any]]:
        item = self.batches.pop(0) if self.batches else []
        if isinstance(item, Exception):
            raise item
        return item


def message(text: str, chat_id: str = CHAT, chat_type: str = "PRIVATE") -> dict[str, Any]:
    return {"event_name": "message.text.received",
            "message": {"text": text, "from": {"id": "zl-user"}, "chat": {"id": chat_id, "chat_type": chat_type}}}


def make(store: Store, clock: Clock, *, sms: bool = True, zalo: bool = True, codes: list[str] | None = None,
         bot_url: str = "https://zalo.me/signet-bot") -> Channels:
    router = Router(store, sms=SmsConfig("http://sms", "u", "p") if sms else None,  # type: ignore[arg-type]
                    zalo=ZaloConfig(TOKEN, bot_url) if zalo else None)
    pool = iter(codes or ["ABCD2345", "EFGH6789", "JKMN2345"])
    return Channels(Settings.from_env(ENV), store, router, clock=clock, codes=lambda: next(pool))  # type: ignore


def by_channel(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {x["channel"]: x for x in items}


# --- Action ----------------------------------------------------------------------------------------------------------

def test_only_configured_channels_are_listed(clock):
    store = Store()
    me = actor("staff", "u-1")
    assert [x["channel"] for x in run(make(store, clock).mine(me))] == ["sms", "zalo"]
    assert [x["channel"] for x in run(make(store, clock, sms=False).mine(me))] == ["zalo"]
    (sms,) = run(make(store, clock, zalo=False).mine(me))
    assert sms == {"channel": "sms", "enabled": False, "phone": "+84••••••678", "link_code": None,
                   "link_expires_at": None, "bot_url": None}


def test_sms_needs_a_phone_and_a_synced_account(clock):
    store = Store()
    channels = make(store, clock)
    with pytest.raises(subscriptions.ChannelError) as err:
        run(channels.set(actor("staff", "u-2"), "sms", True))
    assert (err.value.status, err.value.code) == (409, "no_phone")
    with pytest.raises(subscriptions.ChannelError) as err:
        run(channels.set(actor("staff", "u-chua-dong-bo"), "sms", True))
    assert (err.value.status, err.value.code) == (409, "not_synced")
    # tắt thì không cần số
    assert by_channel(run(channels.set(actor("staff", "u-2"), "sms", False)))["sms"]["enabled"] is False
    assert by_channel(run(channels.set(actor("staff", "u-1"), "sms", True)))["sms"]["enabled"] is True
    assert store.subs[(str(TENANT), "u-1", "sms")]["enabled"] is True


def test_unconfigured_channel_is_refused(clock):
    with pytest.raises(subscriptions.ChannelError) as err:
        run(make(Store(), clock, zalo=False).set(actor("staff", "u-1"), "zalo", True))
    assert (err.value.status, err.value.code) == (400, "channel_off")


def test_turning_zalo_on_shows_a_code_until_it_expires(clock):
    store = Store()
    channels = make(store, clock)
    zalo = by_channel(run(channels.set(actor("staff", "u-1"), "zalo", True)))["zalo"]
    assert zalo == {"channel": "zalo", "enabled": False, "phone": None, "link_code": "ABCD2345",
                    "link_expires_at": (clock.now + LINK_TTL).isoformat(), "bot_url": "https://zalo.me/signet-bot"}
    # bấm lại: mã mới thay mã cũ
    assert by_channel(run(channels.set(actor("staff", "u-1"), "zalo", True)))["zalo"]["link_code"] == "EFGH6789"
    clock.tick(minutes=16)
    assert by_channel(run(channels.mine(actor("staff", "u-1"))))["zalo"]["link_code"] is None


def test_a_code_already_in_use_is_drawn_again(clock):
    store = Store()
    store.collide = 1
    zalo = by_channel(run(make(store, clock).set(actor("staff", "u-1"), "zalo", True)))["zalo"]
    assert zalo["link_code"] == "EFGH6789"
    store.collide = 3
    with pytest.raises(HasuraError):
        run(make(store, clock).set(actor("staff", "u-1"), "zalo", True))


# --- liên kết qua tin nhắn cho bot -----------------------------------------------------------------------------------

def test_messaging_the_code_links_zalo_once(clock):
    store = Store()
    channels = make(store, clock)
    run(channels.set(actor("staff", "u-1"), "zalo", True))
    bot = Bot()
    assert run(channels.link(bot, message(" abcd-2345 "))) == "linked"
    row = store.subs[(str(TENANT), "u-1", "zalo")]
    assert row == {"enabled": True, "zalo_chat_id": CHAT, "link_code": None, "link_expires_at": None}
    zalo = by_channel(run(channels.mine(actor("staff", "u-1"))))["zalo"]
    assert (zalo["enabled"], zalo["link_code"]) == (True, None)
    # mã đã dùng
    assert run(channels.link(bot, message("ABCD2345", "zl-chat-khac"))) == "bad_code"
    assert bot.sent == [(CHAT, LINKED), ("zl-chat-khac", BAD_CODE)]
    assert row["zalo_chat_id"] == CHAT
    # bật lại khi đã liên kết: giữ chat_id, không sinh mã
    run(channels.set(actor("staff", "u-1"), "zalo", True))
    assert row["zalo_chat_id"] == CHAT and store.subs[(str(TENANT), "u-1", "zalo")]["link_code"] is None


def test_expired_or_unknown_codes_are_refused(clock):
    store = Store()
    channels = make(store, clock)
    run(channels.set(actor("staff", "u-1"), "zalo", True))
    clock.tick(minutes=15, seconds=1)
    bot = Bot()
    assert run(channels.link(bot, message("ABCD2345"))) == "bad_code"
    assert run(channels.link(bot, message("ZZZZ9999"))) == "bad_code"
    assert store.subs[(str(TENANT), "u-1", "zalo")]["zalo_chat_id"] is None
    assert bot.sent == [(CHAT, BAD_CODE), (CHAT, BAD_CODE)]


def test_link_writes_in_the_tenant_of_the_code(clock):
    store = Store()
    channels = make(store, clock)
    run(channels.set(actor("staff", "u-9", tenant=OTHER), "zalo", True))
    assert run(channels.link(Bot(), message("ABCD2345"))) == "linked"
    assert store.subs[(str(OTHER), "u-9", "zalo")]["zalo_chat_id"] == CHAT


@pytest.mark.parametrize(("update", "outcome", "reply"), [
    (message("xin chào"), "hint", HINT),
    (message("ABCD2345", chat_type="GROUP"), "ignored", None),
    (message("ABCD2345", chat_id="x" * 65), "ignored", None),
    ({"event_name": "message.image.received", "message": {"chat": {"id": CHAT}}}, "ignored", None),
    ({"event_name": "message.text.received"}, "ignored", None),
])
def test_other_messages_get_a_hint_or_nothing(clock, update, outcome, reply):
    store = Store()
    bot = Bot()
    assert run(make(store, clock).link(bot, update)) == outcome
    assert bot.sent == ([(CHAT, reply)] if reply else [])
    assert "FindCode" not in store.calls


def test_turning_zalo_off_forgets_the_chat(clock):
    store = Store()
    channels = make(store, clock)
    run(channels.set(actor("staff", "u-1"), "zalo", True))
    run(channels.link(Bot(), message("ABCD2345")))
    zalo = by_channel(run(channels.set(actor("staff", "u-1"), "zalo", False)))["zalo"]
    assert zalo["enabled"] is False
    assert store.subs[(str(TENANT), "u-1", "zalo")] == {"enabled": False, "zalo_chat_id": None, "link_code": None,
                                                         "link_expires_at": None}


def test_listen_survives_bot_errors_and_logs_no_chat_or_code(clock, monkeypatch):
    store = Store()
    channels = make(store, clock)
    run(channels.set(actor("staff", "u-1"), "zalo", True))
    bot = Bot(Failure("Zalo 401", final=True), [message("ABCD2345")], RuntimeError("bot hỏng"))
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)
        if len(waits) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(subscriptions.asyncio, "sleep", sleep)
    with raw_log() as stream, pytest.raises(asyncio.CancelledError):
        run(channels.listen(bot))  # type: ignore[arg-type]
    assert waits == [2.0, 2.0]                  # lấy được tin thì nhịp chờ trở lại từ đầu
    lines = [json.loads(x) for x in stream.getvalue().splitlines()]
    assert [x["event"] for x in lines] == ["core.channel.zalo_poll_failed", "core.channel.zalo_linked",
                                           "core.channel.zalo_poll_failed"]
    assert [x.get("error") for x in lines] == ["Zalo 401", None, "RuntimeError"]
    text = stream.getvalue()
    for value in (CHAT, "ABCD2345", TOKEN, PHONE):
        assert value not in text


def test_set_logs_ids_only(clock):
    with raw_log() as stream:
        run(make(Store(), clock).set(actor("staff", "u-1"), "sms", True))
    (line,) = stream.getvalue().splitlines()
    assert json.loads(line) == {"event": "core.channel.set", "channel": "sms", "enabled": True, "user_id": "u-1",
                                "tenant_id": str(TENANT), "request_id": "req-1"}


# --- route trên app --------------------------------------------------------------------------------------------------

class _NoDirectory:
    async def aclose(self) -> None: ...


def body(name: str, role: str = "staff", user: str = "u-1", **payload: Any) -> dict[str, Any]:
    return {"action": {"name": name}, "input": payload,
            "session_variables": {"x-hasura-role": role, "x-hasura-user-id": user,
                                  "x-hasura-tenant-id": str(TENANT)}}


def app_with(store: Store, flowable, env: dict[str, str]):
    return create_app(Settings.from_env({**ENV, **env}), hasura=store, flowable=flowable,  # type: ignore[arg-type]
                      directory=_NoDirectory())  # type: ignore[arg-type]


def test_route_works_with_the_office_off(flowable):
    store = Store()
    app = app_with(store, flowable, {"MOC_OFFICE_ENABLED": "false", "MOC_SMS_GATEWAY_URL": "http://192.168.1.50:8080",
                                     "MOC_SMS_GATEWAY_USER": "sms", "MOC_SMS_GATEWAY_PASSWORD": "p"})
    assert isinstance(app.state.channels, Channels)
    assert "/actions/channels/{name}" in app.openapi()["paths"]
    headers = {"X-Moc-Action-Secret": SECRET}
    with TestClient(app) as c:
        r = c.post("/actions/channels/myChannels", json=body("myChannels"), headers=headers)
        assert r.status_code == 200 and [x["channel"] for x in r.json()] == ["sms"]
        r = c.post("/actions/channels/setMyChannel", json=body("setMyChannel", channel="sms", enabled=True),
                   headers=headers)
        assert r.status_code == 200 and r.json()[0]["enabled"] is True
        r = c.post("/actions/channels/setMyChannel", json=body("setMyChannel", user="u-2", channel="sms",
                                                                enabled=True), headers=headers)
        assert (r.status_code, r.json()["extensions"]["code"]) == (409, "no_phone")
        r = c.post("/actions/channels/setMyChannel", json=body("setMyChannel", channel="zalo", enabled=True),
                   headers=headers)
        assert (r.status_code, r.json()["extensions"]["code"]) == (400, "channel_off")
        assert c.post("/actions/channels/myChannels", json=body("myChannels"),
                      headers={"X-Moc-Action-Secret": "sai"}).status_code == 401
        assert c.post("/actions/channels/myChannels", json=body("myChannels", role="agent"),
                      headers=headers).status_code == 403
        assert c.post("/actions/channels/setMyChannel", json=body("setMyChannel", channel="sms", enabled="có"),
                      headers=headers).status_code == 400
        assert c.post("/actions/channels/myChannels", json=body("setMyChannel"), headers=headers).status_code == 400


def test_database_errors_answer_503(flowable):
    class Down(Store):
        async def as_service(self, actor_, query, variables=None):
            raise HasuraError("Không gọi được Hasura", None)

    app = app_with(Down(), flowable, {"MOC_OFFICE_ENABLED": "false", "MOC_ZALO_BOT_TOKEN": TOKEN})
    app.state.channels.jobs = lambda: []    # không đọc tin của bot thật
    with TestClient(app) as c:
        r = c.post("/actions/channels/myChannels", json=body("myChannels"), headers={"X-Moc-Action-Secret": SECRET})
    assert (r.status_code, r.json()["extensions"]["code"]) == (503, "unavailable")


def test_without_sms_or_zalo_the_list_is_empty_and_no_loop_runs(flowable):
    store = Store()
    app = app_with(store, flowable, {"MOC_OFFICE_ENABLED": "false"})
    assert app.state.router is None and app.state.channels.jobs() == []
    headers = {"X-Moc-Action-Secret": SECRET}
    with TestClient(app) as c:
        r = c.post("/actions/channels/myChannels", json=body("myChannels"), headers=headers)
        assert (r.status_code, r.json()) == (200, [])
        r = c.post("/actions/channels/setMyChannel", json=body("setMyChannel", channel="sms", enabled=True),
                   headers=headers)
        assert (r.status_code, r.json()["extensions"]["code"]) == (400, "channel_off")
    assert store.calls == []
