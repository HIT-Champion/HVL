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

"""POST /internal/similar-documents (F4.3): quyền dịch vụ, văn bản đích, câu tìm từ trích yếu, lọc trong Meilisearch,
hậu kiểm, tìm theo nghĩa tùy chọn, lỗi, nhật ký không có chữ.

Truy xuất là ``Retriever`` thật trên chỉ mục đoạn giả (``FakeChunkIndex``, nạp bằng ``ChunkIndexer`` thật) và Hasura
giả; Ollama giả qua MockTransport.
"""

from __future__ import annotations

import asyncio
import json
import logging
import unicodedata
import uuid
from types import SimpleNamespace

import httpx2
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from assist_fakes import DIMS, EMBED_MODEL, FakeIndexer, FakeOllama, ollama
from conftest import ISSUER, TENANT_A, FakeChunkIndex
from svc_files.app import create_app
from svc_files.assist import similar
from svc_files.assist.ai import QUERY_PREFIX, NullAi
from svc_files.assist.answer import Assistant
from svc_files.assist.index import ChunkIndexer
from svc_files.assist.retrieve import Retriever, Similar
from svc_files.assist.scope import NOTHING, Scope, service_scope
from svc_files.assist.similar import SIMILAR_PREFIX, similar_text, subject_text
from svc_files.assist.vi import keyword_query
from svc_files.config import Settings
from svc_files.hasura import HasuraClient, HasuraError
from svc_files.search import SearchError

ENV = {
    "MOC_OIDC_ISSUER": ISSUER, "MOC_OIDC_JWKS_URL": "http://unused/jwks", "SEAWEEDFS_S3_ACCESS_KEY": "test",
    "SEAWEEDFS_S3_SECRET_KEY": "test", "HASURA_ADMIN_SECRET": "test", "MEILISEARCH_API_KEY": "test",
    "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0",
    "MOC_IMPORT_INTERVAL_S": "0",     # vòng nền nạp lô tắt (không tạo thư mục spool)
    "MOC_ARCHIVE_INTERVAL_S": "0", "MOC_FILES_MAX_MB": "1", "MOC_AI_URL": "", "MOC_AI_EMBED_DIMS": str(DIMS),
}
EMB = "emb_qwen3_embedding_0_6b"
TENANT_B = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")
PATH = "/internal/similar-documents"
SUMMARY = "Về việc xét cấp học bổng khuyến khích học tập học kỳ II năm học 2026–2027"
SUBJECT = "xét cấp học bổng khuyến khích học tập học kỳ II năm học 2026–2027"
Q = "xét cấp học bổng khuyến khích tập kỳ II năm"
STATUS_FILTER = 'status IN ["in_progress", "done", "archived"]'


def run(coro):
    return asyncio.run(coro)


class RefusingIndex(FakeChunkIndex):
    """Meilisearch chưa có embedder: mọi câu tìm lai bị từ chối (400), tìm từ khóa vẫn được."""

    async def search(self, body: dict) -> list[dict]:
        if "hybrid" in body:
            self.searches.append(body)
            raise SearchError(f"Meilisearch trả 400: invalid_search_embedder Cannot find embedder with name `{EMB}`.")
        return await super().search(body)


class RecordingAi(NullAi):
    """Mô hình nhúng giả: ghi lại lời gọi; ``vectors=None`` như OllamaAi khi quá giờ."""

    embed_model = EMBED_MODEL
    embed_available = True

    def __init__(self, vectors=None) -> None:
        self.vectors = vectors
        self.calls: list[dict] = []

    async def embed(self, texts, *, query: bool, timeout_s: float):
        self.calls.append({"texts": list(texts), "query": query, "timeout_s": timeout_s})
        return self.vectors


