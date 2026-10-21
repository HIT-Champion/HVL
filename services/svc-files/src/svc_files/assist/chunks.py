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

"""Cắt văn bản thành đoạn cho chỉ mục của trợ lý hỏi đáp (F4.2) — thuần, không I/O.

Nguồn là một dòng của ``hasura.CHUNK_SOURCES``: văn bản kèm thuộc tính quyền, giao việc chưa hủy và chữ theo trang
của từng tệp (F2.7, ``core.file_texts.page_starts``).

- Chỉ văn bản đủ điều kiện mới có đoạn: không hạn chế; văn bản đến chưa hủy; văn bản đi đã phát hành hoặc đã lưu
  (dự thảo chưa có giá trị và đổi liên tục). Văn bản không còn đủ điều kiện → không có đoạn nào → vòng đồng bộ xóa.
- Tệp ``main`` → ``attachment`` (theo thứ tự gắn) → ``issued``; bỏ tệp mã hóa và tệp chưa đọc được chữ. Mỗi trang cắt
  riêng: không đoạn nào vượt trang, nên trích dẫn "tr. n" luôn đúng.
- Không có đoạn trang nào (bản scan, tệp lỗi, chưa có tệp) → đúng một đoạn ``meta`` dựng từ loại, số ký hiệu, ngày,
  cơ quan, trích yếu; trích dẫn ghi "trích yếu", không bịa trang.
- ``text_sha`` đổi thì phải nhúng lại; chỉ ``meta_sha`` đổi (giao việc, trạng thái…) thì chỉ cập nhật thuộc tính lọc.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

CHUNK_TARGET = 900        # gom dòng tới khoảng từng này ký tự
CHUNK_MAX = 1200          # không đoạn nào dài hơn (kể cả phần chồng)
OVERLAP = 150             # chồng tối đa từng này ký tự: câu cuối của đoạn trước
MIN_CHARS = 40            # đoạn có ít ký tự không trắng hơn thì bỏ (số trang, mẩu chữ ký…)
MAX_CHUNKS = 300          # tối đa mỗi văn bản
META_MAX = 1200           # đoạn meta: trích yếu rất dài thì cắt

ROLE_ORDER = {"main": 0, "attachment": 1, "issued": 2}
# thuộc tính lọc + thuộc tính chỉ để hiển thị nguồn: đổi thì chỉ cập nhật (meta_sha), không nhúng lại
META_FIELDS = ("tenant_id", "direction", "status", "type_code", "year", "department_id", "created_by",
               "assignee_departments", "assignee_users", "issuer_name")

# không tách câu sau các chữ viết tắt này
ABBREVIATIONS = frozenset({"TP.", "Tp.", "ThS.", "TS.", "PGS.", "GS."})
_END = re.compile(r"([.!?;…]+[\"”’)\]]*)\s+(?=\S)")
_OPENERS = "([“\"'‘-–•"


def eligible(doc: Mapping[str, Any]) -> bool:
    """Văn bản có được đưa vào chỉ mục đoạn không."""
    if doc.get("restricted"):
        return False
    if doc.get("direction") == "in":
        return doc.get("status") != "cancelled"
    if doc.get("direction") == "out":
        return doc.get("status") in ("issued", "archived")
    return False


# --- câu, cắt đoạn ------------------------------------------------------------------------------------------------


def sentence_starts(text: str) -> list[int]:
    """Vị trí bắt đầu các câu (trừ câu đầu) trong một dòng: sau ``.!?;…`` + khoảng trắng, trước chữ hoa, số hoặc
    ngoặc mở; không tách sau ``TP.``, ``ThS.``…; số thập phân và số ký hiệu không có khoảng trắng nên không bị tách."""
    out = []
    for m in _END.finditer(text):
        nxt = text[m.end()]
        if not (nxt.isupper() or nxt.isdigit() or nxt in _OPENERS):
            continue
        word = text[:m.end(1)].rsplit(None, 1)[-1]
        if word in ABBREVIATIONS:
            continue
        out.append(m.end())
    return out


def _cut_at(line: str, limit: int) -> int:
    """Chỗ cắt một dòng dài: ranh giới câu gần ``limit`` nhất (không quá ngắn), rồi khoảng trắng, rồi cắt cứng."""
    floor = limit // 2
    best = max((j for j in sentence_starts(line) if floor <= j <= limit), default=None)
    if best is not None:
        return best
    space = line.rfind(" ", floor, limit + 1)
    return space if space > 0 else limit


def _pieces(line: str, limit: int = CHUNK_TARGET) -> list[str]:
    out = []
    while len(line) > limit:
        cut = _cut_at(line, limit)
        out.append(line[:cut].rstrip())
        line = line[cut:].lstrip()
    if line:
        out.append(line)
    return out


def _tail(chunk: str) -> str:
    """Phần chồng sang đoạn sau: câu cuối của đoạn, tối đa ``OVERLAP`` ký tự (cắt ở khoảng trắng)."""
    line = chunk[chunk.rfind("\n") + 1:]
    starts = sentence_starts(line)
    last = line[starts[-1]:] if starts else line
    if len(last) > OVERLAP:
        last = last[-OVERLAP:]
        space = last.find(" ")
        if 0 <= space < len(last) - 1:
            last = last[space + 1:]
    return last.strip()


def _solid(text: str) -> int:
    return len(text) - sum(ch.isspace() for ch in text)


def split_page(text: str) -> list[str]:
    """Chữ một trang → các đoạn: gom dòng tới ~CHUNK_TARGET ký tự, dòng dài cắt ở ranh giới câu rồi khoảng trắng,
    mỗi đoạn sau mở đầu bằng câu cuối của đoạn trước; bỏ đoạn quá ngắn."""
    pieces: list[tuple[str, str]] = []          # (ngăn với mẩu trước, mẩu)
    for line in text.split("\n"):
        line = line.strip()
        if line:
            pieces += [("\n" if k == 0 else " ", p) for k, p in enumerate(_pieces(line))]
    chunks: list[str] = []
    cur = ""
    for sep, piece in pieces:
        if cur and len(cur) + 1 + len(piece) > CHUNK_TARGET:
            chunks.append(cur)
            tail = _tail(cur)
            cur = tail + sep + piece if tail else piece
        else:
            cur = cur + sep + piece if cur else piece
    if cur:
        chunks.append(cur)
    return [c for c in chunks if _solid(c) >= MIN_CHARS]


def pages(content: str, page_starts: list[int] | None) -> list[tuple[int | None, str]]:
    """(số trang, chữ của trang); ``page_starts`` thiếu hoặc sai (dòng cũ trước F4.2) → cả nội dung là một "trang"
    không số."""
    ok = (isinstance(page_starts, list) and page_starts and all(type(s) is int for s in page_starts)
          and page_starts[0] == 0 and page_starts[-1] <= len(content)
          and all(a <= b for a, b in zip(page_starts, page_starts[1:], strict=False)))
    if not ok:
        return [(None, content)]
    bounds = [*page_starts, len(content)]
    return [(i + 1, content[bounds[i]:bounds[i + 1]]) for i in range(len(page_starts))]


# --- đoạn ---------------------------------------------------------------------------------------------------------


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _year(issued_on: str | None) -> int | None:
    try:
        return date.fromisoformat(issued_on).year if issued_on else None
    except ValueError:
        return None


def _base(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Thuộc tính chung của mọi đoạn một văn bản: hiển thị nguồn + thuộc tính lọc theo quyền (scope.py)."""
    live = [a for a in doc.get("assignments") or [] if a.get("status", "open") != "cancelled"]
    departments = sorted({str(a["department_id"]) for a in live if a.get("department_id")})
    users = sorted({str(a["user_id"]) for a in live if a.get("user_id")})
    return {
        "document_id": str(doc["id"]), "tenant_id": str(doc["tenant_id"]),
        "symbol": doc.get("symbol"), "summary": doc.get("summary"), "issuer_name": doc.get("issuer_name"),
        "type_code": doc.get("type_code"), "direction": doc.get("direction"), "status": doc.get("status"),
        "year": _year(doc.get("issued_on")),
        "department_id": str(doc["department_id"]) if doc.get("department_id") else None,
        "created_by": doc.get("created_by"),
        "assignee_departments": departments, "assignee_users": users,
    }


