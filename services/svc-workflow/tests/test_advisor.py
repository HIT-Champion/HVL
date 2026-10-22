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

"""Tác tử gợi ý giao việc (F4.3): nhánh BPMN song song, worker moc-goi-y, lưu gợi ý + sổ bằng vai trò agent, CLI đo."""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import logging
import pathlib
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date

import httpx2
import pytest
from fastapi.testclient import TestClient

from conftest import DEPT_DT, DEPT_KTPM, DOC, TENANT
from svc_workflow import advisor as advisor_mod
from svc_workflow.advisor import HISTORY, TARGET, TOPIC, Advisor
from svc_workflow.app import create_app
from svc_workflow.config import ConfigError, Settings
from svc_workflow.files import FilesClient, FilesError, ServiceToken
from svc_workflow.flowable import ExternalJob, FlowableError
from svc_workflow.hasura import Actor, HasuraClient
from svc_workflow.sla import Deadlines
from test_app import ENV, NoDirectory

PROCESSES = pathlib.Path(__file__).resolve().parents[3] / "processes"
BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
FLOWABLE = "{http://flowable.org/bpmn}"
DIRECTOR_GROUP = f"t:{TENANT}:director"
TODAY = date(2026, 10, 26)                     # thứ Hai
SUMMARY = "Về việc xét cấp học bổng khuyến khích học tập học kỳ II"
P1, P2, P3, P4, P5 = (f"aaaaaaaa-0000-4000-8000-00000000000{i}" for i in range(1, 6))
DIFF_KEYS = {"outcome", "outcome_reason", "department_id", "due_days", "confidence", "evidence", "candidates",
             "semantic", "duration_ms"}


def run(coro):
    return asyncio.run(coro)


class Tick:
    """Đồng hồ đơn điệu giả: mỗi lần đọc tăng 50 ms."""

    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        self.t += 0.05
        return self.t


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env(ENV)


@pytest.fixture
def library(hasura):
    """Văn bản đến đã giao: ba văn bản Tổ Đào tạo chủ trì (một giao thẳng chuyên viên), một văn bản KTPM; văn bản đích
    vào sổ sáng thứ Hai 26/10 giờ VN; KTPM có lãnh đạo phòng."""
    hasura.users["u-manager-ktpm"] = {"id": "u-manager-ktpm", "department_id": str(DEPT_KTPM), "role": "manager",
                                      "enabled": True}
    hasura.document.update(registered_at="2026-10-26T02:00:00Z", summary=SUMMARY)
    hasura.add_past(P1, department=DEPT_DT, registered_at="2026-09-01T02:00:00Z", lead_due="2026-09-11")   # 10 ngày
    hasura.add_past(P2, department=DEPT_DT, registered_at="2026-09-08T02:00:00Z", lead_due="2026-09-15")   # 7 ngày
    hasura.add_past(P3, user="u-staff-dt", registered_at="2026-09-15T02:00:00Z", lead_due="2026-09-27")    # 12 ngày
    hasura.add_past(P4, department=DEPT_KTPM, registered_at="2026-09-20T02:00:00Z", lead_due="2026-09-23")  # 3 ngày
    for doc_id in (P1, P2, P3, P4):
        hasura.past[doc_id]["summary"] = SUMMARY
    return hasura


@pytest.fixture
def advisor(hasura, flowable, files, settings) -> Advisor:
    return Advisor(hasura, flowable, files, settings, clock=Tick(), today=lambda: TODAY)  # type: ignore[arg-type]


def answer(*hits: tuple[str, float], semantic: bool = False) -> dict:
    return {"hits": [{"document_id": d, "score": s} for d, s in hits], "terms": 7, "semantic": semantic,
            "duration_ms": 41}


def goi_y(flowable, job_id: str = "g1", process: str = "p1", doc: str = DOC, *, direction_open: bool = True,
          **variables) -> ExternalJob:
    """Việc moc-goi-y Flowable tạo khi văn bản vào sổ; nhánh chỉ đạo song song vẫn còn việc chiDao mở."""
    job = ExternalJob(job_id, process, "goiYGiaoViec", {"tenantId": str(TENANT), "documentId": doc, **variables})
    flowable.jobs.append(job)
    flowable.topics[job_id] = TOPIC
    if direction_open:
        flowable.add_task(f"cd-{job_id}", "vbden.chiDao", groups=[DIRECTOR_GROUP], doc=doc, process=process)
    return job


# --- nhánh BPMN ------------------------------------------------------------------------------------------


