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

"""Góp ý trong Văn phòng điện tử (F4.6, migration 1792281602700_feedback, metadata office_feedback.yaml): mọi người đã
đăng nhập gửi được mức hài lòng 1–5, nội dung ngắn, khuôn đường dẫn màn hình; thuê ước, người gửi, giờ gửi do Hasura và
CSDL đặt. Văn thư, chuyên viên, lãnh đạo phòng chỉ thấy góp ý của mình; lãnh đạo, quản trị đơn vị đọc cả đơn vị nhưng
không biết ai gửi; đơn vị khác không thấy. Màn hình không chứa id, chuỗi truy vấn. Chặn gửi dồn ở CSDL (3 góp ý mỗi 10
phút, 20 mỗi 24 giờ, cả khi gửi nhiều dòng trong một mutation hay nhiều yêu cầu song song); câu lỗi chứa tên
feedback_rate để giao diện dịch được. Không ai sửa, xóa; không vào sổ kiểm toán; vai trò service, agent không gửi được.
Khung nhìn tổng hợp office.v_feedback_summary (migration 1792281602750) theo màn hình, có dòng mọi màn hình và cờ đơn vị
mẫu.

Mỗi test dùng người gửi mới (chặn gửi dồn tính theo người), trên đơn vị A của conftest hoặc một đơn vị riêng khi cần
số đếm biết trước."""

from __future__ import annotations

import itertools
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import Agent, GraphQLError, User, World, sql

SEND = """mutation ($r: Int!, $c: String, $s: String!) {
  insert_office_feedback_one(object: {rating: $r, comment: $c, screen: $s}) { id rating comment screen created_at mine }
}"""
SEND_MANY = """mutation ($o: [office_feedback_insert_input!]!) {
  insert_office_feedback(objects: $o) { affected_rows } }"""
LIST = "{ office_feedback(order_by: {created_at: desc}) { id rating comment screen created_at mine } }"
SUMMARY = """{ office_v_feedback_summary(order_by: {screen: asc_nulls_first}) { tenant_id sample screen feedback
  rating_total rating_1 rating_2 rating_3 rating_4 rating_5 with_comment last_at } }"""

_n = itertools.count(1)


def person(world: World, role: str = "staff", tenant: str | None = None, department: str | None = None) -> User:
    """Người gửi mới cho mỗi lần gọi: giới hạn gửi dồn tính theo người, test này không ăn vào lượt của test khác."""
    tenant = tenant or world.tenant_a
    if department is None and role in ("staff", "manager") and tenant == world.tenant_a:
        department = world.dept_a1
    return User(f"gop-y-{next(_n)}-{world.tag}", role, tenant, department)


def send(user: User, rating: int = 4, comment: str | None = None, screen: str = "/") -> dict:
    return user.gql(SEND, {"r": rating, "c": comment, "s": screen})["insert_office_feedback_one"]


def ids(user: User) -> set[str]:
    return {f["id"] for f in user.gql(LIST)["office_feedback"]}


def test_every_role_sends_tenant_and_sender_from_token(world: World) -> None:
    for role in ("clerk", "staff", "manager", "director", "tenant_admin"):
        user = person(world, role)
        row = send(user, 5, "  Màn tiếp nhận   dễ dùng ", "/van-ban-den/tiep-nhan")
        assert (row["rating"], row["screen"], row["mine"]) == (5, "/van-ban-den/tiep-nhan", True), role
        assert row["comment"] == "Màn tiếp nhận   dễ dùng"     # gọt hai đầu, giữ nguyên bên trong
        assert sql(f"select tenant_id, user_id, created_at > now() - interval '1 minute' from office.feedback "
                   f"where id = '{row['id']}'") == [[world.tenant_a, user.sub, "t"]], role


def test_sender_cannot_choose_tenant_sender_or_time(world: World) -> None:
    user = person(world)
    for extra in ('tenant_id: "%s"' % world.tenant_b, 'user_id: "nguoi-khac"', 'created_at: "2020-01-01T00:00:00Z"'):
        with pytest.raises(GraphQLError):
            user.gql("mutation { insert_office_feedback_one(object: {rating: 3, screen: \"/\", %s}) { id } }" % extra)


