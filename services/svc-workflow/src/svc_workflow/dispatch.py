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

"""Liên thông văn bản trong hệ thống (F3.12): văn bản đi phát hành cho một đơn vị khác trong hệ thống thành văn bản
đến của đơn vị đó, kèm đúng tệp PDF đã phát hành.

Hộp thư đi nằm trong CSDL: lúc phát hành (mutation ISSUE), trigger ``documents_dispatch`` tạo một dòng
``office.dispatches`` trạng thái ``pending`` cho mỗi đơn vị nhận, trong cùng giao dịch. Ở đây chuyển từng dòng:

  1. svc-files chép tệp phát hành sang thuê ước nhận (``POST /internal/dispatch-file``); id bản sao định trước trong
     dòng nên chép lại không sinh bản thứ hai;
  2. hàm ``office.deliver_dispatch`` — gọi trong phiên của bên nhận — dựng văn bản đến ``received`` gắn bản sao, ghi sự
     kiện ở cả hai bên, chuyển dòng sang ``delivered``; bên nhận đã tiếp nhận văn bản này (tiếp nhận tay trước đó)
     thì ``duplicate``; CSDL từ chối dữ liệu thì ``failed``;
  3. báo văn thư bên nhận (không có văn thư thì lãnh đạo đơn vị), rồi đặt ``notified_at``.

Ngay sau khi phát hành, ``completeTask`` chuyển các dòng của văn bản đó, giới hạn ~15 giây để Hasura (chờ Action
90 giây) không bao giờ hết giờ vì liên thông. Vòng nền ``reconcile`` lấy phần còn lại: dòng chờ đã đến hạn thử, dòng
đã chuyển mà chưa báo (dịch vụ dừng giữa chừng). Lỗi thì ghi ``last_error`` (người dùng thấy ở thẻ "Liên thông") và
thử lại sau 30 s·2^lần, tối đa 1 giờ.

Đúng một lần: một dòng mỗi (văn bản, đơn vị) (``dispatches_once``); mỗi dòng một lượt trong tiến trình
(``dispatch:<id>``), hàm CSDL khóa dòng và xét trạng thái, chỉ mục ``documents_source_once`` chặn sau cùng; mỗi người
nhận một thông báo (khóa ``doc:<văn bản đến>:document.incoming``, như ``Workflow._tell``) — đối soát báo lại sau khi
dừng giữa chừng cũng không gửi trùng. Dòng ``duplicate`` không báo ai: bên nhận đã có văn bản này và đang xử lý nó,
chỉ đặt ``notified_at`` để đối soát bỏ qua.

Sự kiện liên thông do hàm CSDL ghi và không mang ``task_id`` (chỉ mục duy nhất toàn cục
``document_events_task_once``); ở đây không ghi sự kiện nào.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from .files import DISPATCH_FINAL, DispatchFileError, FilesClient, FilesError
from .hasura import (
    BRIEF,
    DELIVER,
    DISPATCH,
    DISPATCH_NOTIFIED,
    DISPATCH_RETRY,
    DOCUMENT_DISPATCHES,
    FAIL_DISPATCH,
    PENDING_DISPATCHES,
    Actor,
    HasuraClient,
    HasuraError,
)
from .notify import Notifier, brief_of
from .workflow import SYSTEM_ACTOR, _Turns

log = logging.getLogger("svc_workflow")

KIND = "document.incoming"
BUDGET_S = 15.0
BACKOFF_FIRST = timedelta(seconds=30)
BACKOFF_MAX = timedelta(hours=1)
LINKED = ("delivered", "duplicate")


def backoff(attempts: int) -> timedelta:
    """Chờ trước lần thử sau: 30 giây, 1 phút, 2 phút… tối đa 1 giờ. attempts: số lần đã lỗi trước lần này."""
    return min(BACKOFF_FIRST * 2 ** min(max(attempts, 0), 10), BACKOFF_MAX)


def _reason(exc: Exception | str) -> str:
    """Câu ngắn ghi vào last_error — giao diện hiện cho văn thư, nên không có địa chỉ nội bộ hay nguyên văn lỗi mạng."""
    if isinstance(exc, str):
        return exc
    if isinstance(exc, DispatchFileError):
        return exc.message
    if isinstance(exc, FilesError):
        return "Chưa lấy được quyền gọi dịch vụ tệp, sẽ thử lại"
    if isinstance(exc, HasuraError) and exc.code:   # CSDL trả lời: câu của ràng buộc hay của hàm deliver_dispatch
        return str(exc)[:300]
    return "Chưa gọi được cơ sở dữ liệu, sẽ thử lại"


def _detail(exc: Exception | str) -> str:
    if isinstance(exc, DispatchFileError) and exc.detail:
        return exc.detail
    return exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"


def _service(tenant_id: str) -> Actor:
    return Actor(SYSTEM_ACTOR, uuid.UUID(tenant_id), "service", None)


class Dispatcher:
    def __init__(self, hasura: HasuraClient, files: FilesClient, notifier: Notifier, *, turns: _Turns | None = None,
                 budget_s: float = BUDGET_S, clock: Callable[[], datetime] | None = None) -> None:
        self.hasura = hasura
        self.files = files
        self.notifier = notifier
        # dùng chung sổ lượt với Workflow (app.py): khóa "dispatch:<id>" cạnh "doc:<id>", "task:<id>"
        self.turns = turns or _Turns()
        self.budget_s = budget_s
        self._clock = clock or (lambda: datetime.now(UTC))

    async def dispatch_document(self, doc_id: str) -> int:
        """Chuyển ngay các dòng chờ của một văn bản vừa phát hành → số dòng đã lấy.

        Không bao giờ ném lỗi: phát hành đã ghi và đã chuyển bước. Hết giờ hay lỗi thì dòng vẫn ``pending``, vòng nền
        đối soát chuyển tiếp.
        """
        ids: list[str] = []
        try:
            async with asyncio.timeout(self.budget_s):
                rows = (await self.hasura.as_system(DOCUMENT_DISPATCHES, {"doc": doc_id}))["office_dispatches"]
                ids = [r["id"] for r in rows]
                await self._each(ids)
        except TimeoutError:
            log.warning(json.dumps({"event": "office.dispatch.deferred", "document_id": doc_id, "count": len(ids),
                                    "budget_s": self.budget_s}))
        except Exception as exc:  # noqa: BLE001 — liên thông không làm hỏng bước phát hành
            log.warning(json.dumps({"event": "office.dispatch.failed", "document_id": doc_id,
                                    "error": _detail(exc)}, ensure_ascii=False))
        return len(ids)

    async def reconcile(self) -> int:
        """Vòng nền: dòng chờ đã đến hạn thử, và dòng đã chuyển mà chưa báo bên nhận → số dòng đã lấy."""
        now = self._clock()
        rows = (await self.hasura.as_system(PENDING_DISPATCHES, {"now": now.isoformat()}))["office_dispatches"]
        await self._each([r["id"] for r in rows])
        return len(rows)

    async def _each(self, ids: Iterable[str]) -> None:
        for dispatch_id in ids:
            try:
                await self.deliver(dispatch_id)
            except Exception as exc:  # noqa: BLE001 — một dòng lỗi không chặn các dòng sau
                log.warning(json.dumps({"event": "office.dispatch.failed", "dispatch_id": dispatch_id,
                                        "error": _detail(exc)}, ensure_ascii=False))

    async def deliver(self, dispatch_id: str) -> str | None:
        """Chuyển một dòng liên thông rồi báo bên nhận → trạng thái sau cùng (None: không có dòng này).

        Dòng đã chuyển thì chỉ báo nếu chưa báo; dòng ``failed`` thì thôi (chưa có thao tác gửi lại).
        """
        async with self.turns.hold(f"dispatch:{dispatch_id.lower()}"):
            row = await self._row(dispatch_id)
            if row is None:
                return None
            if row["status"] == "pending":
                row = await self._transfer(row)
            if row["status"] in LINKED and not row.get("notified_at"):
                await self._notify(row)
            return str(row["status"])

    async def _row(self, dispatch_id: str) -> dict[str, Any] | None:
        return (await self.hasura.as_system(DISPATCH, {"id": dispatch_id}))["office_dispatches_by_pk"]

    async def _transfer(self, row: dict[str, Any]) -> dict[str, Any]:
        """Chép tệp rồi dựng văn bản đến. Lỗi thì hẹn lần thử sau và trả dòng như cũ (vẫn ``pending``)."""
        try:
            await self.files.dispatch_file(row["id"])
        except FilesError as exc:
            if isinstance(exc, DispatchFileError) and exc.code == "not_pending":
                # lần gọi khác (bản sao dịch vụ khác) vừa chuyển xong dòng này: theo trạng thái nó đã ghi
                fresh = await self._row(row["id"])
                if fresh is not None and fresh["status"] != "pending":
                    return fresh
            if isinstance(exc, DispatchFileError) and exc.code in DISPATCH_FINAL:
                return await self._fail(row, exc)
            await self._retry(row, exc)
            return row
        try:
            done = (await self.hasura.as_service(_service(row["to_tenant_id"]), DELIVER,
                                                 {"id": row["id"]}))["office_deliver_dispatch"]
        except HasuraError as exc:
            await self._retry(row, exc)
            return row
        if not done or done[0].get("status") not in (*LINKED, "failed"):
            await self._retry(row, "CSDL chưa chuyển được dòng liên thông, sẽ thử lại")
            return row
        row = {**row, **done[0]}
        record = {"dispatch_id": row["id"], "document_id": row["document_id"], "to_tenant_id": row["to_tenant_id"]}
        if row["status"] == "failed":     # CSDL từ chối dữ liệu của văn bản đến: thử lại cũng vậy
            log.warning(json.dumps({"event": "office.dispatch.failed", **record, "final": True,
                                    "error": row.get("last_error")}, ensure_ascii=False))
        else:
            log.info(json.dumps({"event": f"office.dispatch.{row['status']}", **record,
                                 "incoming_document_id": row["incoming_document_id"]}))
        return row

    async def _fail(self, row: dict[str, Any], exc: DispatchFileError) -> dict[str, Any]:
        """svc-files từ chối vĩnh viễn (sai băm, kho lạnh, trạm quét chặn…) → ``failed`` kèm lý do cho bên gửi."""
        try:
            done = (await self.hasura.as_service(_service(row["tenant_id"]), FAIL_DISPATCH,
                                                 {"id": row["id"], "reason": exc.message}))["office_fail_dispatch"]
        except HasuraError as err:
            await self._retry(row, err)
            return row
        if not done:    # không còn chờ: lần gọi khác vừa xong dòng này, theo trạng thái nó đã ghi
            return await self._row(row["id"]) or row
        log.warning(json.dumps({"event": "office.dispatch.failed", "dispatch_id": row["id"],
                                "document_id": row["document_id"], "to_tenant_id": row["to_tenant_id"],
                                "final": True, "error": _detail(exc)}, ensure_ascii=False))
        return {**row, **done[0]}

    async def _retry(self, row: dict[str, Any], exc: Exception | str) -> None:
        attempts = int(row.get("attempts") or 0)
        next_at = self._clock() + backoff(attempts)
        log.warning(json.dumps({
            "event": "office.dispatch.failed", "dispatch_id": row["id"], "document_id": row["document_id"],
            "to_tenant_id": row["to_tenant_id"], "attempts": attempts + 1, "next_attempt_at": next_at.isoformat(),
            "error": _detail(exc),
        }, ensure_ascii=False))
        await self.hasura.as_service(_service(row["tenant_id"]), DISPATCH_RETRY, {
            "id": row["id"], "error": _reason(exc), "next": next_at.isoformat()})

    async def _notify(self, row: dict[str, Any]) -> None:
        """Báo văn thư bên nhận có văn bản đến mới (không có văn thư thì lãnh đạo đơn vị), rồi đặt ``notified_at``.

        Ghi thông báo lỗi thì để đối soát làm lại; người đã nhận không nhận lần hai (khóa chống trùng).
        """
        if row["status"] == "delivered":
            recipient = _service(row["to_tenant_id"])
            incoming = row["incoming_document_id"]
            try:
                people = await self.notifier.people(recipient)
                users = people.with_role("clerk") or people.with_role("director")
                doc = (await self.hasura.as_service(recipient, BRIEF, {"id": incoming}))["office_documents_by_pk"]
                from_name = (row.get("from_unit") or {}).get("name")
                await self.notifier.send(recipient, users, KIND, f"doc:{incoming}:{KIND}", incoming,
                                         {**brief_of(doc), **({"from_name": from_name} if from_name else {})})
            except HasuraError as exc:
                log.warning(json.dumps({"event": "core.notification.failed", "step": "dispatch",
                                        "dispatch_id": row["id"], "document_id": incoming,
                                        "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
                return
        await self.hasura.as_service(_service(row["tenant_id"]), DISPATCH_NOTIFIED, {
            "id": row["id"], "now": self._clock().isoformat()})