def test_suggestion_branch_never_blocks_direction():
    root = ET.parse(PROCESSES / "van-ban-den.bpmn20.xml").getroot()
    process = root.find(f"{BPMN}process")
    kinds = {el.get("id"): el.tag.removeprefix(BPMN) for el in process if el.get("id")}
    out, incoming = defaultdict(list), defaultdict(list)
    for f in process.iter(f"{BPMN}sequenceFlow"):
        out[f.get("sourceRef")].append(f.get("targetRef"))
        incoming[f.get("targetRef")].append(f.get("sourceRef"))
    # vào sổ → cổng song song → {chỉ đạo, gợi ý}: chiDao có ngay khi khởi chạy, không chờ tác tử
    (gate,) = out["vaoSo"]
    assert kinds[gate] == "parallelGateway" and sorted(out[gate]) == ["chiDao", "goiYGiaoViec"]
    assert incoming["chiDao"] == [gate]
    task = process.find(f"{BPMN}serviceTask[@id='goiYGiaoViec']")
    assert task.get(f"{FLOWABLE}type") == "external-worker" and task.get(f"{FLOWABLE}topic") == "moc-goi-y"
    # timer duy nhất của nhánh: ngắt việc, thời hạn hằng (không theo biến của phiên)
    (boundary,) = [b for b in process.iter(f"{BPMN}boundaryEvent") if b.get("attachedToRef") == "goiYGiaoViec"]
    assert boundary.get("cancelActivity") == "true"
    duration = boundary.find(f"{BPMN}timerEventDefinition/{BPMN}timeDuration").text
    assert duration == "PT10M" and "${" not in duration
    # từ việc gợi ý và timer của nó chỉ tới được điểm kết thúc: không việc người, không cổng nối lại
    seen: set[str] = set()
    todo = ["goiYGiaoViec", boundary.get("id")]
    while todo:
        for target in out[todo.pop()]:
            if target not in seen:
                seen.add(target)
                todo.append(target)
    assert seen == {"daGoiY", "khongGoiY"} and all(kinds[n] == "endEvent" for n in seen)
    assert not [g for g in kinds if kinds[g] == "parallelGateway" and len(incoming[g]) > 1]
    assert root.find(f".//{BPMN}terminateEventDefinition") is None


# --- đường thuận -------------------------------------------------------------------------------------------


def test_suggestion_is_saved_with_its_audit_entry_in_one_agent_call(advisor, library, flowable, files):
    job = goi_y(flowable)
    files.similar_answer = answer((P1, 0.9), (P2, 0.8), (P3, 0.7), (P4, 0.35))
    assert run(advisor.run_jobs()) == 1
    assert flowable.jobs_done == ["g1"] and flowable.jobs_failed == []
    assert flowable.acquired[-1] == (TOPIC, {"count": 5, "lock": "PT1M"})
    assert files.similar_calls == [(TENANT, DOC, 15)]

    row = library.suggestions[DOC]
    assert (row["status"], row["reason"], row["department_id"], row["confidence"]) == (
        "suggested", None, str(DEPT_DT), "high")
    assert row["share"] == round(2.4 / 2.75, 3) and row["process_id"] == job.process_instance_id
    # median_low(10, 7, 12) ngày; 26/10 + 10 = thứ Năm 5/11
    assert (row["due_days"], row["due_on"]) == (10, "2026-11-05")
    assert row["evidence"] == [
        {"document_id": P1, "score": 0.9, "department_id": str(DEPT_DT), "days": 10},
        {"document_id": P2, "score": 0.8, "department_id": str(DEPT_DT), "days": 7},
        {"document_id": P3, "score": 0.7, "department_id": str(DEPT_DT), "days": 12},  # giao thẳng chuyên viên ĐT
        {"document_id": P4, "score": 0.35, "department_id": str(DEPT_KTPM), "days": 3},
    ]
    assert (row["candidates"], row["semantic"], row["tenant_id"], row["agent_id"]) == (
        4, False, str(TENANT), "moc-assigner")

    (entry,) = library.agent_audit
    assert {k: entry[k] for k in ("request_id", "action", "entity", "entity_id", "actor_id", "actor_kind")} == {
        "request_id": "goi-y:g1", "action": "assignment.suggested", "entity": "office.documents", "entity_id": DOC,
        "actor_id": "moc-assigner", "actor_kind": "agent"}
    diff = entry["diff"]
    assert set(diff) == DIFF_KEYS and len(diff) == 9
    assert diff == {"outcome": "suggested", "outcome_reason": None, "department_id": str(DEPT_DT), "due_days": 10,
                    "confidence": "high", "evidence": 4, "candidates": 4, "semantic": False,
                    "duration_ms": row["duration_ms"]}
    assert all(not isinstance(v, (list, dict)) for v in diff.values())     # chỉ giá trị vô hướng
    # đọc bằng service, ghi bằng agent cùng danh tính và mã yêu cầu
    assert [(c[0], c[2], c[3], c[4]) for c in library.agent_calls] == [
        ("GiaoViecDaGoiY", TENANT, "moc-assigner", "goi-y:g1"),
        ("LuuGoiYGiaoViec", TENANT, "moc-assigner", "goi-y:g1")]
    assert library.suggest_reads == ["GiaoViecVanBan", "GiaoViecLichSu", "GiaoViecNguoiChuTri", "GiaoViecDonVi"]


