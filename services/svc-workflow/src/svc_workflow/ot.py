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

"""Hội tụ IT/OT (F3.10, màn (ii)): cảm biến → bản sao số NGSI-LD → dự thảo "Báo cáo sự cố" trong luồng văn bản đi.

Cảm biến (OT) cập nhật thực thể ``TemperatureSensor`` trong context broker NGSI-LD (Scorpio, profile ``iot``); mỗi
đơn vị là một tenant NGSI-LD (header ``NGSILD-Tenant``, tên suy từ mã đơn vị — ``ngsi_tenant``): thực thể, lịch sử
đo, subscription của các đơn vị tách riêng. Thực thể mang ``temperature`` (°C), ``name`` (tên phòng) và
``responsible`` (tên đăng nhập của chuyên viên phụ trách).

Broker không xác thực: ai vào được mạng thiết bị (``iot-devices``) là ghi được vào tenant bất kỳ. Gắn thiết bị với
đơn vị là việc của cổng thiết bị đặt trước broker (IoT Agent / PEP proxy cấp tenant theo khóa của thiết bị) — bản
rút gọn chỉ có cảm biến giả lập. Thiết bị không tới được svc-workflow: chỉ broker ở chung mạng ``iot`` với dịch vụ.

Ở đây:
  - vòng nền đảm bảo mỗi đơn vị có một subscription id cố định: nhiệt độ vượt ``MOC_OT_THRESHOLD`` thì broker gọi
    ``POST /ot/notify/{tenant}`` của svc-workflow, kèm header token = HMAC(MOC_ACTION_SECRET, tenant) — dịch vụ khác
    trong mạng nội bộ gọi thẳng mà không có token đúng thì bị từ chối;
  - nhận thông báo → dựng dự thảo văn bản đi loại Báo cáo, độ khẩn "Khẩn", từ mẫu, đứng tên người phụ trách (chỉ
    người soạn mới trình được dự thảo), ghi sự kiện ``ot.alarm`` vào dòng thời gian và báo người đó. Người phụ trách
    kiểm tra, bổ sung rồi trình như mọi dự thảo: hệ thống không tự trình, không tự gửi gì ra ngoài.

Chống trùng: cảm biến còn một dự thảo chưa trình (hoặc bị trả lại) thì lần vượt ngưỡng sau không dựng dự thảo mới,
chỉ nhắc người phụ trách — mỗi dự thảo nhiều nhất một thông báo mỗi ngày. Người phụ trách không phải chuyên viên đang
hoạt động của đơn vị thì bỏ qua (ghi nhật ký) — thiết bị không chọn được người đứng tên ngoài đơn vị của tenant.

Broker gửi mỗi thông báo một lần: ghi CSDL lỗi (503) thì lần vượt ngưỡng đó mất, lần đo kế tiếp còn trên ngưỡng sẽ
dựng dự thảo.

Sơ đồ cảm biến (Action ``otSensorMap``, trang /cam-bien): đọc số đo mới nhất của các cảm biến trong tenant của đơn vị
người gọi, kèm bốn cờ chất lượng dữ liệu OT tính ở đây (``sensor_view``) — mất tín hiệu, ngoài dải, trùng
``observedAt``, ``observedAt`` ở tương lai. Cảm biến khai phòng bằng Property ``room`` (mã phòng trên sơ đồ). Broker
không trả lời thì trả trạng thái "unavailable", không lỗi: trang báo chưa bật cảm biến.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import math
import re
import unicodedata
import uuid
from dataclasses import dataclass
from decimal import Decimal
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx2

from .hasura import Actor, HasuraClient, HasuraError
from .notify import Notifier

log = logging.getLogger("svc_workflow")

# Ngữ cảnh lõi NGSI-LD 1.9: Scorpio có sẵn, không tải từ Internet. Gửi tường minh để broker không phải tự sinh ngữ
# cảnh cho subscription (subscription tạo trước khi tenant có thực thể thì bản tự sinh không tra lại được)
CONTEXT = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.9.jsonld"
SUBSCRIPTION_ID = "urn:ngsi-ld:Subscription:moc-ot-alarm"
# Scorpio 6.0.2 cất ngữ cảnh ngầm của subscription trong CSDL của tenant, nhưng lúc gửi thông báo lại đọc ngữ cảnh đó
# không kèm tenant (tức ở tenant mặc định) → không thấy, thông báo bị bỏ. Một subscription "neo" tạm dừng ở tenant
# mặc định, cùng ngữ cảnh, để ngữ cảnh đó có ở tenant mặc định (cùng nội dung thì cùng id). Không bao giờ gửi gì.
ANCHOR_ID = "urn:ngsi-ld:Subscription:moc-ot-context"
SENSOR_TYPE = "TemperatureSensor"
TOKEN_HEADER = "X-Moc-OT-Token"
ACTOR = "svc-workflow"
KIND = "ot.alarm"
VN = timezone(timedelta(hours=7))

_USERNAME = re.compile(r"^[A-Za-z0-9._@-]{1,100}$")
_SENSOR = re.compile(r"^urn:ngsi-ld:[A-Za-z0-9:._-]{1,200}$")
_TENANT = re.compile(r"^[A-Za-z0-9]{1,20}$")
_ROOM = re.compile(r"^[a-z0-9-]{1,40}$")

# Sơ đồ cảm biến. Vai trò đọc được: đúng các vai trò mà office.document_visible có thể cho đọc dự thảo "Báo cáo sự
# cố" (văn bản đi); quản trị đơn vị không đọc văn bản nào nên không có sơ đồ
MAP_ROLES = frozenset({"clerk", "staff", "manager", "director"})
# Dải đo của cảm biến giả lập: dải của cảm biến số DS18B20 (−55 °C đến +125 °C, bảng thông số của Analog Devices).
# Số ngoài dải — kể cả dưới 0 K, phi vật lý — là số đo không tin được, không phải nhiệt độ của phòng
RANGE = (-55.0, 125.0)
HISTORY = 10            # số lần đo gần nhất xét trùng observedAt
MAX_SENSORS = 100       # một trang của truy vấn thực thể; đơn vị có nhiều cảm biến hơn thì sơ đồ thiếu phần sau
HISTORY_BUDGET_S = 8.0  # cả lượt đọc lịch sử; quá thì bỏ cờ trùng observedAt lần này (Hasura chờ Action 15 giây)
# observedAt muộn hơn giờ máy chủ quá chừng này là giờ ở tương lai (cờ future_time, đồng hồ thiết bị chạy nhanh); chừa
# cho lệch giờ NTP, trễ mạng. Đồng hồ nhanh ít hơn thì cờ mất tín hiệu chậm nhiều nhất chừng ấy
FUTURE_SLACK = timedelta(minutes=2)

TENANTS = """
query Tenants { core_tenants(order_by: {code: asc}) { id code } }"""

USER_BY_NAME = """
query NguoiPhuTrach($name: String!) {
  core_users(where: {username: {_eq: $name}, enabled: {_eq: true}}, limit: 1) { id role department_id }
}"""

OPEN_DRAFT = """
query DuThaoDangMo($sensor: jsonb!) {
  office_documents(where: {direction: {_eq: "out"}, status: {_in: ["draft", "returned"]},
                           events: {kind: {_eq: "ot.alarm"}, data: {_contains: $sensor}}}, limit: 1) { id summary }
}"""

# hai lệnh ghi trong một yêu cầu: Hasura chạy chung một giao dịch
CREATE_DRAFT = """
mutation DungBaoCaoSuCo($doc: office_documents_insert_input!, $event: office_document_events_insert_input!) {
  insert_office_documents_one(object: $doc) { id }
  insert_office_document_events_one(object: $event) { id }
}"""

SUMMARY = "Báo cáo sự cố nhiệt độ {room} vượt ngưỡng ngày {day}"

BODY = """Hồi {time} ngày {day}, cảm biến nhiệt độ tại {room} (mã {sensor}) đo được {value} °C, vượt ngưỡng cảnh báo {threshold} °C.
{clock}
1. Diễn biến: (ghi các lần đo, thời điểm phát hiện, thiết bị bị ảnh hưởng.)
2. Nguyên nhân sơ bộ: (ghi sau khi kiểm tra tại chỗ.)
3. Biện pháp đã thực hiện: (ghi các việc đã làm để đưa nhiệt độ về mức an toàn.)
4. Kiến nghị: (ghi đề xuất với lãnh đạo, nếu có.)

