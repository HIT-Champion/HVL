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

"""Sơ đồ cảm biến OT (F3.10, Action otSensorMap): cờ chất lượng, đọc broker theo tenant, broker tắt, quyền vai trò,
khớp kiểu GraphQL khai cho Hasura; cảm biến giả lập khai phòng, giả lỗi dữ liệu."""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest

from conftest import OTHER, TENANT
from svc_workflow import ot
from svc_workflow.config import ConfigError, Settings
from svc_workflow.ot import MAP_ROLES, OtBridge, history_times, map_result, sensor_view
from test_ot import ENV, SECRET, OtHasura, client_for

ROOT = pathlib.Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 20, 2, 30, tzinfo=UTC)
STALE = timedelta(minutes=10)


def run(coro):
    return asyncio.run(coro)


def at(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def entity(code: str, value: Any = 22.5, observed: str | None = None, room: Any = None, **extra: Any) -> dict:
    e: dict[str, Any] = {"id": f"urn:ngsi-ld:TemperatureSensor:{code}", "type": "TemperatureSensor",
                         "name": {"type": "Property", "value": f"Phòng {code}"},
                         "responsible": {"type": "Property", "value": "chuyenviendt"}}
    if value is not ...:
        e["temperature"] = {"type": "Property", "value": value, "unitCode": "CEL",
                            "observedAt": observed if observed is not None else at(1)}
    if room is not None:
        e["room"] = {"type": "Property", "value": room}
    return {**e, **extra}


def times(*stamps: str) -> list[datetime]:
    return [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps]


# --- cờ chất lượng ---------------------------------------------------------------------------------------------


def test_fresh_reading_has_no_flag():
    view = sensor_view(entity("kho-1", 22.5, room="kho-1"), times(at(1), at(2)), NOW, STALE)
    assert view == {"id": "urn:ngsi-ld:TemperatureSensor:kho-1", "room": "kho-1", "name": "Phòng kho-1",
                    "value": 22.5, "observed_at": "2026-10-20T02:29:00+00:00", "flags": []}


def test_stale_after_n_minutes_without_reading():
    assert sensor_view(entity("a", observed=at(10)), [], NOW, STALE)["flags"] == []      # đúng N phút: chưa mất
    assert sensor_view(entity("a", observed=at(10.5)), [], NOW, STALE)["flags"] == ["stale"]
    assert sensor_view(entity("a", observed=at(30)), [], NOW, timedelta(minutes=60))["flags"] == []
    never = sensor_view(entity("a", value=...), None, NOW, STALE)              # chưa có lần đo nào
    assert never["flags"] == ["stale"] and never["value"] is None and never["observed_at"] is None
    # thiết bị không gửi observedAt: theo modifiedAt của broker (options=sysAttrs); thiếu cả hai là mất tín hiệu
    no_stamp = entity("a")
    del no_stamp["temperature"]["observedAt"]
    assert sensor_view(no_stamp, [], NOW, STALE)["flags"] == ["stale"]
    no_stamp["temperature"]["modifiedAt"] = at(2)
    assert sensor_view(no_stamp, [], NOW, STALE)["flags"] == []
    assert sensor_view(entity("a", observed="hôm qua"), [], NOW, STALE)["flags"] == ["stale"]
    no_zone = entity("a", observed="2026-10-20T02:29:00")                      # không múi giờ
    assert sensor_view(no_zone, [], NOW, STALE)["flags"] == ["stale"]


@pytest.mark.parametrize(("value", "shown"), [
    (-127, -127.0),          # mã "mất kết nối" của thư viện DallasTemperature
    (-300, -300.0),          # dưới 0 K: phi vật lý
    (125.5, 125.5), (-55.5, -55.5),
    ("41", None), (True, None), (None, None), (10**400, None), ({"v": 1}, None),
])
def test_out_of_range_or_not_a_number(value, shown):
    view = sensor_view(entity("a", value), [], NOW, STALE)
    assert view["flags"] == ["out_of_range"] and view["value"] == shown


def test_range_limits_are_inside():
    assert ot.RANGE == (-55.0, 125.0)
    for value in (-55, 125, 0, 35.1):
        assert sensor_view(entity("a", value), [], NOW, STALE)["flags"] == []


def test_duplicate_observed_at_of_the_latest_reading():
    latest = at(1)
    assert sensor_view(entity("a", observed=latest), times(latest, latest, at(2)), NOW, STALE)["flags"] == \
        ["duplicate_time"]
    # cùng thời điểm viết khác dạng (múi giờ, phần giây) vẫn là trùng
    assert sensor_view(entity("a", observed=latest), times(latest, "2026-10-20T09:29:00.000+07:00"), NOW,
                       STALE)["flags"] == ["duplicate_time"]
    assert sensor_view(entity("a", observed=latest), times(latest, at(2)), NOW, STALE)["flags"] == []
    # trùng ở hai lần đo cũ, số đo mới nhất đúng giờ: cờ đã hết
    assert sensor_view(entity("a", observed=latest), times(latest, at(5), at(5)), NOW, STALE)["flags"] == []
    # không đọc được lịch sử: không kết luận
    assert sensor_view(entity("a", observed=latest), None, NOW, STALE)["flags"] == []


def test_flags_combine_in_fixed_order():
    old = at(40)
    view = sensor_view(entity("a", -127, observed=old), times(old, old), NOW, STALE)
    assert view["flags"] == ["stale", "out_of_range", "duplicate_time"]


def test_device_text_is_cleaned_and_room_code_checked():
    for bad in ("Kho 1", "../kho", "KHO-1", "k" * 41, 5, ""):
        assert sensor_view(entity("a", room=bad), [], NOW, STALE)["room"] is None
    assert sensor_view(entity("a", room="kho-1"), [], NOW, STALE)["room"] == "kho-1"
    odd = entity("a")
    odd["name"] = [{"type": "Property", "value": "Kho\u202e bảo\x00 quản\n", "datasetId": "urn:a"}]
    assert sensor_view(odd, [], NOW, STALE)["name"] == "Kho bảo quản"
    odd["name"] = {"type": "Property", "value": "\x07"}
    assert sensor_view(odd, [], NOW, STALE)["name"] == "a"
    many = entity("a")
    many["temperature"] = [{"type": "Property", "value": 30, "observedAt": at(1)}, {"type": "Property", "value": 99}]
    assert sensor_view(many, [], NOW, STALE)["value"] == 30.0
    assert sensor_view({**entity("a"), "type": "Room"}, [], NOW, STALE) is None
    assert sensor_view({**entity("a"), "id": "kho-1"}, [], NOW, STALE) is None
    assert sensor_view("x", [], NOW, STALE) is None


def test_history_body_shapes():
    one = {"id": "x", "temperature": {"type": "Property", "value": 1, "observedAt": "2026-10-20T02:29:00Z"}}
    assert history_times(one) == times("2026-10-20T02:29:00Z")
    many = {"temperature": [{"observedAt": "2026-10-20T02:29:00Z"}, {"observedAt": "sai"}, "x", {}]}
    assert history_times(many) == times("2026-10-20T02:29:00Z")
    assert history_times({"id": "x"}) == []
    assert history_times([]) is None and history_times(None) is None


# --- đọc broker ----------------------------------------------------------------------------------------------


class MapBroker:
    """Broker NGSI-LD giả cho sơ đồ: thực thể và lịch sử đo theo tenant; tenant chưa có gì thì 404 như Scorpio."""

    def __init__(self) -> None:
        self.entities: dict[str, list[Any]] = {}
        self.history: dict[str, dict[str, list[str]]] = {}
        self.requests: list[httpx2.Request] = []
        self.down = False
        self.status = 200
        self.temporal_broken: set[str] = set()

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if self.down:
            raise httpx2.ConnectError("broker chưa chạy")
        self.requests.append(request)
        assert request.method == "GET"
        tenant = request.headers.get("NGSILD-Tenant", "")
        path = request.url.path
        if path == "/ngsi-ld/v1/entities":
            if self.status != 200:
                return httpx2.Response(self.status, text="lỗi")
            if tenant not in self.entities:
                return httpx2.Response(404, json={"title": "Tenant not found"})
            return httpx2.Response(200, json=self.entities[tenant])
        prefix = "/ngsi-ld/v1/temporal/entities/"
        assert path.startswith(prefix), path
        sensor = path.removeprefix(prefix)
        if sensor in self.temporal_broken:
            return httpx2.Response(500, json={})
        stamps = self.history.get(tenant, {}).get(sensor)
        if stamps is None:
            return httpx2.Response(404, json={})
        return httpx2.Response(200, json={"id": sensor, "type": "TemperatureSensor", "temperature": [
            {"type": "Property", "value": 20, "observedAt": s} for s in stamps]})


@pytest.fixture
def db() -> OtHasura:
    return OtHasura()


@pytest.fixture
def broker() -> MapBroker:
    b = MapBroker()
    latest = at(1)
    b.entities["CNTT"] = [
        entity("may-chu", 41, room="may-chu"),
        entity("kho-3", 23, observed=latest, room="kho-3"),
        entity("kho-2", -127, room="kho-2"),
        entity("phong-doc", 24, observed=at(30), room="phong-doc"),
        entity("hanh-lang", 21),                      # chưa khai phòng: ngoài sơ đồ
        {"id": "urn:ngsi-ld:Room:kho-1", "type": "Room"},  # không phải cảm biến: bỏ qua
    ]
    b.history["CNTT"] = {"urn:ngsi-ld:TemperatureSensor:kho-3": [latest, latest, at(2)],
                         "urn:ngsi-ld:TemperatureSensor:may-chu": [at(1), at(2)]}
    b.entities["KT"] = [entity("kho-kt", 20, room="kho-1")]
    return b


@pytest.fixture
def bridge(db, broker) -> OtBridge:
    return OtBridge(db, None, "http://scorpio:9090", secret=SECRET,  # type: ignore[arg-type]
                    threshold=35, stale_min=10, transport=httpx2.MockTransport(broker))


def test_map_reads_only_the_callers_tenant_with_flags(bridge, broker, caplog):
    result = run(bridge.sensor_map(TENANT, now=NOW))
    assert (result["status"], result["threshold"], result["stale_after_min"]) == ("ready", 35, 10)
    assert (result["range_min"], result["range_max"], result["checked_at"]) == (-55.0, 125.0, NOW.isoformat())
    flags = {s["id"].rsplit(":", 1)[-1]: s["flags"] for s in result["sensors"]}
    assert flags == {"kho-2": ["out_of_range"], "kho-3": ["duplicate_time"], "may-chu": [], "phong-doc": ["stale"],
                     "hanh-lang": []}
    # xếp theo phòng, cảm biến chưa khai phòng ở cuối
    assert [s["room"] for s in result["sensors"]] == ["kho-2", "kho-3", "may-chu", "phong-doc", None]
    # ba cảm biến broker chưa ghi lịch sử (404): không phải lỗi, không ghi nhật ký
    assert not any("ot.map_history_missing" in r.message for r in caplog.records)
    assert {r.headers["NGSILD-Tenant"] for r in broker.requests} == {"CNTT"}
    query = dict(broker.requests[0].url.params)
    assert query == {"type": "TemperatureSensor", "limit": "100", "options": "sysAttrs"}
    temporal = [r for r in broker.requests if "/temporal/" in r.url.path]
    assert len(temporal) == 5 and all(dict(r.url.params) == {"attrs": "temperature", "lastN": "10"} for r in temporal)
    other = run(bridge.sensor_map(OTHER, now=NOW))
    assert [s["id"] for s in other["sensors"]] == ["urn:ngsi-ld:TemperatureSensor:kho-kt"]
    assert broker.requests[-1].headers["NGSILD-Tenant"] == "KT"


def test_map_of_tenant_without_entities_or_unknown_unit_is_empty(bridge, broker):
    del broker.entities["CNTT"]
    assert run(bridge.sensor_map(TENANT, now=NOW)) == map_result("ready", 35, 10, NOW)
    broker.requests.clear()
    assert run(bridge.sensor_map(uuid.uuid4(), now=NOW))["sensors"] == []
    assert broker.requests == []   # đơn vị không có trong CSDL: không hỏi broker tenant nào


@pytest.mark.parametrize("trouble", ["down", "500", "not-a-list"])
def test_broker_trouble_is_unavailable_not_an_error(bridge, broker, caplog, trouble):
    if trouble == "down":
        broker.down = True
    elif trouble == "500":
        broker.status = 500
    else:
        broker.entities["CNTT"] = {"type": "TemperatureSensor"}  # type: ignore[assignment]
    result = run(bridge.sensor_map(TENANT, now=NOW))
    assert result == map_result("unavailable", 35, 10, NOW)
    assert run(bridge.sensor_map(TENANT, now=NOW)) == result
    # trang tự làm mới: broker tắt lâu chỉ ghi một dòng nhật ký
    assert sum("ot.map_unavailable" in r.message for r in caplog.records) == 1


def test_history_failure_only_drops_the_duplicate_check(bridge, broker, caplog, monkeypatch):
    broker.temporal_broken = {"urn:ngsi-ld:TemperatureSensor:kho-3"}
    flags = {s["id"].rsplit(":", 1)[-1]: s["flags"] for s in run(bridge.sensor_map(TENANT, now=NOW))["sensors"]}
    assert flags["kho-3"] == [] and flags["kho-2"] == ["out_of_range"] and flags["phong-doc"] == ["stale"]
    assert any("ot.map_history_missing" in r.message for r in caplog.records)
    # cả lượt đọc lịch sử quá hạn: không cờ trùng nào, phần còn lại vẫn đủ
    broker.temporal_broken = set()
    monkeypatch.setattr(ot, "HISTORY_BUDGET_S", 0)
    flags = {s["id"].rsplit(":", 1)[-1]: s["flags"] for s in run(bridge.sensor_map(TENANT, now=NOW))["sensors"]}
    assert flags["kho-3"] == [] and flags["phong-doc"] == ["stale"]


# --- Action qua HTTP, hợp đồng với Hasura ------------------------------------------------------------------


def action(c, role: str, tenant: uuid.UUID = TENANT):
    return c.post("/actions/otSensorMap", headers={"X-Moc-Action-Secret": SECRET}, json={
        "action": {"name": "otSensorMap"}, "input": {},
        "session_variables": {"x-hasura-role": role, "x-hasura-user-id": "u-1", "x-hasura-tenant-id": str(tenant)}})


def graphql_type(name: str) -> set[str]:
    sdl = (ROOT / "db" / "metadata" / "actions.graphql").read_text(encoding="utf-8")
    body = re.search(rf"^type {name} \{{(.*?)^\}}", sdl, re.S | re.M)
    assert body, name
    return set(re.findall(r"^\s+(\w+)\s*:", body.group(1), re.M))


def test_action_for_document_roles_only(hasura, flowable, bridge):
    with client_for(hasura, flowable, bridge) as c:
        for role in ("clerk", "staff", "manager", "director"):
            r = action(c, role)
            assert r.status_code == 200 and r.json()["status"] == "ready", role
        r = action(c, "tenant_admin")
        assert r.status_code == 403 and r.json()["extensions"]["code"] == "forbidden"
        assert action(c, "service").status_code == 403
        assert c.post("/actions/otSensorMap", json={"action": {"name": "otSensorMap"}, "input": {},
                                                    "session_variables": {}}).status_code == 401


def test_action_result_matches_the_graphql_types(hasura, flowable, bridge):
    with client_for(hasura, flowable, bridge) as c:
        result = action(c, "clerk").json()
    assert set(result) == graphql_type("OtSensorMap")
    assert result["sensors"] and all(set(s) == graphql_type("OtSensor") for s in result["sensors"])
    assert 'otSensorMap: OtSensorMap!' in (ROOT / "db" / "metadata" / "actions.graphql").read_text(encoding="utf-8")


def test_hasura_permissions_match_service_roles():
    meta = (ROOT / "db" / "metadata" / "actions.yaml").read_text(encoding="utf-8")
    block = re.search(r"^  - name: otSensorMap\n(.*?)(?=^  - name: |^custom_types:)", meta, re.S | re.M)
    assert block, "thiếu Action otSensorMap trong db/metadata/actions.yaml"
    assert "type: query" in block.group(1) and "/actions/otSensorMap'" in block.group(1)
    assert set(re.findall(r"- role: (\w+)", block.group(1))) == MAP_ROLES
    objects = meta.split("custom_types:", 1)[1]
    assert "- name: OtSensorMap\n" in objects and "- name: OtSensor\n" in objects


def test_ot_off_says_so_without_error(hasura, flowable):
    env = {k: v for k, v in ENV.items() if k != "MOC_NGSI_URL"}
    with client_for(hasura, flowable, env={**env, "MOC_OT_THRESHOLD": "30", "MOC_OT_STALE_MIN": "15"}) as c:
        r = action(c, "staff")
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["threshold"], body["stale_after_min"], body["sensors"]) == ("off", 30, 15, [])


