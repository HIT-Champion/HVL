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

"""Gợi ý giao việc (F4.3, migration 1792281602100): tác tử moc-assigner (vai trò Hasura agent) lưu gợi ý đơn vị chủ trì
của một văn bản đến và dòng sổ assignment.suggested trong cùng một yêu cầu; thuê ước, danh tính tác tử đặt sẵn từ
phiên; văn bản hạn chế, văn bản đi không có gợi ý, văn bản hạn chế không làm căn cứ; chỉ lãnh đạo đơn vị đọc gợi ý; màn
Sổ kiểm toán và tab Lịch sử thấy kết quả, không thấy trích yếu; view office.v_assignment_suggestion_accuracy đếm gợi ý
lãnh đạo giữ. svc-workflow không chạy ở đây: test gửi đúng các truy vấn của svc_workflow.advisor (EXISTS, SAVE — hợp
đồng F4.3 §5.2) và của giao diện (GoiYGiaoViec, CanCuGoiY — §8)."""

from __future__ import annotations

import itertools
import json
import uuid
from dataclasses import dataclass

import pytest
from conftest import (
    INSERT_DOC,
    Agent,
    GraphQLError,
    Service,
    SQLError,
    User,
    World,
    incoming,
    outgoing,
    received,
    sql,
)

AGENT_ID = "moc-assigner"

# svc_workflow.advisor: văn bản đã có gợi ý chưa; lưu gợi ý + dòng sổ trong một mutation (một giao dịch)
EXISTS = """query ($id: uuid!) { office_assignment_suggestions_by_pk(document_id: $id) { document_id } }"""
SAVE = """mutation ($o: office_assignment_suggestions_insert_input!, $e: core_audit_log_insert_input!) {
  insert_office_assignment_suggestions_one(object: $o) { document_id }
  insert_core_audit_log(objects: [$e]) { affected_rows } }"""
LOG = """mutation ($e: core_audit_log_insert_input!) { insert_core_audit_log(objects: [$e]) { affected_rows } }"""

# Chỉ phần gợi ý của SAVE: kiểm ràng buộc từng cột mà không ghi thêm dòng sổ
SAVE_ONE = """mutation ($o: office_assignment_suggestions_insert_input!) {
  insert_office_assignment_suggestions_one(object: $o) { document_id } }"""

# Giao diện (AssignSuggestion.vue) bằng token lãnh đạo
SHOWN = """query GoiYGiaoViec($id: uuid!) {
  office_assignment_suggestions_by_pk(document_id: $id) {
    status reason department_id confidence share due_days due_on evidence created_at }
  office_documents_by_pk(id: $id) { registered_at } }"""
BASIS = """query CanCuGoiY($ids: [uuid!]!) {
  office_documents(where: {id: {_in: $ids}, restricted: {_eq: false}}) { id symbol summary } }"""

AUDIT_VIEW = """query ($e: String!) {
  core_audit_log(where: {entity_id: {_eq: $e}, action: {_eq: "assignment.suggested"}}, order_by: {id: asc}) {
    actor_id actor_kind action entity overview } }"""
HISTORY = """query ($d: uuid!) { office_document_history(where: {document_id: {_eq: $d}}, order_by: {id: asc}) {
  action entity actor_id actor_kind overview } }"""

ACCURACY = """{ office_v_assignment_suggestion_accuracy { status confidence suggested decided kept_unit due_compared
  kept_due due_abs_error_days } }"""
ASSIGN = """mutation ($o: office_assignments_insert_input!) { insert_office_assignments_one(object: $o) { id } }"""


def agent(tenant: str, sub: str = AGENT_ID) -> Agent:
    return Agent(sub, "agent", tenant)


def basis(doc_id: str, department: str, score: float, days: int | None = 7) -> dict:
    """Một căn cứ như svc-workflow lưu: chỉ id, điểm, đơn vị, số ngày — không chữ văn bản."""
    return {"document_id": doc_id, "score": score, "department_id": department, "days": days}


