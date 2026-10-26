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

"""Gói quy trình (apps/bundle.py) và lệnh triển khai ``python -m svc_workflow.apps.deploy`` mà ``moc app install``
gọi trong container — với Flowable giả."""

from __future__ import annotations

import asyncio
import base64
import copy
import io
import json
import zipfile

import pytest

from app_fakes import APP, BPMN, DON, DUYET, AppFlowable, bundle_zip, form_bytes
from svc_workflow.apps import deploy
from svc_workflow.apps.bundle import INDEX, MANIFEST, BundleError, check_bundle, make_zip
from svc_workflow.config import ConfigError
from svc_workflow.flowable import FlowableError


def run(coro):
    return asyncio.run(coro)


def bundle_errors(data: bytes, app: str = APP) -> list[str]:
    with pytest.raises(BundleError) as e:
        check_bundle(app, data)
    return e.value.errors


def raw_zip(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return out.getvalue()


def manifest(**extra: object) -> bytes:
    body = {"app": APP, "processes": ["processes/don.bpmn20.xml"],
            "forms": {f"{APP}.don": "forms/don.json", f"{APP}.duyet": "forms/duyet.json"}, **extra}
    return json.dumps(body).encode()


def sample_files() -> dict[str, bytes]:
    return {MANIFEST: manifest(), "processes/don.bpmn20.xml": BPMN.encode(), "forms/don.json": form_bytes(DON),
            "forms/duyet.json": form_bytes(DUYET)}


# --- gói --------------------------------------------------------------------------------------------------


def test_bundle_becomes_one_deployment_with_fixed_resource_names():
    b = check_bundle(APP, bundle_zip())
    assert b.name.startswith(f"app/{APP}@") and len(b.name) == len(f"app/{APP}@") + 12
    assert sorted(b.resources) == [INDEX, "nghi-phep.don.bpmn20.xml", "nghi-phep.don.json", "nghi-phep.duyet.json"]
    assert json.loads(b.resources[INDEX]) == {
        "format": 1, "app": APP, "forms": ["nghi-phep.don", "nghi-phep.duyet"],
        "processes": {"nghi-phep.don": {"startForm": "nghi-phep.don", "name": "Xin nghỉ phép"}}}
    with zipfile.ZipFile(io.BytesIO(b.zip())) as zf:
        assert sorted(zf.namelist()) == sorted(b.resources)


def test_same_content_gives_the_same_name_and_bytes_whatever_the_zip_order():
    a = check_bundle(APP, bundle_zip())
    files = sample_files()
    b = check_bundle(APP, raw_zip(dict(reversed(list(files.items())))))
    assert a.name == b.name and a.zip() == b.zip()
    changed = copy.deepcopy(DUYET)
    changed["properties"]["ghiChu"]["maxLength"] = 400
    assert check_bundle(APP, bundle_zip(duyet=changed)).name != a.name


@pytest.mark.parametrize("files, needle", [
    ({**sample_files(), "scripts/x.sh": b"rm -rf /"}, "gói có tệp không khai trong workflow: scripts/x.sh"),
    ({k: v for k, v in sample_files().items() if k != "forms/duyet.json"}, "nghi-phep.duyet (forms/duyet.json): "
                                                                            "không có tệp trong gói"),
    ({k: v for k, v in sample_files().items() if k != "processes/don.bpmn20.xml"}, "processes/don.bpmn20.xml không "
                                                                                    "có trong gói"),
    ({**sample_files(), MANIFEST: manifest(forms={"don": "forms/don.json", f"{APP}.duyet": "forms/duyet.json"})},
     "formKey phải dạng nghi-phep.<tên>"),
    ({**sample_files(), MANIFEST: manifest(forms={"van-ban-den.don": "forms/don.json",
                                                  f"{APP}.duyet": "forms/duyet.json"})}, "formKey phải dạng"),
    ({**sample_files(), MANIFEST: manifest(processes=["processes/don.xml"]), "processes/don.xml": BPMN.encode()},
     "phải có đuôi .bpmn20.xml"),
])
def test_bundle_problems_are_listed(files, needle):
    files.pop("processes/don.bpmn20.xml", None) if "processes/don.xml" in files else None
    errors = bundle_errors(raw_zip(files))
    assert any(needle in e for e in errors), errors


def test_condition_variable_must_be_a_required_field():
    loose = copy.deepcopy(DUYET)
    loose["required"] = []
    errors = bundle_errors(bundle_zip(duyet=loose))
    assert errors == ["processes/don.bpmn20.xml: biến quyetDinh dùng trong điều kiện rẽ nhánh phải là trường bắt "
                      "buộc (required) của form — thiếu biến thì Flowable dừng ở cổng"]


def test_two_files_with_the_same_process_id_are_refused():
    data = bundle_zip(extra_processes={"processes/ban-sao.bpmn20.xml": BPMN.encode()})
    assert any("process id nghi-phep.don trùng" in e for e in bundle_errors(data))


def test_form_and_bpmn_errors_come_together():
    bad_form = {**DON, "additionalProperties": True}
    errors = bundle_errors(bundle_zip(BPMN.replace("t:${tenantId}:director", "t:${tenantId}:root"), don=bad_form))
    assert any("additionalProperties: false" in e for e in errors)
    assert any("candidateGroups" in e for e in errors)


@pytest.mark.parametrize("data, needle", [
    (b"khong phai zip", "không phải zip"),
    (raw_zip({"processes/don.bpmn20.xml": BPMN.encode()}), f"gói thiếu {MANIFEST}"),
    (raw_zip({MANIFEST: b"{"}), "không đọc được"),
    (raw_zip({MANIFEST: json.dumps({"app": "khac", "processes": [], "forms": {}}).encode()}), "app phải là"),
    (raw_zip({MANIFEST: json.dumps({"app": APP, "processes": [], "forms": {}}).encode()}), "workflow.processes"),
    (raw_zip({MANIFEST: json.dumps({"app": APP, "processes": ["a.bpmn20.xml"], "forms": []}).encode()}),
     "workflow.forms"),
    (raw_zip({MANIFEST: manifest(), "../thoat.json": b"{}"}), "không hợp lệ"),
    (raw_zip({MANIFEST: manifest(), "/tuyet-doi.json": b"{}"}), "không hợp lệ"),
    (raw_zip({MANIFEST: manifest(), "a/./b.json": b"{}"}), "không hợp lệ"),
    (raw_zip({MANIFEST: manifest(), **{f"f{i}.json": b"{}" for i in range(64)}}), "tối đa 64"),
])
def test_unreadable_bundles(data, needle):
    errors = bundle_errors(data)
    assert len(errors) == 1 and needle in errors[0], errors


def test_bundle_size_is_capped_while_reading():
    big = raw_zip({MANIFEST: manifest(), **{f"f{i}.json": b"0" * (3 * 1024 * 1024) for i in range(3)}})
    assert "lớn quá 8 MB" in bundle_errors(big)[0]


def test_bad_app_name():
    assert bundle_errors(bundle_zip(), app="Nghi_Phep") == ["tên ứng dụng 'Nghi_Phep' không hợp lệ"]


def test_make_zip_writes_what_moc_app_install_sends():
    with zipfile.ZipFile(io.BytesIO(bundle_zip())) as zf:
        assert sorted(zf.namelist()) == sorted(sample_files())
        assert json.loads(zf.read(MANIFEST)) == json.loads(manifest())
    assert make_zip(APP, {"p.bpmn20.xml": b"x"}, {}) == make_zip(APP, {"p.bpmn20.xml": b"x"}, {})


# --- triển khai -------------------------------------------------------------------------------------------


@pytest.fixture
def fl() -> AppFlowable:
    return AppFlowable()


def test_install_deploys_once_and_skips_an_unchanged_bundle(fl):
    b = check_bundle(APP, bundle_zip())
    first = run(deploy.install(fl, b))
    assert first == {"ok": True, "deployment": b.name, "processes": ["nghi-phep.don"],
                     "forms": ["nghi-phep.don", "nghi-phep.duyet"], "deployed": True, "activated": 0}
    assert [d["name"] for d in fl.deployed] == [b.name]
    assert fl.resources[("dep-1", "nghi-phep.duyet.json")] == form_bytes(DUYET)
    assert run(deploy.install(fl, b))["deployed"] is False and len(fl.deployed) == 1


def test_reinstalling_an_older_bundle_makes_it_the_latest(fl):
    v1 = check_bundle(APP, bundle_zip())
    v2 = check_bundle(APP, bundle_zip(BPMN.replace('flowable:dueDate="P2D"', 'flowable:dueDate="P3D"')))
    run(deploy.install(fl, v1))
    run(deploy.install(fl, v2))
    assert run(deploy.install(fl, v1))["deployed"] is True
    assert run(deploy.latest(fl, APP))["name"] == v1.name
    assert [d["version"] for d in fl.defs.values()] == [1, 2, 3]


def test_remove_suspends_and_install_activates_again(fl):
    b = check_bundle(APP, bundle_zip())
    run(deploy.install(fl, b))
    run(deploy.install(fl, check_bundle(APP, bundle_zip(BPMN.replace("P2D", "P5D")))))
    fl.defs["van-ban-den:1:x"] = {"id": "van-ban-den:1:x", "key": "van-ban-den", "deploymentId": "x",
                                  "suspended": False, "version": 1}
    assert run(deploy.remove(fl, APP)) == {"ok": True, "suspended": 2}
    assert [d["suspended"] for d in fl.defs.values()] == [True, True, False]      # quy trình Văn phòng không đụng
    assert run(deploy.remove(fl, APP)) == {"ok": True, "suspended": 0}
    again = run(deploy.install(fl, b))
    assert again["deployed"] is True and again["activated"] == 2
    assert not any(d["suspended"] for d in fl.defs.values())


def test_check_tells_whether_the_bundle_is_current(fl):
    b = check_bundle(APP, bundle_zip())
    assert run(deploy.check(fl, b))["current"] is False
    run(deploy.install(fl, b))
    assert run(deploy.check(fl, b))["current"] is True
    assert run(deploy.check(None, b))["current"] is None
    fl.down = True
    assert run(deploy.check(fl, b))["current"] is None and fl.deployed


# --- dòng lệnh: một dòng JSON trên stdout --------------------------------------------------------------------


def cli(capsys, argv: list[str], data: bytes | None = None, client: object = None) -> tuple[int, dict | None, str]:
    stdin = io.StringIO(base64.b64encode(data).decode() + "\n" if data is not None else "")
    code = deploy.main(argv, stdin=stdin, client=client)
    out, err = capsys.readouterr()
    lines = out.strip().splitlines()
    assert len(lines) <= 1
    return code, json.loads(lines[0]) if lines else None, err


def test_cli_install_check_remove(capsys, fl):
    code, out, _ = cli(capsys, ["install", APP], bundle_zip(), fl)
    assert code == 0 and out["ok"] and out["deployed"]
    code, out, _ = cli(capsys, ["check", APP], bundle_zip(), fl)
    assert code == 0 and out["current"] is True
    code, out, _ = cli(capsys, ["remove", APP], None, fl)
    assert code == 0 and out == {"ok": True, "suspended": 1}


def test_cli_reports_a_rejected_bundle_as_ok_false(capsys, fl):
    code, out, _ = cli(capsys, ["install", APP], bundle_zip(BPMN.replace("userTask id=\"duyet\"",
                                                                         "userTask flowable:class=\"X\" id=\"duyet\"")),
                       fl)
    assert code == 0 and out["ok"] is False and "flowable:class" in out["errors"][0]
    assert fl.deployed == []


@pytest.mark.parametrize("argv, stdin", [(["install", APP], "khong-phai-base64!"), (["check", APP], "")])
def test_cli_needs_a_base64_zip(capsys, fl, argv, stdin):
    code = deploy.main(argv, stdin=io.StringIO(stdin), client=fl)
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["ok"] is False and out["errors"]


def test_cli_refuses_a_bad_app_name(capsys, fl):
    code, out, _ = cli(capsys, ["remove", "../x"], None, fl)
    assert code == 0 and out == {"ok": False, "errors": ["tên ứng dụng '../x' không hợp lệ"]}


def test_cli_exits_2_when_vault_or_flowable_is_unreachable(capsys, monkeypatch, fl):
    def no_vault():
        raise ConfigError("OpenBao chưa sẵn sàng")

    monkeypatch.setattr(deploy, "_client", no_vault)
    code, out, err = cli(capsys, ["install", APP], bundle_zip())
    assert code == 2 and out is None and "OpenBao chưa sẵn sàng" in err
    code, out, _ = cli(capsys, ["check", APP], bundle_zip())               # --dry-run: gói vẫn kiểm được
    assert code == 0 and out["ok"] is True and out["current"] is None
    fl.down = True
    code, out, err = cli(capsys, ["remove", APP], None, fl)
    assert code == 2 and out is None and "Không gọi được Flowable" in err


def test_cli_closes_the_client(capsys):
    class Closing(AppFlowable):
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    fl = Closing()
    cli(capsys, ["install", APP], bundle_zip(), fl)
    assert fl.closed


def test_client_takes_flowable_credentials_from_the_vault(monkeypatch):
    seen = {}

    def secrets(env):
        seen["env"] = env
        return {**env, "FLOWABLE_PASSWORD": "tu-ket"}

    class Settings:
        flowable_url, flowable_user, flowable_password = "http://flowable/x", "rest-admin", "tu-ket"

        @classmethod
        def from_env(cls, env):
            assert env["FLOWABLE_PASSWORD"] == "tu-ket"
            return cls()

    monkeypatch.setattr(deploy, "with_secrets", secrets)
    monkeypatch.setattr(deploy, "Settings", Settings)
    client = deploy._client()
    try:
        assert seen["env"] is not None and client._http.auth is not None
    finally:
        run(client.aclose())


def test_flowable_error_while_installing_is_not_swallowed(fl):
    fl.down = True
    with pytest.raises(FlowableError):
        run(deploy.install(fl, check_bundle(APP, bundle_zip())))
