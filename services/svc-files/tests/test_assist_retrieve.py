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

"""Truy xuất (F4.2): đoạn của văn bản người hỏi không được đọc, đang hạn chế hoặc không còn đủ điều kiện vào chỉ mục
không bao giờ ra khỏi Retriever, dù chỉ mục (lọc trước) còn cũ; giới hạn mỗi văn bản; lấy thêm lượt; thân tìm lai, tìm
lai lỗi thì lùi về từ khóa; phạm vi dịch vụ (F4.3)."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from conftest import TENANT_A, FakeChunkIndex
from svc_files import hasura as hasura_queries
from svc_files.assist.chunks import eligible
from svc_files.assist.index import ChunkIndexer
from svc_files.assist.retrieve import DocHit, Filters, Passage, Retriever
from svc_files.assist.scope import service_scope, user_scope
from svc_files.hasura import HasuraAuthError, HasuraError
from svc_files.search import SearchError
from test_assist_chunks import link, sentences, text

TENANT_B = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")
EMB = "emb_qwen3_embedding_0_6b"


def run(coro):
    return asyncio.run(coro)


def add(hasura, summary: str, lines: list[str], *, readers: set[str] | None = None, tenant=TENANT_A,
        **cols) -> str:
    files = [link(text(lines), file_id=f"f-{len(hasura.documents)}")]
    return hasura.add_document(tenant, summary, readers=readers, files=files, assignments=[],
                               updated_at="2026-10-21T08:00:00+00:00", **cols)


def sync(hasura, index) -> None:
    run(ChunkIndexer(index, hasura).sync_once())


def scope_of(make_token, *, sub: str = "u-van-thu", role: str = "clerk", department_id: str | None = None,
             tenant=TENANT_A):
    token = make_token(sub=sub, role=role, tenant=str(tenant))
    return user_scope(role=role, user_id=sub, tenant_id=tenant, department_id=department_id, token=token)


@pytest.fixture
def index() -> FakeChunkIndex:
    return FakeChunkIndex()


def retriever(index, hasura, **kw) -> Retriever:
    return Retriever(index, hasura, embedder=kw.pop("embedder", None), **kw)


# --- an toàn: hậu kiểm bằng token người hỏi ------------------------------------------------------------------


def test_stale_index_never_leaks_unreadable_or_restricted_documents(make_token, hasura, index):
    me = "u-chuyen-vien"
    mine = add(hasura, "Học bổng khuyến khích học tập", sentences("HOCBONG", 3), readers={me})
    # chỉ mục còn cũ: giao việc cho tôi đã hủy (Hasura không còn cho đọc), văn bản vừa bật hạn chế (tôi tạo nên vẫn
    # đọc được, nhưng chữ của nó không bao giờ được đưa ra)
    revoked = add(hasura, "Học bổng của phòng khác", sentences("HOCBONG", 3), readers={"u-khac"})
    sealed = add(hasura, "Học bổng mật", sentences("HOCBONG", 3), readers={me})
    for doc_id in (mine, revoked, sealed):
        hasura.documents[doc_id]["assignments"] = [{"department_id": None, "user_id": me,
                                                    "assigned_at": "2026-10-21T08:00:00+00:00"}]
    sync(hasura, index)
    hasura.documents[sealed]["restricted"] = True                  # chưa đồng bộ lại
    scope = scope_of(make_token, sub=me, role="staff", department_id="dep-dt")

    got = run(retriever(index, hasura).search(scope, q="hoc bong", vector=None, limit=10))
    assert {p.document_id for p in got.passages} == {mine}
    assert got.candidates >= 3                                      # Meilisearch đã trả cả đoạn bị cấm
    assert hasura.ask_calls[-1]["by"] == "token" and hasura.ask_calls[-1]["sub"] == me
    assert set(hasura.ask_calls[-1]["ids"]) == {mine, revoked, sealed}


def test_only_passages_of_documents_hasura_returns(make_token, hasura, index):
    hidden = [add(hasura, f"Văn bản mật {i}", sentences("KYLUAT", 2), readers={"u-khac"}) for i in range(4)]
    sync(hasura, index)
    got = run(retriever(index, hasura).search(scope_of(make_token, sub="u-toi"), q="hoc bong", vector=None))
    assert got.passages == [] and got.candidates == len(hidden)


def test_other_tenants_are_filtered_before_meilisearch(make_token, hasura, index):
    add(hasura, "Tuyển sinh A", sentences("TUYENSINH", 2))
    b_doc = add(hasura, "Tuyển sinh B", sentences("TUYENSINH", 2), tenant=TENANT_B)
    sync(hasura, index)
    got = run(retriever(index, hasura).search(scope_of(make_token, tenant=TENANT_B), q="tuyen sinh", vector=None))
    assert {p.document_id for p in got.passages} == {b_doc}
    assert got.candidates == 1 and index.searches[-1]["filter"][0] == f'tenant_id = "{TENANT_B}"'


def test_passages_carry_the_latest_document_data_from_hasura(make_token, hasura, index):
    doc = add(hasura, "Về việc xét học bổng", sentences("HOCBONG", 2), symbol="88/CTSV",
              document_type={"name": "Công văn"}, issuer_name="Phòng Công tác sinh viên")
    sync(hasura, index)
    hasura.documents[doc]["summary"] = "Về việc xét học bổng học kỳ I"      # sửa sau khi đã vào chỉ mục
    got = run(retriever(index, hasura).search(scope_of(make_token), q="hoc bong", vector=None))
    p = got.passages[0]
    assert isinstance(p, Passage) and (p.kind, p.page, p.file_role) == ("page", 1, "main")
    assert p.chunk_id.startswith(doc) and p.file_id and "HOCBONG" in p.text and p.score == 1.0
    assert p.doc == {"id": doc, "direction": "in", "status": "received", "type_code": "CV", "type_name": "Công văn",
                     "symbol": "88/CTSV", "issuer_name": "Phòng Công tác sinh viên", "issued_on": "2026-10-15",
                     "summary": "Về việc xét học bổng học kỳ I"}
    assert "restricted" not in p.doc and got.semantic is False


@pytest.mark.parametrize(("direction", "before", "after"), [
    ("in", "registered", "cancelled"),          # văn bản đến vừa bị hủy
    ("out", "issued", "draft"),                 # văn bản đi bị đưa về dự thảo
    ("out", "archived", "cancelled"),
], ids=["den-huy", "di-ve-du-thao", "di-huy"])
def test_post_check_drops_documents_no_longer_eligible_while_the_index_is_stale(make_token, hasura, index, direction,
                                                                                 before, after):
    other = add(hasura, "Học bổng khác", sentences("HOCBONG", 2))
    doc = add(hasura, "Học bổng", sentences("HOCBONG", 2), direction=direction, status=before)
    sync(hasura, index)
    assert any(c["document_id"] == doc for c in index.docs.values())
    hasura.documents[doc]["status"] = after                         # chưa đồng bộ lại
    got = run(retriever(index, hasura).search(scope_of(make_token), q="hoc bong", vector=None, limit=10))
    assert {p.document_id for p in got.passages} == {other} and got.candidates > len(got.passages)
    hits = run(retriever(index, hasura).similar_documents(service_scope(TENANT_A), q="hoc bong", vector=None))
    assert [h.document_id for h in hits] == [other]


def test_post_check_query_returns_every_field_eligibility_reads():
    class Row(dict):
        def get(self, key, default=None):
            read.add(key)
            return super().get(key, default)

    read: set[str] = set()
    for row in ({"direction": "in", "status": "cancelled"}, {"direction": "out", "status": "issued"},
                {"direction": "x"}, {"restricted": True}):
        eligible(Row(row))
    # thiếu trường nào thì hậu kiểm thật (Hasura) bỏ nhầm hoặc giữ nhầm, dù Hasura giả của test vẫn có đủ
    assert read <= set(hasura_queries._ASK_FIELDS.split())


# --- giới hạn, lượt thêm --------------------------------------------------------------------------------------


def test_at_most_per_doc_passages_per_document_and_limit_overall(make_token, hasura, index):
    big = add(hasura, "Quy chế dài", sentences("HOCBONG", 60))
    small = [add(hasura, f"Văn bản {i}", sentences("HOCBONG", 2)) for i in range(4)]
    sync(hasura, index)
    assert sum(c["document_id"] == big for c in index.docs.values()) > 2
    got = run(retriever(index, hasura).search(scope_of(make_token), q="hoc bong", vector=None, limit=10))
    per_doc = {d: sum(p.document_id == d for p in got.passages) for d in [big, *small]}
    assert per_doc == {big: 2, **{d: 1 for d in small}}
    got = run(retriever(index, hasura).search(scope_of(make_token), q="hoc bong", vector=None, limit=5))
    assert len(got.passages) == 5 and len({p.chunk_id for p in got.passages}) == 5
    assert max(sum(p.document_id == d for p in got.passages) for d in [big, *small]) <= 2
    one = run(retriever(index, hasura, per_doc=1).search(scope_of(make_token), q="hoc bong", vector=None, limit=3))
    assert len({p.document_id for p in one.passages}) == 3


def test_fetches_more_rounds_when_hidden_documents_crowd_the_top(make_token, hasura, index):
    for i in range(7):
        add(hasura, f"Văn bản mật {i}", sentences("NGHIPHEP", 1), readers={"u-khac"})
    mine = add(hasura, "Văn bản của tôi", sentences("NGHIPHEP", 1), readers={"u-toi"})
    sync(hasura, index)
    index.scores.update({c: 0.5 for c, d in index.docs.items() if d["document_id"] == mine})   # xếp cuối
    got = run(retriever(index, hasura, candidates=3).search(scope_of(make_token, sub="u-toi"), q="hoc bong",
                                                             vector=None))
    assert [p.document_id for p in got.passages] == [mine]
    assert [s["offset"] for s in index.searches] == [0, 3, 6] and got.candidates == 8


def test_stops_after_two_extra_rounds(make_token, hasura, index):
    for i in range(10):
        add(hasura, f"Văn bản mật {i}", sentences("NGHIPHEP", 1), readers={"u-khac"})
    mine = add(hasura, "Văn bản của tôi", sentences("NGHIPHEP", 1), readers={"u-toi"})
    sync(hasura, index)
    index.scores.update({c: 0.5 for c, d in index.docs.items() if d["document_id"] == mine})   # thứ 11
    got = run(retriever(index, hasura, candidates=3).search(scope_of(make_token, sub="u-toi"), q="hoc bong",
                                                             vector=None))
    assert got.passages == [] and len(index.searches) == 3


def test_no_extra_round_when_meilisearch_has_no_more(make_token, hasura, index):
    add(hasura, "Một văn bản", sentences("NGHIPHEP", 1), readers={"u-khac"})
    sync(hasura, index)
    run(retriever(index, hasura).search(scope_of(make_token, sub="u-toi"), q="hoc bong", vector=None))
    assert len(index.searches) == 1


def test_manager_without_department_does_not_call_meilisearch(make_token, hasura, index):
    add(hasura, "Văn bản", sentences("A", 2))
    sync(hasura, index)
    scope = scope_of(make_token, sub="u-truong", role="manager", department_id=None)
    got = run(retriever(index, hasura).search(scope, q="khoan", vector=None))
    assert (got.passages, got.candidates, got.semantic) == ([], 0, False) and index.searches == []


# --- tìm nới: câu hỏi có từ hiếm mà văn bản trả lời không có --------------------------------------------------

QUESTION = "Điều kiện xét học bổng khuyến khích tập"     # vi.keyword_query của câu e2e (bỏ "là gì", "học" thứ hai)
FRAME = ["Điều kiện tốt nghiệp: hoàn thành chương trình học và các học phần bắt buộc của ngành đào tạo."]
ANSWER = ["Phòng đề nghị Khoa xét chọn sinh viên nhận học bổng khuyến khích học tập có điểm trung bình từ 3,2."]
NOISE = ["Kế hoạch học tập năm học mới gửi các lớp sinh viên toàn trường để triển khai thực hiện."]


def corpus(hasura, index, **readers) -> tuple[str, str, str]:
    index.frequency = True
    frame = add(hasura, "Công văn một", FRAME)
    answer = add(hasura, "Công văn hai", ANSWER, readers=readers.get("answer"))
    noise = add(hasura, "Công văn ba", NOISE)
    sync(hasura, index)
    return frame, answer, noise


def test_relaxed_pass_finds_the_answer_that_lacks_the_rarest_question_word(make_token, hasura, index):
    frame, answer, _ = corpus(hasura, index)
    got = run(retriever(index, hasura).search(scope_of(make_token), q=QUESTION, vector=None))
    # lượt chính chỉ ra văn bản có chữ "điều kiện"; lượt nới thêm văn bản trả lời, không thêm văn bản chỉ có "học tập".
    # Xếp chung theo tỷ lệ trọng số: văn bản trả lời có gần đủ câu hỏi đứng trước văn bản chỉ có "điều kiện … học"
    assert [s["matchingStrategy"] for s in index.searches] == ["frequency"]
    assert [p.document_id for p in got.passages] == [answer, frame] and got.relaxed == 1
    assert 0.5 <= got.passages[0].score < 1 and got.passages[1].score < 0.5
    (bodies,) = index.multi_searches
    scope_filter = index.searches[0]["filter"]
    assert bodies[0] == {"filter": scope_filter, "q": "", "limit": 0}
    assert [b["q"] for b in bodies[1:]] == ["điều ", "kiện ", "xét ", "học ", "bổng ", "khuyến ", "khích ", "tập "]
    assert all(b["filter"] == scope_filter and b["matchingStrategy"] == "all" and b["limit"] == 24 for b in bodies[1:])


def test_relaxed_passages_are_post_checked_like_the_others(make_token, hasura, index):
    frame, answer, _ = corpus(hasura, index, answer={"u-khac"})
    got = run(retriever(index, hasura).search(scope_of(make_token), q=QUESTION, vector=None))
    assert [p.document_id for p in got.passages] == [frame] and got.relaxed == 0
    assert answer in hasura.ask_calls[-1]["ids"]


def test_question_words_missing_from_the_askers_scope_keep_their_weight(make_token, hasura, index):
    # chuyên viên chỉ thấy hai văn bản mình tạo. Lượt chính ra văn bản có "xét" (từ hiếm nhất trong phạm vi). Văn bản
    # chỉ có "học tập" không được nới vào: "điều kiện", "học bổng", "khuyến khích" không có trong phạm vi nhưng vẫn
    # nặng nhất trong câu hỏi — bỏ chúng khỏi tổng thì "học tập" thành hơn nửa câu hỏi
    index.frequency = True
    add(hasura, "Công văn một", NOISE, created_by="u-cv")
    review = add(hasura, "Công văn hai", ["Hội đồng xét kết quả học tập của sinh viên theo từng học kỳ của năm học."],
                 created_by="u-cv")
    add(hasura, "Công văn ba", ANSWER)
    sync(hasura, index)
    scope = scope_of(make_token, sub="u-cv", role="staff", department_id="dep-dt")
    got = run(retriever(index, hasura).search(scope, q=QUESTION, vector=None))
    assert [p.document_id for p in got.passages] == [review] and got.relaxed == 0 and len(index.multi_searches) == 1


def test_relaxed_pass_runs_even_when_the_main_pass_is_enough(make_token, hasura, index):
    # lượt chính đã đủ một đoạn (văn bản có "điều kiện") nhưng văn bản trả lời có nhiều trọng số câu hỏi hơn: từ hiếm
    # của câu hỏi không quyết văn bản nào được trả
    frame, answer, _ = corpus(hasura, index)
    got = run(retriever(index, hasura).search(scope_of(make_token), q=QUESTION, vector=None, limit=1))
    assert [p.document_id for p in got.passages] == [answer] and got.relaxed == 1 and len(index.multi_searches) == 1


def test_main_passages_that_cover_the_question_keep_meilisearch_order(make_token, hasura, index):
    # mọi đoạn có đủ từ của câu hỏi: tỷ lệ bằng nhau (1), giữ thứ tự xếp hạng của Meilisearch
    index.frequency = True
    first = add(hasura, "Công văn một", ["Hướng dẫn xét học bổng khuyến khích học tập cho sinh viên năm thứ nhất."])
    second = add(hasura, "Công văn hai", ["Thông báo xét học bổng khuyến khích học tập học kỳ hai cho các lớp."])
    sync(hasura, index)
    index.scores.update({c: 0.9 if d["document_id"] == second else 0.8 for c, d in index.docs.items()})
    got = run(retriever(index, hasura).search(scope_of(make_token), q="xét học bổng", vector=None))
    assert [p.document_id for p in got.passages] == [second, first] and got.relaxed == 0
    assert [p.score for p in got.passages] == [1.0, 1.0]


def test_a_passage_with_every_question_word_is_not_pushed_out_by_cut_word_lists(make_token, hasura, index):
    # mỗi từ chỉ lấy `candidates` đoạn đầu: từ phổ biến có ở 5 đoạn nên kết quả của nó dừng ở 3 kế hoạch tuyển sinh
    # đại học, không có kế hoạch tuyển sinh thạc sĩ (có đủ câu hỏi, đứng đầu lượt chính) — vẫn tính được các từ đó
    # cho nó vì có nguyên văn trong đoạn, nên nó không bị xếp sau các đoạn chỉ có từ phổ biến
    index.frequency = True
    fillers = [add(hasura, f"Công văn {n}", ["Kế hoạch tuyển sinh đại học chính quy của trường năm 2027."])
               for n in range(4)]
    master = add(hasura, "Công văn năm",
                 ["Kế hoạch tuyển sinh thạc sĩ khóa mới của Khoa Công nghệ thông tin năm 2027."])
    sync(hasura, index)
    # cùng điểm thì Meilisearch xếp theo thứ tự trong chỉ mục: đoạn thạc sĩ nằm cuối, sau cả bốn kế hoạch kia
    index.docs = dict(sorted(index.docs.items(), key=lambda kv: kv[1]["document_id"] == master))
    first = list(dict.fromkeys(d["document_id"] for d in index.docs.values()))[:3]
    assert set(first) <= set(fillers)
    got = run(retriever(index, hasura, candidates=3).search(scope_of(make_token), q="kế hoạch tuyển sinh thạc",
                                                             vector=None))
    assert [p.document_id for p in got.passages] == [master, *first] and got.relaxed == 3
    assert got.passages[0].score == 1.0 and all(0.5 <= p.score < 1 for p in got.passages[1:])


def test_main_passages_past_the_limit_are_ranked_too(make_token, hasura, index):
    # lượt chính dừng lấy ở `limit` nhưng mọi đoạn nó đã đọc đều được xếp chung: đoạn có từ hiếm nhất đứng sau bốn đoạn
    # có hai từ phổ biến trong lượt chính, lên đầu khi xếp theo trọng số — và không bị đếm là đoạn nhờ tìm nới
    for n in range(4):
        add(hasura, f"Công văn {n}", ["Lịch thi học kỳ một của các lớp sinh viên năm thứ hai trong khoa."])
    exchange = add(hasura, "Công văn bốn", ["Chương trình trao đổi Erasmus cho sinh viên năm thứ ba trong khoa."])
    sync(hasura, index)
    got = run(retriever(index, hasura).search(scope_of(make_token), q="lịch thi Erasmus", vector=None, limit=1))
    assert [p.document_id for p in got.passages] == [exchange] and got.relaxed == 0
    assert 0.5 <= got.passages[0].score < 1


def test_a_failed_relaxed_pass_keeps_the_main_passages(make_token, hasura, index):
    frame, _, _ = corpus(hasura, index)

    async def down(bodies):
        raise SearchError("multi-search quá thời gian")

    index.multi_search = down
    got = run(retriever(index, hasura).search(scope_of(make_token), q=QUESTION, vector=None))
    assert [p.document_id for p in got.passages] == [frame] and got.relaxed == 0
    hits = run(retriever(index, hasura).similar_documents(service_scope(TENANT_A), q=QUESTION, vector=None))
    assert [h.document_id for h in hits] == [frame]


def test_no_relaxed_pass_when_not_needed(make_token, hasura, index):
    frame, answer, _ = corpus(hasura, index)
    # một từ: lượt chính đã tìm đúng từ đó
    run(retriever(index, hasura).search(scope_of(make_token), q="kiện", vector=None))
    assert index.multi_searches == []
    # tìm theo nghĩa: phần nghĩa đã phủ câu hỏi dùng chữ khác
    run(retriever(index, hasura, embedder=EMB).search(scope_of(make_token), q=QUESTION, vector=[0.1, 0.2]))
    assert index.multi_searches == []


def test_chunk_index_multi_search_request():
    import httpx2

    from svc_files.assist.meili import ChunkIndex

    seen = []

    def reply(request):
        seen.append((request.url.path, json.loads(request.content)))
        return httpx2.Response(200, json={"results": [{"hits": [], "estimatedTotalHits": 19},
                                                      {"hits": [{"id": "c1"}], "estimatedTotalHits": 1}]})

    index = ChunkIndex("http://meilisearch:7700", "khoa", "chunks", transport=httpx2.MockTransport(reply))
    got = run(index.multi_search([{"q": "", "limit": 0}, {"q": "kiện ", "limit": 24}]))
    assert got == [([], 19), ([{"id": "c1"}], 1)]
    assert seen == [("/multi-search", {"queries": [{"indexUid": "chunks", "q": "", "limit": 0},
                                                   {"indexUid": "chunks", "q": "kiện ", "limit": 24}]})]


# --- thân yêu cầu ---------------------------------------------------------------------------------------------


def test_keyword_body_filters_and_threshold(make_token, hasura, index):
    scope = scope_of(make_token, sub="u-cv", role="staff", department_id="dep-dt")
    run(retriever(index, hasura).search(scope, q="hoc bong", vector=None,
                                        filters=Filters(direction="in", year=2026, type_code='C"V')))
    body = index.searches[-1]
    assert body["filter"] == [f'tenant_id = "{TENANT_A}"', *scope.where, 'direction = "in"', "year = 2026",
                              'type_code = "C\\"V"']
    assert body["limit"] == 24 and body["offset"] == 0
    assert body["showRankingScore"] is True and body["matchingStrategy"] == "frequency"
    assert body["rankingScoreThreshold"] == 0.0 and "hybrid" not in body and "vector" not in body
    assert body["attributesToRetrieve"] == ["id", "document_id", "kind", "file_id", "file_role", "page", "seq",
                                            "text"]


def test_vector_adds_hybrid_search(make_token, hasura, index):
    add(hasura, "Học bổng", sentences("HOCBONG", 2))
    sync(hasura, index)
    got = run(retriever(index, hasura, embedder=EMB, semantic_ratio=0.7).search(
        scope_of(make_token), q="hoc bong", vector=[0.1, 0.2, 0.3]))
    body = index.searches[-1]
    assert body["hybrid"] == {"embedder": EMB, "semanticRatio": 0.7} and body["vector"] == [0.1, 0.2, 0.3]
    assert body["rankingScoreThreshold"] == 0.75 and got.semantic is True
    run(retriever(index, hasura, embedder=None).search(scope_of(make_token), q="hoc bong", vector=[0.1]))
    assert "hybrid" not in index.searches[-1]                       # không có embedder: chỉ từ khóa


# --- tìm lai lỗi: lùi về từ khóa -----------------------------------------------------------------------------


class RefusingIndex(FakeChunkIndex):
    """Meilisearch từ chối thân tìm khớp ``refuse`` (vd tìm lai khi embedder chưa có: lúc khởi động, khi đổi mô
    hình); ghi lại mọi thân đã gửi."""

    def __init__(self, refuse) -> None:
        super().__init__()
        self.refuse = refuse
        self.sent: list[dict] = []

    async def search(self, body: dict) -> list[dict]:
        self.sent.append(body)
        if self.refuse(body):
            raise SearchError(f"Meilisearch trả 400: invalid_search_embedder Cannot find embedder with name `{EMB}`.")
        return await super().search(body)


def test_hybrid_failure_retries_once_with_keywords_only(make_token, hasura):
    index = RefusingIndex(lambda body: "hybrid" in body)
    doc = add(hasura, "Học bổng", sentences("HOCBONG", 2))
    sync(hasura, index)
    got = run(retriever(index, hasura, embedder=EMB).search(scope_of(make_token), q="hoc bong", vector=[0.1, 0.2]))
    assert [p.document_id for p in got.passages] == [doc]
    assert got.semantic is False and "invalid_search_embedder" in got.hybrid_error
    assert [("vector" in b, b["rankingScoreThreshold"]) for b in index.sent] == [(True, 0.75), (False, 0.0)]
    # văn bản tương tự (F4.3) cũng vậy
    index.sent.clear()
    hits = run(retriever(index, hasura, embedder=EMB).similar_documents(service_scope(TENANT_A), q="hoc bong",
                                                                        vector=[0.1, 0.2]))
    assert [h.document_id for h in hits] == [doc] and ["hybrid" in b for b in index.sent] == [True, False]


def test_hybrid_success_and_keyword_failure_are_not_retried(make_token, hasura):
    index = RefusingIndex(lambda body: False)
    add(hasura, "Học bổng", sentences("HOCBONG", 2))
    sync(hasura, index)
    got = run(retriever(index, hasura, embedder=EMB).search(scope_of(make_token), q="hoc bong", vector=[0.1]))
    assert got.semantic is True and got.hybrid_error is None and len(index.sent) == 1
    # Meilisearch tắt hẳn: tìm lai lỗi, tìm lại bằng từ khóa một lần, cũng lỗi → đi lên (503)
    index.refuse = lambda body: True
    index.sent.clear()
    with pytest.raises(SearchError):
        run(retriever(index, hasura, embedder=EMB).search(scope_of(make_token), q="hoc bong", vector=[0.1]))
    assert ["hybrid" in b for b in index.sent] == [True, False]
    # không tìm lai: không có gì để lùi về
    index.sent.clear()
    with pytest.raises(SearchError):
        run(retriever(index, hasura, embedder=EMB).search(scope_of(make_token), q="hoc bong", vector=None))
    assert len(index.sent) == 1


# --- lỗi --------------------------------------------------------------------------------------------------------


def test_errors_go_straight_up(make_token, hasura, index):
    add(hasura, "Học bổng", sentences("HOCBONG", 2))
    sync(hasura, index)
    scope = scope_of(make_token)
    hasura.reject_tokens = True
    with pytest.raises(HasuraAuthError):
        run(retriever(index, hasura).search(scope, q="hoc bong", vector=None))
    hasura.reject_tokens, hasura.down = False, True
    with pytest.raises(HasuraError):
        run(retriever(index, hasura).search(scope, q="hoc bong", vector=None))
    hasura.down, index.down = False, True
    with pytest.raises(SearchError):
        run(retriever(index, hasura).search(scope, q="hoc bong", vector=None))


# --- phạm vi dịch vụ (F4.3) -----------------------------------------------------------------------------------


def test_service_scope_checks_with_service_role_and_skips_restricted(hasura, index):
    a = add(hasura, "Học bổng", sentences("HOCBONG", 2), readers={"u-khac"})
    sealed = add(hasura, "Học bổng mật", sentences("HOCBONG", 2))
    sync(hasura, index)
    hasura.documents[sealed]["restricted"] = True
    got = run(retriever(index, hasura).search(service_scope(TENANT_A), q="hoc bong", vector=None))
    assert {p.document_id for p in got.passages} == {a}
    assert hasura.ask_calls[-1] == {"by": "service", "tenant_id": str(TENANT_A), "ids": sorted([a, sealed])}


def test_similar_documents_groups_chunks_by_document(hasura, index):
    long = add(hasura, "Quy chế học bổng", sentences("HOCBONG", 40))
    short = add(hasura, "Thông báo học bổng", sentences("HOCBONG", 2))
    itself = add(hasura, "Văn bản đang xét", sentences("HOCBONG", 2))
    sealed = add(hasura, "Học bổng mật", sentences("HOCBONG", 2))
    sync(hasura, index)
    hasura.documents[sealed]["restricted"] = True
    long_chunks = [c for c, d in index.docs.items() if d["document_id"] == long]
    assert len(long_chunks) > 2
    index.scores.update({c: 0.5 for c in long_chunks} | {long_chunks[-1]: 0.95})
    index.scores.update({c: 0.9 for c, d in index.docs.items() if d["document_id"] != long})
    # câu tìm một từ: không nới (điểm nới là tỷ lệ từ chung, sẽ phủ điểm đặt sẵn của từng đoạn)
    hits = run(retriever(index, hasura).similar_documents(
        service_scope(TENANT_A), q="hocbong", vector=None, limit=10,
        where=(f'document_id != "{itself}"', 'status IN ["received", "in_progress"]')))
    assert all(isinstance(h, DocHit) for h in hits)
    # điểm của văn bản = điểm cao nhất trong các đoạn (đoạn cuối của văn bản dài); tự nó, văn bản mật: bỏ
    assert [(h.document_id, h.score) for h in hits] == [(long, 0.95), (short, 0.9)]
    assert hits[1].doc["summary"] == "Thông báo học bổng"
    assert f'document_id != "{itself}"' in index.searches[-1]["filter"]
    assert json.dumps(index.searches[-1]["filter"]).count("tenant_id") == 1
    assert run(retriever(index, hasura).similar_documents(service_scope(TENANT_A), q="hocbong", vector=None,
                                                          limit=1))[0].document_id == long