def test_due_written_on_the_letter_is_not_overridden(advisor, library, flowable, files):
    library.document["due_on"] = "2026-11-20"
    goi_y(flowable)
    files.similar_answer = answer((P1, 0.9), (P2, 0.8), (P3, 0.7))
    run(advisor.run_jobs())
    row = library.suggestions[DOC]
    assert (row["status"], row["department_id"], row["due_days"], row["due_on"]) == (
        "suggested", str(DEPT_DT), None, None)


def test_nothing_similar_is_recorded_as_none(advisor, library, flowable, files):
    goi_y(flowable)
    assert run(advisor.handle(flowable.jobs[0])) == "none"
    row = library.suggestions[DOC]
    assert (row["status"], row["reason"], row["evidence"], row["candidates"]) == ("none", "no_similar", [], 0)
    (entry,) = library.agent_audit
    assert entry["diff"]["outcome"] == "none" and entry["diff"]["outcome_reason"] == "no_similar"
    assert entry["diff"]["evidence"] == 0 and set(entry["diff"]) == DIFF_KEYS


def test_restricted_letters_never_become_evidence(advisor, library, flowable, files):
    # svc-files hậu kiểm đã loại; giả sử vẫn lọt (vừa bật hạn chế): truy vấn lịch sử lọc lại
    library.add_past(P5, department=DEPT_KTPM, lead_due="2026-09-04", restricted=True)
    goi_y(flowable)
    files.similar_answer = answer((P5, 0.95), (P1, 0.9), (P2, 0.8), (P3, 0.7))
    assert run(advisor.handle(flowable.jobs[0])) == "suggested"
    row = library.suggestions[DOC]
    assert P5 not in {e["document_id"] for e in row["evidence"]}
    assert (row["department_id"], row["candidates"]) == (str(DEPT_DT), 4)


def test_a_unit_without_a_manager_is_never_suggested(advisor, library, flowable, files):
    del library.users["u-manager-ktpm"]
    library.add_past(P5, department=DEPT_KTPM, lead_due="2026-09-04")
    goi_y(flowable)
    files.similar_answer = answer((P4, 0.9), (P5, 0.8))
    assert run(advisor.handle(flowable.jobs[0])) == "none"
    assert library.suggestions[DOC]["reason"] == "no_valid_unit"


# --- bỏ qua: không ghi gì, vẫn hoàn thành việc --------------------------------------------------------------


@pytest.mark.parametrize("case", ["disabled", "too_late", "restricted", "outgoing", "missing", "exists", "no_vars"])
def test_skipped_jobs_write_nothing_and_are_completed(case, hasura, flowable, files, settings, library):
    if case == "disabled":
        settings = dataclasses.replace(settings, suggest_enabled=False)
    advisor = Advisor(hasura, flowable, files, settings, clock=Tick(), today=lambda: TODAY)  # type: ignore[arg-type]
    if case == "no_vars":
        flowable.jobs.append(ExternalJob("g1", "p1", "goiYGiaoViec", {}))
        flowable.topics["g1"] = TOPIC
    else:
        goi_y(flowable, direction_open=case != "too_late",
              **({"documentId": P1} if case == "missing" else {}))
    if case == "missing":
        del hasura.past[P1]
    if case == "restricted":
        hasura.document["restricted"] = True
    if case == "outgoing":
        hasura.document["direction"] = "out"
    if case == "exists":
        hasura.suggestions[DOC] = {"document_id": DOC, "status": "suggested"}
    files.similar_answer = answer((P1, 0.9), (P2, 0.8), (P3, 0.7))
    expected = {"disabled": "skipped:disabled", "too_late": "skipped:too_late", "restricted": "skipped:restricted",
                "outgoing": "skipped:restricted", "missing": "skipped:missing", "exists": "skipped:exists",
                "no_vars": "skipped:missing"}[case]
    assert run(advisor.handle(flowable.jobs[0])) == expected
    assert run(advisor.run_jobs()) == 1
    assert flowable.jobs_done == ["g1"] and flowable.jobs_failed == []
    assert hasura.agent_audit == [] and files.similar_calls == []
    assert set(hasura.suggestions) == ({DOC} if case == "exists" else set())
    if case in ("disabled", "no_vars"):
        assert hasura.suggest_reads == [] and hasura.agent_calls == []


