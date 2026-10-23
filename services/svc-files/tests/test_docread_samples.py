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


"""Đo quy tắc trên văn bản mẫu (F4.1, seed/van-ban-den, nhãn trong nhan.json) — không cần Docker, không OCR.

Mọi PDF có lớp chữ trong nhan.json (số mẫu đọc từ nhãn, không ghi cứng): pypdf theo bố cục ngay trong tiến trình
(tệp tin cậy của kho mã) → ``text_lines`` → ``suggest``. Ngưỡng theo tỉ lệ (như scripts/demo.py do-doc-van-ban): số ký
hiệu, ngày ban hành, loại ≥ 90 % đúng; cơ quan ban hành ≥ 80 %; có trích yếu ≥ 80 %; không trường ``high`` nào sai.
Bản scan: TSV Tesseract trong tests/fixtures/ocr (sinh bằng make van-ban-mau khi image có tesseract) — ngưỡng chốt
sau lần đo đầu: 11–14 đo 21/10, cả 7 bản (thêm 20–22) đo 22/10.

    uv run --no-project --with-requirements requirements-dev.txt python -m pytest -q -s tests/test_docread_samples.py
in bảng số đo.
"""

from __future__ import annotations

import io
import json
import pathlib
import re
from datetime import date

import pytest

from svc_files.docread.layout import text_lines, tsv_lines
from svc_files.docread.rules import CATALOG, Suggestion, suggest

SAMPLES = pathlib.Path(__file__).resolve().parents[3] / "seed" / "van-ban-den"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "ocr"
TODAY = date(2026, 10, 21)
FIELDS = ("symbol", "issued_on", "type_code", "issuer_name", "urgency")
TEXT_MIN = {"symbol": 90, "issued_on": 90, "type_code": 90, "issuer_name": 80, "summary": 80}     # % số PDF có chữ
# Bản scan: ngưỡng đo 21/10 (tesseract 5.5.0 + vie 4.1.0) trên đúng 4 bản scan đầu, không áp cho bản thêm sau
TSV_MIN = {"symbol": 3, "issued_on": 4, "type_code": 4, "issuer_name": 3, "summary": 4}
TSV_BASE = ("11-cong-van-anh-300dpi.jpg", "12-quyet-dinh-anh-mo.jpg", "13-thong-bao-ban-scan.pdf", "14-giay-moi-xam.png")
# cả 7 bản scan, đo 22/10 (cùng tesseract): 20 đọc số ký hiệu "07/CĐÐ-UBND", 21 lấy "Chi Nhánh Cần Thơ" làm cơ quan.
# Số tuyệt đối trên đúng 7 bản: thêm bản scan thì test đỏ để chốt lại ngưỡng, không âm thầm nới
TSV_ALL = 7
TSV_ALL_MIN = {"symbol": 5, "issued_on": 7, "type_code": 7, "issuer_name": 5, "summary": 7}

pytestmark = pytest.mark.skipif(not (SAMPLES / "nhan.json").is_file(), reason="không có seed/van-ban-den (image)")


def labels() -> list[dict]:
    return json.loads((SAMPLES / "nhan.json").read_text(encoding="utf-8"))["samples"]


def same(field: str, got: str, want: str) -> bool:
    """So như kịch bản đo: số ký hiệu bỏ khoảng trắng, không phân biệt hoa thường; cơ quan gộp khoảng trắng."""
    if field == "symbol":
        return re.sub(r"\s+", "", got).casefold() == re.sub(r"\s+", "", want).casefold()
    if field == "issuer_name":
        return " ".join(got.split()).casefold() == " ".join(want.split()).casefold()
    return got == want


def words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def overlap(got: str, want: str) -> float:
    """Tỉ lệ từ của nhãn có trong gợi ý."""
    return len(words(got) & words(want)) / max(len(words(want)), 1)


def score(results: list[tuple[str, dict, Suggestion]]) -> dict:
    """Mỗi trường: đúng / sai (điền mà khác — tệ hơn bỏ trống) / trống; nhãn rỗng (loại chưa có trong danh mục, không
    có dấu độ khẩn) mà không gợi ý là đúng. Trích yếu: có gợi ý / trùng ≥ 60% từ với nhãn. Riêng các trường high."""
    table = {f: {"đúng": 0, "sai": 0, "trống": 0, "high": 0, "high_sai": 0} for f in FIELDS}
    table["summary"] = {"có": 0, "khớp": 0, "high": 0, "high_sai": 0}
    wrong: list[str] = []
    for name, want, got in results:
        for f in FIELDS:
            expected = want.get(f)
            if f == "urgency" and expected == "normal":
                expected = None
            field = got.fields.get(f)
            if field is None:
                table[f]["đúng" if expected is None else "trống"] += 1
                continue
            ok = expected is not None and same(f, field.value, expected)
            table[f]["đúng" if ok else "sai"] += 1
            if field.confidence == "high":
                table[f]["high"] += 1
                if not ok:
                    table[f]["high_sai"] += 1
                    wrong.append(f"{name}: {f} = {field.value!r} (high), nhãn {expected!r}")
        summary = got.fields.get("summary")
        if summary is not None:
            table["summary"]["có"] += 1
            ok = overlap(summary.value, want["summary"]) >= 0.6
            table["summary"]["khớp"] += ok
            if summary.confidence == "high":
                table["summary"]["high"] += 1
                if not ok:
                    table["summary"]["high_sai"] += 1
                    wrong.append(f"{name}: summary = {summary.value!r} (high), nhãn {want['summary']!r}")
    return {"n": len(results), "table": table, "wrong": wrong}


