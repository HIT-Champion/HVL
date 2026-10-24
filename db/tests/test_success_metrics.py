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

"""Số đo "sau" của đặc tả §8 (F4.6, migration 1792281602750_success_metrics): office.v_time_to_assign (từ lúc văn bản
đến tới lúc được giao chủ trì, tới tay người xử lý — trung vị, p90) và office.v_overdue_rate (hạn giải quyết so với lúc
xong, kể cả văn bản chưa xong mà đã qua hạn). Mỗi khung nhìn một đơn vị riêng nên số biết trước; có văn bản hạn chế,
văn bản đã hủy, văn bản đi để chắc chúng không vào phép tính; có văn bản đã nộp lưu (dòng thời gian đã gỡ). Dòng month
null tính lại trên mọi văn bản, không cộng từ các tháng. Lúc giao trước lúc đến (nhập tay) tính 0 giờ, văn bản chưa
giao không thành 0 giờ. Cờ sample theo core.tenants.sample_data (đơn vị mới mặc định không phải đơn vị mẫu; seed đặt
cờ cho hai đơn vị mẫu — scripts/tests/test_so_lieu_sau.py kiểm). Chỉ lãnh đạo đơn vị đọc, số của đơn vị mình.

p90 là percentile_cont (nội suy tuyến tính): với [2, 4, 8, 24] giờ, vị trí 0,9 × 3 = 2,7 → 8 + 0,7 × 16 = 19,2."""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass

import pytest
from conftest import User, World, sql

TODAY = "(now() at time zone 'Asia/Ho_Chi_Minh')::date"
ASSIGN = """{ office_v_time_to_assign { tenant_id sample month arrived assigned median_hours p90_hours handled
  handled_median_hours handled_p90_hours waiting } }"""
OVERDUE = "{ office_v_overdue_rate { tenant_id sample month judged on_time late late_open pending } }"


@dataclass(frozen=True)
class Unit:
    tenant: str
    director: User
    rows: dict


def _q(v: object) -> str:
    return "null" if v is None else "'" + str(v).replace("'", "''") + "'"


def _one(statement: str) -> str:
    return sql(statement)[0][0]


class Builder:
    """Dựng văn bản đến bằng quyền quản trị trên một đơn vị mới, mốc thời gian chọn trước."""

    def __init__(self, label: str):
        tag = uuid.uuid4().hex[:6].upper()
        self.tag = tag
        self.tenant = _one(f"insert into core.tenants (code, name) values ('{label}{tag}', 'Đơn vị thử số đo') "
                           f"returning id")
        self.dept = _one(f"insert into office.departments (tenant_id, code, name) values ('{self.tenant}', 'ĐT', "
                         f"'Phòng Đào tạo') returning id")
        self.reg = _one(f"insert into office.registers (tenant_id, direction, year) values ('{self.tenant}', 'in', "
                        f"2026) returning id")
        self.number = itertools.count(1)
        self.director = User(f"lanh-dao-{tag}", "director", self.tenant)

    def incoming(self, status: str, *, created: str = "now() - interval '20 days'", due: str | None = None,
                 restricted: bool = False) -> str:
        n = next(self.number)
        reg = status not in ("received", "cancelled")
        return _one(
            "insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, "
            "summary, restricted, register_id, register_number, registered_at, due_on, created_by, created_at) values "
            f"('{self.tenant}', 'in', '{status}', 'CV', '{n}/SO-DO', 'UBND tỉnh', '2026-08-20', "
            f"'Văn bản đến thử số đo số {n}', {str(restricted).lower()}, {_q(self.reg) if reg else 'null'}, "
            f"{n if reg else 'null'}, {created if reg else 'null'}, {due or 'null'}, 'van-thu', {created}) "
            "returning id")

    def lead(self, doc: str, at: str, *, user: str | None = None, parent: str | None = None,
             status: str = "open") -> str:
        dept = None if user else self.dept
        return _one(
            "insert into office.assignments (tenant_id, document_id, parent_id, department_id, user_id, role, status, "
            f"assigned_by, assigned_at) values ('{self.tenant}', '{doc}', {_q(parent)}, {_q(dept)}, {_q(user)}, "
            f"'lead', '{status}', 'lanh-dao', '{at}') returning id")

    def finished(self, doc: str, kind: str, at: str) -> None:
        sql(f"insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, created_at) "
            f"values ('{self.tenant}', '{doc}', '{kind}', 'chuyen-vien', 'user', '{at}')")


def by_month(rows: list[dict]) -> dict:
    return {r["month"]: r for r in rows}


