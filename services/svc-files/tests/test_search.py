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

"""/api/search: lọc thuê ước từ token, lọc quyền qua Hasura, phân trang, đồng bộ chỉ mục."""

import asyncio
import json
import logging
import uuid

import httpx2
import pytest

from conftest import TENANT_A
from svc_files.search import MAX_CONTENT, Indexer, MeiliClient, SearchError, SearchQuery, build_filter

TENANT_B = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sync(hasura, meili) -> int:
    return asyncio.run(Indexer(hasura, meili).sync_once())


def search(client, token: str, **params):
    return client.get("/api/search", headers=auth(token), params=params)


def pdfs(*contents: str, at: str = "2026-10-18T09:30:00+00:00") -> list[dict]:
    """Tệp PDF đã gắn vào văn bản, kèm lớp chữ đã đọc (như CHANGED_DOCUMENTS trả về)."""
    return [{"file": {"text": {"content": c, "extracted_at": at}}} for c in contents]


def test_finds_vietnamese_without_diacritics(client, make_token, hasura, meili):
    doc = hasura.add_document(TENANT_A, "Công văn về việc tuyển sinh đại học năm 2026")
    hasura.add_document(TENANT_A, "Quyết định thành lập hội đồng thi")
    sync(hasura, meili)
    r = search(client, make_token(), q="cong van tuyen sinh")
    assert r.status_code == 200, r.text
    assert [h["id"] for h in r.json()["hits"]] == [doc]


def test_tenant_filter_comes_from_token_not_from_parameters(client, make_token, hasura, meili):
    hasura.add_document(TENANT_A, "Kế hoạch tuyển sinh của đơn vị A")
    b_doc = hasura.add_document(TENANT_B, "Kế hoạch tuyển sinh của đơn vị B")
    sync(hasura, meili)
    r = search(client, make_token(tenant=str(TENANT_B)), q="tuyen sinh", tenant_id=str(TENANT_A))
    assert [h["id"] for h in r.json()["hits"]] == [b_doc]
    assert all(f["filters"][0] == f'tenant_id = "{TENANT_B}"' for f in meili.searches)


def test_documents_the_user_cannot_read_are_dropped(client, make_token, hasura, meili):
    secret = hasura.add_document(TENANT_A, "Báo cáo tuyển sinh nội bộ", readers={"u-hieu-truong"})
    public = hasura.add_document(TENANT_A, "Thông báo tuyển sinh công khai")
    sync(hasura, meili)
    seen = [h["id"] for h in search(client, make_token(sub="u-chuyen-vien"), q="tuyen sinh").json()["hits"]]
    assert seen == [public]
    seen = {h["id"] for h in search(client, make_token(sub="u-hieu-truong"), q="tuyen sinh").json()["hits"]}
    assert seen == {secret, public}


def test_response_has_no_total_count(client, make_token, hasura, meili):
    hasura.add_document(TENANT_A, "Báo cáo tuyển sinh nội bộ", readers={"u-khac"})
    sync(hasura, meili)
    body = search(client, make_token(), q="tuyen sinh").json()
    assert body == {"hits": [], "next_cursor": None}


def test_finds_visible_document_behind_many_invisible_ones(client, make_token, hasura, meili):
    for i in range(45):
        hasura.add_document(TENANT_A, f"Hồ sơ tuyển sinh nội bộ số {i}", readers={"u-khac"})
    mine = hasura.add_document(TENANT_A, "Hồ sơ tuyển sinh của tôi")
    sync(hasura, meili)
    hits = search(client, make_token(sub="u-toi"), q="ho so tuyen sinh", limit=5).json()["hits"]
    assert [h["id"] for h in hits] == [mine]


def test_pagination_with_next_cursor(client, make_token, hasura, meili):
    ids = [hasura.add_document(TENANT_A, f"Giấy mời họp giao ban tuần {i}") for i in range(5)]
    sync(hasura, meili)
    token = make_token()
    first = search(client, token, q="giay moi hop", limit=2).json()
    second = search(client, token, q="giay moi hop", limit=2, cursor=first["next_cursor"]).json()
    third = search(client, token, q="giay moi hop", limit=2, cursor=second["next_cursor"]).json()
    got = [h["id"] for page in (first, second, third) for h in page["hits"]]
    assert got == sorted(ids)              # Meilisearch giả trả theo thứ tự đẩy vào chỉ mục: theo id
    assert third["next_cursor"] is None


