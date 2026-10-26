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

"""API quy trình cho ứng dụng cắm bằng manifest (#301), qua APISIX ở ``/api/workflow/{app}/…``.

- ``GET  forms/{formKey}``: JSON Schema của form, đúng tệp manifest khai (bản đang triển khai);
- ``POST processes/{processKey}`` ``{"data": {…}}``: kiểm theo form của sự kiện bắt đầu → 201 ``{"id"}``. Biến hệ
  thống ``tenantId``, ``departmentId``, ``initiator`` lấy từ token; form không khai được tên đó
  (``additionalProperties: false``) nên client không ghi đè được;
- ``GET  processes``: đơn người này đã gửi; ``data``: dữ liệu form của đơn và của các bước đã xong (vd quyết định);
- ``GET  tasks``: việc của ứng dụng này mà người này được giao hoặc thuộc nhóm ứng viên, cùng thuê ước; ``data``: dữ
  liệu form đã ghi vào quy trình tới lúc đó;
- ``POST tasks/{taskId}`` ``{"data": {…}}``: kiểm theo form của việc, nhận rồi hoàn thành → 204.

Lỗi kiểm: 422 ``{"errors": {trường: mã}}``, mã như ``schemas/README.md`` cộng ``x-moc-range`` (apps/forms.py). Lỗi
khác như svc-files: ``{"detail": {"code", "message"}}`` — 401 thiếu/sai token, 403 token không phải của client
``app-<tên>`` hoặc chưa gán đơn vị, 404 ứng dụng chưa cài hoặc đã gỡ, form/quy trình/việc không có hoặc không thuộc
ứng dụng, thuê ước, người này (không nói việc của người khác có tồn tại), 409 việc vừa có người khác nhận, 503 chưa
gọi được Flowable hoặc Keycloak.

``moc app remove`` tạm dừng mọi định nghĩa quy trình của ứng dụng (deploy.py) chứ không xóa deployment: lịch sử đơn
còn nguyên trong Flowable, còn API coi ứng dụng là đã gỡ (404) cho tới khi cài lại.

Form, mục lục đọc từ tài nguyên của đúng deployment (bundle.py), nhớ theo id deployment — nội dung một deployment
không bao giờ đổi. Việc của bản quy trình cũ kiểm theo form của chính bản đó.
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu khai báo của các route trong install().
import json
import logging
import os
from collections.abc import Coroutine, Mapping
from typing import Annotated, Any, Self

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings
from ..flowable import FlowableClient, FlowableError, Task
from .auth import AppUser, AuthError, TokenVerifier
from .bpmn import NAME
from .bundle import INDEX, deployment_prefix, form_resource
from .forms import RESERVED, AppForm

log = logging.getLogger("svc_workflow")
CACHE_LIMIT = 500           # mục lục, form, định nghĩa → deployment: bất biến, chỉ cần trần bộ nhớ
# Dữ liệu một form chỉ là vài trường đơn. Đọc quá thì dừng: không giữ cả thân (APISIX cho tới 64 MiB) trong bộ nhớ,
# không đưa chuỗi cỡ đó vào pattern của form (apps/forms.py)
MAX_BODY = 64 * 1024

DATA_BODY: dict[str, Any] = {"requestBody": {"required": True, "content": {"application/json": {"schema": {
    "type": "object", "required": ["data"],
    "properties": {"data": {"type": "object", "description": "Dữ liệu form: tên trường là tên biến của quy trình"}},
}}}}}
ERRORS_422 = {"description": "Dữ liệu chưa đúng form: {\"errors\": {trường: mã}} (schemas/README.md, x-moc-range)",
              "content": {"application/json": {"schema": {
                  "type": "object", "required": ["errors"],
                  "properties": {"errors": {"type": "object", "additionalProperties": {"type": "string"}}}}}}}
TOO_LARGE = {413: {"description": f"Thân yêu cầu lớn quá {MAX_BODY // 1024} KB"}}
COMMON = {401: {"description": "Thiếu hoặc sai token"},
          403: {"description": "Token không phải của client app-<tên>, hoặc tài khoản chưa gán đơn vị"},
          404: {"description": "Ứng dụng chưa cài hoặc đã gỡ"},
          503: {"description": "Chưa gọi được Flowable hoặc Keycloak, thử lại sau"}}


class FormInvalid(Exception):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__(", ".join(sorted(errors)))
        self.errors = errors


async def invalid(request: Request, exc: FormInvalid) -> JSONResponse:
    return JSONResponse({"errors": exc.errors}, status_code=422)


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def unavailable(exc: FlowableError) -> HTTPException:
    log.warning(json.dumps({"event": "app.workflow.flowable_failed", "error": str(exc)[:300]}, ensure_ascii=False))
    return _fail(503, "workflow_unavailable", "Chưa gọi được động cơ quy trình, thử lại sau")


def rest_variables(values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Biến ghi kiểu cho Flowable REST: chuỗi, số nguyên (long), số thực (double), đúng/sai giữ đúng kiểu."""
    out = []
    for name, value in values.items():
        if isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, int):
            kind = "long"
        elif isinstance(value, float):
            kind = "double"
        else:
            kind, value = "string", str(value)
        out.append({"name": name, "type": kind, "value": value})
    return out


