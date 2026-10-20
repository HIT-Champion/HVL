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

import re
import time
import unicodedata
import uuid
from collections.abc import AsyncIterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import BinaryIO

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from svc_files.app import create_app
from svc_files.auth import HASURA_CLAIMS, TokenVerifier
from svc_files.clamav import ScanError, ScanResult
from svc_files.config import Settings
from svc_files.hasura import HasuraAuthError, HasuraError, StoredFile
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
        return ScanResult(clean=True)


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.deleted: list[str] = []
        self.unreadable: set[str] = set()      # khóa đọc lỗi (kho đứt kết nối, hỏng đĩa) dù đối tượng vẫn còn

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

    async def log_event(self, **event) -> None:
        self._check()
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
        return StoredFile(file_id, row["filename"], row["mime_type"], row["size_bytes"], row["sha256_hex"])

    async def file_location(self, *, tenant_id, actor_id, request_id, file_id) -> str | None:
        self._check()
        row = self.files.get(file_id)
        return row["object_key"] if row and row["tenant_id"] == tenant_id else None

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
            "MOC_AUDIT_ANCHOR_INTERVAL_S": "0",
            "MOC_TEXT_INTERVAL_S": "0",
            "MOC_FILES_MAX_MB": "1",
        }
    )


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
def client(settings, scanner, store, verifier, hasura, meili):
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili)
    with TestClient(app) as c:
        yield c
