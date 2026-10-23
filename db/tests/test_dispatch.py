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

"""Liên thông văn bản trong hệ thống (F3.12): đơn vị nhận chọn lúc soạn và khóa sau khi trình, hộp thư đi tạo trong
giao dịch phát hành, office.deliver_dispatch giao đúng một lần, mỗi đơn vị chỉ thấy phần của mình, hai sổ kiểm toán
cùng ghi. svc-workflow, svc-files không chạy ở đây: test ghi như hai dịch vụ ghi (phát hành, chép tệp)."""

from __future__ import annotations

import json
import uuid

import pytest
from conftest import INSERT_DOC, GraphQLError, Service, SQLError, User, World, outgoing, received, sql, visible_ids
from test_outgoing import BODY, approve, issue, number

DELIVER = """
mutation ($id: uuid!) {
  office_deliver_dispatch(args: {dispatch_id: $id}) { id status incoming_document_id last_error delivered_at }
}"""

ONE = """query ($id: uuid!) {
  office_dispatches(where: {id: {_eq: $id}}) {
    id status to_unit { name } from_unit { name } document { id } incoming { id }
  }
}"""

UPDATE_DOC = """
mutation ($id: uuid!, $set: office_documents_set_input!) {
  update_office_documents(where: {id: {_eq: $id}}, _set: $set) { affected_rows }
}"""

STATUS = """
mutation ($id: uuid!, $s: String!) {
  update_office_documents_by_pk(pk_columns: {id: $id}, _set: {status: $s}) { id }
}"""

# Đúng ba mutation svc-workflow gửi khi giao lỗi, khi svc-files từ chối hẳn và khi đã báo văn thư bên nhận (hợp đồng
# F3.12)
RETRY = """
mutation ($id: uuid!, $error: String!, $next: timestamptz!) {
  update_office_dispatches_by_pk(pk_columns: {id: $id}, _inc: {attempts: 1},
                                 _set: {last_error: $error, next_attempt_at: $next}) { id }
}"""
FAIL = """
mutation ($id: uuid!, $reason: String!) {
  office_fail_dispatch(args: {dispatch_id: $id, reason: $reason}) { id status last_error }
}"""
NOTIFIED = """
mutation ($id: uuid!, $now: timestamptz!) {
  update_office_dispatches_by_pk(pk_columns: {id: $id}, _set: {notified_at: $now}) { id }
}"""

HISTORY = """query ($d: uuid!) { office_document_history(where: {document_id: {_eq: $d}}, order_by: {id: asc}) {
  action entity actor_id overview } }"""


@pytest.fixture(scope="module")
def tenant_c(world: World) -> str:
    """Đơn vị thứ ba: nhận cùng văn bản với B, và là người ngoài khi A gửi cho B."""
    return sql(f"insert into core.tenants (code, name) values ('C{world.tag}', 'Đơn vị thử C') returning id")[0][0]


def draft(world: World, n: int, units: list[str], **overrides) -> str:
    doc = outgoing(n, body=BODY, recipients=["Đơn vị nhận"], recipient_tenant_ids=units, **overrides)
    return world.staff_a1.gql(INSERT_DOC, {"o": doc})["insert_office_documents_one"]["id"]


def issued(world: World, n: int, units: list[str], **overrides) -> str:
    """Văn bản đi của phòng A1 gửi `units`, đã duyệt, cấp số, phát hành như svc-workflow làm."""
    doc = draft(world, n, units, **overrides)
    approve(world, doc)
    number(world, doc, n)
    issue(world, doc, f"PDF liên thông {world.tag} {n}".encode(), public=False)
    return doc


def rows(doc: str) -> list[dict]:
    """Hộp thư đi của một văn bản, đọc thẳng CSDL (run_sql in null là NULL)."""
    cols = ["id", "tenant_id", "to_tenant_id", "status", "file_id", "incoming_document_id", "source_verify_code",
            "sha", "attempts", "last_error"]
    found = sql("select id, tenant_id, to_tenant_id, status, file_id, incoming_document_id, source_verify_code, "
                "encode(source_sha256, 'hex'), attempts, last_error from office.dispatches "
                f"where document_id = '{doc}' order by to_tenant_id")
    return [dict(zip(cols, r)) for r in found]


