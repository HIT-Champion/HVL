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
- Nơi chạy (``MOC_AI_DEVICE``, docker-compose.gpu.yml): mỗi lượt dò, khi đã có mô hình sẵn sàng, đọc ``GET /api/ps``
  → ``device``: ``gpu`` (cả mô hình trong bộ nhớ GPU), ``cpu``, ``gpu+cpu`` (chia hai); trang trạng thái hiện nó.
- Sinh: ``POST /api/chat`` không stream, tắt suy nghĩ, đầu ra ép theo JSON Schema (grounding.py dựng lời dặn và kiểm).
- Không sửa ``docread/summarize.py``: tác tử đọc văn bản đến dò mô hình trích yếu riêng.
- **API ngoài** (#430, ``MOC_ASK_API=openai``, mặc định tắt): chỉ bước sinh đi tới máy chủ chuẩn OpenAI
  (``POST {MOC_ASK_API_URL}/chat/completions``, đầu ra ép bằng ``response_format`` JSON Schema), dò sẵn sàng bằng
  ``GET /models``; nhúng vẫn ở Ollama (``SplitAi`` ghép hai bên). Che ở lối ra như với Ollama; bộ kiểm căn cứ ở
  answer.py không đổi. Khóa chỉ đi trong tiêu đề ``Authorization``, không vào nhật ký. ``chat_where`` (``local`` /
  ``external``) cho sổ kiểm toán biết mô hình chạy ở đâu.
- **Che thông tin cá nhân ở lối ra** (F4.4, pii.py): không byte chữ nào tới Ollama mà chưa qua bộ che. ``embed`` che
  từng chuỗi (đoạn văn bản, câu hỏi, trích yếu F4.3 đều chỉ ra mô hình qua đây); ``chat`` che nội dung mọi message.
  Bản che idempotent: answer.py đã che câu hỏi và nguồn bằng nhãn đánh số ``[SĐT-1]`` thì ở đây không còn gì để che —
  còn phải che thêm nghĩa là chỗ gọi đã quên, ghi cảnh báo ``office.assist.pii_at_egress`` (chỉ số chỗ đã che).
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

from .. import pii
from .meili import embedder_name  # tên embedder theo mô hình — luồng B đặt ở meili.py (§4.3)

if TYPE_CHECKING:
    from ..config import Settings

__all__ = ["TRANSIENT", "AiClient", "ChatResult", "NullAi", "OllamaAi", "OpenAiChat", "SplitAi", "embedder_name",
           "make_ai", "query_text"]

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
    chat_where: str             # local: Ollama trong máy; external: API ngoài (MOC_ASK_API=openai)
    embed_model: str | None
    embed_error: str | None     # lý do lần nhúng gần nhất lỗi (None: thành công); đọc ngay sau ``await embed(...)``
    device: str | None          # gpu, cpu, gpu+cpu theo /api/ps của Ollama; None: chưa biết

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
    chat_where = "local"
    embed_model: str | None = None
    embed_error: str | None = "model_unavailable"
    device: str | None = None
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


def _masked(messages: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    """Message gửi ``/api/chat`` với ``content`` đã che (nhãn trơn), và số chỗ phải che thêm ở lối ra."""
    out: list[dict[str, str]] = []
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            m = pii.mask(content)
            if m.spans:
                total += len(m.spans)
                message = {**message, "content": m.text}
        out.append(message)
    return out, total


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
    chat_where = "local"

    def __init__(self, url: str, chat_model: str | None, embed_model: str | None,
                 transport: httpx2.AsyncBaseTransport | None = None, *, dims: int = 1024,
                 interval_s: float = PROBE_INTERVAL_S) -> None:
        self.chat_model = chat_model or None
        self.embed_model = embed_model or None
        self.dims = dims
        self.interval_s = interval_s
        self.embed_error: str | None = None
        self.device: str | None = None      # chưa nạp mô hình nào lần nào: chưa biết
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
        if any(self._state.values()):
            await self._where()

    async def _where(self) -> None:
        """Mô hình đang nạp nằm ở đâu (``GET /api/ps``): ``size_vram`` bằng ``size`` là ``gpu``, bằng 0 là ``cpu``, ở
        giữa là ``gpu+cpu`` (VRAM không đủ, Ollama chia lớp). Chưa nạp mô hình nào (hết ``keep_alive``) thì giữ kết quả
        lần trước."""
        try:
            r = await self._http.get("/api/ps", timeout=5.0)
            models = r.json().get("models") if r.status_code == 200 else None
        except (httpx2.HTTPError, ValueError, AttributeError, TypeError):
            return
        size = vram = 0
        for m in models if isinstance(models, list) else []:
            total, gpu = (m.get("size"), m.get("size_vram")) if isinstance(m, dict) else (None, None)
            if type(total) is int and type(gpu) is int and total > 0:
                size, vram = size + total, vram + max(0, min(gpu, total))
        if size:
            self.device = "cpu" if vram == 0 else "gpu" if vram == size else "gpu+cpu"

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
        # che sau khi thêm tiền tố: chữ gửi đi đúng là chữ đã che
        inputs = [pii.mask_text(query_text(self.embed_model, t) if query else t) for t in texts]
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
        messages, masked = _masked(messages)
        if masked:
            log.warning(json.dumps({"event": "office.assist.pii_at_egress", "masked": masked}, ensure_ascii=False))
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


class OpenAiChat:
    """Bước sinh qua máy chủ nói chuẩn OpenAI (vLLM, llama.cpp, dịch vụ đám mây…). Chỉ có ``chat``; không nhúng."""

    chat_where = "external"
    embed_model: str | None = None
    embed_error: str | None = "model_unavailable"
    embed_available = False
    device: str | None = None       # máy chủ ngoài: không biết mô hình chạy trên gì

    def __init__(self, url: str, model: str, key: str = "", transport: httpx2.AsyncBaseTransport | None = None, *,
                 interval_s: float = PROBE_INTERVAL_S) -> None:
        self.chat_model = model or None
        self.interval_s = interval_s
        self._ready: bool | None = None
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._http = httpx2.AsyncClient(base_url=url, timeout=10.0, transport=transport, headers=headers)

    @property
    def chat_available(self) -> bool:
        return self.chat_model is not None and bool(self._ready)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _set(self, ok: bool, reason: str | None = None) -> None:
        if ok != self._ready:
            log.info(json.dumps({"event": "office.assist.ai_ready" if ok else "office.assist.ai_unavailable",
                                 "kind": "chat", "model": self.chat_model, "where": "external",
                                 **({"reason": reason} if reason else {})}, ensure_ascii=False))
        self._ready = ok

    async def probe(self) -> None:
        """``GET /models`` trả 200 là dùng được. Không đòi mô hình có trong danh sách: có máy chủ chỉ liệt kê một
        phần, hoặc gọi mô hình bằng bí danh."""
        if self.chat_model is None:
            return
        try:
            r = await self._http.get("/models", timeout=5.0)
        except httpx2.HTTPError:
            self._set(False, "unreachable")
            return
        self._set(r.status_code == 200, None if r.status_code == 200 else f"http {r.status_code}")

    async def run(self) -> None:
        while True:
            try:
                await self.probe()
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
                log.warning(json.dumps({"event": "office.assist.ai_probe_failed", "error": str(exc)},
                                       ensure_ascii=False))
            await asyncio.sleep(self.interval_s)

    async def embed(self, texts: Sequence[str], *, query: bool, timeout_s: float) -> list[list[float]] | None:
        return None

    async def chat(self, messages: list[dict[str, str]], *, format: dict[str, Any], options: dict[str, Any],
                   timeout_s: float) -> ChatResult:
        if not self.chat_available:
            return ChatResult(None, "model_unavailable")
        messages, masked = _masked(messages)
        if masked:
            log.warning(json.dumps({"event": "office.assist.pii_at_egress", "masked": masked}, ensure_ascii=False))
        # strict: mọi khóa của schema đều bắt buộc, không thêm khóa lạ — đúng như grounding.FORMAT
        schema = {**format, "additionalProperties": False}
        body: dict[str, Any] = {
            "model": self.chat_model, "messages": messages, "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": "tra_loi", "strict": True,
                                                                       "schema": schema}},
        }
        for ours, theirs in (("temperature", "temperature"), ("num_predict", "max_tokens"), ("seed", "seed")):
            if ours in options:
                body[theirs] = options[ours]
        timeout_s = max(timeout_s, 0.1)
        try:
            r = await asyncio.wait_for(self._http.post("/chat/completions", json=body, timeout=timeout_s), timeout_s)
        except (TimeoutError, httpx2.TimeoutException):
            return ChatResult(None, "model_timeout")
        except httpx2.HTTPError:
            return ChatResult(None, "model_unavailable")
        if r.status_code in (401, 403, 404):        # khóa sai, hết quyền, sai tên mô hình: lượt dò sau kiểm lại
            self._set(False, f"http {r.status_code}")
        if r.status_code != 200:
            return ChatResult(None, "model_unavailable")
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return ChatResult(None, "model_rejected")
        return ChatResult(content, None) if isinstance(content, str) else ChatResult(None, "model_rejected")


