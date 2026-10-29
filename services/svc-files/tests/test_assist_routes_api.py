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

"""POST /api/documents/ask qua bộ định tuyến (#423): gioi_thieu, ngoai_pham_vi không tìm văn bản, không gọi mô hình;
huong_dan trả lời từ hướng dẫn sử dụng; câu nối tiếp ghép với ``previous``; sổ kiểm toán, nhật ký ghi đường mà không
có chữ câu hỏi. Dùng lại fixture ``asking`` của test_assist_api.py."""

from __future__ import annotations

import json
import pathlib

import pytest

from assist_fakes import CHAT_MODEL, FakeOllama, ollama
from test_assist_api import D88, ask, asking, demo  # noqa: F401 (asking là fixture)

GUIDES = str(pathlib.Path(__file__).resolve().parents[3] / "docs" / "huong-dan")


def routed(env, question: str, **body) -> dict:
    r = ask(env, env.token(), question=question, **body)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("mode", ["extract", "generate"])
def test_what_can_you_do_answers_from_the_intro_without_search_or_model(asking, mode):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake))
    fake.requests.clear()
    body = routed(env, "Bạn làm được gì?", mode=mode)
    assert (body["route"], body["route_reason"], body["rewritten"]) == ("gioi_thieu", "kw:lam-duoc-gi", None)
    assert body["status"] == "answered" and body["answer"]["source"] == "extract" and body["answer"]["model"] is None
    text = body["answer"]["text"]
    assert text.startswith("“Tôi tìm trong các văn bản bạn được xem") and text.endswith("” [1]")
    first, *rest = body["sources"]
    assert first["kind"] == "guide" and first["document_id"] is None and first["cited"] is True
    assert first["path"].endswith("gioi_thieu/vi.md#lam-duoc-gi") and first["type_name"] == "Giới thiệu trợ lý"
    assert rest and not any(s["cited"] for s in rest)
    assert env.retriever.calls == [] and fake.requests == []         # không tìm, không nhúng, không gọi mô hình
    assert body["semantic"] is False and body["warnings"] == []


def test_greetings_and_english_get_the_matching_intro(asking):
    env = asking(passages=demo())
    hello = routed(env, "Xin chào")
    assert hello["route_reason"] == "kw:xin-chao" and hello["answer"]["text"].startswith("“Tôi là trợ lý hỏi đáp")
    english = routed(env, "What can you do?")
    assert english["route"] == "gioi_thieu" and english["answer"]["text"].startswith("“I search the documents")
    assert english["sources"][0]["type_name"] == "About the assistant"
    model = routed(env, "Trợ lý này dùng mô hình nào?")
    assert "Qwen3-1.7B" in model["sources"][0]["excerpt"] or "Qwen3-1.7B" in model["answer"]["text"]


@pytest.mark.parametrize(("question", "lang_start"), [
    ("Thời tiết Hà Nội hôm nay thế nào?", "Câu này nằm ngoài phạm vi của tôi."),
    ("Write me a poem", "This question is outside what I can answer."),
])
def test_out_of_scope_gets_a_fixed_answer_and_no_search(asking, question, lang_start):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake))
    fake.requests.clear()
    body = routed(env, question, mode="generate")
    assert body["route"] == "ngoai_pham_vi" and body["status"] == "no_evidence" and body["sources"] == []
    assert body["answer"] == {"text": body["answer"]["text"], "source": "fixed", "model": None}
    assert body["answer"]["text"].startswith(lang_start) and body["extract"] is None
    assert env.retriever.calls == [] and fake.requests == []
    (event,) = env.hasura.agent_events
    assert event["diff"]["answer_source"] == "fixed" and event["diff"]["hits"] == 0


def test_how_to_questions_answer_from_the_user_guide(asking):
    env = asking(passages=demo(), env={"MOC_ASK_GUIDE_DIR": GUIDES})
    body = routed(env, "Nộp đơn nghỉ phép ở đâu?")
    assert (body["route"], body["route_reason"]) == ("huong_dan", "kw:o-dau")
    assert body["status"] in ("answered", "passages_only") and body["sources"]
    assert all(s["kind"] == "guide" and s["document_id"] is None for s in body["sources"])
    assert body["sources"][0]["path"].startswith("docs/huong-dan/")
    assert "nghỉ phép" in (body["sources"][0]["summary"] + body["sources"][0]["excerpt"]).lower()
    assert env.retriever.calls == []                                   # không tìm trong kho văn bản