@pytest.fixture
def similar_env(scanner, store, verifier, meili, vault, hasura, make_token):
    """make(env=…, ai=…, index=…, embedder=…) → SimpleNamespace(client, index, indexer, hasura, sync, post)."""
    clients = []

    def make(*, env=None, ai=None, index=None, embedder=None, embedder_ready=True) -> SimpleNamespace:
        settings = Settings.from_env({**ENV, **(env or {})})
        index = index if index is not None else FakeChunkIndex()
        ai = ai or NullAi()
        indexer = FakeIndexer(embedder)
        indexer.embedder_ready = embedder_ready
        retriever = Retriever(index, hasura, embedder=embedder, candidates=settings.ask_candidates,
                              per_doc=settings.ask_per_doc, min_score=settings.ask_min_score,
                              min_score_semantic=settings.ask_min_score_semantic,
                              semantic_ratio=settings.ask_semantic_ratio)
        assistant = Assistant(settings, retriever=retriever, ai=ai, indexer=indexer, hasura=hasura)
        app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                         vault=vault, assistant=assistant, chunk_indexer=indexer, ai=ai)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        service = make_token(azp="svc-workflow", tenant=None)

        def post(document_id, *, token: str | None = service, tenant=TENANT_A, **extra):
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            return client.post(PATH, headers=headers,
                               json={"tenant_id": str(tenant), "document_id": str(document_id), **extra})

        return SimpleNamespace(client=client, index=index, indexer=indexer, hasura=hasura, post=post,
                               service=service, sync=lambda: run(ChunkIndexer(index, hasura).sync_once()))

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def doc(hasura, summary: str, *, tenant=TENANT_A, **cols) -> str:
    """Văn bản không tệp: chỉ mục đoạn có một đoạn "trích yếu" (meta)."""
    return hasura.add_document(tenant, summary, files=[], assignments=[], **cols)


def corpus(hasura) -> SimpleNamespace:
    """Văn bản đích vừa vào sổ + kho văn bản đến: đã giao (tương tự / khác chủ đề) và các văn bản không được ra."""
    return SimpleNamespace(
        target=doc(hasura, SUMMARY, status="registered"),
        d88=doc(hasura, "Về việc xét cấp học bổng khuyến khích học tập học kỳ I năm học 2026–2027",
                status="in_progress", symbol="88/CTSV"),
        d135=doc(hasura, "Về việc xét học bổng khuyến khích cho sinh viên", status="done", symbol="135/ĐT-ĐH"),
        old=doc(hasura, "V/v cấp học bổng năm học 2024–2025", status="archived"),
        other=doc(hasura, "Về việc tổ chức hội thảo phần mềm nguồn mở", status="in_progress"),
        waiting=doc(hasura, "Về việc xét cấp học bổng khuyến khích học tập (chưa giao)", status="registered"),
        outgoing=doc(hasura, "Về việc xét cấp học bổng khuyến khích học tập", direction="out", status="issued"),
        foreign=doc(hasura, "Về việc xét cấp học bổng khuyến khích học tập", tenant=TENANT_B, status="done"),
    )


# --- quyền ------------------------------------------------------------------------------------------------------


def test_only_service_accounts_and_the_route_is_not_public(similar_env, hasura, make_token):
    env = similar_env()
    c = corpus(hasura)
    r = env.post(c.target, token=None)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "missing_token"
    assert r.headers["www-authenticate"] == "Bearer"
    r = env.post(c.target, token="khong-phai-jwt")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_token"
    for token in (make_token(role="director"), make_token(azp="app-office")):
        r = env.post(c.target, token=token)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "not_a_service"
    assert env.index.searches == [] and hasura.ask_calls == []
    assert PATH not in env.client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("extra", [{"limit": 31}, {"limit": 0}, {"limit": "nhieu"}, {"query": "học bổng"},
                                   {"summary": "x"}], ids=["limit-31", "limit-0", "limit-chu", "thua-q", "thua-tom"])
