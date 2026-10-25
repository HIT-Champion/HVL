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

"""Nộp lưu hồ sơ (F3.8): gói Parquet + tệp + manifest vào bucket lạnh, đọc lại kiểm băm rồi mới gỡ khỏi OLTP."""

from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
import pytest

from svc_files.archive import (ARCHIVE, CLOSED, SHARED_FILES, ArchiveError, Archiver, ColdStore, _add_years,
                               manifest_key, read_package)
from svc_files.hasura import HasuraError
from svc_files.lineage import INSERT as LINEAGE
from svc_files.storage import ObjectMissing

TENANT, CASE = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
D1, D2 = "33333333-3333-3333-3333-333333333331", "33333333-3333-3333-3333-333333333332"
F1, F2 = "44444444-4444-4444-4444-444444444441", "44444444-4444-4444-4444-444444444442"
PDF_IN, PDF_OUT = b"%PDF-1.7 cong van den", b"%PDF-1.7 thong bao di"
NOW = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def case_file(status: str = "closed", retention: int | None = 10) -> dict[str, Any]:
    def doc(i: str, direction: str, data: bytes, fid: str, event: int) -> dict[str, Any]:
        return {
            "id": i, "direction": direction, "status": "done" if direction == "in" else "issued", "restricted": False,
            "type_code": "CV",
            "symbol": f"{i[-1]}/UBND", "issuer_name": "UBND tỉnh", "issued_on": "2026-09-01",
            "summary": f"Văn bản thử {i[-1]}", "body": None, "urgency": "normal", "is_public": False,
            "register_number": 1, "registered_at": "2026-09-01T08:00:00+07:00", "due_on": None,
            "recipients": ["Phòng Đào tạo"], "content_sha256": f"\\x{sha(data)}" if direction == "out" else None,
            "verify_code": "ABCDEFGHIJ" if direction == "out" else None, "department_id": None, "signer_id": None,
            "reply_to_id": None, "created_by": "van-thu", "created_at": f"2026-09-0{event}T08:00:00.5+07:00",
            "updated_at": "2026-09-02T08:00:00+07:00",
            "files": [{"role": "main", "added_by": "van-thu", "added_at": "2026-09-01T08:00:00+07:00",
                       "file": {"id": fid, "object_key": f"tenant/{TENANT}/{fid}", "filename": "công văn.pdf",
                                "mime_type": "application/pdf", "size_bytes": len(data), "sha256": f"\\x{sha(data)}"}}],
            "assignments": [{"id": "55555555-5555-5555-5555-555555555555", "parent_id": None, "department_id": None,
                             "user_id": "chuyen-vien", "role": "lead", "instruction": "Xử lý", "due_on": None,
                             "status": "done", "result_note": "Xong", "assigned_by": "lanh-dao",
                             "assigned_at": "2026-09-01T09:00:00Z",
                             "completed_at": "2026-09-02T09:00:00.25Z"}] if direction == "in" else [],
            "events": [{"id": event, "kind": "office.document.processed", "actor_id": "chuyen-vien",
                        "actor_kind": "user", "note": None, "data": {"a": 1} if event == 1 else {},
                        "created_at": "2026-09-02T09:00:00Z"}],
        }
    return {"id": CASE, "tenant_id": TENANT, "department_id": "d", "year": 2026, "code": "HS-01",
            "title": "Hồ sơ tuyển sinh 2026", "retention_years": retention, "status": status,
            "closed_on": "2026-10-01", "created_by": "chuyen-vien", "created_at": "2026-09-01T00:00:00Z",
            "case_file_documents": [{"added_by": "chuyen-vien", "added_at": "x", "document": doc(D1, "in", PDF_IN, F1, 1)},
                                    {"added_by": "chuyen-vien", "added_at": "y", "document": doc(D2, "out", PDF_OUT, F2, 2)}]}


