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

"""Liên thông văn bản trong hệ thống (F3.12): chép bản phát hành của văn bản đi sang kho của đơn vị nhận.

Văn bản đi có đơn vị nhận trong hệ thống thì lúc phát hành CSDL thêm một dòng ``office.dispatches`` (outbox) cho mỗi
đơn vị, ngay trong giao dịch phát hành. svc-workflow gọi ``POST /internal/dispatch-file`` với id dòng đó; svc-files:

1. đọc dòng outbox, văn bản nguồn và bản phát hành (vai trò ``issued``) bằng khóa quản trị — bên gọi chỉ đưa id dòng,
   không chỉ định được tệp nào khác;
2. từ chối (409) khi dòng không còn chờ, văn bản chưa phát hành, văn bản hạn chế hoặc tệp mã hóa (bản mã gắn với đơn
   vị gửi — F3.7), tệp đã sang kho lạnh, hoặc byte đọc từ kho không khớp băm trong ``core.files``, ``content_sha256``
   của văn bản và băm chụp vào dòng outbox lúc phát hành;
3. quét ClamAV như mọi tệp vào kho, ghi bản sao dưới tiền tố của đơn vị nhận, thêm dòng ``core.files`` thuộc đơn vị
   nhận với id định trước (``dispatches.file_id``) — gọi lại bao nhiêu lần cũng chỉ có một bản sao.

Sau đó svc-workflow gọi hàm ``office.deliver_dispatch`` trong phiên của đơn vị nhận để tạo văn bản đến gắn bản sao
làm tệp ``main``: vòng đọc chữ (texts.py) và đồng bộ tìm kiếm (search.py) nhận nó như tệp tải lên thường.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .clamav import ScanError
from .hasura import HasuraError
from .storage import ObjectMissing, StorageError, object_key

CHUNK_SIZE = 64 * 1024

# log(event, **fields): một dòng nhật ký JSON, kèm request id của lời gọi
Log = Callable[..., None]
# bỏ đối tượng vừa ghi khi không thêm được dòng CSDL (app.discard)
Drop = Callable[[str], Awaitable[None]]


class DispatchError(Exception):
    """Không chép được; status, code, message trả nguyên cho svc-workflow."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _refuse(code: str, message: str) -> DispatchError:
    return DispatchError(409, code, message)


@dataclass(frozen=True)
class Copied:
    file_id: uuid.UUID
    tenant_id: uuid.UUID        # đơn vị nhận
    sha256: str
    size_bytes: int
    created: bool               # False: bản sao đã có từ lần gọi trước, hoặc lần gọi song song thêm dòng trước


def issued_file(row: dict[str, Any]) -> dict[str, Any]:
    """Bản phát hành sẽ chép, sau khi kiểm dòng outbox và văn bản nguồn (hasura.dispatch_source)."""
    if row["status"] != "pending":
        raise _refuse("not_pending", f"Dòng liên thông đã ở trạng thái {row['status']}, không còn chờ chép tệp")
    doc = row["document"]
    if doc["status"] not in ("issued", "archived"):
        raise _refuse("not_issued", "Văn bản chưa phát hành")
    if doc["restricted"]:
        raise _refuse("restricted", "Văn bản hạn chế không gửi liên thông trong hệ thống")
    if not doc["issued"]:
        # nộp lưu (F3.8) gỡ liên kết tệp của văn bản, tệp sang kho lạnh
        if doc["status"] == "archived":
            raise _refuse("cold", "Văn bản đã nộp lưu, bản phát hành đã sang kho lạnh")
        raise _refuse("not_issued", "Văn bản chưa có bản phát hành")
    f = doc["issued"][0]
    if f["encrypted"]:
        raise _refuse("restricted", "Bản phát hành lưu mã hóa theo khóa của đơn vị gửi, không chép sang đơn vị khác")
    if f["storage_tier"] != "hot":
        raise _refuse("cold", "Bản phát hành đã sang kho lạnh")
    return f


def _existing(row: dict[str, Any], to_tenant: uuid.UUID) -> Copied:
    if uuid.UUID(str(row["tenant_id"])) != to_tenant:
        raise _refuse("integrity", "Id bản sao đã là tệp của đơn vị khác")
    return Copied(uuid.UUID(str(row["id"])), to_tenant, row["sha256"], int(row["size_bytes"]), created=False)