def suggestion(doc_id: str, department: str, **overrides) -> dict:
    """Gợi ý `suggested` như svc-workflow lưu (§5.2 bước 9); tenant_id, agent_id, created_at không gửi."""
    row = {"document_id": doc_id, "process_id": f"proc-{doc_id[:8]}", "status": "suggested", "reason": None,
           "department_id": department, "confidence": "high", "share": 0.8, "due_days": 10, "due_on": "2026-11-05",
           "evidence": [], "candidates": 12, "semantic": False, "duration_ms": 183}
    row.update(overrides)
    return row


def nothing(doc_id: str, status: str = "none", reason: str = "no_similar", **overrides) -> dict:
    """Gợi ý không thành (`none` hoặc `failed`): không đơn vị, độ tin cậy, hạn, căn cứ."""
    return suggestion(doc_id, None, status=status, reason=reason, confidence=None, share=None, due_days=None,
                      due_on=None, **overrides)


def event(doc_id: str, department: str | None, **diff) -> dict:
    """Dòng sổ assignment.suggested (§6): đúng 9 khóa, giá trị vô hướng, evidence là số đếm."""
    body = {"outcome": "suggested", "outcome_reason": None, "department_id": department, "due_days": 10,
            "confidence": "high", "evidence": 2, "candidates": 12, "semantic": False, "duration_ms": 183}
    body.update(diff)
    return {"request_id": f"goi-y:{doc_id[:8]}", "action": "assignment.suggested", "entity": "office.documents",
            "entity_id": doc_id, "diff": body}


def stored(doc_id: str) -> list[list[str]]:
    return sql("select tenant_id, agent_id, status, department_id, confidence, due_days, due_on, "
               f"jsonb_array_length(evidence) from office.assignment_suggestions where document_id = '{doc_id}'")


def ledger(doc_id: str) -> list[list[str]]:
    return sql("select tenant_id, actor_id, actor_kind, request_id, action, entity from core.audit_log "
               f"where entity = 'office.documents' and entity_id = '{doc_id}' and action = 'assignment.suggested' "
               "order by id")


def evidence_of(doc_id: str) -> list[dict]:
    [[text]] = sql(f"select evidence::text from office.assignment_suggestions where document_id = '{doc_id}'")
    return json.loads(text)


# số thứ tự văn bản thử của tệp này: số ký hiệu khác nhau, không vướng chỉ mục chống trùng documents_in_dedup
NUMBERS = itertools.count(4301)


def doc(world: World, **overrides) -> str:
    return received(world.clerk_a, incoming(world.tag, next(NUMBERS), **overrides))["id"]


def summary_of(doc_id: str) -> str:
    return sql(f"select summary from office.documents where id = '{doc_id}'")[0][0]


# --- lưu ------------------------------------------------------------------------------------------------------------


def test_agent_saves_suggestion_and_ledger_row_in_one_request(world: World):
    target, first, second = doc(world), doc(world), doc(world)
    assigner = agent(world.tenant_a)
    assert assigner.gql(EXISTS, {"id": target}) == {"office_assignment_suggestions_by_pk": None}
    row = suggestion(target, world.dept_a1, evidence=[basis(first, world.dept_a1, 0.91, 7),
                                                      basis(second, world.dept_a2, 0.52, None)])
    data = assigner.gql(SAVE, {"o": row, "e": event(target, world.dept_a1)})
    assert data == {"insert_office_assignment_suggestions_one": {"document_id": target},
                    "insert_core_audit_log": {"affected_rows": 1}}
    # thuê ước, danh tính tác tử lấy từ phiên
    assert stored(target) == [[world.tenant_a, AGENT_ID, "suggested", world.dept_a1, "high", "10", "2026-11-05", "2"]]
    assert ledger(target) == [[world.tenant_a, AGENT_ID, "agent", f"goi-y:{target[:8]}", "assignment.suggested",
                               "office.documents"]]
    assert assigner.gql(EXISTS, {"id": target}) == {"office_assignment_suggestions_by_pk": {"document_id": target}}
    # việc giao lại (Flowable thử lại): khóa chính chặn cả giao dịch, sổ không thêm dòng — svc-workflow bỏ qua
    with pytest.raises(GraphQLError, match="assignment_suggestions_pkey"):
        assigner.gql(SAVE, {"o": row, "e": event(target, world.dept_a1)})
    assert len(ledger(target)) == 1
    # bảng không gắn core.audit(): chỉ có dòng sổ tác tử tự ghi
    assert sql("select count(*) from core.audit_log where entity = 'office.assignment_suggestions'") == [["0"]]
    assert sql("select audit_id, problem from core.audit_verify()") == []


