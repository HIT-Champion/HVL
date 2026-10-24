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

"""Vòng nền nạp lô: mỗi dòng đi đúng đường tiếp nhận lẻ (ClamAV → kho → core.files, Action receiveIncoming đóng vai
văn thư), lỗi một dòng không hỏng dòng khác, lõi bận thì lùi, mất phản hồi hay khởi động lại thì làm tiếp đúng chỗ
dở mà không nhân đôi văn bản hay tệp."""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta

import pytest

from conftest import EICAR, TENANT_A, text_pdf
from import_fakes import doc, make_lab, ndjson, zip_bytes
from svc_files.auth import HASURA_CLAIMS
from svc_files.hasura import HasuraError
from svc_files.imports.runner import ARCHIVE_LOST, LEASE_RECHECK_S, LEASE_S, MAX_ATTEMPTS, PAUSED, Importer
from svc_files.storage import StorageError

TENANT_B = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")
DEPT = "11111111-0000-4000-8000-000000000001"
PDF_A = b"%PDF-1.7\n% ban chinh\n" + b"a" * 300
PDF_B = b"%PDF-1.7\n% phu luc\n" + b"b" * 300


@pytest.fixture
def lab(monkeypatch, tmp_path, settings, scanner, store, verifier, meili, vault):
    with make_lab(monkeypatch, tmp_path, settings, scanner=scanner, store=store, verifier=verifier, meili=meili,
                  vault=vault) as lab:
        yield lab


@pytest.fixture
def lab1(monkeypatch, tmp_path, settings, scanner, store, verifier, meili, vault):
    """Mỗi mẻ một dòng: thấy được thứ tự, chỗ dở giữa lô."""
    with make_lab(monkeypatch, tmp_path, settings, scanner=scanner, store=store, verifier=verifier, meili=meili,
                  vault=vault, import_chunk=1) as lab:
        yield lab


@pytest.fixture
def clerk(make_token):
    return make_token(sub="u-van-thu", **{HASURA_CLAIMS: {
        "x-hasura-user-id": "u-van-thu", "x-hasura-allowed-roles": ["clerk"], "x-hasura-default-role": "clerk",
        "x-hasura-tenant-id": str(TENANT_A), "x-hasura-department-id": DEPT}})


def create(lab, token, *rows, archive=None, **kw) -> str:
    r = lab.post(token, ndjson(*rows), archive=archive, **kw)
    assert r.status_code == 202, r.text
    return r.json()["id"]


def lines(lab, job_id) -> dict[int, dict]:
    return {r["line"]: r for r in lab.lines(job_id)}


def files_named(lab, name: str) -> list[tuple[uuid.UUID, dict]]:
    return [(fid, row) for fid, row in lab.hasura.files.items() if row["filename"] == name]


# --- đường chính ----------------------------------------------------------------------------------------------


def test_each_row_is_received_as_the_clerk_with_data_untouched(lab, clerk):
    job_id = create(lab, clerk, doc(1), doc(2, urgency="khan"))
    lab.drain()
    calls = lab.hasura.act_calls
    assert [c["action"] for c in calls] == ["receiveIncoming", "receiveIncoming"]
    for line, call in enumerate(calls, 1):
        assert call["role"] == "clerk" and call["tenant_id"] == str(TENANT_A) and call["user_id"] == "u-van-thu"
        assert call["department_id"] == DEPT and call["request_id"] == f"{job_id}:{line}"
    assert calls[0]["variables"] == {"d": doc(1)} and calls[1]["variables"] == {"d": doc(2, urgency="khan")}
    got = lines(lab, job_id)
    for line in (1, 2):
        row = got[line]
        assert row["status"] == "ok" and row["data"] is None and row["code"] is None and row["attempts"] == 1
        assert lab.hasura.incoming[row["result"]["document_id"]]["symbol"] == f"{line}/UBND-VP"
    job = lab.job(job_id)
    assert (job["status"], job["ok"], job["duplicate"], job["failed"]) == ("done", 2, 0, 0)
    assert job["started_at"] and job["finished_at"] and job["note"] is None


def test_one_bad_row_does_not_spoil_the_others(lab, clerk):
    job_id = create(lab, clerk, doc(1), doc(2, summary="ngắn"), doc(3, type_code="XX"), doc(4, la="x"), doc(5))
    lab.drain()
    got = lines(lab, job_id)
    assert {n: r["status"] for n, r in got.items()} == {1: "ok", 2: "failed", 3: "failed", 4: "failed", 5: "ok"}
    assert (got[2]["code"], got[2]["fields"]) == ("invalid", {"summary": "minLength"})
    assert (got[3]["code"], got[3]["fields"]) == ("invalid", {"type_code": "unknown"})
    assert got[4]["fields"] == {"la": "additionalProperties"}
    assert all(r["data"] is None for r in got.values())        # dòng xong không giữ dữ liệu đã gửi
    assert len(lab.hasura.incoming) == 2


