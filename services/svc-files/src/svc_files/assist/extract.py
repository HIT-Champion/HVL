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

"""Câu trích nguyên văn (F4.2) — thuần, tất định, không mô hình: đường trả lời luôn có, kể cả trong CI.

Mỗi câu của mỗi đoạn được chấm ``|term(câu hỏi) ∩ term(câu)| / |term(câu hỏi)|``. Hòa điểm thì câu chỉ nhắc lại trích
yếu, số ký hiệu, cơ quan ban hành (dòng "V/v …", tiêu đề — người dùng đã thấy ở nguồn) xếp sau, rồi câu đứng trước.
Câu đạt khi chạm ``THRESHOLD``, chung ít nhất ``min(2, |term|)`` term và chứa ít nhất ``min(2, ⌈số cặp / 2⌉)`` cặp
term đứng liền nhau của câu hỏi (``vi.term_bigrams``, #448): term là âm tiết, nên "Thủ tục cấp hộ chiếu công vụ" đạt
3/7 với câu có "cung cấp", "công nghệ", "dịch vụ" mà không chung cặp nào. Mỗi đoạn lấy câu tốt nhất trong các câu
đạt (không câu nào đạt thì câu điểm cao nhất, chỉ để làm đoạn trích); tối đa 3 câu, ưu tiên
câu của các văn bản khác nhau; trùng chữ (đoạn chồng nhau) thì bỏ. Văn bản trả lời: mỗi dòng ``“<câu>” [n]``, ``n`` là
số thứ tự của đoạn trong danh sách nguồn. Dạng ``[2]``, ``[1, 3]`` có sẵn trong câu được đổi thành ``(2)``, ``(1, 3)``
(``unmark``): chỉ dấu trích dẫn do máy chủ thêm mới có dạng ``[n]``, giao diện không dựng nhầm thành liên kết nguồn.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from . import vi
from .retrieve import Passage

THRESHOLD = 0.34            # tỷ lệ term của câu hỏi có trong câu
MIN_COMMON = 2              # số term chung tối thiểu (câu hỏi ít term hơn thì bằng số term)
MIN_PAIRS = 2               # số cặp term liền nhau chung tối thiểu (câu hỏi ít cặp thì nửa số cặp, làm tròn lên)
MAX_SENTENCES = 3
SENTENCE_CHARS = 320        # câu dài hơn thì cắt quanh chỗ khớp
EXCERPT_CHARS = 600         # đoạn trích hiện ở danh sách nguồn
ELLIPSIS = "…"
SNAP_CHARS = 24             # lùi / tiến tối đa từng này ký tự để cắt ở ranh giới từ
# dạng dấu trích dẫn: mọi dạng giao diện (utils/answer.ts) dựng thành liên kết nguồn; grounding.validate bỏ chúng
# khỏi câu trả lời của mô hình
CITE_LIKE_RE = re.compile(r"\[(\s*\d{1,3}(?:\s*[,;]\s*\d{1,3})*\s*)\]")


@dataclass(frozen=True)
class Extract:
    text: str | None                        # None: không câu nào đạt
    cited: list[int]                        # số thứ tự nguồn (từ 1) của các câu đã trích, theo thứ tự trong text
    best: dict[str, tuple[int, int]]        # chunk_id → khoảng câu tốt nhất trong passage.text (cả khi không đạt)


@dataclass(frozen=True)
class _Pick:
    n: int
    document_id: str
    score: float
    sentence: str


def _doc_terms(doc: dict[str, Any]) -> set[str]:
    """Term của những gì nguồn đã hiện sẵn: trích yếu, số ký hiệu, cơ quan ban hành, tên loại."""
    kind = doc.get("type_name") or (doc.get("document_type") or {}).get("name") or ""
    text = " ".join(str(doc.get(k) or "") for k in ("summary", "symbol", "issuer_name"))
    return set(vi.terms(f"{text} {kind}"))


def unmark(text: str) -> str:
    """Chữ văn bản đưa vào câu trích, ngữ cảnh mô hình: ``[2]`` → ``(2)``, ``[1, 3]`` → ``(1, 3)``. Giữ độ dài."""
    return CITE_LIKE_RE.sub(r"(\1)", text)


def _window(text: str, lo: int, hi: int, limit: int) -> str:
    """Tối đa ``limit`` ký tự của ``text`` quanh ``[lo, hi)``, cắt ở ranh giới từ, thêm "…" ở phía bị cắt."""
    if len(text) <= limit:
        return text.strip()
    budget = limit - 2 * len(ELLIPSIS)
    if hi - lo >= budget:
        start, end = lo, lo + budget
    else:
        extra = budget - (hi - lo)
        start = max(0, lo - extra // 2)
        end = min(len(text), start + budget)
        start = max(0, end - budget)
    if start > 0 and not text[start - 1].isspace():
        space = text.find(" ", start, min(start + SNAP_CHARS, max(lo, start + 1)))
        if space != -1:
            start = space + 1
    if end < len(text) and not text[end].isspace():
        space = text.rfind(" ", max(end - SNAP_CHARS, hi, start + 1), end)
        if space != -1:
            end = space
    return (ELLIPSIS if start > 0 else "") + text[start:end].strip() + (ELLIPSIS if end < len(text) else "")


def _clip(sentence: str, wanted: set[str]) -> str:
    """Câu trên một dòng, ≤ ``SENTENCE_CHARS`` ký tự, cắt quanh các chỗ khớp term của câu hỏi."""
    flat = " ".join(sentence.split())
    if len(flat) <= SENTENCE_CHARS:
        return flat
    hits = [m.span() for m in vi.TOKEN_RE.finditer(flat) if vi.term_key(m.group()) in wanted]
    lo, hi = (hits[0][0], hits[-1][1]) if hits else (0, 0)
    return _window(flat, lo, hi, SENTENCE_CHARS)


def excerpt(text: str, span: tuple[int, int] | None, limit: int = EXCERPT_CHARS) -> str:
    """Đoạn trích ≤ ``limit`` ký tự quanh câu tốt nhất (``span``), một dòng."""
    lo, hi = span or (0, 0)
    return " ".join(_window(text, lo, hi, limit).split())


def _best(question: set[str], pairs: set[tuple[str, str]],
          passage: Passage) -> tuple[tuple[int, int], float, bool] | None:
    """Câu tốt nhất của đoạn: (khoảng, điểm, đạt) — câu đạt đứng trước, rồi điểm."""
    spans = vi.sentences(passage.text)
    if not spans:
        return None
    need = min(MIN_COMMON, len(question))
    need_pairs = min(MIN_PAIRS, (len(pairs) + 1) // 2)
    shown = _doc_terms(passage.doc) if passage.kind == "page" else set()
    ranked = []
    for a, b in spans:
        sentence = passage.text[a:b]
        got = set(vi.terms(sentence))
        common = len(question & got)
        score = common / len(question) if question else 0.0
        ok = (bool(question) and score >= THRESHOLD and common >= need
              and len(pairs & vi.term_bigrams(sentence)) >= need_pairs)
        restates = bool(shown) and bool(got) and got <= shown
        ranked.append((not ok, -score, restates, a, b))
    failed, neg, _, a, b = min(ranked)
    return (a, b), -neg, not failed


def answer(question: str, passages: Sequence[Passage]) -> Extract:
    wanted = set(vi.terms(question))
    pairs = vi.term_bigrams(question)
    best: dict[str, tuple[int, int]] = {}
    picks: list[_Pick] = []
    for i, passage in enumerate(passages):
        got = _best(wanted, pairs, passage)
        if got is None:
            continue
        (a, b), score, ok = got
        best[passage.chunk_id] = (a, b)
        if ok:
            picks.append(_Pick(i + 1, passage.document_id, score, _clip(unmark(passage.text[a:b]), wanted)))
    picks.sort(key=lambda p: (-p.score, p.n))
    chosen: list[_Pick] = []
    seen_docs: set[str] = set()
    seen_text: set[str] = set()
    for first_pass in (True, False):            # lượt đầu mỗi văn bản một câu, lượt sau lấp chỗ còn trống
        for pick in picks:
            if len(chosen) == MAX_SENTENCES:
                break
            key = vi.normalize(pick.sentence).casefold()
            if pick in chosen or key in seen_text or (first_pass and pick.document_id in seen_docs):
                continue
            chosen.append(pick)
            seen_docs.add(pick.document_id)
            seen_text.add(key)
    chosen.sort(key=lambda p: (-p.score, p.n))
    if not chosen:
        return Extract(None, [], best)
    text = "\n".join(f"“{p.sentence}” [{p.n}]" for p in chosen)
    return Extract(text, [p.n for p in chosen], best)
