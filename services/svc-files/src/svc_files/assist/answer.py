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

"""Trợ lý ``moc-assistant`` trả lời câu hỏi trên kho văn bản (F4.2) — ``Assistant.ask``.

Theo đúng thứ tự, mỗi bước chặn được thì chặn trước khi tốn thêm:

1. ``MOC_ASK_ENABLED``; vai trò người hỏi (clerk, staff, manager, director) → phạm vi lọc trước (scope.py), vai trò
   khác 403.
2. Câu hỏi chuẩn hóa: rỗng, quá 500 ký tự, có ký tự điều khiển, chỉ toàn từ dừng → 400.
3. ``generate``: chờ lượt (``MOC_ASK_CONCURRENCY``, tối đa ``MOC_ASK_QUEUE_S``, quá thì 503 busy).
4. Có mô hình nhúng thì nhúng câu hỏi (≤ 5 giây; lỗi → chỉ tìm theo từ khóa).
5. Truy xuất: Meilisearch lọc trước theo vai trò, Hasura hậu kiểm **bằng token người hỏi** (retrieve.py). Tìm lai lỗi
   thì retrieve.py đã tìm lại chỉ bằng từ khóa: cảnh báo ``embed_unavailable``. Có ``document_id`` ("Hỏi về văn bản
   này") thì thêm một điều kiện lọc, chỉ thu hẹp; câu hỏi có số ký hiệu, ngày, cụm trong ngoặc kép thì tìm lai nghiêng
   về từ khóa (``retrieve.semantic_ratio``).
6. Câu trích nguyên văn (extract.py) — luôn chạy, tất định.
7. ``generate`` + có đoạn + mô hình sẵn sàng + còn ≥ 5 giây → mô hình viết câu trả lời từ đúng các đoạn đã hậu kiểm;
   máy chủ kiểm và tự gán trích dẫn [n] theo bằng chứng (grounding.py). Không đạt thì vẫn 200 với câu trích và cảnh báo.
8. Ghi **một** dòng ``assistant.answered`` vào sổ kiểm toán bằng vai trò ``agent`` **rồi mới trả lời** — không ghi được
   sổ thì 503, không trả gì.

Không có đoạn nào → ``no_evidence``, không gọi mô hình; giống hệt dù văn bản không tồn tại hay người hỏi không được
đọc.

Bộ định tuyến (route.py, #423) chọn đường sau bước 2, trước khi tốn gì thêm: ``gioi_thieu`` trả mục của tệp Giới thiệu
trợ lý, ``ngoai_pham_vi`` trả câu cố định — cả hai không tìm, không gọi mô hình, cả ở ``generate``; ``huong_dan`` tìm
trong kho hướng dẫn sử dụng (guide.py) thay cho bước 4–5, rồi câu trích và mô hình như văn bản — kho không có mục nào
khớp thì đi như ``van_ban`` (mã lý do ``khong-khop-huong-dan``); ``van_ban`` như trên.
Câu nối tiếp (có ``previous``) được ghép thành câu độc lập trước khi chọn đường; câu ghép thay câu hỏi ở mọi bước sau
và trả về ở ``rewritten``. Sổ kiểm toán, nhật ký ghi đường và mã lý do, không ghi câu ghép. Nhật ký không bao giờ
có câu hỏi, câu trả lời, đoạn trích: chỉ độ dài, số term, số đoạn, thời gian.

Che thông tin cá nhân (F4.4): mô hình chỉ đọc bản che. Mỗi lượt ``generate`` một ``pii.Masker``: câu hỏi che trước
(số trong câu hỏi nhận nhãn ``[SĐT-1]``), rồi các đoạn — cùng số thì cùng nhãn, mô hình vẫn biết "số này của ai". Tìm
kiếm, câu trích nguyên văn và nguồn trả người hỏi (người có quyền đọc văn bản) giữ số thật; câu trả lời của mô hình
giữ nhãn. Số chỗ đã che ghi ở khóa ``masked`` của nhật ký, không vào sổ.

Vòng nhúng nền chỉ bị giữ **trong lúc** lượt hỏi gọi Ollama (nhúng câu hỏi, sinh) — suốt lời gọi, lâu bao nhiêu cũng
vậy (#192) — và ``HOLD_S`` giây sau mỗi lời gọi, không phải mỗi lượt hỏi: câu trích không cần mô hình thì không giữ
gì. Người hỏi ngắt kết nối thì api.py hủy lượt (``CancelledError``): lời gọi Ollama bị ngắt, lượt sinh được nhả, thôi
giữ vòng nền; không trả lời nên không ghi sổ, chỉ có nhật ký ``office.assist.ask_cancelled``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, Protocol

from .. import pii
from ..auth import Principal
from ..hasura import HasuraAuthError, HasuraError
from ..search import SearchError
from . import extract, grounding, guide, route, vi
from .ai import AiClient
from .guide import GuideStore
from .retrieve import Filters, Passage, Retrieval, Retriever
from .scope import user_scope
from .store import AnswerLog

if TYPE_CHECKING:
    from ..config import Settings

log = logging.getLogger("svc_files")

MAX_QUESTION = 500          # ký tự sau chuẩn hóa
EMBED_TIMEOUT_S = 5.0       # nhúng câu hỏi; quá thì tìm theo từ khóa
MODEL_MIN_S = 5.0           # còn ít hơn thế trong hạn tổng thì không hỏi mô hình
SAVE_RESERVE_S = 3.0        # để dành cho bước ghi sổ cuối yêu cầu
HOLD_S = 5.0                # lời gọi Ollama xong thì vòng nhúng nền còn nhường thêm chừng này giây (_holding)
RETRY_AFTER = "10"
WARNINGS = ("embed_unavailable", "model_unavailable", "model_timeout", "model_rejected", "model_declined")


class AskError(Exception):
    """Lỗi trả cho người gọi: HTTP status, mã cố định, thông điệp tiếng Việt (api.py dựng thân lỗi)."""

    def __init__(self, status: int, code: str, message: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers


class AskBody(Protocol):
    question: str
    mode: str                   # extract · generate
    direction: str | None
    year: int | None
    type_code: str | None
    document_id: uuid.UUID | None   # chỉ hỏi trong văn bản này — vẫn trong phạm vi người hỏi được xem
    ask_id: uuid.UUID | None
    previous: str | None            # câu hỏi lượt trước (câu nối tiếp), máy chủ không lưu


class _Hold(Protocol):
    embedder_ready: bool        # Meilisearch đã có embedder của mô hình nhúng hiện tại

    def holding(self, after_s: float = ...) -> AbstractContextManager[None]: ...


class _Hasura(Protocol):
    async def as_role(self, role: str, tenant_id: uuid.UUID, user_id: str, request_id: str, query: str,
                      variables: dict[str, Any]) -> dict[str, Any]: ...


def _type_name(doc: dict[str, Any]) -> str | None:
    return doc.get("type_name") or (doc.get("document_type") or {}).get("name")


def source_of(n: int, passage: Passage, best: dict[str, tuple[int, int]], cited: set[int]) -> dict[str, Any]:
    """Một nguồn trả cho người dùng: dữ liệu văn bản lấy từ Hasura (bản mới nhất), không từ chỉ mục."""
    doc = passage.doc
    return {
        "n": n, "document_id": passage.document_id, "symbol": doc.get("symbol"), "type_code": doc.get("type_code"),
        "type_name": _type_name(doc), "summary": doc.get("summary") or "", "issuer_name": doc.get("issuer_name"),
        "issued_on": doc.get("issued_on"), "direction": doc.get("direction"), "status": doc.get("status"),
        "kind": passage.kind, "file_id": passage.file_id, "file_role": passage.file_role, "page": passage.page,
        "excerpt": extract.excerpt(passage.text, best.get(passage.chunk_id)), "cited": n in cited,
    }


def _previous(text: str | None) -> str | None:
    """Câu hỏi lượt trước đã chuẩn hóa; sai dạng (rỗng, dài, có ký tự điều khiển) thì bỏ qua, không thành lỗi."""
    if not text or vi.has_control(text):
        return None
    out = vi.normalize(text)
    return out if out and len(out) <= MAX_QUESTION else None


class Assistant:
    def __init__(self, settings: Settings, *, retriever: Retriever, ai: AiClient, indexer: _Hold, hasura: _Hasura,
                 guides: GuideStore | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.settings = settings
        self.retriever = retriever
        self.guides = guides if guides is not None else GuideStore.load(settings.ask_guide_dir)
        self.ai = ai
        self.indexer = indexer
        self.answers = AnswerLog(hasura, settings.assistant_id)
        self.slots = asyncio.Semaphore(settings.ask_concurrency)
        self._clock = clock

    def _ms(self, start: float) -> int:
        return max(int((self._clock() - start) * 1000), 0)

    async def ask(self, principal: Principal, body: AskBody, request_id: str) -> dict[str, Any]:
        start = self._clock()
        try:
            return await self._ask(principal, body, request_id, start)
        except AskError as exc:
            _log("office.assist.ask_failed", request_id, tenant_id=principal.tenant_id, actor_id=principal.user_id,
                 mode=body.mode, code=exc.code, duration_ms=self._ms(start))
            raise
        except asyncio.CancelledError:
            # người hỏi đã đi (api.py hủy lượt): không trả lời nên không ghi sổ. Hủy đúng lúc đang ghi thì dòng sổ có
            # thể đã vào — sổ có thể nhiều hơn những gì đã trả, không bao giờ ít hơn
            _log("office.assist.ask_cancelled", request_id, tenant_id=principal.tenant_id,
                 actor_id=principal.user_id, mode=body.mode, duration_ms=self._ms(start))
            raise

    async def _ask(self, principal: Principal, body: AskBody, request_id: str, start: float) -> dict[str, Any]:
        s = self.settings
        if not s.ask_enabled:
            raise AskError(503, "assistant_disabled", "Trợ lý hỏi đáp đang tắt — dùng Tìm kiếm")
        scope = user_scope(role=principal.role, user_id=principal.user_id, tenant_id=principal.tenant_id,
                           department_id=principal.department_id, token=principal.token)
        if scope is None:
            raise AskError(403, "forbidden", "Trợ lý hỏi đáp dành cho văn thư, lãnh đạo, trưởng phòng và chuyên viên")
        question = vi.normalize(body.question)
        if vi.has_control(body.question) or not question or len(question) > MAX_QUESTION or not vi.terms(question):
            raise AskError(400, "invalid_question", "Câu hỏi trống, dài quá 500 ký tự, có ký tự điều khiển hoặc chưa "
                                                    "có từ nào để tìm — hãy hỏi cụ thể hơn")
        scoped = body.document_id is not None
        chosen = route.route(question, scoped=scoped)
        rewritten = None
        if chosen.name in ("van_ban", "huong_dan"):
            rewritten = route.follow_up(question, _previous(body.previous))
            if rewritten is not None and chosen.name == "van_ban":
                chosen = route.route(rewritten, scoped=scoped)
        if chosen.name == "huong_dan" and not self.guides.search(rewritten or question, s.ask_top_k):
            # hướng dẫn sử dụng không có mục nào khớp: có thể là câu về một văn bản, tìm như van_ban
            chosen = route.Route("van_ban", route.NO_GUIDE_REASON, chosen.lang)
        if body.mode != "generate" or chosen.name in ("gioi_thieu", "ngoai_pham_vi"):
            return await self._answer(principal, body, question, rewritten, chosen, scope, request_id, start)
        try:
            await asyncio.wait_for(self.slots.acquire(), s.ask_queue_s)
        except TimeoutError:
            raise AskError(503, "busy", "Trợ lý đang soạn câu trả lời khác, thử lại sau ít giây",
                           headers={"Retry-After": RETRY_AFTER}) from None
        try:
            return await self._answer(principal, body, question, rewritten, chosen, scope, request_id, start)
        finally:
            self.slots.release()

    async def _answer(self, principal: Principal, body: AskBody, question: str, rewritten: str | None,
                      chosen: route.Route, scope: Any, request_id: str, start: float) -> dict[str, Any]:
        s = self.settings
        deadline = start + s.ask_deadline_s
        warnings: list[str] = []
        asked = rewritten or question               # câu đem đi tìm, trích, hỏi mô hình
        fixed: str | None = None                    # câu cố định của đường ngoai_pham_vi
        if chosen.name == "van_ban":
            found = await self._search(body, asked, scope, deadline, warnings, request_id)
        else:
            if chosen.name == "huong_dan":
                found_passages = self.guides.search(asked, s.ask_top_k)
            elif chosen.name == "gioi_thieu":
                found_passages = self.guides.intro(chosen.reason, chosen.lang)
            else:
                found_passages, fixed = [], self.guides.fixed(chosen.lang)
            found = Retrieval(found_passages, candidates=len(found_passages), semantic=False)
        passages = list(found.passages[: s.ask_top_k])

        if chosen.name == "gioi_thieu" and passages:
            # mục chính trả lời nguyên văn, không cần khớp từ với câu hỏi ("Xin chào"); không gọi mô hình
            first = guide.lead(passages[0])
            start_at = passages[0].text.find(first)
            quoted = extract.Extract(f"“{first}” [1]", [1], {passages[0].chunk_id: (start_at, start_at + len(first))})
        else:
            quoted = extract.answer(asked, passages)
        cited = list(quoted.cited)
        model_text: str | None = None
        model: str | None = None
        masked = 0                  # số chỗ đã che trong chữ gửi mô hình viết câu trả lời
        if body.mode == "generate" and passages and chosen.name in ("van_ban", "huong_dan"):
            model_text, model, warning, masked = await self._generate(asked, passages, quoted.best, deadline,
                                                                      request_id)
            if warning:
                warnings.append(warning)
            if model_text:
                cited = grounding.citations(model_text)

        if not passages:
            status = "no_evidence"
        elif quoted.text is None and model_text is None:
            status = "passages_only"
        else:
            status = "answered"
        extract_out = {"text": quoted.text, "source": "extract", "model": None} if quoted.text else None
        answer_out = {"text": model_text, "source": "model", "model": model} if model_text else extract_out
        if fixed is not None:
            answer_out = {"text": fixed, "source": "fixed", "model": None}
        answer_source = "model" if model_text else "extract" if quoted.text else "fixed" if fixed else "none"
        warnings = [w for w in dict.fromkeys(warnings) if w in WARNINGS]
        ask_id = str(body.ask_id or uuid.uuid4())
        embed_model = self.ai.embed_model if found.semantic else None
        duration_ms = self._ms(start)

        diff = {
            "user_id": principal.user_id, "ask_id": ask_id, "mode": body.mode, "status": status,
            "answer_source": answer_source, "hits": len(passages), "cited": len(cited),
            "documents": ",".join(dict.fromkeys(p.document_id for p in passages if p.kind != "guide")),
            "semantic": found.semantic, "model": model, "embed_model": embed_model, "duration_ms": duration_ms,
            "warnings": ",".join(warnings), "route": chosen.name, "route_reason": chosen.reason,
            "followup": rewritten is not None,
        }
        try:
            await self.answers.write(principal.tenant_id, request_id, ask_id, diff)
        except HasuraError as exc:
            _log("office.assist.audit_failed", request_id, error=str(exc), code=exc.code)
            raise AskError(503, "database_unavailable",
                           "Chưa ghi được sổ kiểm toán nên chưa trả lời — thử lại sau") from exc

        _log("office.assist.asked", request_id, tenant_id=principal.tenant_id, actor_id=principal.user_id,
             mode=body.mode, status=status, route=chosen.name, route_reason=chosen.reason,
             followup=rewritten is not None, q_length=len(question), terms=len(vi.terms(asked)),
             candidates=found.candidates, relaxed=found.relaxed, hits=len(passages), cited=len(cited),
             semantic=found.semantic, ratio=found.ratio, scoped=body.document_id is not None, model=model,
             warnings=",".join(warnings), masked=masked, duration_ms=duration_ms)
        cited_set = set(cited)
        return {
            "ask_id": ask_id, "status": status, "answer": answer_out, "extract": extract_out,
            "sources": [self._source(i + 1, p, quoted.best, cited_set) for i, p in enumerate(passages)],
            "semantic": found.semantic, "ai_available": self.ai.chat_available, "warnings": warnings,
            "duration_ms": duration_ms, "route": chosen.name, "route_reason": chosen.reason, "rewritten": rewritten,
        }

    @staticmethod
    def _source(n: int, p: Passage, best: dict[str, tuple[int, int]], cited: set[int]) -> dict[str, Any]:
        if p.kind == "guide":
            return guide.source(n, p, extract.excerpt(p.text, best.get(p.chunk_id)), n in cited)
        return source_of(n, p, best, cited)

    async def _search(self, body: AskBody, question: str, scope: Any, deadline: float, warnings: list[str],
                      request_id: str) -> Retrieval:
        """Bước 4–5 của đường ``van_ban``: nhúng câu hỏi, tìm lai trong kho văn bản, hậu kiểm bằng token người hỏi."""
        s = self.settings
        vector: list[float] | None = None
        if self.ai.embed_available and not self.indexer.embedder_ready:
            warnings.append("embed_unavailable")    # Meilisearch chưa có embedder: tìm lai chắc chắn lỗi, không nhúng
        elif self.ai.embed_available:
            left = deadline - self._clock()
            with self._holding():
                got = await self.ai.embed([question], query=True, timeout_s=max(min(EMBED_TIMEOUT_S, left), 0.1))
            if got:
                vector = got[0]
            else:
                warnings.append("embed_unavailable")

        try:
            found = await self.retriever.search(
                scope, q=vi.keyword_query(question), vector=vector, limit=s.ask_top_k, question=question,
                filters=Filters(direction=body.direction, year=body.year, type_code=body.type_code,
                                document_id=None if body.document_id is None else str(body.document_id)))
        except HasuraAuthError as exc:
            raise AskError(401, "invalid_token", "Token không hợp lệ hoặc đã hết hạn",
                           headers={"WWW-Authenticate": "Bearer"}) from exc
        except HasuraError as exc:
            _log("office.assist.search_failed", request_id, error=str(exc), code=exc.code)
            raise AskError(503, "database_unavailable", "CSDL chưa sẵn sàng") from exc
        except SearchError as exc:
            _log("office.assist.search_failed", request_id, error=str(exc))
            raise AskError(503, "search_unavailable", "Dịch vụ tìm kiếm chưa sẵn sàng — thử lại sau") from exc
        if found.hybrid_error:
            # vd embedder chưa có trong Meilisearch (đang khởi động, đang đổi mô hình): đã tìm lại chỉ bằng từ khóa
            _log("office.assist.search_failed", request_id, error=found.hybrid_error, fallback="keywords")
            warnings.append("embed_unavailable")
        return found

    async def _generate(self, question: str, passages: list[Passage], best: dict[str, tuple[int, int]],
                        deadline: float, request_id: str) -> tuple[str | None, str | None, str | None, int]:
        """(câu trả lời đã kiểm, mô hình đã gọi, cảnh báo, số chỗ đã che trong chữ gửi mô hình)."""
        if not self.ai.chat_available:
            return None, None, "model_unavailable", 0
        left = deadline - self._clock()
        if left < MODEL_MIN_S:
            return None, None, "model_timeout", 0
        # Một bộ che cho cả lượt: câu hỏi che trước để số trong câu hỏi nhận nhãn số 1. ``best`` vẫn tính trên chữ
        # gốc (câu trích nguyên văn), sources() đổi sang toạ độ bản che. Mô hình đọc và validate kiểm cùng một bản che
        masker = pii.Masker()
        asked = masker.mask(question).text
        srcs = grounding.sources(passages, best, max_chars=self.settings.ask_context_chars, masker=masker)
        with self._holding():
            result = await self.ai.chat(grounding.messages(srcs, asked), format=grounding.FORMAT,
                                        options=grounding.OPTIONS,
                                        timeout_s=min(self.settings.ask_model_timeout_s, left - SAVE_RESERVE_S))
        model = self.ai.chat_model
        if result.content is None:
            return None, model, result.warning or "model_unavailable", masker.total
        verdict = grounding.validate(result.content, srcs, asked)
        if verdict.text:
            return verdict.text, model, None, masker.total
        if verdict.declined:
            return None, model, "model_declined", masker.total
        # chỉ mã lý do: đầu ra của mô hình có thể chép chữ của văn bản
        _log("office.assist.model_rejected", request_id, model=model, reason=verdict.reason, masked=masker.total)
        return None, model, "model_rejected", masker.total

    def _holding(self) -> AbstractContextManager[None]:
        """Khối gọi Ollama của lượt hỏi: vòng nhúng nền không mở lô mới suốt khối, lời gọi lâu bao nhiêu cũng vậy
        (``ChunkIndexer.holding``, #192). Ra khỏi khối (kể cả khi lượt bị hủy) vòng nền còn nhường thêm ``HOLD_S``
        giây: nhúng câu hỏi xong còn bước truy xuất rồi mới sinh, mà lô đã mở thì không dừng giữa chừng được (tới 8
        đoạn, vài giây trên máy chỉ có CPU); người hỏi tiếp ngay cũng không phải chờ lô. Phần nhường thêm chịu trần
        ``index.MAX_HOLD_S`` (#184)."""
        return self.indexer.holding(HOLD_S)


def _log(event: str, request_id: str, **fields: object) -> None:
    log.info(json.dumps({"event": event, "request_id": request_id, **fields}, ensure_ascii=False, default=str))
