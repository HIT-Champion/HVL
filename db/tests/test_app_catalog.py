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

"""Danh mục ứng dụng (migration 1792281603400, trang /ung-dung) trên PostgreSQL + Hasura thật, bằng đúng hai câu GraphQL
của trang (apps/office/app/utils/apps.ts) và đúng câu SQL `moc app install`/`remove` ghi core.apps:
  - mọi vai trò người dùng đọc ứng dụng đang cài: tên, mô tả (từ manifest; trống thì null), đường, phiên bản, lúc cài,
    lúc cập nhật — không thấy ứng dụng đã gỡ, hỏi băm manifest hay lúc gỡ thì Hasura báo không có trường;
  - lãnh đạo, quản trị đơn vị đọc thêm băm manifest và ứng dụng đã gỡ;
  - manifest (image, cổng, healthcheck, biến môi trường, cổng webhook), schema của ứng dụng không có trong GraphQL của
    vai trò nào; core.apps vẫn không; không vai trò nào ghi; vai trò service không đọc;
  - dữ liệu toàn hệ thống: đơn vị khác thấy cùng danh sách; gỡ, cài lại thì danh mục đổi theo.
"""

from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import re
import sys
import uuid
from datetime import datetime

import pytest
from conftest import GraphQLError, User, sql

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import ung_dung  # noqa: E402

_TS = (REPO / "apps" / "office" / "app" / "utils" / "apps.ts").read_text(encoding="utf-8")
QUERY, QUERY_LEADER = (re.search(rf"export const {n} = `([^`]*)`", _TS).group(1)
                       for n in ("APPS_QUERY", "APPS_QUERY_LEADER"))
USER_FIELDS = {"name", "title", "description", "path", "version", "installed_at", "updated_at"}
LEADER_FIELDS = USER_FIELDS | {"manifest_sha256", "removed_at"}


def run_script(script: str, **variables: object) -> list[list[str]]:
    """Một câu SQL của ung_dung qua run_sql: thay biến psql :'tên' bằng hằng chuỗi, bỏ begin/commit (như
    test_app_registry.py)."""
    for key, value in variables.items():
        script = script.replace(f":'{key}'", "'" + str(value).replace("'", "''") + "'")
    assert not re.search(r":'[a-z]+'", script), "còn biến psql chưa thay"
    return sql("\n".join(ln for ln in script.splitlines() if ln.strip() not in ("begin;", "commit;")))


def install(name: str, manifest: dict, sha: str, *, version: str = "1.0.0") -> None:
    run_script(ung_dung.REGISTER_SQL, name=name, title=manifest.get("title", "Thử"), path=f"/{name}",
               schema=name.replace("-", "_"), version=version, sha=sha,
               manifest=base64.b64encode(json.dumps(manifest, ensure_ascii=False).encode()).decode())


def manifest_of(name: str, **extra: object) -> dict:
    """Manifest như moc app ghi vào core.apps: có cổng, image, healthcheck, biến môi trường, webhook — những thứ danh
    mục không được lộ."""
    return {"name": name, "title": f"Ứng dụng {name}", "version": "1.0.0", "path": f"/{name}",
            "image": {"ref": "registry.noi-bo.example/app@sha256:" + "d" * 64}, "port": 18555,
            "healthcheck": {"test": ["CMD", "true"]}, "environment": {"GREETING": "bi-mat-noi-bo"},
            "database": {"schema": name.replace("-", "_")},
            "events": {"kinds": ["office.document.issued"], "webhook": {"port": 18556, "path": "/su-kien"}}, **extra}


@pytest.fixture()
def apps() -> dict[str, str]:
    tag = uuid.uuid4().hex[:6]
    live, gone = f"dm-{tag}", f"dm-go-{tag}"
    install(live, manifest_of(live, description="  Tin mới của đơn vị  "), hashlib.sha256(live.encode()).hexdigest())
    install(gone, manifest_of(gone, description="Đã gỡ"), hashlib.sha256(gone.encode()).hexdigest())
    run_script(ung_dung.REMOVED_SQL, name=gone)
    return {"live": live, "gone": gone}


def mine(user: User, names: dict[str, str], query: str = QUERY) -> dict[str, dict]:
    return {a["name"]: a for a in user.gql(query)["core_app_catalog"] if a["name"] in names.values()}


def test_users_see_installed_apps_with_display_columns_only(world, apps):
    for user in (world.clerk_a, world.staff_a1, world.manager_a1, world.clerk_b):
        rows = mine(user, apps)
        assert set(rows) == {apps["live"]}, user.role
        row = rows[apps["live"]]
        assert set(row) == USER_FIELDS
        assert row["description"] == "Tin mới của đơn vị" and row["path"] == f"/{apps['live']}"
        assert row["version"] == "1.0.0" and row["installed_at"] and row["updated_at"] == row["installed_at"]
        # băm manifest, lúc gỡ: không có trường cho vai trò này (không phải trả null)
        with pytest.raises(GraphQLError, match="manifest_sha256|removed_at"):
            user.gql(QUERY_LEADER)
        with pytest.raises(GraphQLError, match="removed_at"):
            user.gql("{ core_app_catalog(where: {removed_at: {_is_null: false}}) { name } }")


