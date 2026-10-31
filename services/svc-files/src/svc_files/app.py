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

Tải lên (F1.5, F1.6): kiểm token → quét ClamAV → sạch mới nhận loại theo nội dung (filetype.py), bỏ siêu dữ liệu
ảnh JPEG, PNG (imageclean.py) → ghi SeaweedFS → thêm dòng core.files qua Hasura. ClamAV không trả lời thì từ chối
(503), không bao giờ lưu tệp chưa quét; tệp nhiễm được ghi vào sổ kiểm toán. Tải xuống: hỏi Hasura bằng chính
token người dùng xem họ có được xem tệp không, rồi mới đọc từ SeaweedFS. Tìm kiếm (F1.7): Meilisearch xếp hạng,
Hasura lọc theo quyền — chi tiết ở search.py.

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

Route, thành phần của Văn phòng điện tử (văn bản đi, sổ đăng ký, cổng xác thực trừ anchor-key.pem, liên thông, nộp lưu,
phòng đọc — office/api.py; đọc văn bản đến; gợi ý giao việc; nạp lô văn bản đến) chỉ gắn, chỉ chạy vòng nền khi
MOC_OFFICE_ENABLED bật (mặc định); tắt thì còn lõi: tải tệp lên, xuống, tìm kiếm, hỏi đáp, trạng thái, mốc neo.

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
import unicodedata
import uuid
from collections.abc import Iterator
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, date, datetime
from functools import partial
from typing import TYPE_CHECKING, Annotated, BinaryIO, Literal, Protocol

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from . import __version__, filetype, pii
from .anchors import Anchorer, AnchorSigner, AnchorStore
from .assist import api as assist_api
from .assist.ai import AiClient, make_ai
from .assist.answer import Assistant
from .assist.index import ChunkIndexer
from .assist.meili import ChunkIndex
from .assist.retrieve import Retriever
from .auth import AuthError, Principal, TokenVerifier
from .clamav import ClamAVClient, ScanError
from .config import Settings
from .hasura import HasuraAuthError, HasuraClient, HasuraError, Location, StoredFile
from .imageclean import FORMATS as CLEANED_IMAGES, CleanError, run_clean
from .imports import api as imports_api
from .imports.runner import Importer, IncomingHandler
from .imports.spool import Spool
from .imports.store import ImportStore
from .ocr import run_ocr
from .openbao import with_secrets
from .sealed import SealError, Vault, VaultError, run_check_pdf, run_watermark, seal, unseal
from .search import Cursor, Indexer, MeiliClient, SearchError, SearchQuery, search_documents
from .signing import DocumentSigner, SigningUnavailable, preload as preload_signing
from .status import StatusBoard, default_board
from .storage import ObjectStore, StorageError, object_key, s3_client
from .texts import TextExtractor
from .web import (CHUNK_SIZE, DOWNLOAD_HEADERS, NO_STORE, PEM_RESPONSES, RETRY_AFTER, SEALING_QUEUE_S,
                  content_disposition, error, log_event, log_rid, pem_response)

if TYPE_CHECKING:    # chỉ cho chú thích kiểu; phần Văn phòng nạp trong create_app khi bật (#489)
    from .office import api as office_api

# Phần đầu và biên của multipart cộng thêm vào kích thước tệp
MULTIPART_OVERHEAD = 64 * 1024
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


class StatusOpenDataFile(BaseModel):
    file: str = Field(description="Tên tệp trong bản chụp, vd tt-26-2026-tt-bgddt.pdf")
    url: str | None = Field(description="Nơi đã tải tệp (http/https)")
    sha256: str = Field(description="SHA-256 của tệp; trùng `sha256` của một tệp đính kèm là văn bản từ nguồn này")
    bytes: int
    fetched_at: datetime | None = Field(description="Lúc tải tệp; null: như `fetched_at` của nguồn")
    meta: dict[str, str | int | float | bool | None] = Field(
        description="Thông tin tùy nguồn, chỉ giá trị đơn, vd symbol, issuer_name, issued_on, page_url, gazette")