def test_staff_clerk_manager_see_only_their_own(world: World) -> None:
    author = person(world)
    mine = send(author, 2, "Không tìm thấy nút trình", "/van-ban-di/soan")["id"]
    assert ids(author) == {mine}
    for other in (person(world), person(world, "clerk"), person(world, "manager"), world.staff_a1b, world.clerk_a,
                  world.manager_a1, world.clerk_b):
        assert mine not in ids(other), other.sub


def test_leaders_read_the_unit_without_knowing_who(world: World) -> None:
    author = person(world)
    fid = send(author, 1, "Trang chậm", "/tim-kiem")["id"]
    for leader in (world.director_a, world.admin_a):
        rows = {f["id"]: f for f in leader.gql(LIST)["office_feedback"]}
        assert rows[fid]["comment"] == "Trang chậm" and rows[fid]["mine"] is False, leader.role
        with pytest.raises(GraphQLError, match="user_id"):
            leader.gql("{ office_feedback { user_id } }")
        total = leader.gql("{ office_feedback_aggregate { aggregate { count avg { rating } } } }")
        assert total["office_feedback_aggregate"]["aggregate"]["count"] >= 1
    director_b = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert fid not in ids(director_b)


def test_mine_filters_own_feedback_for_leaders(world: World) -> None:
    leader = person(world, "director")
    own = send(leader, 4)["id"]
    send(person(world), 3)
    rows = leader.gql("{ office_feedback(where: {mine: {_eq: true}}) { id } }")["office_feedback"]
    assert [r["id"] for r in rows] == [own]


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_rating_between_1_and_5(world: World, rating: int) -> None:
    with pytest.raises(GraphQLError, match="feedback_rating"):
        send(person(world), rating)


def test_comment_short_or_empty(world: World) -> None:
    user = person(world)
    assert send(user, 3, "   ")["comment"] is None
    assert send(user, 3, "x" * 500)["comment"] == "x" * 500
    with pytest.raises(GraphQLError, match="feedback_comment"):
        send(person(world), 3, "x" * 501)


def test_comment_whitespace_trimmed_including_newlines(world: World) -> None:
    user = person(world)
    assert send(user, 3, "\n \t\r\n")["comment"] is None         # chỉ có xuống dòng, tab: như để trống
    assert send(user, 3, " \n Dòng một\nDòng hai\t\n")["comment"] == "Dòng một\nDòng hai"


@pytest.mark.parametrize("screen", ["/", "/van-ban-den/tiep-nhan", "/van-ban/:id", "/so-do", "/gop-y"])
def test_screen_pattern_accepts_route_shapes(world: World, screen: str) -> None:
    assert send(person(world), 4, screen=screen)["screen"] == screen


@pytest.mark.parametrize("screen", [
    "/tim-kiem?q=001205000017",                      # chuỗi truy vấn (có thể chứa số CCCD người dùng gõ)
    f"/van-ban/{uuid.uuid4()}",                      # id văn bản
    "/xac-thuc/ABCDEFGH23",                          # mã tra cứu
    "/Van-Ban-Den", "van-ban-den", "", "/van-ban//den", "/van-ban-den/", "/a-", "/" + "a" * 80,
    "/a/b/c/d/e/f/g",                                # quá 6 đoạn
])
def test_screen_pattern_rejects_ids_queries_and_junk(world: World, screen: str) -> None:
    with pytest.raises(GraphQLError, match="feedback_screen"):
        send(person(world), 4, screen=screen)


def test_three_per_ten_minutes(world: World) -> None:
    user = person(world)
    for _ in range(3):
        send(user)
    with pytest.raises(GraphQLError, match="feedback_rate"):
        send(user)
    assert len(ids(user)) == 3
    send(person(world))                              # người khác không bị chặn theo


