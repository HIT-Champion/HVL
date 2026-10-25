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

"""Neo hash đầu chuỗi sổ kiểm toán ra bucket lạnh có khóa ghi (F2.12); chữ ký của két trên từng mốc (thông điệp
signet-anchor-v1, khóa Ed25519 moc-anchor), chữ ký tách rời cạnh mốc, đường công khai tải khóa và chứng thư CA."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key

from svc_files.anchors import (AnchorSigner, Anchorer, AnchorStore, Mark, PublicKey, _raw_public, anchor_key,
                               anchor_message, signature_key, stamp)
from svc_files.config import ConfigError, Settings
from svc_files.hasura import HasuraError
from svc_files.sealed import Vault, VaultError
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


# --- chữ ký mốc neo ----------------------------------------------------------------------------------------------

# Khóa của RFC 8032 §7.1 TEST 1. Thông điệp, chữ ký, vân tay dưới đây cũng nằm trong scripts/tests/test_moc_neo.py
# (bộ kiểm Ed25519 viết bằng Python thuần) và đã kiểm bằng `openssl pkeyutl -verify -rawin` (OpenSSL 3.0.13)
SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
VECTOR_MESSAGE = ("signet-anchor-v1\n42\n" + "ab" * 32 + "\n2026-10-25T01:15:03Z\nhttps://signet.example\n").encode()
VECTOR_SIG = "6Zd3HmfkSkXWyDilTfzxhSy+lofvdwd0rrAJRzWQ0ckGfon3GIc8VcXlfgOsYs05o3GdSErLU9MKfBUSWieVBA=="
VECTOR_KEY = "sha256:06e3fd8fda29bb60ab59557de61edb0aecdb231134be30e75b455f8e1b792fa9"
VECTOR_PEM = ("-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=\n"
              "-----END PUBLIC KEY-----\n")
SYSTEM = "https://signet.example"


class FakeTransit:
    """Phần transit của két mà AnchorSigner gọi. missing: két chưa có khóa (404); forbidden: policy cũ (403); down:
    két không trả lời; wrong: két ký bằng khóa khác khóa nó công bố."""

    def __init__(self, seed: bytes = SEED) -> None:
        self.key = Ed25519PrivateKey.from_private_bytes(seed)
        self.missing = self.forbidden = self.down = self.wrong = False
        self.signed: list[bytes] = []
        self.reads = 0

    async def transit_key(self, name: str) -> dict | None:
        assert name == "moc-anchor"
        self.reads += 1
        if self.down:
            raise VaultError("không gọi được két")
        if self.forbidden:
            raise VaultError("két trả HTTP 403", status=403)
        if self.missing:
            return None
        raw = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return {"type": "ed25519", "latest_version": 1, "keys": {"1": {"public_key": base64.b64encode(raw).decode()}}}

    async def transit_sign_ed25519(self, name: str, data: bytes, *, version: int) -> bytes:
        assert (name, version) == ("moc-anchor", 1)
        self.signed.append(data)
        return (Ed25519PrivateKey.generate() if self.wrong else self.key).sign(data)


@pytest.fixture
def transit() -> FakeTransit:
    return FakeTransit()


@pytest.fixture
def signing(s3, source, transit) -> Anchorer:
    return Anchorer(source, AnchorStore(s3, "moc-cold", retention_days=3650), clock=lambda: NOW,
                    signer=AnchorSigner(transit, SYSTEM))


def test_canonical_message_is_five_lines_each_ending_in_a_newline():
    assert anchor_message(42, "ab" * 32, "2026-10-25T01:15:03Z", SYSTEM) == VECTOR_MESSAGE
    assert stamp(datetime(2026, 10, 25, 8, 15, 3, 999_000, tzinfo=UTC) + timedelta(hours=-7)) == "2026-10-25T01:15:03Z"


@pytest.mark.parametrize("bad", [
    (0, "ab" * 32, "2026-10-25T01:15:03Z", SYSTEM),               # id bắt đầu từ 1
    (True, "ab" * 32, "2026-10-25T01:15:03Z", SYSTEM),            # bool không phải số
    (42, "AB" * 32, "2026-10-25T01:15:03Z", SYSTEM),              # hex thường, đúng như tên khóa trong bucket
    (42, "ab" * 31, "2026-10-25T01:15:03Z", SYSTEM),
    (42, "ab" * 32, "2026-10-25T01:15:03+00:00", SYSTEM),         # một cách viết giờ duy nhất
    (42, "ab" * 32, "2026-10-25T01:15:03Z", ""),
    (42, "ab" * 32, "2026-10-25T01:15:03Z", "https://a\n43"),     # không trường nào giả được một dòng khác
])
def test_message_fields_that_could_be_ambiguous_are_refused(bad):
    with pytest.raises(ValueError):
        anchor_message(*bad)


def test_known_answer_signature_and_fingerprint():
    key = Ed25519PrivateKey.from_private_bytes(SEED)
    assert base64.b64encode(key.sign(VECTOR_MESSAGE)).decode() == VECTOR_SIG
    public = PublicKey(1, key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert public.pem == VECTOR_PEM and public.fingerprint == VECTOR_KEY
    assert public.der == key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    assert load_pem_public_key(public.pem.encode()) == key.public_key()
    assert _raw_public(VECTOR_PEM) == public.raw                    # két trả dạng PEM cũng đọc được
    for odd in ("", "abc", base64.b64encode(b"x" * 31).decode(),
                "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----"):
        with pytest.raises(VaultError):
            _raw_public(odd)


def test_each_anchor_is_signed_over_its_first_write_time_and_the_signature_sits_next_to_it(signing, s3, transit):
    result = run(signing.anchor_once())
    first = s3.objects()[anchor_key(5, H5)][0]["LastModified"]
    assert result.anchored_at == stamp(first) and result.signed.anchored_at == result.anchored_at
    assert result.signed.system == SYSTEM
    message = anchor_message(5, H5, result.anchored_at, SYSTEM)
    assert transit.signed == [message]
    public = transit.key.public_key()
    public.verify(base64.b64decode(result.signed.sig), message)     # InvalidSignature nếu sai
    assert result.signed.key == PublicKey(1, public.public_bytes(Encoding.Raw, PublicFormat.Raw)).fingerprint
    (version,) = s3.objects()[signature_key(5, H5)]
    assert version["ObjectLockMode"] == "COMPLIANCE"
    assert json.loads(version["Body"]) == {"v": "signet-anchor-v1", "audit_id": 5, "hash": H5,
                                           "anchored_at": result.anchored_at, "system": SYSTEM,
                                           "key": result.signed.key, "sig": result.signed.sig}
    # mốc giữ nguyên nội dung cũ; lệnh liệt kê không coi chữ ký là một mốc
    assert json.loads(s3.objects()[anchor_key(5, H5)][0]["Body"]) == {"audit_id": 5, "hash": H5}
    assert [a.key for a in signing.store.list()] == [anchor_key(5, H5)]
    assert signing.latest == Mark(5, H5, first)


def test_signing_again_gives_the_same_signature_so_two_writers_leave_no_tamper_flag(signing, s3, source, transit):
    """Lệnh `audit anchor` chạy lúc vòng nền vừa neo: mốc đã có, ký lại ra đúng chữ ký cũ, không thêm phiên bản."""
    first = run(signing.anchor_once())
    again = Anchorer(source, signing.store, clock=lambda: NOW + timedelta(minutes=7),
                     signer=AnchorSigner(transit, SYSTEM))
    second = run(again.anchor_once())
    assert second.new is False and second.signed == first.signed
    assert len(s3.objects()[signature_key(5, H5)]) == 1
    # cả khi hai tiến trình cùng thấy chữ ký chưa có: hai phiên bản giống hệt nhau
    signing.store._exists = lambda key: False
    signing.store.put_signature(5, H5, first.signed, NOW)
    versions = s3.objects()[signature_key(5, H5)]
    assert len(versions) == 2 and len({v["ETag"] for v in versions}) == 1


def test_a_vault_without_the_anchor_key_still_anchors_unsigned_and_says_so_once(signing, s3, source, transit,
                                                                                 log_records):
    transit.missing = True
    result = run(signing.anchor_once())
    assert result.new is True and result.signed is None and result.anchored_at
    assert source.recorded and signature_key(5, H5) not in s3.objects()
    source.head = (9, H9)
    run(signing.anchor_once())
    warned = [r for r in log_records if r["event"] == "core.audit.anchor_unsigned"]
    assert len(warned) == 1 and "moc-anchor" in warned[0]["error"]


@pytest.mark.parametrize("switch", ["forbidden", "down", "wrong"])
def test_vault_trouble_never_blocks_anchoring_nor_yields_a_bad_signature(signing, s3, source, transit, switch,
                                                                        log_records):
    """Policy cũ (403), két không trả lời, két ký bằng khóa khác: mốc vẫn neo, không có chữ ký nào sai lọt ra."""
    setattr(transit, switch, True)
    result = run(signing.anchor_once())
    assert result.new is True and result.signed is None and source.recorded
    assert signature_key(5, H5) not in s3.objects()
    assert any(r["event"] == "core.audit.anchor_unsigned" for r in log_records)


def test_public_key_is_cached_for_the_public_route_but_signing_reads_it_fresh(transit):
    now = [0.0]
    signer = AnchorSigner(transit, SYSTEM, clock=lambda: now[0])
    first = run(signer.public_key())
    assert run(signer.public_key()) == first and transit.reads == 1
    now[0] = 301.0
    run(signer.public_key())
    assert transit.reads == 2
    run(signer.sign(5, H5, NOW))
    assert transit.reads == 3


def test_vault_signs_ed25519_with_the_exact_key_version(tmp_path):
    (tmp_path / "role_id").write_text("r")
    (tmp_path / "secret_id").write_text("s")
    key = Ed25519PrivateKey.from_private_bytes(SEED)
    seen = []

    def bao(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/login"):
            return httpx2.Response(200, json={"auth": {"client_token": "t", "lease_duration": 3600}})
        body = json.loads(request.content)
        seen.append((request.url.path, sorted(body)))
        version = 2 if body["key_version"] == 3 else body["key_version"]     # 3: két ký bằng phiên bản khác
        sig = base64.b64encode(key.sign(base64.b64decode(body["input"]))).decode()
        return httpx2.Response(200, json={"data": {"signature": f"vault:v{version}:{sig}", "key_version": version}})

    async def scenario():
        vault = Vault("http://openbao:8200", role_id_file=str(tmp_path / "role_id"),
                      secret_id_file=str(tmp_path / "secret_id"), transport=httpx2.MockTransport(bao))
        assert base64.b64encode(await vault.transit_sign_ed25519("moc-anchor", VECTOR_MESSAGE, version=1)).decode() \
            == VECTOR_SIG
        with pytest.raises(VaultError, match="phiên bản khóa khác"):
            await vault.transit_sign_ed25519("moc-anchor", VECTOR_MESSAGE, version=3)
        await vault.aclose()

    asyncio.run(scenario())
    # Ed25519 thuần: không đường băm (/sha2-256), không signature_algorithm như khóa RSA của F4.5
    assert seen[0] == ("/v1/transit/sign/moc-anchor", ["input", "key_version"])


# --- đường công khai: chứng thư CA (#56), khóa công khai ký mốc neo ---------------------------------------------


CA_PEM = """-----BEGIN CERTIFICATE-----
MIIBdTCCASegAwIBAgIUIElYfZWNjZ3yDNeKDMtkC4/IlSIwBQYDK2VwMDAxGDAW
BgNVBAMMD0NBIHRodSAtIFNpZ25ldDEUMBIGA1UECgwLU2lnbmV0IHRlc3QwHhcN
MjYxMDI1MDk1NzEyWhcNMzYxMDIyMDk1NzEyWjAwMRgwFgYDVQQDDA9DQSB0aHUg
LSBTaWduZXQxFDASBgNVBAoMC1NpZ25ldCB0ZXN0MCowBQYDK2VwAyEAN3/QEjqp
3pomdR9HOMwWQ3yFDtcPhkK17BT39dudb4ijUzBRMB0GA1UdDgQWBBQi6FeZTnQX
JV+BVuEQtk81w/MR/zAfBgNVHSMEGDAWgBQi6FeZTnQXJV+BVuEQtk81w/MR/zAP
BgNVHRMBAf8EBTADAQH/MAUGAytlcANBAE8KfXAe8mfrQzDU6nMdflPbkt9p0eUq
Ay7NjLFFLcEzTtHdT2X5NIq8iHqw+uljC67OS9LgoMf/cWfzQ2eQqgY=
-----END CERTIFICATE-----"""


def test_ca_certificate_is_public_pem(client, vault):
    vault.ca_pem = CA_PEM + "\n"
    r = client.get("/api/verify/ca.pem")            # không kèm token
    assert r.status_code == 200 and r.text == CA_PEM + "\n"
    assert r.headers["content-type"] == "application/x-pem-file"
    assert 'filename="signet-ca.pem"' in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_no_ca_in_a_vault_set_up_before_signing_is_404_not_a_lookup(client, vault):
    """Két khởi tạo trước F4.5: 404 — và đường này không rơi vào /api/verify/{code} (sẽ trả JSON not_found 200)."""
    r = client.get("/api/verify/ca.pem")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_ca"
    vault.ca_pem = "không phải PEM"
    assert client.get("/api/verify/ca.pem").status_code == 404


def test_ca_route_reports_a_vault_outage(client, vault):
    vault.down = True
    r = client.get("/api/verify/ca.pem")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "vault_unavailable"


def test_no_anchor_key_in_an_older_vault_is_404(client, vault):
    r = client.get("/api/verify/anchor-key.pem")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_anchor_key"


def test_anchor_key_is_public_pem_with_the_fingerprint_written_in_anchor_lines(client, vault):
    vault.anchor_key = Ed25519PrivateKey.from_private_bytes(SEED)
    r = client.get("/api/verify/anchor-key.pem")
    assert r.status_code == 200 and r.text == VECTOR_PEM
    assert r.headers["content-type"] == "application/x-pem-file"
    assert 'filename="signet-anchor-key.pem"' in r.headers["content-disposition"]
    der = load_pem_public_key(r.content).public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    assert "sha256:" + hashlib.sha256(der).hexdigest() == VECTOR_KEY


def test_anchor_key_route_without_a_vault_or_with_one_down(settings, scanner, store, verifier, hasura, meili, vault):
    from fastapi.testclient import TestClient

    from svc_files.app import create_app

    with TestClient(create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura,
                               meili=meili)) as plain:          # không cấu hình két: không có gì để tải
        assert plain.get("/api/verify/anchor-key.pem").status_code == 404
        assert plain.get("/api/verify/ca.pem").status_code == 404
    vault.down = True
    with TestClient(create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura,
                               meili=meili, vault=vault)) as c:
        r = c.get("/api/verify/anchor-key.pem")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "vault_unavailable"


def test_pem_routes_are_in_the_public_api_before_the_code_lookup(client):
    paths = list(client.get("/openapi.json").json()["paths"])
    assert {"/api/verify/ca.pem", "/api/verify/anchor-key.pem"} <= set(paths)
    assert paths.index("/api/verify/ca.pem") < paths.index("/api/verify/{code}")
    assert paths.index("/api/verify/anchor-key.pem") < paths.index("/api/verify/{code}")
