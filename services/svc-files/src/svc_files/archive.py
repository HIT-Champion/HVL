# Copyright 2026 Mộc Team
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

"""Nộp lưu hồ sơ — dữ liệu nóng sang lạnh (F3.8; NĐ 30/2020 Điều 28–31, Luật Lưu trữ 2024).

Hồ sơ công việc đã đóng (``office.case_files``, status ``closed``) từ MOC_ARCHIVE_AFTER_DAYS ngày thì được nộp lưu:

1. Đọc băm từng tệp trong bucket nóng, so với băm đã ghi lúc tải lên. Lệch một tệp là dừng, chưa ghi gì sang lạnh.
2. Ghi gói lưu trữ vào bucket lạnh (cùng bucket khóa ghi với mốc neo sổ kiểm toán), dưới
   ``cold/<tenant_id>/case/<case_file_id>/``, mọi tên theo băm nội dung:
   - ``documents-<sha256>.parquet``, ``assignments-<sha256>.parquet``, ``events-<sha256>.parquet``: văn bản, giao
     việc, dòng thời gian (DuckDB ghi Parquet nén zstd theo lược đồ cố định, gói nào cũng cùng kiểu cột);
   - ``files/<sha256>``: từng tệp của văn bản, chép nguyên byte từ bucket nóng;
   - ``manifest-<sha256>.json``: liệt kê từng phần kèm SHA-256 và số dòng. Băm của manifest là ``archive_sha256``.
   Mọi đối tượng ghi kèm hạn giữ COMPLIANCE (S3 Object Lock) theo thời hạn bảo quản của hồ sơ (vĩnh viễn: 100 năm).
   Đối tượng đã có cùng băm thì không ghi lại (lượt chạy lại không đẻ thêm phiên bản bị khóa). Tên theo băm nên hai
   lượt chạy cùng lúc không đè manifest của nhau.
3. Đọc lại từng đối tượng từ bucket lạnh, so băm. Chỉ khi khớp hết mới sang bước 4.
4. Hàm SQL ``office.archive_case_file`` (một giao dịch, khóa dòng): kiểm CSDL còn đúng như lúc chụp vào gói, rồi hồ sơ
   → ``archived`` (archive_key, archive_sha256), văn bản → ``archived``, xóa dòng thời gian, liên kết tệp; tệp →
   ``storage_tier = 'cold'``; sự kiện ``case_file.archived`` vào sổ kiểm toán. Lệch một chỗ thì không đổi gì, lượt
   sau làm lại. Giao việc ở lại: là căn cứ quyền xem văn bản và cột "đơn vị nhận" của sổ đăng ký. Dòng văn bản rút
   gọn ở lại: vẫn tìm thấy theo số, ký hiệu, trích yếu; cổng xác thực vẫn trả lời "khớp" theo mã tra cứu và băm.
5. Xóa bản trong bucket nóng (lỗi ở bước này chỉ để thừa đối tượng, không mất gì).

Một hồ sơ lỗi không chặn các hồ sơ khác: lượt nền ghi lỗi rồi làm hồ sơ kế tiếp, giờ sau thử lại.

Phòng đọc: ``read_package`` tải manifest theo ``archive_sha256`` trong CSDL, kiểm băm, rồi DuckDB đọc
``documents-….parquet`` — dùng cho ``GET /api/case-files/{id}/archive``.

Chạy tay trong container (nộp lưu ngay một hồ sơ đã đóng, không đợi đủ ngày):

    python -m svc_files.archive now --case-file <id>
    python -m svc_files.archive now --after-days 0      # mọi hồ sơ đã đóng
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import pathlib
import sys
import tempfile
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import duckdb
from botocore.exceptions import BotoCoreError, ClientError

from .anchors import AnchorStore
from .storage import ObjectMissing, StorageError

log = logging.getLogger("svc_files")

FORMAT = "moc-archive/1"
ACTOR = "svc-files:archive"
PERMANENT_YEARS = 100          # hồ sơ bảo quản vĩnh viễn (retention_years null): khóa ghi 100 năm
RETRY_AFTER = timedelta(hours=24)   # hồ sơ vừa lỗi: lượt nền bỏ qua chừng ấy, không chiếm chỗ của hồ sơ khác

# Lược đồ cố định của từng bảng trong gói: kiểu cột không đổi theo dữ liệu của từng hồ sơ
SCHEMAS: dict[str, dict[str, str]] = {
    "documents": {
        "id": "UUID", "case_file_id": "UUID", "direction": "VARCHAR", "status": "VARCHAR", "type_code": "VARCHAR",
        "symbol": "VARCHAR", "issuer_name": "VARCHAR", "issued_on": "DATE", "summary": "VARCHAR", "body": "VARCHAR",
        "urgency": "VARCHAR", "is_public": "BOOLEAN", "register_number": "INTEGER", "registered_at": "TIMESTAMPTZ",
        "due_on": "DATE", "recipients": "VARCHAR[]", "content_sha256": "VARCHAR", "verify_code": "VARCHAR",
        "department_id": "UUID", "signer_id": "VARCHAR", "reply_to_id": "UUID", "created_by": "VARCHAR",
        "created_at": "TIMESTAMPTZ", "updated_at": "TIMESTAMPTZ",
    },
    "assignments": {
        "id": "UUID", "document_id": "UUID", "parent_id": "UUID", "department_id": "UUID", "user_id": "VARCHAR",
        "role": "VARCHAR", "instruction": "VARCHAR", "due_on": "DATE", "status": "VARCHAR", "result_note": "VARCHAR",
        "assigned_by": "VARCHAR", "assigned_at": "TIMESTAMPTZ", "completed_at": "TIMESTAMPTZ",
    },
    "events": {
        "id": "BIGINT", "document_id": "UUID", "kind": "VARCHAR", "actor_id": "VARCHAR", "actor_kind": "VARCHAR",
        "note": "VARCHAR", "data": "JSON", "created_at": "TIMESTAMPTZ",
    },
}

CLOSED = """
query Closed($before: date!, $limit: Int!, $skip: [uuid!]!) {
  office_case_files(where: {status: {_eq: "closed"}, closed_on: {_lte: $before}, id: {_nin: $skip}},
                    order_by: {closed_on: asc}, limit: $limit) { id }
}"""

CASE_FILE = """
query CaseFile($id: uuid!) {
  office_case_files_by_pk(id: $id) {
    id tenant_id department_id year code title retention_years status closed_on created_by created_at
    case_file_documents(order_by: {added_at: asc}) {
      added_by added_at
      document {
        id direction status restricted type_code symbol issuer_name issued_on summary body urgency is_public
        register_number registered_at due_on recipients content_sha256 verify_code department_id signer_id
        reply_to_id created_by created_at updated_at
        files { role added_by added_at file { id object_key filename mime_type size_bytes sha256 } }
        assignments { id parent_id department_id user_id role instruction due_on status result_note assigned_by
                      assigned_at completed_at }
        events { id kind actor_id actor_kind note data created_at }
      }
    }
  }
}"""

# Tệp còn gắn với văn bản ngoài hồ sơ này thì không chuyển lạnh, không xóa bản nóng
SHARED_FILES = """
query Shared($files: [uuid!]!, $docs: [uuid!]!) {
  office_document_files(where: {file_id: {_in: $files}, document_id: {_nin: $docs}}) { file_id }
}"""

# Hàm SQL office.archive_case_file (migration 1792281601300): kiểm lại rồi đổi CSDL trong một giao dịch
ARCHIVE = """
mutation Archive($p: jsonb!) {
  office_archive_case_file(args: {p: $p}) { id status }
}"""


class ArchiveError(Exception):
    """Không nộp lưu được hồ sơ — thông báo cho người vận hành."""


def package_prefix(tenant_id: str, case_file_id: str) -> str:
    return f"cold/{tenant_id}/case/{case_file_id}/"


def manifest_key(archive_key: str, archive_sha256: str) -> str:
    return f"{archive_key}manifest-{archive_sha256}.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(bytea: str | None) -> str | None:
    return bytea[2:] if bytea and bytea.startswith("\\x") else bytea


def _add_years(moment: datetime, years: int) -> datetime:
    """Cộng năm theo lịch (29/02 sang năm không nhuận thành 28/02) — không nhân 365 ngày."""
    try:
        return moment.replace(year=moment.year + years)
    except ValueError:
        return moment.replace(year=moment.year + years, day=28)


def to_parquet(rows: list[dict[str, Any]], workdir: pathlib.Path, name: str) -> bytes:
    """Ghi các dòng (dict JSON) thành Parquet bằng DuckDB theo lược đồ cố định ``SCHEMAS[name]``."""
    src = workdir / f"{name}.jsonl"
    out = workdir / f"{name}.parquet"
    src.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    columns = "{" + ", ".join(f"'{col}': '{kind}'" for col, kind in SCHEMAS[name].items()) + "}"
    con = duckdb.connect()
    try:
        con.execute(f"copy (select * from read_json('{src}', format='newline_delimited', columns={columns}))"
                    f" to '{out}' (format parquet, compression zstd)")
    finally:
        con.close()
    return out.read_bytes()


def read_parquet(data: bytes, sql: str) -> list[dict[str, Any]]:
    """Chạy một câu SELECT trên tệp Parquet (bảng tên ``t``), trả các dòng dạng dict."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "t.parquet"
        path.write_bytes(data)
        con = duckdb.connect()
        try:
            con.execute(f"create view t as select * from read_parquet('{path}')")
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
        finally:
            con.close()


