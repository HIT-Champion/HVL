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

"""Tự chẩn đoán H-P-D-I (migration 1792281603100_maturity_assessments, metadata office_maturity_assessments.yaml,
trang /tu-chan-doan): chỉ lãnh đạo đơn vị lưu và đọc lịch sử của đơn vị mình; thuê ước, người lưu do Hasura đặt từ
token; điểm h, p, d, i và giờ lưu do CSDL tính, đặt — người gửi không chọn được; answers phải đúng bộ mã câu của phiên
bản hpdi-1 (lỗi mang tên maturity_answers), phiên bản lạ bị chặn (maturity_framework); ghi chú gọt khoảng trắng, tối
đa 300 ký tự; mỗi đơn vị tối đa 5 lần lưu mỗi giờ, 20 lần mỗi 24 giờ (maturity_rate, cả khi gửi song song hay nhiều
dòng một lệnh); không ai sửa, xóa; mỗi lần lưu một dòng sổ kiểm toán. Truy vấn bằng chứng, lịch sử và mutation lưu lấy
nguyên văn từ trang: lãnh đạo đơn vị chạy được, lãnh đạo phòng thì Hasura từ chối (trang không gọi).

Giới hạn lưu dồn đếm theo đơn vị nên mỗi test lưu trong một đơn vị mới (fixture unit), không trong world.tenant_a."""

from __future__ import annotations

import json
import pathlib
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import Agent, GraphQLError, User, World, sql

PAGE = (pathlib.Path(__file__).resolve().parents[2] / "apps" / "office" / "app" / "pages" / "tu-chan-doan.vue") \
    .read_text(encoding="utf-8")


def page_query(name: str) -> str:
    columns = re.search(r"const COLUMNS = '([^']+)'", PAGE).group(1)
    return re.search(rf"const {name} = `([^`]+)`", PAGE).group(1).replace("${COLUMNS}", columns)


EVIDENCE, HISTORY, SAVE = page_query("EVIDENCE"), page_query("HISTORY"), page_query("SAVE")
SAVE_MANY = """mutation ($o: [office_maturity_assessments_insert_input!]!) {
  insert_office_maturity_assessments(objects: $o) { affected_rows } }"""
FULL = {"h1": 2, "h2": 3, "h3": 3, "p1": 4, "p2": 4, "p3": 5, "d1": 1, "d2": 2, "d3": 2, "i1": 1, "i2": 1, "i3": 1}


def new_unit() -> str:
    tag = uuid.uuid4().hex[:6].upper()
    return sql(f"insert into core.tenants (code, name) values ('H{tag}', 'Đơn vị thử tự chẩn đoán') "
               f"returning id")[0][0]


@pytest.fixture
def unit() -> str:
    """Một đơn vị mới cho mỗi test: giới hạn lưu dồn (maturity_rate) đếm theo đơn vị."""
    return new_unit()


def leader(tenant: str) -> User:
    return User(f"lanh-dao-hpdi-{uuid.uuid4().hex[:8]}", "director", tenant)


def save(user: User, answers: dict | None = None, note: str | None = None, framework: str = "hpdi-1") -> dict:
    obj = {"framework": framework, "answers": FULL if answers is None else answers, "note": note}
    return user.gql(SAVE, {"o": obj})["insert_office_maturity_assessments_one"]


def count(tenant: str) -> int:
    return int(sql(f"select count(*) from office.maturity_assessments where tenant_id = '{tenant}'")[0][0])


def history(user: User) -> list[dict]:
    return user.gql(HISTORY)["office_maturity_assessments"]


def test_director_saves_scores_computed_by_the_database(unit: str) -> None:
    director = leader(unit)
    row = save(director, note="  Sau đợt triển khai văn bản đến \n")
    assert (float(row["h"]), float(row["p"]), float(row["d"]), float(row["i"])) == (2.67, 4.33, 1.67, 1.0)
    assert row["framework"] == "hpdi-1" and row["answers"] == FULL
    assert row["note"] == "Sau đợt triển khai văn bản đến"
    assert sql(f"select tenant_id, created_by, created_at > now() - interval '1 minute' "
               f"from office.maturity_assessments where id = '{row['id']}'") == [[unit, director.sub, "t"]]
    assert history(director)[0]["id"] == row["id"]


