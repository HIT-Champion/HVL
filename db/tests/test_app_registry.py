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

"""Ứng dụng cắm vào lõi bằng manifest (migration 1792281603200, scripts/ung_dung.py) trên PostgreSQL + Hasura thật:
  - core.app_events chỉ nhận loại trong danh sách trắng, của văn bản không hạn chế, đúng 5 cột; không mang người làm;
  - migration của ứng dụng chạy bằng ĐÚNG câu SQL `moc app install` gửi, trên phiên psql đăng nhập bằng vai trò CSDL
    riêng của ứng dụng (không superuser, chỉ làm chủ schema của nó): đọc, ghi, tham chiếu lõi, leo vai trò, tạo gì chỗ
    khác thì PostgreSQL chặn; đối tượng chạy bằng quyền của Hasura (hàm hệ thống trong view, default) thì
    moc_app.migration_done() từ chối; hàm của ứng dụng thành SECURITY DEFINER — Hasura (superuser) gọi cũng không đọc
    được lõi. Không để lại gì khi bị từ chối;
  - Bảng tin (apps/bang-tin): migration + quyền Hasura trong app.yaml — người dùng chỉ thấy tin của đơn vị mình, của
    văn bản mình được xem (F3.7); vai trò dịch vụ app_bang_tin chỉ thêm được dòng, đúng câu phần máy chủ gửi.
Cần container PostgreSQL của db/tests/stack.sh (MOC_IT_PG_CONTAINER, như test_backup.py): psql đăng nhập bằng vai trò
của ứng dụng qua socket Unix trong container, như `moc app install`.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import subprocess
import sys
import uuid

import pytest

from conftest import ADMIN_SECRET, GraphQLError, SQLError, User, _post, incoming, make_token, received, sql

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "apps" / "bang-tin"))

import server as bang_tin_server  # noqa: E402
import ung_dung  # noqa: E402

KINDS = ("office.document.received", "office.document.registered", "office.document.issued")


def lit(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_script(script: str, **variables: object) -> list[list[str]]:
    """Một câu SQL của ung_dung qua run_sql: thay biến psql :'tên' bằng hằng chuỗi (như psql làm), bỏ begin/commit
    (run_sql đã là một giao dịch — lỗi thì hủy hết như ON_ERROR_STOP)."""
    for key, value in variables.items():
        script = script.replace(f":'{key}'", lit(value))
    assert not re.search(r":'[a-z]+'", script), "còn biến psql chưa thay"
    return sql("\n".join(ln for ln in script.splitlines() if ln.strip() not in ("begin;", "commit;")))


def metadata(body: dict) -> dict:
    status, out = _post("/v1/metadata", body, {"X-Hasura-Admin-Secret": ADMIN_SECRET})
    assert status == 200, out
    return out


PG = os.environ.get("MOC_IT_PG_CONTAINER", "moc-db-it-postgres")   # container của db/tests/stack.sh


def register(rec: dict) -> None:
    manifest = base64.b64encode(json.dumps(rec.get("manifest", {})).encode()).decode()
    run_script(ung_dung.REGISTER_SQL, name=rec["name"], title=rec.get("title", "Thử"), path=rec["path"],
               schema=rec["schema"], version="1.0.0", manifest=manifest, sha="a" * 64)
    out = run_script(ung_dung.ROLE_SQL.format(role=ung_dung.db_role(rec["schema"]), schema=rec["schema"]))
    assert json.loads(out[0][0]) == {"ok": True}


def as_app(rec: dict, script: str, **variables: str) -> str:
    """psql bằng vai trò của ứng dụng (LOGIN chỉ trong lúc chạy), như ung_dung.run_migrations."""
    role = ung_dung.db_role(rec["schema"])
    sql(ung_dung.LOGIN_SQL.format(role=role, login="login"))
    try:
        cmd = ["docker", "exec", "-i", PG, "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", role,
               "-d", "moc", *(a for k, v in variables.items() for a in ("-v", f"{k}={v}")), "-f", "-"]
        proc = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=60)
    finally:
        sql(ung_dung.LOGIN_SQL.format(role=role, login="nologin"))
    if proc.returncode != 0:
        raise SQLError(proc.stderr.strip())
    return proc.stdout.strip()


def migrate(rec: dict, version: int, body: str) -> None:
    m = {"version": version, "name": f"buoc_{version}", "sha256": "b" * 64, "sql": body}
    as_app(rec, ung_dung.migrate_script(rec, m), name=rec["name"], mname=m["name"], sha=m["sha256"])


@pytest.fixture()
def app() -> dict:
    tag = uuid.uuid4().hex[:6]
    rec = {"name": f"thu-{tag}", "path": f"/thu-{tag}", "schema": f"thu_{tag}"}
    register(rec)
    return rec


# ------------------------------------------------------------------------------------------- danh sách trắng sự kiện

def test_app_events_whitelist_skips_restricted_documents(world):
    # office.document.received do trigger documents_received ghi lúc tiếp nhận (#381), các loại khác ghi tay ở đây
    doc = received(world.clerk_a, incoming(world.tag, 9301))["id"]
    secret = received(world.clerk_a, incoming(world.tag, 9302, restricted=True))["id"]
    for d in (doc, secret):
        for kind in (*KINDS[1:], "office.document.directed", "office.document.assigned"):
            sql(f"insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, data) "
                f"values ('{world.tenant_a}', '{d}', '{kind}', 'van-thu', 'user', '{{\"note\": \"bí mật\"}}')")
    rows = sql(f"select e.kind, e.tenant_id, (e.id = d.id)::text, (e.occurred_at = d.created_at)::text "
               f"from core.app_events e join office.document_events d on d.id = e.id "
               f"where e.document_id in ('{doc}', '{secret}') order by e.id")
    assert rows == [[k, world.tenant_a, "true", "true"] for k in KINDS]
    columns = sql("select column_name from information_schema.columns where table_schema = 'core' "
                  "and table_name = 'app_events' order by ordinal_position")
    assert [c[0] for c in columns] == ["id", "tenant_id", "document_id", "kind", "occurred_at"]


def test_registered_through_core_function_reaches_feed(world):
    from conftest import Service
    doc = received(world.clerk_a, incoming(world.tag, 9303))["id"]
    Service(world.clerk_a.sub, "service", world.tenant_a).gql(
        "mutation ($id: uuid!) { office_register_incoming(args: {document_id: $id}) { id } }", {"id": doc})
    assert sql(f"select kind from core.app_events where document_id = '{doc}' order by id") == [
        ["office.document.received"], ["office.document.registered"]]


def test_feed_and_registry_are_not_in_graphql_for_users(world):
    for query in ("{ core_app_events { id } }", "{ core_apps { name } }", "{ core_app_migrations { app } }"):
        with pytest.raises(GraphQLError, match="not found"):
            world.director_a.gql(query)


# ------------------------------------------------------------------------------------------- sổ ứng dụng

def test_feed_rows_carry_no_session_of_the_actor(world):
    """Hasura lấy session_variables của sự kiện từ hasura.user lúc dòng core.app_events được ghi: hàm chép đặt 'null'
    trong lúc đó (mệnh đề SET), rồi trả lại — phần còn lại của giao dịch vẫn thấy người làm."""
    doc = received(world.clerk_a, incoming(world.tag, 9304))["id"]
    tag = uuid.uuid4().hex[:6]
    sql(f"create table public.thu_phien_{tag} (khi text, gia_tri text);"
        f"create function public.thu_phien_{tag}() returns trigger language plpgsql as $$ begin "
        f"insert into public.thu_phien_{tag} values ('feed', current_setting('hasura.user', true)); return null; "
        f"end $$;"
        f"create trigger thu_phien_{tag} after insert on core.app_events for each row "
        f"execute function public.thu_phien_{tag}();")
    try:
        sql(f"""select set_config('hasura.user', '{{"x-hasura-user-id": "nguoi-lam", "x-hasura-role": "clerk"}}', true);
                insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind)
                values ('{world.tenant_a}', '{doc}', 'office.document.issued', 'nguoi-lam', 'user');
                insert into public.thu_phien_{tag} values ('sau', current_setting('hasura.user', true));""")
        rows = dict(sql(f"select khi, gia_tri from public.thu_phien_{tag}"))
    finally:
        sql(f"drop trigger thu_phien_{tag} on core.app_events; drop function public.thu_phien_{tag}();"
            f"drop table public.thu_phien_{tag};")
    assert rows["feed"] == "null"
    assert json.loads(rows["sau"])["x-hasura-user-id"] == "nguoi-lam"


# ------------------------------------------------------------------------------------------- sổ ứng dụng

def test_registry_is_audited_and_rejects_core_schema(app):
    # người làm: qua psql của moc app là 'moc app' (set local moc.actor); ở đây run_sql của Hasura nên là hasura:admin
    rows = sql(f"select action, actor_kind, tenant_id from core.audit_log "
               f"where entity = 'core.apps' and entity_id = '{app['name']}'")
    assert rows == [["insert", "system", "NULL"]]
    with pytest.raises(SQLError, match="check"):
        register({"name": "thu-core", "path": "/thu-core", "schema": "core"})
    # cài lại cùng tên với schema khác: không đổi schema của ứng dụng đã cài
    out = run_script(ung_dung.REGISTER_SQL, name=app["name"], title="Thử", path=app["path"], schema="schema_khac",
                     version="1.0.1", manifest=base64.b64encode(b"{}").decode(), sha="c" * 64)
    assert json.loads(out[0][0]) == {"ok": False}


def audit_rows(app: dict) -> int:
    return int(sql(f"select count(*) from core.audit_log where entity = 'core.apps' "
                   f"and entity_id = '{app['name']}'")[0][0])


def test_reinstall_without_change_writes_nothing(app):
    before = audit_rows(app)
    register(app)                                       # đúng như lần đầu: không ghi, không thêm dòng sổ
    assert audit_rows(app) == before
    run_script(ung_dung.REGISTER_SQL, name=app["name"], title="Tên mới", path=app["path"], schema=app["schema"],
               version="1.0.0", manifest=base64.b64encode(b"{}").decode(), sha="a" * 64)
    assert audit_rows(app) == before + 1


def test_removed_app_gives_its_path_back(app):
    run_script(ung_dung.REMOVED_SQL, name=app["name"])
    tag = uuid.uuid4().hex[:6]
    register({"name": f"moi-{tag}", "path": app["path"], "schema": f"moi_{tag}"})
    with pytest.raises(SQLError, match="apps_path_active"):            # cài lại bản đã gỡ: đường đã có chủ mới
        run_script(ung_dung.REGISTER_SQL, name=app["name"], title="Thử 2", path=app["path"], schema=app["schema"],
                   version="1.0.0", manifest=base64.b64encode(b"{}").decode(), sha="a" * 64)


# ------------------------------------------------------------------------------------------- vai trò CSDL của ứng dụng

def test_app_role_is_powerless_outside_its_schema(app):
    role = ung_dung.db_role(app["schema"])
    attrs = sql(f"select rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin, rolinherit "
                f"from pg_roles where rolname = '{role}'")
    assert attrs == [["f", "f", "f", "f", "f", "f"]]
    assert sql(f"select count(*) from pg_auth_members m join pg_roles r on r.oid = m.member "
               f"where r.rolname = '{role}'") == [["0"]]
    for schema in ("core", "office", "personal"):
        assert sql(f"select has_schema_privilege('{role}', '{schema}', 'USAGE')") == [["f"]]
    assert sql(f"select nspowner::regrole::text from pg_namespace where nspname = '{app['schema']}'") == [[role]]


def test_migration_objects_stay_owned_by_app_role(app, world):
    s = app["schema"]
    role = ung_dung.db_role(s)
    migrate(app, 1, f"""
        create table {s}.ghi (id bigint primary key, tenant_id uuid not null, ghi_chu text,
                              tao_luc timestamptz not null default now(), ma uuid default gen_random_uuid(),
                              so bigint generated by default as identity, check (char_length(ghi_chu) < 500));
        create index on {s}.ghi (tenant_id);
        create view {s}.ghi_gan_day as select id, tenant_id from {s}.ghi where tao_luc > now() - interval '7 days';
        create function {s}.dem() returns bigint language sql stable as 'select count(*) from {s}.ghi';
        create function {s}.cham() returns trigger language plpgsql as $$
          begin new.ghi_chu := coalesce(new.ghi_chu, 'mới'); return new; end $$;
        create trigger cham before insert on {s}.ghi for each row execute function {s}.cham();
        reset role;
    """)
    assert sql(f"select version, name from core.app_migrations where app = '{app['name']}'") == [["1", "buoc_1"]]
    assert sql(f"select distinct tableowner from pg_tables where schemaname = '{s}'") == [[role]]
    assert sql(f"select distinct viewowner from pg_views where schemaname = '{s}'") == [[role]]
    assert sql(f"select proname, prosecdef::text, proowner::regrole::text from pg_proc "
               f"where pronamespace = '{s}'::regnamespace order by proname") == [["cham", "true", role],
                                                                                 ["dem", "true", role]]
    assert sql(f"select rolcanlogin from pg_roles where rolname = '{role}'") == [["f"]]
    sql(f"insert into {s}.ghi (id, tenant_id) values (1, '{world.tenant_a}')")       # như Hasura: superuser ghi
    assert sql(f"select ghi_chu, {s}.dem() from {s}.ghi") == [["mới", "1"]]


def test_app_function_called_by_hasura_cannot_read_core(app, world):
    """Hàm của ứng dụng (kể cả trong trigger, view) chạy bằng vai trò ứng dụng dù Hasura (superuser) gọi."""
    s = app["schema"]
    migrate(app, 1, f"""
        create table {s}.ghi (id int primary key, tenant_id uuid);
        create function {s}.lo() returns bigint language plpgsql as $$
          begin return (select count(*) from office.documents); end $$;
        create view {s}.xem as select {s}.lo() as so_van_ban;
        create function {s}.chep() returns trigger language plpgsql as $$
          begin insert into core.tenants (code, name) values ('ZZ', 'z'); return new; end $$;
        create trigger chep after insert on {s}.ghi for each row execute function {s}.chep();
    """)
    for statement in (f"select * from {s}.xem", f"select {s}.lo()",
                      f"insert into {s}.ghi values (1, '{world.tenant_a}')"):
        with pytest.raises(SQLError, match="permission denied"):
            sql(statement)
    assert sql("select count(*) from core.tenants where code = 'ZZ'") == [["0"]]


@pytest.mark.parametrize("body", [
    # đọc, ghi, sửa lõi; tạo chỗ khác; leo vai trò — PostgreSQL chặn
    "select count(*) from office.documents",
    "insert into core.tenants (code, name) values ('XX', 'x')",
    "update office.documents set summary = 'x'",
    "delete from core.audit_log",
    "alter table office.documents add column x int",
    "drop table core.app_migrations",
    "create table public.lot (id int)",
    "create schema khac",
    "copy core.tenants to stdout",
    "create table {s}.g (t text); copy {s}.g from program 'id'",
    "select lo_import('/etc/passwd')",
    "create table {s}.a (id int); insert into core.tenants (code, name) values ('YY', 'y')",
    "create role ke_xau",
    # ca của người kiểm (B1): view đọc văn bản lõi, mọi đơn vị
    "create table {s}.ghi (id int primary key, tenant_id uuid not null); "
    "create view {s}.xem as select d.id, d.tenant_id, d.summary, d.restricted from office.documents d",
    "create view {s}.moi_don_vi as select t.id as tenant_id from core.tenants t",
    "create table {s}.b (id int references core.tenants)",
    # SQL động né mẫu chữ (M3), SET ROLE, SESSION AUTHORIZATION
    "do $x$ begin execute 'res' || 'et role'; execute 'create table core.thoat (i int)'; end $x$",
    "set role moc",
    "set session authorization moc",
    "create function {s}.f() returns bigint language sql security definer as 'select count(*) from office.documents'",
    "create table {s}.c (i int); create trigger t after insert on core.tenants for each row execute function "
    "suppress_redundant_updates_trigger()",
    "alter default privileges for role moc grant select on tables to public",
    "grant moc to current_user",
    "grant select on office.documents to public",
    "alter role current_user superuser",
    # chạy bằng quyền của Hasura khi được đọc, ghi: moc_app.migration_done từ chối
    "create view {s}.v as select query from pg_stat_activity",
    "create view {s}.v as select query_to_xml('select 1', true, false, '') as x",
    "create table {s}.d (i int, x text default set_config('role', 'moc', true))",
    "create table {s}.e (i int); create view {s}.v with (security_invoker = true) as select i from {s}.e",
    "select lo_create(0)",
    "alter default privileges grant select on tables to public",
    "create table {s}.f (id serial primary key)",
])
def test_migration_cannot_touch_core(app, body):
    s = app["schema"]
    with pytest.raises(SQLError, match="permission denied|must be|cannot COPY|moc_app:|not allowed|must have"):
        migrate(app, 7, body.format(s=s))
    assert sql(f"select count(*) from core.app_migrations where app = '{app['name']}'") == [["0"]]
    assert sql(f"select count(*) from pg_class where relnamespace = '{s}'::regnamespace") == [["0"]]
    assert sql("select count(*) from core.tenants where code in ('XX', 'YY')") == [["0"]]
    assert sql("select to_regclass('core.thoat') is null") == [["t"]]
    assert sql(f"select count(*) from pg_largeobject_metadata "
               f"where lomowner = '{ung_dung.db_role(s)}'::regrole") == [["0"]]


# ------------------------------------------------------------------------------------------- Bảng tin trên Hasura thật

@pytest.fixture(scope="module")
def bang_tin():
    rec = ung_dung.load_manifest(REPO / "apps" / "bang-tin" / "app.yaml", root=REPO)
    if not sql("select 1 from core.apps where name = 'bang-tin'"):
        register(rec)
        for m in rec["migrations"]:
            as_app(rec, ung_dung.migrate_script(rec, m), name=rec["name"], mname=m["name"], sha=m["sha256"])
    md = metadata({"type": "export_metadata", "version": 2, "args": {}})["metadata"]
    tables = md["sources"][0]["tables"]
    if not any(t["table"] == {"schema": "bang_tin", "name": "tin"} for t in tables):
        tables.extend(rec["tables"])                       # đúng như thư mục metadata trộn: thêm bảng, giữ lõi
        metadata({"type": "replace_metadata", "version": 2, "args": {"metadata": md}})
    assert metadata({"type": "get_inconsistent_metadata", "args": {}})["is_consistent"]
    return rec


def service_headers() -> dict[str, str]:
    """Token như client app-bang-tin-svc nhận từ Keycloak: chỉ vai trò app_bang_tin, không đơn vị."""
    return {"Authorization": "Bearer " + make_token("app:bang-tin", "app_bang_tin", None)}


def insert_tin(row: dict) -> dict:
    _, out = _post("/v1/graphql", {"query": bang_tin_server.INSERT, "variables": {"o": row}}, service_headers())
    return out


def tin_query() -> str:
    js = (REPO / "apps" / "bang-tin" / "public" / "tin.js").read_text(encoding="utf-8")
    return re.search(r"export const QUERY_TIN = `([^`]*)`", js).group(1)


def row(event_id: int, tenant: str, doc: str, kind: str = "office.document.registered") -> dict:
    return {"event_id": event_id, "tenant_id": tenant, "document_id": doc, "kind": kind,
            "occurred_at": "2026-10-25T07:00:00+00:00"}


def test_bang_tin_service_role_only_inserts(bang_tin, world):
    doc = received(world.clerk_a, incoming(world.tag, 9310))["id"]
    base = 9_000_000 + int(uuid.uuid4().hex[:5], 16)
    assert insert_tin(row(base, world.tenant_a, doc)) == {"data": {"insert_bang_tin_tin": {"affected_rows": 1}}}
    dup = insert_tin(row(base, world.tenant_a, doc))["errors"][0]          # server.py coi đây là "đã ghi"
    assert dup["extensions"]["code"] == "constraint-violation" and "tin_pkey" in json.dumps(dup)
    for query in ("{ bang_tin_tin { event_id } }", "{ office_documents { id } }", "{ core_app_events { id } }"):
        _, out = _post("/v1/graphql", {"query": query}, service_headers())
        assert "errors" in out and not out.get("data"), out              # không đọc được gì, kể cả bảng của mình
    with pytest.raises(GraphQLError):
        world.staff_a1.gql(bang_tin_server.INSERT, {"o": row(base + 1, world.tenant_a, doc)})
    assert sql("select tableowner from pg_tables where schemaname = 'bang_tin'") == [["moc_appdb_bang_tin"]]


def test_bang_tin_users_see_own_tenant_and_visible_documents_only(bang_tin, world):
    base = 9_500_000 + int(uuid.uuid4().hex[:5], 16)
    normal = received(world.clerk_a, incoming(world.tag, 9311))["id"]
    secret = received(world.clerk_a, incoming(world.tag, 9312, restricted=True))["id"]
    other = received(world.clerk_b, incoming(world.tag, 9313))["id"]
    for i, (tenant, doc) in enumerate(((world.tenant_a, normal), (world.tenant_a, secret), (world.tenant_b, other))):
        assert "errors" not in insert_tin(row(base + i, tenant, doc, "office.document.issued"))

    def seen(user: User) -> set[str]:
        data = user.gql(tin_query())["bang_tin_tin"]                      # đúng câu trang gửi
        return {t["document_id"] for t in data if t["event_id"] >= base and t["event_id"] < base + 3}

    # đúng quy tắc office.document_visible của lõi: hạn chế thì chỉ người tạo, người được cấp quyền xem thấy cả tin;
    # chuyên viên chỉ thấy văn bản đến được giao; đơn vị khác không thấy gì
    assert seen(world.director_a) == {normal}
    assert seen(world.clerk_a) == {normal, secret}
    assert seen(world.staff_a1) == set()
    assert seen(world.clerk_b) == {other}
    data = world.director_a.gql(tin_query())["bang_tin_tin"]
    mine = next(t for t in data if t["event_id"] == base)
    assert mine["document"]["symbol"] == f"9311/UBND-VP{world.tag}" and mine["kind"] == "office.document.issued"