@pytest.fixture(scope="module")
def assign_unit() -> Unit:
    b = Builder("A")
    # tháng 9: giao chủ trì sau 2, 24, 4, 8 giờ; tới tay người xử lý sau 6, 24, 8 giờ; một văn bản chờ chỉ đạo, một
    # văn bản chờ vào sổ
    a = b.incoming("in_progress", created="'2026-09-01 08:00+07'")
    parent = b.lead(a, "2026-09-01 10:00+07")
    b.lead(a, "2026-09-01 14:00+07", user="chuyen-vien-1", parent=parent)
    bb = b.incoming("in_progress", created="'2026-09-02 08:00+07'")
    b.lead(bb, "2026-09-03 08:00+07", user="chuyen-vien-2")              # giao thẳng cho người: cả hai mốc
    c = b.incoming("in_progress", created="'2026-09-03 08:00+07'")
    b.lead(c, "2026-09-03 12:00+07", status="cancelled")                 # giao rồi hủy: vẫn tính lần giao đầu
    b.lead(c, "2026-09-04 08:00+07")
    b.incoming("registered", created="'2026-09-04 08:00+07'")             # chờ chỉ đạo
    b.incoming("received", created="'2026-09-04 09:00+07'")               # chờ vào sổ
    arch = b.incoming("archived", created="'2026-09-05 10:00+07'")        # đã nộp lưu: không còn dòng thời gian
    b.lead(arch, "2026-09-05 18:00+07", user="chuyen-vien-3")
    secret = b.incoming("in_progress", created="'2026-09-05 08:00+07'", restricted=True)
    b.lead(secret, "2026-09-05 09:00+07")
    b.incoming("cancelled", created="'2026-09-06 08:00+07'")
    # tháng 10: giao sau 1 giờ, tới người xử lý sau 9 giờ; một văn bản lãnh đạo cho lưu, không giao
    g = b.incoming("in_progress", created="'2026-10-01 08:00+07'")
    parent = b.lead(g, "2026-10-01 09:00+07")
    b.lead(g, "2026-10-01 17:00+07", user="chuyen-vien-1", parent=parent)
    filed = b.incoming("done", created="'2026-10-02 08:00+07'")
    b.finished(filed, "office.document.filed", "2026-10-02 09:00+07")
    # văn bản đi không vào số đo văn bản đến
    sql("insert into office.documents (tenant_id, direction, status, type_code, summary, department_id, created_by) "
        f"values ('{b.tenant}', 'out', 'draft', 'TB', 'Dự thảo thử số đo', '{b.dept}', 'chuyen-vien')")
    return Unit(b.tenant, b.director, by_month(b.director.gql(ASSIGN)["office_v_time_to_assign"]))


@pytest.fixture(scope="module")
def overdue_unit() -> Unit:
    b = Builder("Q")
    sept = "'2026-09-01 08:00+07'"
    done = b.incoming("done", created=sept, due="'2026-09-10'")
    b.finished(done, "office.document.processed", "2026-09-08 10:00+07")                # đúng hạn
    edge = b.incoming("done", created=sept, due="'2026-09-10'")
    b.finished(edge, "office.document.processed", "2026-09-11 00:30+07")      # 17:30 UTC ngày 10: vẫn trễ
    filed = b.incoming("done", created=sept, due="'2026-09-05'")
    b.finished(filed, "office.document.filed", "2026-09-06 08:00+07")                   # cho lưu sau hạn: trễ
    b.incoming("done", created=sept, due="'2026-09-20'")                                # xong mà không rõ lúc xong
    archived = b.incoming("archived", created=sept, due="'2026-09-15'")       # nộp lưu: dòng thời gian đã gỡ
    sql(f"insert into office.archived_document_facts (document_id, tenant_id, finished_at) "
        f"values ('{archived}', '{b.tenant}', '2026-09-14 08:00+07')")
    secret = b.incoming("done", created=sept, due="'2026-09-05'", restricted=True)
    b.finished(secret, "office.document.processed", "2026-09-30 08:00+07")
    b.incoming("cancelled", created=sept, due="'2026-09-05'")
    b.incoming("in_progress", due=f"{TODAY} - 3")                                       # chưa xong, đã qua hạn
    b.incoming("in_progress", due=f"{TODAY} + 5")                                       # chưa tới hạn
    b.incoming("registered")                                                            # không có hạn
    return Unit(b.tenant, b.director, by_month(b.director.gql(OVERDUE)["office_v_overdue_rate"]))


def test_time_to_assign_by_arrival_month(assign_unit: Unit) -> None:
    sept, octo = assign_unit.rows["2026-09-01"], assign_unit.rows["2026-10-01"]
    assert (sept["arrived"], sept["assigned"], sept["handled"], sept["waiting"]) == (6, 4, 3, 2)
    # [2, 4, 8, 24] và [6, 8, 24]
    assert sept["median_hours"] == pytest.approx(6.0) and sept["p90_hours"] == pytest.approx(19.2)
    assert sept["handled_median_hours"] == pytest.approx(8.0)
    assert sept["handled_p90_hours"] == pytest.approx(20.8)
    assert (octo["arrived"], octo["assigned"], octo["handled"], octo["waiting"]) == (2, 1, 1, 0)
    assert octo["median_hours"] == pytest.approx(1.0) and octo["handled_median_hours"] == pytest.approx(9.0)