class StatusOpenData(BaseModel):
    source: str = Field(description="Mã nguồn, tên thư mục trong seed/du-lieu-mo, vd cong-bao-gddt")
    name: str | None
    publisher: str | None = Field(description="Cơ quan công bố")
    home_url: str | None
    reuse_basis: str | None = Field(description="Căn cứ dùng lại (điều luật hay giấy phép)")
    licence: str | None = Field(description="Giấy phép mở nếu nguồn có; null: dùng lại theo `reuse_basis`")
    fetched_at: datetime | None = Field(description="Lúc lấy bản chụp")
    age_days: int | None = Field(description="Tuổi bản chụp, tính bằng ngày")
    max_age_days: int | None
    state: Literal["ok", "stale", "broken"] = Field(
        description="ok · stale: quá `max_age_days` · broken: manifest hỏng, thiếu tệp, sai cỡ hay sai SHA-256")
    files: list[StatusOpenDataFile]


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
    open_data: list[StatusOpenData] = Field(
        default_factory=list, description="Nguồn dữ liệu công khai đi kèm bản cài (#424): nguồn gốc, tuổi dữ liệu; "
                                          "bản cài không gọi nguồn lúc chạy, chỉ đọc bản chụp")


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
    hasura: HasuraClient | None = None,     # Văn phòng bật thì phải là OfficeHasura (hoặc bản giả có đủ hàm)
    meili: MeiliClient | None = None,
    anchor_store: AnchorStore | None = None,
    vault: Vault | None = None,
    reader: "office_api.Reader | None" = None,
    assistant: Assistant | None = None,
    chunk_indexer: ChunkIndexer | None = None,
    ai: AiClient | None = None,
    signer: DocumentSigner | None = None,
    status_board: StatusBoard | None = None,
    import_store: ImportStore | None = None,
    cold: "office_api.ColdStore | None" = None,
    archiver: "office_api.Archiver | None" = None,
    archive_stats: "office_api.ArchiveStats | None" = None,
) -> FastAPI:
    _setup_logging()
    settings = settings or Settings.from_env(with_secrets(os.environ))
    # Văn phòng tắt thì không nạp mô-đun nào của nó (#489, docs/architecture.md §4.7); ba tên dưới chỉ dùng khi bật
    if settings.office_enabled:
        from .assist import similar
        from .office import api as office_api
        from .office.hasura import OfficeHasura
    scanner = scanner or ClamAVClient(settings.clamav_host, settings.clamav_port, settings.clamav_timeout_s)
    store = store or ObjectStore(
        settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region, settings.bucket
    )
    verifier = verifier or TokenVerifier(settings.oidc_issuer, settings.oidc_jwks_url, settings.oidc_audience)
    # Văn phòng bật: máy khách chung cộng các câu GraphQL của Văn phòng (office/hasura.py)
    hasura = hasura or (OfficeHasura if settings.office_enabled else HasuraClient)(
        settings.hasura_url, settings.hasura_admin_secret, timeout_s=settings.hasura_timeout_s)
    meili = meili or MeiliClient(settings.meili_url, settings.meili_api_key, settings.search_index)
    cursors = Cursor(settings.hasura_admin_secret)   # khóa dẫn xuất (HKDF) từ một bí mật sẵn có của svc-files
    indexer = Indexer(hasura, meili, interval_s=settings.search_sync_interval_s or 5.0)
    # #253: bản scan (PDF không có lớp chữ) OCR ở vòng nền, hạn MOC_OCR_TIMEOUT_S cho mỗi trang
    scan_ocr = partial(run_ocr, kind="pdf", binary=settings.tesseract_bin, lang=settings.ocr_lang,
                       max_pages=settings.text_ocr_pages, max_pixels=settings.ocr_max_pixels,
                       timeout_s=settings.ocr_timeout_s * settings.text_ocr_pages,
                       memory_mb=settings.ocr_memory_mb) if settings.text_ocr_pages else None
    extractor = TextExtractor(hasura, store, interval_s=settings.text_interval_s or 10.0,
                              max_bytes=settings.max_upload_bytes, ocr=scan_ocr)
    anchorer = Anchorer(
        hasura,
        anchor_store or AnchorStore(
            s3_client(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
            settings.cold_bucket,
            settings.anchor_retention_days,
        ),
        interval_s=settings.anchor_interval_s,
    )
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
    # Văn phòng điện tử (docs/architecture.md §4.3): tác tử đọc văn bản đến, bucket lạnh, vòng nộp lưu — office/api.py.
    # MOC_OFFICE_ENABLED=false: không dựng, không gắn route nào của Văn phòng, không chạy vòng nền của nó
    office = (office_api.Office(settings, hasura, store, reader=reader, cold=cold, archiver=archiver,
                                archive_stats=archive_stats)
              if settings.office_enabled else None)
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
        archive = (asyncio.create_task(office.archiver.run())
                   if office is not None and settings.archive_interval_s > 0 else None)
        # dò Ollama mỗi 60 giây (F4.1); không có mô hình: về ngay
        probe = asyncio.create_task(office.reader.summarizer.run()) if office is not None else None
        # F4.2: vòng đồng bộ + nhúng chỉ mục đoạn, vòng dò mô hình của trợ lý — chỉ khi bật trợ lý
        chunks = (asyncio.create_task(chunk_indexer.run())
                  if settings.ask_enabled and settings.ask_sync_interval_s > 0 else None)
        models = asyncio.create_task(ai.run()) if settings.ask_enabled else None
        # F4.5: dò két một lần để nhật ký khởi động có dòng office.signing.ready / disabled; lỗi để lần phát hành dò lại
        signing = asyncio.create_task(_probe_signer()) if signer is not None else None
        # nạp lô: dọn spool rồi làm tiếp các lô dở (trạng thái nằm trong CSDL); 0 thì tắt cả API tạo lô
        imports = (asyncio.create_task(importer.run())
                   if importer is not None and settings.import_interval_s > 0 else None)
        yield
        for task in (sync, anchor, texts, archive, probe, chunks, models, signing, imports):
            if task is not None:
                task.cancel()
        if office is not None:
            await office.aclose()
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
    if settings.trace_ratio > 0:            # #364: chỉ nạp OpenTelemetry khi bật truy vết
        from . import tracing
        tracing.install(app, "svc-files")
    app.state.indexer = indexer
    app.state.extractor = extractor
    app.state.anchorer = anchorer
    app.state.meili = meili
    app.state.reader = office.reader if office is not None else None
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
    if office is not None:
        office.install_reader(app, current_principal)
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
             "ai": office.reader.summarizer.available if office is not None else False,
             "assist": {"index": bool(chunk_indexer.ready),
                        "semantic": ai.embed_available and bool(chunk_indexer.embedder_ready),
                        "model": ai.chat_available, "embed_pending": chunk_indexer.embed_pending,
                        "embed_failed": chunk_indexer.embed_failed}},
            status_code=200 if ready else 503,
        )

    # Bảng trạng thái cho Prometheus (F3.13, #274), cùng lưu đệm với /api/status. Chỉ trong mạng nội bộ: route `chan`
    # của APISIX trả 404 cho /metrics
    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(await status_board.metrics(), media_type="text/plain; version=0.0.4; charset=utf-8",
                        headers=NO_STORE)

    async def seal_bytes(rid: str, plain: bytes, tenant_id: uuid.UUID, file_id: uuid.UUID) -> tuple[bytes, str]:
        """Bản mã và khóa đã bọc (F3.7). Khóa rõ chỉ sống trong hàm này; két không sẵn sàng thì không lưu gì."""
        if vault is None:
            raise error(503, "vault_unavailable", "Chưa cấu hình két khóa, chưa nhận được tệp của văn bản hạn chế")
        try:
            dek, wrapped = await vault.datakey()
        except VaultError as exc:
            log_rid("core.file.vault_failed", rid, file_id=file_id, error=str(exc))
            raise error(503, "vault_unavailable", "Két khóa chưa sẵn sàng, tệp chưa được lưu") from exc
        return await asyncio.to_thread(seal, plain, dek, tenant_id, file_id), wrapped

    # Kiểm PDF lúc tải lên và giải mã + đóng dấu lúc xem văn bản hạn chế tốn CPU và bộ nhớ (mỗi lượt một tiến trình con
    # tới MEMORY_MB): chung tối đa hai lượt cùng lúc. Bỏ siêu dữ liệu ảnh tải lên cũng vậy, hàng riêng hai lượt. Chờ
    # lượt có hạn — đầy thì 503 busy, không treo yêu cầu
    sealing = asyncio.Semaphore(2)
    cleaning = asyncio.Semaphore(2)

    @asynccontextmanager
    async def slot(lane: asyncio.Semaphore, busy: str) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(lane.acquire(), SEALING_QUEUE_S)
        except TimeoutError:
            raise HTTPException(503, {"code": "busy", "message": busy}, {"Retry-After": RETRY_AFTER}) from None
        try:
            yield
        finally:
            lane.release()

    def sealing_slot() -> AbstractAsyncContextManager[None]:
        return slot(sealing, "Đang kiểm, đóng dấu tệp văn bản hạn chế khác, thử lại sau ít giây")

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
            raise error(413, "too_large", f"Tệp vượt giới hạn {limit // (1024 * 1024)} MB") from None
        except ScanError as exc:
            log_rid("core.file.scan_failed", rid, error=str(exc))
            raise error(503, "scanner_unavailable", "Trạm quét mã độc chưa sẵn sàng, tệp chưa được lưu") from exc

        if digest.size == 0:
            raise error(400, "empty_file", "Tệp rỗng")
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
                raise error(422, "unscannable", "Tệp có mật khẩu hoặc nén quá nhiều lớp nên trạm quét mã độc không "
                             "kiểm được bên trong — đã chặn. Bỏ mật khẩu hoặc giải nén rồi tải lên lại",
                             signature=result.signature)
            raise error(422, "infected", "Tệp chứa mã độc nên đã bị chặn", signature=result.signature)
        return digest

    async def ingest(rid: str, tenant_id: uuid.UUID, actor_id: str, upload: Readable, *, filename: str,
                     declared: str, restricted: bool) -> FileOut:
        """Một tệp vào kho: quét (quarantine) → nhận loại theo nội dung (filetype.py: sai đuôi, sai kiểu khai, tệp
        chạy được thì 415) → văn bản hạn chế: kiểm PDF, mã hóa · ảnh JPEG, PNG: bỏ siêu dữ liệu (imageclean.py) → ghi
        SeaweedFS → thêm dòng core.files của người tải, mime theo nội dung (``declared``: mime trình duyệt khai).
        ClamAV quét byte gốc trước mọi bước: tệp EICAR đổi đuôi vẫn bị chặn và ghi sổ như tệp nhiễm, không thành 415.
        Lỗi trả HTTPException như POST /api/files; lô nạp đọc cùng mã lỗi cho từng dòng."""
        digest = await quarantine(rid, tenant_id, actor_id, upload, filename=filename, limit=settings.max_upload_bytes)
        scanned_at = datetime.now(UTC)
        await upload.seek(0)
        try:
            mime = filetype.check(await upload.read(filetype.HEAD), filename, declared)
        except filetype.Rejected as exc:
            log_rid("core.file.type_rejected", rid, tenant_id=tenant_id, actor_id=actor_id, code=exc.code,
                    found=exc.found, extension=filetype.extension(filename), declared=declared)
            raise error(415, exc.code, exc.message, found=exc.found) from None
        file_id = uuid.uuid4()
        key = object_key(tenant_id, file_id, scanned_at)
        await upload.seek(0)
        wrapped: str | None = None
        body: BinaryIO = upload.file
        # size, sha: của byte người xem nhận (bản rõ) — core.files, cổng xác thực; stored_*: của đối tượng trong kho
        size, sha = digest.size, digest.hexdigest()
        stored_size, stored_sha, stored_mime = size, sha, mime
        if restricted:
            # Văn bản hạn chế (F3.7): bản rõ đọc vào bộ nhớ (Starlette đệm phần lớn tệp ở /tmp — tmpfs trong
            # compose), kiểm đóng dấu được, mã hóa; kho chỉ nhận bản mã
            if mime != "application/pdf":
                raise error(415, "restricted_pdf_only", "Văn bản hạn chế chỉ nhận tệp PDF (để đóng dấu người xem)")
            plain = await upload.read()
            pages = settings.restricted_max_pages
            try:
                async with sealing_slot():      # PDF người dùng tải lên: chỉ mở trong tiến trình con có giới hạn
                    await run_check_pdf(plain, max_pages=pages)
            except SealError as exc:
                raise error(415, "restricted_pdf_only", "Văn bản hạn chế chỉ nhận tệp PDF đọc được, không đặt "
                             f"mật khẩu, tối đa {pages} trang: {exc}", reason=exc.reason) from exc
            blob, wrapped = await seal_bytes(rid, plain, tenant_id, file_id)
            del plain
            body, stored_size = io.BytesIO(blob), len(blob)
            stored_sha, stored_mime = hashlib.sha256(blob).hexdigest(), "application/octet-stream"
        elif mime in CLEANED_IMAGES:
            # Ảnh JPEG, PNG: bỏ EXIF (vị trí GPS), XMP, chú thích — mã hóa lại trong tiến trình con nên byte lưu khác
            # byte tải lên, băm và cỡ tính lại. Loại khác lưu nguyên từng byte (PDF: cổng xác thực, phòng đọc so băm)
            raw = await upload.read()
            try:
                async with slot(cleaning, "Đang xử lý ảnh tải lên khác, thử lại sau ít giây"):
                    cleaned = await run_clean(raw, mime)
            except CleanError as exc:
                raise error(422, "image_unreadable", "Không bỏ được siêu dữ liệu (EXIF, vị trí GPS) của ảnh nên "
                             f"chưa lưu: {exc}", reason=exc.reason) from exc
            del raw
            body, size, sha = io.BytesIO(cleaned), len(cleaned), hashlib.sha256(cleaned).hexdigest()
            stored_size, stored_sha = size, sha
        try:
            await asyncio.to_thread(
                store.put, key, body, size=stored_size, content_type=stored_mime, sha256_hex=stored_sha
            )
        except StorageError as exc:
            log_rid("core.file.store_failed", rid, object_key=key, error=str(exc))
            raise error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng, tệp chưa được lưu") from exc

        try:
            await hasura.insert_file(
                tenant_id=tenant_id,
                actor_id=actor_id,
                request_id=rid,
                file_id=file_id,
                object_key=key,
                filename=filename,
                mime_type=mime,
                size_bytes=size,
                sha256_hex=sha,
                scanned_at=scanned_at,
                wrapped_dek=wrapped,
            )
        except HasuraError as exc:
            log_rid("core.file.record_failed", rid, object_key=key, code=exc.code, error=str(exc))
            await discard(rid, key)
            if exc.code == "constraint-violation":
                # Thường gặp nhất: tenant_id trong token chưa có trong core.tenants.
                raise error(403, "unknown_tenant", "Đơn vị của tài khoản chưa được đăng ký trong hệ thống") from exc
            raise error(503, "database_unavailable", "CSDL chưa sẵn sàng, tệp chưa được lưu") from exc

        log_rid(
            "core.file.stored",
            rid,
            tenant_id=tenant_id,
            actor_id=actor_id,
            file_id=file_id,
            object_key=key,
            size_bytes=size,
            encrypted=wrapped is not None,
        )
        return FileOut(
            id=file_id,
            filename=filename,
            mime_type=mime,
            size_bytes=size,
            sha256=sha,
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
        description="Sau ClamAV: nhận loại theo byte đầu, không tin tên, mime khai; `mime_type` trả về là loại theo "
                    "nội dung. Ảnh JPEG, PNG được bỏ siêu dữ liệu (EXIF, GPS, XMP, chú thích; xoay theo hướng EXIF "
                    "trước) nên `sha256`, `size_bytes` là của ảnh đã làm sạch; tệp loại khác lưu nguyên từng byte.",
        responses={
            401: {"description": "Thiếu hoặc sai token"},
            413: {"description": "Tệp vượt giới hạn MOC_FILES_MAX_MB"},
            415: {"description": "`type_mismatch`: nội dung không khớp đuôi tệp (hay mime khai khi tên không có đuôi), "
                                 "vd tệp .pdf là HTML · `type_not_allowed`: chương trình, kịch bản chạy được (theo nội "
                                 "dung hay đuôi .exe, .bat, .js…) — `found` là loại theo nội dung · "
                                 "`restricted_pdf_only`: restricted=true mà tệp không phải PDF đọc được, không khóa, "
                                 "tối đa MOC_RESTRICTED_MAX_PAGES trang, hoặc quá nặng để kiểm trong giới hạn thời "
                                 "gian, bộ nhớ (`reason`) (PDF phải nhập mật khẩu mới mở thì bị chặn trước ở bước "
                                 "quét: 422 unscannable)"},
            422: {"description": "Tệp chứa mã độc (infected), hoặc có mật khẩu, nén quá nhiều lớp nên không quét được "
                                 "(unscannable) — đã chặn, không lưu, ghi file.rejected vào sổ kiểm toán · "
                                 "`image_unreadable` + `reason` (corrupt, too_many_pixels, timeout, memory): ảnh JPEG, "
                                 "PNG hỏng hoặc quá lớn nên không bỏ được siêu dữ liệu — không lưu"},
            503: {"description": "ClamAV, kho đối tượng, CSDL hoặc két khóa (restricted=true) không sẵn sàng; `busy` "
                                 "(kèm `Retry-After: 10`) khi đang kiểm, đóng dấu tệp hạn chế khác hay xử lý ảnh "
                                 "khác — không lưu"},
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
            raise error(413, "too_large", f"Tệp vượt giới hạn {limit // (1024 * 1024)} MB")
        if restricted and vault is None:
            raise error(503, "vault_unavailable", "Chưa cấu hình két khóa, chưa nhận được tệp của văn bản hạn chế")

        form = await request.form(max_files=1, max_fields=1)
        try:
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise error(400, "missing_file", "Thiếu trường 'file' trong form multipart")
            return await ingest(request.state.request_id, principal.tenant_id, principal.user_id, upload,
                                filename=clean_filename(upload.filename), declared=clean_mime(upload.content_type),
                                restricted=restricted)
        finally:
            await form.close()

    async def ingest_bytes(rid: str, tenant_id: uuid.UUID, actor_id: str, data: bytes, name: str,
                           restricted: bool) -> str:
        """Một tệp lấy ra từ zip của lô nạp đi đúng đường của tải lên lẻ (ingest); trả id tệp đã lưu."""
        out = await ingest(rid, tenant_id, actor_id, MemoryFile(data), filename=clean_filename(name),
                           declared=clean_mime(mimetypes.guess_type(name)[0]), restricted=restricted)
        return str(out.id)

    # Lô nạp chỉ có một loại, văn bản đến (IncomingHandler, của Văn phòng). Văn phòng tắt thì không còn loại nào: không
    # gắn /api/imports*, không chạy vòng nền — lô dở nằm nguyên trong CSDL, bật lại thì làm tiếp
    importer: Importer | None = None
    if office is not None:
        # discard: dòng không thành văn bản thì vòng nền gỡ tệp đã lưu cho dòng (dòng core.files rồi đối tượng trong
        # kho)
        incoming = IncomingHandler(hasura, import_store, ingest_bytes, discard,
                                   max_file_bytes=settings.max_upload_bytes, sealing=vault is not None)
        importer = Importer(import_store, {incoming.kind: incoming}, spool, interval_s=settings.import_interval_s,
                            chunk=settings.import_chunk)
        # Nạp lô văn bản đến: POST /api/imports/{kind}, GET /api/imports… — imports/api.py
        imports_api.install(app, settings=settings, store=import_store, handlers=importer.handlers, spool=spool,
                            principal=current_principal, quarantine=quarantine, clean_filename=clean_filename,
                            max_body=settings.import_data_max_bytes + settings.import_zip_max_bytes
                            + MULTIPART_OVERHEAD)
    app.state.importer = importer

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
            raise error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        if meta is None or loc is None:
            raise error(404, "not_found", "Không có tệp này, hoặc bạn không có quyền xem")
        if meta.encrypted or loc.wrapped_dek is not None:
            return await open_sealed(request, principal, meta, loc)
        key = loc.object_key

        try:
            chunks: Iterator[bytes] = await asyncio.to_thread(store.read_stream, key, CHUNK_SIZE)
        except StorageError as exc:
            log_event("core.file.read_failed", request, file_id=file_id, object_key=key, error=str(exc))
            raise error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc

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
            raise error(503, "vault_unavailable", "Chưa cấu hình két khóa, chưa mở được tệp của văn bản hạn chế")
        wrapped = loc.wrapped_dek
        who = principal.display_name or principal.user_id
        # Bản mã cũng nằm trong RAM: đọc kho, mở khóa đều trong giới hạn số lượt cùng lúc, không chỉ bước giải mã
        async with sealing_slot():
            try:
                blob = b"".join(await asyncio.to_thread(lambda: list(store.read_stream(loc.object_key, CHUNK_SIZE))))
            except StorageError as exc:
                log_event("core.file.read_failed", request, file_id=meta.id, object_key=loc.object_key, error=str(exc))
                raise error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc
            try:
                dek = await vault.unwrap(wrapped)
            except VaultError as exc:
                log_event("core.file.vault_failed", request, file_id=meta.id, error=str(exc))
                raise error(503, "vault_unavailable", "Két khóa chưa sẵn sàng, chưa mở được tệp") from exc
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
                raise error(500, "sealed_corrupt", "Tệp mã hóa không mở được (hỏng hoặc không khớp tệp)") from exc
            # Bản rõ là PDF do người dùng tải lên: đóng dấu trong tiến trình con có giới hạn, qua ống, không xuống đĩa
            try:
                out = await run_watermark(plain, who, at, max_pages=settings.restricted_max_pages)
            except SealError as exc:
                log_event("core.file.stamp_failed", request, tenant_id=principal.tenant_id, file_id=meta.id,
                          reason=exc.reason)
                raise error(422, "unstampable", f"Không đóng dấu được tên người xem lên tệp nên chưa mở: {exc}",
                             reason=exc.reason) from exc
            del plain
        # Mỗi lần mở đều vào sổ kiểm toán; không ghi được sổ thì không trả bản rõ
        try:
            await hasura.log_event(tenant_id=principal.tenant_id, actor_id=principal.user_id, request_id=rid,
                                   action="file.decrypted", entity="core.files", entity_id=str(meta.id),
                                   details={"watermark": who, "at": at.isoformat(timespec="seconds")})
        except HasuraError as exc:
            log_event("core.file.audit_failed", request, file_id=meta.id, error=str(exc))
            raise error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán nên chưa mở tệp") from exc
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
            raise error(400, "empty_query", "Nhập từ cần tìm")
        query = SearchQuery(q=q.strip(), direction=direction, status=status, type_code=type_code,
                            urgency=urgency, year=year)
        scope = json.dumps([principal.user_id, str(principal.tenant_id), *dataclasses.astuple(query)],
                           ensure_ascii=False)
        try:
            offset = cursors.open(cursor, scope) if cursor else 0
        except ValueError as exc:
            raise error(400, "invalid_cursor", "Trang sau không còn hợp lệ, hãy tìm lại") from exc
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
            raise error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        except SearchError as exc:
            log_event("core.search.failed", request, error=str(exc))
            raise error(503, "search_unavailable", "Dịch vụ tìm kiếm chưa sẵn sàng") from exc
        # Không ghi nội dung câu tìm vào nhật ký: có thể chứa thông tin văn bản hạn chế.
        log_event("core.search", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  q_length=len(q), hits=len(hits))
        return SearchOut(hits=[SearchHit.model_validate(h) for h in hits],
                         next_cursor=cursors.seal(next_offset, scope) if next_offset is not None else None)

    # --- API nội bộ, route của Văn phòng ------------------------------------------------------------------

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

    # Route của Văn phòng (office/api.py) gắn ở đúng ba chỗ cũ, xen với route của lõi: thứ tự đường dẫn — nên cả
    # OpenAPI docs/api/openapi/svc-files.json — như khi chúng còn khai trong hàm này
    routes = None
    if office is not None:
        # Văn bản tương tự cho tác tử gợi ý giao việc (F4.3): POST /internal/similar-documents — assist/similar.py
        similar.install(app, assistant, hasura, service_caller)
        routes = office_api.routers(office, scanner=scanner, vault=vault, signer=signer, anchorer=anchorer,
                                    current_principal=current_principal, service_caller=service_caller,
                                    seal_bytes=seal_bytes, sealing_slot=sealing_slot, discard=discard)
        # /internal/issue, /internal/dispatch-file, xem trước, sổ đăng ký, /api/verify/ca.pem
        app.include_router(routes.documents)

    # --- mốc neo sổ kiểm toán (không cần đăng nhập; APISIX giới hạn tốc độ theo IP) ------------------------------

    # Khai báo trước /api/verify/{code} của Văn phòng: route nào khớp trước thì được chọn
    @app.get("/api/verify/anchor-key.pem", response_class=Response, responses=PEM_RESPONSES,
             summary="Khóa công khai Ed25519 ký mốc neo sổ kiểm toán (PEM SubjectPublicKeyInfo; không cần đăng nhập)")
    async def verify_anchor_key(request: Request) -> Response:
        missing = error(404, "no_anchor_key", "Két chưa có khóa ký mốc neo: mốc neo không có chữ ký")
        if anchor_signer is None:
            raise missing
        try:
            key = await anchor_signer.public_key()
        except VaultError as exc:
            log_event("core.verify.anchor_key_failed", request, level=logging.WARNING, error=str(exc))
            raise error(503, "vault_unavailable", "Chưa đọc được két, thử lại sau") from exc
        if key is None:
            raise missing
        return pem_response(key.pem, "signet-anchor-key.pem")

    if routes is not None:      # cổng xác thực: /api/verify/{code}, /api/verify
        app.include_router(routes.verify)

    # --- trạng thái hệ thống (không cần đăng nhập; APISIX giới hạn tốc độ theo IP) ---------------------------

    @app.get("/api/status", response_model=StatusOut,
             responses={429: {"description": "Vượt giới hạn theo địa chỉ IP (APISIX)"}},
             summary="Trạng thái vận hành các thành phần của Signet (không cần đăng nhập, lưu đệm 10 giây)")
    async def system_status() -> JSONResponse:
        # qua model: chỉ các trường khai ở StatusOut ra ngoài, kể cả khi status.py sau này gom thêm gì
        out = StatusOut.model_validate(await status_board.report())
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

    if routes is not None:      # phòng đọc, nộp lưu: /api/case-files/{id}/archive…
        app.include_router(routes.case_files)

    return app
