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


"""Kiểm chất lượng số liệu báo cáo (F3.9, F3.11): office.report_checks tính trong CSDL lúc truy vấn bộ luật trên các
khung nhìn của trang Điều hành — PASSED / WARNING / FAILED kèm số liệu, của đúng đơn vị trong token, chỉ lãnh đạo đơn vị
đọc. Mỗi ca dựng một đơn vị riêng nên số biết trước. Hai luật chặn hồi quy (status_total, unique_keys) được thử bằng
cách thay tạm khung nhìn bằng bản hỏng rồi khôi phục đúng định nghĩa cũ."""

from __future__ import annotations

import base64
import hashlib
import os
import pathlib
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from conftest import GraphQLError, User, World, sql

CHECKS = "{ office_report_checks { tenant_id rule report status expected actual issues detail } }"
BOARD = {"office.v_document_counts", "office.v_overdue_by_department", "office.v_processing_time",
         "office.v_outgoing_by_month"}
OFFICE = pathlib.Path(__file__).resolve().parents[2] / "apps" / "office" / "app"


def _one(statement: str) -> str:
    return sql(statement)[0][0]


def _q(v: object) -> str:
    return "null" if v is None else "'" + str(v).replace("'", "''") + "'"


class Unit:
    """Một đơn vị thử: phòng, sổ, một chuyên viên có phòng, lãnh đạo đơn vị; thêm văn bản như test_dashboard.py."""

    def __init__(self) -> None:
        tag = uuid.uuid4().hex[:6].upper()
        self.tag = tag
        self.tenant = _one(f"insert into core.tenants (code, name) values ('Q{tag}', 'Đơn vị thử kiểm số liệu') "
                           "returning id")
        self.dept = {code: _one(f"insert into office.departments (tenant_id, code, name) values ('{self.tenant}', "
                                f"'{code}', 'Phòng {code}') returning id") for code in ("ĐT", "TCHC")}
        self.reg_in = _one(f"insert into office.registers (tenant_id, direction, year) values ('{self.tenant}', 'in', "
                           "2026) returning id")
        self.reg_out = _one(f"insert into office.registers (tenant_id, direction, year) values ('{self.tenant}', "
                            "'out', 2026) returning id")
        self.staff = f"chuyen-vien-{tag}"
        sql(f"insert into core.users (id, tenant_id, department_id, username, full_name, role) values "
            f"('{self.staff}', '{self.tenant}', '{self.dept['TCHC']}', 'cv{tag}', 'Chuyên viên TCHC', 'staff')")
        self.director = User(f"lanh-dao-{tag}", "director", self.tenant)
        self.number = iter(range(1, 1000))

    def incoming(self, status: str, *, restricted: bool = False,
                 registered: str = "now() - interval '10 days'") -> str:
        n = next(self.number)
        reg = status not in ("received", "cancelled")
        return _one(
            "insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, "
            "summary, restricted, register_id, register_number, registered_at, created_by) values "
            f"('{self.tenant}', 'in', '{status}', 'CV', '{n}/UBND-VP', 'UBND tỉnh', '2026-06-20', "
            f"'Văn bản đến thử kiểm số liệu số {n}', {str(restricted).lower()}, "
            f"{_q(self.reg_in) if reg else 'null'}, {n if reg else 'null'}, {registered if reg else 'null'}, "
            f"'van-thu') returning id")

    def lead(self, doc: str, *, department: str | None = None, user: str | None = None) -> None:
        sql(f"insert into office.assignments (tenant_id, document_id, department_id, user_id, role, assigned_by) "
            f"values ('{self.tenant}', '{doc}', {_q(department)}, {_q(user)}, 'lead', 'lanh-dao')")

    def finished(self, doc: str, at: str) -> None:
        sql(f"insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, created_at) "
            f"values ('{self.tenant}', '{doc}', 'office.document.processed', 'chuyen-vien', 'user', '{at}')")

    def issued(self, on: str, type_code: str = "TB") -> None:
        n = next(self.number)
        sha = hashlib.sha256(os.urandom(16)).hexdigest()
        code = base64.b32encode(os.urandom(10)).decode()[:10]
        sql("insert into office.documents (tenant_id, direction, status, type_code, symbol, summary, issued_on, "
            "register_id, register_number, content_sha256, verify_code, signer_id, department_id, created_by) values "
            f"('{self.tenant}', 'out', 'issued', '{type_code}', '{n:02d}/{type_code}-Q', "
            f"'Văn bản đi thử kiểm số liệu số {n}', '{on}', '{self.reg_out}', {n}, '\\x{sha}', '{code}', 'lanh-dao', "
            f"'{self.dept['ĐT']}', 'chuyen-vien')")

    def consistent(self) -> Unit:
        """Đủ các trạng thái, mỗi văn bản đang xử lý có phòng chủ trì, mỗi văn bản xong có mốc xong."""
        self.incoming("received")
        self.incoming("registered")
        self.incoming("cancelled")
        self.lead(self.incoming("in_progress"), department=self.dept["ĐT"])
        self.lead(self.incoming("in_progress"), user=self.staff)                 # phòng của người được giao
        self.lead(self.incoming("in_progress", restricted=True), department=self.dept["ĐT"])
        for day in (3, 4):
            self.finished(self.incoming("done", registered="'2026-09-01 08:00+07'"), f"2026-09-0{day} 08:00+07")
        self.finished(self.incoming("done", restricted=True, registered="'2026-09-01 08:00+07'"),
                      "2026-09-05 08:00+07")
        self.issued("2026-09-15")
        self.issued("2026-10-02")
        return self

    def checks(self) -> dict[tuple[str, str], dict]:
        rows = self.director.gql(CHECKS)["office_report_checks"]
        assert {r["tenant_id"] for r in rows} == {self.tenant}
        result = {(r["rule"], r["report"]): r for r in rows}
        assert len(result) == len(rows), "mỗi luật một dòng cho mỗi khung nhìn"
        return result