def test_cursor_does_not_reveal_how_many_unreadable_documents_match(client, make_token, hasura, meili):
    # vị trí thô trong Meilisearch đếm cả văn bản người tìm không được đọc: không được lộ ra dưới dạng số
    for i in range(7):
        hasura.add_document(TENANT_A, f"Quyết định kỷ luật số {i}", readers={"u-khac"})
    hasura.add_document(TENANT_A, "Quyết định kỷ luật mẫu", readers={"u-toi"})
    hasura.add_document(TENANT_A, "Quyết định kỷ luật mẫu hai", readers={"u-toi"})
    sync(hasura, meili)
    token = make_token(sub="u-toi")
    first = search(client, token, q="ky luat", limit=1).json()
    again = search(client, token, q="ky luat", limit=1).json()
    assert len(first["hits"]) == 1 and first["next_cursor"]
    assert not first["next_cursor"].isdigit()
    assert first["next_cursor"] != again["next_cursor"]                  # mã hóa với nonce ngẫu nhiên
    second = search(client, token, q="ky luat", limit=1, cursor=first["next_cursor"]).json()
    assert sorted(h["summary"] for h in first["hits"] + second["hits"]) == ["Quyết định kỷ luật mẫu",
                                                                             "Quyết định kỷ luật mẫu hai"]


def test_cursor_only_works_for_the_same_user_and_query(client, make_token, hasura, meili):
    for i in range(3):
        hasura.add_document(TENANT_A, f"Giấy mời họp {i}")
    sync(hasura, meili)
    cursor = search(client, make_token(sub="u-1"), q="giay moi", limit=1).json()["next_cursor"]
    assert search(client, make_token(sub="u-1"), q="giay moi", limit=1, cursor=cursor).status_code == 200
    for token, params in [
        (make_token(sub="u-2"), {"q": "giay moi"}),                         # người khác
        (make_token(sub="u-1"), {"q": "hop"}),                              # câu tìm khác
        (make_token(sub="u-1"), {"q": "giay moi", "direction": "in"}),      # bộ lọc khác
    ]:
        r = search(client, token, limit=1, cursor=cursor, **params)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_cursor"
    tampered = cursor[:-2] + ("AA" if cursor[-2:] != "AA" else "BB")
    for bad in (tampered, "10", "khong-phai-cursor", "A" * 100):
        assert search(client, make_token(sub="u-1"), q="giay moi", cursor=bad).status_code == 400


def test_results_come_from_database_not_from_index(client, make_token, hasura, meili):
    doc = hasura.add_document(TENANT_A, "Về việc tuyển sinh năm 2026")
    sync(hasura, meili)
    hasura.documents[doc]["summary"] = "Về việc tuyển sinh năm 2026 (đã sửa trích yếu)"
    hit = search(client, make_token(), q="tuyen sinh").json()["hits"][0]
    assert hit["summary"].endswith("(đã sửa trích yếu)")


def test_optional_filters_are_passed_to_meilisearch(client, make_token, hasura, meili):
    out = hasura.add_document(TENANT_A, "Dự thảo thông báo tuyển sinh", direction="out", status="draft")
    hasura.add_document(TENANT_A, "Công văn đến về tuyển sinh")
    sync(hasura, meili)
    r = search(client, make_token(), q="tuyen sinh", direction="out", status="draft", year=2026)
    assert [h["id"] for h in r.json()["hits"]] == [out]
    assert meili.searches[0]["filters"][1:] == ['direction = "out"', 'status = "draft"', "year = 2026"]


# --- tìm theo nội dung (F2.7) ---------------------------------------------------------------------------


