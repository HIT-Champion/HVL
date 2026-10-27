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

"""Kênh ngoài của thông báo (core.notification_deliveries): dòng chờ gửi tạo cùng giao dịch với thông báo, gọi lại
cùng khóa không thêm dòng, chỉ dịch vụ của đơn vị đọc và ghi kết quả, mỗi lần đổi vào sổ kiểm toán. SMS, Zalo (#365):
chỉ có dòng chờ cho người đã tự bật kênh (core.notification_subscriptions), SMS cần số điện thoại trong danh bạ.

Số điện thoại, chat_id Zalo trong tệp này là giả lập."""

from __future__ import annotations

import dataclasses

import pytest

from conftest import ADMIN_SECRET, GraphQLError, SQLError, User, gql_raw, sql

NOTIFY = """
mutation ($rows: [core_notifications_insert_input!]!) {
  insert_core_notifications(objects: $rows,
                            on_conflict: {constraint: notifications_once, update_columns: []}) {
    returning { id user_id }
  }
}"""

DELIVERIES = """
query ($ids: [bigint!]!) {
  core_notification_deliveries(where: {notification_id: {_in: $ids}}, order_by: {channel: asc}) {
    id notification_id user_id channel status attempts next_attempt_at sent_at
  }
}"""

DONE = """
mutation ($id: bigint!, $attempts: Int!, $set: core_notification_deliveries_set_input!) {
  update_core_notification_deliveries(where: {id: {_eq: $id}, status: {_eq: "pending"}, attempts: {_eq: $attempts}},
                                      _set: $set) { affected_rows }
}"""

# đúng truy vấn vòng nền của svc-workflow (channels.DUE): khóa quản trị, mọi đơn vị, kèm người nhận trong danh bạ
DUE = """
query ($now: timestamptz!, $ids: [bigint!]!) {
  core_notification_deliveries(where: {status: {_eq: "pending"}, next_attempt_at: {_lte: $now},
                                       notification_id: {_in: $ids}}, order_by: {id: asc}) {
    id tenant_id channel attempts
    notification { kind document_id data created_at }
    recipient { full_name email enabled phone }
    subscriptions { channel enabled zalo_chat_id }
  }
}"""

# đúng mutation của svc-workflow (subscriptions.SAVE)
SAVE = """
mutation ($row: core_notification_subscriptions_insert_input!) {
  insert_core_notification_subscriptions_one(object: $row, on_conflict: {
    constraint: notification_subscriptions_pkey, update_columns: [enabled, zalo_chat_id, link_code, link_expires_at]
  }) { channel }
}"""

SUBS = """
query ($users: [String!]!) {
  core_notification_subscriptions(where: {user_id: {_in: $users}}, order_by: [{user_id: asc}, {channel: asc}]) {
    user_id channel enabled zalo_chat_id link_code
  }
}"""

PHONE = "+84912345678"      # giả lập


@pytest.fixture(scope="module")
def people(world):
    # Người nhận riêng của module: world dùng chung cả phiên, thông báo gửi ở đây không được lọt vào số đếm của
    # test_notifications. Quyền đọc vẫn thử bằng người của world (admin_a) và bằng chính người nhận
    own = {k: User(f"kenh-{u.sub}", u.role, u.tenant, u.department)
           for k in ("director_a", "staff_a1", "staff_a2", "clerk_b") for u in [getattr(world, k)]}
    world = dataclasses.replace(world, **own)
    rows = [{"id": u.sub, "department_id": u.department, "username": u.sub, "full_name": f"Người {u.role}",
             "email": f"{u.role}-{world.tag.lower()}@example.com", "role": u.role}
            for u in (world.director_a, world.staff_a1, world.staff_a2)]
    upsert = """mutation ($o: [core_users_insert_input!]!) {
      insert_core_users(objects: $o, on_conflict: {constraint: users_pkey, update_columns: [email]}) { affected_rows }
    }"""
    world.service_a.gql(upsert, {"o": rows})
    world.service_b.gql(upsert, {"o": [{"id": world.clerk_b.sub, "username": world.clerk_b.sub,
                                        "full_name": "Văn thư B", "role": "clerk"}]})
    return world


def notify(service, key: str, *rows: tuple[str, list[str]], kind: str = "task.assigned") -> list[dict]:
    objects = [{"user_id": user, "kind": kind, "key": key, "data": {"form_key": "vbden.xuLy"},
                **({"channels": channels} if channels else {})} for user, channels in rows]
    return service.gql(NOTIFY, {"rows": objects})["insert_core_notifications"]["returning"]