@pytest.mark.parametrize(("status", "reason"), [("none", "no_similar"), ("none", "no_history"),
                                                ("none", "no_valid_unit"), ("none", "low_confidence"),
                                                ("failed", "timeout"), ("failed", "unavailable")])
def test_agent_saves_outcomes_without_a_suggestion(world: World, status: str, reason: str):
    target = doc(world)
    agent(world.tenant_a).gql(SAVE, {"o": nothing(target, status, reason, candidates=0),
                                     "e": event(target, None, outcome=status, outcome_reason=reason, due_days=None,
                                                confidence=None, evidence=0, candidates=0)})
    assert stored(target) == [[world.tenant_a, AGENT_ID, status, "NULL", "NULL", "NULL", "NULL", "0"]]


def test_document_with_its_own_due_date_gets_no_suggested_due(world: World):
    target = doc(world, due_on="2026-11-20")
    agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(target, world.dept_a1, due_days=None, due_on=None)})
    assert stored(target)[0][5:7] == ["NULL", "NULL"]


@pytest.mark.parametrize("column", ["tenant_id", "agent_id", "created_at"])
def test_agent_cannot_choose_tenant_identity_or_time(world: World, column: str):
    target = doc(world)
    value = {"tenant_id": world.tenant_b, "agent_id": "gia-mao", "created_at": "2026-01-01T00:00:00+07:00"}[column]
    body = agent(world.tenant_a).raw(SAVE_ONE, {"o": {**suggestion(target, world.dept_a1), column: value}})
    assert "errors" in body and column in body["errors"][0]["message"]
    assert stored(target) == []


def test_other_tenant_cannot_save_or_see_suggestions(world: World):
    target = doc(world)
    other = agent(world.tenant_b)
    with pytest.raises(GraphQLError, match="foreign key"):          # văn bản không thuộc đơn vị trong phiên
        other.gql(SAVE_ONE, {"o": suggestion(target, world.dept_b1)})
    with pytest.raises(GraphQLError, match="foreign key"):          # đơn vị chủ trì của đơn vị khác
        agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(target, world.dept_b1)})
    agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(target, world.dept_a1)})
    assert other.gql(EXISTS, {"id": target}) == {"office_assignment_suggestions_by_pk": None}


# --- văn bản hạn chế, văn bản đi ------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["restricted", "outgoing", "restricted_basis", "restricted_basis_upper"])
def test_restricted_and_outgoing_documents_are_sealed(world: World, case: str):
    plain, secret = doc(world), doc(world, restricted=True)
    if case == "restricted":
        target, evidence = secret, [basis(plain, world.dept_a1, 0.9)]
    elif case == "outgoing":
        target = world.staff_a1.gql(INSERT_DOC, {"o": outgoing(next(NUMBERS))})["insert_office_documents_one"]["id"]
        evidence = [basis(plain, world.dept_a1, 0.9)]
    else:
        target = doc(world)
        secret_id = secret.upper() if case == "restricted_basis_upper" else secret
        evidence = [basis(plain, world.dept_a1, 0.9), basis(secret_id, world.dept_a2, 0.8, 3)]
    with pytest.raises(GraphQLError, match="assignment_suggestions_sealed"):
        agent(world.tenant_a).gql(SAVE, {"o": suggestion(target, world.dept_a1, evidence=evidence),
                                         "e": event(target, world.dept_a1)})
    assert stored(target) == [] and ledger(target) == []          # một giao dịch: dòng sổ cũng không ghi
    # kể cả ghi thẳng CSDL
    with pytest.raises(SQLError, match="assignment_suggestions_sealed"):
        sql("insert into office.assignment_suggestions (document_id, tenant_id, agent_id, status, department_id, "
            f"confidence, share, evidence, duration_ms) values ('{target}', '{world.tenant_a}', '{AGENT_ID}', "
            f"'suggested', '{world.dept_a1}', 'high', 0.8, '{json.dumps(evidence)}', 5)")