def test_finds_documents_by_the_text_of_their_pdf(client, make_token, hasura, meili):
    in_pdf = hasura.add_document(TENANT_A, "Công văn về việc rà soát danh sách sinh viên",
                                 files=pdfs("Đề nghị bổ sung chứng chỉ ngoại ngữ B1 trước ngày 30/11"))
    in_summary = hasura.add_document(TENANT_A, "Thông báo thi chứng chỉ ngoại ngữ")
    hasura.add_document(TENANT_A, "Giấy mời họp", files=pdfs("Không liên quan"))
    sync(hasura, meili)
    hits = search(client, make_token(), q="chung chi ngoai ngu").json()["hits"]
    assert {h["id"]: h["matched_content"] for h in hits} == {in_pdf: True, in_summary: False}
    # lượt hỏi lại chỉ trong số ký hiệu, trích yếu, cơ quan ban hành, đúng các kết quả vừa tìm được
    check = meili.searches[-1]
    assert check["attributes"] == ["symbol", "summary", "issuer_name"]
    assert check["filters"][0] == f'tenant_id = "{TENANT_A}"' and check["filters"][-1].startswith("id IN [")


def test_outgoing_body_is_searched(client, make_token, hasura, meili):
    out = hasura.add_document(TENANT_A, "Thông báo lịch họp giao ban", direction="out", status="draft",
                              body="Địa điểm: phòng họp tầng 3, nhà A1.")
    sync(hasura, meili)
    hits = search(client, make_token(), q="phong hop tang 3").json()["hits"]
    assert [(h["id"], h["matched_content"]) for h in hits] == [(out, True)]


def test_restricted_documents_are_found_by_metadata_only(client, make_token, hasura, meili):
    secret = hasura.add_document(TENANT_A, "Báo cáo nhân sự quý III", readers={"u-van-thu"}, restricted=True,
                                 files=pdfs("Danh sách nâng lương trước hạn"))
    sync(hasura, meili)
    assert meili.docs[secret]["content"] == ""
    # kể cả người được đọc văn bản cũng không tìm được theo nội dung: nội dung không vào chỉ mục
    assert search(client, make_token(), q="nang luong").json()["hits"] == []
    assert [h["id"] for h in search(client, make_token(), q="nhan su").json()["hits"]] == [secret]


def test_check_query_failure_still_returns_results(client, make_token, hasura, meili):
    # vd chỉ mục chưa nhận cấu hình lọc theo id ngay sau khi nâng cấp: lượt hỏi thứ hai lỗi
    doc = hasura.add_document(TENANT_A, "Công văn về tuyển sinh")
    sync(hasura, meili)
    real = meili.search

    async def flaky(q, filters, limit, offset, attributes=None):
        if attributes is not None:
            raise SearchError("invalid_search_filter")
        return await real(q, filters, limit, offset)

    meili.search = flaky
    r = search(client, make_token(), q="tuyen sinh")
    assert r.status_code == 200
    assert [(h["id"], h["matched_content"]) for h in r.json()["hits"]] == [(doc, False)]


def test_no_second_query_when_nothing_is_found(client, make_token, hasura, meili):
    sync(hasura, meili)
    assert search(client, make_token(), q="khong co gi").json()["hits"] == []
    assert len(meili.searches) == 1


def test_indexer_repushes_a_document_when_its_pdf_text_arrives(hasura, meili):
    async def scenario():
        indexer = Indexer(hasura, meili)
        doc = hasura.add_document(TENANT_A, "Công văn có tệp chưa đọc chữ")
        assert await indexer.sync_once() == 1 and meili.docs[doc]["content"] == ""
        # tệp vừa được đọc chữ: văn bản không đổi updated_at, vẫn phải đẩy lại
        hasura.documents[doc]["files"] = pdfs("Noi dung trong tep", at="2026-10-18T09:20:00+00:00")
        assert await indexer.sync_once() == 1 and meili.docs[doc]["content"] == "Noi dung trong tep"
        assert await indexer.sync_once() == 0

    asyncio.run(scenario())


def test_indexer_repushes_text_that_arrives_late_with_an_earlier_timestamp(hasura, meili):
    # chữ ghi xong muộn nhưng mốc đọc sớm hơn lần sửa đã đẩy: mốc lớn nhất không đổi, văn bản vẫn phải đẩy lại
    async def scenario():
        indexer = Indexer(hasura, meili)
        doc = hasura.add_document(TENANT_A, "Công văn sửa sau khi đọc chữ", updated_at="2026-10-18T09:20:00+00:00")
        assert await indexer.sync_once() == 1
        hasura.documents[doc]["files"] = pdfs("Chu ghi muon", at="2026-10-18T09:19:50+00:00")
        assert await indexer.sync_once() == 1 and meili.docs[doc]["content"] == "Chu ghi muon"

    asyncio.run(scenario())