def deliveries(service, created: list[dict]) -> list[dict]:
    return service.gql(DELIVERIES, {"ids": [r["id"] for r in created]})["core_notification_deliveries"]


def test_queued_in_the_same_insert_once_per_channel(people):
    w = people
    created = notify(w.service_a, "task:kd-1:assigned", (w.staff_a1.sub, ["email", "webhook"]),
                     (w.staff_a2.sub, ["email"]), (w.director_a.sub, []))
    assert len(created) == 3
    rows = deliveries(w.service_a, created)
    assert sorted((r["user_id"], r["channel"]) for r in rows) == sorted(
        [(w.staff_a1.sub, "email"), (w.staff_a1.sub, "webhook"), (w.staff_a2.sub, "email")])
    assert {r["status"] for r in rows} == {"pending"} and {r["attempts"] for r in rows} == {0}

    # gọi lại cùng khóa (Action gọi lại, timer bắn lại): không thêm thông báo, không thêm dòng chờ gửi
    assert notify(w.service_a, "task:kd-1:assigned", (w.staff_a1.sub, ["email", "webhook"])) == []
    count = sql("select count(*) from core.notification_deliveries d join core.notifications n on n.id = "
                f"d.notification_id where n.key = 'task:kd-1:assigned' and n.tenant_id = '{w.tenant_a}'")
    assert count == [["3"]]


def subscribe(service, user: str, channel: str, enabled: bool = True, **extra) -> None:
    row = {"user_id": user, "channel": channel, "enabled": enabled, "zalo_chat_id": None, "link_code": None,
           "link_expires_at": None, **extra}
    service.gql(SAVE, {"row": row})


def test_channel_list_is_checked(people):
    w = people
    with pytest.raises(GraphQLError):
        notify(w.service_a, "task:kd-2:assigned", (w.staff_a1.sub, ["fax"]))
    # cùng một kênh hai lần vẫn chỉ một dòng
    created = notify(w.service_a, "task:kd-3:assigned", (w.staff_a1.sub, ["email", "email"]))
    assert [r["channel"] for r in deliveries(w.service_a, created)] == ["email"]


def test_only_service_of_the_tenant_reads_and_records_the_result(people):
    w = people
    created = notify(w.service_a, "task:kd-4:overdue", (w.staff_a1.sub, ["email"]), kind="task.overdue")
    (row,) = deliveries(w.service_a, created)
    # dịch vụ trong phiên của đơn vị khác không thấy, người dùng không có bảng này trong schema
    assert deliveries(w.service_b, created) == []
    for user in (w.staff_a1, w.director_a, w.admin_a):
        with pytest.raises(GraphQLError):
            user.gql(DELIVERIES, {"ids": [created[0]["id"]]})

    done = {"status": "sent", "attempts": 1, "sent_at": "2026-10-23T09:00:00+07:00"}
    assert w.service_b.gql(DONE, {"id": row["id"], "attempts": 0, "set": done}) == {
        "update_core_notification_deliveries": {"affected_rows": 0}}
    assert w.service_a.gql(DONE, {"id": row["id"], "attempts": 0, "set": done}) == {
        "update_core_notification_deliveries": {"affected_rows": 1}}
    # ghi kết quả lần nữa (bản sao khác, lần chạy lại): khóa theo trạng thái và số lần, không đè
    assert w.service_a.gql(DONE, {"id": row["id"], "attempts": 0, "set": {"status": "failed"}}) == {
        "update_core_notification_deliveries": {"affected_rows": 0}}

    # không thêm, không xóa, không đổi kênh hay người nhận qua GraphQL
    with pytest.raises(GraphQLError):
        w.service_a.gql("mutation ($n: bigint!, $u: String!) { insert_core_notification_deliveries_one(object: "
                        "{notification_id: $n, user_id: $u, channel: \"email\"}) { id } }",
                        {"n": created[0]["id"], "u": w.staff_a1.sub})
    with pytest.raises(GraphQLError):
        w.service_a.gql("mutation { delete_core_notification_deliveries(where: {}) { affected_rows } }")
    with pytest.raises(GraphQLError):
        w.service_a.gql(DONE, {"id": row["id"], "attempts": 1, "set": {"channel": "webhook"}})