Dự thảo do hệ thống dựng từ cảnh báo của cảm biến; người phụ trách kiểm tra, bổ sung các mục trên trước khi trình."""

# {clock} của BODY: rỗng, hoặc đoạn này khi đồng hồ thiết bị chạy nhanh (giờ, ngày trong báo cáo là giờ máy chủ)
CLOCK_AHEAD = ("\nLưu ý: đồng hồ của cảm biến chạy nhanh (thiết bị ghi giờ đo {time} ngày {day}); giờ, ngày nêu trên là"
               " lúc hệ thống nhận số đo.\n")

RECIPIENTS = ["Lãnh đạo đơn vị (để báo cáo)", "Lưu: VT"]


def ngsi_tenant(code: str) -> str:
    """Tên tenant NGSI-LD của một đơn vị: chính mã nếu chỉ có chữ, số ASCII (vd CNTT); mã có dấu (vd ĐHBK) thì
    "t" + 16 ký tự hex băm của mã — header HTTP và tên CSDL của broker chỉ nhận ASCII."""
    if _TENANT.match(code):
        return code
    return "t" + hashlib.sha256(code.encode()).hexdigest()[:16]


def token(secret: str, tenant: str) -> str:
    """Token broker gửi kèm thông báo của một đơn vị — suy từ khóa Action, không thêm bí mật mới."""
    return hmac.new(secret.encode(), f"ot:{tenant}".encode(), hashlib.sha256).hexdigest()


def query_for(threshold: float) -> str:
    """Điều kiện q: số viết thường, không dạng mũ (1e-05), không làm tròn — đúng ngưỡng handle so."""
    plain = str(int(threshold)) if threshold.is_integer() else format(Decimal(repr(threshold)), "f")
    return f"temperature>{plain}"


def subscription(tenant: str, threshold: float, notify_url: str, tok: str) -> dict[str, Any]:
    return {
        "id": SUBSCRIPTION_ID,
        "type": "Subscription",
        "description": "Signet: nhiệt độ vượt ngưỡng → dự thảo báo cáo sự cố",
        "entities": [{"type": SENSOR_TYPE}],
        "watchedAttributes": ["temperature"],
        "q": query_for(threshold),
        "notification": {
            "attributes": ["temperature", "name", "responsible"],
            "format": "normalized",
            "endpoint": {
                "uri": f"{notify_url}/ot/notify/{quote(tenant, safe='')}",
                "accept": "application/json",
                "receiverInfo": [{"key": TOKEN_HEADER, "value": tok}],
            },
        },
        "@context": CONTEXT,
    }


def anchor(notify_url: str) -> dict[str, Any]:
    return {
        "id": ANCHOR_ID,
        "type": "Subscription",
        "description": "Signet: giữ ngữ cảnh JSON-LD của các subscription ở tenant mặc định; tạm dừng, không gửi gì",
        "isActive": False,
        "entities": [{"type": SENSOR_TYPE}],
        "watchedAttributes": ["temperature"],
        "notification": {"endpoint": {"uri": f"{notify_url}/ot/notify/_", "accept": "application/json"}},
        "@context": CONTEXT,
    }


def _same(found: dict[str, Any], want: dict[str, Any]) -> bool:
    """Subscription trên broker có đúng ngưỡng, địa chỉ, token đang cấu hình không."""
    endpoint = (found.get("notification") or {}).get("endpoint") or {}
    info = {i.get("key"): i.get("value") for i in endpoint.get("receiverInfo") or []}
    return (found.get("q") == want["q"]
            and endpoint.get("uri") == want["notification"]["endpoint"]["uri"]
            and info.get(TOKEN_HEADER) == want["notification"]["endpoint"]["receiverInfo"][0]["value"])


@dataclass(frozen=True)
class Reading:
    sensor: str
    room: str
    value: float
    responsible: str
    observed_at: datetime
    device_at: datetime | None = None  # observedAt thiết bị gửi khi đồng hồ thiết bị chạy nhanh (không dùng làm giờ đo)


def _clean(text: str) -> str:
    """Bỏ ký tự điều khiển, ký tự định dạng (đảo chiều chữ U+202E, ký tự vô hình) khỏi chữ thiết bị gửi."""
    return "".join(ch for ch in text if unicodedata.category(ch)[0] != "C").strip()


def _attr(entity: dict[str, Any], name: str) -> dict[str, Any] | None:
    attr = entity.get(name)
    if isinstance(attr, list):  # nhiều instance (datasetId): lấy cái đầu
        attr = attr[0] if attr else None
    return attr if isinstance(attr, dict) else None


def _value(entity: dict[str, Any], name: str) -> Any:
    attr = _attr(entity, name)
    return attr.get("value") if attr else None


def _number(value: Any) -> float | None:
    """Số hữu hạn, hoặc None (chuỗi "41", true, NaN, số nguyên quá lớn — thiết bị không được tin)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        value = float(value)
    except OverflowError:  # số nguyên quá lớn
        return None
    return value if math.isfinite(value) else None


