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


"""Sổ đăng ký văn bản đến / đi (F2.8): cột theo mẫu NĐ 30 Phụ lục IV, che dòng hạn chế, liền số, in PDF."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from conftest import TENANT_A
from svc_files.hasura import HasuraAuthError, HasuraError
from svc_files.registers import COLUMNS, HIDDEN, WIDTHS, Register, build_register, register_html, render_register_pdf

OTHER_TENANT = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")
PRINTED = datetime(2026, 10, 20, 2, 30, tzinfo=UTC)
TENANT = {"code": "CNTT", "name": "Khoa Công nghệ thông tin", "parent_name": "Trường Đại học Thử",
          "head_title": "Trưởng khoa"}


def incoming(number: int, **over) -> dict:
    doc = {"id": f"d-{number}", "status": "in_progress", "symbol": f"{number}/UBND-VP", "issuer_name": "UBND tỉnh",
           "issued_on": "2026-10-01", "summary": "Về việc báo cáo quý III", "urgency": "normal", "restricted": False,
           "register_number": number, "registered_at": "2026-10-05T18:30:00+00:00", "due_on": None,
           "recipients": None, "verify_code": None, "document_type": {"name": "Công văn"}, "department": None,
           "signer": None, "assignments": [{"user_id": "u-1", "department": {"name": "Phòng Đào tạo"}}],
           "events": []}
    return {**doc, **over}


def outgoing(number: int, **over) -> dict:
    doc = {"id": f"o-{number}", "status": "issued", "symbol": f"{number:02d}/TB-CNTT", "issuer_name": None,
           "issued_on": "2026-10-19", "summary": "Về việc họp giao ban", "urgency": "normal", "restricted": False,
           "register_number": number, "registered_at": None, "due_on": None, "recipients": ["Các bộ môn", "Lưu"],
           "verify_code": "ABCDE23456", "document_type": {"name": "Thông báo"}, "department": {"name": "Phòng Đào tạo"},
           "signer": {"full_name": "Phạm Minh Đức"}, "assignments": [],
           "events": [{"created_at": "2026-10-19T17:10:00+00:00"}]}
    return {**doc, **over}


def book(docs: list[dict], *, direction: str = "in", visible: set[str] | None = None, last: int | None = None,
         users: list[dict] | None = None) -> Register:
    data = {"core_tenants_by_pk": TENANT,
            "office_registers": [{"last_number": last if last is not None else len(docs)}] if docs or last else [],
            "office_documents": docs, "core_users": users or []}
    seen = {d["id"] for d in docs} if visible is None else visible
    return build_register(data, seen, direction=direction, year=2026, printed_at=PRINTED)


# --- cột, ô theo mẫu sổ -----------------------------------------------------------------------------------


def test_columns_follow_the_decree_templates():
    assert len(COLUMNS["in"]) == 9 and len(COLUMNS["out"]) == 10
    assert COLUMNS["in"][:2] == ("Ngày đến", "Số đến") and COLUMNS["out"][0] == "Số, ký hiệu văn bản"
    assert all("Ký nhận" in cols and cols[-1] == "Ghi chú" for cols in COLUMNS.values())
    # vừa vùng in A4 ngang (297 mm trừ lề 18 + 12)
    assert all(len(WIDTHS[d]) == len(COLUMNS[d]) and sum(WIDTHS[d]) == 267 for d in COLUMNS)


def test_incoming_row_cells():
    reg = book([incoming(1, urgency="khan", due_on="2026-10-30")])
    assert reg.entries[0].cells == (
        "06/10/2026",                      # 18:30 UTC ngày 05 là 01:30 ngày 06 giờ Việt Nam
        "1", "UBND tỉnh", "1/UBND-VP", "01/10/2026", "Công văn: Về việc báo cáo quý III", "Phòng Đào tạo",
        "", "Khẩn; Hạn giải quyết 30/10/2026",
    )
    assert reg.entries[0].document_id == "d-1" and not reg.entries[0].hidden


@pytest.mark.parametrize(("over", "receiver"), [
    ({"assignments": [{"user_id": "u-1", "department": None}]}, "Lê Thị Hoa"),      # giao thẳng cho người
    ({"assignments": [], "status": "registered"}, "Trưởng khoa"),                     # chờ lãnh đạo chỉ đạo
    ({"assignments": [], "status": "done"}, "Lưu (không giao xử lý)"),
    ({"assignments": [], "status": "archived"}, "Lưu (không giao xử lý)"),
    ({"assignments": [], "status": "cancelled"}, ""),
])
def test_incoming_receiver(over, receiver):
    reg = book([incoming(1, **over)], users=[{"id": "u-1", "full_name": "Lê Thị Hoa"}])
    assert reg.entries[0].cells[6] == receiver


def test_cancelled_documents_keep_their_number():
    reg = book([incoming(1), incoming(2, status="cancelled", assignments=[])])
    assert [e.number for e in reg.entries] == [1, 2] and reg.entries[1].cells[8] == "Đã hủy" and reg.missing == []


def test_outgoing_row_cells():
    reg = book([outgoing(5, urgency="hoa_toc")], direction="out")
    assert reg.entries[0].cells == (
        "05/TB-CNTT", "19/10/2026", "Thông báo: Về việc họp giao ban", "Phạm Minh Đức", "Các bộ môn; Lưu",
        "Văn thư; Phòng Đào tạo", "", "20/10/2026", "", "Hỏa tốc; Mã xác thực ABCDE-23456",
    )


def test_numbered_but_unissued_outgoing_is_not_shown_as_sent():
    # cấp số rồi mà dựng bản phát hành lỗi: còn "approved", mã chưa tra được ở cổng xác thực
    reg = book([outgoing(1, status="approved", events=[]), outgoing(2, status="cancelled", events=[])], direction="out")
    approved, cancelled = (e.cells for e in reg.entries)
    assert approved[7] == "" and approved[9] == "Đã cấp số, chưa phát hành"
    assert cancelled[7] == "" and cancelled[9] == "Đã hủy" and reg.missing == []


def test_outgoing_without_issue_event_uses_the_document_date():
    reg = book([outgoing(1, events=[], department=None)], direction="out")
    assert reg.entries[0].cells[5] == "Văn thư" and reg.entries[0].cells[7] == "19/10/2026"


# --- dòng hạn chế: liền số nhưng che nội dung ---------------------------------------------------------------


def test_restricted_incoming_rows_keep_number_dates_and_symbol_only():
    reg = book([incoming(1), incoming(2, restricted=True, due_on="2026-10-30", urgency="hoa_toc")], visible={"d-1"})
    secret = reg.entries[1]
    assert secret.hidden and secret.document_id is None and secret.number == 2
    assert secret.cells == ("06/10/2026", "2", "", "2/UBND-VP", "01/10/2026", HIDDEN, "", "", "Hạn chế")
    assert "Về việc" not in "".join(secret.cells) and "UBND tỉnh" not in secret.cells


def test_restricted_outgoing_rows_hide_summary_signer_recipients_and_code():
    reg = book([outgoing(1, restricted=True, urgency="thuong_khan")], direction="out", visible=set())
    assert reg.entries[0].cells == ("01/TB-CNTT", "19/10/2026", HIDDEN, "", "", "Văn thư", "", "20/10/2026", "",
                                    "Hạn chế")


# --- liền số, bìa, HTML ---------------------------------------------------------------------------------------


def test_missing_numbers_are_reported():
    reg = book([incoming(1), incoming(2), incoming(4)], last=4)
    assert reg.missing == [3]
    assert "Sổ thiếu dòng của số: 3." in register_html(reg)


def test_rows_read_after_the_last_number_extend_the_register():
    reg = book([incoming(1), incoming(2), incoming(3)], last=2)
    assert reg.last == 3 and reg.missing == [] and "Từ số 01 đến số 03" in register_html(reg)


def test_cover_states_range_continuity_and_hidden_rows():
    reg = book([incoming(1, registered_at="2026-01-05T02:00:00+00:00"), incoming(2, restricted=True)],
               visible={"d-1"})
    assert reg.date_range == ("05/01/2026", "06/10/2026")
    page = register_html(reg)
    for text in ("Trường Đại học Thử", "Khoa Công nghệ thông tin", "Sổ đăng ký văn bản đến", "Năm: 2026",
                 "Từ ngày 05/01/2026 đến ngày 06/10/2026", "Từ số 01 đến số 02", "Sổ liền số, đủ 2 văn bản.",
                 "1 dòng là văn bản hạn chế", "09:30 ngày 20/10/2026", "Điều 16, Điều 22, Phụ lục IV",
                 "Văn thư cơ quan"):
        assert text in page, text
    assert page.count("<col ") == 9 and "<th>(9)</th>" in page and "<th>(10)</th>" not in page


def test_html_escapes_document_text():
    reg = book([incoming(1, summary='<script>alert("x")</script> & co', issuer_name="A <b>B</b>")])
    page = register_html(reg)
    assert "<script>" not in page and "&lt;script&gt;" in page and "A &lt;b&gt;B&lt;/b&gt;" in page


def test_empty_register_prints_a_placeholder_row():
    reg = book([], direction="out")
    page = register_html(reg)
    assert reg.last_number == 0 and reg.date_range is None and reg.missing == []
    assert "Chưa có văn bản nào trong sổ năm 2026." in page and 'colspan="10"' in page and "Từ số" not in page


def test_render_register_pdf_with_weasyprint():
    try:
        import weasyprint  # noqa: F401
    except OSError:
        pytest.skip("máy này thiếu thư viện Pango của WeasyPrint (image svc-files có sẵn)")
    pdf = render_register_pdf(book([incoming(n) for n in range(1, 40)]))
    assert pdf.startswith(b"%PDF-") and len(pdf) > 5000


# --- API ----------------------------------------------------------------------------------------------------


@pytest.fixture
def printed(monkeypatch):
    """Thay WeasyPrint: trả PDF giả, ghi lại sổ được dựng."""
    seen: list[Register] = []

    def fake(reg: Register) -> bytes:
        seen.append(reg)
        return b"%PDF-1.7 fake register"

    monkeypatch.setattr("svc_files.app.render_register_pdf", fake)
    return seen


def get(client, token, path):
    return client.get(path, headers={"Authorization": f"Bearer {token}"} if token else {})


def test_clerk_reads_the_register_as_json(client, hasura, make_token):
    first = hasura.add_registered(TENANT_A, "in", 1, assignments=[{"user_id": "u-1", "department": {"name": "P1"}}])
    hasura.add_registered(TENANT_A, "in", 2, readers={"u-giam-doc"}, summary="Nhân sự mật")
    hasura.add_registered(TENANT_A, "out", 1)
    hasura.add_registered(TENANT_A, "in", 1, year=2025)
    hasura.add_registered(OTHER_TENANT, "in", 3)
    r = get(client, make_token(), "/api/registers/in/2026")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["direction"] == "in" and body["year"] == 2026 and body["title"] == "Sổ đăng ký văn bản đến"
    assert body["org_name"] == "Khoa Công nghệ thông tin" and body["columns"] == list(COLUMNS["in"])
    assert body["last_number"] == 2 and body["missing"] == []
    assert [(e["number"], e["document_id"], e["hidden"]) for e in body["entries"]] == [
        (1, first, False), (2, None, True)]
    assert body["entries"][1]["cells"][5] == HIDDEN and "Nhân sự mật" not in r.text


def test_director_reads_the_outgoing_register(client, hasura, make_token):
    hasura.add_registered(TENANT_A, "out", 1, symbol="01/TB-CNTT")
    r = get(client, make_token(role="director", sub="u-giam-doc"), "/api/registers/out/2026")
    assert r.status_code == 200 and r.json()["entries"][0]["cells"][0] == "01/TB-CNTT"
    assert len(r.json()["columns"]) == 10


def test_a_year_without_documents_is_an_empty_register(client, make_token):
    r = get(client, make_token(), "/api/registers/in/2031")
    assert r.status_code == 200 and r.json()["entries"] == [] and r.json()["last_number"] == 0


@pytest.mark.parametrize("role", ["staff", "manager", "tenant_admin"])
def test_only_clerks_and_directors_see_registers(client, hasura, make_token, printed, role):
    hasura.add_registered(TENANT_A, "in", 1)
    for path in ("/api/registers/in/2026", "/api/registers/in/2026/pdf"):
        r = get(client, make_token(role=role), path)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "forbidden"
    assert not printed and not hasura.events


@pytest.mark.parametrize("path", ["/api/registers/sent/2026", "/api/registers/in/1999", "/api/registers/out/2101",
                                  "/api/registers/in/nam-nay"])
def test_bad_direction_or_year_is_rejected(client, make_token, path):
    assert get(client, make_token(), path).status_code == 422


def test_register_needs_a_valid_token(client, hasura, make_token):
    hasura.add_registered(TENANT_A, "in", 1)
    assert get(client, None, "/api/registers/in/2026").status_code == 401
    hasura.reject_tokens = True
    r = get(client, make_token(), "/api/registers/in/2026")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_register_reports_database_outage(client, hasura, make_token):
    hasura.down = True
    r = get(client, make_token(), "/api/registers/in/2026/pdf")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"


def test_a_gap_is_read_again_before_it_is_reported(client, hasura, make_token, monkeypatch):
    hasura.add_registered(TENANT_A, "in", 1)
    real, calls = hasura.register, []

    async def racing(**kw):
        data = await real(**kw)
        calls.append(kw)
        if len(calls) == 1:     # văn thư khác vừa cấp số 2, dòng của nó chưa đọc kịp
            data["office_registers"] = [{"last_number": 2}]
        return data

    monkeypatch.setattr(hasura, "register", racing)
    body = get(client, make_token(), "/api/registers/in/2026").json()
    assert len(calls) == 2 and body["missing"] == [] and body["last_number"] == 1


def test_a_real_gap_is_reported(client, hasura, make_token):
    for n in (1, 2, 4):
        hasura.add_registered(TENANT_A, "in", n)
    body = get(client, make_token(), "/api/registers/in/2026").json()
    assert body["missing"] == [3] and body["last_number"] == 4


def test_service_side_auth_errors_are_not_blamed_on_the_user_token(client, hasura, make_token, monkeypatch):
    async def denied(**kw):
        raise HasuraAuthError("access-denied", "access-denied")

    monkeypatch.setattr(hasura, "register", denied)
    r = get(client, make_token(), "/api/registers/in/2026")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"


def test_pdf_download_is_audited(client, hasura, make_token, printed):
    hasura.add_registered(TENANT_A, "in", 1)
    hasura.add_registered(TENANT_A, "in", 2, readers={"u-giam-doc"})
    r = get(client, make_token(), "/api/registers/in/2026/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF-") and r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "no-store"
    assert 'filename="so-dang-ky-van-ban-den-2026.pdf"' in r.headers["content-disposition"]
    assert [e.number for e in printed[0].entries] == [1, 2]
    [event] = hasura.events
    assert event["action"] == "register.printed" and event["entity"] == "office.registers"
    assert event["entity_id"] == "in/2026" and event["actor_id"] == "u-van-thu" and event["tenant_id"] == TENANT_A
    assert event["details"] == {"direction": "in", "year": 2026, "entries": 2, "masked": 1}


def test_outgoing_pdf_name(client, make_token, printed):
    r = get(client, make_token(role="director"), "/api/registers/out/2026/pdf")
    assert r.status_code == 200 and 'filename="so-dang-ky-van-ban-di-2026.pdf"' in r.headers["content-disposition"]


def test_no_pdf_without_an_audit_record(client, hasura, make_token, printed, monkeypatch):
    async def broken(**event):
        raise HasuraError("Hasura tắt")

    monkeypatch.setattr(hasura, "log_event", broken)
    r = get(client, make_token(), "/api/registers/in/2026/pdf")
    assert r.status_code == 503 and not r.content.startswith(b"%PDF")


def test_registers_are_in_the_public_api(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/registers/{direction}/{year}", "/api/registers/{direction}/{year}/pdf"} <= set(paths)