def report(title: str, measured: dict) -> str:
    n, t = measured["n"], measured["table"]
    rows = [f"### {title} — {n} tệp", "| trường | đúng | sai | trống | high (sai) |", "|---|---|---|---|---|"]
    rows += [f"| {f} | {t[f]['đúng']}/{n} | {t[f]['sai']} | {t[f]['trống']} | {t[f]['high']} ({t[f]['high_sai']}) |"
             for f in FIELDS]
    s = t["summary"]
    rows.append(f"| summary | có {s['có']}/{n}, trùng ≥ 60% từ {s['khớp']}/{n} | | | {s['high']} ({s['high_sai']}) |")
    return "\n".join(rows)


def read_text_pdf(data: bytes) -> list[str]:
    """Như pdflayout.py: pypdf theo bố cục (lỗi thì cách thường), tối đa 3 trang."""
    from pypdf import PdfReader

    texts = []
    for page in PdfReader(io.BytesIO(data)).pages[:3]:
        try:
            texts.append(page.extract_text(extraction_mode="layout"))
        except Exception:  # noqa: BLE001 — như bản chạy thật: lỗi bố cục thì lấy chữ thường
            texts.append(page.extract_text())
    return texts


def test_text_pdfs_meet_the_thresholds():
    results = []
    for sample in labels():
        if sample["kind"] != "text":
            continue
        got = suggest(text_lines(read_text_pdf((SAMPLES / sample["file"]).read_bytes())), today=TODAY,
                      type_codes=CATALOG)
        results.append((sample["file"], sample["fields"], got))
    n = len(results)
    assert n >= 15, f"nhan.json chỉ có {n} PDF có lớp chữ"
    measured = score(results)
    print("\n" + report("PDF có lớp chữ (quy tắc, không mô hình)", measured))
    t = measured["table"]
    for f, minimum in TEXT_MIN.items():
        got = t[f]["có"] if f == "summary" else t[f]["đúng"]
        assert 100 * got >= minimum * n, f"{f}: {got}/{n} < {minimum} %\n" + report("PDF có lớp chữ", measured)
    assert not measured["wrong"], "trường high sai:\n" + "\n".join(measured["wrong"])


def test_ocr_fixtures_if_present():
    fixtures = {p.stem: p for p in FIXTURES.glob("*.tsv")} if FIXTURES.is_dir() else {}
    scans = [s for s in labels() if s["kind"] == "scan"]
    if not any(pathlib.Path(s["file"]).stem in fixtures for s in scans):
        pytest.skip("chưa có TSV Tesseract của bản scan (make van-ban-mau khi image svc-files có tesseract)")
    # đã có TSV thì phải đủ cho mọi bản scan trong nhãn: thiếu một tệp không được làm ngưỡng tự tắt
    missing = [s["file"] for s in scans if pathlib.Path(s["file"]).stem not in fixtures]
    assert not missing, f"thiếu TSV của {missing} (make van-ban-mau)"
    results = []
    for sample in scans:
        tsv = fixtures[pathlib.Path(sample["file"]).stem].read_text(encoding="utf-8")
        results.append((sample["file"], sample["fields"], suggest(tsv_lines([tsv]), today=TODAY, type_codes=CATALOG)))
    every = score(results)
    print("\n" + report("Bản scan (TSV Tesseract)", every))
    assert every["n"] == TSV_ALL, f"{every['n']} bản scan, ngưỡng TSV_ALL_MIN chốt cho {TSV_ALL}: đo lại rồi chốt lại"
    for f, minimum in TSV_ALL_MIN.items():
        got = every["table"][f]["có"] if f == "summary" else every["table"][f]["đúng"]
        assert got >= minimum, f"{f}: {got}/{TSV_ALL} < {minimum}\n" + report("Bản scan", every)
    base = score([r for r in results if r[0] in TSV_BASE])
    assert base["n"] == len(TSV_BASE)
    print(report("Bản scan 11–14 (có ngưỡng)", base))
    for f, minimum in TSV_MIN.items():
        got = base["table"][f]["có"] if f == "summary" else base["table"][f]["đúng"]
        assert got >= minimum, f"{f}: {got}/{len(TSV_BASE)} < {minimum}\n" + report("Bản scan 11–14", base)


def test_samples_are_small_fictional_and_leak_no_local_path():
    names = sorted(p.name for p in SAMPLES.iterdir())
    listed = [s["file"] for s in labels()]
    assert sorted(listed + ["nhan.json"]) == names
    assert len(listed) >= 20, f"{len(listed)} văn bản mẫu: \"Hoàn thành khi\" của Phase 4 đo trên ít nhất 20"
    assert sum(p.stat().st_size for p in SAMPLES.iterdir()) <= 3 * 1024 * 1024
    for name in listed:
        data = (SAMPLES / name).read_bytes()
        # thư mục nhà ghép từ tên để chính tệp test không chứa chuỗi đường dẫn máy
        for marker in (*(f"/{d}/".encode() for d in ("home", "Users", "tmp")), b"C:\\", b"file://"):
            assert marker not in data, f"{name} chứa {marker!r}"
        if name.endswith(".pdf"):
            from pypdf import PdfReader

            meta = PdfReader(io.BytesIO(data)).metadata or {}
            assert set(meta) <= {"/Producer", "/Title", "/CreationDate", "/ModDate"}, meta
            assert not any("/" in str(meta.get(k, "")) for k in ("/Title",)), meta
    for sample in labels():
        assert {"type_code", "symbol", "issued_on", "issuer_name", "urgency", "summary"} == set(sample["fields"])
        assert "Mẫu" in sample["fields"]["issuer_name"] or sample["fields"]["issuer_name"] in (
            "Phòng Đào tạo", "Khoa Công nghệ thông tin")      # đơn vị của Trường Đại học Mẫu
