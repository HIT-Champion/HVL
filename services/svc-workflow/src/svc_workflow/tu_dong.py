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

"""Tự động hóa bằng Node-RED (#366): robot của flow báo người trong đơn vị theo vai trò (Action ``notifyFromFlow``).

Flow không chạy bằng tài khoản của người nào: mỗi đơn vị có một robot là client Keycloak lấy token bằng client
credentials. Token của robot chỉ có vai trò Hasura ``tu_dong`` (mặc định và duy nhất), ``x-hasura-tenant-id`` là đơn vị,
``x-hasura-user-id`` là tên client của robot (vd ``tu-dong-robot-cntt``) — không phải uuid, không có trong danh bạ.
Hasura chỉ cho vai trò ``tu_dong`` gọi ``notifyFromFlow`` (db/metadata/actions.graphql) rồi chuyển sang
``POST /actions/tu-dong/notifyFromFlow`` ở đây, kèm ``X-Moc-Action-Secret`` như mọi Action.

Action chỉ làm một việc: báo những người đang hoạt động của chính đơn vị robot, chọn theo vai trò (``roles``), không
theo tên người. Mọi lần đọc, ghi dùng vai trò service với đơn vị của phiên, nên văn bản của đơn vị khác coi như không có
(404). Văn bản hạn chế (F3.7) bị từ chối (403): flow không được gắn nó vào thông báo cho cả nhóm vai trò. Thông báo
kèm văn bản chỉ gửi cho ``director``, ``clerk`` — hai vai trò thấy mọi văn bản không hạn chế của đơn vị; vai trò khác
thì 422 trước khi đọc gì, kẻo trích yếu, số ký hiệu tới người không xem được văn bản.

Chống trùng: khóa ``flow:<robot>:<key>``, ``key`` do flow đặt (vd mã sự kiện nguồn). Flow chạy lại, Node-RED gửi lại
thì người đã có thông báo cùng khóa không nhận thêm; ``sent`` là số người vừa nhận. Thông báo loại ``flow.message``
mang phần văn bản như mọi thông báo (``brief_of``: trích yếu, số ký hiệu, độ khẩn, chiều), ``title``, ``text`` (nếu có)
và ``robot``; đi chuông và kênh ngoài như thông báo khác.

Nhật ký chỉ có đơn vị, robot, vai trò, số người nhận, mã văn bản, mã yêu cầu — không có tiêu đề, lời nhắn vì flow có
thể chép dữ liệu cá nhân vào đó (F4.4).
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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .hasura import Actor, HasuraClient, HasuraError
from .notify import Notifier, brief_of
from .parts import action_doc, action_error, error_doc

log = logging.getLogger("svc_workflow")

ROLE = "tu_dong"
KIND = "flow.message"
ROLES = ("director", "manager", "clerk", "staff", "tenant_admin")
# vai trò thấy mọi văn bản không hạn chế của đơn vị (office.document_visible, migration 1792281600200): thông báo kèm
# văn bản chỉ gửi cho họ, kẻo trích yếu, số ký hiệu lọt tới lãnh đạo phòng, chuyên viên, quản trị không xem được nó
DOCUMENT_READERS = ("director", "clerk")
MAX_ROLES = 5
MAX_TITLE = 120
MAX_TEXT = 1000
MAX_KEY = 200                       # notifications.key: 1–200 ký tự, gồm cả tiền tố flow:<robot>:
KEY = re.compile(r"[A-Za-z0-9._:-]+")
KEY_LENGTH = 100
# ký tự điều khiển C0, DEL, C1 và ký tự đảo hướng chữ (bidi: chữ hiện khác thứ tự thật, giả dạng được câu khác)
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
# như trên, trừ xuống dòng: lời nhắn giữ được nhiều dòng
TEXT_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")

DOCUMENT = """
query FlowDocument($id: uuid!) {
  office_documents_by_pk(id: $id) { id restricted summary symbol urgency direction }
}"""

FLOW_DOC = action_doc({
    "200": {"description": "NotifyFromFlowOutput {sent}: số người vừa nhận thông báo; người đã có thông báo cùng khóa "
                           "không tính (db/metadata/actions.graphql)"},
    "400": error_doc("Sai định dạng Action, hoặc đối số sai: extensions.fields chỉ trường sai và mã lỗi"),
    "401": error_doc("Thiếu hoặc sai X-Moc-Action-Secret: không phải Hasura gọi"),
    "403": error_doc("Không phải robot (vai trò tu_dong), hoặc văn bản hạn chế"),
    "404": error_doc("Không có văn bản này trong đơn vị của robot"),
    "500": error_doc("Lỗi không mong đợi; câu trả về có mã yêu cầu để tra nhật ký"),
    "503": error_doc("Chưa gọi được CSDL, thử lại sau"),
})
# khai ở responses của route chứ không trong openapi_extra: FastAPI khỏi thêm 422 HTTPValidationError của nó (route
# này không bao giờ trả), openapi_extra trộn vào sẽ thành một schema lai
DOC_422 = error_doc("Gửi kèm văn bản cho vai trò có thể không xem được nó: chỉ director, clerk "
                    "(extensions.fields.roles = document_readers_only)")


class BadInput(ValueError):
    """Đối số sai: trường, mã lỗi (tên từ khóa JSON Schema như form, schemas/README.md), câu tiếng Việt; 400, hoặc 422
    khi từng đối số đúng dạng nhưng ghép lại không được."""

    def __init__(self, field: str, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.field, self.code, self.message, self.status = field, code, message, status


class FlowError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class Notice:
    """Đối số của ``notifyFromFlow`` đã kiểm, làm sạch; ``key`` đã có tiền tố ``flow:<robot>:``."""

    roles: tuple[str, ...]
    title: str
    text: str | None
    document_id: str | None
    key: str


def one_line(value: str) -> str:
    """Một dòng: ký tự điều khiển thành dấu cách, gộp khoảng trắng."""
    return " ".join(CONTROL.sub(" ", value).split())


def lines(value: str) -> str:
    """Giữ xuống dòng ``\\n``; bỏ ``\\r`` và ký tự điều khiển khác, tab thành dấu cách; bỏ khoảng trắng hai đầu."""
    return TEXT_CONTROL.sub("", value.replace("\t", " ")).strip()


def _text(payload: dict[str, Any], field: str, *, required: bool = True) -> str | None:
    value = payload.get(field)
    if value is None and not required:
        return None
    if value is None:
        raise BadInput(field, "required", f"Thiếu {field}")
    if not isinstance(value, str):
        raise BadInput(field, "type", f"{field} phải là chuỗi")
    return value


def parse(payload: Any, robot: str) -> Notice:
    """Đối số của Action → ``Notice``; sai thì ném ``BadInput``."""
    if not isinstance(payload, dict):
        raise BadInput("input", "type", "Đối số của Action không đúng định dạng")
    roles = payload.get("roles")
    if roles is None:
        raise BadInput("roles", "required", "Thiếu danh sách vai trò nhận thông báo")
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise BadInput("roles", "type", "roles phải là danh sách tên vai trò")
    if not roles:
        raise BadInput("roles", "minItems", "Chọn ít nhất một vai trò nhận thông báo")
    if len(roles) > MAX_ROLES:
        raise BadInput("roles", "maxItems", f"Chọn nhiều nhất {MAX_ROLES} vai trò")
    if any(r not in ROLES for r in roles):
        raise BadInput("roles", "enum", f"Vai trò chỉ được là: {', '.join(ROLES)}")
    if len(set(roles)) != len(roles):
        raise BadInput("roles", "uniqueItems", "Mỗi vai trò chỉ ghi một lần")

    title = one_line(_text(payload, "title") or "")
    if not title:
        raise BadInput("title", "minLength", "Tiêu đề trống")
    if len(title) > MAX_TITLE:
        raise BadInput("title", "maxLength", f"Tiêu đề dài quá {MAX_TITLE} ký tự")

    text = _text(payload, "text", required=False)
    text = lines(text) if text is not None else None
    if text and len(text) > MAX_TEXT:
        raise BadInput("text", "maxLength", f"Lời nhắn dài quá {MAX_TEXT} ký tự")

    document_id = _text(payload, "document_id", required=False)
    if document_id is not None:
        try:
            document_id = str(uuid.UUID(document_id))
        except ValueError as exc:
            raise BadInput("document_id", "format", "document_id không phải uuid") from exc

    key = _text(payload, "key") or ""
    if not 1 <= len(key) <= KEY_LENGTH:
        raise BadInput("key", "minLength" if not key else "maxLength", f"Khóa chống trùng cần 1–{KEY_LENGTH} ký tự")
    if not KEY.fullmatch(key):
        raise BadInput("key", "pattern", "Khóa chống trùng chỉ gồm chữ không dấu, số và . _ : -")
    full = f"flow:{robot}:{key}"
    if len(full) > MAX_KEY:
        raise BadInput("key", "maxLength", f"Khóa chống trùng quá dài: cả tên robot không quá {MAX_KEY} ký tự")
    # từng đối số đã đúng dạng (400 xét trước); ghép lại: kèm văn bản thì chỉ vai trò thấy mọi văn bản của đơn vị
    if document_id is not None and any(r not in DOCUMENT_READERS for r in roles):
        raise BadInput("roles", "document_readers_only", "Thông báo kèm văn bản chỉ gửi được cho vai trò "
                       f"{' và '.join(DOCUMENT_READERS)}: vai trò khác có thể không xem được văn bản", 422)
    return Notice(tuple(roles), title, text or None, document_id, full)


@dataclass
class FlowNotices:
    """Action của robot tự động hóa, gắn vào app theo khuôn ``parts.Part``; không có việc nền."""

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

    async def notify(self, robot: Actor, notice: Notice) -> int:
        """Ghi, đẩy thông báo cho người có vai trò đã chọn trong đơn vị của robot → số người vừa nhận."""
        # vai trò service, đơn vị của phiên: chỉ thấy văn bản, người dùng của đơn vị robot; người làm là tên robot
        service = Actor(robot.user_id, robot.tenant_id, "service", None, robot.request_id)
        doc = None
        if notice.document_id:
            found = await self.hasura.as_service(service, DOCUMENT, {"id": notice.document_id})
            doc = found["office_documents_by_pk"]
            if doc is None:
                raise FlowError(404, "not_found", "Không có văn bản này trong đơn vị")
            if doc.get("restricted"):
                raise FlowError(403, "forbidden", "Văn bản hạn chế: flow không gửi kèm được")
        people = await self.notifier.people(service)
        recipients: set[str] = set().union(*(people.with_role(r) for r in notice.roles))
        data: dict[str, Any] = {**brief_of(doc), "title": notice.title, "robot": robot.user_id}
        if notice.text:
            data["text"] = notice.text
        sent = await self.notifier.send(service, recipients, KIND, notice.key, notice.document_id, data)
        log.info(json.dumps({"event": "tu_dong.notify", "tenant_id": str(robot.tenant_id), "robot": robot.user_id,
                             "roles": list(notice.roles), "sent": len(sent), "document_id": notice.document_id,
                             "request_id": robot.request_id}, ensure_ascii=False))
        return len(sent)

    def install(self, app: FastAPI) -> None:
        settings = self.settings

        @app.post("/actions/tu-dong/{name}",
                  summary="Robot của flow tự động hóa báo người trong đơn vị theo vai trò: notifyFromFlow (#366)",
                  responses={422: DOC_422}, openapi_extra=FLOW_DOC)
        async def tu_dong_action(name: str, request: Request) -> JSONResponse:
            given = request.headers.get("x-moc-action-secret", "")
            if not hmac.compare_digest(given.encode(), settings.action_secret.encode()):
                return action_error(401, "unauthorized", "Chỉ Hasura được gọi")
            try:
                body: dict[str, Any] = await request.json()
                session = {k.lower(): v for k, v in (body.get("session_variables") or {}).items()}
                payload = body.get("input")
                if (body.get("action") or {}).get("name") != name:
                    return action_error(400, "bad_request", "Tên Action không khớp đường dẫn")
                actor = Actor.from_session(session, request.state.request_id)
            except (ValueError, KeyError, TypeError, AttributeError):
                return action_error(400, "bad_request", "Yêu cầu không đúng định dạng Action")
            if actor.role != ROLE:
                return action_error(403, "forbidden", "Chỉ robot của flow tự động hóa (vai trò tu_dong) được gọi")
            if name != "notifyFromFlow":
                return action_error(400, "bad_request", "Không có Action này")
            try:
                notice = parse(payload, actor.user_id)
            except BadInput as exc:
                code = "bad_request" if exc.status == 400 else "invalid"
                return action_error(exc.status, code, exc.message, {exc.field: exc.code})
            try:
                sent = await self.notify(actor, notice)
            except FlowError as exc:
                return action_error(exc.status, exc.code, exc.message)
            except HasuraError as exc:
                log.warning(json.dumps({"event": "tu_dong.notify_failed", "robot": actor.user_id, "code": exc.code,
                                        "request_id": actor.request_id}))
                return action_error(503, "unavailable", "Chưa ghi được thông báo, thử lại sau")
            except Exception:  # noqa: BLE001 — không để lộ chi tiết nội bộ cho client
                log.exception(json.dumps({"event": "tu_dong.notify_failed", "robot": actor.user_id,
                                          "request_id": actor.request_id}))
                return action_error(500, "internal",
                                    "Lỗi không mong đợi; đã ghi nhật ký với mã " + (actor.request_id or "?"))
            return JSONResponse({"sent": sent})