# --- svc-files không giúp được ------------------------------------------------------------------------------


def test_slow_files_service_gives_a_final_failed_row(hasura, flowable, files, settings, library):
    advisor = Advisor(hasura, flowable, files, dataclasses.replace(settings, suggest_timeout_s=0.05),  # type: ignore[arg-type]
                      clock=Tick(), today=lambda: TODAY)
    files.similar_delay = 1.0
    goi_y(flowable)
    assert run(advisor.run_jobs()) == 1
    assert flowable.jobs_done == ["g1"] and flowable.jobs_failed == []     # không thử lại
    row = hasura.suggestions[DOC]
    assert (row["status"], row["reason"], row["department_id"], row["evidence"]) == ("failed", "timeout", None, [])
    (entry,) = hasura.agent_audit
    assert entry["diff"]["outcome"] == "failed" and entry["diff"]["outcome_reason"] == "timeout"


@pytest.mark.parametrize("error", [
    FilesError("Không gọi được svc-files: connection refused"),
    FilesError("svc-files trả 503", 503, "search_unavailable"),
    FilesError("svc-files trả 500", 500),
    FilesError("Keycloak từ chối tài khoản dịch vụ: HTTP 401", 401),
])
def test_files_service_down_gives_failed_unavailable(advisor, library, flowable, files, error):
    files.similar_error = error
    goi_y(flowable)
    assert run(advisor.run_jobs()) == 1
    assert flowable.jobs_done == ["g1"]
    row = library.suggestions[DOC]
    assert (row["status"], row["reason"]) == ("failed", "unavailable")
    assert library.agent_audit[0]["diff"]["outcome_reason"] == "unavailable"


@pytest.mark.parametrize(("error", "expected"), [
    (FilesError("svc-files trả 503", 503, "assistant_disabled"), "skipped:assistant_disabled"),
    (FilesError("svc-files trả 404", 404, "not_found"), "skipped:not_found"),
    (FilesError("svc-files trả 409", 409, "restricted"), "skipped:restricted"),
    (FilesError("svc-files trả 409", 409, "not_incoming"), "skipped:not_incoming"),
])
def test_files_service_refusals_are_skipped_without_a_row(advisor, library, flowable, files, error, expected):
    files.similar_error = error
    goi_y(flowable)
    assert run(advisor.handle(flowable.jobs[0])) == expected
    assert library.suggestions == {} and library.agent_audit == []


# --- CSDL từ chối, lỗi lạ ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("error", "expected"), [
    ('duplicate key value violates unique constraint "assignment_suggestions_pkey"', "skipped:exists"),
    ("assignment_suggestions_sealed: văn bản hạn chế không có gợi ý giao việc", "skipped:restricted"),
])
def test_database_refusals_are_skipped_and_completed(advisor, library, flowable, files, error, expected):
    library.save_error = error
    files.similar_answer = answer((P1, 0.9))
    goi_y(flowable)
    assert run(advisor.handle(flowable.jobs[0])) == expected
    assert run(advisor.run_jobs()) == 1
    assert flowable.jobs_done == ["g1"] and flowable.jobs_failed == [] and library.agent_audit == []


@pytest.mark.parametrize("broken", ["hasura_read", "hasura_save", "flowable", "bad_payload"])
def test_unexpected_errors_hand_the_job_back_after_30_seconds(advisor, library, flowable, files, broken):
    goi_y(flowable)
    files.similar_answer = answer((P1, 0.9))
    if broken == "hasura_read":
        library.fail_suggest_reads = True
    elif broken == "hasura_save":
        library.save_error = "Không gọi được Hasura"
    elif broken == "flowable":
        flowable.down = True
    else:
        files.similar_answer = {"hits": "không phải danh sách", "semantic": False}
        library.document["registered_at"] = "không phải ngày"
    assert run(advisor.run_jobs()) == 1
    assert flowable.jobs_done == [] and [j for j, _ in flowable.jobs_failed] == ["g1"]
    assert flowable.jobs_retry == {"g1": "PT30S"}
    assert library.suggestions == {}


