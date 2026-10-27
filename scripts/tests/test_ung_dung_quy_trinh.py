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

"""`moc app install | remove | sync` với mục `workflow` của manifest (#301): svc-workflow kiểm gói trước mọi thay đổi,
bước "quy trình" triển khai sau Keycloak, hoàn tác khi Hasura lỗi, gỡ thì tạm dừng. svc-workflow, Docker, CSDL,
Keycloak giả như test_ung_dung.py (dùng lại bản giả của tệp đó). Chạy: python3 -m unittest discover -s scripts/tests."""

from __future__ import annotations

import argparse
import base64
import io
import json
import pathlib
import shutil
import unittest
import unittest.mock
import zipfile
from contextlib import redirect_stdout
from typing import Any

import test_ung_dung as base

BPMN = '<?xml version="1.0" encoding="UTF-8"?>\n<definitions id="d"/>\n'      # svc-workflow giả không đọc
FORM = '{"type": "object"}\n'
WORKFLOW = """
workflow:
  processes: [workflow/don.bpmn20.xml]
  forms:
    bang-tin.don: forms/don.json
    bang-tin.duyet: forms/duyet.json
"""
SCRIPT_TASK = ("workflow/don.bpmn20.xml dòng 9: <scriptTask> không được phép trong <process> — BPMN của ứng dụng chỉ "
               "gồm sự kiện bắt đầu/kết thúc, userTask, cổng rẽ nhánh và luồng")


def setUpModule() -> None:
    base.setUpModule()


def tearDownModule() -> None:
    base.tearDownModule()


