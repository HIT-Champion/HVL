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

// Ngữ cảnh việc trên trang văn bản (#235): đích nút quay lại chỉ nhận đúng "inbox", tóm tắt phần việc của người xem;
// trang và hộp việc nối đúng các phần này.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const { documentBackTarget, processingBrief } = await import('../app/utils/taskContext.ts')
const source = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf8')

test('quay lại hộp việc chỉ khi mở từ hộp việc; tham số lạ về sổ văn bản theo chiều', () => {
  assert.equal(documentBackTarget('inbox', 'in'), '/')
  assert.equal(documentBackTarget('inbox', 'out'), '/')
  for (const from of ['https://example.com', '//example.com', '/admin', '', null, undefined, ['inbox']]) {
    assert.equal(documentBackTarget(from, 'in'), '/van-ban-den', String(from))
  }
  assert.equal(documentBackTarget(undefined, 'out'), '/van-ban-di')
  assert.equal(documentBackTarget(undefined, undefined), '/van-ban-den')
})

const base = () => [
  { id: 'dept', parent_id: null, user_id: null, instruction: 'Rà soát dự thảo kèm theo', due_on: '2026-11-01',
    status: 'open', assigned_by: 'director' },
  { id: 'own', parent_id: 'dept', user_id: 'staff', instruction: 'Gửi bản rà soát cho tổ trưởng', due_on: '2026-10-30',
    status: 'open', assigned_by: 'manager' },
  { id: 'other', parent_id: 'dept', user_id: 'other', instruction: 'Việc của người khác', due_on: null,
    status: 'open', assigned_by: 'manager' },
  { id: 'old', parent_id: null, user_id: 'staff', instruction: 'Việc đã xong', due_on: null,
    status: 'done', assigned_by: 'director' },
]

test('tóm tắt gộp chỉ đạo của phòng rồi của người giao, hạn của lượt giao cho mình', () => {
  assert.deepEqual(processingBrief(base(), 'staff'), {
    instructions: ['Rà soát dự thảo kèm theo', 'Gửi bản rà soát cho tổ trưởng'],
    dueOn: '2026-10-30',
    assignedBy: 'manager',
  })
})

test('chỉ đạo trùng, dòng trống bỏ; không có hạn riêng thì lấy hạn của phòng, rồi hạn văn bản', () => {
  const list = base()
  list[1]!.instruction = '  Rà soát dự thảo kèm theo '
  list[1]!.due_on = null
  const brief = processingBrief(list, 'staff', '2026-12-31')!
  assert.deepEqual(brief.instructions, ['Rà soát dự thảo kèm theo'])
  assert.equal(brief.dueOn, '2026-11-01')
  list[0]!.due_on = null
  list[0]!.instruction = '   '
  assert.equal(processingBrief(list, 'staff', '2026-12-31')!.dueOn, '2026-12-31')
  assert.deepEqual(processingBrief(list, 'staff')!.instructions, ['Rà soát dự thảo kèm theo'])
})

test('không đăng nhập, không được giao, việc đã xong hay đã huỷ thì không có tóm tắt', () => {
  assert.equal(processingBrief(base(), undefined), null)
  assert.equal(processingBrief(base(), 'not-assigned'), null)
  assert.equal(processingBrief(base().filter((a) => a.id !== 'own'), 'staff'), null)
  const cancelled = base().filter((a) => a.id !== 'old')
  cancelled[1]!.status = 'cancelled'
  assert.equal(processingBrief(cancelled, 'staff'), null)
})

test('hộp việc mở văn bản kèm ?from=inbox, giữ ô tìm và bộ lọc khi quay lại; trang dùng đích và tóm tắt', () => {
  assert.match(source('../app/components/TaskQueueItem.vue'), /query: \{ from: 'inbox' \}/)
  const inbox = source('../app/pages/index.vue')
  for (const key of ['inbox-query', 'inbox-filter', 'inbox-category']) {
    assert.match(inbox, new RegExp(`useState<[^>]+>\\('${key}'`))
  }
  const page = source('../app/pages/van-ban/[id].vue')
  assert.match(page, /documentBackTarget\(route\.query\.from, doc\.value\?\.direction\)/)
  assert.match(page, /:brief="brief"/)
  assert.match(source('../app/components/TaskPanel.vue'), /data-testid="processing-brief"/)
})
