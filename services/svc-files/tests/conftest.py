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

"""Đồ dùng chung cho test: khóa ký token giả lập Keycloak, ClamAV, kho đối tượng và Hasura giả."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
import unicodedata
import uuid
from collections.abc import AsyncIterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import BinaryIO

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from svc_files.app import create_app
from svc_files.auth import HASURA_CLAIMS, TokenVerifier
from svc_files.clamav import ScanError, ScanResult
from svc_files.config import Settings
from svc_files.hasura import HasuraAuthError, HasuraError, Location, StoredFile
from svc_files.sealed import VaultError
from svc_files.search import SearchError
from svc_files.storage import ObjectMissing, StorageError

ISSUER = "https://moc.example/realms/moc"
TENANT_A = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000a")

# Chuỗi kiểm thử EICAR, tách hai nửa để chính tệp mã nguồn này không bị phần mềm diệt virus chặn.
EICAR = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*").encode()


@dataclass
class _Key:
    key: object


class StaticKeys:
    """Thay PyJWKClient: trả về đúng một khóa công khai, không gọi mạng."""

    def __init__(self, public_key: object) -> None:
        self._key = _Key(public_key)

    def get_signing_key_from_jwt(self, token: str) -> _Key:
        return self._key


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def make_token(signing_key):
    def _make(*, tenant: str | None = str(TENANT_A), sub: str = "u-van-thu", ttl: int = 300, role: str = "clerk",
              **overrides) -> str:
        now = int(time.time())
        ns = {"x-hasura-user-id": sub, "x-hasura-allowed-roles": [role], "x-hasura-default-role": role}
        if tenant is not None:
            ns["x-hasura-tenant-id"] = tenant
        claims = {"iss": ISSUER, "sub": sub, "iat": now, "exp": now + ttl, HASURA_CLAIMS: ns, **overrides}
        return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test"})

    return _make


@pytest.fixture
def verifier(signing_key) -> TokenVerifier:
    return TokenVerifier(ISSUER, "http://unused/jwks", keys=StaticKeys(signing_key.public_key()))


LOCKED_ZIP = b"PK\x03\x04\x14\x00\x01\x00"   # đầu tệp zip, cờ "có mật khẩu" bật


class FakeScanner:
    """ClamAV giả: coi mọi tệp có chuỗi EICAR là nhiễm."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.scanned = b""

    async def ping(self) -> bool:
        return not self.down

    async def scan(self, chunks: AsyncIterable[bytes]) -> ScanResult:
        data = b"".join([c async for c in chunks])
        if self.down:
            raise ScanError("clamd tắt")
        self.scanned = data
        if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data:
            return ScanResult(clean=False, signature="Eicar-Test-Signature")
        if data.startswith(LOCKED_ZIP):  # như ClamAV có AlertEncrypted: tệp nén có mật khẩu
            return ScanResult(clean=False, signature="Heuristics.Encrypted.Zip")
        return ScanResult(clean=True)


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.deleted: list[str] = []
        self.unreadable: set[str] = set()      # khóa đọc lỗi (kho đứt kết nối, hỏng đĩa) dù đối tượng vẫn còn
        self.reads: list[str] = []             # khóa đã mở để đọc (đọc văn bản đến: tệp hạn chế không được mở)

    def ensure_bucket(self) -> None:
        pass

    def ping(self) -> bool:
        return True

    def put(self, key: str, body: BinaryIO, *, size: int, content_type: str, sha256_hex: str) -> None:
        self.objects[key] = {"data": body.read(), "size": size, "content_type": content_type, "sha256": sha256_hex}

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)

    def read_stream(self, key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        self.reads.append(key)
        if key in self.unreadable:
            raise StorageError(f"đứt kết nối khi đọc {key}")
        if key not in self.objects:
            raise ObjectMissing(f"không có {key}")
        data = self.objects[key]["data"]
        return iter([data[i:i + chunk_size] for i in range(0, len(data), chunk_size)])


@dataclass
class FakeHasura:
    """Hasura giả: người tải lên thấy tệp của mình; tệp trong `shared` thì mọi người cùng thuê ước thấy.

    Văn bản (`documents`): thấy khi cùng thuê ước và `readers` là None (mọi người) hoặc chứa sub.
    """

    files: dict[uuid.UUID, dict] = field(default_factory=dict)
    documents: dict[str, dict] = field(default_factory=dict)
    shared: set[uuid.UUID] = field(default_factory=set)
    events: list[dict] = field(default_factory=list)
    down: bool = False
    reject_tokens: bool = False
    fail_code: str | None = None      # mã lỗi GraphQL giả lập cho insert_file

    def _check(self) -> None:
        if self.down:
            raise HasuraError("Hasura tắt")

    async def ping(self) -> bool:
        return not self.down

    async def aclose(self) -> None:
        pass

    async def insert_file(self, *, tenant_id, actor_id, request_id, file_id, object_key, **row) -> None:
        self._check()
        if self.fail_code:
            raise HasuraError("bị từ chối", self.fail_code)
        self.files[file_id] = {"tenant_id": tenant_id, "created_by": actor_id, "request_id": request_id,
                               "object_key": object_key, **row}

    fail_events: bool = False         # ghi sổ kiểm toán lỗi (Hasura vẫn đọc được)

    async def log_event(self, **event) -> None:
        self._check()
        if self.fail_events:
            raise HasuraError("không ghi được sổ")
        self.events.append(event)

    async def visible_file(self, token: str, file_id: uuid.UUID) -> StoredFile | None:
        self._check()
        if self.reject_tokens:
            raise HasuraAuthError("JWTExpired", "invalid-jwt")
        ns = jwt.decode(token, options={"verify_signature": False})[HASURA_CLAIMS]
        row = self.files.get(file_id)
        if row is None or str(row["tenant_id"]) != ns["x-hasura-tenant-id"]:
            return None
        if row["created_by"] != ns["x-hasura-user-id"] and file_id not in self.shared:
            return None
        return StoredFile(file_id, row["filename"], row["mime_type"], row["size_bytes"], row["sha256_hex"],
                          encrypted=row.get("wrapped_dek") is not None, created_by=row["created_by"])

    async def file_location(self, *, tenant_id, actor_id, request_id, file_id) -> Location | None:
        self._check()
        row = self.files.get(file_id)
        if not row or row["tenant_id"] != tenant_id:
            return None
        return Location(row["object_key"], row.get("wrapped_dek"), file_id in self.in_restricted)

    def add_document(self, tenant: uuid.UUID, summary: str, *, readers: set[str] | None = None, **cols) -> str:
        doc_id = str(uuid.uuid4())
        self.documents[doc_id] = {
            "id": doc_id, "tenant_id": str(tenant), "direction": "in", "status": "received", "type_code": "CV",
            "symbol": f"{len(self.documents) + 1}/UBND-VP", "issuer_name": "UBND tỉnh", "issued_on": "2026-10-15",
            "summary": summary, "urgency": "normal", "register_number": None, "registered_at": None,
            "due_on": None, "updated_at": f"2026-10-18T09:00:{len(self.documents):02d}+00:00",
            "readers": readers, **cols,
        }
        return doc_id

    async def visible_documents(self, token: str, ids: list[str]) -> dict[str, dict]:
        self._check()
        if self.reject_tokens:
            raise HasuraAuthError("JWTExpired", "invalid-jwt")
        ns = jwt.decode(token, options={"verify_signature": False})[HASURA_CLAIMS]
        out = {}
        for doc_id in ids:
            row = self.documents.get(doc_id)
            if row and row["tenant_id"] == ns["x-hasura-tenant-id"] and (
                row["readers"] is None or ns["x-hasura-user-id"] in row["readers"]
            ):
                out[doc_id] = {k: v for k, v in row.items() if k not in {"readers", "tenant_id", "updated_at"}}
        return out

    # --- văn bản đi -------------------------------------------------------------------------------------

    letters: dict[str, dict] = field(default_factory=dict)

    def add_letter(self, tenant: uuid.UUID, *, readers: set[str] | None = None, **cols) -> str:
        doc_id = str(uuid.uuid4())
        self.letters[doc_id] = {
            "id": doc_id, "direction": "out", "status": "approved", "type_code": "TB",
            "summary": "Về việc họp giao ban tháng 11", "body": "Khoa thông báo lịch họp.\nĐề nghị tham dự đầy đủ.",
            "recipients": ["Các bộ môn"], "symbol": "05/TB-CNTT", "issued_on": "2026-10-19",
            "verify_code": "ABCDE23456", "document_type": {"name": "Thông báo", "in_symbol": True},
            "department": {"code": "ĐT"}, "signer": {"full_name": "Phạm Minh Đức"},
            "events": [{"created_at": "2026-10-19T03:00:00+00:00"}],
            "tenant": {"code": "CNTT", "name": "Khoa Công nghệ thông tin", "parent_name": "Trường Đại học Thử",
                       "place_name": "Hà Nội", "head_title": "Trưởng khoa"},
            "_tenant_id": str(tenant), "_readers": readers, **cols,
        }
        return doc_id

    @staticmethod
    def _public(row: dict) -> dict:
        return {k: v for k, v in row.items() if not k.startswith("_")}

    async def letter(self, *, tenant_id, actor_id, request_id, document_id) -> dict | None:
        self._check()
        row = self.letters.get(str(document_id))
        return self._public(row) if row and row["_tenant_id"] == str(tenant_id) else None

    async def visible_letter(self, token: str, tenant_id, document_id) -> dict | None:
        self._check()
        if self.reject_tokens:
            raise HasuraAuthError("JWTExpired", "invalid-jwt")
        ns = jwt.decode(token, options={"verify_signature": False})[HASURA_CLAIMS]
        row = self.letters.get(str(document_id))
        if row is None or row["_tenant_id"] != ns["x-hasura-tenant-id"]:
            return None
        if row["_readers"] is not None and ns["x-hasura-user-id"] not in row["_readers"]:
            return None
        return self._public(row)

    async def verify(self, *, code: str | None = None, sha256_hex: str | None = None) -> dict | None:
        self._check()
        for row in self.letters.values():
            if row["status"] not in ("issued", "archived"):
                continue
            if (code and row["verify_code"] == code) or (sha256_hex and row.get("content_sha256") == sha256_hex):
                return {"verify_code": row["verify_code"], "content_sha256": row["content_sha256"],
                        "symbol": row["symbol"], "issued_on": row["issued_on"], "type_name": row["document_type"]["name"],
                        "issuer_name": row["tenant"]["name"], "parent_name": row["tenant"]["parent_name"],
                        "summary": row["summary"] if row.get("is_public") else None, "status": row["status"]}
        return None

    # --- lớp chữ của PDF (F2.7) ---------------------------------------------------------------------------

    pdfs: list[dict] = field(default_factory=list)      # tệp PDF đã gắn vào văn bản (thứ tự như PENDING_TEXTS)
    texts: dict[str, dict] = field(default_factory=dict)
    rejected: set[str] = field(default_factory=set)     # id tệp mà CSDL không nhận kết quả đọc (chỉ nhận "failed" trơn)
    change_reads: list[str] = field(default_factory=list)   # `after` của từng lần đọc CHANGED_DOCUMENTS

    async def pending_texts(self, limit: int) -> list[dict]:
        self._check()
        return [f for f in self.pdfs if f["id"] not in self.texts][:limit]

    async def save_text(self, *, file_id: str, tenant_id: str, **row) -> None:
        """row: status, pages, content, note, page_starts (F4.2) — như SAVE_TEXT."""
        self._check()
        if file_id in self.rejected and row["note"] != "not saved":
            raise HasuraError("Hasura trả lỗi: integer out of range")
        self.texts.setdefault(file_id, {"tenant_id": tenant_id, **row})      # on_conflict: giữ bản đầu

    # --- sổ đăng ký (F2.8) --------------------------------------------------------------------------------

    def add_registered(self, tenant: uuid.UUID, direction: str, number: int, *, year: int = 2026,
                       readers: set[str] | None = None, **cols) -> str:
        """Văn bản đã vào sổ `direction` năm `year` với số `number`; readers như add_document."""
        defaults = {"status": "registered" if direction == "in" else "issued", "restricted": readers is not None,
                    "register_number": number, "document_type": {"name": "Công văn"}, "department": None,
                    "signer": None, "recipients": None, "verify_code": None, "assignments": [], "events": [],
                    "registered_at": f"{year}-10-0{min(number, 9)}T02:00:00+00:00"}
        summary = cols.pop("summary", f"Văn bản số {number}")
        return self.add_document(tenant, summary, readers=readers, direction=direction, _year=year,
                                 **{**defaults, **cols})

    async def register(self, *, tenant_id, actor_id, request_id, direction: str, year: int) -> dict:
        self._check()
        rows = sorted((r for r in self.documents.values() if r["tenant_id"] == str(tenant_id)
                       and r["direction"] == direction and r.get("_year") == year), key=lambda r: r["register_number"])
        hidden = {"readers", "tenant_id", "updated_at", "_year", "direction", "type_code"}
        return {
            "core_tenants_by_pk": {"code": "CNTT", "name": "Khoa Công nghệ thông tin",
                                   "parent_name": "Trường Đại học Thử", "head_title": "Trưởng khoa"},
            "office_registers": [{"last_number": max(r["register_number"] for r in rows)}] if rows else [],
            "office_documents": [{k: v for k, v in r.items() if k not in hidden} for r in rows],
            "core_users": [{"id": "u-chuyen-vien", "full_name": "Lê Thị Hoa"}],
        }

    async def changed_documents(self, since, limit: int, after: str) -> list[dict]:
        self._check()
        self.change_reads.append(after)

        def changed(r: dict) -> bool:      # như _or của CHANGED_DOCUMENTS: sửa văn bản, hoặc tệp vừa được đọc chữ
            texts = [(f.get("file") or {}).get("text") for f in r.get("files") or []]
            return any(datetime.fromisoformat(t) >= since
                       for t in [r["updated_at"], *(x["extracted_at"] for x in texts if x)])

        rows = sorted((r for r in self.documents.values() if changed(r) and r["id"] > after), key=lambda r: r["id"])
        return [{k: v for k, v in r.items() if k != "readers"} for r in rows[:limit]]

    # --- trợ lý hỏi đáp (F4.2) ------------------------------------------------------------------------------

    chunk_reads: list[str] = field(default_factory=list)    # `after` của từng lần đọc CHUNK_SOURCES
    ask_calls: list[dict] = field(default_factory=list)     # mỗi lần hậu kiểm: cách gọi và các id hỏi

    CHUNK_ROLES = ("main", "attachment", "issued")
    CHUNK_FIELDS = ("id", "tenant_id", "direction", "status", "type_code", "symbol", "issuer_name", "issued_on",
                    "summary", "restricted", "department_id", "created_by", "updated_at", "document_type")

    async def chunk_sources(self, since, limit: int, after: str) -> list[dict]:
        """Như CHUNK_SOURCES: văn bản đổi (sửa, tệp vừa đọc chữ, giao việc mới — kể cả giao việc đã hủy) từ `since`;
        trả giao việc chưa hủy, tệp main/attachment/issued theo thứ tự gắn. Văn bản thêm bằng add_document mang
        `files` (``{"role", "file_id", "added_at", "file": {"encrypted", "text": {...}}}``) và `assignments`
        (``{"department_id", "user_id", "assigned_at", "status"}``)."""
        self._check()
        self.chunk_reads.append(after)
        defaults = {"restricted": False, "department_id": None, "created_by": "u-van-thu",
                    "document_type": {"name": "Công văn"}}

        def files(r: dict) -> list[dict]:
            return sorted((f for f in r.get("files") or [] if f.get("role") in self.CHUNK_ROLES),
                          key=lambda f: f.get("added_at") or "")

        def changed(r: dict) -> bool:
            texts = [((f.get("file") or {}).get("text") or {}).get("extracted_at") for f in files(r)]
            assigned = [a.get("assigned_at") for a in r.get("assignments") or []]
            return any(t and datetime.fromisoformat(t) >= since for t in [r["updated_at"], *texts, *assigned])

        rows = sorted((r for r in self.documents.values() if changed(r) and r["id"] > after), key=lambda r: r["id"])
        out = []
        for r in rows[:limit]:
            row = {k: copy.deepcopy(r.get(k, defaults.get(k))) for k in self.CHUNK_FIELDS}
            row["assignments"] = [{k: a.get(k) for k in ("department_id", "user_id", "assigned_at")}
                                  for a in r.get("assignments") or [] if a.get("status") != "cancelled"]
            row["files"] = [{"role": f["role"], "file_id": f.get("file_id"),
                             "file": copy.deepcopy(f.get("file") or {})} for f in files(r)]
            out.append(row)
        return out

    @staticmethod
    def _ask_row(row: dict) -> dict:
        keys = ("id", "direction", "status", "type_code", "symbol", "issuer_name", "issued_on", "summary")
        return {**{k: row.get(k) for k in keys}, "restricted": bool(row.get("restricted")),
                "document_type": copy.deepcopy(row.get("document_type") or {"name": "Công văn"})}

    async def ask_documents(self, token: str, ids: list[str]) -> dict[str, dict]:
        """Hậu kiểm bằng token người hỏi: như visible_documents (cùng thuê ước, `readers`), kèm cột restricted."""
        self._check()
        if self.reject_tokens:
            raise HasuraAuthError("JWTExpired", "invalid-jwt")
        ns = jwt.decode(token, options={"verify_signature": False})[HASURA_CLAIMS]
        self.ask_calls.append({"by": "token", "sub": ns["x-hasura-user-id"], "ids": list(ids)})
        out = {}
        for doc_id in ids:
            row = self.documents.get(doc_id)
            if row and row["tenant_id"] == ns["x-hasura-tenant-id"] and (
                row["readers"] is None or ns["x-hasura-user-id"] in row["readers"]
            ):
                out[doc_id] = self._ask_row(row)
        return out

    async def ask_documents_service(self, tenant_id, ids: list[str], **_session) -> dict[str, dict]:
        """Vai trò service của đúng thuê ước: mọi văn bản không hạn chế."""
        self._check()
        self.ask_calls.append({"by": "service", "tenant_id": str(tenant_id), "ids": list(ids)})
        return {doc_id: self._ask_row(row) for doc_id in ids if (row := self.documents.get(doc_id))
                and row["tenant_id"] == str(tenant_id) and not row.get("restricted")}

    async def similar_target(self, tenant_id, document_id, **_session) -> dict | None:
        """Văn bản đích của /internal/similar-documents (F4.3): vai trò service của đúng thuê ước, kể cả hạn chế."""
        self._check()
        row = self.documents.get(str(document_id))
        if row is None or row["tenant_id"] != str(tenant_id):
            return None
        return {"id": row["id"], "direction": row["direction"], "restricted": bool(row.get("restricted")),
                "summary": row["summary"]}

    # --- liên thông trong hệ thống (F3.12) ------------------------------------------------------------------

    dispatches: dict[str, dict] = field(default_factory=dict)

    def add_dispatch(self, store: FakeStore, data: bytes, *, to_tenant: uuid.UUID, document: dict | None = None,
                     file: dict | None = None, **cols) -> str:
        """Văn bản đi của TENANT_A đã phát hành, bản phát hành `data` nằm trong kho; một dòng outbox gửi `to_tenant`.
        Dạng dữ liệu như hasura.dispatch_source trả (băm hex, `document.issued`)."""
        sha = hashlib.sha256(data).hexdigest()
        source = uuid.uuid4()
        key = f"tenant/{TENANT_A}/2026/10/{source}"
        store.objects[key] = {"data": data, "size": len(data), "content_type": "application/pdf", "sha256": sha}
        issued = {"id": str(source), "object_key": key, "filename": "05-TB-CNTT.pdf", "mime_type": "application/pdf",
                  "size_bytes": len(data), "sha256": sha, "encrypted": False, "storage_tier": "hot", **(file or {})}
        doc = {"id": str(uuid.uuid4()), "status": "issued", "restricted": False, "content_sha256": sha,
               "issued": [issued], **(document or {})}
        dispatch_id = str(uuid.uuid4())
        self.dispatches[dispatch_id] = {
            "id": dispatch_id, "tenant_id": str(TENANT_A), "to_tenant_id": str(to_tenant), "status": "pending",
            "file_id": str(uuid.uuid4()), "source_sha256": sha, "document": doc, **cols,
        }
        return dispatch_id

    async def dispatch_source(self, dispatch_id: uuid.UUID) -> dict | None:
        self._check()
        return copy.deepcopy(self.dispatches.get(str(dispatch_id)))

    async def dispatched_file(self, file_id: uuid.UUID) -> dict | None:
        self._check()
        row = self.files.get(file_id)
        return {"id": str(file_id), "tenant_id": str(row["tenant_id"]), "object_key": row["object_key"],
                "size_bytes": row["size_bytes"], "sha256": row["sha256_hex"]} if row else None


    # --- đọc văn bản đến (F4.1): vai trò agent ------------------------------------------------------------

    suggestions: dict[str, dict] = field(default_factory=dict)   # office.intake_suggestions theo file_id
    agent_calls: list[dict] = field(default_factory=list)       # mỗi lời gọi as_role: phiên và tên câu GraphQL
    agent_events: list[dict] = field(default_factory=list)      # dòng sổ tác tử đã ghi, cột preset như Hasura đặt
    fail_agent: bool = False          # mọi lời gọi vai trò agent lỗi (CSDL không ghi được sổ)
    sealed: set[str] = field(default_factory=set)   # file_id mà trigger intake_suggestions_guard chặn (văn bản hạn chế)
    # tệp (kể cả tệp rõ) đang gắn vào văn bản hạn chế: FileLocation trả restricted_links khác rỗng
    in_restricted: set[uuid.UUID] = field(default_factory=set)
    document_types: list[dict] = field(default_factory=lambda: [
        {"code": c, "name": n, "in_symbol": True}
        for c, n in (("CV", "Công văn"), ("QĐ", "Quyết định"), ("TB", "Thông báo"), ("KH", "Kế hoạch"))])
    admin_queries: list[str] = field(default_factory=list)

    AGENT_SUGGESTION_COLUMNS = {"file_id", "requested_by", "status", "method", "pages", "fields", "warnings",
                                "summary_source", "model", "duration_ms"}
    AGENT_AUDIT_COLUMNS = {"request_id", "action", "entity", "entity_id", "diff"}
    # check của quyền insert core_audit_log cho vai trò agent (F4.1 đọc văn bản đến, F4.2 trợ lý hỏi đáp)
    AGENT_AUDIT_PAIRS = {("intake.suggested", "core.files"), ("assistant.answered", "ai.questions")}

    async def as_role(self, role: str, tenant_id, user_id: str, request_id: str, query: str, variables: dict) -> dict:
        """Như Hasura với quyền của vai trò agent (db/metadata, luồng A): cột được ghi, preset, check."""
        self._check()
        name = re.search(r"(?:query|mutation)\s+(\w+)", query).group(1)
        self.agent_calls.append({"role": role, "tenant_id": str(tenant_id), "user_id": user_id,
                                 "request_id": request_id, "op": name})
        if self.fail_agent:
            raise HasuraError("không ghi được")
        if role != "agent":
            raise HasuraError("vai trò không có quyền", "validation-failed")
        if name == "GoiYDaCo":
            row = self.suggestions.get(variables["id"])
            return {"office_intake_suggestions_by_pk":
                    {k: v for k, v in row.items() if k not in {"tenant_id", "agent_id", "requested_by"}}
                    if row and row["tenant_id"] == str(tenant_id) else None}
        event = variables["e"]
        if set(event) - self.AGENT_AUDIT_COLUMNS:
            raise HasuraError("cột không được phép", "validation-failed")
        if (event.get("action"), event.get("entity")) not in self.AGENT_AUDIT_PAIRS:
            raise HasuraError("check constraint of an insert permission has failed", "permission-error")
        out: dict = {"insert_core_audit_log": {"affected_rows": 1}}
        if name == "LuuGoiY":
            o = variables["o"]
            if set(o) - self.AGENT_SUGGESTION_COLUMNS:
                raise HasuraError("cột không được phép", "validation-failed")
            if o["file_id"] in self.sealed:
                raise HasuraError("intake_suggestions_sealed: tệp của văn bản hạn chế", "constraint-violation")
            read_at = f"2026-10-21T08:00:{len(self.agent_events) % 60:02d}+00:00"
            self.suggestions[o["file_id"]] = {**o, "tenant_id": str(tenant_id), "agent_id": user_id,
                                              "read_at": read_at}
            out["insert_office_intake_suggestions_one"] = {"file_id": o["file_id"], "read_at": read_at}
        elif name not in ("GhiSoTacTu", "GhiSoTroLy"):
            raise HasuraError(f"câu lạ {name}")
        self.agent_events.append({**event, "tenant_id": str(tenant_id), "actor_id": user_id, "actor_kind": "agent"})
        return out

    async def admin(self, query: str, variables: dict, headers: dict | None = None) -> dict:
        self._check()
        self.admin_queries.append(query)
        if "LoaiVanBan" in query:
            return {"office_document_types": self.document_types}
        raise HasuraError("câu lạ")


def text_pdf(*lines: str, pages: int = 1) -> bytes:
    """PDF nhỏ có lớp chữ (Helvetica, chỉ ASCII), mỗi trang đủ các dòng `lines`; pages=0: không có trang nào."""
    def esc(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream = ("BT /F1 12 Tf 72 760 Td 14 TL " + " ".join(f"({esc(line)}) '" for line in lines) + " ET").encode()
    kids = " ".join(f"{4 + i} 0 R" for i in range(pages))
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", f"<</Type/Pages/Kids[{kids}]/Count {pages}>>".encode(),
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    objs += [f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 3 0 R>>>>"
             f"/Contents {4 + pages} 0 R>>".encode()] * pages
    objs.append(b"<</Length %d>>\nstream\n" % len(stream) + stream + b"\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def pages_pdf(*pages: tuple[str, ...]) -> bytes:
    """PDF nhiều trang, mỗi trang các dòng riêng (Helvetica, chỉ ASCII); trang ``()`` không có chữ (như trang scan)."""
    def esc(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    n = len(pages)
    kids = " ".join(f"{4 + i} 0 R" for i in range(n))
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", f"<</Type/Pages/Kids[{kids}]/Count {n}>>".encode(),
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    objs += [f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 3 0 R>>>>"
             f"/Contents {4 + n + i} 0 R>>".encode() for i in range(n)]
    for lines in pages:
        stream = ("BT /F1 12 Tf 72 760 Td 14 TL " + " ".join(f"({esc(line)}) '" for line in lines) + " ET").encode()
        objs.append(b"<</Length %d>>\nstream\n" % len(stream) + stream + b"\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


# TSV của tesseract (``tsv``) cho một trang công văn ngắn: dòng level 1 là cỡ trang, level 5 là từng từ
SAMPLE_TSV = "\n".join("\t".join(map(str, row)) for row in [
    ("level", "page_num", "block_num", "par_num", "line_num", "word_num", "left", "top", "width", "height", "conf",
     "text"),
    (1, 1, 0, 0, 0, 0, 0, 0, 2000, 2829, -1, ""),
    (2, 1, 1, 0, 0, 0, 150, 120, 700, 120, -1, ""),
    (3, 1, 1, 1, 0, 0, 150, 120, 700, 120, -1, ""),
    (4, 1, 1, 1, 1, 0, 150, 120, 700, 50, -1, ""),
    (5, 1, 1, 1, 1, 1, 150, 120, 200, 50, 96.1, "UBND"),
    (5, 1, 1, 1, 1, 2, 370, 120, 200, 50, 95.3, "TỈNH"),
    (5, 1, 1, 1, 1, 3, 590, 120, 200, 50, 94.8, "MẪU"),
    (4, 1, 1, 1, 2, 0, 150, 190, 700, 50, -1, ""),
    (5, 1, 1, 1, 2, 1, 150, 190, 120, 50, 91.0, "Số:"),
    (5, 1, 1, 1, 2, 2, 290, 190, 400, 50, 88.2, "105/TB-ĐHM"),
    (2, 1, 2, 0, 0, 0, 700, 700, 600, 60, -1, ""),
    (3, 1, 2, 1, 0, 0, 700, 700, 600, 60, -1, ""),
    (4, 1, 2, 1, 1, 0, 700, 700, 600, 60, -1, ""),
    (5, 1, 2, 1, 1, 1, 700, 700, 300, 60, 97.0, "THÔNG"),
    (5, 1, 2, 1, 1, 2, 1020, 700, 280, 60, 96.4, "BÁO"),
    (4, 1, 2, 1, 2, 0, 400, 780, 1200, 50, -1, ""),
    (5, 1, 2, 1, 2, 1, 400, 780, 1200, 50, 90.0, "Lịch họp giao ban tháng 11 của nhà trường"),
]) + "\n"


def fake_tesseract(directory, *, tsv: str = SAMPLE_TSV, sleep_s: float = 0.0, exit_code: int = 0, stderr: str = "",
                   kill: int | None = None):
    """Tesseract giả (``MOC_TESSERACT_BIN``): ghi lại tham số, biến OMP_THREAD_LIMIT, ảnh nhận được, pid vào
    ``directory``; ngủ ``sleep_s`` giây; in ``tsv`` (và ``stderr``); tự giết bằng tín hiệu ``kill`` (không đổ lõi),
    không thì thoát với ``exit_code``."""
    import sys

    kill = None if kill is None else int(kill)      # signal.Signals → số, để in vào mã
    path = directory / "tesseract"
    path.write_text(f"""#!{sys.executable}
import json, os, resource, sys, time
d = {str(directory)!r}
open(os.path.join(d, "pid"), "w").write(str(os.getpid()))
json.dump({{"args": sys.argv[1:], "omp": os.environ.get("OMP_THREAD_LIMIT")}}, open(os.path.join(d, "call.json"), "w"))
open(os.path.join(d, "stdin.png"), "wb").write(sys.stdin.buffer.read())
time.sleep({sleep_s!r})
sys.stdout.write({json.dumps(tsv)})
sys.stderr.write({json.dumps(stderr)})
sys.stdout.flush()
sys.stderr.flush()
if {kill!r} is not None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.kill(os.getpid(), {kill!r})
sys.exit({exit_code})
""", encoding="utf-8")
    path.chmod(0o755)
    return path


def fold(text: str) -> str:
    """Bỏ dấu tiếng Việt như Meilisearch, để FakeMeili tìm không dấu được."""
    text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


@dataclass
class FakeMeili:
    """Meilisearch giả: khớp khi mọi từ của câu tìm có trong số ký hiệu / trích yếu / cơ quan ban hành / nội dung
    (hoặc trong đúng các trường `attributes` khi được chỉ định)."""

    docs: dict[str, dict] = field(default_factory=dict)
    searches: list[dict] = field(default_factory=list)
    down: bool = False
    tasks: int = 0

    async def ping(self) -> bool:
        return not self.down

    async def aclose(self) -> None:
        pass

    async def ensure_index(self) -> int:
        if self.down:
            raise SearchError("Meilisearch tắt")
        self.tasks += 1
        return self.tasks

    async def upsert(self, docs: list[dict]) -> int:
        if self.down:
            raise SearchError("Meilisearch tắt")
        for d in docs:
            self.docs[d["id"]] = d
        self.tasks += 1
        return self.tasks

    async def search(self, q: str, filters: list[str], limit: int, offset: int,
                     attributes: list[str] | None = None) -> list[str]:
        if self.down:
            raise SearchError("Meilisearch tắt")
        self.searches.append({"q": q, "filters": filters, "limit": limit, "offset": offset, "attributes": attributes})
        conds = [re.fullmatch(r'(\w+) = "?(.*?)"?', f).groups() for f in filters if " IN " not in f]
        only = [set(re.findall(r'"([^"]*)"', f)) for f in filters if f.startswith("id IN ")]
        fields = attributes or ("symbol", "summary", "issuer_name", "content")
        words = fold(q).split()
        hits = [
            d["id"] for d in self.docs.values()
            if all(str(d.get(k)) == v for k, v in conds) and all(d["id"] in ids for ids in only)
            and all(w in fold(" ".join(str(d.get(f) or "") for f in fields)) for w in words)
        ]
        return hits[offset:offset + limit]


# --- chỉ mục đoạn của trợ lý hỏi đáp (F4.2) ---------------------------------------------------------------------

_FILTER_TOKEN = re.compile(r'\s*(?:("(?:[^"\\]|\\.)*")|(!=|>=|<=|=|>|<|\(|\)|\[|\]|,)|([^\s()\[\],=!<>"]+))')


def _filter_tokens(expr: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    while pos < len(expr):
        m = _FILTER_TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            if expr[pos:].strip():
                raise ValueError(f"bộ lọc sai ở {pos}: {expr!r}")
            break
        pos = m.end()
        if m.group(1) is not None:
            out.append(("str", re.sub(r"\\(.)", r"\1", m.group(1)[1:-1])))
        elif m.group(2) is not None:
            out.append(("op", m.group(2)))
        else:
            out.append(("word", m.group(3)))
    return out


def meili_filter(expr, doc: dict) -> bool:
    """Bộ lọc Meilisearch (tập con đủ cho F4.2) trên một tài liệu: ``=``, ``!=``, ``IN [...]``, ``IS [NOT] NULL``,
    ``EXISTS``, ``AND``/``OR``/``NOT``, ngoặc; mảng khớp khi có phần tử bằng; chuỗi trong ngoặc kép có thoát ``\\"``
    ``\\\\``. ``expr``: chuỗi, hoặc danh sách (AND) mà phần tử là chuỗi hoặc danh sách con (OR) như API."""
    if expr is None:
        return True
    if isinstance(expr, list):
        return all(any(meili_filter(x, doc) for x in e) if isinstance(e, list) else meili_filter(e, doc) for e in expr)
    tokens = _filter_tokens(expr)
    pos = 0

    def peek(kind=None, value=None):
        if pos >= len(tokens):
            return False
        k, v = tokens[pos]
        return (kind is None or k == kind) and (value is None or (v.upper() if k == "word" else v) == value)

    def take():
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def value():
        k, v = take()
        if k == "str":
            return v
        if k != "word":
            raise ValueError(f"cần giá trị: {expr!r}")
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return v

    def equal(a, b) -> bool:
        if isinstance(a, list):
            return any(equal(x, b) for x in a)
        if isinstance(a, bool) or a is None:
            return False
        if isinstance(a, int | float) and isinstance(b, int | float):
            return a == b
        return str(a) == str(b)

    def primary():
        if peek("op", "("):
            take()
            got = disjunction()
            if not peek("op", ")"):
                raise ValueError(f"thiếu ')': {expr!r}")
            take()
            return got
        if peek("word", "NOT"):
            take()
            return not primary()
        _, attr = take()
        here = doc.get(attr)
        if peek("op", "="):
            take()
            return equal(here, value())
        if peek("op", "!="):
            take()
            return not equal(here, value())
        if peek("word", "IN"):
            take()
            if not peek("op", "["):
                raise ValueError(f"thiếu '[': {expr!r}")
            take()
            values = []
            while not peek("op", "]"):
                values.append(value())
                if peek("op", ","):
                    take()
            take()
            return any(equal(here, v) for v in values)
        if peek("word", "IS"):
            take()
            negate = peek("word", "NOT") and take() is not None
            word = take()[1].upper()
            if word != "NULL":
                raise ValueError(f"chỉ hỗ trợ IS [NOT] NULL: {expr!r}")
            is_null = attr in doc and doc[attr] is None
            return not is_null if negate else is_null
        if peek("word", "EXISTS"):
            take()
            return attr in doc
        raise ValueError(f"toán tử không hỗ trợ trong bộ lọc giả: {expr!r}")

    def conjunction():
        got = primary()
        while peek("word", "AND"):
            take()
            got = primary() and got
        return got

    def disjunction():
        got = conjunction()
        while peek("word", "OR"):
            take()
            got = conjunction() or got
        return got

    result = disjunction()
    if pos != len(tokens):
        raise ValueError(f"thừa ở cuối bộ lọc: {expr!r}")
    return result


@dataclass
class FakeChunkIndex:
    """Chỉ mục ``chunks`` giả (assist/meili.ChunkIndex): lọc thật theo cú pháp Meilisearch (meili_filter), cập nhật
    một phần như PUT (giữ trường không gửi, gộp ``_vectors`` theo embedder), tìm từ khóa đơn giản trên chữ không dấu:
    điểm = tỷ lệ từ của câu tìm có trong tài liệu (``scores`` đặt sẵn điểm cho từng id). ``frequency=True``: như
    chiến lược ``frequency`` thật — tài liệu phải có từ hiếm nhất của câu tìm (ít tài liệu có nhất trong bộ lọc, bằng
    nhau thì từ đứng trước; từ không tài liệu nào có thì bỏ qua)."""

    docs: dict[str, dict] = field(default_factory=dict)
    embedders: dict[str, dict] = field(default_factory=dict)
    settings: list[dict] = field(default_factory=list)        # mỗi lần ensure_embedder: cấu hình đã áp
    writes: list[tuple[str, list]] = field(default_factory=list)   # ("replace" | "update" | "delete", dữ liệu)
    fetches: list[dict] = field(default_factory=list)
    searches: list[dict] = field(default_factory=list)
    multi_searches: list[list[dict]] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    frequency: bool = False
    waited: list[int] = field(default_factory=list)
    down: bool = False
    fail_tasks: bool = False      # tác vụ ghi được nhận nhưng xử lý lỗi (wait báo lỗi)
    failed_tasks: set[int] = field(default_factory=set)       # chỉ các tác vụ này lỗi
    embedder_fails: bool = False  # Meilisearch nhận rồi từ chối cấu hình embedder (tác vụ lỗi, không áp gì)
    tasks: int = 0

    def _task(self) -> int:
        if self.down:
            raise SearchError("Meilisearch tắt")
        self.tasks += 1
        return self.tasks

    async def ping(self) -> bool:
        return not self.down

    async def aclose(self) -> None:
        pass

    async def ensure(self) -> int:
        return self._task()

    async def ensure_embedder(self, embedder: str | None, dims: int) -> int | None:
        task = self._task()
        if self.embedder_fails:
            self.failed_tasks.add(task)
            return task
        removed = [name for name in self.embedders if name.startswith("emb_") and name != embedder]
        for name in removed:
            del self.embedders[name]
            for d in self.docs.values():
                (d.get("_vectors") or {}).pop(name, None)
        if embedder:
            self.embedders[embedder] = {"source": "userProvided", "dimensions": dims}
        self.settings.append({"embedder": embedder, "dims": dims, "removed": removed})
        return task

    async def wait(self, task_uid: int, timeout_s: float = 30.0) -> None:
        if self.down:
            raise SearchError("Meilisearch tắt")
        if self.fail_tasks or task_uid in self.failed_tasks:
            raise SearchError(f"Tác vụ {task_uid} lỗi")
        self.waited.append(task_uid)

    async def fetch(self, filter, fields: list[str], limit: int, offset: int = 0) -> list[dict]:  # noqa: A002
        if self.down:
            raise SearchError("Meilisearch tắt")
        self.fetches.append({"filter": filter, "fields": fields, "limit": limit, "offset": offset})
        rows = [d for d in self.docs.values() if meili_filter(filter, d)]
        return [{k: copy.deepcopy(d[k]) for k in fields if k in d} for d in rows[offset:offset + limit]]

    async def count(self, filter) -> int:  # noqa: A002
        if self.down:
            raise SearchError("Meilisearch tắt")
        return sum(meili_filter(filter, d) for d in self.docs.values())

    async def replace(self, docs: list[dict]) -> int:
        task = self._task()
        self.writes.append(("replace", copy.deepcopy(docs)))
        for d in docs:
            self.docs.pop(d["id"], None)
            self.docs[d["id"]] = copy.deepcopy(d)
        return task

    async def update(self, docs: list[dict]) -> int:
        task = self._task()
        self.writes.append(("update", copy.deepcopy(docs)))
        for d in docs:
            row = self.docs.setdefault(d["id"], {"id": d["id"]})
            for k, v in copy.deepcopy(d).items():
                if k == "_vectors" and isinstance(row.get(k), dict):
                    row[k].update(v)
                else:
                    row[k] = v
        return task

    async def delete_ids(self, ids: list[str]) -> int:
        task = self._task()
        self.writes.append(("delete", list(ids)))
        for i in ids:
            self.docs.pop(i, None)
        return task

    async def delete_where(self, filter) -> int:  # noqa: A002
        task = self._task()
        gone = [i for i, d in self.docs.items() if meili_filter(filter, d)]
        self.writes.append(("delete", gone))
        for i in gone:
            del self.docs[i]
        return task

    def _ranked(self, body: dict) -> list[tuple[float, int, dict]]:
        words = fold(body.get("q") or "").split()
        threshold = body.get("rankingScoreThreshold", 0.0)
        fields = ("text", "symbol", "summary", "issuer_name")
        rows = [(i, d, fold(" ".join(str(d.get(f) or "") for f in fields)).split())
                for i, d in enumerate(self.docs.values()) if meili_filter(body.get("filter"), d)]
        required = None
        if self.frequency and body.get("matchingStrategy") == "frequency":
            df = [(sum(w in text for _, _, text in rows), n, w) for n, w in enumerate(words)]
            required = min(((c, n, w) for c, n, w in df if c), default=(0, 0, None))[2]
        ranked = []
        for i, d, text in rows:
            matched = sum(w in text for w in words)
            score = self.scores.get(d["id"], matched / len(words) if words else 1.0)
            if (words and not matched and d["id"] not in self.scores) or score < threshold:
                continue
            if required is not None and required not in text:
                continue
            ranked.append((-score, i, d))
        ranked.sort(key=lambda t: (t[0], t[1]))
        return ranked

    @staticmethod
    def _hits(body: dict, ranked: list[tuple[float, int, dict]]) -> list[dict]:
        offset, limit = body.get("offset", 0), body.get("limit", 20)
        hits = []
        for neg, _, d in ranked[offset:offset + limit]:
            hit = {k: copy.deepcopy(d[k]) for k in body.get("attributesToRetrieve") or d if k in d}
            if body.get("showRankingScore"):
                hit["_rankingScore"] = -neg
            hits.append(hit)
        return hits

    async def search(self, body: dict) -> list[dict]:
        if self.down:
            raise SearchError("Meilisearch tắt")
        self.searches.append(copy.deepcopy(body))
        return self._hits(body, self._ranked(body))

    async def multi_search(self, bodies: list[dict]) -> list[tuple[list[dict], int]]:
        if self.down:
            raise SearchError("Meilisearch tắt")
        self.multi_searches.append(copy.deepcopy(bodies))
        return [(self._hits(b, ranked), len(ranked)) for b in bodies for ranked in [self._ranked(b)]]


OLLAMA_MODEL = "qwen3:1.7b"
GOOD_SUMMARY = "Về việc tổ chức họp giao ban công tác tháng 11 năm 2026"


class FakeOllama:
    """Ollama giả: /api/tags liệt kê `models`; /api/chat trả `reply` (chuỗi nội dung, hoặc hàm nhận yêu cầu)."""

    def __init__(self, *, models=(OLLAMA_MODEL,), reply=None, status: int = 200) -> None:
        self.models = list(models)
        self.reply = reply if reply is not None else json.dumps({"trich_yeu": GOOD_SUMMARY}, ensure_ascii=False)
        self.status = status
        self.requests: list[httpx2.Request] = []

    def calls(self, path: str) -> list[dict]:
        return [json.loads(r.content) if r.content else {} for r in self.requests if r.url.path == path]

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.url.path == "/api/tags":
            return httpx2.Response(200, json={"models": [{"name": m, "model": m} for m in self.models]})
        if request.url.path == "/api/generate":
            return httpx2.Response(200, json={"model": OLLAMA_MODEL, "done": True})
        reply = self.reply
        if callable(reply):
            reply = await reply(request)
            if isinstance(reply, httpx2.Response):
                return reply
        return httpx2.Response(self.status, json={"model": OLLAMA_MODEL, "done": True,
                                                  "message": {"role": "assistant", "content": reply}})


class FakeVault:
    """Két giả: khóa dữ liệu ngẫu nhiên, "bọc" bằng cách ghi nhớ trong từ điển; đếm số lần mở khóa."""

    def __init__(self) -> None:
        self.keys: dict[str, bytes] = {}
        self.down = False
        self.unwrapped: list[str] = []

    async def datakey(self) -> tuple[bytes, str]:
        if self.down:
            raise VaultError("két tắt")
        key = os.urandom(32)
        wrapped = f"vault:v1:{len(self.keys)}"
        self.keys[wrapped] = key
        return key, wrapped

    async def unwrap(self, wrapped: str) -> bytes:
        if self.down:
            raise VaultError("két tắt")
        self.unwrapped.append(wrapped)
        return self.keys[wrapped]

    async def aclose(self) -> None:
        pass


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env(
        {
            "MOC_OIDC_ISSUER": ISSUER,
            "MOC_OIDC_JWKS_URL": "http://unused/jwks",
            "SEAWEEDFS_S3_ACCESS_KEY": "test",
            "SEAWEEDFS_S3_SECRET_KEY": "test",
            "HASURA_ADMIN_SECRET": "test",
            "MEILISEARCH_API_KEY": "test",
            "MOC_SEARCH_SYNC_INTERVAL_S": "0",
            # trợ lý tắt: không vòng chỉ mục đoạn nào gọi Meilisearch thật (0 chỉ hợp lệ khi tắt; test trợ lý tự tiêm
            # chunk_indexer giả vào create_app)
            "MOC_ASK_ENABLED": "false",
            "MOC_ASK_SYNC_INTERVAL_S": "0",
            "MOC_AUDIT_ANCHOR_INTERVAL_S": "0",
            "MOC_TEXT_INTERVAL_S": "0",
            "MOC_FILES_MAX_MB": "1",
            "MOC_AI_URL": "",       # không dò Ollama trong test (test đọc văn bản đến tự tiêm mô hình giả)
        }
    )


@pytest.fixture
def log_records():
    """Các dòng nhật ký JSON của logger svc_files (đã giải mã), trong lúc chạy test."""
    import logging

    records: list[dict] = []

    class Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(json.loads(record.getMessage()))

    logger, handler = logging.getLogger("svc_files"), Grab()
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield records
    logger.removeHandler(handler)
    logger.setLevel(level)


@pytest.fixture
def scanner() -> FakeScanner:
    return FakeScanner()


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def hasura() -> FakeHasura:
    return FakeHasura()


@pytest.fixture
def meili() -> FakeMeili:
    return FakeMeili()


@pytest.fixture
def vault() -> FakeVault:
    return FakeVault()


@pytest.fixture
def client(settings, scanner, store, verifier, hasura, meili, vault):
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                     vault=vault)
    with TestClient(app) as c:
        yield c
