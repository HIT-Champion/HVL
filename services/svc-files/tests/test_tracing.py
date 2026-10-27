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

"""Truy vết phân tán (#364): tắt thì không nạp OpenTelemetry; bật thì chỉ ghi yêu cầu APISIX đã chọn, span rời dịch
vụ không mang chuỗi truy vấn, header, đường dẫn webhook ngoài, thông điệp lỗi hay thông tin cá nhân."""

from __future__ import annotations

import asyncio
import dataclasses
import http.server
import json
import os
import pathlib
import re
import subprocess
import sys
import threading

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Link, SpanContext, SpanKind, Status, StatusCode

from svc_files import tracing
from svc_files.app import create_app
from svc_files.config import ConfigError, Settings

TRACE = "0af7651916cd43dd8448eb211c80319c"
SAMPLED = f"00-{TRACE}-b7ad6b7169203331-01"         # APISIX đã chọn yêu cầu này
NOT_SAMPLED = f"00-{TRACE}-b7ad6b7169203331-00"
PHONE = "0912 345 678"                              # giá trị giả lập
EMAIL = "nguyenvanb@example.com"
ENV = {"MOC_OIDC_ISSUER": "https://moc.example/realms/moc", "MOC_OIDC_JWKS_URL": "http://unused/jwks",
       "SEAWEEDFS_S3_ACCESS_KEY": "t", "SEAWEEDFS_S3_SECRET_KEY": "t", "HASURA_ADMIN_SECRET": "t",
       "MEILISEARCH_API_KEY": "t", "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_ASK_ENABLED": "false",
       "MOC_ASK_SYNC_INTERVAL_S": "0", "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0",
       "MOC_AI_URL": "", "MOC_IMPORT_INTERVAL_S": "0"}


class Traced:
    """Gọi ``tracing.install`` thật nhưng gửi span vào bộ nhớ; gỡ instrumentation toàn cục sau test."""

    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.installed: list[tuple[FastAPI, object]] = []
        self.real = tracing.install

    def install(self, app: FastAPI, service: str) -> object:
        provider = self.real(app, service, exporter=self.exporter)
        self.installed.append((app, provider))
        return provider

    def spans(self) -> list[ReadableSpan]:
        for _, provider in self.installed:
            provider.force_flush()
        return list(self.exporter.get_finished_spans())


@pytest.fixture
def traced(monkeypatch):
    textmap = get_global_textmap()
    t = Traced()
    monkeypatch.setattr(tracing, "install", lambda app, service: t.install(app, service))
    monkeypatch.setenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", "")      # install() đặt biến này; trả lại như cũ sau test
    yield t
    HTTPX2ClientInstrumentor().uninstrument()
    for app, provider in t.installed:
        FastAPIInstrumentor.uninstrument_app(app)
        provider.shutdown()
    set_global_textmap(textmap)


@pytest.fixture
def traced_client(settings, scanner, store, verifier, hasura, meili, vault, traced):
    app = create_app(dataclasses.replace(settings, trace_ratio=0.1), scanner=scanner, store=store,
                     verifier=verifier, hasura=hasura, meili=meili, vault=vault)
    with TestClient(app) as c:
        yield c


def flat(span: ReadableSpan) -> str:
    return json.dumps({"name": span.name, "attributes": dict(span.attributes or {}),
                       "events": [[e.name, dict(e.attributes or {})] for e in span.events],
                       "status": span.status.description}, ensure_ascii=False)


# --- tắt ----------------------------------------------------------------------------------------------------------

def test_off_by_default_and_open_telemetry_is_not_loaded(settings):
    assert settings.trace_ratio == 0
    # tiến trình riêng: các test khác trong tệp này đã nạp OpenTelemetry vào tiến trình pytest
    code = ("import sys, conftest; from svc_files.app import create_app; from svc_files.config import Settings; "
            f"create_app(Settings.from_env({ENV!r}), store=conftest.FakeStore(), scanner=conftest.FakeScanner(), "
            "hasura=conftest.FakeHasura(), meili=conftest.FakeMeili(), vault=conftest.FakeVault()); "
            "print(sorted(m for m in sys.modules if m.startswith(('opentelemetry.sdk', 'opentelemetry.exporter', "
            "'opentelemetry.instrumentation', 'svc_files.tracing'))))")
    tests = pathlib.Path(__file__).resolve().parent
    # pytest tự thêm src, tests vào sys.path (pyproject.toml), tiến trình con thì không: CI không cài gói
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tests.parent / "src"), str(tests)])}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                          cwd=tests, env=env)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