def test_sent_needs_sent_at(people):
    w = people
    created = notify(w.service_a, "task:kd-5:assigned", (w.staff_a2.sub, ["email"]))
    (row,) = deliveries(w.service_a, created)
    with pytest.raises(GraphQLError):
        w.service_a.gql(DONE, {"id": row["id"], "attempts": 0, "set": {"status": "sent"}})
    with pytest.raises(SQLError, match="notification_deliveries"):
        sql(f"update core.notification_deliveries set last_error = repeat('x', 201) where id = {row['id']}")


def test_due_query_joins_the_directory_across_tenants(people):
    w = people
    a = notify(w.service_a, "task:kd-6:assigned", (w.staff_a1.sub, ["email"]))
    b = notify(w.service_b, "task:kd-6:assigned", (w.clerk_b.sub, ["webhook"]))
    body = gql_raw(DUE, {"now": "2100-01-01T00:00:00Z", "ids": [a[0]["id"], b[0]["id"]]},
                   headers={"X-Hasura-Admin-Secret": ADMIN_SECRET})
    rows = body["data"]["core_notification_deliveries"]
    assert [(r["tenant_id"], r["channel"]) for r in rows] == [(w.tenant_a, "email"), (w.tenant_b, "webhook")]
    # email và trạng thái lấy từ danh bạ
    assert rows[0]["recipient"]["email"] == f"staff-{w.tag.lower()}@example.com" and rows[0]["recipient"]["enabled"]
    assert rows[0]["notification"]["kind"] == "task.assigned"
    assert rows[1]["recipient"]["email"] is None


def test_each_change_is_in_the_audit_chain(people):
    w = people
    created = notify(w.service_a, "task:kd-7:escalated", (w.director_a.sub, ["email"]), kind="task.escalated")
    (row,) = deliveries(w.service_a, created)
    retry = {"attempts": 1, "last_error": "TimeoutError", "next_attempt_at": "2026-10-23T09:00:00Z"}
    w.service_a.gql(DONE, {"id": row["id"], "attempts": 0, "set": retry})
    actions = sql(f"select action, actor_kind from core.audit_log where entity = 'core.notification_deliveries' "
                  f"and entity_id = '{row['id']}' order by id")
    assert actions == [["insert", "service"], ["update", "service"]]
    # thông báo vẫn không vào sổ (bản tin phái sinh), chỉ lần gửi qua kênh ngoài
    assert sql(f"select count(*) from core.audit_log where entity = 'core.notifications' "
               f"and tenant_id = '{w.tenant_a}'") == [["0"]]


# --- SMS, Zalo (#365) -------------------------------------------------------------------------------------------------

def test_personal_channels_only_for_people_who_turned_them_on(people):
    w = people
    sql(f"update core.users set phone = '{PHONE}' where tenant_id = '{w.tenant_a}' and id = '{w.staff_a1.sub}'")
    subscribe(w.service_a, w.staff_a1.sub, "sms")
    subscribe(w.service_a, w.staff_a1.sub, "zalo", zalo_chat_id="zl-chat-5566")
    subscribe(w.service_a, w.staff_a2.sub, "sms")              # bật SMS nhưng danh bạ chưa có số
    subscribe(w.service_a, w.director_a.sub, "sms", enabled=False)
    created = notify(w.service_a, "task:kd-8:assigned", (w.staff_a1.sub, ["email", "sms", "zalo"]),
                     (w.staff_a2.sub, ["sms", "zalo"]), (w.director_a.sub, ["sms", "zalo"]))
    assert sorted((r["user_id"], r["channel"]) for r in deliveries(w.service_a, created)) == sorted(
        [(w.staff_a1.sub, "email"), (w.staff_a1.sub, "sms"), (w.staff_a1.sub, "zalo")])

    # tài khoản bị khóa: không có dòng SMS, Zalo nữa (email vẫn như trước, vòng nền bỏ qua lúc gửi)
    sql(f"update core.users set enabled = false where tenant_id = '{w.tenant_a}' and id = '{w.staff_a1.sub}'")
    try:
        created = notify(w.service_a, "task:kd-9:assigned", (w.staff_a1.sub, ["email", "sms", "zalo"]))
        assert [r["channel"] for r in deliveries(w.service_a, created)] == ["email"]
    finally:
        sql(f"update core.users set enabled = true where tenant_id = '{w.tenant_a}' and id = '{w.staff_a1.sub}'")

    # vòng nền đọc số điện thoại, chat_id kèm dòng chờ
    first = notify(w.service_a, "task:kd-10:assigned", (w.staff_a1.sub, ["sms", "zalo"]))
    body = gql_raw(DUE, {"now": "2100-01-01T00:00:00Z", "ids": [first[0]["id"]]},
                   headers={"X-Hasura-Admin-Secret": ADMIN_SECRET})
    rows = body["data"]["core_notification_deliveries"]
    assert [r["channel"] for r in rows] == ["sms", "zalo"]
    assert rows[0]["recipient"]["phone"] == PHONE
    assert sorted((x["channel"], x["zalo_chat_id"]) for x in rows[1]["subscriptions"]) == [
        ("sms", None), ("zalo", "zl-chat-5566")]


