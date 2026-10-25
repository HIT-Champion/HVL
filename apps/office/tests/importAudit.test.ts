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


// Lô nạp văn bản đến (svc-files /api/imports): dòng sổ import.created / import.finished có nhãn ở cả hai bản ngôn ngữ
// — thao tác, đối tượng, mọi khóa core.audit_overview cho hiện (migration 1792281602800), loại lô — và nằm ở nhóm
// "Văn bản" của trang Sổ kiểm toán.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

type Messages = { [key: string]: string | Messages }
const load = (lang: string): Messages =>
  JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`, import.meta.url), 'utf8')) as Messages
const source = (file: string) => readFileSync(new URL(file, import.meta.url), 'utf8')

function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}

const MIGRATION = '../../../db/migrations/default/1792281602800_import_jobs/up.sql'

test('mọi khóa của sự kiện lô nạp mà sổ kiểm toán cho hiện đều có nhãn ở vi.json và en.json', () => {
  const sql = source(MIGRATION)
  const shown = /r\.action in \('import\.created', 'import\.finished'\)\s+and k in \(([^)]*)\)/.exec(sql)
  assert.ok(shown, 'migration không còn nhánh import.* của core.audit_overview')
  const cols = [...shown[1]!.matchAll(/'(\w+)'/g)].map((m) => m[1]!)
  assert.deepEqual(cols, ['kind', 'format', 'register', 'total', 'ok', 'duplicate', 'failed'])
  const keys = ['audit.action.import.created', 'audit.action.import.finished', 'audit.entity.core.import_jobs',
    'audit.importKind.incoming', ...cols.map((c) => `audit.col.${c}`)]
  for (const lang of ['vi', 'en']) {
    const messages = load(lang)
    for (const key of keys) assert.ok(lookup(messages, key), `${lang}.json thiếu ${key}`)
  }
  assert.equal(lookup(load('vi'), 'audit.action.import.finished'), 'Xong lô nạp văn bản')
})

test('loại lô hiện bằng nhãn, sự kiện lô nạp nằm ở nhóm Văn bản', () => {
  assert.match(source('../app/composables/useAuditFormat.ts'),
    /if \(col === 'kind'\) return label\('audit\.importKind', String\(value\)\)/)
  const page = source('../app/pages/so-kiem-toan.vue')
  const documents = /documents: \[([^\]]*)\]/.exec(page)
  assert.ok(documents && documents[1]!.includes("'core.import_jobs'"))
})
