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

"""Mô hình của trợ lý hỏi đáp (F4.2) qua Ollama giả: dò từng mô hình, nạp trước, nhúng (kiểm số véc-tơ, số chiều,
tiền tố câu hỏi), sinh (thân yêu cầu, quá giờ, lỗi), NullAi."""

from __future__ import annotations

import asyncio
import json
import math

import httpx2
import pytest

from assist_fakes import CHAT_MODEL, DIMS, EMBED_MODEL, FakeOllama, good_answer, ollama
from svc_files.assist import ai as ai_mod
from svc_files.assist import grounding, meili
from svc_files.assist.ai import ChatResult, NullAi, OllamaAi, make_ai, query_text
from svc_files.config import Settings

MESSAGES = [{"role": "system", "content": grounding.SYSTEM}, {"role": "user", "content": "<cau_hoi>\nx\n</cau_hoi>"}]


def run(coro):
    return asyncio.run(coro)


def embed(ai: OllamaAi, texts, *, query: bool = False, timeout_s: float = 5.0):
    return run(ai.embed(texts, query=query, timeout_s=timeout_s))


def chat(ai: OllamaAi, timeout_s: float = 5.0) -> ChatResult:
    return run(ai.chat(MESSAGES, format=grounding.FORMAT, options=grounding.OPTIONS, timeout_s=timeout_s))


def events(records, name: str) -> list[dict]:
    return [r for r in records if r.get("event") == name]


# --- tên embedder, câu hỏi --------------------------------------------------------------------------------------


def test_embedder_name_comes_from_the_index_module():
    assert ai_mod.embedder_name is meili.embedder_name
    assert meili.embedder_name("qwen3-embedding:0.6b") == "emb_qwen3_embedding_0_6b"
    assert meili.embedder_name("bge-m3") == "emb_bge_m3"


def test_query_prefix_only_for_qwen3_embedding():
    assert query_text("qwen3-embedding:0.6b", "Hạn nộp?") == (
        "Instruct: Given a question about Vietnamese administrative documents, retrieve passages that answer the "
        "question\nQuery: Hạn nộp?")
    assert query_text("Qwen3-Embedding:4b", "x").endswith("\nQuery: x")
    assert query_text("bge-m3", "Hạn nộp?") == "Hạn nộp?"
    assert query_text(None, "Hạn nộp?") == "Hạn nộp?"


# --- dò sẵn sàng ------------------------------------------------------------------------------------------------


def test_probe_marks_each_model_and_preloads_it_once(log_records):
    fake = FakeOllama()
    ai = ollama(fake)
    assert ai.chat_available and ai.embed_available
    assert fake.calls("/api/generate") == [{"model": CHAT_MODEL, "keep_alive": "30m", "options": {"num_ctx": 4096}}]
    assert fake.calls("/api/embed") == [{"model": EMBED_MODEL, "input": ["Mộc"], "truncate": True,
                                         "keep_alive": "30m", "options": {"num_ctx": 2048}}]
    ready = events(log_records, "office.assist.ai_ready")
    assert sorted((e["kind"], e["model"]) for e in ready) == [("chat", CHAT_MODEL), ("embed", EMBED_MODEL)]
    run(ai.probe())                                          # không đổi: không ghi nhật ký, không nạp lại
    assert len(events(log_records, "office.assist.ai_ready")) == 2 and len(fake.calls("/api/generate")) == 1


def test_each_model_has_its_own_state(log_records):
    fake = FakeOllama(models=[CHAT_MODEL])
    ai = ollama(fake)
    assert ai.chat_available and not ai.embed_available
    assert [(e["kind"], e["model"]) for e in events(log_records, "office.assist.ai_unavailable")] == [
        ("embed", EMBED_MODEL)]
    fake.models.append(f"{EMBED_MODEL}")
    run(ai.probe())
    assert ai.embed_available and len(fake.calls("/api/embed")) == 1        # vừa sẵn sàng: nạp trước
    fake.models.clear()
    run(ai.probe())
    assert not ai.chat_available and not ai.embed_available
    assert len(events(log_records, "office.assist.ai_unavailable")) == 3


def test_latest_tag_matches_a_bare_model_name():
    ai = ollama(FakeOllama(models=["qwen3:1.7b", "bge-m3:latest"]), embed="bge-m3")
    assert ai.chat_available and ai.embed_available and ai.embed_model == "bge-m3"


@pytest.mark.parametrize("tags", [
    httpx2.Response(500, text="lỗi"), httpx2.Response(200, text="không phải JSON"),
    httpx2.Response(200, json={"models": "x"}), httpx2.Response(200, json=[]),
])
def test_bad_tags_mean_nothing_is_available(tags):
    async def handler(request: httpx2.Request) -> httpx2.Response:
        return tags

    ai = OllamaAi("http://ollama:11434", CHAT_MODEL, EMBED_MODEL, transport=httpx2.MockTransport(handler), dims=DIMS)
    run(ai.probe())
    assert not ai.chat_available and not ai.embed_available


