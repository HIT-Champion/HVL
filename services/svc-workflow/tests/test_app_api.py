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

"""API quy trình cho ứng dụng ``/api/workflow/{app}/…`` (apps/api.py): token của đúng client app-<tên>, kiểm form,
biến hệ thống từ token, ai thấy việc nào, gỡ ứng dụng — với Flowable giả và token ký RSA thật."""

from __future__ import annotations

import asyncio
import copy
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_fakes import APP, BPMN, DON, DUYET, AppFlowable, bundle_zip, form_bytes
from conftest import DEPT_DT, DEPT_KTPM, OTHER, TENANT
from svc_workflow.apps import deploy
from svc_workflow.apps.api import AppWorkflow, rest_variables
from svc_workflow.apps.auth import HASURA_CLAIMS, AppUser, AuthError, TokenVerifier, default_role
from svc_workflow.apps.bundle import check_bundle
from svc_workflow.config import Settings

ISSUER = "https://signet.example/realms/moc"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
API = f"/api/workflow/{APP}"
REQ = {"loai": "phep-nam", "tuNgay": "2026-11-02", "denNgay": "2026-11-04", "lyDo": "Về quê"}


@dataclass
class _Key:
    key: object


class StaticKeys:
    """Thay PyJWKClient: đúng một khóa công khai, không gọi mạng."""

    def __init__(self, key: object) -> None:
        self._key = _Key(key)

    def get_signing_key_from_jwt(self, token: str) -> _Key:
        return self._key


def token(sub: str = "u-staff", role: str = "staff", *, tenant: uuid.UUID | None = TENANT,
          dept: uuid.UUID | None = DEPT_DT, azp: str = f"app-{APP}", key: Any = KEY, ttl: int = 300,
          **extra: Any) -> str:
    now = int(time.time())
    ns: dict[str, Any] = {"x-hasura-user-id": sub, "x-hasura-allowed-roles": [role], "x-hasura-default-role": role}
    if tenant is not None:
        ns["x-hasura-tenant-id"] = str(tenant)
    if dept is not None:
        ns["x-hasura-department-id"] = str(dept)
    claims = {"iss": ISSUER, "sub": sub, "iat": now, "exp": now + ttl, "azp": azp, HASURA_CLAIMS: ns, **extra}
    return jwt.encode(claims, key, algorithm="RS256")


def auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


STAFF = auth(token())
MANAGER = auth(token("u-manager", "manager"))
OTHER_MANAGER = auth(token("u-manager-ktpm", "manager", dept=DEPT_KTPM))
DIRECTOR = auth(token("u-director", "director", dept=None))
OTHER_TENANT = auth(token("u-staff-b", tenant=OTHER))


def install(fl: AppFlowable, **kwargs: Any) -> None:
    asyncio.run(deploy.install(fl, check_bundle(APP, bundle_zip(**kwargs))))


@pytest.fixture
def fl() -> AppFlowable:
    f = AppFlowable()
    install(f)
    return f


@pytest.fixture
def part(fl) -> AppWorkflow:
    return AppWorkflow(fl, TokenVerifier(ISSUER, "unused", keys=StaticKeys(KEY.public_key())))


@pytest.fixture
def client(part) -> TestClient:
    app = FastAPI()
    part.install(app)
    return TestClient(app)


def start(client: TestClient, data: dict[str, Any] | None = None, headers: dict[str, str] = STAFF) -> str:
    r = client.post(f"{API}/processes/{APP}.don", json={"data": data or REQ}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- token --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("headers, status, code", [
    ({}, 401, "missing_token"),
    (auth("khong-phai-jwt"), 401, "invalid_token"),
    (auth(token(ttl=-120)), 401, "invalid_token"),
    (auth(token(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))), 401, "invalid_token"),
    (auth(token(iss="https://khac.example/realms/moc")), 401, "invalid_token"),
    (auth(token(azp="app-office")), 403, "wrong_client"),
    (auth(token(azp="moc-cli")), 403, "wrong_client"),
    (auth(token(azp="app-nghi-phep-khac")), 403, "wrong_client"),
    (auth(token(tenant=None)), 403, "no_tenant"),
])
def test_only_a_valid_token_of_the_apps_own_client_gets_in(client, headers, status, code):
    for method, path in (("GET", "/processes"), ("GET", "/tasks"), ("GET", f"/forms/{APP}.don"),
                         ("POST", f"/processes/{APP}.don"), ("POST", "/tasks/t-1")):
        r = client.request(method, API + path, headers=headers, json={"data": REQ})
        assert r.status_code == status and r.json()["detail"]["code"] == code, (method, path, r.text)
    if status == 401:
        assert r.headers["www-authenticate"] == "Bearer"


