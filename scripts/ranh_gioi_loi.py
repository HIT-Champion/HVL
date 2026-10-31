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


"""Ranh giới lõi – Văn phòng điện tử (docs/architecture.md §4.3, §4.4, §4.7): kiểm kê mọi chỗ phần lõi còn dựa vào
Văn phòng, đọc thẳng mã Python của svc-files, svc-workflow, migration và metadata Hasura. Chỉ đọc tệp, không chạy dịch
vụ, không cần Docker; chỉ thư viện chuẩn.

    python3 scripts/ranh_gioi_loi.py           kiểm kê theo năm mặt, kèm nhóm của từng mô-đun
    python3 scripts/ranh_gioi_loi.py --json    cùng nội dung, dạng JSON

Mỗi chỗ dính là một cạnh, một dòng "<mặt> <nguồn> -> <đích>":

    import    mô-đun ngoài nhóm Văn phòng import mô-đun của Văn phòng lúc nạp (đầu tệp, thân lớp; khối
              if TYPE_CHECKING không tính); import trong hàm chỉ được ở mô-đun trộn, là chỗ ráp khi cờ bật
    du-lieu   mô-đun ngoài nhóm Văn phòng gọi tên một bảng, view, hàm của schema office (SQL office.x hay GraphQL
              office_x…); tên sự kiện nhật ký như "office.assist.asked" không tính
    csdl      hàm, view của core đọc office; trigger nối core với office (trừ trigger sổ kiểm toán core.audit trên
              bảng office, đúng chiều); ràng buộc CHECK của bảng core liệt kê giá trị của Văn phòng; cột của bảng core
              do migration của Văn phòng thêm. Tính trên trạng thái sau migration cuối: câu lệnh tách đúng cả thân
              $$…$$; drop function, trigger, table, column, constraint và set schema về sau đều gỡ cạnh
    metadata  tệp core_*.yaml của Hasura trỏ sang office (quan hệ, hàm), chú thích không tính
    vai-tro   mô-đun ngoài nhóm Văn phòng, hoặc quyền Hasura của bảng core, viết cứng vai trò văn thư
              (clerk, staff, manager, director)

Danh sách đã biết ở scripts/ranh_gioi_loi.txt. Test scripts/tests/test_ranh_gioi_loi.py (make test, CI) là chốt chặn
lùi: cạnh mới thì đỏ (gỡ, hoặc ghi vào danh sách và nói lý do trong PR); cạnh đã gỡ mà danh sách còn thì cũng đỏ (xóa
dòng đó), nên danh sách chỉ ngắn dần. Mô-đun nhóm lõi không được có cạnh nào, kể cả cạnh có trong danh sách.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGES = {"svc_files": "services/svc-files/src/svc_files", "svc_workflow": "services/svc-workflow/src/svc_workflow"}
MIGRATIONS = "db/migrations/default"
TABLES = "db/metadata/databases/default/tables"
KNOWN = ROOT / "scripts" / "ranh_gioi_loi.txt"

LOI, DANG, VP, TRON = "lõi", "dáng nghiệp vụ", "văn phòng", "trộn"
# Nhóm của từng mô-đun theo tiêu chí §4.3: gỡ Văn phòng đi thì mô-đun phải sửa gì. Thư mục office/, docread/ (của
# svc-files) là Văn phòng, apps/ (của svc-workflow) là lõi; __init__.py chỉ có chú thích thì không xếp.
NHOM: dict[str, str] = {
    "svc_files/__init__.py": LOI, "svc_workflow/__init__.py": LOI,     # chỉ chuỗi phiên bản
    # svc-files
    "svc_files/anchors.py": LOI, "svc_files/auth.py": LOI, "svc_files/clamav.py": LOI, "svc_files/filetype.py": LOI,
    "svc_files/imageclean.py": LOI, "svc_files/layout.py": LOI, "svc_files/ocr.py": LOI,
    "svc_files/open_data.py": LOI, "svc_files/openbao.py": LOI, "svc_files/pdflayout.py": LOI,
    "svc_files/pdftext.py": LOI, "svc_files/pii.py": LOI, "svc_files/status.py": LOI, "svc_files/storage.py": LOI,
    "svc_files/tracing.py": LOI, "svc_files/web.py": LOI, "svc_files/assist/store.py": LOI,
    "svc_files/imports/parse.py": LOI, "svc_files/imports/spool.py": LOI,
    "svc_files/hasura.py": DANG, "svc_files/lineage.py": DANG, "svc_files/sealed.py": DANG,
    "svc_files/search.py": DANG, "svc_files/signing.py": DANG, "svc_files/texts.py": DANG,
    "svc_files/vntext.py": DANG, "svc_files/imports/api.py": DANG, "svc_files/imports/store.py": DANG,
    "svc_files/assist/ai.py": DANG, "svc_files/assist/answer.py": DANG,
    "svc_files/assist/api.py": DANG, "svc_files/assist/chunks.py": DANG, "svc_files/assist/data.py": DANG,
    "svc_files/assist/extract.py": DANG, "svc_files/assist/grounding.py": DANG, "svc_files/assist/guide.py": DANG,
    "svc_files/assist/index.py": DANG, "svc_files/assist/meili.py": DANG, "svc_files/assist/retrieve.py": DANG,
    "svc_files/assist/route.py": DANG, "svc_files/assist/scope.py": DANG, "svc_files/assist/vi.py": DANG,
    "svc_files/archive.py": VP, "svc_files/archive_stats.py": VP, "svc_files/dispatch.py": VP,
    "svc_files/registers.py": VP, "svc_files/render.py": VP, "svc_files/assist/similar.py": VP,
    "svc_files/app.py": TRON, "svc_files/config.py": TRON,
    "svc_files/imports/runner.py": TRON,              # khung Importer, Handler là lõi; IncomingHandler là Văn phòng
    # svc-workflow
    "svc_workflow/alerts.py": LOI, "svc_workflow/flowable.py": LOI, "svc_workflow/openbao.py": LOI,
    "svc_workflow/parts.py": LOI, "svc_workflow/pii.py": LOI, "svc_workflow/tracing.py": LOI,
    "svc_workflow/thoi_gian.py": LOI,
    "svc_workflow/channels.py": DANG, "svc_workflow/directory.py": DANG, "svc_workflow/hasura.py": DANG,
    "svc_workflow/notify.py": DANG, "svc_workflow/schemas.py": DANG, "svc_workflow/subscriptions.py": DANG,
    "svc_workflow/tu_dong.py": DANG,                  # robot báo kèm văn bản: đọc office_documents_by_pk
    "svc_workflow/advisor.py": VP, "svc_workflow/dispatch.py": VP, "svc_workflow/files.py": VP,
    "svc_workflow/forms.py": VP, "svc_workflow/ot.py": VP, "svc_workflow/sla.py": VP, "svc_workflow/suggest.py": VP,
    "svc_workflow/workflow.py": VP,
    "svc_workflow/app.py": TRON, "svc_workflow/config.py": TRON,
}
THU_MUC = {"svc_files/office/": VP, "svc_files/docread/": VP, "svc_workflow/office/": VP, "svc_workflow/apps/": LOI}

VAI_TRO_VP = ("clerk", "staff", "manager", "director")
GIA_TRI_VP = re.compile(r"^(office\.|incoming$|clerk$|staff$|manager$|director$)")
# Cột thêm vào bảng core trong migration có nhắc office nhưng không thuộc Văn phòng (đã xem từng cột)
COT_LOI = {
    "core.file_texts.page_starts",    # vị trí đầu mỗi trang trong lớp chữ PDF (pdftext.py), lõi
    "core.tenants.sample_data",       # đơn vị mẫu do make seed nạp (seed/tenants.sql), lõi
}
GRAPHQL_DUOI = ("by_pk", "aggregate", "bool_exp", "insert_input", "set_input", "order_by", "pk_columns_input",
                "inc_input", "on_conflict", "constraint", "update_column", "select_column", "mutation_response",
                "stream_cursor_input", "arr_rel_insert_input", "obj_rel_insert_input", "args")


def nhom_cua(module: str) -> str | None:
    for prefix, group in THU_MUC.items():
        if module.startswith(prefix):
            return group
    return NHOM.get(module)


def modules(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Mọi mô-đun Python của hai dịch vụ, khóa "svc_files/assist/scope.py"; __init__.py chỉ có chú thích bị bỏ."""
    found = {}
    for pkg, rel in PACKAGES.items():
        base = root / rel
        for path in sorted(base.rglob("*.py")):
            if path.name == "__init__.py" and not ast.parse(path.read_text(encoding="utf-8")).body[1:]:
                continue
            found[f"{pkg}/{path.relative_to(base).as_posix()}"] = path
    return found


