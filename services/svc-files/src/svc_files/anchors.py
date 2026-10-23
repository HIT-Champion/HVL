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
dòng giả vào bảng đó cũng không làm vòng neo dừng.

Chạy tay trong container (lệnh ``moc audit anchor``, ``moc audit verify`` trên máy chủ gọi qua docker compose):

    python -m svc_files.anchors now     # neo ngay nếu đầu chuỗi đã đổi, in mốc dạng JSON
    python -m svc_files.anchors list    # liệt kê mốc trong bucket, kèm cờ ghi đè, xóa
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from .storage import StorageError

log = logging.getLogger("svc_files")

PREFIX = "anchors/"
KEY = re.compile(r"^anchors/(\d{12})-([0-9a-f]{64})\.json$")


def anchor_key(audit_id: int, hash_hex: str) -> str:
    return f"{PREFIX}{audit_id:012d}-{hash_hex}.json"


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

    def put(self, audit_id: int, hash_hex: str, now: datetime) -> tuple[str, bool]:
        """Ghi mốc; mốc đã có thì không ghi lại (ghi lại là thêm phiên bản, lúc kiểm sẽ mang cờ ghi đè)."""
        key = anchor_key(audit_id, hash_hex)
        if self._exists(key):
            return key, False
        body = json.dumps({"audit_id": audit_id, "hash": hash_hex}).encode()     # thời điểm: LastModified của kho
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
            raise StorageError(f"Không ghi được mốc {key}: {exc}") from exc
        return key, True

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
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source
        self.store = store
        self.interval_s = interval_s
        self.clock = clock
        self.ready = False
        self.last: tuple[int, str] | None = None       # mốc đã ghi xong cả bucket lẫn CSDL

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
        # Ghi bucket trước, CSDL sau: hỏng giữa chừng thì lượt sau thấy mốc đã có, chỉ ghi nốt dòng tra cứu
        await self.source.record_anchor(last_id, last_hash, location)
        self.last = (last_id, last_hash)
        if created:
            log.info(json.dumps({"event": "core.audit.anchored", "audit_id": last_id, "location": location}))
        return Anchored(last_id, last_hash, location, new=created)

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
    from .storage import s3_client

    args = sys.argv[1:] if argv is None else argv
    if args not in (["now"], ["list"]):
        print("Dùng: python -m svc_files.anchors now|list", file=sys.stderr)
        return 2
    settings = Settings.from_env(with_secrets(os.environ))
    store = AnchorStore(
        s3_client(settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
        settings.cold_bucket,
        settings.anchor_retention_days,
    )
    try:
        if args == ["list"]:
            out: dict[str, Any] = {"bucket": store.bucket, "locked": store.locked(),
                                   "anchors": [asdict(a) for a in store.list()]}
        else:
            async def once() -> Anchored | None:
                hasura = HasuraClient(settings.hasura_url, settings.hasura_admin_secret,
                                      timeout_s=settings.hasura_timeout_s)
                try:
                    return await Anchorer(hasura, store).anchor_once()
                finally:
                    await hasura.aclose()

            result = asyncio.run(once())
            out = {"anchored": asdict(result) if result else None}
    except (StorageError, HasuraError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
