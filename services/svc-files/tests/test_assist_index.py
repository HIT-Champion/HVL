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

"""Vòng nền chỉ mục đoạn (F4.2): thay / cập nhật / xóa đúng lúc, véc-tơ, đổi mô hình, nhường mô hình, không chết;
đoạn làm mô hình lỗi không chặn vòng nhúng, mọi tác vụ của lượt phải xong, embedder lỗi không chặn đồng bộ."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable

import pytest

from conftest import TENANT_A, FakeChunkIndex
from svc_files.assist.chunks import embed_input
from svc_files.assist.index import CANARY, EMBEDDER_RETRY_S, ChunkIndexer, changed_at
from svc_files.assist.meili import embedder_name
from svc_files.search import SearchError
from test_assist_chunks import link, sentences, text

MODEL = "qwen3-embedding:0.6b"
EMB = "emb_qwen3_embedding_0_6b"
FAILED = MODEL + "#failed"


class FakeEmbedder:
    """Phần nhúng của client mô hình (assist/ai.py của luồng C): véc-tơ 4 chiều tất định."""

    def __init__(self, model: str = MODEL, *, available: bool = True) -> None:
        self.embed_model = model
        self.embed_available = available
        self.fail = False
        self.calls: list[dict] = []

    async def embed(self, texts: list[str], *, query: bool, timeout_s: float) -> list[list[float]] | None:
        self.calls.append({"texts": list(texts), "query": query, "timeout_s": timeout_s})
        return None if self.fail else [[float(len(t)), 1.0, 0.0, 0.5] for t in texts]


class PoisonEmbedder(FakeEmbedder):
    """Như OllamaAi: lỗi thì trả None và để lý do ở ``embed_error``. Đầu vào nào chứa ``poison`` làm mô hình lỗi tất
    định (Ollama trả 500 "unsupported value: NaN"); ``down`` (vd "timeout") làm mọi lần gọi lỗi với lý do đó."""

    def __init__(self, poison: str = "DOCHAI", **kw) -> None:
        super().__init__(**kw)
        self.poison = poison
        self.down: str | None = None
        self.embed_error: str | None = None
        self.on_fail: Callable[[], None] | None = None

    async def embed(self, texts: list[str], *, query: bool, timeout_s: float) -> list[list[float]] | None:
        self.calls.append({"texts": list(texts), "query": query, "timeout_s": timeout_s})
        if self.down or any(self.poison in t for t in texts):
            self.embed_error = self.down or "http 500"
            if self.on_fail:
                self.on_fail()
            return None
        self.embed_error = None
        return [[float(len(t)), 1.0, 0.0, 0.5] for t in texts]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def add(hasura, summary: str = "Về việc xét học bổng", *, pages: tuple = (), at: str = "2026-10-21T08:00:00+00:00",
        **cols) -> str:
    files = [link({**text(*pages), "extracted_at": at}, file_id=f"f-{len(hasura.documents)}")] if pages else []
    return hasura.add_document(TENANT_A, summary, files=files, assignments=[], updated_at=at, **cols)


EARLY = "2026-10-21T07:00:00+00:00"     # ngoài cửa sổ overlap của lượt sau: chỉ được đọc lại nhờ mốc mới


def touch(hasura, doc_id: str, at: str, **cols) -> None:
    hasura.documents[doc_id].update(updated_at=at, **cols)


def of(index: FakeChunkIndex, doc_id: str) -> dict[str, dict]:
    return {k: v for k, v in index.docs.items() if v["document_id"] == doc_id}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def index() -> FakeChunkIndex:
    return FakeChunkIndex()


# --- đồng bộ -------------------------------------------------------------------------------------------------------


def test_new_documents_get_chunks_with_null_vectors(hasura, index):
    doc = add(hasura, pages=(sentences("MOT", 20), sentences("HAI", 3)))
    scan = add(hasura, "Thông báo lịch nghỉ Tết")
    indexer = ChunkIndexer(index, hasura, FakeEmbedder())
    assert indexer.embedder == EMB and not indexer.ready
    counts = run(indexer.sync_once())
    assert counts == {"documents": 2, "chunks": len(index.docs), "deleted": 0}
    assert indexer.ready and index.settings == [{"embedder": EMB, "dims": 1024, "removed": []}]
    chunks = of(index, doc)
    assert {c["page"] for c in chunks.values()} == {1, 2}
    assert all(c["_vectors"] == {EMB: None} and c["embed_model"] is None for c in index.docs.values())
    assert [c["kind"] for c in of(index, scan).values()] == ["meta"]
    assert index.waited and index.waited[-1] == index.tasks      # đợi tác vụ cuối trước khi nhúng


def test_without_embedding_model_chunks_have_no_vectors(hasura, index):
    add(hasura, pages=(sentences("MOT", 3),))
    for ai in (None, FakeEmbedder(""), FakeEmbedder("  ")):
        index = FakeChunkIndex()
        indexer = ChunkIndexer(index, hasura, ai)
        run(indexer.sync_once())
        assert indexer.embedder is None and index.settings[0]["embedder"] is None
        assert index.docs and all("_vectors" not in c and c["embed_model"] is None for c in index.docs.values())
        assert run(indexer.embed_once()) == 0


@pytest.mark.parametrize(("start", "change"), [
    ({"direction": "in", "status": "registered"}, {"restricted": True}),
    ({"direction": "in", "status": "in_progress"}, {"status": "cancelled"}),
    ({"direction": "out", "status": "issued"}, {"status": "draft"}),
])
def test_documents_no_longer_eligible_lose_every_chunk(hasura, index, start, change):
    doc = add(hasura, pages=(sentences("A", 20), sentences("B", 20)), **start)
    other = add(hasura, pages=(sentences("C", 3),))
    indexer = ChunkIndexer(index, hasura)
    run(indexer.sync_once())
    assert len(of(index, doc)) > 2
    keep = dict(of(index, other))
    touch(hasura, doc, "2026-10-21T08:05:00+00:00", **change)
    counts = run(indexer.sync_once())
    assert of(index, doc) == {} and of(index, other) == keep
    assert counts["deleted"] > 2 and index.writes[-1][0] == "delete"


def test_changed_text_is_replaced_with_null_vectors(hasura, index):
    doc = add(hasura, pages=(sentences("A", 20), sentences("B", 3)), at=EARLY)
    add(hasura, "Văn bản khác", pages=(sentences("X", 2),))       # đẩy con trỏ lên 08:00
    ai = FakeEmbedder()
    indexer = ChunkIndexer(index, hasura, ai, batch=100)
    run(indexer.sync_once())
    run(indexer.embed_once())
    assert all(c["embed_model"] == MODEL for c in index.docs.values())

    link_ = hasura.documents[doc]["files"][0]
    link_["file"]["text"] = {**text(sentences("A", 20), sentences("C", 3)), "extracted_at": "2026-10-21T08:10:00+00:00"}
    run(indexer.sync_once())                                       # tệp vừa đọc lại chữ: updated_at không đổi
    assert hasura.chunk_reads[-1] == "00000000-0000-0000-0000-000000000000"
    kind, written = index.writes[-1]
    assert kind == "replace" and {c["page"] for c in written} == {2}
    assert all(c["_vectors"] == {EMB: None} and c["embed_model"] is None for c in written)
    page1 = [c for c in of(index, doc).values() if c["page"] == 1]
    assert page1 and all(c["embed_model"] == MODEL and c["_vectors"][EMB]["embeddings"] for c in page1)


def test_new_assignment_updates_filters_and_keeps_vectors(hasura, index):
    doc = add(hasura, pages=(sentences("A", 20),), at=EARLY)
    add(hasura, "Văn bản khác", pages=(sentences("X", 2),))       # đẩy con trỏ lên 08:00
    indexer = ChunkIndexer(index, hasura, FakeEmbedder(), batch=100)
    run(indexer.sync_once())
    run(indexer.embed_once())
    before = {k: dict(v) for k, v in of(index, doc).items()}
    assert run(indexer.sync_once())["documents"] == 0
    hasura.documents[doc]["assignments"].append(
        {"department_id": "dep-dt", "user_id": "u-cv", "assigned_at": "2026-10-21T08:20:00+00:00", "status": "open"})
    assert run(indexer.sync_once())["documents"] == 1               # chỉ giao việc mới: updated_at không đổi
    kind, written = index.writes[-1]
    assert kind == "update" and {c["id"] for c in written} == set(before)
    assert all("_vectors" not in c and "text" not in c and "embed_model" not in c for c in written)
    for cid, c in of(index, doc).items():
        assert c["assignee_departments"] == ["dep-dt"] and c["assignee_users"] == ["u-cv"]
        assert c["_vectors"] == before[cid]["_vectors"] and c["embed_model"] == MODEL
        assert c["text_sha"] == before[cid]["text_sha"] and c["meta_sha"] != before[cid]["meta_sha"]


def test_cancelled_assignment_is_dropped_on_next_document_change(hasura, index):
    doc = add(hasura, pages=(sentences("A", 3),))
    hasura.documents[doc]["assignments"].append(
        {"department_id": "dep-dt", "user_id": None, "assigned_at": "2026-10-21T08:01:00+00:00", "status": "open"})
    indexer = ChunkIndexer(index, hasura)
    run(indexer.sync_once())
    assert all(c["assignee_departments"] == ["dep-dt"] for c in of(index, doc).values())
    hasura.documents[doc]["assignments"][0]["status"] = "cancelled"
    touch(hasura, doc, "2026-10-21T08:30:00+00:00")
    run(indexer.sync_once())
    assert all(c["assignee_departments"] == [] for c in of(index, doc).values())


def test_unchanged_documents_are_not_read_back_or_rewritten(hasura, index):
    add(hasura, pages=(sentences("A", 3),))
    add(hasura, pages=(sentences("B", 3),))
    indexer = ChunkIndexer(index, hasura)
    run(indexer.sync_once())
    writes, fetches = len(index.writes), len(index.fetches)
    assert run(indexer.sync_once()) == {"documents": 0, "chunks": 0, "deleted": 0}
    assert (len(index.writes), len(index.fetches)) == (writes, fetches)


def test_restart_rereads_everything_but_writes_only_differences(hasura, index):
    add(hasura, pages=(sentences("A", 20),))
    run(ChunkIndexer(index, hasura).sync_once())
    writes = len(index.writes)
    again = ChunkIndexer(index, hasura)                            # svc-files khởi động lại: con trỏ về đầu
    assert run(again.sync_once())["documents"] == 0 and again.ready
    assert len(index.writes) == writes and len(index.settings) == 2   # cấu hình áp lại mỗi lần khởi động


def test_pages_through_documents_by_id(hasura, index):
    ids = sorted(add(hasura, f"Văn bản {i}", pages=(sentences(f"V{i}", 2),)) for i in range(5))
    run(ChunkIndexer(index, hasura, page=2).sync_once())
    assert hasura.chunk_reads == ["00000000-0000-0000-0000-000000000000", ids[1], ids[3]]
    assert {c["document_id"] for c in index.docs.values()} == set(ids)


def test_changed_at_counts_text_and_assignments():
    row = {"updated_at": "2026-10-21T08:00:00+00:00",
           "files": [{"file": {"text": {"extracted_at": "2026-10-21T08:03:00+00:00"}}}, {"file": {"text": None}}],
           "assignments": [{"assigned_at": "2026-10-21T08:07:00+00:00"}]}
    assert changed_at(row).isoformat() == "2026-10-21T08:07:00+00:00"


# --- nhúng ---------------------------------------------------------------------------------------------------------


def test_embeds_only_when_available_in_batches_with_the_embedder_name(hasura, index):
    for i in range(3):
        add(hasura, f"Văn bản số {i}", pages=(sentences(f"N{i}", 40),))
    ai = FakeEmbedder(available=False)
    indexer = ChunkIndexer(index, hasura, ai, batch=4)
    assert run(indexer.embed_once()) == 0                          # chưa áp cấu hình chỉ mục
    run(indexer.sync_once())
    total = len(index.docs)
    assert total > 8
    assert run(indexer.embed_once()) == 0 and ai.calls == []       # mô hình nhúng chưa sẵn sàng
    ai.embed_available = True
    done = []
    while n := run(indexer.embed_once()):
        done.append(n)
    assert sum(done) == total and max(done) == 4
    assert all(c["query"] is False and c["timeout_s"] == 120 and len(c["texts"]) <= 4 for c in ai.calls)
    first = ai.calls[0]["texts"][0]
    assert re.fullmatch(r"\d+/UBND-VP — Văn bản số \d", first.split("\n")[0])   # "{symbol} — {summary}" rồi chữ
    for c in index.docs.values():
        assert c["embed_model"] == MODEL
        assert c["_vectors"][EMB] == {"embeddings": [float(len(embed_input(c))), 1.0, 0.0, 0.5], "regenerate": False}
    updates = [w for kind, w in index.writes if kind == "update"]
    assert all(set(u) == {"id", "embed_model", "_vectors"} for batch in updates for u in batch)


def test_model_change_drops_old_embedder_and_embeds_again(hasura, index):
    add(hasura, pages=(sentences("A", 20),))
    old = ChunkIndexer(index, hasura, FakeEmbedder("bge-m3"), batch=100)
    run(old.sync_once())
    run(old.embed_once())
    assert all(c["embed_model"] == "bge-m3" and "emb_bge_m3" in c["_vectors"] for c in index.docs.values())

    ai = FakeEmbedder(MODEL)
    new = ChunkIndexer(index, hasura, ai, batch=100)
    run(new.sync_once())
    assert index.settings[-1] == {"embedder": EMB, "dims": 1024, "removed": ["emb_bge_m3"]}
    assert all("emb_bge_m3" not in (c.get("_vectors") or {}) for c in index.docs.values())
    assert run(new.embed_once()) == len(index.docs) and len(ai.calls[0]["texts"]) == len(index.docs)
    assert all(c["embed_model"] == MODEL and c["_vectors"][EMB]["embeddings"] for c in index.docs.values())


def test_hold_blocks_new_embedding_batches(hasura, index):
    add(hasura, pages=(sentences("A", 3),))
    clock = Clock()
    indexer = ChunkIndexer(index, hasura, FakeEmbedder(), clock=clock)
    run(indexer.sync_once())
    indexer.hold(30)
    assert indexer.held and run(indexer.embed_once()) == 0
    clock.now += 31
    assert not indexer.held and run(indexer.embed_once()) == 1


def test_embedding_failure_writes_nothing(hasura, index, log_records):
    add(hasura, pages=(sentences("BIMAT", 3),))
    ai = FakeEmbedder()
    ai.fail = True
    indexer = ChunkIndexer(index, hasura, ai)
    run(indexer.sync_once())
    writes = len(index.writes)
    assert run(indexer.embed_once()) == 0 and len(index.writes) == writes
    failed = [r for r in log_records if r["event"] == "office.assist.index_failed"]
    assert failed and failed[-1]["error"] == "embed_unavailable"


def test_embedding_names():
    assert embedder_name("qwen3-embedding:0.6b") == "emb_qwen3_embedding_0_6b"
    assert embedder_name("bge-m3") == "emb_bge_m3"
    assert embedder_name("BGE-M3:567m") == "emb_bge_m3_567m"


# --- vòng nền ------------------------------------------------------------------------------------------------------


def test_meilisearch_errors_do_not_kill_the_loop(hasura, index, log_records):
    doc = add(hasura, pages=(sentences("VONGNEN", 3),))
    index.down = True
    indexer = ChunkIndexer(index, hasura, FakeEmbedder(), interval_s=0.01)

    async def scenario():
        task = asyncio.create_task(indexer.run())
        await asyncio.sleep(0.05)
        assert not task.done() and not indexer.ready
        index.down = False
        for _ in range(100):
            await asyncio.sleep(0.01)
            if of(index, doc) and all(c["embed_model"] == MODEL for c in of(index, doc).values()):
                break
        task.cancel()

    run(scenario())
    assert indexer.ready and of(index, doc)
    assert any(r["event"] == "office.assist.index_failed" for r in log_records)
    events = {r["event"] for r in log_records}
    assert {"office.assist.indexed", "office.assist.embedded"} <= events
    assert not any("VONGNEN" in json.dumps(r, ensure_ascii=False) for r in log_records)   # không ghi chữ văn bản


def test_failed_task_is_retried_on_next_round(hasura, index):
    doc = add(hasura, pages=(sentences("A", 3),))
    indexer = ChunkIndexer(index, hasura)
    run(indexer.sync_once())
    touch(hasura, doc, "2026-10-21T09:00:00+00:00", status="cancelled")
    index.fail_tasks = True
    with pytest.raises(Exception, match="lỗi"):
        run(indexer.sync_once())
    index.fail_tasks = False
    index.docs.update({c["id"]: c for kind, w in index.writes if kind == "replace" for c in w})  # tác vụ xóa đã lỗi
    run(indexer.sync_once())
    assert of(index, doc) == {}


# --- đoạn làm mô hình lỗi tất định -------------------------------------------------------------------------------


def test_a_chunk_the_model_always_rejects_is_marked_and_does_not_stall_the_rest(hasura, index, log_records):
    """Trước đây một đoạn lỗi làm cả lô thành None, lượt sau lấy lại đúng lô đó: không đoạn nào được nhúng nữa."""
    bad = add(hasura, "Văn bản độc", pages=(sentences("DOCHAI", 3),))
    for i in range(5):
        add(hasura, f"Văn bản {i}", pages=(sentences(f"BINHTHUONG{i}", 3),))
    ai = PoisonEmbedder()
    indexer = ChunkIndexer(index, hasura, ai, batch=4)
    run(indexer.sync_once())
    poisoned = set(of(index, bad))
    assert len(index.docs) > 4 and poisoned
    handled = []
    while n := run(indexer.embed_once()):
        handled.append(n)
    assert sum(handled) == len(index.docs)
    for cid, c in index.docs.items():
        if cid in poisoned:      # đánh dấu, véc-tơ giữ null: vẫn tìm được theo từ khóa
            assert c["embed_model"] == FAILED and c["_vectors"] == {EMB: None}
        else:
            assert c["embed_model"] == MODEL and c["_vectors"][EMB]["embeddings"]
    calls = len(ai.calls)
    assert run(indexer.embed_once()) == 0 and len(ai.calls) == calls        # đoạn hỏng không bị lấy lại
    assert "#failed" in index.fetches[-1]["filter"]
    skipped = [r for r in log_records if r["event"] == "office.assist.embed_skipped"]
    assert sorted(i for r in skipped for i in r["ids"]) == sorted(poisoned)
    assert not any("DOCHAI" in json.dumps(r, ensure_ascii=False) for r in log_records)


def test_a_batch_made_only_of_bad_chunks_is_marked_when_the_model_still_works(hasura, index):
    doc = add(hasura, "Văn bản độc", pages=(sentences("DOCHAI", 20), sentences("DOCHAI", 20)))
    ai = PoisonEmbedder()
    indexer = ChunkIndexer(index, hasura, ai, batch=100)
    run(indexer.sync_once())
    count = len(of(index, doc))
    assert run(indexer.embed_once()) == count > 1
    # chưa đoạn nào nhúng được: câu mẫu quyết định, một lần — sau đó mô hình đã chứng tỏ còn chạy
    assert [c["texts"] for c in ai.calls].count([CANARY]) == 1 and ai.calls[2]["texts"] == [CANARY]
    assert len(ai.calls) == 1 + count + 1
    assert all(c["embed_model"] == FAILED for c in index.docs.values())


def test_a_model_failing_on_every_input_marks_nothing(hasura, index, log_records):
    """Ollama lỗi 500 với mọi đầu vào (hết bộ nhớ, runner chết…): đoạn đầu lỗi, câu mẫu cũng lỗi — lỗi chung, không
    đánh dấu oan đoạn nào, dừng ngay; lượt sau thử lại."""
    add(hasura, pages=(sentences("A", 20), sentences("B", 20)))
    ai = PoisonEmbedder()
    ai.down = "http 500"
    indexer = ChunkIndexer(index, hasura, ai, batch=3)
    run(indexer.sync_once())
    writes = len(index.writes)
    assert run(indexer.embed_once()) == 0 and len(index.writes) == writes
    assert len(ai.calls) == 3 and ai.calls[-1]["texts"] == [CANARY]      # cả lô, đoạn đầu, câu mẫu
    failed = [r for r in log_records if r["event"] == "office.assist.index_failed"]
    assert failed[-1]["error"] == "embed_unavailable" and failed[-1]["reason"] == "http 500"
    ai.down = None
    while run(indexer.embed_once()):
        pass
    assert all(c["embed_model"] == MODEL for c in index.docs.values())


@pytest.mark.parametrize("reason", ["timeout", "unavailable", "model_unavailable", "http 503", "dims_mismatch"])
def test_transient_failures_mark_nothing_and_are_not_retried_chunk_by_chunk(hasura, index, reason):
    add(hasura, pages=(sentences("A", 20), sentences("B", 20)))
    ai = PoisonEmbedder()
    ai.down = reason
    indexer = ChunkIndexer(index, hasura, ai, batch=3)
    run(indexer.sync_once())
    writes = len(index.writes)
    assert run(indexer.embed_once()) == 0
    assert len(ai.calls) == 1 and len(index.writes) == writes
    ai.down = None
    while run(indexer.embed_once()):
        pass
    assert all(c["embed_model"] == MODEL for c in index.docs.values())


def test_a_question_stops_the_chunk_by_chunk_retry(hasura, index):
    add(hasura, "Văn bản độc", pages=(sentences("DOCHAI", 20), sentences("B", 20)))
    clock = Clock()
    ai = PoisonEmbedder()
    indexer = ChunkIndexer(index, hasura, ai, batch=100, clock=clock)
    run(indexer.sync_once())
    ai.on_fail = lambda: indexer.hold(30)           # lượt hỏi tới đúng lúc lô vừa lỗi
    writes = len(index.writes)
    assert run(indexer.embed_once()) == 0 and len(ai.calls) == 1 and len(index.writes) == writes
    ai.on_fail = None
    clock.now += 31
    assert run(indexer.embed_once()) == len(index.docs)


def test_failed_chunks_are_embedded_again_when_their_text_changes(hasura, index):
    doc = add(hasura, "Văn bản độc", pages=(sentences("DOCHAI", 3),), at=EARLY)
    add(hasura, "Văn bản khác", pages=(sentences("X", 2),))       # đẩy con trỏ lên 08:00
    indexer = ChunkIndexer(index, hasura, PoisonEmbedder(), batch=100)
    run(indexer.sync_once())
    run(indexer.embed_once())
    assert all(c["embed_model"] == FAILED for c in of(index, doc).values())
    link_ = hasura.documents[doc]["files"][0]
    link_["file"]["text"] = {**text(sentences("DASUA", 3)), "extracted_at": "2026-10-21T08:10:00+00:00"}
    run(indexer.sync_once())                                       # đổi chữ: thay đoạn, embed_model về null
    assert run(indexer.embed_once()) == len(of(index, doc))
    assert all(c["embed_model"] == MODEL and c["_vectors"][EMB]["embeddings"] for c in of(index, doc).values())


def test_failed_chunks_are_embedded_again_with_another_model(hasura, index):
    add(hasura, "Văn bản độc", pages=(sentences("DOCHAI", 3),))
    old = ChunkIndexer(index, hasura, PoisonEmbedder(), batch=100)
    run(old.sync_once())
    run(old.embed_once())
    assert all(c["embed_model"] == FAILED for c in index.docs.values())
    new = ChunkIndexer(index, hasura, FakeEmbedder("bge-m3"), batch=100)
    run(new.sync_once())
    assert run(new.embed_once()) == len(index.docs)
    assert all(c["embed_model"] == "bge-m3" for c in index.docs.values())


def test_counts_chunks_waiting_for_and_failing_embedding(hasura, index):
    add(hasura, "Văn bản độc", pages=(sentences("DOCHAI", 3),))
    add(hasura, pages=(sentences("A", 20), sentences("B", 3)))
    indexer = ChunkIndexer(index, hasura, PoisonEmbedder(), batch=100)
    run(indexer.count())
    assert (indexer.embed_pending, indexer.embed_failed) == (None, None)       # chưa áp cấu hình
    run(indexer.sync_once())
    run(indexer.count())
    assert (indexer.embed_pending, indexer.embed_failed) == (len(index.docs), 0)
    run(indexer.embed_once())
    run(indexer.count())
    failed = sum(c["embed_model"] == FAILED for c in index.docs.values())
    assert failed and (indexer.embed_pending, indexer.embed_failed) == (0, failed)
    no_model = ChunkIndexer(FakeChunkIndex(), hasura)
    run(no_model.sync_once())
    run(no_model.count())
    assert (no_model.embed_pending, no_model.embed_failed) == (None, None)


def test_the_loop_counts_after_each_round(hasura, index):
    add(hasura, pages=(sentences("A", 3),))
    indexer = ChunkIndexer(index, hasura, FakeEmbedder(available=False), interval_s=0.01)

    async def scenario():
        task = asyncio.create_task(indexer.run())
        for _ in range(100):
            await asyncio.sleep(0.01)
            if indexer.embed_pending:
                break
        task.cancel()

    run(scenario())
    assert indexer.embed_pending == len(index.docs) and indexer.embed_failed == 0


# --- mọi tác vụ của một lượt đồng bộ -------------------------------------------------------------------------------


def test_every_task_of_a_round_must_succeed_before_the_cursor_moves(hasura, index):
    """Trước đây chỉ đợi tác vụ cuối: tác vụ trước lỗi mà tác vụ cuối xong thì con trỏ vẫn tiến, văn bản của trang lỗi
    không được đọc lại tới lần nó đổi sau."""
    first, second = sorted(add(hasura, f"Văn bản {i}", pages=(sentences(f"V{i}", 2),)) for i in range(2))
    indexer = ChunkIndexer(index, hasura, page=1)
    index.failed_tasks.add(3)    # 1: cấu hình từ khóa · 2: embedder · 3: thay đoạn trang 1 · 4: thay đoạn trang 2
    with pytest.raises(SearchError, match="Tác vụ 3"):
        run(indexer.sync_once())
    assert index.waited == [1, 2]                     # đợi từng tác vụ theo thứ tự, dừng ở tác vụ lỗi
    assert indexer.cursor is None and not indexer.ready
    for cid in list(of(index, first)):
        del index.docs[cid]       # tác vụ 3 lỗi: Meilisearch không ghi gì
    index.failed_tasks.clear()
    run(indexer.sync_once())      # đọc lại từ đầu, ghi lại văn bản của trang lỗi
    assert of(index, first) and of(index, second) and indexer.ready


# --- cấu hình embedder lỗi ---------------------------------------------------------------------------------------


def test_embedder_settings_failure_does_not_block_keyword_sync(hasura, index, log_records):
    """Trước đây cấu hình (gồm cả embedder) lỗi thì sync_once không bao giờ chạy, kể cả phần xóa đoạn."""
    clock = Clock()
    doc = add(hasura, pages=(sentences("A", 3),))
    keep = add(hasura, "Văn bản khác", pages=(sentences("B", 3),))
    index.embedder_fails = True
    ai = FakeEmbedder()
    indexer = ChunkIndexer(index, hasura, ai, clock=clock)
    run(indexer.sync_once())
    assert indexer.ready and not indexer.embedder_ready and of(index, doc) and of(index, keep)
    assert all("_vectors" not in c for c in index.docs.values())    # không gửi tên embedder Meilisearch chưa có
    assert run(indexer.embed_once()) == 0 and ai.calls == []
    failed = [r for r in log_records if r["event"] == "office.assist.index_failed"]
    assert failed[-1]["stage"] == "embedder" and failed[-1]["embedder"] == EMB

    touch(hasura, doc, "2026-10-21T08:05:00+00:00", status="cancelled")
    run(indexer.sync_once())                                       # vẫn xóa đúng lúc
    assert of(index, doc) == {} and of(index, keep)
    assert len(index.failed_tasks) == 1                            # chưa tới lúc thử lại cấu hình embedder

    index.embedder_fails = False
    clock.now += EMBEDDER_RETRY_S + 1
    run(indexer.sync_once())
    assert indexer.embedder_ready and index.settings[-1]["embedder"] == EMB
    assert run(indexer.embed_once()) == len(of(index, keep))
    assert all(c["embed_model"] == MODEL and c["_vectors"][EMB]["embeddings"] for c in of(index, keep).values())
