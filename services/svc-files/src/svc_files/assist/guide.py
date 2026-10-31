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

"""Kho tĩnh của trợ lý hỏi đáp (F4.2, #423): tệp Giới thiệu trợ lý và hướng dẫn sử dụng ``docs/huong-dan/*.md``.

Không đưa vào chỉ mục văn bản: hậu kiểm hỏi ``office.documents`` sẽ loại chúng, và đây không phải văn bản của đơn vị.
Nạp một lần lúc khởi động, tìm trong tiến trình bằng ``vi.terms`` (trọng số idf, tiêu đề mục tính gấp đôi). Mỗi mục
(tiêu đề ``##``, ``###``) thành một đoạn ``kind="guide"`` đi qua câu trích nguyên văn và bộ kiểm căn cứ y như đoạn văn
bản; nguồn trả người hỏi là "Hướng dẫn: <tiêu đề>", không có ``document_id``.

- Giới thiệu trợ lý: ``gioi_thieu/vi.md``, ``gioi_thieu/en.md`` cạnh module này; mỗi mục có neo ``{#mã}`` cố định mà
  ``INTRO_SECTIONS`` trỏ tới theo mã lý do của bộ định tuyến (route.py).
- Hướng dẫn: thư mục ``MOC_ASK_GUIDE_DIR`` (compose gắn ``docs/huong-dan`` vào ``/app/huong-dan``, chỉ đọc). Thiếu thư
  mục thì kho chỉ có phần giới thiệu, câu hỏi cách dùng tìm trong kho văn bản (answer.py).
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path

from . import vi
from .retrieve import Passage

log = logging.getLogger("svc_files")

INTRO_DIR = Path(__file__).with_name("gioi_thieu")
GUIDE_TYPE = {"vi": "Hướng dẫn sử dụng", "en": "User guide"}
INTRO_TYPE = {"vi": "Giới thiệu trợ lý", "en": "About the assistant"}
# mã lý do của route.py → mục chính của tệp giới thiệu
INTRO_SECTIONS = {
    "lam-duoc-gi": "lam-duoc-gi", "what-can-you-do": "lam-duoc-gi", "can-giup": "lam-duoc-gi",
    "dung-mo-hinh": "mo-hinh", "which-model": "mo-hinh",
    "hoi-the-nao": "cach-hoi",
    "cam-on": "cam-on", "thanks": "cam-on",
    "luoi-an-toan": "chua-ro",              # lưới an toàn của route.fallback: không rõ hỏi gì, không có đoạn nào
}
INTRO_DEFAULT = "gioi-thieu"
INTRO_ORDER = ("gioi-thieu", "lam-duoc-gi", "cach-hoi", "mo-hinh")    # mục kèm theo làm nguồn phụ
OUT_OF_SCOPE = "ngoai-pham-vi"
LEAD_SENTENCES = 3
MIN_COVERAGE = 0.35         # tỷ lệ trọng số term của câu hỏi có trong mục

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*(?:\{#([\w-]+)\})?\s*$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE_RE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_MARK_RE = re.compile(r"\*\*|__|`")
_TABLE_RULE_RE = re.compile(r"^\|?[\s:|-]+\|?$")


@dataclass(frozen=True)
class Section:
    key: str                # <tệp>#<neo>, duy nhất trong kho
    anchor: str
    doc_title: str          # tiêu đề cấp 1 của tệp
    title: str              # tiêu đề mục
    path: str               # docs/huong-dan/<tệp>#<neo> — chỉ để hiện, không dựng URL
    text: str               # chữ thuần của mục
    lang: str
    intro: bool


def slug(title: str) -> str:
    """Neo kiểu GitHub: chữ thường, bỏ dấu câu, khoảng trắng thành gạch nối (giữ chữ có dấu)."""
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", title.lower()).strip())


def plain(markdown: str) -> str:
    """Chữ thuần của một đoạn Markdown: bỏ ảnh, chú thích, khối mã, dấu đậm; liên kết giữ chữ; bảng thành dòng chữ."""
    text = _FENCE_RE.sub("", _COMMENT_RE.sub("", markdown))
    lines = []
    for line in text.splitlines():
        line = _MARK_RE.sub("", _LINK_RE.sub(r"\1", _IMAGE_RE.sub("", line))).strip()
        if not line or _TABLE_RULE_RE.match(line):
            continue
        if line.startswith("|"):
            line = "; ".join(c.strip() for c in line.strip("|").split("|") if c.strip()) + "."
        lines.append(line)
    return vi.normalize(" ".join(lines))


def parse(markdown: str, *, name: str, path: str, lang: str = "vi", intro: bool = False) -> list[Section]:
    """Các mục ``##``, ``###`` của một tệp; phần trước mục đầu tiên (nếu có chữ) là mục mang tiêu đề tệp."""
    doc_title = name
    out: list[Section] = []
    title, anchor, body = "", "", []

    def flush() -> None:
        text = plain("\n".join(body))
        if text and vi.terms(text):
            heading = title or doc_title
            neo = anchor or slug(heading)
            out.append(Section(f"{name}#{neo}", neo, doc_title, heading, f"{path}#{neo}", text, lang, intro))

    for line in markdown.splitlines():
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) == 1:
            doc_title = m.group(2)
            continue
        if m:
            flush()
            title, anchor, body = m.group(2), m.group(3) or "", []
        else:
            body.append(line)
    flush()
    return out


