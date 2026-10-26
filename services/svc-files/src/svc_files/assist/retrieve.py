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

"""Truy xuất đoạn cho trợ lý hỏi đáp (F4.2): quyền ở hai lớp, cả hai đứng trước mô hình và trước người dùng.

1. **Lọc trước** trong Meilisearch: điều kiện thuê ước (từ token, luôn đứng đầu) + phạm vi theo vai trò (scope.py)
   + bộ lọc người dùng chọn. Lớp này quyết độ phủ.
2. **Hậu kiểm** bằng Hasura với **token người hỏi** (như tìm kiếm F2.7): đoạn của văn bản Hasura không trả về hoặc
   không còn đủ điều kiện vào chỉ mục (``chunks.eligible``: hạn chế, văn bản đến đã hủy, văn bản đi chưa phát hành)
   bị bỏ. Lớp này quyết an toàn: chỉ mục chậm vài giây sau khi bật hạn chế, hủy giao việc hay hủy văn bản cũng không
   lộ đoạn nào, kể cả tới mô hình. svc-files không viết lại quy tắc quyền.

Tìm lai (từ khóa + nghĩa) lỗi — embedder chưa có trong Meilisearch lúc khởi động hay khi đổi mô hình — thì tìm lại
một lần chỉ bằng từ khóa (``Retrieval.hybrid_error``), không trả lỗi cho người hỏi.

**Tỷ trọng nghĩa theo câu hỏi** (``semantic_ratio``): câu hỏi có số ký hiệu, ngày hay cụm trong ngoặc kép là người hỏi
cần đúng chữ đó — tìm lai dùng ``min(MOC_ASK_SEMANTIC_RATIO, KEYWORD_RATIO)``, câu khác giữ tỷ trọng cấu hình. Vì sao
0,2: xem ``KEYWORD_RATIO``.

**Hỏi trong một văn bản** (``Filters.document_id``, nút "Hỏi về văn bản này"): thêm điều kiện ``document_id = …`` sau
điều kiện thuê ước và phạm vi vai trò — các điều kiện nối bằng AND nên chỉ thu hẹp; hậu kiểm vẫn như mọi lượt.

**Tìm nới** (mỗi lần tìm theo từ khóa, không tìm theo nghĩa): chiến lược ``frequency`` của Meilisearch bỏ dần từ
phổ biến nhưng luôn giữ từ hiếm nhất của câu hỏi — câu "Điều kiện xét học bổng …" mà vài văn bản về xét tốt nghiệp có
chữ "điều kiện" thì lượt chính chỉ ra các văn bản đó, văn bản trả lời (không có chữ "điều kiện") không bao giờ ra. Lượt
nới tìm từng từ riêng trong cùng phạm vi (một ``/multi-search``), cho mỗi từ trọng số ``ln(1 + N / df)`` (``N`` số đoạn
trong phạm vi, ``df`` số đoạn có từ đó; từ không đoạn nào có tính như ``df`` = 0,5), thêm đoạn có tổng trọng số ≥
``RELAX_MIN`` của cả câu hỏi, hậu kiểm như mọi đoạn khác. Mỗi từ chỉ lấy ``candidates`` đoạn đầu, nên từ phổ biến
còn được tính cho đoạn nào có nguyên văn từ đó (bỏ dấu như Meilisearch). Trợ lý xếp chung đoạn lượt chính và đoạn nới
theo tỷ lệ trọng số đó; tìm văn bản tương tự (F4.3) lấy điểm cao hơn giữa ``_rankingScore`` và tỷ lệ, xem ``similar``.
Lượt nới lỗi thì giữ kết quả lượt chính.

Dữ liệu nguồn trả về (số ký hiệu, trích yếu, trạng thái…) lấy từ Hasura — bản mới nhất, không phải bản sao trong chỉ
mục. Không trả số kết quả của Meilisearch theo từng văn bản: con số đó tính cả văn bản người hỏi không được đọc.
"""

from __future__ import annotations

import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

from ..search import SearchError, _quoted
from ..vntext import DASHES, DATE, SYMBOL, fold
from .chunks import eligible
from .scope import NOTHING, Scope
from .vi import TOKEN_RE

FIELDS = ["id", "document_id", "kind", "file_id", "file_role", "page", "seq", "text"]
MORE_ROUNDS = 2            # thiếu đoạn mà Meilisearch còn kết quả: lấy thêm tối đa từng này lượt
RELAX_MIN = 0.5            # tìm nới: đoạn phải có từ chiếm ≥ tỷ lệ này trọng số của câu hỏi
WORD = re.compile(r"\w+")