def copy_file(row: dict, *, tier: str = "hot", sha: str | None = None) -> None:
    """Phần svc-files làm (POST /internal/dispatch-file): bản sao tệp phát hành thuộc đơn vị nhận, id định trước."""
    to, fid, sha = row["to_tenant_id"], row["file_id"], sha or row["sha"]
    sql("insert into core.files (id, tenant_id, object_key, filename, mime_type, size_bytes, sha256, scanned_at, "
        f"storage_tier, created_by) values ('{fid}', '{to}', 'tenant/{to}/2026/10/{fid}', 'van-ban.pdf', "
        f"'application/pdf', 1024, '\\x{sha}', now(), '{tier}', 'svc-files')")


def deliver(dispatch_id: str, tenant: str) -> dict:
    """svc-workflow giao trong phiên của đơn vị nhận: Actor("svc-workflow", <đơn vị nhận>, "service")."""
    return Service("svc-workflow", "service", tenant).gql(DELIVER, {"id": dispatch_id})["office_deliver_dispatch"][0]


def count(statement: str) -> int:
    return int(sql(statement)[0][0])


# --- đơn vị nhận ------------------------------------------------------------------------------------------------


def test_recipients_are_other_units_of_the_system(world, tenant_c):
    doc = draft(world, 9501, [tenant_c, world.tenant_b, world.tenant_b])
    stored = world.staff_a1.gql("query ($id: uuid!) { office_documents_by_pk(id: $id) { recipient_tenant_ids } }",
                                {"id": doc})["office_documents_by_pk"]["recipient_tenant_ids"]
    assert stored == sorted([world.tenant_b, tenant_c])          # bỏ trùng, xếp theo id
    with pytest.raises(GraphQLError, match="documents_recipient_units_other"):
        draft(world, 9502, [world.tenant_a])
    with pytest.raises(GraphQLError, match="documents_recipient_units: có đơn vị nhận không thuộc hệ thống"):
        draft(world, 9502, [str(uuid.uuid4())])
    # văn bản hạn chế không liên thông: tệp mã hóa gắn với đơn vị gửi (F3.7)
    with pytest.raises(GraphQLError, match="documents_restricted_local"):
        draft(world, 9503, [world.tenant_b], restricted=True)
    with pytest.raises(SQLError, match="documents_restricted_local"):     # kể cả ghi thẳng CSDL
        sql(f"update office.documents set restricted = true where id = '{doc}'")
    with pytest.raises(SQLError, match="documents_recipient_units_out"):
        sql("insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, "
            f"summary, recipient_tenant_ids, created_by) values ('{world.tenant_a}', 'in', 'received', 'CV', "
            f"'1/LT{world.tag}', 'UBND', '2026-10-15', 'Văn bản đến có đơn vị nhận', "
            f"array['{world.tenant_b}']::uuid[], 'thu')")


def test_recipients_are_frozen_once_submitted(world, tenant_c):
    doc = draft(world, 9504, [world.tenant_b])

    def change(units: list[str]) -> int:
        body = world.staff_a1.gql(UPDATE_DOC, {"id": doc, "set": {"recipient_tenant_ids": units}})
        return body["update_office_documents"]["affected_rows"]

    assert change([tenant_c]) == 1
    world.service_a.gql(STATUS, {"id": doc, "s": "in_review"})
    assert change([world.tenant_b]) == 0                         # chuyên viên: chỉ sửa dự thảo
    with pytest.raises(SQLError, match="documents_recipient_units: đơn vị nhận chỉ sửa được"):
        sql(f"update office.documents set recipient_tenant_ids = array['{world.tenant_b}']::uuid[] where id = '{doc}'")
    # cùng danh sách (trùng, khác thứ tự) thì không phải sửa
    sql(f"update office.documents set recipient_tenant_ids = array['{tenant_c}', '{tenant_c}']::uuid[] "
        f"where id = '{doc}'")
    world.service_a.gql(STATUS, {"id": doc, "s": "returned"})    # bị trả lại: sửa được như dự thảo
    assert change([world.tenant_b, tenant_c]) == 1


