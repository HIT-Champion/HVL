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

"""Gói quy trình mẫu (nghỉ phép) và Flowable giả cho phần quy trình của ứng dụng (svc_workflow/apps/)."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from svc_workflow.apps.bundle import make_zip
from svc_workflow.flowable import FlowableError, Task

APP = "nghi-phep"
DRAFT = "https://json-schema.org/draft/2020-12/schema"

DON: dict[str, Any] = {
    "$schema": DRAFT, "title": "Đơn xin nghỉ", "type": "object", "additionalProperties": False, "x-moc-nfc": True,
    "required": ["loai", "tuNgay", "denNgay"], "x-moc-range": [["tuNgay", "denNgay"]],
    "properties": {
        "loai": {"enum": ["phep-nam", "om", "viec-rieng"]},
        "tuNgay": {"type": "string", "format": "date"},
        "denNgay": {"type": "string", "format": "date"},
        "soNgay": {"type": "integer", "minimum": 1, "maximum": 30},
        "khanCap": {"type": "boolean"},
        "lyDo": {"type": "string", "minLength": 1, "maxLength": 500},
    },
}
DUYET: dict[str, Any] = {
    "$schema": DRAFT, "title": "Duyệt đơn", "type": "object", "additionalProperties": False, "x-moc-nfc": True,
    "required": ["quyetDinh"],
    "properties": {"quyetDinh": {"enum": ["dong-y", "tu-choi"]}, "ghiChu": {"type": "string", "maxLength": 500}},
}

BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:flowable="http://flowable.org/bpmn"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
             xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
             targetNamespace="https://signet.example/nghi-phep">
  <process id="nghi-phep.don" name="Xin nghỉ phép" isExecutable="true">
    <documentation>Trưởng phòng của người gửi duyệt đơn.</documentation>
    <startEvent id="gui" name="Gửi đơn" flowable:formKey="nghi-phep.don" flowable:initiator="initiator"/>
    <sequenceFlow id="f1" sourceRef="gui" targetRef="duyet"/>
    <userTask id="duyet" name="Duyệt đơn nghỉ" flowable:formKey="nghi-phep.duyet"
              flowable:candidateGroups="t:${tenantId}:d:${departmentId}:manager,t:${tenantId}:director"
              flowable:dueDate="P2D">
      <documentation>Xem đơn, đồng ý hoặc từ chối.</documentation>
    </userTask>
    <sequenceFlow id="f2" sourceRef="duyet" targetRef="ketQua"/>
    <exclusiveGateway id="ketQua" name="Đồng ý?" default="f4"/>
    <sequenceFlow id="f3" name="Đồng ý" sourceRef="ketQua" targetRef="dongY">
      <conditionExpression xsi:type="tFormalExpression"><![CDATA[${quyetDinh == 'dong-y'}]]></conditionExpression>
    </sequenceFlow>
    <sequenceFlow id="f4" sourceRef="ketQua" targetRef="xemLai"/>
    <userTask id="xemLai" name="Xem kết quả" flowable:formKey="nghi-phep.duyet" flowable:assignee="${initiator}"/>
    <sequenceFlow id="f5" sourceRef="xemLai" targetRef="tuChoi"/>
    <endEvent id="dongY" name="Đã duyệt"/>
    <endEvent id="tuChoi" name="Bị từ chối"/>
  </process>
  <bpmndi:BPMNDiagram id="soDo">
    <bpmndi:BPMNPlane id="mat" bpmnElement="nghi-phep.don">
      <bpmndi:BPMNShape id="hGui" bpmnElement="gui"><dc:Bounds x="10" y="10" width="30" height="30"/></bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="hF1" bpmnElement="f1">
        <di:waypoint x="40" y="25"/><di:waypoint x="100.5" y="25"/>
        <bpmndi:BPMNLabel><dc:Bounds x="50" y="5" width="20" height="10"/></bpmndi:BPMNLabel>
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</definitions>
"""


def form_bytes(schema: dict[str, Any]) -> bytes:
    return json.dumps(schema, ensure_ascii=False, indent=2).encode()


def bundle_zip(bpmn: str = BPMN, *, don: dict[str, Any] | None = None, duyet: dict[str, Any] | None = None,
               extra_processes: dict[str, bytes] | None = None, app: str = APP) -> bytes:
    """Gói như moc app install dựng: processes/don.bpmn20.xml, forms/don.json, forms/duyet.json."""
    return make_zip(app, {"processes/don.bpmn20.xml": bpmn.encode(), **(extra_processes or {})},
                    {f"{app}.don": ("forms/don.json", form_bytes(don or DON)),
                     f"{app}.duyet": ("forms/duyet.json", form_bytes(duyet or DUYET))})


