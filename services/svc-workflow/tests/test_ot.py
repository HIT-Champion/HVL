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

"""IT/OT (F3.10): subscription NGSI-LD trên broker, thông báo vượt ngưỡng → dự thảo báo cáo sự cố."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import pathlib
import textwrap
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from conftest import DEPT_DT, TENANT
from svc_workflow.app import create_app
from svc_workflow.config import ConfigError, Settings
from svc_workflow.hasura import Actor, HasuraError
from svc_workflow.ot import (ANCHOR_ID, SUBSCRIPTION_ID, TOKEN_HEADER, OtBridge, ngsi_tenant, query_for, reading,
                             subscription, token)

NOW = datetime(2026, 10, 20, 2, 30, tzinfo=UTC)
SECRET = "bi-mat-action"
SENSOR = "urn:ngsi-ld:TemperatureSensor:phong-may-chu"
SCHEMAS = pathlib.Path(__file__).resolve().parents[3] / "schemas"
OPENAPI = pathlib.Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi" / "svc-workflow.json"


def run(coro):
    return asyncio.run(coro)


def sensor(value: Any = 41, responsible: Any = "chuyenviendt", **extra: Any) -> dict[str, Any]:
    return {"id": SENSOR, "type": "TemperatureSensor",
            "name": {"type": "Property", "value": "Phòng máy chủ tầng 3"},
            "responsible": {"type": "Property", "value": responsible},
            "temperature": {"type": "Property", "value": value, "unitCode": "CEL",
                            "observedAt": "2026-10-20T02:29:00Z"}, **extra}


def notification(*entities: dict[str, Any]) -> dict[str, Any]:
    return {"id": "notification:1", "type": "Notification", "subscriptionId": SUBSCRIPTION_ID,
            "notifiedAt": "2026-10-20T02:29:01Z", "data": list(entities)}


class OtHasura:
    """CSDL giả cho phần IT/OT: hai đơn vị, người dùng theo tên đăng nhập, dự thảo đã dựng."""

    def __init__(self) -> None:
        self.tenants = [{"id": str(TENANT), "code": "CNTT"}, {"id": "318da474-60d6-4a90-aa7f-928b31b8fc59", "code": "KT"}]
        self.users = {
            "chuyenviendt": {"id": "u-staff-dt", "role": "staff", "department_id": str(DEPT_DT)},
            "totruongdt": {"id": "u-manager-dt", "role": "manager", "department_id": str(DEPT_DT)},
        }
        self.drafts: list[tuple[dict[str, Any], dict[str, Any], Actor]] = []
        self.fail = False

    async def as_system(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        assert "Tenants" in query
        return {"core_tenants": self.tenants}

    async def as_service(self, actor: Actor, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        await asyncio.sleep(0)  # nhường lượt như gọi mạng thật: hai thông báo đồng thời xen được vào nhau
        variables = variables or {}
        if "NguoiPhuTrach" in query:
            user = self.users.get(variables["name"]) if actor.tenant_id == TENANT else None
            return {"core_users": [user] if user else []}
        if "DuThaoDangMo" in query:
            sensor_id = variables["sensor"]["sensor"]
            return {"office_documents": [{"id": d["id"], "summary": d["summary"]} for d, e, _ in self.drafts
                                         if d["status"] in ("draft", "returned") and e["data"]["sensor"] == sensor_id]}
        if "DungBaoCaoSuCo" in query:
            if self.fail:
                raise HasuraError("Không gọi được Hasura")
            self.drafts.append((variables["doc"], variables["event"], actor))
            return {"insert_office_documents_one": {"id": variables["doc"]["id"]},
                    "insert_office_document_events_one": {"id": 1}}
        raise AssertionError(query)


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str, str | None, dict[str, Any]]] = []
        self.keys: list[str] = []

    async def send(self, actor: Actor, user_ids, kind: str, key: str, document_id: str | None,
                   data: dict[str, Any]) -> list[str]:
        self.sent.append((list(user_ids), kind, document_id, data))
        self.keys.append(key)
        return list(user_ids)


class Broker:
    """Broker NGSI-LD giả: subscription theo tenant ("" = tenant mặc định, chỉ có subscription neo)."""

    def __init__(self) -> None:
        self.subs: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []
        self.down = False
        self.broken: set[str] = set()  # tenant mà broker trả 500

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if self.down:
            raise httpx2.ConnectError("broker chưa chạy")
        tenant = request.headers.get("NGSILD-Tenant", "")
        self.calls.append(f"{request.method} {tenant}")
        if tenant in self.broken:
            return httpx2.Response(500, json={})
        if request.method == "GET":
            sub = self.subs.get(tenant)
            return httpx2.Response(200, json=sub) if sub else httpx2.Response(404, json={})
        if request.method == "DELETE":
            return httpx2.Response(204) if self.subs.pop(tenant, None) else httpx2.Response(404, json={})
        if request.method == "POST":
            assert request.headers["Content-Type"] == "application/ld+json"
            if tenant in self.subs:
                return httpx2.Response(409, json={})
            body = json.loads(request.content)
            self.subs[tenant] = {k: v for k, v in body.items() if k != "@context"}
            return httpx2.Response(201)
        raise AssertionError(request.method)


@pytest.fixture
def db() -> OtHasura:
    return OtHasura()


@pytest.fixture
def broker() -> Broker:
    return Broker()


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def bridge(db, notifier, broker) -> OtBridge:
    return OtBridge(db, notifier, "http://scorpio:9090", secret=SECRET, threshold=35,  # type: ignore[arg-type]
                    transport=httpx2.MockTransport(broker))


# --- subscription ------------------------------------------------------------------------------------------


def test_token_differs_per_tenant_and_secret():
    assert token(SECRET, "CNTT") != token(SECRET, "KT")
    assert token(SECRET, "CNTT") != token("khoa-khac", "CNTT")
    assert len(token(SECRET, "CNTT")) == 64


def test_subscription_filters_on_threshold_and_carries_token():
    sub = subscription("CNTT", 35, "http://svc-workflow:8000", "tok")
    assert sub["q"] == "temperature>35" and sub["watchedAttributes"] == ["temperature"]
    assert sub["entities"] == [{"type": "TemperatureSensor"}]
    endpoint = sub["notification"]["endpoint"]
    assert endpoint["uri"] == "http://svc-workflow:8000/ot/notify/CNTT"
    assert endpoint["receiverInfo"] == [{"key": TOKEN_HEADER, "value": "tok"}]
    assert sub["@context"].startswith("https://uri.etsi.org/ngsi-ld/")
    assert subscription("Đơn vị/1", 37.5, "http://x", "t")["notification"]["endpoint"]["uri"] == \
        "http://x/ot/notify/%C4%90%C6%A1n%20v%E1%BB%8B%2F1"
    assert subscription("CNTT", 37.5, "http://x", "t")["q"] == "temperature>37.5"


def test_tenant_name_is_ascii_for_any_unit_code():
    assert ngsi_tenant("CNTT") == "CNTT" and ngsi_tenant("KT2") == "KT2"
    accented = ngsi_tenant("ĐHBK")
    assert accented.isascii() and accented.isalnum() and len(accented) == 17
    assert accented == ngsi_tenant("ĐHBK") != ngsi_tenant("DHBK") != ngsi_tenant("ĐHBK.")


def test_threshold_is_written_plain_in_query():
    assert query_for(35.0) == "temperature>35"
    assert query_for(37.5) == "temperature>37.5"
    assert query_for(35.123456789) == "temperature>35.123456789"  # không làm tròn
    assert query_for(1e-05) == "temperature>0.00001"                # không dạng mũ
    assert query_for(-12.0) == "temperature>-12"


def test_ensure_creates_one_subscription_per_tenant_then_leaves_it(bridge, broker):
    assert run(bridge.ensure_all()) == 2
    assert set(broker.subs) == {"", "CNTT", "KT"}
    assert broker.subs["KT"]["notification"]["endpoint"]["receiverInfo"][0]["value"] == token(SECRET, "KT")
    # neo ở tenant mặc định: tạm dừng, không token, không điều kiện — chỉ để broker có ngữ cảnh ở đó
    assert broker.subs[""]["id"] == ANCHOR_ID and broker.subs[""]["isActive"] is False
    assert "q" not in broker.subs[""] and "receiverInfo" not in broker.subs[""]["notification"]["endpoint"]
    broker.calls.clear()
    assert run(bridge.ensure_all()) == 0
    assert broker.calls == ["GET ", "GET CNTT", "GET KT"]


def test_ensure_replaces_subscription_when_threshold_changes(db, notifier, broker, bridge):
    run(bridge.ensure_all())
    hotter = OtBridge(db, notifier, "http://scorpio:9090", secret=SECRET, threshold=40,  # type: ignore[arg-type]
                      transport=httpx2.MockTransport(broker))
    broker.calls.clear()
    assert run(hotter.ensure_all()) == 2
    assert broker.subs["CNTT"]["q"] == "temperature>40"
    assert broker.calls[:4] == ["GET ", "GET CNTT", "DELETE CNTT", "POST CNTT"]


def test_one_failing_tenant_does_not_block_the_others(db, bridge, broker, caplog):
    db.tenants.append({"id": "5b0c8b1e-0d6e-4c43-9a51-1f6f0d4f3a10", "code": "ĐHBK"})
    broker.broken = {"KT"}
    assert run(bridge.ensure_all()) == 2
    assert set(broker.subs) == {"", "CNTT", ngsi_tenant("ĐHBK")}
    assert any("ot.subscription_failed" in r.message and "KT" in r.message for r in caplog.records)
    broker.broken = set()
    assert run(bridge.ensure_all()) == 1  # vòng sau làm nốt


def test_broker_down_is_logged_once_and_not_raised(bridge, broker, caplog):
    broker.down = True
    caplog.set_level("INFO", logger="svc_workflow")
    assert run(bridge.ensure_all()) == 0
    assert run(bridge.ensure_all()) == 0
    assert [r.message for r in caplog.records].count(caplog.records[0].message) == 1
    assert "ot.broker_unreachable" in caplog.records[0].message
    broker.down = False
    assert run(bridge.ensure_all()) == 2
    assert "ot.broker_ready" in caplog.records[-1].message


# --- thông báo → dự thảo -------------------------------------------------------------------------------------


def test_reading_rejects_malformed_entities():
    assert reading(sensor(), NOW).value == 41.0
    assert reading(sensor(), NOW).observed_at == datetime(2026, 10, 20, 2, 29, tzinfo=UTC)
    assert reading(sensor(value="41"), NOW) is None
    assert reading(sensor(value=True), NOW) is None
    assert reading(sensor(value=float("nan")), NOW) is None
    assert reading(sensor(responsible="a b; drop"), NOW) is None
    assert reading(sensor(responsible=None), NOW) is None
    assert reading({**sensor(), "type": "Room"}, NOW) is None
    assert reading({**sensor(), "id": "phong-may"}, NOW) is None
    # mốc đo lệch quá xa (đồng hồ thiết bị sai) thì lấy giờ nhận
    far = sensor()
    far["temperature"]["observedAt"] = "2020-01-01T00:00:00Z"
    assert reading(far, NOW).observed_at == NOW
    assert reading(sensor(value=10**400), NOW) is None                     # số nguyên quá lớn
    assert reading({**sensor(), "id": "urn:ngsi-ld:TemperatureSensor:phòng máy"}, NOW) is None
    # chữ thiết bị gửi: bỏ ký tự điều khiển, đảo chiều; thuộc tính nhiều instance lấy cái đầu
    odd = sensor()
    odd["name"] = [{"type": "Property", "value": "Phòng\u202e máy\x00 chủ\n", "datasetId": "urn:a"}]
    assert reading(odd, NOW).room == "Phòng máy chủ"
    odd["name"] = {"type": "Property", "value": "\x07\u200b"}
    assert reading(odd, NOW).room == "phong-may-chu"


def at(stamp: datetime, value: Any = 41) -> dict[str, Any]:
    entity = sensor(value)
    entity["temperature"]["observedAt"] = stamp.isoformat().replace("+00:00", "Z")
    return entity


def test_reading_uses_server_time_when_device_clock_runs_ahead():
    # muộn hơn giờ máy chủ quá FUTURE_SLACK (2 phút, như cờ future_time của sơ đồ): giờ đo là giờ máy chủ nhận,
    # giữ giờ thiết bị cho dự thảo
    for ahead in (timedelta(minutes=2, seconds=1), timedelta(minutes=30), timedelta(days=400)):
        r = reading(at(NOW + ahead), NOW)
        assert (r.observed_at, r.device_at) == (NOW, NOW + ahead)
    # đồng hồ đúng, nhanh trong FUTURE_SLACK (lệch NTP, trễ mạng) hay chậm dưới một ngày: giữ giờ thiết bị như trước
    for off in (timedelta(minutes=2), timedelta(seconds=30), timedelta(0), -timedelta(minutes=30),
                -timedelta(hours=23)):
        r = reading(at(NOW + off), NOW)
        assert (r.observed_at, r.device_at) == (NOW + off, None)
    late = reading(at(NOW - timedelta(days=2)), NOW)  # chậm quá một ngày: giờ máy chủ, như trước, không ghi chú
    assert (late.observed_at, late.device_at) == (NOW, None)


def test_alarm_builds_urgent_report_draft_for_responsible_staff(bridge, db, notifier):
    created = run(bridge.handle("CNTT", notification(sensor(41.5)), now=NOW))
    assert len(created) == 1
    doc, event, actor = db.drafts[0]
    assert actor.tenant_id == TENANT and actor.role == "service"
    assert doc["id"] == created[0] and event["document_id"] == created[0]
    assert (doc["direction"], doc["status"], doc["type_code"], doc["urgency"]) == ("out", "draft", "BC", "khan")
    assert doc["created_by"] == "u-staff-dt" and doc["department_id"] == str(DEPT_DT)
    assert doc["summary"] == "Báo cáo sự cố nhiệt độ Phòng máy chủ tầng 3 vượt ngưỡng ngày 20/10/2026"
    assert "Hồi 09 giờ 29 ngày 20/10/2026" in doc["body"] and "41,5 °C" in doc["body"] and "35 °C" in doc["body"]
    assert doc["recipients"]
    assert event["kind"] == "ot.alarm" and event["actor_kind"] == "service"
    assert event["data"]["sensor"] == SENSOR and event["data"]["temperature"] == 41.5
    assert notifier.sent == [(["u-staff-dt"], "ot.alarm", created[0], {
        "name": "Phòng máy chủ tầng 3", "temperature": 41.5, "threshold": 35, "summary": doc["summary"]})]


def test_open_draft_of_same_sensor_is_not_duplicated(bridge, db, notifier):
    first = run(bridge.handle("CNTT", notification(sensor(41)), now=NOW))[0]
    assert run(bridge.handle("CNTT", notification(sensor(43)), now=NOW)) == []
    assert len(db.drafts) == 1
    # lần vượt ngưỡng sau chỉ nhắc, cùng khóa trong ngày (CSDL bỏ thông báo trùng khóa); ngày sau nhắc lại
    assert notifier.keys == [f"ot.alarm:{first}:2026-10-20"] * 2
    later = sensor(42)
    later["temperature"]["observedAt"] = "2026-10-21T01:00:00Z"
    assert run(bridge.handle("CNTT", notification(later), now=datetime(2026, 10, 21, 1, 1, tzinfo=UTC))) == []
    assert notifier.keys[-1] == f"ot.alarm:{first}:2026-10-21" and notifier.sent[-1][3]["temperature"] == 42
    db.drafts[0][0]["status"] = "returned"  # bị trả lại: vẫn đang ở người soạn
    assert run(bridge.handle("CNTT", notification(sensor(43)), now=NOW)) == []
    db.drafts[0][0]["status"] = "in_review"  # đã trình: lần vượt ngưỡng sau là sự cố mới
    assert len(run(bridge.handle("CNTT", notification(sensor(44)), now=NOW))) == 1


def test_fast_device_clock_near_midnight_dates_report_and_reminder_by_server_day(bridge, db, notifier):
    # 23 giờ 50 ngày 20/10 giờ Việt Nam; đồng hồ thiết bị nhanh 30 phút nên observedAt đã là 00 giờ 20 ngày 21/10
    now = datetime(2026, 10, 20, 16, 50, tzinfo=UTC)
    first = run(bridge.handle("CNTT", notification(at(now + timedelta(minutes=30), 41.5)), now=now))[0]
    doc, event, _ = db.drafts[0]
    assert doc["summary"] == "Báo cáo sự cố nhiệt độ Phòng máy chủ tầng 3 vượt ngưỡng ngày 20/10/2026"
    assert doc["body"].startswith("Hồi 23 giờ 50 ngày 20/10/2026, cảm biến nhiệt độ tại Phòng máy chủ tầng 3")
    assert ("35 °C.\n\nLưu ý: đồng hồ của cảm biến chạy nhanh (thiết bị ghi giờ đo 00 giờ 20 ngày 21/10/2026);"
            " giờ, ngày nêu trên là lúc hệ thống nhận số đo.\n\n1. Diễn biến:") in doc["body"]
    assert event["data"]["observed_at"] == "2026-10-20T16:50:00+00:00"
    assert event["data"]["device_observed_at"] == "2026-10-20T17:20:00+00:00"
    # lần vượt ngưỡng sau chỉ nhắc, khóa theo ngày của giờ máy chủ: 23 giờ 55 còn ngày 20/10 (trùng khóa, CSDL bỏ),
    # 00 giờ 10 mới sang ngày 21/10
    for minutes in (5, 20):
        later = now + timedelta(minutes=minutes)
        assert run(bridge.handle("CNTT", notification(at(later + timedelta(minutes=30), 42)), now=later)) == []
    assert notifier.keys == [f"ot.alarm:{first}:2026-10-20"] * 2 + [f"ot.alarm:{first}:2026-10-21"]


def test_normal_device_clock_near_midnight_keeps_device_time(bridge, db, notifier):
    now = datetime(2026, 10, 20, 16, 59, 30, tzinfo=UTC)  # 23 giờ 59 phút 30 giây ngày 20/10 giờ Việt Nam
    first = run(bridge.handle("CNTT", notification(at(now - timedelta(minutes=1))), now=now))[0]
    doc, event, _ = db.drafts[0]
    assert doc["summary"].endswith("ngày 20/10/2026") and doc["body"].startswith("Hồi 23 giờ 58 ngày 20/10/2026")
    assert "35 °C.\n\n1. Diễn biến:" in doc["body"] and "chạy nhanh" not in doc["body"]
    assert event["data"]["observed_at"] == "2026-10-20T16:58:30+00:00" and "device_observed_at" not in event["data"]
    assert notifier.keys == [f"ot.alarm:{first}:2026-10-20"]


def test_concurrent_alarms_make_one_draft(bridge, db):
    async def both():
        await asyncio.gather(bridge.handle("CNTT", notification(sensor(41)), now=NOW),
                             bridge.handle("CNTT", notification(sensor(42)), now=NOW))
    run(both())
    assert len(db.drafts) == 1


def test_below_threshold_unknown_tenant_or_non_staff_make_nothing(bridge, db, notifier):
    assert run(bridge.handle("CNTT", notification(sensor(35)), now=NOW)) == []          # bằng ngưỡng: chưa vượt
    assert run(bridge.handle("KHAC", notification(sensor(50)), now=NOW)) == []
    assert run(bridge.handle("CNTT", notification(sensor(50, "totruongdt")), now=NOW)) == []  # không phải chuyên viên
    assert run(bridge.handle("CNTT", notification(sensor(50, "khongco")), now=NOW)) == []
    assert run(bridge.handle("KT", notification(sensor(50)), now=NOW)) == []  # người phụ trách thuộc đơn vị khác
    assert db.drafts == [] and notifier.sent == []
    with pytest.raises(ValueError):
        run(bridge.handle("CNTT", {"data": 5}, now=NOW))


def test_notify_failure_keeps_the_draft(bridge, db, notifier):
    async def broken(*args, **kwargs):
        raise HasuraError("Không gọi được Hasura")
    notifier.send = broken  # type: ignore[method-assign]
    assert len(run(bridge.handle("CNTT", notification(sensor(41)), now=NOW))) == 1
    assert len(db.drafts) == 1


# --- đường HTTP ----------------------------------------------------------------------------------------------

ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": SECRET, "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_DIRECTORY_SYNC_INTERVAL_S": "0", "MOC_RECONCILE_INTERVAL_S": "0",
    "MOC_SLA_POLL_INTERVAL_S": "0", "MOC_PROCESSES_DIR": "/khong-co", "MOC_SCHEMAS_DIR": str(SCHEMAS),
    "MOC_NGSI_URL": "http://scorpio:9090", "MOC_OT_SUBSCRIPTION_INTERVAL_S": "0",
}


class NoDirectory:
    async def aclose(self) -> None: ...


def client_for(hasura, flowable, bridge=None, env=ENV):
    app = create_app(Settings.from_env(env), hasura=hasura, flowable=flowable, directory=NoDirectory(),  # type: ignore[arg-type]
                     ot=bridge)
    return TestClient(app)


def test_notify_endpoint_checks_tenant_token(hasura, flowable, bridge, db):
    with client_for(hasura, flowable, bridge) as c:
        body = notification(sensor(41))
        assert c.post("/ot/notify/CNTT", json=body).status_code == 401
        assert c.post("/ot/notify/CNTT", json=body, headers={TOKEN_HEADER: token(SECRET, "KT")}).status_code == 401
        assert c.post("/ot/notify/CNTT", content=b"[]",
                      headers={TOKEN_HEADER: token(SECRET, "CNTT"), "Content-Type": "application/json"}).status_code == 400
        assert c.post("/ot/notify/CNTT", json={"data": "x"}, headers={TOKEN_HEADER: token(SECRET, "CNTT")}).status_code == 400
        assert db.drafts == []
        r = c.post("/ot/notify/CNTT", json=body, headers={TOKEN_HEADER: token(SECRET, "CNTT")})
        assert r.status_code == 204 and len(db.drafts) == 1
        db.fail = True
        db.drafts[0][0]["status"] = "in_review"
        r = c.post("/ot/notify/CNTT", json=body, headers={TOKEN_HEADER: token(SECRET, "CNTT")})
        assert r.status_code == 503


def test_ot_is_off_without_broker_url(hasura, flowable):
    env = {k: v for k, v in ENV.items() if k != "MOC_NGSI_URL"}
    with client_for(hasura, flowable, env=env) as c:
        r = c.post("/ot/notify/CNTT", json=notification(), headers={TOKEN_HEADER: token(SECRET, "CNTT")})
        assert r.status_code == 404


def action_error(code: str, message: str) -> dict[str, Any]:
    return {"message": message, "extensions": {"code": code}}


def test_notify_errors_keep_the_action_error_format(hasura, flowable, bridge, db):
    # Route khai 204 nên lỗi được ném ra (WorkflowError); bộ xử lý chung trả mã HTTP và thân lỗi như trước
    def post(c: TestClient, content: bytes, token_of: str | None = "CNTT") -> tuple[int, Any]:
        headers = {"Content-Type": "application/json"}
        if token_of:
            headers[TOKEN_HEADER] = token(SECRET, token_of)
        r = c.post("/ot/notify/CNTT", content=content, headers=headers)
        assert r.headers["content-type"] == "application/json"
        return r.status_code, r.json()

    body = json.dumps(notification(sensor(41))).encode()
    wrong_token = action_error("unauthorized", "Sai token của đơn vị")
    not_notification = action_error("bad_request", "Thông báo không phải Notification NGSI-LD")
    with client_for(hasura, flowable, bridge) as c:
        assert post(c, body, None) == (401, wrong_token)
        assert post(c, body, "KT") == (401, wrong_token)
        assert post(c, b"[]") == (400, not_notification)
        assert post(c, b"{") == (400, not_notification)
        assert post(c, b'{"data": "x"}') == (400, action_error("bad_request", "Thông báo không có danh sách thực thể"))
        db.fail = True
        assert post(c, body) == (503, action_error("unavailable", "Chưa ghi được dự thảo, thử lại sau"))
    env = {k: v for k, v in ENV.items() if k != "MOC_NGSI_URL"}
    with client_for(hasura, flowable, env=env) as c:
        assert post(c, body) == (404, action_error("not_found", "Chưa bật IT/OT (MOC_NGSI_URL)"))
    assert db.drafts == []


def test_notify_success_has_no_body_and_openapi_is_unchanged(hasura, flowable, bridge, db):
    with client_for(hasura, flowable, bridge) as c:
        r = c.post("/ot/notify/CNTT", json=notification(sensor(41)), headers={TOKEN_HEADER: token(SECRET, "CNTT")})
        assert r.status_code == 204 and r.content == b"" and "content-type" not in r.headers
        assert len(db.drafts) == 1
        # Ném WorkflowError thay vì trả thân lỗi không đổi tài liệu: route trùng từng trường với docs/api/
        doc = c.get("/openapi.json").json()["paths"]["/ot/notify/{tenant}"]
    assert doc == json.loads(OPENAPI.read_text(encoding="utf-8"))["paths"]["/ot/notify/{tenant}"]
    assert set(doc["post"]["responses"]) == {"204", "401", "404", "422", "503"}


def test_no_content_routes_have_no_return_with_body(hasura, flowable):
    # Kiểm lại luật SonarQube python:S8400 trong CI: route khai 204 chỉ trả Response rỗng, lỗi thì ném ra
    app = client_for(hasura, flowable).app
    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.status_code == 204]
    assert [r.path for r in routes] == ["/ot/notify/{tenant}", "/api/workflow/{app}/tasks/{task_id}", "/ops/alerts"]
    for route in routes:
        tree = ast.parse(textwrap.dedent(inspect.getsource(route.endpoint)))
        returns = {ast.unparse(n.value) if n.value else "" for n in ast.walk(tree) if isinstance(n, ast.Return)}
        assert returns <= {"", "None", "Response(status_code=204)"}, (route.path, sorted(returns))


def test_threshold_must_be_a_number():
    with pytest.raises(ConfigError):
        Settings.from_env({**ENV, "MOC_OT_THRESHOLD": "nan"})
    with pytest.raises(ConfigError):
        Settings.from_env({**ENV, "MOC_OT_THRESHOLD": "nóng"})
    assert Settings.from_env({**ENV, "MOC_OT_THRESHOLD": "37.5"}).ot_threshold == 37.5