def test_restricted_documents_get_no_outcome_row_either(world: World):
    secret = doc(world, restricted=True)
    with pytest.raises(GraphQLError, match="assignment_suggestions_sealed"):
        agent(world.tenant_a).gql(SAVE_ONE, {"o": nothing(secret)})
    assert stored(secret) == []


# --- hình dạng ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("overrides", "constraint"), [
    ({"status": "none", "reason": "no_similar", "confidence": None, "share": None, "due_days": None, "due_on": None},
     "assignment_suggestions_shape"),                                       # none mà có đơn vị
    ({"confidence": None}, "assignment_suggestions_shape"),                 # suggested thiếu độ tin cậy
    ({"share": None}, "assignment_suggestions_shape"),
    ({"reason": "low_confidence"}, "assignment_suggestions_shape"),         # suggested có lý do
    ({"department_id": None, "status": "failed", "reason": "no_similar", "confidence": None, "share": None,
      "due_days": None, "due_on": None}, "assignment_suggestions_shape"),   # failed với lý do của none
    ({"department_id": None, "status": "none", "reason": None, "confidence": None, "share": None, "due_days": None,
      "due_on": None}, "assignment_suggestions_shape"),                     # none thiếu lý do
    ({"department_id": None, "status": "none", "reason": "low_confidence", "confidence": None, "share": None,
      "due_days": None, "due_on": None, "evidence": "<căn cứ>"}, "assignment_suggestions_shape"),  # none có căn cứ
    ({"due_on": None}, "assignment_suggestions_due"),                       # due_days mà không có due_on
    ({"due_days": None}, "assignment_suggestions_due"),
    # PostgreSQL kiểm ràng buộc check theo thứ tự tên: hình dạng phải đúng thì mới tới status_check
    ({"department_id": None, "status": "maybe", "reason": "timeout", "confidence": None, "share": None,
      "due_days": None, "due_on": None}, "assignment_suggestions_status_check"),
    ({"confidence": "very_high"}, "assignment_suggestions_confidence_check"),
    ({"share": 0}, "assignment_suggestions_share_check"),
    ({"share": 1.5}, "assignment_suggestions_share_check"),
    ({"due_days": 0}, "assignment_suggestions_due_days_check"),
    ({"due_days": 366}, "assignment_suggestions_due_days_check"),
    ({"evidence": {"document_id": "x"}}, "assignment_suggestions_evidence_check"),    # không phải mảng
    ({"evidence": "<6 căn cứ>"}, "assignment_suggestions_evidence_check"),             # quá 5 phần tử
    ({"evidence": "<căn cứ có chữ>"}, "assignment_suggestions_evidence_check"),        # quá 2 KB: không chỗ cho chữ
    ({"candidates": 101}, "assignment_suggestions_candidates_check"),
    ({"duration_ms": -1}, "assignment_suggestions_duration_ms_check"),
    ({"process_id": "p" * 65}, "assignment_suggestions_process_id_check"),
])
def test_suggestion_shape_is_checked(world: World, overrides: dict, constraint: str):
    target = doc(world)
    marker = overrides.get("evidence")
    if marker == "<căn cứ>":
        overrides = {**overrides, "evidence": [basis(str(uuid.uuid4()), world.dept_a1, 0.9)]}
    elif marker == "<6 căn cứ>":
        overrides = {**overrides, "evidence": [basis(str(uuid.uuid4()), world.dept_a1, 0.5) for _ in range(6)]}
    elif marker == "<căn cứ có chữ>":
        overrides = {**overrides, "evidence": [{**basis(str(uuid.uuid4()), world.dept_a1, 0.5),
                                                "summary": "Về việc xét cấp học bổng " + "x" * 400} for _ in range(5)]}
    # nguyên từ: assignment_suggestions_due khác assignment_suggestions_due_days_check
    with pytest.raises(GraphQLError, match=rf"\b{constraint}\b"):
        agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(target, world.dept_a1, **overrides)})
    assert stored(target) == []