def test_bad_bodies_are_rejected(similar_env, hasura, extra):
    env = similar_env()
    c = corpus(hasura)
    assert env.post(c.target, **extra).status_code == 422
    auth = {"Authorization": f"Bearer {env.service}"}
    assert env.client.post(PATH, headers=auth, json={}).status_code == 422
    assert env.client.post(PATH, headers=auth, json={"tenant_id": "abc", "document_id": c.target}).status_code == 422
    assert env.index.searches == []


# --- văn bản đích ---------------------------------------------------------------------------------------------------


def test_document_of_another_tenant_or_missing_is_not_found(similar_env, hasura):
    env = similar_env()
    c = corpus(hasura)
    for document_id, tenant in ((c.foreign, TENANT_A), (c.target, TENANT_B), (uuid.uuid4(), TENANT_A)):
        r = env.post(document_id, tenant=tenant)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    assert env.index.searches == []


def test_outgoing_document_is_refused(similar_env, hasura):
    env = similar_env()
    c = corpus(hasura)
    r = env.post(c.outgoing)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_incoming"
    assert env.index.searches == []


def test_restricted_document_is_refused_before_any_search_or_model_call(similar_env, hasura):
    fake = FakeOllama()
    ai = ollama(fake, chat=None)
    env = similar_env(ai=ai, embedder=EMB)
    c = corpus(hasura)
    env.sync()
    hasura.documents[c.target]["restricted"] = True
    fake.requests.clear()
    r = env.post(c.target)
    assert r.status_code == 409 and r.json()["detail"] == {
        "code": "restricted", "message": "Văn bản hạn chế không dùng tác tử gợi ý"}
    # không tìm gì thêm: Meilisearch, hậu kiểm, mô hình nhúng đều không được gọi
    assert env.index.searches == [] and env.index.multi_searches == []
    assert hasura.ask_calls == [] and fake.calls("/api/embed") == [] and env.indexer.holds == []


def test_similar_target_reads_with_the_service_role_of_the_requested_tenant():
    seen: list[httpx2.Request] = []

    def reply(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        body = json.loads(request.content)
        row = {"id": body["variables"]["id"], "direction": "in", "restricted": False, "summary": SUMMARY}
        return httpx2.Response(200, json={"data": {"office_documents_by_pk": row if len(seen) == 1 else None}})

    client = HasuraClient("http://hasura:8080", "bi-mat", transport=httpx2.MockTransport(reply))
    document_id = uuid.uuid4()
    got = run(client.similar_target(TENANT_A, document_id, request_id="req-1"))
    assert got == {"id": str(document_id), "direction": "in", "restricted": False, "summary": SUMMARY}
    headers = {k.lower(): v for k, v in seen[0].headers.items()}
    assert headers["x-hasura-admin-secret"] == "bi-mat" and headers["x-hasura-role"] == "service"
    assert headers["x-hasura-tenant-id"] == str(TENANT_A) and headers["x-hasura-user-id"] == "svc-files"
    assert headers["x-hasura-request-id"] == "req-1" and "authorization" not in headers
    query = json.loads(seen[0].content)["query"]
    assert "office_documents_by_pk(id: $id) { id direction restricted summary }" in query
    assert run(client.similar_target(TENANT_A, document_id)) is None       # thuê ước khác: Hasura trả null
    assert {k.lower(): v for k, v in seen[1].headers.items()}["x-hasura-request-id"]    # tự sinh khi không có


# --- câu tìm từ trích yếu ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("summary", "subject"), [
    (SUMMARY, SUBJECT),
    ("V/v: tổ chức hội thảo khoa học sinh viên", "tổ chức hội thảo khoa học sinh viên"),
    ("V/v tổ chức hội thảo khoa học", "tổ chức hội thảo khoa học"),
    ("v/v:nộp đề cương chi tiết", "nộp đề cương chi tiết"),
    ("Thông báo lịch tiếp công dân của UBND phường", "lịch tiếp công dân của UBND phường"),
    ("Kế hoạch tuyển sinh năm 2027", "tuyển sinh năm 2027"),
    ("Giấy mời dự hội nghị", "dự hội nghị"),
    ("Quyết định thành lập hội đồng", "thành lập hội đồng"),
    ("Công văn gửi các khoa", "gửi các khoa"),
    ("Tờ trình mua sắm thiết bị", "mua sắm thiết bị"),
    ("Xét cấp học bổng khuyến khích học tập", "Xét cấp học bổng khuyến khích học tập"),     # không tiền tố
    ("VỀ VIỆC   xét cấp\n học bổng", "xét cấp học bổng"),                                   # hoa, khoảng trắng
    (unicodedata.normalize("NFD", "Về việc xét học bổng"), "xét học bổng"),                # NFD → NFC
    ("Thông báo kế hoạch tuyển sinh", "kế hoạch tuyển sinh"),                              # chỉ bỏ một lần
    ("Kế hoạchs học tập", "Kế hoạchs học tập"),                                             # không cắt giữa từ
    ("Tổ chức công việc cuối năm, Việc nhà", "Tổ chức công cuối năm, nhà"),                 # bỏ token "việc"
    ("Về việc", ""),
], ids=["ve-viec", "vv-hai-cham", "vv", "vv-dinh", "thong-bao", "ke-hoach", "giay-moi", "quyet-dinh", "cong-van",
        "to-trinh", "khong-tien-to", "hoa-khoang-trang", "nfd", "mot-lan", "giua-tu", "viec", "chi-tien-to"])