class AppFlowable:
    """Flowable giả đủ cho deploy.py và api.py: deployment, tài nguyên, định nghĩa (phiên bản, tạm dừng), phiên quy
    trình, việc và lịch sử."""

    def __init__(self) -> None:
        self.deployed: list[dict[str, Any]] = []
        self.resources: dict[tuple[str, str], bytes] = {}
        self.defs: dict[str, dict[str, Any]] = {}
        self.instances: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, Task] = {}
        self.groups: dict[str, list[str]] = {}
        self.started: list[tuple[str, list[dict[str, Any]]]] = []
        self.claims: list[tuple[str, str | None]] = []
        self.completed: list[tuple[str, list[dict[str, Any]]]] = []
        self.queries: list[dict[str, Any]] = []
        self.down = False
        self.claim_conflict = False
        self.gone_on_complete = False
        self.n = 0

    def _next(self) -> int:
        self.n += 1
        return self.n

    async def aclose(self) -> None: ...

    def _check(self) -> None:
        if self.down:
            raise FlowableError("down")

    async def deployments(self, name_like: str, *, size: int = 1) -> list[dict[str, Any]]:
        self._check()
        prefix = name_like.rstrip("%")
        rows = [d for d in self.deployed if d["name"].startswith(prefix)]
        return sorted(rows, key=lambda d: d["deployTime"], reverse=True)[:size]

    async def deploy_zip(self, name: str, filename: str, content: bytes) -> dict[str, Any]:
        self._check()
        n = self._next()
        dep = {"id": f"dep-{n}", "name": name, "deployTime": f"2026-10-26T10:00:{n:02d}.000+07:00"}
        self.deployed.append(dep)
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for res in zf.namelist():
                self.resources[(dep["id"], res)] = zf.read(res)
                if res.endswith(".bpmn20.xml"):
                    key = res.removesuffix(".bpmn20.xml")
                    version = 1 + sum(1 for d in self.defs.values() if d["key"] == key)
                    did = f"{key}:{version}:{dep['id']}"
                    self.defs[did] = {"id": did, "key": key, "version": version, "deploymentId": dep["id"],
                                      "suspended": False}
        return dep

    async def resource(self, deployment_id: str, name: str) -> bytes | None:
        self._check()
        return self.resources.get((deployment_id, name))

    async def definitions(self, **params: Any) -> list[dict[str, Any]]:
        self._check()
        rows = list(self.defs.values())
        if "deploymentId" in params:
            rows = [r for r in rows if r["deploymentId"] == params["deploymentId"]]
        if "key" in params:
            rows = [r for r in rows if r["key"] == params["key"]]
        if "keyLike" in params:
            rows = [r for r in rows if r["key"].startswith(params["keyLike"].rstrip("%"))]
        if "suspended" in params:
            rows = [r for r in rows if str(r["suspended"]).lower() == params["suspended"]]
        return [dict(r) for r in rows]

    async def definition(self, definition_id: str) -> dict[str, Any] | None:
        self._check()
        return dict(self.defs[definition_id]) if definition_id in self.defs else None

    async def set_definition_state(self, definition_id: str, action: str) -> None:
        self.defs[definition_id]["suspended"] = action == "suspend"

    async def start_definition(self, definition_id: str, variables: list[dict[str, Any]]) -> str:
        self._check()
        pid = f"proc-{self._next()}"
        self.started.append((definition_id, variables))
        self.instances[pid] = {"id": pid, "processDefinitionId": definition_id, "endTime": None,
                               "startTime": f"2026-10-26T09:{self.n:02d}:00.000+07:00",
                               "variables": {v["name"]: v["value"] for v in variables}}
        return pid

    def add_task(self, task_id: str, process: str, form_key: str = f"{APP}.duyet", *, assignee: str | None = None,
                 groups: list[str] | None = None, created: str = "2026-10-26T09:30:00.000+07:00",
                 due: str | None = None) -> None:
        inst = self.instances[process]
        self.tasks[task_id] = Task(task_id, "Duyệt đơn nghỉ", form_key, assignee, process, created,
                                   dict(inst["variables"]), process_definition_id=inst["processDefinitionId"],
                                   due_at=due)
        self.groups[task_id] = groups or []

    async def query_tasks(self, query: dict[str, Any]) -> list[Task]:
        self._check()
        self.queries.append(query)
        prefix = query.get("processDefinitionKeyLike", "%").rstrip("%")
        out = []
        for t in self.tasks.values():
            if not t.process_key.startswith(prefix):
                continue
            if "assignee" in query and t.assignee != query["assignee"]:
                continue
            if "candidateGroupIn" in query and (t.assignee is not None
                                                or not set(self.groups[t.id]) & set(query["candidateGroupIn"])):
                continue
            out.append(t)
        return out

    async def historic_processes(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        self._check()
        self.queries.append(query)
        out = []
        for inst in self.instances.values():
            if inst["processDefinitionId"].split(":")[0] != query["processDefinitionKey"]:
                continue
            if any(inst["variables"].get(v["name"]) != v["value"] for v in query.get("variables", [])):
                continue
            out.append({**inst, "variables": [{"name": k, "value": v, "scope": "local"}
                                              for k, v in inst["variables"].items()]})
        return out

    async def task(self, task_id: str) -> Task | None:
        self._check()
        return self.tasks.get(task_id)

    async def candidate_groups(self, task_id: str) -> list[str]:
        return self.groups.get(task_id, [])

    async def claim(self, task_id: str, user_id: str | None) -> None:
        if self.claim_conflict and user_id:
            raise FlowableError("taken", 409)
        self.claims.append((task_id, user_id))

    async def complete_typed(self, task_id: str, variables: list[dict[str, Any]]) -> None:
        if self.gone_on_complete:
            raise FlowableError("gone", 404)
        self._check()
        self.completed.append((task_id, variables))
        task = self.tasks.pop(task_id)
        self.instances[task.process_instance_id]["variables"].update({v["name"]: v["value"] for v in variables})