def test_token_of_one_app_does_not_open_another(client):
    r = client.get("/api/workflow/khac/processes", headers=STAFF)
    assert r.status_code == 403 and "app-khac" in r.json()["detail"]["message"]


def test_bad_app_name_is_404(client):
    assert client.get("/api/workflow/Nghi_Phep/tasks", headers=STAFF).status_code == 404


SECRETS = {"HASURA_ADMIN_SECRET": "x", "MOC_ACTION_SECRET": "x", "FLOWABLE_ADMIN_PASSWORD": "x",
           "MOC_DIRECTORY_CLIENT_SECRET": "x"}


def test_without_issuer_the_api_says_not_configured(fl):
    settings = Settings.from_env({**SECRETS, "MOC_PUBLIC_URL": ""})
    part = AppWorkflow.build(settings, fl, env={})
    assert part.verifier is None
    app = FastAPI()
    part.install(app)
    r = TestClient(app).get(f"{API}/tasks", headers=STAFF)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "not_configured"


def test_issuer_and_jwks_follow_the_compose_oidc_settings(fl):
    settings = Settings.from_env({**SECRETS, "MOC_PUBLIC_URL": "https://signet.example", "MOC_REALM": "moc"})
    part = AppWorkflow.build(settings, fl, env={})
    assert part.verifier is not None and part.verifier.issuer == "https://signet.example/realms/moc"
    part = AppWorkflow.build(settings, fl, env={"MOC_OIDC_ISSUER": "https://idp.example/realms/x"})
    assert part.verifier.issuer == "https://idp.example/realms/x"
    assert part.jobs() == [] and asyncio.run(part.aclose()) is None


def test_user_comes_from_hasura_claims():
    verifier = TokenVerifier(ISSUER, "unused", keys=StaticKeys(KEY.public_key()))
    user = verifier.verify(token("u-manager", "manager"), APP)
    assert user == AppUser("u-manager", TENANT, "manager", DEPT_DT, f"app-{APP}")
    assert user.groups == [f"t:{TENANT}:manager", f"t:{TENANT}:d:{DEPT_DT}:manager"]
    assert verifier.verify(token(dept=None, role="staff"), APP).groups == [f"t:{TENANT}:staff"]
    bad_dept = verifier.verify(token(dept=None, **{HASURA_CLAIMS: {
        "x-hasura-tenant-id": str(TENANT), "x-hasura-department-id": "khong-phai-uuid"}}), APP)
    assert bad_dept.department_id is None and bad_dept.role == "" and bad_dept.groups == []
    assert default_role("director", ("staff",)) == "" and default_role(None, ("staff",)) == "staff"


def test_unreachable_jwks_is_503():
    class Down:
        def get_signing_key_from_jwt(self, token: str) -> Any:
            raise jwt.PyJWKClientConnectionError("down")

    with pytest.raises(AuthError) as e:
        TokenVerifier(ISSUER, "unused", keys=Down()).verify(token(), APP)
    assert e.value.status == 503 and e.value.code == "jwks_unavailable"


# --- form ---------------------------------------------------------------------------------------------------


def test_form_is_the_schema_the_manifest_declared(client):
    r = client.get(f"{API}/forms/{APP}.don", headers=STAFF)
    assert r.status_code == 200 and r.json() == DON
    assert client.get(f"{API}/forms/{APP}.duyet", headers=STAFF).json() == DUYET


