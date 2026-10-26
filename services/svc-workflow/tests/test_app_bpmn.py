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

"""Kiểm BPMN của ứng dụng theo danh sách trắng (apps/bpmn.py): mẫu hợp lệ và các ca độc — mã chạy trong động cơ,
biểu thức JUEL, nhóm ứng viên lạ, tiền tố của ứng dụng khác, thực thể XML."""

from __future__ import annotations

from pathlib import Path

import pytest

from app_fakes import APP, BPMN, DON, DUYET
from svc_workflow.apps.bpmn import check, check_condition

ROOT = Path(__file__).resolve().parents[3]
WHERE = "processes/don.bpmn20.xml"
FORMS = {f"{APP}.don", f"{APP}.duyet"}
FIELDS = set(DON["properties"]) | set(DUYET["properties"])
USER_TASK = ('<userTask id="duyet" name="Duyệt đơn nghỉ" flowable:formKey="nghi-phep.duyet"\n'
             '              flowable:candidateGroups="t:${tenantId}:d:${departmentId}:manager,t:${tenantId}:director"\n'
             '              flowable:dueDate="P2D">')
CONDITION = "${quyetDinh == 'dong-y'}"
END = '<endEvent id="tuChoi" name="Bị từ chối"/>'


def errors_of(text: str) -> list[str]:
    proc, errors = check(APP, WHERE, text.encode(), FORMS, FIELDS)
    assert (proc is None) == bool(errors)
    return errors


def swap(old: str, new: str) -> str:
    assert old in BPMN, old
    return BPMN.replace(old, new, 1)


def after_end(xml: str) -> str:
    """Chèn thêm phần tử vào process, ngay sau sự kiện kết thúc cuối."""
    return swap(END, END + "\n    " + xml)


def test_sample_process_passes():
    proc, errors = check(APP, WHERE, BPMN.encode(), FORMS, FIELDS)
    assert errors == []
    assert proc is not None and proc.key == "nghi-phep.don" and proc.name == "Xin nghỉ phép"
    assert proc.start_form == "nghi-phep.don" and proc.task_forms == ["nghi-phep.duyet", "nghi-phep.duyet"]
    assert proc.condition_variables == {"quyetDinh"}


