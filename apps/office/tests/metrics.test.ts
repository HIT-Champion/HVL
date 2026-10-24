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


// Trang Số đo (F4.6, đặc tả §8): chọn văn bản cũ để bấm giờ tìm lại, thứ hạng, trung vị; tỷ lệ quá hạn không bịa 0 %
// khi chưa có văn bản nào; dòng mọi tháng, các tháng; khoảng thời gian hiện được cả giây (dữ liệu mẫu); cờ dữ liệu mẫu.
// Cột "trước" của cả bốn dòng là "chưa đo", dòng số bước chuyển tay không có số nào.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import type { OverdueRow, SearchRun } from '../app/utils/metrics.ts'

const { SEARCH_RUNS, fmtDuration, fmtMs, isSample, median, monthRows, overduePct, pickSearchTargets, rankOf,
  searchSummary, totalRow } = await import('../app/utils/metrics.ts')

type Messages = { [key: string]: string | Messages }
const load = (lang: string): Messages =>
  JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`, import.meta.url), 'utf8')) as Messages
const vi = load('vi')
const en = load('en')
const page = readFileSync(new URL('../app/pages/so-do.vue', import.meta.url), 'utf8')

function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}

const UNITS = { second: 'giây', minute: 'phút', hour: 'giờ', day: 'ngày' }
const overdue = (judged: number, late: number, month: string | null = null): OverdueRow =>
  ({ sample: false, month, judged, on_time: judged - late, late, late_open: 0, pending: 0 })
const run = (id: string, ms: number, rank: number | null): SearchRun => ({ id, symbol: `${id}/UBND`, ms, rank })

test('văn bản cần tìm lại: theo thứ tự đã xếp, mỗi số ký hiệu một lần, bỏ văn bản không có số ký hiệu', () => {
  const docs = [
    { id: 'a', symbol: '01/UBND-VP' }, { id: 'b', symbol: null }, { id: 'c', symbol: ' 01/UBND-VP ' },
    { id: 'd', symbol: '  ' }, { id: 'e', symbol: '15/SGDĐT' }, { id: 'f', symbol: '7/ĐHCN' },
    { id: 'g', symbol: '88/CTSV' }, { id: 'h', symbol: '3/TB' }, { id: 'i', symbol: '9/KH' },
  ]
  assert.equal(SEARCH_RUNS, 5)
  assert.deepEqual(pickSearchTargets(docs), [
    { id: 'a', symbol: '01/UBND-VP' }, { id: 'e', symbol: '15/SGDĐT' }, { id: 'f', symbol: '7/ĐHCN' },
    { id: 'g', symbol: '88/CTSV' }, { id: 'h', symbol: '3/TB' },
  ])
  assert.equal(pickSearchTargets(docs, 2).length, 2)
  assert.equal(pickSearchTargets(docs.slice(0, 4)).length, 1)    // ít hơn 5: trang báo thiếu, không bịa thêm
})

test('thứ hạng của văn bản cần tìm: 1 là đầu, không thấy là null', () => {
  const hits = [{ id: 'x' }, { id: 'a' }, { id: 'y' }]
  assert.equal(rankOf(hits, 'x'), 1)
  assert.equal(rankOf(hits, 'a'), 2)
  assert.equal(rankOf(hits, 'z'), null)
  assert.equal(rankOf([], 'a'), null)
})

test('trung vị: lẻ, chẵn, rỗng; không đổi mảng gốc', () => {
  const values = [30, 10, 20]
  assert.equal(median(values), 20)
  assert.deepEqual(values, [30, 10, 20])
  assert.equal(median([40, 10, 30, 20]), 25)
  assert.equal(median([7]), 7)
  assert.equal(median([]), null)
})

test('tổng kết các lần tìm: trung vị, chậm nhất, số lần thấy', () => {
  assert.deepEqual(searchSummary([run('a', 40, 1), run('b', 12, 3), run('c', 25, null), run('d', 18, 1),
    run('e', 90, 2)]), { runs: 5, found: 4, median_ms: 25, max_ms: 90 })
  assert.deepEqual(searchSummary([]), { runs: 0, found: 0, median_ms: null, max_ms: null })
})

test('tỷ lệ quá hạn: chưa có văn bản nào đã rõ thì không có tỷ lệ (không phải 0 %)', () => {
  assert.equal(overduePct(null), null)
  assert.equal(overduePct(undefined), null)
  assert.equal(overduePct(overdue(0, 0)), null)
  assert.equal(overduePct(overdue(4, 0)), 0)
  assert.equal(overduePct(overdue(5, 3)), 60)
})

test('dòng mọi tháng tách riêng; các tháng mới trước, tối đa 12', () => {
  const months = Array.from({ length: 14 }, (_, i) => overdue(1, 0, `2025-${String((i % 12) + 1).padStart(2, '0')}-01`))
    .map((r, i) => (i >= 12 ? { ...r, month: `2026-0${i - 11}-01` } : r))
  const rows = [overdue(9, 2), ...months]
  assert.equal(totalRow(rows)?.judged, 9)
  assert.equal(totalRow(months), null)
  const shown = monthRows(rows)
  assert.equal(shown.length, 12)
  assert.deepEqual(shown.slice(0, 3).map((r) => r.month), ['2026-02-01', '2026-01-01', '2025-12-01'])
  assert.ok(shown.every((r) => r.month !== null))
  assert.equal(monthRows(rows, 2).length, 2)
})

test('khoảng thời gian: giây, phút, giờ, ngày; không có số thì gạch', () => {
  assert.equal(fmtDuration(0, UNITS), '0 giây')
  assert.equal(fmtDuration(3 / 3600, UNITS), '3 giây')        // dữ liệu mẫu: giao xử lý sau vài giây
  assert.equal(fmtDuration(0.5, UNITS), '30 phút')
  assert.equal(fmtDuration(1, UNITS), '1 giờ')
  assert.equal(fmtDuration(19.25, UNITS), '19.3 giờ')
  assert.equal(fmtDuration(47.9, UNITS), '47.9 giờ')
  assert.equal(fmtDuration(72, UNITS), '3 ngày')
  assert.equal(fmtDuration(-2, UNITS), '0 giây')               // không hiện số âm
  for (const missing of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(fmtDuration(missing, UNITS), '—')
  }
  assert.equal(fmtDuration(1.5, UNITS, (n) => n.toFixed(2).replace('.', ',')), '1,50 giờ')
  assert.equal(fmtMs(12.4), '12 ms')
  assert.equal(fmtMs(null), '—')
})

test('cờ dữ liệu mẫu: chỉ cần một dòng của một khung nhìn', () => {
  assert.equal(isSample([], []), false)
  assert.equal(isSample([{ sample: false }], [{ sample: false }]), false)
  assert.equal(isSample([{ sample: false }], [{ sample: true }]), true)
})

test('bảng bốn chỉ số: cột Trước luôn "chưa đo"; dòng số bước chuyển tay chỉ so sánh định tính, không có số', () => {
  assert.equal([...page.matchAll(/t\('metrics\.notMeasured'\)/g)].length, 4)
  for (const id of ['metrics-assign', 'metrics-overdue', 'metrics-search', 'metrics-handoffs']) {
    assert.ok(page.includes(`data-testid="${id}"`), id)
  }
  const handoffs = page.match(/data-testid="metrics-handoffs">([\s\S]*?)<\/tr>/)?.[1] ?? ''
  assert.deepEqual([...handoffs.matchAll(/\{\{\s*([^}]+?)\s*\}\}/g)].map((m) => m[1]), [
    "t('metrics.handoffs.name')", "t('metrics.notMeasured')", "t('metrics.handoffs.value')",
    "t('metrics.handoffs.how')"])
  for (const messages of [vi, en]) {
    assert.doesNotMatch(lookup(messages, 'metrics.handoffs.value')!, /\d/)
    assert.doesNotMatch(lookup(messages, 'metrics.notMeasured')!, /\d/)
  }
  assert.match(lookup(vi, 'metrics.notMeasured')!, /^Chưa đo/)
  assert.match(lookup(vi, 'metrics.search.how')!, /độ trễ hệ thống/)
  assert.match(lookup(vi, 'metrics.sampleNote')!, /dữ liệu mẫu/)
})

test('trang Số đo: tìm lần lượt, không song song; văn bản hạn chế, đã hủy không vào danh sách tìm', () => {
  assert.match(page, /for \(const target of targets\) \{\s*const started = performance\.now\(\)\s*const res = await/)
  assert.doesNotMatch(page, /Promise\.all/)
  assert.match(page, /restricted: \{_eq: false\}/)
  assert.match(page, /status: \{_neq: "cancelled"\}/)
  assert.match(page, /order_by: \[\{created_at: asc\}, \{id: asc\}\]/)
})
