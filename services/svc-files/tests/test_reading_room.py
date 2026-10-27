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

"""Nộp lưu theo yêu cầu và phòng đọc xem tệp (F3.8): lãnh đạo phòng nộp lưu hồ sơ đã đóng; người đọc được văn bản
xem tệp trong gói lạnh — so băm với manifest, đóng dấu người xem, ghi sổ rồi mới trả; gói lạnh không bị sửa."""

import asyncio
import dataclasses
import io
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import jwt
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from pypdf import PdfReader

from conftest import ISSUER, FakeHasura, text_pdf
from svc_files import sealed
from svc_files.app import content_disposition, create_app
from svc_files.archive import ARCHIVE, Archiver, ColdStore, manifest_key
from svc_files.auth import HASURA_CLAIMS
from svc_files.hasura import HasuraError
from svc_files.office import api as office_api
from test_archive import CASE, D1, D2, F1, F2, NOW, TENANT, FakeHot, FakeS3, sha
from test_archive import FakeHasura as AdminHasura
from test_archive import case_file as sample_case_file

DEPT, OTHER_DEPT = str(uuid.uuid4()), str(uuid.uuid4())
PDF_IN = text_pdf("CONG VAN DEN so 12", pages=2)
PDF_OUT = text_pdf("THONG BAO DI so 5")
# người đọc được văn bản nào (như office.document_visible): chuyên viên chỉ văn bản đến giao cho mình
READERS = {D1: {"u-chuyen-vien", "u-van-thu", "u-to-truong"}, D2: {"u-van-thu", "u-to-truong"}}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def page_text(pdf: bytes) -> list[str]:
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages]


@dataclasses.dataclass
class RoomHasura(FakeHasura):
    """Thêm hồ sơ vào Hasura giả: staff, manager thấy hồ sơ của phòng mình, clerk, director cả đơn vị. Hồ sơ thành
    `archived` khi hàm SQL nộp lưu (Hasura quản trị giả của test_archive) đã nhận lượt của nó — như CSDL thật."""

    case_files: dict[str, dict] = dataclasses.field(default_factory=dict)
    admin_hasura: AdminHasura | None = None

    async def visible_case_file(self, token: str, case_file_id: uuid.UUID) -> dict | None:
        self._check()
        ns = jwt.decode(token, options={"verify_signature": False})[HASURA_CLAIMS]
        row = self.case_files.get(str(case_file_id))
        role = ns["x-hasura-default-role"]
        if row is None or row["tenant_id"] != ns["x-hasura-tenant-id"] or role not in (
                "staff", "manager", "clerk", "director"):
            return None
        if role in ("staff", "manager") and row["department_id"] != ns.get("x-hasura-department-id"):
            return None
        out = {k: v for k, v in row.items() if k not in ("tenant_id", "department_id")}
        for p in self.admin_hasura.commits if self.admin_hasura else []:
            if p["id"] == str(case_file_id):
                out.update(status="archived", archive_key=p["archive_key"], archive_sha256=p["archive_sha256"],
                           archived_at="2026-10-20T08:00:00+00:00")
        return out


@dataclasses.dataclass
class Room:
    client: TestClient
    hasura: RoomHasura
    admin: AdminHasura
    s3: FakeS3
    hot: FakeHot
    archiver: Archiver


def package_case_file(mime_out: str = "application/pdf") -> dict:
    """Hồ sơ mẫu của test_archive với tệp là PDF thật (đóng dấu được)."""
    cf = sample_case_file()
    for link, data, mime in zip(cf["case_file_documents"], (PDF_IN, PDF_OUT), ("application/pdf", mime_out),
                                strict=True):
        link["document"]["files"][0]["file"].update(sha256=f"\\x{sha(data)}", size_bytes=len(data), mime_type=mime)
    return cf


