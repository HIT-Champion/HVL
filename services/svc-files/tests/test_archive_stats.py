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

"""Phân tích dữ liệu đã nộp lưu (#304): DuckDB đếm trên các gói Parquet trong bucket lạnh cho trang Điều hành. Gói
dựng bằng đúng job nộp lưu (Archiver) trên kho giả; số liệu phải khớp các văn bản đã nộp lưu, chỉ lãnh đạo đơn vị xem,
chỉ gói của đơn vị mình, gói hỏng thì báo chứ không đếm, kho trống thì số 0."""

import asyncio
import copy
import dataclasses
import json
import time
import uuid

import jwt
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from conftest import ISSUER
from svc_files.app import create_app
from svc_files.archive import CASE_FILE, Archiver, ColdStore, manifest_key
from svc_files.archive_stats import JOB, ArchiveStats
from svc_files.auth import HASURA_CLAIMS
from svc_files.lineage import INSERT as LINEAGE
from svc_files.lineage import Lineage
from test_archive import NOW, TENANT, FakeHot, FakeS3, case_file, sha
from test_archive import FakeHasura as AdminHasura
from test_reading_room import RoomHasura

NS = uuid.UUID("0b3a0000-0000-4000-8000-000000000304")
DAO_TAO, KTPM = str(uuid.uuid5(NS, "dao-tao")), str(uuid.uuid5(NS, "ktpm"))
OTHER_TENANT = str(uuid.uuid5(NS, "don-vi-khac"))


def case_id(n: int) -> str:
    return str(uuid.uuid5(NS, f"case-{n}"))


class Admin(AdminHasura):
    """Hasura quản trị giả của test_archive, có nhiều hồ sơ."""

    def __init__(self) -> None:
        super().__init__(case_file())
        self.cases: dict[str, dict] = {}

    async def admin(self, query: str, variables: dict, headers: dict | None = None) -> dict:
        if query == CASE_FILE:
            return {"office_case_files_by_pk": json.loads(json.dumps(self.cases.get(variables["id"])))}
        return await super().admin(query, variables, headers)


@dataclasses.dataclass
class StatsHasura(RoomHasura):
    """Hasura giả của phòng đọc, thêm danh sách hồ sơ đã nộp lưu người giữ token xem được (cùng quy tắc)."""

    async def archived_case_files(self, token: str) -> list[dict]:
        self._check()
        rows = []
        for cid in self.case_files:
            row = await self.visible_case_file(token, uuid.UUID(cid))
            if row and row["status"] == "archived":
                rows.append({k: row[k] for k in ("id", "code", "archive_key", "archive_sha256")})
        return rows


@dataclasses.dataclass
class Cold:
    s3: FakeS3
    cold: ColdStore
    hot: FakeHot
    admin: Admin
    archiver: Archiver
    packages: list[dict] = dataclasses.field(default_factory=list)   # như Hasura trả cho lãnh đạo đơn vị
    hasura: StatsHasura | None = None
    gets: list[str] = dataclasses.field(default_factory=list)         # key đã đọc từ bucket lạnh


def make_cold() -> Cold:
    s3 = FakeS3()
    cold = ColdStore(s3, "moc-cold")
    cold.ensure = lambda: None
    hot, admin = FakeHot(), Admin()
    c = Cold(s3, cold, hot, admin, Archiver(admin, hot, cold, after_days=365, clock=lambda: NOW))
    get = s3.get_object

    def counted(*, Bucket, Key):  # noqa: N803
        c.gets.append(Key)
        return get(Bucket=Bucket, Key=Key)
    s3.get_object = counted
    return c


def add(c: Cold, n: int, docs: list[tuple[str, str, str | None]], *, year: int = 2026,
        department: str = DAO_TAO) -> dict:
    """Lập hồ sơ HS-0n gồm các văn bản (chiều, loại, ngày ban hành) rồi nộp lưu thật bằng Archiver."""
    base = case_file()
    template = {link["document"]["direction"]: link for link in base["case_file_documents"]}
    links = []
    for i, (direction, type_code, issued_on) in enumerate(docs):
        link = copy.deepcopy(template[direction])
        doc = link["document"]
        doc_id, file_id = (str(uuid.uuid5(NS, f"{n}-{i}-{part}")) for part in ("doc", "file"))
        data = f"%PDF-1.7 {doc_id}".encode()
        doc.update(id=doc_id, type_code=type_code, issued_on=issued_on)
        if direction == "out":
            doc["content_sha256"] = f"\\x{sha(data)}"
        f = doc["files"][0]["file"]
        f.update(id=file_id, object_key=f"tenant/{TENANT}/{file_id}", sha256=f"\\x{sha(data)}", size_bytes=len(data))
        for a in doc["assignments"]:
            a["id"] = str(uuid.uuid5(NS, f"{n}-{i}-assignment"))
        for e in doc["events"]:
            e["id"] = n * 100 + i
        c.hot.objects[f["object_key"]] = data
        links.append(link)
    cid = case_id(n)
    c.admin.cases[cid] = {**base, "id": cid, "year": year, "department_id": department, "code": f"HS-{n:02d}",
                          "case_file_documents": links}
    if c.hasura is not None:
        c.hasura.case_files[cid] = {"id": cid, "tenant_id": TENANT, "department_id": department, "code": f"HS-{n:02d}",
                                    "title": f"Hồ sơ {n}", "year": year, "status": "closed", "closed_on": "2026-10-01",
                                    "archived_at": None, "archive_key": None, "archive_sha256": None}
    done = asyncio.run(c.archiver.archive(cid))
    row = {"id": cid, "code": done.code, "archive_key": done.archive_key, "archive_sha256": done.archive_sha256}
    c.packages.append(row)
    return row