def test_subscription_rows_are_checked(people):
    w = people
    later = "2100-01-01T00:00:00Z"
    bad = [
        {"channel": "zalo", "enabled": True},                                    # bật Zalo mà chưa liên kết
        {"channel": "sms", "zalo_chat_id": "zl-1"},                              # chat_id chỉ của Zalo
        {"channel": "sms", "link_code": "ABCD2345", "link_expires_at": later},
        {"channel": "zalo", "link_code": "abcd2345", "link_expires_at": later},  # chữ thường
        {"channel": "zalo", "link_code": "ABCD1234", "link_expires_at": later},  # có 1: dễ nhầm với I
        {"channel": "zalo", "link_code": "ABCD2345"},                            # mã thiếu hạn
        {"channel": "fax"},
    ]
    for row in bad:
        with pytest.raises(GraphQLError):
            subscribe(w.service_a, w.staff_a2.sub, **{"enabled": False, **row})
    with pytest.raises(GraphQLError):                                            # chưa có trong danh bạ
        subscribe(w.service_a, f"khong-co-{w.tag}", "sms")
    # mã liên kết duy nhất trên mọi đơn vị: vòng đọc tin của bot tìm mã không cần biết đơn vị
    code = f"Q{w.tag}Z".translate(str.maketrans("01", "23"))     # tag: 6 chữ số hex hoa → 8 ký tự hợp lệ
    subscribe(w.service_a, w.staff_a2.sub, "zalo", enabled=False, link_code=code, link_expires_at=later)
    with pytest.raises(GraphQLError):
        subscribe(w.service_b, w.clerk_b.sub, "zalo", enabled=False, link_code=code, link_expires_at=later)
    with pytest.raises(SQLError, match="users_phone"):
        sql(f"update core.users set phone = '0912345678' where tenant_id = '{w.tenant_a}' and id = '{w.staff_a2.sub}'")


def test_only_service_of_the_tenant_sees_subscriptions_and_phones(people):
    w = people
    subscribe(w.service_a, w.director_a.sub, "sms", enabled=True)
    users = [w.director_a.sub]
    assert w.service_a.gql(SUBS, {"users": users})["core_notification_subscriptions"] == [
        {"user_id": w.director_a.sub, "channel": "sms", "enabled": True, "zalo_chat_id": None, "link_code": None}]
    assert w.service_b.gql(SUBS, {"users": users})["core_notification_subscriptions"] == []
    for user in (w.director_a, w.staff_a1, w.admin_a):
        with pytest.raises(GraphQLError):
            user.gql(SUBS, {"users": users})
    # số điện thoại: dịch vụ đọc được, người trong đơn vị (chọn người giao việc) thì không
    phones = "query ($id: String!) { core_users(where: {id: {_eq: $id}}) { id phone } }"
    assert w.service_a.gql(phones, {"id": w.staff_a1.sub})["core_users"][0]["id"] == w.staff_a1.sub
    for user in (w.staff_a2, w.admin_a):
        with pytest.raises(GraphQLError):
            user.gql(phones, {"id": w.staff_a1.sub})
    assert w.admin_a.gql("query ($id: String!) { core_users(where: {id: {_eq: $id}}) { id } }",
                         {"id": w.staff_a1.sub})["core_users"] == [{"id": w.staff_a1.sub}]


def test_subscription_changes_are_in_the_audit_chain(people):
    w = people
    subscribe(w.service_b, w.clerk_b.sub, "sms", enabled=False)
    subscribe(w.service_b, w.clerk_b.sub, "sms", enabled=True)
    subscribe(w.service_b, w.clerk_b.sub, "sms", enabled=True)          # không đổi gì: không thêm dòng sổ
    rows = sql("select action, actor_kind from core.audit_log where entity = 'core.notification_subscriptions' "
               f"and entity_id = '{w.tenant_b}/{w.clerk_b.sub}/sms' order by id")
    assert rows == [["insert", "service"], ["update", "service"]]