# --- bật hạn chế sau khi đã gợi ý -----------------------------------------------------------------------------------


def test_restricting_a_document_drops_its_suggestion_and_strips_it_from_evidence(world: World):
    a, b, c, d = doc(world), doc(world), doc(world), doc(world)
    assigner = agent(world.tenant_a)
    assigner.gql(SAVE_ONE, {"o": suggestion(a, world.dept_a1, evidence=[basis(c, world.dept_a1, 0.8)])})
    kept = [basis(c, world.dept_a2, 0.95, 14), basis(d, world.dept_a2, 0.7, 12)]
    assigner.gql(SAVE_ONE, {"o": suggestion(b, world.dept_a2, confidence="medium", share=0.62, due_days=14,
                                            due_on="2026-11-09",
                                            evidence=[kept[0], basis(a, world.dept_a1, 0.9), kept[1]])})
    sql(f"update office.documents set summary = summary || ' (sửa)' where id = '{a}'")
    assert len(stored(a)) == 1                                  # sửa trường khác: giữ nguyên
    sql(f"update office.documents set restricted = true where id = '{a}'")
    assert stored(a) == []
    # B mất đúng phần tử A, giữ thứ tự; đơn vị, độ tin cậy, hạn giữ nguyên
    assert evidence_of(b) == kept
    assert stored(b) == [[world.tenant_a, AGENT_ID, "suggested", world.dept_a2, "medium", "14", "2026-11-09", "2"]]
    # A không có gợi ý lại được, không làm căn cứ được nữa
    with pytest.raises(GraphQLError, match="assignment_suggestions_sealed"):
        assigner.gql(SAVE_ONE, {"o": suggestion(a, world.dept_a1)})
    with pytest.raises(GraphQLError, match="assignment_suggestions_sealed"):
        assigner.gql(SAVE_ONE, {"o": suggestion(doc(world), world.dept_a1, evidence=[basis(a, world.dept_a1, 0.9)])})


def test_restricting_several_documents_at_once(world: World):
    # một lệnh bật hạn chế X và D: gợi ý của X có căn cứ D, gợi ý của Y có căn cứ X và D
    x, y, c, d = doc(world), doc(world), doc(world), doc(world)
    assigner = agent(world.tenant_a)
    assigner.gql(SAVE_ONE, {"o": suggestion(x, world.dept_a1, evidence=[basis(d, world.dept_a1, 0.8)])})
    assigner.gql(SAVE_ONE, {"o": suggestion(y, world.dept_a1, evidence=[
        basis(x, world.dept_a1, 0.9), basis(d, world.dept_a1, 0.8), basis(c, world.dept_a2, 0.6, 14)])})
    sql(f"update office.documents set restricted = true where id in ('{x}', '{d}')")
    assert stored(x) == [] and stored(d) == []
    assert evidence_of(y) == [basis(c, world.dept_a2, 0.6, 14)]


# --- ai thấy gì, ai ghi được gì -------------------------------------------------------------------------------------