@pytest.mark.parametrize("form_key", [f"{APP}.khong-co", "van-ban-den.don", "vbden.chiDao"])
def test_unknown_or_foreign_form_is_404(client, form_key):
    r = client.get(f"{API}/forms/{form_key}", headers=STAFF)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "form_not_found"


def test_form_resources_are_read_once_per_deployment(client, fl):
    calls = []
    real = fl.resource

    async def counting(dep: str, name: str) -> bytes | None:
        calls.append(name)
        return await real(dep, name)

    fl.resource = counting
    for _ in range(3):
        client.get(f"{API}/forms/{APP}.don", headers=STAFF)
    assert calls == ["moc-app.json", f"{APP}.don.json"]


# --- bắt đầu quy trình -------------------------------------------------------------------------------------


def test_start_writes_typed_form_data_and_system_variables_from_the_token(client, fl):
    pid = start(client, {**REQ, "soNgay": 3, "khanCap": True})
    definition, variables = fl.started[0]
    assert definition == f"{APP}.don:1:dep-1" and pid.startswith("proc-")
    assert variables == [
        {"name": "loai", "type": "string", "value": "phep-nam"},
        {"name": "tuNgay", "type": "string", "value": "2026-11-02"},
        {"name": "denNgay", "type": "string", "value": "2026-11-04"},
        {"name": "soNgay", "type": "long", "value": 3},
        {"name": "khanCap", "type": "boolean", "value": True},
        {"name": "lyDo", "type": "string", "value": "Về quê"},
        {"name": "tenantId", "type": "string", "value": str(TENANT)},
        {"name": "departmentId", "type": "string", "value": str(DEPT_DT)},
        {"name": "initiator", "type": "string", "value": "u-staff"},
    ]


def test_user_without_department_starts_with_an_empty_department(client, fl):
    start(client, headers=DIRECTOR)
    assert {"name": "departmentId", "type": "string", "value": ""} in fl.started[0][1]


@pytest.mark.parametrize("data, errors", [
    ({**REQ, "tuNgay": "2026-11-04", "denNgay": "2026-11-02"}, {"denNgay": "x-moc-range"}),
    ({**REQ, "loai": "nghi-mat"}, {"loai": "enum"}),
    ({**REQ, "tenantId": str(OTHER)}, {"tenantId": "additionalProperties"}),
    ({**REQ, "initiator": "u-director"}, {"initiator": "additionalProperties"}),
    ({**REQ, "soNgay": 1.5, "khanCap": "co"}, {"soNgay": "type", "khanCap": "type"}),
    ({}, {"loai": "required", "tuNgay": "required", "denNgay": "required"}),
    ("khong-phai-doi-tuong", {"": "type"}),
])
def test_invalid_data_is_422_per_field_and_nothing_starts(client, fl, data, errors):
    r = client.post(f"{API}/processes/{APP}.don", json={"data": data}, headers=STAFF)
    assert r.status_code == 422 and r.json() == {"errors": errors}
    assert fl.started == []


