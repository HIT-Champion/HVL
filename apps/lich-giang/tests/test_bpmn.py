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

"""Quy trình của Đổi, bù lịch giảng (workflow/doi-lich-giang.bpmn20.xml) đọc bằng xml.etree, không cần Flowable: chỉ
phần tử lõi nhận cho ứng dụng cài thêm, không mã chạy trên máy chủ; hai cấp duyệt đúng dạng nhóm mà quy trình văn bản
của lõi dùng (trưởng bộ môn: nhóm trưởng phòng của văn bản đi; lãnh đạo khoa: nhóm lãnh đạo của văn bản đến); bộ môn
không đồng ý thì dừng, không tới khoa; mọi nút đi được từ lúc gửi tới một kết thúc; mỗi cổng rẽ phủ đúng các quyết định
của form bước trước nó; sơ đồ vẽ đủ mọi nút. Lõi vẫn tự kiểm lúc cài — test này giữ tệp của ứng dụng không trượt khỏi
danh sách đó. Chạy: python3 -m unittest discover -s apps/lich-giang/tests (make test)."""

from __future__ import annotations

import json
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

APP = pathlib.Path(__file__).resolve().parent.parent
ROOT = APP.parent.parent
BPMN = APP / "workflow" / "doi-lich-giang.bpmn20.xml"
PROCESSES = ROOT / "services" / "svc-workflow" / "processes"
NS = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL", "di": "http://www.omg.org/spec/BPMN/20100524/DI"}
MODEL = "{" + NS["b"] + "}"
FLOWABLE = "{http://flowable.org/bpmn}"
# Phần tử ứng dụng được dùng trong <process> (danh sách trắng của #301): không scriptTask, serviceTask, listener…
ALLOWED = {"startEvent", "userTask", "exclusiveGateway", "endEvent", "sequenceFlow", "conditionExpression"}
# Thuộc tính flowable: được dùng; class, expression, delegateExpression… gọi mã trên máy chủ
FLOWABLE_ATTRS = {"formKey", "initiator", "candidateGroups"}
CONDITION = re.compile(r"\$\{(\w+) == '([a-z0-9-]+)'\}")
# bước → (formKey, tệp form, trường quyết định, nhóm ứng viên, quy trình lõi có cùng nhóm)
STEPS = {
    "boMon": ("lich-giang.bo-mon", "bo-mon.json", "quyetDinhBoMon", "t:${tenantId}:d:${departmentId}:manager",
              "van-ban-di.bpmn20.xml"),
    "khoa": ("lich-giang.khoa", "khoa.json", "quyetDinhKhoa", "t:${tenantId}:director", "van-ban-den.bpmn20.xml"),
}


def tag(el: ET.Element) -> str:
    return el.tag.split("}", 1)[1]