def test_broker_down_through_http_is_still_200(hasura, flowable, bridge, broker):
    broker.down = True
    with client_for(hasura, flowable, bridge) as c:
        r = action(c, "director")
    assert r.status_code == 200 and r.json()["status"] == "unavailable"


def test_stale_minutes_setting():
    assert Settings.from_env(ENV).ot_stale_min == 10
    assert Settings.from_env({**ENV, "MOC_OT_STALE_MIN": "30"}).ot_stale_min == 30
    for bad in ("0", "1441", "-5", "2.5", "lâu"):
        with pytest.raises(ConfigError):
            Settings.from_env({**ENV, "MOC_OT_STALE_MIN": bad})


# --- cảm biến giả lập ----------------------------------------------------------------------------------------


@pytest.fixture
def sensor_module(monkeypatch):
    spec = importlib.util.spec_from_file_location("ot_sensor", ROOT / "services" / "ot-sensor" / "sensor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    sent: list[tuple[str, str, str, dict | None]] = []

    def call(base, method, path, tenant, body=None):
        sent.append((method, path, tenant, body))
        return 201 if method == "POST" else 204

    monkeypatch.setattr(module, "call", call)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    module.sent = sent
    return module


def readings(sent) -> list[tuple[float, datetime]]:
    return [(b["temperature"]["value"], datetime.fromisoformat(b["temperature"]["observedAt"].replace("Z", "+00:00")))
            for m, p, t, b in sent if m == "PATCH" and b and "temperature" in b]


def test_sensor_declares_its_room(sensor_module, capsys):
    assert sensor_module.main(["--tenant", "CNTT", "--sensor", "kho-1", "--name", "Kho bảo quản 1", "--room", "kho-1",
                               "--responsible", "chuyenviendt", "--readings", "21,22", "--interval", "0"]) == 0
    method, path, tenant, body = sensor_module.sent[0]
    assert (method, path, tenant) == ("POST", "/entities", "CNTT")
    assert body["room"] == {"type": "Property", "value": "kho-1"} and body["id"].endswith(":kho-1")
    assert [v for v, _ in readings(sensor_module.sent)] == [21.0, 22.0]
    assert len(capsys.readouterr().out.splitlines()) == 2
    with pytest.raises(SystemExit):
        sensor_module.main(["--tenant", "CNTT", "--responsible", "a", "--readings", "1", "--room", "Kho 1"])


def test_sensor_without_room_sends_none(sensor_module):
    sensor_module.main(["--tenant", "CNTT", "--responsible", "a", "--readings", "30", "--interval", "0"])
    assert "room" not in sensor_module.sent[0][3]


def test_sensor_can_fake_a_frozen_clock_and_a_late_reading(sensor_module):
    sensor_module.main(["--tenant", "CNTT", "--sensor", "kho-3", "--responsible", "a", "--readings", "23,24,25",
                        "--interval", "0", "--frozen-clock"])
    stamps = {t for _, t in readings(sensor_module.sent)}
    assert len(stamps) == 1
    sensor_module.sent.clear()
    before = datetime.now(UTC)
    sensor_module.main(["--tenant", "CNTT", "--sensor", "phong-doc", "--responsible", "a", "--readings", "24",
                        "--interval", "0", "--late", "30"])
    (_, stamp), = readings(sensor_module.sent)
    assert timedelta(minutes=29) < before - stamp < timedelta(minutes=31)


def test_existing_sensor_gets_its_room_on_update(sensor_module):
    sensor_module.call = lambda base, method, path, tenant, body=None: (
        sensor_module.sent.append((method, path, tenant, body)) or (409 if method == "POST" else 204))
    sensor_module.main(["--tenant", "CNTT", "--responsible", "a", "--readings", "30", "--room", "may-chu",
                        "--interval", "0"])
    method, path, _, body = sensor_module.sent[1]
    assert (method, path) == ("PATCH", "/entities/urn:ngsi-ld:TemperatureSensor:phong-may-chu/attrs")
    assert body["room"]["value"] == "may-chu" and body["name"]["value"] == "Phòng máy chủ"