def _variables(row: dict[str, Any]) -> dict[str, Any]:
    return {v["name"]: v.get("value") for v in row.get("variables") or []}


def app_data(variables: Mapping[str, Any]) -> dict[str, Any]:
    """Biến của một phiên quy trình trừ biến hệ thống: chỉ trường các form của ứng dụng (form nào cũng
    ``additionalProperties: false``, AppForm.variables chỉ ghi trường đã khai) — đơn, rồi quyết định của các bước."""
    return {k: v for k, v in variables.items() if k not in RESERVED}


class AppWorkflow:
    """Phần "quy trình của ứng dụng" gắn vào svc-workflow theo khuôn ``parts.Part`` — luôn bật, không phụ thuộc
    ``MOC_OFFICE_ENABLED``."""

    def __init__(self, flowable: FlowableClient, verifier: TokenVerifier | None) -> None:
        self.flowable = flowable
        self.verifier = verifier
        self._index: dict[str, dict[str, Any] | None] = {}
        self._forms: dict[tuple[str, str], AppForm | None] = {}
        self._deployment_of: dict[str, str | None] = {}

    @classmethod
    def build(cls, settings: Settings, flowable: FlowableClient, *, verifier: TokenVerifier | None = None,
              env: Mapping[str, str] = os.environ) -> Self:
        """issuer, JWKS như x-oidc của docker-compose.yml: iss là URL công khai của realm, khóa lấy qua mạng nội bộ.
        Đặt MOC_OIDC_ISSUER, MOC_OIDC_JWKS_URL để đổi; không có MOC_PUBLIC_URL thì API trả 503 (chưa cấu hình)."""
        issuer = env.get("MOC_OIDC_ISSUER") or (f"{settings.public_url}/realms/{settings.realm}"
                                                if settings.public_url else "")
        jwks = (env.get("MOC_OIDC_JWKS_URL")
                or f"{settings.keycloak_url}/realms/{settings.realm}/protocol/openid-connect/certs")
        return cls(flowable, verifier or (TokenVerifier(issuer, jwks) if issuer else None))

    def jobs(self) -> list[Coroutine[Any, Any, None]]:
        return []                    # gói quy trình do moc app install triển khai, không có việc nền

    async def aclose(self) -> None:
        return None                  # Flowable là máy khách chung, create_app đóng

    # --- đọc deployment ------------------------------------------------------------------------------------

    @staticmethod
    def _remember(cache: dict[Any, Any], key: Any, value: Any) -> Any:
        if len(cache) >= CACHE_LIMIT:
            cache.clear()
        cache[key] = value
        return value

    async def latest(self, app: str) -> str | None:
        """id deployment mới nhất của ứng dụng (bản moc app install vừa cài)."""
        prefix = deployment_prefix(app)
        rows = await self.flowable.deployments(f"{prefix}%", size=1)
        return next((r["id"] for r in rows if str(r.get("name", "")).startswith(prefix)), None)

    async def index(self, deployment_id: str) -> dict[str, Any] | None:
        if deployment_id not in self._index:
            raw = await self.flowable.resource(deployment_id, INDEX)
            self._remember(self._index, deployment_id, json.loads(raw) if raw else None)
        return self._index[deployment_id]

    async def form(self, deployment_id: str, form_key: str) -> AppForm | None:
        key = (deployment_id, form_key)
        if key not in self._forms:
            index = await self.index(deployment_id)
            raw = (await self.flowable.resource(deployment_id, form_resource(form_key))
                   if index and form_key in index.get("forms", []) else None)
            self._remember(self._forms, key, AppForm(json.loads(raw)) if raw else None)
        return self._forms[key]

    async def deployment_of(self, definition_id: str) -> str | None:
        if definition_id not in self._deployment_of:
            row = await self.flowable.definition(definition_id)
            self._remember(self._deployment_of, definition_id, row.get("deploymentId") if row else None)
        return self._deployment_of[definition_id]

    async def installed(self, app: str) -> tuple[str, list[dict[str, Any]]]:
        """Deployment mới nhất của ứng dụng và các định nghĩa đang chạy của nó. Chưa cài, hoặc đã gỡ (mọi định nghĩa
        tạm dừng) → 404, dù lịch sử đơn vẫn còn trong Flowable."""
        dep = await self.latest(app)
        rows = await self.flowable.definitions(deploymentId=dep) if dep else []
        live = [r for r in rows if r.get("deploymentId") == dep and not r.get("suspended")]
        if dep is None or not live:
            raise _fail(404, "app_not_installed", "Ứng dụng chưa cài hoặc đã gỡ")
        return dep, live

    # --- nghiệp vụ -----------------------------------------------------------------------------------------

    async def form_schema(self, app: str, form_key: str) -> dict[str, Any]:
        dep, _ = await self.installed(app)
        form = await self.form(dep, form_key) if form_key.startswith(f"{app}.") else None
        if form is None:
            raise _fail(404, "form_not_found", "Ứng dụng không có form này")
        return form.schema

    async def start(self, user: AppUser, app: str, key: str, data: Any) -> str:
        dep, live = await self.installed(app)
        index = await self.index(dep) if key.startswith(f"{app}.") else None
        start = ((index or {}).get("processes") or {}).get(key, {}).get("startForm")
        definition = next((r for r in live if r.get("key") == key), None) if start else None
        if definition is None:
            raise _fail(404, "process_not_found", "Ứng dụng không có quy trình này")
        form = await self.form(dep, start)
        if form is None:
            raise _fail(404, "form_not_found", "Không đọc được form bắt đầu của quy trình")
        errors = form.errors(data)
        if errors:
            raise FormInvalid(errors)
        system = {"tenantId": str(user.tenant_id), "departmentId": str(user.department_id or ""),
                  "initiator": user.user_id}
        return await self.flowable.start_definition(definition["id"],
                                                    rest_variables({**form.variables(data), **system}))

    async def my_processes(self, user: AppUser, app: str) -> list[dict[str, Any]]:
        dep, _ = await self.installed(app)
        index = await self.index(dep)
        rows: list[dict[str, Any]] = []
        for key in sorted(((index or {}).get("processes") or {})):
            rows += await self.flowable.historic_processes({"processDefinitionKey": key, "variables": [
                {"name": "initiator", "value": user.user_id, "operation": "equals", "type": "string"},
                {"name": "tenantId", "value": str(user.tenant_id), "operation": "equals", "type": "string"},
            ]})
        out = []
        for row in rows:
            variables = _variables(row)
            if (variables.get("initiator") != user.user_id or variables.get("tenantId") != str(user.tenant_id)
                    or not str(row.get("processDefinitionId", "")).startswith(f"{app}.")):
                continue
            out.append({
                "id": row["id"], "processKey": row["processDefinitionId"].split(":", 1)[0],
                "startedAt": row.get("startTime"), "endedAt": row.get("endTime"), "data": app_data(variables),
            })
        out.sort(key=lambda p: p["startedAt"] or "", reverse=True)
        return out

    async def tasks(self, user: AppUser, app: str) -> list[dict[str, Any]]:
        await self.installed(app)
        mine = {"processDefinitionKeyLike": f"{app}.%"}
        found: dict[str, Task] = {}
        queries = [{**mine, "assignee": user.user_id}]
        if user.groups:
            queries.append({**mine, "candidateGroupIn": user.groups, "unassigned": True})
        for query in queries:
            for task in await self.flowable.query_tasks(query):
                found[task.id] = task
        out = []
        for task in sorted(found.values(), key=lambda t: t.created_at):
            if not task.process_key.startswith(f"{app}.") or task.variables.get("tenantId") != str(user.tenant_id):
                continue
            out.append({
                "id": task.id, "name": task.name, "formKey": task.form_key, "processKey": task.process_key,
                "processId": task.process_instance_id, "createdAt": task.created_at,
                "dueAt": task.due_at, "data": app_data(task.variables),
            })
        return out

    async def _owned(self, user: AppUser, app: str, task_id: str) -> Task:
        task = await self.flowable.task(task_id)
        if (task is None or not task.process_key.startswith(f"{app}.")
                or task.variables.get("tenantId") != str(user.tenant_id)):
            raise _fail(404, "task_not_found", "Việc không còn hoặc không thuộc ứng dụng này")
        if task.assignee:
            mine = task.assignee == user.user_id
        else:
            mine = bool(set(await self.flowable.candidate_groups(task_id)) & set(user.groups))
        if not mine:
            raise _fail(404, "task_not_found", "Việc không còn hoặc không thuộc ứng dụng này")
        return task

    async def complete(self, user: AppUser, app: str, task_id: str, data: Any) -> None:
        await self.installed(app)
        task = await self._owned(user, app, task_id)
        dep = await self.deployment_of(task.process_definition_id)
        form = await self.form(dep, task.form_key) if dep else None
        if form is None:
            raise _fail(404, "form_not_found", "Không đọc được form của việc")
        errors = form.errors(data)
        if errors:
            raise FormInvalid(errors)
        claimed = False
        if not task.assignee:
            try:
                await self.flowable.claim(task_id, user.user_id)
            except FlowableError as exc:
                if exc.status == 409:
                    raise _fail(409, "task_taken", "Việc này vừa có người khác nhận") from exc
                raise unavailable(exc) from exc
            claimed = True
        try:
            await self.flowable.complete_typed(task_id, rest_variables(form.variables(data)))
        except FlowableError as exc:
            if claimed:
                try:
                    await self.flowable.claim(task_id, None)
                except FlowableError:
                    log.warning(json.dumps({"event": "app.workflow.unclaim_failed", "task_id": task_id}))
            if exc.status == 404:
                raise _fail(404, "task_not_found", "Việc không còn — có thể đã có người xử lý") from exc
            raise unavailable(exc) from exc

    # --- route ---------------------------------------------------------------------------------------------

    def install(self, app: FastAPI) -> None:
        app.add_exception_handler(FormInvalid, invalid)  # type: ignore[arg-type]
        bearer = HTTPBearer(auto_error=False)
        verifier = self.verifier

        # Hàm thường (không async): FastAPI chạy trong threadpool, lần tải JWKS đầu không chặn event loop
        def caller(app: str, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> AppUser:
            if creds is None:
                raise HTTPException(401, {"code": "missing_token", "message": "Thiếu token đăng nhập"},
                                    {"WWW-Authenticate": "Bearer"})
            if verifier is None:
                raise _fail(503, "not_configured", "Chưa cấu hình kiểm token (MOC_PUBLIC_URL hoặc MOC_OIDC_ISSUER)")
            if not NAME.fullmatch(app):
                raise _fail(404, "app_not_found", "Không có ứng dụng này")
            try:
                return verifier.verify(creds.credentials, app)
            except AuthError as exc:
                headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
                raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}, headers) from exc

        User = Annotated[AppUser, Depends(caller)]

        async def body_data(request: Request) -> Any:
            too_large = _fail(413, "too_large", f"Thân yêu cầu lớn quá {MAX_BODY // 1024} KB")
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_BODY:
                raise too_large
            raw = bytearray()
            async for chunk in request.stream():         # không có Content-Length (chunked): đếm khi đọc
                raw += chunk
                if len(raw) > MAX_BODY:
                    raise too_large
            try:
                body = json.loads(raw)
            except (ValueError, RecursionError) as exc:     # RecursionError: mảng lồng hàng vạn tầng
                raise _fail(400, "bad_request", 'Thân yêu cầu phải là JSON {"data": {…}}') from exc
            if not isinstance(body, dict):
                raise _fail(400, "bad_request", 'Thân yêu cầu phải là JSON {"data": {…}}')
            return body.get("data", {})

        def rid(request: Request) -> str:
            return getattr(request.state, "request_id", "")

        tags = ["Quy trình của ứng dụng"]

        @app.get("/api/workflow/{app}/forms/{form_key}", tags=tags, responses={**COMMON, 404: {
                     "description": "Ứng dụng chưa cài, đã gỡ hoặc không có form này"}},
                 summary="JSON Schema của một form, đúng tệp manifest khai")
        async def get_form(app: str, form_key: str, user: User) -> dict[str, Any]:
            try:
                return await self.form_schema(app, form_key)
            except FlowableError as exc:
                raise unavailable(exc) from exc

        @app.post("/api/workflow/{app}/processes/{process_key}", status_code=201, tags=tags, openapi_extra=DATA_BODY,
                  responses={**COMMON, 404: {"description": "Ứng dụng chưa cài, đã gỡ hoặc không có quy trình này"},
                             422: ERRORS_422, **TOO_LARGE},
                  summary="Bắt đầu quy trình với dữ liệu form bắt đầu")
        async def start_process(app: str, process_key: str, user: User, request: Request) -> dict[str, str]:
            data = await body_data(request)
            try:
                pid = await self.start(user, app, process_key, data)
            except FormInvalid as exc:
                log.info(json.dumps({"event": "app.workflow.rejected", "app": app, "process_key": process_key,
                                     "fields": exc.errors, "user_id": user.user_id, "request_id": rid(request)}))
                raise
            except FlowableError as exc:
                raise unavailable(exc) from exc
            log.info(json.dumps({"event": "app.workflow.started", "app": app, "process_key": process_key,
                                 "process_id": pid, "user_id": user.user_id, "tenant_id": str(user.tenant_id),
                                 "request_id": rid(request)}))
            return {"id": pid}

        @app.get("/api/workflow/{app}/processes", tags=tags, responses=COMMON,
                 summary="Đơn người này đã gửi qua ứng dụng, mới nhất trước")
        async def list_processes(app: str, user: User) -> list[dict[str, Any]]:
            try:
                return await self.my_processes(user, app)
            except FlowableError as exc:
                raise unavailable(exc) from exc

        @app.get("/api/workflow/{app}/tasks", tags=tags, responses=COMMON,
                 summary="Việc của ứng dụng giao cho người này hoặc nhóm của người này, cũ nhất trước")
        async def list_tasks(app: str, user: User) -> list[dict[str, Any]]:
            try:
                return await self.tasks(user, app)
            except FlowableError as exc:
                raise unavailable(exc) from exc

        @app.post("/api/workflow/{app}/tasks/{task_id}", status_code=204, tags=tags, openapi_extra=DATA_BODY,
                  responses={**COMMON,
                             404: {"description": "Ứng dụng đã gỡ; việc không còn hoặc không thuộc người này"},
                             409: {"description": "Việc vừa có người khác nhận"}, 422: ERRORS_422, **TOO_LARGE},
                  summary="Hoàn thành một việc với dữ liệu form của việc")
        async def complete_task(app: str, task_id: str, user: User, request: Request) -> Response:
            # Khai trả 204 nên chỉ có một return (204 không thân); lỗi ném ra cho FastAPI, invalid() ở trên
            data = await body_data(request)
            try:
                await self.complete(user, app, task_id, data)
            except FlowableError as exc:
                raise unavailable(exc) from exc
            log.info(json.dumps({"event": "app.workflow.task_completed", "app": app, "task_id": task_id,
                                 "user_id": user.user_id, "request_id": rid(request)}))
            return Response(status_code=204)
