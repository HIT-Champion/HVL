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

"""Khuôn gắn một phần nghiệp vụ vào svc-workflow, trên phần chung (Hasura, Flowable, danh bạ, thông báo).

Một phần (vd Văn phòng điện tử, ``office/api.py``) làm ba việc, ``create_app`` (app.py) gọi cho từng phần đang bật:

- ``install(app)``: gắn route, trạng thái, bộ xử lý lỗi của nó vào app. Route khai thẳng trên app (như Văn phòng)
  hay ``app.include_router(APIRouter)`` đều được; cách sau để lại một mục ``_IncludedRouter`` trong ``app.routes``
  thay cho từng ``APIRoute`` (FastAPI 0.143);
- ``jobs()``: việc nền chạy suốt vòng đời app (triển khai BPMN, vòng định kỳ), app tự hủy khi dừng;
- ``aclose()``: đóng máy khách riêng của nó, sau khi việc nền đã dừng.

Ở đây còn các mảnh phần nào cũng dùng: vòng định kỳ, triển khai BPMN có thử lại, định dạng lỗi của Hasura Action.
Mô-đun không biết phần cụ thể nào.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Protocol

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .flowable import FlowableClient, FlowableError

log = logging.getLogger("svc_workflow")


class Part(Protocol):
    """Một phần nghiệp vụ gắn vào app (xem docstring của mô-đun)."""

    def install(self, app: FastAPI) -> None: ...

    def jobs(self) -> list[Coroutine[Any, Any, None]]: ...

    async def aclose(self) -> None: ...


def error_doc(description: str) -> dict[str, Any]:
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


def action_doc(responses: dict[str, Any]) -> dict[str, Any]:
    """``openapi_extra`` của một route Hasura Action: header bí mật, thân ``{action, input, session_variables}``."""
    return {
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
                    "action": {"type": "object", "required": ["name"], "properties": {
                        "name": {"type": "string", "description": "Trùng {name} trên đường dẫn"}}},
                    "input": {"type": "object",
                              "description": "Đối số của Action, khai trong db/metadata/actions.graphql"},
                    "session_variables": {
                        "type": "object", "additionalProperties": {"type": "string"},
                        "description": "Biến phiên Hasura lấy từ JWT đã kiểm: x-hasura-role, x-hasura-user-id, "
                                       "x-hasura-tenant-id, x-hasura-department-id",
                    },
                },
            }}},
        },
        "responses": responses,
    }


def action_error(status: int, code: str, message: str, fields: dict[str, str] | None = None) -> JSONResponse:
    # Định dạng lỗi Hasura chuyển nguyên cho client: errors[0].message và extensions (code, fields)
    extensions: dict[str, Any] = {"code": code}
    if fields:
        extensions["fields"] = fields
    return JSONResponse({"message": message, "extensions": extensions}, status_code=status)


async def deploy_processes(flowable: FlowableClient, directory: str) -> None:
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


async def every(interval_s: float, name: str, job: Callable[[], Awaitable[Any]]) -> None:
    while True:
        try:
            count = await job()
            if count:
                log.info(json.dumps({"event": name, "count": count}))
        except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
            log.warning(json.dumps({"event": f"{name}_failed", "error": str(exc)}, ensure_ascii=False))
        await asyncio.sleep(interval_s)
