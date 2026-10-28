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

"""Câu GraphQL chỉ Văn phòng điện tử dùng, trên máy khách Hasura chung của svc-files (``svc_files.hasura``).

``OfficeHasura`` thêm vào ``HasuraClient`` các lời gọi của route Văn phòng (dựng văn bản đi, sổ đăng ký, cổng xác
thực, phòng đọc), của liên thông (dispatch.py) và văn bản đích của gợi ý giao việc (assist/similar.py). Cách gọi như
máy khách chung: thay mặt người dùng bằng token của họ, vai trò ``service`` của đúng thuê ước, hoặc khóa quản trị.
Tách khỏi ``hasura.py`` để lõi không mang câu nào của Văn phòng (docs/architecture.md §4.4, §4.7 bước 1).
"""

from __future__ import annotations

import uuid
from typing import Any

from ..hasura import HasuraAuthError, HasuraClient, HasuraError, from_bytea, to_bytea

# Phòng đọc hồ sơ đã nộp lưu (F3.8): hỏi bằng token người dùng, Hasura quyết ai xem được hồ sơ nào
VISIBLE_CASE_FILE = """
query VisibleCaseFile($id: uuid!) {
  office_case_files_by_pk(id: $id) { id code title year status closed_on archived_at archive_key archive_sha256 }
}"""

# Phân tích dữ liệu đã nộp lưu (#304): mọi hồ sơ đã nộp lưu người giữ token xem được — Hasura lọc theo vai trò, đơn vị
ARCHIVED_CASE_FILES = """
query ArchivedCaseFiles {
  office_case_files(where: {status: {_eq: "archived"}}, order_by: {archived_at: asc}) {
    id code archive_key archive_sha256
  }
}"""

# Văn bản đi để dựng PDF: dùng chung cho bản phát hành (vai trò service) và bản xem trước (token người dùng —
# Hasura áp quyền đọc, người không được đọc văn bản nhận null)
LETTER = """
query Letter($id: uuid!, $tenant: uuid!) {
  office_documents_by_pk(id: $id) {
    id direction status type_code summary body recipients symbol issued_on verify_code restricted language
    document_type { name in_symbol }
    department { code }
    signer { full_name }
    events(where: {kind: {_eq: "office.document.approved"}}, order_by: {created_at: desc}, limit: 1) { created_at }
  }
  core_tenants_by_pk(id: $tenant) { code name parent_name place_name head_title }
}"""

