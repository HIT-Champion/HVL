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

"""Route nội bộ ``POST /internal/similar-documents`` — văn bản đến tương tự đã giao, cho tác tử gợi ý giao việc (F4.3).

svc-workflow (tác tử ``moc-assigner``) gọi bằng token tài khoản dịch vụ, như ``/internal/issue``: không có route
APISIX, không có trong OpenAPI công khai. svc-files **chỉ truy xuất** — bỏ phiếu chọn đơn vị, đề xuất hạn, lưu gợi ý,
ghi sổ là việc của svc-workflow. Theo đúng thứ tự, bước nào chặn được thì chặn trước khi tốn thêm:

1. ``MOC_ASK_ENABLED`` (chỉ mục đoạn chỉ chạy khi bật trợ lý) → 503 ``assistant_disabled``.
2. Văn bản đích đọc bằng vai trò service của đúng thuê ước trong yêu cầu: không có → 404; văn bản đi → 409
   ``not_incoming``; văn bản hạn chế → 409 ``restricted`` — **không tìm gì thêm**, không gọi Meilisearch, mô hình.
3. Câu tìm **chỉ lấy từ trích yếu** (``subject_text``): bỏ một tiền tố khuôn mẫu ("Về việc", "V/v", tên loại…), bỏ
   chữ "việc", rồi ``vi.keyword_query`` (≤ 10 term). Không dùng nội dung tệp: Meilisearch chỉ xét 10 từ đầu, mà đầu
   công văn toàn khuôn mẫu ("Căn cứ…", "Kính gửi…").
4. Có mô hình nhúng (và Meilisearch đã có embedder) thì nhúng trích yếu với chỉ dẫn riêng (``similar_text``), tối đa
   3 giây; quá giờ, lỗi thì chỉ tìm theo từ khóa.
5. Truy xuất bằng ``Retriever.similar`` của trợ lý F4.2 trong phạm vi dịch vụ: văn bản đến đã giao (đang xử lý, đã
   xong, đã lưu), trừ chính nó; hậu kiểm bằng vai trò service, bỏ văn bản hạn chế (retrieve.py). Chiều, trạng thái
   kiểm lại trên bản mới nhất từ Hasura: chỉ mục chậm vài giây sau khi đổi trạng thái cũng không lọt văn bản khác.

Trả id và điểm, **không trả chữ văn bản**. Nhật ký ``office.assist.similar`` không có trích yếu, không có câu tìm:
chỉ số term, số văn bản, cờ tìm theo nghĩa, thời gian, lỗi.
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu của dependency khai báo trong install().
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Protocol

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..hasura import HasuraError
from ..search import SearchError
from . import vi
from .answer import Assistant
from .scope import service_scope

log = logging.getLogger("svc_files")

DEFAULT_LIMIT = 15
MAX_LIMIT = 30
EMBED_TIMEOUT_S = 3.0           # nhúng trích yếu; quá thì chỉ tìm theo từ khóa
SCORE_DIGITS = 4
# văn bản đến đã có người nhận xử lý: lịch sử giao việc của chúng là căn cứ bỏ phiếu
STATUSES = ("in_progress", "done", "archived")
# tiền tố khuôn mẫu đầu trích yếu, bỏ một lần, không phân biệt hoa thường ("V/v:" là "V/v" kèm dấu hai chấm)
SUBJECT_PREFIXES = ("về việc", "v/v", "thông báo", "kế hoạch", "giấy mời", "quyết định", "công văn", "tờ trình")
# token không mang nghĩa trong trích yếu ("Về việc …", "… công việc …"); STOPWORDS của vi.py không có "việc" vì câu
# hỏi của F4.2 cần nó — bỏ riêng ở đây, không sửa vi.py
SUBJECT_STOPWORDS = frozenset({"việc"})
# Qwen3-Embedding cần chỉ dẫn ở phía câu tìm (như ai.QUERY_PREFIX của F4.2, nhưng tìm văn bản cùng việc, không tìm
# đoạn trả lời câu hỏi)
SIMILAR_PREFIX = ("Instruct: Given the subject line of a Vietnamese incoming official letter, retrieve earlier "
                  "letters about the same matter\nQuery: ")

_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in SUBJECT_PREFIXES) + r")(?![^\W_])\s*:?\s*", re.IGNORECASE)
_STOPWORD_RE = re.compile(
    r"(?<![^\W_])(?:" + "|".join(re.escape(w) for w in sorted(SUBJECT_STOPWORDS)) + r")(?![^\W_])", re.IGNORECASE)


class SimilarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: uuid.UUID
    document_id: uuid.UUID
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class SimilarHit(BaseModel):
    document_id: uuid.UUID
    score: float                # _rankingScore của Meilisearch (cao nhất trong các đoạn của văn bản), 4 chữ số


class SimilarOut(BaseModel):
    document_id: uuid.UUID
    hits: list[SimilarHit]      # ≤ limit, điểm giảm dần, đã hậu kiểm
    terms: int                  # số term của câu tìm — không gửi chữ
    semantic: bool              # lượt này có tìm theo nghĩa
    duration_ms: int


class _Target(Protocol):
    async def similar_target(self, tenant_id: uuid.UUID, document_id: uuid.UUID, *,
                             request_id: str = "") -> dict[str, Any] | None: ...


def subject_text(summary: str) -> str:
    """Trích yếu → chữ để tìm: NFC, gộp khoảng trắng, bỏ **một** tiền tố khuôn mẫu ở đầu, bỏ token "việc"."""
    s = _PREFIX_RE.sub("", vi.normalize(summary), count=1)
    return " ".join(_STOPWORD_RE.sub(" ", s).split())


def similar_text(model: str | None, subject: str) -> str:
    """Chữ đưa đi nhúng: Qwen3-Embedding cần tiền tố chỉ dẫn; mô hình khác (bge-m3) thì không."""
    if model and model.lower().startswith("qwen3-embedding"):
        return SIMILAR_PREFIX + subject
    return subject


def _ms(start: float) -> int:
    return max(int((time.monotonic() - start) * 1000), 0)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


async def find(assistant: Assistant, tenant_id: uuid.UUID, document_id: uuid.UUID, summary: str,
               limit: int) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    """(hits ``[{document_id, score}]``, số term, có tìm theo nghĩa, lỗi tìm lai) cho một văn bản đến đã kiểm.
    Lỗi Meilisearch (SearchError) và Hasura (HasuraError) đi thẳng lên."""
    subject = subject_text(summary)
    q = vi.keyword_query(subject)
    if not q:                   # trích yếu chỉ có khuôn mẫu, từ dừng: không có gì để tìm
        return [], 0, False, None
    terms = len(q.split())      # mỗi term là một token TOKEN_RE, không chứa khoảng trắng

    ai, indexer = assistant.ai, assistant.indexer
    vector: list[float] | None = None
    # Meilisearch chưa có embedder thì tìm lai chắc chắn lỗi: không nhúng (như answer.py)
    if ai.embed_available and indexer.embedder_ready:
        indexer.hold(EMBED_TIMEOUT_S)      # vòng nhúng nền không mở lô mới trong lúc nhúng trích yếu
        got = await ai.embed([similar_text(ai.embed_model, subject)], query=False, timeout_s=EMBED_TIMEOUT_S)
        vector = (got or [None])[0]

    where = ('direction = "in"', f"status IN [{', '.join(json.dumps(s) for s in STATUSES)}]",
             f'document_id != "{uuid.UUID(str(document_id))}"')
    found = await assistant.retriever.similar(service_scope(tenant_id), q=q, vector=vector, limit=limit, where=where)
    hits = [{"document_id": h.document_id, "score": round(h.score, SCORE_DIGITS)} for h in found.hits
            if h.doc.get("direction") == "in" and h.doc.get("status") in STATUSES]
    return hits, terms, found.semantic, found.error


def install(app: FastAPI, assistant: Assistant | None, hasura: _Target,
            service_caller: Callable[..., str]) -> None:
    """Gắn route nội bộ vào app; ``service_caller``: dependency kiểm token tài khoản dịch vụ của app.py."""

    # API nội bộ: APISIX không có route tới đây; chỉ client trong MOC_SERVICE_CLIENTS (svc-workflow) gọi được.
    # 200 {document_id, hits, terms, semantic, duration_ms} · 404 not_found · 409 not_incoming | restricted ·
    # 503 assistant_disabled | search_unavailable | database_unavailable
    @app.post("/internal/similar-documents", response_model=SimilarOut, include_in_schema=False)
    async def similar_documents(
        body: SimilarIn,
        request: Request,
        caller: Annotated[str, Depends(service_caller)],
    ) -> SimilarOut:
        start = time.monotonic()
        rid = request.state.request_id

        def note(**fields: object) -> None:
            # không bao giờ có trích yếu, câu tìm: chỉ id, số đếm, cờ, mã lỗi
            log.info(json.dumps({"event": "office.assist.similar", "request_id": rid, "tenant_id": body.tenant_id,
                                 "document_id": body.document_id, "caller": caller, "duration_ms": _ms(start),
                                 **fields}, ensure_ascii=False, default=str))

        def fail(status: int, code: str, message: str, error: str | None = None) -> HTTPException:
            note(code=code, error=error)
            return _error(status, code, message)

        if assistant is None or not assistant.settings.ask_enabled:
            raise fail(503, "assistant_disabled", "Trợ lý hỏi đáp đang tắt — không có chỉ mục để tìm văn bản tương tự")
        try:
            target = await hasura.similar_target(body.tenant_id, body.document_id, request_id=rid)
        except HasuraError as exc:
            raise fail(503, "database_unavailable", "CSDL chưa sẵn sàng", str(exc)) from exc
        if target is None:
            raise fail(404, "not_found", "Không có văn bản này trong đơn vị")
        if target.get("direction") != "in":
            raise fail(409, "not_incoming", "Chỉ tìm văn bản tương tự cho văn bản đến")
        if target.get("restricted"):
            raise fail(409, "restricted", "Văn bản hạn chế không dùng tác tử gợi ý")

        try:
            hits, terms, semantic, error = await find(assistant, body.tenant_id, body.document_id,
                                                      target.get("summary") or "", body.limit)
        except HasuraError as exc:
            raise fail(503, "database_unavailable", "CSDL chưa sẵn sàng", str(exc)) from exc
        except SearchError as exc:
            raise fail(503, "search_unavailable", "Dịch vụ tìm kiếm chưa sẵn sàng — thử lại sau", str(exc)) from exc
        duration_ms = _ms(start)
        note(hits=len(hits), terms=terms, semantic=semantic, error=error, duration_ms=duration_ms)
        return SimilarOut(document_id=body.document_id, hits=[SimilarHit.model_validate(h) for h in hits],
                          terms=terms, semantic=semantic, duration_ms=duration_ms)