def test_rate_error_carries_its_name(world: World) -> None:
    """Lỗi raise trong trigger không có trường constraint: Hasura trả mã permission-error, câu "Check constraint
    violation. feedback_rate: gửi quá nhiều góp ý — …". Giao diện (app/utils/errors.ts) nhận ra lỗi nhờ tên có trong
    câu."""
    user = person(world)
    for _ in range(3):
        send(user)
    body = user.raw(SEND, {"r": 4, "c": None, "s": "/"})
    assert "feedback_rate: gửi quá nhiều góp ý" in body["errors"][0]["message"]


BURST, ROUNDS = 10, 3


def burst(user: User, n: int) -> list[str]:
    """n yêu cầu gửi của cùng một người, thả cùng lúc (barrier): "ok" hay "rate" theo thứ tự đã xếp."""
    gate = threading.Barrier(n)

    def attempt(i: int) -> str:
        gate.wait(timeout=30)
        try:
            send(user, 1 + i % 5)
            return "ok"
        except GraphQLError as exc:
            return "rate" if "feedback_rate" in str(exc) else str(exc)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return sorted(pool.map(attempt, range(n)))


def test_parallel_sends_stop_at_three(world: World) -> None:
    """Mười yêu cầu cùng lúc của một người, ba lượt (mỗi lượt một người mới): khóa tư vấn xếp hàng, lượt nào cũng đúng
    3 lần được lưu. Bỏ khóa thì các trigger cùng đếm thiếu và lưu quá 3, nhưng chỉ theo xác suất (với 6 yêu cầu một
    lượt, khoảng 1/8 lượt vẫn ra đúng 3) — nên thả cùng lúc nhiều yêu cầu hơn và lặp vài lượt."""
    for _ in range(ROUNDS):
        user = person(world)
        assert burst(user, BURST) == ["ok"] * 3 + ["rate"] * (BURST - 3)
        assert sql(f"select count(*) from office.feedback where user_id = '{user.sub}'") == [["3"]]


def test_many_rows_in_one_mutation_are_counted(world: World) -> None:
    user = person(world)
    with pytest.raises(GraphQLError, match="feedback_rate"):
        user.gql(SEND_MANY, {"o": [{"rating": 5, "screen": "/"}] * 4})
    assert ids(user) == set()                        # một giao dịch: không dòng nào được lưu
    assert user.gql(SEND_MANY, {"o": [{"rating": 5, "screen": "/"}] * 3})["insert_office_feedback"] == {
        "affected_rows": 3}


def test_twenty_per_day(world: World) -> None:
    user = person(world)
    # 20 góp ý trong 24 giờ qua nhưng không trong 10 phút qua: thêm từng dòng rồi lùi giờ gửi về 2 giờ trước
    sql(f"""do $$ begin for i in 1..20 loop
              insert into office.feedback (tenant_id, user_id, rating, screen)
              values ('{world.tenant_a}', '{user.sub}', 3, '/');
              update office.feedback set created_at = now() - interval '2 hours'
               where tenant_id = '{world.tenant_a}' and user_id = '{user.sub}' and created_at = now();
            end loop; end $$""")
    with pytest.raises(GraphQLError, match="feedback_rate"):
        send(user)
    sql(f"update office.feedback set created_at = now() - interval '25 hours' where user_id = '{user.sub}'")
    send(user)


def test_time_is_set_by_the_database(world: World) -> None:
    user = person(world)
    sql(f"insert into office.feedback (tenant_id, user_id, rating, screen, created_at) "
        f"values ('{world.tenant_a}', '{user.sub}', 3, '/', '2020-01-01')")
    assert sql(f"select created_at > now() - interval '1 minute' from office.feedback where user_id = '{user.sub}'") \
        == [["t"]]