@pytest.mark.parametrize("xml, needle", [
    # mã chạy trong động cơ
    (after_end('<scriptTask id="s" scriptFormat="groovy"><script>Runtime.exec("id")</script></scriptTask>'),
     "<scriptTask> không được phép"),
    (after_end('<serviceTask id="s" flowable:class="org.example.Evil"/>'), "<serviceTask> không được phép"),
    (after_end('<serviceTask id="s" flowable:expression="${execution.getEngineServices()}"/>'),
     "<serviceTask> không được phép"),
    (after_end('<businessRuleTask id="s"/>'), "<businessRuleTask> không được phép"),
    (after_end('<sendTask id="s"/>'), "<sendTask> không được phép"),
    (after_end('<receiveTask id="s"/>'), "<receiveTask> không được phép"),
    (after_end('<callActivity id="s" calledElement="van-ban-den"/>'), "<callActivity> không được phép"),
    (after_end('<subProcess id="s"/>'), "<subProcess> không được phép"),
    (after_end('<boundaryEvent id="b" attachedToRef="duyet"><timerEventDefinition/></boundaryEvent>'),
     "<boundaryEvent> không được phép"),
    (swap('flowable:initiator="initiator"/>',
          'flowable:initiator="initiator"><timerEventDefinition><timeCycle>R/PT1S</timeCycle>'
          '</timerEventDefinition></startEvent>'), "<timerEventDefinition> không được phép trong <startEvent>"),
    (swap(USER_TASK, USER_TASK + '<extensionElements><flowable:taskListener event="create" '
                                 'class="org.example.Evil"/></extensionElements>'),
     "<extensionElements> không được phép"),
    (swap(USER_TASK, USER_TASK + '<flowable:executionListener event="start" expression="${x}"/>'),
     "<flowable:executionListener> không được phép"),
    (after_end('<ext:thing xmlns:ext="urn:la"/>'), "<{urn:la}thing> không được phép"),
    # thuộc tính lạ của Flowable (và của Activiti — Flowable cũng hiểu)
    (swap('<userTask id="duyet"', '<userTask flowable:class="org.example.Evil" id="duyet"'),
     "không được có thuộc tính flowable:class"),
    (swap('<userTask id="duyet"', '<userTask flowable:delegateExpression="${bean}" id="duyet"'),
     "không được có thuộc tính flowable:delegateExpression"),
    (swap('<sequenceFlow id="f1"', '<sequenceFlow flowable:skipExpression="${true}" id="f1"'),
     "không được có thuộc tính flowable:skipExpression"),
    (swap('<userTask id="duyet"', '<userTask flowable:resultVariable="x" id="duyet"'),
     "không được có thuộc tính flowable:resultVariable"),
    (swap('<userTask id="duyet"', '<userTask xmlns:activiti="http://activiti.org/bpmn" '
                                  'activiti:expression="${x}" id="duyet"'),
     "không được có thuộc tính activiti:expression"),
    (swap('<userTask id="duyet"', '<userTask flowable:category="x" id="duyet"'),
     "không được có thuộc tính flowable:category"),
    # biểu thức JUEL ngoài ba chỗ hẹp
    (swap(CONDITION, "${quyetDinh.getClass().forName('java.lang.Runtime')}"), "điều kiện chỉ nhận so sánh"),
    (swap(CONDITION, "${execution.getEngineServices().getRuntimeService() != null}"), "điều kiện chỉ nhận"),
    (swap(CONDITION, "${quyetDinh == 'dong-y' or true}"), "giữa hai so sánh chỉ được && hoặc ||"),
    (swap(CONDITION, "${(quyetDinh == 'dong-y')}"), "điều kiện chỉ nhận"),
    (swap(CONDITION, "${quyetDinh == 'a${x}'}"), "điều kiện phải có dạng"),
    (swap(CONDITION, "#{quyetDinh == 'dong-y'}"), "điều kiện phải có dạng"),
    (swap(CONDITION, "${khongCo == 'x'}"), "biến khongCo không phải trường"),
    (swap('name="Duyệt đơn nghỉ"', 'name="${execution.getVariable(\'x\')}"'), "không được chứa biểu thức"),
    (swap('name="Xin nghỉ phép"', 'name="#{1+1}"'), "không được chứa biểu thức"),
    (swap("<documentation>Xem đơn, đồng ý hoặc từ chối.</documentation>",
          "<documentation>${execution.getEngineServices()}</documentation>"), "không được chứa biểu thức"),
    (swap('targetNamespace="https://signet.example/nghi-phep"', 'targetNamespace="${x}"'),
     "không được chứa biểu thức"),
    (swap('flowable:dueDate="P2D"', 'flowable:dueDate="${hanXuLy}"'), "dueDate chỉ nhận"),
    (swap('flowable:dueDate="P2D"', 'flowable:dueDate="2026-12-31"'), "dueDate chỉ nhận"),
    # ai được giao việc
    (swap("t:${tenantId}:director", "t:${tenantId}:admin"), "candidateGroups t:${tenantId}:admin không hợp lệ"),
    (swap("t:${tenantId}:director", "t:c300d5bb-028f-44cc-ba10-7b5277a4225d:director"), "candidateGroups"),
    (swap("t:${tenantId}:director", "${nhom}"), "candidateGroups"),
    (swap("t:${tenantId}:director", "t:${tenantId.toString()}:director"), "candidateGroups"),
    (swap("t:${tenantId}:director", " t:${tenantId}:director"), "candidateGroups"),
    (swap('flowable:assignee="${initiator}"', 'flowable:assignee="kermit"'), "assignee chỉ được là ${initiator}"),
    (swap('flowable:assignee="${initiator}"', 'flowable:assignee="${nguoiDuyet}"'), "assignee chỉ được là"),
    (swap('flowable:initiator="initiator"', 'flowable:initiator="tenantId"'), "flowable:initiator chỉ được là"),
    # tiền tố của ứng dụng, form trong manifest
    (swap('<process id="nghi-phep.don"', '<process id="don"'), "id 'don' phải dạng nghi-phep.<tên>"),
    (swap('<process id="nghi-phep.don"', '<process id="van-ban-den"'), "phải dạng nghi-phep.<tên>"),
    (swap('<process id="nghi-phep.don"', '<process id="nghi-phep-khac.don"'), "phải dạng nghi-phep.<tên>"),
    (swap('flowable:formKey="nghi-phep.duyet"\n', 'flowable:formKey="vbden.chiDao"\n'),
     "formKey phải dạng nghi-phep.<tên>"),
    (swap('flowable:formKey="nghi-phep.duyet"\n', 'flowable:formKey="nghi-phep.khac"\n'),
     "formKey nghi-phep.khac không có trong workflow.forms"),
    (swap('flowable:formKey="nghi-phep.duyet"\n', ""), "thiếu flowable:formKey"),
    (swap(' flowable:formKey="nghi-phep.don"', ""), "thiếu flowable:formKey — form của đơn"),
    (swap(' flowable:assignee="${initiator}"', ""), "cần flowable:candidateGroups hoặc flowable:assignee"),
    # cấu trúc
    (after_end('<startEvent id="gui2" flowable:formKey="nghi-phep.don"/>'), "cần đúng một <startEvent> (đang có 2)"),
    (swap('<endEvent id="dongY" name="Đã duyệt"/>', "").replace(END, "")
     .replace('targetRef="dongY"', 'targetRef="xemLai"').replace('targetRef="tuChoi"', 'targetRef="xemLai"'),
     "cần ít nhất một <endEvent>"),
    (swap('targetRef="duyet"', 'targetRef="khongCo"'), "targetRef 'khongCo' không trỏ tới bước nào"),
    (swap('default="f4"', 'default="duyet"'), "default 'duyet' không phải sequenceFlow"),
    (swap('<endEvent id="dongY"', '<endEvent id="gui"'), "trùng id gui"),
    (swap('<userTask id="duyet"', '<userTask id="duyet làm"'), "id chỉ gồm chữ, số"),
    (swap('isExecutable="true"', 'isExecutable="false"'), "isExecutable phải là true"),
    (swap('xsi:type="tFormalExpression"', 'xsi:type="tFormalExpression" language="groovy"'),
     "không được có thuộc tính language"),
    (swap(END, '<endEvent id="tuChoi">chữ lạ</endEvent>'), "không được có nội dung chữ"),
    (swap('<dc:Bounds x="10"', '<dc:Bounds x="${x}"'), "phải là một số"),
    (swap('<sequenceFlow id="f1"', '<userTask id="lac" flowable:formKey="nghi-phep.duyet" '
                                    'flowable:assignee="${initiator}"><userTask id="long"/></userTask>'
                                    '<sequenceFlow id="f1"'), "<userTask> không được nằm trong <userTask>"),
], ids=lambda v: v if len(v) < 80 else "")
def test_poison_is_rejected_with_line_and_element(xml, needle):
    errors = errors_of(xml)
    assert any(needle in e for e in errors), errors
    assert all(e.startswith(WHERE) for e in errors)