def test_unit_list_leaves_out_own_unit(world, tenant_c):
    query = "{ office_dispatch_units(order_by: {name: asc}) { id code name parent_name } }"

    def ids(user: User) -> set[str]:
        return {u["id"] for u in user.gql(query)["office_dispatch_units"]}

    # quản trị đơn vị không soạn văn bản nhưng đọc tên đơn vị nhận trong Sổ kiểm toán
    for user in (world.clerk_a, world.staff_a1, world.manager_a1, world.director_a, world.service_a, world.admin_a):
        seen = ids(user)
        assert world.tenant_a not in seen and {world.tenant_b, tenant_c} <= seen, user.role
    seen = ids(world.clerk_b)
    assert world.tenant_b not in seen and world.tenant_a in seen


# --- hộp thư đi --------------------------------------------------------------------------------------------------


def test_issuing_queues_one_delivery_per_unit_once(world, tenant_c):
    doc = issued(world, 9505, [world.tenant_b, tenant_c])
    queued = rows(doc)
    code, sha = sql(f"select verify_code, encode(content_sha256, 'hex') from office.documents where id = '{doc}'")[0]
    assert [r["to_tenant_id"] for r in queued] == sorted([world.tenant_b, tenant_c])
    for r in queued:
        assert (r["tenant_id"], r["status"], r["incoming_document_id"], r["attempts"]) == (
            world.tenant_a, "pending", "NULL", "0")
        assert (r["source_verify_code"], r["sha"]) == (code, sha)    # chụp lúc phát hành
    assert len({r["file_id"] for r in queued}) == 2                  # mỗi đơn vị một bản sao tệp, id định trước
    # đổi trạng thái về sau, kể cả đưa về rồi phát hành lại bằng quyền quản trị, không thêm dòng nào
    sql(f"update office.documents set status = 'approved' where id = '{doc}'")
    sql(f"update office.documents set status = 'issued' where id = '{doc}'")
    sql(f"update office.documents set is_public = true where id = '{doc}'")
    assert rows(doc) == queued
    assert rows(issued(world, 9506, [])) == []                       # không chọn đơn vị nhận: không gửi


