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

``create_app`` dựng phần chung (Hasura, Flowable, danh bạ, thông báo và kênh ngoài, ``/healthz``, ``/readyz``) rồi gắn
từng phần nghiệp vụ đang bật theo khuôn của ``parts.py``. Hiện có một phần: Văn phòng điện tử (``office/api.py``),
tắt bằng ``MOC_OFFICE_ENABLED=false``.

Chạy: ``uvicorn svc_workflow.app:create_app --factory``
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu khai báo trong create_app().
import asyncio
import json
import logging
import os
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from . import __version__, pii
from .channels import Router
from .config import Settings
from .directory import Directory
from .files import FilesClient
from .flowable import FlowableClient
from .hasura import HasuraClient
from .notify import Notifier
from .office.api import Office
from .openbao import with_secrets
from .ot import OtBridge
from .parts import Part

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
    # kênh ngoài (email, webhook): None khi chưa cấu hình — chỉ có chuông trên web như trước
    router = Router.from_settings(hasura, settings) if notifier is None else getattr(notifier, "router", None)
    notifier = notifier or Notifier(hasura, settings.centrifugo_url, settings.centrifugo_api_key, router=router)
    # Phần nghiệp vụ trên phần chung, gắn route theo thứ tự trong danh sách. Thêm một phần (route, việc nền riêng):
    # viết lớp theo khuôn parts.Part như office.api.Office, dựng ở đây rồi thêm vào parts
    office = (Office.build(settings, hasura, flowable, notifier, files=files, ot=ot)
              if settings.office_enabled else None)
    parts: list[Part] = [office] if office is not None else []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        for warning in settings.warnings():     # cấu hình chạy được nhưng có phần không dùng được (vd kênh email)
            log.warning(json.dumps({"event": "config.warning", "message": warning}, ensure_ascii=False))
        # vòng của phần chung: đồng bộ danh bạ Keycloak → core.users, gửi thông báo qua kênh ngoài
        jobs: list[Coroutine[Any, Any, None]] = []
        if settings.directory_sync_interval_s > 0:
            jobs.append(directory.run(settings.directory_sync_interval_s))
        if router is not None and settings.notify_interval_s > 0:
            jobs.append(router.serve(settings.notify_interval_s))
        for part in parts:
            jobs += part.jobs()
        tasks = [asyncio.create_task(job) for job in jobs]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for part in reversed(parts):
                await part.aclose()
            await directory.aclose()
            await notifier.aclose()
            if router is not None:
                await router.aclose()
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

    app.state.directory = directory
    app.state.router = router
    app.state.office = office

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        checks = {"hasura": await hasura.ping(), "flowable": await flowable.ping()}
        ok = all(checks.values())
        return JSONResponse({"status": "ok" if ok else "unavailable", "checks": checks}, status_code=200 if ok else 503)

    # sau /healthz, /readyz như trước: thứ tự route quyết thứ tự trong docs/api/openapi/svc-workflow.json
    for part in parts:
        part.install(app)
    return app