@pytest.mark.parametrize("body", [b"khong-phai-json", b"[1, 2]"])
def test_body_must_be_a_json_object(client, body):
    r = client.post(f"{API}/processes/{APP}.don", content=body, headers={**STAFF, "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_request"


@pytest.mark.parametrize("key", [f"{APP}.khong-co", "van-ban-den", f"{APP}.duyet"])
def test_unknown_or_foreign_process_is_404(client, fl, key):
    r = client.post(f"{API}/processes/{key}", json={"data": REQ}, headers=STAFF)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "process_not_found"
    assert fl.started == []


def test_flowable_down_is_503(client, fl):
    fl.down = True
    for r in (client.post(f"{API}/processes/{APP}.don", json={"data": REQ}, headers=STAFF),
              client.get(f"{API}/processes", headers=STAFF), client.get(f"{API}/tasks", headers=MANAGER),
              client.get(f"{API}/forms/{APP}.don", headers=STAFF)):
        assert r.status_code == 503 and r.json()["detail"]["code"] == "workflow_unavailable"


def test_new_requests_use_the_latest_deployment(client, fl):
    install(fl, bpmn=BPMN.replace('flowable:dueDate="P2D"', 'flowable:dueDate="P3D"'))
    start(client)
    assert fl.started[0][0] == f"{APP}.don:2:dep-2"


# --- đơn của tôi, việc của tôi -----------------------------------------------------------------------------


def test_my_processes_hold_the_request_then_the_decision(client, fl):
    pid = start(client)
    start(client, headers=OTHER_TENANT)
    start(client, headers=MANAGER)
    r = client.get(f"{API}/processes", headers=STAFF)
    assert r.status_code == 200
    assert r.json() == [{"id": pid, "processKey": f"{APP}.don", "startedAt": fl.instances[pid]["startTime"],
                         "endedAt": None, "data": REQ}]
    fl.add_task("t-1", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])
    assert client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y", "ghiChu": "Được"}},
                       headers=MANAGER).status_code == 204
    fl.instances[pid]["endTime"] = "2026-10-26T11:00:00.000+07:00"
    mine = client.get(f"{API}/processes", headers=STAFF).json()
    assert mine[0]["endedAt"] == "2026-10-26T11:00:00.000+07:00"
    assert mine[0]["data"] == {**REQ, "quyetDinh": "dong-y", "ghiChu": "Được"}
    query = next(q for q in fl.queries if "processDefinitionKey" in q)
    assert query["processDefinitionKey"] == f"{APP}.don"
    assert {"name": "initiator", "value": "u-staff", "operation": "equals", "type": "string"} in query["variables"]


def test_tasks_show_the_request_to_the_managers_of_the_senders_department_only(client, fl):
    pid = start(client)
    fl.add_task("t-1", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"], due="2026-10-28T09:30:00.000+07:00")
    tasks = client.get(f"{API}/tasks", headers=MANAGER).json()
    assert tasks == [{"id": "t-1", "name": "Duyệt đơn nghỉ", "formKey": f"{APP}.duyet", "processKey": f"{APP}.don",
                      "processId": pid, "createdAt": "2026-10-26T09:30:00.000+07:00",
                      "dueAt": "2026-10-28T09:30:00.000+07:00", "data": REQ}]
    for who in (OTHER_MANAGER, STAFF, DIRECTOR, OTHER_TENANT):
        assert client.get(f"{API}/tasks", headers=who).json() == []
    assert all(q["processDefinitionKeyLike"] == f"{APP}.%" for q in fl.queries)


def test_assigned_task_is_seen_by_the_assignee(client, fl):
    pid = start(client)
    fl.add_task("t-xem", pid, assignee="u-staff")
    assert [t["id"] for t in client.get(f"{API}/tasks", headers=STAFF).json()] == ["t-xem"]
    assert client.get(f"{API}/tasks", headers=MANAGER).json() == []


def test_task_of_another_tenant_with_the_same_group_name_is_hidden(client, fl):
    pid = start(client, headers=OTHER_TENANT)
    fl.add_task("t-b", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])      # nhóm sai thuê ước: vẫn không lộ
    assert client.get(f"{API}/tasks", headers=MANAGER).json() == []
    r = client.post(f"{API}/tasks/t-b", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER)
    assert r.status_code == 404


# --- hoàn thành việc ---------------------------------------------------------------------------------------


@pytest.fixture
def pending(client, fl) -> str:
    pid = start(client)
    fl.add_task("t-1", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])
    return pid


def test_complete_claims_then_completes_with_typed_variables(client, fl, pending):
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "tu-choi", "ghiChu": "Đủ người nghỉ"}},
                    headers=MANAGER)
    assert r.status_code == 204 and r.content == b""
    assert fl.claims == [("t-1", "u-manager")]
    assert fl.completed == [("t-1", [{"name": "quyetDinh", "type": "string", "value": "tu-choi"},
                                     {"name": "ghiChu", "type": "string", "value": "Đủ người nghỉ"}])]


@pytest.mark.parametrize("data, errors", [
    ({"quyetDinh": "Đồng ý"}, {"quyetDinh": "enum"}),
    ({"quyetDinh": "dong-y", "initiator": "u-manager"}, {"initiator": "additionalProperties"}),
    ({"quyetDinh": "dong-y", "ghiChu": None}, {"ghiChu": "type"}),
])
def test_invalid_decision_is_422_and_the_task_stays(client, fl, pending, data, errors):
    r = client.post(f"{API}/tasks/t-1", json={"data": data}, headers=MANAGER)
    assert r.status_code == 422 and r.json() == {"errors": errors}
    assert fl.claims == [] and fl.completed == []