class Bpmn(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ET.parse(BPMN).getroot()
        processes = self.root.findall("b:process", NS)
        self.assertEqual(len(processes), 1)
        self.process = processes[0]

    def flows_from(self, node_id: str) -> list[ET.Element]:
        return [f for f in self.process.findall("b:sequenceFlow", NS) if f.get("sourceRef") == node_id]

    def test_only_whitelisted_elements_and_attributes(self) -> None:
        for el in self.process.iter():
            if el is self.process:
                continue
            with self.subTest(element=el.tag):
                self.assertTrue(el.tag.startswith(MODEL), "phần tử ngoài BPMN chuẩn (extensionElements…)")
                self.assertIn(tag(el), ALLOWED)
                extra = {k[len(FLOWABLE):] for k in el.attrib if k.startswith(FLOWABLE)} - FLOWABLE_ATTRS
                self.assertEqual(extra, set())
        text = BPMN.read_text(encoding="utf-8")
        for word in ("scriptTask", "serviceTask", "Listener", "flowable:class", "flowable:expression",
                     "delegateExpression", "script>"):
            self.assertNotIn(word, text)

    def test_process_and_form_keys_carry_the_app_prefix(self) -> None:
        self.assertEqual(self.process.get("id"), "lich-giang.don")
        self.assertLessEqual(len(self.process.get("id")), 22)            # MAX_KEY của svc_workflow/apps/bpmn.py
        self.assertEqual(self.process.get("isExecutable"), "true")
        start = self.process.findall("b:startEvent", NS)
        tasks = {t.get("id"): t for t in self.process.findall("b:userTask", NS)}
        self.assertEqual((len(start), sorted(tasks)), (1, sorted(STEPS)))
        self.assertEqual(start[0].get(FLOWABLE + "formKey"), "lich-giang.don")
        self.assertEqual(start[0].get(FLOWABLE + "initiator"), "initiator")
        self.assertEqual(tasks["boMon"].get("name"), "Trưởng bộ môn duyệt")
        self.assertEqual(tasks["khoa"].get("name"), "Lãnh đạo khoa phê duyệt")
        manifest = (APP / "app.yaml").read_text(encoding="utf-8")
        self.assertIn("processes: [workflow/doi-lich-giang.bpmn20.xml]", manifest)
        self.assertRegex(manifest, r"\n    lich-giang\.don: forms/don\.json\n")
        for step, (key, file, *_rest) in STEPS.items():
            self.assertEqual(tasks[step].get(FLOWABLE + "formKey"), key)
            self.assertRegex(manifest, rf"\n    {re.escape(key)}: forms/{re.escape(file)}\n")

    def test_each_step_goes_to_the_group_the_office_workflow_uses(self) -> None:
        for step, (_key, _file, _field, group, office_file) in STEPS.items():
            with self.subTest(step=step):
                task = self.process.find(f"b:userTask[@id='{step}']", NS)
                self.assertEqual(task.get(FLOWABLE + "candidateGroups"), group)
                self.assertIsNone(task.get(FLOWABLE + "assignee"))
                # cùng tên biến, cùng dạng nhóm với một bước của quy trình văn bản (lõi đặt tenantId, departmentId)
                office = ET.parse(PROCESSES / office_file).getroot()
                groups = {t.get(FLOWABLE + "candidateGroups") for t in office.iter(MODEL + "userTask")}
                self.assertIn(group, groups)

    def test_gateways_cover_every_decision_and_a_department_no_stops_before_the_faculty(self) -> None:
        targets = {}
        for step, (_key, file, field, *_rest) in STEPS.items():
            form = json.loads((APP / "forms" / file).read_text(encoding="utf-8"))
            self.assertIn(field, form["required"])                       # biến của điều kiện là trường bắt buộc
            (into_gateway,) = self.flows_from(step)
            gateway = self.process.find(f"b:exclusiveGateway[@id='{into_gateway.get('targetRef')}']", NS)
            self.assertIsNotNone(gateway, f"sau bước {step} phải là một cổng rẽ")
            seen = {}
            for flow in self.flows_from(gateway.get("id")):
                m = CONDITION.fullmatch((flow.find("b:conditionExpression", NS).text or "").strip())
                self.assertIsNotNone(m, f"điều kiện của {flow.get('id')} phải là ${{biến == 'hằng'}}")
                self.assertEqual(m.group(1), field)
                seen[m.group(2)] = flow.get("targetRef")
            self.assertEqual(sorted(seen), sorted(form["properties"][field]["enum"]))
            targets[step] = seen
        self.assertEqual(targets["boMon"], {"dong-y": "khoa", "tu-choi": "boMonTuChoi"})
        self.assertEqual(targets["khoa"], {"dong-y": "daDuyet", "tu-choi": "khoaTuChoi"})
        names = {e.get("id"): e.get("name") for e in self.process.findall("b:endEvent", NS)}
        self.assertEqual(names, {"daDuyet": "Đã duyệt", "boMonTuChoi": "Bộ môn không đồng ý",
                                 "khoaTuChoi": "Khoa không duyệt"})

    def test_every_node_is_on_a_path_from_start_to_an_end(self) -> None:
        nodes = {el.get("id"): tag(el) for el in self.process if tag(el) != "sequenceFlow"}
        edges = [(f.get("sourceRef"), f.get("targetRef")) for f in self.process.findall("b:sequenceFlow", NS)]
        for a, b in edges:
            self.assertIn(a, nodes)
            self.assertIn(b, nodes)

        def reach(start: set[str], pairs: list[tuple[str, str]]) -> set[str]:
            seen, todo = set(start), list(start)
            while todo:
                n = todo.pop()
                for a, b in pairs:
                    if a == n and b not in seen:
                        seen.add(b)
                        todo.append(b)
            return seen

        starts = {i for i, t in nodes.items() if t == "startEvent"}
        ends = {i for i, t in nodes.items() if t == "endEvent"}
        self.assertEqual(reach(starts, edges), set(nodes))
        self.assertEqual(reach(ends, [(b, a) for a, b in edges]), set(nodes))
        self.assertEqual(len(ends), 3)

    def test_diagram_draws_every_node_and_flow(self) -> None:
        drawn = {s.get("bpmnElement") for s in self.root.iter("{" + NS["di"] + "}BPMNShape")}
        drawn |= {e.get("bpmnElement") for e in self.root.iter("{" + NS["di"] + "}BPMNEdge")}
        ids = {el.get("id") for el in self.process if el.get("id")}
        self.assertEqual(drawn, ids)


if __name__ == "__main__":
    unittest.main()
