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

"""Ràng buộc trong CSDL — lớp Poka-yoke cuối, đúng cả khi lớp quyền phía trên có lỗi.

Các câu lệnh chạy bằng quyền quản trị (bỏ qua mọi quyền Hasura) để chứng minh chính CSDL chặn.
"""

from __future__ import annotations

import uuid

import pytest
from conftest import SQLError, sql

SHA = "'\\x" + "ab" * 32 + "'::bytea"


def doc_sql(tenant: str, **cols) -> str:
    values = {
        "tenant_id": tenant, "direction": "in", "status": "received", "type_code": "CV",
        "symbol": f"{uuid.uuid4().hex[:6]}/SGD-VP", "issuer_name": "Sở Giáo dục và Đào tạo",
        "issued_on": "2026-10-10", "summary": "Về việc báo cáo số liệu đầu năm học", "created_by": "test",
    }
    values.update(cols)
    names = ", ".join(values)
    literals = ", ".join("null" if v is None else str(v) if isinstance(v, bool) else f"'{v}'" for v in values.values())
    return f"insert into office.documents ({names}) values ({literals}) returning id"


def test_document_types_seeded_from_nd30():
    rows = dict((code, (name, flag)) for code, name, flag in sql("select code, name, in_symbol::text from office.document_types"))
    assert len(rows) == 28
    assert rows["CV"] == ("Công văn", "false")
    assert rows["QĐ"] == ("Quyết định", "true")
    assert rows["TTr"] == ("Tờ trình", "true")


def test_object_key_must_live_under_own_tenant(world):
    fid = uuid.uuid4()
    with pytest.raises(SQLError, match="files_object_key_tenant"):
        sql(f"""insert into core.files (id, tenant_id, object_key, filename, mime_type, size_bytes, sha256, scanned_at, created_by)
                values ('{fid}', '{world.tenant_a}', 'tenant/{world.tenant_b}/2026/10/{fid}', 'a.pdf',
                        'application/pdf', 1, {SHA}, now(), 'test')""")


def test_sha256_must_be_32_bytes(world):
    fid = uuid.uuid4()
    with pytest.raises(SQLError, match="sha256"):
        sql(f"""insert into core.files (id, tenant_id, object_key, filename, mime_type, size_bytes, sha256, scanned_at, created_by)
                values ('{fid}', '{world.tenant_a}', 'tenant/{world.tenant_a}/2026/10/{fid}', 'a.pdf',
                        'application/pdf', 1, '\\xabcd'::bytea, now(), 'test')""")


def test_incoming_needs_symbol_issuer_and_date(world):
    with pytest.raises(SQLError, match="documents_in_identity"):
        sql(doc_sql(world.tenant_a, symbol=None))


def test_summary_length_is_checked(world):
    with pytest.raises(SQLError, match="summary"):
        sql(doc_sql(world.tenant_a, summary="Ngắn"))


def test_duplicate_incoming_is_blocked_until_cancelled(world):
    symbol = f"{uuid.uuid4().hex[:6]}/BGDĐT-GDĐH"
    first = sql(doc_sql(world.tenant_a, symbol=symbol, issuer_name="Bộ Giáo dục và Đào tạo"))[0][0]
    with pytest.raises(SQLError, match="documents_in_dedup"):
        sql(doc_sql(world.tenant_a, symbol=symbol, issuer_name="bộ giáo dục và đào tạo"))  # khác hoa thường vẫn trùng
    sql(f"update office.documents set status = 'cancelled' where id = '{first}'")
    sql(doc_sql(world.tenant_a, symbol=symbol, issuer_name="Bộ Giáo dục và Đào tạo"))
    # thuê ước khác nhận cùng văn bản là chuyện bình thường
    sql(doc_sql(world.tenant_b, symbol=symbol, issuer_name="Bộ Giáo dục và Đào tạo"))


def test_cannot_point_to_department_of_other_tenant(world):
    with pytest.raises(SQLError, match="foreign key"):
        sql(doc_sql(world.tenant_a, direction="out", status="draft", symbol=None, issuer_name=None, issued_on=None,
                    department_id=world.dept_b1))


def test_incoming_cannot_use_outgoing_register(world):
    # năm 2099: sổ đi của năm nay do test cấp số văn bản đi tạo
    reg = sql(f"insert into office.registers (tenant_id, direction, year) values ('{world.tenant_a}', 'out', 2099) returning id")[0][0]
    with pytest.raises(SQLError, match="foreign key"):
        sql(doc_sql(world.tenant_a, status="registered", register_id=reg, register_number=1,
                    registered_at="2026-10-18T08:00:00+07:00"))


def test_registered_incoming_needs_register_number(world):
    with pytest.raises(SQLError, match="documents_in_registered"):
        sql(doc_sql(world.tenant_a, status="registered"))


def test_issued_outgoing_needs_hash_and_verify_code(world):
    with pytest.raises(SQLError, match="documents_out_issued_complete"):
        sql(doc_sql(world.tenant_a, direction="out", status="issued", symbol="15/TB-ĐHCN", issuer_name=None,
                    department_id=world.dept_a1, signer_id="hieu-truong"))


def test_status_must_match_direction(world):
    with pytest.raises(SQLError, match="documents_status_by_direction"):
        sql(doc_sql(world.tenant_a, direction="out", status="received"))   # trạng thái của văn bản đến


def test_cannot_attach_file_of_other_tenant(world):
    fid = uuid.uuid4()
    sql(f"""insert into core.files (id, tenant_id, object_key, filename, mime_type, size_bytes, sha256, scanned_at, created_by)
            values ('{fid}', '{world.tenant_b}', 'tenant/{world.tenant_b}/2026/10/{fid}', 'b.pdf',
                    'application/pdf', 1, {SHA}, now(), 'test')""")
    doc = sql(doc_sql(world.tenant_a))[0][0]
    with pytest.raises(SQLError, match="foreign key"):
        sql(f"""insert into office.document_files (tenant_id, document_id, file_id, role, added_by)
                values ('{world.tenant_a}', '{doc}', '{fid}', 'main', 'test')""")


def test_one_lead_per_document(world):
    doc = sql(doc_sql(world.tenant_a))[0][0]
    lead = f"""insert into office.assignments (tenant_id, document_id, department_id, role, assigned_by)
               values ('{world.tenant_a}', '{doc}', '{world.dept_a1}', 'lead', 'test')"""
    sql(lead)
    with pytest.raises(SQLError, match="assignments_one_lead"):
        sql(lead)


def test_updated_at_moves_on_update(world):
    doc = sql(doc_sql(world.tenant_a))[0][0]
    sql(f"update office.documents set urgency = 'khan' where id = '{doc}'")
    assert sql(f"select (updated_at > created_at)::text from office.documents where id = '{doc}'") == [["true"]]


def test_tenant_code_rejects_separator_characters():
    with pytest.raises(SQLError, match="tenants_code_check"):
        sql("insert into core.tenants (code, name) values ('ĐH-CN', 'Không hợp lệ')")
