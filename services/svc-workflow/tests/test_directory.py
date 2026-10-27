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

"""Đồng bộ danh bạ Keycloak → core.users: chỉ ghi dòng đổi, người bị xóa thì khóa chứ không xóa."""

from __future__ import annotations

import asyncio

import pytest

from conftest import DEPT_DT, TENANT
from svc_workflow.directory import Directory, phone, to_row


def kc_user(uid: str, role: str = "staff", tenant: str = str(TENANT), *, phone_number: str | None = None,
            **extra) -> dict:
    attrs = {"tenant_id": [tenant], "moc_role": [role], "department_id": [str(DEPT_DT)]}
    if phone_number is not None:
        attrs["phone_number"] = [phone_number]
    return {"id": uid, "username": uid, "firstName": "Nguyễn Văn", "lastName": "An", "email": f"{uid}@x.vn",
            "enabled": True, "attributes": attrs, **extra}


def test_mapping_puts_vietnamese_name_in_order():
    tenant, row = to_row(kc_user("u1"))
    assert tenant == TENANT and row["full_name"] == "Nguyễn Văn An" and row["role"] == "staff"


def test_users_without_tenant_or_with_unknown_role_are_skipped():
    assert to_row(kc_user("u1", role="admin")) is None            # vai trò có sẵn của Hasura: không bao giờ nhận
    assert to_row(kc_user("u1", tenant="khong-phai-uuid")) is None
    assert to_row({"id": "svc", "username": "service-account-svc-workflow", "attributes": {}}) is None


class FakeHasura:
    def __init__(self, current):
        self.current = current
        self.upserts = []

    async def as_service(self, actor, query, variables=None):
        if "TenantUsers" in query:
            return {"core_users": self.current}
        self.upserts.append(variables["rows"])
        return {}


def directory_with(users, current):
    hasura = FakeHasura(current)
    d = Directory("http://kc", "moc", "svc-workflow", "s", hasura)  # type: ignore[arg-type]

    async def fetch():
        return users
    d.fetch_users = fetch  # type: ignore[method-assign]
    return d, hasura


def test_only_changed_rows_are_written_and_missing_users_disabled():
    _, same = to_row(kc_user("u-same"))
    _, old = to_row(kc_user("u-renamed"))
    _, gone = to_row(kc_user("u-gone"))
    users = [kc_user("u-same"), kc_user("u-renamed", firstName="Trần Thị"), kc_user("u-new", role="manager")]
    d, hasura = directory_with(users, [same, old, gone])
    assert asyncio.run(d.sync_once()) == 3
    written = {r["id"]: r for r in hasura.upserts[0]}
    assert set(written) == {"u-renamed", "u-new", "u-gone"}
    assert written["u-renamed"]["full_name"] == "Trần Thị An" and written["u-gone"]["enabled"] is False


def test_nothing_written_when_in_sync():
    _, row = to_row(kc_user("u1"))
    d, hasura = directory_with([kc_user("u1")], [row])
    assert asyncio.run(d.sync_once()) == 0 and hasura.upserts == []



# số điện thoại giả lập
@pytest.mark.parametrize(("given", "stored"), [
    ("0912 345 678", "+84912345678"), ("+84 912.345.678", "+84912345678"), ("(0912) 345-678", "+84912345678"),
    ("0084912345678", "+84912345678"), ("+12025550123", "+12025550123"), ("", None), (None, None),
    ("12345", None), ("+0912345678", None), ("09123abc45", None), ("0912345678901234567", None),
])
def test_phone_numbers_become_e164_or_nothing(given, stored):
    assert phone(given) == stored


def test_phone_is_synced_and_a_change_is_written():
    _, row = to_row(kc_user("u1", phone_number="0912345678"))
    assert row["phone"] == "+84912345678"
    d, hasura = directory_with([kc_user("u1", phone_number="0987654321")], [row])
    assert asyncio.run(d.sync_once()) == 1
    assert hasura.upserts[0][0]["phone"] == "+84987654321"
    assert to_row(kc_user("u2"))[1]["phone"] is None