def test_indexer_retries_a_push_that_meilisearch_refused(hasura, meili):
    async def scenario():
        indexer = Indexer(hasura, meili)
        doc = hasura.add_document(TENANT_A, "Công văn đẩy lỗi")
        meili.down = True
        with pytest.raises(SearchError):
            await indexer.sync_once()
        meili.down = False
        indexer.ready = True
        assert await indexer.sync_once() == 1 and doc in meili.docs

    asyncio.run(scenario())


def test_indexer_pages_by_id_not_by_offset(hasura, meili):
    ids = sorted(hasura.add_document(TENANT_A, f"Văn bản {i}") for i in range(5))
    pushed = asyncio.run(Indexer(hasura, meili, page=2).sync_once())
    assert pushed == 5 and set(meili.docs) == set(ids)
    assert hasura.change_reads == [str(uuid.UUID(int=0)), ids[1], ids[3]]


def test_index_content_joins_body_and_pdf_texts_and_is_capped(hasura, meili):
    out = hasura.add_document(TENANT_A, "Công văn trả lời", direction="out", body="Nội dung công văn",
                              files=pdfs("Phụ lục một", "Phụ lục hai"))
    big = hasura.add_document(TENANT_A, "Công văn dài", files=pdfs("a" * 60_000, "b" * 60_000))
    sync(hasura, meili)
    assert meili.docs[out]["content"] == "Nội dung công văn\n\nPhụ lục một\n\nPhụ lục hai"
    assert len(meili.docs[big]["content"]) == MAX_CONTENT
    assert "files" not in meili.docs[out] and "body" not in meili.docs[out]


@pytest.mark.parametrize("params", [
    {"q": "x", "type_code": 'CV" OR tenant_id = "khac'},
    {"q": "x", "status": "bi_mat"},
    {"q": "x", "direction": "ngang"},
    {"q": "x", "year": 1999},
    {"q": "x", "limit": 500},
    {"q": "x" * 201},
    {"q": ""},
])
def test_invalid_parameters_are_rejected(client, make_token, params):
    assert search(client, make_token(), **params).status_code == 422


def test_blank_query_is_rejected(client, make_token):
    r = search(client, make_token(), q="   ")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "empty_query"


def test_search_needs_token(client):
    assert client.get("/api/search", params={"q": "x"}).status_code == 401


def test_meilisearch_down_is_503(client, make_token, meili):
    meili.down = True
    r = search(client, make_token(), q="x")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "search_unavailable"


def test_database_down_is_503(client, make_token, hasura, meili):
    hasura.add_document(TENANT_A, "Công văn tuyển sinh")
    sync(hasura, meili)
    hasura.down = True
    r = search(client, make_token(), q="tuyen sinh")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"


def test_token_rejected_by_hasura_is_401(client, make_token, hasura, meili):
    hasura.add_document(TENANT_A, "Công văn tuyển sinh")
    sync(hasura, meili)
    hasura.reject_tokens = True
    assert search(client, make_token(), q="tuyen sinh").status_code == 401


def test_query_text_is_not_logged(client, make_token, hasura, meili):
    records: list[str] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = Keep()
    logging.getLogger("svc_files").addHandler(handler)
    try:
        search(client, make_token(), q="ky luat can bo")
    finally:
        logging.getLogger("svc_files").removeHandler(handler)
    events = [json.loads(m) for m in records]
    assert any(e["event"] == "core.search" and e["q_length"] == len("ky luat can bo") for e in events)
    assert not any("ky luat" in m for m in records)


# --- bộ lọc --------------------------------------------------------------------------------------


def test_build_filter_puts_tenant_first_and_escapes_values():
    parts = build_filter(TENANT_A, SearchQuery(q="x", type_code='a"b\\c', year=2026))
    assert parts[0] == f'tenant_id = "{TENANT_A}"'
    assert parts[1] == 'type_code = "a\\"b\\\\c"'
    assert parts[2] == "year = 2026"


# --- đồng bộ chỉ mục -----------------------------------------------------------------------------


