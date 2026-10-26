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

"""Cờ MOC_OFFICE_ENABLED (#302, docs/architecture.md §4.7 bước 2): tắt Văn phòng điện tử khỏi svc-files.

Bật (mặc định): đúng bộ route, đúng thứ tự như trước khi tách route ra office/api.py. Tắt: dịch vụ vẫn lên, route
lõi còn nguyên; route của Văn phòng trả 404, vòng nền của nó không chạy."""

from __future__ import annotations

import pytest

from conftest import FakeHasura, FakeMeili, FakeScanner, FakeStore, FakeVault
from svc_files.archive import Archiver
from svc_files.config import ConfigError
from svc_files.docread.summarize import NullSummarizer
from svc_files.imports.runner import Importer
from svc_files.office import api as office_api
from test_status import Network, StubAi, status_client, status_settings

CASE = "8a0c6a52-0000-4000-8000-0000000000c1"
DOC = "8a0c6a52-0000-4000-8000-0000000000d1"
FILE = "8a0c6a52-0000-4000-8000-0000000000f1"
NOT_FOUND = {"detail": "Not Found"}     # Starlette: không route nào khớp đường dẫn

# Đường dẫn công khai (OpenAPI) theo đúng thứ tự gắn route — như docs/api/openapi/svc-files.json trước khi tách
PUBLIC_API = [
    ("/api/files/{file_id}/read", ["POST"]),
    ("/api/documents/ask", ["POST"]),
    ("/api/files", ["POST"]),
    ("/api/imports/{kind}", ["POST"]),
    ("/api/imports/{job_id}", ["GET"]),
    ("/api/imports/{job_id}/rows", ["GET"]),
    ("/api/imports", ["GET"]),
    ("/api/files/{file_id}", ["GET"]),
    ("/api/search", ["GET"]),
    ("/api/documents/{document_id}/preview", ["GET"]),
    ("/api/registers/{direction}/{year}", ["GET"]),
    ("/api/registers/{direction}/{year}/pdf", ["GET"]),
    ("/api/verify/ca.pem", ["GET"]),
    ("/api/verify/anchor-key.pem", ["GET"]),
    ("/api/verify/{code}", ["GET"]),
    ("/api/verify", ["GET"]),
    ("/api/status", ["GET"]),
    ("/api/case-files/{case_file_id}/archive", ["GET", "POST"]),
    ("/api/case-files/{case_file_id}/archive/files/{file_id}", ["GET"]),
    ("/api/case-files/archive-stats", ["GET"]),
]
# Văn phòng tắt: chỉ còn các đường dẫn của lõi, giữ thứ tự cũ
CORE_API = ["/api/documents/ask", "/api/files", "/api/files/{file_id}", "/api/search", "/api/verify/anchor-key.pem",
            "/api/status"]

# 12 route khai trong office/api.py, rồi các route Văn phòng gắn qua install(): đọc văn bản đến, gợi ý giao việc, nạp lô
OFFICE_ROUTES = [
    ("POST", "/internal/issue"),
    ("POST", "/internal/dispatch-file"),
    ("GET", f"/api/documents/{DOC}/preview"),
    ("GET", "/api/registers/in/2026"),
    ("GET", "/api/registers/out/2026/pdf"),
    ("GET", "/api/verify/ca.pem"),
    ("GET", "/api/verify/ABCDEFGH"),
    ("GET", "/api/verify"),
    ("GET", f"/api/case-files/{CASE}/archive"),
    ("GET", f"/api/case-files/{CASE}/archive/files/{FILE}"),
    ("POST", f"/api/case-files/{CASE}/archive"),
    ("GET", "/api/case-files/archive-stats"),
    ("POST", f"/api/files/{FILE}/read"),
    ("POST", "/internal/similar-documents"),
    ("POST", "/api/imports/incoming"),
    ("GET", f"/api/imports/{FILE}"),
    ("GET", f"/api/imports/{FILE}/rows"),
    ("GET", "/api/imports"),
]


def parts() -> dict:
    return {"scanner": FakeScanner(), "store": FakeStore(), "hasura": FakeHasura(), "meili": FakeMeili(),
            "vault": FakeVault(), "ai": StubAi(), "net": Network()}


@pytest.fixture
def started(monkeypatch) -> list[str]:
    """Tên các vòng nền của Văn phòng mà lifespan đã khởi động."""
    names: list[str] = []

    def mark(name: str):
        async def run(self) -> None:
            names.append(name)
        return run

    monkeypatch.setattr(Archiver, "run", mark("archive"))
    monkeypatch.setattr(NullSummarizer, "run", mark("summarizer"))
    monkeypatch.setattr(Importer, "run", mark("imports"))
    return names


