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

"""Lô nạp trong CSDL (core.import_jobs, core.import_rows — migration 1792281602800), qua Hasura.

Mọi câu đọc, ghi dùng vai trò ``service`` của đúng đơn vị lô (khóa quản trị + X-Hasura-Role: service + thuê ước từ
token lúc tạo lô): quyền trong db/metadata lọc theo đơn vị, preset ``tenant_id`` khi thêm. Riêng hai câu của vòng nền
tìm lô đến giờ và lô chưa xong của mọi đơn vị dùng khóa quản trị không kèm vai trò — việc nội bộ, chỉ đọc, không nhận
tham số người dùng (như ``pending_texts``). Nhận dòng là một lệnh cập nhật có điều kiện (``attempts`` khớp, chưa ai
giữ hoặc đã quá hạn giữ ``claimed_until``) đặt mã lượt giữ ``claim_id`` và trả lại dòng như nó đang có trong CSDL:
chỉ một vòng thắng và làm dòng đó, vòng khác bỏ qua dòng đang được giữ. Lưu tiến độ, thả dòng, ghi kết quả đều kèm
``status = pending`` và đúng ``claim_id`` trong điều kiện: vòng đã mất dòng (quá hạn giữ, vòng khác nhận lại; hay cả lô
bị hủy) nhận về 0 dòng đổi và dừng, không ghi đè gì. Đóng lô chỉ đổi lô chưa ``done``; dòng sổ ``import.finished`` do
trigger của CSDL ghi khi lô chuyển sang ``done`` — hai vòng cùng đóng thì sổ vẫn một dòng.

Gỡ tệp của dòng không thành văn bản (``drop_files``) dùng khóa quản trị không kèm vai trò — vai trò ``service`` không
có quyền xóa core.files — với điều kiện chặt trong câu: đúng đơn vị, đúng người tải, chưa gắn văn bản nào.

db/tests/test_import_jobs.py đọc các câu ở đây bằng ast (không chép tay) để chạy trên Hasura thật.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Protocol

from ..hasura import HasuraError

JOB_COLUMNS = """
    id tenant_id kind created_by department_id status filename format data_sha256 archive_sha256 archive_bytes options
    total ok duplicate failed note created_at started_at run_after finished_at
    pending_rows: rows_aggregate(where: {status: {_eq: "pending"}}) { aggregate { count } }
    ok_rows: rows_aggregate(where: {status: {_eq: "ok"}}) { aggregate { count } }
    duplicate_rows: rows_aggregate(where: {status: {_eq: "duplicate"}}) { aggregate { count } }
    failed_rows: rows_aggregate(where: {status: {_eq: "failed"}}) { aggregate { count } }"""

# Tạo lô: lô, mọi dòng và dòng sổ import.created trong một mutation = một giao dịch
CREATE = """
mutation TaoLo($job: core_import_jobs_insert_input!, $rows: [core_import_rows_insert_input!]!,
               $audit: core_audit_log_insert_input!) {
  insert_core_import_jobs_one(object: $job) { id }
  insert_core_import_rows(objects: $rows) { affected_rows }
  insert_core_audit_log(objects: [$audit]) { affected_rows }
}"""

BY_KEY = """
query LoTheoKhoa($user: String!, $key: String!) {
  core_import_jobs(where: {created_by: {_eq: $user}, idempotency_key: {_eq: $key}}) {""" + JOB_COLUMNS + """
  }
}"""

# Chỉ người tạo lô: lô của người khác cùng đơn vị cũng như không có
JOB = """
query Lo($id: uuid!, $user: String!) {
  core_import_jobs(where: {id: {_eq: $id}, created_by: {_eq: $user}}) {""" + JOB_COLUMNS + """
  }
}"""

JOBS = """
query CacLo($user: String!, $limit: Int!) {
  core_import_jobs(where: {created_by: {_eq: $user}}, order_by: {created_at: desc},
                   limit: $limit) {""" + JOB_COLUMNS + """
  }
}"""

OPEN_COUNT = """
query LoDangMo { core_import_jobs_aggregate(where: {status: {_neq: "done"}}) { aggregate { count } } }"""

ROWS = """
query DongCuaLo($id: uuid!, $statuses: [String!]!, $after: Int!, $limit: Int!) {
  core_import_rows(where: {job_id: {_eq: $id}, status: {_in: $statuses}, line: {_gt: $after}},
                   order_by: {line: asc}, limit: $limit) {
    line status code message fields result
  }
}"""

# Vòng nền — khóa quản trị, mọi đơn vị: lô chưa xong đến giờ, sớm nhất trước (chỉ mục import_jobs_due)
DUE = """
query LoDenGio($now: timestamptz!) {
  core_import_jobs(where: {status: {_neq: "done"}, run_after: {_lte: $now}},
                   order_by: [{run_after: asc}, {created_at: asc}], limit: 1) {
    id tenant_id kind created_by department_id status format options archive_bytes note created_at
  }
}"""

OPEN_IDS = """
query LoChuaXong { core_import_jobs(where: {status: {_neq: "done"}}) { id } }"""

ACTOR = """
query NguoiTaoLo($id: String!) { core_users(where: {id: {_eq: $id}}) { enabled role } }"""

# Dòng còn chờ mà không vòng nào đang giữ (claimed_until trống hoặc đã qua): hai tiến trình làm hai phần khác nhau
PENDING = """
query DongCho($id: uuid!, $limit: Int!, $now: timestamptz!) {
  core_import_rows(where: {job_id: {_eq: $id}, status: {_eq: "pending"},
                           _or: [{claimed_until: {_is_null: true}}, {claimed_until: {_lt: $now}}]},
                   order_by: {line: asc}, limit: $limit) {
    line data files attempts result
  }
}"""

START = """
mutation BatDauLo($id: uuid!, $at: timestamptz!) {
  update_core_import_jobs(where: {id: {_eq: $id}, status: {_eq: "queued"}},
                          _set: {status: "running", started_at: $at}) { affected_rows }
}"""

# Nhận một dòng để xử lý — một lệnh cập nhật có điều kiện, chỉ một bên thắng: attempts khớp (khóa lạc quan như hộp thư
# đi của svc-workflow, channels.py) và chưa ai giữ dòng (hoặc bên giữ đã quá hạn: tiến trình chết hay kẹt giữa chừng).
# Đặt mã lượt giữ $claim; trả dòng sau khi cập nhật — tiến độ bên giữ trước kịp lưu sau lúc đọc PENDING vẫn có ở đây.
# $bump: 1, hoặc 0 khi chỉ nhận để ghi kết quả cho dòng đã hết lượt
CLAIM = """
mutation NhanDong($id: uuid!, $line: Int!, $attempts: Int!, $now: timestamptz!, $until: timestamptz!, $claim: uuid!,
                  $bump: Int!) {
  update_core_import_rows(where: {job_id: {_eq: $id}, line: {_eq: $line}, status: {_eq: "pending"},
                                  attempts: {_eq: $attempts},
                                  _or: [{claimed_until: {_is_null: true}}, {claimed_until: {_lt: $now}}]},
                          _inc: {attempts: $bump}, _set: {claimed_until: $until, claim_id: $claim}) {
    returning { line data files attempts result }
  }
}"""

# Lưu tiến độ (id tệp đã lưu, id văn bản) và gia hạn giữ dòng — chỉ khi dòng còn là của lượt giữ này
PROGRESS = """
mutation TienDoDong($id: uuid!, $line: Int!, $claim: uuid!, $result: jsonb!, $until: timestamptz!) {
  update_core_import_rows(where: {job_id: {_eq: $id}, line: {_eq: $line}, status: {_eq: "pending"},
                                  claim_id: {_eq: $claim}},
                          _set: {result: $result, claimed_until: $until}) { affected_rows }
}"""

# Thôi giữ dòng (lõi bận: dòng chờ lượt sau, vòng nào cũng nhận được khi tới giờ)
RELEASE = """
mutation ThaDong($id: uuid!, $line: Int!, $claim: uuid!) {
  update_core_import_rows(where: {job_id: {_eq: $id}, line: {_eq: $line}, status: {_eq: "pending"},
                                  claim_id: {_eq: $claim}},
                          _set: {claimed_until: null, claim_id: null}) { affected_rows }
}"""

# Dòng còn chờ đã lưu tệp — trước khi hủy cả lô (người tạo bị khóa) để gỡ tệp của chúng
STRANDED = """
query TepCuaDongCho($id: uuid!) {
  core_import_rows(where: {job_id: {_eq: $id}, status: {_eq: "pending"}, result: {_has_key: "file_ids"}},
                   order_by: {line: asc}) {
    line result
  }
}"""

FINISH = """
mutation XongDong($id: uuid!, $line: Int!, $claim: uuid!, $set: core_import_rows_set_input!) {
  update_core_import_rows(where: {job_id: {_eq: $id}, line: {_eq: $line}, status: {_eq: "pending"},
                                  claim_id: {_eq: $claim}},
                          _set: $set) { affected_rows }
}"""

FAIL_PENDING = """
mutation HuyDongCho($id: uuid!, $set: core_import_rows_set_input!) {
  update_core_import_rows(where: {job_id: {_eq: $id}, status: {_eq: "pending"}}, _set: $set) { affected_rows }
}"""

RESCHEDULE = """
mutation HenLo($id: uuid!, $set: core_import_jobs_set_input!) {
  update_core_import_jobs(where: {id: {_eq: $id}, status: {_neq: "done"}}, _set: $set) { affected_rows }
}"""

COUNTS = """
query DemDong($id: uuid!) {
  pending: core_import_rows_aggregate(where: {job_id: {_eq: $id}, status: {_eq: "pending"}}) { aggregate { count } }
  ok: core_import_rows_aggregate(where: {job_id: {_eq: $id}, status: {_eq: "ok"}}) { aggregate { count } }
  duplicate: core_import_rows_aggregate(where: {job_id: {_eq: $id}, status: {_eq: "duplicate"}}) {
    aggregate { count }
  }
  failed: core_import_rows_aggregate(where: {job_id: {_eq: $id}, status: {_eq: "failed"}}) { aggregate { count } }
}"""

# Đóng lô: ảnh chụp số đếm, finished_at. Chỉ lô chưa done: trigger import_jobs_finished (migration 1792281602800) ghi
# dòng sổ import.finished trong cùng giao dịch khi lô chuyển sang done — vòng đóng sau (tiến trình khác) không đổi dòng
# nào nên không ghi sổ lần hai
CLOSE = """
mutation DongLo($id: uuid!, $set: core_import_jobs_set_input!) {
  update_core_import_jobs(where: {id: {_eq: $id}, status: {_neq: "done"}}, _set: $set) { affected_rows }
}"""

# Tra trùng trước khi đưa tệp vào kho — đúng điều kiện chặn trùng của Action (svc-workflow INTAKE_LOOKUP, chỉ mục
# documents_in_dedup): văn bản đến chưa hủy, cùng số ký hiệu, cơ quan ban hành (không phân biệt hoa thường), ngày
EXISTING = """
query VanBanDaCo($symbol: String!, $issuer: String!, $issued: date!) {
  office_documents(where: {direction: {_eq: "in"}, status: {_neq: "cancelled"}, symbol: {_eq: $symbol},
                           issuer_name: {_ilike: $issuer}, issued_on: {_eq: $issued}}, limit: 1) {
    id created_by created_at register_number
  }
}"""

DOCUMENT = """
query VanBanCuaDong($id: uuid!) { office_documents_by_pk(id: $id) { id created_by created_at register_number } }"""

# Văn bản này đã được một dòng khác (của bất kỳ lô nào trong đơn vị) nhận là của mình chưa
CLAIMED = """
query VanBanDaNhan($doc: jsonb!, $id: uuid!, $line: Int!) {
  core_import_rows_aggregate(where: {result: {_contains: $doc}, _not: {job_id: {_eq: $id}, line: {_eq: $line}}}) {
    aggregate { count }
  }
}"""

# Gỡ tệp đã lưu cho một dòng không thành văn bản (Action từ chối, trùng, tệp sau bị chặn, hết lượt…). Khóa quản trị
# không kèm vai trò, người làm trong sổ kiểm toán là FILES_ACTOR (actor_kind system), mã yêu cầu "<lô>:<dòng>". Điều
# kiện nằm trong câu: đúng đơn vị, đúng người tải, chưa gắn văn bản nào (khóa ngoại của office.document_files cũng
# chặn). Tệp người tải đã đặt vào không gian cá nhân (personal.items xóa theo tệp) thì giữ lại: hỏi trước, bỏ khỏi danh
# sách gỡ.
PERSONAL_FILES = """
query TepTrongKhongGianCaNhan($ids: [uuid!]!) { personal_items(where: {file_id: {_in: $ids}}) { file_id } }"""

DROP_FILES = """
mutation GoTepKhongGan($ids: [uuid!]!, $tenant: uuid!, $user: String!) {
  delete_core_files(where: {id: {_in: $ids}, tenant_id: {_eq: $tenant}, created_by: {_eq: $user},
                            _not: {document_files: {}}}) {
    returning { id object_key }
  }
}"""

FILES_ACTOR = "svc-files:import"

STATUSES = ["pending", "ok", "duplicate", "failed"]


class KeyTaken(Exception):
    """Idempotency-Key đã có lô (hai yêu cầu cùng khóa chen nhau: ràng buộc import_jobs_key của CSDL chặn người sau)."""


class _Hasura(Protocol):
    async def as_role(self, role: str, tenant_id: uuid.UUID, user_id: str, request_id: str, query: str,
                      variables: dict[str, Any]) -> dict[str, Any]: ...
    async def admin(self, query: str, variables: dict[str, Any], headers: dict[str, str] | None = None,
                    ) -> dict[str, Any]: ...


def _count(node: dict[str, Any] | None) -> int:
    return int(((node or {}).get("aggregate") or {}).get("count") or 0)


def view(row: dict[str, Any]) -> dict[str, Any]:
    """Một lô như API trả: lô đã đóng lấy số đếm đã chụp, lô đang chạy đếm thẳng từ dòng."""
    out = {k: v for k, v in row.items() if not k.endswith("_rows")}
    out["register"] = bool((row.get("options") or {}).get("register"))
    if row["status"] == "done":
        out["pending"] = 0
    else:
        out["pending"] = _count(row.get("pending_rows"))
        for name in ("ok", "duplicate", "failed"):
            out[name] = _count(row.get(f"{name}_rows"))
    return out


def ilike_exact(text: str) -> str:
    """Mẫu _ilike khớp đúng chuỗi (không phân biệt hoa thường): thoát \\ % _ như svc-workflow."""
    return re.sub(r"([\\%_])", r"\\\1", text)


class ImportStore:
    def __init__(self, hasura: _Hasura) -> None:
        self.hasura = hasura

    async def _service(self, tenant_id: uuid.UUID, user: str, rid: str, query: str,
                       variables: dict[str, Any]) -> dict[str, Any]:
        return await self.hasura.as_role("service", tenant_id, user, rid, query, variables)

    # --- API ----------------------------------------------------------------------------------------

    async def create(self, job: dict[str, Any], rows: list[dict[str, Any]], audit: dict[str, Any], *,
                     tenant_id: uuid.UUID, user: str, rid: str) -> None:
        try:
            await self._service(tenant_id, user, rid, CREATE, {"job": job, "rows": rows, "audit": audit})
        except HasuraError as exc:
            if exc.code == "constraint-violation" and "import_jobs_key" in str(exc):
                raise KeyTaken from exc
            raise

    async def by_key(self, tenant_id: uuid.UUID, user: str, key: str, *, rid: str) -> dict[str, Any] | None:
        data = await self._service(tenant_id, user, rid, BY_KEY, {"user": user, "key": key})
        rows = data["core_import_jobs"]
        return view(rows[0]) if rows else None

    async def get(self, tenant_id: uuid.UUID, user: str, job_id: uuid.UUID, *, rid: str) -> dict[str, Any] | None:
        data = await self._service(tenant_id, user, rid, JOB, {"id": str(job_id), "user": user})
        rows = data["core_import_jobs"]
        return view(rows[0]) if rows else None

    async def list(self, tenant_id: uuid.UUID, user: str, limit: int, *, rid: str) -> list[dict[str, Any]]:
        data = await self._service(tenant_id, user, rid, JOBS, {"user": user, "limit": limit})
        return [view(row) for row in data["core_import_jobs"]]

    async def count_open(self, tenant_id: uuid.UUID, user: str, *, rid: str) -> int:
        return _count((await self._service(tenant_id, user, rid, OPEN_COUNT, {}))["core_import_jobs_aggregate"])

    async def rows(self, tenant_id: uuid.UUID, user: str, job_id: uuid.UUID, *, statuses: list[str], after: int,
                   limit: int, rid: str) -> list[dict[str, Any]]:
        data = await self._service(tenant_id, user, rid, ROWS, {"id": str(job_id), "statuses": statuses,
                                                               "after": after, "limit": limit})
        return data["core_import_rows"]

    # --- vòng nền -----------------------------------------------------------------------------------

    async def due(self, now: datetime) -> dict[str, Any] | None:
        rows = (await self.hasura.admin(DUE, {"now": now.isoformat()}))["core_import_jobs"]
        return rows[0] if rows else None

    async def open_ids(self) -> set[str]:
        return {row["id"] for row in (await self.hasura.admin(OPEN_IDS, {}))["core_import_jobs"]}

    async def actor(self, job: dict[str, Any]) -> dict[str, Any] | None:
        rows = (await self._job(job, ACTOR, {"id": job["created_by"]}))["core_users"]
        return rows[0] if rows else None

    async def _job(self, job: dict[str, Any], query: str, variables: dict[str, Any], *,
                   line: int | None = None) -> dict[str, Any]:
        rid = job["id"] if line is None else f"{job['id']}:{line}"
        return await self._service(uuid.UUID(str(job["tenant_id"])), job["created_by"], rid, query, variables)

    async def pending(self, job: dict[str, Any], limit: int, now: datetime) -> list[dict[str, Any]]:
        data = await self._job(job, PENDING, {"id": job["id"], "limit": limit, "now": now.isoformat()})
        return data["core_import_rows"]

    async def start(self, job: dict[str, Any], at: datetime) -> None:
        await self._job(job, START, {"id": job["id"], "at": at.isoformat()})

    async def claim(self, job: dict[str, Any], line: int, attempts: int, *, now: datetime, until: datetime,
                    claim_id: str, bump: int = 1) -> dict[str, Any] | None:
        """Dòng như đang có trong CSDL sau khi nhận (``attempts`` đã cộng ``bump``); None: vòng khác đã nhận."""
        data = await self._job(job, CLAIM, {"id": job["id"], "line": line, "attempts": attempts,
                                            "now": now.isoformat(), "until": until.isoformat(), "claim": claim_id,
                                            "bump": bump}, line=line)
        rows = data["update_core_import_rows"]["returning"]
        return rows[0] if rows else None

    async def progress(self, job: dict[str, Any], line: int, result: dict[str, Any], *, until: datetime,
                       claim_id: str) -> bool:
        """False: dòng không còn là của lượt giữ này (vòng khác đã nhận lại, hoặc dòng đã xong)."""
        data = await self._job(job, PROGRESS, {"id": job["id"], "line": line, "claim": claim_id, "result": result,
                                               "until": until.isoformat()}, line=line)
        return data["update_core_import_rows"]["affected_rows"] == 1

    async def release(self, job: dict[str, Any], line: int, *, claim_id: str) -> None:
        await self._job(job, RELEASE, {"id": job["id"], "line": line, "claim": claim_id}, line=line)

    async def stranded(self, job: dict[str, Any]) -> list[dict[str, Any]]:
        return (await self._job(job, STRANDED, {"id": job["id"]}))["core_import_rows"]

    async def finish(self, job: dict[str, Any], line: int, values: dict[str, Any], *, claim_id: str) -> bool:
        """False: dòng không còn là của lượt giữ này — kết quả không được ghi."""
        data = await self._job(job, FINISH, {"id": job["id"], "line": line, "claim": claim_id, "set": values},
                               line=line)
        return data["update_core_import_rows"]["affected_rows"] == 1

    async def fail_pending(self, job: dict[str, Any], values: dict[str, Any]) -> int:
        data = await self._job(job, FAIL_PENDING, {"id": job["id"], "set": values})
        return int(data["update_core_import_rows"]["affected_rows"])

    async def reschedule(self, job: dict[str, Any], values: dict[str, Any]) -> None:
        await self._job(job, RESCHEDULE, {"id": job["id"], "set": values})

    async def counts(self, job: dict[str, Any]) -> dict[str, int]:
        data = await self._job(job, COUNTS, {"id": job["id"]})
        return {name: _count(data[name]) for name in STATUSES}

    async def close(self, job: dict[str, Any], values: dict[str, Any]) -> bool:
        """True: chính lệnh này đóng lô (và trigger ghi import.finished); False: vòng khác đã đóng trước."""
        data = await self._job(job, CLOSE, {"id": job["id"], "set": values})
        return data["update_core_import_jobs"]["affected_rows"] == 1

    async def existing(self, job: dict[str, Any], line: int, *, symbol: str, issuer: str,
                       issued_on: str) -> dict[str, Any] | None:
        data = await self._job(job, EXISTING, {"symbol": symbol, "issuer": ilike_exact(issuer), "issued": issued_on},
                               line=line)
        rows = data["office_documents"]
        return rows[0] if rows else None

    async def document(self, job: dict[str, Any], line: int, document_id: str) -> dict[str, Any] | None:
        return (await self._job(job, DOCUMENT, {"id": document_id}, line=line))["office_documents_by_pk"]

    async def claimed(self, job: dict[str, Any], line: int, document_id: str) -> bool:
        data = await self._job(job, CLAIMED, {"doc": {"document_id": document_id}, "id": job["id"], "line": line},
                               line=line)
        return _count(data["core_import_rows_aggregate"]) > 0

    async def drop_files(self, job: dict[str, Any], line: int, file_ids: list[str]) -> list[dict[str, Any]]:
        """Gỡ dòng core.files của các tệp đã lưu cho dòng (chỉ tệp chưa gắn văn bản, chưa đặt vào không gian cá nhân,
        của người tạo lô trong đơn vị lô); trả ``[{id, object_key}]`` đã gỡ để xóa đối tượng trong kho."""
        headers = {"X-Hasura-User-Id": FILES_ACTOR, "X-Hasura-Request-Id": f"{job['id']}:{line}"}
        kept = (await self.hasura.admin(PERSONAL_FILES, {"ids": file_ids}, headers))["personal_items"]
        ids = [i for i in file_ids if i not in {str(row["file_id"]) for row in kept}]
        if not ids:
            return []
        data = await self.hasura.admin(DROP_FILES, {"ids": ids, "tenant": str(job["tenant_id"]),
                                                    "user": job["created_by"]}, headers)
        return data["delete_core_files"]["returning"]