@pytest.mark.parametrize("value, ratio", [("", 0.0), ("0", 0.0), (" 0.25 ", 0.25), ("1", 1.0)])
def test_ratio_from_env(value, ratio):
    assert Settings.from_env({**ENV, "MOC_TRACE_RATIO": value}).trace_ratio == ratio


@pytest.mark.parametrize("value", ["1.5", "-0.1", "nan", "inf", "mot-phan-muoi"])
def test_bad_ratio_stops_the_service(value):
    with pytest.raises(ConfigError):
        Settings.from_env({**ENV, "MOC_TRACE_RATIO": value})


# --- bật: chỉ yêu cầu APISIX đã chọn --------------------------------------------------------------------------------

def test_only_requests_sampled_at_the_gateway_are_recorded(traced_client, traced, make_token):
    headers = {"Authorization": f"Bearer {make_token()}"}
    assert traced_client.get("/api/search", params={"q": "x"}, headers=headers).status_code == 200
    assert traced_client.get("/api/search", params={"q": "x"},
                             headers={**headers, "traceparent": NOT_SAMPLED}).status_code == 200
    assert traced_client.get("/healthz", headers={"traceparent": SAMPLED}).status_code == 200
    assert traced.spans() == []

    r = traced_client.get("/api/search", params={"q": f"{PHONE} {EMAIL}"}, headers={**headers, "traceparent": SAMPLED})
    assert r.status_code == 200
    (span,) = traced.spans()
    assert span.kind == SpanKind.SERVER and span.name == "GET /api/search"
    assert span.context.trace_id == int(TRACE, 16) and span.parent.span_id == 0xb7ad6b7169203331
    assert span.resource.attributes["service.name"] == "svc-files"
    attrs = dict(span.attributes)
    assert attrs["http.url"] == "http://testserver/api/search" and attrs["http.target"] == "/api/search"
    assert attrs["http.route"] == "/api/search" and attrs["http.status_code"] == 200
    assert set(attrs) <= tracing.KEEP | tracing.PATHS | tracing.URLS
    text = flat(span)
    for leak in ("0912", "nguyenvanb", "Bearer", "testclient", "?q"):
        assert leak not in text, leak


# --- bật: lời gọi httpx2 trong yêu cầu --------------------------------------------------------------------------