def test_job_closed_by_the_timer_meanwhile_is_ignored(advisor, library, flowable, files):
    async def gone(job_id, worker_id):
        raise FlowableError("Flowable trả 404: job not found", 404)

    flowable.complete_job = gone
    goi_y(flowable)
    files.similar_answer = answer((P1, 0.9))
    assert run(advisor.run_jobs()) == 1
    assert library.suggestions[DOC]["status"] == "suggested" and flowable.jobs_failed == []


def test_a_batch_runs_side_by_side_and_one_failure_does_not_stop_the_others(advisor, library, flowable, files):
    library.add_past(P5)                       # văn bản đến vừa vào sổ, chưa giao
    files.similar_delay = 0.2
    files.similar_answer = answer((P1, 0.9))
    goi_y(flowable, "g1", "p1")
    goi_y(flowable, "g2", "p2", doc=P5)
    goi_y(flowable, "g3", "p3", tenantId="khong-phai-uuid")
    goi_y(flowable, "g4", "p4", doc="33333333-3333-4333-8333-333333333333")   # không có trong CSDL → bỏ qua
    started = time.monotonic()
    assert run(advisor.run_jobs()) == 4
    # hai lần gọi svc-files 0,2 s chạy cùng lúc: cả lô xong trước khi khóa việc (PT1M) hết
    assert time.monotonic() - started < 0.38
    assert sorted(flowable.jobs_done) == ["g1", "g2", "g3", "g4"] and flowable.jobs_failed == []
    assert set(library.suggestions) == {DOC, P5}


def test_sla_worker_and_suggestion_worker_take_only_their_own_jobs(advisor, hasura, flowable, notifier, files,
                                                                   library):
    deadlines = Deadlines(hasura, flowable, notifier, sla_duration="PT1M")  # type: ignore[arg-type]
    sla_job = ExternalJob("s1", "p9", "nhacHan", {})    # không ghi topic: moc-sla
    flowable.jobs.append(sla_job)
    goi_y(flowable)
    files.similar_answer = answer((P1, 0.9))
    assert run(advisor.run_jobs()) == 1
    assert flowable.jobs_done == ["g1"] and flowable.jobs == [sla_job]
    assert run(deadlines.run_jobs()) == 1
    assert flowable.jobs_done == ["g1", "s1"] and flowable.jobs == []
    assert run(advisor.run_jobs()) == 0


def test_log_line_has_counts_but_no_letter_text(advisor, library, flowable, files, caplog):
    goi_y(flowable)
    files.similar_answer = answer((P1, 0.9), (P2, 0.8), (P3, 0.7), semantic=True)
    with caplog.at_level(logging.INFO, logger="svc_workflow"):
        run(advisor.run_jobs())
    (line,) = [json.loads(r.message) for r in caplog.records if "office.assign.suggested" in r.message]
    assert line == {"event": "office.assign.suggested", "tenant_id": str(TENANT), "document_id": DOC,
                    "outcome": "suggested", "reason": None, "confidence": "high", "candidates": 3,
                    "semantic": True, "duration_ms": line["duration_ms"]}
    assert SUMMARY not in caplog.text and "học bổng" not in caplog.text
    assert "summary" not in TARGET and "summary" not in HISTORY


# --- CLI đo leave-one-out -------------------------------------------------------------------------------------


@pytest.fixture
def cli(monkeypatch, advisor):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("MOC_OPENBAO_ADDR", raising=False)
    closed: list[bool] = []

    async def close() -> None:
        closed.append(True)

    monkeypatch.setattr(advisor_mod, "_build", lambda settings: (advisor, close))

    def call(stdin: str, argv: list[str] | None = None) -> int:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        return advisor_mod.main(["evaluate"] if argv is None else argv)

    call.closed = closed  # type: ignore[attr-defined]
    return call


