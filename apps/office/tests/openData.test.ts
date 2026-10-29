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


// Nguồn dữ liệu công khai: đọc khóa open_data của GET /api/status, nhận ra văn bản nạp từ nguồn qua SHA-256 của tệp,
// hỏi /api/status một lần cho nhiều trang văn bản.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const { OPEN_DATA_TTL_MS, hexOf, loadOpenData, openDataOf, publicOrigin, safeUrl } =
  await import('../app/utils/openData.ts')

type Messages = { [key: string]: string | Messages }
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const vi = JSON.parse(read('../app/locales/vi.json')) as Messages
const en = JSON.parse(read('../app/locales/en.json')) as Messages
const statusPage = read('../app/pages/trang-thai.vue')
const docPage = read('../app/pages/van-ban/[id].vue')

function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}

const HASH_A = 'a'.repeat(64)
const HASH_B = 'b'.repeat(64)

const gazette = {
  source: 'cong-bao-gddt',
  name: 'Văn bản Bộ GD&ĐT trên Công báo',
  publisher: 'Văn phòng Chính phủ',
  home_url: 'https://congbao.chinhphu.vn/',
  reuse_basis: 'Luật Tiếp cận thông tin 2016, Điều 17',
  licence: null,
  fetched_at: '2026-10-29T20:00:00Z',
  age_days: 1,
  max_age_days: 30,
  state: 'ok',
  files: [{
    file: '08-2026-TT-BGDDT.pdf',
    url: 'https://congbao.chinhphu.vn/tai-ve/08.pdf',
    sha256: HASH_A,
    fetched_at: '2026-10-29T20:01:00Z',
    meta: { symbol: '08/2026/TT-BGDĐT', page_url: 'https://congbao.chinhphu.vn/van-ban/08', gazette: 'Số 1201 + 1202' },
  }],
}

const holidays = {
  source: 'ngay-nghi-le', name: 'Ngày nghỉ lễ', publisher: 'Bộ Nội vụ', home_url: 'https://moha.gov.vn/',
  reuse_basis: 'Luật Tiếp cận thông tin 2016', licence: 'CC BY 4.0', fetched_at: '2026-09-01T00:00:00Z',
  age_days: 59, max_age_days: 45, state: 'stale',
  files: [{ file: 'ngay-nghi-2026.json', url: 'https://moha.gov.vn/x.json', sha256: HASH_B, fetched_at: '', meta: {} }],
}

test('open_data: máy chủ cũ không có khóa, hay trả gì lạ, thì là danh sách rỗng', () => {
  assert.deepEqual(openDataOf(null), [])
  assert.deepEqual(openDataOf({}), [])
  assert.deepEqual(openDataOf({ open_data: 'x' }), [])
  assert.deepEqual(openDataOf({ open_data: [null, 1, {}, { name: 'thiếu mã nguồn' }] }), [])
})

test('open_data: đọc đủ trường, trường thiếu thành chuỗi rỗng, trạng thái lạ coi như hỏng', () => {
  const [a, b] = openDataOf({ open_data: [gazette, holidays] })
  assert.equal(a!.source, 'cong-bao-gddt')
  assert.equal(a!.licence, null)
  assert.equal(a!.files[0]!.meta.gazette, 'Số 1201 + 1202')
  assert.equal(b!.licence, 'CC BY 4.0')
  assert.equal(b!.state, 'stale')

  const [c] = openDataOf({ open_data: [{ source: 'x', state: 'unknown', age_days: -3.7, max_age_days: 'n', files: [
    { file: 'thiếu băm' }, { sha256: HASH_A, meta: ['không phải đối tượng'] },
  ] }] })
  assert.equal(c!.name, 'x')
  assert.equal(c!.publisher, '')
  assert.equal(c!.state, 'broken')
  assert.equal(c!.age_days, 0)
  assert.equal(c!.max_age_days, 0)
  assert.equal(c!.files.length, 1)
  assert.deepEqual(c!.files[0]!.meta, {})
})

test('liên kết ra ngoài chỉ nhận http(s)', () => {
  assert.equal(safeUrl('https://congbao.chinhphu.vn/van-ban/08'), 'https://congbao.chinhphu.vn/van-ban/08')
  assert.equal(safeUrl('http://example.org'), 'http://example.org/')
  assert.equal(safeUrl('javascript:alert(1)'), null)
  assert.equal(safeUrl('data:text/html,x'), null)
  assert.equal(safeUrl('/tuong-doi'), null)
  assert.equal(safeUrl(42), null)
})