def test_unreachable_ollama_means_nothing_is_available():
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("không kết nối được", request=request)

    ai = OllamaAi("http://ollama:11434", CHAT_MODEL, EMBED_MODEL, transport=httpx2.MockTransport(down), dims=DIMS)
    run(ai.probe())
    assert not ai.chat_available and not ai.embed_available
    assert embed(ai, ["x"]) is None and chat(ai) == ChatResult(None, "model_unavailable")


def test_background_probe_loop_keeps_running():
    fake = FakeOllama()
    ai = OllamaAi("http://ollama:11434", CHAT_MODEL, EMBED_MODEL, transport=httpx2.MockTransport(fake), dims=DIMS,
                  interval_s=0.01)

    async def go():
        task = asyncio.create_task(ai.run())
        await asyncio.sleep(0.08)
        task.cancel()
        await ai.aclose()

    run(go())
    assert ai.chat_available and len(fake.calls("/api/tags")) >= 3


# --- nhúng ------------------------------------------------------------------------------------------------------


def test_embed_request_and_vectors():
    fake = FakeOllama()
    ai = ollama(fake)
    vectors = embed(ai, ["đoạn một", "đoạn hai"])
    assert vectors == [[pytest.approx(0.1)] * DIMS, [pytest.approx(0.2)] * DIMS]
    body = fake.calls("/api/embed")[-1]
    assert body == {"model": EMBED_MODEL, "input": ["đoạn một", "đoạn hai"], "truncate": True, "keep_alive": "30m",
                    "options": {"num_ctx": 2048}}


def test_query_embedding_carries_the_instruction_prefix():
    fake = FakeOllama()
    ai = ollama(fake)
    embed(ai, ["Hạn nộp?"], query=True)
    assert fake.calls("/api/embed")[-1]["input"] == [query_text(EMBED_MODEL, "Hạn nộp?")]
    other = FakeOllama(models=[CHAT_MODEL, "bge-m3"])
    embed(ollama(other, embed="bge-m3"), ["Hạn nộp?"], query=True)
    assert other.calls("/api/embed")[-1]["input"] == ["Hạn nộp?"]


@pytest.mark.parametrize("reply", [
    {"embeddings": [[0.1] * DIMS, [0.2] * (DIMS - 1)]},             # véc-tơ sau sai số chiều (véc-tơ đầu đúng)
    {"embeddings": [[0.1] * DIMS, [0.2] * DIMS]},                   # thừa véc-tơ
    {"embeddings": []},
    {"embeddings": [[True] * DIMS]},
    {"embeddings": [["0.1"] * DIMS]},
    {"embedding": [0.1] * DIMS},
    [],
])
def test_wrong_vectors_are_none(reply, log_records):
    ai = ollama(FakeOllama(embed_reply=reply))
    assert embed(ai, ["x"]) is None
    assert events(log_records, "office.assist.embed_failed")[-1] == {
        "event": "office.assist.embed_failed", "model": EMBED_MODEL, "reason": "bad_output", "inputs": 1}
    # lỗi của một lần trả về, không phải sai cấu hình: vẫn nhúng tiếp được, lý do không thuộc loại tạm thời
    assert ai.embed_available and ai.embed_error == "bad_output" and ai.embed_error not in ai_mod.TRANSIENT


def test_non_finite_vectors_are_none():
    async def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/tags":
            return httpx2.Response(200, json={"models": [{"name": EMBED_MODEL}]})
        return httpx2.Response(200, text='{"embeddings": [[NaN' + ", 0.1" * (DIMS - 1) + "]]}")

    ai = OllamaAi("http://ollama:11434", None, EMBED_MODEL, transport=httpx2.MockTransport(handler), dims=DIMS)
    run(ai.probe())
    assert ai.embed_available and embed(ai, ["x"]) is None
    assert math.isnan(json.loads('[NaN]')[0])              # Ollama trả NaN thì json vẫn đọc được: phải tự kiểm


def test_embed_errors_are_none_and_a_missing_model_is_marked():
    ai = ollama(FakeOllama(embed_status=500))
    assert embed(ai, ["x"]) is None and ai.embed_available            # lỗi một lần: vẫn dò được
    gone = ollama(FakeOllama(embed_status=404))
    assert embed(gone, ["x"]) is None and not gone.embed_available    # mô hình bị gỡ: chờ lượt dò sau