class FakeHasura:
    def __init__(self, cf: dict[str, Any], shared: list[str] | None = None) -> None:
        self.cf, self.shared, self.commits = cf, shared or [], []
        self.fail_commit = False
        self.due: list[str] = [CASE]
        self.skips: list[list[str]] = []
        self.lineage: list[dict[str, Any]] = []
        self.fail_lineage = False

    async def admin(self, query: str, variables: dict[str, Any], headers: dict[str, str] | None = None) -> dict:
        if query == ARCHIVE:
            if self.fail_commit:
                raise HasuraError("dòng thời gian hoặc tệp của hồ sơ HS-01 đổi trong lúc nộp lưu")
            self.commits.append(variables["p"])
            return {"office_archive_case_file": [{"id": variables["p"]["id"], "status": "archived"}]}
        if query == LINEAGE:
            if self.fail_lineage:
                raise HasuraError("Không gọi được Hasura")
            self.lineage.append(json.loads(json.dumps(variables["o"])))
            return {"insert_core_lineage_events_one": {"id": len(self.lineage)}}
        if query == SHARED_FILES:
            return {"office_document_files": [{"file_id": f} for f in self.shared]}
        if query == CLOSED:
            self.skips.append(variables["skip"])
            return {"office_case_files": [{"id": i} for i in self.due if i not in variables["skip"]]}
        if variables["id"] != CASE:
            return {"office_case_files_by_pk": None}
        return {"office_case_files_by_pk": json.loads(json.dumps(self.cf))}


class FakeHot:
    bucket = "moc-files"

    def __init__(self) -> None:
        self.objects = {f"tenant/{TENANT}/{F1}": PDF_IN, f"tenant/{TENANT}/{F2}": PDF_OUT}
        self.deleted: list[str] = []

    def read_stream(self, key: str):
        return iter([self.objects[key]])

    def delete(self, key: str) -> None:
        self.deleted.append(key)


class FakeS3:
    """Bucket có phiên bản như SeaweedFS bật Object Lock: ghi trùng key là thêm phiên bản, đọc ra bản mới nhất."""

    def __init__(self) -> None:
        self.versions: dict[str, list[tuple[bytes, dict[str, str]]]] = {}
        self.locks: dict[str, tuple[str, datetime]] = {}
        self.puts = 0

    @property
    def objects(self) -> dict[str, bytes]:
        return {k: v[-1][0] for k, v in self.versions.items()}

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata, ObjectLockMode, ObjectLockRetainUntilDate):  # noqa: N803
        self.versions.setdefault(Key, []).append((Body, Metadata))
        self.locks[Key] = (ObjectLockMode, ObjectLockRetainUntilDate)
        self.puts += 1

    def _missing(self, op: str):
        from botocore.exceptions import ClientError
        return ClientError({"Error": {"Code": "NoSuchKey"}}, op)

    def head_object(self, *, Bucket, Key):  # noqa: N803
        if Key not in self.versions:
            raise self._missing("HeadObject")
        return {"Metadata": self.versions[Key][-1][1]}

    def get_object(self, *, Bucket, Key):  # noqa: N803
        if Key not in self.versions:
            raise self._missing("GetObject")

        class Body:
            def __init__(self, b: bytes) -> None:
                self.b = b

            def read(self) -> bytes:
                return self.b
        return {"Body": Body(self.versions[Key][-1][0])}


def make(cf: dict[str, Any] | None = None, shared: list[str] | None = None):
    s3 = FakeS3()
    cold = ColdStore(s3, "moc-cold")
    cold.ensure = lambda: None
    hasura, hot = FakeHasura(cf or case_file(), shared), FakeHot()
    return Archiver(hasura, hot, cold, after_days=365, clock=lambda: NOW), s3, hasura, hot