def make_room(settings, scanner, store, verifier, meili, vault, *, mime_out: str = "application/pdf",
              **changes) -> tuple[Room, TestClient]:
    s3 = FakeS3()
    cold = ColdStore(s3, "moc-cold")
    cold.ensure = lambda: None
    hot = FakeHot()
    hot.objects = {f"tenant/{TENANT}/{F1}": PDF_IN, f"tenant/{TENANT}/{F2}": PDF_OUT}
    admin = AdminHasura(package_case_file(mime_out))
    archiver = Archiver(admin, hot, cold, after_days=365, clock=lambda: NOW)
    hasura = RoomHasura(admin_hasura=admin)
    hasura.case_files[CASE] = {"id": CASE, "tenant_id": TENANT, "department_id": DEPT, "code": "HS-01",
                               "title": "Hồ sơ tuyển sinh 2026", "year": 2026, "status": "closed",
                               "closed_on": "2026-10-01", "archived_at": None, "archive_key": None,
                               "archive_sha256": None}
    for doc_id, readers in READERS.items():
        hasura.documents[doc_id] = {"id": doc_id, "tenant_id": TENANT, "readers": readers}
    app = create_app(dataclasses.replace(settings, archive_interval_s=0, **changes), scanner=scanner, store=store,
                     verifier=verifier, hasura=hasura, meili=meili, vault=vault, cold=cold, archiver=archiver)
    client = TestClient(app)
    return Room(client, hasura, admin, s3, hot, archiver), client


@pytest.fixture
def room(settings, scanner, store, verifier, meili, vault):
    r, client = make_room(settings, scanner, store, verifier, meili, vault)
    with client:
        yield r


@pytest.fixture
def tok(signing_key):
    def _make(sub: str, role: str, department: str | None = DEPT, tenant: str = TENANT, **claims) -> str:
        now = int(time.time())
        ns = {"x-hasura-user-id": sub, "x-hasura-allowed-roles": [role], "x-hasura-default-role": role,
              "x-hasura-tenant-id": tenant}
        if department:
            ns["x-hasura-department-id"] = department
        body = {"iss": ISSUER, "sub": sub, "iat": now, "exp": now + 300, HASURA_CLAIMS: ns, **claims}
        return jwt.encode(body, signing_key, algorithm="RS256", headers={"kid": "test"})

    return _make


def manager(tok) -> dict[str, str]:
    return auth(tok("u-to-truong", "manager", name="Lê Thị Hoa", preferred_username="totruongdt"))


def clerk(tok) -> dict[str, str]:
    return auth(tok("u-van-thu", "clerk", department=None, name="Trần Thị Thu", preferred_username="vanthu"))


def staff(tok) -> dict[str, str]:
    return auth(tok("u-chuyen-vien", "staff", name="Hoàng Văn Nam", preferred_username="chuyenviendt"))


def archive(room: Room, tok) -> dict:
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert r.status_code == 200, r.text
    return r.json()


def viewed(room: Room) -> list[dict]:
    return [e for e in room.hasura.events if e["action"] == "case_file.file_viewed"]


# --- nộp lưu theo yêu cầu --------------------------------------------------------------------------------------------