# Cổng xác thực: đúng một văn bản đã phát hành, theo mã tra cứu hoặc theo băm (vai trò verifier, chỉ đọc
# khung nhìn office.issued_documents). Năm cột chữ ký số (F4.5) null với văn bản không ký
VERIFY = """
query Verify($where: office_issued_documents_bool_exp!) {
  office_issued_documents(where: $where, limit: 1) {
    verify_code content_sha256 symbol issued_on type_name issuer_name parent_name summary status
    signature_level signed_at signer_name signer_ca certificate_serial
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
    document_type { code name }
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

# Liên thông trong hệ thống (F3.12): dòng outbox, văn bản nguồn và bản phát hành của nó — khóa quản trị không kèm vai
# trò (dòng outbox, văn bản thuộc đơn vị gửi; bản sao thuộc đơn vị nhận). svc-workflow chỉ gửi id dòng, mọi thứ khác
# đọc từ CSDL: bên gọi không chỉ định được tệp nào.
DISPATCH_SOURCE = """
query DispatchSource($id: uuid!) {
  office_dispatches_by_pk(id: $id) {
    id tenant_id to_tenant_id status file_id source_sha256
    document {
      id status restricted content_sha256
      files(where: {role: {_eq: "issued"}}) {
        file { id object_key filename mime_type size_bytes sha256 encrypted storage_tier }
      }
    }
  }
}"""

# Bản sao đã có chưa (id định trước = dispatches.file_id): gọi lại sau khi đã chép thì trả đúng dòng đó
DISPATCHED_FILE = """
query DispatchedFile($id: uuid!) {
  core_files_by_pk(id: $id) { id tenant_id object_key size_bytes sha256 }
}"""

# Văn bản đích của tác tử gợi ý giao việc (F4.3, /internal/similar-documents): vai trò service lọc thuê ước nên văn
# bản của thuê ước khác trả null; đọc cả văn bản hạn chế để route từ chối (409) trước khi tìm gì
SIMILAR_TARGET = """
query SimilarTarget($id: uuid!) {
  office_documents_by_pk(id: $id) { id direction restricted summary }
}"""


class OfficeHasura(HasuraClient):
    """``HasuraClient`` cộng các lời gọi của Văn phòng; app.py dựng nó thay máy khách chung khi Văn phòng bật."""

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
        where = {"verify_code": {"_eq": code}} if code else {"content_sha256": {"_eq": to_bytea(sha256_hex or "")}}
        data = await self._call(VERIFY, {"where": where},
                                {"X-Hasura-Admin-Secret": self._secret, "X-Hasura-Role": "verifier"})
        rows = data["office_issued_documents"]
        if not rows:
            return None
        return {**rows[0], "content_sha256": from_bytea(rows[0]["content_sha256"])}

    async def dispatch_source(self, dispatch_id: uuid.UUID) -> dict[str, Any] | None:
        """Dòng office.dispatches kèm văn bản nguồn; ``document.issued``: bản phát hành (0 hoặc 1 tệp). Băm đổi sang
        hex. Không có dòng thì None."""
        data = await self._call(DISPATCH_SOURCE, {"id": str(dispatch_id)}, {"X-Hasura-Admin-Secret": self._secret})
        row = data.get("office_dispatches_by_pk")
        if row is None:
            return None
        doc = {k: v for k, v in row["document"].items() if k != "files"}
        issued = [{**link["file"], "sha256": from_bytea(link["file"]["sha256"])} for link in row["document"]["files"]]
        content = from_bytea(doc["content_sha256"]) if doc["content_sha256"] else None
        return {**row, "source_sha256": from_bytea(row["source_sha256"]),
                "document": {**doc, "content_sha256": content, "issued": issued}}

    async def dispatched_file(self, file_id: uuid.UUID) -> dict[str, Any] | None:
        """Dòng core.files có id này, của bất kỳ thuê ước nào (bản sao liên thông đã chép chưa); băm dạng hex."""
        data = await self._call(DISPATCHED_FILE, {"id": str(file_id)}, {"X-Hasura-Admin-Secret": self._secret})
        row = data.get("core_files_by_pk")
        return {**row, "sha256": from_bytea(row["sha256"])} if row else None

    async def visible_case_file(self, token: str, case_file_id: uuid.UUID) -> dict[str, Any] | None:
        """Hồ sơ nếu người giữ token được xem, ngược lại None; vai trò không đọc hồ sơ cũng là None."""
        try:
            data = await self._call(VISIBLE_CASE_FILE, {"id": str(case_file_id)}, {"Authorization": f"Bearer {token}"})
        except HasuraAuthError:
            raise
        except HasuraError as exc:
            if exc.code == "validation-failed":
                return None
            raise
        row = data.get("office_case_files_by_pk")
        if not row:
            return None
        return {**row, "archive_sha256": from_bytea(row["archive_sha256"]) if row["archive_sha256"] else None}

    async def archived_case_files(self, token: str) -> list[dict[str, Any]]:
        """Hồ sơ đã nộp lưu người giữ token xem được (vị trí gói, băm manifest). Route chỉ gọi cho lãnh đạo đơn vị, vai
        trò đọc được hồ sơ: ``validation-failed`` ở đây là metadata Hasura hỏng, đi ra như mọi ``HasuraError`` (503),
        không thành "chưa có hồ sơ nào nộp lưu"."""
        data = await self._call(ARCHIVED_CASE_FILES, {}, {"Authorization": f"Bearer {token}"})
        return [{**row, "archive_sha256": from_bytea(row["archive_sha256"])} for row in data["office_case_files"]
                if row["archive_key"] and row["archive_sha256"]]

    async def similar_target(self, tenant_id: uuid.UUID, document_id: uuid.UUID, *, request_id: str = "",
                             actor_id: str = "svc-files") -> dict[str, Any] | None:
        """``{id, direction, restricted, summary}`` của văn bản đích (F4.3) trong đúng thuê ước, None khi không có."""
        data = await self.as_role("service", tenant_id, actor_id, request_id or str(uuid.uuid4()), SIMILAR_TARGET,
                                  {"id": str(document_id)})
        return data.get("office_documents_by_pk")


def _letter(data: dict[str, Any]) -> dict[str, Any] | None:
    doc, tenant = data.get("office_documents_by_pk"), data.get("core_tenants_by_pk")
    if doc is None or tenant is None or doc["direction"] != "out":
        return None
    return {**doc, "tenant": tenant}
