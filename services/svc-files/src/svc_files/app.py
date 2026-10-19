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

"""API HTTP của svc-files.

Tải lên (F1.5, F1.6): kiểm token → quét ClamAV → sạch mới ghi SeaweedFS → thêm dòng core.files qua
Hasura. ClamAV không trả lời thì từ chối (503), không bao giờ lưu tệp chưa quét; tệp nhiễm được ghi vào
sổ kiểm toán. Tải xuống: hỏi Hasura bằng chính token người dùng xem họ có được xem tệp không, rồi mới
đọc từ SeaweedFS. Tìm kiếm (F1.7): Meilisearch xếp hạng, Hasura lọc theo quyền — chi tiết ở search.py.

Văn bản đi (F2.4): svc-workflow gọi /internal/issue bằng token tài khoản dịch vụ khi văn thư phát hành —
dựng PDF có số, mã QR từ dữ liệu trong CSDL, quét, lưu như mọi tệp. Người được đọc dự thảo xem trước bản PDF
ở /api/documents/{id}/preview. Cổng xác thực (F2.13): /api/verify trả thông tin công khai của đúng một văn
bản đã phát hành theo mã tra cứu hoặc băm SHA-256, không cần đăng nhập.

Chạy: ``uvicorn svc_files.app:create_app --factory``
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu của
# dependency khai báo bên trong create_app().
import asyncio
import hashlib
import io
import json
import logging
import re
import unicodedata
import uuid
from collections.abc import Iterator
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from . import __version__
from .anchors import Anchorer, AnchorStore
from .auth import AuthError, Principal, TokenVerifier
from .clamav import ClamAVClient, ScanError
from .config import Settings
from .hasura import HasuraAuthError, HasuraClient, HasuraError
from .render import letter_from, render_pdf
from .search import Indexer, MeiliClient, SearchError, SearchQuery, search_documents
from .storage import ObjectStore, StorageError, object_key, s3_client

CHUNK_SIZE = 64 * 1024
# Phần đầu và biên của multipart cộng thêm vào kích thước tệp
MULTIPART_OVERHEAD = 64 * 1024
MIME_RE = re.compile(r"^[\w.+-]+/[\w.+-]+$")

log = logging.getLogger("svc_files")


def _setup_logging() -> None:
    """Mỗi dòng nhật ký là một đối tượng JSON trên stdout; uvicorn chỉ cấu hình logger của riêng nó."""
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False


class FileOut(BaseModel):
    # Không trả object_key: vị trí trong kho là chuyện nội bộ, tệp chỉ lấy qua GET /api/files/{id}.
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    scanned_at: datetime


Status = Literal[
    "received", "registered", "in_progress", "done", "draft", "in_review", "returned", "approved", "issued",
    "archived", "cancelled",
]
Urgency = Literal["normal", "khan", "thuong_khan", "hoa_toc"]


class SearchHit(BaseModel):
    id: uuid.UUID
    direction: Literal["in", "out"]
    status: Status
    type_code: str
    symbol: str | None
    issuer_name: str | None
    issued_on: date | None
    summary: str
    urgency: Urgency
    register_number: int | None
    registered_at: datetime | None
    due_on: date | None


class IssueIn(BaseModel):
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    actor_id: str = Field(min_length=1, max_length=64)


class IssueOut(BaseModel):
    file_id: uuid.UUID
    sha256: str
    size_bytes: int


class VerifiedDocument(BaseModel):
    symbol: str
    issued_on: date
    type_name: str
    issuer_name: str
    parent_name: str | None
    # chỉ có khi văn bản được đánh dấu công khai lúc phát hành
    summary: str | None
    sha256: str
    verify_code: str
    status: Literal["issued", "archived"]


class VerifyOut(BaseModel):
    result: Literal["valid", "not_found"]
    document: VerifiedDocument | None = None


VERIFY_CODE_RE = re.compile(r"[^A-Z2-7]")
NO_STORE = {"Cache-Control": "no-store"}


class SearchOut(BaseModel):
    hits: list[SearchHit]
    # offset để lấy trang sau; None khi đã hết. Không có tổng số kết quả — xem search.py.
    next_offset: int | None


class FileTooLarge(Exception):
    pass


class _Digest:
    """SHA-256 và kích thước, tính trong cùng lượt đọc gửi sang ClamAV."""

    def __init__(self) -> None:
        self._h = hashlib.sha256()
        self.size = 0

    def update(self, chunk: bytes) -> None:
        self._h.update(chunk)
        self.size += len(chunk)

    def hexdigest(self) -> str:
        return self._h.hexdigest()


async def _read_chunks(upload: UploadFile, digest: _Digest, limit: int) -> AsyncIterator[bytes]:
    while chunk := await upload.read(CHUNK_SIZE):
        digest.update(chunk)
        if digest.size > limit:
            raise FileTooLarge
        yield chunk


def clean_filename(name: str | None) -> str:
    """Bỏ đường dẫn và ký tự điều khiển; chuẩn hóa NFC để tên tiếng Việt từ macOS (NFD) khớp."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFC", "".join(ch for ch in base if ch.isprintable())).strip()
    if base in {"", ".", ".."}:
        base = "tep-khong-ten"
    return base[:255]


