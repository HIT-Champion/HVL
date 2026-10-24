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

"""Route ``/api/imports`` — tạo lô nạp, xem lô, xem lỗi từng dòng.

Đi qua route svc-files của APISIX (token người dùng). Tạo lô: kiểm token, vai trò, Content-Length trước khi đọc
multipart (như ``POST /api/files``); tệp dữ liệu qua đúng trạm kiểm dịch ClamAV (``quarantine`` của app.py — nhiễm thì
ghi ``file.rejected``, 422, không có lô); đọc, kiểm cả tệp; zip chép vào spool; lô + dòng + dòng sổ ``import.created``
ghi trong một mutation; 202. Xử lý từng dòng ở vòng nền (runner.py).
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu của dependency khai báo trong install().
import asyncio
import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from ..auth import Principal
from ..config import Settings
from ..hasura import HasuraError
from .parse import ParseError, Row, guess_format, parse
from .runner import Handler
from .spool import Spool, check_rows
from .store import STATUSES, ImportStore, KeyTaken

log = logging.getLogger("svc_files")

Kind = Literal["incoming"]
KEY_RE = re.compile(r"[!-~]{1,200}")
NO_STORE = {"Cache-Control": "no-store"}
RETRY_AFTER = "60"


class ImportOut(BaseModel):
    id: uuid.UUID
    kind: Kind = Field(description="incoming: văn bản đến")
    status: Literal["queued", "running", "done"] = Field(
        description="queued: chờ vòng nền · running: đang xử lý · done: mọi dòng đã xong (đạt, trùng hoặc lỗi)")
    filename: str = Field(description="Tên tệp dữ liệu đã gửi")
    format: Literal["ndjson", "csv"]
    # tên "register" trùng phương thức của lớp cha (ABCMeta.register): đặt tên khác, giữ tên trên API bằng alias
    with_register: bool = Field(alias="register",
                                description="Vào sổ từng văn bản sau khi tiếp nhận (registerIncoming)")
    total: int = Field(description="Số dòng dữ liệu đã nhận (không tính dòng trống, tiêu đề CSV)")
    pending: int = Field(description="Dòng chưa xử lý")
    ok: int = Field(description="Dòng đã ghi (và vào sổ khi register=true)")
    duplicate: int = Field(description="Dòng trùng văn bản đã có (cùng số ký hiệu, cơ quan ban hành, ngày ban hành)")
    failed: int = Field(description="Dòng lỗi — lý do ở GET /api/imports/{id}/rows?status=failed")
    note: str | None = Field(description="Ghi chú của lô, vd tạm dừng vì lõi bận, tệp nén mất sau khi svc-files khởi "
                                         "động lại")
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ImportRowOut(BaseModel):
    line: int = Field(description="NDJSON: dòng vật lý tính từ 1; CSV: hàng như Excel (tiêu đề là 1)")
    status: Literal["pending", "ok", "duplicate", "failed"]
    code: str | None = Field(description="Mã lỗi khi failed, vd invalid, bad_json, missing_attachment, infected, "
                                         "archive_lost, register_failed (services/svc-files/README.md)")
    message: str | None = Field(description="Lý do, tiếng Việt")
    fields: dict[str, str] | None = Field(description="Lỗi theo trường như form tiếp nhận: trường → mã "
                                                      "(schemas/README.md)")
    document_id: uuid.UUID | None = Field(description="Văn bản đã tạo (cả khi vào sổ lỗi: register_failed)")
    register_number: int | None = Field(description="Số đến khi register=true")


class ImportRowsOut(BaseModel):
    rows: list[ImportRowOut]
    next_after: int | None = Field(description="Gửi lại ở tham số `after` để lấy trang sau; null khi đã hết")


class ImportsOut(BaseModel):
    imports: list[ImportOut]


def import_body() -> dict[str, Any]:
    return {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object",
        "required": ["data"],
        "properties": {
            "data": {"type": "string", "format": "binary",
                     "description": "NDJSON (mỗi dòng một object) hoặc CSV có tiêu đề, UTF-8; cùng trường với "
                                    "receiveIncoming(data), thêm `files`: tên tệp trong zip, tệp đầu là bản chính"},
            "archive": {"type": "string", "format": "binary", "description": "Zip tệp đính kèm (tùy chọn)"},
        },
    }}}}}


CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"model": ImportOut, "description": "Gửi lại cùng Idempotency-Key, cùng nội dung: lô đã tạo trước đó"},
    400: {"description": "`missing_file` · `unknown_format` · `bad_encoding` (không phải UTF-8) · `bad_header` (CSV "
                         "thiếu cột bắt buộc, có cột lạ) · `bad_format` (CSV hỏng cấu trúc) · `empty` · `bad_archive` "
                         "(zip hỏng, quá 5000 mục, tên trùng) · `bad_idempotency_key` · `empty_file`"},
    401: {"description": "Thiếu hoặc sai token"},
    403: {"description": "`forbidden` — không phải văn thư · `unknown_tenant`"},
    409: {"description": "`idempotency_conflict` — cùng Idempotency-Key mà khác tệp, định dạng hoặc register"},
    413: {"description": "`too_large` (thân yêu cầu, tệp dữ liệu MOC_IMPORT_DATA_MAX_MB, zip MOC_IMPORT_ZIP_MAX_MB, "
                         "tổng cỡ tệp các dòng trỏ tới — mỗi lần trỏ tính một lần — MOC_IMPORT_STORE_MAX_MB) · "
                         "`too_many_rows` (MOC_IMPORT_MAX_ROWS; register=true: MOC_IMPORT_REGISTER_MAX_ROWS)"},
    422: {"description": "`infected` / `unscannable` — chính tệp dữ liệu bị trạm quét chặn, đã ghi `file.rejected` "
                         "vào sổ kiểm toán, không tạo lô"},
    429: {"description": "`too_many_imports` — đơn vị đã có MOC_IMPORT_MAX_OPEN lô chưa xong (kèm `Retry-After`)"},
    503: {"description": "`imports_disabled` (MOC_IMPORT_INTERVAL_S=0) · `busy` (chỗ giữ zip đầy, kèm `Retry-After`) "
                         "· `scanner_unavailable` · `database_unavailable`"},
}

READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Thiếu hoặc sai token"},
    404: {"description": "`not_found` — không có lô, hoặc lô của người khác (kể cả cùng đơn vị) — hai trường hợp như "
                         "nhau"},
    503: {"description": "`database_unavailable`"},
}


def _error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message}, headers)


def _out(job: dict[str, Any]) -> dict[str, Any]:
    return ImportOut.model_validate(job).model_dump(mode="json", by_alias=True)


def _row_out(row: dict[str, Any]) -> ImportRowOut:
    result = row.get("result") or {}
    return ImportRowOut(line=row["line"], status=row["status"], code=row.get("code"), message=row.get("message"),
                        fields=row.get("fields"), document_id=result.get("document_id"),
                        register_number=result.get("register_number"))


def _db_unavailable(exc: HasuraError) -> HTTPException:
    if exc.code == "constraint-violation":      # thường gặp nhất: đơn vị trong token chưa có trong core.tenants
        return _error(403, "unknown_tenant", "Đơn vị của tài khoản chưa được đăng ký trong hệ thống")
    return _error(503, "database_unavailable", "CSDL chưa sẵn sàng, chưa tạo lô")


def install(app: FastAPI, *, settings: Settings, store: ImportStore, handlers: dict[str, Handler], spool: Spool,
            principal: Callable[..., Principal], quarantine: Callable[..., Awaitable[Any]],
            clean_filename: Callable[[str | None], str], max_body: int) -> None:
    """Gắn các route nạp lô vào app. ``quarantine``: trạm kiểm dịch của app.py (cùng hàm với POST /api/files);
    ``max_body``: trần Content-Length của yêu cầu tạo lô (tệp dữ liệu + zip + phần đầu multipart)."""
    enabled = settings.import_interval_s > 0

    async def check_open(who: Principal, rid: str) -> None:
        try:
            n = await store.count_open(who.tenant_id, who.user_id, rid=rid)
        except HasuraError as exc:
            raise _db_unavailable(exc) from exc
        if n >= settings.import_max_open:
            raise _error(429, "too_many_imports", f"Đơn vị đang có {n} lô chưa xong (tối đa "
                         f"{settings.import_max_open}) — đợi lô trước xong rồi gửi lại", {"Retry-After": RETRY_AFTER})

    def replay(existing: dict[str, Any], kind: str, sha: str, archive: str | None, fmt: str,
               register: bool) -> JSONResponse:
        same = (existing["kind"] == kind and existing["data_sha256"] == sha and existing["archive_sha256"] == archive
                and existing["format"] == fmt and existing["register"] == register)
        if not same:
            raise _error(409, "idempotency_conflict", "Idempotency-Key này đã dùng cho một lô khác nội dung (tệp, "
                         "định dạng hoặc register) — dùng khóa mới cho lô mới")
        return JSONResponse(_out(existing), status_code=200,
                            headers={"Location": f"/api/imports/{existing['id']}", **NO_STORE})

    # Không khai tham số UploadFile: FastAPI sẽ đọc hết thân request TRƯỚC khi kiểm token (như POST /api/files)
    @app.post(
        "/api/imports/{kind}",
        status_code=202,
        response_model=ImportOut,
        openapi_extra=import_body(),
        responses=CREATE_RESPONSES,
        summary="Nạp lô: gửi tệp NDJSON/CSV nhiều văn bản đến (kèm zip tệp đính kèm), xử lý nền",
        description=(
            "Chỉ văn thư. Mỗi dòng đi đúng đường tiếp nhận lẻ: tệp đính kèm qua trạm quét ClamAV rồi mới vào kho, "
            "Action `receiveIncoming` thay mặt người gửi (cách ly đơn vị, sổ kiểm toán chuỗi băm từng văn bản), tùy "
            "chọn `registerIncoming`. Lỗi một dòng không hỏng dòng khác. Trả 202 và `Location` của lô; theo dõi ở GET "
            "/api/imports/{id}, lỗi từng dòng ở /rows. Gửi lại cùng tệp không nhân đôi: dòng đã nạp báo `duplicate`; "
            "kèm `Idempotency-Key` thì nhận lại đúng lô cũ (200)."),
    )
    async def create_import(
        kind: Annotated[Kind, Path(description="Loại lô; hiện có incoming (văn bản đến)")],
        request: Request,
        who: Annotated[Principal, Depends(principal)],
        format: Annotated[Literal["ndjson", "csv"] | None, Query(  # noqa: A002 — tên tham số trên API
            description="Thiếu thì đoán theo đuôi tên tệp (.ndjson, .jsonl, .csv) rồi theo Content-Type")] = None,
        register: Annotated[bool, Query(description=(
            "Vào sổ từng văn bản sau khi tiếp nhận (cấp số đến, khởi chạy quy trình, báo lãnh đạo). Lô có vào sổ tối "
            "đa MOC_IMPORT_REGISTER_MAX_ROWS dòng"))] = False,
        idempotency_key: Annotated[str | None, Header(
            alias="Idempotency-Key", description="Tùy chọn, 1–200 ký tự ASCII in được: gửi lại cùng khóa trả đúng "
                                                 "lô cũ")] = None,
    ) -> JSONResponse:
        handler = handlers[kind]
        if not handler.roles & set(who.roles):
            raise _error(403, "forbidden", "Chỉ văn thư được nạp lô văn bản đến")
        if not enabled:
            raise _error(503, "imports_disabled", "Nạp lô đang tắt (MOC_IMPORT_INTERVAL_S=0)")
        key = idempotency_key
        if key is not None and not KEY_RE.fullmatch(key):
            raise _error(400, "bad_idempotency_key", "Idempotency-Key phải là 1–200 ký tự ASCII in được, không khoảng "
                         "trắng")
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > max_body:
            raise _error(413, "too_large", f"Yêu cầu vượt giới hạn: tệp dữ liệu tối đa "
                         f"{settings.import_data_max_bytes // (1024 * 1024)} MB, tệp nén tối đa "
                         f"{settings.import_zip_max_bytes // (1024 * 1024)} MB")
        rid = request.state.request_id
        if key is None:
            await check_open(who, rid)

        job_id = uuid.uuid4()
        form = await request.form(max_files=2, max_fields=1)
        try:
            return await _create(kind, handler, request, who, form, job_id, rid, format, register, key)
        except BaseException:
            spool.drop(job_id)
            raise
        finally:
            await form.close()

    async def _create(kind: str, handler: Handler, request: Request, who: Principal, form: Any, job_id: uuid.UUID,
                      rid: str, explicit: str | None, register: bool, key: str | None) -> JSONResponse:
        data, archive = form.get("data"), form.get("archive")
        if not isinstance(data, UploadFile):
            raise _error(400, "missing_file", "Thiếu trường 'data' (tệp NDJSON hoặc CSV) trong form multipart")
        if archive is not None and not isinstance(archive, UploadFile):
            raise _error(400, "missing_file", "Trường 'archive' phải là tệp zip")
        try:
            fmt = guess_format(explicit, data.filename, data.content_type)
        except ParseError as exc:
            raise _error(exc.status, exc.code, exc.message) from exc
        filename = clean_filename(data.filename)
        # tệp dữ liệu qua đúng trạm kiểm dịch của tải lên lẻ: nhiễm thì file.rejected vào sổ, 422, không có lô
        digest = await quarantine(rid, who.tenant_id, who.user_id, data, filename=filename,
                                  limit=settings.import_data_max_bytes)
        await data.seek(0)
        raw = await data.read()
        archived: tuple[str, int] | None = None
        if archive is not None:
            try:
                archived = await asyncio.to_thread(spool.receive, archive.file, job_id, settings.import_zip_max_bytes)
            except ParseError as exc:
                raise _error(exc.status, exc.code, exc.message) from exc
        archive_sha = archived[0] if archived else None

        if key is not None:
            try:
                existing = await store.by_key(who.tenant_id, who.user_id, key, rid=rid)
            except HasuraError as exc:
                raise _db_unavailable(exc) from exc
            if existing is not None:
                spool.drop(job_id)
                return replay(existing, kind, digest.hexdigest(), archive_sha, fmt, register)
            await check_open(who, rid)
        if archived and spool.used() > spool.max_bytes:
            raise _error(503, "busy", "Chỗ giữ tệp nén của các lô đang chạy đã đầy — gửi lại sau ít phút",
                         {"Retry-After": RETRY_AFTER})

        limit = settings.import_register_max_rows if register else settings.import_max_rows
        try:
            # đọc tệp 5 MB mất cỡ một giây: chạy trong luồng riêng, không giữ vòng sự kiện của các yêu cầu khác
            rows = await asyncio.to_thread(parse, raw, fmt, handler.columns, max_rows=limit)  # type: ignore[arg-type]
            entries = await asyncio.to_thread(spool.entries, job_id) if archived else None
            check_rows(rows, entries, settings.max_upload_bytes, settings.import_store_max_bytes)
        except ParseError as exc:
            if exc.code == "too_many_rows" and register:
                exc.message += f" (lô có vào sổ tối đa {limit} dòng)"
            raise _error(exc.status, exc.code, exc.message) from exc
        if archived and any(r.files and not r.failed for r in rows):
            spool.commit(job_id)        # trước khi ghi lô: vòng nền thấy lô thì zip đã ở chỗ của nó
        else:
            spool.drop(job_id)

        options = {"register": register}
        now = datetime.now(UTC)
        job = {"id": str(job_id), "kind": kind, "created_by": who.user_id, "department_id": who.department_id,
               "filename": filename, "format": fmt, "data_sha256": digest.hexdigest(), "archive_sha256": archive_sha,
               "archive_bytes": archived[1] if archived else None, "options": options, "idempotency_key": key,
               "total": len(rows)}
        failed = sum(r.failed for r in rows)
        audit = {"actor_id": who.user_id, "actor_kind": "user", "request_id": rid, "action": "import.created",
                 "entity": "core.import_jobs", "entity_id": str(job_id),
                 "diff": {"kind": kind, "format": fmt, "register": register, "total": len(rows), "failed": failed,
                          "filename": filename}}
        try:
            await store.create(job, [_row_in(job_id, r, now) for r in rows], audit, tenant_id=who.tenant_id,
                               user=who.user_id, rid=rid)
        except KeyTaken:
            spool.drop(job_id)
            existing = await store.by_key(who.tenant_id, who.user_id, key or "", rid=rid)
            if existing is None:
                raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng, chưa tạo lô") from None
            return replay(existing, kind, digest.hexdigest(), archive_sha, fmt, register)
        except HasuraError as exc:
            log.warning(json.dumps({"event": "core.import.create_failed", "request_id": rid, "code": exc.code,
                                    "error": str(exc)}, ensure_ascii=False))
            raise _db_unavailable(exc) from exc
        log.info(json.dumps({"event": "core.import.created", "request_id": rid, "job_id": str(job_id),
                             "tenant_id": str(who.tenant_id), "actor_id": who.user_id, "kind": kind, "format": fmt,
                             "rows": len(rows), "failed": failed, "register": register,
                             "archive_bytes": job["archive_bytes"]}, ensure_ascii=False))
        out = {**job, "status": "queued", "register": register, "pending": len(rows) - failed, "ok": 0,
               "duplicate": 0, "failed": failed, "note": None, "created_at": now, "started_at": None,
               "finished_at": None}
        return JSONResponse(_out(out), status_code=202, headers={"Location": f"/api/imports/{job_id}", **NO_STORE})

    def _row_in(job_id: uuid.UUID, row: Row, now: datetime) -> dict[str, Any]:
        base = {"job_id": str(job_id), "line": row.line, "files": row.files}
        if row.failed:
            return {**base, "data": None, "status": "failed", "code": row.code, "message": (row.message or "")[:500],
                    "done_at": now.isoformat()}
        return {**base, "data": row.data}

    async def _job(who: Principal, job_id: uuid.UUID, rid: str) -> dict[str, Any]:
        try:
            job = await store.get(who.tenant_id, who.user_id, job_id, rid=rid)
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        if job is None:
            raise _error(404, "not_found", "Không có lô này")
        return job

    @app.get("/api/imports/{job_id}", response_model=ImportOut, responses=READ_RESPONSES,
             summary="Trạng thái một lô nạp: đã nhận, đang chờ, đạt, trùng, lỗi")
    async def get_import(job_id: uuid.UUID, request: Request,
                         who: Annotated[Principal, Depends(principal)]) -> JSONResponse:
        return JSONResponse(_out(await _job(who, job_id, request.state.request_id)), headers=NO_STORE)

    @app.get("/api/imports/{job_id}/rows", response_model=ImportRowsOut, responses=READ_RESPONSES,
             summary="Kết quả từng dòng của lô nạp (số dòng, mã, lý do) — không trả lại dữ liệu đã gửi")
    async def import_rows(
        job_id: uuid.UUID,
        request: Request,
        who: Annotated[Principal, Depends(principal)],
        status: Literal["pending", "ok", "duplicate", "failed"] | None = None,
        after: Annotated[int, Query(ge=0, description="Số dòng cuối của trang trước (`next_after`)")] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> JSONResponse:
        rid = request.state.request_id
        await _job(who, job_id, rid)
        try:
            rows = await store.rows(who.tenant_id, who.user_id, job_id, statuses=[status] if status else STATUSES,
                                    after=after, limit=limit, rid=rid)
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        out = ImportRowsOut(rows=[_row_out(r) for r in rows],
                            next_after=rows[-1]["line"] if len(rows) == limit else None)
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

    @app.get("/api/imports", response_model=ImportsOut, responses={401: READ_RESPONSES[401], 503: READ_RESPONSES[503]},
             summary="Các lô nạp của chính người gọi, mới trước")
    async def list_imports(request: Request, who: Annotated[Principal, Depends(principal)],
                           limit: Annotated[int, Query(ge=1, le=50)] = 20) -> JSONResponse:
        try:
            jobs = await store.list(who.tenant_id, who.user_id, limit, rid=request.state.request_id)
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        out = ImportsOut(imports=[ImportOut.model_validate(j) for j in jobs])
        return JSONResponse(out.model_dump(mode="json", by_alias=True), headers=NO_STORE)