def test_delivery_creates_one_incoming_document(world):
    # trích yếu văn bản đi không theo ràng buộc của văn bản đến (ký tự vô hình, tab): văn bản đến được làm sạch
    doc = issued(world, 9507, [world.tenant_b], summary="Thông báo​ lịch họp giao ban\tliên thông (thử 9507)  ")
    [row] = rows(doc)
    copy_file(row)
    got = deliver(row["id"], world.tenant_b)
    assert got["status"] == "delivered" and got["last_error"] is None and got["delivered_at"]
    incoming = got["incoming_document_id"]

    symbol, issued_on, type_code, urgency = sql(
        f"select symbol, issued_on::text, type_code, urgency from office.documents where id = '{doc}'")[0]
    fields = sql("select tenant_id, direction, status, symbol, issuer_name, issued_on::text, type_code, urgency, "
                 "summary, source_id, created_by, register_number is null from office.documents "
                 f"where id = '{incoming}'")
    assert fields == [[world.tenant_b, "in", "received", symbol, "Đơn vị thử A", issued_on, type_code, urgency,
                       "Thông báo lịch họp giao ban liên thông (thử 9507)", doc, "svc-workflow", "t"]]
    assert sql(f"select tenant_id, file_id, role from office.document_files where document_id = '{incoming}'") == [
        [world.tenant_b, row["file_id"], "main"]]

    def events(document_id: str) -> list[tuple[str, str, str, dict]]:
        found = sql(f"select kind, actor_id, actor_kind, data::text from office.document_events "
                    f"where document_id = '{document_id}' and kind <> 'office.document.numbered' order by id")
        return [(k, a, ak, json.loads(d)) for k, a, ak, d in found]

    assert events(incoming) == [("office.document.arrived", "svc-workflow", "service", {
        "dispatch_id": row["id"], "from_tenant_id": world.tenant_a, "from_name": "Đơn vị thử A",
        "verify_code": row["source_verify_code"]})]
    assert events(doc) == [("office.document.dispatched", "svc-workflow", "service", {
        "dispatch_id": row["id"], "to_tenant_id": world.tenant_b, "to_name": "Đơn vị thử B"})]

    # gọi lại (vòng đối soát, bản sao dịch vụ khác): trả nguyên dòng, không thêm gì
    assert deliver(row["id"], world.tenant_b) == got
    assert count(f"select count(*) from office.documents where source_id = '{doc}'") == 1
    assert len(events(incoming)) == len(events(doc)) == 1
    # chốt cuối ở CSDL: mỗi văn bản gửi một văn bản đến ở mỗi đơn vị, kể cả bản đã hủy
    with pytest.raises(SQLError, match="documents_source_once"):
        sql("insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, "
            f"summary, source_id, created_by) values ('{world.tenant_b}', 'in', 'cancelled', 'TB', '2/LT{world.tag}', "
            f"'Đơn vị khác', '2026-10-15', 'Bản thứ hai của cùng văn bản gửi', '{doc}', 'thu')")


def test_only_the_receiving_unit_delivers(world, tenant_c):
    doc = issued(world, 9508, [world.tenant_b])
    [row] = rows(doc)
    copy_file(row)
    for tenant in (world.tenant_a, tenant_c):                       # bên gửi, đơn vị ngoài cuộc
        with pytest.raises(GraphQLError, match="không có lượt gửi liên thông"):
            deliver(row["id"], tenant)
    assert rows(doc) == [row]


def test_delivery_waits_for_the_file_copy(world):
    doc = issued(world, 9509, [world.tenant_b])
    [row] = rows(doc)
    with pytest.raises(GraphQLError, match="foreign key"):          # svc-files chưa chép tệp sang đơn vị nhận
        deliver(row["id"], world.tenant_b)
    assert rows(doc) == [row]                                        # vẫn chờ, lượt sau giao lại
    assert count(f"select count(*) from office.documents where source_id = '{doc}'") == 0
    copy_file(row)
    assert deliver(row["id"], world.tenant_b)["status"] == "delivered"


def test_rule_violation_marks_the_delivery_failed(world):
    doc = issued(world, 9510, [world.tenant_b])
    [row] = rows(doc)
    copy_file(row, tier="cold")                     # tệp không gắn được: trigger document_files_hot_only
    got = deliver(row["id"], world.tenant_b)
    assert got["status"] == "failed" and got["incoming_document_id"] is None and "kho lạnh" in got["last_error"]
    assert count(f"select count(*) from office.documents where source_id = '{doc}'") == 0
    assert count(f"select count(*) from office.document_events where document_id = '{doc}' "
                 "and kind like 'office.document.dispatch%'") == 0
    assert deliver(row["id"], world.tenant_b) == got                 # lỗi cố định: không thử lại
    sql(f"update office.documents set status = 'archived' where id = '{doc}'")   # không còn chờ: nộp lưu được


def test_copy_with_another_hash_marks_the_delivery_failed(world):
    doc = issued(world, 9516, [world.tenant_b])
    [row] = rows(doc)
    copy_file(row, sha=uuid.uuid4().hex * 2)        # svc-files đã kiểm băm; đây là lớp kiểm thứ hai trong CSDL
    got = deliver(row["id"], world.tenant_b)
    assert (got["status"], got["incoming_document_id"]) == ("failed", None)
    assert got["last_error"] == "tệp chép sang đơn vị nhận không khớp băm bản phát hành"
    assert count(f"select count(*) from office.documents where source_id = '{doc}'") == 0
    assert deliver(row["id"], world.tenant_b) == got