def test_only_directors_of_the_unit_read_suggestions(world: World):
    target, first = doc(world), doc(world, symbol=f"88/CTSV{world.tag}")
    evidence = [basis(first, world.dept_a1, 0.91, 7)]
    agent(world.tenant_a).gql(SAVE_ONE, {"o": suggestion(target, world.dept_a1, evidence=evidence)})
    data = world.director_a.gql(SHOWN, {"id": target})
    shown = data["office_assignment_suggestions_by_pk"]
    assert (shown["status"], shown["reason"], shown["department_id"], shown["confidence"], shown["due_days"],
            shown["due_on"], shown["evidence"]) == (
        "suggested", None, world.dept_a1, "high", 10, "2026-11-05", evidence)
    assert shown["share"] == pytest.approx(0.8) and shown["created_at"]
    assert "office_documents_by_pk" in data
    # căn cứ: giao diện đọc số ký hiệu, trích yếu bằng token lãnh đạo
    [row] = world.director_a.gql(BASIS, {"ids": [first]})["office_documents"]
    assert row["symbol"] == f"88/CTSV{world.tag}"
    # quan hệ sang văn bản, đơn vị
    rel = world.director_a.gql("query ($id: uuid!) { office_assignment_suggestions_by_pk(document_id: $id) { "
                               "document { id } department { id } } }", {"id": target})
    assert rel["office_assignment_suggestions_by_pk"] == {"document": {"id": target},
                                                          "department": {"id": world.dept_a1}}
    # gợi ý thuộc bước chỉ đạo: vai trò khác không có bảng này
    for user in (world.clerk_a, world.staff_a1, world.manager_a1, world.admin_a):
        assert "errors" in user.raw("{ office_assignment_suggestions { document_id } }"), user.role
        assert "errors" in user.raw(SHOWN, {"id": target}), user.role
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert other.gql("{ office_assignment_suggestions { document_id } }")["office_assignment_suggestions"] == []
    assert other.gql(SHOWN, {"id": target})["office_assignment_suggestions_by_pk"] is None


def test_nobody_edits_suggestions_and_the_agent_has_no_other_rights(world: World):
    target = doc(world)
    assigner = agent(world.tenant_a)
    assigner.gql(SAVE_ONE, {"o": suggestion(target, world.dept_a1)})
    for user in (world.director_a, world.clerk_a):
        assert "errors" in user.raw(SAVE_ONE, {"o": suggestion(doc(world), world.dept_a1)}), user.role
    for actor in (assigner, world.director_a):
        for mutation in ("mutation { update_office_assignment_suggestions(where: {}, _set: {status: \"none\"}) { "
                         "affected_rows } }", "mutation { delete_office_assignment_suggestions(where: {}) { "
                         "affected_rows } }"):
            assert "errors" in actor.raw(mutation), (actor.sub, mutation)
    # tác tử chỉ thấy khóa của dòng đã có; không đọc văn bản, giao việc, danh bạ, sổ
    assert "errors" in assigner.raw("{ office_assignment_suggestions { department_id evidence } }")
    for query in ("{ office_documents { id } }", "{ office_assignments { id } }", "{ core_users { id } }",
                  "{ core_audit_log { id } }", "{ office_v_assignment_suggestion_accuracy { suggested } }"):
        assert "errors" in assigner.raw(query), query
    assert stored(target)[0][2:4] == ["suggested", world.dept_a1]


# --- sổ kiểm toán ---------------------------------------------------------------------------------------------------


def test_agent_ledger_rows_are_about_documents_only(world: World):
    target = doc(world)
    assigner = agent(world.tenant_a)
    assert assigner.gql(LOG, {"e": event(target, world.dept_a1)}) == {"insert_core_audit_log": {"affected_rows": 1}}
    for column, value in (("action", "intake.suggested"), ("action", "assistant.answered"), ("action", "update"),
                          ("entity", "office.assignments"), ("entity", "core.files"), ("entity", "ai.questions")):
        body = assigner.raw(LOG, {"e": {**event(target, world.dept_a1), column: value}})
        assert "errors" in body and "permission" in body["errors"][0]["message"], (column, value)
    for column, value in (("actor_id", world.director_a.sub), ("actor_kind", "user"), ("tenant_id", world.tenant_b)):
        body = assigner.raw(LOG, {"e": {**event(target, world.dept_a1), column: value}})
        assert "errors" in body and column in body["errors"][0]["message"], column
    assert ledger(target) == [[world.tenant_a, AGENT_ID, "agent", f"goi-y:{target[:8]}", "assignment.suggested",
                               "office.documents"]]