@pytest.mark.parametrize(("column", "value"), [("tenant_id", f'"{uuid.uuid4()}"'), ("created_by", '"nguoi-khac"'),
                                               ("h", "5"), ("created_at", '"2020-01-01T00:00:00Z"')])
def test_sender_cannot_choose_tenant_author_scores_or_time(unit: str, column: str, value: str) -> None:
    with pytest.raises(GraphQLError,
                       match=rf"field '{column}' not found in type: 'office_maturity_assessments_insert_input'"):
        leader(unit).gql("mutation ($a: jsonb!) { insert_office_maturity_assessments_one("
                         "object: {framework: \"hpdi-1\", answers: $a, %s: %s}) { id } }" % (column, value),
                         {"a": FULL})
    assert count(unit) == 0


@pytest.mark.parametrize("answers", [
    {},                                                          # không câu nào
    {"h1": 5, "p1": 5, "d1": 5, "i1": 5},                        # mỗi không gian một câu: thiếu 8 câu
    {k: v for k, v in FULL.items() if k != "i3"},                # thiếu một câu
    {**FULL, "h4": 3},                                           # thừa một câu (khuôn mã đúng, ngoài bộ hpdi-1)
    {f"{s}{n}": 3 for s in "hpdi" for n in range(1, 10)},        # 36 câu h1…i9
    {**FULL, "x1": 3},                                           # mã câu lạ
    {**{k: v for k, v in FULL.items() if k != "h1"}, "H1": 2},   # chữ hoa thay cho h1: đủ 12 khóa nhưng sai mã
    {**FULL, "h1": 0}, {**FULL, "h1": 6}, {**FULL, "h1": 2.5},   # ngoài 1–5, số lẻ
    {**FULL, "h1": "3"}, {**FULL, "h1": None}, {**FULL, "h1": True},
    [3, 4], "h1", 3,                                             # không phải đối tượng
])
def test_answers_must_be_exactly_the_question_set(unit: str, answers) -> None:
    with pytest.raises(GraphQLError, match="maturity_answers"):
        save(leader(unit), answers)
    assert count(unit) == 0


def test_answers_error_names_the_question_set(unit: str) -> None:
    body = leader(unit).raw(SAVE, {"o": {"framework": "hpdi-1", "answers": {"h1": 5, "p1": 5, "d1": 5, "i1": 5}}})
    assert "maturity_answers: cần đủ 12 câu của bộ hpdi-1 (h1, h2, h3, p1" in body["errors"][0]["message"]


@pytest.mark.parametrize("framework", ["", "HPDI-1", "hpdi-2", "hpdi 1", "hpdi_1", "x" * 41])
def test_framework_must_be_a_known_question_set(unit: str, framework: str) -> None:
    with pytest.raises(GraphQLError, match="maturity_framework"):
        save(leader(unit), framework=framework)


def test_note_trimmed_short_or_empty(unit: str) -> None:
    director = leader(unit)
    assert save(director, note=" \n\t ")["note"] is None
    assert save(director, note="x" * 300)["note"] == "x" * 300
    with pytest.raises(GraphQLError, match="maturity_note"):
        save(director, note="x" * 301)


def test_history_stays_in_the_tenant(unit: str) -> None:
    a1, a2 = leader(unit), leader(unit)
    mine = save(a1)["id"]
    assert mine in {r["id"] for r in history(a2)}            # lịch sử của đơn vị, không của riêng người lưu
    save(a2)
    director_b = leader(new_unit())
    theirs = save(director_b, {**FULL, "h1": 5})["id"]
    assert mine not in {r["id"] for r in history(director_b)}
    assert theirs not in {r["id"] for r in history(a1)}
    with pytest.raises(GraphQLError, match="created_by"):
        a1.gql("{ office_maturity_assessments { created_by } }")
    with pytest.raises(GraphQLError, match="tenant_id"):
        a1.gql("{ office_maturity_assessments { tenant_id } }")
    total = a1.gql("{ office_maturity_assessments_aggregate { aggregate { count avg { h } } } }")
    assert total["office_maturity_assessments_aggregate"]["aggregate"]["count"] == 2