def test_evaluate_reads_ids_and_prints_rows_without_text(cli, library, files, capsys):
    files.similar_answers = {
        P1: answer((P2, 0.8), (P3, 0.7), (P4, 0.3), semantic=True),
        P4: answer((P1, 0.5)),
        P2: FilesError("svc-files trả 409", 409, "restricted"),
    }
    assert cli(json.dumps({"tenant_id": str(TENANT), "documents": [P1, P4, P2]})) == 0
    out = capsys.readouterr().out
    rows = json.loads(out)["rows"]
    assert [r["document_id"] for r in rows] == [P1, P4, P2]
    keys = {"document_id", "actual", "status", "reason", "department_id", "ranking", "confidence", "due_days",
            "evidence", "semantic", "duration_ms"}
    assert all(set(r) == keys for r in rows)
    first, second, third = rows
    assert first["actual"] == {"department_id": str(DEPT_DT), "days": 10}
    assert (first["status"], first["department_id"], first["confidence"], first["semantic"]) == (
        "suggested", str(DEPT_DT), "medium", True)
    assert first["ranking"] == [str(DEPT_DT), str(DEPT_KTPM)] and first["evidence"] == [P2, P3, P4]
    assert first["due_days"] == 7                              # median_low(7, 12): bỏ qua hạn trên văn bản đích
    assert second["actual"] == {"department_id": str(DEPT_KTPM), "days": 3}
    assert (second["status"], second["department_id"], second["ranking"]) == ("suggested", str(DEPT_DT),
                                                                               [str(DEPT_DT)])
    assert (third["status"], third["reason"], third["evidence"], third["ranking"]) == ("failed", "restricted", [], [])
    assert all(isinstance(r["duration_ms"], int) for r in rows)
    # không ghi gì, không in chữ văn bản
    assert library.suggestions == {} and library.agent_calls == [] and SUMMARY not in out
    assert cli.closed == [True]


@pytest.mark.parametrize(("stdin", "argv"), [
    ("không phải JSON", None),
    (json.dumps({"tenant_id": "x", "documents": []}), None),
    (json.dumps({"tenant_id": str(TENANT), "documents": "abc"}), None),
    (json.dumps({"documents": []}), None),
    ("{}", []),
    ("{}", ["evaluate", "thua"]),
])
def test_evaluate_rejects_bad_input_on_stderr(cli, capsys, stdin, argv):
    assert cli(stdin, argv) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "evaluate" in captured.err


def test_evaluate_reports_database_errors(cli, library, capsys):
    library.fail_suggest_reads = True
    assert cli(json.dumps({"tenant_id": str(TENANT), "documents": [P1]})) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "Không đọc được" in captured.err and cli.closed == [True]


# --- cấu hình, nối vào ứng dụng, client HTTP ----------------------------------------------------------------


def test_settings_read_the_five_variables():
    s = Settings.from_env(ENV)
    assert (s.suggest_enabled, s.suggest_poll_interval_s, s.suggest_timeout_s, s.suggest_min_score,
            s.assigner_id) == (True, 2.0, 10.0, 0.3, "moc-assigner")
    s = Settings.from_env({**ENV, "MOC_SUGGEST_ENABLED": "false", "MOC_SUGGEST_POLL_INTERVAL_S": "0",
                           "MOC_SUGGEST_TIMEOUT_S": "7.5", "MOC_SUGGEST_MIN_SCORE": "0.45",
                           "MOC_ASSIGNER_ID": "moc-thu"})
    assert (s.suggest_enabled, s.suggest_poll_interval_s, s.suggest_timeout_s, s.suggest_min_score,
            s.assigner_id) == (False, 0.0, 7.5, 0.45, "moc-thu")


@pytest.mark.parametrize(("name", "value"), [
    ("MOC_SUGGEST_ENABLED", "co"), ("MOC_SUGGEST_POLL_INTERVAL_S", "-1"), ("MOC_SUGGEST_TIMEOUT_S", "0"),
    ("MOC_SUGGEST_TIMEOUT_S", "60"), ("MOC_SUGGEST_MIN_SCORE", "1.5"), ("MOC_SUGGEST_MIN_SCORE", "nan"),
    ("MOC_ASSIGNER_ID", ""), ("MOC_ASSIGNER_ID", "x" * 65), ("MOC_SUGGEST_TIMEOUT_S", "mười"),
])
def test_bad_suggestion_settings_stop_the_service(name, value):
    with pytest.raises(ConfigError):
        Settings.from_env({**ENV, name: value})