class ColdStore:
    """Bucket lạnh khóa ghi: ghi đối tượng kèm hạn giữ COMPLIANCE, đọc lại để kiểm băm."""

    def __init__(self, s3: Any, bucket: str) -> None:
        self._s3 = s3
        self.bucket = bucket

    def ensure(self) -> None:
        """Tạo bucket bật khóa ghi nếu chưa có (cùng cách với mốc neo); có mà không khóa thì từ chối."""
        AnchorStore(self._s3, self.bucket, 1).ensure_bucket()

    def _stored_sha256(self, key: str) -> str | None:
        try:
            return self._s3.head_object(Bucket=self.bucket, Key=key).get("Metadata", {}).get("sha256")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                return None
            raise StorageError(f"Không đọc được {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"Không đọc được {key}: {exc}") from exc

    def put(self, key: str, data: bytes, content_type: str, retain_until: datetime) -> None:
        """Ghi kèm khóa COMPLIANCE; đã có đúng nội dung này (lượt trước) thì thôi, không thêm phiên bản bị khóa."""
        digest = _sha256(data)
        if self._stored_sha256(key) == digest:
            return
        try:
            self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                                Metadata={"sha256": digest}, ObjectLockMode="COMPLIANCE",
                                ObjectLockRetainUntilDate=retain_until)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Không ghi được {key} vào bucket lạnh: {exc}") from exc

    def get(self, key: str) -> bytes:
        try:
            return self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                raise ObjectMissing(f"Không có {key} trong bucket lạnh") from exc
            raise StorageError(f"Không đọc được {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"Không đọc được {key}: {exc}") from exc


@dataclass(frozen=True)
class Archived:
    case_file_id: str
    code: str
    archive_key: str
    archive_sha256: str
    documents: int
    files: int
    bytes: int


class Archiver:
    """Nộp lưu hồ sơ đã đóng. ``hasura`` là HasuraClient (khóa quản trị), ``hot`` là ObjectStore bucket nóng."""

    def __init__(self, hasura: Any, hot: Any, cold: ColdStore, *, after_days: int, interval_s: float = 3600.0,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.hasura = hasura
        self.hot = hot
        self.cold = cold
        self.after_days = after_days
        self.interval_s = interval_s
        self.clock = clock
        self.failed_at: dict[str, datetime] = {}     # hồ sơ lỗi ở lượt nền → lúc lỗi

    async def _admin(self, query: str, variables: dict[str, Any], request_id: str = "") -> dict[str, Any]:
        headers = {"X-Hasura-User-Id": ACTOR}
        if request_id:
            headers["X-Hasura-Request-Id"] = request_id
        return await self.hasura.admin(query, variables, headers)

    async def due(self, after_days: int | None = None, limit: int = 20) -> list[str]:
        days = self.after_days if after_days is None else after_days
        now = self.clock()
        before = (now - timedelta(days=days)).date()
        skip = [i for i, at in self.failed_at.items() if now - at < RETRY_AFTER]
        data = await self._admin(CLOSED, {"before": before.isoformat(), "limit": limit, "skip": skip})
        return [row["id"] for row in data["office_case_files"]]

    async def _read_hot(self, f: dict[str, Any]) -> bytes:
        body = b"".join(await asyncio.to_thread(lambda k=f["object_key"]: list(self.hot.read_stream(k))))
        if _sha256(body) != f["sha256"]:
            raise ArchiveError(f"tệp {f['filename']} trong bucket nóng không khớp băm đã ghi — dừng nộp lưu")
        return body

    async def archive(self, case_file_id: str) -> Archived:
        request_id = str(uuid.uuid4())
        data = await self._admin(CASE_FILE, {"id": case_file_id})
        cf = data["office_case_files_by_pk"]
        if cf is None:
            raise ArchiveError(f"không có hồ sơ {case_file_id}")
        if cf["status"] != "closed":
            raise ArchiveError(f"hồ sơ {cf['code']} đang {cf['status']}, chỉ nộp lưu hồ sơ đã đóng")
        links = cf.pop("case_file_documents")
        if not links:
            raise ArchiveError(f"hồ sơ {cf['code']} không có văn bản nào")
        docs = [link["document"] for link in links]
        # cùng điều kiện hàm SQL sẽ kiểm — sai thì dừng trước khi ghi gì sang bucket lạnh (đối tượng ở đó bị khóa)
        wrong = [d["symbol"] or d["id"] for d in docs if d.pop("restricted") or d["status"] not in ("done", "issued")]
        if wrong:
            raise ArchiveError(f"hồ sơ {cf['code']}: văn bản {', '.join(wrong)} không còn ở trạng thái nộp lưu được")
        doc_ids = [d["id"] for d in docs]
        # Thời hạn tính từ ngày đóng hồ sơ, không từ giờ chạy: lượt chạy lại ra đúng manifest cũ, không thêm đối tượng
        # bị khóa. Đã quá hạn (hồ sơ đóng lâu, thời hạn ngắn) thì giữ tới hết ngày mai.
        closed = datetime.fromisoformat(cf["closed_on"]).replace(tzinfo=UTC)
        today = datetime.combine(self.clock().date(), datetime.min.time(), UTC)
        retain_until = max(_add_years(closed, cf["retention_years"] or PERMANENT_YEARS), today + timedelta(days=2))
        prefix = package_prefix(cf["tenant_id"], cf["id"])

        files: dict[str, dict[str, Any]] = {}
        for d in docs:
            for link in d["files"]:
                f = link["file"]
                files.setdefault(f["id"], {**f, "sha256": _hex(f["sha256"]), "documents": []})["documents"].append(
                    {"document_id": d["id"], "role": link["role"]})
        # Bước 1: mọi tệp nóng phải khớp băm trước khi ghi bất cứ gì sang bucket lạnh (đối tượng lạnh bị khóa nhiều năm)
        for f in files.values():
            await self._read_hot(f)
        shared = {row["file_id"] for row in (await self._admin(
            SHARED_FILES, {"files": list(files), "docs": doc_ids}))["office_document_files"]}
        await asyncio.to_thread(self.cold.ensure)

        # Bước 2: tệp, chép nguyên byte (đọc lại và kiểm băm lần nữa ngay trước khi ghi)
        entries: list[dict[str, Any]] = []
        total = 0
        for f in files.values():
            body = await self._read_hot(f)
            await asyncio.to_thread(self.cold.put, f"{prefix}files/{f['sha256']}", body, f["mime_type"], retain_until)
            total += len(body)
            entries.append({"path": f"files/{f['sha256']}", "sha256": f["sha256"], "bytes": len(body),
                            "filename": f["filename"], "mime_type": f["mime_type"], "file_id": f["id"],
                            "documents": f["documents"]})

        # Bảng: văn bản (không kèm tệp, giao việc, dòng thời gian lồng nhau), giao việc, dòng thời gian
        rows = {
            "documents": [{**{k: v for k, v in d.items() if k not in ("files", "assignments", "events")},
                           "content_sha256": _hex(d["content_sha256"]), "case_file_id": cf["id"]} for d in docs],
            "assignments": [{**a, "document_id": d["id"]} for d in docs for a in d["assignments"]],
            "events": [{**e, "document_id": d["id"]} for d in docs for e in d["events"]],
        }
        tables: dict[str, dict[str, Any]] = {}
        with tempfile.TemporaryDirectory() as tmp:
            for name in SCHEMAS:
                if not rows[name]:
                    tables[name] = {"path": None, "rows": 0}
                    continue
                data_bytes = await asyncio.to_thread(to_parquet, rows[name], pathlib.Path(tmp), name)
                digest = _sha256(data_bytes)
                path = f"{name}-{digest}.parquet"
                await asyncio.to_thread(self.cold.put, f"{prefix}{path}", data_bytes,
                                        "application/vnd.apache.parquet", retain_until)
                total += len(data_bytes)
                tables[name] = {"path": path, "rows": len(rows[name]), "sha256": digest, "bytes": len(data_bytes)}

        manifest = {
            "format": FORMAT,
            "case_file": {k: cf[k] for k in ("id", "tenant_id", "department_id", "year", "code", "title",
                                             "retention_years", "closed_on", "created_by", "created_at")},
            "retain_until": retain_until.isoformat(),
            "tables": tables,
            "files": entries,
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        archive_sha = _sha256(manifest_bytes)
        await asyncio.to_thread(self.cold.put, manifest_key(prefix, archive_sha), manifest_bytes, "application/json",
                                retain_until)

        # Bước 3: đọc lại cả gói từ bucket lạnh trước khi gỡ gì khỏi OLTP
        expected = {manifest_key(prefix, archive_sha): archive_sha}
        expected |= {f"{prefix}{t['path']}": t["sha256"] for t in tables.values() if t["path"]}
        expected |= {f"{prefix}{e['path']}": e["sha256"] for e in entries}
        for key, digest in expected.items():
            if _sha256(await asyncio.to_thread(self.cold.get, key)) != digest:
                raise ArchiveError(f"đọc lại {key} từ bucket lạnh không khớp băm — chưa gỡ gì khỏi CSDL")

        # Bước 4: CSDL — hàm SQL kiểm lại đúng những dòng đã vào gói rồi mới đổi, trong một giao dịch
        cold_files = [fid for fid in files if fid not in shared]
        result = await self._admin(ARCHIVE, {"p": {
            "id": cf["id"], "archive_key": prefix, "archive_sha256": archive_sha, "bucket": self.cold.bucket,
            "documents": doc_ids, "events": [e["id"] for e in rows["events"]],
            "links": [{"document_id": doc["document_id"], "file_id": f["id"]}
                      for f in files.values() for doc in f["documents"]],
            "cold_files": cold_files, "files": len(entries),
        }}, request_id)
        if [row["status"] for row in result["office_archive_case_file"]] != ["archived"]:
            raise ArchiveError(f"hồ sơ {cf['code']}: CSDL không xác nhận đã nộp lưu")

        # Bước 5: bản nóng
        for fid in cold_files:
            try:
                await asyncio.to_thread(self.hot.delete, files[fid]["object_key"])
            except StorageError as exc:  # thừa một đối tượng trong bucket nóng, không mất gì
                log.warning(json.dumps({"event": "case_file.archive_hot_delete_failed", "error": str(exc)},
                                       ensure_ascii=False))
        done = Archived(cf["id"], cf["code"], prefix, archive_sha, len(docs), len(entries), total)
        log.info(json.dumps({"event": "case_file.archived", **asdict(done)}, ensure_ascii=False))
        return done

    async def run_once(self, after_days: int | None = None) -> tuple[list[Archived], list[dict[str, str]]]:
        """Nộp lưu mọi hồ sơ đến hạn. Một hồ sơ lỗi thì ghi lại rồi làm hồ sơ kế tiếp — không chặn cả hàng."""
        done: list[Archived] = []
        failed: list[dict[str, str]] = []
        for case_file_id in await self.due(after_days):
            try:
                done.append(await self.archive(case_file_id))
                self.failed_at.pop(case_file_id, None)
            except Exception as exc:  # noqa: BLE001 — một hồ sơ hỏng không được chặn các hồ sơ khác
                self.failed_at[case_file_id] = self.clock()
                failed.append({"case_file_id": case_file_id, "error": str(exc)})
                log.warning(json.dumps({"event": "case_file.archive_failed", "case_file_id": case_file_id,
                                        "error": str(exc)}, ensure_ascii=False))
        return done, failed

    async def run(self) -> None:
        while True:
            try:
                await self.run_once()
                delay = self.interval_s
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết; lượt sau thử lại
                log.warning(json.dumps({"event": "case_file.archive_failed", "error": str(exc)}, ensure_ascii=False))
                delay = min(self.interval_s, 300.0)
            await asyncio.sleep(delay)


def read_package(cold: ColdStore, archive_key: str, archive_sha256: str) -> dict[str, Any]:
    """Phòng đọc: tải manifest theo băm trong CSDL, kiểm băm, đọc danh sách văn bản từ Parquet bằng DuckDB."""
    manifest_bytes = cold.get(manifest_key(archive_key, archive_sha256))
    if _sha256(manifest_bytes) != archive_sha256:
        raise ArchiveError("manifest trong bucket lạnh không khớp archive_sha256 trong CSDL")
    manifest = json.loads(manifest_bytes)
    table = manifest["tables"]["documents"]
    data = cold.get(f"{archive_key}{table['path']}")
    if _sha256(data) != table["sha256"]:
        raise ArchiveError("bảng văn bản (Parquet) trong gói không khớp băm trong manifest")
    documents = read_parquet(data, "select id::varchar as id, direction, type_code, symbol, issuer_name, issued_on,"
                                   " summary, register_number, verify_code, content_sha256 from t order by created_at")
    for d in documents:
        d["issued_on"] = d["issued_on"].isoformat() if isinstance(d["issued_on"], date) else d["issued_on"]
    return {"manifest_sha256": archive_sha256, "manifest": manifest, "documents": documents}


def _summary(items: Iterable[Archived]) -> list[dict[str, Any]]:
    return [asdict(a) for a in items]


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .config import Settings
    from .hasura import HasuraClient, HasuraError
    from .openbao import with_secrets
    from .storage import ObjectStore, s3_client

    parser = argparse.ArgumentParser(prog="python -m svc_files.archive", description="Nộp lưu hồ sơ đã đóng")
    parser.add_argument("cmd", choices=["now"])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--case-file", help="nộp lưu ngay hồ sơ này (phải đã đóng), không đợi đủ ngày")
    group.add_argument("--after-days", type=int, help="hồ sơ đóng từ chừng ấy ngày trở lên (mặc định theo cấu hình)")
    args = parser.parse_args(argv)
    settings = Settings.from_env(with_secrets(os.environ))
    s3 = s3_client(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region)
    hot = ObjectStore(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region,
                      settings.bucket)

    async def once() -> tuple[list[Archived], list[dict[str, str]]]:
        hasura = HasuraClient(settings.hasura_url, settings.hasura_admin_secret, timeout_s=settings.hasura_timeout_s)
        try:
            archiver = Archiver(hasura, hot, ColdStore(s3, settings.cold_bucket), after_days=settings.archive_after_days)
            if args.case_file:
                return [await archiver.archive(args.case_file)], []
            return await archiver.run_once(args.after_days)
        finally:
            await hasura.aclose()

    try:
        done, failed = asyncio.run(once())
    except (ArchiveError, StorageError, HasuraError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"archived": _summary(done), "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
