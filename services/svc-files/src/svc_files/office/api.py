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

"""Route của Văn phòng điện tử trong svc-files (docs/architecture.md §4.3, §4.7 bước 2).

Mười một route trước đây khai thẳng trong ``create_app`` (app.py), chia ba ``APIRouter`` theo nhóm:

- ``documents``: ``POST /internal/issue`` (dựng, ký, lưu bản phát hành — F2.4, F4.5), ``POST /internal/dispatch-file``
  (liên thông — F3.12, dispatch.py), ``GET /api/documents/{id}/preview``, sổ đăng ký
  ``GET /api/registers/{in|out}/{năm}`` và ``…/pdf`` (F2.8, registers.py), chứng thư CA ký văn bản đi
  ``GET /api/verify/ca.pem``;
- ``verify``: cổng xác thực ``GET /api/verify/{code}``, ``GET /api/verify?sha256=`` (F2.13);
- ``case_files``: phòng đọc ``GET /api/case-files/{id}/archive``, ``…/archive/files/{file_id}`` và nộp lưu theo yêu
  cầu ``POST /api/case-files/{id}/archive`` (F3.8, archive.py).

Ba nhóm vì app.py gắn chúng đúng ba chỗ cũ, xen giữa route của lõi (``/api/verify/anchor-key.pem`` phải khớp trước
``/api/verify/{code}``; ``/api/status``): thứ tự đường dẫn, nên cả OpenAPI ``docs/api/openapi/svc-files.json``, không
đổi. ``Office`` cũng dựng thành phần của Văn phòng (tác tử đọc văn bản đến, bucket lạnh, vòng nộp lưu) và gắn route
đọc văn bản đến (docread/api.py). ``MOC_OFFICE_ENABLED=false``: app.py không dựng ``Office``, không gắn route nào ở đây.
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu của dependency khai báo trong routers().
import asyncio
import hashlib
import io
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..anchors import Anchorer
from ..archive import (Archived, ArchiveError, Archiver, ArchiveStateError, ColdStore, read_archived_file,
                       read_manifest, read_package)
from ..archive_stats import ArchiveStats
from ..auth import Principal
from ..clamav import ScanError
from ..config import Settings
from ..dispatch import DispatchError, copy_issued_file
from ..docread import api as docread_api
from ..docread.reader import Reader
from ..docread.summarize import make_summarizer
from ..hasura import HasuraAuthError, HasuraError
from ..lineage import Lineage
from ..registers import Register, build_register, render_register_pdf
from ..render import letter_from, render_pdf
from ..sealed import SealError, VaultError, run_watermark
from ..signing import SigningError, SigningOff, SigningUnavailable
from ..storage import ObjectMissing, StorageError, object_key, s3_client
from ..web import (CHUNK_SIZE, DOWNLOAD_HEADERS, NO_STORE, PEM_RESPONSES, RETRY_AFTER, SEALING_QUEUE_S,
                   content_disposition, error, log_event, pem_response)
from .hasura import OfficeHasura

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


VERIFY_CODE_RE = re.compile(r"[^A-Z2-7]")
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
        description="Văn bản người gọi đọc được (cùng quy tắc như trước khi nộp lưu), đọc từ bảng Parquet trong gói "
                    "(DuckDB)")
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


class ArchiveYearOut(BaseModel):
    year: int | None = Field(description="Năm ban hành của văn bản (thiếu thì năm của hồ sơ)")
    incoming: int
    outgoing: int


class ArchiveTypeOut(BaseModel):
    type_code: str = Field(description="Mã loại văn bản (office.document_types)")
    incoming: int
    outgoing: int


class ArchiveDepartmentOut(BaseModel):
    department_id: uuid.UUID | None = Field(description="Phòng lập hồ sơ, theo manifest của gói")
    case_files: int
    documents: int


class UnreadablePackageOut(BaseModel):
    case_file_id: uuid.UUID
    code: str


class ArchiveStatsOut(BaseModel):
    """Số liệu văn bản đã nộp lưu của đơn vị: DuckDB đọc các bảng Parquet trong bucket lạnh (#304). Chỉ số đếm."""

    case_files: int = Field(description="Số hồ sơ đã nộp lưu có gói đọc được, khớp băm")
    documents: int
    incoming: int
    outgoing: int
    by_year: list[ArchiveYearOut]
    by_type: list[ArchiveTypeOut]
    by_department: list[ArchiveDepartmentOut]
    unreadable: list[UnreadablePackageOut] = Field(
        description="Hồ sơ có gói không đọc được (lệch băm, thiếu đối tượng, sai dạng): không vào số liệu, bình thường "
                    "rỗng. Chỉ `case_file_id` và ký hiệu (`code`); lý do ghi vào nhật ký "
                    "(`case_file.archive_stats_skipped`)")
    bucket: str = Field(description="Bucket lạnh (khóa ghi S3 Object Lock) chứa các gói")
    computed_at: datetime = Field(description="Lúc DuckDB tính; tính lại khi có hồ sơ mới nộp lưu")


@dataclass(frozen=True)
class Routers:
    documents: APIRouter    # văn bản đi, liên thông, sổ đăng ký, chứng thư CA
    verify: APIRouter       # cổng xác thực: tra theo mã, theo băm
    case_files: APIRouter   # phòng đọc, nộp lưu theo yêu cầu


class Office:
    """Phần Văn phòng của một app svc-files: thành phần dựng một lần, route gắn qua ``install_reader``, ``routers()``.

    ``reader``, ``cold``, ``archiver``, ``archive_stats``: test tự tiêm bản giả; không truyền thì dựng theo
    ``settings``."""

    def __init__(self, settings: Settings, hasura: OfficeHasura, store: Any, *, reader: Reader | None = None,
                 cold: ColdStore | None = None, archiver: Archiver | None = None,
                 archive_stats: ArchiveStats | None = None) -> None:
        self.settings = settings
        self.hasura = hasura
        self.store = store
        self.reader = reader or Reader(settings, hasura, store, summarizer=make_summarizer(
            settings.ai_url, settings.ai_model, max_chars=settings.ai_max_chars))
        self.cold = cold or ColdStore(
            s3_client(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
            settings.cold_bucket,
        )
        self.archiver = archiver or Archiver(hasura, store, self.cold, after_days=settings.archive_after_days,
                                             interval_s=settings.archive_interval_s,
                                             lineage_url=settings.openlineage_url)
        # Số liệu đã nộp lưu cho trang Điều hành (#304), đọc đúng bucket lạnh của phần này; phả hệ ghi như lượt nộp
        # lưu (khóa quản trị, không nhận gì từ người dùng ngoài đơn vị trong token)
        self.archive_stats = archive_stats or ArchiveStats(self.cold, Lineage(
            lambda query, variables: hasura.admin(query, variables, {"X-Hasura-User-Id": "svc-files:archive-stats"}),
            settings.openlineage_url),
            threads=settings.archive_stats_threads, memory_mb=settings.archive_stats_memory_mb)

    def install_reader(self, app: FastAPI, principal: Callable[..., Principal]) -> None:
        """Đọc văn bản đến (F4.1): POST /api/files/{file_id}/read — docread/api.py."""
        docread_api.install(app, self.reader, principal)

    async def aclose(self) -> None:
        await self.reader.summarizer.aclose()


def routers(
    office: Office,
    *,
    scanner: Any,
    vault: Any,
    signer: Any,
    anchorer: Anchorer,
    current_principal: Callable[..., Principal],
    service_caller: Callable[..., str],
    seal_bytes: Callable[[str, bytes, uuid.UUID, uuid.UUID], Coroutine[Any, Any, tuple[bytes, str]]],
    sealing_slot: Callable[[], AbstractAsyncContextManager[None]],
    discard: Callable[[str, str], Coroutine[Any, Any, None]],
) -> Routers:
    """Ba nhóm route của ``office``. Dependency, trạm quét, két, khóa của app.py truyền vào: ``current_principal``
    (token người dùng), ``service_caller`` (token dịch vụ của /internal/*), ``seal_bytes`` (mã hóa tệp hạn chế),
    ``sealing_slot`` (chung lượt với tải xuống tệp hạn chế), ``discard`` (gỡ đối tượng mồ côi trong kho)."""
    settings, hasura, store = office.settings, office.hasura, office.store
    cold, archiver, archive_stats = office.cold, office.archiver, office.archive_stats
    documents, verify, case_files = APIRouter(), APIRouter(), APIRouter()

    # --- văn bản đi -----------------------------------------------------------------------------------

    async def _scan_bytes(data: bytes) -> bool:
        async def chunks() -> AsyncIterator[bytes]:
            for i in range(0, len(data), CHUNK_SIZE):
                yield data[i:i + CHUNK_SIZE]
        return (await scanner.scan(chunks())).clean

    # API nội bộ: APISIX không có route tới đây; chỉ client trong MOC_SERVICE_CLIENTS (svc-workflow) gọi được.
    @documents.post("/internal/issue", status_code=201, response_model=IssueOut, include_in_schema=False)
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
            raise error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        if row is None:
            raise error(404, "not_found", "Không có văn bản đi này trong đơn vị")
        if row["status"] != "approved" or not row["symbol"] or not row["verify_code"]:
            raise error(409, "not_numbered", "Văn bản chưa được duyệt và cấp số")

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
                raise error(503, "signing_unavailable", "Két ký số chưa sẵn sàng, thử lại sau") from exc
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
                raise error(503, "signing_unavailable", "Két ký số chưa sẵn sàng, thử lại sau") from exc
            except (SigningOff, SigningError) as exc:   # thiếu cấu hình hoặc lỗi ký: phát hành không ký, báo to
                log_event("office.document.sign_failed", request, level=logging.ERROR, document_id=body.document_id,
                          error=str(exc))
            sign_ms = round((time.monotonic() - started) * 1000)
        digest = hashlib.sha256(pdf).hexdigest()
        # Tệp do hệ thống dựng vẫn qua trạm kiểm dịch như mọi tệp: core.files chỉ có tệp đã quét
        try:
            clean = await _scan_bytes(pdf)
        except ScanError as exc:
            raise error(503, "scanner_unavailable", "Trạm quét mã độc chưa sẵn sàng") from exc
        scanned_at = datetime.now(UTC)
        if not clean:
            log_event("office.document.render_rejected", request, document_id=body.document_id)
            raise error(500, "render_rejected", "Bản PDF dựng ra bị trạm quét chặn")

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
            raise error(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc
        try:
            await hasura.insert_file(
                tenant_id=body.tenant_id, actor_id=body.actor_id, request_id=rid, file_id=file_id, object_key=key,
                filename=row["symbol"].replace("/", "-") + ".pdf", mime_type="application/pdf",
                size_bytes=len(pdf), sha256_hex=digest, scanned_at=scanned_at, wrapped_dek=wrapped, signature=record,
            )
        except HasuraError as exc:
            await discard(rid, key)
            raise error(503, "database_unavailable", "CSDL chưa sẵn sàng, chưa lưu bản phát hành") from exc
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
    # 201 bản sao mới · 200 bản sao đã có · 404 không có dòng outbox · 409 {code: not_pending | not_issued |
    # restricted | cold | integrity} · 422 trạm quét chặn · 503 kho, ClamAV, CSDL chưa sẵn sàng (svc-workflow thử lại
    # sau)
    @documents.post("/internal/dispatch-file", status_code=201, response_model=IssueOut, include_in_schema=False)
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
            raise error(exc.status, exc.code, exc.message) from exc
        note("office.dispatch.file_copied" if copied.created else "office.dispatch.file_exists",
             dispatch_id=body.dispatch_id, tenant_id=copied.tenant_id, actor_id=body.actor_id, file_id=copied.file_id,
             size_bytes=copied.size_bytes, caller=caller)
        out = IssueOut(file_id=copied.file_id, sha256=copied.sha256, size_bytes=copied.size_bytes)
        return JSONResponse(out.model_dump(mode="json"), status_code=201 if copied.created else 200)

    @documents.get(
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
            raise error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        if row is None:
            raise error(404, "not_found", "Không có văn bản này, hoặc bạn không có quyền xem")
        if row["status"] in ("issued", "archived"):
            raise error(409, "issued", "Văn bản đã phát hành, hãy tải bản phát hành")
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
            raise error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
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
            raise error(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        return build_register(data, visible, direction=direction, year=year, printed_at=datetime.now(UTC),
                              anchor=anchorer.latest)

    async def _register(direction: str, year: int, request: Request, principal: Principal) -> Register:
        if not REGISTER_ROLES & set(principal.roles):
            raise error(403, "forbidden", "Chỉ văn thư và lãnh đạo đơn vị xem, in sổ đăng ký")
        reg = await _read_register(direction, year, request, principal)
        # Số cuối đã cấp và các dòng là hai câu đọc riêng: văn thư khác vào sổ đúng lúc đó thì có thể thấy số mới mà
        # chưa thấy dòng của nó. Đọc lại một lần; vẫn thiếu thì là thiếu thật, báo ra.
        return await _read_register(direction, year, request, principal) if reg.missing else reg

    Direction = Annotated[Literal["in", "out"], Path(description="in: sổ văn bản đến; out: sổ văn bản đi")]
    Year = Annotated[int, Path(ge=2000, le=2100)]

    @documents.get("/api/registers/{direction}/{year}", response_model=RegisterOut, responses=register_responses,
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

    @documents.get(
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
            raise error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán, thử lại sau") from exc
        log_event("office.register.printed", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  direction=direction, year=year, entries=len(reg.entries))
        name = f"so-dang-ky-van-ban-{'den' if direction == 'in' else 'di'}-{year}.pdf"
        return Response(pdf, media_type="application/pdf", headers={
            **DOWNLOAD_HEADERS, **NO_STORE, "Content-Disposition": content_disposition(name),
        })

    @documents.get("/api/verify/ca.pem", response_class=Response, responses=PEM_RESPONSES,
                   summary="Chứng thư CA nội bộ ký văn bản đi (PEM, chỉ minh họa; không cần đăng nhập)")
    async def verify_ca_pem(request: Request) -> Response:
        missing = error(404, "no_ca", "Két chưa có CA nội bộ: văn bản phát hành không có chữ ký số")
        if vault is None:
            raise missing
        try:
            pem = (await vault.pki_ca_pem()).strip()
        except VaultError as exc:
            if exc.status in (204, 403, 404):   # mount pki chưa có, hoặc chưa có CA
                raise missing from exc
            log_event("core.verify.ca_failed", request, level=logging.WARNING, error=str(exc))
            raise error(503, "vault_unavailable", "Chưa đọc được két, thử lại sau") from exc
        if not pem.startswith("-----BEGIN CERTIFICATE-----"):
            raise missing
        return pem_response(pem + "\n", "signet-ca.pem")

    # --- cổng xác thực (không cần đăng nhập; APISIX giới hạn tốc độ theo IP) ------------------------------

    async def _verify(request: Request, method: str, **lookup: str) -> JSONResponse:
        try:
            row = await hasura.verify(**lookup)
        except HasuraError as exc:
            log_event("core.verify.failed", request, error=str(exc))
            raise error(503, "database_unavailable", "Chưa tra cứu được, thử lại sau") from exc
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

    @verify.get("/api/verify/{code}", response_model=VerifyOut, responses=verify_responses,
                summary="Tra văn bản đã phát hành theo mã tra cứu in cạnh mã QR (không cần đăng nhập)")
    async def verify_by_code(code: Annotated[str, Path(max_length=40)], request: Request) -> JSONResponse:
        # nhận cả dạng có dấu gạch, khoảng trắng, chữ thường: ABCDE-23456, abcde 23456
        normalized = VERIFY_CODE_RE.sub("", code.upper())
        if len(normalized) != 10:
            log_event("core.verify", request, method="code", result="malformed")
            return JSONResponse(VerifyOut(result="not_found").model_dump(mode="json"), headers=NO_STORE)
        return await _verify(request, "code", code=normalized)

    @verify.get("/api/verify", response_model=VerifyOut, responses=verify_responses,
                summary="Tra văn bản đã phát hành theo SHA-256 của tệp PDF (trình duyệt tự tính, không tải tệp lên)")
    async def verify_by_hash(
        request: Request,
        sha256: Annotated[str, Query(pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256 của tệp, 64 ký tự hex")],
    ) -> JSONResponse:
        return await _verify(request, "sha256", sha256_hex=sha256.lower())

    # --- phòng đọc hồ sơ đã nộp lưu (F3.8) ----------------------------------------------------------------

    def _broken(exc: Exception) -> str:
        """Câu lỗi 502 của gói hỏng: lệch băm (ArchiveError) hay thiếu đối tượng — thử lại không khỏi."""
        return "Gói lưu trữ thiếu một phần trong bucket lạnh" if isinstance(exc, ObjectMissing) else str(exc)

    async def _archived_case_file(principal: Principal, case_file_id: uuid.UUID) -> dict:
        """Hồ sơ đã nộp lưu mà người gọi xem được (token → Hasura quyết): 404 / 409 / 503 như nhau ở mọi đường đọc."""
        try:
            row = await hasura.visible_case_file(principal.token, case_file_id)
        except HasuraAuthError as exc:
            raise error(401, "invalid_token", "Token không hợp lệ") from exc
        except HasuraError as exc:
            raise error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
        if row is None:
            raise error(404, "not_found", "Không có hồ sơ này")
        if row["status"] != "archived":
            raise error(409, "not_archived", "Hồ sơ chưa nộp lưu")
        return row

    archive_responses = {
        404: {"description": "Không có hồ sơ, hoặc người gọi không được xem"},
        409: {"description": "Hồ sơ chưa nộp lưu"},
        502: {"description": "`archive_mismatch`: gói trong bucket lạnh không khớp băm ghi trong CSDL, hoặc thiếu "
                             "một phần của gói"},
        503: {"description": "Chưa đọc được CSDL hoặc bucket lạnh"},
    }

    @case_files.get("/api/case-files/{case_file_id}/archive", response_model=ArchiveOut, responses=archive_responses,
                    summary="Phòng đọc: đọc lại gói lưu trữ của hồ sơ đã nộp lưu từ bucket lạnh, kiểm băm")
    async def case_file_archive(case_file_id: uuid.UUID, request: Request,
                                principal: Annotated[Principal, Depends(current_principal)]) -> JSONResponse:
        row = await _archived_case_file(principal, case_file_id)
        try:
            pkg = await asyncio.to_thread(read_package, cold, row["archive_key"], row["archive_sha256"])
        except (ArchiveError, ObjectMissing) as exc:
            log_event("case_file.archive_mismatch", request, level=logging.WARNING, case_file_id=case_file_id,
                      error=str(exc))
            raise error(502, "archive_mismatch", _broken(exc)) from exc
        except StorageError as exc:
            raise error(503, "storage_unavailable", "Chưa đọc được bucket lạnh, thử lại sau") from exc
        # Đọc hồ sơ lưu trữ là việc đáng ghi lại: ai đọc hồ sơ nào
        try:
            await hasura.log_event(
                tenant_id=principal.tenant_id, actor_id=principal.user_id, request_id=request.state.request_id,
                action="case_file.read", entity="office.case_files", entity_id=str(case_file_id),
                details={"code": row["code"], "archive_sha256": row["archive_sha256"]},
            )
        except HasuraError as exc:
            raise error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán, thử lại sau") from exc
        manifest = pkg["manifest"]
        # Từng văn bản theo đúng quyền xem như khi còn nóng (giao việc ở lại CSDL nên quy tắc vẫn áp được)
        try:
            readable = await hasura.visible_documents(principal.token, [d["id"] for d in pkg["documents"]])
        except HasuraError as exc:
            raise error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
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

    @case_files.get(
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
            raise error(502, "archive_mismatch", _broken(exc)) from exc
        except StorageError as exc:
            raise error(503, "storage_unavailable", "Chưa đọc được bucket lạnh, thử lại sau") from exc
        entry = next((f for f in manifest["files"] if f["file_id"] == str(file_id)), None)
        if entry is None:
            raise error(404, "not_found", "Không có tệp này trong hồ sơ, hoặc bạn không có quyền xem")
        # Tệp xem được khi người gọi đọc được ít nhất một văn bản gắn nó — như danh sách `files` của GET …/archive
        try:
            readable = await hasura.visible_documents(principal.token, [d["document_id"] for d in entry["documents"]])
        except HasuraAuthError as exc:
            raise error(401, "invalid_token", "Token không hợp lệ") from exc
        except HasuraError as exc:
            raise error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
        if not readable:
            raise error(404, "not_found", "Không có tệp này trong hồ sơ, hoặc bạn không có quyền xem")
        if entry["mime_type"] != "application/pdf":
            raise error(415, "not_viewable", "Phòng đọc chỉ mở được tệp PDF (đóng dấu tên người xem được)")
        who = principal.display_name or principal.user_id
        # Byte của tệp chỉ nằm trong RAM: đọc kho lạnh, đóng dấu đều trong giới hạn số lượt cùng lúc như F3.7
        async with sealing_slot():
            try:
                data = await asyncio.to_thread(read_archived_file, cold, row["archive_key"], entry)
            except (ArchiveError, ObjectMissing) as exc:
                log_event("case_file.archive_mismatch", request, level=logging.WARNING, case_file_id=case_file_id,
                          file_id=file_id, error=str(exc))
                raise error(502, "archive_mismatch", _broken(exc)) from exc
            except StorageError as exc:
                raise error(503, "storage_unavailable", "Chưa đọc được bucket lạnh, thử lại sau") from exc
            at = datetime.now(UTC)
            try:
                out = await run_watermark(data, who, at, max_pages=settings.restricted_max_pages, kind="archive")
            except SealError as exc:
                log_event("case_file.stamp_failed", request, tenant_id=principal.tenant_id, file_id=file_id,
                          reason=exc.reason)
                raise error(422, "unstampable", f"Không đóng dấu được tên người xem lên tệp nên chưa mở: {exc}",
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
            raise error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán nên chưa mở tệp") from exc
        log_event("case_file.file_viewed", request, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                  case_file_id=case_file_id, file_id=file_id, size_bytes=len(out))
        return Response(out, media_type="application/pdf", headers={
            **DOWNLOAD_HEADERS, **NO_STORE, "Content-Disposition": content_disposition(entry["filename"], inline=True),
        })

    # --- phân tích dữ liệu đã nộp lưu cho trang Điều hành (#304) --------------------------------------------------

    @case_files.get("/api/case-files/archive-stats", response_model=ArchiveStatsOut,
                    responses={
                        401: {"description": "Thiếu hoặc sai token"},
                        403: {"description": "`forbidden`: chỉ lãnh đạo đơn vị (`director`), như trang Điều hành"},
                        503: {"description": "Chưa đọc được CSDL hoặc bucket lạnh"},
                    },
                    summary="Trang Điều hành: số liệu văn bản đã nộp lưu — DuckDB đọc các gói Parquet trong bucket "
                            "lạnh",
                    description="Quyền như trang Điều hành: chỉ lãnh đạo đơn vị, số liệu của đơn vị trong token "
                                "(Hasura trả các hồ sơ đã nộp lưu người gọi xem được). Mỗi gói: manifest so băm với "
                                "CSDL, bảng văn bản so băm với manifest, rồi DuckDB đếm trên mọi bảng một lượt. Chỉ số "
                                "đếm; lưu đệm tới khi có hồ sơ mới nộp lưu (có gói không đọc được thì 60 giây). Mỗi "
                                "tập manifest mới là một run OpenLineage `moc.archive.stats` (đầu vào: các bảng "
                                "Parquet đã đọc).")
    async def case_file_archive_stats(request: Request,
                                      principal: Annotated[Principal, Depends(current_principal)]) -> JSONResponse:
        if principal.role != "director":
            raise error(403, "forbidden", "Chỉ lãnh đạo đơn vị xem số liệu đã nộp lưu")
        try:
            packages = await hasura.archived_case_files(principal.token)
        except HasuraAuthError as exc:
            raise error(401, "invalid_token", "Token không hợp lệ") from exc
        except HasuraError as exc:
            raise error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
        try:
            stats = await archive_stats.get(principal.tenant_id, packages)
        except StorageError as exc:
            raise error(503, "storage_unavailable", "Chưa đọc được bucket lạnh, thử lại sau") from exc
        if stats.unreadable:
            log_event("case_file.archive_mismatch", request, level=logging.WARNING, tenant_id=principal.tenant_id,
                      unreadable=[u["case_file_id"] for u in stats.unreadable])
        out = ArchiveStatsOut(
            case_files=stats.case_files, documents=stats.documents, incoming=stats.incoming, outgoing=stats.outgoing,
            by_year=stats.by_year, by_type=stats.by_type, by_department=stats.by_department,
            unreadable=stats.unreadable, bucket=cold.bucket, computed_at=stats.computed_at,
        )
        return JSONResponse(out.model_dump(mode="json"), headers=NO_STORE)

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
            raise error(401, "invalid_token", "Token không hợp lệ") from exc
        except HasuraError as exc:
            raise error(503, "database_unavailable", "Chưa đọc được CSDL, thử lại sau") from exc
        if row is None:
            raise error(404, "not_found", "Không có hồ sơ này")
        if row["status"] == "archived":
            raise error(409, "already_archived", "Hồ sơ đã nộp lưu")
        if row["status"] != "closed":
            raise error(409, "not_closed", "Hồ sơ còn mở: đóng hồ sơ trước khi nộp lưu")
        return row

    @case_files.post(
        "/api/case-files/{case_file_id}/archive", response_model=ArchiveRunOut, responses=archive_run_responses,
        summary="Nộp lưu ngay hồ sơ đã đóng (lãnh đạo phòng): gói Parquet + tệp + manifest vào bucket lạnh",
        description="Cùng các bước như vòng nộp lưu nền: kiểm băm tệp nóng, ghi gói khóa ghi, đọc lại so băm, "
                    "hàm SQL `office.archive_case_file` một giao dịch. Giành được lượt rồi mới kiểm lại hồ sơ và "
                    "ghi `case_file.archive_requested` vào sổ kiểm toán, sau đó mới làm; CSDL ghi "
                    "`case_file.archived` khi xong.",
    )
    async def archive_case_file(case_file_id: uuid.UUID, request: Request,
                                principal: Annotated[Principal, Depends(current_principal)]) -> JSONResponse:
        # vai trò Hasura áp cho token: manager thì Hasura chỉ trả hồ sơ của phòng mình
        if principal.role != "manager":
            raise error(403, "forbidden", "Chỉ lãnh đạo phòng nộp lưu hồ sơ của phòng mình")
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
                raise error(503, "database_unavailable", "Chưa ghi được sổ kiểm toán, thử lại sau") from exc
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
                raise error(409, "already_archived", "Hồ sơ đã nộp lưu") from exc
            raise error(409, "not_closed", f"Chưa nộp lưu được: {exc}") from exc
        except ArchiveError as exc:
            failed(exc)
            raise error(409, "archive_failed", f"Chưa nộp lưu được: {exc}") from exc
        except StorageError as exc:
            failed(exc)
            raise error(503, "storage_unavailable", "Kho đối tượng chưa sẵn sàng, chưa nộp lưu — thử lại sau") from exc
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
                raise error(409, "already_archived", "Hồ sơ đã nộp lưu") from exc
            if now is not None and exc.code is not None:
                raise error(409, "archive_conflict", "CSDL từ chối lượt nộp lưu vì hồ sơ hoặc văn bản đổi trong lúc "
                             "nộp lưu, chưa đổi gì — tải lại hồ sơ rồi thử lại") from exc
            raise error(503, "database_unavailable",
                         "CSDL chưa xác nhận lượt nộp lưu — tải lại hồ sơ để xem trạng thái, thử lại sau") from exc

    return Routers(documents, verify, case_files)