def test_other_roles_have_no_access(world: World) -> None:
    for user in (world.clerk_a, world.manager_a1, world.staff_a1, world.admin_a, world.service_a,
                 Agent(f"moc-doc-reader-{world.tag}", "agent", world.tenant_a)):
        with pytest.raises(GraphQLError, match="insert_office_maturity_assessments_one"):
            save(user)
        with pytest.raises(GraphQLError, match="office_maturity_assessments"):
            history(user)
    assert count(world.tenant_a) == 0


def test_nobody_updates_or_deletes(unit: str) -> None:
    director = leader(unit)
    rid = save(director)["id"]
    for actor in (director, User(f"quan-tri-hpdi-{uuid.uuid4().hex[:8]}", "tenant_admin", unit)):
        with pytest.raises(GraphQLError, match="update_office_maturity_assessments"):
            actor.gql("mutation ($i: uuid!) { update_office_maturity_assessments_by_pk(pk_columns: {id: $i}, "
                      "_set: {note: \"sửa\"}) { id } }", {"i": rid})
        with pytest.raises(GraphQLError, match="delete_office_maturity_assessments"):
            actor.gql("mutation ($i: uuid!) { delete_office_maturity_assessments_by_pk(id: $i) { id } }", {"i": rid})
    assert sql(f"select count(*) from office.maturity_assessments where id = '{rid}'") == [["1"]]


def test_scores_follow_answers_even_on_direct_write(unit: str) -> None:
    """Ghi thẳng CSDL (chỉ quản trị làm được) cũng qua trigger: điểm luôn tính lại từ answers, không ghi đè được."""
    rid = sql(f"insert into office.maturity_assessments (tenant_id, created_by, framework, answers, h, p, d, i) "
              f"values ('{unit}', 'quan-tri-csdl', 'hpdi-1', '{json.dumps(FULL)}', 5, 5, 5, 5) "
              f"returning id")[0][0]
    sql(f"""update office.maturity_assessments set h = 5, answers = answers || '{{"h1": 5}}' where id = '{rid}'""")
    assert sql(f"select h, p from office.maturity_assessments where id = '{rid}'") == [["3.67", "4.33"]]


def test_each_save_is_in_the_audit_log(unit: str) -> None:
    director = leader(unit)
    rid = save(director)["id"]
    rows = sql(f"select actor_id, actor_kind, action, tenant_id, diff ? 'answers' from core.audit_log "
               f"where entity = 'office.maturity_assessments' and entity_id = '{rid}'")
    assert rows == [[director.sub, "user", "insert", unit, "t"]]


def test_five_saves_per_hour_per_unit(unit: str) -> None:
    a1, a2 = leader(unit), leader(unit)
    for user in (a1, a2, a1, a2, a1):
        save(user)
    # lãnh đạo khác của cùng đơn vị cũng bị chặn: giới hạn theo đơn vị
    for user in (a1, a2):
        with pytest.raises(GraphQLError, match="maturity_rate"):
            save(user)
    assert count(unit) == 5
    save(leader(new_unit()))                         # đơn vị khác không bị chặn theo


def test_rate_error_carries_its_name(unit: str) -> None:
    """Như feedback_rate: Hasura trả "Check constraint violation. maturity_rate: …", giao diện
    (app/utils/errors.ts) nhận ra lỗi nhờ tên có trong câu."""
    director = leader(unit)
    for _ in range(5):
        save(director)
    body = director.raw(SAVE, {"o": {"framework": "hpdi-1", "answers": FULL}})
    assert "maturity_rate: lưu quá nhiều lần" in body["errors"][0]["message"]