def test_manager_archives_then_reader_views_a_stamped_pdf_and_the_cold_package_stays_untouched(room, tok):
    out = archive(room, tok)
    [commit] = room.admin.commits
    assert out["archive_sha256"] == commit["archive_sha256"] and (out["documents"], out["files"]) == (2, 2)
    assert out["archive_key"] == f"cold/{TENANT}/case/{CASE}/" and out["code"] == "HS-01"
    # yêu cầu nộp lưu vào sổ trước, do chính lãnh đạo phòng (dòng case_file.archived do hàm SQL ghi)
    [requested] = room.hasura.events
    assert requested["action"] == "case_file.archive_requested" and requested["actor_id"] == "u-to-truong"
    assert requested["entity"] == "office.case_files" and requested["details"] == {"code": "HS-01"}

    listing = room.client.get(f"/api/case-files/{CASE}/archive", headers=clerk(tok)).json()
    assert {(f["file_id"], f["viewable"], tuple(f["document_ids"])) for f in listing["files"]} == {
        (F1, True, (D1,)), (F2, True, (D2,))}

    versions = {k: list(v) for k, v in room.s3.versions.items()}
    puts = room.s3.puts
    r = room.client.get(f"/api/case-files/{CASE}/archive/files/{F1}", headers=staff(tok))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith('inline; filename="cong van.pdf"')
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]
    texts = page_text(r.content)
    assert len(texts) == 2 and r.content != PDF_IN
    for text in texts:   # mọi trang: nội dung gốc, dấu phòng đọc, tên người xem — không phải chữ của văn bản hạn chế
        assert "CONG VAN DEN so 12" in text and "PHÒNG ĐỌC" in text
        assert "Hoàng Văn Nam (chuyenviendt)" in text and "VĂN BẢN HẠN CHẾ" not in text
    [event] = viewed(room)
    assert (event["entity"], event["entity_id"], event["actor_id"]) == ("office.case_files", CASE, "u-chuyen-vien")
    assert event["details"]["file_id"] == F1 and event["details"]["sha256"] == sha(PDF_IN)
    assert event["details"]["code"] == "HS-01" and event["details"]["archive_sha256"] == out["archive_sha256"]
    assert event["details"]["watermark"] == "Hoàng Văn Nam (chuyenviendt)"
    # chỉ xem: không ghi gì, không thêm phiên bản nào vào bucket lạnh
    assert room.s3.puts == puts and {k: list(v) for k, v in room.s3.versions.items()} == versions


@pytest.mark.parametrize("who", ["staff", "clerk", "director", "manager-of-another-department", "other-tenant"])
def test_only_the_department_manager_can_request_archiving(room, tok, who):
    headers = {
        "staff": staff(tok),
        "clerk": clerk(tok),
        "director": auth(tok("u-truong-khoa", "director", department=None)),
        "manager-of-another-department": auth(tok("u-truong-bm", "manager", department=OTHER_DEPT)),
        "other-tenant": auth(tok("u-to-truong", "manager", tenant=str(uuid.uuid4()))),
    }[who]
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=headers)
    assert r.status_code == (404 if who in ("manager-of-another-department", "other-tenant") else 403)
    assert r.json()["detail"]["code"] in ("forbidden", "not_found")
    assert room.admin.commits == [] and room.s3.puts == 0 and room.hasura.events == []


def test_archiving_needs_a_closed_case_file(room, tok):
    room.hasura.case_files[CASE]["status"] = "open"
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "not_closed")
    room.hasura.case_files[CASE]["status"] = "closed"
    archive(room, tok)
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "already_archived")
    assert len(room.admin.commits) == 1


def test_nothing_is_archived_when_the_request_cannot_be_audited(room, tok):
    room.hasura.fail_events = True
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert r.status_code == 503 and room.admin.commits == [] and room.s3.puts == 0


def test_failed_archiving_is_a_409_and_changes_nothing(room, tok):
    room.hot.objects[f"tenant/{TENANT}/{F1}"] = text_pdf("BAN DA BI SUA")
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "archive_failed"
    assert "không khớp băm" in r.json()["detail"]["message"]
    assert room.admin.commits == [] and room.s3.puts == 0 and room.hot.deleted == []


def hold(room: Room) -> None:
    """Giữ lượt nộp lưu như một lượt khác (vòng nền) đang chạy — trong đúng event loop của app."""
    assert room.client.portal.call(room.archiver.lock.acquire)


def release(room: Room) -> None:
    room.client.portal.call(room.archiver.lock.release)


def test_archiving_waits_for_the_run_in_progress_then_answers_busy_without_an_audit_row(room, tok, monkeypatch):
    monkeypatch.setattr(office_api, "SEALING_QUEUE_S", 0.05)
    hold(room)
    try:
        r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    finally:
        release(room)
    assert (r.status_code, r.json()["detail"]["code"]) == (503, "busy") and r.headers["retry-after"] == "10"
    # bận thì chưa làm gì: không có dòng "yêu cầu nộp lưu", không ghi gì vào bucket lạnh
    assert room.hasura.events == [] and room.admin.commits == [] and room.s3.puts == 0
    archive(room, tok)      # hết bận thì nộp lưu được