def test_subject_text(summary, subject):
    assert subject_text(summary) == subject


def test_the_query_has_no_boilerplate_words():
    q = keyword_query(subject_text(SUMMARY))
    assert q == Q and "việc" not in q.split() and "Về" not in q.split()
    # không bỏ "việc" thì nó chiếm một trong 10 term Meilisearch xét
    assert keyword_query(SUMMARY).split()[0] == "việc"


@pytest.mark.parametrize(("model", "prefixed"), [("qwen3-embedding:0.6b", True), ("Qwen3-Embedding:4b", True),
                                                 ("bge-m3", False), (None, False)])
def test_similar_text_prefixes_only_qwen3_embedding(model, prefixed):
    got = similar_text(model, SUBJECT)
    assert got == (SIMILAR_PREFIX + SUBJECT if prefixed else SUBJECT)
    assert QUERY_PREFIX not in got          # chỉ dẫn riêng, không phải chỉ dẫn hỏi đáp của F4.2


def test_summary_with_only_boilerplate_finds_nothing_without_searching(similar_env, hasura):
    env = similar_env()
    target = doc(hasura, "Về việc", status="registered")
    r = env.post(target)
    assert r.status_code == 200
    assert r.json() | {"duration_ms": 0} == {"document_id": target, "hits": [], "terms": 0, "semantic": False,
                                             "duration_ms": 0}
    assert env.index.searches == []


# --- tìm và hậu kiểm ------------------------------------------------------------------------------------------


def test_finds_earlier_assigned_incoming_documents(similar_env, hasura):
    env = similar_env()
    c = corpus(hasura)
    env.sync()
    r = env.post(c.target, limit=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"document_id", "hits", "terms", "semantic", "duration_ms"}
    assert body["document_id"] == c.target and body["terms"] == 10 and body["semantic"] is False
    assert isinstance(body["duration_ms"], int) and body["duration_ms"] >= 0
    ids = [h["document_id"] for h in body["hits"]]
    # đã giao (đang xử lý, đã xong, đã lưu) mới ra; chính nó, văn bản chưa giao, văn bản đi, thuê ước khác: không
    assert ids[0] == c.d88 and set(ids) == {c.d88, c.d135, c.old}
    assert all(set(h) == {"document_id", "score"} for h in body["hits"])
    scores = [h["score"] for h in body["hits"]]
    assert scores == sorted(scores, reverse=True) and all(0 < s <= 1 for s in scores)
    assert all(round(s, 4) == s for s in scores)
    # một câu tìm Meilisearch: thuê ước đứng đầu, rồi chiều, trạng thái, trừ chính nó
    (sent,) = env.index.searches
    assert sent["q"] == Q
    assert sent["filter"] == [f'tenant_id = "{TENANT_A}"', 'direction = "in"', STATUS_FILTER,
                              f'document_id != "{c.target}"']
    assert "hybrid" not in sent and "vector" not in sent
    # hậu kiểm bằng vai trò service của đúng thuê ước
    assert {call["by"] for call in hasura.ask_calls} == {"service"}
    assert {call["tenant_id"] for call in hasura.ask_calls} == {str(TENANT_A)}


