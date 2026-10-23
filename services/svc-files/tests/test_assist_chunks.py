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

"""Cắt đoạn (F4.2): văn bản nào được vào chỉ mục, đoạn theo trang, độ dài, chồng, đoạn meta, thuộc tính quyền, sha."""

from __future__ import annotations

import copy

import pytest

from conftest import TENANT_A
from svc_files.assist.chunks import (
    CHUNK_MAX,
    MAX_CHUNKS,
    MIN_CHARS,
    OVERLAP,
    _tail,
    build,
    eligible,
    embed_input,
    meta_text,
    meta_update,
    pages,
    sentence_starts,
    split_page,
)
from svc_files.pdftext import join_pages

DOC = "d0000000-0000-4000-8000-000000000001"


def sentences(tag: str, n: int) -> list[str]:
    return [f"Khoản {i} {tag} quy định sinh viên nộp hồ sơ xét học bổng trước ngày {i % 28 + 1}/11/2026."
            for i in range(1, n + 1)]


def text(*page_lines: list[str], status: str = "ok") -> dict:
    """Chữ của một tệp như core.file_texts: các trang nối bằng \\n, page_starts như pdftext."""
    content, starts = join_pages(["\n".join(lines) for lines in page_lines])
    return {"status": status, "pages": len(page_lines), "content": content,
            "page_starts": starts if status == "ok" else None, "extracted_at": "2026-10-21T08:00:00+00:00"}


def link(file_text: dict | None, *, role: str = "main", file_id: str = "f0000000-0000-4000-8000-00000000000a",
         encrypted: bool = False) -> dict:
    return {"role": role, "file_id": file_id, "file": {"encrypted": encrypted, "text": file_text}}


def source(*files: dict, **cols) -> dict:
    return {
        "id": DOC, "tenant_id": str(TENANT_A), "direction": "in", "status": "registered", "type_code": "CV",
        "symbol": "88/CTSV", "issuer_name": "Phòng Công tác sinh viên", "issued_on": "2026-10-15",
        "summary": "Về việc xét học bổng khuyến khích học tập", "restricted": False, "department_id": None,
        "created_by": "u-van-thu", "updated_at": "2026-10-21T08:00:00+00:00", "document_type": {"name": "Công văn"},
        "assignments": [], "files": list(files), **cols,
    }


# --- điều kiện --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("direction", "status", "ok"), [
    *[("in", s, True) for s in ("received", "registered", "in_progress", "done", "archived")],
    ("in", "cancelled", False),
    *[("out", s, False) for s in ("draft", "in_review", "returned", "approved", "cancelled")],
    ("out", "issued", True), ("out", "archived", True),
])
def test_eligibility_by_direction_and_status(direction, status, ok):
    doc = source(link(text(sentences("A", 3))), direction=direction, status=status)
    assert eligible(doc) is ok
    assert bool(build(doc)) is ok
    assert eligible({**doc, "restricted": True}) is False and build({**doc, "restricted": True}) == []


# --- trang ------------------------------------------------------------------------------------------------------


def test_chunks_follow_pages_and_never_cross_them():
    t = text(sentences("TRANGMOT", 30), ["Chỉ trang hai: hội đồng họp tại phòng 301 nhà A1 vào thứ Hai hằng tuần."],
             sentences("TRANGBA", 12))
    chunks = build(source(link(t)))
    assert {c["page"] for c in chunks} == {1, 2, 3}
    markers = {1: "TRANGMOT", 2: "phòng 301", 3: "TRANGBA"}
    for c in chunks:
        assert c["kind"] == "page" and c["file_role"] == "main"
        assert markers[c["page"]] in c["text"]
        assert all(m not in c["text"] for p, m in markers.items() if p != c["page"])
        assert c["id"] == f"{DOC}_{c['file_id']}_{c['page']:03d}_{c['seq']:02d}"
    assert [c["seq"] for c in chunks if c["page"] == 2] == [1]
    assert len({c["id"] for c in chunks}) == len(chunks)


def test_rows_without_page_starts_are_one_page_without_number():
    t = {**text(sentences("CU", 3)), "page_starts": None}
    chunks = build(source(link(t)))
    assert [(c["page"], c["seq"]) for c in chunks] == [(None, 1)]
    assert chunks[0]["id"].endswith("_000_01")
    assert pages("abc", [0, 5]) == [(None, "abc")]          # page_starts sai (vượt độ dài): cũng coi là một trang
    assert pages("abc", [1]) == [(None, "abc")]
    assert pages("ab\ncd", [0, 3]) == [(1, "ab\n"), (2, "cd")]