def _figures(row: dict) -> tuple:
    return row["status"], row["expected"], row["actual"], row["issues"], row["detail"]


@contextmanager
def _replaced(view: str, definition: str) -> Iterator[None]:
    """Thay tạm một khung nhìn (giữ nguyên cột) để giả lập một lần sửa view làm hỏng số, rồi khôi phục đúng bản cũ."""
    old = _one(f"select pg_get_viewdef('{view}'::regclass)")
    sql(f"create or replace view {view} as {definition}")
    try:
        yield
    finally:
        sql(f"create or replace view {view} as {old}")


def test_consistent_unit_passes_every_rule_with_its_figures():
    unit = Unit().consistent()
    checks = unit.checks()
    # 9 văn bản đến: 7 vẽ trên biểu đồ trạng thái + 2 hạn chế (dòng riêng)
    assert _figures(checks["status_total", "office.v_document_counts"]) == ("PASSED", 9, 9, 0, None)
    # 2 văn bản đang xử lý không hạn chế, đều có phòng chủ trì (một qua phòng của người được giao)
    assert _figures(checks["department_total", "office.v_overdue_by_department"]) == ("PASSED", 2, 2, 0, None)
    assert _figures(checks["processing_coverage", "office.v_processing_time"]) == ("PASSED", 2, 2, 0, None)
    keys = {report: _figures(row) for (rule, report), row in checks.items() if rule == "unique_keys"}
    assert keys == {
        "office.v_document_counts": ("PASSED", 7, 7, 0, None),
        "office.v_overdue_by_department": ("PASSED", 2, 2, 0, None),   # hai phòng, không có dòng "chưa rõ phòng"
        "office.v_processing_time": ("PASSED", 1, 1, 0, None),
        "office.v_outgoing_by_month": ("PASSED", 2, 2, 0, None),
    }
    assert all(r["status"] == "PASSED" for r in checks.values())


