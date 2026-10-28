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

"""Robot của flow tự động hóa (tu_dong.py, #366): Action notifyFromFlow chỉ cho vai trò tu_dong, báo người trong đơn
vị theo vai trò, chống trùng theo khóa, từ chối văn bản của đơn vị khác, văn bản hạn chế; nhật ký không có tiêu đề, lời
nhắn.

Họ tên, số điện thoại, số CCCD trong tệp này là giả lập."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import OTHER, SCHEMAS, TENANT, FakeHasura
from svc_workflow.app import create_app
from svc_workflow.channels import describe
from svc_workflow.config import Settings
from svc_workflow.tu_dong import KIND, BadInput, parse
from test_channels import raw_log

SECRET = "bi-mat-action"
ROBOT = "tu-dong-robot-cntt"
ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": SECRET, "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_DIRECTORY_SYNC_INTERVAL_S": "0", "MOC_RECONCILE_INTERVAL_S": "0",
    "MOC_PROCESSES_DIR": "/khong-co", "MOC_SCHEMAS_DIR": str(SCHEMAS), "MOC_NOTIFY_INTERVAL_S": "0",
    "MOC_SLA_POLL_INTERVAL_S": "0", "MOC_SUGGEST_POLL_INTERVAL_S": "0", "MOC_OFFICE_ENABLED": "false",
}
OPEN = "aaaaaaaa-0000-4000-8000-000000000001"
SEALED = "aaaaaaaa-0000-4000-8000-000000000002"
ELSEWHERE = "aaaaaaaa-0000-4000-8000-000000000003"
INPUT = {"roles": ["director", "manager"], "title": "Hợp đồng thuê máy chủ sắp hết hạn", "key": "hop-dong:42"}


@dataclass
class Hasura(FakeHasura):
    """FakeHasura cộng câu FlowDocument: quyền service chỉ thấy văn bản của đơn vị trong phiên. Ghi mọi lần gọi."""

    docs: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, str, str]] = field(default_factory=list)     # (câu, vai trò, người làm)
    boom: bool = False

    async def as_service(self, actor, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        op = query.split("(")[0].split()[1] if query.strip().startswith(("query", "mutation")) else ""
        self.calls.append((op, actor.role, actor.user_id))
        if self.boom:
            raise RuntimeError("lỗi lạ")
        if op == "FlowDocument":
            doc = self.docs.get((variables or {})["id"])
            seen = doc is not None and doc["tenant_id"] == actor.tenant_id
            return {"office_documents_by_pk": {k: v for k, v in doc.items() if k != "tenant_id"} if seen else None}
        return await super().as_service(actor, query, variables)


def user(uid: str, role: str, enabled: bool = True) -> dict[str, Any]:
    return {"id": uid, "department_id": None, "role": role, "enabled": enabled}


@pytest.fixture
def store(hasura) -> Hasura:
    """Người của đơn vị trong conftest (một lãnh đạo, một văn thư, một lãnh đạo phòng, hai chuyên viên), thêm lãnh đạo
    thứ hai, một lãnh đạo đã khóa, một quản trị; ở đơn vị khác có một lãnh đạo."""
    s = Hasura(users={**hasura.users, "u-director-2": user("u-director-2", "director"),
                      "u-director-cu": user("u-director-cu", "director", enabled=False),
                      "u-admin": user("u-admin", "tenant_admin")})
    s.tenant_users[OTHER] = {"u-director-kt": user("u-director-kt", "director")}
    s.docs = {
        OPEN: {"id": OPEN, "tenant_id": TENANT, "restricted": False, "summary": "Gia hạn hợp đồng máy chủ",
               "symbol": "12/TB-CNTT", "urgency": "khan", "direction": "in"},
        SEALED: {"id": SEALED, "tenant_id": TENANT, "restricted": True, "summary": "Hồ sơ nhân sự",
                 "symbol": "3/QĐ-CNTT", "urgency": "normal", "direction": "in"},
        ELSEWHERE: {"id": ELSEWHERE, "tenant_id": OTHER, "restricted": False, "summary": "Văn bản của Khoa Kinh tế",
                    "symbol": "7/TB-KT", "urgency": "normal", "direction": "in"},
    }
    return s


class _NoDirectory:
    async def aclose(self) -> None: ...


def app_for(store: Hasura, flowable, env: dict[str, str] | None = None):
    return create_app(Settings.from_env({**ENV, **(env or {})}), hasura=store, flowable=flowable,  # type: ignore
                      directory=_NoDirectory())  # type: ignore[arg-type]


def body(role: str = "tu_dong", robot: str = ROBOT, tenant: uuid.UUID = TENANT, name: str = "notifyFromFlow",
         **payload: Any) -> dict[str, Any]:
    return {"action": {"name": name}, "input": {**INPUT, **payload},
            "session_variables": {"x-hasura-role": role, "x-hasura-user-id": robot, "x-hasura-tenant-id": str(tenant)}}


def call(client: TestClient, data: dict[str, Any], secret: str | None = SECRET, name: str = "notifyFromFlow",
         **headers: str):
    if secret is not None:
        headers["X-Moc-Action-Secret"] = secret
    return client.post(f"/actions/tu-dong/{name}", json=data, headers=headers)


def error(r) -> tuple[int, str, dict[str, str] | None]:
    ext = r.json()["extensions"]
    return r.status_code, ext["code"], ext.get("fields")


# --- gửi --------------------------------------------------------------------------------------------------------------

def test_robot_notifies_everyone_with_the_chosen_roles_in_its_unit(store, flowable):
    with TestClient(app_for(store, flowable)) as c:
        r = call(c, body())
    assert (r.status_code, r.json()) == (200, {"sent": 3})
    # hợp của hai vai trò; không người đã khóa, không vai trò khác, không ai ở đơn vị khác
    assert {n["user_id"] for n in store.notifications} == {"u-director", "u-director-2", "u-manager-dt"}
    for n in store.notifications:
        assert (n["kind"], n["key"], n["document_id"], n["tenant_id"]) == (
            KIND, f"flow:{ROBOT}:hop-dong:42", None, TENANT)
        assert n["data"] == {"title": INPUT["title"], "robot": ROBOT}
    # mọi lần đọc, ghi bằng vai trò service, người làm là robot
    assert store.calls == [("People", "service", ROBOT), ("Notify", "service", ROBOT)]


def test_same_key_notifies_nobody_twice(store, flowable):
    with TestClient(app_for(store, flowable)) as c:
        assert call(c, body()).json() == {"sent": 3}
        assert call(c, body()).json() == {"sent": 0}                    # Node-RED gửi lại, flow chạy lại
        assert call(c, body(roles=["director", "clerk"])).json() == {"sent": 1}   # chỉ văn thư là người mới
        assert call(c, body(key="hop-dong:43")).json() == {"sent": 3}
    assert len(store.notifications) == 7


def test_keys_of_two_robots_do_not_collide(store, flowable):
    with TestClient(app_for(store, flowable)) as c:
        assert call(c, body()).json() == {"sent": 3}
        assert call(c, body(robot="tu-dong-robot-khac")).json() == {"sent": 3}
    assert {n["key"] for n in store.notifications} == {f"flow:{ROBOT}:hop-dong:42",
                                                       "flow:tu-dong-robot-khac:hop-dong:42"}


def test_document_brief_and_text_ride_along(store, flowable):
    with TestClient(app_for(store, flowable)) as c:
        r = call(c, body(roles=["director", "clerk"], document_id=OPEN.upper(), text="Dòng 1\r\nDòng 2\x07  "))
    assert r.json() == {"sent": 3}
    assert {n["user_id"] for n in store.notifications} == {"u-director", "u-director-2", "u-clerk"}
    n = store.notifications[0]
    assert n["document_id"] == OPEN
    assert n["data"] == {"summary": "Gia hạn hợp đồng máy chủ", "symbol": "12/TB-CNTT", "urgency": "khan",
                         "direction": "in", "title": INPUT["title"], "robot": ROBOT, "text": "Dòng 1\nDòng 2"}
    assert store.calls[0] == ("FlowDocument", "service", ROBOT)


@pytest.mark.parametrize("text", ["", "   ", "\r\n\t\x00", None])
def test_empty_text_is_left_out(store, flowable, text):
    with TestClient(app_for(store, flowable)) as c:
        assert call(c, body(text=text)).json() == {"sent": 3}
    assert all("text" not in n["data"] for n in store.notifications)


def test_document_of_another_unit_is_not_found(store, flowable):
    with TestClient(app_for(store, flowable)) as c:
        r = call(c, body(roles=["director"], document_id=ELSEWHERE))
        assert error(r)[:2] == (404, "not_found")
        assert error(call(c, body(roles=["director"], document_id=str(uuid.uuid4()))))[:2] == (404, "not_found")
    assert store.notifications == [] and {op for op, _, _ in store.calls} == {"FlowDocument"}


def test_restricted_document_is_refused(store, flowable):
    with TestClient(app_for(store, flowable)) as c:
        r = call(c, body(roles=["director"], document_id=SEALED))
    assert error(r)[:2] == (403, "forbidden") and "hạn chế" in r.json()["message"]
    assert store.notifications == [] and [op for op, _, _ in store.calls] == ["FlowDocument"]


@pytest.mark.parametrize("roles", [["director", "manager"], ["staff"], ["clerk", "tenant_admin"]])
def test_with_a_document_only_roles_that_see_every_document(store, flowable, roles):
    """Lãnh đạo phòng, chuyên viên, quản trị có thể không xem được văn bản: trích yếu, số ký hiệu không tới họ."""
    with TestClient(app_for(store, flowable)) as c:
        r = call(c, body(roles=roles, document_id=OPEN))
    assert error(r) == (422, "invalid", {"roles": "document_readers_only"})
    assert store.calls == [] and store.notifications == []          # từ chối trước khi đọc gì


# --- từ chối ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("secret", [None, "", "sai", SECRET + "x"])
def test_wrong_secret_is_401(store, flowable, secret):
    with TestClient(app_for(store, flowable)) as c:
        r = call(c, body(), secret=secret)
    assert error(r)[:2] == (401, "unauthorized") and store.calls == []


@pytest.mark.parametrize("role", ["clerk", "director", "tenant_admin", "service", "agent"])
def test_only_the_robot_role_may_call(store, flowable, role):
    with TestClient(app_for(store, flowable)) as c:
        r = call(c, body(role=role, robot="u-clerk"))
    assert error(r)[:2] == (403, "forbidden") and "tu_dong" in r.json()["message"]
    assert store.calls == []


def test_malformed_requests_are_400(store, flowable):
    with TestClient(app_for(store, flowable)) as c:
        headers = {"X-Moc-Action-Secret": SECRET}
        assert c.post("/actions/tu-dong/notifyFromFlow", content=b"{khong-phai-json",
                      headers=headers).status_code == 400
        assert c.post("/actions/tu-dong/notifyFromFlow", json=[], headers=headers).status_code == 400
        assert error(call(c, body(), name="khac"))[:2] == (400, "bad_request")          # tên không khớp đường dẫn
        assert error(call(c, body(name="khac"), name="khac"))[:2] == (400, "bad_request")   # không có Action này
        no_tenant = body()
        del no_tenant["session_variables"]["x-hasura-tenant-id"]
        assert error(call(c, no_tenant))[:2] == (400, "bad_request")
        r = call(c, {**body(), "input": None})
        assert error(r) == (400, "bad_request", {"input": "type"})
        r = call(c, body(roles=["admin"]))
        assert error(r) == (400, "bad_request", {"roles": "enum"})
    assert store.calls == []


def test_session_variable_names_are_case_insensitive(store, flowable):
    data = body()
    data["session_variables"] = {k.replace("x-hasura", "X-Hasura"): v for k, v in data["session_variables"].items()}
    with TestClient(app_for(store, flowable)) as c:
        assert call(c, data).json() == {"sent": 3}


def test_database_down_is_503_and_surprises_are_500_with_the_request_id(store, flowable):
    store.fail_notify = True
    with TestClient(app_for(store, flowable)) as c:
        assert error(call(c, body()))[:2] == (503, "unavailable")
        store.boom = True
        r = call(c, body(), **{"X-Request-Id": "req-tu-dong-1"})
    assert error(r)[:2] == (500, "internal") and r.json()["message"].endswith("req-tu-dong-1")


def test_route_is_there_with_the_office_on_too(store, flowable):
    app = app_for(store, flowable, {"MOC_OFFICE_ENABLED": "true"})
    responses = app.openapi()["paths"]["/actions/tu-dong/{name}"]["post"]["responses"]
    assert {"200", "400", "401", "403", "404", "422", "500", "503"} <= set(responses)
    with TestClient(app) as c:
        assert call(c, body()).json() == {"sent": 3}


# --- kiểm đối số ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("change", "fields"), [
    ({"roles": None}, ("roles", "required")),
    ({"roles": "director"}, ("roles", "type")),
    ({"roles": [1]}, ("roles", "type")),
    ({"roles": []}, ("roles", "minItems")),
    ({"roles": ["director"] * 6}, ("roles", "maxItems")),
    ({"roles": ["director", "giam_doc"]}, ("roles", "enum")),
    ({"roles": ["clerk", "clerk"]}, ("roles", "uniqueItems")),
    ({"title": None}, ("title", "required")),
    ({"title": 42}, ("title", "type")),
    ({"title": " \n\t\x00 "}, ("title", "minLength")),
    ({"title": "x" * 121}, ("title", "maxLength")),
    ({"text": ["a"]}, ("text", "type")),
    ({"text": "x" * 1001}, ("text", "maxLength")),
    ({"document_id": "khong-phai-uuid"}, ("document_id", "format")),
    ({"document_id": 42}, ("document_id", "type")),
    ({"key": None}, ("key", "required")),
    ({"key": ""}, ("key", "minLength")),
    ({"key": "k" * 101}, ("key", "maxLength")),
    ({"key": "có-dấu"}, ("key", "pattern")),
    ({"key": "a/b"}, ("key", "pattern")),
    ({"key": "a b"}, ("key", "pattern")),
    ({"key": "a\n"}, ("key", "pattern")),
])
def test_bad_input_names_the_field(change, fields):
    payload = {k: v for k, v in {**INPUT, "roles": ["director"], **change}.items() if v is not None}
    with pytest.raises(BadInput) as err:
        parse(payload, ROBOT)
    assert (err.value.field, err.value.code, err.value.status) == (*fields, 400)


def test_input_at_the_limits_is_accepted():
    notice = parse({"roles": ["director", "manager", "clerk", "staff", "tenant_admin"], "title": "x" * 120 + "\n\n",
                    "text": "y" * 1000, "key": "k" * 100}, ROBOT)
    assert len(notice.title) == 120 and len(notice.text or "") == 1000 and notice.key == f"flow:{ROBOT}:{'k' * 100}"
    assert parse({**INPUT, "key": "Ab0._:-"}, ROBOT).key == f"flow:{ROBOT}:Ab0._:-"
    with pytest.raises(BadInput) as err:                             # khóa đủ dài cộng tên robot quá 200 ký tự
        parse({**INPUT, "key": "k" * 100}, "r" * 95)
    assert (err.value.field, err.value.code) == ("key", "maxLength")


def test_title_and_text_are_cleaned():
    notice = parse({**INPUT, "title": " Hợp\tđồng\n\x00 sắp\u202e hết\x85 hạn ",
                    "text": "\r\n  Dòng 1\r\n\tDòng 2\x1b[31m\u2066  \n"}, ROBOT)
    assert notice.title == "Hợp đồng sắp hết hạn"
    assert notice.text == "Dòng 1\n Dòng 2[31m"
    assert parse({**INPUT, "text": " \r\n "}, ROBOT).text is None


def test_without_a_document_every_role_is_allowed():
    roles = ["director", "manager", "clerk", "staff", "tenant_admin"]
    assert parse({**INPUT, "roles": roles}, ROBOT).roles == tuple(roles)
    assert parse({**INPUT, "roles": ["clerk", "director"], "document_id": OPEN}, ROBOT).document_id == OPEN


# --- nhật ký, câu chữ -------------------------------------------------------------------------------------------------

def test_log_line_has_ids_only(store, flowable):
    app = app_for(store, flowable)              # dựng trước raw_log: create_app gắn lại bộ che PII
    title, text = "Gọi Nguyễn Văn An 0912345678", "CCCD 001099012345 hết hạn"     # giả lập
    with raw_log() as stream, TestClient(app) as c:
        call(c, body(roles=["director", "clerk"], title=title, text=text, document_id=OPEN),
             **{"X-Request-Id": "req-tu-dong-2"})
    lines = [json.loads(x) for x in stream.getvalue().splitlines() if '"tu_dong.notify"' in x]
    assert lines == [{"event": "tu_dong.notify", "tenant_id": str(TENANT), "robot": ROBOT,
                      "roles": ["director", "clerk"], "sent": 3, "document_id": OPEN, "request_id": "req-tu-dong-2"}]
    for value in (title, text, "Nguyễn", "0912345678", "001099012345"):
        assert value not in stream.getvalue()


def test_bell_text_for_email_and_shared_channels():
    data = {"summary": "Gia hạn hợp đồng máy chủ", "symbol": "12/TB-CNTT", "title": "Hợp đồng\nsắp hết hạn",
            "robot": ROBOT, "text": "Liên hệ phòng Hành chính"}
    shown = describe(KIND, data)
    assert (shown.title, shown.detail, shown.note) == ("Tự động: Hợp đồng sắp hết hạn", "Liên hệ phòng Hành chính", "")
    shared = describe(KIND, data, names=False)                        # webhook, SMS, Zalo: không lời nhắn
    assert shared.detail == "12/TB-CNTT — Gia hạn hợp đồng máy chủ"
    assert describe(KIND, {"title": "Sao lưu xong", "robot": ROBOT}).detail == ""
