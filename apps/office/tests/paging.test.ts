// Copyright 2026 Mộc Team
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


// "Xem thêm" ở danh sách văn bản đến, đi khi danh sách đổi giữa hai lần lấy (review: offset làm lặp, sót dòng).

import assert from 'node:assert/strict'
import { test } from 'node:test'

const { mergePage, nextPage } = await import('../app/utils/paging.ts')

const docs = (from: number, to: number) => Array.from({ length: to - from }, (_, i) => ({ id: `d${from + i}` }))
// giả lập máy chủ: danh sách hiện tại, cắt theo offset/limit như Hasura
const serve = (list: { id: string }[], shown: number) => {
  const { offset, limit } = nextPage(shown)
  return list.slice(offset, offset + limit)
}

test('trang đầu lấy 51 dòng, hiện 50, còn nữa', () => {
  assert.deepEqual(nextPage(0), { offset: 0, limit: 51 })
  const first = mergePage([], serve(docs(0, 120), 0))
  assert.equal(first.rows.length, 50)
  assert.equal(first.more, true)
})

test('văn bản mới chen lên đầu giữa hai lần lấy: không lặp dòng, không sót', () => {
  let list = docs(0, 120)
  const first = mergePage([], serve(list, 0))
  list = [{ id: 'moi-1' }, { id: 'moi-2' }, ...list]
  const second = mergePage(first.rows, serve(list, first.rows.length))
  const ids = second.rows.map((r) => r.id)
  assert.equal(new Set(ids).size, ids.length)
  assert.deepEqual(ids, docs(0, ids.length).map((d) => d.id))   // nối tiếp liền mạch d0, d1…
  assert.ok(second.more && ids.length > 90)
})

test('văn bản rời tab giữa hai lần lấy: dòng kế tiếp vẫn hiện', () => {
  let list = docs(0, 120)
  const first = mergePage([], serve(list, 0))
  list = list.filter((d) => !['d3', 'd10', 'd49'].includes(d.id))   // ba văn bản đã xong, rời tab "đang xử lý"
  const second = mergePage(first.rows, serve(list, first.rows.length))
  const ids = second.rows.map((r) => r.id)
  assert.ok(ids.includes('d50') && ids.includes('d51'))
  assert.equal(new Set(ids).size, ids.length)
})

test('trang cuối: hết thì không còn nút Xem thêm', () => {
  const list = docs(0, 60)
  const first = mergePage([], serve(list, 0))
  const second = mergePage(first.rows, serve(list, first.rows.length))
  assert.equal(second.rows.length, 60)
  assert.equal(second.more, false)
})