def test_unknown_lead_department_is_a_warning():
    unit = Unit().consistent()
    unit.lead(unit.incoming("in_progress"), user=f"chua-dong-bo-{unit.tag}")   # người chưa có trong danh bạ
    unit.incoming("in_progress")                                                # đang xử lý mà chưa có chủ trì
    row = unit.checks()["department_total", "office.v_overdue_by_department"]
    # tổng vẫn khớp (dòng "chưa rõ phòng" giữ cho đủ), nhưng 2 văn bản không biết phòng nào chủ trì
    assert _figures(row) == ("WARNING", 4, 4, 2, None)


def test_finished_without_a_finish_time_is_a_warning_and_negative_hours_fail():
    unit = Unit().consistent()
    unit.incoming("done", registered="'2026-09-01 08:00+07'")       # nhập thẳng: không có sự kiện processed / filed
    assert _figures(unit.checks()["processing_coverage", "office.v_processing_time"]) == ("WARNING", 3, 2, 1, None)
    # xong trước khi vào sổ: tháng 7 có tổng giờ âm — số trung bình vô nghĩa
    unit.finished(unit.incoming("done", registered="'2026-07-20 08:00+07'"), "2026-07-10 08:00+07")
    row = unit.checks()["processing_coverage", "office.v_processing_time"]
    assert _figures(row) == ("FAILED", 4, 3, 1, ["2026-07"])


def test_regressed_views_fail_the_reconciliation_and_key_rules():
    unit = Unit().consistent()
    # Một lần sửa view đặt tên mới cho trạng thái "cancelled" (như migration 1200, chỉ khác cột status): biểu đồ vẽ 6
    # trạng thái cố định nên không còn vẽ văn bản đó
    renamed = """select d.tenant_id, d.direction, d.restricted,
             case when not d.restricted then replace(d.status, 'cancelled', 'withdrawn') end as status,
             case when not d.restricted then d.urgency end as urgency,
             case when not d.restricted then
               coalesce(d.direction = 'in' and d.status in ('received', 'registered', 'in_progress')
                        and d.due_on < (now() at time zone 'Asia/Ho_Chi_Minh')::date, false)
             end as overdue,
             count(*)::int as documents
        from office.documents d
       group by 1, 2, 3, 4, 5, 6"""
    with _replaced("office.v_document_counts", renamed):
        row = unit.checks()["status_total", "office.v_document_counts"]
        assert _figures(row) == ("FAILED", 9, 8, 1, ["withdrawn"])
    # Gom thêm theo loại văn bản: hai dòng cùng tháng, trang lấy dòng đầu và mất số của dòng kia
    split = ("select tenant_id, date_trunc('month', issued_on::timestamp)::date as month, count(*)::int as documents "
             "from office.documents where direction = 'out' and status in ('issued', 'archived') and not restricted "
             "group by tenant_id, 2, type_code")
    unit.issued("2026-10-20", type_code="CV")
    with _replaced("office.v_outgoing_by_month", split):
        row = unit.checks()["unique_keys", "office.v_outgoing_by_month"]
        assert _figures(row) == ("FAILED", 3, 2, 1, None)
    # khôi phục xong: lại đạt
    checks = unit.checks()
    assert checks["status_total", "office.v_document_counts"]["status"] == "PASSED"
    assert _figures(checks["unique_keys", "office.v_outgoing_by_month"]) == ("PASSED", 2, 2, 0, None)


