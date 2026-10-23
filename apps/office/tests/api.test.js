// Copyright 2026 Signet Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { useApi, ApiError } from '../app/composables/useApi.js';

test('API integration: existing archive reads coexist with the AI endpoints and bearer auth', async (t) => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({ url, init });
    return Response.json({ ok: true });
  });
  const previous = globalThis.useAuth;
  globalThis.useAuth = () => ({ accessToken: async () => 'local-test-token' });
  t.after(() => { if (previous) globalThis.useAuth = previous; else delete globalThis.useAuth; });
  const api = useApi();
  await api.readArchive('case-123');
  await api.readFile('file-123', true);
  await api.ask({ question: 'Thời hạn xử lý là khi nào?', mode: 'extract' });
  assert.deepEqual(calls.map(c => c.url), [
    '/api/case-files/case-123/archive', '/api/files/file-123/read?force=true', '/api/documents/ask',
  ]);
  assert.ok(calls.every(c => c.init.headers.Authorization === 'Bearer local-test-token'));
  assert.equal(calls[1].init.method, 'POST');
  assert.equal(calls[2].init.method, 'POST');
  assert.equal(JSON.parse(calls[2].init.body).mode, 'extract');
});

test('API integration: restricted read error retains the server reason for the UI', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(
    { detail: { code: 'restricted', reason: 'private', message: 'Restricted file' } }, { status: 409 },
  ));
  const previous = globalThis.useAuth;
  globalThis.useAuth = () => ({ accessToken: async () => 'local-test-token' });
  t.after(() => { if (previous) globalThis.useAuth = previous; else delete globalThis.useAuth; });
  await assert.rejects(useApi().readFile('private-file'), e => e instanceof ApiError &&
    e.code === 'restricted' && e.status === 409 && e.reason === 'private');
});
