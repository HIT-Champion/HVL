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

"""Tác tử gợi ý giao việc (F4.3): gợi ý đơn vị chủ trì và hạn cho văn bản đến, trước khi lãnh đạo chỉ đạo.

Văn bản vào sổ thì quy trình ``van-ban-den`` tách một nhánh song song với bước chỉ đạo: việc giao ra ngoài
``goiYGiaoViec`` (external worker, topic ``moc-goi-y``). Vòng nền ở đây nhận việc đó và:

  1. còn việc chỉ đạo mở không (lãnh đạo chỉ đạo rồi thì thôi), văn bản có phải văn bản đến không hạn chế không;
  2. hỏi svc-files các văn bản đến tương tự đã giao (``POST /internal/similar-documents`` — chỉ id và điểm);
  3. đọc đơn vị chủ trì lúc trước của chúng và các phòng có lãnh đạo phòng đang bật, bỏ phiếu (``suggest.py``);
  4. lưu gợi ý và ghi sổ kiểm toán trong cùng một giao dịch, bằng vai trò ``agent`` (danh tính ``moc-assigner``).

Tác tử chỉ gợi ý; lãnh đạo quyết định ở form chỉ đạo. Nhánh không nối lại vào luồng chính: svc-files chậm, lỗi hay
tắt thì văn bản vẫn tới lãnh đạo ngay, chỉ là có dòng ``failed`` (không thử lại) hoặc không có dòng nào. Quá 10 phút
không ai nhận việc thì timer ``boGoiY`` dọn nhánh. Văn bản hạn chế không bao giờ có gợi ý, không bao giờ làm căn cứ
(svc-files hậu kiểm, truy vấn lịch sử lọc lại, trigger CSDL chặn lần ghi).

Nhật ký và sổ không có trích yếu hay chữ nào của văn bản. ``python -m svc_workflow.advisor evaluate`` đo bỏ phiếu
theo kiểu leave-one-out trên các văn bản đã giao (``make do-giao-viec``), không ghi gì.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any

from .config import ConfigError, Settings
from .files import FilesClient, FilesError, ServiceToken
from .flowable import ExternalJob, FlowableClient, FlowableError
from .hasura import Actor, HasuraClient, HasuraError
from .openbao import with_secrets
from .suggest import VN, Hit, Past, Suggestion, lead_unit, past_days, suggest, vn_date

log = logging.getLogger("svc_workflow")

TOPIC = "moc-goi-y"
WORKER = "svc-workflow"
LIMIT = 15  # số văn bản tương tự hỏi svc-files
ACTION = "assignment.suggested"
DIRECTION_FORM = "vbden.chiDao"  # gợi ý thuộc bước chỉ đạo: lãnh đạo chỉ đạo xong thì không gợi ý nữa
BATCH = 5
LOCK = "PT1M"
RETRY_AFTER = "PT30S"

# văn bản đích (vai trò service): phải là văn bản đến không hạn chế
TARGET = """
query GiaoViecVanBan($id: uuid!) {
  office_documents_by_pk(id: $id) { id direction restricted registered_at due_on }
}"""

# đã có gợi ý (vai trò agent chỉ đọc được cột document_id): việc nhận lại sau lỗi không ghi hai lần
EXISTS = """
query GiaoViecDaGoiY($id: uuid!) {
  office_assignment_suggestions_by_pk(document_id: $id) { document_id }
}"""

# lần giao chủ trì đầu tiên (không tính giao lại trong phòng, không tính lần đã hủy) của các văn bản tương tự —
# lọc lại văn bản hạn chế dù svc-files đã hậu kiểm
HISTORY = """
query GiaoViecLichSu($ids: [uuid!]!) {
  office_documents(where: {id: {_in: $ids}, direction: {_eq: "in"}, restricted: {_eq: false}}) {
    id registered_at due_on
    assignments(where: {role: {_eq: "lead"}, parent_id: {_is_null: true}, status: {_neq: "cancelled"}},
                order_by: {assigned_at: asc}, limit: 1) { department_id user_id due_on }
  }
}"""

# lãnh đạo giao thẳng một người: đơn vị chủ trì là phòng của người đó
LEAD_USERS = """
query GiaoViecNguoiChuTri($users: [String!]!) {
  core_users(where: {id: {_in: $users}}) { id department_id }
}"""

# phòng gợi ý được: có thật trong đơn vị và có lãnh đạo phòng đang bật — đúng điều kiện chỉ đạo không báo no_manager
MANAGERS = """
query GiaoViecDonVi {
  office_departments { id }
  core_users(where: {role: {_eq: "manager"}, enabled: {_eq: true}, department_id: {_is_null: false}}) { department_id }
}"""

# một mutation = một giao dịch: không có gợi ý nào mà sổ không biết
SAVE = """
mutation LuuGoiYGiaoViec($o: office_assignment_suggestions_insert_input!, $e: core_audit_log_insert_input!) {
  insert_office_assignment_suggestions_one(object: $o) { document_id }
  insert_core_audit_log(objects: [$e]) { affected_rows }
}"""


def _today_vn() -> date:
    return datetime.now(VN).date()


def _hits(found: dict[str, Any], own_id: str) -> list[Hit]:
    """Hit của svc-files: bỏ phần tử hỏng, bỏ chính văn bản đích (svc-files đã loại, phòng hờ)."""
    out = []
    for item in found.get("hits") or []:
        try:
            doc_id, score = str(uuid.UUID(str(item["document_id"]))), float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if doc_id != own_id:
            out.append(Hit(doc_id, score))
    return out


def suggestion_row(document_id: str, process_id: str | None, s: Suggestion, *, semantic: bool,
                   duration_ms: int) -> dict[str, Any]:
    """Dòng ``office.assignment_suggestions``; ``tenant_id``, ``agent_id`` do preset của vai trò agent đặt."""
    return {
        "document_id": document_id, "process_id": (process_id or "")[:64] or None, "status": s.status,
        "reason": s.reason, "department_id": s.department_id, "confidence": s.confidence, "share": s.share,
        "due_days": s.due_days, "due_on": s.due_on.isoformat() if s.due_on else None,
        # căn cứ chỉ có id và số, không chữ
        "evidence": [{"document_id": e.document_id, "score": round(e.score, 4), "department_id": e.department_id,
                      "days": e.days} for e in s.evidence],
        "candidates": min(s.candidates, 100), "semantic": semantic, "duration_ms": max(duration_ms, 0),
    }


def failed_row(document_id: str, process_id: str | None, reason: str, *, duration_ms: int) -> dict[str, Any]:
    return {
        "document_id": document_id, "process_id": (process_id or "")[:64] or None, "status": "failed",
        "reason": reason, "department_id": None, "confidence": None, "share": None, "due_days": None,
        "due_on": None, "evidence": [], "candidates": 0, "semantic": False, "duration_ms": max(duration_ms, 0),
    }


def audit_row(request_id: str, row: dict[str, Any]) -> dict[str, Any]:
    """Dòng sổ ``assignment.suggested``: chỉ giá trị vô hướng, căn cứ chỉ là số đếm. Khóa ``outcome``,
    ``outcome_reason`` (không phải status, reason) để màn xem sổ không đọc nhầm thành nhãn của F4.1, F4.2."""
    return {"request_id": request_id, "action": ACTION, "entity": "office.documents", "entity_id": row["document_id"],
            "diff": {"outcome": row["status"], "outcome_reason": row["reason"], "department_id": row["department_id"],
                     "due_days": row["due_days"], "confidence": row["confidence"], "evidence": len(row["evidence"]),
                     "candidates": row["candidates"], "semantic": row["semantic"],
                     "duration_ms": row["duration_ms"]}}


class Advisor:
    def __init__(self, hasura: HasuraClient, flowable: FlowableClient, files: FilesClient, settings: Settings, *,
                 clock: Callable[[], float] = time.monotonic, today: Callable[[], date] = _today_vn) -> None:
        self.hasura = hasura
        self.flowable = flowable
        self.files = files
        self.settings = settings
        self._clock = clock
        self._today = today

    # --- việc giao ra ngoài (Flowable) ------------------------------------------------------------------

    async def run_jobs(self) -> int:
        """Nhận các việc gợi ý Flowable đã tạo, xử lý → số việc đã nhận."""
        jobs = await self.flowable.acquire_jobs(TOPIC, WORKER, count=BATCH, lock=LOCK)
        # chạy cùng lúc: mỗi việc ≤ hạn gọi svc-files + 10 giây, nên cả lô xong trước khi khóa PT1M hết
        await asyncio.gather(*(self._run(job) for job in jobs))
        return len(jobs)

    async def _run(self, job: ExternalJob) -> None:
        # Một việc lỗi không chặn việc khác. Lỗi lạ, CSDL hay Flowable không trả lời → Flowable giao lại sau 30 giây;
        # hết lượt thử thì vào hàng việc chết và timer boGoiY dọn nhánh — lãnh đạo vẫn chỉ đạo như thường.
        try:
            await asyncio.wait_for(self.handle(job), self.settings.suggest_timeout_s + 10)
        except Exception as exc:  # noqa: BLE001
            error = str(exc) or type(exc).__name__
            log.warning(json.dumps({"event": "office.assign.job_failed", "job_id": job.id, "error": error},
                                   ensure_ascii=False))
            await self._report(self.flowable.fail_job(job.id, WORKER, error, retry_after=RETRY_AFTER), job.id)
            return
        await self._report(self.flowable.complete_job(job.id, WORKER), job.id)

    async def _report(self, call: Awaitable[None], job_id: str) -> None:
        # timer boGoiY đã bắn lúc mình đang giữ việc thì Flowable trả 404: nhánh đã đóng, không còn gì để báo
        try:
            await call
        except FlowableError as exc:
            log.warning(json.dumps({"event": "office.assign.report_failed", "job_id": job_id, "error": str(exc)},
                                   ensure_ascii=False))

    async def handle(self, job: ExternalJob) -> str:
        """Một việc gợi ý → ``suggested`` | ``none`` | ``failed`` | ``skipped:<lý do>`` (bỏ qua: không ghi gì)."""
        try:
            tenant = uuid.UUID(str(job.variables.get("tenantId")))
            doc_id = str(uuid.UUID(str(job.variables.get("documentId"))))
        except ValueError:
            return self._skipped(None, None, "missing")
        if not self.settings.suggest_enabled:
            return self._skipped(tenant, doc_id, "disabled")
        tasks = await self.flowable.process_tasks(job.process_instance_id)
        if not any(t.form_key == DIRECTION_FORM for t in tasks):
            return self._skipped(tenant, doc_id, "too_late")
        request_id = f"goi-y:{job.id}"
        actor = Actor(self.settings.assigner_id, tenant, "service", None, request_id)
        doc = (await self.hasura.as_service(actor, TARGET, {"id": doc_id}))["office_documents_by_pk"]
        if doc is None:
            return self._skipped(tenant, doc_id, "missing")
        if doc.get("direction") != "in" or doc.get("restricted"):
            return self._skipped(tenant, doc_id, "restricted")
        found = await self.hasura.as_agent(tenant, self.settings.assigner_id, EXISTS, {"id": doc_id},
                                           request_id=request_id)
        if found.get("office_assignment_suggestions_by_pk"):
            return self._skipped(tenant, doc_id, "exists")

        started = self._clock()
        try:
            similar = await asyncio.wait_for(self.files.similar(tenant, doc_id, limit=LIMIT, request_id=request_id),
                                             self.settings.suggest_timeout_s)
        except TimeoutError:
            row = failed_row(doc_id, job.process_instance_id, "timeout", duration_ms=self._ms(started))
            return await self._save(tenant, request_id, row)
        except FilesError as exc:
            if exc.status == 503 and exc.code == "assistant_disabled":
                return self._skipped(tenant, doc_id, "assistant_disabled")  # tắt trợ lý thì không có dòng nào
            if exc.status in (404, 409) and exc.code:
                return self._skipped(tenant, doc_id, exc.code)
            # không thử lại: dòng failed là kết quả cuối, lãnh đạo giao như thường lệ
            log.warning(json.dumps({"event": "office.assign.files_failed", "tenant_id": str(tenant),
                                    "document_id": doc_id, "status": exc.status, "code": exc.code,
                                    "error": str(exc)}, ensure_ascii=False))
            row = failed_row(doc_id, job.process_instance_id, "unavailable", duration_ms=self._ms(started))
            return await self._save(tenant, request_id, row)

        hits = _hits(similar, doc_id)
        history, _ = await self._history(actor, self._worth(hits))
        units = await self._units(actor) if history else set()
        today = self._today()
        registered_on = vn_date(doc["registered_at"]) if doc.get("registered_at") else today
        doc_due = date.fromisoformat(doc["due_on"]) if doc.get("due_on") else None
        s = suggest(hits, history, units, min_score=self.settings.suggest_min_score, registered_on=registered_on,
                    doc_due=doc_due, today=today)
        row = suggestion_row(doc_id, job.process_instance_id, s, semantic=bool(similar.get("semantic")),
                             duration_ms=self._ms(started))
        return await self._save(tenant, request_id, row)

    def _ms(self, started: float) -> int:
        return max(round((self._clock() - started) * 1000), 0)

    def _worth(self, hits: list[Hit]) -> list[str]:
        """Chỉ hỏi lịch sử của văn bản đủ điểm làm căn cứ."""
        return [h.document_id for h in hits if h.score >= self.settings.suggest_min_score and h.score > 0]

    async def _history(self, actor: Actor, ids: list[str]) -> tuple[dict[str, Past], dict[str, str | None]]:
        """id → lần giao chủ trì đầu tiên (đơn vị, số ngày); id → lúc vào sổ."""
        if not ids:
            return {}, {}
        rows = (await self.hasura.as_service(actor, HISTORY, {"ids": sorted(set(ids))}))["office_documents"]
        leads = {r["id"]: (r.get("assignments") or [None])[0] for r in rows}
        users = sorted({lead["user_id"] for lead in leads.values()
                        if lead and not lead.get("department_id") and lead.get("user_id")})
        departments: dict[str, str] = {}
        if users:
            found = (await self.hasura.as_service(actor, LEAD_USERS, {"users": users}))["core_users"]
            departments = {u["id"]: str(u["department_id"]) for u in found if u.get("department_id")}
        history: dict[str, Past] = {}
        registered: dict[str, str | None] = {}
        for r in rows:
            lead = leads[r["id"]]
            # hạn của lần giao; lần giao không ghi hạn thì hạn ghi trên văn bản
            due = (lead or {}).get("due_on") or r.get("due_on")
            history[r["id"]] = Past(r["id"], lead_unit(lead, departments), past_days(r.get("registered_at"), due))
            registered[r["id"]] = r.get("registered_at")
        return history, registered

    async def _units(self, actor: Actor) -> set[str]:
        data = await self.hasura.as_service(actor, MANAGERS)
        known = {str(d["id"]) for d in data["office_departments"]}
        return {str(u["department_id"]) for u in data["core_users"] if str(u["department_id"]) in known}

    async def _save(self, tenant: uuid.UUID, request_id: str, row: dict[str, Any]) -> str:
        try:
            await self.hasura.as_agent(tenant, self.settings.assigner_id, SAVE,
                                       {"o": row, "e": audit_row(request_id, row)}, request_id=request_id)
        except HasuraError as exc:
            # lần chạy khác đã lưu; văn bản (hoặc một căn cứ) vừa thành hạn chế — trigger CSDL chặn cả giao dịch
            if "assignment_suggestions_pkey" in str(exc):
                return self._skipped(tenant, row["document_id"], "exists")
            if "assignment_suggestions_sealed" in str(exc):
                return self._skipped(tenant, row["document_id"], "restricted")
            raise
        log.info(json.dumps({"event": "office.assign.suggested", "tenant_id": str(tenant),
                             "document_id": row["document_id"], "outcome": row["status"], "reason": row["reason"],
                             "confidence": row["confidence"], "candidates": row["candidates"],
                             "semantic": row["semantic"], "duration_ms": row["duration_ms"]}))
        return str(row["status"])

    def _skipped(self, tenant: uuid.UUID | None, doc_id: str | None, reason: str) -> str:
        log.info(json.dumps({"event": "office.assign.suggested", "tenant_id": str(tenant) if tenant else None,
                             "document_id": doc_id, "outcome": "skipped", "reason": reason, "confidence": None,
                             "candidates": None, "semantic": None, "duration_ms": None}))
        return f"skipped:{reason}"

    # --- đo (leave-one-out) ----------------------------------------------------------------------------

    async def evaluate(self, tenant_id: uuid.UUID, ids: list[str]) -> list[dict[str, Any]]:
        """Bỏ phiếu lại cho từng văn bản đã giao như thể nó vừa vào sổ (svc-files đã loại chính nó khỏi kết quả),
        rồi đặt cạnh đơn vị và số ngày thật. Không ghi CSDL, không ghi sổ; dòng chỉ có id và số."""
        actor = Actor(self.settings.assigner_id, tenant_id, "service", None, "goi-y:danh-gia")
        units = await self._units(actor)
        rows = []
        for raw in ids:
            doc_id = str(uuid.UUID(str(raw)))
            started = self._clock()
            failure: str | None = None
            similar: dict[str, Any] = {}
            try:
                similar = await asyncio.wait_for(self.files.similar(tenant_id, doc_id, limit=LIMIT),
                                                 self.settings.suggest_timeout_s)
            except TimeoutError:
                failure = "timeout"
            except FilesError as exc:
                failure = exc.code if exc.status in (404, 409) and exc.code else "unavailable"
            hits = _hits(similar, doc_id)
            history, registered = await self._history(actor, [*self._worth(hits), doc_id])
            own = history.pop(doc_id, None)
            row: dict[str, Any] = {
                "document_id": doc_id,
                "actual": {"department_id": own.department_id if own else None, "days": own.days if own else None},
            }
            if failure is not None:
                row.update(status="failed", reason=failure, department_id=None, ranking=[], confidence=None,
                           due_days=None, evidence=[], semantic=False, duration_ms=self._ms(started))
                rows.append(row)
                continue
            at = registered.get(doc_id)
            registered_on = vn_date(at) if at else self._today()
            s = suggest(hits, history, units, min_score=self.settings.suggest_min_score,
                        registered_on=registered_on, doc_due=None, today=registered_on)
            row.update(status=s.status, reason=s.reason, department_id=s.department_id, ranking=list(s.ranking),
                       confidence=s.confidence, due_days=s.due_days, evidence=[e.document_id for e in s.evidence],
                       semantic=bool(similar.get("semantic")), duration_ms=self._ms(started))
            rows.append(row)
        return rows


def _build(settings: Settings) -> tuple[Advisor, Callable[[], Awaitable[None]]]:
    """Advisor nối thật (CLI trong container), cùng cấu hình với app.py."""
    hasura = HasuraClient(settings.hasura_url, settings.hasura_admin_secret, timeout_s=settings.hasura_timeout_s)
    flowable = FlowableClient(settings.flowable_url, settings.flowable_user, settings.flowable_password)
    files = FilesClient(settings.files_url, ServiceToken(
        settings.keycloak_url, settings.realm, settings.directory_client_id, settings.directory_client_secret))

    async def close() -> None:
        await files.aclose()
        await flowable.aclose()
        await hasura.aclose()

    return Advisor(hasura, flowable, files, settings), close


USAGE = ('Cách dùng: python -m svc_workflow.advisor evaluate < đầu vào JSON '
         '{"tenant_id": "<uuid>", "documents": ["<uuid>", …]} → stdout {"rows": […]}')


def main(argv: list[str] | None = None) -> int:
    """``python -m svc_workflow.advisor evaluate``: stdin JSON → stdout JSON; lỗi ra stderr."""
    args = sys.argv[1:] if argv is None else argv
    if args != ["evaluate"]:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        request = json.load(sys.stdin)
        tenant = uuid.UUID(str(request["tenant_id"]))
        documents = request["documents"]
        if not isinstance(documents, list):
            raise TypeError("documents phải là danh sách id")
        ids = [str(uuid.UUID(str(d))) for d in documents]
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Đầu vào không hợp lệ ({type(exc).__name__}). {USAGE}", file=sys.stderr)
        return 2
    try:
        settings = Settings.from_env(with_secrets(os.environ))
    except ConfigError as exc:
        print(f"Cấu hình: {exc}", file=sys.stderr)
        return 2
    advisor, close = _build(settings)

    async def go() -> list[dict[str, Any]]:
        try:
            return await advisor.evaluate(tenant, ids)
        finally:
            await close()

    try:
        rows = asyncio.run(go())
    except (HasuraError, FlowableError) as exc:
        print(f"Không đọc được dữ liệu để đo: {exc}", file=sys.stderr)
        return 1
    json.dump({"rows": rows}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