def test_unit_that_already_has_it_gets_a_link_not_a_copy(world):
    doc = issued(world, 9511, [world.tenant_b])
    [row] = rows(doc)
    symbol, issued_on = sql(f"select symbol, issued_on::text from office.documents where id = '{doc}'")[0]
    # văn thư B đã tiếp nhận tay từ bản giấy, gõ tên đơn vị gửi khác hoa thường
    manual = received(world.clerk_b, {"type_code": "TB", "symbol": symbol, "issuer_name": "đơn vị thử a",
                                       "issued_on": issued_on, "summary": "Văn bản tiếp nhận từ bản giấy"})["id"]
    got = deliver(row["id"], world.tenant_b)
    assert (got["status"], got["incoming_document_id"]) == ("duplicate", manual)
    assert count(f"select count(*) from office.documents where source_id = '{doc}'") == 0
    assert sql(f"select kind, data->>'to_tenant_id' from office.document_events where document_id = '{doc}' "
               "and kind like 'office.document.dispatch%'") == [["office.document.dispatch_duplicate", world.tenant_b]]
    assert deliver(row["id"], world.tenant_b) == got


# --- ai thấy gì -------------------------------------------------------------------------------------------------


def test_each_side_sees_its_own_half(world, tenant_c):
    doc = issued(world, 9512, [world.tenant_b])
    [row] = rows(doc)
    director_b = User(f"truong-khoa-b-{world.tag}", "director", world.tenant_b)
    clerk_c = User(f"van-thu-c-{world.tag}", "clerk", tenant_c)

    def seen(user: User) -> list[dict]:
        return user.gql(ONE, {"id": row["id"]})["office_dispatches"]

    # còn chờ giao: bên gửi thấy, bên nhận chưa có văn bản nên chưa thấy gì
    assert [r["status"] for r in seen(world.clerk_a)] == ["pending"]
    assert seen(world.clerk_b) == []
    copy_file(row)
    incoming = deliver(row["id"], world.tenant_b)["incoming_document_id"]

    for user in (world.clerk_a, world.director_a, world.staff_a1):  # đọc được văn bản đi
        [mine] = seen(user)
        assert (mine["to_unit"], mine["from_unit"]) == ({"name": "Đơn vị thử B"}, None), user.role
        assert (mine["document"], mine["incoming"]) == ({"id": doc}, None)   # văn bản bên nhận vẫn cách ly
    assert seen(world.staff_a2) == []                                # phòng khác không đọc được văn bản đi
    for user in (world.clerk_b, director_b):
        [theirs] = seen(user)
        assert (theirs["from_unit"], theirs["to_unit"]) == ({"name": "Đơn vị thử A"}, None), user.role
        assert (theirs["incoming"], theirs["document"]) == ({"id": incoming}, None)
        ids = visible_ids(user)
        assert incoming in ids and doc not in ids
    ids = visible_ids(clerk_c)
    assert seen(clerk_c) == [] and incoming not in ids and doc not in ids

    # đúng các trường giao diện chọn: thẻ "Liên thông" ở văn bản đi, thẻ "Nhận từ …" ở văn bản đến
    sent = world.clerk_a.gql("""query ($d: uuid!) { office_documents_by_pk(id: $d) {
      recipient_tenant_ids dispatches(order_by: {created_at: asc}) { status to_unit { name } } } }""",
                             {"d": doc})["office_documents_by_pk"]
    assert sent == {"recipient_tenant_ids": [world.tenant_b],
                    "dispatches": [{"status": "delivered", "to_unit": {"name": "Đơn vị thử B"}}]}
    got = world.clerk_b.gql("""query ($d: uuid!) { office_documents_by_pk(id: $d) {
      source_id source { id } dispatch_in { source_verify_code source_sha256 from_unit { name } } } }""",
                            {"d": incoming})["office_documents_by_pk"]
    assert (got["source_id"], got["source"]) == (doc, None)
    assert got["dispatch_in"] == {"source_verify_code": row["source_verify_code"], "source_sha256": "\\x" + row["sha"],
                                  "from_unit": {"name": "Đơn vị thử A"}}


