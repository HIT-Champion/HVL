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

"""POST /api/documents/ask qua hai đường dữ liệu (#441): ``viec_cua_toi`` đếm Hộp việc, ``dem_van_ban`` đếm văn bản —
bằng token người hỏi, không tìm, không gọi mô hình, câu có số và "Căn cứ", ``data`` và ``link``; sổ kiểm toán, nhật
ký không có chữ câu hỏi hay tên việc. Dùng lại fixture ``asking`` của test_assist_api.py."""

from __future__ import annotations

import json
from datetime import date

import pytest

from assist_fakes import FakeOllama, ollama
from conftest import TENANT_A
from test_assist_api import ask, asking, demo  # noqa: F401 (asking là fixture)

TODAY = date(2026, 10, 30)
ME = "u-van-thu"                # sub mặc định của ask_token


def answered(env, question: str, **body) -> dict:
    env.assistant._today = lambda: TODAY
    r = ask(env, env.token(), question=question, **body)
    assert r.status_code == 200, r.text
    return r.json()


def task(n: int, due: str | None, document_id: str = "d-x", name: str = "Xử lý văn bản đến") -> dict:
    return {"id": f"t-{n}", "name": name, "document_id": document_id, "due_on": due}


@pytest.fixture
def inbox(asking):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake))
    fake.requests.clear()
    readable = env.hasura.add_document(TENANT_A, "Về lịch thi", symbol="88/CTSV")
    hidden = env.hasura.add_document(TENANT_A, "Hồ sơ nhân sự", symbol="12/TCCB", readers={"u-khac"})
    env.hasura.tasks[ME] = [
        task(1, "2026-10-27", readable),                      # quá 3 ngày
        task(2, "2026-10-30", hidden, "Duyệt văn bản đi"),    # hôm nay; văn bản không được đọc: không có số ký hiệu
        task(3, "2026-11-01"),                                # còn 2 ngày
        task(4, "2026-11-20"),
        task(5, None),
    ]
    env.fake = fake
    return env


@pytest.mark.parametrize("mode", ["extract", "generate"])
def test_my_tasks_are_counted_from_the_inbox_without_search_or_model(inbox, mode):
    body = answered(inbox, "Việc nào của tôi sắp quá hạn?", mode=mode)
    assert (body["route"], body["route_reason"], body["status"]) == ("viec_cua_toi", "kw:viec-cua-toi", "answered")
    assert body["answer"]["source"] == "data" and body["answer"]["model"] is None and body["extract"] is None
    assert body["sources"] == [] and body["link"] == "/"
    assert body["data"] == {"kind": "tasks", "on": "2026-10-30", "tasks": 5, "overdue": 1, "today": 1, "soon": 1,
                            "no_due": 1}
    text = body["answer"]["text"]
    assert text.startswith("Hộp việc của bạn có 5 việc đang chờ: 1 quá hạn, 1 đến hạn hôm nay, 1 đến hạn trong 2 ngày")
    assert "Gần hạn nhất: Xử lý văn bản đến 88/CTSV (quá 3 ngày); Duyệt văn bản đi (hạn hôm nay); " in text
    assert "12/TCCB" not in text and "Căn cứ: Hộp việc của bạn trên Signet ngày 30/10/2026" in text
    assert inbox.retriever.calls == [] and inbox.fake.requests == []
    assert [c["op"] for c in inbox.hasura.data_calls] == ["myTasks"]
    assert inbox.hasura.ask_calls[-1]["by"] == "token"                    # số ký hiệu: hậu kiểm bằng token người hỏi


def test_an_empty_inbox_says_so_and_english_questions_get_english(inbox):
    inbox.hasura.tasks[ME] = []
    body = answered(inbox, "Tôi có bao nhiêu việc quá hạn?")
    assert body["answer"]["text"].startswith("Hộp việc của bạn không có việc nào đang chờ. Căn cứ:")
    assert body["data"]["tasks"] == 0 and inbox.hasura.ask_calls == []
    english = answered(inbox, "Which of my tasks are almost overdue?")
    assert english["route"] == "viec_cua_toi" and english["answer"]["text"].startswith("Your inbox has no open tasks.")