test('văn bản nạp từ nguồn: tệp trùng SHA-256 (Hasura trả "\\x…"), lấy trang gốc và số Công báo', () => {
  const sources = openDataOf({ open_data: [gazette, holidays] })
  const origin = publicOrigin([null, `\\x${HASH_A.toUpperCase()}`], sources)
  assert.equal(origin!.source.source, 'cong-bao-gddt')
  assert.equal(origin!.link, 'https://congbao.chinhphu.vn/van-ban/08')
  assert.equal(origin!.gazette, 'Số 1201 + 1202')
  assert.equal(origin!.fetched_at, '2026-10-29T20:01:00Z')

  // không có trang gốc thì dùng địa chỉ tải tệp; tệp không có ngày lấy thì dùng ngày lấy của nguồn
  const other = publicOrigin([HASH_B], sources)
  assert.equal(other!.link, 'https://moha.gov.vn/x.json')
  assert.equal(other!.gazette, '')
  assert.equal(other!.fetched_at, '2026-09-01T00:00:00Z')

  assert.equal(publicOrigin(['c'.repeat(64)], sources), null)
  assert.equal(publicOrigin([], sources), null)
})

test('nguồn hỏng không gắn nhãn; liên kết javascript: trong manifest không thành liên kết', () => {
  const broken = openDataOf({ open_data: [{ ...gazette, state: 'broken' }] })
  assert.equal(publicOrigin([HASH_A], broken), null)

  const bad = openDataOf({ open_data: [{ ...gazette, files: [{ ...gazette.files[0], url: 'javascript:x',
    meta: { page_url: 'javascript:alert(1)' } }] }] })
  assert.equal(publicOrigin([HASH_A], bad)!.link, null)
})

test('SHA-256 hiện liền, chữ thường, không tiền tố', () => {
  assert.equal(hexOf(`\\x${HASH_A.toUpperCase()}`), HASH_A)
  assert.equal(hexOf(` ${HASH_B} `), HASH_B)
  assert.equal(hexOf(null), '')
})

test('hỏi /api/status một lần trong 5 phút; tải lỗi thì lần sau hỏi lại', async () => {
  let calls = 0
  let fail = true
  let clock = 1_000_000_000_000
  const now = () => clock
  const get = async (url: string) => {
    calls += 1
    assert.equal(url, '/api/status')
    if (fail) return { ok: false, json: async () => ({}) }
    return { ok: true, json: async () => ({ open_data: [gazette] }) }
  }

  assert.deepEqual(await loadOpenData(get, now), [])
  assert.equal(calls, 1)
  fail = false
  const first = await loadOpenData(get, now)
  assert.equal(calls, 2)
  assert.equal(first.length, 1)

  // trong hạn: dùng lại, kể cả hai trang mở cùng lúc
  clock += OPEN_DATA_TTL_MS - 1
  const [x, y] = await Promise.all([loadOpenData(get, now), loadOpenData(get, now)])
  assert.equal(calls, 2)
  assert.equal(x, first)
  assert.equal(y, first)

  clock += 1
  await loadOpenData(get, now)
  assert.equal(calls, 3)

  // lỗi mạng (fetch ném lỗi) cũng không giữ lại
  clock += OPEN_DATA_TTL_MS
  assert.deepEqual(await loadOpenData(async () => { throw new TypeError('offline') }, now), [])
  await loadOpenData(get, now)
  assert.equal(calls, 4)
})

test('khóa i18n của hai mục có đủ ở vi.json và en.json, kể cả ba trạng thái nguồn', () => {
  let checked = 0
  for (const source of [statusPage, docPage]) {
    for (const m of source.matchAll(/\bt\('((?:health\.openData|doc\.publicSource)\.[\w.]+)'/g)) {
      assert.ok(lookup(vi, m[1]!) !== undefined, `vi: thiếu khóa ${m[1]}`)
      assert.ok(lookup(en, m[1]!) !== undefined, `en: thiếu khóa ${m[1]}`)
      checked++
    }
  }
  assert.ok(checked >= 20, `chỉ thấy ${checked} khóa`)
  for (const s of ['ok', 'stale', 'broken']) {
    assert.ok(lookup(vi, `health.openData.state.${s}`) && lookup(en, `health.openData.state.${s}`), s)
  }
})

test('trang Trạng thái: mục nguồn chỉ hiện khi máy chủ trả nguồn; liên kết qua safeUrl, mở tab mới', () => {
  assert.match(statusPage, /v-if="sources\.length"[^>]*data-testid="status-open-data"/)
  assert.match(statusPage, /:href="safeUrl\(s\.home_url\)!" target="_blank" rel="noopener"/)
  assert.doesNotMatch(statusPage, /:href="s\./)
})

test('trang văn bản: nhãn nguồn chỉ cho văn bản đến, liên kết lấy từ publicOrigin, danh sách nguồn hỏi một lần', () => {
  assert.match(docPage, /doc\.value && !outgoing\.value\s+\? publicOrigin\(/)
  assert.match(docPage, /<section v-if="origin"[^>]*data-testid="public-source"/)
  assert.match(docPage, /:href="origin\.link" target="_blank" rel="noopener"/)
  assert.match(docPage, /loadOpenData\(\(url\) => fetch\(url, \{ cache: 'no-store' \}\)\)/)
})