def test_many_rows_in_one_mutation_are_counted(unit: str) -> None:
    director = leader(unit)
    row = {"framework": "hpdi-1", "answers": FULL}
    with pytest.raises(GraphQLError, match="maturity_rate"):
        director.gql(SAVE_MANY, {"o": [row] * 6})
    assert count(unit) == 0                          # một giao dịch: không dòng nào được lưu
    assert director.gql(SAVE_MANY, {"o": [row] * 5})["insert_office_maturity_assessments"] == {"affected_rows": 5}


BURST, ROUNDS = 10, 2


def test_parallel_saves_stop_at_five() -> None:
    """Mười yêu cầu lưu cùng lúc (barrier) của một đơn vị, hai lượt: khóa tư vấn theo đơn vị xếp hàng, lượt nào cũng
    đúng 5 lần được lưu. Bỏ khóa thì các trigger cùng đếm thiếu và lưu quá 5 (theo xác suất, như test của góp ý)."""
    for _ in range(ROUNDS):
        tenant = new_unit()
        director = leader(tenant)
        gate = threading.Barrier(BURST)

        def attempt(_: int) -> str:
            gate.wait(timeout=30)
            try:
                save(director)
                return "ok"
            except GraphQLError as exc:
                return "rate" if "maturity_rate" in str(exc) else str(exc)

        with ThreadPoolExecutor(max_workers=BURST) as pool:
            assert sorted(pool.map(attempt, range(BURST))) == ["ok"] * 5 + ["rate"] * (BURST - 5)
        assert count(tenant) == 5


def test_twenty_saves_per_day(unit: str) -> None:
    director = leader(unit)
    # 20 lần lưu trong 24 giờ qua nhưng không trong 1 giờ qua: thêm từng dòng rồi lùi giờ lưu về 2 giờ trước
    sql(f"""do $$ begin for n in 1..20 loop
              insert into office.maturity_assessments (tenant_id, created_by, framework, answers, h, p, d, i)
              values ('{unit}', 'lanh-dao-cu', 'hpdi-1', '{json.dumps(FULL)}', 1, 1, 1, 1);
              update office.maturity_assessments set created_at = now() - interval '2 hours'
               where tenant_id = '{unit}' and created_at = now();
            end loop; end $$""")
    with pytest.raises(GraphQLError, match="maturity_rate"):
        save(director)
    sql(f"update office.maturity_assessments set created_at = now() - interval '25 hours' where tenant_id = '{unit}'")
    save(director)


def test_correcting_a_row_is_not_a_new_save(unit: str) -> None:
    """Sửa dòng (chỉ quản trị CSDL) qua trigger để tính lại điểm nhưng không bị đếm là lần lưu mới."""
    director = leader(unit)
    rid = save(director)["id"]
    for _ in range(4):
        save(director)
    sql(f"""update office.maturity_assessments set answers = answers || '{{"h1": 5}}' where id = '{rid}'""")
    assert sql(f"select h from office.maturity_assessments where id = '{rid}'") == [["3.67"]]


def test_page_queries_run_for_the_director_and_are_refused_for_others(world: World, unit: str) -> None:
    """Đúng chuỗi truy vấn của trang: bằng chứng đo được (các view số đếm đã có, hồ sơ) và lịch sử. Lãnh đạo đơn vị
    chạy được trên một đơn vị mới chưa có dữ liệu (trang không hiện chỉ số nào); lãnh đạo phòng bị từ chối nên trang
    không gọi."""
    director = leader(unit)
    data = director.gql(EVIDENCE)
    assert data["office_v_document_counts"] == [] and data["office_case_files"] == []
    assert data["office_v_time_to_assign"] in ([], [{"sample": False, "month": None, "assigned": 0,
                                                       "median_hours": None}])
    assert history(director) == []
    for other in (world.manager_a1, world.admin_a):
        with pytest.raises(GraphQLError, match=r"field '\w+' not found in type: 'query_root'"):
            other.gql(EVIDENCE)
