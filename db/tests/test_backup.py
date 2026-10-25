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

"""Sao lưu, khôi phục (F3.4): bản dump giữ nguyên sổ kiểm toán, lần khôi phục nối tiếp chuỗi.

Làm như `moc backup` (scripts/backup.py) nhưng ngay trong container PostgreSQL thử: `pg_dump -Fc` CSDL moc qua ống
sang `pg_restore` vào một CSDL mới. Hash mỗi dòng sổ tính trên `jsonb_build_array(...)::text` và
`extract(epoch from occurred_at)`: dump rồi restore không được làm đổi chúng.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

# Câu ghi lần khôi phục mà `moc backup restore` dùng (scripts/audit_chain.py, chỉ dùng thư viện chuẩn)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
from audit_chain import HEAD_SQL, RESTORED_SQL  # noqa: E402
from ung_dung import ROLE_SQL, AppError, recreate_roles_sql  # noqa: E402

PG = os.environ.get("MOC_IT_PG_CONTAINER", "moc-db-it-postgres")   # container của db/tests/stack.sh
COPY = "moc_restore_it"


def psql(db: str, script: str, **variables: str) -> str:
    cmd = ["docker", "exec", "-i", PG, "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", "moc", "-d", db,
           *(a for k, v in variables.items() for a in ("-v", f"{k}={v}")), "-f", "-"]
    proc = subprocess.run(cmd, input=script, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def head(db: str) -> dict:
    return json.loads(psql(db, HEAD_SQL + ";"))


def problems(db: str) -> list[str]:
    return psql(db, "select audit_id || ' ' || problem from core.audit_verify();").splitlines()


@pytest.fixture(scope="module")
def restored():
    """Đầu chuỗi và kết quả kiểm chuỗi của CSDL moc lúc dump; bản khôi phục nằm ở COPY (xóa khi xong)."""
    at_dump = {"head": head("moc"), "problems": problems("moc")}
    psql("postgres", f"drop database if exists {COPY} with (force); create database {COPY};")
    dump = subprocess.Popen(["docker", "exec", PG, "pg_dump", "-U", "moc", "-Fc", "-Z", "0", "-d", "moc"],
                            stdout=subprocess.PIPE)
    assert dump.stdout is not None
    restore = subprocess.run(["docker", "exec", "-i", PG, "pg_restore", "-U", "moc", "--exit-on-error", "-d", COPY],
                             stdin=dump.stdout, capture_output=True, text=True)
    dump.stdout.close()
    code = dump.wait()
    assert restore.returncode == 0, restore.stderr
    assert code == 0
    yield at_dump
    psql("postgres", f"drop database if exists {COPY} with (force);")


def test_restored_copy_keeps_audit_chain(restored):
    """Bản khôi phục có đúng đầu chuỗi lúc dump; tính lại cả chuỗi ra đúng kết quả như bản gốc."""
    assert head(COPY) == restored["head"]
    assert restored["head"]["id"] > 0
    assert problems(COPY) == restored["problems"]


def test_restore_event_continues_chain(restored):
    """Dòng system.restored nối ngay sau đầu chuỗi đã khôi phục, là sự kiện của nền tảng; chuỗi vẫn liền mạch."""
    before = head(COPY)
    diff = {"run": "20261020-040000", "backed_up_at": "2026-10-20T04:00:00+07:00", "audit_id": before["id"]}
    event = int(psql(COPY, RESTORED_SQL, actor="os:it", run=diff["run"], diff=json.dumps(diff)))
    row = json.loads(psql(COPY, f"""select json_build_object('prev', encode(prev_hash, 'hex'), 'tenant', tenant_id,
        'actor', actor_id, 'kind', actor_kind, 'action', action, 'entity', entity, 'entity_id', entity_id,
        'diff', diff)::text from core.audit_log where id = {event};"""))
    assert event == before["id"] + 1
    assert row == {"prev": before["hash"], "tenant": None, "actor": "os:it", "kind": "system",
                   "action": "system.restored", "entity": "backup", "entity_id": diff["run"], "diff": diff}
    assert head(COPY)["id"] == event
    assert problems(COPY) == restored["problems"]


def pg_restore(db: str, dump: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "exec", "-i", PG, "pg_restore", "-U", "moc", "--exit-on-error", "-d", db],
                          input=dump, capture_output=True)


def test_restore_on_new_server_recreates_app_roles_first():
    """Vai trò moc_appdb_* thuộc cả máy chủ, pg_dump một CSDL không chép: máy mới chưa có thì pg_restore
    --exit-on-error dừng ở ALTER … OWNER TO. `moc backup restore` tạo lại chúng theo manifest trước khi khôi phục."""
    role, src, dst = "moc_appdb_thu_khoi_phuc", "moc_bk_src_it", "moc_bk_dst_it"
    psql("postgres", f"drop database if exists {src} with (force); drop database if exists {dst} with (force);"
                     f"drop role if exists {role}; create database {src}; create database {dst};")
    try:
        psql(src, "create schema moc_app; create function moc_app.migration_done(text, bigint, text, text)"
                  " returns json language sql as $$ select '{}'::json $$;"
                  + ROLE_SQL.format(role=role, schema="thu_khoi_phuc").replace("begin;", "").replace("commit;", "")
                  + f"set role {role}; create table thu_khoi_phuc.ghi (i int); reset role;")
        dump = subprocess.run(["docker", "exec", PG, "pg_dump", "-U", "moc", "-Fc", "-d", src],
                              capture_output=True, check=True).stdout
        psql("postgres", f"drop database {src} with (force); drop role {role};")   # như máy mới: chưa có vai trò
        failed = pg_restore(dst, dump)
        assert failed.returncode != 0 and f'role "{role}" does not exist' in failed.stderr.decode()
        psql("postgres", recreate_roles_sql([role]) + f"drop database {dst} with (force); create database {dst};")
        restored = pg_restore(dst, dump)
        assert restored.returncode == 0, restored.stderr.decode()
        assert psql(dst, "select tableowner from pg_tables where schemaname = 'thu_khoi_phuc'") == role
        assert psql("postgres", f"select rolcanlogin, rolsuper, rolinherit, rolbypassrls, rolconnlimit"
                                f" from pg_roles where rolname = '{role}'") == "f|f|f|f|2"
        with pytest.raises(AppError):
            recreate_roles_sql(['moc_appdb_x"; drop role moc; --'])
    finally:
        psql("postgres", f"drop database if exists {src} with (force); drop database if exists {dst} with (force);"
                         f"drop role if exists {role};")
