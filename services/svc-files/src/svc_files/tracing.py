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

"""Truy vết phân tán (#364): span của dịch vụ gửi tới Jaeger qua OTLP/HTTP. Tắt mặc định.

Bật khi ``MOC_TRACE_RATIO`` > 0, cùng biến APISIX dùng để lấy mẫu (profile ``trace`` chạy Jaeger; docs/van-hanh.md mục
Truy vết). Tắt thì ``create_app`` không import tệp này, không nạp gói OpenTelemetry nào. Dịch vụ không tự lấy mẫu: chỉ
ghi span khi yêu cầu mang ``traceparent`` APISIX đã chọn (``ParentBased(ALWAYS_OFF)``), nên việc nền (đồng bộ danh bạ,
gửi thông báo, lập chỉ mục…) không sinh span nào.

Span rời dịch vụ qua ``Redacting``, theo danh sách trắng:
- chỉ giữ thuộc tính có tên trong ``KEEP``, ``PATHS``, ``URLS``; mọi giá trị chuỗi qua ``pii.mask_text``;
- đường dẫn, URL bỏ chuỗi truy vấn (ô tìm kiếm ``?q=…``); URL tới máy ngoài (tên có dấu chấm: webhook Slack, ntfy…
  mang token trong đường dẫn) chỉ còn ``scheme://host[:port]``;
- sự kiện ngoại lệ chỉ giữ ``exception.type``; bỏ mô tả lỗi của trạng thái (thường là ``str(exc)``).
Instrumentation không ghi header (Authorization, cookie) nếu không bật; danh sách trắng bỏ chúng cả khi có.
svc_workflow/tracing.py là bản chép y hệt byte của tệp này (test so byte).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ParentBased
from opentelemetry.trace import Link, Status
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from . import pii

ENDPOINT = "http://jaeger:4318/v1/traces"
# dò sống, dò sẵn sàng, chỉ số Prometheus: không ghi span
EXCLUDED = "healthz,readyz,metrics"

# Thuộc tính được rời dịch vụ: tên theo quy ước HTTP cũ và mới của instrumentation FastAPI, httpx2
KEEP = frozenset({
    "http.method", "http.request.method", "http.status_code", "http.response.status_code", "http.route",
    "http.scheme", "url.scheme", "http.flavor", "network.protocol.version", "error.type",
    "net.peer.name", "net.peer.port", "server.address", "server.port", "net.host.name", "net.host.port",
})
PATHS = frozenset({"http.target", "url.path"})
URLS = frozenset({"http.url", "url.full"})


def _url(value: str) -> str:
    parts = urlsplit(value)
    host = parts.netloc.rpartition("@")[2]          # bỏ user:mật-khẩu@ nếu có
    if "." in (parts.hostname or ""):
        return urlunsplit((parts.scheme, host, "", "", ""))
    return urlunsplit((parts.scheme, host, pii.mask_text(parts.path), "", ""))


def _attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if key in PATHS:
            out[key] = pii.mask_text(str(value).partition("?")[0])
        elif key in URLS:
            out[key] = _url(str(value))
        elif key in KEEP:
            out[key] = pii.mask_text(value) if isinstance(value, str) else value
    return out


def redact(span: ReadableSpan) -> ReadableSpan:
    """Bản của ``span`` được phép rời dịch vụ (luật ở đầu tệp)."""
    events = [Event(e.name, {k: v for k, v in (e.attributes or {}).items() if k == "exception.type"}, e.timestamp)
              for e in span.events]
    return ReadableSpan(
        name=pii.mask_text(span.name),
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=_attributes(span.attributes),
        events=events,
        links=[Link(link.context) for link in span.links],
        kind=span.kind,
        status=Status(span.status.status_code),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class Redacting(SpanExporter):
    """Bọc exporter thật: chỉ ``redact(span)`` tới được Jaeger."""

    def __init__(self, inner: SpanExporter) -> None:
        self.inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self.inner.export([redact(span) for span in spans])

    def shutdown(self) -> None:
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.inner.force_flush(timeout_millis)


def install(app: FastAPI, service: str, *, exporter: SpanExporter | None = None) -> TracerProvider:
    """Ghi span cho route của ``app`` và mọi lời gọi httpx2 trong tiến trình. ``exporter``: test thay Jaeger."""
    # chỉ traceparent: baggage client tự gửi không được chuyển tiếp sang dịch vụ khác hay webhook ngoài
    set_global_textmap(TraceContextTextMapPropagator())
    provider = TracerProvider(resource=Resource.create({"service.name": service}), sampler=ParentBased(ALWAYS_OFF))
    provider.add_span_processor(BatchSpanProcessor(Redacting(exporter or OTLPSpanExporter(ENDPOINT, timeout=3))))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=EXCLUDED,
                                       exclude_spans=["receive", "send"])
    HTTPX2ClientInstrumentor().instrument(tracer_provider=provider)
    return provider
