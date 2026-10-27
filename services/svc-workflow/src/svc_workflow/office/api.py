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

"""Phần Văn phòng điện tử gắn vào svc-workflow theo khuôn của ``parts.py``.

- Route: ``POST /actions/{name}`` (Hasura Actions ``receiveIncoming``, ``registerIncoming``, ``submitOutgoing``,
  ``myTasks``, ``completeTask``, ``otSensorMap``) và ``POST /ot/notify/{tenant}`` (context broker NGSI-LD).
- Việc nền: triển khai BPMN văn bản (``processes/``), đối soát quy trình, báo văn bản quá hạn, liên thông, nhắc hạn,
  gợi ý giao việc, giữ subscription IT/OT.

``create_app`` chỉ dựng phần này khi ``MOC_OFFICE_ENABLED`` bật (mặc định); tắt thì svc-workflow chỉ còn phần chung
(docs/architecture.md §4.7, bước 2).
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu khai báo của các route trong _routes().
import asyncio
import hmac
import json
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ..advisor import Advisor
from ..config import ConfigError, Settings
from ..dispatch import Dispatcher
from ..files import FilesClient, ServiceToken
from ..flowable import FlowableClient
from ..hasura import Actor, HasuraClient, HasuraError
from ..notify import Notifier
from ..ot import MAP_ROLES, TOKEN_HEADER, OtBridge, map_result
from ..parts import action_doc, action_error, deploy_processes, error_doc, every
from ..schemas import FormSchema, SchemaFileError
from ..sla import Deadlines
from ..workflow import Workflow, WorkflowError

log = logging.getLogger("svc_workflow")

# Thân yêu cầu đọc bằng tay để lỗi nào cũng trả đúng định dạng Action, nên khai cho tài liệu OpenAPI ở đây.
ACTION_DOC = action_doc({
    "200": {"description": "Kết quả của Action, đúng kiểu trả về khai trong db/metadata/actions.graphql"},
    "400": error_doc("Sai định dạng Action; dữ liệu văn bản đến, kết quả hoặc dữ liệu của việc không hợp lệ"),
    "401": error_doc("Thiếu hoặc sai X-Moc-Action-Secret: không phải Hasura gọi"),
    "403": error_doc("Vai trò không được dùng Action này, hoặc việc không giao cho người gọi"),
    "404": error_doc("Không có văn bản hoặc việc"),
    "409": error_doc("Văn bản đến trùng văn bản đã tiếp nhận, văn bản sai trạng thái, việc vừa có người khác "
                     "nhận, hoặc CSDL từ chối"),
    "500": error_doc("Lỗi không mong đợi; câu trả về có mã yêu cầu để tra nhật ký"),
    "503": error_doc("Chưa gọi được Flowable hoặc CSDL, thử lại sau"),
})


async def refused(request: Request, exc: WorkflowError) -> JSONResponse:
    # Lỗi nghiệp vụ ném ra khỏi route (vd /ot/notify, khai trả 204) → thân lỗi định dạng Action như action_error().
    # /actions/{name} tự bắt WorkflowError trước để ghi nhật ký kèm người gọi, nên không đi qua đây.
    return action_error(exc.status, exc.code, exc.message, exc.fields)


@dataclass
class Office:
    """Các thành phần của Văn phòng, dựng trên máy khách chung mà ``create_app`` truyền vào."""

    settings: Settings
    flowable: FlowableClient
    files: FilesClient
    workflow: Workflow
    dispatcher: Dispatcher
    deadlines: Deadlines
    advisor: Advisor | None
    ot: OtBridge | None

    @classmethod
    def build(
        cls,
        settings: Settings,
        hasura: HasuraClient,
        flowable: FlowableClient,
        notifier: Notifier,
        *,
        files: FilesClient | None = None,
        ot: OtBridge | None = None,
    ) -> Self:
        files = files or FilesClient(settings.files_url, ServiceToken(
            settings.keycloak_url, settings.realm, settings.directory_client_id, settings.directory_client_secret))
        try:
            intake = FormSchema.load(Path(settings.schemas_dir) / "van-ban-den.json")
        except SchemaFileError as exc:
            raise ConfigError(f"MOC_SCHEMAS_DIR: {exc}") from exc
        dispatcher = Dispatcher(hasura, files, notifier)
        workflow = Workflow(hasura, flowable, files, notifier=notifier, sla_duration=settings.sla_duration,
                            intake=intake, dispatcher=dispatcher)
        deadlines = Deadlines(hasura, flowable, notifier, sla_duration=settings.sla_duration)
        ot = ot or (OtBridge(hasura, notifier, settings.ngsi_url, secret=settings.action_secret,
                             threshold=settings.ot_threshold, notify_url=settings.ot_notify_url,
                             stale_min=settings.ot_stale_min)
                    if settings.ngsi_url else None)
        # F4.3: tác tử gợi ý giao việc nhận việc moc-goi-y của nhánh song song với bước chỉ đạo; không chạy thì nhánh
        # tự hết sau PT10M (timer boGoiY), văn bản vẫn tới lãnh đạo như thường
        advisor = Advisor(hasura, flowable, files, settings) if settings.suggest_poll_interval_s > 0 else None
        return cls(settings, flowable, files, workflow, dispatcher, deadlines, advisor, ot)

    def jobs(self) -> list[Coroutine[Any, Any, None]]:
        """Triển khai BPMN văn bản, rồi các vòng định kỳ của Văn phòng; chu kỳ 0 thì vòng đó không chạy."""
        settings = self.settings
        jobs = [deploy_processes(self.flowable, settings.processes_dir)]
        if settings.reconcile_interval_s > 0:
            jobs.append(every(settings.reconcile_interval_s, "office.process.reconciled", self.workflow.reconcile))
            jobs.append(every(settings.reconcile_interval_s, "office.document.overdue_notified",
                              self.deadlines.overdue_documents))
        if settings.dispatch_interval_s > 0:
            jobs.append(every(settings.dispatch_interval_s, "office.dispatch.reconciled", self.dispatcher.reconcile))
        if settings.sla_poll_interval_s > 0:
            jobs.append(every(settings.sla_poll_interval_s, "office.sla.jobs_handled", self.deadlines.run_jobs))
        if self.advisor is not None:
            jobs.append(every(settings.suggest_poll_interval_s, "office.assign.jobs_handled", self.advisor.run_jobs))
        if self.ot is not None and settings.ot_interval_s > 0:
            jobs.append(every(settings.ot_interval_s, "ot.subscriptions_ensured", self.ot.ensure_all))
        return jobs

    async def aclose(self) -> None:
        if self.ot is not None:
            await self.ot.aclose()
        await self.files.aclose()

    def install(self, app: FastAPI) -> None:
        app.state.workflow = self.workflow
        app.state.dispatcher = self.dispatcher
        app.state.deadlines = self.deadlines
        app.state.advisor = self.advisor
        app.state.ot = self.ot
        app.add_exception_handler(WorkflowError, refused)  # type: ignore[arg-type]
        self._routes(app)

    def _routes(self, app: FastAPI) -> None:
        # Khai thẳng trên app như các install() của svc-files, không qua app.include_router(APIRouter): FastAPI 0.143
        # gắn router con thành một mục _IncludedRouter trong app.routes, danh sách route sẽ khác trước (OpenAPI thì
        # không đổi). Thứ tự khai quyết thứ tự trong docs/api/openapi/svc-workflow.json
        settings, workflow, ot = self.settings, self.workflow, self.ot

        @app.post("/ot/notify/{tenant}", status_code=204,
                     summary="Nhận thông báo của subscription NGSI-LD: cảm biến vượt ngưỡng → dự thảo báo cáo sự cố "
                             "(F3.10)",
                     description="Chỉ context broker gọi, kèm header X-Moc-OT-Token của đơn vị (broker nhận token khi "
                                 "svc-workflow tạo subscription). Thân là Notification NGSI-LD (format normalized).",
                     responses={401: {"description": "Thiếu hoặc sai token của đơn vị"},
                                404: {"description": "Chưa cấu hình MOC_NGSI_URL"},
                                503: {"description": "Chưa ghi được CSDL, broker sẽ báo lỗi gửi"}})
        async def ot_notify(tenant: str, request: Request) -> Response:
            # Khai trả 204 nên chỉ có một return (204 không thân); lỗi ném WorkflowError cho refused() ở trên
            if ot is None:
                raise WorkflowError("not_found", "Chưa bật IT/OT (MOC_NGSI_URL)", 404)
            if not ot.check(tenant, request.headers.get(TOKEN_HEADER, "")):
                raise WorkflowError("unauthorized", "Sai token của đơn vị", 401)
            try:
                body = await request.json()
                if not isinstance(body, dict):
                    raise ValueError("không phải đối tượng JSON")
            except ValueError as exc:
                raise WorkflowError("bad_request", "Thông báo không phải Notification NGSI-LD") from exc
            try:
                await ot.handle(tenant, body)
            except ValueError as exc:
                raise WorkflowError("bad_request", "Thông báo không có danh sách thực thể") from exc
            except HasuraError as exc:
                log.warning(json.dumps({"event": "ot.alarm_failed", "tenant": tenant, "error": str(exc)},
                                       ensure_ascii=False))
                raise WorkflowError("unavailable", "Chưa ghi được dự thảo, thử lại sau", 503) from exc
            return Response(status_code=204)

        @app.post("/actions/{name}",
                     summary="Chạy một Hasura Action: receiveIncoming, registerIncoming, submitOutgoing, myTasks, "
                             "completeTask, otSensorMap",
                     openapi_extra=ACTION_DOC)
        async def action(name: str, request: Request) -> JSONResponse:
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
            except (ValueError, KeyError, TypeError):
                return action_error(400, "bad_request", "Yêu cầu không đúng định dạng Action")

            started = asyncio.get_running_loop().time()
            try:
                if name == "receiveIncoming" and actor.role == "clerk":
                    result: Any = await workflow.receive_incoming(actor, payload.get("data"))
                elif name == "registerIncoming" and actor.role == "clerk":
                    result = await workflow.register_incoming(actor, str(payload.get("documentId", "")))
                elif name == "submitOutgoing" and actor.role == "staff":
                    result = await workflow.submit_outgoing(
                        actor, str(payload.get("documentId", "")), str(payload.get("signerId", "")),
                    )
                elif name == "myTasks":
                    result = await workflow.my_tasks(actor)
                elif name == "otSensorMap" and actor.role in MAP_ROLES:
                    # sơ đồ cảm biến (F3.10): chỉ tenant NGSI-LD của đơn vị trong phiên; chưa bật IT/OT thì "off"
                    result = (await ot.sensor_map(actor.tenant_id) if ot is not None
                              else map_result("off", settings.ot_threshold, settings.ot_stale_min, datetime.now(UTC)))
                elif name == "completeTask":
                    result = await workflow.complete_task(
                        actor, str(payload.get("taskId", "")), str(payload.get("outcome", "")), payload.get("data"),
                    )
                else:
                    return action_error(403, "forbidden", "Vai trò không được dùng thao tác này")
            except WorkflowError as exc:
                log.info(json.dumps({"event": "office.action.rejected", "action": name, "code": exc.code,
                                     "fields": exc.fields, "user_id": actor.user_id, "request_id": actor.request_id}))
                return action_error(exc.status, exc.code, exc.message, exc.fields)
            except Exception:  # noqa: BLE001 — không để lộ chi tiết nội bộ cho client
                log.exception(json.dumps({"event": "office.action.failed", "action": name,
                                          "request_id": actor.request_id}))
                return action_error(500, "internal",
                                    "Lỗi không mong đợi; đã ghi nhật ký với mã " + (actor.request_id or "?"))
            log.info(json.dumps({
                "event": "office.action.done", "action": name, "user_id": actor.user_id,
                "tenant_id": str(actor.tenant_id), "request_id": actor.request_id,
                "ms": round((asyncio.get_running_loop().time() - started) * 1000),
            }))
            return JSONResponse(result)
