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

"""Tác tử ``moc-doc-reader`` đọc văn bản đến vừa tải lên, gợi ý thông tin cho form tiếp nhận (F4.1).

``Reader.read`` theo đúng thứ tự, mỗi bước chặn được thì chặn trước khi tốn thêm:

1. Văn thư (vai trò ``clerk``), tệp xem được bằng token của họ **và** do chính họ tải lên (khác → 404 như không có).
   Chỉ tệp có dòng ``core.files`` — tức đã qua ClamAV.
2. Vị trí trong kho (vai trò service, thuê ước trong token). Tệp mã hóa (F3.7) **hoặc** tệp đang gắn vào văn bản hạn
   chế (kể cả tệp rõ có từ trước F3.7) → 409 **trước gợi ý đã lưu và trước khi đọc byte**: bản chữ trần hay bản gửi
   mô hình đều vô hiệu việc hạn chế.
3. Đã có gợi ý lưu (``force`` false) → trả luôn, ``cached``, không ghi sổ.
4. Cỡ tệp → chờ lượt (``MOC_READ_CONCURRENCY``, tối đa ``MOC_READ_QUEUE_S`` giây, quá thì 503 busy) → đọc byte.
5. Nhận loại theo byte đầu, không tin mime khai. PDF: lớp chữ giữ bố cục (pdflayout.py, tiến trình con); trang 1 đủ
   chữ thì dùng, không thì OCR ảnh nhúng — không có ảnh, hay máy chủ chưa OCR được, thì quay về lớp chữ ít ỏi đó.
   Ảnh: OCR (ocr.py, tiến trình con, giết cả nhóm khi quá giờ).
6. Quy tắc (rules.py) quyết mọi trường; mô hình (summarize.py) chỉ viết trích yếu khi quy tắc không ra trích yếu tin
   cậy cao và còn đủ thời gian trong hạn tổng ``MOC_READ_DEADLINE_S``.
7. Một mutation vai trò ``agent``: lưu gợi ý + ghi một dòng sổ ``intake.suggested`` (chỉ siêu dữ liệu) cùng giao dịch,
   **rồi mới trả kết quả** — không ghi được sổ thì không trả gợi ý. Đọc hỏng (422) chỉ ghi dòng sổ.

Nhật ký không bao giờ có chữ của văn bản: chỉ số trang, số ký tự, tên các trường tìm thấy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, TypeVar
from zoneinfo import ZoneInfo

from ..auth import Principal
from ..config import Settings
from ..hasura import HasuraAuthError, HasuraError, Location, StoredFile
from ..storage import ObjectMissing, StorageError
from . import layout, rules
from .ocr import SERVER_NOTES, run_ocr
from .pdflayout import extract_layout
from .store import SuggestionStore
from .summarize import Summarizer

log = logging.getLogger("svc_files")
VN = ZoneInfo("Asia/Ho_Chi_Minh")
T = TypeVar("T")

FIELD_KEYS = ("type_code", "symbol", "issued_on", "issuer_name", "summary", "urgency")
FOUND_ORDER = ("symbol", "issued_on", "issuer_name", "type_code", "urgency", "summary")   # cột `found` của sổ
WARNINGS = frozenset({
    "future_date", "invalid_date", "symbol_no_number", "type_conflict", "low_text", "truncated",
    "model_unavailable", "model_timeout", "model_rejected", "model_skipped",
})
URGENCY = frozenset({"normal", "khan", "thuong_khan", "hoa_toc"})
CONFIDENCE = frozenset({"high", "medium", "low"})
SOURCES = frozenset({"rule", "model"})
MAX_VALUE = 500          # trích yếu tối đa 500 ký tự (schemas/van-ban-den.json)
MAX_PAGES_COLUMN = 200   # ràng buộc cột pages của office.intake_suggestions
MIN_TEXT = 40            # ký tự không trắng ở trang 1 để coi là PDF có lớp chữ (ít hơn: bản scan, OCR)
TEXT_TIMEOUT_S = 20.0    # hạn đọc lớp chữ
TEXT_MEMORY_MB = 1024    # như pdftext.py
MODEL_MIN_S = 5.0        # còn ít hơn thế trong hạn tổng thì không hỏi mô hình
MODEL_MARGIN_S = 2.0
SAVE_RESERVE_S = 3.0     # để dành cho bước ghi CSDL cuối yêu cầu
RETRY_AFTER = "10"
RESTRICTED = "Văn bản hạn chế không đọc tự động — nhập tay"
NOT_FOUND = "Không có tệp này, hoặc không phải tệp bạn vừa tải lên"

# byte đầu → loại tệp (không tin mime khai lúc tải lên)
MAGIC = (
    (b"%PDF-", "pdf"),
    (b"\xff\xd8\xff", "image"),          # JPEG
    (b"\x89PNG", "image"),               # PNG (89 50 4E 47)
    (b"II*\x00", "image"),               # TIFF little-endian
    (b"MM\x00*", "image"),               # TIFF big-endian
)

UNREADABLE = {
    "password": "Tệp PDF đặt mật khẩu nên không đọc được — nhập tay",
    "corrupt": "Tệp hỏng hoặc sai định dạng nên không đọc được — nhập tay",
    "no_text": "Tệp không có lớp chữ, cũng không có ảnh để nhận dạng — nhập tay",
    "timeout": "Đọc tệp quá lâu nên đã dừng — nhập tay hoặc thử lại",
    "memory": "Tệp cần quá nhiều bộ nhớ để đọc — nhập tay",
    "too_many_pixels": "Ảnh quá lớn (quá nhiều điểm ảnh) — chụp lại nhỏ hơn hoặc nhập tay",
}


class ReadError(Exception):
    """Lỗi trả cho người gọi: HTTP status, mã cố định, thông điệp tiếng Việt (api.py dựng thân lỗi)."""

    def __init__(self, status: int, code: str, message: str, *, reason: str | None = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.reason = reason
        self.headers = headers


class _Unreadable(Exception):
    def __init__(self, reason: str, method: str, pages: int) -> None:
        super().__init__(reason)
        self.reason = reason if reason in UNREADABLE else "corrupt"
        self.method = method
        self.pages = pages


class _TooLarge(Exception):
    pass


@dataclass(frozen=True)
class _Text:
    method: str                 # text · ocr
    pages: int
    lines: list[layout.Line]
    truncated: bool = False


class _Hasura(Protocol):
    async def visible_file(self, token: str, file_id: uuid.UUID) -> StoredFile | None: ...
    async def file_location(self, *, tenant_id: uuid.UUID, actor_id: str, request_id: str,
                            file_id: uuid.UUID) -> Location | None: ...
    async def as_role(self, role: str, tenant_id: uuid.UUID, user_id: str, request_id: str, query: str,
                      variables: dict[str, Any]) -> dict[str, Any]: ...
    async def admin(self, query: str, variables: dict[str, Any], headers: dict[str, str] | None = None,
                    ) -> dict[str, Any]: ...


class _Objects(Protocol):
    def read_stream(self, key: str, chunk_size: int = ...) -> Any: ...


Suggest = Callable[..., rules.Suggestion]
Lines = Callable[[Sequence[str]], list[layout.Line]]


def sniff(data: bytes) -> str | None:
    for magic, kind in MAGIC:
        if data.startswith(magic):
            return kind
    return None


def clean_fields(raw: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Trường của quy tắc → JSON lưu và trả: chỉ khóa đã biết, giá trị một dòng không ký tự điều khiển, đúng miền."""
    out: dict[str, dict[str, str]] = {}
    for key in FIELD_KEYS:
        f = raw.get(key)
        value = getattr(f, "value", None)
        confidence, source = getattr(f, "confidence", None), getattr(f, "source", "rule")
        if not isinstance(value, str) or confidence not in CONFIDENCE or source not in SOURCES:
            continue
        value = "".join(ch for ch in unicodedata.normalize("NFC", value)
                        if ch.isspace() or unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs", "Cn"))
        value = " ".join(value.split())[:MAX_VALUE].rstrip()
        if not value or (key == "urgency" and value not in URGENCY):
            continue
        if key == "issued_on":
            try:
                date.fromisoformat(value)
            except ValueError:
                continue
        out[key] = {"value": value, "confidence": confidence, "source": source}
    return out


def _ms(start: float) -> int:
    return max(int((time.monotonic() - start) * 1000), 0)


class Reader:
    def __init__(self, settings: Settings, hasura: _Hasura, store: _Objects, *, summarizer: Summarizer,
                 suggest: Suggest | None = None, text_lines: Lines | None = None, tsv_lines: Lines | None = None,
                 today: Callable[[], date] | None = None) -> None:
        self.settings = settings
        self.hasura = hasura
        self.objects = store
        self.summarizer = summarizer
        self.suggestions = SuggestionStore(hasura, settings.agent_id)
        # quy tắc thuần (luồng C) tiêm được: test API không phụ thuộc quy tắc
        self.suggest: Suggest = suggest or rules.suggest
        self.text_lines: Lines = text_lines or layout.text_lines
        self.tsv_lines: Lines = tsv_lines or layout.tsv_lines
        self.today = today or (lambda: datetime.now(VN).date())
        self.slots = asyncio.Semaphore(settings.read_concurrency)

    # --- luồng chính -----------------------------------------------------------------------------------------

    async def read(self, principal: Principal, file_id: uuid.UUID, force: bool, request_id: str) -> dict[str, Any]:
        start = time.monotonic()
        try:
            return await self._read(principal, file_id, force, request_id, start)
        except ReadError as exc:
            self._log("office.intake.read_failed", request_id, file_id=file_id, reason=exc.reason or exc.code,
                      duration_ms=_ms(start))
            raise

    async def _read(self, principal: Principal, file_id: uuid.UUID, force: bool, request_id: str,
                    start: float) -> dict[str, Any]:
        if not self.settings.read_enabled:
            raise ReadError(503, "reader_disabled", "Chức năng đọc văn bản đến đang tắt — nhập tay")
        if "clerk" not in principal.roles:
            raise ReadError(403, "forbidden", "Chỉ văn thư dùng chức năng đọc văn bản đến")
        meta = await self._visible(principal, file_id)
        if meta.encrypted:
            raise ReadError(409, "restricted", RESTRICTED)
        # Hạn chế theo văn bản, không chỉ theo tệp: tệp rõ gắn vào văn bản hạn chế cũng dừng ở đây — trước cả gợi ý
        # đã lưu (văn bản có thể bị đánh dấu hạn chế sau lần đọc trước), trước khi mở kho
        loc = await self._db(self.hasura.file_location(tenant_id=principal.tenant_id, actor_id=principal.user_id,
                                                       request_id=request_id, file_id=file_id))
        if loc is None:
            raise ReadError(404, "not_found", NOT_FOUND)
        if loc.wrapped_dek is not None or loc.restricted:
            raise ReadError(409, "restricted", RESTRICTED)
        if not force:
            row = await self._db(self.suggestions.cached(principal.tenant_id, file_id, request_id))
            if row is not None:
                self._log("office.intake.read", request_id, file_id=file_id, tenant_id=principal.tenant_id,
                          actor_id=principal.user_id, method=row["method"], pages=row["pages"], chars=None,
                          found=",".join(k for k in FOUND_ORDER if k in (row["fields"] or {})),
                          duration_ms=_ms(start), model=row["model"], cached=True)
                return self._out(row, cached=True)
        if meta.size_bytes > self.settings.read_max_bytes:
            raise self._too_large()
        try:
            await asyncio.wait_for(self.slots.acquire(), self.settings.read_queue_s)
        except TimeoutError:
            raise ReadError(503, "busy", "Đang đọc văn bản khác, thử lại sau ít giây",
                            headers={"Retry-After": RETRY_AFTER}) from None
        try:
            return await self._read_file(principal, meta, loc, request_id, start)
        finally:
            self.slots.release()

    async def _read_file(self, principal: Principal, meta: StoredFile, loc: Location, request_id: str,
                         start: float) -> dict[str, Any]:
        deadline = start + self.settings.read_deadline_s
        tenant, file_id = principal.tenant_id, meta.id
        data = await self._bytes(loc.object_key)
        kind = sniff(data)
        if kind is None:
            raise ReadError(415, "unsupported", "Chỉ đọc được tệp PDF và ảnh JPEG, PNG, TIFF — nhập tay")

        try:
            text = await self._text(kind, data, deadline)
        except _Unreadable as exc:
            diff = self._diff(principal, file_id, status="unreadable", method=exc.method, pages=exc.pages,
                              fields={}, summary_source="none", model=None, duration_ms=_ms(start), reason=exc.reason)
            await self._db(self.suggestions.log(tenant, request_id, file_id, diff),
                           "Chưa ghi được sổ kiểm toán — thử lại sau")
            raise ReadError(422, "unreadable", UNREADABLE[exc.reason], reason=exc.reason) from None
        del data

        suggestion = await self._suggest(text.lines, request_id, file_id)
        fields = clean_fields(suggestion.fields)
        if text.method == "ocr":
            # chữ nhận dạng từ ảnh: một ký tự sai, thừa (vết mộc, nét gạch) vẫn ra số ký hiệu hợp lệ — đo trên
            # bản scan mẫu đã có ca "high" sai. Không trường nào từ OCR được "high": vẫn điền, nhãn "chưa chắc"
            fields = {k: {**f, "confidence": "medium"} if f["confidence"] == "high" else f for k, f in fields.items()}
        warnings = [w for w in dict.fromkeys(suggestion.warnings) if w in WARNINGS]
        if text.truncated and "truncated" not in warnings:
            warnings.append("truncated")
        body = suggestion.body or "\n".join(line.text for line in text.lines)
        model, warning = await self._summary(fields, body, deadline)
        if warning and warning not in warnings:
            warnings.append(warning)

        summary_source = fields["summary"]["source"] if "summary" in fields else "none"
        duration_ms = _ms(start)
        row = {
            "file_id": str(file_id), "requested_by": principal.user_id, "status": "ok" if fields else "empty",
            "method": text.method, "pages": text.pages, "fields": fields, "warnings": warnings,
            "summary_source": summary_source, "model": model, "duration_ms": duration_ms,
        }
        diff = self._diff(principal, file_id, status=row["status"], method=text.method, pages=text.pages,
                          fields=fields, summary_source=summary_source, model=model, duration_ms=duration_ms)
        try:
            read_at = await self.suggestions.save(tenant, request_id, row, diff)
        except HasuraError as exc:
            if "intake_suggestions_sealed" in str(exc):     # trigger CSDL: tệp vừa gắn vào văn bản hạn chế
                raise ReadError(409, "restricted", RESTRICTED) from exc
            raise ReadError(503, "database_unavailable",
                            "Chưa ghi được sổ kiểm toán nên chưa trả gợi ý — thử lại sau") from exc
        self._log("office.intake.read", request_id, file_id=file_id, tenant_id=tenant, actor_id=principal.user_id,
                  method=text.method, pages=text.pages, chars=sum(len(line.text) for line in text.lines),
                  found=diff["found"], duration_ms=duration_ms, model=model, cached=False)
        return self._out({**row, "read_at": read_at}, cached=False)

    # --- từng bước -------------------------------------------------------------------------------------------

    async def _visible(self, principal: Principal, file_id: uuid.UUID) -> StoredFile:
        try:
            meta = await self.hasura.visible_file(principal.token, file_id)
        except HasuraAuthError as exc:
            raise ReadError(401, "invalid_token", "Token không hợp lệ hoặc đã hết hạn",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
        except HasuraError as exc:
            raise ReadError(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        # Chỉ tệp chính văn thư tải lên: tệp gắn vào văn bản họ đọc được mà người khác tải lên thì như không có
        if meta is None or meta.created_by != principal.user_id:
            raise ReadError(404, "not_found", NOT_FOUND)
        return meta

    async def _db(self, call: Awaitable[T], message: str = "CSDL chưa sẵn sàng") -> T:
        try:
            return await call
        except HasuraError as exc:
            raise ReadError(503, "database_unavailable", message) from exc

    def _too_large(self) -> ReadError:
        mb = self.settings.read_max_bytes // (1024 * 1024)
        return ReadError(413, "too_large", f"Tệp lớn hơn {mb} MB, không đọc tự động — nhập tay")

    async def _bytes(self, key: str) -> bytes:
        limit = self.settings.read_max_bytes

        def read() -> bytes:
            buf = bytearray()
            for chunk in self.objects.read_stream(key):
                buf += chunk
                if len(buf) > limit:
                    raise _TooLarge
            return bytes(buf)

        try:
            return await asyncio.to_thread(read)
        except _TooLarge:
            raise self._too_large() from None
        except ObjectMissing as exc:
            raise ReadError(404, "not_found", "Tệp không còn trong kho") from exc
        except StorageError as exc:
            raise ReadError(503, "storage_unavailable", "Kho lưu tệp chưa sẵn sàng") from exc

    def _left(self, deadline: float) -> float:
        return max(deadline - time.monotonic() - SAVE_RESERVE_S, 1.0)

    async def _text(self, kind: str, data: bytes, deadline: float) -> _Text:
        s = self.settings
        pages = 1
        layer: _Text | None = None      # lớp chữ PDF có mà ít: dùng khi OCR không giúp được
        if kind == "pdf":
            got = await extract_layout(data, max_pages=s.read_text_pages, timeout_s=min(TEXT_TIMEOUT_S,
                                       self._left(deadline)), memory_mb=TEXT_MEMORY_MB)
            if got.status == "failed":
                raise _Unreadable(got.note or "corrupt", "text", 0)
            pages = min(got.pages if got.pages is not None else len(got.texts), MAX_PAGES_COLUMN)
            first = got.texts[0] if got.texts else ""
            if sum(not ch.isspace() for ch in first) >= MIN_TEXT:
                return _Text("text", pages, self.text_lines(list(got.texts)), got.truncated)
            if any(not ch.isspace() for page in got.texts for ch in page):
                layer = _Text("text", pages, self.text_lines(list(got.texts)), got.truncated)
        # Bản scan, ảnh chụp: OCR. PDF trang 1 ít chữ (chỉ dòng đầu, số trang…) mà không có ảnh nhúng nào, hay máy chủ
        # chưa OCR được, thì dùng lớp chữ ít ỏi đó — vẫn có gợi ý (quy tắc tự cảnh báo low_text) thay vì lỗi
        if not shutil.which(s.tesseract_bin):
            if layer is not None:
                return layer
            raise ReadError(503, "ocr_unavailable", "Máy chủ chưa có bộ nhận dạng chữ (tesseract) — nhập tay")
        got_ocr = await run_ocr(data, kind, binary=s.tesseract_bin, lang=s.ocr_lang, max_pages=s.ocr_max_pages,
                                max_pixels=s.ocr_max_pixels, timeout_s=min(s.ocr_timeout_s, self._left(deadline)),
                                memory_mb=s.ocr_memory_mb)
        if got_ocr.status == "failed":
            if layer is not None and (got_ocr.note == "no_text" or got_ocr.note in SERVER_NOTES):
                return layer
            if got_ocr.note in SERVER_NOTES:
                raise ReadError(503, "ocr_unavailable", "Bộ nhận dạng chữ (tesseract) chưa chạy được trên máy chủ")
            raise _Unreadable(got_ocr.note or "corrupt", "ocr", pages)
        if kind != "pdf":
            pages = 1
        return _Text("ocr", pages, self.tsv_lines(list(got_ocr.tsv)))

    async def _suggest(self, lines: list[layout.Line], request_id: str, file_id: uuid.UUID) -> rules.Suggestion:
        codes: Collection[str] | None = await self.suggestions.type_codes()
        today = self.today()
        try:
            # quy tắc thuần, regex tuyến tính trên ≤ 20 000 ký tự — vẫn chạy ngoài vòng sự kiện
            return await asyncio.to_thread(lambda: self.suggest(lines, today=today, type_codes=codes))
        except Exception as exc:  # noqa: BLE001 — lỗi quy tắc thì coi như không tìm được gì, văn thư nhập tay
            # chỉ tên lỗi: thông điệp lỗi có thể chứa chữ của văn bản
            self._log("office.intake.rules_failed", request_id, file_id=file_id, error=type(exc).__name__)
            return rules.Suggestion({}, (), "")

    async def _summary(self, fields: dict[str, dict[str, str]], body: str, deadline: float,
                       ) -> tuple[str | None, str | None]:
        """Trích yếu bằng mô hình khi cần; trả (tên mô hình đã gọi, cảnh báo). Thành công thì ghi đè ``summary``."""
        rule = fields.get("summary")
        if self.settings.ai_summary != "always" and rule is not None and rule["confidence"] == "high":
            return None, None
        model = self.summarizer
        if not model.available:
            return None, "model_unavailable"
        left = deadline - time.monotonic()
        if left < MODEL_MIN_S or not body.strip():
            return None, "model_skipped"
        result = await model.summarize(body, timeout_s=min(self.settings.ai_timeout_s, left - MODEL_MARGIN_S))
        if result.text:
            fields["summary"] = {"value": result.text[:MAX_VALUE], "confidence": "medium", "source": "model"}
            return model.model, None
        return model.model, result.warning or "model_rejected"

    # --- dữ liệu ra ------------------------------------------------------------------------------------------

    def _diff(self, principal: Principal, file_id: uuid.UUID, *, status: str, method: str, pages: int,
              fields: dict[str, Any], summary_source: str, model: str | None, duration_ms: int,
              reason: str | None = None) -> dict[str, Any]:
        """Diff của dòng sổ ``intake.suggested``: chỉ giá trị vô hướng (giao diện hiểu mảng là [cũ, mới]), không có
        giá trị của trường nào — số ký hiệu, trích yếu, chữ OCR không vào sổ."""
        return {
            "user_id": principal.user_id, "file_id": str(file_id), "status": status, "method": method,
            "pages": pages, "found": ",".join(k for k in FOUND_ORDER if k in fields),
            "summary_source": summary_source, "model": model, "duration_ms": duration_ms, "reason": reason,
        }

    @staticmethod
    def _out(row: dict[str, Any], *, cached: bool) -> dict[str, Any]:
        return {
            "file_id": str(row["file_id"]), "status": row["status"], "method": row["method"], "pages": row["pages"],
            "fields": row.get("fields") or {}, "warnings": row.get("warnings") or [],
            "summary_source": row["summary_source"], "model": row.get("model"), "duration_ms": row["duration_ms"],
            "cached": cached, "read_at": row["read_at"],
        }

    @staticmethod
    def _log(event: str, request_id: str, **fields: object) -> None:
        log.info(json.dumps({"event": event, "request_id": request_id, **fields}, ensure_ascii=False, default=str))
