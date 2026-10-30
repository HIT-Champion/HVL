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

"""Chữ tiếng Việt cho trợ lý hỏi đáp (F4.2) — thuần Python, không I/O.

- ``normalize``: NFC, bỏ ký tự điều khiển / vô hình (như ``vntext.INVISIBLE_RE``), gộp khoảng trắng.
- ``tokens``: chữ thường, tách theo ký tự không phải chữ, nhưng giữ nguyên số (``3,2``, ``15/11/2026``,
  ``200.000``) và số ký hiệu (``88/CTSV``, ``131/ĐT-ĐH``) thành một token.
- ``terms``: token bỏ từ dừng, khử trùng, so khớp trên dạng bỏ dấu (``vntext.fold``). Từ dừng so trên token
  chữ thường **còn dấu**: bỏ dấu trước thì "có" trùng "cơ" của "cơ quan", "thì" trùng "thi" của "kỳ thi".
- ``term_bigrams``: cặp term đứng liền nhau, gần với từ hai âm tiết ("hộ chiếu") — câu trích dùng để không nhận câu
  chỉ khớp âm tiết lẻ ("cấp" của "cung cấp").
- ``keyword_query``: tối đa 10 term (Meilisearch chỉ xét 10 từ đầu của câu tìm), viết lại bằng chữ gốc.
- ``sentences``: khoảng ``[đầu, cuối)`` của từng câu, để trích nguyên văn.
"""

from __future__ import annotations

import re
import unicodedata

from ..vntext import INVISIBLE_RE, fold

MAX_QUERY_TERMS = 10

# Từ hư, đại từ, từ hỏi thường gặp trong câu hỏi — viết có dấu, chữ thường
STOPWORDS = frozenset("""
à ạ ai anh bao biết bị các cái cần cho chị chưa có của cũng đã đang đâu để đến đều được đó gì hay hãy hoặc hỏi khi
không là lại mà mình một nào này nên nếu nhé như những nhiêu ở phải ra rằng rồi sao sẽ tại thế thì tôi trong vậy về
vì với và xin em ơi
""".split())

# Khoảng trắng dạng ký tự điều khiển (xuống dòng, tab, phân cách dòng Unicode) → dấu cách, trước khi bỏ ký tự vô hình
_SPACE_CTRL_RE = re.compile("[\t\n\r\x0b\x0c\x1c-\x1f\x85  ]")
# Ký tự điều khiển thật (không phải khoảng trắng) và nửa cặp thay thế: câu hỏi có chúng thì từ chối, không lặng lẽ bỏ
_CONTROL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]")

# Số (3,2 · 15/11/2026 · 200.000 · 7:30), có thể kèm đuôi số ký hiệu (/CTSV, /ĐT-ĐH, /2026/NĐ-CP); hoặc một từ
TOKEN_RE = re.compile(r"\d+(?:[.,:/]\d+)*(?:/[^\W_]+(?:-[^\W_]+)*)*|[^\W_]+")

# --- câu ---------------------------------------------------------------------------------------------------------
_END_RE = re.compile(r"[.!?;]+[\"'”’)\]»]*")
_LINE_END_RE = re.compile(r"[.!?;:][\"'”’)\]»]*$")
_OPENERS = "([{\"'“‘«-–—•*"
# viết tắt có dấu chấm đứng trước tên riêng: không tách câu ở đó
ABBREVIATIONS = frozenset({"TP", "Tp", "ThS", "TS", "PGS", "GS"})
_WORD_BEFORE_RE = re.compile(r"([^\W\d_][\w.]*)$")
# số thứ tự đầu dòng (1. · II. · a.): dấu chấm sau nó không kết thúc câu
_MARKER_RE = re.compile(r"\d{1,3}|[IVXLC]{1,6}|[a-zđ]")


def normalize(s: str) -> str:
    """NFC, bỏ ký tự điều khiển và vô hình, gộp mọi khoảng trắng (cả xuống dòng) thành một dấu cách."""
    s = _SPACE_CTRL_RE.sub(" ", s)
    s = INVISIBLE_RE.sub("", s)
    return " ".join(unicodedata.normalize("NFC", s).split())


def has_control(s: str) -> bool:
    """Có ký tự điều khiển (ngoài tab, xuống dòng) hay nửa cặp thay thế — câu hỏi như vậy bị từ chối (400)."""
    return _CONTROL_RE.search(s) is not None


def tokens(s: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(normalize(s))]


def _is_term(token: str) -> bool:
    return token not in STOPWORDS and (len(token) >= 2 or token[0].isdigit())