def _chunk(base: dict[str, Any], *, chunk_id: str, kind: str, file_id: str | None, file_role: str | None,
           page: int | None, seq: int, text: str) -> dict[str, Any]:
    meta = {k: base[k] for k in META_FIELDS}
    return {
        "id": chunk_id, "document_id": base["document_id"], "tenant_id": base["tenant_id"], "kind": kind,
        "file_id": file_id, "file_role": file_role, "page": page, "seq": seq, "text": text,
        "symbol": base["symbol"], "summary": base["summary"], "issuer_name": base["issuer_name"],
        "type_code": base["type_code"], "direction": base["direction"], "status": base["status"],
        "year": base["year"], "department_id": base["department_id"], "created_by": base["created_by"],
        "assignee_departments": base["assignee_departments"], "assignee_users": base["assignee_users"],
        "text_sha": _sha("|".join([base["symbol"] or "", base["summary"] or "", text])),
        "meta_sha": _sha(json.dumps(meta, sort_keys=True, ensure_ascii=False)),
    }


def meta_text(doc: Mapping[str, Any]) -> str:
    """"{tên loại} số {symbol} ngày {dd/mm/yyyy} của {issuer_name}: {summary}" — bỏ phần nào không có."""
    parts = [(doc.get("document_type") or {}).get("name") or doc.get("type_code") or "Văn bản"]
    if doc.get("symbol"):
        parts.append(f"số {doc['symbol']}")
    try:
        if doc.get("issued_on"):
            parts.append(f"ngày {date.fromisoformat(doc['issued_on']):%d/%m/%Y}")
    except ValueError:
        pass
    if doc.get("issuer_name"):
        parts.append(f"của {doc['issuer_name']}")
    head = " ".join(parts)
    text = f"{head}: {doc['summary']}" if doc.get("summary") else head
    return text[:META_MAX].rstrip()


