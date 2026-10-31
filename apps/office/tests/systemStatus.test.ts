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


// Trang trạng thái hệ thống (/trang-thai, công khai): nhóm thành phần theo tầng đúng thứ tự API, chuỗi thời gian chạy
// và giờ kiểm theo giờ Việt Nam, đủ khóa i18n ở cả hai ngôn ngữ cho mọi mã svc-files trả, trang không cần đăng nhập,
// chỉ gọi /api/status không kèm token, tự làm mới mỗi 30 giây; chân trang công khai và trang đăng nhập lỗi trỏ tới
// trang.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

process.env.TZ = 'America/Los_Angeles'   // máy ở múi giờ khác: giờ kiểm vẫn theo giờ Việt Nam
const { STATUS_REFRESH_MS, fmtClock, fmtUptime, groupByLayer } = await import('../app/utils/systemStatus.ts')

type Messages = { [key: string]: string | Messages }
const load = (lang: string): Messages =>
  JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`, import.meta.url), 'utf8')) as Messages
const vi = load('vi')
const en = load('en')
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}

const page = read('../app/pages/trang-thai.vue')
const layout = read('../app/layouts/public.vue')

// như svc-files trả (status.py: LAYERS, default_board)
const LAYERS = [['nguoi-dung', 'Người dùng'], ['loi', 'Lõi'], ['quy-trinh', 'Quy trình'], ['du-lieu', 'Dữ liệu'],
  ['tri-tue', 'Trí tuệ nhân tạo']].map(([id, label]) => ({ id: id!, label: label! }))
const COMPONENTS: [string, string, string][] = [
  ['cong-api', 'nguoi-dung', 'Cổng API'], ['dang-nhap', 'nguoi-dung', 'Đăng nhập một lần'], ['csdl', 'loi', 'CSDL'],
  ['ket-khoa', 'loi', 'Két khóa'], ['quet-ma-doc', 'loi', 'Quét mã độc'], ['quy-trinh', 'quy-trinh', 'Quy trình'],
  ['luu-tru', 'du-lieu', 'Lưu trữ tệp'], ['tim-kiem', 'du-lieu', 'Tìm kiếm'], ['tro-ly-ai', 'tri-tue', 'Trợ lý AI'],
]
const component = ([id, layer, label]: [string, string, string]) =>
  ({ id, layer, label, software: 'X', status: 'ok' as const })

test('nhóm theo tầng đúng thứ tự người dùng → lõi → quy trình → dữ liệu → trí tuệ nhân tạo', () => {
  const groups = groupByLayer({ layers: LAYERS, components: [...COMPONENTS].reverse().map(component) })
  assert.deepEqual(groups.map((g) => g.id), ['nguoi-dung', 'loi', 'quy-trinh', 'du-lieu', 'tri-tue'])
  assert.deepEqual(groups[1]!.components.map((c) => c.id).sort(), ['csdl', 'ket-khoa', 'quet-ma-doc'])
})

test('tầng không có thành phần thì ẩn; thành phần mang tầng lạ vẫn hiện, ở cuối', () => {
  const groups = groupByLayer({
    layers: LAYERS,
    components: [component(['csdl', 'loi', 'CSDL']), component(['moi', 'tang-moi', 'Thành phần mới'])],
  })
  assert.deepEqual(groups.map((g) => [g.id, g.label]), [['loi', 'Lõi'], ['tang-moi', 'tang-moi']])
})

test('thời gian chạy: hai đơn vị lớn nhất khác 0', () => {
  const units = { day: 'ngày', hour: 'giờ', minute: 'phút', less: 'dưới 1 phút' }
  assert.equal(fmtUptime(0, units), 'dưới 1 phút')
  assert.equal(fmtUptime(59.9, units), 'dưới 1 phút')
  assert.equal(fmtUptime(60, units), '1 phút')
  assert.equal(fmtUptime(5 * 3600 + 12 * 60 + 7, units), '5 giờ 12 phút')
  assert.equal(fmtUptime(3 * 86_400 + 4 * 3600 + 59 * 60, units), '3 ngày 4 giờ')
  assert.equal(fmtUptime(2 * 86_400 + 30 * 60, units), '2 ngày')            // không ghép giờ bằng 0 với phút
  assert.equal(fmtUptime(-5, units), 'dưới 1 phút')
})

test('giờ kiểm theo giờ Việt Nam, 24 giờ, có giây', () => {
  assert.equal(fmtClock('2026-10-23T01:02:03+00:00'), '08:02:03')
  assert.equal(fmtClock('2026-10-23T17:30:00Z'), '00:30:00')
})

test('mọi mã svc-files trả có nhãn ở cả hai ngôn ngữ; nhãn tiếng Việt trùng nhãn của API', () => {
  for (const messages of [vi, en]) {
    for (const [id] of COMPONENTS) assert.ok(lookup(messages, `health.component.${id}`), id)
    for (const { id } of LAYERS) assert.ok(lookup(messages, `health.layer.${id}`), id)
    for (const s of ['ok', 'degraded', 'down', 'off']) assert.ok(lookup(messages, `health.state.${s}`), s)
    for (const s of ['ok', 'degraded', 'down']) {
      assert.ok(lookup(messages, `health.overall.${s}`), s)
      assert.ok(lookup(messages, `health.overallHint.${s}`), s)
    }
  }
  for (const [id, , label] of COMPONENTS) assert.equal(lookup(vi, `health.component.${id}`), label)
  for (const { id, label } of LAYERS) assert.equal(lookup(vi, `health.layer.${id}`), label)
  assert.equal(lookup(vi, 'health.title'), 'Trạng thái hệ thống')
})

test('khóa i18n viết thẳng trong trang và khung công khai đều có trong vi.json và en.json', () => {
  let checked = 0
  for (const source of [page, layout]) {
    for (const m of source.matchAll(/\bt\('([\w.-]+)'/g)) {
      assert.ok(lookup(vi, m[1]!) !== undefined, `vi: thiếu khóa ${m[1]}`)
      assert.ok(lookup(en, m[1]!) !== undefined, `en: thiếu khóa ${m[1]}`)
      checked++
    }
  }
  assert.ok(checked >= 25, `chỉ thấy ${checked} khóa`)
  assert.match(page, /publicTitle: 'health\.title'/)
  assert.ok(lookup(vi, 'health.title') && lookup(en, 'health.title'))
})

test('trang công khai: khung public, không qua đăng nhập, chỉ gọi /api/status không kèm token', () => {
  assert.match(page, /definePageMeta\(\{ layout: 'public'/)
  assert.doesNotMatch(page, /useApi|useAuth|Authorization|gql\(/)
  assert.match(page, /fetch\('\/api\/status', \{ cache: 'no-store' \}\)/)
  assert.doesNotMatch(page, /v-html/)
  const middleware = read('../app/middleware/auth.global.ts')
  const open = middleware.indexOf("=== '/trang-thai') return")
  assert.ok(open > 0 && open < middleware.indexOf('useAuth()'),
    'middleware phải cho /trang-thai qua trước khi hỏi đăng nhập')
})

test('tự làm mới mỗi 30 giây khi tab đang mở, dọn bộ đếm khi rời trang; 429 giữ kết quả cũ', () => {
  assert.equal(STATUS_REFRESH_MS, 30_000)
  assert.match(page, /setInterval\(\(\) => \{ if \(!document\.hidden\) load\(\) \}, STATUS_REFRESH_MS\)/)
  assert.match(page, /onBeforeUnmount\(\(\) => \{\s*clearInterval\(timer\)/)
  assert.match(page, /res\.status === 429\) throw new Error\(t\('health\.rateLimited'\)\)/)
  // lỗi không xóa dữ liệu đang hiện
  const failed = page.slice(page.indexOf('} catch (e) {'), page.indexOf('} finally {'))
  assert.doesNotMatch(failed, /data\.value =/)
})

test('đường tới trang: chân trang công khai, trang đăng nhập lỗi, thanh bên sau đăng nhập', () => {
  assert.match(layout, /<NuxtLink to="\/trang-thai"[^>]*>\{\{ t\('health\.title'\) \}\}<\/NuxtLink>/)
  assert.match(layout, /<NuxtLink to="\/xac-thuc"/)
  // và từ trang công khai về trang chủ: logo và nút "Trang chủ" ở thanh trên
  assert.match(layout, /<NuxtLink to="\/" class="moc-public-wordmark/)
  assert.match(layout, /<NuxtLink to="\/"[^>]*>\{\{ t\('nav\.home'\) \}\}<\/NuxtLink>/)
  assert.match(read('../app/pages/dang-nhap.vue'), /<NuxtLink to="\/trang-thai"/)
  assert.match(read('../app/layouts/default.vue'), /<NuxtLink to="\/trang-thai"/)
})
