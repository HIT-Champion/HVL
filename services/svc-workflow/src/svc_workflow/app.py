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

"""API HTTP của svc-workflow — chỉ Hasura gọi (Actions), không qua APISIX.

Hasura gửi ``{action, input, session_variables}``; biến phiên lấy từ JWT đã kiểm, nên thuê ước, người
dùng, vai trò không do client tự khai. Yêu cầu không mang đúng ``X-Moc-Action-Secret`` bị từ chối: trong
mạng nội bộ cũng không tin ai (zero-trust).

Chạy: ``uvicorn svc_workflow.app:create_app --factory``
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu khai báo trong create_app().
import asyncio
import hmac
import json
import logging
import os
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from . import __version__, pii
from .advisor import Advisor
from .channels import Router
from .config import ConfigError, Settings
from .directory import Directory
from .dispatch import Dispatcher
from .files import FilesClient, ServiceToken
from .flowable import FlowableClient, FlowableError
from .hasura import Actor, HasuraClient, HasuraError
from .notify import Notifier
from .openbao import with_secrets
from .ot import MAP_ROLES, TOKEN_HEADER, OtBridge, map_result
from .schemas import FormSchema, SchemaFileError
from .sla import Deadlines
from .workflow import Workflow, WorkflowError

log = logging.getLogger("svc_workflow")
# Mã yêu cầu nhận từ X-Request-Id: cùng luật với bước tách mã của Vector và make logs-tra (log tập trung F3.14)
REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")


def _setup_logging() -> None:
    """Mỗi dòng nhật ký là một đối tượng JSON trên stdout.

    F4.4: dòng của dịch vụ (kể cả traceback của ``office.action.failed``), uvicorn.error, uvicorn.access đều qua bộ
    che PII; dòng truy cập bỏ chuỗi truy vấn. Uvicorn dựng logger và handler của nó trước khi gọi factory."""
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    # ngoài nhánh trên: logger đã có handler từ trước (fixture của test) vẫn phải được che
    pii.install_log_redaction(log)


def _error_doc(description: str) -> dict[str, Any]:
    return {"description": description, "content": {"application/json": {"schema": {
        "type": "object",
        "required": ["message", "extensions"],
        "properties": {
            "message": {"type": "string", "description": "Câu tiếng Việt, Hasura chuyển nguyên cho người dùng"},
            "extensions": {"type": "object", "required": ["code"], "properties": {
                "code": {"type": "string"},
                "fields": {"type": "object", "additionalProperties": {"type": "string"},
                           "description": "Trường sai → mã lỗi, cùng mã với form (schemas/README.md)"},
            }},
        },
    }}}}


# Thân yêu cầu đọc bằng tay để lỗi nào cũng trả đúng định dạng Action, nên khai cho tài liệu OpenAPI ở đây.
ACTION_DOC: dict[str, Any] = {
    "parameters": [{
        "name": "X-Moc-Action-Secret", "in": "header", "required": True, "schema": {"type": "string"},
        "description": "Bí mật chung giữa Hasura và svc-workflow (MOC_ACTION_SECRET)",
    }],
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": {
            "type": "object",
            "required": ["action", "input", "session_variables"],
            "properties": {
                "action": {"type": "object", "required": ["name"],
                           "properties": {"name": {"type": "string", "description": "Trùng {name} trên đường dẫn"}}},
                "input": {"type": "object", "description": "Đối số của Action, khai trong db/metadata/actions.graphql"},
                "session_variables": {
                    "type": "object", "additionalProperties": {"type": "string"},
                    "description": "Biến phiên Hasura lấy từ JWT đã kiểm: x-hasura-role, x-hasura-user-id, "
                                   "x-hasura-tenant-id, x-hasura-department-id",
                },
            },
        }}},
    },
    "responses": {
        "200": {"description": "Kết quả của Action, đúng kiểu trả về khai trong db/metadata/actions.graphql"},
        "400": _error_doc("Sai định dạng Action; dữ liệu văn bản đến, kết quả hoặc dữ liệu của việc không hợp lệ"),
        "401": _error_doc("Thiếu hoặc sai X-Moc-Action-Secret: không phải Hasura gọi"),
        "403": _error_doc("Vai trò không được dùng Action này, hoặc việc không giao cho người gọi"),
        "404": _error_doc("Không có văn bản hoặc việc"),
        "409": _error_doc("Văn bản đến trùng văn bản đã tiếp nhận, văn bản sai trạng thái, việc vừa có người khác "
                          "nhận, hoặc CSDL từ chối"),
        "500": _error_doc("Lỗi không mong đợi; câu trả về có mã yêu cầu để tra nhật ký"),
        "503": _error_doc("Chưa gọi được Flowable hoặc CSDL, thử lại sau"),
    },
}


def _error(status: int, code: str, message: str, fields: dict[str, str] | None = None) -> JSONResponse:
    # Định dạng lỗi Hasura chuyển nguyên cho client: errors[0].message và extensions (code, fields)
    extensions: dict[str, Any] = {"code": code}
    if fields:
        extensions["fields"] = fields
    return JSONResponse({"message": message, "extensions": extensions}, status_code=status)


async def _deploy_processes(flowable: FlowableClient, directory: str) -> None:
    """Deploy BPMN khi khởi động; Flowable chưa lên thì thử lại, không chặn việc nhận yêu cầu."""
    delay = 2.0
    while True:
        try:
            deployed = await flowable.deploy_dir(directory)
            log.info(json.dumps({"event": "core.workflow.deployed", "deployments": deployed}))
            return
        except FlowableError as exc:
            log.warning(json.dumps({"event": "core.workflow.deploy_failed", "error": str(exc)}, ensure_ascii=False))
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


async def _every(interval_s: float, name: str, job) -> None:
    while True:
        try:
            count = await job()
            if count:
                log.info(json.dumps({"event": name, "count": count}))
        except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
            log.warning(json.dumps({"event": f"{name}_failed", "error": str(exc)}, ensure_ascii=False))
        await asyncio.sleep(interval_s)


def create_app(
    settings: Settings | None = None,
    *,
    hasura: HasuraClient | None = None,
    flowable: FlowableClient | None = None,
    directory: Directory | None = None,
    files: FilesClient | None = None,
    notifier: Notifier | None = None,
    ot: OtBridge | None = None,
) -> FastAPI:
    _setup_logging()
    settings = settings or Settings.from_env(with_secrets(os.environ))
    hasura = hasura or HasuraClient(settings.hasura_url, settings.hasura_admin_secret,
                                    timeout_s=settings.hasura_timeout_s)
    flowable = flowable or FlowableClient(settings.flowable_url, settings.flowable_user, settings.flowable_password)
    directory = directory or Directory(settings.keycloak_url, settings.realm, settings.directory_client_id,
                                       settings.directory_client_secret, hasura)
    files = files or FilesClient(settings.files_url, ServiceToken(
        settings.keycloak_url, settings.realm, settings.directory_client_id, settings.directory_client_secret))
    # kênh ngoài (email, webhook): None khi chưa cấu hình — chỉ có chuông trên web như trước
    router = Router.from_settings(hasura, settings) if notifier is None else getattr(notifier, "router", None)
    notifier = notifier or Notifier(hasura, settings.centrifugo_url, settings.centrifugo_api_key, router=router)
    try:
        intake = FormSchema.load(Path(settings.schemas_dir) / "van-ban-den.json")
    except SchemaFileError as exc:
        raise ConfigError(f"MOC_SCHEMAS_DIR: {exc}") from exc
    dispatcher = Dispatcher(hasura, files, notifier)
    workflow = Workflow(hasura, flowable, files, notifier=notifier, sla_duration=settings.sla_duration, intake=intake,
                        dispatcher=dispatcher)
    deadlines = Deadlines(hasura, flowable, notifier, sla_duration=settings.sla_duration)
    ot = ot or (OtBridge(hasura, notifier, settings.ngsi_url, secret=settings.action_secret,
                         threshold=settings.ot_threshold, notify_url=settings.ot_notify_url,
                         stale_min=settings.ot_stale_min)
                if settings.ngsi_url else None)
    # F4.3: tác tử gợi ý giao việc nhận việc moc-goi-y của nhánh song song với bước chỉ đạo; không chạy thì nhánh tự
    # hết sau PT10M (timer boGoiY), văn bản vẫn tới lãnh đạo như thường
    advisor = Advisor(hasura, flowable, files, settings) if settings.suggest_poll_interval_s > 0 else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        for warning in settings.warnings():     # cấu hình chạy được nhưng có phần không dùng được (vd kênh email)
            log.warning(json.dumps({"event": "config.warning", "message": warning}, ensure_ascii=False))
        tasks = [asyncio.create_task(_deploy_processes(flowable, settings.processes_dir))]
        if settings.directory_sync_interval_s > 0:
            tasks.append(asyncio.create_task(directory.run(settings.directory_sync_interval_s)))
        if settings.reconcile_interval_s > 0:
            tasks.append(asyncio.create_task(
                _every(settings.reconcile_interval_s, "office.process.reconciled", workflow.reconcile)))
            tasks.append(asyncio.create_task(
                _every(settings.reconcile_interval_s, "office.document.overdue_notified", deadlines.overdue_documents)))
        if settings.dispatch_interval_s > 0:
            tasks.append(asyncio.create_task(
                _every(settings.dispatch_interval_s, "office.dispatch.reconciled", dispatcher.reconcile)))
        if settings.sla_poll_interval_s > 0:
            tasks.append(asyncio.create_task(
                _every(settings.sla_poll_interval_s, "office.sla.jobs_handled", deadlines.run_jobs)))
        if advisor is not None:
            tasks.append(asyncio.create_task(
                _every(settings.suggest_poll_interval_s, "office.assign.jobs_handled", advisor.run_jobs)))
        if ot is not None and settings.ot_interval_s > 0:
            tasks.append(asyncio.create_task(_every(settings.ot_interval_s, "ot.subscriptions_ensured", ot.ensure_all)))
        if router is not None and settings.notify_interval_s > 0:
            tasks.append(asyncio.create_task(router.serve(settings.notify_interval_s)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await directory.aclose()
            if ot is not None:
                await ot.aclose()
            await notifier.aclose()
            if router is not None:
                await router.aclose()
            await files.aclose()
            await flowable.aclose()
            await hasura.aclose()

    app = FastAPI(
        title="Signet svc-workflow",
        version=__version__,
        description="Hasura Actions của Văn phòng điện tử. API nội bộ: chỉ Hasura gọi, không qua cổng APISIX; "
                    "ứng dụng gọi các Action này bằng GraphQL (docs/api/README.md).",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # APISIX gắn X-Request-Id (giữ mã client tự gửi), Hasura chuyển tiếp sang Action (forward_client_headers); gọi
        # thẳng (khi phát triển) thì tự sinh. Mã sai dạng (dài, dấu cách, ký tự điều khiển…) cũng thay bằng mã mới: mọi
        # mã trong nhật ký, sổ kiểm toán đều tra được. Trả lại ở header để người gọi tra nhật ký, log tập trung (F3.14)
        rid = request.headers.get("x-request-id", "")
        if not REQUEST_ID.fullmatch(rid):
            rid = uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    app.state.workflow = workflow
    app.state.dispatcher = dispatcher
    app.state.deadlines = deadlines
    app.state.advisor = advisor
    app.state.directory = directory
    app.state.ot = ot
    app.state.router = router

    @app.exception_handler(WorkflowError)
    async def refused(request: Request, exc: WorkflowError) -> JSONResponse:
        # Lỗi nghiệp vụ ném ra khỏi route (vd /ot/notify, khai trả 204) → thân lỗi định dạng Action như _error().
        # /actions/{name} tự bắt WorkflowError trước để ghi nhật ký kèm người gọi, nên không đi qua đây.
        return _error(exc.status, exc.code, exc.message, exc.fields)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        checks = {"hasura": await hasura.ping(), "flowable": await flowable.ping()}
        ok = all(checks.values())
        return JSONResponse({"status": "ok" if ok else "unavailable", "checks": checks}, status_code=200 if ok else 503)

    @app.post("/ot/notify/{tenant}", status_code=204,
              summary="Nhận thông báo của subscription NGSI-LD: cảm biến vượt ngưỡng → dự thảo báo cáo sự cố (F3.10)",
              description="Chỉ context broker gọi, kèm header X-Moc-OT-Token của đơn vị (broker nhận token khi "
                          "svc-workflow tạo subscription). Thân là Notification NGSI-LD (format normalized).",
              responses={401: {"description": "Thiếu hoặc sai token của đơn vị"},
                         404: {"description": "Chưa cấu hình MOC_NGSI_URL"},
                         503: {"description": "Chưa ghi được CSDL, broker sẽ báo lỗi gửi"}})
    async def ot_notify(tenant: str, request: Request) -> Response:
        # Khai trả 204 nên chỉ có một return (204 không thân); lỗi ném WorkflowError cho bộ xử lý chung ở trên
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
            return _error(401, "unauthorized", "Chỉ Hasura được gọi")
        try:
            body: dict[str, Any] = await request.json()
            session = {k.lower(): v for k, v in (body.get("session_variables") or {}).items()}
            payload = body.get("input") or {}
            if (body.get("action") or {}).get("name") != name:
                return _error(400, "bad_request", "Tên Action không khớp đường dẫn")
            actor = Actor.from_session(session, request.state.request_id)
        except (ValueError, KeyError, TypeError):
            return _error(400, "bad_request", "Yêu cầu không đúng định dạng Action")

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
                # sơ đồ cảm biến (F3.10): chỉ tenant NGSI-LD của đơn vị trong phiên; chưa bật IT/OT thì trạng thái "off"
                result = (await ot.sensor_map(actor.tenant_id) if ot is not None
                          else map_result("off", settings.ot_threshold, settings.ot_stale_min, datetime.now(UTC)))
            elif name == "completeTask":
                result = await workflow.complete_task(
                    actor, str(payload.get("taskId", "")), str(payload.get("outcome", "")), payload.get("data"),
                )
            else:
                return _error(403, "forbidden", "Vai trò không được dùng thao tác này")
        except WorkflowError as exc:
            log.info(json.dumps({"event": "office.action.rejected", "action": name, "code": exc.code,
                                 "fields": exc.fields, "user_id": actor.user_id, "request_id": actor.request_id}))
            return _error(exc.status, exc.code, exc.message, exc.fields)
        except Exception:  # noqa: BLE001 — không để lộ chi tiết nội bộ cho client
            log.exception(json.dumps({"event": "office.action.failed", "action": name, "request_id": actor.request_id}))
            return _error(500, "internal", "Lỗi không mong đợi; đã ghi nhật ký với mã " + (actor.request_id or "?"))
        log.info(json.dumps({
            "event": "office.action.done", "action": name, "user_id": actor.user_id,
            "tenant_id": str(actor.tenant_id), "request_id": actor.request_id,
            "ms": round((asyncio.get_running_loop().time() - started) * 1000),
        }))
        return JSONResponse(result)

    return app
