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

"""Route ``POST /api/files/{file_id}/read`` — đọc văn bản đến, gợi ý thông tin tiếp nhận (F4.1).

Đi qua route ``/api/files/*`` sẵn có của APISIX (token người dùng), không qua Hasura action: byte tệp chỉ có ở
svc-files. Đồng bộ, hạn tổng ``MOC_READ_DEADLINE_S`` (< 60 giây mặc định của APISIX). Luồng đọc ở reader.py.
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu của dependency khai báo trong install().
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth import Principal
from .reader import Reader, ReadError

FieldKey = Literal["type_code", "symbol", "issued_on", "issuer_name", "summary", "urgency"]


class ReadField(BaseModel):
    value: str = Field(description="issued_on: ngày ISO; urgency: normal | khan | thuong_khan | hoa_toc; type_code: "
                                   "mã trong danh mục loại văn bản")
    confidence: Literal["high", "medium", "low"] = Field(
        description="high, medium: giao diện điền sẵn; low: chỉ hiện gợi ý, văn thư bấm Dùng")
    source: Literal["rule", "model"] = Field(description="rule: quy tắc; model: mô hình ngôn ngữ (chỉ trích yếu)")


class ReadOut(BaseModel):
    file_id: uuid.UUID
    status: Literal["ok", "empty"] = Field(description="ok: tìm được ít nhất một trường; empty: đọc được mà không ra "
                                                       "trường nào")
    method: Literal["text", "ocr"] = Field(description="text: lớp chữ của PDF; ocr: nhận dạng chữ bản scan, ảnh")
    pages: int = Field(description="Số trang của tệp")
    fields: dict[FieldKey, ReadField] = Field(description="Chỉ có khóa đã tìm thấy")
    warnings: list[str] = Field(description=(
        "Mã cố định: future_date, invalid_date, symbol_no_number, type_conflict, low_text, truncated, "
        "model_unavailable, model_timeout, model_rejected, model_skipped"))
    summary_source: Literal["rule", "model", "none"]
    model: str | None = Field(description="Mô hình ngôn ngữ đã gọi; null nếu không gọi")
    duration_ms: int
    cached: bool = Field(description="true: gợi ý đã lưu từ lần đọc trước (không đọc lại, không ghi sổ)")
    read_at: datetime


READ_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"description": "Thiếu hoặc sai token (`missing_token`, `invalid_token`)"},
    403: {"description": "`forbidden` — không phải văn thư"},
    404: {"description": "`not_found` — không có tệp, không xem được, không do người gọi tải lên, hoặc không còn trong "
                          "kho"},
    409: {"description": "`restricted` — tệp của văn bản hạn chế: không đọc (kiểm trước khi đọc byte)"},
    413: {"description": "`too_large` — tệp lớn hơn `MOC_READ_MAX_MB`"},
    415: {"description": "`unsupported` — byte đầu không phải PDF, JPEG, PNG, TIFF (không tin mime khai)"},
    422: {"description": "`unreadable` kèm `reason`: password, corrupt, no_text, timeout, memory, too_many_pixels — "
                          "đã ghi `intake.suggested` (status unreadable) vào sổ kiểm toán"},
    503: {"description": "`busy` (kèm `Retry-After: 10`) chờ lượt quá `MOC_READ_QUEUE_S` · `reader_disabled` · "
                          "`ocr_unavailable` · `storage_unavailable` · `database_unavailable` — gồm cả khi chưa ghi "
                          "được sổ kiểm toán: không ghi được sổ thì không trả gợi ý"},
}

NO_STORE = {"Cache-Control": "no-store"}


def install(app: FastAPI, reader: Reader, principal: Callable[..., Principal]) -> None:
    """Gắn route đọc văn bản đến vào app; ``principal``: dependency kiểm token người dùng của app.py."""

    @app.post(
        "/api/files/{file_id}/read",
        response_model=ReadOut,
        responses=READ_RESPONSES,
        summary="Đọc văn bản đến vừa tải lên (lớp chữ PDF hoặc OCR), gợi ý thông tin tiếp nhận",
        description=(
            "Chỉ văn thư, chỉ tệp chính mình tải lên. Tác tử `moc-doc-reader` đọc tệp, quy tắc tìm số ký hiệu, ngày "
            "ban hành, cơ quan ban hành, loại, độ khẩn, trích yếu; có mô hình ngôn ngữ thì mô hình chỉ viết trích "
            "yếu. Mỗi lần đọc thật ghi một dòng `intake.suggested` vào sổ kiểm toán (chỉ siêu dữ liệu, không có nội "
            "dung văn bản) cùng giao dịch lưu gợi ý. Đã có gợi ý thì trả luôn (`cached`), trừ khi `force=true`. "
            "Không tạo văn bản: văn thư đối chiếu, sửa rồi mới lưu."
        ),
    )
    async def read_file(
        file_id: uuid.UUID,
        request: Request,
        who: Annotated[Principal, Depends(principal)],
        force: Annotated[bool, Query(description="true: đọc lại dù đã có gợi ý lưu (nút Đọc lại)")] = False,
    ) -> JSONResponse:
        try:
            out = await reader.read(who, file_id, force, request.state.request_id)
        except ReadError as exc:
            detail: dict[str, object] = {"code": exc.code, "message": exc.message}
            if exc.reason:
                detail["reason"] = exc.reason
            raise HTTPException(exc.status, detail, exc.headers) from exc
        return JSONResponse(ReadOut.model_validate(out).model_dump(mode="json"), headers=NO_STORE)