def settings_with_loops(tmp_path, **extra: str):
    # nộp lưu theo mặc định (3600 giây), nạp lô bật: cả ba vòng nền của Văn phòng đều có lý do để chạy
    return status_settings(MOC_IMPORT_INTERVAL_S="2", MOC_IMPORT_SPOOL_DIR=str(tmp_path / "spool"), **extra)


# --- đọc cờ -----------------------------------------------------------------------------------------------------------

def test_office_is_on_by_default():
    assert status_settings().office_enabled is True


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("1", True), ("false", False), ("0", False),
                                               (" FALSE ", False)])
def test_office_flag_values(raw, expected):
    assert status_settings(MOC_OFFICE_ENABLED=raw).office_enabled is expected


@pytest.mark.parametrize("raw", ["", "tat", "2"])
def test_office_flag_rejects_anything_else(raw):
    with pytest.raises(ConfigError, match="MOC_OFFICE_ENABLED"):
        status_settings(MOC_OFFICE_ENABLED=raw)


# --- bật (mặc định): không đổi gì so với trước khi tách ---------------------------------------------------------------

def test_office_on_keeps_the_public_api_and_its_order(verifier):
    with status_client(status_settings(), parts(), verifier) as c:
        paths = c.get("/openapi.json").json()["paths"]
    assert [(p, sorted(m.upper() for m in ops)) for p, ops in paths.items()] == PUBLIC_API


@pytest.mark.parametrize(("method", "path"), OFFICE_ROUTES)
def test_office_on_serves_every_office_route(verifier, method, path):
    with status_client(status_settings(), parts(), verifier) as c:
        r = c.request(method, path)
    assert r.json() != NOT_FOUND     # route có mặt: 401 thiếu token, 422 thiếu tham số, 404 có mã lỗi riêng…


def test_office_on_starts_its_background_loops(verifier, started, tmp_path):
    with status_client(settings_with_loops(tmp_path), parts(), verifier) as c:
        assert c.get("/healthz").status_code == 200
        assert c.app.state.reader is not None and c.app.state.importer is not None
    assert sorted(started) == ["archive", "imports", "summarizer"]


# --- tắt: lõi còn nguyên, Văn phòng biến mất --------------------------------------------------------------------------

def test_office_off_public_api_is_the_core_only(verifier):
    with status_client(status_settings(MOC_OFFICE_ENABLED="false"), parts(), verifier) as c:
        paths = c.get("/openapi.json").json()["paths"]
    assert list(paths) == CORE_API


@pytest.mark.parametrize(("method", "path"), OFFICE_ROUTES)
def test_office_off_route_is_404(verifier, method, path):
    with status_client(status_settings(MOC_OFFICE_ENABLED="false"), parts(), verifier) as c:
        r = c.request(method, path)
    assert r.status_code == 404 and r.json() == NOT_FOUND


def test_office_off_core_routes_still_answer(verifier):
    with status_client(status_settings(MOC_OFFICE_ENABLED="false"), parts(), verifier) as c:
        assert c.get("/healthz").json() == {"status": "ok"}
        ready = c.get("/readyz")
        assert ready.status_code == 200 and ready.json()["ai"] is False   # không có tác tử đọc văn bản đến
        assert c.get("/api/status").status_code == 200
        assert c.get("/metrics").status_code == 200
        # két chưa có khóa ký mốc neo: 404 của chính route lõi, không phải "không có route"
        anchor = c.get("/api/verify/anchor-key.pem")
        assert anchor.status_code == 404 and anchor.json()["detail"]["code"] == "no_anchor_key"
        for method, path in [("POST", "/api/files"), ("GET", f"/api/files/{FILE}"), ("GET", "/api/search?q=x"),
                             ("POST", "/api/documents/ask")]:
            r = c.request(method, path)
            assert r.status_code == 401 and r.json() != NOT_FOUND, (method, path)


def test_office_off_runs_no_office_background_loop(verifier, started, monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise AssertionError("Văn phòng tắt mà vẫn dựng")

    monkeypatch.setattr(office_api, "Office", boom)
    with status_client(settings_with_loops(tmp_path, MOC_OFFICE_ENABLED="false"), parts(), verifier) as c:
        assert c.get("/healthz").status_code == 200
        assert c.app.state.reader is None and c.app.state.importer is None
    assert started == []
