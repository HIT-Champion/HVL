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

"""Mảnh dùng chung của các route HTTP trong app.py và office/: câu lỗi, nhật ký theo mã yêu cầu, đầu đề trả tệp.

Tách khỏi app.py để route của Văn phòng (office/api.py) dùng chung mà không nhập app.py (docs/architecture.md §4.7).
"""

from __future__ import annotations

import json
import logging
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import Response

from . import filetype

CHUNK_SIZE = 64 * 1024
# Văn bản hạn chế (F3.7): chờ lượt kiểm / đóng dấu PDF (cả lượt bỏ siêu dữ liệu ảnh) quá chừng này thì 503 busy
SEALING_QUEUE_S = 10.0
RETRY_AFTER = "10"
NO_STORE = {"Cache-Control": "no-store"}

log = logging.getLogger("svc_files")


def content_disposition(filename: str, *, inline: bool = False) -> str:
    """Tải về (attachment), kèm tên ASCII cho trình duyệt cũ và tên UTF-8 đầy đủ (RFC 6266). ``inline`` chỉ cho bản PDF
    đã đóng dấu người xem của phòng đọc (F3.8)."""
    fallback = filetype.ascii_name(filename)       # tải lên đã chặn tên mà bản ASCII có đuôi chạy được
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{fallback or 'tep'}\"; filename*=UTF-8''{quote(filename, safe='')}"


# Tệp người dùng tải lên có thể là HTML hay SVG chứa script: không bao giờ để trình duyệt hiển thị nó
# như một trang của Signet. Giao diện lấy tệp bằng fetch kèm token rồi lưu về máy, không cần hiển thị inline.
DOWNLOAD_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}


def error(status: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def log_event(event: str, request: Request, *, level: int = logging.INFO, **fields: object) -> None:
    log_rid(event, request.state.request_id, level=level, **fields)


def log_rid(event: str, rid: str, *, level: int = logging.INFO, **fields: object) -> None:
    """Như log_event, cho việc không gắn với một yêu cầu HTTP (vòng nền của lô nạp: mã yêu cầu là `<lô>:<dòng>`)."""
    record = {"event": event, "request_id": rid, **fields}
    log.log(level, json.dumps(record, ensure_ascii=False, default=str))


# Chứng thư CA nội bộ (F4.5, route của Văn phòng) và khóa công khai ký mốc neo sổ kiểm toán (lõi): tệp công khai đọc
# từ két, để người ngoài tự kiểm chữ ký số văn bản và mốc neo đã chép ra ngoài (docs/van-hanh.md mục Mốc neo công
# khai). Két chưa có PKI, chưa có khóa (két khởi tạo trước khi có chúng) thì 404; két không trả lời thì 503
PEM_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"content": {"application/x-pem-file": {}}, "description": "Tệp PEM"},
    404: {"description": "Két chưa có (két khởi tạo trước khi có tính năng này, hoặc không dùng két)"},
    429: {"description": "Vượt giới hạn tra cứu theo địa chỉ IP (APISIX)"},
    503: {"description": "Két không trả lời"},
}


def pem_response(text: str, filename: str) -> Response:
    return Response(text, media_type="application/x-pem-file", headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=300",
        "Content-Disposition": content_disposition(filename)})