def test_duplicates_and_resending_the_same_file(lab, clerk, store):
    archive = zip_bytes({"a.pdf": PDF_A, "b.pdf": PDF_B})
    rows = (doc(1, files=["a.pdf"]), doc(2), doc(1, issuer_name="ubnd TỈNH Hưng Yên", files=["b.pdf"]))
    first = create(lab, clerk, *rows, archive=archive)
    lab.drain()
    got = lines(lab, first)
    assert [got[n]["status"] for n in (1, 2, 3)] == ["ok", "ok", "duplicate"]
    # trùng tra trước khi đưa tệp vào kho: b.pdf không được lưu
    assert got[3]["fields"] == {"symbol": "duplicate"} and files_named(lab, "b.pdf") == []
    objects, files = dict(store.objects), dict(lab.hasura.files)

    again = create(lab, clerk, *rows, archive=archive)
    lab.drain()
    assert {r["status"] for r in lab.lines(again)} == {"duplicate"}
    assert store.objects == objects and lab.hasura.files == files and len(lab.hasura.incoming) == 2
    job = lab.job(again)
    assert (job["ok"], job["duplicate"], job["failed"]) == (0, 3, 0)


# --- tệp đính kèm --------------------------------------------------------------------------------------------


def test_attachments_are_scanned_stored_as_the_clerk_and_attached_in_order(lab, clerk, scanner, store):
    # tệp đã tải lên trước (file_ids) giữ ở đầu, tệp trong zip nối sau theo thứ tự của files
    up = lab.client.post("/api/files", headers={"Authorization": f"Bearer {clerk}"},
                         files={"file": ("to-trinh.pdf", PDF_A, "application/pdf")}).json()["id"]
    job_id = create(lab, clerk, doc(1, file_ids=[up], files=["tep/b.pdf", "tep/a.pdf"]),
                    archive=zip_bytes({"tep/a.pdf": PDF_A, "tep/b.pdf": PDF_B}))
    lab.drain()
    (row,) = lab.lines(job_id)
    assert row["status"] == "ok"
    document = lab.hasura.incoming[row["result"]["document_id"]]
    ((b_id, b_row),) = files_named(lab, "b.pdf")
    ((a_id, a_row),) = files_named(lab, "a.pdf")
    assert document["file_ids"] == [up, str(b_id), str(a_id)]
    assert row["result"]["file_ids"] == [str(b_id), str(a_id)]
    for fid, f in ((b_id, b_row), (a_id, a_row)):
        assert f["created_by"] == "u-van-thu" and f["tenant_id"] == TENANT_A and f["mime_type"] == "application/pdf"
        assert f["request_id"] == f"{job_id}:1" and f["object_key"].startswith(f"tenant/{TENANT_A}/")
        assert f["object_key"].endswith(str(fid)) and f["wrapped_dek"] is None
    assert store.objects[a_row["object_key"]]["data"] == PDF_A
    assert scanner.scanned == PDF_A         # tệp cuối cùng qua trạm quét là a.pdf


def test_infected_attachment_fails_only_its_row(lab, clerk, store):
    job_id = create(lab, clerk, doc(1, files=["sach.pdf", "virus.pdf"]), doc(2, files=["sach2.pdf"]),
                    archive=zip_bytes({"sach.pdf": PDF_A, "virus.pdf": EICAR, "sach2.pdf": PDF_B}))
    lab.drain()
    got = lines(lab, job_id)
    assert (got[1]["status"], got[1]["code"]) == ("failed", "infected")
    assert "virus.pdf" in got[1]["message"] and "Eicar-Test-Signature" in got[1]["message"]
    assert got[2]["status"] == "ok"
    (event,) = lab.hasura.events
    assert event["action"] == "file.rejected" and event["request_id"] == f"{job_id}:1"
    assert event["actor_id"] == "u-van-thu" and event["details"]["filename"] == "virus.pdf"
    assert all(o["data"] != EICAR for o in store.objects.values())
    # sach.pdf đã vào kho trước khi gặp tệp nhiễm: dòng không thành văn bản nên tệp được gỡ (core.files và kho)
    assert len(lab.hasura.incoming) == 1
    assert files_named(lab, "sach.pdf") == [] and len(lab.hasura.files) == 1 and len(store.objects) == 1
    (drop,) = lab.imports.dropped
    assert (drop["line"], len(drop["dropped"])) == (1, 1) and len(store.deleted) == 1


def test_encrypted_entry_is_unscannable(lab, clerk):
    job_id = create(lab, clerk, doc(1, files=["khoa.pdf"]), archive=zip_bytes({"khoa.pdf": PDF_A},
                                                                             encrypted={"khoa.pdf"}))
    lab.drain()
    (row,) = lab.lines(job_id)
    assert (row["status"], row["code"]) == ("failed", "unscannable")


