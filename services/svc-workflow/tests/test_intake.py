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

"""Tiếp nhận văn bản đến — lớp kiểm thứ hai của poka-yoke (F2.2), chạy trên bộ ca thử dùng chung với form và CSDL."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import NEW, SCHEMAS, TENANT, actor
from svc_workflow.app import create_app
from svc_workflow.config import ConfigError, Settings
from svc_workflow.schemas import FormSchema, SchemaFileError, today_vn
from svc_workflow.workflow import INTAKE_COLUMNS, WorkflowError

CASES = json.loads((SCHEMAS / "van-ban-den.cases.json").read_text(encoding="utf-8"))
INTAKE = FormSchema.load(SCHEMAS / "van-ban-den.json")
TODAY = date(2026, 10, 19)
F1, F2 = "0b7c6f1e-3a52-4f0e-9a51-2d4f3c6e8a10", "5d1e2c3b-7a8f-4e6d-b1c2-9f0a8e7d6c5b"


def value(v: Any, today: date) -> Any:
    if isinstance(v, dict) and "$repeat" in v:
        return v["$repeat"] * v["times"]
    if isinstance(v, dict) and "$nfd" in v:
        return unicodedata.normalize("NFD", v["$nfd"])
    if isinstance(v, str) and (m := re.fullmatch(r"today([+-]\d+)?", v)):
        return (today + timedelta(days=int(m.group(1) or 0))).isoformat()
    return v


def build(case: dict[str, Any], today: date = TODAY) -> dict[str, Any]:
    """Một ca trong schemas/van-ban-den.cases.json → dữ liệu gửi đi (cách đọc ghi ở $comment của tệp)."""
    data = {k: value(v, today) for k, v in CASES["base"].items()}
    data.update({k: value(v, today) for k, v in case.get("set", {}).items()})
    for k in case.get("unset", []):
        data.pop(k, None)
    return data


def run(coro):
    return asyncio.run(coro)


# --- schema dùng chung: cùng kết quả với form (apps/office/tests/forms.test.ts) ---------------------------


@pytest.mark.parametrize("case", CASES["valid"], ids=lambda c: c["name"])
def test_valid_cases_pass(case):
    assert INTAKE.errors(build(case), TODAY) == {}


@pytest.mark.parametrize("case", CASES["invalid"], ids=lambda c: c["name"])
def test_invalid_cases_name_the_field_and_rule(case):
    assert INTAKE.errors(build(case), TODAY) == case["error"]


def test_not_an_object_is_a_type_error():
    assert INTAKE.errors(["CV"], TODAY) == {"": "type"}
    assert INTAKE.errors(None, TODAY) == {"": "type"}


def test_default_today_is_the_vietnam_date():
    """Máy chủ chạy theo UTC: từ 0 giờ đến 7 giờ sáng ở Việt Nam, ngày UTC vẫn là hôm trước."""
    vn = today_vn()
    assert INTAKE.errors({**build({}, vn), "issued_on": vn.isoformat()}) == {}
    assert INTAKE.errors({**build({}, vn), "issued_on": (vn + timedelta(days=1)).isoformat(), "due_on": None}) == {
        "issued_on": "x-moc-date"}


def test_broken_schema_file_is_reported(tmp_path: Path):
    bad = tmp_path / "van-ban-den.json"
    bad.write_text('{"type": "khong-co-kieu-nay"}', encoding="utf-8")
    with pytest.raises(SchemaFileError, match="Schema không hợp lệ"):
        FormSchema.load(bad)
    with pytest.raises(SchemaFileError, match="Không đọc được"):
        FormSchema.load(tmp_path / "khong-co.json")


# --- Action receiveIncoming ----------------------------------------------------------------------------


@pytest.fixture
def clerk():
    return actor("clerk", "u-clerk")


@pytest.fixture
def uploaded(hasura):
    hasura.uploads.update({F1: "u-clerk", F2: "u-clerk"})
    return hasura


def receive(workflow, who, data):
    return run(workflow.receive_incoming(who, data))


def test_receive_writes_the_document_with_server_side_columns(workflow, uploaded, clerk):
    data = build({"set": {"file_ids": [F1, F2]}}, today_vn())
    assert receive(workflow, clerk, data) == {"document_id": NEW}
    (op, variables, who), = uploaded.writes
    doc = variables["doc"]
    assert op == "TiepNhan" and who == clerk
    assert (doc["direction"], doc["status"], doc["created_by"]) == ("in", "received", "u-clerk")
    assert doc["files"]["data"] == [{"file_id": F1, "role": "main", "added_by": "u-clerk"},
                                    {"file_id": F2, "role": "attachment", "added_by": "u-clerk"}]
    assert {k: doc[k] for k in ("symbol", "issuer_name", "summary", "urgency")} == {
        k: data[k] for k in ("symbol", "issuer_name", "summary", "urgency")}


def test_receive_without_optional_fields_leaves_database_defaults(workflow, uploaded, clerk):
    receive(workflow, clerk, build({"unset": ["urgency", "due_on", "restricted", "file_ids"]}, today_vn()))
    doc = uploaded.writes[0][1]["doc"]
    assert "urgency" not in doc and "restricted" not in doc and doc["files"] == {"data": []}


@pytest.mark.parametrize("case", CASES["invalid"], ids=lambda c: c["name"])
def test_receive_rejects_every_invalid_case_before_touching_the_database(workflow, uploaded, clerk, case):
    with pytest.raises(WorkflowError) as err:
        receive(workflow, clerk, build(case, today_vn()))
    assert (err.value.status, err.value.code, err.value.fields) == (400, "invalid", case["error"])
    assert uploaded.writes == [] and uploaded.lookups == []


def test_unknown_document_type(workflow, uploaded, clerk):
    with pytest.raises(WorkflowError) as err:
        receive(workflow, clerk, build({"set": {"type_code": "XYZ"}}, today_vn()))
    assert err.value.fields == {"type_code": "unknown"} and uploaded.writes == []


def test_files_must_be_uploaded_by_the_same_clerk(workflow, uploaded, clerk):
    uploaded.uploads[F2] = "u-clerk-khac"
    with pytest.raises(WorkflowError) as err:
        receive(workflow, clerk, build({"set": {"file_ids": [F1, F2]}}, today_vn()))
    assert err.value.fields == {"file_ids": "unknown"} and uploaded.writes == []


def test_duplicate_is_refused_even_with_different_letter_case(workflow, uploaded, clerk):
    data = build({}, today_vn())
    receive(workflow, clerk, data)
    with pytest.raises(WorkflowError) as err:
        receive(workflow, clerk, {**data, "issuer_name": data["issuer_name"].upper(), "file_ids": []})
    assert (err.value.status, err.value.code, err.value.fields) == (409, "duplicate", {"symbol": "duplicate"})
    assert len(uploaded.writes) == 1


def test_like_wildcards_in_issuer_are_matched_literally(workflow, uploaded, clerk):
    receive(workflow, clerk, build({"set": {"issuer_name": "Sở 50%_A\\B"}}, today_vn()))
    assert uploaded.lookups[0]["issuer"] == "Sở 50\\%\\_A\\\\B"


def test_race_caught_by_the_index_is_reported_like_a_duplicate(workflow, uploaded, clerk):
    """Hai văn thư cùng lưu một văn bản: cả hai qua bước tra trùng, chỉ index của CSDL chặn được người sau."""
    uploaded.fail_writes = 'Uniqueness violation. duplicate key value violates unique constraint "documents_in_dedup"'
    with pytest.raises(WorkflowError) as err:
        receive(workflow, clerk, build({}, today_vn()))
    assert (err.value.status, err.value.code, err.value.fields) == (409, "duplicate", {"symbol": "duplicate"})
    assert "đã được tiếp nhận" in err.value.message


def test_other_database_refusal_becomes_a_vietnamese_message(workflow, uploaded, clerk):
    uploaded.fail_writes = 'Check constraint violation. new row … violates check constraint "documents_in_dates"'
    with pytest.raises(WorkflowError) as err:
        receive(workflow, clerk, build({}, today_vn()))
    assert err.value.status == 409 and "Ngày ban hành" in err.value.message


def test_only_schema_fields_become_columns():
    """Mọi thuộc tính của schema (trừ file_ids) là cột được ghi, và chỉ những cột đó."""
    assert set(INTAKE.schema["properties"]) - {"file_ids"} == set(INTAKE_COLUMNS)


# --- lớp HTTP --------------------------------------------------------------------------------------------

ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": "bi-mat-action", "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_DIRECTORY_SYNC_INTERVAL_S": "0", "MOC_RECONCILE_INTERVAL_S": "0",
    "MOC_PROCESSES_DIR": "/khong-co", "MOC_SCHEMAS_DIR": str(SCHEMAS),
}


class NoDirectory:
    async def aclose(self) -> None: ...


def call(client, role: str, data: Any):
    return client.post("/actions/receiveIncoming", headers={"X-Moc-Action-Secret": "bi-mat-action"}, json={
        "action": {"name": "receiveIncoming"}, "input": {"data": data},
        "session_variables": {"x-hasura-role": role, "x-hasura-user-id": "u-clerk", "x-hasura-tenant-id": str(TENANT)},
    })


def test_http_returns_field_errors_for_the_form(hasura, flowable):
    app = create_app(Settings.from_env(ENV), hasura=hasura, flowable=flowable, directory=NoDirectory())  # type: ignore[arg-type]
    hasura.uploads[F1] = "u-clerk"
    with TestClient(app) as client:
        assert call(client, "staff", build({}, today_vn())).status_code == 403
        r = call(client, "clerk", build({"set": {"symbol": " 15/UBND"}, "unset": ["summary"]}, today_vn()))
        assert r.status_code == 400
        assert r.json()["extensions"] == {"code": "invalid", "fields": {"symbol": "not", "summary": "required"}}
        assert call(client, "clerk", None).json()["extensions"]["fields"] == {"": "type"}
        r = call(client, "clerk", build({}, today_vn()))
        assert r.status_code == 200 and r.json() == {"document_id": NEW}


def test_service_does_not_start_without_the_schema(hasura, flowable):
    with pytest.raises(ConfigError, match="MOC_SCHEMAS_DIR"):
        create_app(Settings.from_env({**ENV, "MOC_SCHEMAS_DIR": "/khong-co"}), hasura=hasura, flowable=flowable,
                   directory=NoDirectory())  # type: ignore[arg-type]