def test_limit_and_default_limit(similar_env, hasura):
    env = similar_env()
    target = doc(hasura, SUMMARY, status="registered")
    many = [doc(hasura, f"Về việc xét cấp học bổng đợt {i}", status="done") for i in range(20)]
    env.sync()
    r = env.post(target, limit=2)
    assert len(r.json()["hits"]) == 2
    r = env.post(target)                                    # mặc định 15
    assert len(r.json()["hits"]) == 15 and {h["document_id"] for h in r.json()["hits"]} <= set(many)


def test_post_check_drops_documents_restricted_or_moved_while_the_index_is_stale(similar_env, hasura):
    env = similar_env()
    c = corpus(hasura)
    env.sync()
    hasura.documents[c.d88]["restricted"] = True            # chưa đồng bộ lại: đoạn còn trong chỉ mục
    hasura.documents[c.old]["status"] = "cancelled"
    hasura.documents[c.d135]["status"] = "registered"       # trạng thái trong chỉ mục cũ hơn CSDL
    assert any(d["document_id"] == c.d88 for d in env.index.docs.values())
    r = env.post(c.target)
    assert r.status_code == 200 and r.json()["hits"] == []
    # đã hỏi Hasura về văn bản hạn chế nhưng Hasura (vai trò service) không trả: không lọt ra
    assert c.d88 in hasura.ask_calls[-1]["ids"]


def rare_word_corpus(hasura) -> SimpleNamespace:
    """Đích "học kỳ II": trong phạm vi chỉ một văn bản khác chủ đề có chữ "II" (từ hiếm nhất của câu tìm)."""
    return SimpleNamespace(
        target=doc(hasura, SUMMARY, status="registered"),
        d88=doc(hasura, "Về việc xét cấp học bổng khuyến khích học tập học kỳ I năm học 2026–2027",
                status="in_progress"),
        intern=doc(hasura, "Về việc tổ chức thực tập doanh nghiệp học kỳ II năm học 2026–2027", status="done"),
    )


def test_a_rare_word_that_says_nothing_about_the_topic_does_not_decide_the_evidence(similar_env, hasura):
    # frequency thật bắt mọi văn bản phải có "II" → lượt chính chỉ ra văn bản thực tập; lượt nới đưa 88 (cùng chủ đề,
    # học kỳ I) vào và xếp nó trên văn bản chỉ chung "kỳ", "II", "năm", "tập"
    env = similar_env()
    env.index.frequency = True
    c = rare_word_corpus(hasura)
    env.sync()
    r = env.post(c.target)
    assert r.status_code == 200, r.text
    hits = r.json()["hits"]
    assert [h["document_id"] for h in hits][:1] == [c.d88] and 0.5 <= hits[0]["score"] <= 1
    (sent,) = env.index.searches
    assert sent["matchingStrategy"] == "frequency"
    (bodies,) = env.index.multi_searches
    assert bodies[0] == {"filter": sent["filter"], "q": "", "limit": 0}
    assert [b["q"] for b in bodies[1:]] == [f"{t} " for t in Q.casefold().split()]


def test_relaxed_evidence_is_post_checked_like_the_rest(similar_env, hasura):
    env = similar_env()
    env.index.frequency = True
    c = rare_word_corpus(hasura)
    env.sync()
    hasura.documents[c.d88]["restricted"] = True            # chỉ mục chưa đồng bộ lại
    r = env.post(c.target)
    assert c.d88 not in {h["document_id"] for h in r.json()["hits"]}
    assert c.d88 in hasura.ask_calls[-1]["ids"]