def test_app_runs_the_advisor_only_when_polling(hasura, flowable, files, library):
    app = create_app(Settings.from_env({**ENV, "MOC_SUGGEST_POLL_INTERVAL_S": "0"}), hasura=hasura,  # type: ignore[arg-type]
                     flowable=flowable, files=files, directory=NoDirectory())  # type: ignore[arg-type]
    assert app.state.advisor is None
    app = create_app(Settings.from_env({**ENV, "MOC_SUGGEST_POLL_INTERVAL_S": "0.05"}), hasura=hasura,  # type: ignore[arg-type]
                     flowable=flowable, files=files, directory=NoDirectory())  # type: ignore[arg-type]
    assert isinstance(app.state.advisor, Advisor)
    files.similar_answer = answer((P1, 0.9))
    goi_y(flowable)
    with TestClient(app):
        deadline = time.monotonic() + 5
        while "g1" not in flowable.jobs_done and time.monotonic() < deadline:
            time.sleep(0.02)
    assert flowable.jobs_done == ["g1"] and hasura.suggestions[DOC]["status"] == "suggested"


def files_client(handler) -> FilesClient:
    def keycloak(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"access_token": "tok-svc", "expires_in": 300})

    token = ServiceToken("http://keycloak:8080", "moc", "svc-workflow", "s", transport=httpx2.MockTransport(keycloak))
    return FilesClient("http://svc-files:8000", token, transport=httpx2.MockTransport(handler))


def call_similar(handler, document_id: str = DOC.upper()):
    async def go():
        client = files_client(handler)
        try:
            return await client.similar(TENANT, document_id)
        finally:
            await client.aclose()

    return run(go())


def test_similar_posts_the_contract_body_with_the_service_token():
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"document_id": DOC, "hits": [{"document_id": P1, "score": 0.81}],
                                          "terms": 7, "semantic": False, "duration_ms": 41})

    assert call_similar(handler)["hits"] == [{"document_id": P1, "score": 0.81}]
    (request,) = seen
    assert request.method == "POST" and request.url.path == "/internal/similar-documents"
    assert request.headers["authorization"] == "Bearer tok-svc"
    assert json.loads(request.content) == {"tenant_id": str(TENANT), "document_id": DOC, "limit": 15}


@pytest.mark.parametrize(("status", "body", "code"), [
    (409, {"detail": {"code": "restricted", "message": "Văn bản hạn chế"}}, "restricted"),
    (503, {"detail": {"code": "assistant_disabled", "message": "Trợ lý đang tắt"}}, "assistant_disabled"),
    (422, {"detail": [{"loc": ["body", "limit"], "msg": "…"}]}, None),
    (500, "không phải JSON", None),
])
def test_similar_errors_carry_status_and_code(status, body, code):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if isinstance(body, str):
            return httpx2.Response(status, text=body)
        return httpx2.Response(status, json=body)

    with pytest.raises(FilesError) as err:
        call_similar(handler)
    assert (err.value.status, err.value.code) == (status, code)


def test_similar_unreachable_has_no_status():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("svc-files:8000 refused", request=request)

    with pytest.raises(FilesError) as err:
        call_similar(handler)
    assert (err.value.status, err.value.code) == (None, None)


def keycloak_issuing(tokens: list[str]):
    """Keycloak giả: mỗi lần lấy token trả token kế tiếp trong danh sách."""
    left = iter(tokens)

    def keycloak(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"access_token": next(left), "expires_in": 300})

    return httpx2.MockTransport(keycloak)


def test_similar_retries_once_with_a_new_token_after_401():
    # token hết hạn sớm hơn ServiceToken tính (đồng hồ bị chỉnh, khóa Keycloak đổi): svc-files trả 401 — chưa làm gì —
    # nên bỏ token, lấy token mới, gửi lại đúng một lần, không ghi dòng failed vĩnh viễn cho văn bản
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["authorization"])
        if request.headers["authorization"] == "Bearer tok-cu":
            return httpx2.Response(401, json={"detail": {"code": "invalid_token", "message": "Token hết hạn"}})
        return httpx2.Response(200, json={"document_id": DOC, "hits": [], "terms": 7, "semantic": False,
                                          "duration_ms": 9})

    async def go():
        token = ServiceToken("http://keycloak:8080", "moc", "svc-workflow", "s",
                             transport=keycloak_issuing(["tok-cu", "tok-moi"]))
        client = FilesClient("http://svc-files:8000", token, transport=httpx2.MockTransport(handler))
        try:
            return await client.similar(TENANT, DOC)
        finally:
            await client.aclose()

    assert run(go())["hits"] == []
    assert seen == ["Bearer tok-cu", "Bearer tok-moi"]


