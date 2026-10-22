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

"""Nhật ký qua bộ che PII (F4.4): create_app gắn bộ lọc vào logger của dịch vụ và của uvicorn; traceback của
office.action.failed được che; dòng truy cập bỏ chuỗi truy vấn.

Số, email trong tệp này là giá trị giả lập đúng định dạng (số ví dụ, miền example.com), không phải của ai.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from uvicorn.config import LOGGING_CONFIG
from uvicorn.logging import AccessFormatter, DefaultFormatter
from uvicorn.protocols.utils import get_path_with_query_string

from conftest import DOC, SCHEMAS, TENANT
from svc_workflow.app import create_app
from svc_workflow.config import Settings
from svc_workflow.pii import PiiFilter
from svc_workflow.workflow import Workflow

PHONE = "0912345678"                    # giả lập
CCCD = "001205000017"                   # giả lập
EMAIL = "nguyenvanb@example.com"        # giả lập (miền dành cho ví dụ, RFC 2606)
LOGGERS = ("svc_workflow", "uvicorn", "uvicorn.error", "uvicorn.access")
ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": "bi-mat-action", "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_DIRECTORY_SYNC_INTERVAL_S": "0", "MOC_RECONCILE_INTERVAL_S": "0",
    "MOC_PROCESSES_DIR": "/khong-co", "MOC_SCHEMAS_DIR": str(SCHEMAS),
}


class NoDirectory:
    async def aclose(self) -> None: ...


def make_app(hasura, flowable):
    return create_app(Settings.from_env(ENV), hasura=hasura, flowable=flowable,
                      directory=NoDirectory())  # type: ignore[arg-type]


@contextlib.contextmanager
def bare_loggers() -> Iterator[None]:
    """Bỏ handler, bộ lọc mà các lần create_app trước để lại trên logger dùng chung (chỉ kiểm lần create_app của
    test này); trả lại nguyên trạng khi xong."""
    saved = [(lg, lg.handlers[:], lg.filters[:], lg.level, lg.propagate) for lg in map(logging.getLogger, LOGGERS)]
    try:
        for lg, *_ in saved:
            lg.handlers.clear()
            lg.filters.clear()
        yield
    finally:
        for lg, handlers, filters, level, propagate in saved:
            lg.handlers[:], lg.filters[:], lg.propagate = handlers, filters, propagate
            lg.setLevel(level)


def uvicorn_logging() -> None:
    """Như uvicorn làm trước khi gọi factory (LOGGING_CONFIG mặc định): handler "default" ra stderr cho uvicorn và
    uvicorn.error, handler "access" ra stdout cho uvicorn.access. Không gọi dictConfig vì nó đóng mọi handler đang có,
    kể cả của pytest."""
    formatters = LOGGING_CONFIG["formatters"]
    for name, stream, formatter in (
            ("uvicorn", sys.stderr, DefaultFormatter(formatters["default"]["fmt"], use_colors=False)),
            ("uvicorn.access", sys.stdout, AccessFormatter(formatters["access"]["fmt"], use_colors=False))):
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


@pytest.mark.parametrize("handler_first", [False, True], ids=["nhu-chay-that", "logger-da-co-handler"])
def test_create_app_masks_service_and_uvicorn_lines(handler_first, hasura, flowable, capsys):
    with bare_loggers():
        uvicorn_logging()
        log = logging.getLogger("svc_workflow")
        if handler_first:       # logger đã có handler (test gắn trước): _setup_logging không thêm handler nào
            log.addHandler(logging.StreamHandler(sys.stderr))
            log.setLevel(logging.INFO)
        for _ in range(2):      # dựng app lần nữa (test, nhiều worker): vẫn một bộ lọc ở mỗi chỗ
            make_app(hasura, flowable)
        for name in LOGGERS:
            logger = logging.getLogger(name)
            for where in (logger, *logger.handlers):
                access = [f.access for f in where.filters if isinstance(f, PiiFilter)]
                assert access == [name == "uvicorn.access"], (name, where)

        # đúng lời gọi của uvicorn khi trả xong một yêu cầu (protocols/http/h11_impl.py)
        path = get_path_with_query_string({"path": "/healthz", "query_string": f"so={PHONE}".encode()})
        logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "172.18.0.7:40112", "GET", path, "1.1",
                                                 200)
        try:
            raise ValueError(f"không gửi được tới {EMAIL}")
        except ValueError as exc:
            logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=exc)
        log.warning(json.dumps({"event": "core.thu", "error": f"CCCD {CCCD} trùng"}, ensure_ascii=False))
        out, err = capsys.readouterr()

    assert '172.18.0.7:40112 - "GET /healthz?… HTTP/1.1" 200' in out and "so=" not in out
    assert "Exception in ASGI application" in err and "ValueError: không gửi được tới [EMAIL]" in err
    assert '{"event": "core.thu", "error": "CCCD [CCCD] trùng"}' in err
    for value in (PHONE, CCCD, EMAIL):
        assert value not in out + err


def test_failed_action_traceback_is_masked(hasura, flowable, monkeypatch):
    async def fails(self, actor, document_id):
        raise ValueError("Số định danh 001205000017 đã gắn với hồ sơ khác")   # dòng này cũng hiện trong traceback

    monkeypatch.setattr(Workflow, "register_incoming", fails)
    app = make_app(hasura, flowable)
    log, stream = logging.getLogger("svc_workflow"), io.StringIO()
    handler = logging.StreamHandler(stream)       # gắn sau create_app: bộ lọc ở mức logger vẫn che
    handler.setFormatter(logging.Formatter("%(message)s"))      # như _setup_logging
    log.addHandler(handler)
    try:
        with TestClient(app) as c:
            r = c.post("/actions/registerIncoming",
                       json={"action": {"name": "registerIncoming"}, "input": {"documentId": DOC},
                             "session_variables": {"x-hasura-role": "clerk", "x-hasura-user-id": "u-clerk",
                                                   "x-hasura-tenant-id": str(TENANT)}},
                       headers={"X-Moc-Action-Secret": "bi-mat-action", "X-Request-Id": "req-f44"})
    finally:
        log.removeHandler(handler)
    assert r.status_code == 500 and r.json()["extensions"]["code"] == "internal" and CCCD not in r.text

    text = stream.getvalue()
    head, _, trace = text[text.index('{"event": "office.action.failed"'):].partition("\n")
    assert json.loads(head) == {"event": "office.action.failed", "action": "registerIncoming", "request_id": "req-f44"}
    assert trace.startswith("Traceback (most recent call last):")
    assert 'raise ValueError("Số định danh [CCCD] đã gắn với hồ sơ khác")' in trace     # dòng mã trong traceback
    assert "\nValueError: Số định danh [CCCD] đã gắn với hồ sơ khác\n" in trace
    assert CCCD not in text
