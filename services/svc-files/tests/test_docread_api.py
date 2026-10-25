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

"""POST /api/files/{id}/read (F4.1): quyền, văn bản hạn chế, lỗi tệp, sổ kiểm toán của tác tử, OCR, mô hình.

Quy tắc (luồng C) được thay bằng quy tắc giả qua ``Reader(suggest=…, text_lines=…, tsv_lines=…)``: test này kiểm luồng
đọc, không kiểm độ đúng của quy tắc. Tesseract giả, Ollama giả — không cần dịch vụ nào chạy.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import signal
import uuid
from datetime import date

import httpx2
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import GOOD_SUMMARY, ISSUER, OLLAMA_MODEL, TENANT_A, FakeOllama, fake_tesseract, text_pdf
from svc_files.app import create_app
from svc_files.config import Settings
from svc_files.docread.layout import Line
from svc_files.docread.reader import Reader
from svc_files.docread.rules import Field, Suggestion
from svc_files.docread.summarize import NullSummarizer, OllamaSummarizer

LETTER_LINES = ("UBND TINH MAU", "So: 99/TB-SMK", "Ha Noi, ngay 15 thang 10 nam 2026", "THONG BAO",
                "Lich hop giao ban thang 11 cua nha truong")
LETTER = text_pdf(*LETTER_LINES)
# trích yếu quy tắc tin cậy cao (dòng V/v): ở chế độ fallback không hỏi mô hình
CONG_VAN = text_pdf("UBND TINH MAU", "So: 07/UBND-VP", "V/v ra soat chung chi ngoai ngu cua giang vien")
DIFF_KEYS = {"user_id", "file_id", "status", "method", "pages", "found", "summary_source", "model", "duration_ms",
             "reason"}
TODAY = date(2026, 10, 21)
ENV = {
    "MOC_OIDC_ISSUER": ISSUER, "MOC_OIDC_JWKS_URL": "http://unused/jwks", "SEAWEEDFS_S3_ACCESS_KEY": "test",
    "SEAWEEDFS_S3_SECRET_KEY": "test", "HASURA_ADMIN_SECRET": "test", "MEILISEARCH_API_KEY": "test",
    "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0",
    "MOC_IMPORT_INTERVAL_S": "0",     # vòng nền nạp lô tắt (không tạo thư mục spool)
    "MOC_ARCHIVE_INTERVAL_S": "0", "MOC_FILES_MAX_MB": "1", "MOC_AI_URL": "",
    "MOC_ASK_ENABLED": "false",     # không chạy vòng chỉ mục đoạn F4.2 (nó gọi Meilisearch thật)
}


# --- quy tắc giả ------------------------------------------------------------------------------------------


def fake_text_lines(pages):
    return [Line(row.strip(), 0.0, 1.0, i / 40, no) for no, page in enumerate(pages, 1)
            for i, row in enumerate(page.split("\n")) if row.strip()]


def fake_tsv_lines(pages):
    out = []
    for no, page in enumerate(pages, 1):
        groups: dict[tuple, list[str]] = {}
        for row in page.strip("\n").split("\n")[1:]:
            cols = row.split("\t")
            if cols[0] == "5" and cols[11]:
                groups.setdefault(tuple(cols[2:5]), []).append(cols[11])
        out += [Line(" ".join(words), 0.0, 1.0, i / 40, no) for i, words in enumerate(groups.values())]
    return out


SEEN: list[dict] = []


def fake_suggest(lines, *, today, type_codes=None):
    SEEN.append({"today": today, "type_codes": type_codes})
    text = "\n".join(line.text for line in lines)
    fields = {}
    if m := re.search(r"S[oố]: (\S+)", text):
        fields["symbol"] = Field(m.group(1), "high")
    if m := re.search(r"ngay (\d+) thang (\d+) nam (\d{4})", text):
        fields["issued_on"] = Field(date(int(m[3]), int(m[2]), int(m[1])).isoformat(), "high")
    if ("THONG BAO" in text or "THÔNG BÁO" in text) and (type_codes is None or "TB" in type_codes):
        fields["type_code"] = Field("TB", "high")
    if m := re.search(r"^V/v (.+)$", text, re.M):
        fields["summary"] = Field("Về việc " + m.group(1), "high")
    elif m := re.search(r"^(L[iị]ch h[oọ]p .+)$", text, re.M):
        fields["summary"] = Field(m.group(1), "low")
    return Suggestion(fields, ("future_date",) if "2099" in text else (), text)


# --- dựng app ---------------------------------------------------------------------------------------------


def ready_ollama(fake: FakeOllama, **kw) -> OllamaSummarizer:
    s = OllamaSummarizer("http://ollama:11434", OLLAMA_MODEL, transport=httpx2.MockTransport(fake), **kw)
    assert asyncio.run(s.probe())
    return s


@pytest.fixture
def reading(tmp_path, scanner, store, verifier, hasura, meili, vault):
    """make(env=…, summarizer=…, suggest=…) → TestClient có Reader dùng quy tắc giả và tesseract giả."""
    clients = []

    def make(*, env=None, summarizer=None, suggest=fake_suggest, tesseract=None) -> TestClient:
        directory = tmp_path / f"tess{len(clients)}"
        directory.mkdir()
        settings = Settings.from_env({**ENV, "MOC_TESSERACT_BIN": str(tesseract or fake_tesseract(directory)),
                                      **(env or {})})
        reader = Reader(settings, hasura, store, summarizer=summarizer or NullSummarizer(), suggest=suggest,
                        text_lines=fake_text_lines, tsv_lines=fake_tsv_lines, today=lambda: TODAY)
        app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                         vault=vault, reader=reader)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    SEEN.clear()
    yield make
    for client in clients:
        client.__exit__(None, None, None)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def upload(client, token, data: bytes = LETTER, *, name="cong-van.pdf", mime="application/pdf",
           restricted=False) -> str:
    r = client.post("/api/files" + ("?restricted=true" if restricted else ""), headers=auth(token),
                    files={"file": (name, data, mime)})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def read(client, token, file_id: str, *, force: bool = False):
    return client.post(f"/api/files/{file_id}/read" + ("?force=true" if force else ""), headers=auth(token))


def png(size=(1240, 1754)) -> bytes:
    out = io.BytesIO()
    Image.new("L", size, 255).save(out, "PNG")
    return out.getvalue()


# --- đọc thành công, sổ kiểm toán ---------------------------------------------------------------------------


def test_reads_a_text_pdf_and_logs_one_agent_event(reading, make_token, hasura):
    client = reading()
    token = make_token(sub="u-van-thu")
    file_id = upload(client, token)
    r = read(client, token, file_id)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["file_id"] == file_id and body["status"] == "ok" and body["method"] == "text" and body["pages"] == 1
    assert body["fields"] == {
        "symbol": {"value": "99/TB-SMK", "confidence": "high", "source": "rule"},
        "issued_on": {"value": "2026-10-15", "confidence": "high", "source": "rule"},
        "type_code": {"value": "TB", "confidence": "high", "source": "rule"},
        "summary": {"value": "Lich hop giao ban thang 11 cua nha truong", "confidence": "low", "source": "rule"},
    }
    assert body["summary_source"] == "rule" and body["model"] is None and body["cached"] is False
    assert body["warnings"] == ["model_unavailable"]       # trích yếu quy tắc chưa chắc, mà không có mô hình
    assert isinstance(body["duration_ms"], int) and body["read_at"].startswith("2026-10-21T08:00:00")
    assert SEEN[-1] == {"today": TODAY, "type_codes": frozenset({"CV", "QĐ", "TB", "KH"})}

    # một dòng sổ của tác tử: vai trò agent, danh tính tác tử, thuê ước trong token — người làm do preset đặt
    (event,) = hasura.agent_events
    assert event["actor_id"] == "moc-doc-reader" and event["actor_kind"] == "agent"
    assert event["tenant_id"] == str(TENANT_A)
    assert event["action"] == "intake.suggested" and event["entity"] == "core.files" and event["entity_id"] == file_id
    assert set(event["diff"]) == DIFF_KEYS
    assert event["diff"] == {**event["diff"], "user_id": "u-van-thu", "file_id": file_id, "status": "ok",
                             "method": "text", "pages": 1, "found": "symbol,issued_on,type_code,summary",
                             "summary_source": "rule", "model": None, "reason": None}
    assert not any(isinstance(v, list | dict) for v in event["diff"].values())    # không mảng: giao diện hiểu [cũ, mới]
    dumped = json.dumps(event, ensure_ascii=False)
    assert not any(v in dumped for v in ("99/TB-SMK", "2026-10-15", "Lich hop", "UBND", "cong-van.pdf"))
    (call,) = [c for c in hasura.agent_calls if c["op"] == "LuuGoiY"]
    assert call == {"role": "agent", "tenant_id": str(TENANT_A), "user_id": "moc-doc-reader",
                    "request_id": call["request_id"], "op": "LuuGoiY"}
    assert call["request_id"] == r.headers["x-request-id"] == event["request_id"]

    saved = hasura.suggestions[file_id]
    assert saved["requested_by"] == "u-van-thu" and saved["agent_id"] == "moc-doc-reader"
    assert saved["fields"] == body["fields"] and saved["warnings"] == body["warnings"]


def test_cached_result_is_returned_without_logging_force_reads_again(reading, make_token, hasura, store):
    client = reading()
    token = make_token()
    file_id = upload(client, token)
    first = read(client, token, file_id).json()
    reads = len(store.reads)
    again = read(client, token, file_id)
    assert again.status_code == 200 and again.json()["cached"] is True
    assert {k: v for k, v in again.json().items() if k != "cached"} == {k: v for k, v in first.items()
                                                                         if k != "cached"}
    assert len(hasura.agent_events) == 1 and len(store.reads) == reads      # không ghi sổ, không đọc kho
    forced = read(client, token, file_id, force=True)
    assert forced.status_code == 200 and forced.json()["cached"] is False
    assert len(hasura.agent_events) == 2 and len(store.reads) == reads + 1
    assert len([q for q in hasura.admin_queries if "LoaiVanBan" in q]) == 1    # danh mục loại giữ 10 phút


def test_logs_have_no_document_text(reading, make_token, log_records):
    client = reading()
    token = make_token()
    file_id = upload(client, token)
    assert read(client, token, file_id).status_code == 200
    (done,) = [r for r in log_records if r["event"] == "office.intake.read"]
    assert {"file_id", "tenant_id", "actor_id", "method", "pages", "chars", "found", "duration_ms", "model",
            "cached"} <= set(done)
    assert done["chars"] > 0 and done["found"] == "symbol,issued_on,type_code,summary"
    dumped = json.dumps(log_records, ensure_ascii=False)
    assert not any(v in dumped for v in ("99/TB-SMK", "Lich hop", "UBND TINH", "THONG BAO"))


def test_empty_result_when_rules_find_nothing(reading, make_token, hasura):
    client = reading(suggest=lambda lines, **kw: Suggestion({}, ("low_text",), ""))
    token = make_token()
    body = read(client, token, upload(client, token)).json()
    assert body["status"] == "empty" and body["fields"] == {} and body["summary_source"] == "none"
    assert body["warnings"] == ["low_text", "model_unavailable"]
    assert hasura.agent_events[0]["diff"]["status"] == "empty" and hasura.agent_events[0]["diff"]["found"] == ""


def test_rule_output_is_cleaned(reading, make_token):
    def sloppy(lines, **kw):
        return Suggestion({
            "symbol": Field("  12/QĐ-​UBND \n", "high"), "urgency": Field("gap", "high"),
            "issued_on": Field("2026-02-31", "high"), "issuer_name": Field("UBND", "chac"),
            "summary": Field("Về việc " + "x" * 600, "medium"), "la": Field("?", "high"),
        }, ("future_date", "future_date", "ma_la"), "")
    client = reading(suggest=sloppy)
    token = make_token()
    body = read(client, token, upload(client, token)).json()
    assert set(body["fields"]) == {"symbol", "summary"}
    assert body["fields"]["symbol"]["value"] == "12/QĐ-UBND" and len(body["fields"]["summary"]["value"]) == 500
    assert body["warnings"] == ["future_date", "model_unavailable"]


def test_a_crash_in_the_rules_is_an_empty_result(reading, make_token, log_records):
    def broken(lines, **kw):
        raise ValueError("Lich hop giao ban")          # thông điệp lỗi có chữ của văn bản: không được vào nhật ký
    client = reading(suggest=broken)
    token = make_token()
    assert read(client, token, upload(client, token)).json()["status"] == "empty"
    (failed,) = [r for r in log_records if r["event"] == "office.intake.rules_failed"]
    assert failed["error"] == "ValueError" and "Lich hop" not in json.dumps(log_records)


# --- quyền ------------------------------------------------------------------------------------------------


def test_needs_a_token(reading, make_token):
    client = reading()
    file_id = upload(client, make_token())
    assert client.post(f"/api/files/{file_id}/read").status_code == 401


def test_only_clerks_read(reading, make_token, store):
    client = reading()
    token = make_token(sub="u-chuyen-vien", role="staff")
    file_id = upload(client, token)
    r = read(client, token, file_id)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "forbidden"
    assert store.reads == []


def test_files_of_others_are_404(reading, make_token, hasura, store):
    client = reading()
    file_id = upload(client, make_token(sub="u-van-thu"))
    hasura.shared.add(uuid.UUID(file_id))        # người kia xem được tệp (gắn vào văn bản họ đọc) — vẫn không đọc
    for token in (make_token(sub="u-van-thu-2"), make_token(sub="u-van-thu", tenant=str(uuid.uuid4()))):
        r = read(client, token, file_id)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    assert read(client, make_token(), str(uuid.uuid4())).status_code == 404
    assert store.reads == [] and hasura.agent_events == []


def test_restricted_file_is_409_before_any_byte_is_read(reading, make_token, hasura, store):
    fake = FakeOllama()
    client = reading(summarizer=ready_ollama(fake))
    token = make_token()
    file_id = upload(client, token, LETTER, restricted=True)
    for force in (False, True):
        r = read(client, token, file_id, force=force)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "restricted"
    assert store.reads == []                                    # kho chưa mở tệp lần nào
    assert fake.calls("/api/chat") == []                        # mô hình không nhận gì
    assert hasura.agent_events == [] and hasura.suggestions == {}


def test_plain_file_of_a_restricted_document_is_409_before_cache_and_bytes(reading, make_token, hasura, store):
    # tệp rõ gắn vào văn bản hạn chế: có từ trước F3.7, hoặc văn bản được đánh dấu hạn chế sau lần đọc trước
    fake = FakeOllama()
    client = reading(summarizer=ready_ollama(fake))
    token = make_token()
    never_read, read_before = upload(client, token), upload(client, token)
    assert read(client, token, read_before).status_code == 200          # gợi ý đã lưu khi văn bản còn thường
    store.reads.clear()
    chats, events = len(fake.calls("/api/chat")), len(hasura.agent_events)
    hasura.in_restricted |= {uuid.UUID(never_read), uuid.UUID(read_before)}
    for file_id in (never_read, read_before):
        for force in (False, True):
            r = read(client, token, file_id, force=force)
            assert r.status_code == 409 and r.json()["detail"]["code"] == "restricted"
            assert "fields" not in r.text and "99/TB-SMK" not in r.text      # gợi ý đã lưu cũng không trả
    assert store.reads == []                                    # kho chưa mở tệp lần nào
    assert len(fake.calls("/api/chat")) == chats                # mô hình không nhận thêm gì
    assert len(hasura.agent_events) == events and str(never_read) not in hasura.suggestions


def test_database_trigger_sealing_the_file_is_409(reading, make_token, hasura):
    client = reading()
    token = make_token()
    file_id = upload(client, token)
    hasura.sealed.add(file_id)       # tệp vừa gắn vào văn bản hạn chế sau bước kiểm vị trí: trigger CSDL chặn
    r = read(client, token, file_id)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "restricted"
    assert hasura.suggestions == {}


def test_token_rejected_by_hasura_is_401(reading, make_token, hasura):
    client = reading()
    token = make_token()
    file_id = upload(client, token)
    hasura.reject_tokens = True
    r = read(client, token, file_id)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


# --- lỗi của tệp, của kho, của CSDL -------------------------------------------------------------------------


def test_too_large_is_413_without_reading(reading, make_token, hasura, store):
    client = reading()
    token = make_token()
    file_id = upload(client, token)
    hasura.files[uuid.UUID(file_id)]["size_bytes"] = 2 * 1024 * 1024      # MOC_READ_MAX_MB = MOC_FILES_MAX_MB = 1
    r = read(client, token, file_id)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    assert store.reads == []


def test_zip_is_415_and_a_zip_named_pdf_never_gets_in(reading, make_token, hasura):
    client = reading()
    token = make_token()
    data = b"PK\x03\x04" + b"\x00" * 200
    # tải lên đã nhận loại theo nội dung (filetype.py): zip đặt đuôi .pdf không vào kho
    r = client.post("/api/files", headers=auth(token), files={"file": ("cong-van.pdf", data, "application/pdf")})
    assert r.status_code == 415 and r.json()["detail"]["code"] == "type_mismatch"
    # đọc vẫn nhận loại theo byte đầu (tệp lưu trước khi có bước trên): zip không đọc được
    file_id = upload(client, token, data, name="cong-van.zip")
    r = read(client, token, file_id)
    assert r.status_code == 415 and r.json()["detail"]["code"] == "unsupported"
    assert hasura.agent_events == []


def test_password_pdf_is_422_and_only_the_audit_row_is_written(reading, make_token, hasura):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(LETTER)))
    writer.encrypt(user_password="bi-mat", owner_password="chu", algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    client = reading()
    token = make_token()
    file_id = upload(client, token, out.getvalue())
    r = read(client, token, file_id)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "unreadable" and r.json()["detail"]["reason"] == "password"
    (event,) = hasura.agent_events
    assert event["diff"]["status"] == "unreadable" and event["diff"]["reason"] == "password"
    assert event["diff"]["found"] == "" and set(event["diff"]) == DIFF_KEYS
    assert hasura.suggestions == {}


def test_pdf_without_text_or_images_is_422_no_text(reading, make_token):
    client = reading()
    token = make_token()
    r = read(client, token, upload(client, token, text_pdf(pages=1)))
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "no_text"


def test_missing_object_is_404_and_broken_storage_503(reading, make_token, store):
    client = reading()
    token = make_token()
    first, second = upload(client, token), upload(client, token)
    key = next(k for k in store.objects if k.endswith(second))
    store.unreadable.add(key)
    store.objects.pop(next(k for k in store.objects if k.endswith(first)))
    assert read(client, token, first).json()["detail"]["code"] == "not_found"
    r = read(client, token, second)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "storage_unavailable"


def test_audit_failure_returns_no_suggestion(reading, make_token, hasura):
    client = reading()
    token = make_token()
    file_id = upload(client, token)
    hasura.fail_agent = True
    r = read(client, token, file_id, force=True)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"
    assert "fields" not in r.text and "99/TB-SMK" not in r.text


def test_audit_failure_of_an_unreadable_file_is_503(reading, make_token, hasura):
    client = reading()
    token = make_token()
    file_id = upload(client, token, text_pdf(pages=1))
    hasura.fail_agent = True
    assert read(client, token, file_id, force=True).json()["detail"]["code"] == "database_unavailable"


def test_database_down_is_503(reading, make_token, hasura):
    client = reading()
    token = make_token()
    file_id = upload(client, token)
    hasura.down = True
    assert read(client, token, file_id).json()["detail"]["code"] == "database_unavailable"


def test_reader_can_be_switched_off(reading, make_token):
    client = reading(env={"MOC_READ_ENABLED": "false"})
    token = make_token()
    r = read(client, token, upload(client, token))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "reader_disabled"


def test_busy_is_503_with_retry_after(reading, make_token):
    client = reading(env={"MOC_READ_QUEUE_S": "0.2"})
    token = make_token()
    file_id = upload(client, token)
    slots = client.app.state.reader.slots
    asyncio.run(slots.acquire())                 # lượt duy nhất đang bận
    try:
        r = read(client, token, file_id)
    finally:
        slots.release()
    assert r.status_code == 503 and r.json()["detail"]["code"] == "busy" and r.headers["retry-after"] == "10"
    assert read(client, token, file_id).status_code == 200


# --- OCR --------------------------------------------------------------------------------------------------


def test_image_goes_through_ocr(reading, make_token, hasura):
    client = reading()
    token = make_token()
    file_id = upload(client, token, png(), name="anh-chup.png", mime="image/png")
    body = read(client, token, file_id).json()
    assert body["method"] == "ocr" and body["pages"] == 1 and body["status"] == "ok"
    assert body["fields"]["symbol"]["value"] == "105/TB-ĐHM" and body["fields"]["type_code"]["value"] == "TB"
    # quy tắc chấm "high" nhưng chữ từ OCR: không trường nào được điền như chắc chắn
    assert body["fields"]["symbol"]["confidence"] == "medium"
    assert "high" not in {f["confidence"] for f in body["fields"].values()}
    assert hasura.agent_events[0]["diff"]["method"] == "ocr"


def test_scan_pdf_uses_ocr_on_its_embedded_image(reading, make_token):
    out = io.BytesIO()
    Image.new("L", (1240, 1754), 255).save(out, "PDF", resolution=150)
    client = reading()
    token = make_token()
    body = read(client, token, upload(client, token, out.getvalue())).json()
    assert (body["method"], body["pages"], body["fields"]["symbol"]["value"]) == ("ocr", 1, "105/TB-ĐHM")


def test_ocr_timeout_is_422_and_logged(reading, make_token, hasura, tmp_path):
    (tmp_path / "cham").mkdir()
    client = reading(env={"MOC_OCR_TIMEOUT_S": "1.5"}, tesseract=fake_tesseract(tmp_path / "cham", sleep_s=10))
    token = make_token()
    r = read(client, token, upload(client, token, png(), name="anh.png", mime="image/png"))
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "timeout"
    assert hasura.agent_events[0]["diff"] | {"duration_ms": 0} == {
        "user_id": "u-van-thu", "file_id": r.request.url.path.split("/")[3], "status": "unreadable", "method": "ocr",
        "pages": 1, "found": "", "summary_source": "none", "model": None, "duration_ms": 0, "reason": "timeout"}


def test_image_over_the_pixel_limit_is_422(reading, make_token):
    client = reading(env={"MOC_OCR_MAX_PIXELS": "10000"})
    token = make_token()
    r = read(client, token, upload(client, token, png((200, 200)), name="anh.png", mime="image/png"))
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "too_many_pixels"


def test_missing_tesseract_is_503(reading, make_token, tmp_path):
    client = reading(tesseract=tmp_path / "khong-co-tesseract")
    token = make_token()
    r = read(client, token, upload(client, token, png(), name="anh.png", mime="image/png"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ocr_unavailable"


@pytest.mark.parametrize(("sig", "reason"), [(signal.SIGKILL, "memory"), (signal.SIGABRT, "memory"),
                                             (signal.SIGSEGV, "corrupt")],
                         ids=["SIGKILL", "SIGABRT", "SIGSEGV"])
def test_tesseract_killed_by_a_signal_is_422_with_audit_row(reading, make_token, hasura, tmp_path, sig, reason):
    (tmp_path / "giet").mkdir()
    client = reading(tesseract=fake_tesseract(tmp_path / "giet", kill=sig))
    token = make_token()
    r = read(client, token, upload(client, token, png(), name="anh.png", mime="image/png"))
    assert r.status_code == 422                     # lỗi của tệp, không phải 503 "máy chủ chưa có tesseract"
    assert r.json()["detail"]["code"] == "unreadable" and r.json()["detail"]["reason"] == reason
    (event,) = hasura.agent_events
    assert event["diff"]["status"] == "unreadable" and event["diff"]["reason"] == reason
    assert event["diff"]["method"] == "ocr" and hasura.suggestions == {}


# PDF có lớp chữ nhưng trang 1 dưới 40 ký tự, không có ảnh nhúng nào (văn bản ngắn xuất từ phần mềm)
THIN = text_pdf("THONG BAO", "So: 99/TB-SMK")


def test_thin_text_layer_without_images_falls_back_to_the_text(reading, make_token, hasura):
    client = reading()
    token = make_token()
    body = read(client, token, upload(client, token, THIN)).json()      # OCR: không có ảnh (no_text)
    assert body["method"] == "text" and body["status"] == "ok"
    assert body["fields"]["symbol"]["value"] == "99/TB-SMK" and body["fields"]["type_code"]["value"] == "TB"
    assert hasura.agent_events[0]["diff"]["method"] == "text"


def test_thin_text_layer_is_used_when_tesseract_is_missing(reading, make_token, tmp_path):
    client = reading(tesseract=tmp_path / "khong-co-tesseract")
    token = make_token()
    body = read(client, token, upload(client, token, THIN)).json()
    assert (body["method"], body["fields"]["symbol"]["value"]) == ("text", "99/TB-SMK")
    # không có lớp chữ nào: vẫn cần OCR, máy chủ chưa có thì 503 như trước
    r = read(client, token, upload(client, token, text_pdf(pages=1)))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ocr_unavailable"


def test_thin_text_layer_is_used_when_tesseract_has_no_language_data(reading, make_token, tmp_path, monkeypatch):
    from svc_files.docread import reader as reader_module
    from svc_files.docread.ocr import OcrResult

    async def no_vie(*args, **kwargs):
        return OcrResult("failed", None, (), "engine_failed")

    monkeypatch.setattr(reader_module, "run_ocr", no_vie)
    client = reading()
    token = make_token()
    assert read(client, token, upload(client, token, THIN)).json()["method"] == "text"
    r = read(client, token, upload(client, token, png(), name="anh.png", mime="image/png"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ocr_unavailable"     # ảnh: không có gì để lùi


# --- mô hình trích yếu ------------------------------------------------------------------------------------


def test_model_writes_the_summary_when_the_rule_is_unsure(reading, make_token, hasura):
    fake = FakeOllama()
    client = reading(summarizer=ready_ollama(fake))
    token = make_token()
    body = read(client, token, upload(client, token)).json()
    assert body["fields"]["summary"] == {"value": GOOD_SUMMARY, "confidence": "medium", "source": "model"}
    assert body["summary_source"] == "model" and body["model"] == OLLAMA_MODEL and body["warnings"] == []
    (chat,) = fake.calls("/api/chat")
    assert "Lich hop giao ban" in chat["messages"][1]["content"]
    diff = hasura.agent_events[0]["diff"]
    assert diff["summary_source"] == "model" and diff["model"] == OLLAMA_MODEL
    assert GOOD_SUMMARY not in json.dumps(hasura.agent_events, ensure_ascii=False)


def test_model_is_not_asked_when_the_rule_summary_is_sure(reading, make_token):
    fake = FakeOllama()
    client = reading(summarizer=ready_ollama(fake))
    token = make_token()
    body = read(client, token, upload(client, token, CONG_VAN)).json()
    assert body["summary_source"] == "rule" and body["model"] is None and body["warnings"] == []
    assert fake.calls("/api/chat") == []


def test_always_mode_asks_the_model_anyway(reading, make_token):
    fake = FakeOllama()
    client = reading(env={"MOC_AI_SUMMARY": "always"}, summarizer=ready_ollama(fake))
    token = make_token()
    assert read(client, token, upload(client, token, CONG_VAN)).json()["summary_source"] == "model"
    assert len(fake.calls("/api/chat")) == 1


async def _slow(request):
    await asyncio.sleep(3)
    return json.dumps({"trich_yeu": GOOD_SUMMARY}, ensure_ascii=False)


@pytest.mark.parametrize(("reply", "warning"), [
    (_slow, "model_timeout"),
    ("khong phai json", "model_rejected"),
    (json.dumps({"trich_yeu": "Về việc xem tại http://la.example nhé"}), "model_rejected"),
], ids=["cham", "khong-phai-json", "co-lien-ket"])
def test_model_failures_keep_the_rule_summary(reading, make_token, reply, warning):
    client = reading(env={"MOC_AI_TIMEOUT_S": "0.3"}, summarizer=ready_ollama(FakeOllama(reply=reply)))
    token = make_token()
    body = read(client, token, upload(client, token)).json()
    assert body["warnings"] == [warning] and body["summary_source"] == "rule" and body["model"] == OLLAMA_MODEL
    assert body["fields"]["summary"] == {"value": "Lich hop giao ban thang 11 cua nha truong", "confidence": "low",
                                         "source": "rule"}


def test_model_missing_from_ollama_is_never_called(reading, make_token):
    fake = FakeOllama(models=["llama3:8b"])
    s = OllamaSummarizer("http://ollama:11434", OLLAMA_MODEL, transport=httpx2.MockTransport(fake))
    assert not asyncio.run(s.probe())
    client = reading(summarizer=s)
    token = make_token()
    assert read(client, token, upload(client, token)).json()["warnings"] == ["model_unavailable"]
    assert fake.calls("/api/chat") == []


def test_model_is_skipped_when_the_deadline_is_near(reading, make_token):
    fake = FakeOllama()
    client = reading(env={"MOC_READ_DEADLINE_S": "4"}, summarizer=ready_ollama(fake))
    token = make_token()
    assert read(client, token, upload(client, token)).json()["warnings"] == ["model_skipped"]
    assert fake.calls("/api/chat") == []


def test_readyz_reports_the_model_without_changing_readiness(reading):
    assert reading().get("/readyz").json()["ai"] is False
    r = reading(summarizer=ready_ollama(FakeOllama())).get("/readyz")
    assert r.status_code == 200 and r.json()["ai"] is True and r.json()["status"] == "ready"


def test_route_is_in_the_openapi_document(reading):
    spec = reading().get("/openapi.json").json()
    op = spec["paths"]["/api/files/{file_id}/read"]["post"]
    assert {"401", "403", "404", "409", "413", "415", "422", "503"} <= set(op["responses"])


def test_settings_defaults_and_checks():
    from svc_files.config import ConfigError

    s = Settings.from_env({k: v for k, v in ENV.items() if k != "MOC_AI_URL"})
    assert s.read_enabled and s.read_max_bytes == 1024 * 1024 and s.ai_url == "http://ollama:11434"
    assert (s.ocr_lang, s.ocr_max_pages, s.read_text_pages, s.agent_id) == ("vie", 1, 3, "moc-doc-reader")
    assert (s.read_deadline_s, s.read_queue_s, s.ocr_timeout_s, s.ai_summary) == (50.0, 15.0, 40.0, "fallback")
    assert Settings.from_env({**ENV, "MOC_READ_MAX_MB": "5"}).read_max_bytes == 5 * 1024 * 1024
    for bad in ({"MOC_AI_SUMMARY": "doi-khi"}, {"MOC_OCR_LANG": "vie --psm"}, {"MOC_READ_ENABLED": "co"},
                {"MOC_READ_CONCURRENCY": "0"}, {"MOC_AI_URL": "ollama:11434"}, {"MOC_AGENT_ID": ""}):
        with pytest.raises(ConfigError):
            Settings.from_env({**ENV, **bad})


def test_reads_the_object_of_the_file_in_the_token_tenant(reading, make_token, store):
    # đọc đúng đối tượng của tệp, theo thuê ước trong token (vai trò service, file_location)
    client = reading()
    token = make_token()
    file_id = upload(client, token)
    read(client, token, file_id)
    (key,) = store.reads
    assert key.startswith(f"tenant/{TENANT_A}/") and key.endswith(file_id)
    assert hashlib.sha256(store.objects[key]["data"]).hexdigest() == hashlib.sha256(LETTER).hexdigest()


# --- GraphQL thật của store.py qua HasuraClient -------------------------------------------------------------


def test_store_talks_to_hasura_as_the_agent_role():
    from svc_files.docread.store import SuggestionStore
    from svc_files.hasura import HasuraClient

    file_id = str(uuid.uuid4())
    sent: list[httpx2.Request] = []

    def hasura_http(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        query = json.loads(request.content)["query"]
        if "LuuGoiY" in query:
            return httpx2.Response(200, json={"data": {
                "insert_office_intake_suggestions_one": {"file_id": file_id, "read_at": "2026-10-21T08:00:00+00:00"},
                "insert_core_audit_log": {"affected_rows": 1}}})
        if "GoiYDaCo" in query:
            return httpx2.Response(200, json={"data": {"office_intake_suggestions_by_pk": None}})
        if "LoaiVanBan" in query:
            return httpx2.Response(200, json={"data": {"office_document_types": [{"code": "CV"}, {"code": "TB"}]}})
        if "VisibleFile" in query:
            return httpx2.Response(200, json={"data": {"core_files_by_pk": {
                "id": file_id, "filename": "a.pdf", "mime_type": "application/pdf", "size_bytes": 10,
                "sha256": "\\x" + "ab" * 32, "encrypted": False, "created_by": "u-van-thu"}}})
        return httpx2.Response(200, json={"errors": [{"message": "câu lạ"}]})

    now = [0.0]
    client = HasuraClient("http://hasura:8080", "bi-mat", transport=httpx2.MockTransport(hasura_http))
    store = SuggestionStore(client, "moc-doc-reader", clock=lambda: now[0])
    row = {"file_id": file_id, "requested_by": "u-van-thu", "status": "ok", "method": "text", "pages": 1,
           "fields": {}, "warnings": [], "summary_source": "none", "model": None, "duration_ms": 5}
    diff = {"user_id": "u-van-thu", "file_id": file_id, "status": "ok"}

    async def go():
        assert await store.cached(TENANT_A, uuid.UUID(file_id), "req-1") is None
        read_at = await store.save(TENANT_A, "req-1", row, diff)
        codes = await store.type_codes()
        now[0] = 599.0
        await store.type_codes()                   # còn trong 10 phút: không hỏi lại
        now[0] = 601.0
        await store.type_codes()
        meta = await client.visible_file("tok", uuid.UUID(file_id))
        await client.aclose()
        return read_at, codes, meta

    read_at, codes, meta = asyncio.run(go())
    assert read_at == "2026-10-21T08:00:00+00:00" and codes == frozenset({"CV", "TB"})
    assert meta.created_by == "u-van-thu"

    cached, save = sent[0], sent[1]
    for request in (cached, save):
        h = {k.lower(): v for k, v in request.headers.items()}
        assert h["x-hasura-admin-secret"] == "bi-mat" and h["x-hasura-role"] == "agent"
        assert h["x-hasura-tenant-id"] == str(TENANT_A) and h["x-hasura-user-id"] == "moc-doc-reader"
        assert h["x-hasura-request-id"] == "req-1"
    body = json.loads(save.content)
    assert "on_conflict: {constraint: intake_suggestions_pkey" in body["query"]
    assert "insert_core_audit_log" in body["query"]          # cùng một mutation = cùng giao dịch
    assert body["variables"]["o"] == row
    # dòng sổ chỉ gồm cột vai trò agent được ghi: người làm, loại người làm, thuê ước do preset đặt
    assert body["variables"]["e"] == {"request_id": "req-1", "action": "intake.suggested", "entity": "core.files",
                                      "entity_id": file_id, "diff": diff}
    types = [r for r in sent if "LoaiVanBan" in json.loads(r.content)["query"]]
    assert len(types) == 2 and "x-hasura-role" not in {k.lower() for k in types[0].headers}