@pytest.fixture
def upstream():
    """Máy chủ HTTP giả. Gọi bằng ``localhost`` là dịch vụ nội bộ (tên không có dấu chấm như meilisearch, hasura
    trong mạng Docker); gọi bằng ``127.0.0.1`` là máy ngoài (tên có dấu chấm: webhook, cổng SMS trong mạng LAN)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        seen: list[dict[str, str]] = []

        def do_GET(self) -> None:
            Handler.seen.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        do_POST = do_GET

        def log_message(self, *args) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://localhost:{server.server_address[1]}", Handler.seen
    server.shutdown()


@pytest.fixture
def small_app(traced, upstream):
    base, _ = upstream
    app = FastAPI()

    @app.get("/goi")
    async def goi() -> dict[str, bool]:
        async with httpx2.AsyncClient(timeout=5) as c:
            await c.get(f"{base}/indexes/docs/search", params={"q": PHONE})
            # máy ngoài, token trong đường dẫn như webhook Slack
            outside = base.replace("http://localhost", "http://moc:mat-khau@127.0.0.1")
            await c.post(f"{outside}/services/T0/B0/{'b' * 24}?x=1", json={})
        raise ValueError(f"không gửi được cho {EMAIL}")

    traced.install(app, "svc-files")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def calls(upstream, host: str) -> list[dict[str, str]]:
    """Header (tên viết thường) của các lời gọi tới máy chủ giả qua tên máy ``host``."""
    seen = [{k.lower(): v for k, v in headers.items()} for headers in upstream[1]]
    return [h for h in seen if h["host"].rpartition(":")[0] == host]


def test_client_calls_inside_a_sampled_request(small_app, traced, upstream):
    headers = {"traceparent": SAMPLED, "baggage": "nguoi-dung=nguyenvanb"}
    assert small_app.get("/goi", headers=headers).status_code == 500
    spans = traced.spans()
    (server,) = [s for s in spans if s.kind == SpanKind.SERVER]
    (internal,) = [s for s in spans if s.kind == SpanKind.CLIENT]                      # máy ngoài: không có span
    assert internal.attributes["http.url"].endswith("/indexes/docs/search")             # nội bộ: giữ đường dẫn
    assert internal.attributes["http.url"].startswith("http://localhost:")
    assert server.status.status_code == StatusCode.ERROR and server.status.description is None
    assert [dict(e.attributes) for e in server.events] == [{"exception.type": "ValueError"}]
    for span in (internal, server):
        assert span.context.trace_id == int(TRACE, 16)
        text = flat(span)
        for leak in ("0912", "nguyenvanb", "mat-khau", "bbbb", "/services/", "?", "Traceback"):
            assert leak not in text, (leak, text)
    # dịch vụ phía sau nhận traceparent của cùng trace, không có baggage dù client gửi; máy ngoài không nhận gì
    (inside,), (outside,) = calls(upstream, "localhost"), calls(upstream, "127.0.0.1")
    assert inside["traceparent"].split("-")[1] == TRACE and "baggage" not in inside
    assert not {"traceparent", "tracestate", "baggage"} & set(outside)


def test_unsampled_requests_and_background_work_leave_no_span(small_app, traced, upstream):
    small_app.get("/goi", headers={"traceparent": NOT_SAMPLED, "baggage": "k=v"})
    small_app.get("/goi")

    async def background() -> None:            # vòng nền (lập chỉ mục, gửi thông báo): không có yêu cầu cha
        async with httpx2.AsyncClient(timeout=5) as c:
            await c.get(f"{upstream[0]}/health")

    asyncio.run(background())
    assert traced.spans() == []
    assert all("baggage" not in {k.lower() for k in seen} for seen in upstream[1])
    # trace không ghi (cờ 00) vẫn có mã hợp lệ, propagator vẫn chèn: máy ngoài thì không nhận
    outside = calls(upstream, "127.0.0.1")
    assert len(outside) == 2 and all("traceparent" not in seen for seen in outside)


def test_external_hosts_are_left_alone():
    pattern = re.compile(tracing.EXTERNAL)
    for url in ("https://hooks.slack.com/services/T0", "http://u:p@192.168.1.50:8080/message", "http://[::1]:80/",
                "https://bot-api.zaloplatforms.com/bot123:abc/sendMessage", "http://127.0.0.1:9/x"):
        assert pattern.search(url), url
    for url in ("http://hasura:8080/v1/graphql", "http://meilisearch:7700/indexes", "http://localhost:1/a.b",
                "http://svc-files:8000/x?h=a.b", "http://u.v@keycloak:8080/realms"):
        assert not pattern.search(url), url
    assert "," not in tracing.EXTERNAL


# --- bộ che -------------------------------------------------------------------------------------------------------

def test_redact_keeps_only_the_whitelist():
    ctx = SpanContext(int(TRACE, 16), 0xb7ad6b7169203331, is_remote=False)
    span = ReadableSpan(
        name=f"GET gọi {PHONE}", context=ctx,
        attributes={"http.method": "GET", "http.request.header.authorization": ("Bearer abc",),
                    "http.user_agent": "Mozilla", "net.peer.ip": "10.0.0.7", "url.full": "https://u:p@x.vn:8443/a?b=c",
                    "url.path": f"/api/x/{EMAIL}", "http.route": "/api/x/{id}", "db.statement": "select 1"},
        events=[Event("exception", {"exception.type": "KeyError", "exception.message": EMAIL,
                                    "exception.stacktrace": "Traceback …"})],
        links=[Link(ctx, {"note": EMAIL})],
        status=Status(StatusCode.ERROR, f"lỗi {EMAIL}"), kind=SpanKind.CLIENT)
    out = tracing.redact(span)
    assert dict(out.attributes) == {"http.method": "GET", "url.full": "https://x.vn:8443",
                                    "url.path": "/api/x/[EMAIL]", "http.route": "/api/x/{id}"}
    assert out.name == "GET gọi [SĐT]"
    assert [dict(e.attributes) for e in out.events] == [{"exception.type": "KeyError"}]
    assert [link.attributes for link in out.links] == [None]
    assert out.status.status_code == StatusCode.ERROR and out.status.description is None
    assert out.context == ctx and out.kind == SpanKind.CLIENT