@pytest.fixture
def documents(asking):
    env = asking(passages=demo())
    add = env.hasura.add_document
    add(TENANT_A, "a", registered_at="2026-10-05T09:00:00+07:00")
    add(TENANT_A, "b", registered_at="2026-09-30T17:30:00+00:00", type_code="QĐ")     # 01/10 00:30 giờ Việt Nam
    add(TENANT_A, "c", registered_at="2026-09-30T16:30:00+00:00")                     # 30/09 23:30 giờ Việt Nam
    add(TENANT_A, "d", registered_at="2026-10-06T09:00:00+07:00", readers={"u-khac"})  # không được xem
    add(TENANT_A, "e", registered_at=None)                                            # chưa vào sổ
    add(TENANT_A, "f", direction="out", status="issued", issued_on="2026-10-12")
    add(TENANT_A, "g", direction="out", status="draft", issued_on=None)
    return env


def test_incoming_documents_are_counted_by_registration_time_in_vietnam(documents):
    body = answered(documents, "Có bao nhiêu văn bản đến trong tháng 10?")
    assert (body["route"], body["status"], body["answer"]["source"]) == ("dem_van_ban", "answered", "data")
    assert body["data"] == {"kind": "documents", "counts": {"in": 2}, "type_code": None, "from": "2026-10-01",
                            "to": "2026-11-01"}
    assert body["link"] == "/van-ban-den" and body["sources"] == []
    assert body["answer"]["text"] == ("Có 2 văn bản đến trong tháng 10/2026. Căn cứ: các văn bản bạn được xem trên "
                                      "Signet; văn bản đến tính theo ngày vào sổ, văn bản đi theo ngày ban hành (giờ "
                                      "Việt Nam).")
    (call,) = documents.hasura.data_calls
    assert call["op"] == "count" and call["sub"] == ME and documents.retriever.calls == []


def test_without_a_direction_both_are_counted_and_types_narrow_the_count(documents):
    both = answered(documents, "Có bao nhiêu văn bản?")
    assert both["data"]["counts"] == {"in": 4, "out": 2} and both["link"] is None
    assert both["answer"]["text"].startswith("Có 4 văn bản đến và 2 văn bản đi. Căn cứ: các văn bản bạn được xem")
    typed = answered(documents, "Có bao nhiêu quyết định đến trong tháng này?")
    assert typed["data"]["counts"] == {"in": 1} and typed["data"]["type_code"] == "QĐ"
    english = answered(documents, "How many outgoing documents were there this month?")
    assert english["answer"]["text"].startswith("There is 1 outgoing document this month (October 2026). Basis:")


def test_a_count_follow_up_is_counted_for_the_new_month(documents):
    body = answered(documents, "Còn tháng 9 thì sao?", previous="Có bao nhiêu văn bản đến trong tháng 10?")
    assert body["rewritten"] == "Có bao nhiêu văn bản đến trong tháng 9" and body["route"] == "dem_van_ban"
    assert body["data"]["counts"] == {"in": 1}


def test_audit_and_log_record_the_route_not_the_question_or_task_names(inbox, log_records):
    answered(inbox, "Việc nào của tôi sắp quá hạn?")
    (event,) = inbox.hasura.agent_events
    diff = event["diff"]
    assert (diff["route"], diff["answer_source"], diff["status"], diff["hits"]) == ("viec_cua_toi", "data",
                                                                                   "answered", 0)
    assert diff["documents"] == ""
    (done,) = [x for x in log_records if x["event"] == "office.assist.asked"]
    assert done["route"] == "viec_cua_toi"
    dumped = json.dumps([event, done], ensure_ascii=False)
    assert "quá hạn" not in dumped and "88/CTSV" not in dumped and "Xử lý" not in dumped


def test_a_rejected_token_is_401_and_a_database_error_is_503(inbox, log_records):
    inbox.hasura.reject_tokens = True
    inbox.assistant._today = lambda: TODAY
    r = ask(inbox, inbox.token(), question="Việc nào của tôi sắp quá hạn?")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_token"
    inbox.hasura.reject_tokens, inbox.hasura.down = False, True
    r = ask(inbox, inbox.token(), question="Có bao nhiêu văn bản đến trong tháng 10?")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"
    assert [x["route"] for x in log_records if x["event"] == "office.assist.count_failed"] == ["dem_van_ban"]
    assert inbox.hasura.agent_events == []                                # không trả lời thì không ghi sổ


def test_in_a_document_scope_a_count_question_searches_that_document(documents):
    from test_assist_api import D88
    body = answered(documents, "Có bao nhiêu văn bản đến trong tháng 10?", document_id=D88)
    assert body["route"] == "van_ban" and body["data"] is None and body["link"] is None
    assert documents.hasura.data_calls == []
