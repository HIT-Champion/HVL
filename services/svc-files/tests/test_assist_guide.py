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

"""Kho tĩnh của trợ lý (assist/guide.py, #423): tách mục Markdown, tìm trong hướng dẫn sử dụng thật của repo
(docs/huong-dan), tệp Giới thiệu trợ lý đủ mục ở cả hai ngôn ngữ và nói đúng mô hình mặc định."""

from __future__ import annotations

import dataclasses
import pathlib

import pytest

from svc_files.assist import grounding, guide, route
from svc_files.config import Settings

ROOT = pathlib.Path(__file__).resolve().parents[3]
GUIDES = ROOT / "docs" / "huong-dan"


@pytest.fixture(scope="module")
def store() -> guide.GuideStore:
    return guide.GuideStore.load(GUIDES)


def test_parse_splits_sections_and_keeps_fixed_anchors():
    md = ("# Tài liệu\n\nLời mở đầu của tệp.\n\n## Đơn nghỉ phép {#don-nghi}\n\nVào **Đơn nghỉ phép**, bấm "
          "[Tạo đơn](../x.md).\n\n![ảnh](anh/a.png)\n\n### Hủy đơn\n\n| Bước | Việc |\n|---|---|\n| 1 | Mở đơn |\n\n"
          "```\nmã bỏ qua\n```\n<!-- ghi chú bỏ qua -->\n## Trống\n\n")
    sections = guide.parse(md, name="viec-chung", path="docs/huong-dan/viec-chung.md")
    assert [(s.title, s.anchor) for s in sections] == [
        ("Tài liệu", "tài-liệu"), ("Đơn nghỉ phép", "don-nghi"), ("Hủy đơn", "hủy-đơn")]
    lead, leave, cancel = sections
    assert lead.text == "Lời mở đầu của tệp." and lead.doc_title == "Tài liệu"
    assert leave.text == "Vào Đơn nghỉ phép, bấm Tạo đơn." and leave.path == "docs/huong-dan/viec-chung.md#don-nghi"
    assert cancel.text == "Bước; Việc. 1; Mở đơn." and "mã bỏ qua" not in cancel.text
    assert leave.key == "viec-chung#don-nghi" and not leave.intro


def test_the_repo_user_guides_load_with_unique_keys(store):
    assert len(store.guides) >= 30
    assert len({s.key for s in store.guides}) == len(store.guides)
    assert {s.path.split("#")[0] for s in store.guides} >= {f"docs/huong-dan/{p.name}" for p in GUIDES.glob("*.md")
                                                             if p.name != "README.md"}


@pytest.mark.parametrize(("question", "expected"), [
    ("Nộp đơn nghỉ phép ở đâu?", "nghỉ phép"),
    ("Đổi mật khẩu ở đâu?", "mật khẩu"),
    ("Làm thế nào để ký số văn bản đi?", "ký"),
])
def test_how_to_questions_find_a_matching_guide_section(store, question, expected):
    found = store.search(question, 5)
    assert found, question
    top = found[0]
    assert top.kind == "guide" and top.document_id.startswith("guide:") and top.file_id is None
    assert expected in f"{top.doc['summary']} {top.text}".lower()
    assert top.doc["path"].startswith("docs/huong-dan/") and top.doc["type_name"] == "Hướng dẫn sử dụng"
    assert [p.score for p in found] == sorted((p.score for p in found), reverse=True)


def test_unrelated_questions_find_nothing_in_the_guides(store):
    assert store.search("Điều kiện xét học bổng khuyến khích học tập", 5) == []
    assert store.search("", 5) == []


def test_without_the_guide_folder_only_the_intro_is_there(tmp_path, caplog):
    empty = guide.GuideStore.load(tmp_path / "khong-co")
    assert empty.guides == [] and empty.search("Nộp đơn nghỉ phép ở đâu?", 5) == []
    assert empty.intro("kw:lam-duoc-gi", "vi") and "guides_missing" in caplog.text


@pytest.mark.parametrize("lang", ["vi", "en"])
def test_the_intro_file_has_every_section_the_router_points_to(store, lang):
    anchors = {a for (lng, a) in store.intros if lng == lang}
    assert anchors >= {*guide.INTRO_SECTIONS.values(), *guide.INTRO_ORDER, guide.INTRO_DEFAULT, guide.OUT_OF_SCOPE}
    for code, code_lang, _ in route._INTRO:
        found = store.intro(f"kw:{code}", lang)
        main = guide.INTRO_SECTIONS.get(code, guide.INTRO_DEFAULT)
        assert found[0].chunk_id.endswith(f"#{main}"), code
        assert len(found) == len(guide.INTRO_ORDER) + (main not in guide.INTRO_ORDER)
        assert all(p.kind == "guide" and p.doc["type_name"] == guide.INTRO_TYPE[lang] for p in found)
        assert code_lang in ("vi", "en")


def test_the_intro_answer_is_its_first_sentences(store):
    (main, *_) = store.intro("kw:lam-duoc-gi", "vi")
    first = guide.lead(main)
    assert first.startswith("Tôi tìm trong các văn bản bạn được xem") and first in main.text
    assert first.count(". ") <= guide.LEAD_SENTENCES


def test_out_of_scope_text_is_fixed_per_language(store):
    assert store.fixed("vi").startswith("Câu này nằm ngoài phạm vi của tôi.")
    assert store.fixed("en").startswith("This question is outside what I can answer.")
    assert store.fixed("fr") == store.fixed("vi")


def test_the_intro_states_the_default_models_and_limits():
    # tệp giới thiệu là nguồn của câu trả lời: sai mô hình, sai giới hạn là trợ lý tự nói sai về mình
    defaults = {f.name: f.default for f in dataclasses.fields(Settings)}
    ask_model, embed_model = defaults["ask_model"], defaults["ai_embed_model"]
    names = {"qwen3:1.7b": "Qwen3-1.7B", "qwen3-embedding:0.6b": "Qwen3-Embedding-0.6B"}
    assert ask_model in names and embed_model in names
    for lang, limit in (("vi", f"tối đa {grounding.MAX_SOURCES} đoạn"), ("en", f"at most {grounding.MAX_SOURCES}")):
        text = (guide.INTRO_DIR / f"{lang}.md").read_text(encoding="utf-8")
        assert names[ask_model] in text and names[embed_model] in text, lang
        assert limit in text and "Apache-2.0" in text and "Ollama" in text, lang


def test_guide_sources_have_no_document_and_name_their_file(store):
    (p, *_) = store.search("Nộp đơn nghỉ phép ở đâu?", 5)
    src = guide.source(2, p, "đoạn trích", True)
    assert src["document_id"] is None and src["kind"] == "guide" and src["n"] == 2 and src["cited"] is True
    assert src["path"] == p.doc["path"] and src["summary"] == p.doc["summary"] and src["file_id"] is None
