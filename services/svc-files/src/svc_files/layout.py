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

"""Dòng chữ có vị trí trên trang (F4.1) — đầu vào chung của quy tắc trích xuất (``docread/rules.py``).

Văn bản hành chính theo thể thức NĐ 30/2020 có phần đầu hai cột: trái là cơ quan ban hành, số ký hiệu, trích yếu
công văn; phải là quốc hiệu, tiêu ngữ, địa danh và ngày. Quy tắc cần biết dòng nằm cột nào, cao thấp ra sao, nên hai
nguồn chữ đều quy về cùng một dạng ``Line`` với tọa độ chuẩn hóa 0..1:

- ``text_lines``: chữ pypdf trích theo bố cục (``extraction_mode="layout"``) — mỗi hàng là một dòng trên trang, khoảng
  trắng giữ vị trí ngang. Tách cột ở chuỗi từ 3 khoảng trắng; x theo vị trí ký tự, y theo số hàng.
- ``tsv_lines``: TSV của Tesseract — gom từ theo (khối, đoạn, dòng), bỏ từ có độ tin cậy âm, chuẩn hóa theo cỡ trang
  (dòng level 1); hai cột nằm chung một dòng của Tesseract thì tách ở khoảng hở lớn.

Thuần Python, không I/O, không bao giờ ném lỗi vì nội dung (chữ do tiến trình con đọc từ tệp người dùng tải lên).
"""

from __future__ import annotations

import math
import re
import statistics
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

MAX_ROWS = 3000      # mỗi trang đọc tối đa từng này hàng chữ / dòng TSV
MAX_COLS = 3000      # và từng này ký tự mỗi hàng: chữ bố cục của PDF lạ có thể rất rộng
MAX_TEXT = 100_000   # đủ chữ thì thôi (quy tắc chỉ xét 20 000 ký tự đầu)

# Một đoạn chữ trên hàng: các từ cách nhau tối đa 2 khoảng trắng; từ 3 khoảng trắng là sang cột khác
_SEGMENT = re.compile(r"\S+(?: {1,2}\S+)*")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Line:
    """Một dòng chữ. Không biết vị trí thì ``x0 = 0, x1 = 1`` (quy tắc chuyển sang nhánh không tọa độ)."""

    text: str             # NFC, một dòng
    x0: float = 0.0       # 0..1 theo bề rộng trang
    x1: float = 1.0
    y: float = 0.0        # 0..1 từ trên xuống
    page: int = 1         # từ 1


def clean(text: str) -> str:
    """Một dòng sạch: bỏ ký tự điều khiển và ký tự ẩn, NFC, gộp khoảng trắng."""
    chars = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("Z") or ch in "\t\n\r\v\f":
            chars.append(" ")
        elif cat in ("Cc", "Cf", "Cs", "Co", "Cn"):
            continue
        else:
            chars.append(ch)
    return _SPACES.sub(" ", unicodedata.normalize("NFC", "".join(chars))).strip()


def _unit(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)


def _segments(row: str) -> list[tuple[int, int]]:
    """Các đoạn chữ của một hàng (vị trí đầu, cuối). Dòng văn bản căn đều hai bên có khoảng trắng giãn đều giữa mọi
    từ (≥ 3 khoảng hở gần bằng nhau): vẫn là một dòng, không phải nhiều cột."""
    spans = [m.span() for m in _SEGMENT.finditer(row)]
    gaps = [b[0] - a[1] for a, b in zip(spans, spans[1:])]
    if len(gaps) >= 3 and max(gaps) - min(gaps) <= 2:
        return [(spans[0][0], spans[-1][1])]
    return spans


def text_lines(pages: Sequence[str]) -> list[Line]:
    """Chữ pypdf theo bố cục, mỗi phần tử một trang → các dòng (mỗi cột một dòng), theo thứ tự trên → dưới, trái →
    phải. Bề rộng trang lấy bằng hàng dài nhất (pypdf đã bỏ lề trái chung), chiều cao bằng số hàng."""
    out: list[Line] = []
    size = 0
    for number, page in enumerate(pages, 1):
        if size >= MAX_TEXT:
            break
        rows = [row.replace("\t", " ")[:MAX_COLS] for row in str(page).splitlines()[:MAX_ROWS]]
        while rows and not rows[-1].strip():
            rows.pop()
        while rows and not rows[0].strip():
            rows.pop(0)
        if not rows:
            continue
        indent = min(len(row) - len(row.lstrip(" ")) for row in rows if row.strip())
        width = max(max(len(row.rstrip()) for row in rows) - indent, 1)
        for i, row in enumerate(rows):
            for start, end in _segments(row):
                text = clean(row[start:end])
                if text:
                    out.append(Line(text, _unit((start - indent) / width), _unit((end - indent) / width),
                                    _unit(i / len(rows)), number))
                    size += len(text)
            if size >= MAX_TEXT:
                break
    return out


def _number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(value)
    return number


def tsv_lines(pages: Sequence[str]) -> list[Line]:
    """TSV của ``tesseract … tsv``, mỗi phần tử một trang (ảnh) → các dòng, theo thứ tự trên → dưới, trái → phải.

    Cột TSV: level page_num block_num par_num line_num word_num left top width height conf text. Dòng level 1 cho cỡ
    trang; level 5 là từ, conf < 0 là dòng cấu trúc, bỏ. Thiếu dòng level 1 thì lấy khung bao các từ."""
    out: list[Line] = []
    for number, tsv in enumerate(pages, 1):
        width = height = 0.0
        groups: dict[tuple[int, int, int, int], list[tuple[float, float, float, float, str]]] = {}
        for row in str(tsv).splitlines()[:MAX_ROWS * 10]:
            cols = row.split("\t")
            if len(cols) < 12:
                continue
            try:
                level, page_num, block, par, line = (int(c) for c in cols[:5])
                left, top, w, h, conf = (_number(c) for c in (*cols[6:10], cols[10]))
            except ValueError:      # dòng tiêu đề, dòng hỏng
                continue
            if level == 1:
                width, height = max(width, left + w), max(height, top + h)
            elif level == 5 and conf >= 0 and w >= 0 and h >= 0:
                text = clean("\t".join(cols[11:]))[:MAX_COLS]
                if text:
                    groups.setdefault((page_num, block, par, line), []).append((left, top, w, h, text))
        words = [word for group in groups.values() for word in group]
        if not words:
            continue
        width = width or max(left + w for left, _, w, _, _ in words) or 1.0
        height = height or max(top + h for _, top, _, h, _ in words) or 1.0
        for group in groups.values():
            group.sort(key=lambda word: word[0])
            # Hai cột cùng hàng mà Tesseract gộp một dòng: tách ở khoảng hở rộng hơn 3 lần chiều cao chữ
            gap = max(3 * statistics.median(h for _, _, _, h, _ in group), 0.03 * width)
            segments = [[group[0]]]
            for word in group[1:]:
                prev = segments[-1][-1]
                if word[0] - (prev[0] + prev[2]) > gap:
                    segments.append([word])
                else:
                    segments[-1].append(word)
            for seg in segments:
                text = clean(" ".join(word[4] for word in seg))
                if text:
                    out.append(Line(text, _unit(seg[0][0] / width), _unit(max(x + w for x, _, w, _, _ in seg) / width),
                                    _unit(min(top for _, top, _, _, _ in seg) / height), number))
    out.sort(key=lambda line: (line.page, line.y, line.x0))
    return out
