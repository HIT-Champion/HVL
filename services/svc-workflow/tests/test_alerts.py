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

"""Cảnh báo vận hành (alerts.py, #284): đọc webhook của Alertmanager, token, gửi quản trị mọi đơn vị, chống trùng.

Đường thật Prometheus → Alertmanager → svc-workflow → chuông: ``make demo-canh-bao`` (bước CI luồng chính)."""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from conftest import OTHER, SCHEMAS, TENANT
from svc_workflow.alerts import KIND, MAX_ALERTS, BadAlert, parse
from svc_workflow.app import create_app
from svc_workflow.config import ConfigError, Settings

TOKEN = "gia-lap-" * 4      # giả lập; ít ký tự khác nhau để gitleaks không coi là khóa thật
ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": "bi-mat-action", "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_DIRECTORY_SYNC_INTERVAL_S": "0", "MOC_RECONCILE_INTERVAL_S": "0",
    "MOC_PROCESSES_DIR": "/khong-co", "MOC_SCHEMAS_DIR": str(SCHEMAS), "MOC_ALERT_TOKEN": TOKEN,
}
STARTS = "2026-10-28T09:00:00.123456789Z"
ALERT = {
    "status": "firing",
    "labels": {"alertname": "ComponentDown", "severity": "critical", "component": "hasura", "critical": "true",
               "instance": "svc-files:8000", "job": "svc-files"},
    "annotations": {"summary": "Thành phần hasura gián đoạn — cả Signet ngừng phục vụ"},
    "startsAt": STARTS, "endsAt": "0001-01-01T00:00:00Z",
    "generatorURL": "http://prometheus:9090/graph?g0.expr=moc_component_up", "fingerprint": "4f2a0c1e9b8d7a65",
}
# thân webhook phiên bản 4 như Alertmanager gửi (receiver "signet" trong platform/monitoring/alertmanager.yml)
BODY = {
    "version": "4", "groupKey": '{}:{alertname="ComponentDown"}', "truncatedAlerts": 0, "status": "firing",
    "receiver": "signet", "groupLabels": {"alertname": "ComponentDown"}, "commonLabels": {}, "commonAnnotations": {},
    "externalURL": "http://alertmanager:9093", "alerts": [ALERT],
}


def resolved(body: dict) -> dict:
    out = copy.deepcopy(body)
    out["status"] = "resolved"
    for alert in out["alerts"]:
        alert.update(status="resolved", endsAt="2026-10-28T09:07:30Z")
    return out


# --- đọc webhook ----------------------------------------------------------------------------------------------------

def test_parse_keeps_rule_text_and_drops_other_labels():
    [(key, data)] = parse(BODY)
    assert key == f"{KIND}:4f2a0c1e9b8d7a65:{STARTS}:firing"
    assert data == {"status": "firing", "alert": "ComponentDown", "severity": "critical", "component": "hasura",
                    "message": "Thành phần hasura gián đoạn — cả Signet ngừng phục vụ", "starts_at": STARTS}
    [(key, data)] = parse(resolved(BODY))
    assert key.endswith(":resolved") and data["ends_at"] == "2026-10-28T09:07:30Z"


def test_parse_cleans_text_and_falls_back_to_the_alert_name():
    alert = {**ALERT, "labels": {"alertname": "SlowRoute", "route": "graph\nql"}, "annotations": {}}
    [(_, data)] = parse({"alerts": [alert]})
    assert data["message"] == "SlowRoute" and data["route"] == "graph ql" and data["severity"] == ""
    alert = {**ALERT, "annotations": {"summary": "x\x00" * 400}}
    [(_, data)] = parse({"alerts": [alert]})
    assert len(data["message"]) == 300 and data["message"].endswith("…") and "\x00" not in data["message"]


@pytest.mark.parametrize("body", [
    [], {"alerts": {}}, {"alerts": []}, {"alerts": [ALERT] * (MAX_ALERTS + 1)}, {"alerts": ["x"]},
    {"alerts": [{**ALERT, "status": "pending"}]},
    {"alerts": [{**ALERT, "fingerprint": "../../etc"}]},
    {"alerts": [{**ALERT, "fingerprint": 42}]},
    {"alerts": [{**ALERT, "startsAt": "hôm qua"}]},
    {"alerts": [{**ALERT, "labels": {"severity": "critical"}}]},
    {"alerts": [{**ALERT, "annotations": "tóm tắt"}]},
])
def test_parse_rejects_what_alertmanager_never_sends(body):
    with pytest.raises(BadAlert):
        parse(body)


