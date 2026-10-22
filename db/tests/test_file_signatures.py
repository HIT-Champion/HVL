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

"""Ký số văn bản đi (F4.5, chỉ minh họa; migration 1792281602200): svc-files ghi dòng core.files của bản phát hành đã ký
và dòng core.file_signatures trong cùng một mutation (vai trò service, thuê ước đặt sẵn từ phiên); khóa ngoại kèm thuê
ước chặn gắn chữ ký vào tệp của đơn vị khác; ràng buộc từng cột; cổng xác thực (vai trò verifier) đọc chuẩn, người ký,
CA, số sê-ri, giờ ký qua khung nhìn office.issued_documents (tìm theo băm, nên văn bản đã nộp lưu vẫn có chữ ký), null
khi bản phát hành không ký; không vai trò nào đọc bảng; sổ kiểm toán có dòng của chữ ký (bản tối thiểu chưa có nhánh
core.audit_overview: chỉ hiện tên khóa, trừ file_id); xóa tệp thì chữ ký mất theo. svc-files không chạy ở đây: test
gửi đúng mutation INSERT_SIGNED_FILE của svc_files.hasura (hợp đồng F4.5 §4.5)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from conftest import ADMIN_SECRET, GraphQLError, Service, User, World, gql_raw, sql
from test_case_files import ARCHIVE, _admin, _closed
from test_outgoing import ISSUE, approve, as_clerk, draft, number

# svc_files.hasura.INSERT_SIGNED_FILE: tệp và chữ ký trong một giao dịch, không cần quyền đọc bảng chữ ký
SAVE = """mutation InsertSignedFile($o: core_files_insert_input!, $s: core_file_signatures_insert_input!) {
  insert_core_files_one(object: $o) { id }
  insert_core_file_signatures(objects: [$s]) { affected_rows } }"""
FILE_ONLY = """mutation ($o: core_files_insert_input!) { insert_core_files_one(object: $o) { id } }"""
SIGN_ONLY = """mutation ($s: core_file_signatures_insert_input!) {
  insert_core_file_signatures(objects: [$s]) { affected_rows } }"""

# svc_files.hasura.VERIFY (F4.5 thêm năm cột chữ ký)
VERIFY = """query ($where: office_issued_documents_bool_exp!) {
  office_issued_documents(where: $where) {
    verify_code content_sha256 symbol issued_on type_code type_name issuer_name parent_name summary status
    signature_level signed_at signer_name signer_ca certificate_serial
  }
}"""

AUDIT_VIEW = """query ($e: String!) {
  core_audit_log(where: {entity: {_eq: "core.file_signatures"}, entity_id: {_eq: $e}}, order_by: {id: asc}) {
    action entity entity_id actor_id actor_kind overview } }"""

CA = "CA nội bộ Mộc - MẪU, chỉ minh họa"
SIGNED_AT = datetime(2026, 10, 23, 3, 12, 45, tzinfo=timezone.utc)
SIGNATURE_COLUMNS = ("signature_level", "signed_at", "signer_name", "signer_ca", "certificate_serial")


def svc_files(tenant: str) -> Service:
    """svc-files khi phát hành: khóa quản trị + vai trò service + thuê ước của văn bản."""
    return Service("svc-files", "service", tenant)


def file_row(tenant: str, content: bytes) -> dict:
    """Dòng core.files của bản phát hành như svc-files ghi (đã qua ClamAV, khóa đối tượng dưới tiền tố đơn vị)."""
    file_id = str(uuid.uuid4())
    return {"id": file_id, "object_key": f"tenant/{tenant}/2026/10/{file_id}", "filename": "van-ban.pdf",
            "mime_type": "application/pdf", "size_bytes": len(content),
            "sha256": "\\x" + hashlib.sha256(content).hexdigest(), "scanned_at": "2026-10-23T10:12:46+07:00"}


def signature(file_id: str, tenant: str, **overrides) -> dict:
    """SignatureRecord như svc-files gửi (§4.5): tenant_id do Hasura đặt, cert_sha256 dạng \\x…"""
    row = {"file_id": file_id, "level": "PAdES-B-B", "signed_at": SIGNED_AT.isoformat(),
           "signer_name": "Đơn vị thử A, Trường Đại học Thử", "ca_name": CA, "serial": uuid.uuid4().hex,
           "cert_sha256": "\\x" + hashlib.sha256(file_id.encode()).hexdigest(),
           "not_after": "2027-10-23T03:12:45+00:00", "key_name": f"moc-ky-so-{tenant}", "key_version": 1}
    row.update(overrides)
    return row


def save_signed(tenant: str, content: bytes, **overrides) -> tuple[str, dict]:
    o = file_row(tenant, content)
    s = signature(o["id"], tenant, **overrides)
    data = svc_files(tenant).gql(SAVE, {"o": o, "s": s})
    assert data == {"insert_core_files_one": {"id": o["id"]}, "insert_core_file_signatures": {"affected_rows": 1}}
    return o["id"], s


def save_file(tenant: str, content: bytes) -> str:
    """Tệp không ký (văn bản hạn chế, két chưa có PKI, ký lỗi): chỉ dòng core.files."""
    return svc_files(tenant).gql(FILE_ONLY, {"o": file_row(tenant, content)})["insert_core_files_one"]["id"]


def stored(file_id: str) -> list[list[str]]:
    return sql("select tenant_id, level, signer_name, ca_name, serial, key_name, key_version from core.file_signatures "
               f"where file_id = '{file_id}'")


def files(file_id: str) -> list[list[str]]:
    return sql(f"select tenant_id from core.files where id = '{file_id}'")


def verifier(where: dict) -> list[dict]:
    body = gql_raw(VERIFY, {"where": where},
                   headers={"X-Hasura-Admin-Secret": ADMIN_SECRET, "X-Hasura-Role": "verifier"})
    assert "errors" not in body, body
    return body["data"]["office_issued_documents"]


def pdf(world: World, n: int) -> bytes:
    return f"%PDF-1.7 ký số thử {world.tag} {n}".encode()


def issue(world: World, n: int, *, signed: bool) -> tuple[str, str, dict | None]:
    """Văn bản đi qua đủ các bước tới phát hành; bản phát hành có (hoặc không có) chữ ký như svc-files ghi, rồi phần
    svc-workflow làm (trạng thái issued, content_sha256, gắn tệp vai trò issued). Trả mã tra cứu, id tệp, chữ ký."""
    doc = draft(world, n, summary=f"Thông báo lịch họp giao ban tháng 11 (ký số {n})")
    approve(world, doc)
    code = number(world, doc, n)["verify_code"]
    content = pdf(world, n)
    sig = None
    if signed:
        file_id, sig = save_signed(world.tenant_a, content)
    else:
        file_id = save_file(world.tenant_a, content)
    as_clerk(world).gql(ISSUE, {
        "id": doc, "sha": "\\x" + hashlib.sha256(content).hexdigest(), "public": False,
        "file": {"document_id": doc, "file_id": file_id, "role": "issued", "added_by": world.clerk_a.sub},
    })
    return code, file_id, sig


# --- ghi ------------------------------------------------------------------------------------------------------------


def test_file_and_signature_are_saved_in_one_mutation(world: World):
    file_id, sig = save_signed(world.tenant_a, b"%PDF-1.7 ban phat hanh da ky")
    assert files(file_id) == [[world.tenant_a]]
    assert stored(file_id) == [[world.tenant_a, "PAdES-B-B", "Đơn vị thử A, Trường Đại học Thử", CA, sig["serial"],
                                f"moc-ky-so-{world.tenant_a}", "1"]]
    [[cert]] = sql(f"select encode(cert_sha256, 'hex') from core.file_signatures where file_id = '{file_id}'")
    assert cert == sig["cert_sha256"][2:]


def test_bad_signature_keeps_the_file_out_too(world: World):
    # một giao dịch: chữ ký bị chặn thì dòng tệp cũng không được lưu (svc-files trả lỗi, svc-workflow thử lại)
    o = file_row(world.tenant_a, b"%PDF-1.7 chu ky hong")
    with pytest.raises(GraphQLError, match=r"\bfile_signatures_level_check\b"):
        svc_files(world.tenant_a).gql(SAVE, {"o": o, "s": signature(o["id"], world.tenant_a, level="PAdES-B-T")})
    assert files(o["id"]) == [] and stored(o["id"]) == []


def test_signature_cannot_be_attached_to_a_file_of_another_unit(world: World):
    file_id = save_file(world.tenant_a, b"%PDF-1.7 tep cua A")
    with pytest.raises(GraphQLError, match="foreign key"):        # phiên đơn vị B, tệp của đơn vị A
        svc_files(world.tenant_b).gql(SIGN_ONLY, {"s": signature(file_id, world.tenant_b)})
    with pytest.raises(GraphQLError, match="foreign key"):        # tệp không tồn tại
        svc_files(world.tenant_a).gql(SIGN_ONLY, {"s": signature(str(uuid.uuid4()), world.tenant_a)})
    assert stored(file_id) == []


def test_service_cannot_choose_tenant_or_time(world: World):
    file_id = save_file(world.tenant_a, b"%PDF-1.7 chon don vi")
    for column, value in (("tenant_id", world.tenant_b), ("created_at", "2026-01-01T00:00:00+07:00")):
        body = svc_files(world.tenant_a).raw(SIGN_ONLY, {"s": {**signature(file_id, world.tenant_a), column: value}})
        assert "errors" in body and column in body["errors"][0]["message"], column
    assert stored(file_id) == []


# --- hình dạng ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("overrides", "constraint"), [
    ({"level": "PAdES-B-T"}, "file_signatures_level_check"),             # chỉ B-B: không có dấu thời gian tin cậy
    ({"serial": "3f:9a:01"}, "file_signatures_serial_check"),            # hex thường, không dấu ':'
    ({"serial": "3F9A01"}, "file_signatures_serial_check"),
    ({"serial": "a"}, "file_signatures_serial_check"),
    ({"cert_sha256": "\\x" + "ab" * 31}, "file_signatures_cert_sha256_check"),
    ({"key_name": "moc-files"}, "file_signatures_key_name_check"),       # chỉ khóa ký moc-ky-so-<đơn vị>
    ({"key_name": "moc-ky-so-khoa-cntt"}, "file_signatures_key_name_check"),
    ({"key_version": 0}, "file_signatures_key_version_check"),
    ({"signer_name": ""}, "file_signatures_signer_name_check"),
    ({"signer_name": "x" * 65}, "file_signatures_signer_name_check"),     # CN ≤ 64 ký tự (RFC 5280)
    ({"ca_name": "x" * 65}, "file_signatures_ca_name_check"),
])
def test_signature_shape_is_checked(world: World, overrides: dict, constraint: str):
    file_id = save_file(world.tenant_a, b"%PDF-1.7 hinh dang")
    with pytest.raises(GraphQLError, match=rf"\b{constraint}\b"):
        svc_files(world.tenant_a).gql(SIGN_ONLY, {"s": signature(file_id, world.tenant_a, **overrides)})
    assert stored(file_id) == []


def test_one_signature_per_file(world: World):
    file_id, _ = save_signed(world.tenant_a, b"%PDF-1.7 mot chu ky")
    with pytest.raises(GraphQLError, match="file_signatures_pkey"):
        svc_files(world.tenant_a).gql(SIGN_ONLY, {"s": signature(file_id, world.tenant_a)})
    assert len(stored(file_id)) == 1


# --- cổng xác thực --------------------------------------------------------------------------------------------------


def test_verifier_reads_the_signature_of_a_signed_issued_document(world: World):
    code, file_id, sig = issue(world, 9601, signed=True)
    [found] = verifier({"verify_code": {"_eq": code}})
    assert (found["signature_level"], found["signer_name"], found["signer_ca"], found["certificate_serial"]) == (
        "PAdES-B-B", "Đơn vị thử A, Trường Đại học Thử", CA, sig["serial"])
    assert datetime.fromisoformat(found["signed_at"]) == SIGNED_AT
    assert found["status"] == "issued" and found["issuer_name"] == "Đơn vị thử A"
    # tra theo băm như trình duyệt: cùng một dòng
    assert verifier({"content_sha256": {"_eq": found["content_sha256"]}}) == [found]
    # chữ ký tìm theo băm: một tệp khác cùng nội dung (tải lên lại bản đã nhận) không có chữ ký, không nhân dòng, không
    # thay chữ ký của bản phát hành
    copy = save_file(world.tenant_a, pdf(world, 9601))
    assert copy != file_id and stored(copy) == []
    assert verifier({"verify_code": {"_eq": code}}) == [found]
    assert sql(f"select count(*) from office.issued_documents where verify_code = '{code}'") == [["1"]]


def test_archived_document_keeps_its_signature(world: World):
    # nộp lưu (F3.8) xóa dòng gắn tệp của văn bản nhưng giữ tệp (chuyển sang kho lạnh), nên giữ cả dòng chữ ký: cổng xác
    # thực vẫn hiện chữ ký của văn bản đã nộp lưu
    code, file_id, sig = issue(world, 9603, signed=True)
    [[doc]] = sql(f"select id from office.documents where verify_code = '{code}'")
    cf = _closed(world, doc)
    events = [int(r[0]) for r in sql(f"select id from office.document_events where document_id = '{doc}'")]
    p = {"id": cf["id"], "archive_key": f"cold/{world.tenant_a}/case/{cf['id']}/",
         "archive_sha256": hashlib.sha256(b"manifest ky so").hexdigest(), "bucket": "moc-cold", "documents": [doc],
         "events": events, "links": [{"document_id": doc, "file_id": file_id}], "cold_files": [file_id], "files": 1}
    body = _admin(ARCHIVE, {"p": p})
    assert "errors" not in body, body
    assert sql(f"select count(*) from office.document_files where document_id = '{doc}'") == [["0"]]
    assert sql(f"select storage_tier from core.files where id = '{file_id}'") == [["cold"]]
    [found] = verifier({"verify_code": {"_eq": code}})
    assert found["status"] == "archived"
    assert (found["signature_level"], found["signer_name"], found["signer_ca"], found["certificate_serial"]) == (
        "PAdES-B-B", "Đơn vị thử A, Trường Đại học Thử", CA, sig["serial"])
    assert verifier({"content_sha256": {"_eq": found["content_sha256"]}}) == [found]


def test_unsigned_issued_document_has_null_signature_and_same_columns(world: World):
    code, _, _ = issue(world, 9602, signed=False)
    [found] = verifier({"verify_code": {"_eq": code}})
    assert all(found[c] is None for c in SIGNATURE_COLUMNS), found
    assert found["status"] == "issued" and found["type_name"] == "Thông báo" and found["summary"] is None
    assert found["symbol"].endswith(f"/TB-A{world.tag}") and found["content_sha256"].startswith("\\x")


def test_verifier_still_reads_one_row_and_nothing_else(world: World):
    assert len(verifier({})) <= 1                                     # limit: 1 giữ nguyên
    body = gql_raw("{ core_file_signatures { file_id } }",
                   headers={"X-Hasura-Admin-Secret": ADMIN_SECRET, "X-Hasura-Role": "verifier"})
    assert "errors" in body


# --- quyền ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["clerk_a", "staff_a1", "manager_a1", "director_a", "admin_a"])
def test_users_do_not_see_signatures_table(world: World, who: str):
    body = getattr(world, who).raw("{ core_file_signatures { file_id serial } }")
    assert "errors" in body and "core_file_signatures" in body["errors"][0]["message"]
    body = getattr(world, who).raw(SIGN_ONLY, {"s": signature(str(uuid.uuid4()), world.tenant_a)})
    assert "errors" in body


def test_nobody_reads_edits_or_deletes_signatures(world: World):
    file_id, _ = save_signed(world.tenant_a, b"%PDF-1.7 khong sua")
    svc = svc_files(world.tenant_a)
    for query in ("{ core_file_signatures { file_id } }",
                  'mutation { update_core_file_signatures(where: {}, _set: {serial: "ff"}) { affected_rows } }',
                  "mutation { delete_core_file_signatures(where: {}) { affected_rows } }"):
        assert "errors" in svc.raw(query), query
    # trả `returning` cần quyền đọc: svc-files chỉ hỏi affected_rows
    body = svc.raw("""mutation ($s: core_file_signatures_insert_input!) {
      insert_core_file_signatures(objects: [$s]) { returning { file_id } } }""",
                   {"s": signature(str(uuid.uuid4()), world.tenant_a)})
    assert "errors" in body
    assert len(stored(file_id)) == 1


# --- sổ kiểm toán, xóa tệp ------------------------------------------------------------------------------------------


def test_signature_is_in_the_audit_log(world: World):
    file_id, _ = save_signed(world.tenant_a, b"%PDF-1.7 vao so")
    assert sql("select tenant_id, actor_id, actor_kind, action, entity from core.audit_log "
               f"where entity = 'core.file_signatures' and entity_id = '{file_id}'") == [
        [world.tenant_a, "svc-files", "service", "insert", "core.file_signatures"]]
    # bản tối thiểu của F4.5 chưa thêm nhánh vào core.audit_overview: màn Sổ kiểm toán thấy tên khóa, giá trị chỉ có ở
    # file_id (danh sách chung); vân tay chứng thư, số sê-ri không hiện
    for viewer in (world.director_a, world.admin_a):
        [row] = viewer.gql(AUDIT_VIEW, {"e": file_id})["core_audit_log"]
        assert (row["action"], row["entity"], row["entity_id"], row["actor_kind"]) == (
            "insert", "core.file_signatures", file_id, "service")
        overview = row["overview"]
        assert overview["file_id"] == [None, file_id]
        for key in ("level", "signed_at", "signer_name", "ca_name", "serial", "cert_sha256", "key_name", "key_version"):
            assert key in overview and overview[key] is None, key
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert other.gql(AUDIT_VIEW, {"e": file_id})["core_audit_log"] == []


def test_deleting_the_file_deletes_its_signature(world: World):
    file_id, _ = save_signed(world.tenant_a, b"%PDF-1.7 xoa tep")
    sql(f"delete from core.files where id = '{file_id}'")
    assert files(file_id) == [] and stored(file_id) == []
    assert sql("select action from core.audit_log "
               f"where entity = 'core.file_signatures' and entity_id = '{file_id}' order by id") == [
        ["insert"], ["delete"]]
