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

"""Neo hash đầu chuỗi sổ kiểm toán ra bucket lạnh có khóa ghi (F2.12).

Superuser PostgreSQL tắt được trigger, sửa một dòng sổ rồi tính lại hash của mọi dòng phía sau: chuỗi lại liền
mạch và core.audit_verify() báo nguyên vẹn. Mốc neo chặn đường này: định kỳ chép (last_id, last_hash) ra một
đối tượng trên bucket bật S3 Object Lock, chế độ COMPLIANCE. Trong hạn giữ không ai xóa, ghi đè hay rút ngắn hạn
được, kể cả tài khoản quản trị kho (đã thử trên SeaweedFS 4.48). Viết lại chuỗi từ dòng k thì mọi mốc từ k trở
đi không còn khớp, và lệnh `moc audit verify` chỉ ra khoảng dòng bị viết lại.

Khóa đối tượng: ``anchors/<audit_id, 12 chữ số>-<hash hex>.json``. Hash nằm ngay trong tên nên lệnh kiểm chỉ
liệt kê bucket, không tải từng tệp; nội dung tệp chép lại đúng hai giá trị đó cho người đọc, không gì khác, nên hai
lần ghi cùng một mốc cho cùng một nội dung. Ghi đè một khóa chỉ tạo thêm phiên bản (bucket khóa ghi luôn bật
versioning), bản đầu vẫn còn: khi liệt kê, mốc có phiên bản khác nội dung mang cờ.

Khóa ghi chỉ có hiệu lực khi đi qua cổng S3: SeaweedFS chạy với -filer.disableHttp và nằm riêng mạng storage với
svc-files (docker-compose.yml), để không ai đi vòng qua filer.

Vòng neo nhớ mốc vừa ghi trong bộ nhớ, không hỏi bảng core.audit_anchors trong CSDL: người sửa được CSDL thêm một
dòng giả vào bảng đó cũng không làm vòng neo dừng. Mốc nhớ được cũng là mốc in ở chân sổ đăng ký (registers.py).

Chữ ký mốc neo: bucket lạnh nằm trên chính máy chủ, nên mốc còn được chép ra ngoài (``moc audit anchor --to``,
``--publish``: một kho git công khai) và két ký từng mốc để người ngoài tự kiểm. Khóa Ed25519 ``moc-anchor`` trong
transit do két sinh, không cho xuất; chỉ svc-files được ký và đọc khóa công khai (policy trong
platform/openbao/start.sh). Thông điệp ký là năm dòng UTF-8, dòng nào cũng kết thúc bằng một ``\\n``:

    signet-anchor-v1
    <audit_id, số thập phân>
    <hash, 64 chữ hex thường>
    <anchored_at: lúc kho ghi phiên bản đầu của mốc, giờ UTC, dạng 2026-10-25T01:15:03Z>
    <URL công khai của hệ thống, MOC_PUBLIC_URL>

Ed25519 thuần (RFC 8032, không băm trước). Dòng đầu tách chữ ký này khỏi mọi việc ký khác; URL gắn mốc với đúng một
hệ thống. Mọi trường đều suy ra từ mốc đã khóa trong bucket, và Ed25519 cho cùng một chữ ký với cùng thông điệp: ký
lại một mốc ra đúng chữ ký cũ, hai tiến trình cùng neo một mốc không làm ra hai nội dung khác nhau. Chữ ký tách rời
nằm cạnh mốc (``anchors/<…>.sig.json``, cũng khóa ghi). Két chưa có khóa (két khởi tạo trước khi có chữ ký mốc neo)
thì mốc vẫn ghi như cũ, chỉ không có chữ ký; mốc cũ không chữ ký vẫn hợp lệ. Khóa công khai ở ``GET
/api/verify/anchor-key.pem`` (SubjectPublicKeyInfo); vân tay ``sha256:<hex>`` là SHA-256 của dạng DER. Người ngoài
kiểm bằng OpenSSL 3: docs/van-hanh.md mục "Mốc neo công khai".

Chạy tay trong container (lệnh ``moc audit anchor``, ``moc audit verify`` trên máy chủ gọi qua docker compose):

    python -m svc_files.anchors now     # neo ngay nếu đầu chuỗi đã đổi, in mốc (kèm chữ ký) dạng JSON
    python -m svc_files.anchors list    # liệt kê mốc trong bucket, kèm cờ ghi đè, xóa
    python -m svc_files.anchors key     # khóa công khai ký mốc neo (PEM, vân tay); két chưa có khóa: null
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .sealed import VaultError
from .storage import StorageError

log = logging.getLogger("svc_files")

PREFIX = "anchors/"
KEY = re.compile(r"^anchors/(\d{12})-([0-9a-f]{64})\.json$")
MESSAGE = "signet-anchor-v1"            # dòng đầu của thông điệp ký, cũng là trường "v" của dòng mốc chép ra ngoài
SIGNING_KEY = "moc-anchor"              # khóa Ed25519 trong transit của két
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HASH = re.compile(r"^[0-9a-f]{64}$")
# DER của SubjectPublicKeyInfo cho Ed25519 (RFC 8410): tiền tố cố định rồi 32 byte khóa
SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
KEY_TTL_S = 300.0                       # khóa công khai đọc từ két dùng lại bao lâu cho đường công khai


def anchor_key(audit_id: int, hash_hex: str) -> str:
    return f"{PREFIX}{audit_id:012d}-{hash_hex}.json"


def signature_key(audit_id: int, hash_hex: str) -> str:
    """Chữ ký tách rời của mốc, cạnh mốc; không khớp KEY nên lệnh liệt kê mốc bỏ qua."""
    return f"{PREFIX}{audit_id:012d}-{hash_hex}.sig.json"


def stamp(at: datetime) -> str:
    """Giờ trong thông điệp ký: UTC, tới giây (kho ghi LastModified tới giây)."""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def anchor_message(audit_id: int, hash_hex: str, anchored_at: str, system: str) -> bytes:
    """Thông điệp két ký cho một mốc (docstring của mô-đun). Trường sai dạng thì ValueError: không trường nào được
    chứa xuống dòng, nếu không hai bộ giá trị khác nhau có thể cho cùng một thông điệp."""
    if (type(audit_id) is not int or audit_id < 1 or not HASH.match(hash_hex) or not STAMP.match(anchored_at)
            or not system or any(ch in system for ch in "\r\n")):
        raise ValueError("mốc neo không đúng dạng để ký")
    return "".join(f"{line}\n" for line in (MESSAGE, str(audit_id), hash_hex, anchored_at, system)).encode()


@dataclass(frozen=True)
class PublicKey:
    version: int            # phiên bản khóa trong transit
    raw: bytes              # 32 byte khóa Ed25519

    @property
    def der(self) -> bytes:
        return SPKI_PREFIX + self.raw

    @property
    def pem(self) -> str:
        return f"-----BEGIN PUBLIC KEY-----\n{base64.b64encode(self.der).decode()}\n-----END PUBLIC KEY-----\n"

    @property
    def fingerprint(self) -> str:
        """``sha256:<hex>`` của DER — như ``openssl pkey -pubin -outform DER | sha256sum``."""
        return "sha256:" + hashlib.sha256(self.der).hexdigest()


def _raw_public(value: object) -> bytes:
    """Khóa công khai két trả: base64 của 32 byte (transit ed25519); nhận cả PEM SubjectPublicKeyInfo cho chắc."""
    text = str(value or "").strip()
    try:
        if text.startswith("-----BEGIN PUBLIC KEY-----"):
            der = base64.b64decode("".join(text.splitlines()[1:-1]), validate=True)
            raw = der[len(SPKI_PREFIX):] if der.startswith(SPKI_PREFIX) else b""
        else:
            raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raw = b""
    if len(raw) != 32:
        raise VaultError("két trả khóa công khai Ed25519 không đúng dạng", status=200)
    return raw


@dataclass(frozen=True)
class Signed:
    """Chữ ký của một mốc, đủ để người ngoài dựng lại thông điệp và kiểm."""
    anchored_at: str        # như trong thông điệp: UTC, tới giây
    system: str
    key: str                # vân tay khóa công khai, sha256:<hex>
    sig: str                # 64 byte chữ ký Ed25519, base64


@dataclass(frozen=True)
class Mark:
    """Mốc mới nhất vòng neo đã ghi hoặc thấy trong bucket — in ở chân sổ đăng ký."""
    audit_id: int
    hash: str
    anchored_at: datetime


@dataclass(frozen=True)
class Anchor:
    audit_id: int
    hash: str               # hex
    anchored_at: str        # lúc kho ghi phiên bản đầu tiên (ISO 8601)
    key: str
    overwritten: bool = False   # có phiên bản khác nội dung cùng khóa (bản đầu vẫn còn)
    deleted: bool = False       # có dấu xóa (bản đầu vẫn còn)


@dataclass(frozen=True)
class Anchored:
    audit_id: int
    hash: str
    location: str
    new: bool               # False: đầu chuỗi chưa đổi từ mốc trước, hoặc mốc này đã có trong bucket
    anchored_at: str | None = None      # lúc kho ghi phiên bản đầu (như trong thông điệp ký); None: không ghi lượt này
    signed: Signed | None = None        # None: két chưa có khóa ký mốc neo, hoặc ký lỗi (nhật ký anchor_unsigned)


class _Transit(Protocol):
    async def transit_key(self, name: str) -> dict[str, Any] | None: ...
    async def transit_sign_ed25519(self, name: str, data: bytes, *, version: int) -> bytes: ...


class AnchorSigner:
    """Ký mốc bằng khóa ``moc-anchor`` của két và tự kiểm chữ ký két trả trước khi dùng: két ký kiểu khác (băm trước,
    có ngữ cảnh) hay khóa vừa đổi thì mốc thành không chữ ký, không bao giờ ra một chữ ký người ngoài kiểm không qua."""

    def __init__(self, vault: _Transit, system: str, *, key: str = SIGNING_KEY,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._vault = vault
        self.system = system
        self.key = key
        self._clock = clock
        self._cached: tuple[float, PublicKey | None] | None = None

    async def public_key(self, *, fresh: bool = False) -> PublicKey | None:
        """Phiên bản mới nhất của khóa. None: két chưa có khóa, hoặc policy cũ của svc-files chưa cho đọc (két khởi tạo
        trước khi có chữ ký mốc neo — docs/van-hanh.md mục Két bí mật). Két không trả lời: VaultError."""
        now = self._clock()
        if not fresh and self._cached is not None and now - self._cached[0] < KEY_TTL_S:
            return self._cached[1]
        try:
            info = await self._vault.transit_key(self.key)
        except VaultError as exc:
            if exc.status != 403:
                raise
            info = None
        found = None
        if info is not None:
            if info.get("type") != "ed25519":
                raise VaultError(f"khóa {self.key} trong két không phải Ed25519", status=200)
            try:
                version = int(info["latest_version"])
                found = PublicKey(version, _raw_public(info["keys"][str(version)]["public_key"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise VaultError(f"két trả thông tin khóa {self.key} lạ: {type(exc).__name__}", status=200) from None
        self._cached = (now, found)
        return found

    async def sign(self, audit_id: int, hash_hex: str, anchored_at: datetime) -> Signed | None:
        """Chữ ký của mốc; két chưa có khóa thì None. Két lỗi hoặc trả chữ ký không khớp khóa: VaultError."""
        key = await self.public_key(fresh=True)
        if key is None:
            return None
        at = stamp(anchored_at)
        message = anchor_message(audit_id, hash_hex, at, self.system)
        sig = await self._vault.transit_sign_ed25519(self.key, message, version=key.version)
        try:
            Ed25519PublicKey.from_public_bytes(key.raw).verify(sig, message)
        except (InvalidSignature, ValueError):
            raise VaultError("chữ ký két trả không khớp khóa công khai moc-anchor", status=200) from None
        return Signed(anchored_at=at, system=self.system, key=key.fingerprint, sig=base64.b64encode(sig).decode())


def signed_line(audit_id: int, hash_hex: str, signed: Signed) -> dict[str, Any]:
    """Một mốc có chữ ký dạng JSON — nội dung tệp .sig.json, cũng là dòng `moc audit anchor --to` chép ra ngoài."""
    return {"v": MESSAGE, "audit_id": audit_id, "hash": hash_hex, "anchored_at": signed.anchored_at,
            "system": signed.system, "key": signed.key, "sig": signed.sig}


class AnchorStore:
    """Bucket lạnh: tạo với Object Lock, ghi mốc kèm hạn giữ COMPLIANCE, liệt kê mốc."""

    def __init__(self, s3: Any, bucket: str, retention_days: int) -> None:
        self._s3 = s3
        self.bucket = bucket
        self.retention = timedelta(days=retention_days)

    def ensure_bucket(self) -> None:
        """Tạo bucket bật khóa ghi; bucket có sẵn mà không bật khóa thì từ chối neo vào đó."""
        try:
            self._s3.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket", "NotFound"}:
                raise StorageError(f"Không đọc được bucket {self.bucket}: {exc}") from exc
            try:
                self._s3.create_bucket(Bucket=self.bucket, ObjectLockEnabledForBucket=True)
            except (BotoCoreError, ClientError) as create_exc:
                raise StorageError(f"Không tạo được bucket {self.bucket}: {create_exc}") from create_exc
        except BotoCoreError as exc:
            raise StorageError(f"Không kết nối được kho đối tượng: {exc}") from exc
        if not self.locked():
            raise StorageError(f"Bucket {self.bucket} không bật khóa ghi (S3 Object Lock): không neo vào đây được")

    def locked(self) -> bool:
        try:
            conf = self._s3.get_object_lock_configuration(Bucket=self.bucket)
        except ClientError:
            return False
        except BotoCoreError as exc:
            raise StorageError(f"Không kết nối được kho đối tượng: {exc}") from exc
        return conf.get("ObjectLockConfiguration", {}).get("ObjectLockEnabled") == "Enabled"

    def _exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise StorageError(f"Không đọc được {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"Không kết nối được kho đối tượng: {exc}") from exc
        return True

    def _put_locked(self, key: str, body: bytes, now: datetime) -> bool:
        """Ghi một đối tượng khóa ghi; đã có thì không ghi lại (ghi lại là thêm phiên bản, lúc kiểm mang cờ ghi đè)."""
        if self._exists(key):
            return False
        try:
            self._s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                ObjectLockMode="COMPLIANCE",
                ObjectLockRetainUntilDate=now + self.retention,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Không ghi được {key}: {exc}") from exc
        return True

    def put(self, audit_id: int, hash_hex: str, now: datetime) -> tuple[str, bool]:
        """Ghi mốc; mốc đã có thì không ghi lại."""
        key = anchor_key(audit_id, hash_hex)
        body = json.dumps({"audit_id": audit_id, "hash": hash_hex}).encode()     # thời điểm: LastModified của kho
        return key, self._put_locked(key, body, now)

    def put_signature(self, audit_id: int, hash_hex: str, signed: Signed, now: datetime) -> bool:
        """Ghi chữ ký tách rời cạnh mốc. Cùng mốc, cùng khóa thì cùng nội dung (xem docstring mô-đun): hai tiến trình
        cùng ghi chỉ thêm phiên bản giống hệt."""
        body = json.dumps(signed_line(audit_id, hash_hex, signed)).encode()
        return self._put_locked(signature_key(audit_id, hash_hex), body, now)

    def first_written(self, audit_id: int, hash_hex: str) -> datetime:
        """Lúc kho ghi phiên bản đầu của mốc — giờ ký trong chữ ký, giống anchored_at của lệnh liệt kê. Phiên bản đầu
        bị khóa ghi nên giá trị này không đổi, ai đọc lúc nào cũng thấy như nhau."""
        key = anchor_key(audit_id, hash_hex)
        times = []
        try:
            for page in self._s3.get_paginator("list_object_versions").paginate(Bucket=self.bucket, Prefix=key):
                times += [v["LastModified"] for v in page.get("Versions", []) if v["Key"] == key]
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Không đọc được các phiên bản của {key}: {exc}") from exc
        if not times:
            raise StorageError(f"Không thấy mốc {key} trong bucket {self.bucket}")
        return min(times)

    def list(self) -> list[Anchor]:
        versions: dict[str, list[dict[str, Any]]] = {}
        markers: set[str] = set()
        try:
            for page in self._s3.get_paginator("list_object_versions").paginate(Bucket=self.bucket, Prefix=PREFIX):
                for v in page.get("Versions", []):
                    versions.setdefault(v["Key"], []).append(v)
                for m in page.get("DeleteMarkers", []):
                    markers.add(m["Key"])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "NoSuchBucket":
                return []                               # chưa neo lần nào
            raise StorageError(f"Không liệt kê được mốc trong bucket {self.bucket}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"Không kết nối được kho đối tượng: {exc}") from exc
        anchors = []
        for key, found in versions.items():
            match = KEY.match(key)
            if match is None:
                continue
            first = min(found, key=lambda v: v["LastModified"])
            anchors.append(Anchor(
                audit_id=int(match[1]),
                hash=match[2],
                anchored_at=first["LastModified"].astimezone(UTC).isoformat(),
                key=key,
                overwritten=len({v.get("ETag") for v in found}) > 1,
                deleted=key in markers,
            ))
        return sorted(anchors, key=lambda a: (a.audit_id, a.anchored_at))


class _Source(Protocol):
    async def audit_head(self) -> tuple[int, str]: ...
    async def record_anchor(self, audit_id: int, hash_hex: str, location: str) -> None: ...


class Anchorer:
    """Vòng nền: đầu chuỗi đổi so với mốc trước thì neo. Không có gì mới thì không ghi gì."""

    def __init__(self, source: _Source, store: AnchorStore, *, interval_s: float = 600.0,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 signer: AnchorSigner | None = None) -> None:
        self.source = source
        self.store = store
        self.interval_s = interval_s
        self.clock = clock
        self.signer = signer
        self.ready = False
        self.last: tuple[int, str] | None = None       # mốc đã ghi xong cả bucket lẫn CSDL
        self.latest: Mark | None = None                # như last, kèm lúc kho ghi — chân sổ đăng ký
        self._unsigned_logged = False

    async def anchor_once(self) -> Anchored | None:
        """Neo đầu chuỗi hiện tại; sổ còn trống thì None."""
        last_id, last_hash = await self.source.audit_head()
        if last_id == 0:
            return None
        location = f"s3://{self.store.bucket}/{anchor_key(last_id, last_hash)}"
        if self.last == (last_id, last_hash):
            return Anchored(last_id, last_hash, location, new=False)     # chưa có dòng sổ nào mới từ mốc trước
        if not self.ready:
            await asyncio.to_thread(self.store.ensure_bucket)
            self.ready = True
        # Mốc đã có trong bucket (khởi động lại, lượt trước hỏng giữa chừng) thì không ghi thêm phiên bản
        _, created = await asyncio.to_thread(self.store.put, last_id, last_hash, self.clock())
        at = await asyncio.to_thread(self.store.first_written, last_id, last_hash)
        signed = await self._sign(last_id, last_hash, at)
        # Ghi bucket trước, CSDL sau: hỏng giữa chừng thì lượt sau thấy mốc đã có, chỉ ghi nốt dòng tra cứu
        await self.source.record_anchor(last_id, last_hash, location)
        self.last = (last_id, last_hash)
        self.latest = Mark(last_id, last_hash, at)
        if created:
            log.info(json.dumps({"event": "core.audit.anchored", "audit_id": last_id, "location": location,
                                 "signed": signed is not None}))
        return Anchored(last_id, last_hash, location, new=created, anchored_at=stamp(at), signed=signed)

    async def _sign(self, audit_id: int, hash_hex: str, at: datetime) -> Signed | None:
        """Ký mốc, ghi chữ ký cạnh mốc. Không ký được thì mốc vẫn neo như cũ: chữ ký chỉ cộng thêm, không chặn neo."""
        if self.signer is None:
            return None
        try:
            signed = await self.signer.sign(audit_id, hash_hex, at)
        except (VaultError, ValueError) as exc:
            log.warning(json.dumps({"event": "core.audit.anchor_unsigned", "audit_id": audit_id, "error": str(exc)},
                                   ensure_ascii=False))
            return None
        if signed is None:
            if not self._unsigned_logged:         # két cũ: báo một lần mỗi lần khởi động, không mỗi chu kỳ
                self._unsigned_logged = True
                log.warning(json.dumps({"event": "core.audit.anchor_unsigned", "audit_id": audit_id,
                                        "error": f"két chưa có khóa {self.signer.key} hoặc policy chưa cho đọc"
                                                 " (docs/van-hanh.md mục Két bí mật)"}, ensure_ascii=False))
            return None
        try:
            await asyncio.to_thread(self.store.put_signature, audit_id, hash_hex, signed, self.clock())
        except StorageError as exc:     # chữ ký vẫn đúng (ký lại ra y hệt), chỉ thiếu bản cạnh mốc trong bucket
            log.warning(json.dumps({"event": "core.audit.anchor_signature_unsaved", "audit_id": audit_id,
                                    "error": str(exc)}, ensure_ascii=False))
        self._unsigned_logged = False
        return signed

    async def run(self) -> None:
        while True:
            try:
                await self.anchor_once()
                delay = self.interval_s
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết; lượt sau thử lại
                log.warning(json.dumps({"event": "core.audit.anchor_failed", "error": str(exc)}, ensure_ascii=False))
                delay = min(self.interval_s, 30.0)      # kho chưa lên lúc khởi động: thử lại sớm, không đợi cả chu kỳ
            await asyncio.sleep(delay)


def main(argv: list[str] | None = None) -> int:
    from .config import Settings
    from .hasura import HasuraClient, HasuraError
    from .openbao import with_secrets
    from .sealed import Vault
    from .storage import s3_client

    args = sys.argv[1:] if argv is None else argv
    if args not in (["now"], ["list"], ["key"]):
        print("Dùng: python -m svc_files.anchors now|list|key", file=sys.stderr)
        return 2
    settings = Settings.from_env(with_secrets(os.environ))
    store = AnchorStore(
        s3_client(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
        settings.cold_bucket,
        settings.anchor_retention_days,
    )

    def vault() -> Vault | None:
        if not settings.vault_addr:
            return None
        return Vault(settings.vault_addr, role_id_file=settings.vault_role_id_file,
                     secret_id_file=settings.vault_secret_id_file, key=settings.transit_key)

    try:
        if args == ["list"]:
            out: dict[str, Any] = {"bucket": store.bucket, "locked": store.locked(),
                                   "anchors": [asdict(a) for a in store.list()]}
        elif args == ["key"]:
            async def read_key() -> PublicKey | None:
                bao = vault()
                if bao is None:
                    return None
                try:
                    return await AnchorSigner(bao, settings.public_url).public_key()
                finally:
                    await bao.aclose()

            key = asyncio.run(read_key())
            out = {"key": {"version": key.version, "fingerprint": key.fingerprint, "pem": key.pem} if key else None}
        else:
            async def once() -> Anchored | None:
                hasura = HasuraClient(settings.hasura_url, settings.hasura_admin_secret,
                                      timeout_s=settings.hasura_timeout_s)
                bao = vault()
                try:
                    signer = AnchorSigner(bao, settings.public_url) if bao is not None else None
                    return await Anchorer(hasura, store, signer=signer).anchor_once()
                finally:
                    await hasura.aclose()
                    if bao is not None:
                        await bao.aclose()

            result = asyncio.run(once())
            out = {"anchored": asdict(result) if result else None}
    except (StorageError, HasuraError, VaultError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