def test_error_names_the_line():
    xml = after_end('<scriptTask id="s"/>')
    line = xml[:xml.index("<scriptTask")].count("\n") + 1
    assert errors_of(xml) == [f"{WHERE} dòng {line}: <scriptTask> không được phép trong <process> — BPMN của ứng "
                              "dụng chỉ gồm sự kiện bắt đầu/kết thúc, userTask, cổng rẽ nhánh và luồng "
                              "(docs/them-ung-dung.md, mục quy trình)"]


def test_every_problem_is_reported_in_one_run():
    xml = swap('<process id="nghi-phep.don"', '<process id="don"')
    xml = xml.replace("t:${tenantId}:director", "t:${tenantId}:admin")
    xml = xml.replace('<endEvent id="tuChoi"', '<scriptTask id="s"/><endEvent id="tuChoi"')
    assert len(errors_of(xml)) == 3


@pytest.mark.parametrize("prolog, needle", [
    ('<!DOCTYPE definitions [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>', "<!DOCTYPE"),
    ('<!doctype definitions>', "<!DOCTYPE"),
    ('<!ENTITY lol "lol">', "<!ENTITY"),
    ('<?xml-stylesheet href="x.xsl"?>', "chỉ thị xử lý"),
])
def test_xml_entities_and_processing_instructions_are_refused_before_parsing(prolog, needle):
    xml = BPMN.replace("<definitions", prolog + "\n<definitions", 1)
    errors = errors_of(xml)
    assert len(errors) == 1 and needle in errors[0] and "dòng 2" in errors[0]