async def _read(store: Any, f: dict[str, Any], dispatch_id: uuid.UUID, log: Log) -> bytes:
    try:
        return b"".join(await asyncio.to_thread(lambda: list(store.read_stream(f["object_key"], CHUNK_SIZE))))
    except ObjectMissing as exc:
        log("office.dispatch.source_missing", dispatch_id=dispatch_id, file_id=f["id"], error=str(exc))
        raise _refuse("integrity", "Không còn bản phát hành trong kho tệp") from exc
    except StorageError as exc:
        log("core.file.read_failed", file_id=f["id"], object_key=f["object_key"], error=str(exc))
        raise DispatchError(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc


async def copy_issued_file(dispatch_id: uuid.UUID, *, actor_id: str, request_id: str, hasura: Any, store: Any,
                           scanner: Any, log: Log, drop: Drop) -> Copied:
    """Chép bản phát hành của dòng outbox sang đơn vị nhận; lỗi thì DispatchError (409 từ chối, 503 thử lại sau)."""
    try:
        row = await hasura.dispatch_source(dispatch_id)
        existing = await hasura.dispatched_file(uuid.UUID(row["file_id"])) if row else None
    except HasuraError as exc:
        log("office.dispatch.lookup_failed", dispatch_id=dispatch_id, code=exc.code, error=str(exc))
        raise DispatchError(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
    if row is None:
        raise DispatchError(404, "not_found", "Không có dòng liên thông này")
    to_tenant, file_id = uuid.UUID(row["to_tenant_id"]), uuid.UUID(row["file_id"])
    # Đã chép (lần trước svc-workflow quá hạn chờ, hoặc chép xong mà chưa tạo được văn bản đến): trả lại bản sao đó,
    # kể cả khi dòng outbox vừa được một bản svc-workflow khác chuyển sang delivered
    if existing is not None:
        return _existing(existing, to_tenant)

    f = issued_file(row)
    data = await _read(store, f, dispatch_id, log)
    digest = hashlib.sha256(data).hexdigest()
    if {f["sha256"], row["document"]["content_sha256"], row["source_sha256"]} != {digest} \
            or len(data) != int(f["size_bytes"]):
        log("office.dispatch.integrity_failed", dispatch_id=dispatch_id, file_id=f["id"], sha256=digest,
            size_bytes=len(data))
        raise _refuse("integrity", "Bản phát hành trong kho không khớp băm SHA-256 đã ghi lúc phát hành — không chép")

    # Như mọi tệp vào kho: quét trước, sạch mới ghi
    async def chunks() -> AsyncIterator[bytes]:
        for i in range(0, len(data), CHUNK_SIZE):
            yield data[i:i + CHUNK_SIZE]

    try:
        result = await scanner.scan(chunks())
    except ScanError as exc:
        log("core.file.scan_failed", dispatch_id=dispatch_id, error=str(exc))
        raise DispatchError(503, "scanner_unavailable", "Trạm quét mã độc chưa sẵn sàng, chưa chép tệp") from exc
    scanned_at = datetime.now(UTC)
    if not result.clean:
        details = {"filename": f["filename"], "size_bytes": len(data), "sha256": digest, "signature": result.signature,
                   "dispatch_id": str(dispatch_id), "from_tenant_id": str(row["tenant_id"])}
        log("core.file.rejected", tenant_id=to_tenant, actor_id=actor_id, **details)
        try:   # vào sổ của đơn vị nhận — tệp bị chặn trước cửa kho của họ
            await hasura.log_event(tenant_id=to_tenant, actor_id=actor_id, request_id=request_id, action="file.rejected",
                                   entity="core.files", entity_id=digest, details=details, actor_kind="service")
        except HasuraError as exc:
            log("core.file.audit_failed", error=str(exc))
        code = "unscannable" if result.unscannable else "infected"
        raise DispatchError(422, code, "Trạm quét mã độc chặn bản phát hành — không chép")

    key = object_key(to_tenant, file_id, scanned_at)
    try:
        await asyncio.to_thread(store.put, key, io.BytesIO(data), size=len(data), content_type=f["mime_type"],
                                sha256_hex=digest)
    except StorageError as exc:
        log("core.file.store_failed", object_key=key, error=str(exc))
        raise DispatchError(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng, chưa chép tệp") from exc
    try:
        await hasura.insert_file(tenant_id=to_tenant, actor_id=actor_id, request_id=request_id, file_id=file_id,
                                 object_key=key, filename=f["filename"], mime_type=f["mime_type"], size_bytes=len(data),
                                 sha256_hex=digest, scanned_at=scanned_at)
    except HasuraError as exc:
        log("core.file.record_failed", object_key=key, code=exc.code, error=str(exc))
        return await _settle(hasura, key, file_id, to_tenant, drop, exc)
    return Copied(file_id, to_tenant, digest, len(data), created=True)


async def _settle(hasura: Any, key: str, file_id: uuid.UUID, to_tenant: uuid.UUID, drop: Drop,
                  error: HasuraError) -> Copied:
    """Không thêm được dòng core.files: một lần gọi song song đã thêm trước (trùng khóa chính) hay CSDL lỗi?"""
    try:
        winner = await hasura.dispatched_file(file_id)
    except HasuraError:
        # Không biết dòng đã vào chưa (lỗi có thể tới sau khi CSDL đã ghi): giữ đối tượng — thừa một đối tượng trong
        # kho còn hơn dòng core.files trỏ vào chỗ trống. Lần gọi lại trong tháng ghi đúng khóa này.
        raise DispatchError(503, "database_unavailable", "CSDL chưa sẵn sàng, chưa chép xong tệp") from error
    if winner is None:
        await drop(key)
        raise DispatchError(503, "database_unavailable", "CSDL chưa sẵn sàng, chưa chép tệp") from error
    # Lần gọi kia thắng: dùng dòng của nó. Cùng tháng thì hai lần ghi cùng một khóa đối tượng — đó là đối tượng của
    # dòng thắng, giữ nguyên; chỉ bỏ đối tượng của mình khi khóa khác.
    if winner["object_key"] != key:
        await drop(key)
    return _existing(winner, to_tenant)
