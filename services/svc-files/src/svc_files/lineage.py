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

"""Phả hệ dữ liệu và kiểm chất lượng (F3.9) — sự kiện OpenLineage cho từng bước của job nộp lưu (F3.8).

Mỗi lượt nộp lưu một hồ sơ là một run của job cha ``moc.case_file.archive``; từng bước là một run con (facet
``parent``): ``.tables`` (bảng OLTP → Parquet), ``.files`` (bucket nóng → bucket lạnh), ``.manifest`` (Parquet + tệp →
manifest), ``.commit`` (manifest → CSDL). Sự kiện theo đặc tả OpenLineage 2-0-2, dựng bằng thư viện chuẩn (không thêm
phụ thuộc), ghi vào ``core.lineage_events`` qua Hasura; đặt MOC_OPENLINEAGE_URL thì gửi thêm tới một máy chủ nhận
OpenLineage (vd Marquez ``http://marquez:5000/api/v1/lineage``).

Quy ước tên dataset (theo quy ước đặt tên của OpenLineage):
- bảng PostgreSQL: namespace ``postgres://postgres:5432``, tên ``moc.<schema>.<bảng>``;
- đối tượng S3: namespace ``s3://<bucket>``, tên là key (``cold/<tenant>/case/<id>/documents-<sha256>.parquet``).

Kiểm chất lượng: mỗi bảng Parquet vừa dựng được DuckDB đọc lại (trước khi ghi sang lạnh) — số dòng phải bằng số dòng
lấy từ CSDL, các cột bắt buộc không có null. Kết quả là facet ``dataQualityAssertions``: ở bước ``tables`` nằm trong
facet của dataset vừa ghi (mở rộng của Signet — đặc tả định nghĩa facet này cho đầu vào), ở bước ``manifest`` nằm trong
``inputFacets`` của bảng đầu vào (đúng đặc tả, Marquez hiển thị được). Trượt một mục thì bước ``tables`` FAIL, job dừng
(cảnh báo trong nhật ký, ``quality_ok = false`` trong bảng phả hệ).

Bước nào lỗi thì run con của bước đó FAIL. Thông báo lỗi trong phả hệ chỉ có tên lớp lỗi (lỗi kiểm chất lượng thì có ký
hiệu hồ sơ, tên bảng) — không có tên tệp, số ký hiệu văn bản. Ghi phả hệ lỗi không làm hỏng việc nộp lưu: chỉ ghi cảnh
báo vào nhật ký.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx2

log = logging.getLogger("svc_files")

PRODUCER = "https://github.com/HIT-Champion/HVL/tree/main/services/svc-files"
SPEC = "https://openlineage.io/spec"
RUN_EVENT = f"{SPEC}/2-0-2/OpenLineage.json#/$defs/RunEvent"
JOB_NAMESPACE = "moc"
PG = "postgres://postgres:5432"

# Cột bắt buộc của từng bảng trong gói: null ở đây là dữ liệu hỏng, không nộp lưu
REQUIRED: dict[str, tuple[str, ...]] = {
    "documents": ("id", "case_file_id", "direction", "status", "type_code", "summary", "created_by", "created_at"),
    "assignments": ("id", "document_id", "role", "status", "assigned_by", "assigned_at"),
    "events": ("id", "document_id", "kind", "actor_kind", "created_at"),
}

INSERT = """
mutation ($o: core_lineage_events_insert_input!) { insert_core_lineage_events_one(object: $o) { id } }"""


def pg(table: str) -> dict[str, Any]:
    return {"namespace": PG, "name": f"moc.{table}", "facets": {}}


def s3(bucket: str, key: str, facets: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"namespace": f"s3://{bucket}", "name": key, "facets": facets or {}}


def _facet(name: str, version: str = "1-0-1", **fields: Any) -> dict[str, Any]:
    return {"_producer": PRODUCER, "_schemaURL": f"{SPEC}/facets/{version}/{name}.json#/$defs/{name}", **fields}


def schema_facet(columns: dict[str, str]) -> dict[str, Any]:
    return _facet("SchemaDatasetFacet", "1-1-1", fields=[{"name": c, "type": t} for c, t in columns.items()])


def quality_facets(name: str, expected_rows: int, measured: dict[str, int], size: int) -> tuple[dict, dict, bool]:
    """Từ số đo trên Parquet vừa ghi (``rows`` và số null từng cột) → facet dataset, facet đầu ra, đạt hay không."""
    assertions = [{"assertion": "row_count_equals_source", "success": measured["rows"] == expected_rows}]
    assertions += [{"assertion": "not_null", "column": col, "success": measured[col] == 0} for col in REQUIRED[name]]
    ok = all(a["success"] for a in assertions)
    facets = {"dataQualityAssertions": _facet("DataQualityAssertionsDatasetFacet", "1-0-1", assertions=assertions)}
    output = {"outputStatistics": _facet("OutputStatisticsOutputDatasetFacet", "1-0-2", rowCount=measured["rows"],
                                         size=size)}
    return facets, output, ok


def null_counts_sql(name: str) -> str:
    """Câu SELECT đếm dòng và null của các cột bắt buộc, chạy trên Parquet (bảng ``t``)."""
    cols = ", ".join(f'count(*) filter (where "{c}" is null) as "{c}"' for c in REQUIRED[name])
    return f"select count(*) as rows, {cols} from t"


class Lineage:
    """Phát sự kiện OpenLineage. ``store`` ghi một sự kiện vào CSDL (Hasura khóa quản trị); ``url`` tùy chọn."""

    def __init__(self, store: Callable[[str, dict[str, Any]], Awaitable[Any]] | None, url: str = "",
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self.store, self.url, self.clock, self.transport = store, url, clock, transport

    def event(self, kind: str, job: str, run_id: str, *, parent: tuple[str, str] | None = None,
              inputs: list[dict[str, Any]] | None = None, outputs: list[dict[str, Any]] | None = None,
              error: str | None = None) -> dict[str, Any]:
        run_facets: dict[str, Any] = {}
        if parent:
            run_facets["parent"] = _facet("ParentRunFacet", "1-1-0", run={"runId": parent[1]},
                                          job={"namespace": JOB_NAMESPACE, "name": parent[0]})
        if error:
            run_facets["errorMessage"] = _facet("ErrorMessageRunFacet", "1-0-1", message=error,
                                                programmingLanguage="python")
        return {
            "eventType": kind, "eventTime": self.clock().isoformat(), "producer": PRODUCER, "schemaURL": RUN_EVENT,
            "run": {"runId": run_id, "facets": run_facets},
            "job": {"namespace": JOB_NAMESPACE, "name": job, "facets": {}},
            "inputs": inputs or [], "outputs": outputs or [],
        }

    async def emit(self, tenant_id: str | None, event: dict[str, Any]) -> None:
        """Ghi một sự kiện; lỗi ghi chỉ thành cảnh báo trong nhật ký — phả hệ không được chặn việc nộp lưu."""
        datasets = event["inputs"] + event["outputs"]
        checks = [a["success"] for d in datasets for a in
                  d.get("facets", {}).get("dataQualityAssertions", {}).get("assertions", [])]
        row = {
            "tenant_id": tenant_id, "run_id": event["run"]["runId"],
            "parent_run_id": event["run"]["facets"].get("parent", {}).get("run", {}).get("runId"),
            "job": event["job"]["name"], "event_type": event["eventType"], "event_time": event["eventTime"],
            "inputs": [f"{d['namespace']}/{d['name']}" for d in event["inputs"]],
            "outputs": [f"{d['namespace']}/{d['name']}" for d in event["outputs"]],
            "quality_ok": all(checks) if checks else None, "event": event,
        }
        if self.store is not None:
            try:
                await self.store(INSERT, {"o": row})
            except Exception as exc:  # noqa: BLE001 — phả hệ hỏng không làm hỏng nộp lưu
                log.warning(json.dumps({"event": "lineage.store_failed", "job": row["job"], "error": str(exc)},
                                       ensure_ascii=False))
        if self.url:
            try:
                async with httpx2.AsyncClient(timeout=2, transport=self.transport) as client:
                    (await client.post(self.url, json=event)).raise_for_status()
            except Exception as exc:  # noqa: BLE001 — kể cả địa chỉ sai cú pháp: không chặn nộp lưu
                log.warning(json.dumps({"event": "lineage.send_failed", "job": row["job"], "error": str(exc)},
                                       ensure_ascii=False))
        if row["quality_ok"] is False:
            log.warning(json.dumps({"event": "lineage.quality_failed", "job": row["job"], "run_id": row["run_id"],
                                    "datasets": [d["name"] for d in datasets if not all(
                                        a["success"] for a in d.get("facets", {}).get(
                                            "dataQualityAssertions", {}).get("assertions", []))]},
                                   ensure_ascii=False))


def new_run() -> str:
    return str(uuid.uuid4())