def test_archive_writes_locked_package_then_strips_oltp():
    archiver, s3, hasura, hot = make()
    done = asyncio.run(archiver.archive(CASE))
    prefix = f"cold/{TENANT}/case/{CASE}/"
    assert done.archive_key == prefix and (done.documents, done.files) == (2, 2)
    manifest = json.loads(s3.objects[manifest_key(prefix, done.archive_sha256)])
    tables = manifest["tables"]
    # mọi tên theo băm nội dung: hai lượt chạy cùng lúc không đè được phần của nhau
    assert set(s3.objects) == {manifest_key(prefix, done.archive_sha256), f"{prefix}files/{sha(PDF_IN)}",
                               f"{prefix}files/{sha(PDF_OUT)}"} | {f"{prefix}{t['path']}" for t in tables.values()}
    assert all(t["path"] == f"{name}-{t['sha256']}.parquet" for name, t in tables.items())
    # mọi đối tượng khóa ghi COMPLIANCE theo thời hạn bảo quản (10 năm, theo lịch)
    assert {mode for mode, _ in s3.locks.values()} == {"COMPLIANCE"}
    assert {until for _, until in s3.locks.values()} == {datetime(2036, 10, 1, tzinfo=UTC)}
    assert done.archive_sha256 == sha(s3.objects[manifest_key(prefix, done.archive_sha256)])
    assert tables["documents"]["rows"] == 2 and tables["assignments"]["rows"] == 1 and tables["events"]["rows"] == 2
    assert {e["filename"] for e in manifest["files"]} == {"công văn.pdf"}
    [commit] = hasura.commits
    assert commit["documents"] == [D1, D2] and commit["cold_files"] == [F1, F2] and commit["events"] == [1, 2]
    assert commit["links"] == [{"document_id": D1, "file_id": F1}, {"document_id": D2, "file_id": F2}]
    assert commit["archive_sha256"] == done.archive_sha256 and commit["files"] == 2
    assert hot.deleted == [f"tenant/{TENANT}/{F1}", f"tenant/{TENANT}/{F2}"]


def test_parquet_columns_have_fixed_types():
    archiver, s3, _, _ = make()
    done = asyncio.run(archiver.archive(CASE))
    manifest = json.loads(s3.objects[manifest_key(done.archive_key, done.archive_sha256)])
    types = {}
    with tempfile.TemporaryDirectory() as tmp:
        con = duckdb.connect()
        for name, table in manifest["tables"].items():
            target = pathlib.Path(tmp) / f"{name}.parquet"
            target.write_bytes(s3.objects[f"{done.archive_key}{table['path']}"])
            types[name] = {row[0]: row[1] for row in con.execute(f"describe select * from '{target}'").fetchall()}
        con.close()
    # thời gian lẫn có và không có phần lẻ giây vẫn là TIMESTAMPTZ; {} và {"a": 1} vẫn là JSON
    assert types["documents"]["created_at"] == "TIMESTAMP WITH TIME ZONE"
    assert types["documents"]["id"] == "UUID" and types["documents"]["recipients"] == "VARCHAR[]"
    assert types["assignments"]["completed_at"] == "TIMESTAMP WITH TIME ZONE"
    assert types["events"]["data"] == "JSON" and types["events"]["id"] == "BIGINT"


def test_reading_room_reads_parquet_and_checks_hash():
    archiver, s3, _, _ = make()
    done = asyncio.run(archiver.archive(CASE))
    pkg = read_package(archiver.cold, done.archive_key, done.archive_sha256)
    assert [(d["id"], d["symbol"], d["verify_code"]) for d in pkg["documents"]] == [
        (D1, "1/UBND", None), (D2, "2/UBND", "ABCDEFGHIJ")]
    assert pkg["documents"][1]["content_sha256"] == sha(PDF_OUT) and pkg["documents"][0]["issued_on"] == "2026-09-01"
    with pytest.raises(ObjectMissing):          # manifest tìm theo băm trong CSDL: băm khác là không có
        read_package(archiver.cold, done.archive_key, "0" * 64)
    path = json.loads(s3.objects[manifest_key(done.archive_key, done.archive_sha256)])["tables"]["documents"]["path"]
    s3.versions[f"{done.archive_key}{path}"].append((b"PAR1 sua", {}))
    with pytest.raises(ArchiveError, match="Parquet"):
        read_package(archiver.cold, done.archive_key, done.archive_sha256)