def _strip_sql(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def migrations(root: pathlib.Path) -> list[tuple[str, str]]:
    base = root / MIGRATIONS
    return [(d.name, _strip_sql((d / "up.sql").read_text(encoding="utf-8")))
            for d in sorted(base.iterdir()) if (d / "up.sql").is_file()]


def office_objects(migs: list[tuple[str, str]]) -> set[str]:
    """Tên bảng, view, hàm của schema office tạo trong migration."""
    names: set[str] = set()
    pattern = (r"create\s+(?:or\s+replace\s+)?(?:unlogged\s+)?(?:table|function|view|materialized\s+view)\s+"
               r"(?:if\s+not\s+exists\s+)?office\.(\w+)")
    for _, sql in migs:
        names.update(m.lower() for m in re.findall(pattern, sql, re.I))
    return names


def _strings(path: pathlib.Path) -> list[str]:
    """Hằng chuỗi trong mã, trừ docstring và chuỗi đứng một mình làm chú thích."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            skip.add(id(node.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip]


def _office_refs(text: str, objects: set[str]) -> set[str]:
    refs = set()
    for name in re.findall(r"\boffice\.(\w+)", text):
        if name in objects:
            refs.add(f"office.{name}")
    for rest in re.findall(r"\b(?:insert_|update_|delete_)?office_(\w+)", text):
        fits = [o for o in objects
                if rest == o or (rest.startswith(o + "_") and rest[len(o) + 1:] in GRAPHQL_DUOI)]
        best = max(fits, key=len, default=None)
        if best:
            refs.add(f"office.{best}")
    return refs


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def _import_nodes(tree: ast.Module) -> list[tuple[ast.Import | ast.ImportFrom, bool]]:
    """Mọi lệnh import kèm cờ "chạy lúc nạp mô-đun": đầu tệp, thân lớp, khối if/try/with ở mức đó là có; thân hàm
    (chạy khi gọi) là không; khối ``if TYPE_CHECKING:`` (chỉ cho chú thích kiểu) không tính."""
    out: list[tuple[ast.Import | ast.ImportFrom, bool]] = []

    def visit(nodes: list[Any], at_load: bool) -> None:
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                out.append((node, at_load))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(node.body, False)
            elif isinstance(node, ast.If) and _is_type_checking(node.test):
                visit(node.orelse, at_load)
            else:
                for field in ("body", "orelse", "finalbody", "handlers"):
                    child = getattr(node, field, None)
                    if isinstance(child, list):
                        visit(child, at_load)

    visit(tree.body, True)
    return out


def _imports(module: str, path: pathlib.Path) -> list[tuple[list[str], bool]]:
    """Mô-đun trong cùng gói mà mô-đun này import: mỗi tên là các ứng viên theo thứ tự ưu tiên ("svc_files/assist/
    similar" cho ``from .assist import similar``, rồi "svc_files/assist"), kèm cờ chạy lúc nạp mô-đun."""
    pkg = module.split("/", 1)[0]
    parent = list(pathlib.PurePosixPath(module).parent.parts[1:])
    out = []
    for node, at_load in _import_nodes(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == pkg and parts[1:]:
                    out.append(([f"{pkg}/" + "/".join(parts[1:])], at_load))
            continue
        if node.level:
            base = parent[:len(parent) - (node.level - 1)] if node.level > 1 else parent
            mod = [m for m in (node.module or "").split(".") if m]
        elif (node.module or "").split(".")[0] == pkg:
            base, mod = [], (node.module or "").split(".")[1:]
        else:
            continue
        for alias in node.names:
            candidates = [base + mod + [alias.name]] + ([base + mod] if mod else [])
            out.append(([f"{pkg}/" + "/".join(c) for c in candidates if c], at_load))
    return out


def _resolve(target: str, known: dict[str, pathlib.Path]) -> str | None:
    if f"{target}.py" in known:
        return f"{target}.py"
    if any(k.startswith(target + "/") for k in known):
        return target + "/"
    return None


def code_edges(root: pathlib.Path, objects: set[str]) -> tuple[set[str], dict[str, str | None]]:
    mods = modules(root)
    groups = {m: nhom_cua(m) for m in mods}
    edges = set()
    for module, path in mods.items():
        if groups[module] == VP:
            continue
        for candidates, at_load in _imports(module, path):
            resolved = next((r for r in (_resolve(c, mods) for c in candidates) if r), None)
            if resolved is None:
                continue
            group = nhom_cua(resolved) if not resolved.endswith("/") else THU_MUC.get(resolved)
            # import trong hàm chỉ được ở mô-đun trộn: đó là chỗ ráp, chạy khi phần Văn phòng được bật
            if group == VP and (at_load or groups[module] != TRON):
                edges.add(f"import {module} -> {resolved}")
        text = "\n".join(_strings(path))
        for ref in sorted(_office_refs(text, objects)):
            edges.add(f"du-lieu {module} -> {ref}")
        roles = sorted({r for r in VAI_TRO_VP if re.search(rf"[\"']{r}[\"']", path.read_text(encoding="utf-8"))
                        and any(s == r for s in _strings(path))})
        if roles:
            edges.add(f"vai-tro {module} -> {','.join(roles)}")
    return edges, groups


def statements(sql: str) -> list[str]:
    """Tách câu lệnh theo dấu ; nằm ngoài chuỗi '…' và thân $tag$…$tag$ (thân hàm có ; riêng của nó)."""
    out, buf, i, tag, quoted = [], [], 0, None, False
    while i < len(sql):
        c = sql[i]
        if tag:
            if sql.startswith(tag, i):
                buf.append(tag)
                i += len(tag)
                tag = None
                continue
        elif quoted:
            quoted = c != "'"
        elif c == "'":
            quoted = True
        elif c == "$" and (m := re.match(r"\$\w*\$", sql[i:])):
            tag = m.group(0)
            buf.append(tag)
            i += len(tag)
            continue
        elif c == ";":
            out.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    out.append("".join(buf).strip())
    return [s for s in out if s]


def _top_level(text: str) -> list[str]:
    """Tách theo dấu phẩy không nằm trong ngoặc: các cột của create table, các hành động của alter table."""
    parts, depth, buf = [], 0, []
    for c in text:
        if c == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        depth += (c == "(") - (c == ")")
        buf.append(c)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _names(text: str) -> list[tuple[str, str]]:
    """Các tên schema.tên trong danh sách của drop (bỏ phần tham số trong ngoặc)."""
    return [(s.lower(), n.lower()) for s, n in re.findall(r"(\w+)\.(\w+)", re.sub(r"\([^)]*\)", "", text))]


_CHECK = re.compile(r"check\s*\(\s*(\w+)\s+in\s*\(([^)]*)\)", re.I)


def db_edges(root: pathlib.Path, objects: set[str]) -> set[str]:
    """Trạng thái CSDL sau migration cuối: áp lần lượt create, replace, drop, set schema; chỉ trạng thái cuối có
    cạnh."""
    functions: dict[str, str] = {}                       # hàm, view của core → câu tạo mới nhất
    triggers: dict[tuple[str, str], tuple[str, str]] = {}   # (tên, schema.bảng) → (schema, hàm)
    checks: dict[tuple[str, str], tuple[str, list[str]]] = {}  # (bảng core, tên ràng buộc) → (cột, giá trị)
    columns: dict[str, str] = {}                         # core.bảng.cột do migration có nhắc office thêm → migration

    def drop_table(schema: str, table: str) -> None:
        for key in [k for k in triggers if k[1] == f"{schema}.{table}"]:
            del triggers[key]
        if schema == "core":
            for key in [k for k in checks if k[0] == table]:
                del checks[key]
            for key in [k for k in columns if k.startswith(f"core.{table}.")]:
                del columns[key]

    def add_check(table: str, name: str | None, text: str) -> None:
        if m := _CHECK.search(text):
            col = m.group(1).lower()
            checks[(table, (name or f"{table}_{col}_check").lower())] = (col, re.findall(r"'([^']*)'", m.group(2)))

    for migration, sql in migrations(root):
        office_tied = bool(re.search(r"\boffice\.", sql))
        for stmt in statements(sql):
            flat = " ".join(stmt.split())
            if m := re.match(r"create\s+(?:or\s+replace\s+)?(?:function|view)\s+core\.(\w+)", flat, re.I):
                functions[m.group(1).lower()] = stmt
            elif m := re.match(r"drop\s+(?:function|view)\s+(?:if\s+exists\s+)?(.*)", flat, re.I):
                for schema, name in _names(m.group(1)):
                    if schema == "core":
                        functions.pop(name, None)
                    for key in [k for k, v in triggers.items() if v == (schema, name)]:
                        del triggers[key]
            elif m := re.match(r"alter\s+(?:function|view)\s+core\.(\w+)(?:\([^)]*\))?\s+(set\s+schema|rename\s+to)\s+"
                               r"(\w+)", flat, re.I):
                body = functions.pop(m.group(1).lower(), None)
                if body is not None and m.group(2).lower().startswith("rename"):
                    functions[m.group(3).lower()] = body
            elif m := re.match(r"create\s+(?:or\s+replace\s+)?(?:constraint\s+)?trigger\s+(\w+)\s.*?\bon\s+(\w+)\.(\w+)"
                               r"\s.*?execute\s+(?:function|procedure)\s+(\w+)\.(\w+)", flat, re.I):
                name, schema, table, fn_schema, fn = (g.lower() for g in m.groups())
                triggers[(name, f"{schema}.{table}")] = (fn_schema, fn)
            elif m := re.match(r"drop\s+trigger\s+(?:if\s+exists\s+)?(\w+)\s+on\s+(\w+)\.(\w+)", flat, re.I):
                triggers.pop((m.group(1).lower(), f"{m.group(2).lower()}.{m.group(3).lower()}"), None)
            elif m := re.match(r"drop\s+table\s+(?:if\s+exists\s+)?(.*)", flat, re.I):
                for schema, table in _names(m.group(1)):
                    drop_table(schema, table)
            elif m := re.match(r"create\s+table\s+(?:if\s+not\s+exists\s+)?core\.(\w+)\s*\((.*)\)", flat, re.I):
                table = m.group(1).lower()
                for item in _top_level(m.group(2)):
                    if c := re.match(r"constraint\s+(\w+)\s+(check\b.*)", item, re.I):
                        add_check(table, c.group(1), c.group(2))
                    elif not re.match(r"(primary|unique|foreign|exclude)\b", item, re.I):
                        add_check(table, None, item)
            elif m := re.match(r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?core\.(\w+)\s+(.*)", flat, re.I):
                table = m.group(1).lower()
                for action in _top_level(m.group(2)):
                    if a := re.match(r"add\s+column\s+(?:if\s+not\s+exists\s+)?(\w+)(.*)", action, re.I):
                        key = f"core.{table}.{a.group(1).lower()}"
                        if office_tied and key not in COT_LOI:
                            columns[key] = migration
                        add_check(table, None, a.group(1) + a.group(2))
                    elif a := re.match(r"add\s+(?:constraint\s+(\w+)\s+)?(check\b.*)", action, re.I):
                        add_check(table, a.group(1), a.group(2))
                    elif a := re.match(r"drop\s+constraint\s+(?:if\s+exists\s+)?(\w+)", action, re.I):
                        checks.pop((table, a.group(1).lower()), None)
                    elif a := re.match(r"drop\s+column\s+(?:if\s+exists\s+)?(\w+)", action, re.I):
                        col = a.group(1).lower()
                        columns.pop(f"core.{table}.{col}", None)
                        for key in [k for k, v in checks.items() if k[0] == table and v[0] == col]:
                            del checks[key]
                    elif re.match(r"set\s+schema\b", action, re.I):
                        drop_table("core", table)

    edges = set()
    for fn, stmt in functions.items():
        for ref in sorted(_office_refs(stmt, objects)):
            edges.add(f"csdl ham core.{fn} -> {ref}")
    for (_, on), (fn_schema, fn) in triggers.items():
        if on.startswith("core.") and fn_schema == "office":
            edges.add(f"csdl trigger {on} -> office.{fn}")
        if on.startswith("office.") and fn_schema == "core" and fn != "audit":
            edges.add(f"csdl trigger {on} -> core.{fn}")
    for (table, _), (col, values) in checks.items():
        vp = sorted(v for v in values if GIA_TRI_VP.match(v))
        if vp:
            edges.add(f"csdl rang-buoc core.{table}.{col} -> {','.join(vp)}")
    for key, migration in columns.items():
        edges.add(f"csdl cot {key} <- {migration}")
    return edges


def metadata_edges(root: pathlib.Path, objects: set[str]) -> set[str]:
    edges = set()
    for path in sorted((root / TABLES).glob("core_*.yaml")):
        text = "\n".join(line.split(" #", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
                         if not line.lstrip().startswith("#"))
        refs = _office_refs(text, objects)
        refs.update(f"office.{n}" for n in re.findall(r"\{\s*name:\s*(\w+)\s*,\s*schema:\s*office\s*\}", text))
        refs.update(f"office.{n}" for n in re.findall(r"\{\s*schema:\s*office\s*,\s*name:\s*(\w+)\s*\}", text))
        refs.update(f"office.{n}" for n in re.findall(r"name:\s*(\w+)\s*\n\s*schema:\s*office\b", text))
        refs.update(f"office.{n}" for n in re.findall(r"schema:\s*office\s*\n\s*name:\s*(\w+)", text))
        for ref in sorted(refs):
            edges.add(f"metadata {path.name} -> {ref}")
        roles = sorted(set(re.findall(r"role:\s*(\w+)", text)) & set(VAI_TRO_VP))
        if roles:
            edges.add(f"vai-tro {path.name} -> {','.join(roles)}")
    return edges


def inventory(root: pathlib.Path = ROOT) -> dict[str, Any]:
    objects = office_objects(migrations(root))
    code, groups = code_edges(root, objects)
    edges = code | db_edges(root, objects) | metadata_edges(root, objects)
    return {"edges": sorted(edges), "groups": groups, "office_objects": len(objects)}


def known(path: pathlib.Path = KNOWN) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def main(argv: list[str]) -> int:
    inv = inventory()
    if argv == ["--json"]:
        print(json.dumps(inv, ensure_ascii=False, indent=2))
        return 0
    if argv:
        print(__doc__)
        return 2
    by_group: dict[str, list[str]] = {}
    for module, group in sorted(inv["groups"].items()):
        by_group.setdefault(group or "CHƯA XẾP", []).append(module)
    print(f"Mô-đun theo nhóm ({len(inv['groups'])}), schema office có {inv['office_objects']} bảng, view, hàm:")
    for group, mods in by_group.items():
        print(f"  {group}: {len(mods)}")
    by_face: dict[str, list[str]] = {}
    for edge in inv["edges"]:
        by_face.setdefault(edge.split(" ", 1)[0], []).append(edge)
    print(f"\nCạnh lõi → Văn phòng ({len(inv['edges'])}):")
    for face, edges in by_face.items():
        print(f"  {face} ({len(edges)})")
        for edge in edges:
            print(f"    {edge.split(' ', 1)[1]}")
    listed = set(known())
    new, gone = set(inv["edges"]) - listed, listed - set(inv["edges"])
    print(f"\nSo với {KNOWN.relative_to(ROOT)}: {len(new)} cạnh mới, {len(gone)} cạnh đã gỡ mà danh sách còn")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