def test_billion_laughs_is_refused():
    lol = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
           + "".join(f'<!ENTITY lol{i} "{("&lol" + str(i - 1) + ";") * 10 if i > 1 else "&lol;" * 10}">'
                     for i in range(1, 10))
           + ']><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">&lol9;</definitions>')
    assert "<!DOCTYPE" in errors_of(lol)[0]


@pytest.mark.parametrize("raw, needle", [
    (BPMN.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"').encode(), "chỉ nhận XML mã hóa UTF-8"),
    (BPMN.encode("utf-16"), "không phải UTF-8"),
    (b"<definitions", "XML sai"),
    (b'<process xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="nghi-phep.don"/>', "gốc phải là"),
    (BPMN.replace("</definitions>", "").encode(), "XML sai"),
    (b" " * (512 * 1024 + 1), "lớn quá"),
])
def test_unreadable_files_are_rejected(raw, needle):
    proc, errors = check(APP, WHERE, raw, FORMS, FIELDS)
    assert proc is None and len(errors) == 1 and needle in errors[0], errors


def test_one_process_per_file():
    second = BPMN[BPMN.index("<process"):BPMN.index("</process>") + len("</process>")]
    xml = swap("</process>", "</process>\n" + second.replace('"nghi-phep.don"', '"nghi-phep.hai"', 1)
               .replace('id="', 'id="x'))
    assert any("cần đúng một <process>" in e for e in errors_of(xml))


def test_app_name_is_checked():
    assert check("Nghi_Phep", WHERE, BPMN.encode(), FORMS, FIELDS)[1] == ["tên ứng dụng 'Nghi_Phep' không hợp lệ"]


@pytest.mark.parametrize("text, used, ok", [
    ("${quyetDinh == 'dong-y'}", {"quyetDinh"}, True),
    ("  ${quyetDinh != 'tu-choi' && loai == 'om' || loai == 'phep-nam'}  ", {"quyetDinh", "loai"}, True),
    ("${quyetDinh == ''}", {"quyetDinh"}, True),
    ("${quyetDinh == \"dong-y\"}", set(), False),
    ("${quyetDinh == 'a\\'b'}", set(), False),
    ("${quyetDinh == 'dong-y' &&}", {"quyetDinh"}, False),
    ("${quyetDinh}", set(), False),
    ("${true}", set(), False),
    ("${quyetDinh == 'x'} ${loai == 'y'}", set(), False),
    ("quyetDinh == 'dong-y'", set(), False),
])
def test_condition_grammar(text, used, ok):
    found, problem = check_condition(text, FIELDS)
    assert (problem is None) == ok, problem
    if ok:
        assert found == used


def test_diagram_prefixes_do_not_matter_only_namespaces():
    """Trình vẽ BPMN (Flowable Modeler, bpmn.io) đặt tiền tố omgdc/omgdi; danh sách trắng xét namespace."""
    xml = (BPMN.replace("xmlns:dc=", "xmlns:omgdc=").replace("xmlns:di=", "xmlns:omgdi=")
           .replace("<dc:", "<omgdc:").replace("<di:", "<omgdi:"))
    assert errors_of(xml) == []
    assert errors_of(xml.replace('xmlns:omgdc="http://www.omg.org/spec/DD/20100524/DC"', 'xmlns:omgdc="urn:la"'))


APP_BPMN = sorted((ROOT / "apps" / APP / "workflow").glob("*.bpmn20.xml"))


@pytest.mark.skipif(not APP_BPMN, reason="chưa có apps/nghi-phep/workflow/*.bpmn20.xml (ứng dụng mẫu)")
def test_sample_app_bpmn_passes_and_a_script_task_in_it_is_named():
    for path in APP_BPMN:
        text = path.read_text(encoding="utf-8")
        assert errors_of(text) == [], path
        flow = text.index("<sequenceFlow")
        poison = text[:flow] + '<scriptTask id="chayMa" scriptFormat="groovy"><script>"id".execute()</script>' \
                               "</scriptTask>\n    " + text[flow:]
        assert any("<scriptTask> không được phép" in e for e in errors_of(poison))