def test_hot_copy_mismatch_stops_before_anything_cold():
    archiver, s3, hasura, hot = make()
    hot.objects[f"tenant/{TENANT}/{F2}"] = b"%PDF bi sua"
    with pytest.raises(ArchiveError, match="không khớp băm"):
        asyncio.run(archiver.archive(CASE))
    # tệp 1 khớp nhưng chưa được chép: không để lại đối tượng bị khóa nhiều năm cho một lượt hỏng
    assert s3.puts == 0 and hasura.commits == [] and hot.deleted == []


def test_retry_after_failed_commit_adds_no_locked_versions():
    archiver, s3, hasura, hot = make()
    hasura.fail_commit = True
    with pytest.raises(HasuraError):
        asyncio.run(archiver.archive(CASE))
    assert hot.deleted == [] and s3.puts == 6     # 2 tệp, 3 bảng, manifest
    hasura.fail_commit = False
    # một giờ sau: gói vẫn y hệt (manifest không ghi giờ nộp lưu, hạn khóa tính từ ngày đóng)
    archiver.clock = lambda: NOW + timedelta(hours=1)
    asyncio.run(archiver.archive(CASE))
    assert s3.puts == 6 and len(hasura.commits) == 1


def test_one_bad_case_file_does_not_block_the_queue():
    archiver, _, hasura, _ = make()
    hasura.due = ["99999999-9999-9999-9999-999999999999", CASE]
    done, failed = asyncio.run(archiver.run_once())
    assert [d.case_file_id for d in done] == [CASE]
    assert failed[0]["case_file_id"].startswith("9999") and "không có hồ sơ" in failed[0]["error"]


def test_only_closed_case_files():
    archiver, *_ = make(case_file("open"))
    with pytest.raises(ArchiveError, match="đã đóng"):
        asyncio.run(archiver.archive(CASE))


def test_shared_file_stays_hot():
    archiver, _, hasura, hot = make(shared=[F2])
    asyncio.run(archiver.archive(CASE))
    assert hasura.commits[0]["cold_files"] == [F1] and hot.deleted == [f"tenant/{TENANT}/{F1}"]


def test_permanent_retention_locks_a_century_by_calendar():
    archiver, s3, _, _ = make(case_file(retention=None))
    asyncio.run(archiver.archive(CASE))
    assert {until for _, until in s3.locks.values()} == {datetime(2126, 10, 1, tzinfo=UTC)}
    assert _add_years(datetime(2028, 2, 29, tzinfo=UTC), 10) == datetime(2038, 2, 28, tzinfo=UTC)


def test_failed_case_file_waits_a_day_before_retry():
    archiver, _, hasura, _ = make()
    bad = "99999999-9999-9999-9999-999999999999"
    hasura.due = [bad, CASE]
    asyncio.run(archiver.run_once())
    archiver.clock = lambda: NOW + timedelta(hours=23)
    asyncio.run(archiver.run_once())
    archiver.clock = lambda: NOW + timedelta(hours=25)
    asyncio.run(archiver.run_once())
    # lượt nền bỏ qua hồ sơ vừa lỗi 24 giờ, để hồ sơ lỗi không chiếm chỗ hồ sơ khác trong giới hạn mỗi lượt
    assert hasura.skips == [[], [bad], []]


def test_restricted_or_unfinished_document_stops_before_anything_cold():
    for key, value in (("restricted", True), ("status", "processing")):
        cf = case_file()
        cf["case_file_documents"][0]["document"][key] = value
        archiver, s3, hasura, hot = make(cf)
        with pytest.raises(ArchiveError, match="không còn ở trạng thái nộp lưu được"):
            asyncio.run(archiver.archive(CASE))
        assert s3.puts == 0 and hasura.commits == [] and hot.deleted == []