@pytest.mark.parametrize("who", [OTHER_MANAGER, STAFF, DIRECTOR, OTHER_TENANT])
def test_people_outside_the_group_cannot_complete(client, fl, pending, who):
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y"}}, headers=who)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "task_not_found"
    assert fl.claims == [] and fl.completed == []


def test_task_taken_by_someone_else_is_409(client, fl, pending):
    fl.claim_conflict = True
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "task_taken"


def test_failed_completion_gives_the_task_back(client, fl, pending):
    fl.gone_on_complete = True
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER)
    assert r.status_code == 404
    assert fl.claims == [("t-1", "u-manager"), ("t-1", None)]


def test_unknown_task_is_404(client):
    assert client.post(f"{API}/tasks/khong-co", json={"data": {"quyetDinh": "dong-y"}},
                       headers=MANAGER).status_code == 404


def test_office_task_is_not_reachable_through_the_app_api(client, fl):
    fl.instances["p-office"] = {"id": "p-office", "processDefinitionId": "van-ban-den:1:x", "endTime": None,
                                "startTime": "x", "variables": {"tenantId": str(TENANT)}}
    fl.add_task("t-office", "p-office", "vbden.chiDao", groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])
    assert client.get(f"{API}/tasks", headers=MANAGER).json() == []
    r = client.post(f"{API}/tasks/t-office", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER)
    assert r.status_code == 404 and fl.claims == []


def test_task_of_an_older_version_is_checked_with_that_versions_form(client, fl, pending):
    stricter = copy.deepcopy(DUYET)
    stricter["properties"]["quyetDinh"]["enum"] = ["dong-y", "tu-choi", "can-bo-sung"]
    install(fl, duyet=stricter)
    assert client.get(f"{API}/forms/{APP}.duyet", headers=STAFF).json() == stricter
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "can-bo-sung"}}, headers=MANAGER)
    assert r.status_code == 422 and r.json() == {"errors": {"quyetDinh": "enum"}}


# --- gỡ, cài lại ---------------------------------------------------------------------------------------------


def test_removed_app_answers_404_but_history_stays_in_flowable(client, fl, pending):
    asyncio.run(deploy.remove(fl, APP))
    for method, path in (("GET", "/processes"), ("GET", "/tasks"), ("GET", f"/forms/{APP}.don"),
                         ("POST", f"/processes/{APP}.don"), ("POST", "/tasks/t-1")):
        r = client.request(method, API + path, headers=MANAGER, json={"data": {"quyetDinh": "dong-y"}})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "app_not_installed", (method, path)
    assert pending in fl.instances and fl.completed == []
    install(fl)                                          # cài lại cùng bản: bật lại, đơn đang dở làm tiếp
    assert len(fl.deployed) == 1
    assert client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER).status_code == 204


def test_app_never_installed_is_404():
    app = FastAPI()
    AppWorkflow(AppFlowable(), TokenVerifier(ISSUER, "unused", keys=StaticKeys(KEY.public_key()))).install(app)
    r = TestClient(app).get(f"{API}/forms/{APP}.don", headers=STAFF)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "app_not_installed"


def test_rest_variables_keep_types():
    assert rest_variables({"a": True, "b": 2, "c": 1.5, "d": "x"}) == [
        {"name": "a", "type": "boolean", "value": True}, {"name": "b", "type": "long", "value": 2},
        {"name": "c", "type": "double", "value": 1.5}, {"name": "d", "type": "string", "value": "x"}]


def test_openapi_lists_the_five_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert sorted(paths) == [f"/api/workflow/{{app}}/{p}" for p in (
        "forms/{form_key}", "processes", "processes/{process_key}", "tasks", "tasks/{task_id}")]
    assert form_bytes(DON)                               # mẫu dùng chung còn đọc được
