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

"""Vòng nền của lô nạp: lấy lô đến giờ, làm một mẻ dòng, nhường lô khác; hết dòng chờ thì đóng lô.

Mọi trạng thái nằm trong CSDL (store.py), nên svc-files khởi động lại thì vòng chạy tiếp đúng chỗ dở: dòng ``pending``
làm lại từ bước chưa xong — tệp đã lưu (id trong ``result``) không lưu lần hai, văn bản đã tạo mà chưa kịp ghi id thì
được nhận về (xem ``IncomingHandler``). Zip trên tmpfs mất khi container khởi động lại: dòng còn cần tệp thành
``failed`` mã ``archive_lost``, ``note`` của lô báo gửi lại kèm tệp nén (dòng đã nạp sẽ báo trùng).

Giữ dòng: nhận một dòng là cập nhật có điều kiện, đặt ``claimed_until`` = bây giờ + ``LEASE_S`` (gia hạn mỗi lần lưu
tiến độ) và mã lượt giữ ``claim_id`` của mẻ. Vòng khác (tiến trình thứ hai) không thấy, không nhận được dòng đang được
giữ, nên không lưu tệp của dòng đó lần hai. Lõi bận thì thả dòng ngay; tiến trình chết giữa chừng thì dòng nhận lại
được sau khi hết hạn giữ. Một bước kéo dài quá hạn giữ (hay đồng hồ hai tiến trình lệch nhau) thì vòng khác nhận lại
dòng; vòng cũ biết mình mất dòng ở lần ghi kế tiếp (mọi lệnh ghi dòng kèm ``claim_id``, ``LeaseLost``): không ghi gì
thêm, gỡ tệp vừa lưu mà chưa kịp ghi vào dòng — tệp đó không ai khác biết tới.

Dòng kết thúc mà không thành văn bản (Action từ chối, trùng, tệp sau bị chặn, hết lượt, người tạo bị khóa…) thì tệp
đã lưu cho dòng được gỡ (``Handler.abandon``): không để lại tệp không gắn văn bản nào trong kho.

Phân loại lỗi của một dòng:

- vĩnh viễn (dữ liệu sai, tệp nhiễm, trùng…): dòng ``failed`` / ``duplicate``, các dòng khác vẫn chạy;
- tạm (lõi bận: Hasura, svc-workflow, ClamAV, kho, két không trả lời): dòng giữ ``pending``, lô lùi ``run_after``
  ``min(60, 2^lần)`` giây, ``note`` báo tạm dừng; lô khác vẫn chạy. Quá ``MAX_ATTEMPTS`` lượt thì ``failed`` mã
  ``unavailable``;
- lạ (lỗi ``internal`` của Action, ngoại lệ không lường): thử tối đa ``INTERNAL_TRIES`` lượt rồi ``failed``.

Đầu mỗi mẻ kiểm lại danh bạ: người tạo lô bị khóa hoặc không còn vai trò được tạo lô thì mọi dòng chờ thành
``actor_revoked`` — vòng nền đóng vai họ bằng khóa quản trị, nên quyền phải còn khi mỗi dòng được ghi.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
import zipfile
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, Literal, Protocol

from fastapi import HTTPException

from ..hasura import AUTH_CODES, HasuraError
from .parse import Columns
from .spool import EntryError, Spool, read_entry
from .spool import index as zip_index

log = logging.getLogger("svc_files")

MAX_ATTEMPTS = 20           # bằng trần check attempts của core.import_rows (lùi dần, cộng lại khoảng 16 phút)
INTERNAL_TRIES = 3
BACKOFF_MAX_S = 60
MESSAGE_MAX = 500
NOTE_MAX = 500
LEASE_S = 300               # giữ dòng trong lúc làm: dài hơn một bước (một tệp, một lời gọi Action 35 giây)
LEASE_RECHECK_S = 30        # mọi dòng còn chờ đều đang được vòng khác giữ: hỏi lại lô sau chừng này
PAUSED = "Tạm dừng"
ARCHIVE_LOST = ("Tệp nén đính kèm không còn sau khi svc-files khởi động lại — gửi lại lô kèm tệp nén; dòng đã nạp "
                "sẽ báo trùng")

# Mã lỗi không phải lỗi của dữ liệu: lõi chưa sẵn sàng, thử lại sau (None: không gọi được Hasura, hết giờ)
TRANSIENT = {None, "unexpected", "unavailable", "database_unavailable", "scanner_unavailable",
             "storage_unavailable", "busy", "vault_unavailable"}
# Hasura từ chối phiên hay quyền của vai trò: lưu thành forbidden
FORBIDDEN = AUTH_CODES | {"validation-failed", "permission-error"}
CODE_RE = re.compile(r"[^a-z_]")
VN = timezone(timedelta(hours=7))

Status = Literal["ok", "duplicate", "failed"]

RECEIVE = """
mutation NhanVanBanDen($d: jsonb!) { receiveIncoming(data: $d) { document_id } }"""

REGISTER = """
mutation VaoSoVanBanDen($id: uuid!) { registerIncoming(documentId: $id) { document_id register_number } }"""


class LeaseLost(Exception):
    """Dòng không còn là của lượt giữ này: quá hạn giữ và vòng khác đã nhận lại, hoặc cả lô bị hủy (người tạo bị khóa).
    ``file_ids``: tệp vừa lưu cho dòng mà chưa ghi được vào dòng — người bắt phải gỡ."""

    def __init__(self, file_ids: list[str] | None = None) -> None:
        super().__init__("dòng đã sang tay vòng khác")
        self.file_ids = list(file_ids or [])


class Transient(Exception):
    """Lõi chưa sẵn sàng: dòng giữ pending, lô lùi lại."""

    def __init__(self, code: str | None, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Outcome:
    status: Status
    code: str | None = None
    message: str | None = None
    fields: dict[str, Any] | None = None


def _clip(text: str | None, limit: int = MESSAGE_MAX) -> str | None:
    return None if text is None else text[:limit]


def row_code(code: str | None, fallback: str = "internal") -> str:
    """Mã lưu vào core.import_rows.code (^[a-z_]{1,40}$)."""
    if code in FORBIDDEN:
        return "forbidden"
    cleaned = CODE_RE.sub("_", (code or "").lower())[:40]
    return cleaned or fallback


class Chunk:
    """Một mẻ của một lô: zip mở một lần cho cả mẻ, lưu tiến độ của dòng (và gia hạn giữ dòng). Mọi dòng mẻ này nhận
    mang cùng mã lượt giữ ``claim_id``."""

    def __init__(self, store: Any, spool: Spool, job: dict[str, Any],
                 until: Callable[[], datetime] | None = None) -> None:
        self.store = store
        self.spool = spool
        self.job = job
        self.until = until or (lambda: datetime.now(UTC) + timedelta(seconds=LEASE_S))
        self.claim_id = str(uuid.uuid4())
        self.results: dict[int, dict[str, Any]] = {}      # tiến độ đã lưu trong mẻ này, theo dòng
        self.archive_lost = False
        self._zip: zipfile.ZipFile | None = None
        self._entries: dict[str, zipfile.ZipInfo] = {}
        self._opened = False

    async def archive(self) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo]] | None:
        if not self._opened:
            self._opened = True
            self._zip = await asyncio.to_thread(self.spool.open, self.job["id"], self.job.get("archive_bytes"))
            if self._zip is not None:
                try:
                    self._entries = await asyncio.to_thread(zip_index, self._zip)
                except Exception:  # noqa: BLE001 — zip đã kiểm lúc tạo lô; hỏng sau đó cũng như mất
                    self._zip.close()
                    self._zip = None
        if self._zip is None:
            self.archive_lost = True
            return None
        return self._zip, self._entries

    async def save(self, line: int, result: dict[str, Any], *, stored: list[str] | None = None) -> None:
        """Lưu tiến độ của dòng; dòng đã sang tay vòng khác thì ``LeaseLost`` mang ``stored`` — tệp vừa lưu cho lần ghi
        này, không nằm trong dòng nào."""
        if not await self.store.progress(self.job, line, result, until=self.until(), claim_id=self.claim_id):
            raise LeaseLost(stored)
        self.results[line] = dict(result)

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()


class Handler(Protocol):
    kind: str
    roles: frozenset[str]           # vai trò được tạo lô loại này (và phải còn khi vòng nền ghi từng dòng)
    columns: Columns

    # ném Transient (lõi bận) hay LeaseLost (dòng đã sang tay vòng khác, từ chunk.save)
    async def process(self, job: dict[str, Any], row: dict[str, Any], chunk: Chunk) -> Outcome: ...

    # dòng kết thúc mà không ghi được (không phải ok): dọn những gì đã làm dở cho dòng; trả số thứ đã gỡ
    async def abandon(self, job: dict[str, Any], line: int, result: dict[str, Any]) -> int: ...


class _Actions(Protocol):
    async def act_as(self, *, role: str, tenant_id: uuid.UUID, user_id: str, department_id: str | None,
                     request_id: str, query: str, variables: dict[str, Any]) -> dict[str, Any]: ...


# (rid, thuê ước, người tải, byte, tên trong zip, hạn chế) → id tệp đã quét, lưu — ingest() của app.py
Ingest = Callable[[str, uuid.UUID, str, bytes, str, bool], Awaitable[str]]
# (rid, khóa đối tượng) → xóa đối tượng trong kho, lỗi thì ghi nhật ký core.file.orphaned — discard() của app.py
Discard = Callable[[str, str], Awaitable[None]]


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


@dataclass
class IncomingHandler:
    """Văn bản đến: mỗi dòng đi đúng đường tiếp nhận lẻ — tệp đính kèm qua ``ingest`` (ClamAV → kho → core.files),
    Action ``receiveIncoming`` thay mặt văn thư (kiểm schema, tra loại / tệp / trùng, ghi văn bản, sổ kiểm toán), tùy
    chọn ``registerIncoming`` (vào sổ, cấp số đến)."""

    actions: _Actions
    store: Any
    ingest: Ingest
    discard: Discard
    max_file_bytes: int
    sealing: bool                   # đã cấu hình két (F3.7): mới nhận được tệp của văn bản hạn chế
    kind: str = "incoming"
    roles: frozenset[str] = frozenset({"clerk"})
    act_role: str = "clerk"
    columns: Columns = field(default_factory=lambda: Columns(
        required=("type_code", "symbol", "issuer_name", "issued_on", "summary"),
        optional=("urgency", "due_on", "restricted", "file_ids"),
        booleans=frozenset({"restricted"}),
        lists=frozenset({"file_ids"}),
    ))

    async def _act(self, job: dict[str, Any], line: int, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        return await self.actions.act_as(
            role=self.act_role, tenant_id=uuid.UUID(str(job["tenant_id"])), user_id=job["created_by"],
            department_id=job.get("department_id"), request_id=f"{job['id']}:{line}", query=query, variables=variables)

    async def _existing(self, job: dict[str, Any], line: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Văn bản đến cùng khóa chặn trùng đã có chưa — chỉ hỏi khi các trường khóa đúng kiểu (sai thì để Action
        báo lỗi theo trường)."""
        symbol, issuer, issued = data.get("symbol"), data.get("issuer_name"), data.get("issued_on")
        if not (isinstance(symbol, str) and isinstance(issuer, str) and _valid_date(issued)):
            return None
        return await self.store.existing(job, line, symbol=symbol, issuer=issuer, issued_on=issued)

    async def _ours(self, job: dict[str, Any], line: int, found: dict[str, Any]) -> bool:
        """Văn bản trùng này do chính dòng này tạo ở lượt trước (Action đã ghi mà vòng nền không nhận được trả lời,
        hoặc dịch vụ dừng trước khi lưu id): cùng người tạo lô, tạo sau lúc tạo lô, chưa dòng nào khác nhận."""
        if found.get("created_by") != job["created_by"]:
            return False
        try:
            created, started = (datetime.fromisoformat(str(found.get("created_at"))),
                                datetime.fromisoformat(str(job["created_at"])))
        except ValueError:
            return False
        if created < started:
            return False
        return not await self.store.claimed(job, line, str(found["id"]))

    async def process(self, job: dict[str, Any], row: dict[str, Any], chunk: Chunk) -> Outcome:
        line, data = row["line"], dict(row["data"] or {})
        files: list[str] = list(row.get("files") or [])
        result: dict[str, Any] = dict(row.get("result") or {})
        rid = f"{job['id']}:{line}"
        stored: list[str] = list(result.get("file_ids") or [])

        if result.get("document_id") is None and len(stored) < len(files):
            # Tra trùng trước khi đưa tệp vào kho: gửi lại cùng tệp không quét, lưu rồi lại gỡ hàng loạt tệp. Chỉ là
            # tối ưu — Action vẫn là bên quyết trùng hay không; dòng bị từ chối thì abandon() gỡ tệp đã lưu.
            if await self._existing(job, line, data) is not None:
                return Outcome("duplicate", message="Văn bản đến này đã được tiếp nhận (cùng số ký hiệu, cơ quan ban "
                               "hành, ngày ban hành) — chưa lưu tệp đính kèm", fields={"symbol": "duplicate"})
            # parse.py đã chặn restricted không phải true/false (bad_value) trước khi có lô: ở đây đúng ý văn thư
            restricted = data.get("restricted") is True
            if restricted and not self.sealing:
                return Outcome("failed", "vault_unavailable", "Chưa cấu hình két khóa nên chưa nhận được tệp của văn "
                               "bản hạn chế (F3.7)")
            opened = await chunk.archive()
            if opened is None:
                return Outcome("failed", "archive_lost", ARCHIVE_LOST)
            zf, entries = opened
            for name in files[len(stored):]:
                try:
                    blob = await asyncio.to_thread(read_entry, zf, entries, name, self.max_file_bytes)
                except EntryError as exc:
                    return Outcome("failed", exc.code, _clip(exc.message))
                try:
                    file_id = await self.ingest(rid, uuid.UUID(str(job["tenant_id"])), job["created_by"], blob, name,
                                                restricted)
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, dict) else {}
                    code, message = detail.get("code"), str(detail.get("message") or exc.detail)
                    if code in TRANSIENT:
                        raise Transient(code, message) from exc
                    if detail.get("signature"):
                        message = f"{message} ({detail['signature']})"
                    return Outcome("failed", row_code(code), _clip(f"{name}: {message}"))
                stored.append(file_id)
                result["file_ids"] = stored
                await chunk.save(line, result, stored=[file_id])    # tệp đã vào kho: lượt sau không lưu lại

        if result.get("document_id") is None:
            payload = dict(data)
            if stored:
                payload["file_ids"] = [*(data.get("file_ids") or []), *stored]
            try:
                out = await self._act(job, line, RECEIVE, {"d": payload})
            except HasuraError as exc:
                if exc.code == "duplicate":
                    found = await self._existing(job, line, data) if row["attempts"] > 1 else None
                    if found is None or not await self._ours(job, line, found):
                        return Outcome("duplicate", message=_clip(str(exc)), fields=exc.fields)
                    result["document_id"] = str(found["id"])
                    if found.get("register_number") is not None:
                        result["register_number"] = found["register_number"]
                else:
                    return self._failure(exc, row)
            else:
                result["document_id"] = out["receiveIncoming"]["document_id"]
            await chunk.save(line, result)

        if (job.get("options") or {}).get("register") and result.get("register_number") is None:
            try:
                out = await self._act(job, line, REGISTER, {"id": result["document_id"]})
            except HasuraError as exc:
                number = None
                if exc.code == "wrong_status":      # đã vào sổ ở lượt trước: đọc lại số
                    doc = await self.store.document(job, line, result["document_id"])
                    number = (doc or {}).get("register_number")
                if number is None:
                    if exc.code in TRANSIENT:
                        raise Transient(exc.code, str(exc)) from exc
                    # văn bản đã tiếp nhận (document_id giữ trong kết quả): văn thư vào sổ trên giao diện
                    return Outcome("failed", "register_failed", _clip(f"Đã tiếp nhận nhưng chưa vào sổ: {exc}"))
                result["register_number"] = number
            else:
                result["register_number"] = out["registerIncoming"]["register_number"]
            await chunk.save(line, result)
        return Outcome("ok")

    async def abandon(self, job: dict[str, Any], line: int, result: dict[str, Any]) -> int:
        """Dòng không thành văn bản: gỡ các tệp đã lưu cho dòng (dòng core.files rồi đối tượng trong kho). Câu gỡ chỉ
        nhận tệp chưa gắn văn bản nào — văn bản đã tạo mà vòng nền chưa kịp nhận id (mất phản hồi) vẫn giữ tệp của
        nó; khóa ngoại của office.document_files cũng chặn."""
        ids = [str(i) for i in result.get("file_ids") or []]
        if not ids or result.get("document_id"):
            return 0
        dropped = await self.store.drop_files(job, line, ids)
        for row in dropped:
            await self.discard(f"{job['id']}:{line}", row["object_key"])
        return len(dropped)

    def _failure(self, exc: HasuraError, row: dict[str, Any]) -> Outcome:
        if exc.code in TRANSIENT:
            raise Transient(exc.code, str(exc)) from exc
        if exc.code == "internal" and row["attempts"] < INTERNAL_TRIES:
            raise Transient(exc.code, str(exc)) from exc
        return Outcome("failed", row_code(exc.code), _clip(str(exc)), exc.fields)


