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

"""Liên thông trong hệ thống (F3.12): chép bản phát hành sang kho của đơn vị nhận — API nội bộ của svc-workflow."""

from __future__ import annotations

import hashlib
import re
import uuid

import pytest

from conftest import EICAR
from svc_files.hasura import HasuraError

TENANT_B = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")    # đơn vị nhận
PDF = b"%PDF-1.7 ban phat hanh 05/TB-CNTT"
SHA = hashlib.sha256(PDF).hexdigest()


def dispatch(client, token, dispatch_id):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/internal/dispatch-file", headers=headers,
                       json={"dispatch_id": str(dispatch_id), "actor_id": "svc-workflow"})


@pytest.fixture
def service(make_token):
    return make_token(azp="svc-workflow", tenant=None)


@pytest.fixture
def pending(hasura, store):
    return hasura.add_dispatch(store, PDF, to_tenant=TENANT_B)


def copies(store) -> dict[str, dict]:
    """Đối tượng trong kho dưới tiền tố của đơn vị nhận."""
    return {k: v for k, v in store.objects.items() if k.startswith(f"tenant/{TENANT_B}/")}


def source_key(hasura, dispatch_id) -> str:
    return hasura.dispatches[dispatch_id]["document"]["issued"][0]["object_key"]


def test_dispatch_requires_the_workflow_service_token(client, hasura, store, make_token, pending):
    assert dispatch(client, None, pending).status_code == 401
    r = dispatch(client, make_token(azp="app-office"), pending)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_a_service"
    assert not copies(store) and not hasura.files


def test_dispatch_copies_the_issued_file_into_the_recipient_unit(client, hasura, store, scanner, service, pending):
    r = dispatch(client, service, pending)
    assert r.status_code == 201
    file_id = hasura.dispatches[pending]["file_id"]
    assert r.json() == {"file_id": file_id, "sha256": SHA, "size_bytes": len(PDF)}
    # bản sao nằm dưới tiền tố của đơn vị nhận, đúng khuôn khóa (ràng buộc files_object_key_tenant)
    ((key, stored),) = copies(store).items()
    assert re.fullmatch(rf"tenant/{TENANT_B}/\d{{4}}/\d{{2}}/{file_id}", key)
    assert stored["data"] == PDF and stored["sha256"] == SHA and stored["content_type"] == "application/pdf"
    assert scanner.scanned == PDF
    row = hasura.files[uuid.UUID(file_id)]
    assert row["tenant_id"] == TENANT_B and row["created_by"] == "svc-workflow" and row["object_key"] == key
    assert (row["filename"], row["sha256_hex"], row["size_bytes"]) == ("05-TB-CNTT.pdf", SHA, len(PDF))
    assert row.get("wrapped_dek") is None
    assert source_key(hasura, pending) in store.objects      # bản của đơn vị gửi giữ nguyên


def test_calling_again_returns_the_same_copy(client, hasura, store, service, pending):
    first, second = dispatch(client, service, pending), dispatch(client, service, pending)
    assert (first.status_code, second.status_code) == (201, 200) and first.json() == second.json()
    # dòng outbox vừa được tạo văn bản đến (bản svc-workflow khác): gọi lại vẫn ra đúng bản sao đó
    hasura.dispatches[pending]["status"] = "delivered"
    again = dispatch(client, service, pending)
    assert again.status_code == 200 and again.json() == first.json()
    assert len(copies(store)) == 1 and len(hasura.files) == 1


def _tamper(hasura, store, dispatch_id):
    obj = store.objects[source_key(hasura, dispatch_id)]
    obj["data"] = obj["data"][:5] + bytes([obj["data"][5] ^ 1]) + obj["data"][6:]


def _lose(hasura, store, dispatch_id):
    store.objects.pop(source_key(hasura, dispatch_id))


@pytest.mark.parametrize(("cols", "spoil"), [
    ({}, _tamper),                                      # byte trong kho bị sửa
    ({}, _lose),                                        # đối tượng không còn trong kho
    ({"file": {"sha256": "00" * 32}}, None),            # khác core.files.sha256
    ({"document": {"content_sha256": "11" * 32}}, None),  # khác office.documents.content_sha256
    ({"source_sha256": "22" * 32}, None),               # khác băm chụp vào dòng outbox lúc phát hành
], ids=["tampered", "missing", "file-hash", "document-hash", "outbox-hash"])
def test_integrity_mismatch_is_refused(client, hasura, store, scanner, service, cols, spoil):
    d = hasura.add_dispatch(store, PDF, to_tenant=TENANT_B, **cols)
    if spoil:
        spoil(hasura, store, d)
    r = dispatch(client, service, d)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "integrity"
    assert not copies(store) and not hasura.files and scanner.scanned == b""


