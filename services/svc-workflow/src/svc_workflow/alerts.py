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

"""Cảnh báo vận hành ra chuông, email, webhook (F3.13, #284).

Prometheus tính luật cảnh báo (``platform/monitoring/canh-bao.yml``) rồi đẩy cảnh báo đang bật sang Alertmanager.
Alertmanager gom theo tên cảnh báo, chống gửi dồn (``platform/monitoring/alertmanager.yml``) và gọi ``POST /ops/alerts``
ở đây kèm ``Authorization: Bearer <MOC_ALERT_TOKEN>``. Mỗi cảnh báo ``firing`` hay ``resolved`` thành một thông báo
``ops.alert`` cho mọi quản trị đơn vị (vai trò ``tenant_admin``) của mọi đơn vị: thành phần dùng chung gián đoạn thì đơn
vị nào cũng chịu. Thông báo đi qua ``Notifier`` như mọi thông báo khác, nên email, webhook, SMS, Zalo dùng lại cấu hình
kênh sẵn có (``MOC_NOTIFY_*_KINDS``), không khai bí mật lần thứ hai trong Alertmanager.

Chống trùng: khóa ``ops.alert:<fingerprint>:<startsAt>:<status>``. Alertmanager gửi lại (``repeat_interval``, mất nhật
ký gửi khi khởi động lại) không sinh dòng thứ hai; sự cố bật lại sau khi đã hết có ``startsAt`` mới nên là thông báo
mới. Ghi CSDL lỗi thì trả 503 để Alertmanager gửi lại cả lô.

Thông báo chỉ mang tên cảnh báo, mức, câu tóm tắt của luật và nhãn thành phần, route: không có dữ liệu của người dùng.
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu khai báo của route trong install().
import hmac
import json
import logging
import re
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Self

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from .config import Settings
from .hasura import Actor, HasuraClient, HasuraError
from .notify import Notifier

log = logging.getLogger("svc_workflow")

KIND = "ops.alert"
ACTOR = "svc-workflow"
ROLE = "tenant_admin"
# Alertmanager gửi nhiều nhất max_alerts cảnh báo mỗi lần (alertmanager.yml); thân lớn hơn là không phải nó
MAX_ALERTS = 50
# nhãn của luật cảnh báo (canh-bao.yml) chép vào thông báo; nhãn khác (instance, job…) bỏ
LABELS = ("component", "route")
FINGERPRINT = re.compile(r"[0-9a-f]{1,64}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})")
CONTROL = re.compile(r"[\x00-\x1f\x7f]+")

TENANTS = """
query Tenants { core_tenants(order_by: {code: asc}) { id code } }"""


class BadAlert(ValueError):
    """Thân không phải webhook của Alertmanager."""


def _refuse(status: int, code: str, message: str) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return HTTPException(status, {"code": code, "message": message}, headers)


def _text(value: Any, limit: int) -> str:
    """Chữ một dòng, bỏ ký tự điều khiển, cắt ở ``limit`` ký tự."""
    text = " ".join(CONTROL.sub(" ", str(value)).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse(body: Any) -> list[tuple[str, dict[str, Any]]]:
    """Thân webhook của Alertmanager (phiên bản 4) → (khóa chống trùng, dữ liệu thông báo) của từng cảnh báo."""
    if not isinstance(body, dict) or not isinstance(body.get("alerts"), list):
        raise BadAlert("thiếu danh sách alerts")
    if not 1 <= len(body["alerts"]) <= MAX_ALERTS:
        raise BadAlert(f"cần 1–{MAX_ALERTS} cảnh báo")
    out: list[tuple[str, dict[str, Any]]] = []
    for alert in body["alerts"]:
        if not isinstance(alert, dict):
            raise BadAlert("cảnh báo không phải đối tượng JSON")
        status, fingerprint, starts = alert.get("status"), alert.get("fingerprint"), alert.get("startsAt")
        labels, annotations = alert.get("labels"), alert.get("annotations") or {}
        if status not in ("firing", "resolved"):
            raise BadAlert("status phải là firing hoặc resolved")
        if not (isinstance(fingerprint, str) and FINGERPRINT.fullmatch(fingerprint)):
            raise BadAlert("fingerprint sai dạng")
        if not (isinstance(starts, str) and TIMESTAMP.fullmatch(starts)):
            raise BadAlert("startsAt sai dạng")
        if not (isinstance(labels, dict) and labels.get("alertname")) or not isinstance(annotations, dict):
            raise BadAlert("thiếu nhãn alertname")
        data: dict[str, Any] = {
            "status": status,
            "alert": _text(labels["alertname"], 100),
            "severity": _text(labels.get("severity") or "", 20),
            "message": _text(annotations.get("summary") or labels["alertname"], 300),
            "starts_at": starts,
        }
        for name in LABELS:
            if labels.get(name):
                data[name] = _text(labels[name], 100)
        ends = alert.get("endsAt")
        if status == "resolved" and isinstance(ends, str) and TIMESTAMP.fullmatch(ends):
            data["ends_at"] = ends
        out.append((f"{KIND}:{fingerprint}:{starts}:{status}", data))
    return out


@dataclass
class OpsAlerts:
    """Route nhận cảnh báo của Alertmanager, gắn vào app theo khuôn ``parts.Part``; không có việc nền."""

    settings: Settings
    hasura: HasuraClient
    notifier: Notifier

    @classmethod
    def build(cls, settings: Settings, hasura: HasuraClient, notifier: Notifier) -> Self:
        return cls(settings, hasura, notifier)

    def jobs(self) -> list[Coroutine[Any, Any, None]]:
        return []

    async def aclose(self) -> None:
        return None

    def check(self, authorization: str) -> bool:
        scheme, _, given = authorization.partition(" ")
        token = self.settings.alert_token
        return bool(token) and scheme.lower() == "bearer" and hmac.compare_digest(given.strip().encode(),
                                                                                  token.encode())

    async def deliver(self, alerts: list[tuple[str, dict[str, Any]]]) -> int:
        """Ghi thông báo cho quản trị của từng đơn vị → số thông báo vừa ghi (bỏ khóa đã có)."""
        sent = 0
        for tenant in (await self.hasura.as_system(TENANTS))["core_tenants"]:
            actor = Actor(ACTOR, uuid.UUID(tenant["id"]), "service", None)
            admins = (await self.notifier.people(actor)).with_role(ROLE)
            for key, data in alerts:
                sent += len(await self.notifier.send(actor, admins, KIND, key, None, data))
        return sent

    def install(self, app: FastAPI) -> None:
        @app.post("/ops/alerts", status_code=204,
                  summary="Nhận cảnh báo của Alertmanager → thông báo ops.alert cho quản trị đơn vị (F3.13)",
                  description="Chỉ Alertmanager gọi (receiver webhook trong platform/monitoring/alertmanager.yml), kèm "
                              "Authorization: Bearer MOC_ALERT_TOKEN. Thân là webhook phiên bản 4 của Alertmanager; "
                              "mỗi cảnh báo firing/resolved thành một thông báo cho mọi người dùng vai trò "
                              "tenant_admin, gửi lại không sinh thông báo thứ hai.",
                  responses={400: {"description": "Thân không phải webhook của Alertmanager"},
                             401: {"description": "Thiếu hoặc sai token"},
                             404: {"description": "Chưa đặt MOC_ALERT_TOKEN"},
                             503: {"description": "Chưa ghi được CSDL, Alertmanager sẽ gửi lại"}})
        async def ops_alerts(request: Request) -> Response:
            # Khai trả 204 nên chỉ có một return (204 không thân); lỗi ném ra cho FastAPI như apps/api.py
            if not self.settings.alert_token:
                raise _refuse(404, "not_found", "Chưa bật cảnh báo vận hành (MOC_ALERT_TOKEN)")
            if not self.check(request.headers.get("authorization", "")):
                raise _refuse(401, "unauthorized", "Sai token của Alertmanager")
            try:
                alerts = parse(await request.json())
            except ValueError as exc:       # JSON hỏng (JSONDecodeError là ValueError) hoặc sai dạng
                raise _refuse(400, "bad_request", f"Thân không phải webhook của Alertmanager: {exc}") from exc
            try:
                sent = await self.deliver(alerts)
            except HasuraError as exc:
                log.warning(json.dumps({"event": "ops.alert.failed", "error": str(exc)}, ensure_ascii=False))
                raise _refuse(503, "database_unavailable", "Chưa ghi được thông báo, Alertmanager sẽ gửi lại") from exc
            log.info(json.dumps({"event": "ops.alert.received", "alerts": [d["alert"] for _, d in alerts],
                                 "notifications": sent}, ensure_ascii=False))
            return Response(status_code=204)
