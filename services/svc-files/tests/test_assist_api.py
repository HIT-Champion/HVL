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

"""POST /api/documents/ask (F4.2): quyền, câu hỏi, câu trích, mô hình, sổ kiểm toán của trợ lý, lỗi.

Truy xuất (luồng B) được thay bằng Retriever giả có hậu kiểm theo người đọc; Ollama giả qua MockTransport. Test này
kiểm luồng trả lời: đoạn nào tới được người dùng và mô hình, sổ ghi gì, lỗi nào trả mã nào.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from assist_fakes import (
    CHAT_MODEL, DIMS, DOC_88, EMBED_MODEL, PAGE_88, QUESTION, QUOTE, AskHasura, FakeIndexer, FakeOllama,
    FakeRetriever, ask_token, good_answer, ollama, passage,
)
from conftest import ISSUER, TENANT_A
from svc_files.app import create_app
from svc_files.assist import answer as answer_module
from svc_files.assist.ai import NullAi
from svc_files.assist.answer import Assistant
from svc_files.config import Settings
from svc_files.hasura import HasuraAuthError, HasuraError
from svc_files.search import SearchError

ENV = {
    "MOC_OIDC_ISSUER": ISSUER, "MOC_OIDC_JWKS_URL": "http://unused/jwks", "SEAWEEDFS_S3_ACCESS_KEY": "test",
    "SEAWEEDFS_S3_SECRET_KEY": "test", "HASURA_ADMIN_SECRET": "test", "MEILISEARCH_API_KEY": "test",
    "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0",
    "MOC_IMPORT_INTERVAL_S": "0",     # vòng nền nạp lô tắt (không tạo thư mục spool)
    "MOC_ARCHIVE_INTERVAL_S": "0", "MOC_FILES_MAX_MB": "1", "MOC_AI_URL": "",
    "MOC_AI_EMBED_DIMS": str(DIMS),
}
DIFF_KEYS = {"user_id", "ask_id", "mode", "status", "answer_source", "hits", "cited", "documents", "semantic",
             "model", "embed_model", "duration_ms", "warnings"}
DEPT_DT = "5cc372aa-304d-4574-896c-4f3e781a2ce7"
D88 = "8c1d2e3f-0000-4000-8000-000000000088"
D_MAT = "8c1d2e3f-0000-4000-8000-0000000000ff"
SECRET = "Phương án XANH LAM bố trí kinh phí 450.000.000 đồng cho đề án mật."


@pytest.fixture
def asking(scanner, store, verifier, meili, vault, signing_key):
    """make(env=…, passages=…, ai=…) → SimpleNamespace(client, hasura, retriever, indexer, token(...))."""
    clients = []

    def make(*, env=None, passages=None, ai=None, readers=None, restricted=()) -> SimpleNamespace:
        settings = Settings.from_env({**ENV, **(env or {})})
        hasura = AskHasura()
        retriever = FakeRetriever(list(passages or []), dict(readers or {}), set(restricted))
        indexer = FakeIndexer()
        ai = ai or NullAi()
        assistant = Assistant(settings, retriever=retriever, ai=ai, indexer=indexer, hasura=hasura)
        app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                         vault=vault, assistant=assistant, chunk_indexer=indexer, ai=ai)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return SimpleNamespace(client=client, hasura=hasura, retriever=retriever, indexer=indexer,
                               assistant=assistant, token=lambda **kw: ask_token(signing_key, **kw))

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def ask(env: SimpleNamespace, token: str | None, **body):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return env.client.post("/api/documents/ask", headers=headers, json={"question": QUESTION, **body})


def demo(**kw):
    return [passage(PAGE_88, document_id=D88, **kw)]


# --- trả lời bằng câu trích --------------------------------------------------------------------------------------


def test_extract_answers_with_a_verbatim_quote_and_its_source(asking):
    env = asking(passages=demo())
    r = ask(env, env.token())
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["status"] == "answered" and body["semantic"] is False and body["ai_available"] is False
    assert body["answer"] == {"text": f"“{QUOTE}” [1]", "source": "extract", "model": None}
    assert body["extract"] == body["answer"] and body["warnings"] == []
    (src,) = body["sources"]
    assert src["n"] == 1 and src["document_id"] == D88 and src["symbol"] == "88/CTSV" and src["page"] == 1
    assert src["type_name"] == "Công văn" and src["issuer_name"] == "Phòng Công tác sinh viên"
    assert src["kind"] == "page" and src["file_role"] == "main" and src["cited"] is True
    assert src["issued_on"] == "2026-10-15" and src["status"] == "in_progress" and src["direction"] == "in"
    assert "3,2" in src["excerpt"] and len(src["excerpt"]) <= 600 and "\n" not in src["excerpt"]
    uuid.UUID(body["ask_id"])
    # câu tìm cho Meilisearch: term của câu hỏi, chữ gốc, không từ dừng
    (call,) = env.retriever.calls
    assert call["q"] == "Điều kiện xét học bổng khuyến khích tập" and call["vector"] is None and call["limit"] == 5
    assert call["scope"].tenant_id == TENANT_A and call["scope"].where == () and call["scope"].token
    assert env.indexer.holds == []              # không gọi mô hình nào: không giữ vòng nhúng nền


def test_extract_without_any_model_never_calls_ollama(asking):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake, chat=None, embed=None))
    fake.requests.clear()
    assert ask(env, env.token()).json()["status"] == "answered"
    assert fake.requests == []


def test_extract_with_an_embedding_model_searches_by_meaning_and_never_chats(asking):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake))
    body = ask(env, env.token()).json()
    assert body["semantic"] is True and body["ai_available"] is True and body["answer"]["source"] == "extract"
    assert fake.calls("/api/chat") == []
    (embed,) = [c for c in fake.calls("/api/embed") if c["input"] != ["Mộc"]]     # bỏ lần nạp trước
    assert embed["model"] == EMBED_MODEL and embed["input"][0].endswith("Query: " + QUESTION)
    assert len(env.retriever.calls[0]["vector"]) == DIMS


def test_embedding_failure_falls_back_to_keywords(asking):
    fake = FakeOllama(embed_status=500)
    env = asking(passages=demo(), ai=ollama(fake))
    body = ask(env, env.token()).json()
    assert body["status"] == "answered" and body["semantic"] is False and body["warnings"] == ["embed_unavailable"]
    assert env.retriever.calls[0]["vector"] is None


def test_no_question_embedding_while_meilisearch_has_no_embedder(asking):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake))
    env.indexer.embedder_ready = False
    body = ask(env, env.token()).json()
    assert body["status"] == "answered" and body["semantic"] is False and body["warnings"] == ["embed_unavailable"]
    assert env.retriever.calls[0]["vector"] is None and env.indexer.holds == []


def test_hybrid_search_failure_answers_by_keywords_with_a_warning(asking, log_records):
    env = asking(passages=demo(), ai=ollama(FakeOllama()))
    env.retriever.hybrid_error = "Meilisearch trả 400: invalid_search_embedder Cannot find embedder"
    r = ask(env, env.token())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "answered" and body["semantic"] is False and body["warnings"] == ["embed_unavailable"]
    assert env.retriever.calls[0]["vector"] is not None         # đã nhúng câu hỏi, Meilisearch chưa tìm lai được
    diff = env.hasura.agent_events[0]["diff"]
    assert (diff["semantic"], diff["embed_model"], diff["warnings"]) == (False, None, "embed_unavailable")
    (failed,) = [x for x in log_records if x["event"] == "office.assist.search_failed"]
    assert failed["fallback"] == "keywords" and "invalid_search_embedder" in failed["error"]


def test_passages_without_a_short_answer(asking):
    env = asking(passages=[passage("Danh mục tài liệu kèm theo gồm năm phụ lục về cơ sở vật chất.")])
    body = ask(env, env.token()).json()
    assert body["status"] == "passages_only" and body["answer"] is None and body["extract"] is None
    assert len(body["sources"]) == 1 and body["sources"][0]["cited"] is False


def test_filters_and_scope_reach_the_retriever(asking):
    env = asking(passages=demo())
    token = env.token(sub="u-chuyen-vien", role="staff", department=DEPT_DT)
    assert ask(env, token, direction="in", year=2026, type_code="CV").status_code == 200
    call = env.retriever.calls[0]
    f = call["filters"]
    assert (f.direction, f.year, f.type_code) == ("in", 2026, "CV")
    assert call["scope"].where and "u-chuyen-vien" in call["scope"].where[0]


def test_document_scope_and_the_whole_question_reach_the_retriever(asking, log_records):
    env = asking(passages=demo())
    assert ask(env, env.token(), document_id=D88.upper()).status_code == 200
    call = env.retriever.calls[0]
    # id chuẩn hóa (chữ thường) trước khi vào bộ lọc; nguyên câu hỏi để chọn tỷ trọng nghĩa (câu tìm đã bỏ ngoặc kép)
    assert call["filters"].document_id == D88 and call["question"] == QUESTION
    (done,) = [r for r in log_records if r["event"] == "office.assist.asked"]
    assert done["scoped"] is True and "ratio" in done
    assert ask(env, env.token()).status_code == 200
    assert env.retriever.calls[1]["filters"].document_id is None


# --- quyền ---------------------------------------------------------------------------------------------------------


def test_needs_a_token(asking):
    env = asking(passages=demo())
    r = ask(env, None)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "missing_token"


@pytest.mark.parametrize("role", ["tenant_admin", "verifier", "agent"])
def test_roles_without_documents_are_403_before_any_search(asking, role):
    env = asking(passages=demo())
    r = ask(env, env.token(role=role))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "forbidden"
    assert env.retriever.calls == [] and env.hasura.agent_events == []


def test_no_evidence_when_every_passage_is_forbidden_and_the_model_gets_nothing(asking):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake), readers={D88: {"u-chuyen-vien-dt"}})
    token = env.token(sub="u-giang-vien-ktpm", role="staff")
    for mode in ("extract", "generate"):
        r = ask(env, token, mode=mode)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "no_evidence" and body["sources"] == [] and body["answer"] is None
        assert body["extract"] is None and body["warnings"] == []
        assert "88/CTSV" not in r.text and "3,2" not in r.text
    assert fake.calls("/api/chat") == []
    assert [e["diff"]["status"] for e in env.hasura.agent_events] == ["no_evidence", "no_evidence"]
    assert all(e["diff"]["documents"] == "" for e in env.hasura.agent_events)


def test_restricted_documents_never_reach_anyone(asking):
    secret = passage(SECRET, document_id=D_MAT, symbol="01/MẬT")
    env = asking(passages=[secret], restricted={D_MAT})
    for role in ("clerk", "director"):
        body = ask(env, env.token(role=role), question="Phương án XANH LAM bố trí kinh phí bao nhiêu?").json()
        assert body["status"] == "no_evidence" and "XANH" not in json.dumps(body, ensure_ascii=False)


def test_generate_sends_only_post_checked_passages_to_the_model(asking):
    fake = FakeOllama()
    forbidden = passage(SECRET + " Điều kiện xét học bổng khuyến khích học tập đặc biệt.", document_id=D_MAT,
                        symbol="02/MẬT")
    env = asking(passages=[forbidden, *demo()], ai=ollama(fake), readers={D_MAT: {"u-truong-khoa"}})
    r = ask(env, env.token(), mode="generate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "answered" and body["answer"]["source"] == "model"
    assert body["answer"]["model"] == CHAT_MODEL
    assert body["answer"]["text"].endswith("[1].") and body["extract"]["source"] == "extract"
    assert [s["symbol"] for s in body["sources"]] == ["88/CTSV"] and body["sources"][0]["cited"] is True
    (chat,) = fake.calls("/api/chat")
    sent = json.dumps(chat, ensure_ascii=False)
    assert "XANH LAM" not in sent and "02/MẬT" not in sent and "3,2" in sent
    assert chat["model"] == CHAT_MODEL and chat["think"] is False and chat["stream"] is False
    assert chat["options"]["num_predict"] == 320 and chat["format"]["required"] == ["du_can_cu", "tra_loi"]
    assert chat["messages"][1]["content"].count("<nguon ") == 1


def test_model_answer_without_citations_is_cited_by_the_server(asking):
    # đầu ra thật của qwen3:1.7b: đúng nội dung, không ghi [n]
    fake = FakeOllama(reply=good_answer("Điều kiện xét học bổng khuyến khích học tập là điểm trung bình chung học kỳ "
                                        "từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt."))
    env = asking(passages=demo(), ai=ollama(fake))
    body = ask(env, env.token(), mode="generate").json()
    assert body["answer"]["source"] == "model" and body["answer"]["text"].endswith("đạt loại Tốt [1].")
    assert body["warnings"] == [] and body["sources"][0]["cited"] is True
    assert env.hasura.agent_events[0]["diff"]["cited"] == 1
    (chat,) = fake.calls("/api/chat")
    assert "ngoặc vuông" not in chat["messages"][0]["content"]


def test_generate_without_a_model_returns_the_quote(asking):
    env = asking(passages=demo())
    body = ask(env, env.token(), mode="generate").json()
    assert body["answer"]["source"] == "extract" and body["warnings"] == ["model_unavailable"]
    assert env.hasura.agent_events[0]["diff"]["model"] is None


async def _slow(request):
    await asyncio.sleep(3)
    return good_answer()


@pytest.mark.parametrize(("reply", "warning"), [
    (_slow, "model_timeout"),
    ("khong phai json", "model_rejected"),
    (good_answer("Sinh viên cần điểm từ 3,5 trở lên [1]."), "model_rejected"),       # số không có trong nguồn
    (good_answer("Sinh viên phải nộp giấy khám sức khỏe và bản sao hộ chiếu [1]."), "model_rejected"),   # ý bịa
    (json.dumps({"du_can_cu": False, "tra_loi": ""}), "model_declined"),
], ids=["cham", "khong-phai-json", "so-bia", "y-bia", "tu-choi"])
def test_model_failures_keep_the_quote(asking, reply, warning):
    fake = FakeOllama(reply=reply)
    env = asking(env={"MOC_ASK_MODEL_TIMEOUT_S": "0.3"}, passages=demo(), ai=ollama(fake))
    body = ask(env, env.token(), mode="generate").json()
    assert body["status"] == "answered" and body["warnings"] == [warning]
    assert body["answer"] == {"text": f"“{QUOTE}” [1]", "source": "extract", "model": None}
    diff = env.hasura.agent_events[0]["diff"]
    assert diff["answer_source"] == "extract" and diff["model"] == CHAT_MODEL and diff["warnings"] == warning


def test_model_is_skipped_when_the_deadline_is_near(asking):
    fake = FakeOllama()
    env = asking(env={"MOC_ASK_DEADLINE_S": "4"}, passages=demo(), ai=ollama(fake))
    assert ask(env, env.token(), mode="generate").json()["warnings"] == ["model_timeout"]
    assert fake.calls("/api/chat") == []


def test_background_embedding_is_held_only_while_ollama_is_called(asking):
    async def slow(request):
        await asyncio.sleep(0.5)
        return good_answer()

    ai = ollama(FakeOllama(reply=slow))
    env = asking(passages=demo(), ai=ai)
    seen: list[tuple[str, int]] = []        # (bước, số khối giữ đang mở lúc bắt đầu bước)

    def watch(step, call):
        async def watched(*args, **kwargs):
            seen.append((step, env.indexer.active))
            return await call(*args, **kwargs)
        return watched

    ai.embed, ai.chat = watch("embed", ai.embed), watch("chat", ai.chat)
    env.retriever.search = watch("search", env.retriever.search)
    assert ask(env, env.token()).status_code == 200            # câu trích: chỉ nhúng câu hỏi
    assert seen == [("embed", 1), ("search", 0)] and env.indexer.holds == [answer_module.HOLD_S]
    seen.clear()
    env.indexer.holds.clear()
    assert ask(env, env.token(), mode="generate").json()["answer"]["source"] == "model"
    # giữ suốt từng lời gọi Ollama (cả 0,5 giây sinh), không giữ lúc truy xuất; mỗi lời gọi xong nhường thêm HOLD_S
    assert seen == [("embed", 1), ("search", 0), ("chat", 1)] and env.indexer.active == 0
    assert env.indexer.holds == [answer_module.HOLD_S] * 2 and answer_module.HOLD_S <= 5


def test_busy_is_503_with_retry_after_only_for_generate(asking):
    env = asking(env={"MOC_ASK_QUEUE_S": "0.2"}, passages=demo())
    slots = env.assistant.slots
    asyncio.run(slots.acquire())                 # lượt sinh duy nhất đang bận
    try:
        r = ask(env, env.token(), mode="generate")
        assert ask(env, env.token()).status_code == 200            # câu trích không phải chờ lượt
    finally:
        slots.release()
    assert r.status_code == 503 and r.json()["detail"]["code"] == "busy" and r.headers["retry-after"] == "10"
    assert ask(env, env.token(), mode="generate").status_code == 200


# --- người hỏi ngắt kết nối (nút "Dừng", Esc, đóng trang) -------------------------------------------------------


def _post(app, token: str, body: dict, gone: asyncio.Event):
    """Gọi thẳng ứng dụng ASGI (qua middleware thật của app.py) như một trình duyệt: gửi thân yêu cầu, rồi ngắt kết
    nối khi ``gone`` bật. TestClient không ngắt được giữa chừng. Trả (coroutine, các tin đã gửi về)."""
    raw = json.dumps(body).encode()
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/api/documents/ask", "raw_path": b"/api/documents/ask", "query_string": b"", "root_path": "",
             "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"),
                         (b"content-length", str(len(raw)).encode()), (b"authorization", f"Bearer {token}".encode())],
             "client": ("127.0.0.1", 50000), "server": ("testserver", 80)}
    pending = [{"type": "http.request", "body": raw, "more_body": False}]
    sent: list[dict] = []

    async def receive() -> dict:
        if pending:
            return pending.pop()
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    return app(scope, receive, send), sent


def test_disconnect_cancels_the_model_call_frees_the_slot_and_writes_no_audit_row(
        scanner, store, verifier, meili, vault, signing_key, log_records):
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        held: list[int] = []

        async def endless(request):
            held.append(indexer.active)
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()                 # httpx đóng kết nối: Ollama thật dừng sinh
                raise
            return good_answer()

        fake = FakeOllama(reply=endless)
        ai = ollama(fake, probe=False)
        await ai.probe()
        settings = Settings.from_env(ENV)
        hasura, indexer = AskHasura(), FakeIndexer()
        assistant = Assistant(settings, retriever=FakeRetriever(demo()), ai=ai, indexer=indexer, hasura=hasura)
        app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                         vault=vault, assistant=assistant, chunk_indexer=indexer, ai=ai)
        token = ask_token(signing_key)

        gone = asyncio.Event()
        call, sent = _post(app, token, {"question": QUESTION, "mode": "generate"}, gone)
        call = asyncio.create_task(call)
        await asyncio.wait_for(started.wait(), 5)
        assert assistant.slots.locked()                         # lượt sinh duy nhất đang bận
        gone.set()
        await asyncio.wait_for(call, 5)
        assert cancelled.is_set() and not assistant.slots.locked()
        assert held == [1] and indexer.active == 0              # giữ vòng nền suốt lời gọi; bị hủy thì thôi giữ
        assert sent[0]["status"] == 499 and hasura.agent_events == []

        # lượt kế tiếp không phải chờ hàng 20 giây
        fake.reply = good_answer()
        call, sent = _post(app, token, {"question": QUESTION, "mode": "generate"}, asyncio.Event())
        await asyncio.wait_for(call, 5)
        assert sent[0]["status"] == 200
        assert [e["diff"]["answer_source"] for e in hasura.agent_events] == ["model"]
        assert indexer.active == 0                              # không lượt nào để lại khối giữ đang mở
        await ai.aclose()

    asyncio.run(scenario())
    (gone,) = [r for r in log_records if r["event"] == "office.assist.ask_cancelled"]
    assert gone["mode"] == "generate" and "duration_ms" in gone
    assert [r["event"] for r in log_records if r["event"] == "office.assist.asked"] == ["office.assist.asked"]


# --- câu hỏi -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("question", ["", "   \n ", "là gì vậy?", "Có phải không ạ?", "x" * 501,
                                      "Điều kiện\x00 học bổng", "Hạn nộp\x1b[31m hồ sơ"],
                         ids=["rong", "trang", "tu-dung", "tu-dung-2", "qua-dai", "nul", "esc"])
def test_invalid_questions_are_400(asking, question):
    env = asking(passages=demo())
    r = ask(env, env.token(), question=question)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_question"
    assert env.retriever.calls == [] and env.hasura.agent_events == []


def test_newlines_and_invisible_characters_are_normalized_not_rejected(asking):
    env = asking(passages=demo())
    r = ask(env, env.token(), question="Điều kiện xét\nhọc bổng khuyến​ khích học tập?")
    assert r.status_code == 200 and r.json()["status"] == "answered"


@pytest.mark.parametrize("body", [
    {"mode": "tom-tat"}, {"year": 1999}, {"type_code": "CV/QĐ"}, {"direction": "ngang"}, {"ask_id": "khong-phai"},
    {"cau_hoi": "thừa khóa"}, {"question": 42}, {"document_id": "khong-phai"},
])
def test_malformed_bodies_are_422(asking, body):
    env = asking(passages=demo())
    assert ask(env, env.token(), **body).status_code == 422


def test_assistant_can_be_switched_off(asking):
    env = asking(env={"MOC_ASK_ENABLED": "false"}, passages=demo())
    r = ask(env, env.token())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "assistant_disabled"


# --- lỗi phía sau ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("error", "status", "code"), [
    (SearchError("Meilisearch tắt"), 503, "search_unavailable"),
    (HasuraError("Hasura tắt"), 503, "database_unavailable"),
    (HasuraAuthError("JWTExpired", "invalid-jwt"), 401, "invalid_token"),
])
def test_backend_errors(asking, error, status, code):
    env = asking(passages=demo())
    env.retriever.fail = error
    r = ask(env, env.token())
    assert r.status_code == status and r.json()["detail"]["code"] == code
    assert env.hasura.agent_events == []


def test_no_answer_without_an_audit_row(asking):
    env = asking(passages=demo())
    env.hasura.fail_agent = True
    r = ask(env, env.token())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"
    assert "3,2" not in r.text and "88/CTSV" not in r.text


# --- sổ kiểm toán, nhật ký ---------------------------------------------------------------------------------------


def test_one_agent_audit_row_without_question_or_answer(asking):
    fake = FakeOllama()
    env = asking(passages=demo(), ai=ollama(fake))
    r = ask(env, env.token(sub="u-van-thu"), mode="generate")
    body = r.json()
    (event,) = env.hasura.agent_events
    assert event["actor_id"] == "moc-assistant" and event["actor_kind"] == "agent"
    assert event["tenant_id"] == str(TENANT_A) and event["action"] == "assistant.answered"
    assert event["entity"] == "ai.questions" and event["entity_id"] == body["ask_id"]
    assert event["request_id"] == r.headers["x-request-id"]
    assert set(event["diff"]) == DIFF_KEYS
    assert event["diff"] == {
        "user_id": "u-van-thu", "ask_id": body["ask_id"], "mode": "generate", "status": "answered",
        "answer_source": "model", "hits": 1, "cited": 1, "documents": D88, "semantic": True, "model": CHAT_MODEL,
        "embed_model": EMBED_MODEL, "duration_ms": body["duration_ms"], "warnings": "",
    }
    assert not any(isinstance(v, list | dict) for v in event["diff"].values())    # giao diện hiểu mảng là [cũ, mới]
    dumped = json.dumps(event, ensure_ascii=False)
    for leak in ("học bổng", "hoc bong", "3,2", "88/CTSV", "Tốt", "Điều kiện"):
        assert leak not in dumped
    (call,) = [c for c in env.hasura.agent_calls if c["op"] == "GhiSoTroLy"]
    assert call["role"] == "agent" and call["user_id"] == "moc-assistant"


def test_generate_reuses_the_ask_id_of_the_extract_round(asking):
    env = asking(passages=demo(), ai=ollama(FakeOllama()))
    first = ask(env, env.token()).json()
    second = ask(env, env.token(), mode="generate", ask_id=first["ask_id"]).json()
    assert second["ask_id"] == first["ask_id"]
    assert [e["entity_id"] for e in env.hasura.agent_events] == [first["ask_id"]] * 2
    assert [e["diff"]["mode"] for e in env.hasura.agent_events] == ["extract", "generate"]


def test_logs_have_no_question_or_document_text(asking, log_records):
    env = asking(passages=demo(), ai=ollama(FakeOllama(reply="khong phai json")))
    assert ask(env, env.token(), mode="generate").status_code == 200
    (done,) = [r for r in log_records if r["event"] == "office.assist.asked"]
    assert {"tenant_id", "actor_id", "mode", "status", "q_length", "terms", "candidates", "hits", "cited",
            "semantic", "model", "warnings", "duration_ms"} <= set(done)
    assert done["terms"] == 8 and done["hits"] == 1 and done["q_length"] == len(QUESTION)
    (rejected,) = [r for r in log_records if r["event"] == "office.assist.model_rejected"]
    assert rejected["reason"] == "bad_json"
    dumped = json.dumps(log_records, ensure_ascii=False)
    for leak in ("học bổng", "3,2", "88/CTSV", "khong phai json"):
        assert leak not in dumped


# --- app -----------------------------------------------------------------------------------------------------------


def test_readyz_reports_the_assistant_without_changing_readiness(asking):
    r = asking().client.get("/readyz")
    assert r.status_code == 200 and r.json()["assist"] == {"index": True, "semantic": False, "model": False,
                                                           "embed_pending": None, "embed_failed": None}
    r = asking(ai=ollama(FakeOllama(models=[EMBED_MODEL]))).client.get("/readyz")
    assert r.json()["assist"] == {"index": True, "semantic": True, "model": False, "embed_pending": None,
                                  "embed_failed": None} and r.json()["status"] == "ready"


def test_route_is_in_the_openapi_document(asking):
    op = asking().client.get("/openapi.json").json()["paths"]["/api/documents/ask"]["post"]
    assert {"400", "401", "403", "422", "503"} <= set(op["responses"])


def test_default_app_builds_the_assistant(settings, scanner, store, verifier, hasura, meili, vault):
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                     vault=vault)
    # không có MOC_AI_URL: không mô hình nào, chỉ tìm theo từ khóa
    assert isinstance(app.state.ai, NullAi) and app.state.assistant.retriever.embedder is None
    assert app.state.assistant.retriever.candidates == 24 and app.state.assistant.retriever.per_doc == 2
    with_ai = Settings.from_env({**ENV, "MOC_AI_URL": "http://ollama:11434"})
    app = create_app(with_ai, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                     vault=vault)
    assert app.state.assistant.retriever.embedder == "emb_qwen3_embedding_0_6b"
    # truy xuất và vòng nhúng nền dùng cùng một tên embedder
    assert app.state.chunk_indexer.embedder == app.state.assistant.retriever.embedder


def test_settings_build_an_ollama_client_when_there_is_an_url():
    from svc_files.assist.ai import OllamaAi, make_ai

    ai = make_ai(Settings.from_env({**ENV, "MOC_AI_URL": "http://ollama:11434", "MOC_ASK_MODEL": "qwen3:4b"}))
    assert isinstance(ai, OllamaAi) and ai.chat_model == "qwen3:4b" and ai.embed_model == EMBED_MODEL
    asyncio.run(ai.aclose())
    ai = make_ai(Settings.from_env({**ENV, "MOC_AI_URL": "http://ollama:11434", "MOC_AI_EMBED_MODEL": ""}))
    assert ai.embed_model is None and ai.chat_model == "qwen3:1.7b"
    asyncio.run(ai.aclose())


# --- nối với chỉ mục đoạn và truy xuất thật (luồng B) -------------------------------------------------------------


def test_end_to_end_with_the_real_chunk_index_and_retriever(scanner, store, verifier, meili, vault, signing_key):
    """Từ chữ PDF trong Hasura giả → vòng đồng bộ đoạn → Meilisearch giả → hậu kiểm bằng token → câu trích. Chạy khi
    đã có bản của luồng B (``FakeChunkIndex`` trong conftest, ``chunk_sources``/``ask_documents`` của FakeHasura)."""
    import conftest

    if not hasattr(conftest, "FakeChunkIndex") or not hasattr(conftest.FakeHasura, "ask_documents"):
        pytest.skip("cần chỉ mục đoạn giả và hậu kiểm giả của luồng B (tests/conftest.py)")
    from svc_files.assist.index import ChunkIndexer
    from svc_files.assist.retrieve import Retriever

    at = "2026-10-21T08:00:00+00:00"
    hasura = AskHasura()

    def add(content: str, *, readers=None, **cols) -> str:
        text = {"status": "ok", "pages": 1, "content": content, "page_starts": [0], "extracted_at": at}
        files = [{"role": "main", "file_id": str(uuid.uuid4()), "added_at": at,
                  "file": {"encrypted": False, "text": text}}]
        return hasura.add_document(TENANT_A, cols.pop("summary", DOC_88["summary"]), readers=readers, files=files,
                                   assignments=[], updated_at=at, document_type={"name": "Công văn"}, **cols)

    d88 = add(PAGE_88, symbol="88/CTSV", issuer_name="Phòng Công tác sinh viên")
    hidden = add(f"Điều kiện xét học bổng khuyến khích học tập đặc biệt. {SECRET}", readers={"u-khac"},
                 symbol="99/MAT", summary="Về việc học bổng đặc biệt")
    fake = FakeOllama()
    ai = ollama(fake)
    index = conftest.FakeChunkIndex()
    indexer = ChunkIndexer(index, hasura, ai, dims=DIMS)
    asyncio.run(indexer.sync_once())
    asyncio.run(indexer.embed_once())
    asyncio.run(indexer.count())          # như cuối mỗi vòng nền (vòng nền của app cũng chạy, đếm ra cùng số)
    settings = Settings.from_env(ENV)
    assistant = Assistant(settings, retriever=Retriever(index, hasura, embedder=indexer.embedder), ai=ai,
                          indexer=indexer, hasura=hasura)
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                     vault=vault, assistant=assistant, chunk_indexer=indexer, ai=ai)
    with TestClient(app) as client:
        r = client.post("/api/documents/ask", headers={"Authorization": f"Bearer {ask_token(signing_key)}"},
                        json={"question": QUESTION})
        nobody = client.post("/api/documents/ask", json={"question": QUESTION}, headers={
            "Authorization": f"Bearer {ask_token(signing_key, sub='u-tp', role='manager')}"})
        ready = client.get("/readyz").json()["assist"]
        searched = len(index.searches)
        # hỏi trong một văn bản: văn bản được đọc, văn bản không được đọc (lọc trước cho qua, hậu kiểm bỏ)
        mine, other = (client.post("/api/documents/ask", headers={"Authorization": f"Bearer {ask_token(signing_key)}"},
                                   json={"question": QUESTION, "document_id": doc}) for doc in (d88, hidden))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "answered" and body["semantic"] is True and body["answer"]["source"] == "extract"
    assert body["answer"]["text"] == f"“{QUOTE}” [1]"
    assert [(x["document_id"], x["symbol"], x["page"], x["file_role"]) for x in body["sources"]] == [
        (d88, "88/CTSV", 1, "main")]
    assert "XANH LAM" not in r.text and "450.000.000" not in r.text
    # văn bản không được đọc đã qua lọc trước (clerk) nhưng bị hậu kiểm bằng token người hỏi loại ra
    by_token = [c for c in hasura.ask_calls if c["by"] == "token"]
    assert by_token and hidden in by_token[0]["ids"] and by_token[0]["sub"] == "u-van-thu"
    # cùng embedder ở vòng nhúng nền và lượt hỏi; véc-tơ câu hỏi có tiền tố chỉ dẫn
    search = index.searches[0]
    assert search["hybrid"]["embedder"] == "emb_qwen3_embedding_0_6b" and len(search["vector"]) == DIMS
    assert fake.calls("/api/embed")[-1]["input"][0].startswith("Instruct: ")
    # quản lý không có phòng: không gọi Meilisearch, không có căn cứ
    assert nobody.json()["status"] == "no_evidence" and searched == 1
    assert ready == {"index": True, "semantic": True, "model": True, "embed_pending": 0, "embed_failed": 0}
    assert mine.json()["status"] == "answered" and [x["document_id"] for x in mine.json()["sources"]] == [d88]
    assert index.searches[searched]["filter"][-1] == f'document_id = "{d88}"'
    assert other.json()["status"] == "no_evidence" and other.json()["sources"] == []
    assert "XANH LAM" not in other.text and "99/MAT" not in other.text