def test_restricted_rows_store_sealed_pdfs(lab, clerk, store):
    secret = text_pdf("NOI DUNG HAN CHE")
    job_id = create(lab, clerk, doc(1, restricted=True, files=["mat.pdf"]), doc(2, restricted=True, files=["mat.docx"]),
                    archive=zip_bytes({"mat.pdf": secret, "mat.docx": b"PK docx"}))
    lab.drain()
    got = lines(lab, job_id)
    assert got[1]["status"] == "ok"
    ((fid, f),) = files_named(lab, "mat.pdf")
    assert f["wrapped_dek"] and store.objects[f["object_key"]]["data"] != secret
    assert lab.hasura.incoming[got[1]["result"]["document_id"]]["restricted"] is True
    assert (got[2]["status"], got[2]["code"]) == ("failed", "restricted_pdf_only")


def test_restricted_rows_without_a_vault(monkeypatch, tmp_path, settings, scanner, store, verifier, meili, clerk):
    with make_lab(monkeypatch, tmp_path, settings, scanner=scanner, store=store, verifier=verifier, meili=meili,
                  vault=None) as lab:
        job_id = create(lab, clerk, doc(1, restricted=True, files=["mat.pdf"]), doc(2),
                        archive=zip_bytes({"mat.pdf": text_pdf("X")}))
        lab.drain()
        got = lines(lab, job_id)
    assert (got[1]["status"], got[1]["code"]) == ("failed", "vault_unavailable")
    assert got[2]["status"] == "ok" and store.objects == {}


# --- dòng không thành văn bản: gỡ tệp đã lưu ---------------------------------------------------------------------


def test_rows_rejected_after_their_files_were_stored_leave_no_files(lab, clerk, store):
    # Action quyết loại văn bản, ngày… sau khi tệp đã qua trạm quét và vào kho: bị từ chối thì gỡ tệp của dòng
    archive = zip_bytes({"ok.pdf": PDF_A, "loai.pdf": PDF_B, "ngay.pdf": PDF_A + b"2", "ngan.pdf": PDF_B + b"3"})
    job_id = create(lab, clerk, doc(1, files=["ok.pdf"]), doc(2, type_code="XX", files=["loai.pdf"]),
                    doc(3, issued_on="2026-13-45", files=["ngay.pdf"]), doc(4, summary="ngắn", files=["ngan.pdf"]),
                    archive=archive)
    lab.drain()
    got = lines(lab, job_id)
    assert [got[n]["code"] for n in (1, 2, 3, 4)] == [None, "invalid", "invalid", "invalid"]
    assert got[2]["fields"] == {"type_code": "unknown"} and got[3]["fields"] == {"issued_on": "format"}
    ((ok_id, ok_row),) = files_named(lab, "ok.pdf")
    assert list(lab.hasura.files) == [ok_id] and list(store.objects) == [ok_row["object_key"]]
    assert len(store.deleted) == 3
    assert sorted(d["line"] for d in lab.imports.dropped) == [2, 3, 4]
    assert all(len(d["dropped"]) == 1 for d in lab.imports.dropped)


def test_resending_a_batch_with_rejected_rows_keeps_the_file_count(lab, clerk, store):
    # như bước 5 của make demo-nap-lo: dòng hợp lệ báo trùng, dòng Action từ chối lưu tệp rồi gỡ lại
    rows = (doc(1, files=["a.pdf"]), doc(2, type_code="XX", files=["b.pdf"]), doc(3, issued_on="15/10/2026",
                                                                                  files=["c.pdf"]))
    archive = zip_bytes({"a.pdf": PDF_A, "b.pdf": PDF_B, "c.pdf": PDF_A + b"c"})
    create(lab, clerk, *rows, archive=archive)
    lab.drain()
    files, objects = dict(lab.hasura.files), dict(store.objects)
    assert len(files) == 1 and len(objects) == 1
    again = create(lab, clerk, *rows, archive=archive)
    lab.drain()
    assert [r["status"] for r in lab.lines(again)] == ["duplicate", "failed", "failed"]
    assert lab.hasura.files == files and store.objects == objects and len(lab.hasura.incoming) == 1


def test_files_attached_to_a_document_or_kept_in_the_personal_space_are_not_dropped(lab, clerk, store):
    job_id = create(lab, clerk, doc(1, files=["a.pdf"]), doc(2, files=["b.pdf"]),
                    archive=zip_bytes({"a.pdf": PDF_A, "b.pdf": PDF_B}))
    lab.drain()
    handler, job = lab.importer.handlers["incoming"], lab.job(job_id)
    attached = lines(lab, job_id)[1]["result"]["file_ids"]
    # gỡ nhầm một dòng đã thành văn bản (vd văn bản tạo xong mà mất phản hồi): tệp đã gắn văn bản vẫn còn
    assert lab.client.portal.call(handler.abandon, job, 1, {"file_ids": attached}) == 0
    ((b_id, _),) = files_named(lab, "b.pdf")
    lab.imports.personal.add(str(b_id))
    assert lab.client.portal.call(handler.abandon, job, 2, {"file_ids": [str(b_id)]}) == 0
    assert len(lab.hasura.files) == 2 and store.deleted == []
    # văn bản đã có id trong kết quả: không hỏi gỡ gì
    assert lab.client.portal.call(handler.abandon, job, 1, {"file_ids": attached, "document_id": "x"}) == 0
    assert [d["line"] for d in lab.imports.dropped] == [1, 2]