@pytest.mark.parametrize(("cols", "code"), [
    ({"status": "delivered"}, "not_pending"),
    ({"status": "failed"}, "not_pending"),
    ({"document": {"status": "approved", "issued": []}}, "not_issued"),
    ({"document": {"status": "cancelled"}}, "not_issued"),
    ({"document": {"restricted": True}}, "restricted"),
    ({"file": {"encrypted": True}}, "restricted"),
    ({"file": {"storage_tier": "cold"}}, "cold"),
    ({"document": {"status": "archived", "issued": []}}, "cold"),     # nộp lưu gỡ liên kết tệp
])
def test_refusals(client, hasura, store, scanner, service, cols, code):
    r = dispatch(client, service, hasura.add_dispatch(store, PDF, to_tenant=TENANT_B, **cols))
    assert r.status_code == 409 and r.json()["detail"]["code"] == code
    assert not copies(store) and not hasura.files and scanner.scanned == b""


def test_scanner_down_stores_nothing(client, hasura, store, scanner, service, pending):
    scanner.down = True
    r = dispatch(client, service, pending)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "scanner_unavailable"
    assert not copies(store) and not hasura.files


def test_database_down(client, hasura, store, service, pending):
    hasura.down = True
    r = dispatch(client, service, pending)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable" and not copies(store)


def test_unknown_dispatch_is_not_found(client, service):
    assert dispatch(client, service, uuid.uuid4()).status_code == 404


def test_infected_copy_is_blocked_and_logged_for_the_recipient(client, hasura, store, service):
    d = hasura.add_dispatch(store, EICAR, to_tenant=TENANT_B)
    r = dispatch(client, service, d)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "infected"
    assert not copies(store) and not hasura.files
    (event,) = hasura.events
    assert (event["tenant_id"], event["action"], event["actor_id"], event["actor_kind"]) == \
        (TENANT_B, "file.rejected", "svc-workflow", "service")
    assert event["details"]["signature"] == "Eicar-Test-Signature" and event["details"]["dispatch_id"] == d


@pytest.mark.parametrize("same_key", [True, False], ids=["same-key", "other-key"])
def test_primary_key_conflict_keeps_the_winners_object(client, hasura, store, service, pending, same_key):
    file_id = uuid.UUID(hasura.dispatches[pending]["file_id"])
    insert = hasura.insert_file
    keys: dict[str, str] = {}

    async def racing(*, object_key, **row):
        # lần gọi song song thêm dòng cùng id định trước ngay trước lần này; khác tháng thì khác khóa đối tượng
        keys["mine"] = object_key
        keys["winner"] = object_key if same_key else f"tenant/{TENANT_B}/2000/01/{file_id}"
        store.objects.setdefault(keys["winner"], {"data": PDF, "size": len(PDF), "content_type": "application/pdf",
                                                  "sha256": SHA})
        await insert(object_key=keys["winner"], **row)
        raise HasuraError('Uniqueness violation. duplicate key value violates unique constraint "files_pkey"',
                          "constraint-violation")

    hasura.insert_file = racing
    r = dispatch(client, service, pending)
    assert r.status_code == 200 and r.json() == {"file_id": str(file_id), "sha256": SHA, "size_bytes": len(PDF)}
    assert hasura.files[file_id]["object_key"] == keys["winner"]
    assert list(copies(store)) == [keys["winner"]]
    assert store.deleted == ([] if same_key else [keys["mine"]])


def test_failed_insert_without_a_row_leaves_no_copy(client, hasura, store, service, pending):
    hasura.fail_code = "unexpected"
    r = dispatch(client, service, pending)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable"
    assert not copies(store) and len(store.deleted) == 1 and not hasura.files


def test_dispatch_is_not_part_of_the_public_api(client):
    assert "/internal/dispatch-file" not in client.get("/openapi.json").json()["paths"]