def test_time_to_assign_total_recomputed_over_all_documents(assign_unit: Unit) -> None:
    every = assign_unit.rows[None]
    assert (every["arrived"], every["assigned"], every["handled"], every["waiting"]) == (8, 5, 4, 2)
    # [1, 2, 4, 8, 24]: trung vị 4 — không phải trung bình của hai trung vị tháng (6 và 1)
    assert every["median_hours"] == pytest.approx(4.0) and every["p90_hours"] == pytest.approx(17.6)
    # [6, 8, 9, 24]
    assert every["handled_median_hours"] == pytest.approx(8.5) and every["handled_p90_hours"] == pytest.approx(19.5)
    assert set(assign_unit.rows) == {"2026-09-01", "2026-10-01", None}


def test_overdue_rate_by_due_month(overdue_unit: Unit) -> None:
    sept = overdue_unit.rows["2026-09-01"]
    # đúng hạn: xong trước hạn, nộp lưu trước hạn; trễ: xong sau 0 giờ ngày hạn theo giờ Việt Nam, cho lưu sau hạn
    assert (sept["judged"], sept["on_time"], sept["late"], sept["late_open"], sept["pending"]) == (4, 2, 2, 0, 0)


def test_overdue_rate_counts_open_documents_past_due(overdue_unit: Unit) -> None:
    every = overdue_unit.rows[None]
    assert (every["judged"], every["on_time"], every["late"], every["late_open"], every["pending"]) == (5, 2, 3, 1, 1)
    months = [r for m, r in overdue_unit.rows.items() if m not in (None, "2026-09-01")]
    assert sum(r["late_open"] for r in months) == 1 and sum(r["pending"] for r in months) == 1
    late_month = _one(f"select to_char(date_trunc('month', {TODAY} - 3), 'YYYY-MM-DD')")
    assert overdue_unit.rows[late_month]["late_open"] == 1


def test_sample_flag_follows_the_tenant(assign_unit: Unit, overdue_unit: Unit) -> None:
    assert not any(r["sample"] for r in assign_unit.rows.values())
    sql(f"update core.tenants set sample_data = true where id = '{overdue_unit.tenant}'")
    try:
        rows = overdue_unit.director.gql(OVERDUE)["office_v_overdue_rate"]
        assert rows and all(r["sample"] for r in rows)
    finally:
        sql(f"update core.tenants set sample_data = false where id = '{overdue_unit.tenant}'")


def test_new_tenants_are_not_sample() -> None:
    # CSDL của job db trống, không có hai đơn vị của make seed: seed/tenants.sql đặt cờ được kiểm tĩnh ở
    # scripts/tests/test_so_lieu_sau.py
    tag = uuid.uuid4().hex[:6].upper()
    assert _one(f"insert into core.tenants (code, name) values ('N{tag}', 'Đơn vị thật') returning sample_data") == "f"


def test_assigned_before_arrival_is_zero_and_unassigned_stays_out() -> None:
    """Lúc giao nhập tay trước lúc văn bản đến: 0 giờ, không âm. Văn bản chưa giao không thành 0 giờ (greatest() bỏ
    qua null — khung nhìn dùng case)."""
    b = Builder("Z")
    early = b.incoming("in_progress", created="'2026-09-10 10:00+07'")
    b.lead(early, "2026-09-10 08:00+07", user="chuyen-vien-1")
    b.incoming("registered", created="'2026-09-10 11:00+07'")
    rows = by_month(b.director.gql(ASSIGN)["office_v_time_to_assign"])
    every = rows[None]
    assert (every["arrived"], every["assigned"], every["handled"], every["waiting"]) == (2, 1, 1, 1)
    assert every["median_hours"] == 0 and every["p90_hours"] == 0 and every["handled_median_hours"] == 0


def test_only_directors_read_their_own_tenant(world: World, assign_unit: Unit, overdue_unit: Unit) -> None:
    for query, field, unit in ((ASSIGN, "office_v_time_to_assign", assign_unit),
                               (OVERDUE, "office_v_overdue_rate", overdue_unit)):
        assert {r["tenant_id"] for r in unit.director.gql(query)[field]} == {unit.tenant}
        assert {r["tenant_id"] for r in world.director_a.gql(query)[field]} <= {world.tenant_a}
        for other in (world.clerk_a, world.manager_a1, world.staff_a1, world.admin_a):
            assert "errors" in other.raw(query), (other.role, field)
