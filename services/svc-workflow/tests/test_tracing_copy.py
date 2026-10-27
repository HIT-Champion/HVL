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

"""svc_workflow/tracing.py là bản chép y hệt byte của svc_files/tracing.py (#364), như pii.py. Bộ test đầy đủ của bộ
che nằm ở svc-files (test_tracing.py); ở đây giữ hai bản không lệch nhau, kiểm biến bật/tắt và span của một Action:
Hasura chuyển tiếp traceparent của APISIX (forward_client_headers), nên Action nối vào đúng trace của yêu cầu."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from svc_workflow import tracing
from svc_workflow.app import create_app
from svc_workflow.config import ConfigError, Settings
from test_app import ENV, NoDirectory, body

ORIGINAL = pathlib.Path(__file__).resolve().parents[2] / "svc-files" / "src" / "svc_files" / "tracing.py"
TRACE = "0af7651916cd43dd8448eb211c80319c"


def test_copy_is_byte_identical_to_svc_files():
    if not ORIGINAL.is_file():
        pytest.skip("không có services/svc-files (chạy trong image svc-workflow)")
    assert pathlib.Path(tracing.__file__).read_bytes() == ORIGINAL.read_bytes(), (
        "svc_workflow/tracing.py lệch svc_files/tracing.py — sửa ở svc-files rồi chép lại y hệt")


def test_off_by_default_and_open_telemetry_is_not_loaded():
    assert Settings.from_env(ENV).trace_ratio == 0
    # tiến trình riêng: tệp này đã nạp OpenTelemetry vào tiến trình pytest
    code = ("import sys; from svc_workflow.app import create_app; from svc_workflow.config import Settings; "
            "from test_app import ENV, NoDirectory; from conftest import FakeHasura, FakeFlowable; "
            "create_app(Settings.from_env(ENV), hasura=FakeHasura(), flowable=FakeFlowable(), "
            "directory=NoDirectory()); "
            "print(sorted(m for m in sys.modules if m.startswith(('opentelemetry.sdk', 'opentelemetry.exporter', "
            "'opentelemetry.instrumentation', 'svc_workflow.tracing'))))")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                          cwd=pathlib.Path(__file__).parent)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


@pytest.mark.parametrize("value", ["2", "-1", "nan", "mot-phan-muoi"])
def test_bad_ratio_stops_the_service(value):
    with pytest.raises(ConfigError):
        Settings.from_env({**ENV, "MOC_TRACE_RATIO": value})


def test_action_joins_the_gateway_trace(monkeypatch, hasura, flowable):
    exporter, installed, real, textmap = InMemorySpanExporter(), [], tracing.install, get_global_textmap()
    monkeypatch.setattr(tracing, "install", lambda app, service: installed.append(
        (app, real(app, service, exporter=exporter))))
    app = create_app(Settings.from_env({**ENV, "MOC_TRACE_RATIO": "0.1"}), hasura=hasura, flowable=flowable,
                     directory=NoDirectory())  # type: ignore[arg-type]
    try:
        with TestClient(app) as client:
            r = client.post("/actions/myTasks", json=body("myTasks", "staff"),
                            headers={"X-Moc-Action-Secret": "bi-mat-action",
                                     "traceparent": f"00-{TRACE}-b7ad6b7169203331-01"})
            assert r.status_code == 200, r.text
        ((_, provider),) = installed
        provider.force_flush()
        (span,) = exporter.get_finished_spans()
        assert span.kind == SpanKind.SERVER and span.name == "POST /actions/{name}"
        assert span.context.trace_id == int(TRACE, 16)
        assert span.resource.attributes["service.name"] == "svc-workflow"
        assert "bi-mat-action" not in str(dict(span.attributes))
    finally:
        HTTPX2ClientInstrumentor().uninstrument()
        for instrumented, provider in installed:
            FastAPIInstrumentor.uninstrument_app(instrumented)
            provider.shutdown()
        set_global_textmap(textmap)