def test_a_failed_drop_is_logged_and_the_batch_goes_on(lab, clerk, store, monkeypatch, caplog):
    async def broken(job, line, ids):
        raise HasuraError("Không gọi được Hasura: ConnectError")

    monkeypatch.setattr(lab.imports, "drop_files", broken)
    job_id = create(lab, clerk, doc(1, type_code="XX", files=["a.pdf"]), doc(2),
                    archive=zip_bytes({"a.pdf": PDF_A}))
    with caplog.at_level(logging.WARNING, logger="svc_files"):
        lab.drain()
    got = lines(lab, job_id)
    assert (got[1]["code"], got[2]["status"], lab.job(job_id)["status"]) == ("invalid", "ok", "done")
    (left,) = [json.loads(r.getMessage()) for r in caplog.records if "core.import.files_left" in r.getMessage()]
    assert left["line"] == 1 and left["file_ids"] == got[1]["result"]["file_ids"] and len(lab.hasura.files) == 1


def test_rows_given_up_or_revoked_drop_the_files_they_stored(lab1, clerk, store):
    lab = lab1
    job_id = create(lab, clerk, doc(1, files=["a.pdf"]), doc(2, files=["b.pdf"]),
                    archive=zip_bytes({"a.pdf": PDF_A, "b.pdf": PDF_B}))
    # dòng 1: tệp đã lưu, svc-workflow bận tới hết lượt → failed unavailable, tệp gỡ
    lab.imports.lines[(job_id, 1)]["attempts"] = MAX_ATTEMPTS - 1
    lab.hasura.fail_next = [HasuraError("svc-workflow bận", "unavailable")]
    lab.run()
    got = lines(lab, job_id)
    assert (got[1]["status"], got[1]["code"]) == ("failed", "unavailable") and files_named(lab, "a.pdf") == []
    # dòng 2: tệp đã lưu, lõi bận (dòng còn chờ) rồi người tạo lô bị khóa → actor_revoked, tệp gỡ
    lab.hasura.fail_next = [HasuraError("svc-workflow bận", "unavailable")]
    lab.run()
    assert lines(lab, job_id)[2]["status"] == "pending" and len(files_named(lab, "b.pdf")) == 1
    lab.imports.users[(str(TENANT_A), "u-van-thu")] = {"enabled": False, "role": "clerk"}
    lab.advance(120)
    lab.drain()
    got = lines(lab, job_id)
    assert got[2]["code"] == "actor_revoked" and lab.hasura.files == {} and store.objects == {}
    assert len(store.deleted) == 2 and lab.hasura.incoming == {}


# --- giữ dòng: hai vòng không làm cùng một dòng ---------------------------------------------------------------


def test_two_workers_never_work_the_same_row(lab, clerk, scanner, monkeypatch):
    # hai tiến trình svc-files cùng làm một lô; ClamAV chậm để hai vòng chen nhau giữa lúc lưu tệp
    real = scanner.scan

    async def slow(chunks):
        await asyncio.sleep(0.05)
        return await real(chunks)

    monkeypatch.setattr(scanner, "scan", slow)
    names = [f"c{n}.pdf" for n in range(4)]
    job_id = create(lab, clerk, *(doc(n, files=[name]) for n, name in enumerate(names, 1)),
                    archive=zip_bytes({name: PDF_A + name.encode() for name in names}))
    other = Importer(lab.imports, lab.importer.handlers, lab.importer.spool, chunk=20, clock=lab.now)

    async def both() -> None:
        await asyncio.gather(lab.importer.run_once(), other.run_once())

    lab.client.portal.call(both)
    lab.advance(LEASE_RECHECK_S + 1)
    lab.drain()
    got = lab.lines(job_id)
    assert [r["status"] for r in got] == ["ok"] * 4 and [r["attempts"] for r in got] == [1] * 4
    assert len(lab.hasura.files) == 4 and len(lab.hasura.incoming) == 4      # mỗi dòng đúng một tệp, không mồ côi
    assert sorted(f for d in lab.hasura.incoming.values() for f in d["file_ids"]) == sorted(
        str(fid) for fid in lab.hasura.files)
    assert lab.imports.dropped == []


