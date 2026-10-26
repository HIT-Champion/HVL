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

"""Quy trình của Đơn nghỉ phép (workflow/don-nghi-phep.bpmn20.xml) đọc bằng xml.etree, không cần Flowable: chỉ phần tử
lõi nhận cho ứng dụng cài thêm, không mã chạy trên máy chủ; nhóm duyệt đúng dạng nhóm trưởng phòng mà quy trình văn
bản đi của lõi dùng (cùng tên biến); mọi nút đi được từ lúc gửi đơn tới một kết thúc; cổng rẽ phủ đúng các quyết định
của form duyệt; sơ đồ vẽ đủ mọi nút. Lõi vẫn tự kiểm lúc cài — test này giữ tệp của ứng dụng không trượt khỏi danh sách
đó. Chạy: python3 -m unittest discover -s apps/nghi-phep/tests (make test)."""

from __future__ import annotations

import json
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

APP = pathlib.Path(__file__).resolve().parent.parent
ROOT = APP.parent.parent
BPMN = APP / "workflow" / "don-nghi-phep.bpmn20.xml"
OFFICE = ROOT / "services" / "svc-workflow" / "processes" / "van-ban-di.bpmn20.xml"
NS = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL", "di": "http://www.omg.org/spec/BPMN/20100524/DI"}
MODEL = "{" + NS["b"] + "}"
FLOWABLE = "{http://flowable.org/bpmn}"
# Phần tử ứng dụng được dùng trong <process> (danh sách trắng của #301): không scriptTask, serviceTask, listener…
ALLOWED = {"startEvent", "userTask", "exclusiveGateway", "endEvent", "sequenceFlow", "conditionExpression"}
# Thuộc tính flowable: được dùng; class, expression, delegateExpression… gọi mã trên máy chủ
FLOWABLE_ATTRS = {"formKey", "initiator", "candidateGroups"}
CONDITION = re.compile(r"\$\{(\w+) == '([a-z0-9-]+)'\}")
GROUP = "t:${tenantId}:d:${departmentId}:manager"


def tag(el: ET.Element) -> str:
    return el.tag.split("}", 1)[1]


class Bpmn(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ET.parse(BPMN).getroot()
        processes = self.root.findall("b:process", NS)
        self.assertEqual(len(processes), 1)
        self.process = processes[0]

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
        self.assertEqual(self.process.get("id"), "nghi-phep.don")
        self.assertEqual(self.process.get("isExecutable"), "true")
        start = self.process.findall("b:startEvent", NS)
        task = self.process.findall("b:userTask", NS)
        self.assertEqual((len(start), len(task)), (1, 1))
        self.assertEqual(start[0].get(FLOWABLE + "formKey"), "nghi-phep.don")
        self.assertEqual(start[0].get(FLOWABLE + "initiator"), "initiator")
        self.assertEqual(task[0].get(FLOWABLE + "formKey"), "nghi-phep.duyet")
        self.assertEqual(task[0].get("name"), "Trưởng phòng duyệt")
        manifest = (APP / "app.yaml").read_text(encoding="utf-8")
        self.assertIn("processes: [workflow/don-nghi-phep.bpmn20.xml]", manifest)
        for key in ("nghi-phep.don", "nghi-phep.duyet"):
            self.assertRegex(manifest, rf"\n    {re.escape(key)}: forms/\w+\.json\n")

    def test_reviewers_are_the_managers_of_the_requesters_department(self) -> None:
        task = self.process.find("b:userTask", NS)
        self.assertEqual(task.get(FLOWABLE + "candidateGroups"), GROUP)
        self.assertIsNone(task.get(FLOWABLE + "assignee"))
        # cùng tên biến, cùng dạng nhóm với bước duyệt cấp phòng của văn bản đi (lõi đặt tenantId, departmentId)
        office = ET.parse(OFFICE).getroot()
        groups = {t.get(FLOWABLE + "candidateGroups") for t in office.iter(MODEL + "userTask")}
        self.assertIn(GROUP, groups)

    def test_gateway_covers_every_decision_of_the_review_form(self) -> None:
        duyet = json.loads((APP / "forms" / "duyet.json").read_text(encoding="utf-8"))
        gateway = self.process.find("b:exclusiveGateway", NS)
        out = [f for f in self.process.findall("b:sequenceFlow", NS) if f.get("sourceRef") == gateway.get("id")]
        seen = {}
        for flow in out:
            cond = flow.find("b:conditionExpression", NS)
            m = CONDITION.fullmatch((cond.text or "").strip())
            self.assertIsNotNone(m, f"điều kiện của {flow.get('id')} phải là ${{biến == 'hằng'}}")
            self.assertEqual(m.group(1), "quyetDinh")
            seen[m.group(2)] = self.process.find(f"b:endEvent[@id='{flow.get('targetRef')}']", NS).get("name")
        self.assertEqual(sorted(seen), sorted(duyet["properties"]["quyetDinh"]["enum"]))
        self.assertEqual(seen, {"dong-y": "Đã duyệt", "tu-choi": "Bị từ chối"})
        self.assertIn("quyetDinh", duyet["required"])

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
        self.assertEqual(len(ends), 2)

    def test_diagram_draws_every_node_and_flow(self) -> None:
        drawn = {s.get("bpmnElement") for s in self.root.iter("{" + NS["di"] + "}BPMNShape")}
        drawn |= {e.get("bpmnElement") for e in self.root.iter("{" + NS["di"] + "}BPMNEdge")}
        ids = {el.get("id") for el in self.process if el.get("id")}
        self.assertEqual(drawn, ids)


if __name__ == "__main__":
    unittest.main()