class GuideStore:
    def __init__(self, sections: list[Section]) -> None:
        self.guides = [s for s in sections if not s.intro]
        self.intros = {(s.lang, s.anchor): s for s in sections if s.intro}
        self._terms = {s.key: set(vi.terms(f"{s.title} {s.text}")) for s in self.guides}
        self._title_terms = {s.key: set(vi.terms(s.title)) for s in self.guides}
        df: dict[str, int] = {}
        for found in self._terms.values():
            for term in found:
                df[term] = df.get(term, 0) + 1
        n = max(len(self.guides), 1)
        self._idf = {t: math.log(1 + n / c) for t, c in df.items()}
        self._max_idf = math.log(1 + n)

    @classmethod
    def load(cls, guide_dir: str | Path | None, intro_dir: Path = INTRO_DIR) -> GuideStore:
        sections: list[Section] = []
        for lang in ("vi", "en"):
            file = intro_dir / f"{lang}.md"
            sections += parse(file.read_text(encoding="utf-8"), name=f"gioi-thieu-{lang}",
                              path=f"services/svc-files/src/svc_files/assist/gioi_thieu/{lang}.md", lang=lang,
                              intro=True)
        folder = Path(guide_dir) if guide_dir else None
        if folder is None or not folder.is_dir():
            log.warning('{"event": "office.assist.guides_missing", "dir": "%s"}', folder)
        else:
            for file in sorted(folder.glob("*.md")):
                sections += parse(file.read_text(encoding="utf-8"), name=file.stem,
                                  path=f"docs/huong-dan/{file.name}")
        return cls(sections)

    def search(self, question: str, k: int) -> list[Passage]:
        """Các mục hướng dẫn khớp câu hỏi nhất, tối đa ``k``; mục khớp ít hơn ``MIN_COVERAGE`` trọng số thì bỏ."""
        wanted = vi.terms(question)
        total = sum(self._idf.get(t, self._max_idf) for t in wanted)
        if not total:
            return []
        scored = []
        for s in self.guides:
            got = self._terms[s.key]
            hit = sum(self._idf[t] for t in wanted if t in got)
            if hit / total < MIN_COVERAGE:
                continue
            bonus = sum(self._idf[t] for t in wanted if t in self._title_terms[s.key])
            scored.append((hit + bonus, s))
        scored.sort(key=lambda p: (-p[0], p[1].key))
        return [passage(s, score) for score, s in scored[:k]]

    def intro(self, reason: str, lang: str) -> list[Passage]:
        """Mục giới thiệu trả lời mã lý do ``reason`` (đứng đầu), kèm các mục chung làm nguồn phụ."""
        main = INTRO_SECTIONS.get(reason.removeprefix("kw:"), INTRO_DEFAULT)
        order = [main, *(a for a in INTRO_ORDER if a != main)]
        found = [self.intros.get((lang, a)) or self.intros.get(("vi", a)) for a in order]
        return [passage(s, 1.0) for s in found if s is not None]

    def fixed(self, lang: str) -> str:
        """Câu cố định cho câu ngoài phạm vi (mục ``ngoai-pham-vi`` của tệp giới thiệu)."""
        s = self.intros.get((lang, OUT_OF_SCOPE)) or self.intros[("vi", OUT_OF_SCOPE)]
        return s.text


def passage(s: Section, score: float) -> Passage:
    label = INTRO_TYPE[s.lang] if s.intro else GUIDE_TYPE[s.lang]
    return Passage(chunk_id=f"guide:{s.key}", document_id=f"guide:{s.key.split('#')[0]}", kind="guide",
                   file_id=None, file_role=None, page=None, text=s.text, score=score,
                   doc={"symbol": s.key.split("#")[0], "title": s.doc_title, "summary": s.title, "path": s.path,
                        "type_name": label})


def lead(p: Passage, n: int = LEAD_SENTENCES) -> str:
    """Vài câu đầu của một mục: câu trả lời của đường ``gioi_thieu``, không cần khớp từ với câu hỏi ("Xin chào")."""
    spans = vi.sentences(p.text)[:n]
    return p.text[spans[0][0]: spans[-1][1]] if spans else p.text


def source(n: int, p: Passage, excerpt: str, cited: bool) -> dict[str, object]:
    """Nguồn ``kind="guide"`` trả người hỏi: không có văn bản, tệp, trang; ``path`` là tệp trong repo kèm neo."""
    return {
        "n": n, "document_id": None, "symbol": p.doc["title"], "type_code": None, "type_name": p.doc["type_name"],
        "summary": p.doc["summary"], "issuer_name": None, "issued_on": None, "direction": None, "status": None,
        "kind": "guide", "file_id": None, "file_role": None, "page": None, "excerpt": excerpt, "cited": cited,
        "path": p.doc["path"],
    }
