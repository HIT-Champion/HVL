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

"""Kiểm BPMN của ứng dụng theo DANH SÁCH TRẮNG trước khi triển khai lên Flowable của lõi.

BPMN của ứng dụng chạy trong cùng động cơ với quy trình Văn phòng điện tử, bằng quyền của động cơ: scriptTask chạy
mã, serviceTask gọi lớp Java hay bean, listener chạy khi qua một bước, và biểu thức ``${…}`` (JUEL) gọi được phương
thức của mọi đối tượng trong ngữ cảnh — ``${execution.getEngineServices()…}`` là đọc, sửa được quy trình của đơn vị
khác. Flowable còn tính biểu thức ở tên việc, mô tả (documentation), formKey, hạn, người được giao. Nên chỉ nhận đúng
những gì một quy trình duyệt cần, mọi thứ khác bị từ chối kèm dòng và phần tử:

- phần tử: definitions, process, startEvent, endEvent, userTask, exclusiveGateway, parallelGateway, sequenceFlow,
  conditionExpression, documentation, và phần sơ đồ (bpmndi, dc, di) — không extensionElements, listener, timer,
  message, script, service, call activity, sub process…;
- thuộc tính: chỉ các thuộc tính liệt kê cho từng phần tử, giá trị theo mẫu hẹp; ``${`` và ``#{`` không được có ở bất
  cứ đâu ngoài ba chỗ dưới đây;
- conditionExpression: ``${bien == 'chuoi'}``, ``!=``, nối bằng ``&&`` hoặc ``||`` — biến là trường của form, không
  gọi hàm, không thuộc tính, không ngoặc;
- userTask: ``flowable:formKey`` bắt buộc, có tiền tố ``<tên app>.``, có trong manifest; ``flowable:candidateGroups``
  chỉ ``t:${tenantId}:<vai trò>`` hoặc ``t:${tenantId}:d:${departmentId}:<vai trò>`` (vai trò của realm);
  ``flowable:assignee`` chỉ ``${initiator}``; ``flowable:dueDate`` chỉ một khoảng ISO 8601 viết sẵn (P3D, PT24H);
- startEvent: đúng một, ``flowable:formKey`` bắt buộc, ``flowable:initiator`` chỉ được là ``initiator``.

DOCTYPE, ENTITY bị chặn trước khi phân tích (thực thể ngoài đọc được tệp của máy chủ, thực thể lồng làm nổ bộ nhớ).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from xml.parsers import expat

from ..directory import ROLES

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC = "http://www.omg.org/spec/DD/20100524/DC"
DI = "http://www.omg.org/spec/DD/20100524/DI"
FLOWABLE = "http://flowable.org/bpmn"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
PREFIX = {BPMN: "", BPMNDI: "bpmndi:", DC: "dc:", DI: "di:", FLOWABLE: "flowable:", XSI: "xsi:",
          "http://activiti.org/bpmn": "activiti:"}
MAX_BPMN_BYTES = 512 * 1024
# Flowable đặt id định nghĩa quy trình "<khóa>:<phiên bản>:<uuid 36 ký tự>"; chuỗi đó quá 64 ký tự thì id chỉ còn uuid,
# mất khóa — lõi không còn biết việc, đơn thuộc ứng dụng nào (Task.process_key), đơn vào mà không ai thấy. 22 ký tự
# vừa tới phiên bản 9999: 22 + 1 + 4 + 1 + 36 = 64
MAX_KEY = 22

NAME = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", re.ASCII)              # như name của manifest
ELEMENT_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", re.ASCII)
NUMBER = re.compile(r"-?[0-9]{1,7}(\.[0-9]{1,6})?", re.ASCII)
DURATION = re.compile(r"P(?=[0-9T])([0-9]{1,4}D)?(T(?=[0-9])([0-9]{1,4}H)?([0-9]{1,4}M)?)?", re.ASCII)
VARIABLE = re.compile(r"[a-z][A-Za-z0-9]{0,63}", re.ASCII)
COMPARE = re.compile(r"\s*([a-z][A-Za-z0-9]{0,63})\s*(==|!=)\s*'([^'\\$#{}]{0,100})'\s*", re.ASCII)
JOIN = re.compile(r"\s*(&&|\|\|)\s*", re.ASCII)
EXPRESSION = ("${", "#{")
FREE_TEXT = re.compile(r"[^\x00-\x08\x0b\x0c\x0e-\x1f]{0,2000}")


def key_pattern(app: str) -> re.Pattern[str]:
    """Process id (= processKey), formKey của ứng dụng: ``<tên app>.<tên>``."""
    return re.compile(re.escape(app) + r"\.[a-z][a-z0-9]*(-[a-z0-9]+)*", re.ASCII)


def group_pattern() -> re.Pattern[str]:
    roles = "|".join(sorted(ROLES))
    return re.compile(r"t:\$\{tenantId\}:(?:d:\$\{departmentId\}:)?(?:" + roles + ")", re.ASCII)


GROUP = group_pattern()


@dataclass
class Node:
    ns: str
    tag: str
    attrs: dict[str, str]
    line: int
    children: list[Node] = field(default_factory=list)
    text: str = ""

    @property
    def label(self) -> str:
        return f"<{PREFIX.get(self.ns, '{' + self.ns + '}')}{self.tag}>"


@dataclass
class Process:
    """Một process đã kiểm: khóa, form của sự kiện bắt đầu, form của các việc, biến các điều kiện dùng."""

    key: str
    name: str
    start_form: str
    task_forms: list[str]
    condition_variables: set[str]


class BpmnError(Exception):
    pass


def parse(raw: bytes) -> Node:
    """Đọc XML bằng expat, giữ số dòng của từng phần tử. Không DOCTYPE, ENTITY, chỉ thị xử lý."""
    if len(raw) > MAX_BPMN_BYTES:
        raise BpmnError(f"tệp lớn quá {MAX_BPMN_BYTES // 1024} KB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BpmnError(f"không phải UTF-8 ({exc})") from None
    declaration = re.match(r"\ufeff?<\?xml[^>]*\?>", text)
    if declaration and not re.search(r"encoding\s*=\s*[\"']utf-8[\"']", declaration.group(0), re.I) \
            and "encoding" in declaration.group(0):
        raise BpmnError("chỉ nhận XML mã hóa UTF-8")
    upper = text.upper()
    for bad in ("<!DOCTYPE", "<!ENTITY"):
        if bad in upper:
            line = upper[:upper.index(bad)].count("\n") + 1
            raise BpmnError(f"dòng {line}: không được có {bad} (thực thể XML đọc được tệp của máy chủ)")
    rest = text[declaration.end():] if declaration else text
    if "<?" in rest:
        line = text[:text.index("<?", len(text) - len(rest))].count("\n") + 1
        raise BpmnError(f"dòng {line}: không được có chỉ thị xử lý <?…?>")

    parser = expat.ParserCreate("UTF-8", " ")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    root: list[Node] = []
    stack: list[Node] = []

    def refuse(*_args: Any) -> None:
        raise BpmnError(f"dòng {parser.CurrentLineNumber}: không được có DOCTYPE, ENTITY")

    def start(name: str, attrs: dict[str, str]) -> None:
        ns, _, tag = name.rpartition(" ")
        node = Node(ns, tag, dict(attrs), parser.CurrentLineNumber)
        (stack[-1].children if stack else root).append(node)
        stack.append(node)

    def end(_name: str) -> None:
        stack.pop()

    def chars(data: str) -> None:
        if stack:
            stack[-1].text += data

    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.ExternalEntityRefHandler = refuse
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    try:
        parser.Parse(raw, True)
    except expat.ExpatError as exc:
        raise BpmnError(f"dòng {exc.lineno}: XML sai ({expat.errors.messages[exc.code]})") from None
    return root[0]


def _attr_name(name: str) -> str:
    ns, _, local = name.rpartition(" ")
    return f"{PREFIX.get(ns, '{' + ns + '}') if ns else ''}{local}"


def _expression_free(value: str) -> bool:
    return not any(mark in value for mark in EXPRESSION)


def check_condition(text: str, fields: set[str]) -> tuple[set[str], str | None]:
    """``${a == 'x' && b != 'y'}`` → (biến dùng, None) hoặc (…, lý do sai)."""
    body = text.strip()
    if not (body.startswith("${") and body.endswith("}")) or body.count("${") != 1:
        return set(), "điều kiện phải có dạng ${bien == 'chuoi'}"
    inner, used, pos = body[2:-1], set(), 0
    while True:
        m = COMPARE.match(inner, pos)
        if not m:
            return used, ("điều kiện chỉ nhận so sánh bien == 'chuoi' hoặc bien != 'chuoi', nối bằng && hoặc || "
                          "(không gọi hàm, không thuộc tính, không ngoặc)")
        used.add(m.group(1))
        pos = m.end()
        if pos == len(inner):
            break
        j = JOIN.match(inner, pos)
        if not j:
            return used, "giữa hai so sánh chỉ được && hoặc ||"
        pos = j.end()
    unknown = sorted(used - fields)
    if unknown:
        return used, f"biến {', '.join(unknown)} không phải trường của form nào trong manifest"
    return used, None


# Thuộc tính được phép của từng phần tử: tên → hàm kiểm giá trị (None: hợp lệ, chuỗi: lý do sai)
Check = Any


class _Checker:
    def __init__(self, app: str, where: str, forms: set[str], fields: set[str]) -> None:
        self.app, self.where, self.forms, self.fields = app, where, forms, fields
        self.key = key_pattern(app)
        self.errors: list[str] = []
        self.ids: dict[str, Node] = {}

    def err(self, node: Node, message: str) -> None:
        self.errors.append(f"{self.where} dòng {node.line}: {node.label} {message}")

    # --- giá trị thuộc tính -----------------------------------------------------------------------------
    def _id(self, v: str) -> str | None:
        return None if ELEMENT_ID.fullmatch(v) else "id chỉ gồm chữ, số, _ . - (≤ 64 ký tự)"

    def _text(self, v: str) -> str | None:
        if not _expression_free(v):
            return "không được chứa biểu thức ${…} hoặc #{…} (Flowable tính biểu thức ở đây)"
        return None if FREE_TEXT.fullmatch(v) else "dài quá 2000 ký tự hoặc có ký tự điều khiển"

    def _number(self, v: str) -> str | None:
        return None if NUMBER.fullmatch(v) else "phải là một số"

    def _bool(self, v: str) -> str | None:
        return None if v in ("true", "false") else "chỉ nhận true hoặc false"

    def _executable(self, v: str) -> str | None:
        return None if v == "true" else "isExecutable phải là true"

    def _form_key(self, v: str) -> str | None:
        if not self.key.fullmatch(v):
            return f"formKey phải dạng {self.app}.<tên> (chữ thường, số, gạch nối)"
        if v not in self.forms:
            return f"formKey {v} không có trong workflow.forms của manifest"
        return None

    def _groups(self, v: str) -> str | None:
        bad = [g for g in v.split(",") if not GROUP.fullmatch(g)]
        if bad:
            return (f"candidateGroups {', '.join(bad)} không hợp lệ: chỉ t:${{tenantId}}:<vai trò> hoặc "
                    f"t:${{tenantId}}:d:${{departmentId}}:<vai trò>, vai trò trong {', '.join(sorted(ROLES))}, "
                    "cách nhau bằng dấu phẩy, không khoảng trắng")
        return None

    def _assignee(self, v: str) -> str | None:
        return None if v == "${initiator}" else "assignee chỉ được là ${initiator} (người gửi đơn)"

    def _initiator(self, v: str) -> str | None:
        return None if v == "initiator" else "flowable:initiator chỉ được là initiator"

    def _due(self, v: str) -> str | None:
        return None if DURATION.fullmatch(v) else "dueDate chỉ nhận một khoảng ISO 8601 viết sẵn, vd P3D, PT24H"

    def _fixed(self, *values: str) -> Check:
        return lambda v: None if v in values else f"chỉ nhận {' hoặc '.join(values)}"

    def _ref(self, v: str) -> str | None:
        return self._id(v)

    def allowed(self, node: Node) -> dict[str, Check] | None:
        """Thuộc tính được phép của phần tử; None: phần tử không có trong danh sách trắng."""
        named = {"id": self._id, "name": self._text}
        table: dict[tuple[str, str], dict[str, Check]] = {
            (BPMN, "definitions"): {"id": self._id, "name": self._text, "targetNamespace": self._text,
                                    "exporter": self._text, "exporterVersion": self._text,
                                    "typeLanguage": self._fixed("http://www.w3.org/2001/XMLSchema"),
                                    "expressionLanguage": self._fixed("http://www.w3.org/1999/XPath")},
            (BPMN, "process"): {**named, "isExecutable": self._executable},
            (BPMN, "documentation"): {"id": self._id, "textFormat": self._fixed("text/plain")},
            (BPMN, "startEvent"): {**named, f"{FLOWABLE} formKey": self._form_key,
                                   f"{FLOWABLE} initiator": self._initiator},
            (BPMN, "endEvent"): named,
            (BPMN, "userTask"): {**named, f"{FLOWABLE} formKey": self._form_key,
                                 f"{FLOWABLE} candidateGroups": self._groups, f"{FLOWABLE} assignee": self._assignee,
                                 f"{FLOWABLE} dueDate": self._due},
            (BPMN, "exclusiveGateway"): {**named, "default": self._ref},
            (BPMN, "parallelGateway"): named,
            (BPMN, "sequenceFlow"): {**named, "sourceRef": self._ref, "targetRef": self._ref},
            (BPMN, "conditionExpression"): {"id": self._id, f"{XSI} type": self._fixed("tFormalExpression")},
            (BPMNDI, "BPMNDiagram"): named,
            (BPMNDI, "BPMNPlane"): {"id": self._id, "bpmnElement": self._ref},
            (BPMNDI, "BPMNShape"): {"id": self._id, "bpmnElement": self._ref, "isExpanded": self._bool,
                                    "isHorizontal": self._bool, "isMarkerVisible": self._bool},
            (BPMNDI, "BPMNEdge"): {"id": self._id, "bpmnElement": self._ref, "sourceElement": self._ref,
                                   "targetElement": self._ref},
            (BPMNDI, "BPMNLabel"): {"id": self._id},
            (DC, "Bounds"): {"x": self._number, "y": self._number, "width": self._number, "height": self._number},
            (DI, "waypoint"): {"x": self._number, "y": self._number},
        }
        return table.get((node.ns, node.tag))

    CHILDREN: dict[tuple[str, str], set[tuple[str, str]]] = {
        (BPMN, "definitions"): {(BPMN, "process"), (BPMN, "documentation"), (BPMNDI, "BPMNDiagram")},
        (BPMN, "process"): {(BPMN, t) for t in ("documentation", "startEvent", "endEvent", "userTask",
                                                 "exclusiveGateway", "parallelGateway", "sequenceFlow")},
        (BPMN, "sequenceFlow"): {(BPMN, "documentation"), (BPMN, "conditionExpression")},
        (BPMNDI, "BPMNDiagram"): {(BPMNDI, "BPMNPlane")},
        (BPMNDI, "BPMNPlane"): {(BPMNDI, "BPMNShape"), (BPMNDI, "BPMNEdge")},
        (BPMNDI, "BPMNShape"): {(DC, "Bounds"), (BPMNDI, "BPMNLabel")},
        (BPMNDI, "BPMNEdge"): {(DI, "waypoint"), (BPMNDI, "BPMNLabel")},
        (BPMNDI, "BPMNLabel"): {(DC, "Bounds")},
    }
    FLOW_NODES = ("startEvent", "endEvent", "userTask", "exclusiveGateway", "parallelGateway")
    WITH_DOCS = {(BPMN, t) for t in FLOW_NODES}
    TEXT_ALLOWED = {(BPMN, "documentation"), (BPMN, "conditionExpression")}

    def walk(self, node: Node, parent: Node | None = None) -> None:
        attrs = self.allowed(node)
        if attrs is None:
            where = f" trong {parent.label}" if parent else ""
            self.err(node, f"không được phép{where} — BPMN của ứng dụng chỉ gồm sự kiện bắt đầu/kết thúc, userTask, "
                           "cổng rẽ nhánh và luồng (docs/them-ung-dung.md, mục quy trình)")
            return
        for name, value in node.attrs.items():
            check = attrs.get(name)
            if check is None:
                self.err(node, f"không được có thuộc tính {_attr_name(name)}")
                continue
            problem = check(value)
            if problem is None and name not in (f"{FLOWABLE} candidateGroups", f"{FLOWABLE} assignee") \
                    and not _expression_free(value):
                problem = "không được chứa biểu thức ${…} hoặc #{…}"
            if problem:
                self.err(node, problem)
        if "id" in node.attrs and node.ns == BPMN and ELEMENT_ID.fullmatch(node.attrs["id"]):
            if node.attrs["id"] in self.ids:
                self.err(node, f"trùng id {node.attrs['id']} (dòng {self.ids[node.attrs['id']].line})")
            self.ids[node.attrs["id"]] = node
        if node.text.strip() and (node.ns, node.tag) not in self.TEXT_ALLOWED:
            self.err(node, "không được có nội dung chữ")
        if (node.ns, node.tag) == (BPMN, "documentation") and (problem := self._text(node.text.strip())):
            self.err(node, problem)
        children = self.CHILDREN.get((node.ns, node.tag), set())
        if (node.ns, node.tag) in self.WITH_DOCS:
            children = {(BPMN, "documentation")}
        for child in node.children:
            if (child.ns, child.tag) not in children and self.allowed(child) is not None:
                self.err(child, f"không được nằm trong {node.label}")
                continue
            self.walk(child, node)


def check(app: str, where: str, raw: bytes, forms: set[str], fields: set[str]) -> tuple[Process | None, list[str]]:
    """Một tệp BPMN của ứng dụng → (process, []) hoặc (None, lỗi tiếng Việt kèm dòng, phần tử).

    forms: formKey khai trong manifest; fields: tên trường của mọi form (biến điều kiện được dùng)."""
    if not NAME.fullmatch(app):
        return None, [f"tên ứng dụng {app!r} không hợp lệ"]
    try:
        root = parse(raw)
    except BpmnError as exc:
        return None, [f"{where}: {exc}"]
    c = _Checker(app, where, forms, fields)
    if (root.ns, root.tag) != (BPMN, "definitions"):
        return None, [f"{where} dòng {root.line}: gốc phải là <definitions> của BPMN 2.0 ({BPMN})"]
    c.walk(root)
    processes = [n for n in root.children if (n.ns, n.tag) == (BPMN, "process")]
    if len(processes) != 1:
        c.errors.append(f"{where}: cần đúng một <process> trong mỗi tệp (đang có {len(processes)})")
        return None, c.errors
    proc = processes[0]
    key = proc.attrs.get("id", "")
    if not c.key.fullmatch(key):
        c.err(proc, f"id {key!r} phải dạng {app}.<tên> (chữ thường, số, gạch nối) — id là processKey")
    elif len(key) > MAX_KEY:
        c.err(proc, f"id {key!r} dài {len(key)} ký tự, tối đa {MAX_KEY}: Flowable bỏ khóa khỏi id định nghĩa khi "
                    "<khóa>:<phiên bản>:<uuid> quá 64 ký tự, lõi không còn biết việc thuộc ứng dụng nào")
    nodes = [n for n in proc.children if n.ns == BPMN and n.tag in _Checker.FLOW_NODES]
    starts = [n for n in nodes if n.tag == "startEvent"]
    if len(starts) != 1:
        c.err(proc, f"cần đúng một <startEvent> (đang có {len(starts)}) — API bắt đầu quy trình theo form của nó")
    elif f"{FLOWABLE} formKey" not in starts[0].attrs:
        c.err(starts[0], "thiếu flowable:formKey — form của đơn gửi lúc bắt đầu")
    if not any(n.tag == "endEvent" for n in nodes):
        c.err(proc, "cần ít nhất một <endEvent>")
    for task in (n for n in nodes if n.tag == "userTask"):
        if f"{FLOWABLE} formKey" not in task.attrs:
            c.err(task, "thiếu flowable:formKey")
        if f"{FLOWABLE} candidateGroups" not in task.attrs and f"{FLOWABLE} assignee" not in task.attrs:
            c.err(task, "cần flowable:candidateGroups hoặc flowable:assignee — không thì không ai thấy việc")
    node_ids = {n.attrs.get("id") for n in nodes}
    flows = [n for n in proc.children if (n.ns, n.tag) == (BPMN, "sequenceFlow")]
    flow_ids = {f.attrs.get("id") for f in flows}
    used: set[str] = set()
    for flow in flows:
        for ref in ("sourceRef", "targetRef"):
            if flow.attrs.get(ref) not in node_ids:
                c.err(flow, f"{ref} {flow.attrs.get(ref)!r} không trỏ tới bước nào của process")
        for cond in (ch for ch in flow.children if (ch.ns, ch.tag) == (BPMN, "conditionExpression")):
            found, problem = check_condition(cond.text, fields)
            used |= found
            if problem:
                c.err(cond, problem)
    for gw in (n for n in nodes if n.tag == "exclusiveGateway" and "default" in n.attrs):
        if gw.attrs["default"] not in flow_ids:
            c.err(gw, f"default {gw.attrs['default']!r} không phải sequenceFlow của process")
    if c.errors:
        return None, c.errors
    return Process(key=key, name=proc.attrs.get("name", ""), start_form=starts[0].attrs[f"{FLOWABLE} formKey"],
                   task_forms=[n.attrs[f"{FLOWABLE} formKey"] for n in nodes if n.tag == "userTask"],
                   condition_variables=used), []
