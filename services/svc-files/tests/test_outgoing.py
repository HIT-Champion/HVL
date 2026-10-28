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


"""Văn bản đi: dựng PDF theo thể thức, phát hành (API nội bộ), xem trước dự thảo, cổng xác thực."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime

import pytest

from conftest import TENANT_A
from svc_files.render import VN, TEXT, Letter, display_code, en_date, letter_from, letter_html, render_pdf, vn_date

OTHER_TENANT = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")


def base_letter(**over) -> Letter:
    fields = dict(org_name="Khoa Công nghệ thông tin", org_code="CNTT", type_code="TB", type_name="Thông báo",
                  in_symbol=True, summary="Về việc họp giao ban", body="Đoạn một.\nĐoạn hai.", recipients=["Các bộ môn"],
                  dept_code="ĐT")
    fields.update(over)
    return Letter(**fields)


@pytest.fixture
def rendered(monkeypatch):
    """Thay WeasyPrint: trả PDF giả mang ký hiệu, ghi lại văn bản được dựng."""
    seen: list[Letter] = []

    def fake(letter: Letter) -> bytes:
        seen.append(letter)
        return b"%PDF-1.7 fake " + (letter.symbol or "du-thao").encode()

    monkeypatch.setattr("svc_files.office.api.render_pdf", fake)
    return seen


# --- khuôn văn bản -------------------------------------------------------------------------------------


@pytest.mark.parametrize(("day", "text"), [
    (date(2026, 2, 5), "Hà Nội, ngày 05 tháng 02 năm 2026"),
    (date(2026, 10, 19), "Hà Nội, ngày 19 tháng 10 năm 2026"),
    (date(2026, 3, 1), "Hà Nội, ngày 01 tháng 3 năm 2026"),
])
def test_dates_follow_decree_30(day, text):
    assert vn_date(day, "Hà Nội") == text


def test_user_text_is_escaped():
    page = letter_html(base_letter(body='<script>alert(1)</script>\n<img src=x onerror=alert(2)>',
                                   summary='"><b>trích yếu</b>', recipients=["<i>nơi nhận</i>"]))
    assert "<script>" not in page and "<img src=x" not in page and "<b>trích yếu" not in page
    assert "&lt;script&gt;" in page and "&lt;i&gt;nơi nhận" in page


@pytest.mark.parametrize(("over", "number"), [
    ({}, "/TB-CNTT"),
    ({"type_code": "CV", "type_name": "Công văn", "in_symbol": False}, "/CNTT-ĐT"),
])
def test_draft_leaves_number_blank_and_is_watermarked(over, number):
    page = letter_html(base_letter(**over))
    assert number in page and "DỰ THẢO" in page and "data:image/svg+xml" not in page


def test_letter_type_letter_has_vv_line_and_salutation():
    page = letter_html(base_letter(type_code="CV", type_name="Công văn", in_symbol=False,
                                   summary="V/v cử cán bộ dự tập huấn", recipients=["Phòng Đào tạo"]))
    assert "V/v cử cán bộ dự tập huấn" in page and "V/v V/v" not in page
    assert "Kính gửi: Phòng Đào tạo." in page and "Như trên" in page


def test_issued_letter_carries_qr_and_readable_code():
    page = letter_html(base_letter(symbol="05/TB-CNTT", issued_on=date(2026, 10, 19), verify_code="ABCDE23456",
                                   verify_url="https://moc.example/xac-thuc/ABCDE23456"))
    assert "Số: 05/TB-CNTT" in page and "data:image/svg+xml" in page and "DỰ THẢO" not in page
    assert display_code("ABCDE23456") == "ABCDE-23456" and "ABCDE-23456" in page
    assert "https://moc.example/xac-thuc" in page


def test_preview_of_a_numbered_document_hides_number_and_code(hasura):
    row = hasura._public(hasura.letters[hasura.add_letter(TENANT_A)])
    draft = letter_from(row, draft=True)
    assert draft.draft and draft.verify_code is None and draft.issued_on is None
    issued = letter_from(row, verify_base="https://moc.example/xac-thuc")
    assert issued.verify_url == "https://moc.example/xac-thuc/ABCDE23456" and issued.signer_name == "Phạm Minh Đức"


# --- văn bản tiếng Anh (F2.9, #398) ---------------------------------------------------------------------


def test_both_letter_languages_have_the_same_texts():
    assert TEXT["vi"].keys() == TEXT["en"].keys()
    assert all(TEXT[lang]["verify"].count("{}") == 1 for lang in TEXT)


@pytest.mark.parametrize(("day", "text"), [
    (date(2026, 2, 5), "Hà Nội, February 5, 2026"),
    (date(2026, 10, 19), "Hà Nội, October 19, 2026"),
])
def test_english_dates_keep_the_place_as_entered(day, text):
    assert en_date(day, "Hà Nội") == text
    assert en_date(None, None).endswith(f", {datetime.now(VN).year}")


def test_english_letter_translates_the_fixed_parts_only():
    page = letter_html(base_letter(lang="en", type_name="Notice", summary="Về việc họp giao ban",
                                   symbol="05/TB-CNTT", issued_on=date(2026, 10, 19), verify_code="ABCDE23456",
                                   verify_url="https://moc.example/xac-thuc/ABCDE23456", signer_name="Phạm Minh Đức",
                                   approved_at=datetime(2026, 10, 19, 3, 0, tzinfo=UTC)))
    for text in ('<html lang="en">', "Socialist Republic of Vietnam", "Independence - Freedom - Happiness",
                 "No.: 05/TB-CNTT", "October 19, 2026", '<div class="name">Notice</div>', "Recipients:",
                 "<li>- Các bộ môn;</li>", "<li>- Archived: Records office, ĐT.</li>", "Head of unit",
                 "Approved in the Signet system<br>10:00 on October 19, 2026", 'alt="Verification QR code"',
                 "open\nhttps://moc.example/xac-thuc and enter the code", "ABCDE-23456", "SHA-256",
                 # chữ người dùng nhập giữ nguyên
                 "Khoa Công nghệ thông tin", "Về việc họp giao ban", "<p>Đoạn một.</p>", "Phạm Minh Đức"):
        assert text in page, text
    for vietnamese in ("Cộng hòa", "Độc lập", "Số:", "ngày ", "Nơi nhận", "Lưu:", "Thủ trưởng", "Đã duyệt",
                       "Kiểm tra văn bản", "Mã QR"):
        assert vietnamese not in page, vietnamese


def test_english_official_letter_has_re_line_and_to():
    page = letter_html(base_letter(lang="en", type_code="CV", type_name="Official letter", in_symbol=False,
                                   summary="Re: sending staff to the training", recipients=["Phòng Đào tạo"]))
    assert "Re: sending staff to the training" in page and "Re: Re:" not in page
    # tiếng Việt chỉ bỏ "V/v", "Về việc" gõ sẵn: trích yếu bắt đầu bằng "Re:" giữ nguyên như trước
    vi = letter_html(base_letter(type_code="CV", type_name="Công văn", in_symbol=False, summary="Re: góp ý dự thảo"))
    assert "V/v Re: góp ý dự thảo" in vi
    assert "To: Phòng Đào tạo." in page and "<li>- As above;</li>" in page and "Kính gửi" not in page
    many = letter_html(base_letter(lang="en", in_symbol=False, recipients=["A", "B"]))
    assert "To:<ul><li>- A;</li><li>- B.</li></ul>" in many


def test_english_draft_is_watermarked_without_number():
    page = letter_html(base_letter(lang="en"))
    assert "/TB-CNTT" in page and "DRAFT" in page and "DỰ THẢO" not in page
    assert "Draft — not yet approved" in page and "Preview of a draft: no number" in page
    assert "data:image/svg+xml" not in page and "(draft)" in page


@pytest.mark.parametrize(("language", "lang", "name"), [("en", "en", "Notice"), ("vi", "vi", "Thông báo"),
                                                         (None, "vi", "Thông báo"), ("fr", "vi", "Thông báo")])
def test_letter_from_reads_the_document_language(hasura, language, lang, name):
    row = hasura._public(hasura.letters[hasura.add_letter(TENANT_A, language=language)])
    letter = letter_from(row, verify_base="https://moc.example/xac-thuc")
    assert (letter.lang, letter.type_name) == (lang, name)
    custom = letter_from({**row, "type_code": "XYZ", "document_type": {"name": "Loại riêng", "in_symbol": True}})
    assert custom.type_name == "Loại riêng"


def test_render_pdf_with_weasyprint():
    try:
        import weasyprint  # noqa: F401
    except OSError:
        pytest.skip("máy này thiếu thư viện Pango của WeasyPrint (image svc-files có sẵn)")
    pdf = render_pdf(base_letter(symbol="05/TB-CNTT", issued_on=date(2026, 10, 19), verify_code="ABCDE23456",
                                 verify_url="https://moc.example/xac-thuc/ABCDE23456"))
    assert pdf.startswith(b"%PDF-") and len(pdf) > 5000


# --- phát hành: API nội bộ của svc-workflow ------------------------------------------------------------


def issue(client, token, doc_id, tenant=TENANT_A):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/internal/issue", headers=headers,
                       json={"tenant_id": str(tenant), "document_id": doc_id, "actor_id": "u-van-thu"})


def test_issue_requires_the_workflow_service_token(client, hasura, make_token, rendered):
    doc = hasura.add_letter(TENANT_A)
    assert issue(client, None, doc).status_code == 401
    r = issue(client, make_token(azp="app-office"), doc)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_a_service"
    assert not rendered and not hasura.files


def test_issue_renders_scans_and_stores_the_numbered_letter(client, hasura, store, scanner, make_token, rendered):
    doc = hasura.add_letter(TENANT_A)
    r = issue(client, make_token(azp="svc-workflow", tenant=None), doc)
    assert r.status_code == 201
    out = r.json()
    (stored,) = store.objects.values()
    assert out["sha256"] == hashlib.sha256(stored["data"]).hexdigest() == stored["sha256"]
    assert stored["content_type"] == "application/pdf" and scanner.scanned == stored["data"]
    row = hasura.files[uuid.UUID(out["file_id"])]
    assert row["filename"] == "05-TB-CNTT.pdf" and row["tenant_id"] == TENANT_A and row["created_by"] == "u-van-thu"
    assert rendered[0].verify_url == "https://moc.example/xac-thuc/ABCDE23456" and not rendered[0].draft


@pytest.mark.parametrize(("cols", "tenant", "status"), [
    ({"status": "in_review", "symbol": None, "verify_code": None}, TENANT_A, 409),
    ({}, OTHER_TENANT, 404),
])
def test_issue_refuses_unnumbered_or_foreign_documents(client, hasura, make_token, rendered, cols, tenant, status):
    doc = hasura.add_letter(TENANT_A, **cols)
    assert issue(client, make_token(azp="svc-workflow", tenant=None), doc, tenant).status_code == status
    assert not rendered and not hasura.files


def test_issue_stores_nothing_when_scanner_is_down(client, hasura, store, scanner, make_token, rendered):
    scanner.down = True
    r = issue(client, make_token(azp="svc-workflow", tenant=None), hasura.add_letter(TENANT_A))
    assert r.status_code == 503 and not store.objects and not hasura.files


def test_issue_is_not_part_of_the_public_api(client):
    assert "/internal/issue" not in client.get("/openapi.json").json()["paths"]


# --- xem trước dự thảo ------------------------------------------------------------------------------------


def test_preview_renders_a_watermarked_draft_for_readers(client, hasura, make_token, rendered):
    doc = hasura.add_letter(TENANT_A, status="in_review", symbol=None, verify_code=None)
    r = client.get(f"/api/documents/{doc}/preview", headers={"Authorization": f"Bearer {make_token()}"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "no-store" and "sandbox" in r.headers["content-security-policy"]
    assert rendered[0].draft


def test_preview_hides_documents_the_caller_cannot_read(client, hasura, make_token, rendered):
    secret = hasura.add_letter(TENANT_A, status="draft", readers={"u-khac"})
    foreign = hasura.add_letter(OTHER_TENANT, status="draft")
    for doc in (secret, foreign, str(uuid.uuid4())):
        r = client.get(f"/api/documents/{doc}/preview", headers={"Authorization": f"Bearer {make_token()}"})
        assert r.status_code == 404
    assert client.get(f"/api/documents/{secret}/preview").status_code == 401
    assert not rendered


def test_issued_documents_are_downloaded_not_previewed(client, hasura, make_token, rendered):
    doc = hasura.add_letter(TENANT_A, status="issued", content_sha256="ab" * 32)
    r = client.get(f"/api/documents/{doc}/preview", headers={"Authorization": f"Bearer {make_token()}"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "issued"


# --- cổng xác thực ------------------------------------------------------------------------------------------


@pytest.fixture
def issued(hasura):
    return hasura.add_letter(TENANT_A, status="issued", content_sha256="cd" * 32, is_public=False)


@pytest.mark.parametrize("code", ["ABCDE23456", "abcde-23456", "ABCDE 23456"])
def test_verify_by_code_needs_no_login(client, issued, code):
    r = client.get(f"/api/verify/{code}")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["result"] == "valid"
    assert body["document"] == {
        "symbol": "05/TB-CNTT", "issued_on": "2026-10-19", "type_name": "Thông báo",
        "issuer_name": "Khoa Công nghệ thông tin", "parent_name": "Trường Đại học Thử", "summary": None,
        "sha256": "cd" * 32, "verify_code": "ABCDE23456", "status": "issued", "signature": None,
    }


def test_public_documents_show_their_summary(client, hasura, issued):
    hasura.letters[issued]["is_public"] = True
    assert client.get("/api/verify/ABCDE23456").json()["document"]["summary"] == "Về việc họp giao ban tháng 11"


@pytest.mark.parametrize("code", ["ZZZZZ22222", "ABC", "x" * 40])
def test_unknown_or_malformed_codes_are_not_found(client, issued, code):
    assert client.get(f"/api/verify/{code}").json() == {"result": "not_found", "document": None}


def test_unissued_documents_cannot_be_verified(client, hasura):
    hasura.add_letter(TENANT_A, status="approved", content_sha256="ef" * 32)
    assert client.get("/api/verify/ABCDE23456").json()["result"] == "not_found"


def test_verify_by_hash(client, issued):
    assert client.get("/api/verify", params={"sha256": "CD" * 32}).json()["result"] == "valid"
    assert client.get("/api/verify", params={"sha256": "00" * 32}).json()["result"] == "not_found"
    assert client.get("/api/verify", params={"sha256": "xyz"}).status_code == 422


def test_verify_reports_database_down(client, hasura, issued):
    hasura.down = True
    assert client.get("/api/verify/ABCDE23456").status_code == 503
