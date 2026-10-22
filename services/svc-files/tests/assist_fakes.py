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

"""Đồ giả cho test trợ lý hỏi đáp (F4.2, luồng C): Retriever giả có hậu kiểm theo người đọc, vòng chỉ mục giả, Hasura
vai trò agent ghi được ``assistant.answered``, Ollama giả qua MockTransport (``/api/tags``, ``/api/embed``,
``/api/chat``). Không đụng ``conftest.py`` (luồng B)."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx2
import jwt

from conftest import ISSUER, TENANT_A, FakeHasura
from svc_files.auth import HASURA_CLAIMS
from svc_files.assist.ai import OllamaAi
from svc_files.assist.retrieve import Passage, Retrieval
from svc_files.hasura import HasuraError

CHAT_MODEL = "qwen3:1.7b"
EMBED_MODEL = "qwen3-embedding:0.6b"
DIMS = 8                     # số chiều nhỏ cho test (MOC_AI_EMBED_DIMS)

# Trang 1 của công văn 88/CTSV như lớp chữ PDF đọc ra (WeasyPrint + pypdf, có ngắt dòng do dàn trang)
PAGE_88 = (
    "TRƯỜNG ĐẠI HỌC THỬ\nPHÒNG CÔNG TÁC SINH VIÊN\nSố: 88/CTSV\nV/v xét cấp học bổng khuyến khích\nhọc tập học kỳ I "
    "năm học 2026–2027\nCỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\nHà Nội, ngày 15 tháng 10 năm "
    "2026\nKính gửi: Khoa Công nghệ thông tin\nCăn cứ Quy định về học bổng khuyến khích học tập của Trường, Phòng Công "
    "tác\nsinh viên đề nghị Khoa xét chọn sinh viên có điểm trung bình chung học kỳ từ 3,2 trở\nlên và điểm rèn luyện "
    "đạt loại Tốt.\nBiên bản họp xét của Khoa và danh sách đề nghị gửi về Phòng trước ngày\n15/11/2026.\n"
    "Trân trọng./.\nTRƯỞNG PHÒNG\n(Đã ký)\nVăn bản giả lập để chạy thử Mộc, không phải văn bản thật."
)
DOC_88 = {"direction": "in", "status": "in_progress", "type_code": "CV", "type_name": "Công văn", "symbol": "88/CTSV",
          "issuer_name": "Phòng Công tác sinh viên", "issued_on": "2026-10-15",
          "summary": "Về việc xét cấp học bổng khuyến khích học tập học kỳ I năm học 2026–2027"}
QUESTION = "Điều kiện xét học bổng khuyến khích học tập là gì?"
QUOTE = ("Căn cứ Quy định về học bổng khuyến khích học tập của Trường, Phòng Công tác sinh viên đề nghị Khoa xét chọn "
         "sinh viên có điểm trung bình chung học kỳ từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt.")


def passage(text: str, *, document_id: str | None = None, page: int | None = 1, kind: str = "page",
            seq: int = 1, file_role: str | None = "main", score: float = 0.9, **doc: Any) -> Passage:
    doc_id = document_id or str(uuid.uuid4())
    file_id = None if kind == "meta" else str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))
    chunk = f"{doc_id}_meta" if kind == "meta" else f"{doc_id}_{file_id}_{page or 0:03d}_{seq:02d}"
    return Passage(chunk, doc_id, kind, file_id, None if kind == "meta" else file_role,  # type: ignore[arg-type]
                   None if kind == "meta" else page, text, score, {"id": doc_id, **DOC_88, **doc})


def ask_token(signing_key, *, sub: str = "u-van-thu", role: str = "clerk", department: str | None = None,
              tenant: str = str(TENANT_A), default_role: bool = True) -> str:
    """Token như Keycloak của Signet: một vai trò cho cả allowed-roles và default-role, kèm phòng nếu có."""
    now = int(time.time())
    ns: dict[str, Any] = {"x-hasura-user-id": sub, "x-hasura-allowed-roles": [role], "x-hasura-tenant-id": tenant}
    if default_role:
        ns["x-hasura-default-role"] = role
    if department:
        ns["x-hasura-department-id"] = department
    claims = {"iss": ISSUER, "sub": sub, "iat": now, "exp": now + 300, HASURA_CLAIMS: ns}
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test"})


@dataclass
class FakeRetriever:
    """Retriever giả: ``passages`` theo thứ tự xếp hạng của Meilisearch; hậu kiểm như Hasura với token người hỏi —
    văn bản có ``readers`` chỉ người trong đó đọc được, văn bản ``restricted`` không ai nhận. ``hybrid_error``: tìm
    lai lỗi, đã tìm lại chỉ bằng từ khóa (như Retriever khi embedder chưa có trong Meilisearch)."""

    passages: list[Passage] = field(default_factory=list)
    readers: dict[str, set[str]] = field(default_factory=dict)
    restricted: set[str] = field(default_factory=set)
    calls: list[dict[str, Any]] = field(default_factory=list)
    fail: Exception | None = None
    hybrid_error: str | None = None

    async def search(self, scope, *, q, vector, limit=5, filters=None) -> Retrieval:
        self.calls.append({"scope": scope, "q": q, "vector": vector, "limit": limit, "filters": filters})
        if self.fail is not None:
            raise self.fail
        ns = jwt.decode(scope.token, options={"verify_signature": False})[HASURA_CLAIMS] if scope.token else {}
        sub = ns.get("x-hasura-user-id")
        visible = [p for p in self.passages if p.document_id not in self.restricted
                   and (p.document_id not in self.readers or sub in self.readers[p.document_id])]
        if vector is not None and self.hybrid_error:
            return Retrieval(visible[:limit], len(self.passages), False, self.hybrid_error)
        return Retrieval(visible[:limit], len(self.passages), vector is not None)


class FakeIndexer:
    """Vòng nền giả: chỉ ghi lại các lần ``hold`` của lượt hỏi."""

    def __init__(self, embedder: str | None = None) -> None:
        self.ready = True
        self.embedder = embedder
        self.embedder_ready = True
        self.embed_pending: int | None = None
        self.embed_failed: int | None = None
        self.holds: list[float] = []

    def hold(self, seconds: float) -> None:
        self.holds.append(seconds)

    async def run(self) -> None:
        return None


class AskHasura(FakeHasura):
    """FakeHasura (conftest) + quyền insert ``core_audit_log`` của vai trò agent như metadata của luồng A: cặp
    ``assistant.answered`` / ``ai.questions``, preset ``actor_id``, ``actor_kind``, thuê ước."""

    ASSISTANT_AUDIT_COLUMNS = {"request_id", "action", "entity", "entity_id", "diff"}
    ALLOWED = {("intake.suggested", "core.files"), ("assistant.answered", "ai.questions")}

    async def as_role(self, role: str, tenant_id, user_id: str, request_id: str, query: str, variables: dict) -> dict:
        name = re.search(r"(?:query|mutation)\s+(\w+)", query).group(1)
        if name != "GhiSoTroLy":
            return await super().as_role(role, tenant_id, user_id, request_id, query, variables)
        self._check()
        self.agent_calls.append({"role": role, "tenant_id": str(tenant_id), "user_id": user_id,
                                 "request_id": request_id, "op": name})
        if self.fail_agent:
            raise HasuraError("không ghi được")
        if role != "agent":
            raise HasuraError("vai trò không có quyền", "validation-failed")
        event = variables["e"]
        if set(event) - self.ASSISTANT_AUDIT_COLUMNS:
            raise HasuraError("cột không được phép", "validation-failed")
        if (event["action"], event["entity"]) not in self.ALLOWED:
            raise HasuraError("check constraint of an insert permission has failed", "permission-error")
        self.agent_events.append({**event, "tenant_id": str(tenant_id), "actor_id": user_id, "actor_kind": "agent"})
        return {"insert_core_audit_log": {"affected_rows": 1}}


def good_answer(text: str = "Sinh viên cần điểm trung bình chung học kỳ từ 3,2 trở lên và điểm rèn luyện đạt "
                            "loại Tốt [1].") -> str:
    return json.dumps({"du_can_cu": True, "tra_loi": text}, ensure_ascii=False)


class FakeOllama:
    """Ollama giả cho trợ lý: ``/api/tags`` liệt kê ``models``; ``/api/embed`` trả véc-tơ ``dims`` chiều (hoặc
    ``embed_reply``); ``/api/chat`` trả ``reply`` (chuỗi, hoặc hàm async nhận yêu cầu)."""

    def __init__(self, *, models=(CHAT_MODEL, EMBED_MODEL), reply=None, dims: int = DIMS, embed_reply=None,
                 embed_status: int = 200, chat_status: int = 200, embed_sleep_s: float = 0.0) -> None:
        self.models = list(models)
        self.reply = reply if reply is not None else good_answer()
        self.dims = dims
        self.embed_reply = embed_reply
        self.embed_status = embed_status
        self.chat_status = chat_status
        self.embed_sleep_s = embed_sleep_s
        self.requests: list[httpx2.Request] = []

    def calls(self, path: str) -> list[dict]:
        return [json.loads(r.content) if r.content else {} for r in self.requests if r.url.path == path]

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/tags":
            return httpx2.Response(200, json={"models": [{"name": m, "model": m} for m in self.models]})
        if path == "/api/generate":
            return httpx2.Response(200, json={"model": CHAT_MODEL, "done": True})
        if path == "/api/embed":
            if self.embed_sleep_s:
                await asyncio.sleep(self.embed_sleep_s)
            body = json.loads(request.content)
            count = len(body["input"]) if isinstance(body["input"], list) else 1
            data = self.embed_reply if self.embed_reply is not None else {
                "model": body["model"], "embeddings": [[0.1 * (i + 1)] * self.dims for i in range(count)]}
            return httpx2.Response(self.embed_status, json=data)
        reply = self.reply
        if callable(reply):
            reply = await reply(request)
            if isinstance(reply, httpx2.Response):
                return reply
        return httpx2.Response(self.chat_status, json={"model": CHAT_MODEL, "done": True,
                                                       "message": {"role": "assistant", "content": reply}})


def ollama(fake: FakeOllama, *, chat: str | None = CHAT_MODEL, embed: str | None = EMBED_MODEL, dims: int = DIMS,
           probe: bool = True) -> OllamaAi:
    """OllamaAi nối vào Ollama giả; ``probe``: dò một lượt trước (như vòng nền lúc khởi động)."""
    ai = OllamaAi("http://ollama:11434", chat, embed, transport=httpx2.MockTransport(fake), dims=dims)
    if probe:
        asyncio.run(ai.probe())
    return ai