# Tỷ trọng nghĩa tối đa khi câu hỏi cần đúng chữ. Meilisearch xếp chung hai danh sách theo điểm nhân trọng số: đoạn
# khớp từ khóa (điểm s_k, trọng số 1 − r) đứng trước đoạn chỉ gần nghĩa (độ tương đồng s_v, trọng số r) khi
# (1 − r)·s_k > r·s_v. Với r = 0,5 phải có s_k > s_v, mà văn bản cùng chủ đề khác số ký hiệu thường có s_v ≥ 0,8 nên
# đẩy văn bản có đúng số ký hiệu xuống; với r = 0,2 chỉ cần s_k > s_v / 4: mọi đoạn khớp từ khóa có điểm > 0,25 đứng
# trước cả đoạn gần nghĩa nhất (s_v = 1). Không về 0: người hỏi gõ khác chữ trong văn bản (5/3/2026 và 05/03/2026)
# thì đoạn gần nghĩa vẫn lấp chỗ sau các đoạn khớp từ khóa.
KEYWORD_RATIO = 0.2
# Ngày viết bằng số, có hay không có chữ "ngày" đứng trước: 15/11/2026, 5-3-2026, 5.3.2026. Ngày viết bằng chữ ("ngày
# 5 tháng 3 năm 2026") dùng vntext.DATE
NUM_DATE = re.compile(r"(?<![\w/.-])[0-9]{1,2}[/.-][0-9]{1,2}[/.-](?:19|20)[0-9]{2}(?![\w/.-])")
QUOTED = re.compile(r'["“][^"“”]*\w[^"“”]*["”]')     # cụm trong ngoặc kép thẳng hoặc cong, có ít nhất một chữ
SYMBOL_TAIL = re.compile(r"/\s*[^\W\d_]")              # số ký hiệu có phần chữ sau "/" (88/CTSV); 15/11 thì không

T = TypeVar("T")


def exact_cues(question: str) -> list[str]:
    """Dấu hiệu câu hỏi cần khớp đúng chữ, theo thứ tự ``symbol``, ``date``, ``quoted`` — chỉ tên dấu hiệu, không có
    chữ của câu hỏi.

    - ``symbol``: mẫu "Số 123/QĐ-…" của bộ đọc văn bản đến (``vntext.SYMBOL``, cả "Số 152a/TB-VP", "Số 12 /
      QĐ") trên chữ bỏ dấu; hoặc token số ký hiệu của ``vi.TOKEN_RE`` ("123/QĐ-ĐHCN", "45/TB-KCNTT", "88/CTSV"). Cả
      hai phải có chữ sau "/" (``SYMBOL_TAIL``): bỏ dấu thì "hồ sơ 15/11/2026" cũng có "so 15/11". Không dùng mẫu trần
      ``docread.rules.BARE``: nó đòi gạch nối và chữ hoa để khỏi nhầm trong thân văn bản, còn người hỏi hay gõ chữ
      thường, và có số ký hiệu không gạch nối (88/CTSV).
    - ``date``: ``NUM_DATE`` (15/11/2026) hoặc ``vntext.DATE`` ("ngày 5 tháng 3 năm 2026").
    - ``quoted``: cụm trong ngoặc kép ("…" hoặc “…”).
    """
    folded = DASHES.sub("-", fold(question))
    cues = []
    if (any(any(ch.isdigit() for ch in m.group("num")) and SYMBOL_TAIL.search(m.group("sym"))
            for m in SYMBOL.finditer(folded))
            or any(SYMBOL_TAIL.search(token) for token in TOKEN_RE.findall(question))):
        cues.append("symbol")
    if NUM_DATE.search(folded) or DATE.search(folded):
        cues.append("date")
    if QUOTED.search(question):
        cues.append("quoted")
    return cues


def semantic_ratio(question: str, base: float) -> float:
    """Tỷ trọng tìm theo nghĩa cho một câu hỏi: ``base`` (``MOC_ASK_SEMANTIC_RATIO``), trừ khi câu hỏi có dấu hiệu cần
    khớp đúng chữ (``exact_cues``) — khi đó ``min(base, KEYWORD_RATIO)``: không bao giờ tăng tỷ trọng đã cấu hình."""
    return min(base, KEYWORD_RATIO) if exact_cues(question) else base


