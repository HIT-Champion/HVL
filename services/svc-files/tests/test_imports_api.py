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

"""API nạp lô (/api/imports): ai được tạo lô, kiểm cả tệp trước khi nhận, tệp dữ liệu qua trạm kiểm dịch, khóa
Idempotency, giới hạn, chỉ người tạo xem được lô và dòng của mình."""

import asyncio
import hashlib
import uuid

import pytest

from conftest import EICAR, TENANT_A
from import_fakes import doc, make_lab, ndjson, zip_bytes
from svc_files.auth import HASURA_CLAIMS

TENANT_B = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")
PDF = b"%PDF-1.7\n% cong van mau\n" + b"x" * 500


@pytest.fixture
def lab(monkeypatch, tmp_path, settings, scanner, store, verifier, meili, vault):
    with make_lab(monkeypatch, tmp_path, settings, scanner=scanner, store=store, verifier=verifier, meili=meili,
                  vault=vault) as lab:
        yield lab


@pytest.fixture
def clerk(make_token):
    return make_token(sub="u-van-thu")


def test_needs_a_token(lab):
    r = lab.client.post("/api/imports/incoming", files={"data": ("lo.ndjson", ndjson(doc(1)), "text/plain")})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "missing_token"


@pytest.mark.parametrize("role", ["staff", "director", "manager", "tenant_admin"])
def test_only_clerks_create_batches(lab, make_token, role):
    r = lab.post(make_token(sub="u-khac", role=role), ndjson(doc(1)))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "forbidden"
    assert lab.imports.jobs == {}