def test_document_still_being_dispatched_stops_before_anything_cold():
    cf = case_file()
    cf["case_file_documents"][1]["document"]["dispatches"] = [{"id": "66666666-6666-6666-6666-666666666666"}]
    archiver, s3, hasura, hot = make(cf)
    with pytest.raises(ArchiveError, match="còn đang gửi liên thông"):
        asyncio.run(archiver.archive(CASE))
    assert s3.puts == 0 and hasura.commits == [] and hot.deleted == []


def test_lock_counts_from_closing_date_but_never_ends_in_the_past():
    cf = case_file(retention=1)
    cf["closed_on"] = "2020-01-01"
    archiver, s3, _, _ = make(cf)
    asyncio.run(archiver.archive(CASE))
    # hết hạn bảo quản từ 2021 nhưng vẫn khóa tới sau hôm nay hai ngày: không ghi đối tượng có hạn khóa đã qua
    assert {until for _, until in s3.locks.values()} == {datetime(2026, 10, 22, tzinfo=UTC)}


def test_lineage_one_run_per_step_linked_to_the_archive_run():
    archiver, _, hasura, _ = make()
    done = asyncio.run(archiver.archive(CASE))
    ev = hasura.lineage
    assert [(e["job"], e["event_type"]) for e in ev] == [
        ("moc.case_file.archive", "START"), ("moc.case_file.archive.files", "COMPLETE"),
        ("moc.case_file.archive.tables", "COMPLETE"), ("moc.case_file.archive.manifest", "COMPLETE"),
        ("moc.case_file.archive.commit", "COMPLETE"), ("moc.case_file.archive", "COMPLETE")]
    parent = ev[0]["run_id"]
    assert {e["parent_run_id"] for e in ev[1:5]} == {parent} and ev[-1]["run_id"] == parent
    assert {e["tenant_id"] for e in ev} == {TENANT}
    prefix = f"s3://moc-cold/cold/{TENANT}/case/{CASE}/"
    # phả hệ: manifest ← bảng Parquet + tệp ← bảng OLTP / bucket nóng
    tables = ev[2]
    assert tables["inputs"] == ["postgres://postgres:5432/moc.office.documents",
                                "postgres://postgres:5432/moc.office.assignments",
                                "postgres://postgres:5432/moc.office.document_events"]
    assert [o.split("/")[-1].split("-")[0] for o in tables["outputs"]] == ["documents", "assignments", "events"]
    assert ev[1]["inputs"] == [f"s3://moc-files/tenant/{TENANT}/{F1}", f"s3://moc-files/tenant/{TENANT}/{F2}"]
    assert ev[3]["outputs"] == [f"{prefix}manifest-{done.archive_sha256}.json"]
    assert set(ev[3]["inputs"]) == set(tables["outputs"]) | set(ev[1]["outputs"])
    assert ev[4]["inputs"] == ev[3]["outputs"] and ev[-1]["outputs"] == ev[3]["outputs"]
    # bước commit khai đúng các bảng hàm SQL ghi, kể cả số liệu giữ lại mà báo cáo thời gian xử lý đọc
    assert {o.rsplit(".", 1)[1] for o in ev[4]["outputs"]} == {"case_files", "documents", "document_events",
                                                                 "document_files", "archived_document_facts", "files",
                                                                 "audit_log"}
    # kiểm chất lượng: số dòng khớp CSDL, cột bắt buộc không null — nằm trong facet của từng bảng
    assert tables["quality_ok"] is True and ev[1]["quality_ok"] is None and ev[3]["quality_ok"] is None
    assert done.run_id == parent
    # ở bước manifest, bảng Parquet là đầu vào: kết quả kiểm nằm trong inputFacets như đặc tả
    first_in = ev[3]["event"]["inputs"][0]
    assert first_in["inputFacets"]["dataQualityAssertions"]["assertions"][0]["success"] is True
    docs = tables["event"]["outputs"][0]
    assert docs["outputFacets"]["outputStatistics"]["rowCount"] == 2
    checks = {(a["assertion"], a.get("column")) for a in docs["facets"]["dataQualityAssertions"]["assertions"]}
    assert ("row_count_equals_source", None) in checks and ("not_null", "summary") in checks
    assert [f["name"] for f in docs["facets"]["schema"]["fields"]][:2] == ["id", "case_file_id"]
    # sự kiện đúng khuôn OpenLineage
    run = ev[0]["event"]
    assert run["schemaURL"].endswith("#/$defs/RunEvent") and run["job"]["namespace"] == "moc"
    assert ev[1]["event"]["run"]["facets"]["parent"]["run"]["runId"] == parent