@pytest.mark.parametrize("who", ["clerk_a", "director_a", "staff_a1", "clerk_b"])
def test_users_cannot_deliver(world, who):
    body = getattr(world, who).raw(DELIVER, {"id": str(uuid.uuid4())})
    assert "errors" in body and "office_deliver_dispatch" in body["errors"][0]["message"]


def test_service_records_retries_but_not_outcomes(world, tenant_c):
    doc = issued(world, 9513, [world.tenant_b])
    [row] = rows(doc)
    retry = {"id": row["id"], "error": "svc-files 503", "next": "2026-10-21T10:00:00+07:00"}
    for svc in (world.service_a, world.service_b):                  # phiên bên gửi hay bên nhận đều được
        assert svc.gql(RETRY, retry)["update_office_dispatches_by_pk"] == {"id": row["id"]}
    assert Service("svc-workflow", "service", tenant_c).gql(RETRY, retry)["update_office_dispatches_by_pk"] is None
    assert world.service_b.gql(NOTIFIED, {"id": row["id"], "now": "2026-10-21T10:00:00+07:00"})[
        "update_office_dispatches_by_pk"] == {"id": row["id"]}
    assert sql(f"select status, attempts, last_error, notified_at is not null from office.dispatches "
               f"where id = '{row['id']}'") == [["pending", "2", "svc-files 503", "t"]]
    # trạng thái, văn bản đến chỉ đổi qua office_deliver_dispatch; không ai thêm, xóa dòng
    body = world.service_b.raw('mutation ($id: uuid!) { update_office_dispatches_by_pk(pk_columns: {id: $id}, '
                               '_set: {status: "delivered"}) { id } }', {"id": row["id"]})
    assert "errors" in body and "status" in body["errors"][0]["message"]
    for mutation in ("mutation { insert_office_dispatches_one(object: {}) { id } }",
                     "mutation { delete_office_dispatches(where: {}) { affected_rows } }"):
        assert "errors" in world.service_b.raw(mutation)
    for user in (world.clerk_a, world.clerk_b):
        body = user.raw(RETRY, retry)
        assert "errors" in body and "update_office_dispatches_by_pk" in body["errors"][0]["message"]


def test_service_marks_a_lasting_refusal_failed(world, tenant_c):
    doc = issued(world, 9517, [world.tenant_b, tenant_c])
    by = {r["to_tenant_id"]: r for r in rows(doc)}
    to_b, to_c = by[world.tenant_b], by[tenant_c]
    service_c = Service("svc-workflow", "service", tenant_c)
    reason = "Trạm quét mã độc chặn bản phát hành khi chép sang đơn vị nhận"

    def fail(svc: User, dispatch_id: str, why: str = reason) -> list[dict]:
        return svc.gql(FAIL, {"id": dispatch_id, "reason": why})["office_fail_dispatch"]

    assert fail(service_c, to_b["id"]) == []                         # đơn vị ngoài cuộc không đụng được
    assert fail(world.service_a, to_b["id"]) == [{"id": to_b["id"], "status": "failed", "last_error": reason}]
    assert fail(world.service_a, to_b["id"], "lần hai") == []          # đã hỏng: giữ lý do đầu
    assert deliver(to_b["id"], world.tenant_b)["status"] == "failed"  # giao sau đó cũng không tạo văn bản đến
    for user in (world.clerk_a, world.clerk_b, world.admin_a):
        body = user.raw(FAIL, {"id": to_c["id"], "reason": reason})
        assert "errors" in body and "office_fail_dispatch" in body["errors"][0]["message"]
    # vẫn chờ một đơn vị: chưa nộp lưu được
    with pytest.raises(SQLError, match="documents_dispatch_pending"):
        sql(f"update office.documents set status = 'archived' where id = '{doc}'")
    # bên nhận cũng đánh dấu được; lý do rỗng thành câu chung
    assert fail(service_c, to_c["id"], "  ") == [{"id": to_c["id"], "status": "failed",
                                                   "last_error": "không chuyển được"}]
    assert [(r["status"], r["incoming_document_id"]) for r in rows(doc)] == [("failed", "NULL")] * 2
    assert count(f"select count(*) from office.documents where source_id = '{doc}'") == 0
    sql(f"update office.documents set status = 'archived' where id = '{doc}'")    # không còn chờ: nộp lưu được

    # dòng đã giao giữ nguyên
    other = issued(world, 9518, [world.tenant_b])
    [row] = rows(other)
    copy_file(row)
    assert deliver(row["id"], world.tenant_b)["status"] == "delivered"
    assert fail(world.service_b, row["id"]) == []
    assert rows(other)[0]["status"] == "delivered"


