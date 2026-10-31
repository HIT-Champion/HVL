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


"""Chốt chặn lùi cho ranh giới lõi – Văn phòng điện tử (scripts/ranh_gioi_loi.py, docs/architecture.md §4.4, §4.7).
Không cần Docker, không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import textwrap
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ranh_gioi_loi", SCRIPTS / "ranh_gioi_loi.py")
rg = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(rg)

SUA = ("Gỡ chỗ dính, hoặc nếu chưa tránh được thì thêm đúng dòng đó vào scripts/ranh_gioi_loi.txt và nói lý do trong "
       "PR (docs/architecture.md §4.4). Xem bằng: python3 scripts/ranh_gioi_loi.py")


class RepoBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inv = rg.inventory()
        cls.edges = set(cls.inv["edges"])
        cls.known = rg.known()

    def test_every_module_has_a_group(self) -> None:
        missing = sorted(m for m, g in self.inv["groups"].items() if g is None)
        self.assertEqual(missing, [], "mô-đun mới chưa xếp nhóm: thêm vào NHOM của scripts/ranh_gioi_loi.py theo tiêu "
                                      "chí §4.3 (lõi, dáng nghiệp vụ, văn phòng, trộn)")
        stale = sorted(set(rg.NHOM) - set(self.inv["groups"]))
        self.assertEqual(stale, [], "NHOM còn mô-đun không còn trong mã: xóa dòng đó")

    def test_core_modules_have_no_edge_at_all(self) -> None:
        core = {m for m, g in self.inv["groups"].items() if g == rg.LOI}
        bad = sorted(e for e in self.edges if e.split(" ")[1] in core)
        self.assertEqual(bad, [], "mô-đun nhóm lõi không được dựa vào Văn phòng, kể cả khi dòng có trong danh sách")

    def test_no_new_edge(self) -> None:
        new = sorted(self.edges - set(self.known))
        self.assertEqual(new, [], f"chỗ dính lõi → Văn phòng mới. {SUA}")

    def test_list_only_shrinks(self) -> None:
        gone = sorted(set(self.known) - self.edges)
        self.assertEqual(gone, [], "các chỗ dính này đã gỡ: xóa dòng của chúng trong scripts/ranh_gioi_loi.txt")
        dup = sorted({e for e in self.known if self.known.count(e) > 1})
        self.assertEqual(dup, [], "dòng lặp trong scripts/ranh_gioi_loi.txt")


def write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


class Scanner(unittest.TestCase):
    """Bộ dò trên một cây giả: bắt đúng chỗ dính, bỏ qua docstring, chú thích, định nghĩa đã bị thay."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        write(self.root, f"{rg.MIGRATIONS}/1_core/up.sql", """
            create table core.users (id uuid, role text not null check (role in ('clerk', 'tenant_admin')));
            create table core.jobs (id uuid, state text check (state in ('queued', 'done')));
            create function core.audit() returns trigger language plpgsql as $$ begin return new; end $$;
            create function core.visible(f uuid) returns boolean language sql as $$ select true $$;
            """)
        write(self.root, f"{rg.MIGRATIONS}/2_office/up.sql", """
            create table office.documents (id uuid);
            create function office.redact() returns trigger language plpgsql as $$ begin return new; end $$;
            -- core.visible bên dưới đọc office.documents (chú thích, không tính)
            create or replace function core.visible(f uuid) returns boolean language sql as $$
              select exists (select 1 from office.documents d where d.id = f) $$;
            create trigger audit after insert on office.documents for each row execute function core.audit();
            create trigger redact before insert on core.users for each row execute function office.redact();
            alter table core.users add column head_title text;
            """)
        write(self.root, f"{rg.MIGRATIONS}/3_core_again/up.sql", """
            create or replace function core.visible(f uuid) returns boolean language sql as $$ select true $$;
            """)
        write(self.root, f"{rg.TABLES}/core_users.yaml", """
            # quan hệ cũ tới office.documents đã gỡ (chú thích, không tính)
            table: {name: users, schema: core}
            select_permissions:
              - role: staff
                permission: {columns: [id], filter: {}}
            """)
        write(self.root, "services/svc-files/src/svc_files/__init__.py", '"""Gói."""\n__version__ = "1"\n')
        write(self.root, "services/svc-files/src/svc_files/core_mod.py", '''
            """Đọc office.documents (docstring, không tính)."""
            from .office import api
            Q = "query { office_documents_by_pk(id: $id) { id } }"
            EVENT = "office.documents.cached"
            def who(role):
                "chuỗi đứng một mình: 'clerk' không tính"
                return role == "manager"
            ''')
        write(self.root, "services/svc-files/src/svc_files/office/api.py", 'Q = "office_documents"\n')
        write(self.root, "services/svc-workflow/src/svc_workflow/__init__.py", '"""Gói."""\n__version__ = "1"\n')

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_code_edges(self) -> None:
        objects = rg.office_objects(rg.migrations(self.root))
        self.assertEqual(objects, {"documents", "redact"})
        edges, groups = rg.code_edges(self.root, objects)
        self.assertEqual(groups["svc_files/office/api.py"], rg.VP)
        self.assertIsNone(groups["svc_files/core_mod.py"])
        self.assertEqual(sorted(edges), [
            "du-lieu svc_files/core_mod.py -> office.documents",
            "import svc_files/core_mod.py -> svc_files/office/",
            "vai-tro svc_files/core_mod.py -> manager",
        ])

    def test_db_edges_take_the_latest_definition(self) -> None:
        objects = rg.office_objects(rg.migrations(self.root))
        self.assertEqual(sorted(rg.db_edges(self.root, objects)), [
            "csdl cot core.users.head_title <- 2_office",
            "csdl rang-buoc core.users.role -> clerk",
            "csdl trigger core.users -> office.redact",
        ])

    def test_metadata_ignores_comments_and_counts_roles(self) -> None:
        objects = rg.office_objects(rg.migrations(self.root))
        self.assertEqual(sorted(rg.metadata_edges(self.root, objects)), ["vai-tro core_users.yaml -> staff"])
        write(self.root, f"{rg.TABLES}/core_files.yaml", """
            table: {name: files, schema: core}
            array_relationships:
              - name: document_files
                using:
                  manual_configuration:
                    remote_table: {name: documents, schema: office}
            """)
        self.assertIn("metadata core_files.yaml -> office.documents", rg.metadata_edges(self.root, objects))


if __name__ == "__main__":
    unittest.main()
