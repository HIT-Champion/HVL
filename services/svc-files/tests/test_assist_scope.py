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

"""Lọc trước theo vai trò (F4.2): chuỗi lọc Meilisearch đúng từng vai trò, giá trị được thoát, và bảng chân trị
``visible_in_index`` ↔ ``office.document_visible`` (các ca của db/tests/test_permissions.py + lưới đủ tổ hợp)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import pytest

from conftest import TENANT_A, meili_filter
from svc_files.assist.chunks import build
from svc_files.assist.scope import NOTHING, Scope, service_scope, user_scope, visible_in_index

A1, A2 = "dep-a1", "dep-a2"


@dataclass(frozen=True)
class User:
    sub: str
    role: str
    department_id: str | None


CLERK = User("u-van-thu", "clerk", None)
DIRECTOR = User("u-giam-doc", "director", None)
MANAGER_A1 = User("u-truong-a1", "manager", A1)
MANAGER_A2 = User("u-truong-a2", "manager", A2)
STAFF_A1 = User("u-cv-a1", "staff", A1)
STAFF_A1B = User("u-cv-a1b", "staff", A1)
STAFF_A2 = User("u-cv-a2", "staff", A2)
LOST_STAFF = User("u-thieu-phong", "staff", None)       # token thiếu department_id
LOST_MANAGER = User("u-truong-thieu-phong", "manager", None)
ADMIN = User("u-quan-tri", "tenant_admin", None)
USERS = [CLERK, DIRECTOR, MANAGER_A1, MANAGER_A2, STAFF_A1, STAFF_A1B, STAFF_A2, LOST_STAFF, LOST_MANAGER, ADMIN]


def document_visible(doc: dict, user: User, acl: frozenset[str] = frozenset()) -> bool:
    """Chép tay office.document_visible (migration 0200) — đối chiếu, không phải mã chạy thật."""
    if doc["tenant_id"] != str(TENANT_A):
        return False
    if doc["restricted"] and doc["created_by"] != user.sub and user.sub not in acl:
        return False
    live = [a for a in doc["assignments"] if a.get("status", "open") != "cancelled"]
    match user.role:
        case "clerk" | "director":
            return True
        case "manager":
            return user.department_id is not None and (
                doc["department_id"] == user.department_id
                or any(a.get("department_id") == user.department_id for a in live))
        case "staff":
            return (doc["created_by"] == user.sub
                    or (doc["direction"] == "out" and user.department_id is not None
                        and doc["department_id"] == user.department_id)
                    or any(a.get("user_id") == user.sub for a in live))
        case _:
            return False


def document(*, direction="in", department_id=None, created_by=CLERK.sub, assignments=()) -> dict:
    status = "issued" if direction == "out" else "registered"      # đủ điều kiện vào chỉ mục: quyền không xét
    return {"id": "d0000000-0000-4000-8000-000000000001", "tenant_id": str(TENANT_A), "direction": direction,
            "status": status, "type_code": "CV", "symbol": "1/X", "issuer_name": "UBND", "issued_on": "2026-10-15",
            "summary": "Văn bản thử quyền", "restricted": False, "department_id": department_id,
            "created_by": created_by, "updated_at": "2026-10-21T08:00:00+00:00", "assignments": list(assignments),
            "files": []}


def check(doc: dict, user: User) -> bool:
    """Ba cách phải cùng kết quả: quy tắc CSDL, vị từ visible_in_index, bộ lọc Meilisearch trên đoạn thật."""
    expected = document_visible(doc, user)
    scope = user_scope(role=user.role, user_id=user.sub, tenant_id=TENANT_A, department_id=user.department_id,
                       token="t")
    if scope is None:
        assert expected is False, user
        return False
    chunk = build(doc)[0]
    by_filter = scope.where != NOTHING and meili_filter([f'tenant_id = "{TENANT_A}"', *scope.where], chunk)
    by_predicate = visible_in_index(role=user.role, user_id=user.sub, department_id=user.department_id, chunk=chunk)
    assert by_filter == by_predicate == expected, (user, doc)
    return expected


# --- chuỗi lọc -----------------------------------------------------------------------------------------------------


def test_filter_strings_per_role():
    def where(user: User) -> tuple[str, ...] | None:
        scope = user_scope(role=user.role, user_id=user.sub, tenant_id=TENANT_A, department_id=user.department_id,
                           token="tok")
        return None if scope is None else scope.where

    assert where(CLERK) == () and where(DIRECTOR) == ()
    assert where(MANAGER_A1) == ('(department_id = "dep-a1" OR assignee_departments = "dep-a1")',)
    assert where(STAFF_A1) == ('(created_by = "u-cv-a1" OR assignee_users = "u-cv-a1"'
                               ' OR (direction = "out" AND department_id = "dep-a1"))',)
    assert where(LOST_STAFF) == ('(created_by = "u-thieu-phong" OR assignee_users = "u-thieu-phong")',)
    assert where(LOST_MANAGER) == NOTHING
    for role in ("tenant_admin", "service", "agent", "verifier", ""):
        assert user_scope(role=role, user_id="u", tenant_id=TENANT_A, department_id=A1, token="t") is None


def test_scope_carries_tenant_and_token():
    scope = user_scope(role="clerk", user_id="u", tenant_id=TENANT_A, department_id=None, token="tok")
    assert scope == Scope(TENANT_A, (), "tok")
    assert service_scope(TENANT_A) == Scope(TENANT_A, (), None)


def test_values_with_quotes_and_backslashes_are_escaped():
    sub = 'u"x\\y'
    scope = user_scope(role="staff", user_id=sub, tenant_id=TENANT_A, department_id=None, token="t")
    assert scope.where == ('(created_by = "u\\"x\\\\y" OR assignee_users = "u\\"x\\\\y")',)
    assert meili_filter(list(scope.where), {"created_by": sub, "assignee_users": []})
    assert not meili_filter(list(scope.where), {"created_by": "u", "assignee_users": ["x\\y"]})


def test_a_crafted_department_cannot_widen_the_filter():
    crafted = 'dep-a1" OR tenant_id != "khac'
    scope = user_scope(role="manager", user_id="u", tenant_id=TENANT_A, department_id=crafted, token="t")
    assert not meili_filter(list(scope.where), {"department_id": A2, "assignee_departments": [], "tenant_id": "x"})
    assert meili_filter(list(scope.where), {"department_id": crafted, "assignee_departments": []})


# --- bảng chân trị ------------------------------------------------------------------------------------------------


def test_outgoing_document_is_visible_within_its_department():
    # test_outgoing_draft_visible_within_department_only (+ người thiếu phòng: test_user_without_department_claim…)
    doc = document(direction="out", department_id=A1, created_by=STAFF_A1.sub)
    for user in (STAFF_A1, STAFF_A1B, MANAGER_A1, DIRECTOR, CLERK):
        assert check(doc, user), user
    for user in (STAFF_A2, MANAGER_A2, LOST_STAFF, LOST_MANAGER, ADMIN):
        assert not check(doc, user), user


def test_assignments_grant_visibility():
    # test_assignment_grants_visibility
    doc = document(direction="in", created_by=CLERK.sub)
    assert not check(doc, MANAGER_A2) and not check(doc, STAFF_A2)
    lead = {"department_id": A2, "user_id": None, "assigned_at": "2026-10-21T08:00:00+00:00"}
    doc = document(direction="in", created_by=CLERK.sub, assignments=[lead])
    assert check(doc, MANAGER_A2) and not check(doc, STAFF_A2)
    support = {"department_id": None, "user_id": STAFF_A2.sub, "assigned_at": "2026-10-21T08:01:00+00:00"}
    doc = document(direction="in", created_by=CLERK.sub, assignments=[lead, support])
    assert check(doc, STAFF_A2) and not check(doc, STAFF_A1)


def test_cancelled_assignments_grant_nothing():
    cancelled = [{"department_id": A2, "user_id": STAFF_A2.sub, "assigned_at": "2026-10-21T08:00:00+00:00",
                  "status": "cancelled"}]
    doc = document(direction="in", created_by=CLERK.sub, assignments=cancelled)
    assert not check(doc, MANAGER_A2) and not check(doc, STAFF_A2)


def test_incoming_document_of_own_department_is_not_visible_to_staff():
    # staff thấy theo phòng chỉ với văn bản đi; văn bản đến cần giao việc cho chính mình
    doc = document(direction="in", department_id=A1, created_by=CLERK.sub)
    assert check(doc, MANAGER_A1) and not check(doc, STAFF_A1)


def test_tenant_admin_reads_nothing():
    # test_tenant_admin_cannot_read_documents_but_manages_departments
    assert user_scope(role="tenant_admin", user_id=ADMIN.sub, tenant_id=TENANT_A, department_id=None,
                      token="t") is None
    assert not visible_in_index(role="tenant_admin", user_id=ADMIN.sub, department_id=None,
                                chunk=build(document())[0])


ASSIGNMENT_SETS = [
    (),
    ({"department_id": A1, "user_id": None},),
    ({"department_id": A2, "user_id": None, "status": "cancelled"},),
    ({"department_id": None, "user_id": STAFF_A2.sub},),
    ({"department_id": None, "user_id": STAFF_A1.sub, "status": "cancelled"},),
    ({"department_id": A2, "user_id": None}, {"department_id": A2, "user_id": STAFF_A1B.sub}),
]


@pytest.mark.parametrize(("direction", "department_id", "created_by", "assignments"), list(itertools.product(
    ("in", "out"), (None, A1, A2), (CLERK.sub, STAFF_A1.sub, STAFF_A2.sub), ASSIGNMENT_SETS)))
def test_truth_table_matches_document_visible(direction, department_id, created_by, assignments):
    doc = document(direction=direction, department_id=department_id, created_by=created_by,
                   assignments=[{**a, "assigned_at": "2026-10-21T08:00:00+00:00"} for a in assignments])
    for user in USERS:
        check(doc, user)
