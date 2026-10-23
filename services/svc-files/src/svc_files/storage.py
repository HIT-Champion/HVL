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

"""Kho đối tượng: SeaweedFS qua API chuẩn S3.

SeaweedFS chỉ nằm trong mạng nội bộ. Không phát URL ký sẵn ra ngoài — tệp luôn đi
qua svc-files, nếu không sẽ bỏ qua bước quét ClamAV (kế hoạch §2).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any, BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageError(Exception):
    """Kho đối tượng lỗi hoặc không kết nối được."""


class ObjectMissing(StorageError):
    """Kho trả lời được nhưng không có đối tượng này — đọc lại cũng không ra."""


def object_key(tenant_id: uuid.UUID, file_id: uuid.UUID, at: datetime) -> str:
    """Khóa ``tenant/<tenant_id>/<yyyy>/<mm>/<file_id>`` (mo-hinh-du-lieu.md §1)."""
    return f"tenant/{tenant_id}/{at:%Y}/{at:%m}/{file_id}"


def s3_client(endpoint: str, access_key: str, secret_key: str, region: str) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            # Chỉ tính checksum khi API bắt buộc: kho S3 tương thích không phải lúc
            # nào cũng hiểu kiểu checksum mặc định của boto3 bản mới.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            connect_timeout=5,
            read_timeout=60,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


class ObjectStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, region: str, bucket: str) -> None:
        self.bucket = bucket
        self._s3 = s3_client(endpoint, access_key, secret_key, region)

    def ensure_bucket(self) -> None:
        try:
            self._s3.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket", "NotFound"}:
                raise StorageError(f"Không đọc được bucket {self.bucket}: {exc}") from exc
            try:
                self._s3.create_bucket(Bucket=self.bucket)
            except (BotoCoreError, ClientError) as create_exc:
                raise StorageError(f"Không tạo được bucket {self.bucket}: {create_exc}") from create_exc
        except BotoCoreError as exc:
            raise StorageError(f"Không kết nối được kho đối tượng: {exc}") from exc

    def ping(self) -> bool:
        try:
            self._s3.head_bucket(Bucket=self.bucket)
        except (BotoCoreError, ClientError):
            return False
        return True

    def put(self, key: str, body: BinaryIO, *, size: int, content_type: str, sha256_hex: str) -> None:
        # Tên tệp gốc (có dấu tiếng Việt) không ghi vào metadata S3 vì metadata chỉ nhận ASCII;
        # tên tệp nằm trong CSDL (core.files).
        try:
            self._s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentLength=size,
                ContentType=content_type,
                Metadata={"sha256": sha256_hex},
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Không ghi được {key}: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._s3.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Không xóa được {key}: {exc}") from exc

    def read_stream(self, key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        """Mở đối tượng và trả về các khúc dữ liệu; lỗi khi mở báo ngay, không đợi tới lúc đọc."""
        try:
            body = self._s3.get_object(Bucket=self.bucket, Key=key)["Body"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                raise ObjectMissing(f"Không có {key} trong kho") from exc
            raise StorageError(f"Không đọc được {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"Không đọc được {key}: {exc}") from exc

        def chunks() -> Iterator[bytes]:
            try:
                yield from body.iter_chunks(chunk_size)
            except BotoCoreError as exc:
                raise StorageError(f"Đứt kết nối khi đọc {key}: {exc}") from exc
            finally:
                body.close()

        return chunks()