class SplitAi:
    """Nhúng ở Ollama tại chỗ (hoặc không nhúng), sinh qua API ngoài."""

    chat_where = "external"

    def __init__(self, embedder: AiClient, writer: OpenAiChat) -> None:
        self.embedder = embedder
        self.writer = writer
        self.chat_model = writer.chat_model
        self.embed_model = embedder.embed_model

    @property
    def embed_error(self) -> str | None:
        return self.embedder.embed_error

    @property
    def chat_available(self) -> bool:
        return self.writer.chat_available

    @property
    def embed_available(self) -> bool:
        return self.embedder.embed_available

    @property
    def device(self) -> str | None:
        """Nơi Ollama tại chỗ đặt mô hình nhúng (và mô hình trích yếu F4.1 nếu cùng máy); bước viết chạy ngoài."""
        return self.embedder.device

    async def embed(self, texts: Sequence[str], *, query: bool, timeout_s: float) -> list[list[float]] | None:
        return await self.embedder.embed(texts, query=query, timeout_s=timeout_s)

    async def chat(self, messages: list[dict[str, str]], *, format: dict[str, Any], options: dict[str, Any],
                   timeout_s: float) -> ChatResult:
        return await self.writer.chat(messages, format=format, options=options, timeout_s=timeout_s)

    async def run(self) -> None:
        await asyncio.gather(self.embedder.run(), self.writer.run())

    async def aclose(self) -> None:
        await self.embedder.aclose()
        await self.writer.aclose()


def make_ai(settings: Settings) -> AiClient:
    if settings.ask_api == "openai":
        embedder: AiClient = (OllamaAi(settings.ai_url, None, settings.ai_embed_model, dims=settings.ai_embed_dims)
                              if settings.ai_url and settings.ai_embed_model else NullAi())
        return SplitAi(embedder, OpenAiChat(settings.ask_api_url, settings.ask_model, settings.ask_api_key))
    if not settings.ai_url:
        return NullAi()
    return OllamaAi(settings.ai_url, settings.ask_model, settings.ai_embed_model or None,
                    dims=settings.ai_embed_dims)