def test_similar_gives_up_after_the_second_401():
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["authorization"])
        return httpx2.Response(401, json={"detail": {"code": "invalid_token", "message": "Token hết hạn"}})

    async def go():
        token = ServiceToken("http://keycloak:8080", "moc", "svc-workflow", "s",
                             transport=keycloak_issuing(["tok-1", "tok-2", "tok-3"]))
        client = FilesClient("http://svc-files:8000", token, transport=httpx2.MockTransport(handler))
        try:
            return await client.similar(TENANT, DOC)
        finally:
            await client.aclose()

    with pytest.raises(FilesError) as err:
        run(go())
    assert (err.value.status, err.value.code) == (401, "invalid_token") and seen == ["Bearer tok-1", "Bearer tok-2"]


def test_concurrent_calls_after_401_fetch_one_new_token():
    # mười lời gọi cùng gặp 401 với token cũ: chỉ một lần hỏi Keycloak token mới; lời gọi đến sau không bỏ nhầm token
    # mới mà lời gọi khác vừa lấy
    asked = []

    def keycloak(request: httpx2.Request) -> httpx2.Response:
        asked.append(len(asked))
        return httpx2.Response(200, json={"access_token": f"tok-{len(asked)}", "expires_in": 300})

    async def files(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(0)
        if request.headers["authorization"] == "Bearer tok-1":
            return httpx2.Response(401, json={"detail": {"code": "invalid_token", "message": "Token hết hạn"}})
        return httpx2.Response(200, json={"document_id": DOC, "hits": [], "terms": 7, "semantic": False,
                                          "duration_ms": 9})

    async def go():
        token = ServiceToken("http://keycloak:8080", "moc", "svc-workflow", "s",
                             transport=httpx2.MockTransport(keycloak))
        client = FilesClient("http://svc-files:8000", token, transport=httpx2.MockTransport(files))
        try:
            return await asyncio.gather(*(client.similar(TENANT, DOC) for _ in range(10)))
        finally:
            await client.aclose()

    assert [r["hits"] for r in run(go())] == [[]] * 10 and len(asked) == 2


def test_issue_retry_keeps_the_request_id():
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append((request.headers["authorization"], request.headers.get("x-request-id")))
        if len(seen) == 1:
            return httpx2.Response(401, json={"detail": {"code": "invalid_token", "message": "Token hết hạn"}})
        return httpx2.Response(201, json={"file_id": "f-1", "sha256": "0" * 64, "size_bytes": 10})

    async def go():
        token = ServiceToken("http://keycloak:8080", "moc", "svc-workflow", "s",
                             transport=keycloak_issuing(["tok-cu", "tok-moi"]))
        client = FilesClient("http://svc-files:8000", token, transport=httpx2.MockTransport(handler))
        try:
            return await client.issue(Actor("u-vt", TENANT, "clerk", None, "rid-123"), DOC)
        finally:
            await client.aclose()

    assert run(go())["file_id"] == "f-1"
    assert seen == [("Bearer tok-cu", "rid-123"), ("Bearer tok-moi", "rid-123")]


def test_service_token_expiry_follows_the_wall_clock(monkeypatch):
    # máy ngủ hay VM tạm dừng: time.monotonic đứng yên còn giờ thật (và exp của token) vẫn chạy — 300 giây giờ thật sau
    # phải lấy token mới dù monotonic chưa tới hạn
    now = [time.time()]
    monkeypatch.setattr(time, "time", lambda: now[0])

    async def go():
        token = ServiceToken("http://keycloak:8080", "moc", "svc-workflow", "s",
                             transport=keycloak_issuing(["tok-1", "tok-2"]))
        try:
            got = [await token.get()]
            now[0] += 200
            got.append(await token.get())      # còn hạn (trừ hao 30 giây: tới 270 giây)
            now[0] += 100
            got.append(await token.get())      # 300 giây giờ thật: token cũ đã hết hạn
            return got
        finally:
            await token.aclose()

    assert run(go()) == ["tok-1", "tok-1", "tok-2"]


@pytest.mark.parametrize("request_id", ["goi-y:g1", ""])
def test_as_agent_sends_the_agent_session(request_id):
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"data": {"ok": True}})

    async def go():
        client = HasuraClient("http://hasura:8080", "khoa", transport=httpx2.MockTransport(handler))
        try:
            return await client.as_agent(TENANT, "moc-assigner", "query X { x }", request_id=request_id)
        finally:
            await client.aclose()

    assert run(go()) == {"ok": True}
    headers = seen[0].headers
    assert (headers["x-hasura-role"], headers["x-hasura-user-id"], headers["x-hasura-tenant-id"],
            headers["x-hasura-admin-secret"]) == ("agent", "moc-assigner", str(TENANT), "khoa")
    assert headers.get("x-hasura-request-id") == (request_id or None)
    assert "x-hasura-department-id" not in headers
