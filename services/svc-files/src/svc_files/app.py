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

"""API HTTP của svc-files.

Tải lên (F1.5, F1.6): kiểm token → quét ClamAV → sạch mới ghi SeaweedFS → thêm dòng core.files qua
Hasura. ClamAV không trả lời thì từ chối (503), không bao giờ lưu tệp chưa quét; tệp nhiễm được ghi vào
sổ kiểm toán. Tải xuống: hỏi Hasura bằng chính token người dùng xem họ có được xem tệp không, rồi mới
đọc từ SeaweedFS. Tìm kiếm (F1.7): Meilisearch xếp hạng, Hasura lọc theo quyền — chi tiết ở search.py.

Văn bản đi (F2.4): svc-workflow gọi /internal/issue bằng token tài khoản dịch vụ khi văn thư phát hành —
dựng PDF có số, mã QR từ dữ liệu trong CSDL, ký số PAdES bằng khóa của đơn vị trong két (F4.5, chỉ minh họa —
signing.py; văn bản hạn chế không ký), quét, lưu như mọi tệp. Người được đọc dự thảo xem trước bản PDF
ở /api/documents/{id}/preview. Cổng xác thực (F2.13): /api/verify trả thông tin công khai của đúng một văn
bản đã phát hành theo mã tra cứu hoặc băm SHA-256, không cần đăng nhập; /api/verify/ca.pem, /api/verify/anchor-key.pem
trả chứng thư CA nội bộ và khóa công khai ký mốc neo sổ kiểm toán (anchors.py). Sổ đăng ký văn bản đến / đi (F2.8):
văn thư, lãnh đạo xem sổ một năm ở /api/registers/{in|out}/{năm} và in ra PDF để ký nhận, đóng sổ — registers.py.
Nộp lưu (F3.8): vòng nền chuyển hồ sơ đã đóng sang bucket lạnh — archive.py; lãnh đạo phòng nộp lưu ngay bằng
POST /api/case-files/{id}/archive; phòng đọc GET cùng đường đọc lại gói (DuckDB đọc Parquet), kiểm băm với CSDL, và
…/archive/files/{file_id} cho xem một tệp: so băm với manifest, đóng dấu người xem như F3.7, ghi sổ rồi mới trả.
Liên thông trong hệ thống (F3.12):
svc-workflow gọi /internal/dispatch-file để chép bản phát hành sang kho của đơn vị nhận — dispatch.py. Đọc văn bản đến
(F4.1): văn thư gọi /api/files/{id}/read, tác tử đọc tệp vừa tải lên và gợi ý thông tin tiếp nhận — docread/. Hỏi đáp
trên kho văn bản (F4.2): /api/documents/ask trả câu trích nguyên văn có nguồn từ các văn bản người hỏi được xem, tùy
chọn câu trả lời do mô hình viết; vòng nền giữ chỉ mục đoạn `chunks` — assist/. Trạng thái hệ thống: /api/status gom
tình trạng các thành phần cho trang công khai /trang-thai, đã làm sạch và lưu đệm — status.py. Nạp lô văn bản đến:
văn thư gửi tệp NDJSON/CSV (kèm zip) ở /api/imports/incoming, vòng nền đưa từng dòng qua đúng đường tải lên lẻ
(ingest) và Action receiveIncoming thay mặt họ — imports/.

Chạy: ``uvicorn svc_files.app:create_app --factory``
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu của
# dependency khai báo bên trong create_app().
import asyncio
import dataclasses
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import time
import unicodedata
import uuid
from collections.abc import Iterator
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Annotated, BinaryIO, Literal, Protocol
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from . import __version__, pii
from .anchors import Anchorer, AnchorSigner, AnchorStore
from .archive import (Archived, ArchiveError, Archiver, ArchiveStateError, ColdStore, read_archived_file,
                      read_manifest, read_package)
from .assist import api as assist_api
from .assist import similar
from .assist.ai import AiClient, make_ai
from .assist.answer import Assistant
from .assist.index import ChunkIndexer
from .assist.meili import ChunkIndex
from .assist.retrieve import Retriever
from .auth import AuthError, Principal, TokenVerifier
from .clamav import ClamAVClient, ScanError
from .config import Settings
from .dispatch import DispatchError, copy_issued_file
from .docread import api as docread_api
from .docread.reader import Reader
from .docread.summarize import make_summarizer
from .hasura import HasuraAuthError, HasuraClient, HasuraError, Location, StoredFile
from .imports import api as imports_api
from .imports.runner import Importer, IncomingHandler
from .imports.spool import Spool
from .imports.store import ImportStore
from .openbao import with_secrets
from .registers import Register, build_register, render_register_pdf
from .render import letter_from, render_pdf
from .sealed import SealError, Vault, VaultError, run_check_pdf, run_watermark, seal, unseal
from .search import Cursor, Indexer, MeiliClient, SearchError, SearchQuery, search_documents
from .signing import DocumentSigner, SigningError, SigningOff, SigningUnavailable, preload as preload_signing
from .status import StatusBoard, default_board
from .storage import ObjectMissing, ObjectStore, StorageError, object_key, s3_client
from .texts import TextExtractor

CHUNK_SIZE = 64 * 1024
# Phần đầu và biên của multipart cộng thêm vào kích thước tệp
MULTIPART_OVERHEAD = 64 * 1024
# Văn bản hạn chế (F3.7): chờ lượt kiểm / đóng dấu PDF quá chừng này thì 503 busy
SEALING_QUEUE_S = 10.0
RETRY_AFTER = "10"
MIME_RE = re.compile(r"^[\w.+-]+/[\w.+-]+$")

log = logging.getLogger("svc_files")


def _setup_logging() -> None:
    """Mỗi dòng nhật ký là một đối tượng JSON trên stdout; uvicorn chỉ cấu hình logger của riêng nó.

    F4.4: dòng của dịch vụ, uvicorn.error, uvicorn.access đều qua bộ che PII; dòng truy cập bỏ chuỗi truy vấn
    (``/api/search?…``). Uvicorn dựng logger và handler của nó trước khi gọi factory, nên gắn được cả vào handler."""
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    # ngoài nhánh trên: logger đã có handler từ trước (fixture của test) vẫn phải được che
    pii.install_log_redaction(log)


class FileOut(BaseModel):
    # Không trả object_key: vị trí trong kho là chuyện nội bộ, tệp chỉ lấy qua GET /api/files/{id}.
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    scanned_at: datetime
    encrypted: bool = False     # tệp của văn bản hạn chế (F3.7): lưu mã hóa, xem có dấu tên người xem


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
    matched_content: bool = Field(
        False, description="Khớp trong nội dung (văn bản đi, chữ của tệp PDF đính kèm), không khớp số ký hiệu, "
                           "trích yếu, cơ quan ban hành")


class IssueIn(BaseModel):
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    actor_id: str = Field(min_length=1, max_length=64)


class DispatchFileIn(BaseModel):
    dispatch_id: uuid.UUID
    actor_id: str = Field(min_length=1, max_length=64)


class IssueOut(BaseModel):
    # cũng là kết quả của /internal/dispatch-file (bản sao liên thông, F3.12)
    file_id: uuid.UUID
    sha256: str
    size_bytes: int


class VerifiedSignature(BaseModel):
    """Chữ ký số của bản phát hành (F4.5) — PKI nội bộ của Signet, chỉ minh họa, không có giá trị pháp lý như chữ ký số
    công cộng. svc-files đã tự kiểm chữ ký lúc ký; kiểm lại tệp: python -m svc_files.signing verify."""

    level: Literal["PAdES-B-B"] = Field(description="Chuẩn chữ ký: PAdES mức B-B, không có dấu thời gian tin cậy")
    signer: str = Field(description="Người ký: CN chứng thư của đơn vị phát hành")
    ca: str = Field(description="CN của CA nội bộ cấp chứng thư")
    serial: str = Field(description="Số sê-ri chứng thư, hex thường")
    signed_at: datetime = Field(description="Giờ ký tự ghi trong chữ ký (không có dấu thời gian tin cậy)")
    illustrative: Literal[True] = Field(True, description="Luôn true: chữ ký chỉ để minh họa")


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
    signature: VerifiedSignature | None = Field(
        None, description="Chữ ký số của bản phát hành (F4.5, chỉ minh họa); null: văn bản phát hành khi ký số "
                          "chưa bật hoặc ký lỗi, hoặc văn bản hạn chế")


class VerifyOut(BaseModel):
    result: Literal["valid", "not_found"]
    document: VerifiedDocument | None = None


class StatusComponent(BaseModel):
    id: str = Field(description="Mã thành phần, vd cong-api, dang-nhap, csdl, quy-trinh, tro-ly-ai")
    layer: str = Field(description="Mã tầng trong `layers`")
    label: str = Field(description="Tên tiếng Việt, vd Đăng nhập một lần")
    software: str = Field(description="Phần mềm nguồn mở đảm nhận (không kèm phiên bản), vd Keycloak")
    status: Literal["ok", "degraded", "down", "off"] = Field(
        description="ok: hoạt động · degraded: chạy một phần · down: gián đoạn (không trả lời, quá hạn dò) · off: "
                    "tắt theo cấu hình (vd chưa bật mô hình ngôn ngữ)")


class StatusLayer(BaseModel):
    id: str
    label: str


class StatusAi(BaseModel):
    enabled: bool = Field(description="Mô hình viết câu trả lời của trợ lý đang sẵn sàng")
    model: str | None = Field(description="Tên mô hình khi bật, vd qwen3:1.7b; null khi tắt")
    semantic: bool = Field(description="Tìm theo nghĩa được (mô hình nhúng sẵn sàng)")


class StatusOut(BaseModel):
    """Trạng thái vận hành, công khai: chỉ chữ cố định và trạng thái, không tên máy, địa chỉ hay số liệu nghiệp vụ."""

    status: Literal["ok", "degraded", "down"] = Field(
        description="down: có thành phần thiết yếu gián đoạn · degraded: thành phần khác gián đoạn hoặc chạy một phần")
    checked_at: datetime = Field(description="Lúc dò; kết quả lưu đệm MOC_STATUS_CACHE_S giây (mặc định 10)")
    version: str = Field(description="Phiên bản Signet đang chạy (MOC_VERSION)")
    uptime_s: int = Field(description="Số giây svc-files đã chạy liên tục từ lần khởi động gần nhất")
    last_backup_at: datetime | None = Field(
        description="Lượt sao lưu gần nhất (`moc backup create`) mà CSDL biết; null: chưa có")
    ai: StatusAi
    layers: list[StatusLayer] = Field(description="Các tầng theo thứ tự hiện: người dùng → lõi → quy trình → dữ liệu "
                                                  "→ trí tuệ nhân tạo")
    components: list[StatusComponent]


VERIFY_CODE_RE = re.compile(r"[^A-Z2-7]")
NO_STORE = {"Cache-Control": "no-store"}
# Sổ đăng ký là việc của văn thư; lãnh đạo đơn vị xem để kiểm (NĐ 30/2020, Điều 16, 22)
REGISTER_ROLES = {"clerk", "director"}


class RegisterEntryOut(BaseModel):
    number: int = Field(description="Số đến (sổ đến) hoặc số văn bản đi (sổ đi)")
    document_id: uuid.UUID | None = Field(description="Mở văn bản trên giao diện; null khi dòng bị che")
    hidden: bool = Field(description="Văn bản hạn chế người gọi không được đọc: chỉ có số, ngày, số ký hiệu")
    cells: list[str] = Field(description="Giá trị từng cột, đúng thứ tự `columns`; ô Ký nhận để trống")


class RegisterOut(BaseModel):
    direction: Literal["in", "out"]
    year: int
    title: str
    org_name: str
    columns: list[str] = Field(description="Cột theo mẫu sổ đăng ký, NĐ 30/2020/NĐ-CP Phụ lục IV")
    entries: list[RegisterEntryOut]
    last_number: int = Field(description="Số cuối đã cấp trong năm")
    missing: list[int] = Field(description="Số đã cấp mà không có dòng — sổ phải liền số, bình thường rỗng")


class ArchivedDocumentOut(BaseModel):
    id: uuid.UUID
    direction: Literal["in", "out"]
    type_code: str
    symbol: str | None
    issuer_name: str | None
    issued_on: date | None
    summary: str
    register_number: int | None
    verify_code: str | None
    content_sha256: str | None


class ArchivedFileOut(BaseModel):
    file_id: uuid.UUID = Field(description="Mở trong phòng đọc: GET /api/case-files/{id}/archive/files/{file_id}")
    filename: str
    mime_type: str
    sha256: str
    bytes: int
    document_ids: list[uuid.UUID] = Field(description="Văn bản người gọi đọc được có gắn tệp này")
    viewable: bool = Field(description="Xem được trong phòng đọc (PDF, đóng dấu người xem); tệp khác chỉ hiện băm, cỡ")


class ArchiveOut(BaseModel):
    case_file_id: uuid.UUID
    code: str
    title: str
    closed_on: date | None
    archived_at: datetime
    archive_key: str = Field(description="Tiền tố của gói trong bucket lạnh (khóa ghi S3 Object Lock)")
    manifest_sha256: str = Field(description="Băm manifest.json đọc từ bucket lạnh — đã so khớp với CSDL")
    retain_until: datetime = Field(description="Hạn giữ khóa ghi của gói")
    documents: list[ArchivedDocumentOut] = Field(
        description="Văn bản người gọi đọc được (cùng quy tắc như trước khi nộp lưu), đọc từ bảng Parquet trong gói (DuckDB)")
    files: list[ArchivedFileOut] = Field(description="Tệp của các văn bản trên")
    hidden: int = Field(description="Số văn bản trong gói người gọi không được đọc — chỉ biết có, không biết là gì")


class ArchiveRunOut(BaseModel):
    """Kết quả nộp lưu theo yêu cầu: gói đã nằm trong bucket lạnh, đọc lại khớp băm, CSDL đã chuyển `archived`."""

    case_file_id: uuid.UUID
    code: str
    archive_key: str = Field(description="Tiền tố của gói trong bucket lạnh (khóa ghi S3 Object Lock)")
    archive_sha256: str = Field(description="Băm manifest của gói — cũng là case_files.archive_sha256")
    documents: int
    files: int
    bytes: int = Field(description="Tổng số byte tệp và bảng Parquet đã ghi vào gói")
    run_id: str = Field(description="Run OpenLineage của lượt nộp lưu (core.lineage_events, F3.9)")


class SearchOut(BaseModel):
    hits: list[SearchHit]
    # Không có tổng số kết quả, vị trí trang sau cũng mã hóa — xem search.Cursor.
    next_cursor: str | None = Field(description="Gửi lại ở tham số `cursor` để lấy trang sau; null khi đã hết")


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


class Readable(Protocol):
    """Tệp đọc được hai lượt (quét rồi ghi kho): UploadFile của Starlette, hoặc MemoryFile."""

    file: BinaryIO

    async def read(self, size: int = -1) -> bytes: ...
    async def seek(self, offset: int) -> None: ...


class MemoryFile:
    """Tệp trong bộ nhớ đọc như UploadFile — tệp lấy ra từ tệp nén của lô nạp đi đúng đường quét, ghi kho của tệp tải
    lên lẻ (ingest)."""

    def __init__(self, data: bytes) -> None:
        self.file: BinaryIO = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)

    async def seek(self, offset: int) -> None:
        self.file.seek(offset)


async def _read_chunks(upload: Readable, digest: _Digest, limit: int) -> AsyncIterator[bytes]:
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


def content_disposition(filename: str, *, inline: bool = False) -> str:
    """Tải về (attachment), kèm tên ASCII cho trình duyệt cũ và tên UTF-8 đầy đủ (RFC 6266). ``inline`` chỉ cho bản PDF
    đã đóng dấu người xem của phòng đọc (F3.8)."""
    folded = unicodedata.normalize("NFKD", filename.replace("đ", "d").replace("Đ", "D"))
    fallback = "".join(ch for ch in folded if ch.isascii() and ch.isprintable() and ch not in '"\\').strip()
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{fallback or 'tep'}\"; filename*=UTF-8''{quote(filename, safe='')}"


# Tệp người dùng tải lên có thể là HTML hay SVG chứa script: không bao giờ để trình duyệt hiển thị nó
# như một trang của Signet. Giao diện lấy tệp bằng fetch kèm token rồi lưu về máy, không cần hiển thị inline.
DOWNLOAD_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}


def _error(status: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def log_event(event: str, request: Request, *, level: int = logging.INFO, **fields: object) -> None:
    log_rid(event, request.state.request_id, level=level, **fields)


def log_rid(event: str, rid: str, *, level: int = logging.INFO, **fields: object) -> None:
    """Như log_event, cho việc không gắn với một yêu cầu HTTP (vòng nền của lô nạp: mã yêu cầu là `<lô>:<dòng>`)."""
    record = {"event": event, "request_id": rid, **fields}
    log.log(level, json.dumps(record, ensure_ascii=False, default=str))


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
    vault: Vault | None = None,
    reader: Reader | None = None,
    assistant: Assistant | None = None,
    chunk_indexer: ChunkIndexer | None = None,
    ai: AiClient | None = None,
    signer: DocumentSigner | None = None,
    status_board: StatusBoard | None = None,
    import_store: ImportStore | None = None,
    cold: ColdStore | None = None,
    archiver: Archiver | None = None,
) -> FastAPI:
    _setup_logging()
    settings = settings or Settings.from_env(with_secrets(os.environ))
    scanner = scanner or ClamAVClient(settings.clamav_host, settings.clamav_port, settings.clamav_timeout_s)
    store = store or ObjectStore(
        settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region, settings.bucket
    )
    verifier = verifier or TokenVerifier(settings.oidc_issuer, settings.oidc_jwks_url, settings.oidc_audience)
    hasura = hasura or HasuraClient(settings.hasura_url, settings.hasura_admin_secret, timeout_s=settings.hasura_timeout_s)
    meili = meili or MeiliClient(settings.meili_url, settings.meili_api_key, settings.search_index)
    cursors = Cursor(settings.hasura_admin_secret)   # khóa dẫn xuất (HKDF) từ một bí mật sẵn có của svc-files
    indexer = Indexer(hasura, meili, interval_s=settings.search_sync_interval_s or 5.0)
    extractor = TextExtractor(hasura, store, interval_s=settings.text_interval_s or 10.0,
                              max_bytes=settings.max_upload_bytes)
    anchorer = Anchorer(
        hasura,
        anchor_store or AnchorStore(
            s3_client(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
            settings.cold_bucket,
            settings.anchor_retention_days,
        ),
        interval_s=settings.anchor_interval_s,
    )
    cold = cold or ColdStore(
        s3_client(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
        settings.cold_bucket,
    )
    archiver = archiver or Archiver(hasura, store, cold, after_days=settings.archive_after_days,
                                    interval_s=settings.archive_interval_s, lineage_url=settings.openlineage_url)
    if vault is None and settings.vault_addr:
        vault = Vault(settings.vault_addr, role_id_file=settings.vault_role_id_file,
                      secret_id_file=settings.vault_secret_id_file, key=settings.transit_key)
        # Ký số bản phát hành (F4.5): khóa transit của đơn vị, CA nội bộ của két. Test tự tiêm bộ ký (két giả)
        signer = signer or DocumentSigner(vault)
    if not settings.sign_enabled:
        signer = None
    # Mốc neo sổ kiểm toán ký bằng khóa moc-anchor của két (anchors.py); không có két thì neo không chữ ký
    anchor_signer = AnchorSigner(vault, settings.public_url) if vault is not None else None
    anchorer.signer = anchor_signer
    reader = reader or Reader(settings, hasura, store, summarizer=make_summarizer(
        settings.ai_url, settings.ai_model, max_chars=settings.ai_max_chars))
    # Hỏi đáp trên kho văn bản (F4.2): chỉ mục đoạn riêng trên cùng Meilisearch, mô hình nhúng / sinh tùy chọn
    ai = ai or make_ai(settings)
    chunk_index = ChunkIndex(settings.meili_url, settings.meili_api_key, settings.ask_index)
    chunk_indexer = chunk_indexer or ChunkIndexer(chunk_index, hasura, ai, dims=settings.ai_embed_dims,
                                                  batch=settings.ai_embed_batch,
                                                  interval_s=settings.ask_sync_interval_s)
    assistant = assistant or Assistant(
        settings,
        # cùng một tên embedder với vòng nhúng nền (đặt theo ai.embed_model): véc-tơ câu hỏi khớp véc-tơ đoạn
        retriever=Retriever(chunk_index, hasura, embedder=chunk_indexer.embedder,
                            candidates=settings.ask_candidates, per_doc=settings.ask_per_doc,
                            min_score=settings.ask_min_score, min_score_semantic=settings.ask_min_score_semantic,
                            semantic_ratio=settings.ask_semantic_ratio),
        ai=ai, indexer=chunk_indexer, hasura=hasura)
    # Trạng thái hệ thống (công khai): dò bằng chính các client trên, thêm APISIX, Keycloak, svc-workflow qua HTTP
    status_board = status_board or default_board(settings, scanner=scanner, store=store, hasura=hasura, meili=meili,
                                                 vault=vault, ai=ai)
    # Nạp lô văn bản đến: hàng đợi bền trong CSDL, zip giữ tạm trên tmpfs; handler nối vào ingest() ở dưới
    import_store = import_store or ImportStore(hasura)
    spool = Spool(settings.import_spool_dir, settings.import_spool_bytes)

    async def _probe_signer() -> None:
        try:
            if await signer.ready():
                await asyncio.to_thread(preload_signing)    # nạp pyHanko ngoài event loop
        except SigningUnavailable as exc:
            log.warning(json.dumps({"event": "office.signing.unavailable", "error": str(exc)}, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 — task nền: lỗi lạ (nạp pyHanko…) phải ra nhật ký, không chết lặng
            log.error(json.dumps({"event": "office.signing.unavailable", "error": f"{type(exc).__name__}: {exc}"},
                                 ensure_ascii=False))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        for warning in settings.warnings():     # cấu hình chạy được nhưng dễ chậm (vd ba mô hình tranh hai chỗ)
            log.warning(json.dumps({"event": "config.warning", "message": warning}, ensure_ascii=False))
        try:
            await asyncio.to_thread(store.ensure_bucket)
        except StorageError as exc:
            # Không dừng dịch vụ: /readyz báo chưa sẵn sàng cho tới khi kho đối tượng lên.
            log.warning(json.dumps({"event": "storage.bucket_unready", "error": str(exc)}, ensure_ascii=False))
        sync = asyncio.create_task(indexer.run()) if settings.search_sync_interval_s > 0 else None
        anchor = asyncio.create_task(anchorer.run()) if settings.anchor_interval_s > 0 else None
        texts = asyncio.create_task(extractor.run()) if settings.text_interval_s > 0 else None
        archive = asyncio.create_task(archiver.run()) if settings.archive_interval_s > 0 else None
        probe = asyncio.create_task(reader.summarizer.run())  # dò Ollama mỗi 60 giây (F4.1); không có mô hình: về ngay
        # F4.2: vòng đồng bộ + nhúng chỉ mục đoạn, vòng dò mô hình của trợ lý — chỉ khi bật trợ lý
        chunks = (asyncio.create_task(chunk_indexer.run())
                  if settings.ask_enabled and settings.ask_sync_interval_s > 0 else None)
        models = asyncio.create_task(ai.run()) if settings.ask_enabled else None
        # F4.5: dò két một lần để nhật ký khởi động có dòng office.signing.ready / disabled; lỗi để lần phát hành dò lại
        signing = asyncio.create_task(_probe_signer()) if signer is not None else None
        # nạp lô: dọn spool rồi làm tiếp các lô dở (trạng thái nằm trong CSDL); 0 thì tắt cả API tạo lô
        imports = asyncio.create_task(importer.run()) if settings.import_interval_s > 0 else None
        yield
        for task in (sync, anchor, texts, archive, probe, chunks, models, signing, imports):
            if task is not None:
                task.cancel()
        await reader.summarizer.aclose()
        await status_board.aclose()
        await ai.aclose()
        await chunk_index.aclose()
        await meili.aclose()
        await hasura.aclose()
        if vault is not None:
            await vault.aclose()

    app = FastAPI(
        title="Signet — svc-files",
        version=__version__,
        description="Tải tệp lên qua trạm kiểm dịch ClamAV, tải xuống theo quyền, tìm văn bản. Gọi qua cổng APISIX "
                    "với token Bearer do Keycloak cấp (docs/api/README.md).",
        lifespan=lifespan,
    )
    app.state.indexer = indexer
    app.state.extractor = extractor
    app.state.anchorer = anchorer
    app.state.meili = meili
    app.state.reader = reader
    app.state.assistant = assistant
    app.state.chunk_indexer = chunk_indexer
    app.state.ai = ai
    app.state.signer = signer
    app.state.status_board = status_board
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

    # Đọc văn bản đến (F4.1): POST /api/files/{file_id}/read — docread/api.py
    docread_api.install(app, reader, current_principal)
    # Hỏi đáp trên kho văn bản (F4.2): POST /api/documents/ask — assist/api.py
    assist_api.install(app, assistant, current_principal)

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
        # ai: mô hình trích yếu (F4.1, profile ai) — tùy chọn, không ảnh hưởng ready
        # assist (F4.2): chỉ mục đoạn đã đồng bộ xong một lượt; tìm theo nghĩa được (mô hình nhúng sẵn sàng, đúng số
        # chiều, embedder đã áp trong Meilisearch); mô hình viết câu trả lời sẵn sàng; số đoạn chờ nhúng / bị đánh dấu
        # hỏng (null: không nhúng hoặc chưa đếm) — không ảnh hưởng ready (không có chúng vẫn tìm theo từ khóa)
        return JSONResponse(
            {"status": status, "clamav": clamd_ok, "storage": store_ok, "hasura": hasura_ok, "search": search_ok,
             "ai": reader.summarizer.available,
             "assist": {"index": bool(chunk_indexer.ready),
                        "semantic": ai.embed_available and bool(chunk_indexer.embedder_ready),
                        "model": ai.chat_available, "embed_pending": chunk_indexer.embed_pending,
                        "embed_failed": chunk_indexer.embed_failed}},
            status_code=200 if ready else 503,
        )

    async def seal_bytes(rid: str, plain: bytes, tenant_id: uuid.UUID, file_id: uuid.UUID) -> tuple[bytes, str]:
        """Bản mã và khóa đã bọc (F3.7). Khóa rõ chỉ sống trong hàm này; két không sẵn sàng thì không lưu gì."""
        if vault is None:
            raise _error(503, "vault_unavailable", "Chưa cấu hình két khóa, chưa nhận được tệp của văn bản hạn chế")
        try:
            dek, wrapped = await vault.datakey()
        except VaultError as exc:
            log_rid("core.file.vault_failed", rid, file_id=file_id, error=str(exc))
            raise _error(503, "vault_unavailable", "Két khóa chưa sẵn sàng, tệp chưa được lưu") from exc
        return await asyncio.to_thread(seal, plain, dek, tenant_id, file_id), wrapped

    # Kiểm PDF lúc tải lên và giải mã + đóng dấu lúc xem văn bản hạn chế tốn CPU và bộ nhớ (mỗi lượt một tiến trình con
    # tới MEMORY_MB): chung tối đa hai lượt cùng lúc. Chờ lượt có hạn — đầy thì 503 busy, không treo yêu cầu
    sealing = asyncio.Semaphore(2)

    @asynccontextmanager
    async def sealing_slot() -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(sealing.acquire(), SEALING_QUEUE_S)
        except TimeoutError:
            raise HTTPException(
                503, {"code": "busy", "message": "Đang kiểm, đóng dấu tệp văn bản hạn chế khác, thử lại sau ít giây"},
                {"Retry-After": RETRY_AFTER},
            ) from None
        try:
            yield
        finally:
            sealing.release()

    async def discard(rid: str, key: str) -> None:
        """Gỡ đối tượng vừa ghi khi không thêm được dòng CSDL — không để tệp mồ côi trong kho."""
        try:
            await asyncio.to_thread(store.delete, key)
        except StorageError as exc:
            log_rid("core.file.orphaned", rid, object_key=key, error=str(exc))

    async def quarantine(rid: str, tenant_id: uuid.UUID, actor_id: str, upload: Readable, *, filename: str,
                         limit: int) -> _Digest:
        """Trạm kiểm dịch (F1.6): quét luồng tệp bằng ClamAV, tính SHA-256 và cỡ trong cùng lượt đọc. Nhiễm, hoặc có
        mật khẩu, nén quá sâu nên không quét được bên trong: ghi file.rejected vào sổ kiểm toán rồi từ chối (422).
        ClamAV không trả lời: 503. Quá `limit`: 413. Rỗng: 400. Mọi tệp vào đều qua đây — tải lên lẻ, tệp dữ liệu và
        tệp đính kèm của lô nạp (imports/) — nên không có lối nào vào kho mà chưa quét."""
        digest = _Digest()
        try:
            result = await scanner.scan(_read_chunks(upload, digest, limit))
        except FileTooLarge:
            raise _error(413, "too_large", f"Tệp vượt giới hạn {limit // (1024 * 1024)} MB") from None
        except ScanError as exc:
            log_rid("core.file.scan_failed", rid, error=str(exc))
            raise _error(503, "scanner_unavailable", "Trạm quét mã độc chưa sẵn sàng, tệp chưa được lưu") from exc

        if digest.size == 0:
            raise _error(400, "empty_file", "Tệp rỗng")
        if not result.clean:
            details = {
                "filename": filename,
                "size_bytes": digest.size,
                "sha256": digest.hexdigest(),
                "signature": result.signature,
            }
            log_rid("core.file.rejected", rid, tenant_id=tenant_id, actor_id=actor_id, **details)
            try:
                await hasura.log_event(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    request_id=rid,
                    action="file.rejected",
                    entity="core.files",
                    entity_id=digest.hexdigest(),
                    details=details,
                )
            except HasuraError as exc:
                # Tệp vẫn bị chặn; chỉ thiếu dòng trong sổ — nhật ký JSON ở trên vẫn còn.
                log_rid("core.file.audit_failed", rid, error=str(exc))
            if result.unscannable:
                raise _error(422, "unscannable", "Tệp có mật khẩu hoặc nén quá nhiều lớp nên trạm quét mã độc không "
                             "kiểm được bên trong — đã chặn. Bỏ mật khẩu hoặc giải nén rồi tải lên lại",
                             signature=result.signature)
            raise _error(422, "infected", "Tệp chứa mã độc nên đã bị chặn", signature=result.signature)
        return digest

    async def ingest(rid: str, tenant_id: uuid.UUID, actor_id: str, upload: Readable, *, filename: str, mime: str,
                     restricted: bool) -> FileOut:
        """Một tệp vào kho: quét (quarantine) → (văn bản hạn chế: kiểm PDF, mã hóa) → ghi SeaweedFS → thêm dòng
        core.files của người tải. Lỗi trả HTTPException như POST /api/files; lô nạp đọc cùng mã lỗi cho từng dòng."""
        digest = await quarantine(rid, tenant_id, actor_id, upload, filename=filename, limit=settings.max_upload_bytes)
        scanned_at = datetime.now(UTC)
        file_id = uuid.uuid4()
        key = object_key(tenant_id, file_id, scanned_at)
        await upload.seek(0)
        wrapped: str | None = None
        body: BinaryIO = upload.file
        stored_size, stored_sha, stored_mime = digest.size, digest.hexdigest(), mime
        if restricted:
            # Văn bản hạn chế (F3.7): bản rõ đọc vào bộ nhớ (Starlette đệm phần lớn tệp ở /tmp — tmpfs trong
            # compose), kiểm đóng dấu được, mã hóa; kho chỉ nhận bản mã
            if mime != "application/pdf":
                raise _error(415, "restricted_pdf_only", "Văn bản hạn chế chỉ nhận tệp PDF (để đóng dấu người xem)")
            plain = await upload.read()
            pages = settings.restricted_max_pages
            try:
                async with sealing_slot():      # PDF người dùng tải lên: chỉ mở trong tiến trình con có giới hạn
                    await run_check_pdf(plain, max_pages=pages)
            except SealError as exc:
                raise _error(415, "restricted_pdf_only", "Văn bản hạn chế chỉ nhận tệp PDF đọc được, không đặt "
                             f"mật khẩu, tối đa {pages} trang: {exc}", reason=exc.reason) from exc
            blob, wrapped = await seal_bytes(rid, plain, tenant_id, file_id)
            del plain
            body, stored_size = io.BytesIO(blob), len(blob)
            stored_sha, stored_mime = hashlib.sha256(blob).hexdigest(), "application/octet-stream"
        try:
            await asyncio.to_thread(
                store.put, key, body, size=stored_size, content_type=stored_mime, sha256_hex=stored_sha
            )
        except StorageError as exc:
            log_rid("core.file.store_failed", rid, object_key=key, error=str(exc))
            raise _error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng, tệp chưa được lưu") from exc

        try:
            await hasura.insert_file(
                tenant_id=tenant_id,
                actor_id=actor_id,
                request_id=rid,
                file_id=file_id,
                object_key=key,
                filename=filename,
                mime_type=mime,
                size_bytes=digest.size,
                sha256_hex=digest.hexdigest(),
                scanned_at=scanned_at,
                wrapped_dek=wrapped,
            )
        except HasuraError as exc:
            log_rid("core.file.record_failed", rid, object_key=key, code=exc.code, error=str(exc))
            await discard(rid, key)
            if exc.code == "constraint-violation":
                # Thường gặp nhất: tenant_id trong token chưa có trong core.tenants.
                raise _error(403, "unknown_tenant", "Đơn vị của tài khoản chưa được đăng ký trong hệ thống") from exc
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng, tệp chưa được lưu") from exc

        log_rid(
            "core.file.stored",
            rid,
            tenant_id=tenant_id,
            actor_id=actor_id,
            file_id=file_id,
            object_key=key,
            size_bytes=digest.size,
            encrypted=wrapped is not None,
        )
        return FileOut(
            id=file_id,
            filename=filename,
            mime_type=mime,
            size_bytes=digest.size,
            sha256=digest.hexdigest(),
            scanned_at=scanned_at,
            encrypted=wrapped is not None,
        )

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
            415: {"description": "restricted=true mà tệp không phải PDF đọc được, không khóa, tối đa "
                                 "MOC_RESTRICTED_MAX_PAGES trang, hoặc quá nặng để kiểm trong giới hạn thời gian, bộ nhớ "
                                 "(`reason`) (PDF phải nhập mật khẩu mới mở thì bị chặn trước ở bước quét: 422 "
                                 "unscannable)"},
            422: {"description": "Tệp chứa mã độc (infected), hoặc có mật khẩu, nén quá nhiều lớp nên không quét được "
                                 "(unscannable) — đã chặn, không lưu, ghi file.rejected vào sổ kiểm toán"},
            503: {"description": "ClamAV, kho đối tượng, CSDL hoặc két khóa (restricted=true) không sẵn sàng; `busy` "
                                 "(kèm `Retry-After: 10`) khi đang kiểm, đóng dấu tệp hạn chế khác — không lưu"},
        },
    )
    async def upload_file(
        request: Request,
        principal: Annotated[Principal, Depends(current_principal)],
        restricted: Annotated[bool, Query(description=(
            "Tệp của văn bản hạn chế (F3.7): chỉ nhận PDF; lưu mã hóa bằng khóa dữ liệu riêng do két cấp, "
            "chỉ gắn được vào văn bản hạn chế, xem có dấu tên người xem"))] = False,
    ) -> FileOut:
        limit = settings.max_upload_bytes
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > limit + MULTIPART_OVERHEAD:
            raise _error(413, "too_large", f"Tệp vượt giới hạn {limit // (1024 * 1024)} MB")
        if restricted and vault is None:
            raise _error(503, "vault_unavailable", "Chưa cấu hình két khóa, chưa nhận được tệp của văn bản hạn chế")

        form = await request.form(max_files=1, max_fields=1)
        try:
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise _error(400, "missing_file", "Thiếu trường 'file' trong form multipart")
            return await ingest(request.state.request_id, principal.tenant_id, principal.user_id, upload,
                                filename=clean_filename(upload.filename), mime=clean_mime(upload.content_type),
                                restricted=restricted)
        finally:
            await form.close()

    async def ingest_bytes(rid: str, tenant_id: uuid.UUID, actor_id: str, data: bytes, name: str,
                           restricted: bool) -> str:
        """Một tệp lấy ra từ zip của lô nạp đi đúng đường của tải lên lẻ (ingest); trả id tệp đã lưu."""
        out = await ingest(rid, tenant_id, actor_id, MemoryFile(data), filename=clean_filename(name),
                           mime=clean_mime(mimetypes.guess_type(name)[0]), restricted=restricted)
        return str(out.id)

    # discard: dòng không thành văn bản thì vòng nền gỡ tệp đã lưu cho dòng (dòng core.files rồi đối tượng trong kho)
    incoming = IncomingHandler(hasura, import_store, ingest_bytes, discard, max_file_bytes=settings.max_upload_bytes,
                               sealing=vault is not None)
    importer = Importer(import_store, {incoming.kind: incoming}, spool, interval_s=settings.import_interval_s,
                        chunk=settings.import_chunk)
    app.state.importer = importer
    # Nạp lô văn bản đến: POST /api/imports/{kind}, GET /api/imports… — imports/api.py
    imports_api.install(app, settings=settings, store=import_store, handlers=importer.handlers, spool=spool,
                        principal=current_principal, quarantine=quarantine, clean_filename=clean_filename,
                        max_body=settings.import_data_max_bytes + settings.import_zip_max_bytes + MULTIPART_OVERHEAD)

    @app.get(
        "/api/files/{file_id}",
        response_class=StreamingResponse,
        summary="Tải tệp xuống, nếu người gọi được xem tệp",
        description="Tệp của văn bản hạn chế (F3.7) được giải mã trong bộ nhớ, đóng dấu tên người xem và giờ xem lên "
                    "mọi trang; mỗi lần mở ghi một dòng `file.decrypted` vào sổ kiểm toán — không ghi được sổ thì "
                    "không trả tệp.",
        responses={
            200: {"content": {"application/octet-stream": {}}, "description": "Nội dung tệp, luôn ở dạng tải về"},
            401: {"description": "Thiếu hoặc sai token"},
            404: {"description": "Không có tệp, hoặc người gọi không được xem — hai trường hợp trả như nhau"},
            422: {"description": "Tệp mã hóa giải mã được nhưng không đóng dấu người xem được (`unstampable`, "
                                 "`reason`): PDF quá MOC_RESTRICTED_MAX_PAGES trang, quá nặng hoặc hỏng — không trả tệp"},
            500: {"description": "Tệp mã hóa không mở được: bản mã hỏng hoặc không khớp tệp"},
            503: {"description": "CSDL, kho đối tượng hoặc két khóa không sẵn sàng; `busy` (kèm `Retry-After: 10`) khi "
                                 "đang mở, kiểm tệp hạn chế khác"},
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
            loc = None
            if meta is not None:
                loc = await hasura.file_location(
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
        if meta is None or loc is None:
            raise _error(404, "not_found", "Không có tệp này, hoặc bạn không có quyền xem")
        if meta.encrypted or loc.wrapped_dek is not None:
            return await open_sealed(request, principal, meta, loc)
        key = loc.object_key

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

    async def open_sealed(request: Request, principal: Principal, meta: StoredFile, loc: Location) -> Response:
        """Tệp của văn bản hạn chế (F3.7): giải mã trong bộ nhớ, kiểm băm, đóng dấu người xem, ghi sổ rồi mới trả."""
        rid = request.state.request_id
        if vault is None or loc.wrapped_dek is None:
            raise _error(503, "vault_unavailable", "Chưa cấu hình két khóa, chưa mở được tệp của văn bản hạn chế")
        wrapped = loc.wrapped_dek
        who = principal.display_name or principal.user_id
        # Bản mã cũng nằm trong RAM: đọc kho, mở khóa đều trong giới hạn số lượt cùng lúc, không chỉ bước giải mã
        async with sealing_slot():
            try:
                blob = b"".join(await asyncio.to_thread(lambda: list(store.read_stream(loc.object_key, CHUNK_SIZE))))
            except StorageError as exc:
                log_event("core.file.read_failed", request, file_id=meta.id, object_key=loc.object_key, error=str(exc))
                raise _error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc
            try:
                dek = await vault.unwrap(wrapped)
            except VaultError as exc:
                log_event("core.file.vault_failed", request, file_id=meta.id, error=str(exc))
                raise _error(503, "vault_unavailable", "Két khóa chưa sẵn sàng, chưa mở được tệp") from exc
            at = datetime.now(UTC)

            def unseal_checked() -> bytes:
                plain = unseal(blob, dek, principal.tenant_id, meta.id)
                if hashlib.sha256(plain).hexdigest() != meta.sha256:
                    raise SealError("băm bản rõ không khớp CSDL")
                return plain

            try:
                plain = await asyncio.to_thread(unseal_checked)
            except SealError as exc:
                log_event("core.file.unseal_failed", request, tenant_id=principal.tenant_id, file_id=meta.id,
                          error=str(exc))
                raise _error(500, "sealed_corrupt", "Tệp mã hóa không mở được (hỏng hoặc không khớp tệp)") from exc
            # Bản rõ là PDF do người dùng tải lên: đóng dấu trong tiến trình con có giới hạn, qua ống, không xuống đĩa
            try:
                out = await run_watermark(plain, who, at, max_pages=settings.restricted_max_pages)
            except SealError as exc:
                log_event("core.file.stamp_failed", request, tenant_id=principal.tenant_id, file_id=meta.id,
                          reason=exc.reason)
                raise _error(422, "unstampable", f"Không đóng dấu được tên người xem lên tệp nên chưa mở: {exc}",
                             reason=exc.reason) from exc
            del plain
        # Mỗi lần mở đều vào sổ kiểm toán; không ghi được sổ thì không trả bản rõ
        try:
            await hasura.log_event(tenant_id=principal.tenant_id, actor_id=principal.user_id, request_id=rid,
                                   action="file.decrypted", entity="core.files", entity_id=str(meta.id),
                                   details={"watermark": who, "at": at.isoformat(timespec="seconds")})
        except HasuraError as exc:
            log_event("core.file.audit_failed", request, file_id=meta.id, error=str(exc))
            raise _error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán nên chưa mở tệp") from exc
        log_event("core.file.decrypted", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  file_id=meta.id, size_bytes=len(out))
        return Response(out, media_type="application/pdf", headers={
            **DOWNLOAD_HEADERS, **NO_STORE, "Content-Disposition": content_disposition(meta.filename),
        })

    @app.get(
        "/api/search",
        response_model=SearchOut,
        summary="Tìm văn bản theo số ký hiệu, trích yếu, cơ quan ban hành, nội dung",
        responses={
            400: {"description": "Câu tìm trống, hoặc `cursor` sai, không phải của câu tìm này"},
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
        cursor: Annotated[str | None, Query(max_length=100, description="`next_cursor` của trang trước")] = None,
    ) -> SearchOut:
        if not q.strip():
            raise _error(400, "empty_query", "Nhập từ cần tìm")
        query = SearchQuery(q=q.strip(), direction=direction, status=status, type_code=type_code,
                            urgency=urgency, year=year)
        scope = json.dumps([principal.user_id, str(principal.tenant_id), *dataclasses.astuple(query)],
                           ensure_ascii=False)
        try:
            offset = cursors.open(cursor, scope) if cursor else 0
        except ValueError as exc:
            raise _error(400, "invalid_cursor", "Trang sau không còn hợp lệ, hãy tìm lại") from exc
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
        return SearchOut(hits=[SearchHit.model_validate(h) for h in hits],
                         next_cursor=cursors.seal(next_offset, scope) if next_offset is not None else None)

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

    # Văn bản tương tự cho tác tử gợi ý giao việc (F4.3): POST /internal/similar-documents — assist/similar.py
    similar.install(app, assistant, hasura, service_caller)

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

        # Ký số (F4.5): ký trước khi băm — băm, sự kiện issued, sổ kiểm toán, bản liên thông, cổng xác thực đều theo
        # bản đã ký. Văn bản hạn chế không ký (mỗi lần xem bị viết lại để đóng dấu tên người xem). Két chưa có PKI,
        # từ chối hay pyHanko lỗi: phát hành không ký; két không trả lời: 503, không lưu gì, văn thư bấm lại
        will_sign = False
        if signer is not None and not row.get("restricted"):
            try:
                will_sign = await signer.ready()
            except SigningUnavailable as exc:
                log_event("office.document.sign_failed", request, level=logging.ERROR, document_id=body.document_id,
                          error=str(exc))
                raise _error(503, "signing_unavailable", "Két ký số chưa sẵn sàng, thử lại sau") from exc
        verify_base = f"{settings.public_url}/xac-thuc"
        pdf = await asyncio.to_thread(render_pdf, letter_from(row, verify_base=verify_base))
        record, sign_ms = None, 0
        if will_sign:
            tenant, started = row["tenant"], time.monotonic()
            try:
                pdf, record = await signer.sign(
                    pdf, tenant_id=body.tenant_id, org_name=tenant["name"], parent_name=tenant.get("parent_name"),
                    place_name=tenant.get("place_name"), symbol=row["symbol"],
                    verify_url=f"{verify_base}/{row['verify_code']}")
            except SigningUnavailable as exc:
                log_event("office.document.sign_failed", request, level=logging.ERROR, document_id=body.document_id,
                          error=str(exc))
                raise _error(503, "signing_unavailable", "Két ký số chưa sẵn sàng, thử lại sau") from exc
            except (SigningOff, SigningError) as exc:   # thiếu cấu hình hoặc lỗi ký: phát hành không ký, báo to
                log_event("office.document.sign_failed", request, level=logging.ERROR, document_id=body.document_id,
                          error=str(exc))
            sign_ms = round((time.monotonic() - started) * 1000)
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
        stored, wrapped, stored_mime = pdf, None, "application/pdf"
        if row.get("restricted"):       # văn bản hạn chế (F3.7): bản phát hành cũng lưu mã hóa như tệp tải lên
            stored, wrapped = await seal_bytes(rid, pdf, body.tenant_id, file_id)
            stored_mime = "application/octet-stream"
        try:
            await asyncio.to_thread(store.put, key, io.BytesIO(stored), size=len(stored), content_type=stored_mime,
                                    sha256_hex=hashlib.sha256(stored).hexdigest())
        except StorageError as exc:
            raise _error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc
        try:
            await hasura.insert_file(
                tenant_id=body.tenant_id, actor_id=body.actor_id, request_id=rid, file_id=file_id, object_key=key,
                filename=row["symbol"].replace("/", "-") + ".pdf", mime_type="application/pdf",
                size_bytes=len(pdf), sha256_hex=digest, scanned_at=scanned_at, wrapped_dek=wrapped, signature=record,
            )
        except HasuraError as exc:
            await discard(rid, key)
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng, chưa lưu bản phát hành") from exc
        log_event("office.document.rendered", request, tenant_id=body.tenant_id, actor_id=body.actor_id,
                  document_id=body.document_id, file_id=file_id, size_bytes=len(pdf), encrypted=wrapped is not None,
                  signed=record is not None, caller=caller)
        if record is not None:
            log_event("office.document.signed", request, tenant_id=body.tenant_id, document_id=body.document_id,
                      file_id=file_id, key_name=record.key_name, key_version=record.key_version, serial=record.serial,
                      duration_ms=sign_ms)
        return IssueOut(file_id=file_id, sha256=digest, size_bytes=len(pdf))

    # Mỗi lúc một lượt chép liên thông: svc-workflow gọi lại khi lần trước quá hạn chờ thì lần sau đợi lần trước xong
    # rồi thấy bản sao đã có (200), không chép song song trong cùng tiến trình
    copying = asyncio.Lock()

    # Liên thông trong hệ thống (F3.12) — dispatch.py. Như /internal/issue: APISIX không có route, chỉ dịch vụ nội bộ.
    # 201 bản sao mới · 200 bản sao đã có · 404 không có dòng outbox · 409 {code: not_pending | not_issued | restricted |
    # cold | integrity} · 422 trạm quét chặn · 503 kho, ClamAV, CSDL chưa sẵn sàng (svc-workflow thử lại sau)
    @app.post("/internal/dispatch-file", status_code=201, response_model=IssueOut, include_in_schema=False)
    async def dispatch_file(
        body: DispatchFileIn,
        request: Request,
        caller: Annotated[str, Depends(service_caller)],
    ) -> JSONResponse:
        def note(event: str, **fields: object) -> None:
            log_event(event, request, **fields)

        try:
            async with copying:
                copied = await copy_issued_file(body.dispatch_id, actor_id=body.actor_id,
                                                request_id=request.state.request_id, hasura=hasura, store=store,
                                                scanner=scanner, log=note,
                                                drop=lambda key: discard(request.state.request_id, key))
        except DispatchError as exc:
            raise _error(exc.status, exc.code, exc.message) from exc
        note("office.dispatch.file_copied" if copied.created else "office.dispatch.file_exists",
             dispatch_id=body.dispatch_id, tenant_id=copied.tenant_id, actor_id=body.actor_id, file_id=copied.file_id,
             size_bytes=copied.size_bytes, caller=caller)
        out = IssueOut(file_id=copied.file_id, sha256=copied.sha256, size_bytes=copied.size_bytes)
        return JSONResponse(out.model_dump(mode="json"), status_code=201 if copied.created else 200)

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

    # --- sổ đăng ký văn bản đến / đi (F2.8) ----------------------------------------------------------------

    printing = asyncio.Semaphore(2)
    register_responses: dict[int | str, dict[str, object]] = {
        401: {"description": "Thiếu hoặc sai token"},
        403: {"description": "Chỉ văn thư và lãnh đạo đơn vị xem, in sổ đăng ký"},
        503: {"description": "CSDL không sẵn sàng"},
    }

    async def _read_register(direction: str, year: int, request: Request, principal: Principal) -> Register:
        try:
            data = await hasura.register(tenant_id=principal.tenant_id, actor_id=principal.user_id,
                                         request_id=request.state.request_id, direction=direction, year=year)
        except HasuraError as exc:      # vai trò service: lỗi phía máy chủ, không phải token người gọi
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        ids = [doc["id"] for doc in data["office_documents"]]
        try:
            # dòng nào người gọi đọc được: Hasura quyết theo token của họ, sổ chỉ che phần còn lại
            visible = set(await hasura.visible_documents(principal.token, ids)) if ids else set()
        except HasuraAuthError as exc:
            raise HTTPException(
                401, {"code": "invalid_token", "message": "Token không hợp lệ hoặc đã hết hạn"},
                {"WWW-Authenticate": "Bearer"},
            ) from exc
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        return build_register(data, visible, direction=direction, year=year, printed_at=datetime.now(UTC),
                              anchor=anchorer.latest)

    async def _register(direction: str, year: int, request: Request, principal: Principal) -> Register:
        if not REGISTER_ROLES & set(principal.roles):
            raise _error(403, "forbidden", "Chỉ văn thư và lãnh đạo đơn vị xem, in sổ đăng ký")
        reg = await _read_register(direction, year, request, principal)
        # Số cuối đã cấp và các dòng là hai câu đọc riêng: văn thư khác vào sổ đúng lúc đó thì có thể thấy số mới mà
        # chưa thấy dòng của nó. Đọc lại một lần; vẫn thiếu thì là thiếu thật, báo ra.
        return await _read_register(direction, year, request, principal) if reg.missing else reg

    Direction = Annotated[Literal["in", "out"], Path(description="in: sổ văn bản đến; out: sổ văn bản đi")]
    Year = Annotated[int, Path(ge=2000, le=2100)]

    @app.get("/api/registers/{direction}/{year}", response_model=RegisterOut, responses=register_responses,
             summary="Sổ đăng ký văn bản đến / đi của một năm, đúng các cột sẽ in")
    async def register_json(direction: Direction, year: Year, request: Request,
                            principal: Annotated[Principal, Depends(current_principal)]) -> JSONResponse:
        reg = await _register(direction, year, request, principal)
        out = RegisterOut(
            direction=direction, year=year, title=reg.title, org_name=reg.org_name, columns=list(reg.columns),
            entries=[RegisterEntryOut(number=e.number, document_id=e.document_id, hidden=e.hidden, cells=list(e.cells))
                     for e in reg.entries],
            last_number=reg.last, missing=reg.missing,
        )
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

    @app.get(
        "/api/registers/{direction}/{year}/pdf",
        response_class=Response,
        responses={**register_responses, 200: {"content": {"application/pdf": {}},
                                              "description": "Sổ A4 ngang: bìa, bảng theo mẫu, chỗ ký của văn thư"}},
        summary="In sổ đăng ký văn bản đến / đi của một năm ra PDF để ký nhận, đóng sổ (NĐ 30/2020, Điều 16, 22)",
    )
    async def register_pdf(direction: Direction, year: Year, request: Request,
                           principal: Annotated[Principal, Depends(current_principal)]) -> Response:
        reg = await _register(direction, year, request, principal)
        async with printing:    # WeasyPrint tốn CPU: không để nhiều lần in chiếm hết luồng của tải tệp lên, xuống
            pdf = await asyncio.to_thread(render_register_pdf, reg)
        # In sổ là việc đáng ghi lại: ai in, sổ nào, bao nhiêu dòng — vào sổ kiểm toán chuỗi băm
        try:
            await hasura.log_event(
                tenant_id=principal.tenant_id, actor_id=principal.user_id, request_id=request.state.request_id,
                action="register.printed", entity="office.registers", entity_id=f"{direction}/{year}",
                details={"direction": direction, "year": year, "entries": len(reg.entries),
                         "masked": sum(e.hidden for e in reg.entries)},
            )
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán, thử lại sau") from exc
        log_event("office.register.printed", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  direction=direction, year=year, entries=len(reg.entries))
        name = f"so-dang-ky-van-ban-{'den' if direction == 'in' else 'di'}-{year}.pdf"
        return Response(pdf, media_type="application/pdf", headers={
            **DOWNLOAD_HEADERS, **NO_STORE, "Content-Disposition": content_disposition(name),
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
            signature = None
            if row.get("signature_level"):      # F4.5: văn bản cũ, văn bản hạn chế không có chữ ký
                signature = VerifiedSignature(level=row["signature_level"], signer=row["signer_name"],
                                              ca=row["signer_ca"], serial=row["certificate_serial"],
                                              signed_at=row["signed_at"])
            out = VerifyOut(result="valid", document=VerifiedDocument(
                symbol=row["symbol"], issued_on=row["issued_on"], type_name=row["type_name"],
                issuer_name=row["issuer_name"], parent_name=row["parent_name"], summary=row["summary"],
                sha256=row["content_sha256"], verify_code=row["verify_code"], status=row["status"],
                signature=signature,
            ))
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

    verify_responses = {
        200: {"model": VerifyOut, "description": "valid: văn bản đã phát hành; not_found: không có văn bản nào khớp"},
        429: {"description": "Vượt giới hạn tra cứu theo địa chỉ IP (APISIX)"},
        503: {"description": "CSDL không sẵn sàng"},
    }

    # Chứng thư CA nội bộ (F4.5) và khóa công khai ký mốc neo sổ kiểm toán: tệp công khai đọc từ két, để người ngoài
    # tự kiểm chữ ký số văn bản và mốc neo đã chép ra ngoài (docs/van-hanh.md mục Mốc neo công khai). Khai báo trước
    # /api/verify/{code}: route nào khớp trước thì được chọn. Két chưa có PKI, chưa có khóa (két khởi tạo trước khi có
    # chúng) thì 404; két không trả lời thì 503
    pem_responses: dict[int | str, dict[str, object]] = {
        200: {"content": {"application/x-pem-file": {}}, "description": "Tệp PEM"},
        404: {"description": "Két chưa có (két khởi tạo trước khi có tính năng này, hoặc không dùng két)"},
        429: {"description": "Vượt giới hạn tra cứu theo địa chỉ IP (APISIX)"},
        503: {"description": "Két không trả lời"},
    }

    def _pem(text: str, filename: str) -> Response:
        return Response(text, media_type="application/x-pem-file", headers={
            "X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=300",
            "Content-Disposition": content_disposition(filename)})

    @app.get("/api/verify/ca.pem", response_class=Response, responses=pem_responses,
             summary="Chứng thư CA nội bộ ký văn bản đi (PEM, chỉ minh họa; không cần đăng nhập)")
    async def verify_ca_pem(request: Request) -> Response:
        missing = _error(404, "no_ca", "Két chưa có CA nội bộ: văn bản phát hành không có chữ ký số")
        if vault is None:
            raise missing
        try:
            pem = (await vault.pki_ca_pem()).strip()
        except VaultError as exc:
            if exc.status in (204, 403, 404):   # mount pki chưa có, hoặc chưa có CA
                raise missing from exc
            log_event("core.verify.ca_failed", request, level=logging.WARNING, error=str(exc))
            raise _error(503, "vault_unavailable", "Chưa đọc được két, thử lại sau") from exc
        if not pem.startswith("-----BEGIN CERTIFICATE-----"):
            raise missing
        return _pem(pem + "\n", "signet-ca.pem")

    @app.get("/api/verify/anchor-key.pem", response_class=Response, responses=pem_responses,
             summary="Khóa công khai Ed25519 ký mốc neo sổ kiểm toán (PEM SubjectPublicKeyInfo; không cần đăng nhập)")
    async def verify_anchor_key(request: Request) -> Response:
        missing = _error(404, "no_anchor_key", "Két chưa có khóa ký mốc neo: mốc neo không có chữ ký")
        if anchor_signer is None:
            raise missing
        try:
            key = await anchor_signer.public_key()
        except VaultError as exc:
            log_event("core.verify.anchor_key_failed", request, level=logging.WARNING, error=str(exc))
            raise _error(503, "vault_unavailable", "Chưa đọc được két, thử lại sau") from exc
        if key is None:
            raise missing
        return _pem(key.pem, "signet-anchor-key.pem")

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

    # --- trạng thái hệ thống (không cần đăng nhập; APISIX giới hạn tốc độ theo IP) ---------------------------

    @app.get("/api/status", response_model=StatusOut,
             responses={429: {"description": "Vượt giới hạn theo địa chỉ IP (APISIX)"}},
             summary="Trạng thái vận hành các thành phần của Signet (không cần đăng nhập, lưu đệm 10 giây)")
    async def system_status() -> JSONResponse:
        # qua model: chỉ các trường khai ở StatusOut ra ngoài, kể cả khi status.py sau này gom thêm gì
        out = StatusOut.model_validate(await status_board.report())
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

    # --- phòng đọc hồ sơ đã nộp lưu (F3.8) ----------------------------------------------------------------

    def _broken(exc: Exception) -> str:
        """Câu lỗi 502 của gói hỏng: lệch băm (ArchiveError) hay thiếu đối tượng — thử lại không khỏi."""
        return "Gói lưu trữ thiếu một phần trong bucket lạnh" if isinstance(exc, ObjectMissing) else str(exc)

    async def _archived_case_file(principal: Principal, case_file_id: uuid.UUID) -> dict:
        """Hồ sơ đã nộp lưu mà người gọi xem được (token → Hasura quyết): 404 / 409 / 503 như nhau ở mọi đường đọc."""
        try:
            row = await hasura.visible_case_file(principal.token, case_file_id)
        except HasuraAuthError as exc:
            raise _error(401, "invalid_token", "Token không hợp lệ") from exc
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
        if row is None:
            raise _error(404, "not_found", "Không có hồ sơ này")
        if row["status"] != "archived":
            raise _error(409, "not_archived", "Hồ sơ chưa nộp lưu")
        return row

    archive_responses = {
        404: {"description": "Không có hồ sơ, hoặc người gọi không được xem"},
        409: {"description": "Hồ sơ chưa nộp lưu"},
        502: {"description": "`archive_mismatch`: gói trong bucket lạnh không khớp băm ghi trong CSDL, hoặc thiếu "
                             "một phần của gói"},
        503: {"description": "Chưa đọc được CSDL hoặc bucket lạnh"},
    }

    @app.get("/api/case-files/{case_file_id}/archive", response_model=ArchiveOut, responses=archive_responses,
             summary="Phòng đọc: đọc lại gói lưu trữ của hồ sơ đã nộp lưu từ bucket lạnh, kiểm băm")
    async def case_file_archive(case_file_id: uuid.UUID, request: Request,
                                principal: Annotated[Principal, Depends(current_principal)]) -> JSONResponse:
        row = await _archived_case_file(principal, case_file_id)
        try:
            pkg = await asyncio.to_thread(read_package, cold, row["archive_key"], row["archive_sha256"])
        except (ArchiveError, ObjectMissing) as exc:
            log_event("case_file.archive_mismatch", request, level=logging.WARNING, case_file_id=case_file_id,
                      error=str(exc))
            raise _error(502, "archive_mismatch", _broken(exc)) from exc
        except StorageError as exc:
            raise _error(503, "storage_unavailable", "Chưa đọc được bucket lạnh, thử lại sau") from exc
        # Đọc hồ sơ lưu trữ là việc đáng ghi lại: ai đọc hồ sơ nào
        try:
            await hasura.log_event(
                tenant_id=principal.tenant_id, actor_id=principal.user_id, request_id=request.state.request_id,
                action="case_file.read", entity="office.case_files", entity_id=str(case_file_id),
                details={"code": row["code"], "archive_sha256": row["archive_sha256"]},
            )
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán, thử lại sau") from exc
        manifest = pkg["manifest"]
        # Từng văn bản theo đúng quyền xem như khi còn nóng (giao việc ở lại CSDL nên quy tắc vẫn áp được)
        try:
            readable = await hasura.visible_documents(principal.token, [d["id"] for d in pkg["documents"]])
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
        documents = [d for d in pkg["documents"] if d["id"] in readable]
        files = []
        for f in manifest["files"]:
            linked = [link["document_id"] for link in f["documents"] if link["document_id"] in readable]
            if linked:
                files.append(ArchivedFileOut(
                    file_id=f["file_id"], filename=f["filename"], mime_type=f["mime_type"], sha256=f["sha256"],
                    bytes=f["bytes"], document_ids=linked, viewable=f["mime_type"] == "application/pdf"))
        out = ArchiveOut(
            case_file_id=case_file_id, code=row["code"], title=row["title"], closed_on=row["closed_on"],
            archived_at=row["archived_at"], archive_key=row["archive_key"], manifest_sha256=pkg["manifest_sha256"],
            retain_until=manifest["retain_until"],
            documents=[ArchivedDocumentOut(**d) for d in documents],
            files=files,
            hidden=len(pkg["documents"]) - len(documents),
        )
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

    archived_file_responses = {
        200: {"content": {"application/pdf": {}},
              "description": "Bản PDF có dấu tên người xem và giờ xem trên mọi trang, `Content-Disposition: inline`"},
        401: {"description": "Thiếu hoặc sai token"},
        404: {"description": "Không có hồ sơ, tệp không thuộc gói, hoặc người gọi không đọc được văn bản nào gắn tệp "
                             "này — các trường hợp trả như nhau"},
        409: {"description": "Hồ sơ chưa nộp lưu"},
        415: {"description": "`not_viewable`: tệp không phải PDF — phòng đọc chỉ mở bản PDF đóng dấu được"},
        422: {"description": "`unstampable` + `reason`: PDF không đóng dấu được (quá MOC_RESTRICTED_MAX_PAGES "
                             "trang, quá nặng, hỏng) — không trả tệp"},
        502: {"description": "`archive_mismatch`: manifest không khớp băm trong CSDL, tệp không khớp băm trong "
                             "manifest, hoặc gói thiếu manifest hay tệp — không trả tệp"},
        503: {"description": "CSDL, bucket lạnh hoặc sổ kiểm toán chưa sẵn sàng; `busy` (kèm `Retry-After: 10`) khi "
                             "đang đóng dấu tệp khác"},
    }

    @app.get(
        "/api/case-files/{case_file_id}/archive/files/{file_id}",
        response_class=Response,
        responses=archived_file_responses,
        summary="Phòng đọc: xem một tệp trong gói lưu trữ (chỉ xem, PDF có dấu tên người xem)",
        description="Cùng quy tắc quyền như `GET /api/case-files/{id}/archive`: hồ sơ người gọi xem được, tệp gắn "
                    "với văn bản người gọi đọc được. Tệp đọc từ bucket lạnh, so băm với manifest (manifest đã so với "
                    "CSDL), đóng dấu tên người xem và giờ xem lên mọi trang, ghi `case_file.file_viewed` vào sổ "
                    "kiểm toán — ghi không được thì không trả tệp. Không ghi gì vào bucket lạnh.",
    )
    async def view_archived_file(case_file_id: uuid.UUID, file_id: uuid.UUID, request: Request,
                                 principal: Annotated[Principal, Depends(current_principal)]) -> Response:
        row = await _archived_case_file(principal, case_file_id)
        try:
            manifest = await asyncio.to_thread(read_manifest, cold, row["archive_key"], row["archive_sha256"])
        except (ArchiveError, ObjectMissing) as exc:
            log_event("case_file.archive_mismatch", request, level=logging.WARNING, case_file_id=case_file_id,
                      error=str(exc))
            raise _error(502, "archive_mismatch", _broken(exc)) from exc
        except StorageError as exc:
            raise _error(503, "storage_unavailable", "Chưa đọc được bucket lạnh, thử lại sau") from exc
        entry = next((f for f in manifest["files"] if f["file_id"] == str(file_id)), None)
        if entry is None:
            raise _error(404, "not_found", "Không có tệp này trong hồ sơ, hoặc bạn không có quyền xem")
        # Tệp xem được khi người gọi đọc được ít nhất một văn bản gắn nó — như danh sách `files` của GET …/archive
        try:
            readable = await hasura.visible_documents(principal.token, [d["document_id"] for d in entry["documents"]])
        except HasuraAuthError as exc:
            raise _error(401, "invalid_token", "Token không hợp lệ") from exc
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
        if not readable:
            raise _error(404, "not_found", "Không có tệp này trong hồ sơ, hoặc bạn không có quyền xem")
        if entry["mime_type"] != "application/pdf":
            raise _error(415, "not_viewable", "Phòng đọc chỉ mở được tệp PDF (đóng dấu tên người xem được)")
        who = principal.display_name or principal.user_id
        # Byte của tệp chỉ nằm trong RAM: đọc kho lạnh, đóng dấu đều trong giới hạn số lượt cùng lúc như F3.7
        async with sealing_slot():
            try:
                data = await asyncio.to_thread(read_archived_file, cold, row["archive_key"], entry)
            except (ArchiveError, ObjectMissing) as exc:
                log_event("case_file.archive_mismatch", request, level=logging.WARNING, case_file_id=case_file_id,
                          file_id=file_id, error=str(exc))
                raise _error(502, "archive_mismatch", _broken(exc)) from exc
            except StorageError as exc:
                raise _error(503, "storage_unavailable", "Chưa đọc được bucket lạnh, thử lại sau") from exc
            at = datetime.now(UTC)
            try:
                out = await run_watermark(data, who, at, max_pages=settings.restricted_max_pages, kind="archive")
            except SealError as exc:
                log_event("case_file.stamp_failed", request, tenant_id=principal.tenant_id, file_id=file_id,
                          reason=exc.reason)
                raise _error(422, "unstampable", f"Không đóng dấu được tên người xem lên tệp nên chưa mở: {exc}",
                             reason=exc.reason) from exc
            del data
        # Mỗi lần xem đều vào sổ kiểm toán; không ghi được sổ thì không trả tệp
        try:
            await hasura.log_event(
                tenant_id=principal.tenant_id, actor_id=principal.user_id, request_id=request.state.request_id,
                action="case_file.file_viewed", entity="office.case_files", entity_id=str(case_file_id),
                details={"code": row["code"], "archive_sha256": row["archive_sha256"], "file_id": str(file_id),
                         "sha256": entry["sha256"], "watermark": who, "at": at.isoformat(timespec="seconds")},
            )
        except HasuraError as exc:
            log_event("case_file.audit_failed", request, case_file_id=case_file_id, error=str(exc))
            raise _error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán nên chưa mở tệp") from exc
        log_event("case_file.file_viewed", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  case_file_id=case_file_id, file_id=file_id, size_bytes=len(out))
        return Response(out, media_type="application/pdf", headers={
            **DOWNLOAD_HEADERS, **NO_STORE, "Content-Disposition": content_disposition(entry["filename"], inline=True),
        })

    # Nộp lưu theo yêu cầu (F3.8): lãnh đạo phòng nộp lưu hồ sơ đã đóng của phòng mình ngay, không đợi vòng nền
    # (MOC_ARCHIVE_AFTER_DAYS). Đội chọn: chuyên viên lập, đóng; lãnh đạo phòng (`manager`) nộp — hai người, người nộp
    # là người phụ trách phòng có hồ sơ (căn cứ điều khoản chưa đối chiếu văn bản gốc, xem PLAN/NOTES việc 90). Một
    # lượt mỗi lúc trong tiến trình: dùng chung khóa với vòng nền (Archiver.lock); hàm SQL làm trọng tài cho mọi lượt
    archive_lock = archiver.lock

    archive_run_responses = {
        401: {"description": "Thiếu hoặc sai token"},
        403: {"description": "`forbidden`: chỉ lãnh đạo phòng (`manager`) nộp lưu hồ sơ của phòng mình"},
        404: {"description": "Không có hồ sơ, hoặc hồ sơ không thuộc phòng của người gọi"},
        409: {"description": "`not_closed` hồ sơ còn mở · `already_archived` đã nộp lưu (kể cả lượt khác vừa xong) · "
                             "`archive_failed` + `message`: không nộp lưu được (văn bản không còn ở trạng thái nộp lưu "
                             "được, đang gửi liên thông, tệp trong kho nóng không khớp băm…) · `archive_conflict`: "
                             "CSDL từ chối vì hồ sơ hay văn bản đổi trong lúc nộp lưu — CSDL không đổi gì"},
        503: {"description": "CSDL, kho đối tượng hoặc sổ kiểm toán chưa sẵn sàng; `busy` (kèm `Retry-After: 10`) khi "
                             "đang có lượt nộp lưu khác trong tiến trình (nút bấm hay vòng nền) — chưa ghi sổ"},
    }

    async def _closed_case_file(principal: Principal, case_file_id: uuid.UUID) -> dict:
        """Hồ sơ đã đóng mà người gọi (manager) xem được, không thì lỗi đúng nghĩa: 404, 409 already_archived, 409
        not_closed, 401, 503."""
        try:
            row = await hasura.visible_case_file(principal.token, case_file_id)
        except HasuraAuthError as exc:
            raise _error(401, "invalid_token", "Token không hợp lệ") from exc
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
        if row is None:
            raise _error(404, "not_found", "Không có hồ sơ này")
        if row["status"] == "archived":
            raise _error(409, "already_archived", "Hồ sơ đã nộp lưu")
        if row["status"] != "closed":
            raise _error(409, "not_closed", "Hồ sơ còn mở: đóng hồ sơ trước khi nộp lưu")
        return row

    @app.post("/api/case-files/{case_file_id}/archive", response_model=ArchiveRunOut, responses=archive_run_responses,
              summary="Nộp lưu ngay hồ sơ đã đóng (lãnh đạo phòng): gói Parquet + tệp + manifest vào bucket lạnh",
              description="Cùng các bước như vòng nộp lưu nền: kiểm băm tệp nóng, ghi gói khóa ghi, đọc lại so băm, "
                          "hàm SQL `office.archive_case_file` một giao dịch. Giành được lượt rồi mới kiểm lại hồ sơ và "
                          "ghi `case_file.archive_requested` vào sổ kiểm toán, sau đó mới làm; CSDL ghi "
                          "`case_file.archived` khi xong.")
    async def archive_case_file(case_file_id: uuid.UUID, request: Request,
                                principal: Annotated[Principal, Depends(current_principal)]) -> JSONResponse:
        # vai trò Hasura áp cho token: manager thì Hasura chỉ trả hồ sơ của phòng mình
        if principal.role != "manager":
            raise _error(403, "forbidden", "Chỉ lãnh đạo phòng nộp lưu hồ sơ của phòng mình")
        await _closed_case_file(principal, case_file_id)      # trả lời ngay, không chờ lượt
        try:
            await asyncio.wait_for(archive_lock.acquire(), SEALING_QUEUE_S)
        except TimeoutError:
            raise HTTPException(503, {"code": "busy", "message": "Đang nộp lưu hồ sơ khác, thử lại sau ít giây"},
                                {"Retry-After": RETRY_AFTER}) from None
        try:
            # trong lúc chờ lượt, lượt khác có thể đã nộp lưu xong hồ sơ này
            row = await _closed_case_file(principal, case_file_id)
            try:
                await hasura.log_event(
                    tenant_id=principal.tenant_id, actor_id=principal.user_id, request_id=request.state.request_id,
                    action="case_file.archive_requested", entity="office.case_files", entity_id=str(case_file_id),
                    details={"code": row["code"]},
                )
            except HasuraError as exc:
                raise _error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán, thử lại sau") from exc
            done = await _run_archive(principal, case_file_id, request)
        finally:
            archive_lock.release()
        log_event("case_file.archived", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  case_file_id=case_file_id, archive_sha256=done.archive_sha256, documents=done.documents,
                  files=done.files)
        out = ArchiveRunOut(case_file_id=case_file_id, code=done.code, archive_key=done.archive_key,
                            archive_sha256=done.archive_sha256, documents=done.documents, files=done.files,
                            bytes=done.bytes, run_id=done.run_id)
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

    async def _run_archive(principal: Principal, case_file_id: uuid.UUID, request: Request) -> Archived:
        """Một lượt nộp lưu (đã giữ khóa), lỗi đổi ra mã đúng nghĩa."""
        def failed(exc: Exception) -> None:
            log_event("case_file.archive_failed", request, level=logging.WARNING, case_file_id=case_file_id,
                      error=str(exc))

        try:
            return await archiver.archive(str(case_file_id))
        except ArchiveStateError as exc:     # lệnh tay ở tiến trình khác vừa đổi trạng thái hồ sơ
            failed(exc)
            if exc.status == "archived":
                raise _error(409, "already_archived", "Hồ sơ đã nộp lưu") from exc
            raise _error(409, "not_closed", f"Chưa nộp lưu được: {exc}") from exc
        except ArchiveError as exc:
            failed(exc)
            raise _error(409, "archive_failed", f"Chưa nộp lưu được: {exc}") from exc
        except StorageError as exc:
            failed(exc)
            raise _error(503, "storage_unavailable", "Kho đối tượng chưa sẵn sàng, chưa nộp lưu — thử lại sau") from exc
        except HasuraError as exc:
            failed(exc)
            # CSDL trả lời khác "đã nộp lưu": đọc lại hồ sơ để biết. Đã archived → lượt khác (hoặc chính lượt này, mất
            # câu trả lời) đã xong. Vẫn closed mà Hasura có trả lời (có mã lỗi) → hàm SQL từ chối, giao dịch đã quay
            # lui: xung đột, 409. Không đọc lại được hay mất kết nối → chưa biết, 503
            try:
                now = await hasura.visible_case_file(principal.token, case_file_id)
            except HasuraError:
                now = None
            if now is not None and now["status"] == "archived":
                raise _error(409, "already_archived", "Hồ sơ đã nộp lưu") from exc
            if now is not None and exc.code is not None:
                raise _error(409, "archive_conflict", "CSDL từ chối lượt nộp lưu vì hồ sơ hoặc văn bản đổi trong lúc "
                             "nộp lưu, chưa đổi gì — tải lại hồ sơ rồi thử lại") from exc
            raise _error(503, "database_unavailable",
                         "CSDL chưa xác nhận lượt nộp lưu — tải lại hồ sơ để xem trạng thái, thử lại sau") from exc

    return app