def test_leaders_see_manifest_hash_and_removed_apps(world, apps):
    other_director = User(f"lanh-dao-b-{world.tag}", "director", world.tenant_b)
    for user in (world.director_a, world.admin_a, other_director):
        rows = mine(user, apps, QUERY_LEADER)
        assert set(rows) == {apps["live"], apps["gone"]}, user.role
        live, gone = rows[apps["live"]], rows[apps["gone"]]
        assert set(live) == LEADER_FIELDS
        assert live["manifest_sha256"] == hashlib.sha256(apps["live"].encode()).hexdigest()
        assert live["removed_at"] is None and gone["removed_at"] and gone["updated_at"] == gone["removed_at"]
    # cùng một danh sách cho mọi đơn vị: không có cột đơn vị nào để lọc
    assert mine(world.director_a, apps, QUERY_LEADER) == mine(other_director, apps, QUERY_LEADER)


def test_graphql_exposes_only_catalog_columns_and_no_writes(world):
    fields = '{ __type(name: "core_app_catalog") { fields { name } } }'
    mutations = "{ __schema { mutationType { fields { name } } } }"
    for user in (world.clerk_a, world.staff_a1, world.manager_a1, world.director_a, world.admin_a):
        got = {f["name"] for f in user.gql(fields)["__type"]["fields"]}
        assert got == (LEADER_FIELDS if user.role in ("director", "tenant_admin") else USER_FIELDS), user.role
        names = {f["name"] for f in (user.gql(mutations)["__schema"]["mutationType"] or {"fields": []})["fields"]}
        assert not {n for n in names if "app_catalog" in n or "core_apps" in n}, user.role
        for query in ("{ core_apps { name } }", "{ core_app_catalog { manifest } }",
                      "{ core_app_catalog { schema_name } }",
                      'mutation { insert_core_app_catalog(objects: [{name: "x"}]) { affected_rows } }',
                      "mutation { delete_core_app_catalog(where: {}) { affected_rows } }"):
            with pytest.raises(GraphQLError):
                user.gql(query)
    with pytest.raises(GraphQLError, match="not found"):
        world.service_a.gql("{ core_app_catalog { name } }")


def test_view_carries_nothing_internal_from_the_manifest(world, apps):
    rows = sql(f"select row_to_json(c)::text from core.app_catalog c where c.name = '{apps['live']}'")
    text = rows[0][0]
    for leak in ("18555", "18556", "registry.noi-bo.example", "bi-mat-noi-bo", "GREETING", "healthcheck",
                 apps["live"].replace("-", "_")):
        assert leak not in text, leak
    columns = sql("select attname from pg_attribute where attrelid = 'core.app_catalog'::regclass and attnum > 0 "
                  "order by attnum")
    assert {c[0] for c in columns} == LEADER_FIELDS


def test_blank_or_missing_description_is_null(world):
    tag = uuid.uuid4().hex[:6]
    blank, none = f"dm-trong-{tag}", f"dm-khong-{tag}"
    # chỉ khoảng trắng (ký tự điều khiển như tab, xuống dòng thì moc app từ chối từ lúc kiểm manifest)
    install(blank, manifest_of(blank, description="   "), "e" * 64)
    install(none, manifest_of(none), "f" * 64)
    rows = mine(world.staff_a1, {"a": blank, "b": none})
    assert rows[blank]["description"] is None and rows[none]["description"] is None


def test_catalog_follows_remove_and_reinstall(world, apps):
    live = apps["live"]
    before = mine(world.director_a, apps, QUERY_LEADER)[live]
    run_script(ung_dung.REMOVED_SQL, name=live)
    assert live not in mine(world.staff_a1, apps)
    assert mine(world.admin_a, apps, QUERY_LEADER)[live]["removed_at"]
    # cài lại bản mới: hiện lại cho mọi người, lúc cài giữ nguyên lần đầu, lúc cập nhật, phiên bản, băm theo bản mới
    install(live, manifest_of(live, description="Bản 1.1"), "9" * 64, version="1.1.0")
    after = mine(world.staff_a1, apps)[live]
    assert after["version"] == "1.1.0" and after["description"] == "Bản 1.1"
    assert after["installed_at"] == before["installed_at"]
    assert datetime.fromisoformat(after["updated_at"]) > datetime.fromisoformat(before["updated_at"])
    leader = mine(world.director_a, apps, QUERY_LEADER)[live]
    assert leader["removed_at"] is None and leader["manifest_sha256"] == "9" * 64