def test_retriever_similar_keeps_the_semantic_flag_and_similar_documents_wraps_it(hasura):
    index = FakeChunkIndex()
    a = doc(hasura, "Về việc xét cấp học bổng khuyến khích", status="done")
    run(ChunkIndexer(index, hasura).sync_once())
    retriever = Retriever(index, hasura, embedder=EMB)
    got = run(retriever.similar(service_scope(TENANT_A), q="học bổng", vector=[0.1] * DIMS))
    assert isinstance(got, Similar) and got.semantic is True and got.error is None
    assert [h.document_id for h in got.hits] == [a]
    hits = run(retriever.similar_documents(service_scope(TENANT_A), q="học bổng", vector=None))
    assert [h.document_id for h in hits] == [a]
    nothing = run(retriever.similar(Scope(TENANT_A, NOTHING, None), q="học bổng", vector=None))
    assert nothing == Similar([], False, None)


# --- tìm theo nghĩa (tùy chọn) ------------------------------------------------------------------------------------


def test_with_an_embedding_model_searches_by_meaning(similar_env, hasura):
    fake = FakeOllama()
    env = similar_env(ai=ollama(fake, chat=None), embedder=EMB)
    c = corpus(hasura)
    env.sync()
    fake.requests.clear()
    r = env.post(c.target)
    assert r.status_code == 200 and r.json()["semantic"] is True
    assert r.json()["hits"][0]["document_id"] == c.d88
    # trích yếu (không phải câu tìm từ khóa) mang chỉ dẫn riêng; không phải tiền tố hỏi đáp của F4.2
    (call,) = fake.calls("/api/embed")
    assert call["input"] == [SIMILAR_PREFIX + SUBJECT]
    (sent,) = env.index.searches
    assert sent["hybrid"]["embedder"] == EMB and len(sent["vector"]) == DIMS and sent["q"] == Q
    assert env.index.multi_searches == []                       # tìm theo nghĩa đã phủ chữ khác: không nới
    assert env.indexer.holds == [similar.EMBED_TIMEOUT_S]       # vòng nhúng nền nhường mô hình


def test_embedding_is_bounded_by_three_seconds_and_a_miss_falls_back_to_keywords(similar_env, hasura):
    ai = RecordingAi(vectors=None)              # như OllamaAi quá 3 giây: không có véc-tơ
    env = similar_env(ai=ai, embedder=EMB)
    c = corpus(hasura)
    env.sync()
    r = env.post(c.target)
    assert r.status_code == 200 and r.json()["semantic"] is False and r.json()["hits"]
    assert ai.calls == [{"texts": [SIMILAR_PREFIX + SUBJECT], "query": False, "timeout_s": 3.0}]
    assert "hybrid" not in env.index.searches[-1]


def test_slow_embedding_model_only_costs_the_timeout(similar_env, hasura, monkeypatch):
    monkeypatch.setattr(similar, "EMBED_TIMEOUT_S", 0.05)
    fake = FakeOllama(embed_sleep_s=0.5)
    ai = ollama(fake, chat=None)
    env = similar_env(ai=ai, embedder=EMB)
    c = corpus(hasura)
    env.sync()
    r = env.post(c.target)
    assert r.status_code == 200 and r.json()["semantic"] is False
    assert r.json()["hits"][0]["document_id"] == c.d88 and ai.embed_error == "timeout"
    assert all("hybrid" not in b for b in env.index.searches)


def test_no_embedding_when_meilisearch_has_no_embedder_yet(similar_env, hasura):
    ai = RecordingAi(vectors=[[0.1] * DIMS])
    env = similar_env(ai=ai, embedder=EMB, embedder_ready=False)
    c = corpus(hasura)
    env.sync()
    r = env.post(c.target)
    assert r.status_code == 200 and r.json()["semantic"] is False and ai.calls == []