class FakeWorkflow:
    """svc_workflow.apps.deploy trong container: trả đúng một dòng JSON như lệnh thật; nhớ bản đang triển khai."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.current: str | None = None             # gói (base64) của deployment mới nhất
        self.reject: list[str] = []
        self.down = False
        self.suspended = False

    def __call__(self, action: str, name: str, bundle: str | None) -> str:
        self.calls.append((action, name, bundle))
        if self.down:
            raise base.u.AppError("docker compose exec -T svc-workflow… thoát 1: svc-workflow is not running")
        if self.reject and action != "remove":
            return json.dumps({"ok": False, "errors": self.reject}, ensure_ascii=False) + "\n"
        deployment = f"app/{name}@{abs(hash(bundle)) % 10**12:012d}"
        info = {"deployment": deployment, "processes": [f"{name}.don"], "forms": [f"{name}.don", f"{name}.duyet"]}
        if action == "check":
            return json.dumps({"ok": True, **info, "current": bundle == self.current}) + "\n"
        if action == "install":
            deployed, activated = bundle != self.current, int(self.suspended)
            self.current, self.suspended = bundle, False
            return json.dumps({"ok": True, **info, "deployed": deployed, "activated": activated}) + "\n"
        self.suspended = True
        return json.dumps({"ok": True, "suspended": 1}) + "\n"

    def actions(self) -> list[str]:
        return [a for a, _, _ in self.calls]


class WorkflowFlow(unittest.TestCase):
    setUp_core = base.Flow.setUp
    tearDown = base.Flow.tearDown
    snapshot = base.Flow.snapshot

    def setUp(self) -> None:
        self.setUp_core()
        self.app = self.tmp / "apps" / "bang-tin"
        shutil.copytree(base.APP.parent, self.app, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        self.manifest = self.app / "app.yaml"
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8") + WORKFLOW, encoding="utf-8")
        (self.app / "workflow").mkdir()
        (self.app / "workflow" / "don.bpmn20.xml").write_text(BPMN, encoding="utf-8")
        (self.app / "forms").mkdir()
        for name in ("don", "duyet"):
            (self.app / "forms" / f"{name}.json").write_text(FORM, encoding="utf-8")
        self.wf = FakeWorkflow()
        run = self.system.run
        self.order: list[str] = []

        def fake_run(cmd: list[str], *, input: str | None = None, timeout: float = 900) -> str:
            if "svc_workflow.apps.deploy" in cmd:
                at = cmd.index("svc_workflow.apps.deploy")
                self.order.append(f"quy trình {cmd[at + 1]}")
                return self.wf(cmd[at + 1], cmd[at + 2], input)
            self.order.append(" ".join(cmd[:2]))
            return run(cmd, input=input, timeout=timeout)

        self.system.run = fake_run

    def install(self, **kw: Any) -> dict[str, Any]:
        return base.u.install(self.manifest, state=self.state, system=self.system, out=self.lines.append, **kw)

    def text(self) -> str:
        return "\n".join(self.lines)

    # --- cài ------------------------------------------------------------------------------------------------

    def test_install_checks_first_then_deploys_after_keycloak(self) -> None:
        self.install()
        self.assertEqual(self.wf.actions(), ["check", "install"])
        self.assertEqual(self.order[0], "quy trình check")                 # trước image, CSDL, Keycloak
        out = self.text()
        self.assertIn("1/9 manifest: hợp lệ (1 migration, 1 bảng, 1 quy trình (svc-workflow đã kiểm)", out)
        self.assertRegex(out, r"6/9 quy trình: đã triển khai app/bang-tin@\d{12} \(1 quy trình, 2 form\)")
        self.assertIn("9/9 Hasura: metadata đã áp", out)
        steps = [ln.split(":")[0].strip() for ln in self.lines if ln.startswith("  ")]
        self.assertEqual(steps, [f"{i}/9 {n}" for i, n in enumerate(
            ["manifest", "image", "CSDL", "bí mật", "Keycloak", "quy trình", "tệp chạy", "container", "Hasura"], 1)])
        rec = json.loads((self.tmp / base.u.STATE / "apps" / "bang-tin.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["workflow"]["processes"], {"workflow/don.bpmn20.xml": BPMN})
        self.assertEqual(rec["workflow"]["forms"]["bang-tin.duyet"], {"path": "forms/duyet.json", "text": FORM})

    def test_bundle_is_the_declared_files_in_a_stable_zip(self) -> None:
        self.install()
        _, name, bundle = self.wf.calls[-1]
        self.assertEqual(name, "bang-tin")
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(bundle))) as zf:
            self.assertEqual(sorted(zf.namelist()), ["forms/don.json", "forms/duyet.json", "moc-workflow.json",
                                                     "workflow/don.bpmn20.xml"])
            self.assertEqual(json.loads(zf.read("moc-workflow.json")), {
                "app": "bang-tin", "processes": ["workflow/don.bpmn20.xml"],
                "forms": {"bang-tin.don": "forms/don.json", "bang-tin.duyet": "forms/duyet.json"}})
            self.assertEqual(zf.read("workflow/don.bpmn20.xml").decode(), BPMN)
        self.assertEqual(self.wf.calls[0][2], bundle)                       # kiểm và triển khai cùng một gói

    def test_install_again_keeps_the_deployment(self) -> None:
        self.install()
        snap = self.snapshot()
        self.lines.clear()
        self.install()
        self.assertEqual(self.wf.actions(), ["check", "install", "check", "install"])
        self.assertRegex(self.text(), r"6/9 quy trình: app/bang-tin@\d{12} đã triển khai, giữ nguyên")
        self.assertEqual(self.snapshot(), snap)

    def test_rejected_bundle_changes_nothing(self) -> None:
        before = self.snapshot()
        self.wf.reject = [SCRIPT_TASK]
        with self.assertRaises(base.u.StepFailed) as ctx:
            self.install()
        msg = str(ctx.exception)
        self.assertIn("bước 1/9 (manifest): quy trình chưa đúng (1 lỗi):", msg)
        self.assertIn("<scriptTask> không được phép", msg)
        self.assertEqual(self.wf.actions(), ["check"])
        self.assertEqual(self.order, ["quy trình check"])                   # không image, không compose
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.system.kc.writes, [])
        self.assertEqual(self.system.db.scripts, [])
        args = argparse.Namespace(cmd="install", manifest=str(self.manifest), json=False)
        err = io.StringIO()
        with unittest.mock.patch("sys.stderr", err):
            self.assertEqual(base.u._fail(ctx.exception, args), 1)
        self.assertIn("scriptTask", err.getvalue())

    def test_svc_workflow_down_stops_before_any_change(self) -> None:
        self.wf.down = True
        before = self.snapshot()
        with self.assertRaises(base.u.StepFailed) as ctx:
            self.install()
        self.assertIn("bước 1/9 (manifest): chưa gọi được svc-workflow", str(ctx.exception))
        self.assertEqual(self.snapshot(), before)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(base.u._fail(ctx.exception, argparse.Namespace(cmd="install", json=True)), 2)

    def test_dry_run_only_checks(self) -> None:
        before = self.snapshot()
        self.install(dry_run=True)
        self.assertEqual(self.wf.actions(), ["check"])
        self.assertEqual(self.snapshot(), before)
        self.assertRegex(self.text(), r"6/9 quy trình: sẽ triển khai app/bang-tin@\d{12} \(1 quy trình, 2 form\)")
        self.lines.clear()
        self.install()
        self.lines.clear()
        self.install(dry_run=True)
        self.assertRegex(self.text(), r"6/9 quy trình: đã triển khai đúng bản này app/bang-tin@")

    def test_dry_run_without_svc_workflow_still_prints_the_plan(self) -> None:
        self.wf.down = True
        self.install(dry_run=True)
        out = self.text()
        self.assertIn("1 quy trình (chưa kiểm được: chưa gọi được svc-workflow", out)
        self.assertIn("6/9 quy trình: sẽ triển khai (chưa hỏi được Flowable) gói quy trình", out)
        self.assertIn("9/9 Hasura: sẽ áp", out)

    def test_dry_run_reports_a_rejected_bundle(self) -> None:
        self.wf.reject = [SCRIPT_TASK]
        with self.assertRaises(base.u.StepFailed) as ctx:
            self.install(dry_run=True)
        self.assertIn("scriptTask", str(ctx.exception))

    # --- hoàn tác, đổi gói ----------------------------------------------------------------------------------

    def test_hasura_failure_suspends_a_first_deployment(self) -> None:
        self.system.broken_once = True
        with self.assertRaises(base.u.StepFailed) as ctx:
            self.install()
        self.assertIn("bước 9/9 (Hasura)", str(ctx.exception))
        self.assertIn("; quy trình vừa triển khai đã tạm dừng", str(ctx.exception))
        self.assertEqual(self.wf.actions(), ["check", "install", "remove"])

    def test_hasura_failure_puts_the_previous_bundle_back(self) -> None:
        self.install()
        first = self.wf.current
        (self.app / "forms" / "duyet.json").write_text('{"type": "object", "title": "mới"}\n', encoding="utf-8")
        self.system.broken_once = True
        with self.assertRaises(base.u.StepFailed) as ctx:
            self.install()
        self.assertIn("; quy trình về bản của lần cài trước", str(ctx.exception))
        self.assertEqual(self.wf.actions(), ["check", "install", "check", "install", "install"])
        self.assertNotEqual(self.wf.calls[3][2], first)                     # bản mới đã triển khai…
        self.assertEqual(self.wf.calls[4][2], first)                        # …rồi cài lại bản trước
        self.assertEqual(self.wf.current, first)

    def test_container_failure_suspends_a_first_deployment(self) -> None:
        # bước sau "quy trình" lỗi: không để BPMN, form mới chạy khi chưa có trang, route
        with unittest.mock.patch.object(base.u, "up_services", side_effect=base.u.AppError("compose up thoát 1")):
            with self.assertRaises(base.u.StepFailed) as ctx:
                self.install()
        self.assertIn("bước 8/9 (container): compose up thoát 1; quy trình vừa triển khai đã tạm dừng",
                      str(ctx.exception))
        self.assertEqual(self.wf.actions(), ["check", "install", "remove"])
        self.install()                                                      # chạy lại: bật lại, làm tiếp
        self.assertFalse(self.wf.suspended)

    def test_files_failure_puts_the_previous_bundle_back(self) -> None:
        self.install()
        first = self.wf.current
        (self.app / "forms" / "duyet.json").write_text('{"type": "object", "title": "mới"}\n', encoding="utf-8")
        with unittest.mock.patch.object(self.state, "write", side_effect=base.u.AppError("không ghi được")):
            with self.assertRaises(base.u.StepFailed) as ctx:
                self.install()
        self.assertIn("bước 7/9 (tệp chạy): không ghi được; quy trình về bản của lần cài trước", str(ctx.exception))
        self.assertEqual(self.wf.current, first)

    def container_fails(self) -> str:
        with unittest.mock.patch.object(base.u, "up_services", side_effect=base.u.AppError("compose up thoát 1")):
            with self.assertRaises(base.u.StepFailed) as ctx:
                self.install()
        return str(ctx.exception)

    def record_bytes(self) -> bytes:
        return (self.tmp / base.u.STATE / "apps" / "bang-tin.json").read_bytes()

    def test_container_failing_twice_still_suspends_a_first_deployment(self) -> None:
        # lần lỗi đầu đã ghi bản ghi mới: lần sau vẫn hoàn tác về lúc chưa cài, không về bản ghi lần lỗi để lại
        for _ in range(2):
            self.assertIn("; quy trình vừa triển khai đã tạm dừng", self.container_fails())
            self.assertTrue(self.wf.suspended)
        self.assertEqual(self.wf.actions(), ["check", "install", "remove"] * 2)
        self.assertTrue(self.state.before_path("bang-tin").exists())
        self.install()
        self.assertFalse(self.wf.suspended)
        self.assertFalse(self.state.before_path("bang-tin").exists())         # cài xong: hết đích hoàn tác

    def test_upgrade_failing_twice_still_goes_back_to_the_previous_bundle(self) -> None:
        self.install()
        first = self.wf.current
        (self.app / "forms" / "duyet.json").write_text('{"type": "object", "title": "mới"}\n', encoding="utf-8")
        for _ in range(2):
            self.assertIn("; quy trình về bản của lần cài trước", self.container_fails())
            self.assertEqual(self.wf.current, first)

    def test_hasura_undo_after_a_container_failure_restores_the_record_before_both(self) -> None:
        self.install()
        first, record = self.wf.current, self.record_bytes()
        (self.app / "forms" / "duyet.json").write_text('{"type": "object", "title": "mới"}\n', encoding="utf-8")
        self.container_fails()
        self.assertNotEqual(self.record_bytes(), record)                    # lần dở để lại bản ghi mới
        self.system.broken_once = True
        with self.assertRaises(base.u.StepFailed) as ctx:
            self.install()
        self.assertIn("bước 9/9 (Hasura)", str(ctx.exception))
        self.assertEqual(self.record_bytes(), record)
        self.assertEqual(self.wf.current, first)
        self.assertFalse(self.state.before_path("bang-tin").exists())

    def test_failure_before_the_workflow_step_leaves_flowable_alone(self) -> None:
        with unittest.mock.patch.object(base.u, "step_keycloak", side_effect=base.u.AppError("Keycloak 500")):
            with self.assertRaises(base.u.StepFailed) as ctx:
                self.install()
        self.assertIn("bước 5/9 (Keycloak): Keycloak 500", str(ctx.exception))
        self.assertNotIn("quy trình", str(ctx.exception))
        self.assertEqual(self.wf.actions(), ["check"])

    def test_dropping_workflow_from_the_manifest_suspends_it(self) -> None:
        self.install()
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(WORKFLOW, ""), encoding="utf-8")
        self.lines.clear()
        self.install()
        self.assertEqual(self.wf.actions()[-1], "remove")
        self.assertIn("6/9 quy trình: manifest không còn workflow: đã tạm dừng 1 định nghĩa quy trình", self.text())
        self.lines.clear()
        self.install()                                                      # lần sau: không còn bước quy trình
        self.assertIn("8/8 Hasura", self.text())

    # --- gỡ, đồng bộ ------------------------------------------------------------------------------------------

    def test_remove_suspends_and_keeps_history(self) -> None:
        self.install()
        self.lines.clear()
        base.u.remove("bang-tin", state=self.state, system=self.system, out=self.lines.append)
        self.assertEqual(self.wf.actions()[-1], "remove")
        self.assertTrue(self.wf.suspended)
        self.assertIn("4/6 quy trình: đã tạm dừng 1 định nghĩa quy trình; lịch sử, đơn đang dở giữ nguyên",
                      self.text())
        self.lines.clear()
        self.install()                                                      # cài lại cùng bản: bật lại
        self.assertRegex(self.text(), r"đã triển khai, giữ nguyên \(1 quy trình, 2 form\); bật lại 1 định nghĩa")

    def test_remove_keeps_the_client_until_the_workflow_is_suspended(self) -> None:
        self.install()
        self.wf.down = True
        with self.assertRaises(base.u.StepFailed) as ctx:
            base.u.remove("bang-tin", state=self.state, system=self.system, out=self.lines.append)
        self.assertIn("bước 4/6 (quy trình)", str(ctx.exception))
        clients = [c["clientId"] for c in self.system.kc.clients()]
        self.assertIn("app-bang-tin", clients)                             # chưa xóa: chạy lại gỡ tiếp
        self.wf.down = False
        base.u.remove("bang-tin", state=self.state, system=self.system, out=self.lines.append)
        self.assertTrue(self.wf.suspended)
        self.assertNotIn("app-bang-tin", [c["clientId"] for c in self.system.kc.clients()])

    def test_remove_after_a_failed_install_drops_the_undo_target(self) -> None:
        self.container_fails()
        self.assertTrue(self.state.before_path("bang-tin").exists())
        base.u.remove("bang-tin", state=self.state, system=self.system, out=self.lines.append)
        self.assertFalse(self.state.before_path("bang-tin").exists())

    def test_remove_dry_run_does_not_call_svc_workflow(self) -> None:
        self.install()
        calls = len(self.wf.calls)
        base.u.remove("bang-tin", state=self.state, system=self.system, dry_run=True, out=self.lines.append)
        self.assertEqual(len(self.wf.calls), calls)
        self.assertIn("4/6 quy trình: sẽ tạm dừng mọi định nghĩa quy trình", self.text())

    def test_sync_redeploys_from_the_record(self) -> None:
        self.install()
        shutil.rmtree(self.app / "workflow")                                # nguồn mất: bản ghi vẫn đủ
        self.wf.current = None
        result = base.u.sync(state=self.state, system=self.system, out=self.lines.append)
        self.assertTrue(any(a.startswith("bang-tin: quy trình: đã triển khai") for a in result["actions"]))
        self.assertEqual(self.wf.actions()[-1], "install")


class ManifestRules(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(base.tempfile.mkdtemp())
        self.app = self.tmp / "app"
        shutil.copytree(base.APP.parent, self.app, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        (self.app / "workflow").mkdir()
        (self.app / "workflow" / "don.bpmn20.xml").write_text(BPMN, encoding="utf-8")
        (self.app / "forms").mkdir()
        (self.app / "forms" / "don.json").write_text(FORM, encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def errors(self, workflow: Any) -> list[str]:
        m = {**base.manifest(), "workflow": workflow}
        return base.u.check_manifest(m, self.app, base.schema())

    def test_valid_workflow(self) -> None:
        self.assertEqual(self.errors({"processes": ["workflow/don.bpmn20.xml"],
                                      "forms": {"bang-tin.don": "forms/don.json"}}), [])

    def test_rules(self) -> None:
        cases = [
            ({"processes": ["workflow/don.bpmn20.xml"], "forms": {"khac.don": "forms/don.json"}},
             "workflow.forms.khac.don: formKey phải mở đầu bằng bang-tin."),
            ({"processes": ["workflow/khong-co.bpmn20.xml"], "forms": {}}, "workflow.processes: không có tệp"),
            ({"processes": ["workflow/don.bpmn20.xml"], "forms": {"bang-tin.don": "forms/khong-co.json"}},
             "workflow.forms.bang-tin.don: không có tệp forms/khong-co.json"),
            ({"processes": ["w/../../../etc/x.bpmn20.xml"], "forms": {}}, "workflow.processes"),
            ({"processes": ["../x.bpmn20.xml"], "forms": {}}, "workflow"),
            ({"processes": ["workflow/don.xml"], "forms": {}}, "workflow"),
            ({"processes": [], "forms": {}}, "workflow"),
            ({"processes": ["workflow/don.bpmn20.xml"]}, "workflow"),
            ({"processes": ["workflow/don.bpmn20.xml"], "forms": {"BangTin.Don": "forms/don.json"}}, "workflow"),
        ]
        for workflow, needle in cases:
            with self.subTest(workflow=workflow):
                errors = self.errors(workflow)
                self.assertTrue(any(needle in e for e in errors), errors)

    def test_big_file_is_refused(self) -> None:
        (self.app / "workflow" / "don.bpmn20.xml").write_bytes(b" " * (base.u.MAX_WORKFLOW_FILE + 1))
        errors = self.errors({"processes": ["workflow/don.bpmn20.xml"], "forms": {}})
        self.assertTrue(any("lớn quá" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