def test_every_chunk_fits_even_for_long_lines():
    long_line = " ".join(sentences("DAI", 40))                     # một dòng ~3 500 ký tự, nhiều câu
    no_stop = " ".join(["chuoi chu khong co dau cau"] * 200)        # không có ranh giới câu: cắt ở khoảng trắng
    no_space = "x" * 3000                                           # không có cả khoảng trắng: cắt cứng
    chunks = build(source(link(text([long_line], [no_stop], [no_space, *sentences("SAU", 25)]))))
    assert chunks and all(len(c["text"]) <= CHUNK_MAX for c in chunks)
    assert all(len(c["text"]) - sum(ch.isspace() for ch in c["text"]) >= MIN_CHARS for c in chunks)
    first = [c["text"] for c in chunks if c["page"] == 1]
    assert len(first) >= 4 and all(t.rstrip().endswith(".") for t in first)   # cắt ở ranh giới câu


def test_consecutive_chunks_overlap_by_the_last_sentence():
    body = split_page("\n".join(sentences("CHONG", 40)))
    assert len(body) >= 3
    for prev, nxt in zip(body, body[1:], strict=False):
        tail = _tail(prev)
        assert tail and len(tail) <= OVERLAP and prev.endswith(tail)
        assert nxt.startswith(tail)
        assert tail == prev.split("\n")[-1]                 # câu cuối (mỗi câu một dòng)


def test_tiny_fragments_are_dropped():
    assert split_page("- 2 -\nNơi nhận:") == []
    assert split_page("\n".join(sentences("NGAN", 1))) != []
    chunks = build(source(link(text(sentences("A", 2), ["- 2 -"]))))
    assert {c["page"] for c in chunks} == {1}


def test_at_most_max_chunks_per_document():
    t = text(*[sentences(f"P{i}", 30) for i in range(200)])
    chunks = build(source(link(t)))
    assert len(chunks) == MAX_CHUNKS


def test_sentences_do_not_split_abbreviations_numbers_or_symbols():
    line = ("Điểm trung bình từ 3,2 trở lên. ThS. Nguyễn Văn A tại TP. Hồ Chí Minh nhận 3.2 điểm theo 88/CTSV. "
            "Hạn nộp 15/11/2026; Phòng họp tầng 3.")
    starts = sentence_starts(line)
    parts = [line[a:b].strip() for a, b in zip([0, *starts], [*starts, len(line)], strict=False)]
    assert parts == ["Điểm trung bình từ 3,2 trở lên.",
                     "ThS. Nguyễn Văn A tại TP. Hồ Chí Minh nhận 3.2 điểm theo 88/CTSV.",
                     "Hạn nộp 15/11/2026;", "Phòng họp tầng 3."]


# --- tệp ----------------------------------------------------------------------------------------------------------


def test_files_in_order_main_attachment_issued_and_encrypted_skipped():
    files = [
        link(text(sentences("PHATHANH", 2)), role="issued", file_id="f-issued"),
        link(text(sentences("KEMHAI", 2)), role="attachment", file_id="f-kem-2"),
        link(text(sentences("CHINH", 2)), role="main", file_id="f-main"),
        link(text(sentences("MATMA", 2)), role="attachment", file_id="f-ma", encrypted=True),
        link(text(sentences("NHAP", 2)), role="draft", file_id="f-draft"),
        link(text(sentences("KEMBA", 2)), role="attachment", file_id="f-kem-3"),
    ]
    chunks = build(source(*files))
    assert [c["file_id"] for c in chunks] == ["f-main", "f-kem-2", "f-kem-3", "f-issued"]
    assert [c["file_role"] for c in chunks] == ["main", "attachment", "attachment", "issued"]
    assert not any("MATMA" in c["text"] or "NHAP" in c["text"] for c in chunks)


@pytest.mark.parametrize("files", [
    [],                                                                   # chưa có tệp
    [link(None)],                                                         # chưa đọc chữ
    [link(text([], status="empty"))],                                     # bản scan
    [link({"status": "failed", "pages": None, "content": "", "page_starts": None})],
    [link(text(sentences("MAT", 3)), encrypted=True)],                    # tệp mã hóa
    [link(text(["Trang 1"]))],                                            # chữ quá ít
])
def test_one_meta_chunk_when_no_page_chunk(files):
    chunks = build(source(*files))
    assert len(chunks) == 1
    meta = chunks[0]
    assert (meta["id"], meta["kind"], meta["file_id"], meta["file_role"], meta["page"]) == \
        (f"{DOC}_meta", "meta", None, None, None)
    assert meta["text"] == ("Công văn số 88/CTSV ngày 15/10/2026 của Phòng Công tác sinh viên: "
                            "Về việc xét học bổng khuyến khích học tập")


