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

"""Gọi Hasura GraphQL — CSDL của tệp nằm sau Hasura, svc-files không nối thẳng PostgreSQL.

Hai cách gọi:

- **Thay mặt người dùng** (``visible_file``): chuyển nguyên token của họ, Hasura áp quyền của vai trò.
  svc-files không tự viết lại quy tắc ai được xem tệp nào — quy tắc chỉ nằm ở db/metadata.
- **Vai trò service** (các hàm còn lại): khóa quản trị kèm thuê ước, người thực hiện, request id
  (db/README.md, mục "Dịch vụ gọi Hasura"). Chỉ dùng cho việc người dùng không được tự làm: thêm dòng
  ``core.files`` sau khi quét sạch, ghi sự kiện vào sổ kiểm toán, đọc ``object_key``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx2

INSERT_FILE = """
mutation InsertFile($o: core_files_insert_input!) {
  insert_core_files_one(object: $o) { id }
}"""

LOG_EVENT = """
mutation LogEvent($o: core_audit_log_insert_input!) {
  insert_core_audit_log(objects: [$o]) { affected_rows }
}"""

VISIBLE_FILE = """
query VisibleFile($id: uuid!) {
  core_files_by_pk(id: $id) { id filename mime_type size_bytes sha256 }
}"""

FILE_LOCATION = """
query FileLocation($id: uuid!) {
  core_files_by_pk(id: $id) { object_key }
}"""

# Đồng bộ chỉ mục tìm kiếm: đọc xuyên mọi thuê ước, lật trang theo id. Văn bản cũng được đọc lại khi
# một tệp của nó vừa được đọc chữ (F2.7) — việc đó không đổi updated_at của văn bản.
CHANGED_DOCUMENTS = """
query ChangedDocuments($since: timestamptz!, $limit: Int!, $after: uuid!) {
  office_documents(
    where: {_and: [{id: {_gt: $after}}, {_or: [
      {updated_at: {_gte: $since}},
      {files: {role: {_in: ["main", "attachment"]}, file: {text: {extracted_at: {_gte: $since}}}}}
    ]}]}
    order_by: {id: asc}
    limit: $limit
  ) {
    id tenant_id direction status type_code symbol issuer_name issued_on summary urgency restricted body updated_at
    files(where: {role: {_in: ["main", "attachment"]}}, order_by: {added_at: asc}) {
      file { text { content extracted_at } }
    }
  }
}"""

# Lớp chữ của PDF (F2.7): tệp PDF chính hoặc đính kèm của một văn bản, chưa đọc chữ. Bỏ tệp đã mã hóa, tệp của
# văn bản hạn chế (bản chữ trần sẽ vô hiệu việc mã hóa — F3.7; CSDL cũng chặn, xem migration file_texts), tệp chưa
# gắn vào văn bản nào (chưa biết có hạn chế không), bản thảo và bản phát hành văn bản đi (chỉ mục không dùng).
PENDING_TEXTS = """
query PendingTexts($limit: Int!) {
  core_files(
    where: {_and: [
      {mime_type: {_eq: "application/pdf"}}, {encrypted: {_eq: false}},
      {document_files: {role: {_in: ["main", "attachment"]}}},
      {_not: {text: {}}}, {_not: {document_files: {document: {restricted: {_eq: true}}}}}
    ]}
    order_by: [{created_at: asc}, {id: asc}]
    limit: $limit
  ) { id tenant_id object_key size_bytes }
}"""

SAVE_TEXT = """
mutation SaveText($o: core_file_texts_insert_input!) {
  insert_core_file_texts_one(object: $o, on_conflict: {constraint: file_texts_pkey, update_columns: []}) { file_id }
}"""

# Kết quả tìm kiếm: chỉ những văn bản người dùng được đọc, dữ liệu mới nhất từ CSDL
VISIBLE_DOCUMENTS = """
query VisibleDocuments($ids: [uuid!]!) {
  office_documents(where: {id: {_in: $ids}}) {
    id direction status type_code symbol issuer_name issued_on summary urgency register_number registered_at due_on
  }
}"""

# Văn bản đi để dựng PDF: dùng chung cho bản phát hành (vai trò service) và bản xem trước (token người dùng —
# Hasura áp quyền đọc, người không được đọc văn bản nhận null)
LETTER = """
query Letter($id: uuid!, $tenant: uuid!) {
  office_documents_by_pk(id: $id) {
    id direction status type_code summary body recipients symbol issued_on verify_code
    document_type { name in_symbol }
    department { code }
    signer { full_name }
    events(where: {kind: {_eq: "office.document.approved"}}, order_by: {created_at: desc}, limit: 1) { created_at }
  }
  core_tenants_by_pk(id: $tenant) { code name parent_name place_name head_title }
}"""

# Cổng xác thực: đúng một văn bản đã phát hành, theo mã tra cứu hoặc theo băm (vai trò verifier, chỉ đọc
# khung nhìn office.issued_documents)
VERIFY = """
query Verify($where: office_issued_documents_bool_exp!) {
  office_issued_documents(where: $where, limit: 1) {
    verify_code content_sha256 symbol issued_on type_name issuer_name parent_name summary status
  }
}"""

# Sổ đăng ký văn bản đến / đi của một năm (F2.8): mọi dòng của sổ, kể cả văn bản hạn chế, để sổ in ra liền số
# (vai trò service). Dòng nào người in không được đọc thì registers.py che nội dung — hỏi lại bằng token của họ.
REGISTER = """
query Register($tenant: uuid!, $direction: String!, $year: Int!) {
  core_tenants_by_pk(id: $tenant) { code name parent_name head_title }
  office_registers(where: {direction: {_eq: $direction}, year: {_eq: $year}}) { last_number }
  office_documents(where: {register: {direction: {_eq: $direction}, year: {_eq: $year}}},
                   order_by: {register_number: asc}) {
    id status symbol issuer_name issued_on summary urgency restricted register_number registered_at due_on
    recipients verify_code
    document_type { name }
    department { name }
    signer { full_name }
    assignments(where: {role: {_eq: "lead"}, parent_id: {_is_null: true}, status: {_neq: "cancelled"}},
                order_by: {assigned_at: asc}, limit: 1) {
      user_id department { name }
    }
    events(where: {kind: {_eq: "office.document.issued"}}, limit: 1) { created_at }
  }
  core_users { id full_name }
}"""

# Neo sổ kiểm toán (anchors.py): đầu chuỗi — khóa quản trị, không vai trò nào đọc được core.audit_head
AUDIT_HEAD = """
query AuditHead {
  core_audit_head { last_id last_hash }
}"""

RECORD_ANCHOR = """
mutation RecordAnchor($o: core_audit_anchors_insert_input!) {
  insert_core_audit_anchors_one(object: $o, on_conflict: {constraint: audit_anchors_once, update_columns: []}) { id }
}"""

# Hasura từ chối chính token/phiên của người gọi
AUTH_CODES = {"invalid-jwt", "invalid-headers", "access-denied", "jwt-missing-role-claims"}


class HasuraError(Exception):
    """Hasura không trả lời, hoặc trả lỗi không mong đợi."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class HasuraAuthError(HasuraError):
    """Hasura không nhận token của người dùng."""


