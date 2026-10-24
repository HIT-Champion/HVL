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

"""Đồ giả cho test nạp lô: Hasura có Action tiếp nhận / vào sổ (như svc-workflow), lô và dòng trong bộ nhớ với cùng
ràng buộc chính của CSDL (migration 1792281602800)."""

from __future__ import annotations

import io
import json
import re
import struct
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx2

from conftest import FakeHasura
from svc_files.hasura import HasuraError
from svc_files.imports.store import STATUSES, KeyTaken, view

REQUIRED = ("type_code", "symbol", "issuer_name", "issued_on", "summary")
KNOWN = {*REQUIRED, "urgency", "due_on", "restricted", "file_ids"}
TYPES = {"CV", "TB", "QĐ", "KH", "GM", "BC", "TTr"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ActionHasura(FakeHasura):
    """FakeHasura có thêm act_as: receiveIncoming, registerIncoming kiểm như svc-workflow (tóm lược) — trường bắt
    buộc, ngày, trích yếu, khóa lạ, loại văn bản, tệp do chính người gọi tải lên, tệp mã hóa ↔ văn bản hạn chế, trùng
    theo (đơn vị, cơ quan ban hành không phân biệt hoa thường, số ký hiệu, ngày)."""

    incoming: dict[str, dict] = field(default_factory=dict)       # văn bản đến đã tạo qua Action
    act_calls: list[dict] = field(default_factory=list)
    fail_next: list[HasuraError] = field(default_factory=list)    # lỗi lần lượt cho các lời gọi Action tới
    lose_reply: int = 0       # số lần receiveIncoming ghi xong rồi mất phản hồi (svc-files hết giờ chờ)
    lose_register: int = 0    # số lần registerIncoming vào sổ xong rồi mất phản hồi
    register_error: HasuraError | None = None
    numbers: Counter = field(default_factory=Counter)

    async def act_as(self, *, role: str, tenant_id, user_id: str, department_id: str | None, request_id: str,
                     query: str, variables: dict, timeout_s: float | None = None) -> dict:
        name = "receiveIncoming" if "receiveIncoming" in query else "registerIncoming"
        self.act_calls.append({"action": name, "role": role, "tenant_id": str(tenant_id), "user_id": user_id,
                               "department_id": department_id, "request_id": request_id, "variables": variables})
        self._check()
        if self.fail_next:
            raise self.fail_next.pop(0)
        if role != "clerk":
            raise HasuraError("field not found in type: 'mutation_root'", "validation-failed")
        if name == "receiveIncoming":
            return {"receiveIncoming": self._receive(str(tenant_id), user_id, variables["d"])}
        return {"registerIncoming": self._register(str(tenant_id), variables["id"])}

    def _receive(self, tenant: str, user: str, data: dict) -> dict:
        fields: dict[str, str] = {}
        for key in data:
            if key not in KNOWN:
                fields[key] = "additionalProperties"
        for key in REQUIRED:
            if key not in data:
                fields[key] = "required"
            elif not isinstance(data[key], str):
                fields[key] = "type"
        if isinstance(data.get("summary"), str) and len(data["summary"]) < 10:
            fields["summary"] = "minLength"
        issued = data.get("issued_on")
        if isinstance(issued, str):
            try:
                date.fromisoformat(issued)
            except ValueError:
                fields["issued_on"] = "format"
        if "restricted" in data and not isinstance(data["restricted"], bool):
            fields["restricted"] = "type"
        if fields:
            raise HasuraError("Dữ liệu văn bản đến chưa hợp lệ: " + ", ".join(sorted(fields)), "invalid", fields)
        if data["type_code"] not in TYPES:
            raise HasuraError("Không có loại văn bản này", "invalid", {"type_code": "unknown"})
        file_ids = data.get("file_ids", [])
        mine = [self.files.get(uuid.UUID(f)) for f in file_ids]
        if any(f is None or str(f["tenant_id"]) != tenant or f["created_by"] != user for f in mine):
            raise HasuraError("Tệp không tồn tại hoặc không do bạn tải lên", "invalid", {"file_ids": "unknown"})
        sealed = sum(1 for f in mine if f.get("wrapped_dek"))
        if data.get("restricted") and sealed != len(file_ids):
            raise HasuraError("Văn bản hạn chế chỉ gắn tệp tải lên ở chế độ hạn chế", "invalid",
                              {"file_ids": "not_sealed"})
        if not data.get("restricted") and sealed:
            raise HasuraError("Tệp mã hóa chỉ gắn vào văn bản hạn chế", "invalid", {"file_ids": "sealed"})
        if self.find(tenant, data["symbol"], data["issuer_name"], data["issued_on"]):
            raise HasuraError("Đã có văn bản đến cùng số ký hiệu, cơ quan ban hành và ngày ban hành", "duplicate",
                              {"symbol": "duplicate"})
        doc_id = str(uuid.uuid4())
        self.incoming[doc_id] = {"id": doc_id, "tenant_id": tenant, "created_by": user, "created_at": now_iso(),
                                 "status": "received", "register_number": None, "file_ids": list(file_ids),
                                 **{k: data[k] for k in data if k != "file_ids"}}
        if self.lose_reply:
            self.lose_reply -= 1
            raise HasuraError("Không gọi được Hasura: ReadTimeout")
        return {"document_id": doc_id}

    def _register(self, tenant: str, doc_id: str) -> dict:
        if self.register_error is not None:
            raise self.register_error
        doc = self.incoming.get(doc_id)
        if doc is None or doc["tenant_id"] != tenant:
            raise HasuraError("Không tìm thấy văn bản", "document_not_found")
        if doc["register_number"] is not None:
            raise HasuraError("Văn bản đã vào sổ", "wrong_status")
        self.numbers[tenant] += 1
        doc.update(register_number=self.numbers[tenant], status="registered")
        if self.lose_register:
            self.lose_register -= 1
            raise HasuraError("Không gọi được Hasura: ReadTimeout")
        return {"document_id": doc_id, "register_number": doc["register_number"]}

    def find(self, tenant: str, symbol: str, issuer: str, issued_on: str) -> dict | None:
        for doc in self.incoming.values():
            if (doc["tenant_id"] == tenant and doc["symbol"] == symbol and doc["issued_on"] == issued_on
                    and doc["issuer_name"].lower() == issuer.lower() and doc["status"] != "cancelled"):
                return doc
        return None


def _iso(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


@dataclass
class FakeImportStore:
    """core.import_jobs / core.import_rows trong bộ nhớ, cùng giao diện với imports.store.ImportStore: khóa
    Idempotency theo (đơn vị, người tạo), mọi câu của service lọc theo đơn vị, nhận dòng khi attempts khớp và chưa ai
    giữ hay đã quá hạn giữ (đặt claim_id, trả dòng sau khi nhận), ghi dòng chỉ khi còn pending và đúng claim_id, data
    xóa khi dòng xong, ràng buộc số đếm khi đóng lô; đóng lô chỉ đổi lô chưa done và ghi import.finished đúng lúc lô
    chuyển sang done như trigger import_jobs_finished. Gỡ tệp (drop_files) theo đúng điều kiện của DROP_FILES: đúng đơn
    vị, đúng người tải, chưa gắn văn bản, chưa đặt vào không gian cá nhân."""

    hasura: ActionHasura
    jobs: dict[str, dict] = field(default_factory=dict)
    lines: dict[tuple[str, int], dict] = field(default_factory=dict)    # core.import_rows
    audit: list[dict] = field(default_factory=list)
    users: dict[tuple[str, str], dict] = field(default_factory=dict)
    down: bool = False
    ops: list[tuple[str, str]] = field(default_factory=list)      # (câu, thuê ước) — kiểm cách ly đơn vị
    personal: set[str] = field(default_factory=set)               # id tệp đã đặt vào không gian cá nhân
    dropped: list[dict] = field(default_factory=list)             # lời gọi gỡ tệp: lô, dòng, id xin gỡ, id đã gỡ

    def _check(self, op: str, tenant: Any = None) -> None:
        self.ops.append((op, str(tenant)))
        if self.down:
            raise HasuraError("Không gọi được Hasura: ConnectError")

    def _rows_of(self, job_id: str) -> list[dict]:
        return sorted((r for (j, _), r in self.lines.items() if j == job_id), key=lambda r: r["line"])

    def _view(self, job: dict) -> dict:
        counts = Counter(r["status"] for r in self._rows_of(job["id"]))
        raw = {**job, **{f"{s}_rows": {"aggregate": {"count": counts[s]}} for s in STATUSES}}
        return view(json.loads(json.dumps(raw, default=str)))

    def _mine(self, tenant, user: str) -> list[dict]:
        return [j for j in self.jobs.values() if j["tenant_id"] == str(tenant) and j["created_by"] == user]

    # --- API ---------------------------------------------------------------------------------------------

    async def create(self, job: dict, rows: list[dict], audit: dict, *, tenant_id, user: str, rid: str) -> None:
        self._check("create", tenant_id)
        # mã hóa như HasuraClient gửi thật (httpx2: JSON UTF-8, không NaN/inf): giá trị không gửi được thì lỗi ở đây
        httpx2.Request("POST", "http://hasura/v1/graphql", json={"variables": {"job": job, "rows": rows,
                                                                               "audit": audit}})
        key = job.get("idempotency_key")
        if key is not None and any(j["idempotency_key"] == key for j in self._mine(tenant_id, job["created_by"])):
            raise KeyTaken
        assert 1 <= job["total"] == len(rows)
        at = now_iso()
        self.jobs[job["id"]] = {**job, "tenant_id": str(tenant_id), "status": "queued", "ok": 0, "duplicate": 0,
                                "failed": 0, "note": None, "created_at": at, "started_at": None, "run_after": at,
                                "finished_at": None}
        for r in rows:
            assert r["job_id"] == job["id"]                   # job_id not null, khóa ngoại (job_id, tenant_id)
            assert (r["data"] is None) == ("status" in r)       # dòng hỏng lúc đọc: không có dữ liệu
            assert len(r["files"]) <= 20
            self.lines[(job["id"], r["line"])] = {"status": "pending", "attempts": 0, "result": None, "code": None,
                                                 "message": None, "fields": None, "done_at": None,
                                                 "claimed_until": None, "claim_id": None, **r, "job_id": job["id"],
                                                 "tenant_id": str(tenant_id)}
        self.audit.append({**audit, "tenant_id": str(tenant_id)})

    async def by_key(self, tenant_id, user: str, key: str, *, rid: str) -> dict | None:
        self._check("by_key", tenant_id)
        found = [j for j in self._mine(tenant_id, user) if j["idempotency_key"] == key]
        return self._view(found[0]) if found else None

    async def get(self, tenant_id, user: str, job_id, *, rid: str) -> dict | None:
        self._check("get", tenant_id)
        job = self.jobs.get(str(job_id))
        if job is None or job["tenant_id"] != str(tenant_id) or job["created_by"] != user:
            return None
        return self._view(job)

    async def list(self, tenant_id, user: str, limit: int, *, rid: str) -> list[dict]:
        self._check("list", tenant_id)
        jobs = sorted(self._mine(tenant_id, user), key=lambda j: j["created_at"], reverse=True)
        return [self._view(j) for j in jobs[:limit]]

    async def count_open(self, tenant_id, user: str, *, rid: str) -> int:
        self._check("count_open", tenant_id)
        return sum(1 for j in self.jobs.values() if j["tenant_id"] == str(tenant_id) and j["status"] != "done")

    async def rows(self, tenant_id, user: str, job_id, *, statuses: list[str], after: int, limit: int,
                   rid: str) -> list[dict]:
        self._check("rows", tenant_id)
        out = [r for r in self._rows_of(str(job_id)) if r["tenant_id"] == str(tenant_id)
               and r["status"] in statuses and r["line"] > after]
        return [{k: r[k] for k in ("line", "status", "code", "message", "fields", "result")} for r in out[:limit]]

    # --- vòng nền ----------------------------------------------------------------------------------------

    async def due(self, now: datetime) -> dict | None:
        self._check("due")
        ready = [j for j in self.jobs.values() if j["status"] != "done" and _iso(j["run_after"]) <= now]
        if not ready:
            return None
        job = min(ready, key=lambda j: (_iso(j["run_after"]), j["created_at"]))
        keys = ("id", "tenant_id", "kind", "created_by", "department_id", "status", "format", "options",
                "archive_bytes", "note", "created_at")
        return {k: job[k] for k in keys}

    async def open_ids(self) -> set[str]:
        self._check("open_ids")
        return {j["id"] for j in self.jobs.values() if j["status"] != "done"}

    async def actor(self, job: dict) -> dict | None:
        self._check("actor", job["tenant_id"])
        return self.users.get((str(job["tenant_id"]), job["created_by"]))

    def _row(self, job: dict, line: int) -> dict:
        row = self.lines[(job["id"], line)]
        assert row["tenant_id"] == str(job["tenant_id"])    # vai trò service chỉ thấy dòng của đơn vị mình
        return row

    @staticmethod
    def _free(row: dict, now: datetime) -> bool:
        return row.get("claimed_until") is None or _iso(row["claimed_until"]) < now

    async def pending(self, job: dict, limit: int, now: datetime) -> list[dict]:
        self._check("pending", job["tenant_id"])
        out = [r for r in self._rows_of(job["id"]) if r["status"] == "pending" and self._free(r, now)][:limit]
        return [json.loads(json.dumps({k: r[k] for k in ("line", "data", "files", "attempts", "result")}))
                for r in out]

    async def start(self, job: dict, at: datetime) -> None:
        self._check("start", job["tenant_id"])
        row = self.jobs[job["id"]]
        if row["status"] == "queued":
            row.update(status="running", started_at=at.isoformat())

    async def claim(self, job: dict, line: int, attempts: int, *, now: datetime, until: datetime, claim_id: str,
                    bump: int = 1) -> dict | None:
        self._check("claim", job["tenant_id"])
        row = self._row(job, line)
        if row["status"] != "pending" or row["attempts"] != attempts or not self._free(row, now):
            return None
        assert attempts + bump <= 20       # check attempts between 0 and 20
        row.update(attempts=attempts + bump, claimed_until=until.isoformat(), claim_id=claim_id)
        return json.loads(json.dumps({k: row[k] for k in ("line", "data", "files", "attempts", "result")}))

    @staticmethod
    def _held(row: dict, claim_id: str) -> bool:
        return row["status"] == "pending" and row.get("claim_id") == claim_id

    async def progress(self, job: dict, line: int, result: dict, *, until: datetime, claim_id: str) -> bool:
        self._check("progress", job["tenant_id"])
        row = self._row(job, line)
        if not self._held(row, claim_id):
            return False
        row.update(result=json.loads(json.dumps(result)), claimed_until=until.isoformat())
        return True

    async def release(self, job: dict, line: int, *, claim_id: str) -> None:
        self._check("release", job["tenant_id"])
        row = self._row(job, line)
        if self._held(row, claim_id):
            row.update(claimed_until=None, claim_id=None)

    async def stranded(self, job: dict) -> list[dict]:
        self._check("stranded", job["tenant_id"])
        return [json.loads(json.dumps({"line": r["line"], "result": r["result"]})) for r in self._rows_of(job["id"])
                if r["status"] == "pending" and "file_ids" in (r["result"] or {})]

    async def drop_files(self, job: dict, line: int, file_ids: list[str]) -> list[dict]:
        self._check("drop_files")
        attached = {f for d in self.hasura.incoming.values() for f in d["file_ids"]}
        out = []
        for fid in file_ids:
            row = self.hasura.files.get(uuid.UUID(fid))
            if (row is None or str(row["tenant_id"]) != str(job["tenant_id"]) or row["created_by"] != job["created_by"]
                    or fid in attached or fid in self.personal):
                continue
            del self.hasura.files[uuid.UUID(fid)]
            out.append({"id": fid, "object_key": row["object_key"]})
        self.dropped.append({"job": job["id"], "line": line, "asked": list(file_ids),
                             "dropped": [o["id"] for o in out]})
        return out

    async def finish(self, job: dict, line: int, values: dict, *, claim_id: str) -> bool:
        self._check("finish", job["tenant_id"])
        row = self._row(job, line)
        if not self._held(row, claim_id):
            return False
        assert values["data"] is None and values["status"] in ("ok", "duplicate", "failed")
        assert (values["status"] == "failed") == (values.get("code") is not None)
        assert values.get("code") is None or re.fullmatch(r"[a-z_]{1,40}", values["code"])
        assert values.get("message") is None or len(values["message"]) <= 500
        row.update(values)
        return True

    async def fail_pending(self, job: dict, values: dict) -> int:
        self._check("fail_pending", job["tenant_id"])
        rows = [r for r in self._rows_of(job["id"]) if r["status"] == "pending"]
        for r in rows:
            r.update(values)
        return len(rows)

    async def reschedule(self, job: dict, values: dict) -> None:
        self._check("reschedule", job["tenant_id"])
        row = self.jobs[job["id"]]
        if row["status"] != "done":
            assert values.get("note") is None or len(values["note"]) <= 500
            row.update(values)

    async def counts(self, job: dict) -> dict[str, int]:
        self._check("counts", job["tenant_id"])
        counts = Counter(r["status"] for r in self._rows_of(job["id"]))
        return {s: counts[s] for s in STATUSES}

    async def close(self, job: dict, values: dict) -> bool:
        self._check("close", job["tenant_id"])
        row = self.jobs[job["id"]]
        if row["status"] == "done":
            return False
        assert values["ok"] + values["duplicate"] + values["failed"] == row["total"]   # import_jobs_closed
        row.update(values)
        # trigger import_jobs_finished: một dòng sổ khi lô chuyển sang done, trong cùng giao dịch
        self.audit.append({
            "actor_id": row["created_by"], "actor_kind": "service", "request_id": row["id"],
            "action": "import.finished", "entity": "core.import_jobs", "entity_id": row["id"],
            "tenant_id": row["tenant_id"],
            "diff": {"kind": row["kind"], "format": row["format"], "register": (row.get("options") or {}).get(
                "register") is True, "total": row["total"], "ok": row["ok"], "duplicate": row["duplicate"],
                "failed": row["failed"]}})
        return True

    async def existing(self, job: dict, line: int, *, symbol: str, issuer: str, issued_on: str) -> dict | None:
        self._check("existing", job["tenant_id"])
        doc = self.hasura.find(str(job["tenant_id"]), symbol, issuer, issued_on)
        return {k: doc[k] for k in ("id", "created_by", "created_at", "register_number")} if doc else None

    async def document(self, job: dict, line: int, document_id: str) -> dict | None:
        self._check("document", job["tenant_id"])
        doc = self.hasura.incoming.get(document_id)
        if doc is None or doc["tenant_id"] != str(job["tenant_id"]):
            return None
        return {k: doc[k] for k in ("id", "created_by", "created_at", "register_number")}

    async def claimed(self, job: dict, line: int, document_id: str) -> bool:
        self._check("claimed", job["tenant_id"])
        return any((r["result"] or {}).get("document_id") == document_id and (j, n) != (job["id"], line)
                   for (j, n), r in self.lines.items() if r["tenant_id"] == str(job["tenant_id"]))


def zip_bytes(entries: dict[str, bytes], *, encrypted: set[str] = frozenset()) -> bytes:
    """Zip trong bộ nhớ. zipfile không ghi được zip có mật khẩu: tên trong ``encrypted`` được bật bit "mã hóa" (bit 0
    của cờ) ở đầu mục và ở thư mục trung tâm, như 7-Zip đặt mật khẩu — đủ để kiểm cờ, nội dung vẫn đọc trần."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(zipfile.ZipInfo(name, date_time=(2026, 10, 23, 8, 0, 0)), data,
                        compress_type=zipfile.ZIP_DEFLATED)
    raw = bytearray(buf.getvalue())
    if encrypted:
        with zipfile.ZipFile(io.BytesIO(bytes(raw))) as zf:
            offsets, pos = {i.filename: i.header_offset for i in zf.infolist()}, zf.start_dir
        for name in encrypted:
            raw[offsets[name] + 6] |= 0x1                     # cờ của đầu mục (local file header)
        while raw[pos:pos + 4] == b"PK\x01\x02":            # bản ghi thư mục trung tâm
            n, m, k = struct.unpack_from("<HHH", raw, pos + 28)
            if bytes(raw[pos + 46:pos + 46 + n]).decode() in encrypted:
                raw[pos + 8] |= 0x1
            pos += 46 + n + m + k
    return bytes(raw)


def ndjson(*rows: dict | str) -> bytes:
    return "\n".join(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows).encode() + b"\n"


def doc(n: int, **overrides) -> dict:
    """Một dòng văn bản đến hợp lệ."""
    row = {"type_code": "CV", "symbol": f"{n}/UBND-VP", "issuer_name": "UBND tỉnh Hưng Yên", "issued_on": "2026-10-15",
           "summary": f"Về việc triển khai chuyển đổi số năm học 2026–2027 (dòng {n})"}
    row.update(overrides)
    return row


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Lab:
    """svc-files thật (create_app) trên đồ giả, vòng nền nạp lô không tự chạy: test gọi từng lượt bằng run()."""

    client: Any
    hasura: ActionHasura
    imports: FakeImportStore
    store: Any
    scanner: Any
    importer: Any
    spool_dir: Any
    offset_s: float = 0.0

    def now(self) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=self.offset_s)

    def advance(self, seconds: float) -> None:
        self.offset_s += seconds

    def run(self, times: int = 1) -> list[bool]:
        """Chạy vòng nền đúng `times` lượt trong event loop của app."""
        return [self.client.portal.call(self.importer.run_once) for _ in range(times)]

    def drain(self, limit: int = 100) -> int:
        """Chạy tới khi không còn lô nào đến giờ; trả số lượt đã làm."""
        for n in range(limit):
            if not self.client.portal.call(self.importer.run_once):
                return n
        raise AssertionError("vòng nền chưa hết việc sau từng ấy lượt")

    def post(self, token: str, data: bytes, *, name: str = "lo.ndjson", mime: str = "application/x-ndjson",
             archive: bytes | None = None, params: dict | None = None, headers: dict | None = None,
             kind: str = "incoming") -> Any:
        files = {"data": (name, data, mime)}
        if archive is not None:
            files["archive"] = ("tep.zip", archive, "application/zip")
        return self.client.post(f"/api/imports/{kind}", params=params or {}, files=files,
                                headers={"Authorization": f"Bearer {token}", **(headers or {})})

    def job(self, job_id: str) -> dict:
        return self.imports.jobs[job_id]

    def lines(self, job_id: str) -> list[dict]:
        return self.imports._rows_of(job_id)


def make_lab(monkeypatch, tmp_path, settings, *, scanner, store, verifier, meili, vault, hasura=None,
             imports=None, **overrides) -> Any:
    """Dựng svc-files có nạp lô bật; trả context manager cho Lab (TestClient chạy lifespan)."""
    import contextlib
    import dataclasses

    from fastapi.testclient import TestClient

    from svc_files.app import create_app
    from svc_files.imports.runner import Importer

    async def idle(self) -> None:       # lifespan không tự chạy vòng nền
        return None

    monkeypatch.setattr(Importer, "run", idle)
    hasura = hasura or ActionHasura()
    imports = imports or FakeImportStore(hasura)
    cfg = dataclasses.replace(settings, **{"import_interval_s": 2.0, "import_spool_dir": str(tmp_path / "spool"),
                                           **overrides})
    app = create_app(cfg, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili, vault=vault,
                     import_store=imports)

    @contextlib.contextmanager
    def running():
        with TestClient(app) as client:
            lab = Lab(client, hasura, imports, store, scanner, app.state.importer, tmp_path / "spool")
            lab.importer.clock = lab.now
            yield lab

    return running()
