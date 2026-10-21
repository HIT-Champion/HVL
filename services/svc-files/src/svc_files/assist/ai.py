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

"""Mô hình chạy tại chỗ cho trợ lý hỏi đáp (F4.2): nhúng (tìm theo nghĩa) và viết câu trả lời — đều tùy chọn.

Ollama ở profile ``ai`` của compose, mạng nội bộ không ra Internet. Không bật profile (CI) thì mọi thứ vẫn chạy: tìm
theo từ khóa, trả câu trích nguyên văn.

- Dò sẵn sàng: ``GET /api/tags`` lúc khởi động và mỗi 60 giây (vòng nền), **mỗi mô hình một trạng thái** (mô hình
  sinh ``MOC_ASK_MODEL``, mô hình nhúng ``MOC_AI_EMBED_MODEL``). Vừa sẵn sàng thì nạp trước, cùng ``num_ctx`` với lần
  gọi thật (khác ``num_ctx`` thì Ollama nạp lại mô hình). Nhật ký chỉ ghi khi đổi trạng thái.
- Nhúng: ``POST /api/embed`` (``truncate``, ``num_ctx`` 2048); câu hỏi (``query=True``) mang tiền tố chỉ dẫn mà
  Qwen3-Embedding cần, đoạn văn bản thì không. Kết quả phải đủ số véc-tơ, đúng ``MOC_AI_EMBED_DIMS`` chiều, toàn số
  hữu hạn — sai thì coi như không nhúng được; lý do lần lỗi gần nhất ở ``embed_error`` để vòng nền phân biệt lỗi tạm
  (``TRANSIENT``: thử lại sau) với đoạn làm mô hình lỗi tất định. Véc-tơ đầu tiên Ollama trả (lúc nạp trước hoặc lần
  nhúng đầu) mà khác ``MOC_AI_EMBED_DIMS`` chiều là sai cấu hình: tắt nhúng tới khi khởi động lại, ghi lỗi rõ.
- Sinh: ``POST /api/chat`` không stream, tắt suy nghĩ, đầu ra ép theo JSON Schema (grounding.py dựng lời dặn và kiểm).
- Không sửa ``docread/summarize.py``: tác tử đọc văn bản đến dò mô hình trích yếu riêng.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import httpx2

from .meili import embedder_name  # tên embedder theo mô hình — luồng B đặt ở meili.py (§4.3)

if TYPE_CHECKING:
    from ..config import Settings

__all__ = ["TRANSIENT", "AiClient", "ChatResult", "NullAi", "OllamaAi", "embedder_name", "make_ai", "query_text"]

log = logging.getLogger("svc_files")

KEEP_ALIVE = "30m"
PROBE_INTERVAL_S = 60.0
PRELOAD_TIMEOUT_S = 120.0       # nạp mô hình từ đĩa trên CPU
EMBED_OPTIONS: dict[str, Any] = {"num_ctx": 2048}
CHAT_PRELOAD_OPTIONS: dict[str, Any] = {"num_ctx": 4096}     # như grounding.OPTIONS, docread/summarize.OPTIONS
QUERY_PREFIX = ("Instruct: Given a question about Vietnamese administrative documents, retrieve passages that "
                "answer the question\nQuery: ")
# lý do nhúng lỗi không do nội dung đưa vào: chưa có mô hình, quá giờ, mất kết nối, Ollama bận / mất mô hình, sai số
# chiều — vòng nền thử lại lượt sau, không đánh dấu đoạn hỏng
TRANSIENT = frozenset({"model_unavailable", "timeout", "unavailable", "dims_mismatch",
                       "http 404", "http 408", "http 429", "http 502", "http 503", "http 504"})


def query_text(model: str | None, question: str) -> str:
    """Câu hỏi đưa đi nhúng: Qwen3-Embedding cần tiền tố chỉ dẫn ở phía câu hỏi; mô hình khác (bge-m3) thì không."""
    if model and model.lower().startswith("qwen3-embedding"):
        return QUERY_PREFIX + question
    return question


@dataclass(frozen=True)
class ChatResult:
    content: str | None         # nội dung trả về của mô hình (chưa kiểm)
    warning: str | None         # model_unavailable · model_timeout · model_rejected (trả về không đúng dạng)


class AiClient(Protocol):
    chat_model: str | None
    embed_model: str | None
    embed_error: str | None     # lý do lần nhúng gần nhất lỗi (None: thành công); đọc ngay sau ``await embed(...)``

    @property
    def chat_available(self) -> bool: ...
    @property
    def embed_available(self) -> bool: ...

    async def embed(self, texts: Sequence[str], *, query: bool, timeout_s: float) -> list[list[float]] | None: ...
    async def chat(self, messages: list[dict[str, str]], *, format: dict[str, Any], options: dict[str, Any],
                   timeout_s: float) -> ChatResult: ...
    async def run(self) -> None: ...        # vòng dò nền (lifespan); không có gì để dò thì về ngay
    async def aclose(self) -> None: ...


class NullAi:
    """``MOC_AI_URL`` rỗng: không có mô hình nào — tìm theo từ khóa, trả câu trích."""

    chat_model: str | None = None
    embed_model: str | None = None
    embed_error: str | None = "model_unavailable"
    chat_available = False
    embed_available = False

    async def embed(self, texts: Sequence[str], *, query: bool, timeout_s: float) -> list[list[float]] | None:
        return None

    async def chat(self, messages: list[dict[str, str]], *, format: dict[str, Any], options: dict[str, Any],
                   timeout_s: float) -> ChatResult:
        return ChatResult(None, "model_unavailable")

    async def run(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


def _vectors(data: object, count: int, dims: int) -> list[list[float]] | None:
    """Véc-tơ từ thân trả về của ``/api/embed`` nếu đủ ``count`` véc-tơ, mỗi véc-tơ ``dims`` số hữu hạn."""
    rows = data.get("embeddings") if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) != count:
        return None
    out: list[list[float]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != dims:
            return None
        if not all(isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x) for x in row):
            return None
        out.append([float(x) for x in row])
    return out


class OllamaAi:
    def __init__(self, url: str, chat_model: str | None, embed_model: str | None,
                 transport: httpx2.AsyncBaseTransport | None = None, *, dims: int = 1024,
                 interval_s: float = PROBE_INTERVAL_S) -> None:
        self.chat_model = chat_model or None
        self.embed_model = embed_model or None
        self.dims = dims
        self.interval_s = interval_s
        self.embed_error: str | None = None
        self._state: dict[str, bool | None] = {"chat": None, "embed": None}     # None: chưa dò lần nào
        self._dims: int | None = None       # số chiều véc-tơ đầu tiên Ollama trả; None: chưa thấy véc-tơ nào
        self._http = httpx2.AsyncClient(base_url=url, timeout=10.0, transport=transport)

    @property
    def chat_available(self) -> bool:
        return self.chat_model is not None and bool(self._state["chat"])

    @property
    def embed_available(self) -> bool:
        return self.embed_model is not None and bool(self._state["embed"]) and self._dims in (None, self.dims)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _set(self, kind: str, ok: bool) -> bool:
        """Đặt trạng thái một mô hình; True nếu vừa đổi. Chỉ ghi nhật ký khi đổi."""
        changed = ok != self._state[kind]
        self._state[kind] = ok
        if changed:
            model = self.chat_model if kind == "chat" else self.embed_model
            log.info(json.dumps({"event": "office.assist.ai_ready" if ok else "office.assist.ai_unavailable",
                                 "kind": kind, "model": model}, ensure_ascii=False))
        return changed

    async def _tags(self) -> set[str]:
        try:
            r = await self._http.get("/api/tags", timeout=5.0)
            models = r.json().get("models") if r.status_code == 200 else None
        except (httpx2.HTTPError, ValueError, AttributeError, TypeError):
            return set()
        if not isinstance(models, list):
            return set()
        return {str(m.get("name")) for m in models if isinstance(m, dict)}

    async def probe(self) -> None:
        names = await self._tags()
        for kind, model in (("chat", self.chat_model), ("embed", self.embed_model)):
            if model is None:
                continue
            ok = model in names or f"{model}:latest" in names
            if self._set(kind, ok) and ok:
                await self._preload(kind, model)

    async def _preload(self, kind: str, model: str) -> None:
        # nạp trước chỉ để lần hỏi đầu nhanh hơn; lỗi thì lần gọi thật tự nạp
        if kind == "chat":
            path, body = "/api/generate", {"model": model, "keep_alive": KEEP_ALIVE, "options": CHAT_PRELOAD_OPTIONS}
        else:
            path, body = "/api/embed", {"model": model, "input": ["Mộc"], "truncate": True, "keep_alive": KEEP_ALIVE,
                                        "options": EMBED_OPTIONS}
        try:
            r = await self._http.post(path, json=body, timeout=PRELOAD_TIMEOUT_S)
        except httpx2.HTTPError:
            return
        if kind == "embed" and r.status_code == 200:
            try:
                self._check_dims(r.json())      # sai số chiều thì biết ngay lúc khởi động, trước lô nhúng đầu
            except ValueError:
                pass

    def _check_dims(self, data: object) -> bool:
        """Véc-tơ đầu tiên Ollama trả có đúng ``MOC_AI_EMBED_DIMS`` chiều không (kiểm một lần). Khác là sai cấu hình,
        không do nội dung: tắt nhúng tới khi sửa biến rồi khởi động lại — chỉ tìm theo từ khóa, ``/readyz`` báo
        ``semantic: false``."""
        if self._dims is None:
            rows = data.get("embeddings") if isinstance(data, dict) else None
            first = rows[0] if isinstance(rows, list) and rows else None
            if (not isinstance(first, list) or not first
                    or not all(isinstance(x, int | float) and not isinstance(x, bool) for x in first)):
                return True                 # sai dạng: _vectors loại, lần sau kiểm lại
            self._dims = len(first)
            if self._dims != self.dims:
                log.error(json.dumps({
                    "event": "office.assist.embed_dims_mismatch", "model": self.embed_model, "dims": self._dims,
                    "expected": self.dims, "message": "MOC_AI_EMBED_DIMS khác số chiều của mô hình nhúng: tắt tìm "
                                                      "theo nghĩa — sửa MOC_AI_EMBED_DIMS rồi khởi động lại svc-files",
                }, ensure_ascii=False))
        return self._dims == self.dims

    async def run(self) -> None:
        while True:
            try:
                await self.probe()
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
                log.warning(json.dumps({"event": "office.assist.ai_probe_failed", "error": str(exc)},
                                       ensure_ascii=False))
            await asyncio.sleep(self.interval_s)

    async def embed(self, texts: Sequence[str], *, query: bool, timeout_s: float) -> list[list[float]] | None:
        """Véc-tơ của từng chuỗi, đúng thứ tự; None khi chưa có mô hình, quá giờ, lỗi, hoặc kết quả sai dạng —
        lý do ở ``embed_error``."""
        if not texts:
            return None
        if not self.embed_available:
            self.embed_error = "model_unavailable"
            return None
        inputs = [query_text(self.embed_model, t) if query else t for t in texts]
        body = {"model": self.embed_model, "input": inputs, "truncate": True, "keep_alive": KEEP_ALIVE,
                "options": EMBED_OPTIONS}
        timeout_s = max(timeout_s, 0.1)
        try:
            # timeout của httpx tính từng bước (kết nối, đọc…): wait_for chặn tổng thời gian
            r = await asyncio.wait_for(self._http.post("/api/embed", json=body, timeout=timeout_s), timeout_s)
        except (TimeoutError, httpx2.TimeoutException):
            return self._embed_failed("timeout", len(texts))
        except httpx2.HTTPError:
            return self._embed_failed("unavailable", len(texts))
        if r.status_code == 404:        # mô hình bị gỡ khỏi Ollama: lượt dò sau kiểm lại
            self._set("embed", False)
        if r.status_code != 200:
            return self._embed_failed(f"http {r.status_code}", len(texts))
        try:
            data = r.json()
        except ValueError:
            data = None
        if not self._check_dims(data):
            return self._embed_failed("dims_mismatch", len(texts))
        vectors = _vectors(data, len(texts), self.dims)
        if vectors is None:
            return self._embed_failed("bad_output", len(texts))
        self.embed_error = None
        return vectors

    def _embed_failed(self, reason: str, count: int) -> None:
        self.embed_error = reason
        log.warning(json.dumps({"event": "office.assist.embed_failed", "model": self.embed_model, "reason": reason,
                                "inputs": count}, ensure_ascii=False))
        return None

    async def chat(self, messages: list[dict[str, str]], *, format: dict[str, Any], options: dict[str, Any],
                   timeout_s: float) -> ChatResult:
        if not self.chat_available:
            return ChatResult(None, "model_unavailable")
        body = {"model": self.chat_model, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
                "format": format, "options": options, "messages": messages}
        timeout_s = max(timeout_s, 0.1)
        try:
            r = await asyncio.wait_for(self._http.post("/api/chat", json=body, timeout=timeout_s), timeout_s)
        except (TimeoutError, httpx2.TimeoutException):
            return ChatResult(None, "model_timeout")
        except httpx2.HTTPError:
            return ChatResult(None, "model_unavailable")
        if r.status_code == 404:
            self._set("chat", False)
        if r.status_code != 200:
            return ChatResult(None, "model_unavailable")
        try:
            content = r.json()["message"]["content"]
        except (ValueError, KeyError, TypeError):
            return ChatResult(None, "model_rejected")
        return ChatResult(content, None) if isinstance(content, str) else ChatResult(None, "model_rejected")


def make_ai(settings: Settings) -> AiClient:
    if not settings.ai_url:
        return NullAi()
    return OllamaAi(settings.ai_url, settings.ask_model, settings.ai_embed_model or None,
                    dims=settings.ai_embed_dims)