# --- sổ kiểm toán, nộp lưu ---------------------------------------------------------------------------------------


def test_both_ledgers_record_the_delivery(world):
    doc = issued(world, 9514, [world.tenant_b])
    [row] = rows(doc)
    copy_file(row)
    incoming = deliver(row["id"], world.tenant_b)["incoming_document_id"]

    def ledger(entity: str, entity_id: str) -> list[list[str]]:
        return sql(f"select tenant_id, action, actor_id, actor_kind from core.audit_log "
                   f"where entity = '{entity}' and entity_id = '{entity_id}' order by id")

    assert ledger("office.dispatches", row["id"]) == [
        [world.tenant_a, "insert", world.clerk_a.sub, "service"],    # trong giao dịch phát hành
        [world.tenant_a, "update", "svc-workflow", "service"]]       # lần giao, chạy trong phiên của đơn vị nhận
    assert ledger("office.documents", incoming) == [[world.tenant_b, "insert", "svc-workflow", "service"]]
    assert ledger("office.document_files", f"{incoming}/{row['file_id']}") == [
        [world.tenant_b, "insert", "svc-workflow", "service"]]
    assert sql("select audit_id, problem from core.audit_verify()") == []

    # tab Lịch sử của văn bản đi có các lần gửi: id, trạng thái thấy được, băm vẫn ẩn
    sent = [r for r in world.staff_a1.gql(HISTORY, {"d": doc})["office_document_history"]
            if r["entity"] == "office.dispatches"]
    assert [r["action"] for r in sent] == ["insert", "update"]
    assert sent[0]["overview"]["to_tenant_id"] == [None, world.tenant_b]
    assert "source_sha256" in sent[0]["overview"] and sent[0]["overview"]["source_sha256"] is None
    assert sent[1]["overview"]["status"] == ["pending", "delivered"]
    assert sent[1]["overview"]["incoming_document_id"] == [None, incoming]
    # bên nhận chỉ có dòng trong sổ của mình: văn bản đến (kèm văn bản gửi), tệp
    theirs = world.clerk_b.gql(HISTORY, {"d": incoming})["office_document_history"]
    assert [(r["action"], r["entity"]) for r in theirs] == [("insert", "office.documents"),
                                                            ("insert", "office.document_files")]
    assert theirs[0]["overview"]["source_id"] == [None, doc]


def test_archiving_waits_for_pending_delivery(world):
    doc = issued(world, 9515, [world.tenant_b])
    [row] = rows(doc)
    with pytest.raises(SQLError, match="documents_dispatch_pending"):
        sql(f"update office.documents set status = 'archived' where id = '{doc}'")
    copy_file(row)
    deliver(row["id"], world.tenant_b)
    sql(f"update office.documents set status = 'archived' where id = '{doc}'")
    assert sql(f"select status from office.documents where id = '{doc}'") == [["archived"]]