def test_indexer_pushes_only_changes(hasura, meili):
    async def scenario():
        indexer = Indexer(hasura, meili)
        a = hasura.add_document(TENANT_A, "Văn bản thứ nhất về tuyển sinh")
        hasura.add_document(TENANT_A, "Văn bản thứ hai về tuyển sinh")
        assert await indexer.sync_once() == 2
        assert await indexer.sync_once() == 0                  # không đổi gì → không đẩy lại

        hasura.documents[a]["updated_at"] = "2026-10-18T09:05:00+00:00"
        hasura.documents[a]["summary"] = "Văn bản thứ nhất đã sửa"
        assert await indexer.sync_once() == 1
        assert meili.docs[a]["summary"] == "Văn bản thứ nhất đã sửa"

        # giao dịch ghi xong muộn: updated_at sớm hơn con trỏ nhưng vẫn trong cửa sổ overlap
        late = hasura.add_document(TENANT_A, "Văn bản ghi muộn", updated_at="2026-10-18T09:04:30+00:00")
        assert await indexer.sync_once() == 1
        assert late in meili.docs

    asyncio.run(scenario())


def test_index_document_shape(hasura, meili):
    doc = hasura.add_document(TENANT_A, "Công văn số 5", issued_on="2026-03-02")
    sync(hasura, meili)
    indexed = meili.docs[doc]
    assert indexed["tenant_id"] == str(TENANT_A)
    assert indexed["year"] == 2026 and indexed["issued_ts"] == 1772409600
    assert "readers" not in indexed and "updated_at" not in indexed


# --- client Meilisearch --------------------------------------------------------------------------


class Recorder:
    def __init__(self, replies: dict[tuple[str, str], tuple[int, dict]]) -> None:
        self.replies = replies
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        status, body = self.replies[(request.method, request.url.path)]
        return httpx2.Response(status, json=body)


def meili_client(rec: Recorder) -> MeiliClient:
    return MeiliClient("http://meilisearch:7700", "khoa-meili", "documents", transport=httpx2.MockTransport(rec))


def test_ensure_index_creates_missing_index_and_hides_all_but_id():
    rec = Recorder({
        ("GET", "/indexes/documents"): (404, {"code": "index_not_found"}),
        ("POST", "/indexes"): (202, {"taskUid": 1}),
        ("PATCH", "/indexes/documents/settings"): (202, {"taskUid": 2}),
    })
    assert asyncio.run(meili_client(rec).ensure_index()) == 2
    settings = json.loads(rec.requests[-1].content)
    assert settings["displayedAttributes"] == ["id"]
    assert {"tenant_id", "id"} <= set(settings["filterableAttributes"])
    assert settings["searchableAttributes"][-1] == "content"          # khớp nội dung xếp sau khớp trích yếu
    assert all(r.headers["authorization"] == "Bearer khoa-meili" for r in rec.requests)


def test_search_asks_only_for_ids():
    rec = Recorder({("POST", "/indexes/documents/search"): (200, {"hits": [{"id": "a"}, {"id": "b"}]})})
    ids = asyncio.run(meili_client(rec).search("tuyen sinh", ['tenant_id = "t"'], 20, 0))
    assert ids == ["a", "b"]
    body = json.loads(rec.requests[-1].content)
    assert body["attributesToRetrieve"] == ["id"] and body["filter"] == ['tenant_id = "t"']
    assert body["matchingStrategy"] == "all"                        # không bớt từ khi ít kết quả
    assert "attributesToSearchOn" not in body
    asyncio.run(meili_client(rec).search("tuyen sinh", ['tenant_id = "t"'], 2, 0, attributes=["summary"]))
    body = json.loads(rec.requests[-1].content)
    assert body["attributesToSearchOn"] == ["summary"] and body["matchingStrategy"] == "all"


def test_meilisearch_errors_raise_search_error():
    rec = Recorder({("POST", "/indexes/documents/search"): (400, {"code": "invalid_search_filter", "message": "x"})})
    with pytest.raises(SearchError, match="invalid_search_filter"):
        asyncio.run(meili_client(rec).search("q", [], 20, 0))


def test_wait_reports_failed_task():
    rec = Recorder({("GET", "/tasks/7"): (200, {"status": "failed", "error": {"code": "x"}})})
    with pytest.raises(SearchError):
        asyncio.run(meili_client(rec).wait(7))