def stats_of(c: Cold, engine: ArchiveStats | None = None, tenant: str = TENANT):
    return asyncio.run((engine or ArchiveStats(c.cold)).get(uuid.UUID(tenant), c.packages))


def two_case_files(c: Cold) -> None:
    add(c, 1, [("in", "CV", "2025-03-02"), ("out", "QD", "2025-04-01"), ("out", "CV", "2026-01-05")], year=2025)
    add(c, 2, [("in", "CV", "2026-02-01"), ("in", "TB", "2026-05-01")], department=KTPM)


# --- truy vấn DuckDB trên gói lạnh ------------------------------------------------------------------------------------

def test_counts_match_the_archived_packages_by_year_type_and_department():
    c = make_cold()
    two_case_files(c)
    s = stats_of(c)
    assert (s.case_files, s.documents, s.incoming, s.outgoing, s.unreadable) == (2, 5, 3, 2, [])
    assert s.by_year == [{"year": 2025, "incoming": 1, "outgoing": 1}, {"year": 2026, "incoming": 2, "outgoing": 1}]
    assert s.by_type == [{"type_code": "CV", "incoming": 2, "outgoing": 1}, {"type_code": "QD", "incoming": 0,
                         "outgoing": 1}, {"type_code": "TB", "incoming": 1, "outgoing": 0}]
    assert s.by_department == [{"department_id": DAO_TAO, "case_files": 1, "documents": 3},
                               {"department_id": KTPM, "case_files": 1, "documents": 2}]
    # đọc từ bucket lạnh, không từ CSDL: bản nóng của các tệp đã xóa, Hasura quản trị chỉ được hỏi lúc nộp lưu
    assert len(c.hot.deleted) == 5
    assert {k.rsplit("/", 1)[-1].split("-")[0] for k in c.gets[-4:]} == {"manifest", "documents"}


def test_document_without_issue_date_counts_in_the_case_file_year():
    c = make_cold()
    add(c, 1, [("out", "CV", None), ("in", "CV", "2026-02-01")], year=2024)
    assert stats_of(c).by_year == [{"year": 2024, "incoming": 0, "outgoing": 1},
                                   {"year": 2026, "incoming": 1, "outgoing": 0}]


def test_empty_archive_is_all_zeros_without_reading_the_bucket():
    c = make_cold()
    s = stats_of(c)
    assert (s.case_files, s.documents, s.incoming, s.outgoing) == (0, 0, 0, 0)
    assert (s.by_year, s.by_type, s.by_department, s.unreadable, c.gets) == ([], [], [], [], [])


def test_tampered_missing_or_misplaced_package_is_reported_and_left_out():
    c = make_cold()
    bad, gone, good = (add(c, n, [("in", "CV", "2026-02-01")]) for n in (1, 2, 3))
    manifest = json.loads(c.s3.objects[manifest_key(bad["archive_key"], bad["archive_sha256"])])
    table = f"{bad['archive_key']}{manifest['tables']['documents']['path']}"
    c.s3.versions[table].append((b"PAR1 khong phai bang da nop luu", {}))    # một bản khác nằm trên bản đã khóa
    del c.s3.versions[manifest_key(gone["archive_key"], gone["archive_sha256"])]
    # gói ghi dưới tiền tố của đơn vị khác: không bao giờ đọc, dù CSDL (hỏng) có trỏ tới
    stray = {"id": case_id(9), "code": "HS-09", "archive_key": f"cold/{OTHER_TENANT}/case/{case_id(9)}/",
             "archive_sha256": "ab" * 32}
    c.packages.append(stray)
    c.gets.clear()
    s = stats_of(c)
    assert (s.case_files, s.documents) == (1, 1)
    assert [u["code"] for u in s.unreadable] == ["HS-01", "HS-02", "HS-09"]
    assert not any(OTHER_TENANT in key for key in c.gets)
    assert good["archive_key"] in "".join(c.gets)