def test_how_to_with_a_model_writes_from_guide_passages(asking):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake), env={"MOC_ASK_GUIDE_DIR": GUIDES})
    body = routed(env, "Nộp đơn nghỉ phép ở đâu?", mode="generate")
    assert body["route"] == "huong_dan"
    (chat,) = fake.calls("/api/chat")
    sent = json.dumps(chat, ensure_ascii=False)
    assert chat["model"] == CHAT_MODEL and "nghỉ phép" in sent and "88/CTSV" not in sent


def test_how_to_without_the_guide_folder_has_no_evidence(asking):
    env = asking(passages=demo(), env={"MOC_ASK_GUIDE_DIR": "/khong-co/huong-dan"})
    body = routed(env, "Nộp đơn nghỉ phép ở đâu?")
    assert body["route"] == "huong_dan" and body["status"] == "no_evidence" and body["sources"] == []


def test_a_follow_up_is_spliced_with_the_previous_question(asking, log_records):
    env = asking(passages=demo())
    body = routed(env, "Còn khoa Kinh tế thì sao?", previous="Điều kiện xét học bổng khoa CNTT là gì?")
    assert body["route"] == "van_ban" and body["rewritten"] == "Điều kiện xét học bổng khoa Kinh tế là gì"
    (call,) = env.retriever.calls
    assert "Kinh tế" in call["q"] and "học bổng" in call["q"] and "Còn" not in call["q"]
    (event,) = env.hasura.agent_events
    assert event["diff"]["followup"] is True and event["diff"]["route"] == "van_ban"
    (done,) = [x for x in log_records if x["event"] == "office.assist.asked"]
    assert done["followup"] is True
    dumped = json.dumps([event, done], ensure_ascii=False)
    assert "Kinh tế" not in dumped and "CNTT" not in dumped           # không chữ câu hỏi nào vào sổ, nhật ký


@pytest.mark.parametrize("previous", [None, "", "   ", "a\x00b", "Điều kiện " * 60])
def test_a_missing_or_bad_previous_is_ignored(asking, previous):
    env = asking(passages=demo())
    body = routed(env, "Còn khoa Kinh tế thì sao?", previous=previous)
    assert body["rewritten"] is None and body["route"] == "van_ban"
    assert env.hasura.agent_events[0]["diff"]["followup"] is False


def test_a_standalone_question_ignores_previous(asking):
    env = asking(passages=demo())
    body = routed(env, "Điều kiện xét học bổng khuyến khích học tập là gì?", previous="Học phí năm 2026 là bao nhiêu?")
    assert body["rewritten"] is None and body["status"] == "answered" and body["sources"][0]["document_id"] == D88


def test_routes_go_to_the_audit_row_and_the_log_without_the_question(asking, log_records):
    env = asking(passages=demo())
    routed(env, "Bạn làm được gì?")
    (event,) = env.hasura.agent_events
    diff = event["diff"]
    assert (diff["route"], diff["route_reason"], diff["followup"]) == ("gioi_thieu", "kw:lam-duoc-gi", False)
    assert diff["documents"] == "" and diff["answer_source"] == "extract"
    (done,) = [x for x in log_records if x["event"] == "office.assist.asked"]
    assert (done["route"], done["route_reason"]) == ("gioi_thieu", "kw:lam-duoc-gi")
    assert "làm được" not in json.dumps([event, done], ensure_ascii=False)


def test_the_eval_set_takes_its_labelled_route(asking):
    # seed/hoi-dap/cau-hoi.json (make do-hoi-dap đỏ khi đường sai): đường, câu ghép và mục hướng dẫn đều tất định
    data = json.loads((pathlib.Path(GUIDES).parents[1] / "seed" / "hoi-dap" / "cau-hoi.json").read_text("utf-8"))
    env = asking(passages=demo(), env={"MOC_ASK_GUIDE_DIR": GUIDES})
    for q in data["questions"]:
        body = routed(env, q["question"], previous=q.get("previous"))
        assert body["route"] == q["route"], q["id"]
        assert (body["rewritten"] is not None) == (q["loai"] == "noi_tiep"), q["id"]
        guides = [w["guide"] for w in q["expect"] if "guide" in w] if isinstance(q["expect"], list) else []
        if guides:
            paths = [s["path"] for s in body["sources"][:3]]
            assert any(g == p for g in guides for p in paths), (q["id"], paths)
        if q["loai"] == "ngoai_pham_vi":
            assert body["status"] == "no_evidence" and body["answer"]["source"] == "fixed", q["id"]


def test_in_a_document_scope_how_to_words_still_search_that_document(asking):
    env = asking(passages=demo(), env={"MOC_ASK_GUIDE_DIR": GUIDES})
    body = routed(env, "Nộp hồ sơ học bổng ở đâu?", document_id=D88)
    assert body["route"] == "van_ban" and env.retriever.calls[0]["filters"].document_id == D88