def _time(stamp: Any) -> datetime | None:
    """Mốc thời gian ISO 8601 có múi giờ, hoặc None."""
    if not isinstance(stamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _room_name(entity: dict[str, Any], sensor: str) -> str:
    name = _value(entity, "name")
    return (_clean(name)[:120] if isinstance(name, str) else "") or sensor.rsplit(":", 1)[-1]


def reading(entity: Any, now: datetime) -> Reading | None:
    """Một thực thể trong thông báo → lần đo, hoặc None nếu thiếu hay sai dạng (thiết bị không được tin).

    Giờ đo — giờ, ngày của báo cáo và ngày của khóa nhắc — theo ``observedAt`` của thiết bị; thiếu, cũ hơn một ngày,
    hoặc muộn hơn ``now`` quá ``FUTURE_SLACK`` (đồng hồ thiết bị chạy nhanh, như cờ ``future_time`` của sơ đồ) thì
    theo ``now``, giờ máy chủ nhận thông báo — broker gửi ngay khi nhận số đo. Không thì thiết bị nhanh 30 phút gửi số
    đo lúc 23 giờ 50 làm báo cáo ghi ngày hôm sau. Giờ thiết bị chạy nhanh giữ ở ``device_at`` để dự thảo ghi rõ.
    """
    if not isinstance(entity, dict) or entity.get("type") != SENSOR_TYPE:
        return None
    sensor, value = entity.get("id"), _number(_value(entity, "temperature"))
    responsible = _value(entity, "responsible")
    if not isinstance(sensor, str) or not _SENSOR.match(sensor) or value is None:
        return None
    if not isinstance(responsible, str) or not _USERNAME.match(responsible):
        return None
    observed, ahead = now, None
    attr = entity.get("temperature")
    parsed = _time(attr.get("observedAt")) if isinstance(attr, dict) else None
    if parsed is not None and parsed - now > FUTURE_SLACK:
        ahead = parsed
    elif parsed is not None and now - parsed < timedelta(days=1):
        observed = parsed
    return Reading(sensor, _room_name(entity, sensor), value, responsible, observed, ahead)


# --- sơ đồ cảm biến ------------------------------------------------------------------------------------------


def sensor_view(entity: Any, history: list[datetime] | None, now: datetime,
                stale_after: timedelta) -> dict[str, Any] | None:
    """Một thực thể cảm biến → một dòng của sơ đồ: số đo mới nhất và cờ chất lượng; None nếu không phải cảm biến.

    - ``stale`` (mất tín hiệu): chưa có số đo, hoặc số đo mới nhất cũ hơn ``stale_after`` (theo ``observedAt``; thiết
      bị không gửi ``observedAt``, hoặc gửi giờ ở tương lai, thì theo ``modifiedAt`` — lúc broker nhận số đo);
    - ``out_of_range`` (ngoài dải): giá trị không phải số hữu hạn, hoặc ngoài ``RANGE``;
    - ``duplicate_time`` (trùng ``observedAt``): ``observedAt`` của số đo mới nhất có từ hai lần trở lên trong
      ``history`` (các lần đo gần nhất) — đồng hồ thiết bị đứng hoặc gửi lặp. Có số đo mới đúng giờ thì cờ tự hết.
      ``history`` None (không đọc được lịch sử) thì không kết luận cờ này;
    - ``future_time`` (giờ đo ở tương lai): ``observedAt`` của số đo mới nhất muộn hơn ``now`` quá ``FUTURE_SLACK`` —
      đồng hồ thiết bị chạy nhanh. Giờ đó không dùng để xét mất tín hiệu: theo nó thì số đo cuối luôn có vẻ mới, thiết
      bị đã mất tín hiệu không bao giờ bị gắn ``stale``.
    """
    if not isinstance(entity, dict) or entity.get("type") != SENSOR_TYPE:
        return None
    sensor = entity.get("id")
    if not isinstance(sensor, str) or not _SENSOR.match(sensor):
        return None
    room = _value(entity, "room")
    attr = _attr(entity, "temperature")
    value = _number(attr.get("value")) if attr else None
    stamp = _time(attr.get("observedAt")) if attr else None      # giờ thiết bị
    received = _time(attr.get("modifiedAt")) if attr else None   # giờ broker (options=sysAttrs)
    observed = stamp or received
    ahead = stamp is not None and stamp - now > FUTURE_SLACK
    last = received if ahead else observed
    flags = []
    if last is None or now - last > stale_after:
        flags.append("stale")
    if attr is not None and (value is None or not RANGE[0] <= value <= RANGE[1]):
        flags.append("out_of_range")
    if observed is not None and history is not None and sum(t == observed for t in history) >= 2:
        flags.append("duplicate_time")
    if ahead:
        flags.append("future_time")
    return {
        "id": sensor,
        "room": room if isinstance(room, str) and _ROOM.match(room) else None,
        "name": _room_name(entity, sensor),
        "value": value,
        "observed_at": observed.astimezone(UTC).isoformat() if observed else None,
        "flags": flags,
    }


def history_times(body: Any) -> list[datetime] | None:
    """Thân trả về của temporal API cho một thực thể → các ``observedAt`` của ``temperature``; None nếu sai dạng.

    Thuộc tính một instance có thể về dạng đối tượng thay vì mảng (JSON-LD rút gọn)."""
    if not isinstance(body, dict):
        return None
    attr = body.get("temperature")
    instances = attr if isinstance(attr, list) else [attr] if isinstance(attr, dict) else []
    return [t for t in (_time(i.get("observedAt")) for i in instances if isinstance(i, dict)) if t is not None]


def map_result(status: str, threshold: float, stale_min: int, now: datetime,
               sensors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Kết quả của Action otSensorMap — đúng kiểu ``OtSensorMap`` khai trong db/metadata/actions.graphql.

    ``status``: ``ready`` (broker trả lời), ``off`` (chưa đặt MOC_NGSI_URL), ``unavailable`` (broker không trả lời:
    chưa bật profile iot, đang khởi động)."""
    return {"status": status, "threshold": threshold, "stale_after_min": stale_min, "range_min": RANGE[0],
            "range_max": RANGE[1], "checked_at": now.astimezone(UTC).isoformat(), "sensors": sensors or []}


def _num(x: float) -> str:
    return f"{x:g}".replace(".", ",")  # 41,5 °C


def draft(r: Reading, threshold: float, user: dict[str, Any], doc_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Dự thảo văn bản đi dựng từ mẫu, và sự kiện ot.alarm của nó."""
    local = r.observed_at.astimezone(VN)
    day = local.strftime("%d/%m/%Y")
    data = {"sensor": r.sensor, "name": r.room, "temperature": r.value, "threshold": threshold,
            "observed_at": r.observed_at.astimezone(UTC).isoformat()}
    clock = ""
    if r.device_at is not None:  # giờ thiết bị cả trong sự kiện: thân dự thảo người phụ trách còn sửa được
        data["device_observed_at"] = r.device_at.astimezone(UTC).isoformat()
        device = r.device_at.astimezone(VN)
        clock = CLOCK_AHEAD.format(time=device.strftime("%H giờ %M"), day=device.strftime("%d/%m/%Y"))
    doc = {
        "id": doc_id,
        "direction": "out",
        "status": "draft",
        "type_code": "BC",
        "urgency": "khan",
        "summary": SUMMARY.format(room=r.room, day=day),
        "body": BODY.format(time=local.strftime("%H giờ %M"), day=day, room=r.room, sensor=r.sensor,
                            value=_num(r.value), threshold=_num(threshold), clock=clock),
        "recipients": RECIPIENTS,
        "department_id": user["department_id"],
        "created_by": user["id"],
    }
    return doc, {"document_id": doc_id, "kind": KIND, "actor_id": ACTOR, "actor_kind": "service", "data": data}


class OtBridge:
    def __init__(self, hasura: HasuraClient, notifier: Notifier, ngsi_url: str, *, secret: str,
                 threshold: float = 35.0, notify_url: str = "http://svc-workflow:8000", timeout_s: float = 5.0,
                 stale_min: int = 10, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self.hasura = hasura
        self.notifier = notifier
        self.secret = secret
        self.threshold = threshold
        self.stale_min = stale_min
        self.notify_url = notify_url.rstrip("/")
        self._http = httpx2.AsyncClient(base_url=ngsi_url.rstrip("/"), timeout=timeout_s, transport=transport)
        self._lock = asyncio.Lock()  # một thông báo một lúc: hai lần vượt ngưỡng sát nhau không dựng hai dự thảo
        self._reachable: bool | None = None
        self._map_ok: bool | None = None  # lần đọc sơ đồ trước có tới được broker không (chỉ ghi nhật ký khi đổi)

    async def aclose(self) -> None:
        await self._http.aclose()

    def check(self, tenant: str, given: str) -> bool:
        return hmac.compare_digest(given.encode(), token(self.secret, tenant).encode())

    # --- subscription trên broker ------------------------------------------------------------------------

    async def ensure_all(self) -> int:
        """Mỗi đơn vị một subscription đúng cấu hình → số subscription vừa tạo hay thay.

        Broker chưa chạy (chưa bật profile iot) thì chỉ ghi nhật ký lúc đổi trạng thái, không ghi mỗi vòng. Một đơn
        vị lỗi (broker từ chối, trả lạ) thì ghi nhật ký rồi làm tiếp đơn vị sau, vòng sau thử lại.
        """
        tenants = (await self.hasura.as_system(TENANTS))["core_tenants"]
        changed = 0
        try:
            try:
                await self._ensure_anchor()
            except httpx2.TransportError:
                raise
            except (httpx2.HTTPError, RuntimeError, ValueError) as exc:
                log.warning(json.dumps({"event": "ot.subscription_failed", "tenant": "", "error": str(exc)[:300]},
                                       ensure_ascii=False))
            for t in tenants:
                try:
                    changed += await self.ensure(ngsi_tenant(t["code"]))
                except httpx2.TransportError:
                    raise
                except (httpx2.HTTPError, RuntimeError, ValueError) as exc:
                    log.warning(json.dumps({"event": "ot.subscription_failed", "tenant": t["code"],
                                            "error": str(exc)[:300]}, ensure_ascii=False))
        except httpx2.TransportError as exc:
            if self._reachable is not False:
                log.warning(json.dumps({"event": "ot.broker_unreachable", "error": str(exc)}, ensure_ascii=False))
            self._reachable = False
            return 0
        if self._reachable is not True:
            log.info(json.dumps({"event": "ot.broker_ready", "tenants": len(tenants)}))
        self._reachable = True
        return changed

    async def _ensure_anchor(self) -> None:
        r = await self._http.get(f"/ngsi-ld/v1/subscriptions/{ANCHOR_ID}")
        if r.status_code == 200:
            return
        if r.status_code != 404:
            raise RuntimeError(f"broker trả HTTP {r.status_code} khi đọc subscription neo")
        made = await self._http.post("/ngsi-ld/v1/subscriptions", json=anchor(self.notify_url),
                                     headers={"Content-Type": "application/ld+json"})
        if made.status_code not in (201, 409):
            raise RuntimeError(f"broker không tạo được subscription neo: HTTP {made.status_code} {made.text[:200]}")

    async def ensure(self, tenant: str) -> int:
        want = subscription(tenant, self.threshold, self.notify_url, token(self.secret, tenant))
        headers = {"NGSILD-Tenant": tenant}
        r = await self._http.get(f"/ngsi-ld/v1/subscriptions/{SUBSCRIPTION_ID}", headers=headers)
        if r.status_code == 200 and _same(r.json(), want):
            return 0
        if r.status_code == 200:  # ngưỡng, địa chỉ hay khóa đã đổi: thay cả subscription
            gone = await self._http.delete(f"/ngsi-ld/v1/subscriptions/{SUBSCRIPTION_ID}", headers=headers)
            if gone.status_code not in (204, 404):
                raise RuntimeError(f"broker không xóa được subscription cũ: HTTP {gone.status_code}")
        elif r.status_code != 404:
            raise RuntimeError(f"broker trả HTTP {r.status_code} khi đọc subscription")
        made = await self._http.post("/ngsi-ld/v1/subscriptions", json=want,
                                     headers={**headers, "Content-Type": "application/ld+json"})
        if made.status_code != 201:
            raise RuntimeError(f"broker không tạo được subscription: HTTP {made.status_code} {made.text[:200]}")
        log.info(json.dumps({"event": "ot.subscription_created", "tenant": tenant, "q": want["q"]},
                            ensure_ascii=False))
        return 1

    # --- sơ đồ cảm biến (Action otSensorMap) ----------------------------------------------------------------

    async def sensor_map(self, tenant_id: uuid.UUID, now: datetime | None = None) -> dict[str, Any]:
        """Số đo mới nhất và cờ chất lượng của mọi cảm biến trong tenant NGSI-LD của một đơn vị.

        Chỉ đọc tenant của ``tenant_id`` (đơn vị trong biến phiên của người gọi). Broker không trả lời, trả lỗi hay
        trả lạ → ``unavailable``; tenant chưa có thực thể nào (Scorpio trả 404 TenantNotFound) → không có cảm biến.
        Lịch sử của từng cảm biến (để xét trùng ``observedAt``) đọc song song, tối đa 8 lời gọi một lúc, cả lượt trong
        ``HISTORY_BUDGET_S`` giây; broker chưa ghi lịch sử (404) thì coi như chưa có lần đo nào trong lịch sử, lỗi khác
        thì cảm biến đó không có kết luận về cờ trùng.
        """
        now = now or datetime.now(UTC)
        tenants = (await self.hasura.as_system(TENANTS))["core_tenants"]
        code = next((t["code"] for t in tenants if t["id"] == str(tenant_id)), None)
        if code is None:
            return map_result("ready", self.threshold, self.stale_min, now)
        tenant = ngsi_tenant(code)
        headers = {"NGSILD-Tenant": tenant, "Accept": "application/json"}
        try:
            r = await self._http.get("/ngsi-ld/v1/entities", headers=headers, params={
                "type": SENSOR_TYPE, "limit": MAX_SENSORS, "options": "sysAttrs"})
            entities = [] if r.status_code == 404 else r.json() if r.status_code == 200 else None
            error = "" if isinstance(entities, list) else f"HTTP {r.status_code}"
        except (httpx2.HTTPError, ValueError) as exc:
            entities, error = None, f"{type(exc).__name__}: {str(exc)[:200]}"
        if not isinstance(entities, list):
            # trang tự làm mới 30 giây một lần: profile iot tắt lâu dài thì không ghi một dòng mỗi lần đọc
            if self._map_ok is not False:
                log.warning(json.dumps({"event": "ot.map_unavailable", "tenant": tenant, "error": error},
                                       ensure_ascii=False))
            self._map_ok = False
            return map_result("unavailable", self.threshold, self.stale_min, now)
        self._map_ok = True

        ids = [e["id"] for e in entities if isinstance(e, dict) and isinstance(e.get("id"), str)
               and _SENSOR.match(e["id"]) and e.get("temperature") is not None]
        gate = asyncio.Semaphore(8)

        async def history(sensor: str) -> list[datetime] | None:
            async with gate:
                try:
                    h = await self._http.get(f"/ngsi-ld/v1/temporal/entities/{sensor}", headers=headers,
                                             params={"attrs": "temperature", "lastN": HISTORY})
                    if h.status_code == 404:  # broker chưa ghi lịch sử nào của cảm biến (ghi bất đồng bộ)
                        return []
                    return history_times(h.json()) if h.status_code == 200 else None
                except (httpx2.HTTPError, ValueError):
                    return None

        try:
            found = await asyncio.wait_for(asyncio.gather(*(history(s) for s in ids)), HISTORY_BUDGET_S)
        except TimeoutError:
            found = [None] * len(ids)
        histories = dict(zip(ids, found, strict=True))
        missing = sum(h is None for h in found)
        if missing:
            log.warning(json.dumps({"event": "ot.map_history_missing", "tenant": tenant, "sensors": missing}))
        stale_after = timedelta(minutes=self.stale_min)
        rows = [v for v in (sensor_view(e, histories.get(e.get("id")) if isinstance(e, dict) else None, now,
                                        stale_after) for e in entities) if v is not None]
        rows.sort(key=lambda v: (v["room"] is None, v["room"] or "", v["id"]))
        return map_result("ready", self.threshold, self.stale_min, now, rows)

    # --- thông báo từ broker -----------------------------------------------------------------------------

    async def handle(self, tenant: str, payload: dict[str, Any], now: datetime | None = None) -> list[str]:
        """Thông báo của subscription → id các dự thảo vừa dựng."""
        now = now or datetime.now(UTC)
        entities = payload.get("data")
        if not isinstance(entities, list):
            raise ValueError("data không phải danh sách thực thể")
        found = [t for t in (await self.hasura.as_system(TENANTS))["core_tenants"] if ngsi_tenant(t["code"]) == tenant]
        if not found:
            log.warning(json.dumps({"event": "ot.unknown_tenant", "tenant": tenant}, ensure_ascii=False))
            return []
        actor = Actor(ACTOR, uuid.UUID(found[0]["id"]), "service", None)
        created: list[str] = []
        async with self._lock:
            for entity in entities:
                r = reading(entity, now)
                if r is None or r.value <= self.threshold:
                    continue
                doc_id = await self._draft(actor, r)
                if doc_id:
                    created.append(doc_id)
        return created

    async def _draft(self, actor: Actor, r: Reading) -> str | None:
        users = (await self.hasura.as_service(actor, USER_BY_NAME, {"name": r.responsible}))["core_users"]
        user = users[0] if users else None
        if user is None or user["role"] != "staff" or not user["department_id"]:
            log.warning(json.dumps({"event": "ot.alarm_ignored", "reason": "không có chuyên viên phụ trách",
                                    "sensor": r.sensor, "tenant_id": str(actor.tenant_id)}, ensure_ascii=False))
            return None
        open_draft = (await self.hasura.as_service(actor, OPEN_DRAFT, {"sensor": {"sensor": r.sensor}}))
        if open_draft["office_documents"]:
            doc = open_draft["office_documents"][0]
            log.info(json.dumps({"event": "ot.alarm_open_draft", "sensor": r.sensor, "value": r.value,
                                 "document_id": doc["id"]}))
            await self._notify(actor, user, r, doc["id"], doc["summary"])  # nhắc, mỗi ngày nhiều nhất một lần
            return None
        doc, event = draft(r, self.threshold, user, str(uuid.uuid4()))
        await self.hasura.as_service(actor, CREATE_DRAFT, {"doc": doc, "event": event})
        doc_id = doc["id"]
        log.info(json.dumps({"event": KIND, "sensor": r.sensor, "value": r.value, "threshold": self.threshold,
                             "document_id": doc_id, "tenant_id": str(actor.tenant_id)}))
        await self._notify(actor, user, r, doc_id, doc["summary"])
        return doc_id

    async def _notify(self, actor: Actor, user: dict[str, Any], r: Reading, doc_id: str, summary: str) -> None:
        day = r.observed_at.astimezone(VN).date().isoformat()  # đồng hồ thiết bị chạy nhanh thì ngày theo giờ máy chủ
        try:
            await self.notifier.send(actor, [user["id"]], KIND, f"{KIND}:{doc_id}:{day}", doc_id,
                                     {"name": r.room, "temperature": r.value, "threshold": self.threshold,
                                      "summary": summary})
        except HasuraError as exc:  # dự thảo đã có; thiếu thông báo thì người phụ trách vẫn thấy trong danh sách
            log.warning(json.dumps({"event": "ot.notify_failed", "document_id": doc_id, "error": str(exc)},
                                   ensure_ascii=False))