def build(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Các đoạn của một văn bản (rỗng nếu không đủ điều kiện). Chưa có ``embed_model``, ``_vectors``: vòng đồng bộ
    thêm khi ghi (index.py)."""
    if not eligible(doc):
        return []
    base = _base(doc)
    doc_id = base["document_id"]
    out: list[dict[str, Any]] = []
    files = sorted(doc.get("files") or [], key=lambda f: ROLE_ORDER.get(f.get("role"), len(ROLE_ORDER)))
    for link in files:
        role, file = link.get("role"), link.get("file") or {}
        text = file.get("text") or {}
        if role not in ROLE_ORDER or file.get("encrypted") or text.get("status") != "ok" or not text.get("content"):
            continue
        file_id = str(link.get("file_id") or file.get("id"))
        for page, body in pages(text["content"], text.get("page_starts")):
            for seq, piece in enumerate(split_page(body), 1):
                if len(out) == MAX_CHUNKS:
                    return out
                out.append(_chunk(base, chunk_id=f"{doc_id}_{file_id}_{page or 0:03d}_{seq:02d}", kind="page",
                                  file_id=file_id, file_role=role, page=page, seq=seq, text=piece))
    if not out:
        out.append(_chunk(base, chunk_id=f"{doc_id}_meta", kind="meta", file_id=None, file_role=None, page=None,
                          seq=1, text=meta_text(doc)))
    return out


def meta_update(chunk: Mapping[str, Any]) -> dict[str, Any]:
    """Tài liệu cập nhật một phần khi chỉ thuộc tính lọc đổi: id + thuộc tính lọc + meta_sha, không ``_vectors``."""
    return {"id": chunk["id"], **{k: chunk[k] for k in META_FIELDS}, "meta_sha": chunk["meta_sha"]}


def embed_input(chunk: Mapping[str, Any]) -> str:
    """Chữ đưa vào mô hình nhúng: "{symbol} — {summary}" rồi chữ của đoạn; đoạn meta đã chứa cả hai."""
    text = chunk.get("text") or ""
    if chunk.get("kind") == "meta":
        return text
    head = " — ".join(p for p in (chunk.get("symbol"), chunk.get("summary")) if p)
    return f"{head}\n{text}" if head else text