def test_cached_until_a_new_package_arrives_and_each_new_set_is_one_lineage_run():
    c = make_cold()
    add(c, 1, [("in", "CV", "2026-02-01"), ("out", "CV", "2026-03-01")])
    events: list[dict] = []

    async def store(query: str, variables: dict) -> dict:
        assert query == LINEAGE
        events.append(json.loads(json.dumps(variables["o"])))
        return {"insert_core_lineage_events_one": {"id": len(events)}}

    engine = ArchiveStats(c.cold, Lineage(store))
    first = stats_of(c, engine)
    reads = len(c.gets)
    assert stats_of(c, engine) is first and len(c.gets) == reads       # cùng tập manifest: không đọc lại kho
    [event] = events
    table = json.loads(c.s3.objects[manifest_key(c.packages[0]["archive_key"], c.packages[0]["archive_sha256"])])
    documents = f"s3://moc-cold/{c.packages[0]['archive_key']}{table['tables']['documents']['path']}"
    assert (event["job"], event["event_type"], event["tenant_id"]) == (JOB, "COMPLETE", TENANT)
    assert event["inputs"] == [documents] and event["outputs"] == []
    add(c, 2, [("in", "TB", "2026-04-01")])
    again = stats_of(c, engine)
    assert (again.case_files, again.documents) == (2, 3) and len(events) == 2
    assert len(events[1]["inputs"]) == 2 and events[1]["run_id"] != event["run_id"]


# --- route của trang Điều hành ----------------------------------------------------------------------------------------

@pytest.fixture
def board(settings, scanner, store, verifier, meili, vault):
    c = make_cold()
    c.hasura = StatsHasura(admin_hasura=c.admin)
    app = create_app(dataclasses.replace(settings, archive_interval_s=0), scanner=scanner, store=store,
                     verifier=verifier, hasura=c.hasura, meili=meili, vault=vault, cold=c.cold, archiver=c.archiver)
    with TestClient(app) as client:
        yield c, client


@pytest.fixture
def token(signing_key):
    def _make(role: str, *, department: str | None = DAO_TAO, tenant: str = TENANT) -> dict[str, str]:
        now = int(time.time())
        ns = {"x-hasura-user-id": f"u-{role}", "x-hasura-allowed-roles": [role], "x-hasura-default-role": role,
              "x-hasura-tenant-id": tenant}
        if department:
            ns["x-hasura-department-id"] = department
        body = {"iss": ISSUER, "sub": f"u-{role}", "iat": now, "exp": now + 300, HASURA_CLAIMS: ns}
        return {"Authorization": f"Bearer {jwt.encode(body, signing_key, algorithm='RS256', headers={'kid': 'test'})}"}

    return _make


URL = "/api/case-files/archive-stats"


def test_director_sees_the_counts_of_the_cold_packages(board, token):
    c, client = board
    two_case_files(c)
    r = client.get(URL, headers=token("director", department=None))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert (body["case_files"], body["documents"], body["incoming"], body["outgoing"]) == (2, 5, 3, 2)
    assert body["by_year"] == [{"year": 2025, "incoming": 1, "outgoing": 1},
                               {"year": 2026, "incoming": 2, "outgoing": 1}]
    assert [t["type_code"] for t in body["by_type"]] == ["CV", "QD", "TB"]
    assert body["by_department"][0] == {"department_id": DAO_TAO, "case_files": 1, "documents": 3}
    assert body["unreadable"] == [] and body["bucket"] == "moc-cold" and body["computed_at"]
    # chỉ số đếm: không trích yếu, số ký hiệu, tên tệp nào trong câu trả lời
    assert "Văn bản thử" not in r.text and "UBND" not in r.text and "công văn.pdf" not in r.text


@pytest.mark.parametrize("role", ["clerk", "manager", "staff", "tenant_admin"])
def test_only_the_director_reads_the_archive_stats(board, token, role):
    c, client = board
    two_case_files(c)
    c.gets.clear()
    r = client.get(URL, headers=token(role))
    assert (r.status_code, r.json()["detail"]["code"]) == (403, "forbidden")
    assert c.gets == []


def test_director_of_another_unit_sees_nothing_of_this_unit(board, token):
    c, client = board
    two_case_files(c)
    c.gets.clear()
    r = client.get(URL, headers=token("director", department=None, tenant=OTHER_TENANT))
    assert r.status_code == 200
    assert (r.json()["case_files"], r.json()["documents"], r.json()["by_type"]) == (0, 0, [])
    assert c.gets == []


def test_empty_archive_is_200_with_zeros_and_no_tokens_is_401(board, token):
    _, client = board
    r = client.get(URL, headers=token("director", department=None))
    assert r.status_code == 200
    assert {k: r.json()[k] for k in ("case_files", "documents", "by_year", "by_type", "by_department")} == {
        "case_files": 0, "documents": 0, "by_year": [], "by_type": [], "by_department": []}
    assert client.get(URL).status_code == 401


def test_database_or_cold_bucket_down_is_503(board, token):
    c, client = board
    add(c, 1, [("in", "CV", "2026-02-01")])
    c.hasura.down = True
    r = client.get(URL, headers=token("director", department=None))
    assert (r.status_code, r.json()["detail"]["code"]) == (503, "database_unavailable")
    c.hasura.down = False

    def down(*, Bucket, Key):  # noqa: N803
        raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "GetObject")
    c.s3.get_object = down
    r = client.get(URL, headers=token("director", department=None))
    assert (r.status_code, r.json()["detail"]["code"]) == (503, "storage_unavailable")