def test_nobody_updates_or_deletes(world: World) -> None:
    user = person(world)
    fid = send(user, 2)["id"]
    for actor in (user, world.director_a, world.admin_a):
        with pytest.raises(GraphQLError, match="update_office_feedback"):
            actor.gql("mutation ($i: uuid!) { update_office_feedback_by_pk(pk_columns: {id: $i}, _set: {rating: 5}) "
                      "{ id } }", {"i": fid})
        with pytest.raises(GraphQLError, match="delete_office_feedback"):
            actor.gql("mutation ($i: uuid!) { delete_office_feedback_by_pk(id: $i) { id } }", {"i": fid})
    assert sql(f"select rating from office.feedback where id = '{fid}'") == [["2"]]


def test_not_in_the_audit_log(world: World) -> None:
    fid = send(person(world), 5, "Hay")["id"]
    # sổ ghi người thực hiện: lãnh đạo đọc sổ sẽ biết ai góp ý
    rows = sql(f"select count(*) from core.audit_log where entity = 'office.feedback' or entity_id = '{fid}'")
    assert rows == [["0"]]


def test_service_and_agent_cannot_send(world: World) -> None:
    for robot in (world.service_a, Agent(f"moc-doc-reader-{world.tag}", "agent", world.tenant_a)):
        with pytest.raises(GraphQLError, match="insert_office_feedback_one"):
            robot.gql(SEND, {"r": 5, "c": None, "s": "/"})
        with pytest.raises(GraphQLError):
            robot.gql(LIST)


def test_summary_by_screen_for_leaders(world: World) -> None:
    tag = uuid.uuid4().hex[:6].upper()
    tenant = sql(f"insert into core.tenants (code, name) values ('G{tag}', 'Đơn vị thử góp ý') returning id")[0][0]
    director = User(f"lanh-dao-gop-y-{tag}", "director", tenant)
    admin = User(f"quan-tri-gop-y-{tag}", "tenant_admin", tenant)
    for rating, comment, screen in ((5, "Nhanh", "/"), (4, None, "/"), (1, "Không thấy văn bản", "/tim-kiem"),
                                    (2, None, "/tim-kiem"), (3, None, "/van-ban/:id")):
        send(person(world, "staff", tenant), rating, comment, screen)
    rows = {r["screen"]: r for r in director.gql(SUMMARY)["office_v_feedback_summary"]}
    assert {s: (r["feedback"], r["rating_total"], r["with_comment"]) for s, r in rows.items()} == {
        "/": (2, 9, 1), "/tim-kiem": (2, 3, 1), "/van-ban/:id": (1, 3, 0), None: (5, 15, 2)}
    assert [rows[None][f"rating_{i}"] for i in range(1, 6)] == [1, 1, 1, 1, 1]
    assert {r["tenant_id"] for r in rows.values()} == {tenant} and not any(r["sample"] for r in rows.values())
    assert admin.gql(SUMMARY)["office_v_feedback_summary"] == director.gql(SUMMARY)["office_v_feedback_summary"]
    # đơn vị mẫu của make seed: số ghi rõ là trên dữ liệu mẫu
    sql(f"update core.tenants set sample_data = true where id = '{tenant}'")
    assert all(r["sample"] for r in director.gql(SUMMARY)["office_v_feedback_summary"])


def test_only_leaders_aggregate(world: World) -> None:
    send(person(world), 4)
    query = "{ office_feedback_aggregate { aggregate { count } } }"
    for other in (person(world), person(world, "clerk"), person(world, "manager"), world.staff_a1):
        with pytest.raises(GraphQLError, match="office_feedback_aggregate"):
            other.gql(query)
    for leader in (world.director_a, world.admin_a):
        assert leader.gql(query)["office_feedback_aggregate"]["aggregate"]["count"] >= 1


def test_summary_only_for_leaders_of_the_unit(world: World) -> None:
    send(person(world), 4)
    assert {r["tenant_id"] for r in world.director_a.gql(SUMMARY)["office_v_feedback_summary"]} == {world.tenant_a}
    director_b = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert {r["tenant_id"] for r in director_b.gql(SUMMARY)["office_v_feedback_summary"]} <= {world.tenant_b}
    for other in (world.clerk_a, world.manager_a1, world.staff_a1):
        assert "errors" in other.raw(SUMMARY), other.role