def test_personal_columns_in_report_views_follow_the_catalog():
    unit = Unit()
    tag = uuid.uuid4().hex[:6]
    exposed, filtered = f"office.v_t20_{tag}_people", f"office.v_t20_{tag}_named"
    inner, nested = f"office.t20_{tag}_inner", f"office.v_t20_{tag}_nested"
    sql(f"create view {exposed} as select u.tenant_id, u.email, count(*)::int as n from core.users u group by 1, 2")
    sql(f"create view {filtered} as select u.tenant_id, count(*)::int as n from core.users u "
        "where u.full_name is not null group by 1")
    sql(f"create view {inner} as select u.tenant_id, u.username from core.users u")
    sql(f"create view {nested} as select i.tenant_id, count(*)::int as n from {inner} i group by 1")
    try:
        checks = unit.checks()
        pii = {report: _figures(row) for (rule, report), row in checks.items() if rule == "no_personal_columns"}
        # xuất ra cột cá nhân: Trượt (cột đọc từ bảng gốc cũng ghi kèm)
        assert pii[exposed] == ("FAILED", 0, 1, 1, [f"{exposed}.email", "core.users.email"])
        # chỉ đọc để lọc: Cảnh báo
        assert pii[filtered] == ("WARNING", 0, 0, 1, ["core.users.full_name"])
        # đọc qua một view lồng (không theo quy ước v_, chỉ là một tầng): vẫn thấy
        assert pii[nested] == ("WARNING", 0, 0, 1, ["core.users.username"])
        assert inner not in pii
        # mọi khung nhìn báo cáo thật đều đạt, mỗi khung nhìn đúng một dòng
        views = {r[0] for r in sql("select n.nspname || '.' || c.relname from pg_class c join pg_namespace n "
                                    "on n.oid = c.relnamespace where n.nspname = 'office' "
                                    "and c.relname like 'v\\_%' and c.relkind in ('v', 'm')")}
        assert set(pii) == views and len(views) >= 12
        assert {r: s for r, (s, *_) in pii.items() if r not in (exposed, filtered, nested)} == \
            {r: "PASSED" for r in views - {exposed, filtered, nested}}
    finally:
        sql(f"drop view if exists {nested}; drop view if exists {inner}; drop view if exists {filtered}; "
            f"drop view if exists {exposed}")
    assert not {report for rule, report in unit.checks() if report in (exposed, filtered, nested)}


def test_only_unit_leaders_read_their_own_results(world: World):
    mine = world.director_a.gql(CHECKS)["office_report_checks"]
    assert mine and {r["tenant_id"] for r in mine} == {world.tenant_a}
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert {r["tenant_id"] for r in other.gql(CHECKS)["office_report_checks"]} == {world.tenant_b}
    for user in (world.clerk_a, world.staff_a1, world.manager_a1, world.admin_a, world.clerk_b):
        with pytest.raises(GraphQLError):
            user.gql(CHECKS)
    fields = world.director_a.gql('{ __type(name: "office_report_checks") { fields { name } } }')
    assert {f["name"] for f in fields["__type"]["fields"]} == {"tenant_id", "rule", "report", "status", "expected",
                                                              "actual", "issues", "detail"}
    root = world.director_a.gql("{ __schema { queryType { fields { name } } mutationType { fields { name } } } }")
    names = {f["name"] for t in ("queryType", "mutationType") for f in (root["__schema"][t] or {}).get("fields", [])}
    assert {n for n in names if "report_checks" in n} == {"office_report_checks"}


def test_rules_match_what_the_office_declares(world: World):
    rows = world.director_a.gql(CHECKS)["office_report_checks"]
    quality = (OFFICE / "utils" / "quality.ts").read_text(encoding="utf-8")
    declared = re.search(r"export const REPORT_RULES = \[([^\]]*)\]", quality)
    assert declared and set(re.findall(r"'(\w+)'", declared.group(1))) == {r["rule"] for r in rows}
    assert {r["status"] for r in rows} <= {"PASSED", "WARNING", "FAILED"}
    # luật đối chiếu biết đúng 6 trạng thái trang Điều hành vẽ
    board = (OFFICE / "pages" / "dieu-hanh.vue").read_text(encoding="utf-8")
    drawn = re.search(r"const IN_STATUSES = \[([^\]]*)\]", board)
    up = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "default" / "1792281603300_report_checks"
          / "up.sql").read_text(encoding="utf-8")
    shown = re.search(r"restricted or status in \(([^)]*)\)", up)
    assert drawn and shown and re.findall(r"'(\w+)'", drawn.group(1)) == re.findall(r"'(\w+)'", shown.group(1))
    # mỗi khung nhìn của trang Điều hành có ít nhất một luật về số (ngoài luật catalog)
    numeric = {r["report"] for r in rows if r["rule"] != "no_personal_columns"}
    assert numeric == BOARD