def test_a_run_that_finished_while_waiting_answers_already_archived(room, tok):
    hold(room)
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(room.client.post, f"/api/case-files/{CASE}/archive", headers=manager(tok))
        deadline = time.monotonic() + 5
        while not room.archiver.lock._waiters and time.monotonic() < deadline:   # POST đã qua kiểm đầu, đang chờ
            time.sleep(0.01)
        # lượt đang giữ khóa nộp lưu xong hồ sơ này
        room.admin.commits.append({"id": CASE, "archive_key": f"cold/{TENANT}/case/{CASE}/",
                                   "archive_sha256": "a" * 64})
        release(room)
        r = waiting.result(timeout=10)
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "already_archived")
    assert room.hasura.events == [] and room.s3.puts == 0


class CountingHot(FakeHot):
    reads = 0

    def read_stream(self, key: str):
        self.reads += 1
        return super().read_stream(key)


def test_background_run_takes_the_same_lock_as_the_archive_button():
    async def go() -> None:
        cold = ColdStore(FakeS3(), "moc-cold")
        cold.ensure = lambda: None
        admin = AdminHasura(package_case_file())
        hot = CountingHot()
        hot.objects = {f"tenant/{TENANT}/{F1}": PDF_IN, f"tenant/{TENANT}/{F2}": PDF_OUT}
        archiver = Archiver(admin, hot, cold, after_days=365, clock=lambda: NOW)
        await archiver.lock.acquire()           # nút "Nộp lưu" đang chạy
        task = asyncio.create_task(archiver.run_once(after_days=0))
        for _ in range(500):                    # vòng nền tới lượt hồ sơ đến hạn thì đứng chờ khóa
            if archiver.lock._waiters or task.done():
                break
            await asyncio.sleep(0.01)
        assert archiver.lock._waiters and not task.done()
        assert admin.commits == [] and hot.reads == 0      # chưa đọc, chưa ghi gì
        archiver.lock.release()
        done, failed = await task
        assert [d.code for d in done] == ["HS-01"] and failed == []

    asyncio.run(go())


def test_archive_started_elsewhere_is_already_archived(room, tok):
    # lệnh tay ở tiến trình khác vừa nộp lưu: CSDL (khóa quản trị) đã archived, token người gọi còn thấy closed
    room.admin.cf["status"] = "archived"
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "already_archived")
    assert room.admin.commits == [] and room.s3.puts == 0


def reject_commit(room: Room, code: str | None, *, committed: bool = False, then_down: bool = False) -> None:
    """Hàm SQL nộp lưu trả lỗi (code: mã GraphQL, None là mất kết nối); committed: CSDL đã nhận rồi mới mất câu trả
    lời; then_down: sau đó không đọc lại được hồ sơ."""
    original = room.admin.admin

    async def admin(query, variables, headers=None):
        if query != ARCHIVE:
            return await original(query, variables, headers)
        if committed:
            await original(query, variables, headers)
        room.hasura.down = then_down
        raise HasuraError("văn bản trong hồ sơ HS-01 đổi trong lúc nộp lưu", code)

    room.admin.admin = admin


@pytest.mark.parametrize(("code", "committed", "then_down", "status", "error"), [
    ("permission-error", False, False, 409, "archive_conflict"),     # hàm SQL từ chối, giao dịch quay lui
    ("unexpected", False, False, 409, "archive_conflict"),
    (None, False, False, 503, "database_unavailable"),               # mất kết nối: chưa biết đã xong chưa
    ("permission-error", False, True, 503, "database_unavailable"),  # không đọc lại được hồ sơ
    (None, True, False, 409, "already_archived"),                     # đã xong, chỉ mất câu trả lời
])
def test_database_answer_to_the_archive_run_maps_to_the_right_error(room, tok, code, committed, then_down, status,
                                                                     error):
    reject_commit(room, code, committed=committed, then_down=then_down)
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (status, error)
    assert room.hot.deleted == []          # bản nóng chỉ xóa sau khi CSDL xác nhận
    assert len(room.admin.commits) == (1 if committed else 0)


