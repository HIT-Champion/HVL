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

"""Dashboard điều hành (F3.11): bốn khung nhìn chỉ có số đếm, lãnh đạo đơn vị đọc số của đơn vị mình.

Dữ liệu dựng trên một đơn vị riêng (không dùng chung đơn vị A của các test khác), nên số đếm biết trước. Mỗi khung
nhìn có kèm văn bản hạn chế: chúng không được đổi số nào của phép chia, chỉ vào con số tổng theo chiều.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from dataclasses import dataclass

import pytest
from conftest import User, sql

TODAY = "(now() at time zone 'Asia/Ho_Chi_Minh')::date"

COUNTS = "{ office_v_document_counts { tenant_id direction restricted status urgency overdue documents } }"
DEPARTMENTS = "{ office_v_overdue_by_department { tenant_id code in_progress overdue } }"
TIMES = "{ office_v_processing_time { tenant_id month documents total_hours with_due on_time } }"
OUTGOING = "{ office_v_outgoing_by_month(order_by: {month: asc}) { tenant_id month documents } }"


@dataclass(frozen=True)
class Office:
    tenant: str
    director: User


def _q(v: object) -> str:
    return "null" if v is None else "'" + str(v).replace("'", "''") + "'"


def _one(statement: str) -> str:
    return sql(statement)[0][0]


@pytest.fixture(scope="module")
def office() -> Office:
    tag = uuid.uuid4().hex[:6].upper()
    tenant = _one(f"insert into core.tenants (code, name) values ('D{tag}', 'Đơn vị thử dashboard') returning id")
    dept = {code: _one(f"insert into office.departments (tenant_id, code, name) values ('{tenant}', '{code}', "
                       f"'Phòng {code}') returning id") for code in ("ĐT", "KHCN", "TCHC")}
    reg_in = _one(f"insert into office.registers (tenant_id, direction, year) values ('{tenant}', 'in', 2026) returning id")
    reg_out = _one(f"insert into office.registers (tenant_id, direction, year) values ('{tenant}', 'out', 2026) returning id")
    clerk, staff = f"van-thu-{tag}", f"chuyen-vien-tchc-{tag}"
    sql(f"insert into core.users (id, tenant_id, department_id, username, full_name, role) values "
        f"('{staff}', '{tenant}', '{dept['TCHC']}', 'cv{tag}', 'Chuyên viên TCHC', 'staff')")
    number = iter(range(1, 100))

    def incoming(status: str, *, urgency: str = "normal", due: str | None = None, restricted: bool = False,
                 registered: str = "now() - interval '10 days'") -> str:
        n = next(number)
        reg = status != "received"
        return _one(
            "insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, "
            "summary, urgency, restricted, register_id, register_number, registered_at, due_on, created_by) values "
            f"('{tenant}', 'in', '{status}', 'CV', '{n}/UBND-VP', 'UBND tỉnh', '2026-08-20', "
            f"'Văn bản đến thử dashboard số {n}', '{urgency}', {str(restricted).lower()}, "
            f"{_q(reg_in) if reg else 'null'}, {n if reg else 'null'}, {registered if reg else 'null'}, "
            f"{due or 'null'}, '{clerk}') returning id")

    def lead(doc: str, *, department: str | None = None, user: str | None = None) -> None:
        sql(f"insert into office.assignments (tenant_id, document_id, department_id, user_id, role, assigned_by) "
            f"values ('{tenant}', '{doc}', {_q(department)}, {_q(user)}, 'lead', 'lanh-dao')")

    def finished(doc: str, kind: str, at: str) -> None:
        sql(f"insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, created_at) "
            f"values ('{tenant}', '{doc}', '{kind}', 'chuyen-vien', 'user', '{at}')")

    def issued(n: int, on: str, restricted: bool = False) -> None:
        sha = hashlib.sha256(os.urandom(16)).hexdigest()
        code = base64.b32encode(os.urandom(10)).decode()[:10]
        sql("insert into office.documents (tenant_id, direction, status, type_code, symbol, summary, issued_on, "
            "register_id, register_number, content_sha256, verify_code, signer_id, department_id, restricted, "
            f"created_by) values ('{tenant}', 'out', 'issued', 'TB', '{n:02d}/TB-D', 'Thông báo thử dashboard số {n}', "
            f"'{on}', '{reg_out}', {n}, '\\x{sha}', '{code}', 'lanh-dao', '{dept['ĐT']}', {str(restricted).lower()}, "
            "'chuyen-vien')")

    incoming("received")
    incoming("received", due=f"{TODAY} - 1")                                # chưa vào sổ mà đã qua hạn: vẫn quá hạn
    incoming("registered", urgency="khan")
    late = incoming("in_progress", urgency="hoa_toc", due=f"{TODAY} - 3")
    lead(late, department=dept["ĐT"])
    lead(incoming("in_progress", due=f"{TODAY} + 5"), user=staff)          # giao cho người: lấy phòng của người đó
    lead(incoming("in_progress", due=f"{TODAY} + 2"), user=f"chua-dong-bo-{tag}")   # chưa có trong danh bạ
    lead(incoming("in_progress", due=f"{TODAY} - 3", restricted=True), department=dept["ĐT"])
    # xong trong tháng 9: xử lý 3 ngày, đúng hạn; cho lưu sau 1 ngày, quá hạn; xử lý 2 ngày, không có hạn
    done = incoming("done", registered="'2026-09-01 08:00+07'", due="'2026-09-08'")
    finished(done, "office.document.processed", "2026-09-04 08:00+07")
    filed = incoming("done", registered="'2026-09-01 08:00+07'", due="'2026-09-01'")
    finished(filed, "office.document.filed", "2026-09-02 08:00+07")
    no_due = incoming("done", registered="'2026-09-01 08:00+07'")
    finished(no_due, "office.document.processed", "2026-09-03 08:00+07")
    secret = incoming("done", registered="'2026-09-01 08:00+07'", restricted=True)
    finished(secret, "office.document.processed", "2026-09-21 08:00+07")
    issued(1, "2026-09-15")
    issued(2, "2026-10-02")
    issued(3, "2026-10-05", restricted=True)
    sql("insert into office.documents (tenant_id, direction, status, type_code, summary, department_id, created_by) "
        f"values ('{tenant}', 'out', 'draft', 'TB', 'Dự thảo thử dashboard', '{dept['ĐT']}', 'chuyen-vien')")
    return Office(tenant, User(f"lanh-dao-{tag}", "director", tenant))


def test_counts_by_direction_status_urgency(office):
    rows = office.director.gql(COUNTS)["office_v_document_counts"]
    assert {r["tenant_id"] for r in rows} == {office.tenant}
    got = {(r["direction"], r["restricted"], r["status"], r["urgency"], r["overdue"], r["documents"]) for r in rows}
    assert got == {
        ("in", False, "received", "normal", False, 1),
        ("in", False, "received", "normal", True, 1),
        ("in", False, "registered", "khan", False, 1),
        ("in", False, "in_progress", "hoa_toc", True, 1),
        ("in", False, "in_progress", "normal", False, 2),
        ("in", False, "done", "normal", False, 3),
        ("out", False, "issued", "normal", False, 2),
        ("out", False, "draft", "normal", False, 1),
        # văn bản hạn chế: chỉ một con số mỗi chiều, không trạng thái, độ khẩn, quá hạn
        ("in", True, None, None, None, 2),
        ("out", True, None, None, None, 1),
    }


def test_breakdowns_only_count_what_the_director_can_read(office):
    # Mọi số chia đều tính lại được từ văn bản lãnh đạo đọc được: trừ đi không lộ gì về văn bản hạn chế
    data = office.director.gql("""{ office_v_document_counts(where: {restricted: {_eq: false}}) { documents }
        office_documents_aggregate { aggregate { count } } }""")
    assert sum(r["documents"] for r in data["office_v_document_counts"]) == \
        data["office_documents_aggregate"]["aggregate"]["count"] == 12


def test_overdue_by_lead_department_lists_every_department(office):
    rows = office.director.gql(DEPARTMENTS)["office_v_overdue_by_department"]
    assert {r["code"]: (r["in_progress"], r["overdue"]) for r in rows} == {
        "ĐT": (1, 1),          # văn bản hạn chế quá hạn của phòng không được tính
        "KHCN": (0, 0),        # phòng chưa có việc vẫn có dòng
        "TCHC": (1, 0),        # việc giao cho một chuyên viên tính về phòng của người đó
        None: (1, 0),          # người được giao chưa có trong danh bạ: chưa rõ phòng, tổng vẫn đủ
    }


def test_processing_time_from_registration_to_done(office):
    rows = office.director.gql(TIMES)["office_v_processing_time"]
    # 3 + 1 + 2 ngày; đúng hạn tính trong số có hạn
    assert rows == [{"tenant_id": office.tenant, "month": "2026-09-01", "documents": 3, "total_hours": 144.0,
                     "with_due": 2, "on_time": 1}]


def test_outgoing_issued_by_month(office):
    rows = office.director.gql(OUTGOING)["office_v_outgoing_by_month"]
    assert [(r["month"], r["documents"]) for r in rows] == [("2026-09-01", 1), ("2026-10-01", 1)]


def test_only_directors_read_their_own_tenant(world, office):
    for query in (COUNTS, DEPARTMENTS, TIMES, OUTGOING):
        field = query.split()[1].split("(")[0]
        # lãnh đạo đơn vị khác không thấy số của đơn vị này, chỉ thấy đơn vị mình
        assert {r["tenant_id"] for r in world.director_a.gql(query)[field]} <= {world.tenant_a}
        for other in (world.clerk_a, world.manager_a1, world.staff_a1, world.admin_a):
            assert "errors" in other.raw(query), (other.role, field)
