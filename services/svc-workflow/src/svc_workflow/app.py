# Copyright 2026 Mộc Team
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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings
from .directory import Directory
from .flowable import FlowableClient, FlowableError
from .hasura import Actor, HasuraClient
from .workflow import Workflow, WorkflowError

log = logging.getLogger("svc_workflow")


def _setup_logging() -> None:
    """Mỗi dòng nhật ký là một đối tượng JSON trên stdout."""
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False


def _error(status: int, code: str, message: str) -> JSONResponse:
    # Định dạng lỗi Hasura chuyển nguyên cho client: errors[0].message và extensions.code
    return JSONResponse({"message": message, "extensions": {"code": code}}, status_code=status)


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
) -> FastAPI:
    _setup_logging()
    settings = settings or Settings.from_env()
    hasura = hasura or HasuraClient(settings.hasura_url, settings.hasura_admin_secret,
                                    timeout_s=settings.hasura_timeout_s)
    flowable = flowable or FlowableClient(settings.flowable_url, settings.flowable_user, settings.flowable_password)
    directory = directory or Directory(settings.keycloak_url, settings.realm, settings.directory_client_id,
                                       settings.directory_client_secret, hasura)
    workflow = Workflow(hasura, flowable, sla_duration=settings.sla_duration)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks = [asyncio.create_task(_deploy_processes(flowable, settings.processes_dir))]
        if settings.directory_sync_interval_s > 0:
            tasks.append(asyncio.create_task(directory.run(settings.directory_sync_interval_s)))
        if settings.reconcile_interval_s > 0:
            tasks.append(asyncio.create_task(
                _every(settings.reconcile_interval_s, "office.process.reconciled", workflow.reconcile)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await directory.aclose()
            await flowable.aclose()
            await hasura.aclose()

    app = FastAPI(title="Mộc svc-workflow", version=__version__, lifespan=lifespan)
    app.state.workflow = workflow
    app.state.directory = directory

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        checks = {"hasura": await hasura.ping(), "flowable": await flowable.ping()}
        ok = all(checks.values())
        return JSONResponse({"status": "ok" if ok else "unavailable", "checks": checks}, status_code=200 if ok else 503)

    @app.post("/actions/{name}")
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
            actor = Actor.from_session(session, request.headers.get("x-request-id", ""))
        except (ValueError, KeyError, TypeError):
            return _error(400, "bad_request", "Yêu cầu không đúng định dạng Action")

        started = asyncio.get_running_loop().time()
        try:
            if name == "registerIncoming" and actor.role == "clerk":
                result: Any = await workflow.register_incoming(actor, str(payload.get("documentId", "")))
            elif name == "myTasks":
                result = await workflow.my_tasks(actor)
            elif name == "completeTask":
                result = await workflow.complete_task(
                    actor, str(payload.get("taskId", "")), str(payload.get("outcome", "")), payload.get("data"),
                )
            else:
                return _error(403, "forbidden", "Vai trò không được dùng thao tác này")
        except WorkflowError as exc:
            log.info(json.dumps({"event": "office.action.rejected", "action": name, "code": exc.code,
                                 "user_id": actor.user_id, "request_id": actor.request_id}))
            return _error(exc.status, exc.code, exc.message)
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