@dataclass(frozen=True)
class Filters:
    direction: str | None = None
    year: int | None = None
    type_code: str | None = None
    document_id: str | None = None      # chỉ đoạn của một văn bản ("Hỏi về văn bản này"): chỉ thu hẹp phạm vi


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    document_id: str
    kind: Literal["page", "meta"]
    file_id: str | None
    file_role: Literal["main", "attachment", "issued"] | None
    page: int | None
    text: str
    score: float
    # bản mới nhất từ Hasura: id direction status type_code type_name symbol issuer_name issued_on summary
    doc: dict[str, Any]


@dataclass(frozen=True)
class Retrieval:
    passages: list[Passage]
    candidates: int         # số đoạn Meilisearch đã trả (trước hậu kiểm) — chỉ ghi nhật ký, không trả người dùng
    semantic: bool          # lượt này có tìm theo nghĩa
    hybrid_error: str | None = None     # tìm lai lỗi nên đã tìm lại chỉ bằng từ khóa — chỉ ghi nhật ký
    relaxed: int = 0        # số đoạn có được nhờ tìm nới — chỉ ghi nhật ký
    ratio: float | None = None          # tỷ trọng nghĩa đã dùng; None khi chỉ tìm từ khóa — chỉ ghi nhật ký


@dataclass(frozen=True)
class DocHit:
    """Một văn bản tương tự (F4.3): điểm = điểm cao nhất trong các đoạn của nó."""
    document_id: str
    score: float
    doc: dict[str, Any]


@dataclass(frozen=True)
class Similar:
    """Kết quả tìm văn bản tương tự (F4.3) — ``Retriever.similar``."""
    hits: list[DocHit]      # đã hậu kiểm, điểm giảm dần
    semantic: bool          # lượt này có tìm theo nghĩa
    error: str | None = None    # tìm lai lỗi nên đã tìm lại chỉ bằng từ khóa — chỉ ghi nhật ký


class _Index(Protocol):
    async def search(self, body: dict[str, Any]) -> list[dict[str, Any]]: ...
    async def multi_search(self, bodies: list[dict[str, Any]]) -> list[tuple[list[dict[str, Any]], int]]: ...


class _Hasura(Protocol):
    async def ask_documents(self, token: str, ids: list[str]) -> dict[str, dict[str, Any]]: ...
    async def ask_documents_service(self, tenant_id: Any, ids: list[str]) -> dict[str, dict[str, Any]]: ...


def filter_parts(filters: Filters) -> list[str]:
    parts = []
    if filters.direction is not None:
        parts.append(f"direction = {_quoted(filters.direction)}")
    if filters.year is not None:
        parts.append(f"year = {int(filters.year)}")
    if filters.type_code is not None:
        parts.append(f"type_code = {_quoted(filters.type_code)}")
    if filters.document_id is not None:
        parts.append(f"document_id = {_quoted(filters.document_id)}")
    return parts


def source_doc(row: dict[str, Any]) -> dict[str, Any]:
    """Dòng Hasura → dữ liệu nguồn trả về (``type_name`` từ ``document_type``, bỏ ``restricted``)."""
    return {
        "id": row["id"], "direction": row.get("direction"), "status": row.get("status"),
        "type_code": row.get("type_code"), "type_name": (row.get("document_type") or {}).get("name"),
        "symbol": row.get("symbol"), "issuer_name": row.get("issuer_name"), "issued_on": row.get("issued_on"),
        "summary": row.get("summary"),
    }


