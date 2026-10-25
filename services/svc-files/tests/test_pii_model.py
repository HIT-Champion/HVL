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

"""Che thông tin cá nhân trong chữ gửi mô hình (F4.4, luồng B) với Ollama giả: trích yếu F4.1, nhúng (đoạn, câu hỏi,
trích yếu F4.3), câu trả lời F4.2 — mô hình chỉ thấy nhãn, người có quyền đọc văn bản vẫn thấy số thật ở câu trích.

CI không bật mô hình nên đây là chỗ duy nhất kiểm "không byte nào tới Ollama mà chưa che": mọi kiểm đọc thẳng các yêu
cầu Ollama giả đã nhận. Mọi số, email trong tệp là GIẢ LẬP, hợp lệ về định dạng (số ví dụ phổ biến, CCCD đuôi 0000xx,
email @example.com theo RFC 2606): có thể trùng số thật nhưng không thuộc người nào trong hệ thống.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from types import SimpleNamespace

import httpx2
import pytest
from fastapi.testclient import TestClient

from assist_fakes import (
    CHAT_MODEL, DIMS, EMBED_MODEL, PAGE_88, AskHasura, FakeIndexer, FakeRetriever, ask_token, good_answer, ollama,
    passage,
)
from assist_fakes import QUESTION as ASK_88
from assist_fakes import FakeOllama as AssistOllama
from conftest import (
    GOOD_SUMMARY, ISSUER, OLLAMA_MODEL, TENANT_A, FakeChunkIndex, FakeOllama, fake_tesseract, text_pdf,
)
from svc_files import pii
from svc_files.app import create_app
from svc_files.assist import extract, grounding, similar
from svc_files.assist.ai import NullAi
from svc_files.assist.answer import Assistant
from svc_files.assist.index import ChunkIndexer
from svc_files.assist.retrieve import Similar
from svc_files.config import Settings
from svc_files.docread.reader import Reader
from svc_files.docread.summarize import NullSummarizer, OllamaSummarizer, SummaryResult, check
from test_assist_chunks import link, text
from test_docread_api import DIFF_KEYS, fake_suggest, fake_text_lines, fake_tsv_lines, read, upload
from test_docread_api import ENV as READ_ENV

# giá trị giả lập
CCCD = "001205000017"
CMND = "172000045"
PHONE = "0912345678"
EMAIL = "nguyenvanb@example.com"
ACCOUNT = "0011 0041 23456"
VALUES = (CCCD, CMND, PHONE, EMAIL, ACCOUNT)

ASK_ENV = {
    "MOC_OIDC_ISSUER": ISSUER, "MOC_OIDC_JWKS_URL": "http://unused/jwks", "SEAWEEDFS_S3_ACCESS_KEY": "test",
    "SEAWEEDFS_S3_SECRET_KEY": "test", "HASURA_ADMIN_SECRET": "test", "MEILISEARCH_API_KEY": "test",
    "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0",
    "MOC_IMPORT_INTERVAL_S": "0",     # vòng nền nạp lô tắt (không tạo thư mục spool)
    "MOC_ARCHIVE_INTERVAL_S": "0", "MOC_FILES_MAX_MB": "1", "MOC_AI_URL": "", "MOC_AI_EMBED_DIMS": str(DIMS),
}


def run(coro):
    return asyncio.run(coro)


def leaks(sent: str, values) -> list[str]:
    """Giá trị nào còn trong ``sent`` ở bất kỳ cách viết nào: số so trên dãy chữ số đã bỏ phân cách (liền, nhóm cách /
    chấm / gạch, +84 thay số 0 đầu), email không phân biệt hoa thường và dạng ``%40``."""
    flat = re.sub(r"[\s.\-()+]", "", sent)
    low = sent.lower()
    out = []
    for value in values:
        if "@" in value:
            if value.lower() in low or value.lower().replace("@", "%40") in low:
                out.append(value)
            continue
        digits = re.sub(r"\D", "", value)
        if digits in flat or (digits.startswith("0") and digits[1:] in flat):
            out.append(value)
    return out


def fragments(sent: str, value: str, size: int) -> list[str]:
    """Các mẩu ``size`` chữ số liền nhau của ``value`` có trong một dãy chữ số của ``sent`` (bỏ phân cách đơn)."""
    digits = re.sub(r"\D", "", value)
    runs = re.findall(r"\d+(?:[ .\-\u00a0]\d+)*", sent)
    pieces = {digits[i:i + size] for i in range(len(digits) - size + 1)}
    return sorted({p for r in runs for p in pieces if p in re.sub(r"\D", "", r)})


def sent_text(requests: list[httpx2.Request]) -> str:
    """Mọi thứ Ollama giả đã nhận: byte thô và bản JSON đã giải mã (chữ có dấu không bị thoát ``\\uXXXX``)."""
    parts = []
    for r in requests:
        raw = r.content.decode("utf-8") if r.content else ""
        parts.append(raw)
        if raw:
            parts.append(json.dumps(json.loads(raw), ensure_ascii=False))
    return "\n".join(parts)


# --- 1. trích yếu F4.1 -----------------------------------------------------------------------------------------

LETTER = (
    "ĐƠN ĐỀ NGHỊ CẤP BẢN SAO BẰNG TỐT NGHIỆP\n"
    f"Người làm đơn: Nguyễn Văn B, số CCCD {CCCD}, CMND số {CMND}, cấp ngày 05/3/2021.\n"
    f"Thư điện tử: {EMAIL}. Số tài khoản {ACCOUNT} để nộp lệ phí 02 bản sao.\n"
    "Văn bản giả lập để chạy thử Mộc, không phải văn bản thật.\n"
    f"Điện thoại liên hệ: {PHONE}. Kính đề nghị Phòng Đào tạo xem xét, giải quyết. Trân trọng cảm ơn."
)
CUT = LETTER.index(PHONE) + 7       # MOC_AI_MAX_CHARS rơi giữa số điện thoại của chữ gốc: "…liên hệ: 0912345|678"


def test_summarizer_masks_before_cutting_and_counts_what_it_sent():
    # tiền đề: cắt trước rồi mới che thì mẩu số vắt qua chỗ cắt không còn là số điện thoại, bộ che bỏ qua
    assert PHONE[:7] in pii.mask_text(LETTER[:CUT])
    fake = FakeOllama()

    async def go():
        s = OllamaSummarizer("http://ollama:11434", OLLAMA_MODEL, max_chars=CUT,
                             transport=httpx2.MockTransport(fake))
        assert await s.probe()
        return await s.summarize(LETTER, timeout_s=5)

    assert run(go()) == SummaryResult(GOOD_SUMMARY, None, 5)       # 5 loại, mỗi loại một chỗ
    sent = sent_text(fake.requests)
    assert leaks(sent, VALUES) == []
    (chat,) = fake.calls("/api/chat")
    user = chat["messages"][1]["content"]
    assert len(user) == len("<van_ban>\n\n</van_ban>") + CUT      # vẫn cắt ở MOC_AI_MAX_CHARS, trên bản che
    for label in ("[CCCD]", "[CMND]", "[EMAIL]", "[STK]", "[SĐT]"):
        assert label in user                                        # nhãn trơn, không đánh số
    assert fragments(user, PHONE, 5) == []                          # không lọt quá 4 chữ số liền của số bị cắt
    assert "05/3/2021" in user and "02 bản sao" in user             # ngày, số lượng: không che nhầm


BROKEN = ("ĐƠN ĐỀ NGHỊ CẤP BẢN SAO BẰNG TỐT NGHIỆP\n"
          "Người làm đơn: Nguyễn Văn B, điện thoại 0912 345\n678, số CCCD của tôi là 001205\n000017,\n"
          "thư điện tử nguyenvanb@example.com. Văn bản giả lập để chạy thử Mộc, không phải văn bản thật.")


def test_summarizer_masks_numbers_broken_across_lines():
    # chữ PDF, OCR giữ xuống dòng giữa các nhóm số ("0912 345⏎678", "001205⏎000017"): xuống dòng là phân cách nhóm
    fake = FakeOllama()

    async def go():
        s = OllamaSummarizer("http://ollama:11434", OLLAMA_MODEL, transport=httpx2.MockTransport(fake))
        assert await s.probe()
        return await s.summarize(BROKEN, timeout_s=5)

    assert run(go()) == SummaryResult(GOOD_SUMMARY, None, 3)
    assert leaks(sent_text(fake.requests), (PHONE, CCCD, EMAIL)) == []
    (chat,) = fake.calls("/api/chat")
    assert "điện thoại [SĐT], số CCCD của tôi là [CCCD],\n" in chat["messages"][1]["content"]


def test_summarizer_counts_nothing_without_personal_data_or_without_a_call():
    fake = FakeOllama()

    async def go():
        s = OllamaSummarizer("http://ollama:11434", OLLAMA_MODEL, transport=httpx2.MockTransport(fake))
        before = await s.summarize(LETTER, timeout_s=5)            # chưa dò: không gửi gì
        assert await s.probe()
        return before, await s.summarize("Kế hoạch tổ chức hội nghị năm 2026, gồm 02 phiên.", timeout_s=5)

    before, plain = run(go())
    assert before == SummaryResult(None, "model_unavailable", 0) and plain == SummaryResult(GOOD_SUMMARY, None, 0)
    (chat,) = fake.calls("/api/chat")
    assert "Kế hoạch tổ chức hội nghị năm 2026, gồm 02 phiên." in chat["messages"][1]["content"]


def test_summarizer_counts_only_what_reaches_the_model():
    # số ở sau chỗ cắt không tới mô hình: không tính; nhãn bị cắt dở ("[SĐ") vẫn tính — chỗ đó đã được che
    fake = FakeOllama()
    body = f"Điện thoại liên hệ: {PHONE}. Kính đề nghị xem xét. Thư điện tử: {EMAIL}."
    cuts = {len("Điện thoại liên hệ: [SĐT]. Kính"): ("Kính", 1), len("Điện thoại liên hệ: [SĐ"): ("[SĐ", 1),
            400: ("[EMAIL].", 2)}

    async def go(max_chars):
        s = OllamaSummarizer("http://ollama:11434", OLLAMA_MODEL, max_chars=max_chars,
                             transport=httpx2.MockTransport(fake))
        assert await s.probe()
        return (await s.summarize(body, timeout_s=5)).masked

    for max_chars, (tail, count) in cuts.items():
        assert run(go(max_chars)) == count
        assert fake.calls("/api/chat")[-1]["messages"][1]["content"].endswith(tail + "\n</van_ban>")


# --- 2. trích yếu có nhãn bị loại ------------------------------------------------------------------------------


@pytest.mark.parametrize("content", [
    '{"trich_yeu": "Về việc ông A ([SĐT]) đề nghị cấp bản sao"}',
    '{"trich_yeu": "Về việc ông A (CCCD [CCCD-1]) đề nghị cấp bản sao"}',
    '{"trich_yeu": "Về việc gửi kết quả về [EMAIL-12]"}',
], ids=["sdt-tron", "cccd-danh-so", "email-hai-chu-so"])
def test_summary_with_a_mask_label_is_rejected(content):
    # mô hình chỉ thấy nhãn nên có thể chép nhãn vào trích yếu: loại như trích yếu có số điện thoại (model_rejected)
    assert check(content) is None


def test_the_same_summary_without_a_label_is_accepted():
    assert check('{"trich_yeu": "Về việc ông A đề nghị cấp bản sao"}') == "Về việc ông A đề nghị cấp bản sao"


# --- 3. tác tử đọc văn bản đến -----------------------------------------------------------------------------------

READ_LINES = ("UBND TINH MAU", "So: 99/TB-SMK", "Ha Noi, ngay 15 thang 10 nam 2026", "THONG BAO",
              "Lich hop giao ban thang 11 cua nha truong", f"Lien he: 0912 345 678, CCCD {CCCD}")


@pytest.fixture
def reading(tmp_path, scanner, store, verifier, hasura, meili, vault):
    """make(summarizer) → TestClient có Reader dùng quy tắc giả của test_docread_api (trích yếu "Lich hop…" chưa
    chắc nên hỏi mô hình)."""
    clients = []

    def make(summarizer) -> TestClient:
        directory = tmp_path / f"tess{len(clients)}"
        directory.mkdir()
        settings = Settings.from_env({**READ_ENV, "MOC_TESSERACT_BIN": str(fake_tesseract(directory))})
        reader = Reader(settings, hasura, store, summarizer=summarizer, suggest=fake_suggest,
                        text_lines=fake_text_lines, tsv_lines=fake_tsv_lines)
        client = TestClient(create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura,
                                       meili=meili, vault=vault, reader=reader))
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def test_reader_logs_how_much_was_masked_but_the_audit_row_does_not(reading, make_token, hasura, log_records):
    fake = FakeOllama()
    s = OllamaSummarizer("http://ollama:11434", OLLAMA_MODEL, transport=httpx2.MockTransport(fake))
    assert run(s.probe())
    client = reading(s)
    token = make_token(sub="u-van-thu")
    file_id = upload(client, token, text_pdf(*READ_LINES))
    r = read(client, token, file_id)
    assert r.status_code == 200, r.text
    assert r.json()["summary_source"] == "model"

    (chat,) = fake.calls("/api/chat")
    user = chat["messages"][1]["content"]
    assert "Lich hop giao ban" in user and "[SĐT]" in user and "[CCCD]" in user
    assert leaks(sent_text(fake.requests), ("0912 345 678", CCCD)) == []

    (done,) = [x for x in log_records if x["event"] == "office.intake.read"]
    assert done["masked"] == 2 and done["cached"] is False
    (event,) = hasura.agent_events                          # sổ: đúng các khóa cũ, không có "masked"
    assert set(event["diff"]) == DIFF_KEYS and "masked" not in event["diff"]
    assert leaks(json.dumps(log_records, ensure_ascii=False), ("0912 345 678", CCCD)) == []

    assert read(client, token, file_id).json()["cached"] is True     # gợi ý đã lưu: không gọi mô hình
    cached = [x for x in log_records if x["event"] == "office.intake.read" and x["cached"]]
    assert [x["masked"] for x in cached] == [0]


def test_reader_without_a_model_logs_zero(reading, make_token, log_records):
    client = reading(NullSummarizer())
    token = make_token()
    assert read(client, token, upload(client, token, text_pdf(*READ_LINES))).status_code == 200
    (done,) = [x for x in log_records if x["event"] == "office.intake.read"]
    assert done["masked"] == 0


# --- 4. nhúng: đoạn, câu hỏi, trích yếu F4.3 ---------------------------------------------------------------------

SUMMARY = f"Về việc ông Nguyễn Văn B (số {PHONE[:4]} {PHONE[4:7]} {PHONE[7:]}) đề nghị cấp bản sao bằng tốt nghiệp"


def embeds(fake: AssistOllama) -> list[str]:
    """Chuỗi đã gửi ``/api/embed``, bỏ lần nạp trước ("Mộc")."""
    return [s for c in fake.calls("/api/embed") if c["input"] != ["Mộc"] for s in c["input"]]


def test_chunks_are_embedded_masked_but_indexed_as_written(hasura):
    fake = AssistOllama()
    ai = ollama(fake, chat=None)
    page = [f"Người làm đơn: Nguyễn Văn B, số CCCD {CCCD}.", f"Thư điện tử: {EMAIL}, điện thoại {PHONE}.",
            "Văn bản giả lập để chạy thử Mộc, không phải văn bản thật."]
    hasura.add_document(TENANT_A, SUMMARY, files=[link(text(page), file_id="f-pii")], assignments=[],
                        updated_at="2026-10-21T08:00:00+00:00")
    index = FakeChunkIndex()
    indexer = ChunkIndexer(index, hasura, ai, dims=DIMS, batch=100)
    run(indexer.sync_once())
    assert run(indexer.embed_once()) == len(index.docs) > 0
    sent = embeds(fake)
    assert len(sent) == len(index.docs)
    assert leaks(sent_text(fake.requests), (CCCD, EMAIL, PHONE)) == []
    assert any("[CCCD]" in s and "[EMAIL]" in s for s in sent) and all("[SĐT]" in s for s in sent)
    # chỉ mục giữ chữ gốc: tìm theo số vẫn được, text_sha không đổi
    stored = "\n".join(f"{d.get('summary')}\n{d.get('text')}" for d in index.docs.values())
    assert CCCD in stored and EMAIL in stored and "0912 345 678" in stored


def test_chunks_with_numbers_broken_across_lines_are_embedded_masked(hasura):
    # split_page giữ xuống dòng giữa các dòng PDF: số bị dàn trang ngắt dòng vẫn phải che ở lối ra embed
    fake = AssistOllama()
    ai = ollama(fake, chat=None)
    page = ["Người làm đơn: Nguyễn Văn B, điện thoại 0912 345", "678, số CCCD của tôi là 001205",
            "000017, thư điện tử nguyenvanb@example.com.", "Văn bản giả lập để chạy thử Mộc, không phải văn bản thật."]
    hasura.add_document(TENANT_A, "Về việc đề nghị cấp bản sao bằng tốt nghiệp",
                        files=[link(text(page), file_id="f-pii")], assignments=[],
                        updated_at="2026-10-21T08:00:00+00:00")
    index = FakeChunkIndex()
    indexer = ChunkIndexer(index, hasura, ai, dims=DIMS, batch=100)
    run(indexer.sync_once())
    assert run(indexer.embed_once()) == len(index.docs) > 0
    stored = "\n".join(str(d.get("text")) for d in index.docs.values())
    assert "0912 345\n678" in stored and "001205\n000017" in stored        # tiền đề: đoạn giữ xuống dòng của chữ gốc
    assert leaks(sent_text(fake.requests), (PHONE, CCCD, EMAIL)) == []
    assert any("[SĐT]" in s and "[CCCD]" in s and "[EMAIL]" in s for s in embeds(fake))


@pytest.fixture
def asking(scanner, store, verifier, meili, vault, signing_key):
    """make(passages, ai, env) → SimpleNamespace(client, hasura, retriever, ask(question, mode))."""
    clients = []

    def make(passages, ai, env=None) -> SimpleNamespace:
        settings = Settings.from_env({**ASK_ENV, **(env or {})})
        hasura = AskHasura()
        retriever = FakeRetriever(list(passages))
        indexer = FakeIndexer()
        assistant = Assistant(settings, retriever=retriever, ai=ai, indexer=indexer, hasura=hasura)
        client = TestClient(create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura,
                                       meili=meili, vault=vault, assistant=assistant, chunk_indexer=indexer, ai=ai))
        client.__enter__()
        clients.append(client)
        token = ask_token(signing_key)

        def ask(question: str, mode: str = "extract"):
            return client.post("/api/documents/ask", headers={"Authorization": f"Bearer {token}"},
                               json={"question": question, "mode": mode})

        return SimpleNamespace(client=client, hasura=hasura, retriever=retriever, ask=ask)

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def test_question_is_embedded_masked_but_searched_as_asked(asking):
    fake = AssistOllama()
    env = asking([passage(f"Điện thoại liên hệ của người làm đơn là {PHONE}.")], ollama(fake))
    question = f"Số {PHONE} là của ai?"
    assert env.ask(question).status_code == 200
    (sent,) = embeds(fake)
    assert sent.endswith("\nQuery: Số [SĐT] là của ai?")          # tiền tố câu hỏi của Qwen3-Embedding, rồi bản che
    assert leaks(sent_text(fake.requests), (PHONE,)) == []
    (call,) = env.retriever.calls
    assert PHONE in call["q"]                                       # tìm tại chỗ theo quyền người hỏi: câu gốc


def test_similar_subject_is_embedded_masked():
    class Stub:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def similar(self, scope, *, q, vector, limit, where):
            self.calls.append({"q": q, "vector": vector})
            return Similar([], vector is not None)

    fake = AssistOllama()
    retriever = Stub()
    assistant = SimpleNamespace(ai=ollama(fake, chat=None), indexer=FakeIndexer(), retriever=retriever)
    hits, terms, semantic, _ = run(similar.find(assistant, TENANT_A, uuid.uuid4(), SUMMARY, 5))
    assert hits == [] and terms > 0 and semantic is True
    (sent,) = embeds(fake)
    assert sent == similar.SIMILAR_PREFIX + "ông Nguyễn Văn B (số [SĐT]) đề nghị cấp bản sao bằng tốt nghiệp"
    assert leaks(sent_text(fake.requests), (PHONE,)) == []
    assert "0912" in retriever.calls[0]["q"]                       # tìm từ khóa vẫn bằng trích yếu gốc


# --- 5. câu trả lời do mô hình viết ------------------------------------------------------------------------------

P1, P2, P3 = "0912 345 678", "0812 345 678", "0903 123 456"      # ba số đầu đoạn, có dấu cách
P4 = "0987 654 321"                                               # trong câu tốt nhất ở cuối đoạn, và trong câu hỏi
PHONES = (P1, P2, P3, P4)
QUESTION = f"Số điện thoại {P4} là của ai?"
SYMBOL = "15/ĐN-ĐT"
DON = "8c1d2e3f-0000-4000-8000-0000000000d0"
FILLER = ("Hồ sơ gồm đơn theo mẫu, bản sao giấy tờ tùy thân và biên lai nộp lệ phí cấp bản sao. "
          "Người làm đơn nhận kết quả tại bộ phận một cửa của nhà trường. ")
SIZE = 1200
P3_AT = 497     # cửa sổ 700 ký tự quanh câu cuối của đoạn 1200 ký tự bắt đầu ở 502 — giữa P3 trên chữ gốc


def _filler(n: int) -> str:
    """Đúng ``n`` ký tự chữ đệm, không chữ số, hết câu ở cuối (". ") để câu sau là một câu riêng."""
    return (FILLER * (n // len(FILLER) + 2))[: n - 2] + ". "


def _passage_text() -> str:
    head = (f"Đơn đề nghị cấp bản sao bằng tốt nghiệp gửi Phòng Đào tạo. Văn phòng khoa nhận hồ sơ qua số {P1}. "
            f"Bộ phận một cửa trả kết quả qua số {P2}. ")
    third = f"Tổng đài hỗ trợ: {P3}. "
    tail = f"Số điện thoại liên hệ của người làm đơn là {P4}."
    before = head + _filler(P3_AT - len(head) - len("Tổng đài hỗ trợ: ")) + third
    out = before + _filler(SIZE - len(before) - len(tail)) + tail
    assert len(out) == SIZE and out.index(P3) == P3_AT
    return out


PASSAGE_TEXT = _passage_text()
BEST = f"Số điện thoại liên hệ của người làm đơn là {P4}."


def test_cutting_before_masking_would_leak_a_piece_of_a_number():
    # tiền đề của ca 5: cắt cửa sổ trên chữ gốc rồi mới che thì P3 bị cắt đôi, mẩu còn lại lọt qua bộ che
    ps = [passage(PASSAGE_TEXT, document_id=DON, page=2, symbol=SYMBOL)]
    best = extract.answer(QUESTION, ps).best
    assert PASSAGE_TEXT[slice(*best[ps[0].chunk_id])] == BEST
    naive = pii.mask_text(extract.excerpt(PASSAGE_TEXT, best[ps[0].chunk_id], grounding.SOURCE_CHARS))
    assert fragments(naive, P3, 3) != []


def test_model_reads_numbered_labels_and_the_user_still_gets_the_numbers(asking, log_records):
    fake = AssistOllama(reply=good_answer("Số liên hệ là [SĐT-1]."))
    env = asking([passage(PASSAGE_TEXT, document_id=DON, page=2, symbol=SYMBOL)], ollama(fake, embed=None))
    r = env.ask(QUESTION, "generate")
    assert r.status_code == 200, r.text
    body = r.json()

    # (a) mô hình không thấy số nào, kể cả mẩu 3 chữ số; câu hỏi và nguồn cùng nhãn [SĐT-1]
    (chat,) = fake.calls("/api/chat")
    sent = sent_text(fake.requests)
    assert leaks(sent, PHONES) == []
    for phone in PHONES:
        assert fragments(sent, phone, 3) == [], phone
    user = chat["messages"][1]["content"]
    assert "<cau_hoi>\nSố điện thoại [SĐT-1] là của ai?\n</cau_hoi>" in user
    # (b) câu tốt nhất vẫn nằm trong nguồn 1, mang cùng nhãn với câu hỏi
    block = re.search(r'<nguon so="1"[^>]*>\n(.*?)\n</nguon>', user, re.S)
    assert block and "Số điện thoại liên hệ của người làm đơn là [SĐT-1]." in block.group(1)
    assert f'ky_hieu="{SYMBOL}" trang="2"' in user

    # (c) người hỏi (có quyền đọc) nhận câu trích nguyên văn có số thật; nguồn đúng như dữ liệu
    assert body["extract"]["text"] == f"“{BEST}” [1]"
    (src,) = body["sources"]
    assert P4 in src["excerpt"] and src["n"] == 1 and src["page"] == 2 and src["symbol"] == SYMBOL
    assert src["document_id"] == DON and src["cited"] is True

    # (d) câu trả lời của mô hình giữ nhãn, máy chủ vẫn gán trích dẫn [1]
    assert body["answer"] == {"text": "Số liên hệ là [SĐT-1] [1].", "source": "model", "model": CHAT_MODEL}
    assert body["warnings"] == []

    # (e) nhật ký đếm số chỗ đã che; lối ra không phải che thêm gì
    (done,) = [x for x in log_records if x["event"] == "office.assist.asked"]
    assert done["masked"] == 5             # hợp đồng đòi ≥ 4: câu hỏi 1 + đoạn 4 (đếm cả số ngoài cửa sổ)
    assert [x for x in log_records if x["event"] == "office.assist.pii_at_egress"] == []
    assert leaks(json.dumps(log_records, ensure_ascii=False), PHONES) == []
    assert "masked" not in env.hasura.agent_events[0]["diff"]       # sổ không đổi


@pytest.mark.parametrize(("reply", "reason"), [
    ("Số liên hệ là 0987 654 322.", "unsupported_number"),        # số không có trong bản che
    # chỉ nhắc lại câu hỏi mô hình đã đọc (kể cả nhãn): không có gì mới để gán nguồn — validate phải so với câu hỏi
    # đã che, không phải câu hỏi gốc (với câu gốc thì "[SĐT-1]" thành term mới, có ở nguồn, và lọt qua)
    ("Số điện thoại [SĐT-1].", "unsupported"),
], ids=["so-bia", "nhac-lai-cau-hoi"])
def test_rejected_model_answer_logs_the_mask_count(asking, log_records, reply, reason):
    fake = AssistOllama(reply=good_answer(reply))
    env = asking([passage(PASSAGE_TEXT, document_id=DON, page=2, symbol=SYMBOL)], ollama(fake, embed=None))
    body = env.ask(QUESTION, "generate").json()
    assert body["answer"]["source"] == "extract" and body["warnings"] == ["model_rejected"]
    (rejected,) = [x for x in log_records if x["event"] == "office.assist.model_rejected"]
    assert rejected["reason"] == reason and rejected["masked"] == 5
    (done,) = [x for x in log_records if x["event"] == "office.assist.asked"]
    assert done["masked"] == 5


def test_extract_mode_logs_zero(asking, log_records):
    env = asking([passage(PASSAGE_TEXT, document_id=DON)], NullAi())
    assert env.ask(QUESTION).json()["extract"]["text"] == f"“{BEST}” [1]"
    (done,) = [x for x in log_records if x["event"] == "office.assist.asked"]
    assert done["masked"] == 0


MAILS = ("phong.dao-tao+cv@dhm.example.edu.vn", "van.phong.khoa.cong.nghe@dhm.example.edu.vn",
         "mot.cua.tiep.nhan.ho.so@dhm.example.edu.vn")
LONG = ("Người làm đơn đề nghị cấp bản sao bằng tốt nghiệp nộp đơn theo mẫu "
        + "kèm bản sao giấy tờ tùy thân và biên lai nộp lệ phí " * 10 + "tại bộ phận một cửa.")


def test_best_sentence_moves_to_masked_coordinates():
    # nhãn ngắn hơn địa chỉ thư: dùng toạ độ câu tốt nhất của chữ gốc trên bản che thì cửa sổ lệch phải ~90 ký tự và
    # cắt mất đầu câu dài — window() đổi toạ độ nên cả câu vẫn trong nguồn
    text = (f"Hộp thư nhận hồ sơ: {MAILS[0]}, {MAILS[1]}, {MAILS[2]}. " + LONG + " "
            + "Kết quả trả trong năm ngày làm việc. " * 8)
    ps = [passage(text)]
    question = "Người làm đơn đề nghị cấp bản sao bằng tốt nghiệp nộp gì?"
    best = extract.answer(question, ps).best
    assert text[slice(*best[ps[0].chunk_id])] == LONG and 500 < len(LONG) < grounding.SOURCE_CHARS - 60
    (src,) = grounding.sources(ps, best, max_chars=2800, masker=pii.Masker())
    assert LONG in src.text and leaks(src.text, MAILS) == []


def test_number_split_by_a_blank_line_is_masked_once_whitespace_is_collapsed(log_records):
    # hai ký tự trắng liền (dòng trống) không là phân cách: "0912\n\n345 678" chưa phải số; đoạn trích gộp khoảng
    # trắng thì thành số — sources() che nốt bằng cùng bộ che, lối ra không phải che thêm
    ps = [passage("Văn phòng khoa nhận đơn đề nghị cấp bản sao bằng tốt nghiệp, điện thoại 0912\n\n345 678.")]
    assert pii.mask(ps[0].text).spans == ()
    masker = pii.Masker()
    asked = masker.mask(f"Văn phòng khoa có số {P1} không?").text
    (src,) = grounding.sources(ps, {}, max_chars=2800, masker=masker)
    assert src.text.endswith("điện thoại [SĐT-1].") and masker.total == 2
    fake = AssistOllama()
    run(ollama(fake, embed=None).chat(grounding.messages([src], asked), format=grounding.FORMAT,
                                      options=grounding.OPTIONS, timeout_s=5))
    assert leaks(sent_text(fake.requests), (P1,)) == []
    assert [x for x in log_records if x["event"] == "office.assist.pii_at_egress"] == []


def test_context_without_personal_data_is_unchanged():
    # kho hỏi đáp mẫu không có chỗ nào bị che: ngữ cảnh mô hình y hệt trước F4.4, số đo do-hoi-dap không đổi
    ps = [passage(PAGE_88), passage(PAGE_88.replace("3,2", "3,6"), page=2)]
    best = extract.answer(ASK_88, ps).best
    masker = pii.Masker()
    assert masker.mask(ASK_88).text == ASK_88
    assert grounding.sources(ps, best, max_chars=2800, masker=masker) == grounding.sources(ps, best, max_chars=2800)
    assert masker.total == 0


# --- 6. lối ra chat ----------------------------------------------------------------------------------------------


def test_chat_masks_at_egress_and_warns_the_caller_forgot(log_records):
    fake = AssistOllama()
    ai = ollama(fake, embed=None)
    messages = [{"role": "system", "content": grounding.SYSTEM},
                {"role": "user", "content": f"<cau_hoi>\nAi có số {P1} và email {EMAIL}?\n</cau_hoi>"}]
    result = run(ai.chat(messages, format=grounding.FORMAT, options=grounding.OPTIONS, timeout_s=5))
    assert result.content == good_answer()
    (chat,) = fake.calls("/api/chat")
    assert chat["messages"][1]["content"] == "<cau_hoi>\nAi có số [SĐT] và email [EMAIL]?\n</cau_hoi>"
    assert chat["messages"][0] == messages[0]
    assert leaks(sent_text(fake.requests), (P1, EMAIL)) == []
    assert P1 in messages[1]["content"]                             # không sửa message của chỗ gọi
    (warned,) = [x for x in log_records if x["event"] == "office.assist.pii_at_egress"]
    assert warned == {"event": "office.assist.pii_at_egress", "masked": 2}


def test_chat_that_was_masked_upstream_does_not_warn(log_records):
    fake = AssistOllama()
    ai = ollama(fake, embed=None)
    masker = pii.Masker()
    content = masker.mask(f"Ai có số {P1}?").text
    run(ai.chat([{"role": "user", "content": content}], format=grounding.FORMAT, options=grounding.OPTIONS,
                timeout_s=5))
    (chat,) = fake.calls("/api/chat")
    assert chat["messages"][0]["content"] == "Ai có số [SĐT-1]?"    # nhãn đánh số giữ nguyên: bản che idempotent
    assert [x for x in log_records if x["event"] == "office.assist.pii_at_egress"] == []


def test_unavailable_chat_sends_nothing_and_does_not_warn(log_records):
    fake = AssistOllama(models=[EMBED_MODEL])
    ai = ollama(fake, embed=None)
    result = run(ai.chat([{"role": "user", "content": f"Số {P1}"}], format=grounding.FORMAT,
                         options=grounding.OPTIONS, timeout_s=5))
    assert result.content is None and fake.calls("/api/chat") == []
    assert [x for x in log_records if x["event"] == "office.assist.pii_at_egress"] == []