def test_a_row_held_by_a_dead_worker_is_taken_again_after_its_lease(lab, clerk):
    job_id = create(lab, clerk, doc(1), doc(2))
    # tiến trình trước nhận dòng 1 rồi chết giữa chừng: dòng còn chờ, đang được giữ
    held = (lab.now() + timedelta(seconds=LEASE_S)).isoformat()
    lab.imports.lines[(job_id, 1)].update(attempts=1, claimed_until=held)
    lab.drain()
    got = lines(lab, job_id)
    assert (got[1]["status"], got[2]["status"]) == ("pending", "ok")
    # mọi dòng còn chờ đều đang bị giữ: lô hẹn lại sau LEASE_RECHECK_S, không quay vòng liên tục
    assert datetime.fromisoformat(lab.job(job_id)["run_after"]) > lab.now() + timedelta(seconds=LEASE_RECHECK_S - 5)
    lab.advance(LEASE_S + 1)
    lab.drain()
    got = lines(lab, job_id)
    assert (got[1]["status"], got[1]["attempts"], lab.job(job_id)["status"]) == ("ok", 2, "done")
    assert len(lab.hasura.incoming) == 2


def test_a_worker_that_lost_its_row_writes_nothing_for_it(lab, clerk, scanner, store, monkeypatch):
    # vòng A nhận dòng rồi kẹt ở bước quét tệp quá hạn giữ; vòng B nhận lại dòng, cũng đang quét thì A chạy tiếp. A chỉ
    # biết mình mất dòng ở lần ghi kế tiếp: không ghi gì vào dòng, gỡ tệp vừa lưu — kho chỉ còn tệp gắn văn bản
    real, calls = scanner.scan, []
    entered, go = [asyncio.Event(), asyncio.Event()], [asyncio.Event(), asyncio.Event()]

    async def gated(chunks):
        n = len(calls)
        calls.append(n)
        entered[n].set()
        await asyncio.wait_for(go[n].wait(), 10)
        return await real(chunks)

    job_id = create(lab, clerk, doc(1, files=["g0.pdf"]), archive=zip_bytes({"g0.pdf": PDF_A}))
    monkeypatch.setattr(scanner, "scan", gated)         # sau khi tạo lô: tệp dữ liệu cũng qua trạm quét
    other = Importer(lab.imports, lab.importer.handlers, lab.importer.spool, chunk=20, clock=lab.now)

    async def scenario() -> None:
        a = asyncio.create_task(lab.importer.run_once())
        await asyncio.wait_for(entered[0].wait(), 10)      # A đã nhận dòng, đang quét
        lab.advance(LEASE_S + 1)            # một bước của A kéo dài quá hạn giữ
        b = asyncio.create_task(other.run_once())
        await asyncio.wait_for(entered[1].wait(), 10)      # B đã nhận lại dòng, đang quét
        go[0].set()
        await a
        go[1].set()
        await b

    lab.client.portal.call(scenario)
    lab.drain()
    (row,) = lab.lines(job_id)
    assert (row["status"], row["attempts"]) == ("ok", 2)
    (document,) = lab.hasura.incoming.values()
    assert row["result"]["document_id"] == document["id"]
    # đúng một tệp trong kho và trong core.files, gắn với văn bản: tệp A lưu sau khi mất dòng đã bị gỡ
    assert [str(fid) for fid in lab.hasura.files] == document["file_ids"] and len(store.objects) == 1
    assert [e["entity_id"] for e in lab.imports.audit if e["action"] == "import.finished"] == [job_id]


def test_a_row_left_at_its_last_attempt_is_given_up_and_drops_its_files(lab, clerk, store):
    job_id = create(lab, clerk, doc(1, files=["a.pdf"]), archive=zip_bytes({"a.pdf": PDF_A}))
    lab.hasura.fail_next = [HasuraError("svc-workflow bận", "unavailable")]
    lab.run()
    assert len(files_named(lab, "a.pdf")) == 1
    # tiến trình chết ở lượt cuối sau khi lưu tệp: dòng còn chờ, attempts = MAX_ATTEMPTS — chỉ nhận để ghi lỗi
    lab.imports.lines[(job_id, 1)]["attempts"] = MAX_ATTEMPTS
    calls = len(lab.hasura.act_calls)
    lab.advance(120)
    lab.drain()
    (row,) = lab.lines(job_id)
    assert (row["status"], row["code"], row["attempts"]) == ("failed", "unavailable", MAX_ATTEMPTS)
    assert len(lab.hasura.act_calls) == calls and files_named(lab, "a.pdf") == [] and store.objects == {}


def test_two_workers_closing_the_same_batch_log_it_once(lab, clerk, monkeypatch):
    # hai vòng cùng thấy lô hết dòng chờ (mọi dòng hỏng lúc đọc) rồi cùng đóng: lô done một lần, sổ đúng một dòng
    job_id = create(lab, clerk, "{x", "[1]")
    real = lab.imports.due

    async def due(now):
        job = await real(now)
        await asyncio.sleep(0.01)           # cả hai vòng lấy được lô trước khi vòng nào đóng
        return job

    monkeypatch.setattr(lab.imports, "due", due)
    other = Importer(lab.imports, lab.importer.handlers, lab.importer.spool, chunk=20, clock=lab.now)

    async def both() -> list[bool]:
        return await asyncio.gather(lab.importer.run_once(), other.run_once())

    assert lab.client.portal.call(both) == [True, True]
    job = lab.job(job_id)
    assert (job["status"], job["failed"]) == ("done", 2)
    assert [e["entity_id"] for e in lab.imports.audit if e["action"] == "import.finished"] == [job_id]