def test_embed_timeout(log_records):
    ai = ollama(FakeOllama(embed_sleep_s=0.5))
    assert embed(ai, ["x"], timeout_s=0.1) is None
    assert events(log_records, "office.assist.embed_failed")[-1]["reason"] == "timeout"


def test_no_embedding_model_or_not_ready_means_no_call():
    fake = FakeOllama()
    ai = ollama(fake, embed=None)
    assert embed(ai, ["x"]) is None and not ai.embed_available and fake.calls("/api/embed") == []
    cold = ollama(fake, probe=False)                                   # chưa dò lần nào
    assert embed(cold, ["x"]) is None and embed(ollama(fake), []) is None


# --- sinh -------------------------------------------------------------------------------------------------------


def test_chat_request_and_reply():
    fake = FakeOllama()
    ai = ollama(fake)
    assert chat(ai) == ChatResult(good_answer(), None)
    (body,) = fake.calls("/api/chat")
    assert body == {"model": CHAT_MODEL, "stream": False, "think": False, "keep_alive": "30m",
                    "format": grounding.FORMAT, "options": grounding.OPTIONS, "messages": MESSAGES}


def test_chat_timeout():
    async def slow(request):
        await asyncio.sleep(0.5)
        return good_answer()

    assert chat(ollama(FakeOllama(reply=slow)), timeout_s=0.1) == ChatResult(None, "model_timeout")


def test_chat_errors():
    assert chat(ollama(FakeOllama(chat_status=500))) == ChatResult(None, "model_unavailable")
    gone = ollama(FakeOllama(chat_status=404))
    assert chat(gone) == ChatResult(None, "model_unavailable") and not gone.chat_available

    async def odd(request):
        return httpx2.Response(200, json={"done": True})

    async def not_text(request):
        return httpx2.Response(200, json={"message": {"role": "assistant", "content": {"du_can_cu": True}}})

    async def not_json(request):
        return httpx2.Response(200, text="xin chào")

    for reply in (odd, not_text, not_json):
        assert chat(ollama(FakeOllama(reply=reply))) == ChatResult(None, "model_rejected")


def test_chat_without_a_ready_model_makes_no_call():
    fake = FakeOllama(models=[EMBED_MODEL])
    ai = ollama(fake)
    assert chat(ai) == ChatResult(None, "model_unavailable") and fake.calls("/api/chat") == []
    assert chat(ollama(fake, chat=None)) == ChatResult(None, "model_unavailable")


# --- không có mô hình --------------------------------------------------------------------------------------------


def test_null_ai():
    ai = NullAi()
    assert ai.chat_model is None and ai.embed_model is None and not ai.chat_available and not ai.embed_available
    assert run(ai.embed(["x"], query=True, timeout_s=1)) is None
    assert run(ai.chat(MESSAGES, format=grounding.FORMAT, options=grounding.OPTIONS, timeout_s=1)) == ChatResult(
        None, "model_unavailable")
    assert run(ai.run()) is None and run(ai.aclose()) is None


def test_make_ai_follows_settings(settings):
    assert isinstance(make_ai(settings), NullAi)
    env = {"MOC_OIDC_ISSUER": "http://kc/realms/moc", "MOC_OIDC_JWKS_URL": "http://unused/jwks",
           "SEAWEEDFS_S3_ACCESS_KEY": "t", "SEAWEEDFS_S3_SECRET_KEY": "t", "HASURA_ADMIN_SECRET": "t",
           "MEILISEARCH_API_KEY": "t", "MOC_AI_URL": "http://ollama:11434", "MOC_AI_MODEL": "qwen3:1.7b"}
    got = make_ai(Settings.from_env(env))
    assert isinstance(got, OllamaAi) and (got.chat_model, got.embed_model, got.dims) == (
        "qwen3:1.7b", "qwen3-embedding:0.6b", 1024)
    got = make_ai(Settings.from_env({**env, "MOC_ASK_MODEL": "qwen3:4b", "MOC_AI_EMBED_MODEL": "",
                                     "MOC_AI_EMBED_DIMS": "768"}))
    assert (got.chat_model, got.embed_model, got.dims) == ("qwen3:4b", None, 768)
    run(got.aclose())


def test_log_lines_are_json(log_records):
    ollama(FakeOllama(models=[]))
    assert all(json.dumps(r) for r in log_records)


# --- lý do lỗi nhúng, số chiều -----------------------------------------------------------------------------------


