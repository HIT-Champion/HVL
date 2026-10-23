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

"""Nghiệp vụ của các Action: tiếp nhận, vào sổ, trình văn bản đi, hộp việc, hoàn thành việc, đối soát.

Thứ tự ghi khi hoàn thành một việc: kiểm quyền và dữ liệu → nhận việc (claim) trong Flowable → ghi
PostgreSQL trong một giao dịch, kèm sự kiện mang ``task_id`` → hoàn thành việc trong Flowable. Gọi lại sau
lỗi mạng: sự kiện có ``task_id`` đã có thì bỏ qua bước ghi, chỉ hoàn thành nốt trong Flowable — không giao
việc hai lần (docs/mo-hinh-du-lieu.md §4.1, "idempotent theo taskId"). Hai lần gọi chen nhau (bấm lại khi chờ lâu)
chạy lần lượt; CSDL còn chặn lần ghi thứ hai bằng chỉ mục duy nhất theo ``task_id``. Vào sổ, trình văn bản đi cũng
một văn bản một lượt, và chỉ gắn quy trình khi văn bản chưa có — không khởi chạy hai quy trình cho một văn bản.

Sau mỗi bước, người phải làm bước kế tiếp nhận thông báo (F2.5, notify.py). Thông báo gửi sau khi bước đã ghi
xong và không bao giờ làm hỏng bước đó: lỗi chỉ ghi nhật ký. Văn bản đi có đơn vị nhận trong hệ thống thì sau khi
phát hành được chuyển sang các đơn vị đó (F3.12, dispatch.py) — cũng không bao giờ làm hỏng bước phát hành.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import secrets
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .files import FilesClient, FilesError
from .flowable import FlowableClient, FlowableError, Task
from .forms import FORMS, ChiDao, Note, PhanCong, PhatHanh, XuLy
from .hasura import (
    BRIEF,
    CLAIM_PROCESS,
    DISPATCH_UNITS,
    DOCUMENT,
    NUMBER_OUTGOING,
    OPEN_ASSIGNMENTS,
    OUTGOING,
    PROCESS_OF,
    REGISTER_INCOMING,
    SHARE,
    TASK_DONE,
    UNLINKED,
    USER,
    VISIBLE,
    Actor,
    HasuraClient,
    HasuraError,
)
from .notify import Notifier, People, brief_of, load_people, task_people
from .schemas import FormSchema

if TYPE_CHECKING:
    from .dispatch import Dispatcher

PROCESS_IN = "van-ban-den"
PROCESS_OUT = "van-ban-di"
BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
URGENCY_RANK = {"hoa_toc": 3, "thuong_khan": 2, "khan": 1, "normal": 0}
SYSTEM_ACTOR = "svc-workflow"

log = logging.getLogger("svc_workflow")


class WorkflowError(Exception):
    """Lỗi trả về cho bên gọi (Hasura, context broker): mã máy đọc + câu tiếng Việt."""

    def __init__(self, code: str, message: str, status: int = 400, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields  # trường → mã lỗi, cùng mã với form (schemas/README.md)


# Tên ràng buộc trong CSDL → câu cho người dùng (db/README.md: "Đặt tên cho ràng buộc check")
CONSTRAINT_MESSAGES = {
    "documents_due_after_registered": "Hạn giải quyết không được trước ngày vào sổ",
    "documents_in_identity": "Văn bản đến phải có số ký hiệu, cơ quan ban hành và ngày ban hành",
    "documents_in_dedup": "Văn bản này đã được tiếp nhận: trùng cơ quan ban hành, số ký hiệu và ngày ban hành",
    "documents_in_symbol": "Số, ký hiệu tối đa 50 ký tự, một dòng, không có khoảng trắng ở đầu hoặc cuối",
    "documents_in_issuer": "Cơ quan ban hành tối đa 200 ký tự, một dòng, không có khoảng trắng ở đầu hoặc cuối",
    "documents_in_summary": "Trích yếu không được có khoảng trắng ở đầu hoặc cuối",
    "documents_in_dates": "Ngày ban hành không được sau ngày tiếp nhận; hạn giải quyết không được trước ngày ban hành",
    "documents_summary_check": "Trích yếu cần 10–500 ký tự",
    "documents_type_code_fkey": "Không có loại văn bản này",
    "assignments_one_lead": "Văn bản đã có nơi chủ trì",
    "documents_body_length": "Nội dung văn bản dài quá 20.000 ký tự",
    "documents_out_issued_complete": "Văn bản chưa đủ số, ký hiệu, ngày ban hành, người ký để phát hành",
    "document_files_sealed": "Văn bản hạn chế chỉ nhận tệp tải lên ở chế độ hạn chế (đã mã hóa), và ngược lại",
    "documents_restricted_sealed": "Văn bản đã có tệp nên không đổi được chế độ hạn chế",
    "documents_restricted_private": "Văn bản hạn chế không công khai trích yếu ở trang tra cứu",
    "document_events_task_once": "Việc này đã được ghi ở một lần gọi khác",
    # liên thông trong hệ thống (F3.12, migration 1792281601800): ràng buộc check và trigger chuẩn hóa đơn vị nhận
    "documents_restricted_local": "Văn bản hạn chế không gửi liên thông trong hệ thống",
    "documents_recipient_units": "Đơn vị nhận trong hệ thống không hợp lệ: chỉ văn bản đi gửi liên thông, tới đơn vị "
                                 "khác có trong hệ thống, và chỉ đổi được khi văn bản còn là dự thảo",
}

# Chỉ mục duy nhất theo task_id của sự kiện: một việc Flowable chỉ ghi dữ liệu một lần (migration 1792281601700)
TASK_ONCE = "document_events_task_once"

RESTRICTED_NOT_SEALED = "Văn bản hạn chế chỉ nhận tệp tải lên ở chế độ hạn chế (đã mã hóa)"
SEALED_NOT_RESTRICTED = "Tệp đã mã hóa chỉ gắn được vào văn bản hạn chế"
RESTRICTED_PUBLIC = CONSTRAINT_MESSAGES["documents_restricted_private"]
RESTRICTED_LOCAL = CONSTRAINT_MESSAGES["documents_restricted_local"]



class _Turns:
    """Mỗi khóa một lượt: hai lần gọi cùng văn bản hay cùng việc (bấm đúp, bấm lại khi chờ lâu, job đối soát) chạy
    lần lượt, lần sau thấy những gì lần trước đã ghi. Chỉ trong một tiến trình — svc-workflow chạy một tiến trình;
    nhiều bản sao thì CSDL vẫn chặn ghi đôi (giành process_id, chỉ mục document_events_task_once), chỉ không chặn
    được việc làm thừa trước lúc ghi (dựng PDF phát hành, khởi chạy quy trình rồi hủy)."""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}

    @contextlib.asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        lock, waiting = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, waiting + 1)
        try:
            async with lock:
                yield
        finally:
            lock, waiting = self._locks[key]
            if waiting == 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, waiting - 1)


def new_verify_code() -> str:
    """Mã tra cứu in cạnh mã QR: 10 ký tự base32 ngẫu nhiên (50 bit) — không đoán, không liệt kê được."""
    return "".join(secrets.choice(BASE32) for _ in range(10))


def _db_error(exc: HasuraError) -> WorkflowError:
    text = str(exc)
    for name, message in CONSTRAINT_MESSAGES.items():
        if name in text:
            return WorkflowError("constraint", message, 409)
    if exc.code in {"constraint-violation", "data-exception"}:
        return WorkflowError("rejected", text, 409)
    return WorkflowError("database_unavailable", "Chưa ghi được vào cơ sở dữ liệu, thử lại sau", 503)


@dataclass(frozen=True)
class Plan:
    """Việc cần ghi khi hoàn thành một task: một mutation (một giao dịch) và biến cho Flowable.

    prepare: việc chạy sau khi đã nhận task, ngay trước mutation, trả thêm biến cho mutation — dùng khi phát
    hành (cấp số, dựng PDF), để không dựng PDF cho một task người khác đã nhận.
    note: ý kiến kèm theo, ghi vào thông báo việc kế tiếp (lý do trả lại dự thảo).
    after: thông báo thêm sau khi Flowable đã chuyển bước (văn bản đã phát hành, đã xử lý xong).
    """

    mutation: str
    variables: dict[str, Any]
    flow: dict[str, Any]
    prepare: Callable[[], Awaitable[dict[str, Any]]] | None = None
    note: str | None = None
    after: Callable[[], Awaitable[None]] | None = None


DIRECT = """
mutation ChiDao($doc: uuid!, $due: date, $lead: office_assignments_insert_input!,
                $supports: [office_assignments_insert_input!]!, $event: office_document_events_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $doc}, _set: {status: "in_progress", due_on: $due}) { id }
  insert_office_assignments_one(object: $lead) { id }
  insert_office_assignments(objects: $supports) { affected_rows }
  insert_office_document_events_one(object: $event) { id }
}"""

FILE = """
mutation Luu($doc: uuid!, $event: office_document_events_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $doc}, _set: {status: "done"}) { id }
  insert_office_document_events_one(object: $event) { id }
}"""

ASSIGN = """
mutation PhanCong($child: office_assignments_insert_input!, $event: office_document_events_insert_input!) {
  insert_office_assignments_one(object: $child) { id }
  insert_office_document_events_one(object: $event) { id }
}"""

# văn bản trước, giao việc sau: khóa dòng văn bản trước khi trigger sổ kiểm toán giữ core.audit_head — cùng thứ tự với
# lúc tác tử gợi ý giao việc (F4.3) khóa văn bản căn cứ rồi mới ghi sổ, nên hai bên không chờ vòng nhau (deadlock)
PROCESSED = """
mutation XuLy($ids: [uuid!]!, $note: String!, $now: timestamptz!, $doc: uuid!,
              $event: office_document_events_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $doc}, _set: {status: "done"}) { id }
  update_office_assignments(where: {id: {_in: $ids}}, _set: {status: "done", result_note: $note, completed_at: $now}) {
    affected_rows
  }
  insert_office_document_events_one(object: $event) { id }
}"""

SUBMIT = """
mutation Trinh($doc: uuid!, $set: office_documents_set_input!, $event: office_document_events_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $doc}, _set: $set) { id }
  insert_office_document_events_one(object: $event) { id }
}"""

SET_STATUS = """
mutation DoiTrangThai($doc: uuid!, $status: String!, $event: office_document_events_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $doc}, _set: {status: $status}) { id }
  insert_office_document_events_one(object: $event) { id }
}"""

EVENT_ONLY = """
mutation GhiSuKien($event: office_document_events_insert_input!) {
  insert_office_document_events_one(object: $event) { id }
}"""

ISSUE = """
mutation PhatHanh($doc: uuid!, $sha: bytea!, $public: Boolean!, $file: office_document_files_insert_input!,
                  $event: office_document_events_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $doc},
                                _set: {status: "issued", content_sha256: $sha, is_public: $public}) { id }
  insert_office_document_files_one(object: $file) { file_id }
  insert_office_document_events_one(object: $event) { id }
}"""

# Tiếp nhận: những điều schema không biết mà CSDL biết — loại văn bản có thật, tệp do chính người này tải lên
# (đã qua ClamAV mới có dòng trong core.files), chưa có văn bản trùng (kể cả văn bản hạn chế văn thư không thấy)
INTAKE_LOOKUP = """
query IntakeLookup($type: String!, $files: [uuid!]!, $user: String!, $symbol: String!, $issuer: String!,
                   $issued: date!) {
  office_document_types_by_pk(code: $type) { code }
  core_files(where: {id: {_in: $files}, created_by: {_eq: $user}}) { id encrypted }
  office_documents(where: {direction: {_eq: "in"}, status: {_neq: "cancelled"}, symbol: {_eq: $symbol},
                           issuer_name: {_ilike: $issuer}, issued_on: {_eq: $issued}}, limit: 1) { id }
}"""

# Cột văn thư được đặt khi tiếp nhận: đúng các thuộc tính của schemas/van-ban-den.json trừ file_ids. Thêm thuộc
# tính vào schema thì phải thêm ở đây (test_intake kiểm), không thì một thuộc tính mới như register_number,
# is_public thành cột văn thư tự đặt được.
INTAKE_COLUMNS = ("type_code", "symbol", "issuer_name", "issued_on", "summary", "urgency", "due_on", "restricted")

RECEIVE = """
mutation TiepNhan($doc: office_documents_insert_input!) {
  insert_office_documents_one(object: $doc) { id }
}"""

DEPARTMENT_MANAGERS = """
query Managers($dept: uuid!) {
  office_departments_by_pk(id: $dept) { id }
  core_users(where: {department_id: {_eq: $dept}, role: {_eq: "manager"}, enabled: {_eq: true}}) { id }
}"""


class Workflow:
    def __init__(self, hasura: HasuraClient, flowable: FlowableClient, files: FilesClient | None = None, *,
                 notifier: Notifier | None = None, sla_duration: str = "PT24H",
                 intake: FormSchema | None = None, dispatcher: Dispatcher | None = None) -> None:
        self.hasura = hasura
        self.flowable = flowable
        self.files = files
        self.notifier = notifier
        self.sla_duration = sla_duration
        self.intake = intake
        self.dispatcher = dispatcher
        # một sổ lượt chung với liên thông: khóa "dispatch:<id>" nằm cạnh "doc:<id>", "task:<id>"
        self._turns = dispatcher.turns if dispatcher is not None else _Turns()

    # --- tiếp nhận ------------------------------------------------------------------------------------

    async def receive_incoming(self, actor: Actor, data: Any) -> dict[str, Any]:
        """Văn thư tiếp nhận văn bản đến — lớp thứ hai của poka-yoke (F2.2).

        Kiểm lại toàn bộ theo schemas/van-ban-den.json như form đã kiểm, rồi những điều chỉ CSDL biết. Văn thư
        không còn quyền ghi thẳng bảng văn bản, nên dữ liệu nào vào được CSDL cũng đã qua đây.
        """
        if self.intake is None:
            raise WorkflowError("unavailable", "Chưa nạp schema tiếp nhận văn bản đến", 503)
        errors = self.intake.errors(data)
        if errors:
            raise WorkflowError("invalid", "Dữ liệu văn bản đến chưa hợp lệ: " + ", ".join(sorted(errors)), 400,
                                fields=errors)
        file_ids: list[str] = data.get("file_ids", [])
        try:
            found = await self.hasura.as_service(actor, INTAKE_LOOKUP, {
                "type": data["type_code"], "files": file_ids, "user": actor.user_id, "symbol": data["symbol"],
                "issuer": re.sub(r"([\\%_])", r"\\\1", data["issuer_name"]), "issued": data["issued_on"],
            })
        except HasuraError as exc:
            raise _db_error(exc) from exc
        if found["office_document_types_by_pk"] is None:
            raise WorkflowError("invalid", "Không có loại văn bản này", 400, fields={"type_code": "unknown"})
        if len(found["core_files"]) != len(file_ids):
            raise WorkflowError("invalid", "Tệp không tồn tại hoặc không do bạn tải lên", 400,
                                fields={"file_ids": "unknown"})
        sealed = sum(1 for f in found["core_files"] if f.get("encrypted"))    # F3.7; CSDL cũng chặn (trigger)
        if data.get("restricted") and sealed != len(file_ids):
            raise WorkflowError("invalid", RESTRICTED_NOT_SEALED, 400, fields={"file_ids": "not_sealed"})
        if not data.get("restricted") and sealed:
            raise WorkflowError("invalid", SEALED_NOT_RESTRICTED, 400, fields={"file_ids": "sealed"})
        if found["office_documents"]:
            raise WorkflowError("duplicate", CONSTRAINT_MESSAGES["documents_in_dedup"], 409,
                                fields={"symbol": "duplicate"})

        doc = {k: data[k] for k in INTAKE_COLUMNS if k in data}
        doc.update(direction="in", status="received", created_by=actor.user_id, files={"data": [
            {"file_id": f, "role": "main" if i == 0 else "attachment", "added_by": actor.user_id}
            for i, f in enumerate(file_ids)
        ]})
        try:
            created = await self.hasura.as_service(actor, RECEIVE, {"doc": doc})
        except HasuraError as exc:
            if "documents_in_dedup" in str(exc):     # hai văn thư lưu cùng lúc: chỉ mục của CSDL chặn người sau
                raise WorkflowError("duplicate", CONSTRAINT_MESSAGES["documents_in_dedup"], 409,
                                    fields={"symbol": "duplicate"}) from exc
            raise _db_error(exc) from exc
        return {"document_id": created["insert_office_documents_one"]["id"]}

    # --- vào sổ ---------------------------------------------------------------------------------------

    async def register_incoming(self, actor: Actor, document_id: str) -> dict[str, Any]:
        try:
            uuid.UUID(document_id)
        except ValueError:
            raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404) from None
        try:
            await self._check_visible(actor, document_id)
        except WorkflowError as exc:
            if exc.code == "restricted":  # văn thư khác không có tên: như không có văn bản, không lộ là có
                raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404) from None
            raise
        async with self._turns.hold(f"doc:{document_id.lower()}"):
            return await self._register_incoming(actor, document_id)

    async def _register_incoming(self, actor: Actor, document_id: str) -> dict[str, Any]:
        try:
            data = await self.hasura.as_service(actor, REGISTER_INCOMING, {"id": document_id})
        except HasuraError as exc:
            if "không có văn bản" in str(exc):
                raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404) from exc
            if "vào sổ" in str(exc):
                raise WorkflowError("wrong_status", str(exc), 409) from exc
            raise _db_error(exc) from exc
        doc = data["office_register_incoming"][0]
        if not doc["process_id"]:
            try:
                pid = await self._attach_process(actor, doc)
            except (FlowableError, HasuraError) as exc:
                # Số đến đã cấp và đã ghi; job đối soát sẽ khởi chạy quy trình sau
                log.warning(json.dumps({"event": "office.process.start_failed", "document_id": doc["id"],
                                        "error": str(exc)}, ensure_ascii=False))
            else:
                await self._share(actor, pid, doc["id"])
                await self._announce(actor, pid, doc["id"])
        return {"document_id": doc["id"], "register_number": doc["register_number"]}

    async def _attach_process(self, actor: Actor, doc: dict[str, Any]) -> str:
        pid = await self.flowable.find_process(PROCESS_IN, doc["id"])
        started = pid is None
        if pid is None:
            pid = await self.flowable.start_process(PROCESS_IN, doc["id"], {
                "tenantId": str(actor.tenant_id),
                "documentId": doc["id"],
                "urgency": doc.get("urgency") or "normal",
                "dueOn": doc.get("due_on") or "",
                "slaDuration": self.sla_duration,
                "leadDepartmentId": "",
                "handlerId": "",
            })
        return await self._claim_process(actor, doc["id"], pid, started=started)

    async def _claim_process(self, actor: Actor, doc_id: str, pid: str, *, started: bool) -> str:
        """Ghi process_id khi văn bản chưa có. Lần gọi khác đã ghi trước thì theo phiên của lần đó và hủy phiên mình
        vừa khởi chạy — không thì một văn bản có hai quy trình chạy song song, mỗi bước hai việc."""
        try:
            won = await self.hasura.as_service(actor, CLAIM_PROCESS, {"id": doc_id, "pid": pid})
            if won["update_office_documents"]["affected_rows"]:
                return pid
            found = (await self.hasura.as_service(actor, PROCESS_OF, {"id": doc_id}))["office_documents_by_pk"]
        except HasuraError as exc:
            if started:  # quy trình đã chạy mà chưa chắc đã gắn: để lại dấu cho người vận hành đối chiếu
                log.warning(json.dumps({"event": "office.process.unlinked", "document_id": doc_id, "process_id": pid,
                                        "error": str(exc)}, ensure_ascii=False))
            raise
        winner = (found or {}).get("process_id")
        if started and winner != pid:
            try:
                await self.flowable.delete_process(pid, "trùng: văn bản đã gắn quy trình khác")
            except FlowableError as exc:
                log.warning(json.dumps({"event": "office.process.duplicate_left", "document_id": doc_id,
                                        "process_id": pid, "error": str(exc)}, ensure_ascii=False))
        if not winner:
            raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404)
        return winner

    async def reconcile(self) -> int:
        """Gắn quy trình cho văn bản đã vào sổ mà chưa có (lỗi giữa chừng ở registerIncoming)."""
        rows = (await self.hasura.as_system(UNLINKED))["office_documents"]
        for row in rows:
            actor = Actor(SYSTEM_ACTOR, uuid.UUID(row["tenant_id"]), "service", None)
            async with self._turns.hold(f"doc:{row['id'].lower()}"):
                pid = await self._attach_process(actor, row)
                await self._share(actor, pid, row["id"])
                await self._announce(actor, pid, row["id"])
        return len(rows)

    # --- trình văn bản đi -----------------------------------------------------------------------------

    async def submit_outgoing(self, actor: Actor, document_id: str, signer_id: str) -> dict[str, Any]:
        """Người soạn trình dự thảo cho lãnh đạo phòng duyệt: lần đầu, hoặc sau khi sửa theo ý kiến trả lại."""
        try:
            async with self._turns.hold(f"doc:{document_id.lower()}"):
                return await self._submit_outgoing(actor, document_id, signer_id)
        except HasuraError as exc:
            raise _db_error(exc) from exc
        except FlowableError as exc:
            raise WorkflowError("workflow_unavailable", "Chưa gọi được động cơ quy trình, thử lại sau", 503) from exc

    async def _submit_outgoing(self, actor: Actor, document_id: str, signer_id: str) -> dict[str, Any]:
        doc = await self._outgoing(actor, document_id)
        if doc["created_by"] != actor.user_id:
            raise WorkflowError("not_your_document", "Chỉ người soạn mới trình được dự thảo này", 403)
        if doc["status"] == "in_review" and doc["signer_id"] == signer_id:
            # gọi lại sau lỗi mạng: dữ liệu đã ghi, chỉ hoàn thành nốt bước sửa trong Flowable nếu còn. Không còn gì để
            # hoàn thành thì lần trước đã cấp quyền xem, đã báo; cấp lại thì người soạn (không có quyền cấp, gỡ) gọi lại
            # lúc nào cũng thêm lại được người mà văn thư, lãnh đạo đơn vị vừa gỡ khỏi danh sách xem
            if await self._finish_revision(actor, doc, signer_id):
                await self._share(actor, doc["process_id"], doc["id"])
                await self._announce(actor, doc["process_id"], doc["id"])
            return {"document_id": doc["id"], "status": "in_review"}
        if doc["status"] not in ("draft", "returned"):
            raise WorkflowError("wrong_status", "Văn bản đã trình, không trình lại được", 409)
        if not (doc["body"] or "").strip():
            raise WorkflowError("invalid_data", "Dự thảo chưa có nội dung", 400)
        if not doc["recipients"]:
            raise WorkflowError("invalid_data", "Dự thảo chưa ghi nơi nhận", 400)
        if doc.get("recipient_tenant_ids"):
            await self._check_units(actor, doc, doc["recipient_tenant_ids"])
        signer = await self._user(actor, signer_id)
        if signer is None or signer["role"] != "director":
            raise WorkflowError("invalid_data", "Người ký phải là lãnh đạo đơn vị", 400)
        found = await self.hasura.as_service(actor, DEPARTMENT_MANAGERS, {"dept": doc["department_id"]})
        if not found["core_users"]:
            raise WorkflowError("no_manager", "Phòng của bạn chưa có lãnh đạo phòng để duyệt", 409)

        first = doc["status"] == "draft"
        changes: dict[str, Any] = {"status": "in_review", "signer_id": signer_id}
        process_id = doc["process_id"]
        revision: Task | None = None
        if first and not process_id:
            process_id = await self._start_outgoing(actor, doc, signer_id)
        elif first:
            # lần trình trước đã khởi chạy, gắn quy trình rồi lỗi lúc ghi: lần này có thể chọn người ký khác
            await self._set_signer(process_id, signer_id)
        else:
            # trả lại đã ghi mà Flowable chưa sang bước sửa (lỗi lúc chuyển bước): ghi in_review lúc này thì lần bấm
            # lại của người duyệt đưa quy trình về bước sửa khi CSDL đã là in_review — người soạn kẹt, không sửa được
            revision = await self._revision_task(actor, doc)
            if revision is None:
                raise WorkflowError("return_pending", "Bước trả lại dự thảo của người duyệt chưa hoàn tất, thử lại sau "
                                                      "ít phút", 409)
        event = {
            "document_id": doc["id"],
            "kind": "office.document.submitted" if first else "office.document.resubmitted",
            "actor_id": actor.user_id,
            "actor_kind": "user",
            "data": {"signer_id": signer_id},
        }
        await self.hasura.as_service(actor, SUBMIT, {"doc": doc["id"], "set": changes, "event": event})
        if revision is not None:
            await self.flowable.complete(revision.id, {"signerId": signer_id})
        await self._share(actor, process_id, doc["id"])
        await self._announce(actor, process_id, doc["id"])
        return {"document_id": doc["id"], "status": "in_review"}

    async def _check_units(self, actor: Actor, doc: dict[str, Any], units: list[str]) -> None:
        """Đơn vị nhận trong hệ thống (F3.12): có thật, không phải đơn vị mình; văn bản hạn chế không gửi liên thông
        (tệp niêm phong gắn với thuê ước của mình). CSDL cũng chặn — ở đây để báo đúng trường trước khi trình."""
        field = "recipient_tenant_ids"
        if doc.get("restricted"):
            raise WorkflowError("invalid", RESTRICTED_LOCAL, 400, fields={field: "restricted"})
        wanted = {str(u).lower() for u in units}
        if str(actor.tenant_id) in wanted:
            raise WorkflowError("invalid", "Không gửi liên thông cho chính đơn vị mình", 400, fields={field: "self"})
        found = (await self.hasura.as_service(actor, DISPATCH_UNITS, {"ids": sorted(wanted)}))["office_dispatch_units"]
        if {str(u["id"]).lower() for u in found} != wanted:
            raise WorkflowError("invalid", "Đơn vị nhận không có trong hệ thống", 400, fields={field: "unknown"})

    async def _start_outgoing(self, actor: Actor, doc: dict[str, Any], signer_id: str) -> str:
        pid = await self.flowable.find_process(PROCESS_OUT, doc["id"])
        started = pid is None
        if pid is None:
            pid = await self.flowable.start_process(PROCESS_OUT, doc["id"], {
                "tenantId": str(actor.tenant_id),
                "documentId": doc["id"],
                "departmentId": doc["department_id"],
                "drafterId": doc["created_by"],
                "signerId": signer_id,
                "urgency": doc.get("urgency") or "normal",
                "dueOn": "",
                "slaDuration": self.sla_duration,
                "outcome": "",
            })
        linked = await self._claim_process(actor, doc["id"], pid, started=started)
        if linked != pid or not started:
            # phiên có từ trước (lần trình trước khởi chạy mà chưa gắn được, hoặc lần gọi khác vừa gắn): signerId là
            # người ký của lần đó
            await self._set_signer(linked, signer_id)
        return linked

    async def _set_signer(self, process_id: str, signer_id: str) -> None:
        """Ghi người ký vào phiên quy trình đã có, trước khi ghi CSDL — không thì việc ký (vbdi.duyetDonVi) giao cho
        người chọn lần trước, còn bản phát hành ghi người chọn lần này. Việc ký nhận người được giao lúc tạo: quy
        trình đã qua bước duyệt cấp phòng thì đổi biến không còn tác dụng, từ chối."""
        if any(t.form_key != "vbdi.duyetPhong" for t in await self.flowable.process_tasks(process_id)):
            raise WorkflowError("signer_locked", "Dự thảo đã qua bước duyệt cấp phòng, không đổi được người ký", 409)
        await self.flowable.set_variables(process_id, {"signerId": signer_id})

    async def _revision_task(self, actor: Actor, doc: dict[str, Any]) -> Task | None:
        """Việc "sửa dự thảo" đang mở của người soạn trong quy trình của văn bản."""
        if not doc["process_id"]:
            return None
        for task in await self.flowable.tasks_for(actor.user_id, []):
            if task.process_instance_id == doc["process_id"] and task.form_key == "vbdi.chinhSua":
                return task
        return None

    async def _finish_revision(self, actor: Actor, doc: dict[str, Any], signer_id: str) -> bool:
        """Hoàn thành bước "sửa dự thảo" của người soạn: quy trình quay về duyệt cấp phòng, người ký có thể đổi.
        False — không còn việc này để hoàn thành."""
        task = await self._revision_task(actor, doc)
        if task is None:
            return False
        await self.flowable.complete(task.id, {"signerId": signer_id})
        return True

    async def _outgoing(self, actor: Actor, doc_id: str) -> dict[str, Any]:
        try:
            uuid.UUID(doc_id)
        except ValueError:
            raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404) from None
        doc = (await self.hasura.as_service(actor, OUTGOING, {"id": doc_id}))["office_documents_by_pk"]
        if doc is None or doc["direction"] != "out":
            raise WorkflowError("document_not_found", "Không tìm thấy văn bản đi", 404)
        return doc

    # --- thông báo ------------------------------------------------------------------------------------

    async def _quietly(self, what: str, doc_id: str, job: Callable[[], Awaitable[None]]) -> None:
        """Thông báo không bao giờ làm hỏng bước nghiệp vụ đã ghi xong: lỗi chỉ ghi nhật ký."""
        try:
            await job()
        except Exception as exc:  # noqa: BLE001 — bước đã ghi và đã chuyển trong Flowable, không được báo lỗi
            log.warning(json.dumps({"event": "core.notification.failed", "step": what, "document_id": doc_id,
                                    "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))

    async def brief(self, actor: Actor, doc_id: str) -> dict[str, Any] | None:
        """Trích yếu, số ký hiệu, độ khẩn ghi kèm thông báo; văn bản hạn chế chỉ có nhãn."""
        doc = (await self.hasura.as_service(actor, BRIEF, {"id": doc_id}))["office_documents_by_pk"]
        return brief_of(doc) if doc is not None else None

    async def _share(self, actor: Actor, process_id: str | None, doc_id: str) -> None:
        """Văn bản hạn chế (F3.7): người phải làm việc đang mở được thêm vào danh sách xem, không thì họ nhận việc
        mà không mở được văn bản. Bước nghiệp vụ đã ghi xong nên lỗi chỉ ghi nhật ký; văn thư, lãnh đạo đơn vị cấp
        tay được ở màn văn bản. Người đã bị gỡ mà lại phải làm bước sau thì được thêm lại."""
        if not process_id:
            return
        try:
            doc = (await self.hasura.as_service(actor, BRIEF, {"id": doc_id}))["office_documents_by_pk"]
            if not doc or not doc.get("restricted"):
                return
            tasks = await self.flowable.process_tasks(process_id)
            people = await load_people(self.hasura, actor)
            users: set[str] = set()
            for task in tasks:
                users |= await task_people(self.flowable, actor, task, people)
            if users:
                await self.hasura.as_service(actor, SHARE, {"rows": [
                    {"document_id": doc_id, "user_id": u, "granted_by": actor.user_id} for u in sorted(users)]})
        except (HasuraError, FlowableError) as exc:
            log.warning(json.dumps({"event": "office.acl.share_failed", "document_id": doc_id,
                                    "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))

    async def _announce(self, actor: Actor, process_id: str | None, doc_id: str, *, note: str | None = None) -> None:
        """Báo cho người phải làm từng việc đang mở của quy trình — trừ chính người vừa làm bước trước."""
        notifier = self.notifier
        if notifier is None or not process_id:
            return

        async def job() -> None:
            tasks = await self.flowable.process_tasks(process_id)
            if not tasks:
                return
            brief = await self.brief(actor, doc_id) or {}
            people = await notifier.people(actor)
            for task in tasks:
                users = await notifier.task_people(self.flowable, actor, task, people) - {actor.user_id}
                data = {"form_key": task.form_key, "task_id": task.id, **brief, **({"note": note} if note else {})}
                await notifier.send(actor, users, "task.assigned", f"task:{task.id}:assigned", doc_id, data)

        await self._quietly("announce", doc_id, job)

    async def _tell(self, actor: Actor, users: set[str], kind: str, doc_id: str, **data: Any) -> None:
        """Một thông báo về văn bản (không gắn việc) cho những người cụ thể, mỗi người một lần."""
        notifier = self.notifier
        if notifier is None:
            return
        brief = await self.brief(actor, doc_id) or {}
        people: People = await notifier.people(actor)
        by = people.get(actor.user_id)
        payload = {**brief, **({"by_name": by.full_name} if by else {}),
                   **{k: v for k, v in data.items() if v not in (None, "")}}
        await notifier.send(actor, (users & people.keys()) - {actor.user_id}, kind, f"doc:{doc_id}:{kind}", doc_id,
                            payload)

    # --- hộp việc -------------------------------------------------------------------------------------

    async def my_tasks(self, actor: Actor) -> list[dict[str, Any]]:
        try:
            tasks = await self.flowable.tasks_for(actor.user_id, actor.groups)
        except FlowableError as exc:
            raise WorkflowError("workflow_unavailable", "Chưa lấy được hộp việc, thử lại sau", 503) from exc
        mine = [t for t in tasks if t.variables.get("tenantId") == str(actor.tenant_id)]
        mine.sort(key=lambda t: t.created_at)
        mine.sort(key=lambda t: URGENCY_RANK.get(t.variables.get("urgency") or "normal", 0), reverse=True)
        return [
            {
                "id": t.id,
                "name": t.name,
                "form_key": t.form_key,
                "document_id": t.variables.get("documentId"),
                "created_at": t.created_at,
                "due_on": t.variables.get("dueOn") or None,
                "urgency": t.variables.get("urgency") or "normal",
            }
            for t in mine
            if t.variables.get("documentId")
        ]

    # --- hoàn thành việc --------------------------------------------------------------------------------

    async def complete_task(self, actor: Actor, task_id: str, outcome: str, data: dict[str, Any] | None) -> dict:
        async with self._turns.hold(f"task:{task_id}"):
            return await self._complete_task(actor, task_id, outcome, data)

    async def _complete_task(self, actor: Actor, task_id: str, outcome: str, data: dict[str, Any] | None) -> dict:
        try:
            task = await self.flowable.task(task_id)
        except FlowableError as exc:
            raise WorkflowError("workflow_unavailable", "Chưa gọi được động cơ quy trình, thử lại sau", 503) from exc
        if task is None or task.variables.get("tenantId") != str(actor.tenant_id):
            raise WorkflowError("task_not_found", "Việc không còn — có thể đã có người xử lý", 404)
        await self._check_owner(actor, task)
        await self._check_visible(actor, task.variables.get("documentId") or "")

        if task.form_key == "vbdi.chinhSua":
            raise WorkflowError("use_submit", "Sửa dự thảo xong thì trình lại để lãnh đạo duyệt", 400)
        outcomes = FORMS.get(task.form_key)
        if outcomes is None:
            raise WorkflowError("unknown_form", f"Không xử lý được việc loại {task.form_key}", 400)
        model = outcomes.get(outcome)
        if model is None:
            raise WorkflowError("bad_outcome", f"Kết quả không hợp lệ: {outcome}", 400)
        try:
            form = model.model_validate(data or {})
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            raise WorkflowError("invalid_data", f"Dữ liệu không hợp lệ{' (' + where + ')' if where else ''}: "
                                                f"{first['msg']}", 400) from exc

        doc_id = task.variables["documentId"]
        saved = await self._saved_flow(actor, doc_id, task_id)
        if saved:
            # Lần gọi trước đã ghi CSDL rồi lỗi ở Flowable: hoàn thành nốt đúng kết quả đã ghi, không theo lựa chọn
            # khác của lần bấm này. Kế hoạch chỉ còn để lấy ý kiến, thông báo thêm — dữ liệu đã sang bước sau (giao
            # việc đã xong…) thì không dựng lại được, bỏ qua
            again = None
            if saved.get("outcome") == outcome:
                with contextlib.suppress(WorkflowError):
                    again = await self._plan(actor, task, doc_id, outcome, form)
            else:
                log.warning(json.dumps({"event": "office.task.retry_other_outcome", "task_id": task_id,
                                        "saved": saved.get("outcome"), "asked": outcome}, ensure_ascii=False))
            return await self._finish(actor, task, doc_id, saved, note=again.note if again else None,
                                      after=again.after if again else None)
        plan = await self._plan(actor, task, doc_id, outcome, form)

        claimed = False
        if not task.assignee:
            try:
                await self.flowable.claim(task_id, actor.user_id)
            except FlowableError as exc:
                if exc.status == 409:
                    raise WorkflowError("task_taken", "Việc này vừa có người khác nhận", 409) from exc
                raise WorkflowError("workflow_unavailable", "Chưa gọi được động cơ quy trình", 503) from exc
            claimed = True
        flow = plan.flow
        try:
            if saved is None:
                variables = plan.variables
                if plan.prepare is not None:
                    variables = {**variables, **await plan.prepare()}
                # biến Flowable ghi cùng sự kiện: lần bấm lại hoàn thành đúng nhánh đã ghi
                event = variables["event"]
                variables = {**variables, "event": {**event, "data": {**event["data"], "flow": plan.flow}}}
                try:
                    await self.hasura.as_service(actor, plan.mutation, variables)
                except HasuraError as exc:
                    if TASK_ONCE not in str(exc):
                        raise
                    # bản sao svc-workflow khác vừa ghi xong việc này: hoàn thành nốt đúng kết quả nó đã ghi. Không
                    # thấy sự kiện của chính văn bản này thì không coi là đã ghi
                    found = await self._saved_flow(actor, doc_id, task_id)
                    if found is None:
                        raise
                    flow = found or plan.flow
        except (HasuraError, WorkflowError) as exc:
            if claimed:
                await self._unclaim(task_id)
            if isinstance(exc, WorkflowError):
                raise
            raise _db_error(exc) from exc
        return await self._finish(actor, task, doc_id, flow, note=plan.note, after=plan.after)

    async def _finish(self, actor: Actor, task: Task, doc_id: str, flow: dict[str, Any], *, note: str | None = None,
                      after: Callable[[], Awaitable[None]] | None = None) -> dict:
        """Hoàn thành việc trong Flowable sau khi dữ liệu đã ghi, rồi báo người làm bước sau."""
        try:
            await self.flowable.complete(task.id, flow)
        except FlowableError as exc:
            if exc.status == 404:
                # lần gọi khác vừa hoàn thành việc này sau khi dữ liệu đã ghi: lần đó báo người làm bước sau
                return {"task_id": task.id, "document_id": doc_id}
            # Dữ liệu đã ghi; người dùng bấm lại sẽ chỉ hoàn thành nốt trong Flowable
            raise WorkflowError("workflow_unavailable", "Đã lưu, nhưng chưa chuyển được bước tiếp — bấm lại", 503) from exc
        await self._share(actor, task.process_instance_id, doc_id)
        await self._announce(actor, task.process_instance_id, doc_id, note=note)
        if after is not None:
            await self._quietly("after", doc_id, after)
        return {"task_id": task.id, "document_id": doc_id}

    async def _saved_flow(self, actor: Actor, doc_id: str, task_id: str) -> dict[str, Any] | None:
        """Sự kiện mang task_id của văn bản: dữ liệu của việc đã ghi ở một lần gọi trước. Trả biến Flowable đã ghi
        cùng nó; None — chưa ghi; {} — ghi bởi bản trước khi có trường flow."""
        done = await self.hasura.as_service(actor, TASK_DONE, {"doc": doc_id, "task": {"task_id": task_id}})
        rows = done["office_document_events"]
        if not rows:
            return None
        return (rows[0].get("data") or {}).get("flow") or {}

    async def _task_done(self, actor: Actor, doc_id: str, task_id: str) -> bool:
        return await self._saved_flow(actor, doc_id, task_id) is not None

    async def _check_owner(self, actor: Actor, task: Task) -> None:
        if task.assignee:
            if task.assignee != actor.user_id:
                raise WorkflowError("not_your_task", "Việc này không giao cho bạn", 403)
            return
        groups = await self.flowable.candidate_groups(task.id)
        if not set(groups) & set(actor.groups):
            raise WorkflowError("not_your_task", "Việc này không giao cho bạn", 403)

    async def _check_visible(self, actor: Actor, doc_id: str) -> None:
        """Văn bản hạn chế: chỉ người đọc được nó (có tên trong danh sách xem, hoặc người tạo) làm tiếp việc của nó."""
        if not doc_id:
            return
        try:
            doc = (await self.hasura.as_service(actor, BRIEF, {"id": doc_id}))["office_documents_by_pk"]
            if not doc or not doc.get("restricted"):
                return
            seen = (await self.hasura.as_user(actor, VISIBLE, {"id": doc_id}))["office_documents_by_pk"]
        except HasuraError as exc:
            raise _db_error(exc) from exc
        if seen is None:
            raise WorkflowError("restricted", "Văn bản hạn chế: bạn chưa có tên trong danh sách được xem — nhờ văn "
                                              "thư hoặc lãnh đạo đơn vị cấp quyền", 403)

    async def _unclaim(self, task_id: str) -> None:
        try:
            await self.flowable.claim(task_id, None)
        except FlowableError:
            log.warning(json.dumps({"event": "office.task.unclaim_failed", "task_id": task_id}))

    async def _document(self, actor: Actor, doc_id: str) -> dict[str, Any]:
        doc = (await self.hasura.as_service(actor, DOCUMENT, {"id": doc_id}))["office_documents_by_pk"]
        if doc is None:
            raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404)
        return doc

    async def _open_assignments(self, actor: Actor, doc_id: str) -> list[dict[str, Any]]:
        return (await self.hasura.as_service(actor, OPEN_ASSIGNMENTS, {"doc": doc_id}))["office_assignments"]

    async def _user(self, actor: Actor, user_id: str) -> dict[str, Any] | None:
        user = (await self.hasura.as_service(actor, USER, {"id": user_id}))["core_users_by_pk"]
        return user if user and user["enabled"] else None

    def _event(self, actor: Actor, doc_id: str, kind: str, task_id: str, note: str | None, **data: Any) -> dict:
        return {
            "document_id": doc_id,
            "kind": kind,
            "actor_id": actor.user_id,
            "actor_kind": "user",
            "note": note,
            "data": {"task_id": task_id, **{k: v for k, v in data.items() if v not in (None, [], "")}},
        }

    async def _plan(self, actor: Actor, task: Task, doc_id: str, outcome: str, form: Any) -> Plan:
        try:
            return await self._plan_unchecked(actor, task, doc_id, outcome, form)
        except HasuraError as exc:
            raise _db_error(exc) from exc

    async def _plan_unchecked(self, actor: Actor, task: Task, doc_id: str, outcome: str, form: Any) -> Plan:
        if isinstance(form, ChiDao):
            return await self._plan_direct(actor, task, doc_id, form)
        if task.form_key == "vbden.chiDao" and isinstance(form, Note):
            event = self._event(actor, doc_id, "office.document.filed", task.id, form.note)
            return Plan(FILE, {"doc": doc_id, "event": event}, {"outcome": "file"})
        if task.form_key == "vbden.phanCong":
            return await self._plan_assign(actor, task, doc_id, outcome, form)
        if isinstance(form, XuLy):
            return await self._plan_processed(actor, task, doc_id, form)
        if task.form_key in ("vbdi.duyetPhong", "vbdi.duyetDonVi"):
            return await self._plan_review(actor, task, doc_id, outcome, form)
        if isinstance(form, PhatHanh):
            return await self._plan_issue(actor, task, doc_id, form)
        raise WorkflowError("unknown_form", f"Không xử lý được việc loại {task.form_key}", 400)

    async def _plan_direct(self, actor: Actor, task: Task, doc_id: str, form: ChiDao) -> Plan:
        doc = await self._document(actor, doc_id)
        if form.due_on and form.due_on < date.today():
            raise WorkflowError("invalid_data", "Hạn giải quyết đã qua", 400)
        due = form.due_on.isoformat() if form.due_on else doc["due_on"]
        if form.lead_user_id:
            user = await self._user(actor, form.lead_user_id)
            if user is None or user["role"] not in {"staff", "manager"}:
                raise WorkflowError("invalid_data", "Người chủ trì không thuộc đơn vị hoặc không xử lý văn bản", 400)
        else:
            found = await self.hasura.as_service(actor, DEPARTMENT_MANAGERS, {"dept": str(form.lead_department_id)})
            if found["office_departments_by_pk"] is None:
                raise WorkflowError("invalid_data", "Phòng chủ trì không thuộc đơn vị", 400)
            if not found["core_users"]:
                raise WorkflowError("no_manager", "Phòng chủ trì chưa có lãnh đạo phòng để phân công", 409)
        for dept in form.supports:
            found = await self.hasura.as_service(actor, DEPARTMENT_MANAGERS, {"dept": str(dept)})
            if found["office_departments_by_pk"] is None:
                raise WorkflowError("invalid_data", "Phòng phối hợp không thuộc đơn vị", 400)

        base = {"document_id": doc_id, "instruction": form.instruction, "due_on": due, "assigned_by": actor.user_id}
        lead = {**base, "role": "lead"}
        if form.lead_user_id:
            lead["user_id"] = form.lead_user_id
        else:
            lead["department_id"] = str(form.lead_department_id)
        supports = [{**base, "role": "support", "department_id": str(d)} for d in form.supports]
        event = self._event(
            actor, doc_id, "office.document.directed", task.id, form.instruction,
            lead_department_id=str(form.lead_department_id) if form.lead_department_id else None,
            lead_user_id=form.lead_user_id, supports=[str(d) for d in form.supports], due_on=due,
        )
        return Plan(
            DIRECT,
            {"doc": doc_id, "due": due, "lead": lead, "supports": supports, "event": event},
            {"outcome": "direct", "leadDepartmentId": str(form.lead_department_id or ""),
             "handlerId": form.lead_user_id or "", "dueOn": due or ""},
        )

    async def _plan_assign(self, actor: Actor, task: Task, doc_id: str, outcome: str, form: Any) -> Plan:
        parent = next(
            (a for a in await self._open_assignments(actor, doc_id)
             if a["parent_id"] is None and a["role"] == "lead" and a["department_id"] == str(actor.department_id)),
            None,
        )
        if parent is None:
            raise WorkflowError("no_assignment", "Phòng của bạn không chủ trì văn bản này", 409)
        if outcome == "assign":
            assert isinstance(form, PhanCong)
            user = await self._user(actor, form.user_id)
            if user is None or user["department_id"] != str(actor.department_id) or user["role"] not in {"staff", "manager"}:
                raise WorkflowError("invalid_data", "Người được giao phải thuộc phòng của bạn", 400)
            handler = form.user_id
        else:
            handler = actor.user_id
        child = {
            "document_id": doc_id, "parent_id": parent["id"], "user_id": handler, "role": "lead",
            "instruction": form.note, "due_on": parent["due_on"], "assigned_by": actor.user_id,
        }
        event = self._event(actor, doc_id, "office.document.assigned", task.id, form.note, user_id=handler)
        return Plan(ASSIGN, {"child": child, "event": event}, {"outcome": outcome, "handlerId": handler})

    async def _plan_processed(self, actor: Actor, task: Task, doc_id: str, form: XuLy) -> Plan:
        open_rows = await self._open_assignments(actor, doc_id)
        mine = next((a for a in open_rows if a["user_id"] == actor.user_id and a["role"] == "lead"), None)
        if mine is None:
            raise WorkflowError("no_assignment", "Bạn không có việc mở với văn bản này", 409)
        ids = [mine["id"]] + ([mine["parent_id"]] if mine["parent_id"] else [])
        event = self._event(actor, doc_id, "office.document.processed", task.id, form.result_note)
        # người đã giao việc: lãnh đạo phòng phân công, lãnh đạo đơn vị chỉ đạo
        assigners = {a.get("assigned_by") for a in open_rows if a["id"] in ids}

        async def after() -> None:
            await self._tell(actor, {u for u in assigners if u}, "document.processed", doc_id,
                             note=form.result_note[:300])

        return Plan(
            PROCESSED,
            {"ids": ids, "note": form.result_note, "now": datetime.now(UTC).isoformat(), "doc": doc_id,
             "event": event},
            {"outcome": "done"},
            after=after,
        )

    # --- văn bản đi -------------------------------------------------------------------------------------

    async def _plan_review(self, actor: Actor, task: Task, doc_id: str, outcome: str, form: Any) -> Plan:
        """Lãnh đạo phòng (vbdi.duyetPhong) hoặc người ký (vbdi.duyetDonVi) đồng ý hay trả lại dự thảo."""
        doc = await self._outgoing(actor, doc_id)
        if doc["status"] != "in_review" and not await self._task_done(actor, doc_id, task.id):
            raise WorkflowError("wrong_status", "Văn bản không ở bước chờ duyệt", 409)
        level = "department" if task.form_key == "vbdi.duyetPhong" else "unit"
        if outcome == "return":
            event = self._event(actor, doc_id, "office.document.returned", task.id, form.note, level=level)
            return Plan(SET_STATUS, {"doc": doc_id, "status": "returned", "event": event}, {"outcome": "return"},
                        note=form.note)
        if level == "department":
            event = self._event(actor, doc_id, "office.document.reviewed", task.id, form.note, level=level)
            return Plan(EVENT_ONLY, {"event": event}, {"outcome": "approve"})
        event = self._event(actor, doc_id, "office.document.approved", task.id, form.note)
        return Plan(SET_STATUS, {"doc": doc_id, "status": "approved", "event": event}, {"outcome": "approve"})

    async def _plan_issue(self, actor: Actor, task: Task, doc_id: str, form: PhatHanh) -> Plan:
        """Văn thư phát hành: cấp số đi → svc-files dựng PDF có số, mã QR, rồi lưu → ghi băm, chuyển issued.

        Gọi lại sau lỗi: cấp số trả về số đã cấp; PDF được dựng lại (tệp cũ chưa gắn vào văn bản thì bỏ).
        Có đơn vị nhận trong hệ thống: CSDL tạo dòng liên thông cùng giao dịch phát hành (trigger), sau khi chuyển
        bước thì chuyển ngay sang các đơn vị đó; chưa xong thì vòng nền đối soát chuyển tiếp (dispatch.py).
        """
        doc = await self._outgoing(actor, doc_id)
        if doc["status"] != "approved" and not await self._task_done(actor, doc_id, task.id):
            raise WorkflowError("wrong_status", "Văn bản chưa được lãnh đạo đơn vị ký duyệt", 409)
        if form.is_public and doc.get("restricted"):
            raise WorkflowError("invalid", RESTRICTED_PUBLIC, 400, fields={"is_public": "restricted"})
        files = self.files
        if files is None:
            raise WorkflowError("files_unavailable", "Chưa nối được dịch vụ tệp để dựng bản phát hành", 503)

        async def prepare() -> dict[str, Any]:
            numbered = (await self.hasura.as_service(
                actor, NUMBER_OUTGOING, {"id": doc_id, "code": new_verify_code()}))["office_number_outgoing"][0]
            try:
                pdf = await files.issue(actor, doc_id)
            except FilesError as exc:
                log.warning(json.dumps({"event": "office.document.render_failed", "document_id": doc_id,
                                        "error": str(exc)}, ensure_ascii=False))
                raise WorkflowError("files_unavailable", "Chưa dựng được bản phát hành, thử lại sau", 503) from exc
            event = self._event(actor, doc_id, "office.document.issued", task.id, None, symbol=numbered["symbol"],
                                verify_code=numbered["verify_code"], sha256=pdf["sha256"], is_public=form.is_public)
            return {
                "sha": "\\x" + pdf["sha256"],
                "file": {"document_id": doc_id, "file_id": pdf["file_id"], "role": "issued", "added_by": actor.user_id},
                "event": event,
            }

        async def after() -> None:
            await self._quietly("after", doc_id, lambda: self._tell(
                actor, {doc["created_by"], doc["signer_id"]} - {None}, "document.issued", doc_id))
            if doc.get("recipient_tenant_ids") and self.dispatcher is not None:
                await self.dispatcher.dispatch_document(doc_id)   # tự giới hạn thời gian, không ném lỗi

        return Plan(ISSUE, {"doc": doc_id, "public": form.is_public}, {"outcome": "issue"}, prepare, after=after)