# --- lỗi tạm, mất phản hồi, khởi động lại ------------------------------------------------------------------------


def test_busy_core_pauses_the_batch_and_lets_others_run(lab, clerk, make_token):
    a = create(lab, clerk, doc(1))
    b = create(lab, make_token(sub="u-van-thu-b", tenant=str(TENANT_B)), doc(1))
    lab.hasura.fail_next = [HasuraError("Không gọi được svc-workflow", "unavailable")]
    assert lab.run() == [True]                  # lô A: lõi bận
    row = lines(lab, a)[1]
    assert (row["status"], row["attempts"], row["data"]) == ("pending", 1, doc(1))
    assert row["claimed_until"] is None         # lõi bận: thả dòng ngay, lượt sau (vòng nào cũng được) nhận lại
    job = lab.job(a)
    assert job["note"].startswith(PAUSED) and "svc-workflow" in job["note"]
    assert datetime.fromisoformat(job["run_after"]) > lab.now()
    assert lab.run() == [True]                  # lô B vẫn chạy
    assert lab.job(b)["status"] == "done" and lab.job(b)["ok"] == 1
    assert lab.run() == [False]                 # lô A chưa tới giờ thử lại
    lab.advance(3)
    lab.drain()
    job = lab.job(a)
    assert (job["status"], job["ok"], job["note"]) == ("done", 1, None)
    assert lines(lab, a)[1]["attempts"] == 2


def test_backoff_grows_and_gives_up_after_max_attempts(lab, clerk):
    job_id = create(lab, clerk, doc(1))
    waits = []
    for _ in range(3):
        lab.hasura.fail_next = [HasuraError("Không gọi được Hasura: ConnectError")]
        before = lab.now()
        lab.run()
        waits.append(round((datetime.fromisoformat(lab.job(job_id)["run_after"]) - before).total_seconds()))
        lab.advance(120)
    assert waits == [2, 4, 8]
    lab.imports.lines[(job_id, 1)]["attempts"] = MAX_ATTEMPTS - 1
    lab.hasura.fail_next = [HasuraError("svc-workflow bận", "unavailable")]
    lab.drain()
    (row,) = lab.lines(job_id)
    assert (row["status"], row["code"], row["attempts"]) == ("failed", "unavailable", MAX_ATTEMPTS)
    assert lab.job(job_id)["status"] == "done"


def test_internal_errors_are_retried_a_few_times(lab, clerk):
    job_id = create(lab, clerk, doc(1), doc(2))
    lab.hasura.fail_next = [HasuraError("lỗi lạ", "internal")] * 3
    for _ in range(3):
        lab.run()
        lab.advance(120)
    lab.drain()
    got = lines(lab, job_id)
    assert (got[1]["status"], got[1]["code"], got[1]["attempts"]) == ("failed", "internal", 3)
    assert got[2]["status"] == "ok"


def test_lost_reply_is_claimed_back_not_duplicated(lab, clerk):
    job_id = create(lab, clerk, doc(1))
    lab.hasura.lose_reply = 1
    lab.run()
    assert lines(lab, job_id)[1]["status"] == "pending" and len(lab.hasura.incoming) == 1
    lab.advance(120)
    lab.drain()
    (row,) = lab.lines(job_id)
    (document_id,) = lab.hasura.incoming
    assert row["status"] == "ok" and row["result"]["document_id"] == document_id
    assert (lab.job(job_id)["ok"], lab.job(job_id)["duplicate"]) == (1, 0)


def test_lost_reply_does_not_claim_a_document_of_another_row(lab, clerk):
    # hai dòng cùng khóa chặn trùng trong một lô: dòng 2 mất phản hồi rồi gặp văn bản của dòng 1 → trùng, không nhận
    job_id = create(lab, clerk, doc(1), doc(1))
    lab.run()
    got = lines(lab, job_id)
    assert got[1]["status"] == "ok" and got[2]["status"] == "duplicate"
    lab.imports.lines[(job_id, 2)].update(status="pending", attempts=1, result=None, data=doc(1), done_at=None,
                                          claimed_until=None)
    lab.imports.jobs[job_id]["status"] = "running"
    lab.drain()
    assert lines(lab, job_id)[2]["status"] == "duplicate"
    assert lines(lab, job_id)[2]["result"] is None