def term_pairs(s: str) -> list[tuple[str, str]]:
    """(dạng bỏ dấu chữ thường, chữ gốc) của từng term, khử trùng theo dạng bỏ dấu, giữ thứ tự xuất hiện."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for original in TOKEN_RE.findall(normalize(s)):
        low = original.lower()
        if not _is_term(low):
            continue
        key = fold(low)
        if key not in seen:
            seen.add(key)
            out.append((key, original))
    return out


def terms(s: str) -> list[str]:
    """Term (dạng bỏ dấu, chữ thường) của chuỗi: bỏ từ dừng, bỏ chữ cái lẻ (trừ số), khử trùng, giữ thứ tự."""
    return [key for key, _ in term_pairs(s)]


def term_key(token: str) -> str:
    """Dạng so khớp của một token đã tách (``TOKEN_RE``): chữ thường, bỏ dấu."""
    return fold(token.lower())


def term_bigrams(s: str) -> set[tuple[str, str]]:
    """Cặp term đứng liền nhau (dạng bỏ dấu) của chuỗi: "hộ chiếu", "xanh lam". Từ dừng ở giữa thì không thành cặp."""
    keys = [fold(t) if _is_term(t) else None for t in tokens(s)]
    return {(a, b) for a, b in zip(keys, keys[1:], strict=False) if a and b}


def keyword_query(s: str) -> str:
    """Câu tìm cho Meilisearch: tối đa 10 term đầu, chữ gốc (Meilisearch tự bỏ dấu, chịu gõ sai)."""
    return " ".join(original for _, original in term_pairs(s)[:MAX_QUERY_TERMS])


# --- tách câu --------------------------------------------------------------------------------------------------


def _next_char(s: str, i: int, *, stop_at_newline: bool = False) -> int:
    """Vị trí ký tự không trắng đầu tiên từ ``i`` (dừng ở xuống dòng nếu cần); ``len(s)`` khi hết chuỗi."""
    while i < len(s) and s[i].isspace() and not (stop_at_newline and s[i] == "\n"):
        i += 1
    return i


def _abbreviation(s: str, dot: int) -> bool:
    m = _WORD_BEFORE_RE.search(s, max(0, dot - 20), dot)
    return m is not None and m.group(1).rsplit(".", 1)[-1] in ABBREVIATIONS


def _marker(s: str, dot: int) -> bool:
    return _MARKER_RE.fullmatch(s[s.rfind("\n", 0, dot) + 1:dot].strip()) is not None


def sentences(s: str) -> list[tuple[int, int]]:
    """Khoảng ``[đầu, cuối)`` của từng câu trong ``s`` (đã bỏ khoảng trắng hai đầu), theo thứ tự.

    Tách sau ``. ! ? ;`` (kèm ngoặc, nháy đóng) khi tiếp theo là khoảng trắng rồi chữ hoa, chữ số hoặc ngoặc mở —
    không tách ở ``TP.``, ``Tp.``, ``ThS.``, ``TS.``, ``PGS.``, ``GS.`` và sau số thứ tự đầu dòng (``1.``, ``II.``,
    ``a.``); số thập phân, ngày, số ký hiệu không có khoảng trắng sau dấu chấm nên không bị tách. Tách ở xuống dòng
    khi dòng trước kết thúc bằng dấu câu (cả ``:``), dòng sau bắt đầu bằng chữ hoa hoặc ngoặc mở, hoặc có dòng trống.
    Dòng sau bắt đầu bằng chữ thường hay chữ số mà dòng trước không có dấu câu là dòng bị ngắt do dàn trang PDF (lớp
    chữ giữ ngắt dòng), cùng một câu.
    """
    cuts: set[int] = set()
    for m in _END_RE.finditer(s):
        end = m.end()
        if end >= len(s) or not s[end].isspace():
            continue
        k = _next_char(s, end)
        if k >= len(s):
            continue
        ch = s[k]
        if not (ch.isupper() or ch.isdigit() or ch in _OPENERS):
            continue
        if m.group() == "." and _marker(s, m.start()):
            continue
        if "." in m.group() and _abbreviation(s, m.start()):
            continue
        cuts.add(end)
    line_start = 0
    for m in re.finditer("\n", s):
        nl = m.start()
        prev = s[line_start:nl].rstrip()
        line_start = m.end()
        k = _next_char(s, m.end(), stop_at_newline=True)
        if k >= len(s):
            continue
        ch = s[k]
        if ch == "\n" or not prev or _LINE_END_RE.search(prev) or ch.isupper() or ch in _OPENERS:
            cuts.add(nl)
    spans: list[tuple[int, int]] = []
    start = 0
    for cut in [*sorted(cuts), len(s)]:
        a = _next_char(s, start)
        b = cut
        while b > a and s[b - 1].isspace():
            b -= 1
        if a < b:
            spans.append((a, b))
        start = cut
    return spans
