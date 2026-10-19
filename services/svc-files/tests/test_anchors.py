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

"""Neo hash đầu chuỗi sổ kiểm toán ra bucket lạnh có khóa ghi (F2.12)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from botocore.exceptions import ClientError

from svc_files.anchors import Anchorer, AnchorStore, anchor_key
from svc_files.config import ConfigError, Settings
from svc_files.hasura import HasuraError
from svc_files.storage import StorageError

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
H5 = "5" * 64
H9 = "9" * 64


def missing(op: str, code: str = "404") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "Not Found"}}, op)


class FakeS3:
    """Đủ phần S3 mà AnchorStore dùng, có versioning như bucket bật Object Lock."""

    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, Any]] = {}
        self.clock = NOW

    def head_bucket(self, Bucket: str) -> None:  # noqa: N803 — tên tham số theo boto3
        if Bucket not in self.buckets:
            raise missing("HeadBucket")

    def create_bucket(self, Bucket: str, ObjectLockEnabledForBucket: bool = False) -> None:  # noqa: N803
        self.buckets[Bucket] = {"locked": ObjectLockEnabledForBucket, "versions": {}, "markers": set()}

    def get_object_lock_configuration(self, Bucket: str) -> dict:  # noqa: N803
        if not self.buckets.get(Bucket, {}).get("locked"):
            raise missing("GetObjectLockConfiguration", "ObjectLockConfigurationNotFoundError")
        return {"ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}}

    def head_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803
        b = self.buckets[Bucket]
        if not b["versions"].get(Key) or Key in b["markers"]:
            raise missing("HeadObject")
        return {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **extra: Any) -> dict:  # noqa: N803
        self.clock += timedelta(seconds=1)
        self.buckets[Bucket]["versions"].setdefault(Key, []).append(
            {"Key": Key, "LastModified": self.clock, "ETag": hashlib.md5(Body).hexdigest(), "Body": Body, **extra})
        self.buckets[Bucket]["markers"].discard(Key)
        return {}

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        self.buckets[Bucket]["markers"].add(Key)

    def get_paginator(self, name: str) -> FakeS3:
        assert name == "list_object_versions"
        return self

    def paginate(self, Bucket: str, Prefix: str):  # noqa: N803
        if Bucket not in self.buckets:
            raise missing("ListObjectVersions", "NoSuchBucket")
        b = self.buckets[Bucket]
        versions = [v for k, vs in b["versions"].items() if k.startswith(Prefix) for v in vs]
        yield {"Versions": versions[:2]}
        yield {"Versions": versions[2:], "DeleteMarkers": [{"Key": k} for k in b["markers"]]}

    def objects(self, bucket: str = "moc-cold") -> dict[str, list[dict]]:
        return self.buckets[bucket]["versions"]


@dataclass
class FakeSource:
    head: tuple[int, str] = (5, H5)
    recorded: list[tuple[int, str, str]] = field(default_factory=list)
    fail_record: bool = False

    async def audit_head(self) -> tuple[int, str]:
        return self.head

    async def record_anchor(self, audit_id: int, hash_hex: str, location: str) -> None:
        if self.fail_record:
            raise HasuraError("Không gọi được Hasura")
        self.recorded.append((audit_id, hash_hex, location))


@pytest.fixture
def s3() -> FakeS3:
    return FakeS3()


@pytest.fixture
def source() -> FakeSource:
    return FakeSource()


@pytest.fixture
def anchorer(s3, source) -> Anchorer:
    return Anchorer(source, AnchorStore(s3, "moc-cold", retention_days=3650), clock=lambda: NOW)


def run(coro):
    return asyncio.run(coro)


def test_first_anchor_creates_a_locked_bucket_and_keeps_it_for_the_retention_period(anchorer, s3, source):
    result = run(anchorer.anchor_once())
    key = anchor_key(5, H5)
    assert key == f"anchors/000000000005-{H5}.json"
    assert (result.audit_id, result.new, result.location) == (5, True, f"s3://moc-cold/{key}")
    assert s3.buckets["moc-cold"]["locked"]
    (version,) = s3.objects()[key]
    assert json.loads(version["Body"]) == {"audit_id": 5, "hash": H5}
    assert version["ObjectLockMode"] == "COMPLIANCE"
    assert version["ObjectLockRetainUntilDate"] == NOW + timedelta(days=3650)
    assert source.recorded == [(5, H5, f"s3://moc-cold/{key}")]


def test_nothing_new_since_the_last_anchor_writes_nothing(anchorer, s3, source):
    run(anchorer.anchor_once())
    again = run(anchorer.anchor_once())
    assert again.new is False and len(source.recorded) == 1
    assert sum(len(v) for v in s3.objects().values()) == 1


def test_chain_rewritten_under_the_same_id_is_anchored_again(anchorer, s3, source):
    """Đầu chuỗi giữ nguyên id nhưng đổi hash (chuỗi bị tính lại): neo thêm mốc mới, mốc cũ vẫn còn để đối chiếu."""
    run(anchorer.anchor_once())
    source.head = (5, "a" * 64)
    assert run(anchorer.anchor_once()).new is True
    assert sorted(s3.objects()) == [anchor_key(5, H5), anchor_key(5, "a" * 64)]


def test_two_writers_of_the_same_anchor_leave_no_tamper_flag(s3):
    """Vòng nền và lệnh `audit anchor` cùng ghi một mốc: hai phiên bản cùng nội dung, không mang cờ ghi đè."""
    store = AnchorStore(s3, "moc-cold", retention_days=1)
    store.ensure_bucket()
    store._exists = lambda key: False           # cả hai cùng thấy mốc chưa có
    store.put(5, H5, NOW)
    store.put(5, H5, NOW + timedelta(seconds=3))
    (anchor,) = store.list()
    assert len(s3.objects()[anchor.key]) == 2 and not anchor.overwritten


def test_empty_log_is_not_anchored(anchorer, s3, source):
    source.head = (0, "0" * 64)
    assert run(anchorer.anchor_once()) is None
    assert s3.buckets == {}


def test_retry_after_a_database_error_adds_no_second_version(anchorer, s3, source):
    source.fail_record = True
    with pytest.raises(HasuraError):
        run(anchorer.anchor_once())
    source.fail_record = False
    result = run(anchorer.anchor_once())
    assert result.new is False                                # mốc đã nằm trong bucket từ lượt trước
    assert len(s3.objects()[anchor_key(5, H5)]) == 1
    assert source.recorded == [(5, H5, f"s3://moc-cold/{anchor_key(5, H5)}")]


def test_refuses_a_bucket_without_object_lock(anchorer, s3, source):
    s3.create_bucket(Bucket="moc-cold")
    with pytest.raises(StorageError, match="khóa ghi"):
        run(anchorer.anchor_once())
    assert s3.objects() == {} and source.recorded == []


def test_listing_reads_the_hash_from_the_key_and_flags_tampering(anchorer, s3, source):
    run(anchorer.anchor_once())
    source.head = (9, H9)
    run(anchorer.anchor_once())
    store = anchorer.store
    s3.put_object(Bucket="moc-cold", Key=anchor_key(5, H5), Body=b'{"audit_id": 5, "hash": "khac"}')
    s3.delete_object(Bucket="moc-cold", Key=anchor_key(9, H9))
    s3.put_object(Bucket="moc-cold", Key="anchors/ghi-chu.txt", Body=b"khong phai moc")

    first, second = store.list()
    assert (first.audit_id, first.hash, first.overwritten, first.deleted) == (5, H5, True, False)
    assert first.anchored_at == (NOW + timedelta(seconds=1)).isoformat()      # lúc ghi bản đầu, không phải bản sau
    assert (second.audit_id, second.hash, second.overwritten, second.deleted) == (9, H9, False, True)


def test_listing_before_the_first_anchor_is_empty(s3):
    assert AnchorStore(s3, "moc-cold", retention_days=1).list() == []


def test_background_loop_survives_a_failed_round(s3, source, caplog):
    source.fail_record = True
    anchorer = Anchorer(source, AnchorStore(s3, "moc-cold", retention_days=1), interval_s=0.01)

    async def two_rounds():
        task = asyncio.create_task(anchorer.run())
        await asyncio.sleep(0.05)
        source.fail_record = False
        await asyncio.sleep(0.05)
        task.cancel()

    run(two_rounds())
    assert "core.audit.anchor_failed" in caplog.text
    assert source.recorded and source.recorded[0][0] == 5


BASE_ENV = {"MOC_OIDC_ISSUER": "https://moc.example/realms/moc", "MOC_OIDC_JWKS_URL": "http://unused/jwks",
            "SEAWEEDFS_S3_ACCESS_KEY": "k", "SEAWEEDFS_S3_SECRET_KEY": "s", "HASURA_ADMIN_SECRET": "h",
            "MEILISEARCH_API_KEY": "m"}


def test_anchor_defaults():
    s = Settings.from_env(BASE_ENV)
    assert (s.cold_bucket, s.anchor_interval_s, s.anchor_retention_days) == ("moc-cold", 600.0, 3650)


@pytest.mark.parametrize("extra", [
    {"MOC_AUDIT_ANCHOR_INTERVAL_S": "-1"},
    {"MOC_AUDIT_ANCHOR_RETENTION_DAYS": "0"},
    {"MOC_COLD_BUCKET": "moc-files"},
])
def test_bad_anchor_settings_stop_the_service(extra):
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE_ENV, **extra})