def clean_mime(value: str | None) -> str:
    mime = (value or "").split(";", 1)[0].strip().lower()
    return mime if MIME_RE.match(mime) else "application/octet-stream"


def content_disposition(filename: str) -> str:
    """Luôn tải về (attachment), kèm tên ASCII cho trình duyệt cũ và tên UTF-8 đầy đủ (RFC 6266)."""
    folded = unicodedata.normalize("NFKD", filename.replace("đ", "d").replace("Đ", "D"))
    fallback = "".join(ch for ch in folded if ch.isascii() and ch.isprintable() and ch not in '"\\').strip()
    return f"attachment; filename=\"{fallback or 'tep'}\"; filename*=UTF-8''{quote(filename, safe='')}"


# Tệp người dùng tải lên có thể là HTML hay SVG chứa script: không bao giờ để trình duyệt hiển thị nó
# như một trang của Mộc. Giao diện xem PDF bằng PDF.js (đọc qua fetch), không cần hiển thị inline.
DOWNLOAD_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}


def _error(status: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def log_event(event: str, request: Request, **fields: object) -> None:
    record = {"event": event, "request_id": request.state.request_id, **fields}
    log.info(json.dumps(record, ensure_ascii=False, default=str))


UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            }
        },
    }
}


def create_app(
    settings: Settings | None = None,
    *,
    scanner: ClamAVClient | None = None,
    store: ObjectStore | None = None,
    verifier: TokenVerifier | None = None,
    hasura: HasuraClient | None = None,
    meili: MeiliClient | None = None,
    anchor_store: AnchorStore | None = None,
) -> FastAPI:
    _setup_logging()
    settings = settings or Settings.from_env()
    scanner = scanner or ClamAVClient(settings.clamav_host, settings.clamav_port, settings.clamav_timeout_s)
    store = store or ObjectStore(
        settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region, settings.bucket
    )
    verifier = verifier or TokenVerifier(settings.oidc_issuer, settings.oidc_jwks_url, settings.oidc_audience)
    hasura = hasura or HasuraClient(settings.hasura_url, settings.hasura_admin_secret, timeout_s=settings.hasura_timeout_s)
    meili = meili or MeiliClient(settings.meili_url, settings.meili_api_key, settings.search_index)
    indexer = Indexer(hasura, meili, interval_s=settings.search_sync_interval_s or 5.0)
    anchorer = Anchorer(
        hasura,
        anchor_store or AnchorStore(
            s3_client(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
            settings.cold_bucket,
            settings.anchor_retention_days,
        ),
        interval_s=settings.anchor_interval_s,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            await asyncio.to_thread(store.ensure_bucket)
        except StorageError as exc:
            # Không dừng dịch vụ: /readyz báo chưa sẵn sàng cho tới khi kho đối tượng lên.
            log.warning(json.dumps({"event": "storage.bucket_unready", "error": str(exc)}, ensure_ascii=False))
        sync = asyncio.create_task(indexer.run()) if settings.search_sync_interval_s > 0 else None
        anchor = asyncio.create_task(anchorer.run()) if settings.anchor_interval_s > 0 else None
        yield
        for task in (sync, anchor):
            if task is not None:
                task.cancel()
        await meili.aclose()
        await hasura.aclose()

    app = FastAPI(
        title="Mộc — svc-files",
        version=__version__,
        description="Tải tệp lên qua trạm kiểm dịch ClamAV, tải xuống theo quyền, tìm văn bản. Gọi qua cổng APISIX "
                    "với token Bearer do Keycloak cấp (docs/api/README.md).",
        lifespan=lifespan,
    )
    app.state.indexer = indexer
    app.state.anchorer = anchorer
    app.state.meili = meili
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # APISIX gắn X-Request-Id; gọi thẳng (khi phát triển) thì tự sinh.
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    # Hàm thường (không async): FastAPI chạy trong threadpool, lần tải JWKS đầu không chặn event loop.
    def current_principal(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> Principal:
        if creds is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "missing_token", "message": "Thiếu token đăng nhập"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            return verifier.verify(creds.credentials)
        except AuthError as exc:
            headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
            raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}, headers) from exc

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        clamd_ok, store_ok, hasura_ok, search_ok = await asyncio.gather(
            scanner.ping(), asyncio.to_thread(store.ping), hasura.ping(), meili.ping()
        )
        ready = clamd_ok and store_ok and hasura_ok
        # Tìm kiếm hỏng không chặn tải lên / tải xuống: báo "degraded" nhưng vẫn sẵn sàng nhận yêu cầu.
        status = "not_ready" if not ready else "ready" if search_ok else "degraded"
        return JSONResponse(
            {"status": status, "clamav": clamd_ok, "storage": store_ok, "hasura": hasura_ok, "search": search_ok},
            status_code=200 if ready else 503,
        )

    async def discard(request: Request, key: str) -> None:
        """Gỡ đối tượng vừa ghi khi không thêm được dòng CSDL — không để tệp mồ côi trong kho."""
        try:
            await asyncio.to_thread(store.delete, key)
        except StorageError as exc:
            log_event("core.file.orphaned", request, object_key=key, error=str(exc))

    # Không khai tham số UploadFile: FastAPI sẽ đọc hết thân request TRƯỚC khi kiểm token.
    # Ở đây kiểm token và Content-Length trước, rồi mới đọc multipart.
    @app.post(
        "/api/files",
        status_code=201,
        response_model=FileOut,
        openapi_extra=UPLOAD_BODY,
        summary="Tải tệp lên: quét ClamAV, sạch mới lưu",
        responses={
            401: {"description": "Thiếu hoặc sai token"},
            413: {"description": "Tệp vượt giới hạn MOC_FILES_MAX_MB"},
            422: {"description": "Tệp chứa mã độc — đã chặn, không lưu, ghi vào sổ kiểm toán"},
            503: {"description": "ClamAV, kho đối tượng hoặc CSDL không sẵn sàng — không lưu"},
        },
    )
    async def upload_file(
        request: Request,
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> FileOut:
        limit = settings.max_upload_bytes
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > limit + MULTIPART_OVERHEAD:
            raise _error(413, "too_large", f"Tệp vượt giới hạn {limit // (1024 * 1024)} MB")

        form = await request.form(max_files=1, max_fields=1)
        try:
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise _error(400, "missing_file", "Thiếu trường 'file' trong form multipart")

            filename = clean_filename(upload.filename)
            mime = clean_mime(upload.content_type)
            digest = _Digest()
            try:
                result = await scanner.scan(_read_chunks(upload, digest, limit))
            except FileTooLarge:
                raise _error(413, "too_large", f"Tệp vượt giới hạn {limit // (1024 * 1024)} MB") from None
            except ScanError as exc:
                log_event("core.file.scan_failed", request, error=str(exc))
                raise _error(503, "scanner_unavailable", "Trạm quét mã độc chưa sẵn sàng, tệp chưa được lưu") from exc
            scanned_at = datetime.now(UTC)

            if digest.size == 0:
                raise _error(400, "empty_file", "Tệp rỗng")
            if not result.clean:
                details = {
                    "filename": filename,
                    "size_bytes": digest.size,
                    "sha256": digest.hexdigest(),
                    "signature": result.signature,
                }
                log_event("core.file.rejected", request, tenant_id=principal.tenant_id,
                          actor_id=principal.user_id, **details)
                try:
                    await hasura.log_event(
                        tenant_id=principal.tenant_id,
                        actor_id=principal.user_id,
                        request_id=request.state.request_id,
                        action="file.rejected",
                        entity="core.files",
                        entity_id=digest.hexdigest(),
                        details=details,
                    )
                except HasuraError as exc:
                    # Tệp vẫn bị chặn; chỉ thiếu dòng trong sổ — nhật ký JSON ở trên vẫn còn.
                    log_event("core.file.audit_failed", request, error=str(exc))
                raise _error(422, "infected", "Tệp chứa mã độc nên đã bị chặn", signature=result.signature)

            file_id = uuid.uuid4()
            key = object_key(principal.tenant_id, file_id, scanned_at)
            await upload.seek(0)
            try:
                await asyncio.to_thread(
                    store.put, key, upload.file, size=digest.size, content_type=mime, sha256_hex=digest.hexdigest()
                )
            except StorageError as exc:
                log_event("core.file.store_failed", request, object_key=key, error=str(exc))
                raise _error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng, tệp chưa được lưu") from exc
        finally:
            await form.close()

        try:
            await hasura.insert_file(
                tenant_id=principal.tenant_id,
                actor_id=principal.user_id,
                request_id=request.state.request_id,
                file_id=file_id,
                object_key=key,
                filename=filename,
                mime_type=mime,
                size_bytes=digest.size,
                sha256_hex=digest.hexdigest(),
                scanned_at=scanned_at,
            )
        except HasuraError as exc:
            log_event("core.file.record_failed", request, object_key=key, code=exc.code, error=str(exc))
            await discard(request, key)
            if exc.code == "constraint-violation":
                # Thường gặp nhất: tenant_id trong token chưa có trong core.tenants.
                raise _error(403, "unknown_tenant", "Đơn vị của tài khoản chưa được đăng ký trong hệ thống") from exc
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng, tệp chưa được lưu") from exc

        log_event(
            "core.file.stored",
            request,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            file_id=file_id,
            object_key=key,
            size_bytes=digest.size,
        )
        return FileOut(
            id=file_id,
            filename=filename,
            mime_type=mime,
            size_bytes=digest.size,
            sha256=digest.hexdigest(),
            scanned_at=scanned_at,
        )

    @app.get(
        "/api/files/{file_id}",
        response_class=StreamingResponse,
        summary="Tải tệp xuống, nếu người gọi được xem tệp",
        responses={
            200: {"content": {"application/octet-stream": {}}, "description": "Nội dung tệp, luôn ở dạng tải về"},
            401: {"description": "Thiếu hoặc sai token"},
            404: {"description": "Không có tệp, hoặc người gọi không được xem — hai trường hợp trả như nhau"},
            503: {"description": "CSDL hoặc kho đối tượng không sẵn sàng"},
        },
    )
    async def download_file(
        file_id: uuid.UUID,
        request: Request,
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> StreamingResponse:
        rid = request.state.request_id
        try:
            meta = await hasura.visible_file(principal.token, file_id)
            key = None
            if meta is not None:
                key = await hasura.file_location(
                    tenant_id=principal.tenant_id, actor_id=principal.user_id, request_id=rid, file_id=file_id
                )
        except HasuraAuthError as exc:
            raise HTTPException(
                401, {"code": "invalid_token", "message": "Token không hợp lệ hoặc đã hết hạn"},
                {"WWW-Authenticate": "Bearer"},
            ) from exc
        except HasuraError as exc:
            log_event("core.file.lookup_failed", request, file_id=file_id, code=exc.code, error=str(exc))
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        if meta is None or key is None:
            raise _error(404, "not_found", "Không có tệp này, hoặc bạn không có quyền xem")

        try:
            chunks: Iterator[bytes] = await asyncio.to_thread(store.read_stream, key, CHUNK_SIZE)
        except StorageError as exc:
            log_event("core.file.read_failed", request, file_id=file_id, object_key=key, error=str(exc))
            raise _error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc

        log_event("core.file.downloaded", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  file_id=file_id)
        return StreamingResponse(
            chunks,
            media_type=meta.mime_type,
            headers={
                **DOWNLOAD_HEADERS,
                "Content-Disposition": content_disposition(meta.filename),
                "Content-Length": str(meta.size_bytes),
                "ETag": f'"{meta.sha256}"',
            },
        )

    @app.get(
        "/api/search",
        response_model=SearchOut,
        summary="Tìm văn bản theo số ký hiệu, trích yếu, cơ quan ban hành",
        responses={
            401: {"description": "Thiếu hoặc sai token"},
            503: {"description": "Meilisearch hoặc CSDL không sẵn sàng"},
        },
    )
    async def search(
        request: Request,
        principal: Annotated[Principal, Depends(current_principal)],
        q: Annotated[str, Query(min_length=1, max_length=200, description="Gõ có dấu hay không dấu đều được")],
        direction: Literal["in", "out"] | None = None,
        status: Status | None = None,
        type_code: Annotated[str | None, Query(pattern=r'^[^\s/"\\-]{1,10}$')] = None,
        urgency: Urgency | None = None,
        year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    ) -> SearchOut:
        if not q.strip():
            raise _error(400, "empty_query", "Nhập từ cần tìm")
        query = SearchQuery(q=q.strip(), direction=direction, status=status, type_code=type_code,
                            urgency=urgency, year=year)
        try:
            hits, next_offset = await search_documents(
                meili, hasura, token=principal.token, tenant_id=principal.tenant_id, query=query,
                limit=limit, offset=offset,
            )
        except HasuraAuthError as exc:
            raise HTTPException(
                401, {"code": "invalid_token", "message": "Token không hợp lệ hoặc đã hết hạn"},
                {"WWW-Authenticate": "Bearer"},
            ) from exc
        except HasuraError as exc:
            log_event("core.search.failed", request, code=exc.code, error=str(exc))
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        except SearchError as exc:
            log_event("core.search.failed", request, error=str(exc))
            raise _error(503, "search_unavailable", "Dịch vụ tìm kiếm chưa sẵn sàng") from exc
        # Không ghi nội dung câu tìm vào nhật ký: có thể chứa thông tin văn bản hạn chế.
        log_event("core.search", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  q_length=len(q), hits=len(hits))
        return SearchOut(hits=[SearchHit.model_validate(h) for h in hits], next_offset=next_offset)

    # --- văn bản đi -----------------------------------------------------------------------------------

    def service_caller(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> str:
        if creds is None:
            raise HTTPException(401, {"code": "missing_token", "message": "Thiếu token"}, {"WWW-Authenticate": "Bearer"})
        try:
            return verifier.verify_service(creds.credentials, settings.service_clients)
        except AuthError as exc:
            headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
            raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}, headers) from exc

    async def _scan_bytes(data: bytes) -> bool:
        async def chunks() -> AsyncIterator[bytes]:
            for i in range(0, len(data), CHUNK_SIZE):
                yield data[i:i + CHUNK_SIZE]
        return (await scanner.scan(chunks())).clean

    # API nội bộ: APISIX không có route tới đây; chỉ client trong MOC_SERVICE_CLIENTS (svc-workflow) gọi được.
    @app.post("/internal/issue", status_code=201, response_model=IssueOut, include_in_schema=False)
    async def issue_document(
        body: IssueIn,
        request: Request,
        caller: Annotated[str, Depends(service_caller)],
    ) -> IssueOut:
        rid = request.state.request_id
        try:
            row = await hasura.letter(tenant_id=body.tenant_id, actor_id=body.actor_id, request_id=rid,
                                      document_id=body.document_id)
        except HasuraError as exc:
            log_event("office.document.render_failed", request, document_id=body.document_id, error=str(exc))
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        if row is None:
            raise _error(404, "not_found", "Không có văn bản đi này trong đơn vị")
        if row["status"] != "approved" or not row["symbol"] or not row["verify_code"]:
            raise _error(409, "not_numbered", "Văn bản chưa được duyệt và cấp số")

        pdf = await asyncio.to_thread(render_pdf, letter_from(row, verify_base=f"{settings.public_url}/xac-thuc"))
        digest = hashlib.sha256(pdf).hexdigest()
        # Tệp do hệ thống dựng vẫn qua trạm kiểm dịch như mọi tệp: core.files chỉ có tệp đã quét
        try:
            clean = await _scan_bytes(pdf)
        except ScanError as exc:
            raise _error(503, "scanner_unavailable", "Trạm quét mã độc chưa sẵn sàng") from exc
        scanned_at = datetime.now(UTC)
        if not clean:
            log_event("office.document.render_rejected", request, document_id=body.document_id)
            raise _error(500, "render_rejected", "Bản PDF dựng ra bị trạm quét chặn")

        file_id = uuid.uuid4()
        key = object_key(body.tenant_id, file_id, scanned_at)
        try:
            await asyncio.to_thread(store.put, key, io.BytesIO(pdf), size=len(pdf), content_type="application/pdf",
                                    sha256_hex=digest)
        except StorageError as exc:
            raise _error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc
        try:
            await hasura.insert_file(
                tenant_id=body.tenant_id, actor_id=body.actor_id, request_id=rid, file_id=file_id, object_key=key,
                filename=row["symbol"].replace("/", "-") + ".pdf", mime_type="application/pdf",
                size_bytes=len(pdf), sha256_hex=digest, scanned_at=scanned_at,
            )
        except HasuraError as exc:
            await discard(request, key)
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng, chưa lưu bản phát hành") from exc
        log_event("office.document.rendered", request, tenant_id=body.tenant_id, actor_id=body.actor_id,
                  document_id=body.document_id, file_id=file_id, size_bytes=len(pdf), caller=caller)
        return IssueOut(file_id=file_id, sha256=digest, size_bytes=len(pdf))

    @app.get(
        "/api/documents/{document_id}/preview",
        response_class=Response,
        summary="Xem trước văn bản đi dưới dạng PDF đúng thể thức, chưa có số và mã xác thực",
        responses={
            200: {"content": {"application/pdf": {}}, "description": "Bản PDF in chữ DỰ THẢO"},
            401: {"description": "Thiếu hoặc sai token"},
            404: {"description": "Không có văn bản đi, hoặc người gọi không được đọc — hai trường hợp trả như nhau"},
            409: {"description": "Văn bản đã phát hành: tải bản phát hành thay vì xem trước"},
            503: {"description": "CSDL không sẵn sàng"},
        },
    )
    async def preview_document(
        document_id: uuid.UUID,
        request: Request,
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> Response:
        try:
            row = await hasura.visible_letter(principal.token, principal.tenant_id, document_id)
        except HasuraAuthError as exc:
            raise HTTPException(
                401, {"code": "invalid_token", "message": "Token không hợp lệ hoặc đã hết hạn"},
                {"WWW-Authenticate": "Bearer"},
            ) from exc
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        if row is None:
            raise _error(404, "not_found", "Không có văn bản này, hoặc bạn không có quyền xem")
        if row["status"] in ("issued", "archived"):
            raise _error(409, "issued", "Văn bản đã phát hành, hãy tải bản phát hành")
        pdf = await asyncio.to_thread(render_pdf, letter_from(row, draft=True))
        log_event("office.document.previewed", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  document_id=document_id)
        return Response(pdf, media_type="application/pdf", headers={
            **DOWNLOAD_HEADERS, **NO_STORE,
            "Content-Disposition": content_disposition(f"du-thao-{document_id}.pdf"),
        })

    # --- cổng xác thực (không cần đăng nhập; APISIX giới hạn tốc độ theo IP) ------------------------------

    async def _verify(request: Request, method: str, **lookup: str) -> JSONResponse:
        try:
            row = await hasura.verify(**lookup)
        except HasuraError as exc:
            log_event("core.verify.failed", request, error=str(exc))
            raise _error(503, "database_unavailable", "Chưa tra cứu được, thử lại sau") from exc
        log_event("core.verify", request, method=method, result="valid" if row else "not_found")
        if row is None:
            out = VerifyOut(result="not_found")
        else:
            out = VerifyOut(result="valid", document=VerifiedDocument(
                symbol=row["symbol"], issued_on=row["issued_on"], type_name=row["type_name"],
                issuer_name=row["issuer_name"], parent_name=row["parent_name"], summary=row["summary"],
                sha256=row["content_sha256"], verify_code=row["verify_code"], status=row["status"],
            ))
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

    verify_responses = {
        200: {"model": VerifyOut, "description": "valid: văn bản đã phát hành; not_found: không có văn bản nào khớp"},
        429: {"description": "Vượt giới hạn tra cứu theo địa chỉ IP (APISIX)"},
        503: {"description": "CSDL không sẵn sàng"},
    }

    @app.get("/api/verify/{code}", response_model=VerifyOut, responses=verify_responses,
             summary="Tra văn bản đã phát hành theo mã tra cứu in cạnh mã QR (không cần đăng nhập)")
    async def verify_by_code(code: Annotated[str, Path(max_length=40)], request: Request) -> JSONResponse:
        # nhận cả dạng có dấu gạch, khoảng trắng, chữ thường: ABCDE-23456, abcde 23456
        normalized = VERIFY_CODE_RE.sub("", code.upper())
        if len(normalized) != 10:
            log_event("core.verify", request, method="code", result="malformed")
            return JSONResponse(VerifyOut(result="not_found").model_dump(mode="json"), headers=NO_STORE)
        return await _verify(request, "code", code=normalized)

    @app.get("/api/verify", response_model=VerifyOut, responses=verify_responses,
             summary="Tra văn bản đã phát hành theo SHA-256 của tệp PDF (trình duyệt tự tính, không tải tệp lên)")
    async def verify_by_hash(
        request: Request,
        sha256: Annotated[str, Query(pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256 của tệp, 64 ký tự hex")],
    ) -> JSONResponse:
        return await _verify(request, "sha256", sha256_hex=sha256.lower())

    return app