def test_hybrid_failure_retries_with_keywords_only(similar_env, hasura, log_records):
    env = similar_env(ai=RecordingAi(vectors=[[0.1] * DIMS]), embedder=EMB, index=RefusingIndex())
    c = corpus(hasura)
    env.sync()
    r = env.post(c.target)
    assert r.status_code == 200 and r.json()["semantic"] is False
    assert r.json()["hits"][0]["document_id"] == c.d88
    assert ["hybrid" in b for b in env.index.searches] == [True, False]
    (line,) = [x for x in log_records if x["event"] == "office.assist.similar"]
    assert "invalid_search_embedder" in line["error"] and line["semantic"] is False


# --- lỗi ----------------------------------------------------------------------------------------------------------


def test_search_unavailable(similar_env, hasura):
    env = similar_env()
    c = corpus(hasura)
    env.index.down = True
    r = env.post(c.target)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "search_unavailable"


def test_database_unavailable_reading_the_target_or_post_checking(similar_env, hasura, monkeypatch):
    env = similar_env()
    c = corpus(hasura)
    env.sync()
    hasura.down = True
    r = env.post(c.target)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"
    assert env.index.searches == []
    hasura.down = False

    async def broken(*_a, **_kw):
        raise HasuraError("Hasura trả HTTP 502")

    monkeypatch.setattr(hasura, "ask_documents_service", broken)
    r = env.post(c.target)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"


def test_assistant_disabled(similar_env, hasura):
    env = similar_env(env={"MOC_ASK_ENABLED": "false"})
    c = corpus(hasura)
    r = env.post(c.target)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "assistant_disabled"
    assert env.index.searches == []


def test_no_assistant_at_all_is_disabled(hasura):
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = "req-1"
        return await call_next(request)

    def caller(request: Request) -> str:
        if "authorization" not in request.headers:
            raise HTTPException(401, {"code": "missing_token", "message": "Thiếu token"})
        return "svc-workflow"

    similar.install(app, None, hasura, caller)
    with TestClient(app) as client:
        body = {"tenant_id": str(TENANT_A), "document_id": str(uuid.uuid4())}
        assert client.post(PATH, json=body).status_code == 401
        r = client.post(PATH, json=body, headers={"Authorization": "Bearer x"})
        assert r.status_code == 503 and r.json()["detail"]["code"] == "assistant_disabled"


# --- nhật ký -------------------------------------------------------------------------------------------------------


def test_logs_never_contain_the_summary_or_the_query(similar_env, hasura, log_records, caplog):
    caplog.set_level(logging.DEBUG)
    fake = FakeOllama()
    env = similar_env(ai=ollama(fake, chat=None), embedder=EMB)
    c = corpus(hasura)
    env.sync()
    r = env.post(c.target)
    assert r.status_code == 200 and r.json()["hits"]
    hasura.documents[c.d135]["restricted"] = True
    assert env.post(c.d135).status_code == 409
    env.index.down = True
    assert env.post(c.target).status_code == 503
    lines = [x for x in log_records if x["event"] == "office.assist.similar"]
    assert len(lines) == 3
    ok, sealed, down = lines
    assert {k for k in ok if k != "event"} == {"request_id", "tenant_id", "document_id", "caller", "hits", "terms",
                                                "semantic", "duration_ms", "error"}
    assert ok["tenant_id"] == str(TENANT_A) and ok["document_id"] == c.target and ok["caller"] == "svc-workflow"
    assert ok["hits"] == len(r.json()["hits"]) and ok["terms"] == 10 and ok["semantic"] is True
    assert ok["error"] is None and ok["duration_ms"] == r.json()["duration_ms"]
    assert sealed["code"] == "restricted" and down["code"] == "search_unavailable"
    text = json.dumps(log_records, ensure_ascii=False) + caplog.text
    for secret in (SUMMARY, SUBJECT, Q, "bổng", "khuyến", "bong khuyen", "hội thảo"):
        assert secret not in text
