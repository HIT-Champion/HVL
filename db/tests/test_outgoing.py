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

"""Văn bản đi: nội dung dự thảo, cấp số đi (office.number_outgoing), phát hành và khung nhìn của cổng xác thực."""

from __future__ import annotations

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from conftest import ADMIN_SECRET, INSERT_DOC, GraphQLError, Service, gql_raw, outgoing, received, sql

NUMBER = """
mutation ($id: uuid!, $code: String!) {
  office_number_outgoing(args: {document_id: $id, verify_code: $code}) {
    id status register_number symbol issued_on verify_code
  }
}"""

ISSUE = """
mutation ($id: uuid!, $sha: bytea!, $public: Boolean!, $file: office_document_files_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $id}, _set: {status: "issued", content_sha256: $sha, is_public: $public}) {
    id status
  }
  insert_office_document_files_one(object: $file) { file_id }
}"""

VERIFY = """
query ($where: office_issued_documents_bool_exp!) {
  office_issued_documents(where: $where) {
    verify_code content_sha256 symbol issued_on type_code type_name issuer_name parent_name summary status
  }
}"""

BODY = "Khoa thông báo lịch họp giao ban tháng 11.\n\nĐề nghị các bộ môn cử đại diện tham dự đầy đủ."


def code(n: int) -> str:
    """Mã tra cứu đúng dạng: 10 ký tự base32."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    raw = uuid.uuid4().int + n
    return "".join(alphabet[(raw >> (5 * i)) & 31] for i in range(10))


def verifier(where: dict) -> list[dict]:
    body = gql_raw(VERIFY, {"where": where}, headers={"X-Hasura-Admin-Secret": ADMIN_SECRET, "X-Hasura-Role": "verifier"})
    assert "errors" not in body, body
    return body["data"]["office_issued_documents"]


def draft(world, n: int, **overrides) -> str:
    doc = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(n, body=BODY, recipients=["Các bộ môn"], **overrides)})
    return doc["insert_office_documents_one"]["id"]


def approve(world, doc_id: str) -> None:
    """Phần svc-workflow làm khi trình và duyệt đủ cấp: người ký, trạng thái."""
    world.service_a.gql(
        """mutation ($id: uuid!, $signer: String!) {
          update_office_documents_by_pk(pk_columns: {id: $id}, _set: {status: "approved", signer_id: $signer}) { id }
        }""",
        {"id": doc_id, "signer": world.director_a.sub},
    )


def as_clerk(world) -> Service:
    return Service(world.clerk_a.sub, "service", world.tenant_a)


def number(world, doc_id: str, n: int = 0) -> dict:
    return as_clerk(world).gql(NUMBER, {"id": doc_id, "code": code(n)})["office_number_outgoing"][0]


def issue(world, doc_id: str, content: bytes, *, public: bool) -> str:
    """Phần svc-workflow làm sau khi svc-files dựng PDF: tệp phát hành, băm, trạng thái issued."""
    file_id = sql(
        f"insert into core.files (tenant_id, object_key, filename, mime_type, size_bytes, sha256, scanned_at, created_by) "
        f"select '{world.tenant_a}', 'tenant/{world.tenant_a}/2026/10/' || gen_random_uuid(), 'van-ban.pdf', "
        f"'application/pdf', {len(content)}, '\\x{hashlib.sha256(content).hexdigest()}', now(), 'svc-files' returning id"
    )[0][0]
    as_clerk(world).gql(ISSUE, {
        "id": doc_id, "sha": "\\x" + hashlib.sha256(content).hexdigest(), "public": public,
        "file": {"document_id": doc_id, "file_id": file_id, "role": "issued", "added_by": world.clerk_a.sub},
    })
    return hashlib.sha256(content).hexdigest()


def test_staff_writes_body_only_while_draft(world):
    doc = draft(world, 9301)
    world.staff_a1.gql("mutation ($id: uuid!, $b: String!) { update_office_documents_by_pk(pk_columns: {id: $id}, "
                       "_set: {body: $b}) { id } }", {"id": doc, "b": BODY + "\n\nTrân trọng."})
    approve(world, doc)
    changed = world.staff_a1.gql(
        "mutation ($id: uuid!) { update_office_documents(where: {id: {_eq: $id}}, _set: {body: \"sửa sau khi duyệt\"}) "
        "{ affected_rows } }", {"id": doc})
    assert changed["update_office_documents"]["affected_rows"] == 0
    assert sql(f"select body like '%Trân trọng.' from office.documents where id = '{doc}'") == [["t"]]


def test_incoming_documents_have_no_body(world):
    with pytest.raises(GraphQLError, match="documents_body_only_out"):
        received(world.clerk_a, {"type_code": "CV", "symbol": "1/X", "issuer_name": "UBND", "issued_on": "2026-10-15",
                                 "summary": "Văn bản đến có nội dung", "body": "không được"})
    with pytest.raises(Exception, match="documents_body_only_out"):
        sql(f"insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, "
            f"summary, body, created_by) values ('{world.tenant_a}', 'in', 'received', 'CV', '1/Y', 'UBND', "
            f"'2026-10-15', 'Văn bản đến có nội dung', 'x', 'thu')")


def test_numbers_are_consecutive_and_symbols_follow_decree_30(world):
    notice, letter = draft(world, 9302), draft(world, 9303, type_code="CV", summary="V/v cử cán bộ dự tập huấn")
    for d in (notice, letter):
        approve(world, d)
    first, second = number(world, notice, 1), number(world, letter, 2)

    assert second["register_number"] == first["register_number"] + 1
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    assert first["issued_on"] == today and first["status"] == "approved"
    # văn bản có tên loại: số/tên loại-đơn vị; công văn: số/đơn vị-phòng soạn thảo; số < 10 có số 0 ở trước
    n1, n2 = first["register_number"], second["register_number"]
    assert first["symbol"] == f"{n1:02d}/TB-A{world.tag}"
    assert second["symbol"] == f"{n2:02d}/A{world.tag}-ĐT"

    events = sql(f"select kind, actor_id, data->>'symbol' from office.document_events where document_id = '{notice}'")
    assert events == [["office.document.numbered", world.clerk_a.sub, first["symbol"]]]
    registers = sql(f"select direction, last_number from office.registers where tenant_id = '{world.tenant_a}' "
                    f"and direction = 'out'")
    assert registers == [["out", str(n2)]]


def test_numbering_twice_keeps_the_first_number_and_code(world):
    doc = draft(world, 9304)
    approve(world, doc)
    first, again = number(world, doc, 3), number(world, doc, 4)
    assert (again["register_number"], again["symbol"], again["verify_code"]) == \
           (first["register_number"], first["symbol"], first["verify_code"])
    assert sql(f"select count(*) from office.document_events where document_id = '{doc}'") == [["1"]]


def test_parallel_numbering_gets_distinct_consecutive_numbers(world):
    docs = [draft(world, 9310 + i) for i in range(8)]
    for d in docs:
        approve(world, d)
    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = sorted(r["register_number"] for r in pool.map(lambda p: number(world, p[1], p[0]), enumerate(docs)))
    assert numbers == list(range(numbers[0], numbers[0] + 8))


def test_only_approved_outgoing_documents_get_a_number(world):
    doc = draft(world, 9305)
    with pytest.raises(GraphQLError, match="chưa được cấp số"):
        number(world, doc)
    incoming = received(world.clerk_a, {"type_code": "CV", "symbol": f"9/UBND{world.tag}", "issuer_name": "UBND",
                                        "issued_on": "2026-10-15", "summary": "Văn bản đến không cấp số đi"})
    with pytest.raises(GraphQLError, match="chỉ văn bản đi"):
        number(world, incoming["id"])


def test_other_tenant_cannot_number(world):
    doc = draft(world, 9306)
    approve(world, doc)
    with pytest.raises(GraphQLError, match="không có văn bản"):
        world.service_b.gql(NUMBER, {"id": doc, "code": code(5)})
    assert sql(f"select register_number is null from office.documents where id = '{doc}'") == [["t"]]


@pytest.mark.parametrize("who", ["clerk_a", "director_a", "staff_a1"])
def test_users_cannot_number_directly(world, who):
    body = getattr(world, who).raw(NUMBER, {"id": str(uuid.uuid4()), "code": code(6)})
    assert "errors" in body and "office_number_outgoing" in body["errors"][0]["message"]


def test_issued_document_must_carry_hash_and_number(world):
    doc = draft(world, 9307)
    approve(world, doc)
    with pytest.raises(GraphQLError, match="documents_out_issued_complete"):
        world.service_a.gql('mutation ($id: uuid!) { update_office_documents_by_pk(pk_columns: {id: $id}, '
                            '_set: {status: "issued"}) { id } }', {"id": doc})


def test_verifier_finds_one_issued_document_by_code_or_hash(world):
    doc = draft(world, 9308, summary="Thông báo tuyển sinh thạc sĩ đợt 2 năm 2026")
    approve(world, doc)
    numbered = number(world, doc, 7)
    # đã có số, mã nhưng chưa phát hành: cổng xác thực chưa thấy
    assert verifier({"verify_code": {"_eq": numbered["verify_code"]}}) == []

    sha = issue(world, doc, f"PDF thử {world.tag}".encode(), public=False)
    by_code = verifier({"verify_code": {"_eq": numbered["verify_code"]}})
    by_hash = verifier({"content_sha256": {"_eq": "\\x" + sha}})
    assert by_code == by_hash and len(by_code) == 1
    found = by_code[0]
    assert found["symbol"] == numbered["symbol"] and found["status"] == "issued"
    assert found["issuer_name"] == "Đơn vị thử A" and found["type_name"] == "Thông báo"
    assert found["content_sha256"] == "\\x" + sha
    assert found["summary"] is None, "trích yếu chỉ hiện khi văn bản được đánh dấu công khai"

    world.service_a.gql('mutation ($id: uuid!) { update_office_documents_by_pk(pk_columns: {id: $id}, '
                        '_set: {is_public: true}) { id } }', {"id": doc})
    assert verifier({"verify_code": {"_eq": numbered["verify_code"]}})[0]["summary"].startswith("Thông báo tuyển sinh")


def test_verifier_cannot_list_or_read_anything_else(world):
    assert len(verifier({})) <= 1
    body = gql_raw("{ office_documents { id } }", headers={"X-Hasura-Admin-Secret": ADMIN_SECRET,
                                                           "X-Hasura-Role": "verifier"})
    assert "errors" in body


@pytest.mark.parametrize("who", ["clerk_a", "director_a", "staff_a1", "admin_a"])
def test_users_do_not_see_the_verification_view(world, who):
    body = getattr(world, who).raw("{ office_issued_documents { verify_code } }")
    assert "errors" in body and "office_issued_documents" in body["errors"][0]["message"]


def test_tenant_admin_edits_letterhead_but_no_one_else_does(world):
    update = """mutation ($id: uuid!) { update_core_tenants_by_pk(pk_columns: {id: $id},
                _set: {parent_name: "Trường Đại học Thử", place_name: "Hà Nội", head_title: "Trưởng khoa"}) { id } }"""
    world.admin_a.gql(update, {"id": world.tenant_a})
    row = world.staff_a1.gql("query ($id: uuid!) { core_tenants_by_pk(id: $id) { parent_name place_name head_title } }",
                             {"id": world.tenant_a})["core_tenants_by_pk"]
    assert row == {"parent_name": "Trường Đại học Thử", "place_name": "Hà Nội", "head_title": "Trưởng khoa"}
    for user in (world.clerk_a, world.director_a):
        assert "errors" in user.raw(update, {"id": world.tenant_a}), user.role
    assert world.admin_a.gql(update, {"id": world.tenant_b})["update_core_tenants_by_pk"] is None
