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

"""Che nhầm trên kho mẫu (F4.4): chữ thật của seed/ không có số điện thoại, CCCD, email hay số tài khoản nào, nên
mọi nguồn phải ra 0 chỗ bị che — có chỗ bị che nghĩa là bộ nhận dạng che nhầm (sửa bộ nhận dạng, không sửa mẫu).

Nguồn (số mẫu đọc từ nhan.json, không ghi cứng):
- seed/van-ban-den, PDF có lớp chữ: đọc mọi trang theo hai cách như bản chạy thật — lớp chữ cho chỉ mục và trợ lý hỏi
  đáp (``pdftext.extract``) và theo bố cục cho đọc văn bản đến F4.1 (``pdflayout``, pypdf chế độ layout);
- seed/van-ban-den, bản scan: TSV Tesseract trong tests/fixtures/ocr nếu có, ghép dòng như ``tsv_lines``;
- seed/hoi-dap: mọi trang của các PDF nhiều trang, hai cách đọc như trên;
- mọi chuỗi trong van-ban-den/nhan.json, hoi-dap/cau-hoi.json, giao-viec/lich-su.json.

    uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q -s tests/test_pii_corpus.py
in bảng số đo (§6.2 CONTRACT F4.4).
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest

from svc_files import pdftext, pii
from svc_files.docread import pdflayout
from svc_files.docread.layout import tsv_lines

SEED = pathlib.Path(__file__).resolve().parents[3] / "seed"
SAMPLES = SEED / "van-ban-den"
QA = SEED / "hoi-dap"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "ocr"
YEAR = 2026

pytestmark = pytest.mark.skipif(not (SAMPLES / "nhan.json").is_file(), reason="không có seed/ (image)")


def labels() -> list[dict]:
    return json.loads((SAMPLES / "nhan.json").read_text(encoding="utf-8"))["samples"]


def pdf_views(path: pathlib.Path) -> list[str]:
    """Chữ của PDF theo hai cách đọc của bản chạy thật, mọi trang (tệp mẫu tin cậy: đọc ngay trong tiến trình)."""
    data = path.read_bytes()
    return [pdftext.extract(data).content, "\n".join(pdflayout.extract(data, max_pages=10_000).texts)]


def strings(value: object) -> Iterator[str]:
    """Mọi chuỗi (cả khóa) trong một giá trị JSON."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def sources() -> list[tuple[str, int, list[tuple[str, str]]]]:
    """(nguồn, số tệp / chuỗi, [(tên, chữ)…])."""
    text_pdfs = [s["file"] for s in labels() if s["kind"] == "text"]
    scans = [s["file"] for s in labels() if s["kind"] == "scan"]
    tsv = {p.stem: p for p in FIXTURES.glob("*.tsv")} if FIXTURES.is_dir() else {}
    missing = [name for name in scans if pathlib.Path(name).stem not in tsv]
    if missing:
        print(f"\nchưa có TSV: {', '.join(missing)}")
    with_tsv = [name for name in scans if pathlib.Path(name).stem in tsv]
    qa = sorted(QA.glob("*.pdf"))
    json_files = [SAMPLES / "nhan.json", QA / "cau-hoi.json", SEED / "giao-viec" / "lich-su.json"]
    json_strings = [(f"{p.name}#{i}", s) for p in json_files
                    for i, s in enumerate(strings(json.loads(p.read_text(encoding="utf-8"))))]
    return [
        ("seed/van-ban-den, PDF có lớp chữ", len(text_pdfs),
         [(name, view) for name in text_pdfs for view in pdf_views(SAMPLES / name)]),
        ("seed/van-ban-den, bản scan (TSV)", len(with_tsv),
         [(name, "\n".join(line.text for line in tsv_lines([tsv[pathlib.Path(name).stem].read_text(encoding="utf-8")])))
          for name in with_tsv]),
        ("seed/hoi-dap, mọi trang", len(qa), [(p.name, view) for p in qa for view in pdf_views(p)]),
        ("nhãn, câu hỏi, lịch sử giao việc", len(json_strings), json_strings),
    ]


def test_seed_corpus_has_nothing_to_mask():
    rows = ["### Che nhầm trên kho mẫu (F4.4)", "| Nguồn | Tệp / chuỗi | Ký tự | Chuỗi số ứng viên | Bị che |",
            "|---|---|---|---|---|"]
    hits = []
    measured = {}
    for title, count, texts in sources():
        chars = sum(len(text) for _, text in texts)
        candidates = sum(1 for _, text in texts for _ in pii.NUMBER_RE.finditer(text))
        masked = 0
        for name, text in texts:
            for span in pii.find(text, year=YEAR):
                masked += 1
                hits.append(f"{name}: {span.kind} …{text[max(0, span.start - 30):span.end + 10]!r}…")
        measured[title] = (count, chars, candidates)
        rows.append(f"| {title} | {count} | {chars} | {candidates} | **{masked}** |")
    print("\n" + "\n".join(rows))
    assert not hits, "kho mẫu bị che nhầm:\n" + "\n".join(hits)
    # đủ nguồn: thiếu tệp thì bảng "0 chỗ bị che" không còn nghĩa gì
    assert measured["seed/van-ban-den, PDF có lớp chữ"][0] >= 10
    assert measured["seed/hoi-dap, mọi trang"][0] >= 6
    assert all(chars > 0 and candidates > 0 for count, chars, candidates in measured.values() if count)
    assert sum(chars for _, chars, _ in measured.values()) >= 50_000