def test_ledger_and_history_show_the_outcome_not_the_text(world: World):
    target = doc(world)
    summary = summary_of(target)
    # svc-workflow không bao giờ đưa chữ vào diff; cố tình nhét vào thì màn xem sổ, tab Lịch sử chỉ có tên khóa
    leaked = {"summary": summary, "symbol": "88/CTSV", "reason": "x", "method": "ocr", "hits": 3}
    agent(world.tenant_a).gql(LOG, {"e": event(target, world.dept_a1, evidence=4, **leaked)})
    expected = {"outcome": "suggested", "outcome_reason": None, "department_id": world.dept_a1, "due_days": 10,
                "confidence": "high", "evidence": 4, "candidates": 12, "semantic": False, "duration_ms": 183,
                "summary": None, "symbol": None, "reason": None, "method": None, "hits": None}
    for viewer in (world.director_a, world.admin_a):
        [row] = viewer.gql(AUDIT_VIEW, {"e": target})["core_audit_log"]
        assert (row["actor_id"], row["actor_kind"], row["action"], row["entity"]) == (
            AGENT_ID, "agent", "assignment.suggested", "office.documents")
        assert row["overview"] == expected, viewer.role
    # tab Lịch sử của văn bản: người đọc được văn bản thấy dòng của tác tử, không có trích yếu
    rows = [r for r in world.director_a.gql(HISTORY, {"d": target})["office_document_history"]
            if r["action"] == "assignment.suggested"]
    assert rows == [{"action": "assignment.suggested", "entity": "office.documents", "actor_id": AGENT_ID,
                     "actor_kind": "agent", "overview": expected}]
    assert summary not in json.dumps(rows, ensure_ascii=False)
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    assert other.gql(AUDIT_VIEW, {"e": target})["core_audit_log"] == []


def test_suggestion_keys_show_only_on_suggestion_rows(world: World):
    # khóa của F4.3 không có giá trị ở dòng khác; khóa của F3.12 vẫn trong danh sách chung
    entity_id = f"lt-{world.tag}-f43"
    shown = {"attempts": [0, 1], "delivered_at": [None, "2026-10-21T10:00:00+07:00"]}
    hidden = {"outcome": [None, "suggested"], "outcome_reason": [None, "x"], "due_days": [None, 3],
              "confidence": [None, "high"], "evidence": [0, 2], "candidates": [0, 5]}
    world.service_a.gql("""mutation ($o: core_audit_log_insert_input!) { insert_core_audit_log_one(object: $o) {
      id } }""", {"o": {"actor_id": "svc-workflow", "actor_kind": "service", "action": "update",
                       "entity": "office.dispatches", "entity_id": entity_id, "diff": {**shown, **hidden}}})
    [[text]] = sql(f"select core.audit_overview(a)::text from core.audit_log a where a.entity_id = '{entity_id}'")
    assert json.loads(text) == {**shown, **dict.fromkeys(hidden)}


# --- số đo giữ / đổi gợi ý ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    tenant: str
    director: User
    admin: User