def test_meta_text_skips_missing_parts():
    assert meta_text({"type_code": "TB", "summary": "Lịch nghỉ Tết"}) == "TB: Lịch nghỉ Tết"
    assert meta_text({"document_type": {"name": "Thông báo"}, "issued_on": "2026-11-02"}) == "Thông báo ngày 02/11/2026"


def test_outgoing_document_uses_its_issued_copy():
    doc = source(link(text(sentences("PHATHANH", 3)), role="issued", file_id="f-issued"), direction="out",
                 status="issued", issuer_name=None, department_id="dep-dt", created_by="u-chuyen-vien")
    chunks = build(doc)
    assert {c["file_role"] for c in chunks} == {"issued"} and chunks[0]["direction"] == "out"


# --- thuộc tính quyền, sha --------------------------------------------------------------------------------------


def test_permission_attributes_come_from_document_and_live_assignments():
    doc = source(link(text(sentences("A", 3))), department_id="dep-ktpm", created_by="u-tao", assignments=[
        {"department_id": "dep-dt", "user_id": None, "assigned_at": "2026-10-20T01:00:00+00:00"},
        {"department_id": "dep-dt", "user_id": "u-b", "assigned_at": "2026-10-20T01:00:00+00:00"},
        {"department_id": None, "user_id": "u-a", "assigned_at": "2026-10-20T01:00:00+00:00"},
        {"department_id": "dep-huy", "user_id": "u-huy", "assigned_at": "2026-10-20T01:00:00+00:00",
         "status": "cancelled"},
    ])
    for c in build(doc):
        assert (c["department_id"], c["created_by"]) == ("dep-ktpm", "u-tao")
        assert c["assignee_departments"] == ["dep-dt"] and c["assignee_users"] == ["u-a", "u-b"]
        assert c["tenant_id"] == str(TENANT_A) and c["year"] == 2026 and c["document_id"] == DOC
        assert "_vectors" not in c and "embed_model" not in c


def test_shas_are_stable_and_split_text_from_filters():
    doc = source(link(text(sentences("A", 30), sentences("B", 3))))
    first = build(doc)
    assert first == build(copy.deepcopy(doc))
    assert all(len(c["text_sha"]) == 16 and len(c["meta_sha"]) == 16 for c in first)

    assigned = build({**doc, "assignments": [{"department_id": "dep-dt", "user_id": None,
                                              "assigned_at": "2026-10-21T09:00:00+00:00"}], "status": "in_progress"})
    assert [c["text_sha"] for c in assigned] == [c["text_sha"] for c in first]
    assert all(a["meta_sha"] != b["meta_sha"] for a, b in zip(assigned, first, strict=True))

    renamed = build({**doc, "summary": "Về việc khác"})
    assert all(a["text_sha"] != b["text_sha"] for a, b in zip(renamed, first, strict=True))

    edited = copy.deepcopy(doc)
    edited["files"][0]["file"]["text"] = text(sentences("A", 30), sentences("C", 3))
    changed = {c["id"] for c, o in zip(build(edited), first, strict=True) if c["text_sha"] != o["text_sha"]}
    assert changed and all(c.endswith(("_002_01", "_002_02")) for c in changed)


def test_meta_update_carries_only_filters():
    chunk = build(source(link(text(sentences("A", 3)))))[0]
    upd = meta_update(chunk)
    assert set(upd) == {"id", "tenant_id", "direction", "status", "type_code", "year", "department_id", "created_by",
                        "assignee_departments", "assignee_users", "issuer_name", "meta_sha"}


def test_embed_input():
    page = {"kind": "page", "symbol": "88/CTSV", "summary": "Về học bổng", "text": "Điều kiện…"}
    assert embed_input(page) == "88/CTSV — Về học bổng\nĐiều kiện…"
    assert embed_input({**page, "symbol": None}) == "Về học bổng\nĐiều kiện…"
    assert embed_input({"kind": "meta", "symbol": "88/CTSV", "summary": "x", "text": "Công văn số 88/CTSV: x"}) == \
        "Công văn số 88/CTSV: x"
