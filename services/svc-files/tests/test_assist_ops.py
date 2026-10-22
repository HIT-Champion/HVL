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

"""Vận hành trợ lý hỏi đáp (F4.2): ``/readyz`` phần ``assist`` báo đúng khi cấu hình hay chỉ mục có vấn đề — sai số
chiều véc-tơ, embedder chưa áp được, đoạn chờ nhúng / bị đánh dấu hỏng — và cảnh báo cấu hình lúc khởi động. Không
gọi mạng: chỉ mục đoạn, Ollama, mô hình trích yếu đều là đồ giả."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from assist_fakes import DIMS, EMBED_MODEL, FakeIndexer, FakeOllama, ollama
from conftest import ISSUER, TENANT_A, FakeChunkIndex
from svc_files.app import create_app
from svc_files.assist.ai import NullAi
from svc_files.assist.index import ChunkIndexer
from svc_files.config import Settings
from svc_files.docread.reader import Reader
from svc_files.docread.summarize import NullSummarizer
from test_assist_chunks import link, sentences, text

ENV = {
    "MOC_OIDC_ISSUER": ISSUER, "MOC_OIDC_JWKS_URL": "http://unused/jwks", "SEAWEEDFS_S3_ACCESS_KEY": "test",
    "SEAWEEDFS_S3_SECRET_KEY": "test", "HASURA_ADMIN_SECRET": "test", "MEILISEARCH_API_KEY": "test",
    "MOC_SEARCH_SYNC_INTERVAL_S": "0", "MOC_AUDIT_ANCHOR_INTERVAL_S": "0", "MOC_TEXT_INTERVAL_S": "0",
    "MOC_ARCHIVE_INTERVAL_S": "0", "MOC_FILES_MAX_MB": "1", "MOC_AI_URL": "", "MOC_AI_EMBED_DIMS": str(DIMS),
}


def assist_ready(deps, settings: Settings, **kw) -> dict:
    """``/readyz`` → phần ``assist`` của một app có trợ lý (vòng nền, Ollama, mô hình trích yếu tiêm vào)."""
    scanner, store, verifier, hasura, meili, vault = deps
    reader = Reader(settings, hasura, store, summarizer=NullSummarizer())
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=hasura, meili=meili,
                     vault=vault, reader=reader, **kw)
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["status"] == "ready"      # assist không bao giờ đổi sẵn sàng
    return r.json()["assist"]


@pytest.fixture
def deps(scanner, store, verifier, hasura, meili, vault) -> tuple:
    return scanner, store, verifier, hasura, meili, vault


def test_wrong_embedding_dimensions_show_on_readyz(deps):
    settings = Settings.from_env(ENV)
    ok = assist_ready(deps, settings, ai=ollama(FakeOllama(models=[EMBED_MODEL])), chunk_indexer=FakeIndexer())
    assert ok["semantic"] is True
    wrong = assist_ready(deps, settings, ai=ollama(FakeOllama(models=[EMBED_MODEL], dims=DIMS * 2)),
                         chunk_indexer=FakeIndexer())
    assert wrong["semantic"] is False and wrong["index"] is True


def test_readyz_shows_embedder_failure_and_backlog(deps, hasura):
    for i in range(2):
        hasura.add_document(TENANT_A, f"Văn bản {i}", files=[link(text(sentences(f"V{i}", 3)), file_id=f"f-{i}")],
                            assignments=[], updated_at="2026-10-21T08:00:00+00:00")
    index = FakeChunkIndex(embedder_fails=True)
    ai = ollama(FakeOllama(models=[EMBED_MODEL]))
    indexer = ChunkIndexer(index, hasura, ai, dims=DIMS, interval_s=3600)
    asyncio.run(indexer.sync_once())
    asyncio.run(indexer.count())
    got = assist_ready(deps, Settings.from_env(ENV), ai=ai, chunk_indexer=indexer)
    # mô hình nhúng sẵn sàng nhưng Meilisearch chưa có embedder: chưa tìm theo nghĩa được; đoạn vẫn vào chỉ mục
    assert got == {"index": True, "semantic": False, "model": False, "embed_pending": len(index.docs),
                   "embed_failed": 0}


def test_three_models_for_two_ollama_slots_are_logged_at_startup(deps, log_records):
    settings = Settings.from_env({**ENV, "MOC_AI_URL": "http://ollama:11434", "MOC_ASK_MODEL": "qwen3:4b"})
    assist_ready(deps, settings, ai=NullAi(), chunk_indexer=FakeIndexer())
    (warning,) = [r for r in log_records if r["event"] == "config.warning"]
    assert "OLLAMA_MAX_LOADED_MODELS" in warning["message"]
    log_records.clear()
    assist_ready(deps, Settings.from_env({**ENV, "MOC_AI_URL": "http://ollama:11434"}), ai=NullAi(),
                 chunk_indexer=FakeIndexer())
    assert not [r for r in log_records if r["event"] == "config.warning"]