def test_files_already_stored_are_not_stored_again(lab, clerk, store, monkeypatch):
    job_id = create(lab, clerk, doc(1, files=["a.pdf", "b.pdf"]), archive=zip_bytes({"a.pdf": PDF_A, "b.pdf": PDF_B}))
    real, calls = store.put, []

    def flaky(key, body, **kw):
        calls.append(key)
        if len(calls) == 2:
            raise StorageError("kho đứt kết nối")
        return real(key, body, **kw)

    monkeypatch.setattr(store, "put", flaky)
    lab.run()
    (row,) = lab.lines(job_id)
    assert row["status"] == "pending" and len(row["result"]["file_ids"]) == 1
    assert "Kho lưu tệp" in lab.job(job_id)["note"]
    lab.advance(120)
    lab.drain()
    (row,) = lab.lines(job_id)
    assert row["status"] == "ok" and len(calls) == 3
    assert len(lab.hasura.files) == 2
    (document,) = lab.hasura.incoming.values()
    assert [lab.hasura.files[uuid.UUID(f)]["filename"] for f in document["file_ids"]] == ["a.pdf", "b.pdf"]


def test_a_new_importer_continues_where_the_old_one_stopped(lab1, clerk):
    lab = lab1
    job_id = create(lab, clerk, doc(1), doc(2), doc(3))
    lab.run()
    assert [r["status"] for r in lab.lines(job_id)] == ["ok", "pending", "pending"]
    fresh = Importer(lab.imports, lab.importer.handlers, lab.importer.spool, chunk=1, clock=lab.now)
    while lab.client.portal.call(fresh.run_once):
        pass
    assert [r["status"] for r in lab.lines(job_id)] == ["ok", "ok", "ok"]
    assert len(lab.hasura.incoming) == 3 and lab.job(job_id)["ok"] == 3


def test_lost_archive_fails_only_rows_that_need_it(lab, clerk):
    job_id = create(lab, clerk, doc(1, files=["a.pdf"]), doc(2), archive=zip_bytes({"a.pdf": PDF_A}))
    (lab.spool_dir / f"{job_id}.zip").unlink()          # tmpfs mất khi container khởi động lại
    lab.drain()
    got = lines(lab, job_id)
    assert (got[1]["status"], got[1]["code"], got[1]["message"]) == ("failed", "archive_lost", ARCHIVE_LOST)
    assert got[2]["status"] == "ok"
    assert lab.job(job_id)["note"] == ARCHIVE_LOST


def test_prepare_cleans_the_spool_but_keeps_open_batches(lab, clerk):
    job_id = create(lab, clerk, doc(1, files=["a.pdf"]), archive=zip_bytes({"a.pdf": PDF_A}))
    stale, part = lab.spool_dir / f"{uuid.uuid4()}.zip", lab.spool_dir / f"{uuid.uuid4()}.zip.part"
    for p in (stale, part):
        p.write_bytes(b"x")
    past = time.time() - 3600
    for p in (stale, part, lab.spool_dir / f"{job_id}.zip"):
        os.utime(p, (past, past))
    lab.client.portal.call(lab.importer.prepare)
    assert sorted(p.name for p in lab.spool_dir.iterdir()) == [f"{job_id}.zip"]
    assert oct(lab.spool_dir.stat().st_mode & 0o777) == "0o700"


@pytest.mark.parametrize("actor", [{"enabled": False, "role": "clerk"}, {"enabled": True, "role": "staff"}])
def test_revoked_creator_stops_the_batch(lab1, clerk, actor):
    lab = lab1
    job_id = create(lab, clerk, doc(1), doc(2), doc(3, summary="x"))
    lab.run()
    lab.imports.users[(str(TENANT_A), "u-van-thu")] = actor
    lab.drain()
    got = lines(lab, job_id)
    assert got[1]["status"] == "ok"
    assert (got[2]["status"], got[2]["code"], got[2]["data"]) == ("failed", "actor_revoked", None)
    assert got[3]["code"] == "actor_revoked"
    job = lab.job(job_id)
    assert (job["status"], job["ok"], job["failed"]) == ("done", 1, 2)
    assert len(lab.hasura.incoming) == 1


def test_enabled_clerk_in_the_directory_keeps_going(lab, clerk):
    lab.imports.users[(str(TENANT_A), "u-van-thu")] = {"enabled": True, "role": "clerk"}
    job_id = create(lab, clerk, doc(1))
    lab.drain()
    assert lab.job(job_id)["ok"] == 1


# --- vào sổ -----------------------------------------------------------------------------------------------------


def test_register_gives_incoming_numbers(lab, clerk):
    job_id = create(lab, clerk, doc(1), doc(2), params={"register": "true"})
    lab.drain()
    assert [c["action"] for c in lab.hasura.act_calls] == ["receiveIncoming", "registerIncoming"] * 2
    got = lines(lab, job_id)
    assert [got[n]["result"]["register_number"] for n in (1, 2)] == [1, 2]
    r = lab.client.get(f"/api/imports/{job_id}/rows", headers={"Authorization": f"Bearer {clerk}"})
    assert [x["register_number"] for x in r.json()["rows"]] == [1, 2]
    (event,) = [e for e in lab.imports.audit if e["action"] == "import.finished"]
    assert event["diff"]["register"] is True