def test_clerk_creates_a_batch_with_tenant_and_user_from_the_token(lab, make_token, scanner):
    token = make_token(sub="u-van-thu", **{HASURA_CLAIMS: {
        "x-hasura-user-id": "u-van-thu", "x-hasura-allowed-roles": ["clerk"], "x-hasura-default-role": "clerk",
        "x-hasura-tenant-id": str(TENANT_A), "x-hasura-department-id": "11111111-0000-4000-8000-000000000001"}})
    data = ndjson(doc(1), doc(2), "", "{hỏng", doc(3, files=["a.pdf"]))
    r = lab.post(token, data, headers={"X-Request-Id": "req-lo-1"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert r.headers["Location"] == f"/api/imports/{body['id']}"
    assert r.headers["Cache-Control"] == "no-store"
    assert body["status"] == "queued" and body["kind"] == "incoming" and body["format"] == "ndjson"
    assert (body["total"], body["pending"], body["failed"], body["ok"]) == (4, 2, 2, 0)
    assert body["register"] is False

    job = lab.job(body["id"])
    assert job["tenant_id"] == str(TENANT_A) and job["created_by"] == "u-van-thu"
    assert job["department_id"] == "11111111-0000-4000-8000-000000000001"
    assert job["data_sha256"] == hashlib.sha256(data).hexdigest()
    assert job["filename"] == "lo.ndjson" and job["archive_sha256"] is None
    # tệp dữ liệu đã qua trạm quét như tải lên lẻ
    assert scanner.scanned == data
    lines = {r["line"]: r for r in lab.lines(body["id"])}
    assert sorted(lines) == [1, 2, 4, 5]                        # dòng trống (3) không phải dòng dữ liệu
    assert lines[1]["status"] == "pending" and lines[1]["data"] == doc(1)
    assert (lines[4]["status"], lines[4]["code"], lines[4]["data"]) == ("failed", "bad_json", None)
    # dòng trỏ tệp mà không gửi zip: lỗi ngay lúc nhận, các dòng khác vẫn chờ xử lý
    assert (lines[5]["status"], lines[5]["code"]) == ("failed", "missing_attachment")
    # dòng sổ import.created ghi cùng lần tạo lô
    (event,) = lab.imports.audit
    assert event["action"] == "import.created" and event["entity"] == "core.import_jobs"
    assert event["entity_id"] == body["id"] and event["actor_id"] == "u-van-thu" and event["request_id"] == "req-lo-1"
    assert event["tenant_id"] == str(TENANT_A)
    assert event["diff"] == {"kind": "incoming", "format": "ndjson", "register": False, "total": 4, "failed": 2,
                             "filename": "lo.ndjson"}


def test_body_too_large_is_refused_before_reading_the_form(lab, clerk, scanner):
    limit = (5 + 50) * 1024 * 1024 + 64 * 1024       # tệp dữ liệu + zip + phần đầu multipart
    r = lab.client.post("/api/imports/incoming", content=b"x",
                        headers={"Authorization": f"Bearer {clerk}", "Content-Length": str(limit + 1),
                                 "Content-Type": "multipart/form-data; boundary=x"})
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "too_large"
    assert scanner.scanned == b""


def test_infected_data_file_is_rejected_and_logged_without_a_batch(lab, clerk):
    r = lab.post(clerk, EICAR, name="lo.csv", mime="text/csv", headers={"X-Request-Id": "req-nhiem"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "infected"
    (event,) = lab.hasura.events
    assert event["action"] == "file.rejected" and event["request_id"] == "req-nhiem"
    assert event["details"]["filename"] == "lo.csv"
    assert lab.imports.jobs == {}


def test_data_file_over_its_limit_is_413(lab, clerk):
    big = ndjson(*(doc(i, summary="Về việc " + "x" * 400) for i in range(14000)))
    assert len(big) > 5 * 1024 * 1024
    r = lab.post(clerk, big)
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "too_large"


def test_idempotency_key_returns_the_same_batch(lab, clerk, make_token):
    data, key = ndjson(doc(1), doc(2)), {"Idempotency-Key": "lo-2026-10-23#1"}
    first = lab.post(clerk, data, headers=key)
    assert first.status_code == 202
    again = lab.post(clerk, data, headers=key)
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert again.headers["Location"] == first.headers["Location"]
    assert len(lab.imports.jobs) == 1 and len(lab.lines(first.json()["id"])) == 2
    assert len(lab.imports.audit) == 1
    # cùng khóa mà khác nội dung, khác register: 409
    other = lab.post(clerk, ndjson(doc(1)), headers=key)
    assert other.status_code == 409
    assert other.json()["detail"]["code"] == "idempotency_conflict"
    assert lab.post(clerk, data, headers=key, params={"register": "true"}).status_code == 409
    # khóa thuộc về từng người: văn thư khác dùng cùng khóa là lô khác
    assert lab.post(make_token(sub="u-van-thu-2"), data, headers=key).status_code == 202


@pytest.mark.parametrize("key", ["", "có dấu", "a b", "x" * 201])
def test_bad_idempotency_key_is_400(lab, clerk, key):
    r = lab.post(clerk, ndjson(doc(1)), headers={"Idempotency-Key": key.encode()})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_idempotency_key"


def test_disabled_imports_answer_503(monkeypatch, tmp_path, settings, scanner, store, verifier, meili, vault,
                                     make_token):
    with make_lab(monkeypatch, tmp_path, settings, scanner=scanner, store=store, verifier=verifier, meili=meili,
                  vault=vault, import_interval_s=0.0) as lab:
        r = lab.post(make_token(), ndjson(doc(1)))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "imports_disabled"


def test_too_many_open_batches_per_tenant_is_429(lab, clerk, make_token):
    for i in range(3):
        assert lab.post(clerk, ndjson(doc(i))).status_code == 202
    # văn thư khác cùng đơn vị cũng bị chặn: trần tính theo đơn vị
    r = lab.post(make_token(sub="u-van-thu-2"), ndjson(doc(9)))
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "too_many_imports"
    assert r.headers["Retry-After"] == "60"
    # đơn vị khác không bị ảnh hưởng
    assert lab.post(make_token(sub="u-van-thu-b", tenant=str(TENANT_B)), ndjson(doc(9))).status_code == 202
    # một lô xong thì gửi tiếp được
    lab.drain()
    assert lab.post(clerk, ndjson(doc(10))).status_code == 202


def test_full_spool_answers_busy(monkeypatch, tmp_path, settings, scanner, store, verifier, meili, vault, make_token):
    with make_lab(monkeypatch, tmp_path, settings, scanner=scanner, store=store, verifier=verifier, meili=meili,
                  vault=vault, import_spool_bytes=4096, import_zip_max_bytes=4096) as lab:
        lab.spool_dir.mkdir(parents=True, exist_ok=True)
        (lab.spool_dir / f"{uuid.uuid4()}.zip").write_bytes(b"z" * 4000)
        r = lab.post(make_token(), ndjson(doc(1, files=["a.pdf"])), archive=zip_bytes({"a.pdf": PDF}))
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "busy"
        assert r.headers["Retry-After"] == "60"
        # phần vừa nhận được xóa, không có lô
        assert [p.name.endswith(".zip") for p in lab.spool_dir.iterdir()] == [True]
        assert lab.imports.jobs == {}


@pytest.mark.parametrize(("data", "name", "params", "status", "code"), [
    (b"type_code,symbol\nCV,1\n", "lo.csv", {}, 400, "bad_header"),
    (b"\xff\xfe{}", "lo.ndjson", {}, 400, "bad_encoding"),
    (b'{"a": 1}\n', "lo.txt", {}, 400, "unknown_format"),
    (b"\n\n", "lo.ndjson", {}, 400, "empty"),
    (b'type_code,symbol,issuer_name,issued_on,summary\nCV,"1\n', "lo.csv", {}, 400, "bad_format"),
])
def test_whole_file_errors(lab, clerk, data, name, params, status, code):
    r = lab.post(clerk, data, name=name, mime="application/octet-stream", params=params)
    assert r.status_code == status, r.text
    assert r.json()["detail"]["code"] == code
    assert lab.imports.jobs == {}


def test_format_query_overrides_the_file_name(lab, clerk):
    r = lab.post(clerk, b"type_code,symbol,issuer_name,issued_on,summary\nCV,1/UB,UB,2026-10-01,Ve viec mau thu\n",
                 name="du-lieu.txt", mime="text/plain", params={"format": "csv"})
    assert r.status_code == 202, r.text
    assert r.json()["format"] == "csv"


def test_row_limits(monkeypatch, tmp_path, settings, scanner, store, verifier, meili, vault, make_token):
    with make_lab(monkeypatch, tmp_path, settings, scanner=scanner, store=store, verifier=verifier, meili=meili,
                  vault=vault, import_max_rows=5, import_register_max_rows=2) as lab:
        token = make_token()
        assert lab.post(token, ndjson(*(doc(i) for i in range(5)))).status_code == 202
        r = lab.post(token, ndjson(*(doc(i) for i in range(6))))
        assert r.status_code == 413 and r.json()["detail"]["code"] == "too_many_rows"
        # lô có vào sổ: trần riêng
        r = lab.post(token, ndjson(*(doc(i) for i in range(3))), params={"register": "true"})
        assert r.status_code == 413 and r.json()["detail"]["code"] == "too_many_rows"
        assert "vào sổ" in r.json()["detail"]["message"]
        r = lab.post(token, ndjson(*(doc(i) for i in range(2))), params={"register": "true"})
        assert r.status_code == 202 and r.json()["register"] is True


def test_archive_is_checked_when_the_batch_is_created(lab, clerk):
    archive = zip_bytes({"tep/a.pdf": PDF, "tep/b.pdf": PDF, "to.pdf": b"x" * (1024 * 1024 + 1)})
    data = ndjson(doc(1, files=["tep/a.pdf", "tep/b.pdf"]), doc(2, files=["tep/khong-co.pdf"]),
                  doc(3, files=["to.pdf"]), doc(4))
    r = lab.post(clerk, data, archive=archive)
    assert r.status_code == 202, r.text
    job = lab.job(r.json()["id"])
    assert job["archive_sha256"] == hashlib.sha256(archive).hexdigest() and job["archive_bytes"] == len(archive)
    lines = {x["line"]: x for x in lab.lines(job["id"])}
    assert lines[1]["status"] == "pending" and lines[1]["files"] == ["tep/a.pdf", "tep/b.pdf"]
    assert (lines[2]["status"], lines[2]["code"]) == ("failed", "missing_attachment")
    assert "tep/khong-co.pdf" in lines[2]["message"]
    assert (lines[3]["status"], lines[3]["code"]) == ("failed", "too_large")      # trần MOC_FILES_MAX_MB = 1
    # zip nằm ở spool, đúng tên lô, chỉ chủ đọc được
    path = lab.spool_dir / f"{job['id']}.zip"
    assert path.read_bytes() == archive
    assert oct(lab.spool_dir.stat().st_mode & 0o777) == "0o700"


def test_batch_storing_too_many_bytes_is_refused(monkeypatch, tmp_path, settings, scanner, store, verifier, meili,
                                                vault, make_token):
    # một mục zip trỏ lặp lại: mỗi dòng sẽ lưu một bản, nên tính mỗi lần trỏ vào trần MOC_IMPORT_STORE_MAX_MB
    big = b"%PDF-1.7\n" + b"\0" * 3000
    with make_lab(monkeypatch, tmp_path, settings, scanner=scanner, store=store, verifier=verifier, meili=meili,
                  vault=vault, import_store_max_bytes=4 * len(big)) as lab:
        token = make_token()
        archive = zip_bytes({"z.pdf": big})
        assert len(archive) < 200
        r = lab.post(token, ndjson(*(doc(n, files=["z.pdf"]) for n in range(5))), archive=archive)
        assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
        assert "chia thành nhiều lô" in r.json()["detail"]["message"]
        assert lab.imports.jobs == {} and list(lab.spool_dir.iterdir()) == []
        r = lab.post(token, ndjson(*(doc(n, files=["z.pdf"]) for n in range(4))), archive=archive)
        assert r.status_code == 202, r.text


@pytest.mark.parametrize(("data", "name"), [
    (ndjson(doc(1, restricted="yes", files=["mat.pdf"]), doc(2, restricted="1", files=["mat.pdf"]),
            doc(3, restricted="có", files=["mat.pdf"]), doc(4, restricted="true", files=["mat.pdf"])), "lo.ndjson"),
    ("type_code,symbol,issuer_name,issued_on,summary,restricted,files\n"
     "CV,1/UB,UB,2026-10-15,Về việc mẫu một,1,mat.pdf\nCV,2/UB,UB,2026-10-15,Về việc mẫu hai,có,mat.pdf\n"
     "CV,3/UB,UB,2026-10-15,Về việc mẫu ba,yes,mat.pdf\nCV,4/UB,UB,2026-10-15,Về việc mẫu bốn,x,mat.pdf\n"
     .encode(), "lo.csv"),
])
def test_restricted_of_the_wrong_type_never_stores_a_plain_copy(lab, clerk, store, data, name):
    # văn thư muốn văn bản hạn chế mà gõ sai kiểu: dòng lỗi ngay lúc tạo lô, không tệp nào vào kho (kể cả bản rõ)
    r = lab.post(clerk, data, name=name, mime="text/csv" if name.endswith(".csv") else "application/x-ndjson",
                 archive=zip_bytes({"mat.pdf": PDF}))
    assert r.status_code == 202, r.text
    assert (r.json()["failed"], r.json()["pending"]) == (4, 0)
    lab.drain()
    rows = lab.lines(r.json()["id"])
    assert {(x["status"], x["code"]) for x in rows} == {("failed", "bad_value")}
    assert all("restricted chỉ nhận true hoặc false" in x["message"] for x in rows)
    assert store.objects == {} and lab.hasura.files == {} and lab.hasura.act_calls == []
    assert list(lab.spool_dir.iterdir()) == []          # không dòng nào cần zip: không giữ


def test_lone_surrogate_is_a_row_error_not_a_500(lab, clerk):
    data = ndjson(doc(1), '{"type_code": "CV", "summary": "Về việc \\ud800 mẫu"}', doc(3))
    r = lab.post(clerk, data)
    assert r.status_code == 202, r.text
    lab.drain()
    got = {x["line"]: x for x in lab.lines(r.json()["id"])}
    assert (got[2]["status"], got[2]["code"]) == ("failed", "bad_value") and "\\ud800" in got[2]["message"]
    assert got[1]["status"] == got[3]["status"] == "ok"


def test_number_out_of_range_is_a_row_error_not_a_500(lab, clerk):
    # 1e999 → inf: json.loads nhận, nhưng HasuraClient (httpx2, allow_nan=False) không gửi được — cả yêu cầu lỗi 500
    data = ndjson(doc(1), '{"type_code": "CV", "x": 1e999}', '{"urgency": -1e999}', doc(4))
    r = lab.post(clerk, data)
    assert r.status_code == 202, r.text
    lab.drain()
    got = {x["line"]: x for x in lab.lines(r.json()["id"])}
    assert [(got[n]["status"], got[n]["code"]) for n in (1, 2, 3, 4)] == [
        ("ok", None), ("failed", "bad_value"), ("failed", "bad_value"), ("ok", None)]
    assert "1e999" in got[2]["message"]


def test_data_file_is_parsed_off_the_event_loop(lab, clerk, monkeypatch):
    from svc_files.imports import api

    real, loops = api.parse, []

    def spy(*args, **kw):
        try:
            loops.append(asyncio.get_running_loop())
        except RuntimeError:
            loops.append(None)          # luồng riêng: không có vòng sự kiện nào chạy ở đây
        return real(*args, **kw)

    monkeypatch.setattr(api, "parse", spy)
    assert lab.post(clerk, ndjson(doc(1))).status_code == 202
    assert loops == [None]


def test_broken_archive_is_400(lab, clerk):
    r = lab.post(clerk, ndjson(doc(1, files=["a.pdf"])), archive=b"PK\x03\x04 khong phai zip")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_archive"
    assert list(lab.spool_dir.iterdir()) == [] and lab.imports.jobs == {}


def test_archive_not_needed_by_any_row_is_not_kept(lab, clerk):
    r = lab.post(clerk, ndjson(doc(1)), archive=zip_bytes({"a.pdf": PDF}))
    assert r.status_code == 202
    assert list(lab.spool_dir.iterdir()) == []
    assert lab.job(r.json()["id"])["archive_sha256"] is not None


def test_only_the_creator_reads_a_batch(lab, clerk, make_token):
    job_id = lab.post(clerk, ndjson(doc(1))).json()["id"]
    r = lab.client.get(f"/api/imports/{job_id}", headers={"Authorization": f"Bearer {clerk}"})
    assert r.status_code == 200 and r.json()["id"] == job_id and r.json()["pending"] == 1
    assert r.headers["Cache-Control"] == "no-store"
    for token in (make_token(sub="u-van-thu-2"), make_token(tenant=str(TENANT_B)),
                  make_token(sub="u-hieu-truong", role="director")):
        for path in (f"/api/imports/{job_id}", f"/api/imports/{job_id}/rows"):
            r = lab.client.get(path, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 404, (token, path)
            assert r.json()["detail"]["code"] == "not_found"
    r = lab.client.get(f"/api/imports/{uuid.uuid4()}", headers={"Authorization": f"Bearer {clerk}"})
    assert r.status_code == 404


def test_rows_are_filtered_and_paged_without_the_submitted_data(lab, clerk):
    data = ndjson(doc(1), "[1]", doc(3, summary="ngắn"), doc(4), "{x", doc(6))
    job_id = lab.post(clerk, data).json()["id"]
    lab.drain()
    auth = {"Authorization": f"Bearer {clerk}"}
    body = lab.client.get(f"/api/imports/{job_id}", headers=auth).json()
    assert (body["status"], body["total"], body["ok"], body["failed"], body["pending"]) == ("done", 6, 3, 3, 0)
    failed = lab.client.get(f"/api/imports/{job_id}/rows", params={"status": "failed"}, headers=auth).json()
    assert [(r["line"], r["code"]) for r in failed["rows"]] == [(2, "not_object"), (3, "invalid"), (5, "bad_json")]
    assert failed["rows"][1]["fields"] == {"summary": "minLength"}
    assert failed["next_after"] is None
    page = lab.client.get(f"/api/imports/{job_id}/rows", params={"limit": 2}, headers=auth).json()
    assert [r["line"] for r in page["rows"]] == [1, 2] and page["next_after"] == 2
    rest = lab.client.get(f"/api/imports/{job_id}/rows", params={"after": 2, "limit": 10}, headers=auth).json()
    assert [r["line"] for r in rest["rows"]] == [3, 4, 5, 6]
    ok = rest["rows"][1]
    assert ok["status"] == "ok" and uuid.UUID(ok["document_id"]) and ok["register_number"] is None
    assert set(ok) == {"line", "status", "code", "message", "fields", "document_id", "register_number"}


def test_list_shows_only_own_batches_newest_first(lab, clerk, make_token):
    a = lab.post(clerk, ndjson(doc(1))).json()["id"]
    b = lab.post(clerk, ndjson(doc(2))).json()["id"]
    lab.post(make_token(sub="u-van-thu-2"), ndjson(doc(3)))
    r = lab.client.get("/api/imports", headers={"Authorization": f"Bearer {clerk}"})
    assert r.status_code == 200
    ids = [j["id"] for j in r.json()["imports"]]
    assert set(ids) == {a, b} and len(ids) == 2
    assert r.json()["imports"][0]["register"] is False


def test_database_down_is_503(lab, clerk):
    lab.imports.down = True
    r = lab.post(clerk, ndjson(doc(1)))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "database_unavailable"
    assert lab.imports.jobs == {}