@dataclass(frozen=True)
class StoredFile:
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str  # hex


def _bytea(hex_digest: str) -> str:
    return "\\x" + hex_digest


def _hex(bytea: str) -> str:
    return bytea[2:] if bytea.startswith("\\x") else bytea


class HasuraClient:
    def __init__(
        self,
        base_url: str,
        admin_secret: str,
        *,
        timeout_s: float = 10.0,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._secret = admin_secret
        self._http = httpx2.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            r = await self._http.get("/healthz")
        except httpx2.HTTPError:
            return False
        return r.status_code == 200

    async def _call(self, query: str, variables: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            r = await self._http.post("/v1/graphql", json={"query": query, "variables": variables}, headers=headers)
        except httpx2.HTTPError as exc:
            raise HasuraError(f"Không gọi được Hasura: {exc}") from exc
        if r.status_code != 200:
            raise HasuraError(f"Hasura trả HTTP {r.status_code}")
        body = r.json()
        errors = body.get("errors")
        if errors:
            first = errors[0]
            code = (first.get("extensions") or {}).get("code")
            cls = HasuraAuthError if code in AUTH_CODES else HasuraError
            raise cls(str(first.get("message")), code)
        return body["data"]

    def _as_service(self, tenant_id: uuid.UUID, actor_id: str, request_id: str) -> dict[str, str]:
        return {
            "X-Hasura-Admin-Secret": self._secret,
            "X-Hasura-Role": "service",
            "X-Hasura-Tenant-Id": str(tenant_id),
            "X-Hasura-User-Id": actor_id,
            "X-Hasura-Request-Id": request_id,
        }

    async def insert_file(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: str,
        request_id: str,
        file_id: uuid.UUID,
        object_key: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        sha256_hex: str,
        scanned_at: datetime,
    ) -> None:
        """Thêm dòng core.files; tenant_id và created_by do Hasura đặt từ phiên, không gửi trong dữ liệu."""
        await self._call(
            INSERT_FILE,
            {"o": {
                "id": str(file_id),
                "object_key": object_key,
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "sha256": _bytea(sha256_hex),
                "scanned_at": scanned_at.isoformat(),
            }},
            self._as_service(tenant_id, actor_id, request_id),
        )

    async def log_event(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: str,
        request_id: str,
        action: str,
        entity: str,
        entity_id: str,
        details: dict[str, Any],
    ) -> None:
        """Ghi một sự kiện vào core.audit_log; id, thời điểm và hash do trigger trong CSDL đặt."""
        await self._call(
            LOG_EVENT,
            {"o": {
                "actor_id": actor_id,
                "actor_kind": "user",
                "request_id": request_id,
                "action": action,
                "entity": entity,
                "entity_id": entity_id,
                "diff": details,
            }},
            self._as_service(tenant_id, actor_id, request_id),
        )

    async def visible_file(self, token: str, file_id: uuid.UUID) -> StoredFile | None:
        """Thông tin tệp nếu người giữ token được xem, ngược lại None (không phân biệt "không có" và "không được xem")."""
        try:
            data = await self._call(VISIBLE_FILE, {"id": str(file_id)}, {"Authorization": f"Bearer {token}"})
        except HasuraAuthError:
            raise
        except HasuraError as exc:
            if exc.code == "validation-failed":  # vai trò không có quyền đọc core.files (vd tenant_admin)
                return None
            raise
        row = data.get("core_files_by_pk")
        if row is None:
            return None
        return StoredFile(
            id=uuid.UUID(row["id"]),
            filename=row["filename"],
            mime_type=row["mime_type"],
            size_bytes=int(row["size_bytes"]),
            sha256=_hex(row["sha256"]),
        )

    async def visible_documents(self, token: str, ids: list[str]) -> dict[str, dict[str, Any]]:
        """Trong các id cho trước, những văn bản người giữ token được đọc — Hasura áp quyền của vai trò."""
        try:
            data = await self._call(VISIBLE_DOCUMENTS, {"ids": ids}, {"Authorization": f"Bearer {token}"})
        except HasuraAuthError:
            raise
        except HasuraError as exc:
            if exc.code == "validation-failed":  # vai trò không đọc văn bản (vd tenant_admin)
                return {}
            raise
        return {row["id"]: row for row in data["office_documents"]}

    async def changed_documents(self, since: datetime, limit: int, after: str) -> list[dict[str, Any]]:
        """Văn bản sửa (hoặc có tệp vừa được đọc chữ) từ `since` của mọi thuê ước, để đồng bộ chỉ mục tìm kiếm.

        Lật trang theo id (`after`: id cuối của trang trước), không theo offset: văn bản đổi giữa lúc đang lật thì
        thứ tự theo id vẫn đứng yên, không trượt mất dòng nào ở mép trang.

        Gọi bằng khóa quản trị không kèm vai trò (vai trò admin của Hasura): việc nội bộ, chỉ đọc, không
        nhận tham số nào từ người dùng.
        """
        data = await self._call(
            CHANGED_DOCUMENTS,
            {"since": since.isoformat(), "limit": limit, "after": after},
            {"X-Hasura-Admin-Secret": self._secret},
        )
        return data["office_documents"]

    async def pending_texts(self, limit: int) -> list[dict[str, Any]]:
        """Tệp PDF chờ đọc chữ, của mọi thuê ước — khóa quản trị: việc nội bộ, không nhận tham số từ người dùng."""
        data = await self._call(PENDING_TEXTS, {"limit": limit}, {"X-Hasura-Admin-Secret": self._secret})
        return data["core_files"]

    async def save_text(self, *, file_id: str, tenant_id: str, status: str, pages: int | None, content: str,
                        note: str | None) -> None:
        await self._call(SAVE_TEXT, {"o": {"file_id": file_id, "tenant_id": tenant_id, "status": status,
                                           "pages": pages, "content": content, "note": note}},
                         {"X-Hasura-Admin-Secret": self._secret})

    async def file_location(
        self, *, tenant_id: uuid.UUID, actor_id: str, request_id: str, file_id: uuid.UUID
    ) -> str | None:
        data = await self._call(FILE_LOCATION, {"id": str(file_id)}, self._as_service(tenant_id, actor_id, request_id))
        row = data.get("core_files_by_pk")
        return row["object_key"] if row else None

    async def letter(self, *, tenant_id: uuid.UUID, actor_id: str, request_id: str,
                     document_id: uuid.UUID) -> dict[str, Any] | None:
        """Dữ liệu dựng bản phát hành, đọc bằng vai trò service của đúng thuê ước trong yêu cầu."""
        data = await self._call(LETTER, {"id": str(document_id), "tenant": str(tenant_id)},
                                self._as_service(tenant_id, actor_id, request_id))
        return _letter(data)

    async def visible_letter(self, token: str, tenant_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, Any] | None:
        """Dữ liệu dựng bản xem trước nếu người giữ token được đọc văn bản, ngược lại None."""
        try:
            data = await self._call(LETTER, {"id": str(document_id), "tenant": str(tenant_id)},
                                    {"Authorization": f"Bearer {token}"})
        except HasuraAuthError:
            raise
        except HasuraError as exc:
            if exc.code == "validation-failed":  # vai trò không đọc văn bản (vd tenant_admin)
                return None
            raise
        return _letter(data)

    async def register(self, *, tenant_id: uuid.UUID, actor_id: str, request_id: str, direction: str,
                       year: int) -> dict[str, Any]:
        """Mọi dòng của sổ đăng ký một năm, đọc bằng vai trò service của đúng thuê ước trong token người gọi."""
        return await self._call(REGISTER, {"tenant": str(tenant_id), "direction": direction, "year": year},
                                self._as_service(tenant_id, actor_id, request_id))

    async def verify(self, *, code: str | None = None, sha256_hex: str | None = None) -> dict[str, Any] | None:
        """Văn bản đã phát hành có mã tra cứu hoặc băm này (vai trò verifier), không có thì None."""
        where = {"verify_code": {"_eq": code}} if code else {"content_sha256": {"_eq": _bytea(sha256_hex or "")}}
        data = await self._call(VERIFY, {"where": where},
                                {"X-Hasura-Admin-Secret": self._secret, "X-Hasura-Role": "verifier"})
        rows = data["office_issued_documents"]
        if not rows:
            return None
        return {**rows[0], "content_sha256": _hex(rows[0]["content_sha256"])}

    async def audit_head(self) -> tuple[int, str]:
        """(id dòng cuối, hash dòng cuối) của sổ kiểm toán."""
        data = await self._call(AUDIT_HEAD, {}, {"X-Hasura-Admin-Secret": self._secret})
        head = data["core_audit_head"][0]
        return int(head["last_id"]), _hex(head["last_hash"])

    async def record_anchor(self, audit_id: int, hash_hex: str, location: str) -> None:
        await self._call(RECORD_ANCHOR, {"o": {"audit_id": audit_id, "hash": _bytea(hash_hex), "location": location}},
                         {"X-Hasura-Admin-Secret": self._secret})


def _letter(data: dict[str, Any]) -> dict[str, Any] | None:
    doc, tenant = data.get("office_documents_by_pk"), data.get("core_tenants_by_pk")
    if doc is None or tenant is None or doc["direction"] != "out":
        return None
    return {**doc, "tenant": tenant}