def test_register_failure_keeps_the_received_document(lab, clerk):
    job_id = create(lab, clerk, doc(1), params={"register": "true"})
    lab.hasura.register_error = HasuraError("Chưa cấu hình sổ văn bản đến năm 2026", "no_register")
    lab.drain()
    (row,) = lab.lines(job_id)
    assert (row["status"], row["code"]) == ("failed", "register_failed")
    assert row["result"]["document_id"] in lab.hasura.incoming
    assert row["message"].startswith("Đã tiếp nhận nhưng chưa vào sổ")


def test_register_lost_reply_reads_the_number_back(lab, clerk):
    job_id = create(lab, clerk, doc(1), params={"register": "true"})
    lab.hasura.lose_register = 1
    lab.run()
    assert lab.lines(job_id)[0]["status"] == "pending"
    lab.advance(120)
    lab.drain()
    (row,) = lab.lines(job_id)
    assert row["status"] == "ok" and row["result"]["register_number"] == 1
    assert [c["action"] for c in lab.hasura.act_calls] == ["receiveIncoming", "registerIncoming", "registerIncoming"]
    assert lab.hasura.numbers[str(TENANT_A)] == 1


# --- nhiều lô, đóng lô ------------------------------------------------------------------------------------------


def test_two_tenants_take_turns(lab1, clerk, make_token):
    lab = lab1
    a = create(lab, clerk, doc(1), doc(2))
    b = create(lab, make_token(sub="u-van-thu-b", tenant=str(TENANT_B)), doc(1), doc(2))
    lab.drain()
    assert [c["tenant_id"] for c in lab.hasura.act_calls] == [str(TENANT_A), str(TENANT_B)] * 2
    assert lab.job(a)["ok"] == 2 and lab.job(b)["ok"] == 2
    # văn bản trùng số ký hiệu ở hai đơn vị là hai văn bản khác nhau
    assert len(lab.hasura.incoming) == 4
    # mọi câu của vòng nền chạy trong đơn vị của lô, trừ câu tìm lô đến giờ (khóa quản trị)
    assert all(t in (str(TENANT_A), str(TENANT_B)) for op, t in lab.imports.ops if op not in ("due", "open_ids"))


def test_closing_a_batch_snapshots_counts_and_logs_it(lab, clerk):
    job_id = create(lab, clerk, doc(1, files=["a.pdf"]), doc(1), "{x", archive=zip_bytes({"a.pdf": PDF_A}))
    assert (lab.spool_dir / f"{job_id}.zip").exists()
    lab.drain()
    job = lab.job(job_id)
    assert (job["status"], job["ok"], job["duplicate"], job["failed"], job["total"]) == ("done", 1, 1, 1, 3)
    assert job["finished_at"] == job["run_after"]
    (event,) = [e for e in lab.imports.audit if e["action"] == "import.finished"]
    assert event == {"actor_id": "u-van-thu", "actor_kind": "service", "request_id": job_id,
                     "action": "import.finished", "entity": "core.import_jobs", "entity_id": job_id,
                     "tenant_id": str(TENANT_A),
                     "diff": {"kind": "incoming", "format": "ndjson", "register": False, "total": 3, "ok": 1,
                              "duplicate": 1, "failed": 1}}
    assert not (lab.spool_dir / f"{job_id}.zip").exists()
    r = lab.client.get(f"/api/imports/{job_id}", headers={"Authorization": f"Bearer {clerk}"}).json()
    assert (r["status"], r["ok"], r["duplicate"], r["failed"], r["pending"]) == ("done", 1, 1, 1, 0)
    assert lab.run() == [False]


def test_an_error_while_working_pushes_the_batch_back(lab, clerk):
    job_id = create(lab, clerk, doc(1))

    async def broken(job, at):
        raise HasuraError("Không gọi được Hasura: ConnectError")

    lab.imports.start = broken
    with pytest.raises(HasuraError):
        lab.run()
    wait = (datetime.fromisoformat(lab.job(job_id)["run_after"]) - lab.now()).total_seconds()
    assert 55 < wait <= 60
    del lab.imports.start
    lab.advance(61)
    lab.drain()
    assert lab.job(job_id)["ok"] == 1


def test_unknown_kind_waits_for_a_handler(lab, clerk):
    job_id = create(lab, clerk, doc(1))
    lab.imports.jobs[job_id]["kind"] = "outgoing"
    assert lab.run() == [True]
    job = lab.job(job_id)
    assert job["status"] == "queued" and "outgoing" in job["note"]
    assert (datetime.fromisoformat(job["run_after"]) - lab.now()).total_seconds() > 3500
    assert lab.hasura.act_calls == []
