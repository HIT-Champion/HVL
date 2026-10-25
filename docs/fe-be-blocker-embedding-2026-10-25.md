# FE ↔ AI integration blocker — 25/10/2026

<!-- Copyright 2026 Signet Team -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Status: awaiting BE resolution. User explicitly chose **record the error and wait for BE**, rather than rebuilding
any local index. Do not delete, rebuild, patch or manually repair the AI search index without new authorization.

## Reproduction and observed state

- Upstream source: `origin/develop` `f9abff0`; unchanged `services/`, `db/`, `platform/`, `schemas/`, `scripts/`.
- Local Compose project `signet-fe-local`, seeded document database and existing keyword `chunks` index.
- Official pinned Ollama image and default models pulled successfully on retry. Models match documented IDs:
  `qwen3:1.7b` → `8f68893c685c`, `qwen3-embedding:0.6b` → `ac6da0dfba84`.
- Enabled existing AI runtime settings in ignored local `.env`; recreated `svc-files`, without source changes.
- Ollama lists both models loaded (generation context 4096, embedding context 2048).
- `svc-files` logs `office.assist.index_failed`, stage `embedder`. Meilisearch rejects configuring
  `emb_qwen3_embedding_0_6b` with `source: userProvided` because pre-existing chunk documents have no vectors.
  Error code: `vector_embedding_error`; the log reports one document and at least 38 others.

Meilisearch's diagnostic says user-provided embedding documents need `_vectors.<embedder>` arrays or an explicit null
opt-out. This is evidence for BE diagnosis, not a change made by FE.

## Expected behavior

Enabling the documented default AI profile on a previously seeded keyword-only deployment should migrate/reindex
safely, reach semantic readiness and allow FE end-to-end verification of hybrid retrieval and generated answers.
The existing document database and original files must be preserved.

## Impact on FE acceptance

Keyword/extract Q&A remains available. Semantic retrieval and complete AI integration are **not accepted** until BE
resolves the index transition and readiness plus actual browser answers can be verified. A loaded model alone does
not prove application integration. Frontend must continue to display the actual mode/warnings and preserve sources.

No BE/AI source patch, index rebuild or external issue/message was made. Evidence logs remain in the ignored
`.cache/latest-review/ai-model-pull-retry.log` and local service logs. Do not publish `.env` or private test sessions.


Continuation note: upstream advanced from f9abff0 to f86970f. The latter snapshot was imported unchanged, including
Flowable optimistic-lock retries, scoped PKCE WAF exclusions, and future sensor-clock flags. It does not fix the
existing-index embedding transition. The user decision to wait for BE on that blocker remains in force.
