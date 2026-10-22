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

"""Đột biến mã của bộ che PII (F4.4): bản tự động của việc "bỏ sửa thì đỏ" đội vẫn làm tay — không cần mutmut.

Mỗi đột biến thay đúng một đoạn trong mã nguồn pii.py (đoạn cũ phải xuất hiện đúng một lần, không thì danh sách đã
lệch với mã và phải cập nhật), nạp bản đã sửa vào một module tạm (không ghi đĩa) rồi chạy ``failures`` của
test_pii.py — bảng dương tính, âm tính, đột biến dữ liệu vào, vị trí, Masker, nhật ký. Bản gốc phải không hỏng ca
nào; mọi đột biến phải làm hỏng ít nhất một ca (bị giết). Đột biến sống sót nghĩa là test có lỗ hổng.

    uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q -s tests/test_pii_mutation.py
in bảng số ca hỏng của từng đột biến.
"""

from __future__ import annotations

import pathlib
import sys
import time
import types

from svc_files import pii
from test_pii import failures

SOURCE = pathlib.Path(pii.__file__)
BUDGET_S = 10.0

MUTANTS = (
    ("bỏ vùng bảo vệ UUID", "for m in UUID_RE.finditer(text)]", "for m in ()]"),
    ("bỏ kiểm mã tỉnh", "d[:3] not in PROVINCES or ", ""),
    ("nới chữ số thế kỷ thành 0–9", 'd[3] not in "0123"', 'd[3] not in "0123456789"'),
    ("bỏ kiểm năm sinh tương lai", "int(d[4:6]) <= year % 100", "True"),
    ("bỏ lookbehind chữ trước số", r'r"(?<![^\W_]|[/@])(?<!\d\.)', r'r"(?<![/@])(?<!\d\.)'),
    ("đầu số di động thành mọi 0[35789]", "return prefix in MOBILE_PREFIXES",
     'return prefix[:2] in ("03", "05", "07", "08", "09")'),
    ("bỏ cổng mã số thuế", "_after_tax_code(folded, first)", "False"),
    ("STK không cần từ khóa", "|stk|", "||stk|"),
    ("Masker đánh số theo vị trí", "_canonical(text[s.start:s.end], s.kind))", "str(s.start))"),
    ("window không đưa lo về đầu nhãn", "(0 if start else len(label))", "(pos - s.start if start else len(label))"),
    ("PiiFilter không che exc_text", "record.exc_text = mask_text(record.exc_text)",
     "record.exc_text = record.exc_text"),
    ("access=True giữ chuỗi truy vấn", 'head, sep, _ = path.partition("?")', 'head, sep = path, ""'),
    ("xuống dòng không là phân cách", r'SEP = r"(?:\r\n|[\s.\-])"', r'SEP = r"(?:[^\S\r\n]|[.\-])"'),
    ("bỏ điều kiện nhóm đầu ≥ 3 chữ số", "else 3      # số chữ số tối thiểu", "else 2      # số chữ số tối thiểu"),
    ("che một lượt, không lặp tới điểm bất động", "MAX_PASSES = 3", "MAX_PASSES = 1"),
)


def load(source: str, label: str) -> types.ModuleType:
    """Nạp mã nguồn vào module tạm. Đăng ký tạm trong sys.modules vì dataclass tra module của lớp lúc tạo lớp."""
    module = types.ModuleType("svc_files._pii_dot_bien")
    module.__package__ = "svc_files"
    sys.modules[module.__name__] = module
    try:
        exec(compile(source, f"{SOURCE.name} [{label}]", "exec", dont_inherit=True), module.__dict__)
    finally:
        del sys.modules[module.__name__]
    return module


def test_the_original_source_passes_every_check():
    assert failures(load(SOURCE.read_text(encoding="utf-8"), "gốc")) == []


def test_every_mutant_is_killed():
    source = SOURCE.read_text(encoding="utf-8")
    assert len(MUTANTS) == 15
    started = time.perf_counter()
    rows, survivors = [], []
    for name, old, new in MUTANTS:
        assert source.count(old) == 1, f"đột biến {name} không áp được — cập nhật danh sách ({source.count(old)} chỗ)"
        broken = failures(load(source.replace(old, new), name))
        rows.append(f"| {name} | {len(broken)} | {broken[0][:90] if broken else 'SỐNG SÓT'} |")
        if not broken:
            survivors.append(name)
    elapsed = time.perf_counter() - started
    print(f"\n### Đột biến mã pii.py — {len(MUTANTS) - len(survivors)}/{len(MUTANTS)} bị giết, {elapsed:.1f} s",
          "| đột biến | số ca hỏng | ca hỏng đầu tiên |", "|---|---|---|", *rows, sep="\n")
    assert not survivors, f"đột biến sống sót (test chưa bắt được): {survivors}"
    assert elapsed <= BUDGET_S, f"{len(MUTANTS)} đột biến chạy {elapsed:.1f} s > {BUDGET_S} s"
