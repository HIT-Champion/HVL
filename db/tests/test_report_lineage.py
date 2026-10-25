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


"""Phả hệ của báo cáo tổng hợp (F3.9, F3.11): office.report_lineage tính từ catalog PostgreSQL — khung nhìn báo cáo
(office.v_*) đọc bảng, view nào, kể cả view lồng view; tạo, sửa, xóa view là phả hệ đổi theo, không khai tay. Chỉ có tên
và cạnh, giống nhau cho mọi đơn vị; lãnh đạo đơn vị đọc (như dashboard), vai trò khác không thấy. Khai báo biểu đồ →
khung nhìn của office (apps/office/app/utils/lineage.ts) chỉ được nêu khung nhìn có thật trong phả hệ."""

from __future__ import annotations

import pathlib
import re
import uuid

import pytest
from conftest import GraphQLError, User, World, sql

LINEAGE = "{ office_report_lineage { report consumer source source_kind depth } }"
OF = """query ($r: String!) { office_report_lineage(where: {report: {_eq: $r}}) {
  report consumer source source_kind depth } }"""
DASHBOARD = {
    "office.v_document_counts": {"office.documents"},
    "office.v_overdue_by_department": {"core.users", "office.assignments", "office.departments", "office.documents"},
    "office.v_processing_time": {"office.archived_document_facts", "office.document_events", "office.documents"},
    "office.v_outgoing_by_month": {"office.documents"},
}
OFFICE_DECLARATION = pathlib.Path(__file__).resolve().parents[2] / "apps" / "office" / "app" / "utils" / "lineage.ts"


def _edges(user: User, report: str) -> set[tuple[str, str, str, int]]:
    rows = user.gql(OF, {"r": report})["office_report_lineage"]
    assert {r["report"] for r in rows} <= {report}
    return {(r["consumer"], r["source"], r["source_kind"], r["depth"]) for r in rows}


def test_dashboard_views_trace_to_their_tables_from_the_catalog(world: World):
    for view, tables in DASHBOARD.items():
        assert _edges(world.director_a, view) == {(view, t, "table", 1) for t in tables}, view


def test_every_report_view_is_a_root():
    views = {r[0] for r in sql("select n.nspname || '.' || c.relname from pg_class c join pg_namespace n "
                                "on n.oid = c.relnamespace where n.nspname = 'office' and c.relname like 'v\\_%' "
                                "and c.relkind in ('v', 'm')")}
    reports = {r[0] for r in sql("select distinct report from office.report_lineage")}
    assert len(views) >= 9 and reports == views


def test_no_report_view_hides_tables_behind_a_function():
    # catalog không ghi bảng mà một hàm SQL đọc: view báo cáo gọi hàm tự viết thì phả hệ sẽ thiếu cạnh — chặn ở đây
    calls = sql("""select distinct c.relname || ' → ' || pn.nspname || '.' || p.proname
      from pg_rewrite r
      join pg_class c on c.oid = r.ev_class join pg_namespace n on n.oid = c.relnamespace
      join pg_depend d on d.classid = 'pg_rewrite'::regclass and d.objid = r.oid
                      and d.refclassid = 'pg_proc'::regclass
      join pg_proc p on p.oid = d.refobjid join pg_namespace pn on pn.oid = p.pronamespace
     where n.nspname = 'office' and c.relname like 'v\\_%'
       and pn.nspname not in ('pg_catalog', 'information_schema')""")
    assert calls == []


def test_new_nested_and_changed_views_follow_the_catalog(world: World):
    tag = uuid.uuid4().hex[:6]
    inner, root, mat = f"office.t89_{tag}_inner", f"office.v_t89_{tag}", f"office.v_t89_{tag}_mat"
    sql(f"create view {inner} as select d.tenant_id, d.id from office.documents d "
        "join office.registers g on g.id = d.register_id")
    sql(f"create view {root} as select i.tenant_id, count(*)::int as n from {inner} i "
        "where exists (select 1 from office.assignments a where a.document_id = i.id) group by 1")
    sql(f"create materialized view {mat} as select tenant_id, count(*)::int as n from office.feedback group by 1 "
        "with no data")
    try:
        # view lồng view: đi tiếp tới bảng; subquery trong exists cũng là một cạnh
        assert _edges(world.director_a, root) == {
            (root, inner, "view", 1), (root, "office.assignments", "table", 1),
            (inner, "office.documents", "table", 2), (inner, "office.registers", "table", 2)}
        assert _edges(world.director_a, mat) == {(mat, "office.feedback", "table", 1)}
        # view không theo quy ước tên v_ không là báo cáo, chỉ là một tầng
        assert _edges(world.director_a, inner) == set()
        # sửa view là phả hệ đổi theo
        sql(f"create or replace view {root} as select i.tenant_id, count(*)::int as n from {inner} i group by 1")
        assert ("office.assignments" not in {s for _, s, _, _ in _edges(world.director_a, root)})
    finally:
        sql(f"drop materialized view if exists {mat}; drop view if exists {root}; drop view if exists {inner}")
    assert _edges(world.director_a, root) == set() and _edges(world.director_a, mat) == set()


def test_only_unit_leaders_read_and_only_names(world: World):
    mine = {tuple(r.values()) for r in world.director_a.gql(LINEAGE)["office_report_lineage"]}
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    # catalog chung: đơn vị nào cũng thấy cùng một phả hệ, không có cột đơn vị nào để lọc
    assert mine and {tuple(r.values()) for r in other.gql(LINEAGE)["office_report_lineage"]} == mine
    for user in (world.clerk_a, world.staff_a1, world.manager_a1, world.admin_a, world.clerk_b):
        with pytest.raises(GraphQLError):
            user.gql(LINEAGE)
    fields = world.director_a.gql('{ __type(name: "office_report_lineage") { fields { name } } }')
    assert {f["name"] for f in fields["__type"]["fields"]} == {"report", "consumer", "source", "source_kind", "depth"}
    with pytest.raises(GraphQLError):
        world.director_a.gql('mutation { insert_office_report_lineage(objects: [{report: "x"}]) { affected_rows } }')


def test_office_declares_only_real_report_views(world: World):
    text = OFFICE_DECLARATION.read_text(encoding="utf-8")
    block = text[text.index("export const BOARD_CHARTS"):]
    block = block[:block.index("\n]\n")]
    declared = set(re.findall(r"'(office\.v_\w+)'", block))
    assert declared == set(DASHBOARD)
    reports = {r["report"] for r in world.director_a.gql(LINEAGE)["office_report_lineage"]}
    assert declared <= reports
