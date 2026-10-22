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

"""Phạm vi truy xuất của trợ lý hỏi đáp (F4.2): lớp lọc trước trong Meilisearch theo vai trò người hỏi.

Viết đúng như ``office.document_visible`` (migration 0200) trên thuộc tính quyền chép vào từng đoạn (chunks.py):

- ``clerk``, ``director``: mọi văn bản của thuê ước;
- ``manager``: văn bản của phòng mình, hoặc có giao việc chưa hủy cho phòng mình; token thiếu phòng → không gì;
- ``staff``: mình tạo, hoặc có giao việc chưa hủy cho mình, hoặc văn bản đi của phòng mình;
- vai trò khác (``tenant_admin``…): không được hỏi.

Văn bản hạn chế không bao giờ vào chỉ mục nên không cần ACL. Lớp này chỉ quyết **độ phủ**: chỉ mục chậm vài giây
hoặc lệch quy tắc thì thiếu kết quả, không lộ — an toàn do hậu kiểm bằng Hasura với token người hỏi (retrieve.py).
Mọi giá trị đi qua ``search._quoted``: không ghép được thêm điều kiện vào bộ lọc.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..search import _quoted

READ_ALL = frozenset({"clerk", "director"})
ROLES = READ_ALL | {"manager", "staff"}

# không đoạn nào khớp (mọi đoạn đều có kind): truy xuất thấy điều kiện này thì không gọi Meilisearch
NOTHING: tuple[str, ...] = ("kind IS NULL",)


@dataclass(frozen=True)
class Scope:
    tenant_id: uuid.UUID
    where: tuple[str, ...]   # điều kiện Meilisearch theo vai trò, đứng sau điều kiện thuê ước
    token: str | None        # có: hậu kiểm bằng token người hỏi · None: phạm vi dịch vụ (F4.3)


def user_scope(*, role: str, user_id: str, tenant_id: uuid.UUID, department_id: str | None,
               token: str) -> Scope | None:
    """Phạm vi của người hỏi; None khi vai trò không được hỏi (API trả 403)."""
    if role in READ_ALL:
        return Scope(tenant_id, (), token)
    if role == "manager":
        if not department_id:
            return Scope(tenant_id, NOTHING, token)
        d = _quoted(department_id)
        return Scope(tenant_id, (f"(department_id = {d} OR assignee_departments = {d})",), token)
    if role == "staff":
        u = _quoted(user_id)
        parts = [f"created_by = {u}", f"assignee_users = {u}"]
        if department_id:
            parts.append(f'(direction = "out" AND department_id = {_quoted(department_id)})')
        return Scope(tenant_id, ("(" + " OR ".join(parts) + ")",), token)
    return None


def service_scope(tenant_id: uuid.UUID) -> Scope:
    """Phạm vi dịch vụ (F4.3 gợi ý giao việc): cả thuê ước, hậu kiểm bằng vai trò service, bỏ văn bản hạn chế."""
    return Scope(tenant_id, (), None)


def visible_in_index(*, role: str, user_id: str, department_id: str | None, chunk: Mapping[str, Any]) -> bool:
    """Vị từ tương đương ``user_scope(...).where`` trên một đoạn (không xét thuê ước) — để test đối chiếu với các ca
    của ``office.document_visible``."""
    if role in READ_ALL:
        return True
    if role == "manager":
        return bool(department_id) and (chunk.get("department_id") == department_id
                                        or department_id in (chunk.get("assignee_departments") or []))
    if role == "staff":
        return (chunk.get("created_by") == user_id or user_id in (chunk.get("assignee_users") or [])
                or (bool(department_id) and chunk.get("direction") == "out"
                    and chunk.get("department_id") == department_id))
    return False