class Retriever:
    def __init__(self, index: _Index, hasura: _Hasura, *, embedder: str | None, candidates: int = 24,
                 per_doc: int = 2, min_score: float = 0.0, min_score_semantic: float = 0.75,
                 semantic_ratio: float = 0.5) -> None:
        self.index = index
        self.hasura = hasura
        self.embedder = embedder
        self.candidates = candidates
        self.per_doc = per_doc
        self.min_score = min_score
        self.min_score_semantic = min_score_semantic
        self.semantic_ratio = semantic_ratio

    def _body(self, scope: Scope, q: str, vector: list[float] | None, where: list[str],
              ratio: float | None = None) -> tuple[dict[str, Any], bool]:
        semantic = vector is not None and bool(self.embedder)
        body: dict[str, Any] = {
            "q": q,
            "filter": [f"tenant_id = {_quoted(str(scope.tenant_id))}", *scope.where, *where],
            "limit": self.candidates, "offset": 0,
            "attributesToRetrieve": FIELDS,
            "showRankingScore": True,
            "matchingStrategy": "frequency",
            "rankingScoreThreshold": self.min_score_semantic if semantic else self.min_score,
        }
        if semantic:
            body["hybrid"] = {"embedder": self.embedder,
                              "semanticRatio": self.semantic_ratio if ratio is None else ratio}
            body["vector"] = vector
        return body, semantic

    async def _readable(self, scope: Scope, ids: list[str]) -> dict[str, dict[str, Any]]:
        if scope.token is not None:
            return await self.hasura.ask_documents(scope.token, ids)
        return await self.hasura.ask_documents_service(scope.tenant_id, ids)

    async def _rounds(self, scope: Scope, body: dict[str, Any]
                      ) -> AsyncIterator[tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]]:
        """Từng lượt: (đoạn Meilisearch trả về, văn bản đã hậu kiểm: được đọc và còn đủ điều kiện vào chỉ mục). Lỗi
        Meilisearch (SearchError) và Hasura (HasuraAuthError, HasuraError) đi thẳng lên."""
        checked: dict[str, dict[str, Any] | None] = {}
        for round_no in range(1 + MORE_ROUNDS):
            hits = await self.index.search({**body, "offset": round_no * self.candidates})
            new = sorted({str(h["document_id"]) for h in hits} - checked.keys())
            if new:
                readable = await self._readable(scope, new)
                for doc_id in new:
                    row = readable.get(doc_id)
                    # cùng điều kiện với vòng đồng bộ: đoạn còn trong chỉ mục cũ của văn bản vừa hủy, vừa về dự thảo
                    checked[doc_id] = row if row is not None and eligible(row) else None
            yield hits, {k: v for k, v in checked.items() if v is not None}
            if len(hits) < self.candidates:
                return

    async def _hybrid_or_keywords(self, scope: Scope, q: str, vector: list[float] | None, where: list[str],
                                  collect: Callable[[dict[str, Any]], Awaitable[T]], ratio: float | None = None
                                  ) -> tuple[T, bool, str | None]:
        """``collect(thân tìm)`` → (kết quả, có tìm theo nghĩa, lỗi tìm lai). Tìm lai lỗi thì tìm lại một lần chỉ bằng
        từ khóa; Meilisearch tắt hẳn thì lần đó cũng lỗi và SearchError đi lên. ``ratio``: tỷ trọng nghĩa của lượt
        này, None thì theo cấu hình."""
        body, semantic = self._body(scope, q, vector, where, ratio)
        if not semantic:
            return await collect(body), False, None
        try:
            return await collect(body), True, None
        except SearchError as exc:
            body, _ = self._body(scope, q, None, where)
            return await collect(body), False, str(exc)

    async def search(self, scope: Scope, *, q: str, vector: list[float] | None, limit: int = 5,
                     filters: Filters = Filters(),  # noqa: B008 — dataclass bất biến
                     question: str | None = None) -> Retrieval:
        """``q``: câu tìm (``vi.keyword_query``); ``question``: nguyên câu hỏi đã chuẩn hóa, để chọn tỷ trọng nghĩa
        (``semantic_ratio`` — ``keyword_query`` đã bỏ ngoặc kép); không có thì xét trên ``q``."""
        if scope.where == NOTHING or limit <= 0:
            return Retrieval([], 0, False)
        ratio = semantic_ratio(q if question is None else question, self.semantic_ratio)
        (passages, candidates, relaxed), semantic, error = await self._hybrid_or_keywords(
            scope, q, vector, filter_parts(filters), lambda body: self._passages(scope, body, limit), ratio)
        return Retrieval(passages, candidates, semantic, error, relaxed, ratio if semantic else None)

    async def _passages(self, scope: Scope, body: dict[str, Any], limit: int) -> tuple[list[Passage], int, int]:
        """(đoạn đã hậu kiểm theo thứ tự xếp hạng, số đoạn Meilisearch đã trả, số đoạn nhờ tìm nới)."""
        passages: list[Passage] = []
        seen: set[str] = set()
        per_doc: dict[str, int] = {}
        checked: dict[str, dict[str, Any]] = {}     # văn bản đã qua hậu kiểm
        known: set[str] = set()                      # văn bản đã hậu kiểm, qua hay không
        candidates = 0

        def take(hit: dict[str, Any], score: float) -> bool:
            """Thêm đoạn nếu văn bản đã qua hậu kiểm, đoạn chưa có và văn bản chưa đủ đoạn; True khi đã thêm."""
            doc_id, chunk_id = str(hit["document_id"]), str(hit["id"])
            row = checked.get(doc_id)
            if row is None or chunk_id in seen or per_doc.get(doc_id, 0) >= self.per_doc:
                return False
            seen.add(chunk_id)
            per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
            passages.append(Passage(
                chunk_id=chunk_id, document_id=doc_id, kind=hit.get("kind") or "page",
                file_id=hit.get("file_id"), file_role=hit.get("file_role"), page=hit.get("page"),
                text=hit.get("text") or "", score=score, doc=source_doc(row),
            ))
            return True

        main: dict[str, dict[str, Any]] = {}       # mọi đoạn lượt chính đã đọc, theo thứ tự Meilisearch
        async with aclosing(self._rounds(scope, body)) as rounds:
            async for hits, readable in rounds:
                candidates += len(hits)
                checked = readable
                known.update(str(h["document_id"]) for h in hits)
                for hit in hits:
                    main.setdefault(str(hit["id"]), hit)
                for hit in hits:
                    if take(hit, float(hit.get("_rankingScore") or 0.0)) and len(passages) == limit:
                        break
                if len(passages) == limit:
                    break
        if "hybrid" in body:
            return passages, candidates, 0
        # Tìm theo từ khóa luôn nới (đầu tệp), kể cả khi lượt chính đã đủ, rồi xếp chung mọi đoạn theo tỷ lệ trọng số
        # câu hỏi mà đoạn có: đoạn chỉ khớp từ hiếm nhất ("điều kiện" của "đủ điều kiện xét tốt nghiệp") không đứng
        # trước đoạn trả lời có gần đủ câu hỏi. Lượt nới lỗi: kết quả lượt chính vẫn dùng được.
        try:
            weighed = await self._relaxed(body, floor=0.0, also=list(main.values()))
        except SearchError:
            return passages, candidates, 0
        if not weighed:
            return passages, candidates, 0
        share = {str(h["id"]): s for h, s in weighed}
        relaxed = [(h, s) for h, s in weighed if s >= RELAX_MIN and str(h["id"]) not in main]
        new = sorted({str(h["document_id"]) for h, _ in relaxed} - known)
        if new:
            readable = await self._readable(scope, new)
            checked = {**checked, **{d: r for d in new if (r := readable.get(d)) is not None and eligible(r)}}
        pool = [(h, share.get(i, float(h.get("_rankingScore") or 0.0))) for i, h in main.items()] + relaxed
        pool.sort(key=lambda x: -x[1])              # sort ổn định: cùng điểm thì đoạn lượt chính trước
        passages, seen, per_doc = [], set(), {}
        for hit, score in pool:
            if take(hit, score) and len(passages) == limit:
                break
        return passages, candidates, sum(p.chunk_id not in main for p in passages)

    async def _relaxed(self, body: dict[str, Any], floor: float = RELAX_MIN, also: list[dict[str, Any]] | None = None
                       ) -> list[tuple[dict[str, Any], float]]:
        """Tìm nới (xem đầu tệp): (đoạn, tỷ lệ trọng số) ≥ ``floor``, cao trước, tối đa ``candidates`` đoạn —
        ``floor`` = 0 thì mọi đoạn đã thấy, kể cả các đoạn ``also`` (để xếp đoạn lượt chính). Câu tìm dưới hai từ thì
        không nới: lượt chính đã tìm từng từ."""
        terms = list(dict.fromkeys(w.casefold() for w in str(body.get("q") or "").split()))
        if len(terms) < 2:
            return []
        scoped = {"filter": body["filter"]}
        # dấu cách cuối: từ là từ trọn, không phải tiền tố (Meilisearch coi từ cuối câu tìm là tiền tố)
        results = await self.index.multi_search(
            [{**scoped, "q": "", "limit": 0}]
            + [{**scoped, "q": f"{t} ", "matchingStrategy": "all", "limit": self.candidates,
                "attributesToRetrieve": FIELDS} for t in terms])
        total = results[0][1]
        if total <= 0:
            return []
        weights = [math.log(1 + total / max(df, 0.5)) for _, df in results[1:]]
        mass = sum(weights)
        hits = {str(h["id"]): h for h in also or ()}
        found: dict[str, set[int]] = {}             # đoạn → các từ có đoạn đó trong kết quả
        for n, (term_hits, _) in enumerate(results[1:]):
            for hit in term_hits:
                hits.setdefault(str(hit["id"]), hit)
                found.setdefault(str(hit["id"]), set()).add(n)
        # mỗi từ chỉ lấy ``candidates`` đoạn đầu: từ có ở nhiều đoạn hơn thì đoạn đứng sau không có trong kết quả của
        # từ đó — tính cả từ có nguyên văn trong đoạn, kẻo đoạn có đủ câu hỏi bị xếp sau đoạn chỉ có từ phổ biến
        folded = [fold(t).casefold() for t in terms]

        def share(chunk_id: str, hit: dict[str, Any]) -> float:
            text = fold(str(hit.get("text") or "")).casefold()
            words = set(WORD.findall(text))
            return sum(w for n, (t, w) in enumerate(zip(folded, weights, strict=True))
                       if n in found.get(chunk_id, ()) or (t in words if WORD.fullmatch(t) else t in text)) / mass

        ranked = sorted(((hit, s) for chunk_id, hit in hits.items() if (s := share(chunk_id, hit)) >= floor),
                        key=lambda x: -x[1])
        return ranked if floor <= 0 else ranked[: self.candidates]

    async def similar_documents(self, scope: Scope, *, q: str, vector: list[float] | None, limit: int = 10,
                                where: tuple[str, ...] = ()) -> list[DocHit]:
        """Như ``similar`` nhưng chỉ trả danh sách văn bản (bỏ cờ tìm theo nghĩa, lỗi tìm lai)."""
        return (await self.similar(scope, q=q, vector=vector, limit=limit, where=where)).hits

    async def similar(self, scope: Scope, *, q: str, vector: list[float] | None, limit: int = 10,
                      where: tuple[str, ...] = ()) -> Similar:
        """Văn bản tương tự (F4.3): gộp đoạn theo văn bản, điểm = điểm cao nhất; đã hậu kiểm như ``search``.
        ``where``: điều kiện thêm, viết sẵn (vd ``'document_id != "…"'``) — chỉ truyền chuỗi do mã dựng."""
        if scope.where == NOTHING or limit <= 0:
            return Similar([], False)

        async def collect(body: dict[str, Any]) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
            best: dict[str, float] = {}
            readable: dict[str, dict[str, Any]] = {}
            seen: set[str] = set()                   # văn bản đã hậu kiểm, qua hay không
            async with aclosing(self._rounds(scope, body)) as rounds:
                async for hits, readable in rounds:
                    seen.update(str(h["document_id"]) for h in hits)
                    for hit in hits:
                        doc_id = str(hit["document_id"])
                        if doc_id in readable:
                            best[doc_id] = max(best.get(doc_id, 0.0), float(hit.get("_rankingScore") or 0.0))
                    if len(best) >= limit:
                        break
            if "hybrid" in body:
                return best, readable
            # Tìm theo từ khóa luôn nới (đầu tệp), kể cả khi lượt chính đã đủ: trích yếu hay có từ hiếm không nói gì
            # về chủ đề ("II" của học kỳ, năm học) mà frequency vẫn bắt mọi văn bản phải có. Điểm = điểm cao hơn giữa
            # _rankingScore và tỷ lệ trọng số từ chung — cùng thang [0, 1], cùng tăng theo độ phủ câu tìm.
            try:
                relaxed = await self._relaxed(body)
            except SearchError:                      # lượt nới lỗi: kết quả lượt chính vẫn dùng được
                return best, readable
            new = sorted({str(h["document_id"]) for h, _ in relaxed} - seen)
            if new:
                rows = await self._readable(scope, new)
                readable = {**readable, **{d: r for d in new if (r := rows.get(d)) is not None and eligible(r)}}
            for hit, share in relaxed:
                doc_id = str(hit["document_id"])
                if doc_id in readable:
                    best[doc_id] = max(best.get(doc_id, 0.0), share)
            return best, readable

        (best, readable), semantic, error = await self._hybrid_or_keywords(scope, q, vector, list(where), collect)
        ranked = sorted(best.items(), key=lambda kv: -kv[1])[:limit]
        return Similar([DocHit(doc_id, score, source_doc(readable[doc_id])) for doc_id, score in ranked],
                       semantic, error)
