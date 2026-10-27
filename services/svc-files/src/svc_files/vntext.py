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

"""Chữ tiếng Việt dùng chung: bỏ dấu giữ nguyên độ dài, ký tự vô hình, mẫu số ký hiệu và ngày ban hành.

Thuần Python, chỉ thư viện chuẩn. Đọc văn bản đến (``docread/rules.py``, ``docread/summarize.py``) và trợ lý hỏi đáp
(``assist/vi.py``, ``assist/retrieve.py``) cùng dùng; trước đây nằm trong ``docread/`` nên trợ lý phải nhập gói của
Văn phòng (docs/architecture.md §4.4).

- ``fold``: bỏ dấu, ``len(fold(s)) == len(s)`` — regex chạy trên chữ đã bỏ dấu, cắt giá trị từ chữ gốc cùng vị trí.
- ``SYMBOL``, ``DATE``: "Số: 12/QĐ-UBND", "<địa danh>, ngày … tháng … năm …" theo thể thức NĐ 30/2020, khớp trên
  ``fold(text)``; ``DASHES``: các kiểu gạch ngang đổi về "-" trước khi khớp.
- ``INVISIBLE_RE``: ký tự điều khiển, vô hình (cả xuống dòng).
"""

from __future__ import annotations

import re
import unicodedata

# Bỏ dấu giữ nguyên độ dài: mỗi ký tự Latin có dấu → chữ gốc (đ → d, Đ → D); ký tự khác giữ nguyên


def _fold_table() -> dict[int, str]:
    table = {ord("đ"): "d", ord("Đ"): "D", 0xD0: "D", 0xF0: "d", 0x189: "D", 0x111: "d", 0x110: "D"}
    for start, end in ((0xC0, 0x250), (0x1E00, 0x1F00)):
        for cp in range(start, end):
            base = unicodedata.normalize("NFD", chr(cp))[0]
            if base != chr(cp) and base.isascii():
                table.setdefault(cp, base)
    return table


_FOLD = _fold_table()


def fold(s: str) -> str:
    """Bỏ dấu tiếng Việt, GIỮ NGUYÊN ĐỘ DÀI (``len(fold(s)) == len(s)`` với chữ NFC): vị trí khớp trên chữ đã bỏ dấu
    cũng là vị trí trên chữ gốc."""
    return s.translate(_FOLD)


# Mẫu của bộ đọc văn bản đến (ví dụ trong tests/test_docread_rules.py)
SYMBOL = re.compile(r"\b(?P<pre>[Ss][Oo06])\s*[:.;]?\s*(?P<sym>(?P<num>[0-9OoIl]{1,5})[A-Za-z]?\s*/\s*"
                    r"(?:(?:19|20)[0-9]{2}\s*/\s*)?[A-Za-z0-9&]{1,12}(?:\s*-\s*[A-Za-z0-9&]{1,12}){0,4})")
DATE = re.compile(r"(?i)(?:(?P<place>[A-Z][A-Za-z.' ]{1,40}?)\s*,\s*)?ng[a-z]{0,2}y\s+(?P<d>[0-9]{1,2})\s+"
                  r"th[a-z]{0,2}ng\s+(?P<m>[0-9]{1,2})\s+n[a-z]{0,2}m\s+(?P<y>(?:19|20)[0-9]{2})\b")
DASHES = re.compile("[‐-―−]")

# ký tự điều khiển, vô hình — như $defs/text của schemas/van-ban-den.json (ở đây cả xuống dòng: trích yếu một dòng)
INVISIBLE_RE = re.compile(
    "[\u0000-\u001f\u007f-\u009f\u00ad\u115f\u1160\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\u3164\ufeff"
    "\uffa0\u2028\u2029]"
)