# --- route ----------------------------------------------------------------------------------------------------------

class NoDirectory:
    async def aclose(self) -> None: ...


def admin(user: str) -> dict:
    return {"id": user, "department_id": None, "role": "tenant_admin", "enabled": True}


@pytest.fixture
def admins(hasura):
    """Một quản trị ở TENANT, một ở đơn vị khác; người dùng vai trò khác không nhận cảnh báo."""
    hasura.users["u-admin"] = admin("u-admin")
    hasura.tenant_users[OTHER] = {"u-admin-kt": admin("u-admin-kt"),
                                  "u-staff-kt": {**admin("u-staff-kt"), "role": "staff"},
                                  "u-admin-cu": {**admin("u-admin-cu"), "enabled": False}}
    return hasura


def client_for(hasura, flowable, env=ENV):
    app = create_app(Settings.from_env(env), hasura=hasura, flowable=flowable,  # type: ignore[arg-type]
                     directory=NoDirectory())  # type: ignore[arg-type]
    return TestClient(app)


def post(client, body=BODY, token=TOKEN, scheme="Bearer"):
    headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    return client.post("/ops/alerts", json=body, headers=headers)


def test_alert_reaches_the_admins_of_every_tenant_once(admins, flowable):
    with client_for(admins, flowable) as client:
        assert post(client).status_code == 204
        assert post(client).status_code == 204          # Alertmanager gửi lại (repeat_interval): không thêm dòng
        assert post(client, resolved(BODY)).status_code == 204
    got = [(n["user_id"], n["tenant_id"], n["data"]["status"]) for n in admins.notifications]
    assert sorted(got) == sorted([("u-admin", TENANT, "firing"), ("u-admin-kt", OTHER, "firing"),
                                  ("u-admin", TENANT, "resolved"), ("u-admin-kt", OTHER, "resolved")])
    assert {(n["kind"], n["document_id"]) for n in admins.notifications} == {(KIND, None)}


def test_alert_that_fires_again_later_is_a_new_notification(admins, flowable):
    again = copy.deepcopy(BODY)
    again["alerts"][0]["startsAt"] = "2026-10-28T11:00:00Z"
    with client_for(admins, flowable) as client:
        for body in (BODY, resolved(BODY), again):
            assert post(client, body).status_code == 204
    assert [n["data"]["status"] for n in admins.notifications if n["user_id"] == "u-admin"] == [
        "firing", "resolved", "firing"]


@pytest.mark.parametrize(("token", "scheme"), [(None, "Bearer"), ("sai-" * 5, "Bearer"),
                                              (TOKEN, "Basic"), (TOKEN + "x", "Bearer"), ("", "Bearer")])
def test_wrong_or_missing_token_is_refused(admins, flowable, token, scheme):
    with client_for(admins, flowable) as client:
        r = post(client, token=token, scheme=scheme)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "unauthorized"
    assert r.headers["www-authenticate"] == "Bearer"
    assert admins.notifications == []


def test_route_is_off_without_a_token(admins, flowable):
    env = {k: v for k, v in ENV.items() if k != "MOC_ALERT_TOKEN"}
    with client_for(admins, flowable, env) as client:
        assert post(client).status_code == 404
        assert post(client, token="").status_code == 404
    assert admins.notifications == []


def test_bad_body_is_400(admins, flowable):
    with client_for(admins, flowable) as client:
        r = client.post("/ops/alerts", content=b"{khong-phai-json", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_request"
        assert post(client, {"alerts": []}).status_code == 400
    assert admins.notifications == []


def test_database_down_is_503_so_alertmanager_retries(admins, flowable):
    admins.fail_notify = True
    with client_for(admins, flowable) as client:
        r = post(client)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"


def test_token_is_checked_and_never_printed():
    settings = Settings.from_env(ENV)
    assert settings.alert_token == TOKEN and TOKEN not in repr(settings)
    assert Settings.from_env({**ENV, "MOC_ALERT_TOKEN": " "}).alert_token == ""
    for bad in ("ngan", "co dau cach 0123456789", "x" * 201):
        with pytest.raises(ConfigError, match="MOC_ALERT_TOKEN"):
            Settings.from_env({**ENV, "MOC_ALERT_TOKEN": bad})