def _now() -> datetime:
    return datetime.now(UTC)


class Importer:
    def __init__(self, store: Any, handlers: dict[str, Handler], spool: Spool, *, interval_s: float = 2.0,
                 chunk: int = 20, clock: Callable[[], datetime] = _now) -> None:
        self.store = store
        self.handlers = handlers
        self.spool = spool
        self.interval_s = interval_s
        self.chunk = chunk
        self.clock = clock
        self.started = time.time()

    def _log(self, event: str, *, level: int = logging.INFO, **fields: object) -> None:
        log.log(level, json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))

    async def prepare(self) -> None:
        """Dọn spool lúc khởi động: phần nhận dở, zip của lô đã xong hay không còn."""
        try:
            keep: set[str] | None = await self.store.open_ids()
        except HasuraError as exc:
            self._log("core.import.spool_unchecked", level=logging.WARNING, error=str(exc))
            keep = None
        removed = await asyncio.to_thread(self.spool.prepare, keep, before=self.started)
        if removed:
            self._log("core.import.spool_cleaned", removed=removed)

    async def run_once(self) -> bool:
        """Làm một mẻ của lô đến giờ sớm nhất; False khi không có lô nào đến giờ."""
        job = await self.store.due(self.clock())
        if job is None:
            return False
        try:
            await self._work(job)
        except Exception:
            # lỗi khi làm lô này (CSDL bận…): đẩy lô ra sau để lô khác vẫn chạy, rồi báo lên vòng ngoài
            try:
                await self.store.reschedule(job, {"run_after": (self.clock() + timedelta(
                    seconds=BACKOFF_MAX_S)).isoformat()})
            except Exception:  # noqa: BLE001, S110 — CSDL không trả lời thì lượt sau tự thử lại lô này
                pass
            raise
        return True

    async def _work(self, job: dict[str, Any]) -> None:
        handler = self.handlers.get(job["kind"])
        if handler is None:     # migration thêm loại mà svc-files chưa có handler: để đó, báo trong note
            await self.store.reschedule(job, {"run_after": (self.clock() + timedelta(hours=1)).isoformat(),
                                              "note": f"svc-files chưa xử lý được loại lô {job['kind']}"})
            return
        if job["status"] == "queued":
            await self.store.start(job, self.clock())
        actor = await self.store.actor(job)
        # không có trong danh bạ (chưa đồng bộ từ Keycloak) thì vẫn chạy: Action không dựa vào danh bạ
        if actor is not None and (not actor.get("enabled") or actor.get("role") not in handler.roles):
            stranded = await self.store.stranded(job)       # dòng chờ đã lưu tệp: gỡ tệp sau khi hủy dòng
            n = await self.store.fail_pending(job, {
                "status": "failed", "data": None, "code": "actor_revoked", "done_at": self.clock().isoformat(),
                "message": "Người tạo lô đã bị khóa hoặc không còn vai trò được nạp lô — dòng chưa ghi"})
            self._log("core.import.actor_revoked", job_id=job["id"], tenant_id=job["tenant_id"], rows=n)
            for row in stranded:
                await self._abandon(handler, job, row["line"], row.get("result"))
            await self._close(job)
            return
        await self._chunk(job, handler)

    def _until(self) -> datetime:
        return self.clock() + timedelta(seconds=LEASE_S)

    async def _chunk(self, job: dict[str, Any], handler: Handler) -> None:
        started = time.monotonic()
        rows = await self.store.pending(job, self.chunk, self.clock())
        chunk = Chunk(self.store, self.spool, job, self._until)
        done: Counter[str] = Counter()
        paused: tuple[Transient, int] | None = None
        try:
            for row in rows:
                line, attempts = row["line"], int(row["attempts"])
                spent = attempts >= MAX_ATTEMPTS    # tiến trình chết ở lượt cuối: nhận dòng chỉ để ghi lỗi
                claimed = await self.store.claim(job, line, attempts, now=self.clock(), until=self._until(),
                                                 claim_id=chunk.claim_id, bump=0 if spent else 1)
                if claimed is None:
                    continue        # vòng khác vừa nhận dòng này (đang giữ, hoặc attempts đã đổi): bỏ qua
                # dòng như đang có trong CSDL lúc nhận: tiến độ vòng giữ trước kịp lưu sau lúc đọc cũng có ở đây
                row, tries = claimed, int(claimed["attempts"])
                try:
                    if spent:
                        outcome = Outcome("failed", "unavailable", "Lõi không sẵn sàng quá lâu, đã thử lại nhiều lần "
                                          "— gửi lại dòng này sau")
                    else:
                        outcome = await handler.process(job, row, chunk)
                except LeaseLost as exc:
                    await self._lost(handler, job, line, exc.file_ids)
                    continue
                except Transient as exc:
                    if tries >= MAX_ATTEMPTS:
                        outcome = Outcome("failed", "unavailable", _clip(f"Lõi không sẵn sàng quá lâu: {exc.message}"))
                    else:
                        paused = (exc, tries)
                        await self.store.release(job, line, claim_id=chunk.claim_id)
                        break
                except Exception as exc:  # noqa: BLE001 — lỗi lạ của một dòng không được làm chết vòng nền
                    self._log("core.import.row_failed", level=logging.ERROR, job_id=job["id"], line=line,
                              error=f"{type(exc).__name__}: {exc}")
                    if tries < INTERNAL_TRIES:
                        paused = (Transient("internal", f"lỗi không mong đợi ({type(exc).__name__})"), tries)
                        await self.store.release(job, line, claim_id=chunk.claim_id)
                        break
                    outcome = Outcome("failed", "internal", "Lỗi không mong đợi khi xử lý dòng; đã ghi nhật ký với "
                                      f"mã {job['id']}:{line}")
                if not await self._finish(job, line, outcome, claim_id=chunk.claim_id):
                    await self._lost(handler, job, line, [])
                    continue
                if outcome.status != "ok":
                    await self._abandon(handler, job, line, chunk.results.get(line, row.get("result")))
                done[outcome.status] += 1
        finally:
            chunk.close()
        note = job.get("note")
        if chunk.archive_lost:
            note = ARCHIVE_LOST
        elif note and note.startswith(PAUSED):
            note = None
        self._log("core.import.chunk", job_id=job["id"], tenant_id=job["tenant_id"], rows=sum(done.values()),
                  ok=done["ok"], duplicate=done["duplicate"], failed=done["failed"],
                  ms=round((time.monotonic() - started) * 1000))
        if paused is not None:
            exc, tries = paused
            retry = self.clock() + timedelta(seconds=min(BACKOFF_MAX_S, 2 ** tries))
            note = _clip(f"{PAUSED}: {exc.message} — thử lại lúc {retry.astimezone(VN):%H:%M:%S}", NOTE_MAX)
            await self.store.reschedule(job, {"run_after": retry.isoformat(), "note": note})
            self._log("core.import.paused", job_id=job["id"], code=exc.code, retry_at=retry)
            return
        counts = await self.store.counts(job)
        if counts["pending"]:
            # nhường lô khác: lô này về cuối hàng đợi. Không lấy được dòng nào (vòng khác đang giữ mọi dòng còn chờ)
            # thì hỏi lại sau LEASE_RECHECK_S — vòng kia làm xong mẻ của nó sẽ tự đưa lô lên lại
            wait = 0 if rows else LEASE_RECHECK_S
            await self.store.reschedule(job, {"run_after": (self.clock() + timedelta(seconds=wait)).isoformat(),
                                              "note": note})
            return
        await self._close(job, note=note)

    async def _abandon(self, handler: Handler, job: dict[str, Any], line: int, result: dict[str, Any] | None) -> None:
        """Dòng đã kết thúc không thành văn bản: gỡ tệp đã lưu cho dòng. Lỗi lúc gỡ không làm hỏng mẻ — tệp còn lại
        được ghi nhật ký để người vận hành dọn."""
        if not (result or {}).get("file_ids"):
            return
        try:
            n = await handler.abandon(job, line, result or {})
        except Exception as exc:  # noqa: BLE001 — dòng đã xong; chỉ còn tệp chưa gỡ được
            self._log("core.import.files_left", level=logging.WARNING, job_id=job["id"], line=line,
                      file_ids=(result or {}).get("file_ids"), error=f"{type(exc).__name__}: {exc}")
            return
        if n:
            self._log("core.import.files_dropped", job_id=job["id"], tenant_id=job["tenant_id"], line=line, files=n)

    async def _lost(self, handler: Handler, job: dict[str, Any], line: int, file_ids: list[str]) -> None:
        """Dòng đã sang tay vòng khác giữa chừng (quá hạn giữ) hoặc cả lô bị hủy: không ghi gì thêm cho dòng, không
        gỡ tệp trong dòng (vòng kia dùng). Tệp vừa lưu mà chưa ghi được vào dòng thì không ai biết tới: gỡ ngay."""
        self._log("core.import.lease_lost", level=logging.WARNING, job_id=job["id"], line=line, files=len(file_ids))
        await self._abandon(handler, job, line, {"file_ids": file_ids})

    async def _finish(self, job: dict[str, Any], line: int, outcome: Outcome, *, claim_id: str) -> bool:
        return await self.store.finish(job, line, {
            "status": outcome.status, "data": None, "code": outcome.code if outcome.status == "failed" else None,
            "message": _clip(outcome.message), "fields": outcome.fields, "done_at": self.clock().isoformat()},
            claim_id=claim_id)

    async def _close(self, job: dict[str, Any], *, note: str | None = None) -> None:
        counts = await self.store.counts(job)
        if counts["pending"]:
            await self.store.reschedule(job, {"run_after": self.clock().isoformat()})
            return
        at = self.clock().isoformat()
        tally = {"ok": counts["ok"], "duplicate": counts["duplicate"], "failed": counts["failed"]}
        # dòng sổ import.finished do trigger import_jobs_finished ghi khi lô chuyển sang done, cùng giao dịch: hai vòng
        # cùng đóng thì lệnh sau không đổi gì (closed False), sổ vẫn một dòng
        closed = await self.store.close(job, {"status": "done", "finished_at": at, "run_after": at, "note": note,
                                              **tally})
        await asyncio.to_thread(self.spool.drop, job["id"])
        if closed:
            self._log("core.import.finished", job_id=job["id"], tenant_id=job["tenant_id"], **tally)

    async def run(self) -> None:
        try:
            await self.prepare()
        except Exception as exc:  # noqa: BLE001 — dọn không được thì vẫn chạy
            self._log("core.import.spool_unchecked", level=logging.WARNING, error=f"{type(exc).__name__}: {exc}")
        while True:
            try:
                busy = await self.run_once()
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết; lượt sau thử lại
                self._log("core.import.failed", level=logging.WARNING, error=f"{type(exc).__name__}: {exc}")
                busy = False
            # còn lô đến giờ thì làm tiếp ngay, hết thì nghỉ
            await asyncio.sleep(0 if busy else self.interval_s)
