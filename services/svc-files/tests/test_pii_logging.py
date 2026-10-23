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

"""Nhật ký qua bộ che PII (F4.4): create_app gắn bộ lọc vào logger của dịch vụ và của uvicorn; dòng chặn tệp nhiễm
ghi tên đã che, còn sổ kiểm toán giữ tên gốc; dòng truy cập bỏ chuỗi truy vấn.

Kèm kiểm tĩnh định dạng nhật ký truy cập của APISIX (platform/apisix/config.yaml) và nginx của app-office: không còn chuỗi
truy vấn và Referer, các trường khác giữ như mặc định. Không chạy được APISIX/nginx ở đây, nên regex của map được
thử bằng re của Python; cú pháp thật do người tích hợp kiểm trên stack (apisix test, nginx -t).

Số, email trong tệp này là giá trị giả lập đúng định dạng (số ví dụ, miền example.com), không phải của ai.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import pathlib
import re
import sys
from collections.abc import Iterator

import pytest
from uvicorn.config import LOGGING_CONFIG
from uvicorn.logging import AccessFormatter, DefaultFormatter
from uvicorn.protocols.utils import get_path_with_query_string

from conftest import EICAR
from svc_files.app import create_app
from svc_files.pii import PiiFilter

PHONE = "0912345678"                    # giả lập
CCCD = "001205000017"                   # giả lập
EMAIL = "nguyenvanb@example.com"        # giả lập (miền dành cho ví dụ, RFC 2606)
LOGGERS = ("svc_files", "uvicorn", "uvicorn.error", "uvicorn.access")

ROOT = pathlib.Path(__file__).resolve().parents[3]
GATEWAY = ROOT / "platform" / "apisix" / "config.yaml"
NGINX = ROOT / "apps" / "office" / "nginx" / "default.conf.template"
# Định dạng trước F4.4: mặc định của APISIX 3.18 (nginx_config.http.access_log_format) và log_format "main" của image
# nginx-unprivileged 1.30.6. F4.4 chỉ đổi phần mang chuỗi truy vấn, bỏ Referer; các trường khác giữ nguyên.
APISIX_DEFAULT = ('$remote_addr - $remote_user [$time_local] $http_host "$request" $status $body_bytes_sent '
                  '$request_time "$http_referer" "$http_user_agent" $upstream_addr $upstream_status '
                  '$upstream_response_time "$upstream_scheme://$upstream_host$upstream_uri"')
NGINX_MAIN = ('$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" '
              '"$http_user_agent" "$http_x_forwarded_for"')
# Biến nginx mang chuỗi truy vấn (đã mã hóa phần trăm: regex che không thấy) hoặc Referer
LEAKY = {"request", "request_uri", "args", "query_string", "is_args", "http_referer", "upstream_uri", "request_body"}
URIS = ("/api/search?q=0912%20345%20678", "/tim-kiem?q=001205000017&trang=2", "/hoi-dap?q=a?b",
        "/realms/moc/protocol/openid-connect/auth?code=abc&state=xyz", "/api/files/7b1d2c3e", "/healthz", "/", "")


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
def test_create_app_masks_service_and_uvicorn_lines(handler_first, settings, scanner, store, verifier, hasura, meili,
                                                    vault, capsys):
    with bare_loggers():
        uvicorn_logging()
        log = logging.getLogger("svc_files")
        if handler_first:       # như fixture log_records đứng trước client: _setup_logging không thêm handler nào
            log.addHandler(logging.StreamHandler(sys.stderr))
            log.setLevel(logging.INFO)
        for _ in range(2):      # dựng app lần nữa (test, nhiều worker): vẫn một bộ lọc ở mỗi chỗ
            create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                       vault=vault)
        for name in LOGGERS:
            logger = logging.getLogger(name)
            for where in (logger, *logger.handlers):
                access = [f.access for f in where.filters if isinstance(f, PiiFilter)]
                assert access == [name == "uvicorn.access"], (name, where)

        # đúng lời gọi của uvicorn khi trả xong một yêu cầu (protocols/http/h11_impl.py)
        path = get_path_with_query_string({"path": "/api/search", "query_string": f"q={PHONE}".encode()})
        logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "172.18.0.5:51234", "GET", path, "1.1",
                                                 200)
        try:
            raise ValueError(f"không gửi được tới {EMAIL}")
        except ValueError as exc:
            logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=exc)
        log.info(json.dumps({"event": "core.thu", "cccd": CCCD}, ensure_ascii=False))
        out, err = capsys.readouterr()

    assert '172.18.0.5:51234 - "GET /api/search?… HTTP/1.1" 200' in out and "q=" not in out
    assert "Exception in ASGI application" in err and "Traceback" in err
    assert "ValueError: không gửi được tới [EMAIL]" in err
    assert '{"event": "core.thu", "cccd": "[CCCD]"}' in err
    for value in (PHONE, CCCD, EMAIL):
        assert value not in out + err


def test_rejected_file_name_is_masked_in_the_log_but_kept_in_the_audit_ledger(client, make_token, hasura,
                                                                               log_records):
    # log_records đứng sau client: handler của nó gắn sau create_app, vẫn nhận bản đã che (bộ lọc ở mức logger)
    r = client.post("/api/files", headers={"Authorization": f"Bearer {make_token(sub='u-1')}"},
                    files={"file": (f"don-{PHONE}.txt", EICAR)})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "infected"

    (line,) = [x for x in log_records if x["event"] == "core.file.rejected"]
    assert line["filename"] == "don-[SĐT].txt"
    # phần còn lại của dòng không bị che nhầm
    assert line["sha256"] == hashlib.sha256(EICAR).hexdigest() and line["size_bytes"] == len(EICAR)
    assert line["signature"] == "Eicar-Test-Signature" and line["actor_id"] == "u-1"
    assert PHONE not in json.dumps(log_records, ensure_ascii=False)
    # sổ kiểm toán không che: có phân quyền, có chuỗi băm, tên gốc là chứng cứ
    (event,) = hasura.events
    assert event["action"] == "file.rejected" and event["details"]["filename"] == f"don-{PHONE}.txt"


# ---- định dạng nhật ký truy cập của APISIX và nginx (app-office) ------------------------------------------------

def without_query(fmt: str) -> str:
    """Định dạng mặc định → định dạng F4.4: "$request" thành phương thức, đường dẫn bỏ truy vấn, giao thức;
    $upstream_uri thành bản bỏ truy vấn; bỏ Referer."""
    return (fmt.replace('"$request"', '"$request_method $moc_duong_dan $server_protocol"')
            .replace(' "$http_referer"', "").replace("$upstream_uri", "$moc_duong_dan_upstream"))


def variables(fmt: str) -> set[str]:
    return set(re.findall(r"\$(\w+)", fmt))


def strips_query(text: str, target: str, source: str) -> None:
    """``map $source $target { "~regex" $nhóm; }`` có trong ``text``, và regex (chạy bằng re của Python) cho đúng phần
    trước dấu ? đầu tiên với mọi URI mẫu."""
    found = re.findall(rf'map \${source} \${target} \{{\s*"~([^"]+)" \$(\w+);\s*\}}', text)
    assert len(found) == 1, f"thiếu map ${source} → ${target}"
    (regex, group), = found
    pattern = re.compile(regex.replace("(?<", "(?P<"))      # nhóm đặt tên của PCRE → cú pháp re
    assert group in pattern.groupindex, f"${group} không phải nhóm khớp của {regex}"
    for uri in URIS:
        m = pattern.match(uri)
        assert m is not None and m.group(group) == uri.split("?", 1)[0], uri


@pytest.mark.skipif(not GATEWAY.is_file(), reason="không có platform/apisix/ (chạy trong image)")
def test_apisix_access_log_has_no_query_string_or_referer():
    lines = GATEWAY.read_text(encoding="utf-8").splitlines()

    def parent(i: int, indent: int) -> str:
        """Khóa YAML gần nhất phía trên dòng i có đúng ``indent`` dấu cách (bỏ chú thích)."""
        return next(x for x in reversed(lines[:i]) if re.match(rf" {{{indent}}}[^ #]", x))

    (i,) = [n for n, x in enumerate(lines) if x.lstrip().startswith("access_log_format:")]
    # APISIX bọc chuỗi này trong '…' khi dựng nginx.conf: một dòng, không có dấu nháy đơn bên trong
    m = re.fullmatch(r"    access_log_format: '([^']*)'", lines[i])
    assert m and parent(i, 2) == "  http:" and parent(i, 0) == "nginx_config:"
    fmt = m.group(1)
    assert fmt == without_query(APISIX_DEFAULT)
    assert not variables(fmt) & LEAKY

    (j,) = [n for n, x in enumerate(lines) if x.lstrip().startswith("http_configuration_snippet:")]
    assert lines[j] == "  http_configuration_snippet: |" and parent(j, 0) == "nginx_config:"
    block = []
    for x in lines[j + 1:]:
        if x and not x.startswith("    "):
            break
        block.append(x)
    snippet = "\n".join(block)
    strips_query(snippet, "moc_duong_dan", "request_uri")
    strips_query(snippet, "moc_duong_dan_upstream", "upstream_uri")


@pytest.mark.skipif(not NGINX.is_file(), reason="không có apps/office (chạy trong image)")
def test_office_nginx_access_log_has_no_query_string_or_referer():
    text = NGINX.read_text(encoding="utf-8")
    head, server = text.split("\nserver {", 1)      # map, log_format ở ngữ cảnh http: trước khối server
    m = re.search(r"^log_format moc_khong_truy_van ((?:'[^']*'\s*)+);", head, re.M)
    assert m, "thiếu log_format moc_khong_truy_van"
    fmt = "".join(re.findall(r"'([^']*)'", m.group(1)))
    assert fmt == without_query(NGINX_MAIN)
    assert not variables(fmt) & LEAKY
    assert re.search(r"^    access_log /var/log/nginx/access\.log moc_khong_truy_van;$", server, re.M)
    strips_query(head, "moc_duong_dan", "request_uri")
    # envsubst của image thay mọi biến môi trường có trong container (chữ hoa): biến nginx phải là chữ thường
    assert {v for v in re.findall(r"\$\{?(\w+)", text) if not v.islower()} == {"MOC_REALM"}
