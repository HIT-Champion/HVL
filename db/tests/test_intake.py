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

"""Poka-yoke lớp 3 (F2.2): CSDL chặn văn bản đến sai kể cả khi ghi thẳng bằng quyền quản trị.

Cùng bộ ca thử với form và Action receiveIncoming (schemas/van-ban-den.cases.json). Mỗi ca chèn thẳng một dòng
trong khối DO rồi tự hủy bằng một lỗi riêng: thấy đúng lỗi đó là CSDL đã nhận dòng, không để lại gì.
"""

from __future__ import annotations

import json
import pathlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from conftest import SQLError, incoming, received, sql

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "schemas" / "van-ban-den.cases.json").read_text(encoding="utf-8"))
TODAY = datetime.now(timezone(timedelta(hours=7))).date()    # như created_at theo giờ Việt Nam trong ràng buộc
ACCEPTED = "moc-test-rollback"


def value(v: Any) -> Any:
    if isinstance(v, dict) and "$repeat" in v:
        return v["$repeat"] * v["times"]
    if isinstance(v, dict) and "$nfd" in v:
        return unicodedata.normalize("NFD", v["$nfd"])
    if isinstance(v, str) and (m := re.fullmatch(r"today([+-]\d+)?", v)):
        return (TODAY + timedelta(days=int(m.group(1) or 0))).isoformat()
    return v


def build(case: dict[str, Any]) -> dict[str, Any]:
    data = {k: value(v) for k, v in CASES["base"].items()}
    data.update({k: value(v) for k, v in case.get("set", {}).items()})
    for k in case.get("unset", []):
        data.pop(k, None)
    return data


def literal(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return "'" + str(v).replace("'", "''") + "'"


def write_directly(world, data: dict[str, Any], direction: str = "in", status: str = "received") -> str:
    """Chèn thẳng như superuser rồi hủy; trả lỗi của PostgreSQL (ACCEPTED nếu CSDL đã nhận dòng)."""
    row = {"tenant_id": world.tenant_a, "direction": direction, "status": status, "created_by": world.clerk_a.sub,
           **{k: v for k, v in data.items() if k != "file_ids"}}
    insert = (f"insert into office.documents ({', '.join(row)}) "
              f"values ({', '.join(literal(v) for v in row.values())})")
    try:
        sql(f"do $moc$ begin {insert}; raise exception '{ACCEPTED}'; end $moc$")
    except SQLError as exc:
        return str(exc)
    raise AssertionError("khối DO phải luôn kết thúc bằng lỗi")


@pytest.mark.parametrize("case", CASES["valid"], ids=lambda c: c["name"])
def test_database_accepts_what_the_form_accepts(world, case):
    """Không có dữ liệu nào qua được form và Action mà CSDL lại từ chối."""
    assert write_directly(world, build(case)) == ACCEPTED


@pytest.mark.parametrize("case", [c for c in CASES["invalid"] if "db" in c], ids=lambda c: c["name"])
def test_database_refuses_invalid_rows_written_directly(world, case):
    error = write_directly(world, build(case))
    assert case["db"] in error, error


def test_duplicate_is_refused_by_the_index(world):
    doc = incoming(world.tag, 801)
    received(world.clerk_a, doc)
    error = write_directly(world, {**doc, "issuer_name": doc["issuer_name"].upper()})
    assert "documents_in_dedup" in error


def test_constraints_were_validated_against_existing_rows():
    """Migration thêm ràng buộc NOT VALID rồi kiểm lại dữ liệu cũ; CSDL mới thì phải kiểm xong hết."""
    rows = sql("select conname, convalidated from pg_constraint where conrelid = 'office.documents'::regclass "
               "and conname in ('documents_in_symbol', 'documents_in_issuer', 'documents_in_summary', "
               "'documents_in_dates') order by conname")
    assert rows == [["documents_in_dates", "t"], ["documents_in_issuer", "t"], ["documents_in_summary", "t"],
                    ["documents_in_symbol", "t"]]


def test_rules_apply_only_to_incoming_documents(world):
    """Dự thảo văn bản đi chưa có số, ký hiệu, cơ quan ban hành, ngày ban hành: ràng buộc mới không đụng tới."""
    draft = {"type_code": "TB", "summary": "Thông báo lịch họp giao ban tháng 11", "department_id": world.dept_a1}
    assert write_directly(world, draft, direction="out", status="draft") == ACCEPTED