def test_cold_bucket_down_while_archiving_is_503(room, tok, monkeypatch):
    def down(**_kw):
        raise ClientError({"Error": {"Code": "InternalError"}}, "PutObject")

    monkeypatch.setattr(room.s3, "put_object", down)
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (503, "storage_unavailable")
    assert room.admin.commits == [] and room.hot.deleted == []


def test_archive_request_with_the_database_down_is_503(room, tok):
    room.hasura.down = True
    r = room.client.post(f"/api/case-files/{CASE}/archive", headers=manager(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (503, "database_unavailable")
    assert room.admin.commits == []


# --- phòng đọc xem tệp -----------------------------------------------------------------------------------------------

def test_file_of_a_document_the_caller_cannot_read_is_not_found(room, tok):
    archive(room, tok)
    # chuyên viên chỉ đọc được văn bản đến: tệp của văn bản đi không có trong danh sách của họ, mở thẳng cũng 404
    listing = room.client.get(f"/api/case-files/{CASE}/archive", headers=staff(tok)).json()
    assert [f["file_id"] for f in listing["files"]] == [F1] and listing["hidden"] == 1
    for file_id in (F2, str(uuid.uuid4())):
        r = room.client.get(f"/api/case-files/{CASE}/archive/files/{file_id}", headers=staff(tok))
        assert (r.status_code, r.json()["detail"]["code"]) == (404, "not_found")
    assert viewed(room) == []


def test_case_file_must_be_visible_and_archived(room, tok):
    r = room.client.get(f"/api/case-files/{CASE}/archive/files/{F1}", headers=clerk(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "not_archived")
    archive(room, tok)
    other = auth(tok("u-van-thu", "clerk", department=None, tenant=str(uuid.uuid4())))
    for headers in (other, auth(tok("u-giang-vien", "staff", department=OTHER_DEPT))):
        r = room.client.get(f"/api/case-files/{CASE}/archive/files/{F1}", headers=headers)
        assert r.status_code == 404
    assert room.client.get(f"/api/case-files/{CASE}/archive/files/{F1}").status_code == 401
    assert viewed(room) == []


def test_tampered_file_or_manifest_in_the_cold_bucket_is_never_returned(room, tok):
    out = archive(room, tok)
    prefix = out["archive_key"]
    room.s3.versions[f"{prefix}files/{sha(PDF_IN)}"].append((text_pdf("NOI DUNG DA BI THAY"), {}))
    r = room.client.get(f"/api/case-files/{CASE}/archive/files/{F1}", headers=clerk(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (502, "archive_mismatch")
    assert b"%PDF" not in r.content
    manifest = room.s3.versions[manifest_key(prefix, out["archive_sha256"])]
    manifest.append((manifest[-1][0].replace(b"HS-01", b"HS-99"), {}))
    r = room.client.get(f"/api/case-files/{CASE}/archive/files/{F2}", headers=clerk(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (502, "archive_mismatch")
    assert viewed(room) == []


def test_missing_part_of_the_package_is_a_broken_package_not_a_retry(room, tok):
    out = archive(room, tok)
    prefix = out["archive_key"]
    del room.s3.versions[f"{prefix}files/{sha(PDF_IN)}"]
    r = room.client.get(f"/api/case-files/{CASE}/archive/files/{F1}", headers=clerk(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (502, "archive_mismatch")
    del room.s3.versions[manifest_key(prefix, out["archive_sha256"])]
    for url in (f"/api/case-files/{CASE}/archive", f"/api/case-files/{CASE}/archive/files/{F2}"):
        r = room.client.get(url, headers=clerk(tok))
        assert (r.status_code, r.json()["detail"]["code"]) == (502, "archive_mismatch")
    assert viewed(room) == []


def test_cold_bucket_down_is_503(room, tok, monkeypatch):
    archive(room, tok)

    def down(**_kw):
        raise ClientError({"Error": {"Code": "InternalError"}}, "GetObject")

    monkeypatch.setattr(room.s3, "get_object", down)
    r = room.client.get(f"/api/case-files/{CASE}/archive/files/{F1}", headers=clerk(tok))
    assert (r.status_code, r.json()["detail"]["code"]) == (503, "storage_unavailable")


def test_nothing_is_returned_when_the_view_cannot_be_audited(room, tok):
    archive(room, tok)
    room.hasura.fail_events = True
    r = room.client.get(f"/api/case-files/{CASE}/archive/files/{F1}", headers=clerk(tok))
    assert r.status_code == 503 and b"%PDF" not in r.content


def test_only_pdf_files_open_in_the_reading_room(settings, scanner, store, verifier, meili, vault, tok):
    r, client = make_room(settings, scanner, store, verifier, meili, vault, mime_out="image/png")
    with client:
        archive(r, tok)
        listing = client.get(f"/api/case-files/{CASE}/archive", headers=clerk(tok)).json()
        assert {f["file_id"]: f["viewable"] for f in listing["files"]} == {F1: True, F2: False}
        got = client.get(f"/api/case-files/{CASE}/archive/files/{F2}", headers=clerk(tok))
        assert (got.status_code, got.json()["detail"]["code"]) == (415, "not_viewable")
        assert viewed(r) == []


def test_pdf_over_the_page_cap_is_not_stamped(settings, scanner, store, verifier, meili, vault, tok):
    r, client = make_room(settings, scanner, store, verifier, meili, vault, restricted_max_pages=1)
    with client:
        archive(r, tok)
        got = client.get(f"/api/case-files/{CASE}/archive/files/{F1}", headers=clerk(tok))
        assert (got.status_code, got.json()["detail"]["code"]) == (422, "unstampable")
        assert got.json()["detail"]["reason"] == "too_many_pages" and viewed(r) == []
        assert client.get(f"/api/case-files/{CASE}/archive/files/{F2}", headers=clerk(tok)).status_code == 200


# --- dấu phòng đọc ---------------------------------------------------------------------------------------------------

def test_reading_room_stamp_has_its_own_words_and_restricted_stamp_is_unchanged():
    at = datetime(2026, 10, 20, 3, 15, tzinfo=UTC)
    archive_text = page_text(sealed.watermark(PDF_OUT, "Trần Thị Thu (vanthu)", at, kind="archive"))[0]
    assert "PHÒNG ĐỌC" in archive_text and "Chỉ để xem" in archive_text and "10:15 20/10/2026" in archive_text
    assert "VĂN BẢN HẠN CHẾ" not in archive_text and "THONG BAO DI so 5" in archive_text
    restricted_text = page_text(sealed.watermark(PDF_OUT, "Trần Thị Thu (vanthu)", at))[0]
    assert "VĂN BẢN HẠN CHẾ" in restricted_text and "PHÒNG ĐỌC" not in restricted_text
    # tiến trình con đóng dấu đúng như trong tiến trình
    out = asyncio.run(sealed.run_watermark(PDF_OUT, "Trần Thị Thu (vanthu)", at, max_pages=500, kind="archive"))
    assert page_text(out) == [archive_text]
    with pytest.raises(ValueError):
        asyncio.run(sealed.run_watermark(PDF_OUT, "An", at, max_pages=500, kind="khac"))


def test_inline_disposition_only_when_asked():
    assert content_disposition("Công văn số 5.pdf").startswith('attachment; filename="Cong van so 5.pdf"')
    assert content_disposition("Công văn số 5.pdf", inline=True) == (
        "inline; filename=\"Cong van so 5.pdf\"; filename*=UTF-8''C%C3%B4ng%20v%C4%83n%20s%E1%BB%91%205.pdf")
