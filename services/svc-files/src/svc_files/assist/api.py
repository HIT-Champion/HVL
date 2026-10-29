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

"""Route ``POST /api/documents/ask`` — hỏi đáp trên kho văn bản (F4.2).

Đi qua route ``/api/documents/*`` sẵn có của APISIX (token người dùng), không thêm route gateway. Đồng bộ, hạn tổng
``MOC_ASK_DEADLINE_S`` (< 60 giây mặc định của APISIX). Luồng trả lời ở answer.py.

Người hỏi ngắt kết nối (nút "Dừng", Esc, đóng trang) thì lượt hỏi bị hủy: Starlette không tự hủy endpoint (app.py
dùng ``@app.middleware("http")``), nên route tự theo dõi kết nối song song với lượt hỏi.
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu của dependency khai báo trong install().
import asyncio
import uuid
from collections.abc import Callable, Coroutine
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from .answer import Assistant, AskError

# Thân yêu cầu dài hơn thế này là sai kiểu (422); 501–2 000 ký tự vẫn tới được bước kiểm câu hỏi (400 invalid_question)
MAX_BODY_QUESTION = 2000


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(max_length=MAX_BODY_QUESTION, description="Câu hỏi, tối đa 500 ký tự sau chuẩn hóa",
                          examples=["Điều kiện xét học bổng khuyến khích học tập là gì?"])
    mode: Literal["extract", "generate"] = Field(
        "extract", description="extract: chỉ câu trích nguyên văn (dưới 1 giây) · generate: thêm câu trả lời do mô "
                               "hình viết (15–40 giây, chỉ khi `ai_available`)")
    direction: Literal["in", "out"] | None = Field(None, description="Chỉ văn bản đến (in) hoặc văn bản đi (out)")
    year: int | None = Field(None, ge=2000, le=2100, description="Năm ban hành")
    type_code: str | None = Field(None, pattern=r'^[^\s/"\\-]{1,10}$', description="Mã loại văn bản, vd CV")
    document_id: uuid.UUID | None = Field(
        None, description="Chỉ hỏi trong một văn bản (nút \"Hỏi về văn bản này\"). Chỉ thu hẹp phạm vi: văn bản người "
                          "hỏi không được xem, văn bản hạn chế hay không có thì trả `no_evidence` như mọi lượt")
    ask_id: uuid.UUID | None = Field(None, description="Gửi lại `ask_id` của lượt extract ở lượt generate: hai dòng "
                                                       "sổ kiểm toán cùng một câu hỏi")
    previous: str | None = Field(
        None, max_length=MAX_BODY_QUESTION,
        description="Câu hỏi của lượt ngay trước trong cùng phạm vi (`rewritten` của lượt đó nếu có), để hiểu câu nối "
                    "tiếp như \"Còn khoa Kinh tế thì sao?\". Máy chủ không lưu; sai dạng thì bị bỏ qua",
        examples=["Điều kiện xét học bổng khoa CNTT là gì?"])


class AskAnswer(BaseModel):
    text: str = Field(description="Chữ thuần; mỗi ý kèm [n] trỏ tới `sources[n-1]`. Giao diện hiển thị như chữ, "
                                  "không như HTML")
    source: Literal["extract", "model", "fixed", "data"] = Field(
        description="extract: câu trích nguyên văn · model: mô hình viết, máy chủ kiểm và gán [n] theo bằng chứng · "
                    "fixed: câu cố định cho câu hỏi ngoài phạm vi · data: câu có số từ dữ liệu của người hỏi")
    model: str | None = Field(description="Mô hình đã viết câu trả lời; null với câu trích")


class AskSource(BaseModel):
    n: int = Field(description="Số trong dấu [n], từ 1")
    document_id: uuid.UUID | None = Field(description="null với nguồn `guide`")
    symbol: str | None
    type_code: str | None
    type_name: str | None
    summary: str
    issuer_name: str | None
    issued_on: date | None
    direction: Literal["in", "out"] | None
    status: str | None
    kind: Literal["page", "meta", "guide"] = Field(
        description="page: đoạn chữ của tệp · meta: chỉ có trích yếu (bản scan, chưa có tệp, tệp không đọc được chữ) · "
                    "guide: mục của hướng dẫn sử dụng hay của Giới thiệu trợ lý; `symbol` là tên tài liệu, `summary` "
                    "là tiêu đề mục")
    file_id: uuid.UUID | None
    file_role: Literal["main", "attachment", "issued"] | None = Field(
        description="main: bản chính · attachment: tài liệu kèm theo · issued: bản phát hành văn bản đi")
    page: int | None = Field(description="Trang trong tệp; null với đoạn meta hoặc chữ chưa có ranh giới trang")
    excerpt: str = Field(description="Đoạn trích ≤ 600 ký tự quanh câu khớp nhất")
    cited: bool = Field(description="Câu trả lời có trích nguồn này")
    path: str | None = Field(None, description="Chỉ nguồn `guide`: tệp trong repo kèm neo mục, vd "
                                               "`docs/huong-dan/viec-chung.md#đơn-nghỉ-phép`")


class AskOut(BaseModel):
    ask_id: uuid.UUID
    status: Literal["answered", "passages_only", "no_evidence"] = Field(
        description="answered: có câu trả lời · passages_only: có đoạn liên quan, chưa trích được câu trả lời ngắn · "
                    "no_evidence: không có văn bản nào người hỏi được xem có nội dung này")
    answer: AskAnswer | None = Field(
        description="Câu trả lời của mô hình nếu đạt, không thì câu trích; null khi không có")
    extract: AskAnswer | None = Field(description="Câu trích nguyên văn; null khi không câu nào đạt")
    sources: list[AskSource] = Field(description="Theo thứ tự xếp hạng, tối đa `MOC_ASK_TOP_K`; [] khi no_evidence")
    semantic: bool = Field(description="Lượt này có tìm theo nghĩa (mô hình nhúng)")
    ai_available: bool = Field(description="Mô hình viết câu trả lời đang sẵn sàng (gọi lại với mode=generate)")
    warnings: list[Literal["embed_unavailable", "model_unavailable", "model_timeout", "model_rejected",
                           "model_declined"]]
    duration_ms: int
    route: Literal["van_ban", "gioi_thieu", "huong_dan", "ngoai_pham_vi", "viec_cua_toi", "dem_van_ban"] = Field(
        description="Đường bộ định tuyến đã chọn: van_ban: tìm trong kho văn bản · gioi_thieu: câu về chính trợ lý, "
                    "câu chào · huong_dan: cách dùng Signet, trả lời từ hướng dẫn sử dụng · ngoai_pham_vi: câu cố "
                    "định, không tìm · viec_cua_toi: đếm việc trong Hộp việc của người hỏi · dem_van_ban: đếm văn bản "
                    "người hỏi được xem. Trừ van_ban, huong_dan, các đường không gọi mô hình, cả khi mode=generate")
    route_reason: str = Field(description="Mã lý do, máy đọc: `kw:<mẫu>` (mẫu đã khớp) hoặc `mac-dinh`",
                              examples=["kw:lam-duoc-gi"])
    rewritten: str | None = Field(description="Câu nối tiếp đã ghép với `previous` thành câu độc lập — câu đem đi tìm. "
                                              "null khi không phải câu nối tiếp")
    data: dict[str, Any] | None = Field(
        default=None,
        description="Đường viec_cua_toi, dem_van_ban: các số và bộ lọc của câu trả lời `source: data`, máy đọc. "
                    "viec_cua_toi: `{kind: tasks, on, tasks, overdue, today, soon, no_due}` · dem_van_ban: `{kind: "
                    "documents, counts: {in?, out?}, type_code, from, to}` (`to` là ngày sau ngày cuối; null: không "
                    "lọc theo ngày). null với đường khác",
        examples=[{"kind": "documents", "counts": {"in": 12}, "type_code": None, "from": "2026-10-01",
                   "to": "2026-11-01"}])
    link: str | None = Field(
        default=None, description="Trang trong Signet xem danh sách đã đếm: `/` (Hộp việc, Lịch hạn), `/van-ban-den`, "
                                  "`/van-ban-di`; null khi không có trang nào hợp", examples=["/van-ban-den"])


ASK_RESPONSES: dict[int | str, dict[str, object]] = {
    400: {"description": "`invalid_question` — rỗng sau chuẩn hóa, quá 500 ký tự, có ký tự điều khiển, hoặc chỉ toàn "
                          "từ dừng"},
    401: {"description": "`missing_token`, `invalid_token` (cả khi Hasura từ chối token lúc hậu kiểm)"},
    403: {"description": "`forbidden` — vai trò không phải văn thư, lãnh đạo, trưởng phòng, chuyên viên"},
    503: {"description": "`assistant_disabled` · `busy` (kèm `Retry-After: 10`, chờ lượt sinh quá `MOC_ASK_QUEUE_S`) "
                          "· `search_unavailable` · `database_unavailable` — gồm cả khi chưa ghi được sổ kiểm toán: "
                          "không ghi được sổ thì không trả lời"},
}

NO_STORE = {"Cache-Control": "no-store"}
GONE = 499                  # người hỏi đã ngắt kết nối (như nginx): không còn ai nhận thân trả về


async def _gone(request: Request) -> None:
    """Về khi người hỏi ngắt kết nối. FastAPI đã đọc hết thân yêu cầu nên tin kế tiếp chỉ còn ``http.disconnect``:
    khi client đóng kết nối, hoặc (qua BaseHTTPMiddleware, TestClient) khi đã gửi xong câu trả lời."""
    while (await request.receive())["type"] != "http.disconnect":
        pass


async def until_gone[T](request: Request, work: Coroutine[Any, Any, T]) -> T | None:
    """Chạy ``work``; người hỏi ngắt kết nối trước khi xong thì hủy nó — lời gọi Ollama bị ngắt, lượt sinh được nhả —
    và trả None. Lỗi của ``work`` (AskError…) đi lên như thường."""
    task = asyncio.ensure_future(work)
    watch = asyncio.ensure_future(_gone(request))
    try:
        await asyncio.wait((task, watch), return_when=asyncio.FIRST_COMPLETED)
        if not task.done() and watch.exception() is not None:
            await asyncio.wait((task,))         # không theo dõi được kết nối: chờ lượt hỏi như cũ
    finally:
        task.cancel()                           # đã xong thì không có tác dụng
        watch.cancel()
        await asyncio.gather(task, watch, return_exceptions=True)
    return None if task.cancelled() else task.result()


def install(app: FastAPI, assistant: Assistant, principal: Callable[..., Principal]) -> None:
    """Gắn route hỏi đáp vào app; ``principal``: dependency kiểm token người dùng của app.py."""

    @app.post(
        "/api/documents/ask",
        response_model=AskOut,
        responses=ASK_RESPONSES,
        summary="Hỏi đáp trên kho văn bản: câu trích nguyên văn có nguồn, tùy chọn câu trả lời do mô hình viết",
        description=(
            "Chỉ tìm trong các văn bản người hỏi được xem (lọc trước theo vai trò trong Meilisearch, hậu kiểm bằng "
            "chính token người hỏi qua Hasura); văn bản hạn chế không bao giờ vào chỉ mục. `extract` trả câu trích "
            "nguyên văn kèm số ký hiệu, trang; `generate` thêm câu trả lời do mô hình chạy tại chỗ viết từ đúng các "
            "đoạn đó, mỗi câu có [n] do máy chủ gán theo bằng chứng. Mỗi lượt ghi một dòng `assistant.answered` của "
            "tác tử `moc-assistant` vào sổ kiểm toán — không có câu hỏi, câu trả lời; không ghi được sổ thì không trả "
            "lời. Người hỏi ngắt kết nối thì lượt bị hủy, không ghi sổ."
        ),
    )
    async def ask(
        body: AskIn,
        request: Request,
        who: Annotated[Principal, Depends(principal)],
    ) -> Response:
        try:
            out = await until_gone(request, assistant.ask(who, body, request.state.request_id))
        except AskError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}, exc.headers) from exc
        if out is None:         # người hỏi đã đi: lượt đã hủy, không ghi sổ
            return Response(status_code=GONE, headers=NO_STORE)
        return JSONResponse(AskOut.model_validate(out).model_dump(mode="json"), headers=NO_STORE)