def test_embed_error_tells_passing_failures_from_bad_input():
    ai = ollama(FakeOllama())
    assert embed(ai, ["x"]) and ai.embed_error is None
    for status, transient in ((500, False), (400, False), (503, True), (404, True)):
        ai = ollama(FakeOllama(embed_status=status))
        assert embed(ai, ["x"]) is None and ai.embed_error == f"http {status}"
        assert (ai.embed_error in ai_mod.TRANSIENT) is transient
    slow = ollama(FakeOllama(embed_sleep_s=0.5))
    assert embed(slow, ["x"], timeout_s=0.1) is None and slow.embed_error == "timeout"
    assert slow.embed_error in ai_mod.TRANSIENT
    cold = ollama(FakeOllama(), probe=False)
    assert embed(cold, ["x"]) is None and cold.embed_error == "model_unavailable"
    assert cold.embed_error in ai_mod.TRANSIENT
    assert NullAi.embed_error in ai_mod.TRANSIENT


def test_wrong_dimensions_turn_embedding_off_with_a_clear_error(log_records):
    """MOC_AI_EMBED_DIMS lệch số chiều thật: trước đây mọi lần nhúng bị loại lặng lẽ mà /readyz vẫn báo semantic."""
    fake = FakeOllama(dims=DIMS * 2)
    ai = ollama(fake)                                   # véc-tơ đầu tiên: lần nạp trước lúc dò
    assert not ai.embed_available and ai.chat_available
    (err,) = events(log_records, "office.assist.embed_dims_mismatch")
    assert (err["model"], err["dims"], err["expected"]) == (EMBED_MODEL, DIMS * 2, DIMS)
    assert "MOC_AI_EMBED_DIMS" in err["message"]
    calls = len(fake.calls("/api/embed"))
    assert embed(ai, ["x"]) is None and len(fake.calls("/api/embed")) == calls     # không gọi nữa
    fake.models.clear()
    run(ai.probe())
    fake.models.append(EMBED_MODEL)
    run(ai.probe())                                     # Ollama khởi động lại: vẫn tắt tới khi sửa biến
    assert not ai.embed_available and len(events(log_records, "office.assist.embed_dims_mismatch")) == 1


def test_wrong_dimensions_found_on_the_first_embedding_when_preload_failed(log_records):
    fake = FakeOllama(dims=DIMS + 1)
    preloads: list[httpx2.Request] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/embed" and not preloads:
            preloads.append(request)
            raise httpx2.ConnectError("đang nạp", request=request)
        return await fake(request)

    ai = OllamaAi("http://ollama:11434", None, EMBED_MODEL, transport=httpx2.MockTransport(handler), dims=DIMS)
    run(ai.probe())
    assert ai.embed_available                           # nạp trước lỗi: chưa biết số chiều
    assert embed(ai, ["x"]) is None and ai.embed_error == "dims_mismatch"
    assert ai.embed_error in ai_mod.TRANSIENT
    assert not ai.embed_available and events(log_records, "office.assist.embed_dims_mismatch")


def test_right_dimensions_are_checked_once():
    fake = FakeOllama()
    ai = ollama(fake)
    assert embed(ai, ["x"]) and ai.embed_available
    fake.embed_reply = {"embeddings": [[0.1] * (DIMS - 1)]}         # lần sau mà sai số chiều: lỗi của lần đó
    assert embed(ai, ["x"]) is None and ai.embed_error == "bad_output" and ai.embed_available


@pytest.mark.parametrize(("loaded", "device"), [
    ([{"name": CHAT_MODEL, "size": 2_000, "size_vram": 2_000}], "gpu"),
    ([{"name": CHAT_MODEL, "size": 2_000, "size_vram": 0}], "cpu"),
    ([{"name": CHAT_MODEL, "size": 2_000, "size_vram": 2_000}, {"name": EMBED_MODEL, "size": 1_000, "size_vram": 0}],
     "gpu+cpu"),
])
def test_device_follows_where_ollama_loaded_the_models(loaded, device):
    # MOC_AI_DEVICE (docker-compose.gpu.yml): /api/ps cho biết phần nào của mô hình nằm trong VRAM
    fake = FakeOllama()
    fake.loaded = loaded
    assert ollama(fake).device == device


def test_device_unknown_until_a_model_is_loaded_then_kept():
    fake = FakeOllama()
    ai = ollama(fake)
    assert ai.device is None and NullAi().device is None
    fake.loaded = [{"name": CHAT_MODEL, "size": 2_000, "size_vram": 2_000}]
    asyncio.run(ai.probe())
    assert ai.device == "gpu"
    fake.loaded = [{"name": CHAT_MODEL, "size": True, "size_vram": "2000"}]      # sai dạng: bỏ qua
    asyncio.run(ai.probe())
    fake.loaded = []                                                            # hết keep_alive: giữ lần trước
    asyncio.run(ai.probe())
    assert ai.device == "gpu"


def test_no_ps_call_before_any_model_is_ready():
    fake = FakeOllama(models=())
    ollama(fake)
    assert fake.calls("/api/ps") == []