def test_quality_failure_stops_before_anything_cold_and_is_in_lineage():
    cf = case_file()
    cf["case_file_documents"][0]["document"]["summary"] = None
    archiver, s3, hasura, hot = make(cf)
    with pytest.raises(ArchiveError, match="không đạt kiểm chất lượng"):
        asyncio.run(archiver.archive(CASE))
    assert s3.puts == 0 and hasura.commits == [] and hot.deleted == []
    assert [(e["job"], e["event_type"], e["quality_ok"]) for e in hasura.lineage] == [
        ("moc.case_file.archive", "START", None), ("moc.case_file.archive.tables", "FAIL", False),
        ("moc.case_file.archive", "FAIL", None)]
    failed = {(a["column"], a["success"]) for a in hasura.lineage[1]["event"]["outputs"][0]["facets"][
        "dataQualityAssertions"]["assertions"] if a["assertion"] == "not_null"}
    assert ("summary", False) in failed and ("id", True) in failed
    assert "bảng documents" in hasura.lineage[-1]["event"]["run"]["facets"]["errorMessage"]["message"]


def test_lineage_store_down_does_not_block_archiving():
    archiver, _, hasura, _ = make()
    hasura.fail_lineage = True
    asyncio.run(archiver.archive(CASE))
    assert len(hasura.commits) == 1 and hasura.lineage == []


def test_lineage_also_sent_to_openlineage_server():
    import httpx2
    got: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        got.append(json.loads(request.content))
        return httpx2.Response(201)

    archiver, _, hasura, _ = make()
    archiver.lineage.url = "http://marquez:5000/api/v1/lineage"
    archiver.lineage.transport = httpx2.MockTransport(handler)
    asyncio.run(archiver.archive(CASE))
    assert [e["eventType"] for e in got] == [e["event_type"] for e in hasura.lineage]
    assert got[0]["producer"].endswith("services/svc-files")


def test_failed_step_is_named_and_lineage_never_carries_file_names():
    archiver, _, hasura, _ = make()
    hasura.fail_commit = True
    with pytest.raises(HasuraError):
        asyncio.run(archiver.archive(CASE))
    assert [(e["job"].removeprefix("moc.case_file.archive"), e["event_type"]) for e in hasura.lineage] == [
        ("", "START"), (".files", "COMPLETE"), (".tables", "COMPLETE"), (".manifest", "COMPLETE"),
        (".commit", "FAIL"), ("", "FAIL")]
    # tệp nóng lệch băm: thông báo lỗi có tên tệp — phả hệ (văn thư đọc được, có thể gửi ra Marquez) chỉ có lớp lỗi
    archiver, _, hasura, hot = make()
    hot.objects[f"tenant/{TENANT}/{F2}"] = b"%PDF bi sua"
    with pytest.raises(ArchiveError, match="công văn.pdf"):
        asyncio.run(archiver.archive(CASE))
    assert "công văn" not in json.dumps(hasura.lineage, ensure_ascii=False)
    assert hasura.lineage[-1]["event"]["run"]["facets"]["errorMessage"]["message"].startswith("ArchiveError")


def test_bad_openlineage_url_does_not_block_archiving():
    archiver, _, hasura, _ = make()
    archiver.lineage.url = "http://[::1/x"
    asyncio.run(archiver.archive(CASE))
    assert len(hasura.commits) == 1 and len(hasura.lineage) == 6
