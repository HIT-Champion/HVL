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

"""Phân tích dữ liệu đã nộp lưu (#304, nguyên lý (i)): DuckDB tổng hợp trên các gói Parquet trong bucket lạnh.

Trang Điều hành (F3.11) đọc dữ liệu nóng qua bốn khung nhìn của Hasura; phần "Văn bản đã nộp lưu" đọc kho lạnh:

1. Hasura, bằng token người xem, trả các hồ sơ đã nộp lưu họ xem được: vị trí gói, băm manifest. Route chỉ nhận lãnh
   đạo đơn vị (như trang Điều hành), Hasura lọc theo đơn vị trong token.
2. Mỗi gói: manifest tải theo băm trong CSDL, kiểm băm (``read_manifest``, như phòng đọc); bảng
   ``documents-<sha256>.parquet`` so băm với manifest. Gói không nằm dưới ``cold/<đơn vị của người xem>/``, manifest
   của hồ sơ khác, lệch băm, thiếu đối tượng: bỏ khỏi số liệu, báo trong ``unreadable``.
3. DuckDB đọc mọi bảng văn bản một lượt (``read_parquet`` trên danh sách tệp), nối với bảng nhỏ dựng từ manifest (năm,
   phòng của hồ sơ), ra số đếm theo năm ban hành và chiều, theo loại văn bản, theo phòng lập hồ sơ. Chỉ có số đếm:
   không trích yếu, số ký hiệu hay tên người. Văn bản hạn chế không có trong gói nào (``archive.py`` không nộp lưu hồ
   sơ có văn bản hạn chế), nên không có gì phải tách riêng như ở khung nhìn nóng.

Gói không đổi (tên theo băm, khóa ghi), nên kết quả chỉ phụ thuộc tập manifest: lưu đệm theo đơn vị, tính lại khi có hồ
sơ mới nộp lưu. Kết quả có gói không đọc được thì không lưu đệm. Mỗi tập manifest mới là một run OpenLineage
``moc.archive.stats`` (đầu vào: các bảng Parquet đã đọc) trong ``core.lineage_events`` — phả hệ ghi lại bước đọc dữ
liệu lạnh để phân tích; lỗi ghi phả hệ chỉ thành cảnh báo trong nhật ký.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import pathlib
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import duckdb

from .archive import ArchiveError, ColdStore, package_prefix, read_manifest
from .lineage import Lineage, s3
from .storage import ObjectMissing

log = logging.getLogger("svc_files")

JOB = "moc.archive.stats"

TOTALS = """
select count(*)::int as documents,
       count(*) filter (where direction = 'in')::int as incoming,
       count(*) filter (where direction = 'out')::int as outgoing
  from docs"""

# Năm ban hành của văn bản (văn bản đến: ngày của cơ quan gửi); thiếu thì năm của hồ sơ
BY_YEAR = """
select coalesce(year(d.issued_on), c.year)::int as year,
       count(*) filter (where d.direction = 'in')::int as incoming,
       count(*) filter (where d.direction = 'out')::int as outgoing
  from docs d join cases c on c.id = d.case_file_id
 group by 1
 order by 1 nulls last"""

BY_TYPE = """
select type_code,
       count(*) filter (where direction = 'in')::int as incoming,
       count(*) filter (where direction = 'out')::int as outgoing
  from docs
 group by 1
 order by count(*) desc, 1"""

# Phòng lập hồ sơ (manifest), kể cả hồ sơ có gói văn bản rỗng
BY_DEPARTMENT = """
select c.department_id,
       count(distinct c.id)::int as case_files,
       count(d.id)::int as documents
  from cases c left join docs d on d.case_file_id = c.id
 group by 1
 order by documents desc, case_files desc, 1 nulls last"""


@dataclass(frozen=True)
class Stats:
    """Số liệu đã nộp lưu của một đơn vị, tính từ ``case_files`` gói đọc được."""

    case_files: int
    documents: int
    incoming: int
    outgoing: int
    by_year: list[dict[str, Any]]
    by_type: list[dict[str, Any]]
    by_department: list[dict[str, Any]]
    unreadable: list[dict[str, str]]     # {case_file_id, code}: gói lệch băm, thiếu, sai chỗ — không vào số liệu
    computed_at: datetime
    inputs: list[str] = field(default_factory=list)   # key các bảng Parquet đã đọc (đầu vào của run phả hệ)


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def aggregate(tables: list[pathlib.Path], cases: list[tuple[str, int | None, str | None]]) -> dict[str, Any]:
    """DuckDB: các bảng văn bản (Parquet, cùng lược đồ ``archive.SCHEMAS``) nối với hồ sơ (id, năm, phòng) → số đếm."""
    con = duckdb.connect()
    try:
        con.execute("create table cases (id uuid, year integer, department_id varchar)")
        if cases:
            con.executemany("insert into cases values (?::uuid, ?, ?)", cases)
        if tables:
            files = ", ".join(f"'{p}'" for p in tables)      # tên tệp do chính hàm gọi đặt (băm hex), không từ ngoài
            con.execute(f"create view docs as select direction, type_code, issued_on, case_file_id, id"
                        f" from read_parquet([{files}])")
        else:
            con.execute("create table docs (direction varchar, type_code varchar, issued_on date, case_file_id uuid,"
                        " id uuid)")
        return {**_rows(con, TOTALS)[0], "by_year": _rows(con, BY_YEAR), "by_type": _rows(con, BY_TYPE),
                "by_department": _rows(con, BY_DEPARTMENT)}
    finally:
        con.close()


def compute(cold: ColdStore, tenant_id: str, packages: list[dict[str, Any]], now: datetime) -> Stats:
    """Đọc, kiểm băm từng gói rồi tổng hợp. ``packages``: hồ sơ đã nộp lưu (id, code, archive_key, archive_sha256)
    người xem được. ``StorageError`` (kho không trả lời) đi ra ngoài; gói hỏng chỉ vào ``unreadable``."""
    cases: list[tuple[str, int | None, str | None]] = []
    unreadable: list[dict[str, str]] = []
    inputs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tables: list[pathlib.Path] = []
        for p in packages:
            key = p["archive_key"]
            try:
                if key != package_prefix(tenant_id, p["id"]):
                    raise ArchiveError("gói không nằm dưới tiền tố của đơn vị người xem")
                manifest = read_manifest(cold, key, p["archive_sha256"])
                cf = manifest["case_file"]
                if cf["id"] != p["id"] or cf["tenant_id"] != tenant_id:
                    raise ArchiveError("manifest của hồ sơ khác")
                table = manifest["tables"]["documents"]
                if table["path"]:
                    data = cold.get(f"{key}{table['path']}")
                    if hashlib.sha256(data).hexdigest() != table["sha256"]:
                        raise ArchiveError("bảng văn bản (Parquet) không khớp băm trong manifest")
                    path = pathlib.Path(tmp) / f"{table['sha256']}.parquet"
                    path.write_bytes(data)
                    tables.append(path)
                    inputs.append(f"{key}{table['path']}")
            except (ArchiveError, ObjectMissing) as exc:
                unreadable.append({"case_file_id": p["id"], "code": p["code"]})
                log.warning(json.dumps({"event": "case_file.archive_stats_skipped", "case_file_id": p["id"],
                                        "error": str(exc)}, ensure_ascii=False))
                continue
            cases.append((p["id"], cf.get("year"), cf.get("department_id")))
        counts = aggregate(tables, cases)
    return Stats(case_files=len(cases), unreadable=unreadable, computed_at=now, inputs=inputs, **counts)


class ArchiveStats:
    """Số liệu đã nộp lưu cho trang Điều hành: lưu đệm theo đơn vị, tính lại khi tập manifest đổi."""

    def __init__(self, cold: ColdStore, lineage: Lineage | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.cold = cold
        self.lineage = lineage
        self.clock = clock
        # một lượt tính mỗi lúc: nhiều người cùng mở trang thì người sau đợi rồi lấy kết quả đã lưu đệm, không cùng
        # tải lại mọi gói
        self.lock = asyncio.Lock()
        self._cache: dict[str, tuple[tuple[tuple[str, str], ...], Stats]] = {}
        self._traced: dict[str, tuple[tuple[str, str], ...]] = {}    # tập manifest đã ghi phả hệ, theo đơn vị

    async def get(self, tenant_id: uuid.UUID, packages: list[dict[str, Any]]) -> Stats:
        tenant = str(tenant_id)
        snapshot = tuple(sorted((p["id"], p["archive_sha256"]) for p in packages))
        async with self.lock:
            cached = self._cache.get(tenant)
            if cached and cached[0] == snapshot:
                return cached[1]
            stats = await asyncio.to_thread(compute, self.cold, tenant, packages, self.clock())
            if not stats.unreadable:
                self._cache[tenant] = (snapshot, stats)
            trace = stats.inputs and self._traced.get(tenant) != snapshot
            if trace:
                self._traced[tenant] = snapshot
        if trace and self.lineage is not None:
            await self.lineage.emit(tenant, self.lineage.event(
                "COMPLETE", JOB, str(uuid.uuid4()), inputs=[s3(self.cold.bucket, key) for key in stats.inputs]))
        return stats