@pytest.fixture(scope="module")
def unit() -> Unit:
    """Một đơn vị riêng (không dùng chung đơn vị A của các test khác), nên số đếm của view biết trước."""
    tag = uuid.uuid4().hex[:6].upper()
    [[tenant]] = sql(f"insert into core.tenants (code, name) values ('V{tag}', 'Đơn vị thử gợi ý giao việc') "
                     "returning id")
    [[dt]] = sql(f"insert into office.departments (tenant_id, code, name) values ('{tenant}', 'ĐT', 'Tổ Đào tạo') "
                 "returning id")
    [[ktpm]] = sql(f"insert into office.departments (tenant_id, code, name) values ('{tenant}', 'KTPM', "
                   "'Bộ môn Kỹ thuật phần mềm') returning id")
    person = f"chuyen-vien-dt-{tag}"
    sql(f"insert into core.users (id, tenant_id, department_id, username, full_name, role) values "
        f"('{person}', '{tenant}', '{dt}', 'cvdt{tag}', 'Chuyên viên Tổ Đào tạo', 'staff')")
    clerk = User(f"van-thu-{tag}", "clerk", tenant)
    director = User(f"truong-khoa-{tag}", "director", tenant)
    service = Service(f"svc-{tag}", "service", tenant)
    assigner = agent(tenant)
    numbers = iter(range(1, 100))

    def new_doc() -> str:
        return received(clerk, incoming(tag, next(numbers)))["id"]

    def suggest(doc_id: str, **overrides) -> None:
        assigner.gql(SAVE_ONE, {"o": suggestion(doc_id, dt, **overrides)})

    def lead(doc_id: str, *, department: str | None = None, user: str | None = None, due: str | None = None,
             status: str = "open") -> None:
        # assigned_at mặc định now() của giao dịch ghi: mỗi yêu cầu một giao dịch, nên thứ tự gọi là thứ tự thời gian
        service.gql(ASSIGN, {"o": {"document_id": doc_id, "department_id": department, "user_id": user,
                                   "role": "lead", "due_on": due, "status": status, "assigned_by": director.sub}})

    d1, d2, d3, d4, d5, d6 = (new_doc() for _ in range(6))
    lead(d3, department=ktpm, due="2026-11-05")      # giao trước lúc gợi ý: không tính là quyết định sau gợi ý
    for d in (d1, d2, d3, d6):
        suggest(d)                                   # ĐT, cao, hạn 05/11/2026
    suggest(d4, confidence="medium", share=0.55, due_days=None, due_on=None)
    assigner.gql(SAVE_ONE, {"o": nothing(d5)})
    lead(d1, department=dt, due="2026-11-05")        # giữ đơn vị và hạn
    lead(d2, user=person, due="2026-11-08")          # giao cho người của ĐT: giữ đơn vị; lệch hạn 3 ngày
    lead(d4, department=ktpm, due="2026-11-20")      # đổi đơn vị; gợi ý không có hạn để so
    lead(d5, department=dt)                          # không gợi ý được, lãnh đạo vẫn giao
    lead(d6, department=dt, due="2026-11-05", status="cancelled")   # việc đã hủy không tính
    lead(d6, department=ktpm, due="2026-11-03")      # đổi đơn vị, lệch hạn 2 ngày
    return Unit(tenant, director, User(f"quan-tri-{tag}", "tenant_admin", tenant))


def test_accuracy_counts_what_leaders_kept_after_the_suggestion(unit: Unit):
    for viewer in (unit.director, unit.admin):
        rows = viewer.gql(ACCURACY)["office_v_assignment_suggestion_accuracy"]
        assert sorted((r["status"], r["confidence"] or "", r["suggested"], r["decided"], r["kept_unit"],
                       r["due_compared"], r["kept_due"], r["due_abs_error_days"]) for r in rows) == [
            ("none", "", 1, 1, 0, 0, 0, 0),
            ("suggested", "high", 4, 3, 2, 3, 1, 5),
            ("suggested", "medium", 1, 1, 0, 0, 0, 0),
        ], viewer.role


def test_accuracy_is_for_leaders_of_the_unit_only(world: World, unit: Unit):
    for user in (world.staff_a1, world.manager_a1, world.clerk_a):
        assert "errors" in user.raw(ACCURACY), user.role
    assert "errors" in User(f"van-thu-{unit.tenant[:6]}", "clerk", unit.tenant).raw(ACCURACY)
    other = User(f"hieu-truong-b-{world.tag}", "director", world.tenant_b)
    rows = other.gql("{ office_v_assignment_suggestion_accuracy { tenant_id } }")[
        "office_v_assignment_suggestion_accuracy"]
    assert {r["tenant_id"] for r in rows} <= {world.tenant_b}
