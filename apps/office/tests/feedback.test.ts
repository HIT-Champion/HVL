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


// Góp ý (F4.6): màn hình gắn vào góp ý là khuôn đường dẫn — không id, không chuỗi truy vấn — và luôn qua được ràng
// buộc feedback_screen của CSDL (đọc thẳng regex trong migration); mọi trang sau đăng nhập có tên màn hình; điểm trung
// bình, thứ tự màn hình của trang Góp ý; nút Góp ý, mục thanh bên gắn vào khung chính; lỗi feedback_* của CSDL có câu
// ở cả hai ngôn ngữ; đủ khóa i18n cho nút và hai trang mới.

import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'
import type { FeedbackSummaryRow } from '../app/utils/feedback.ts'

const { FEEDBACK_MAX, FEEDBACK_RATINGS, averageRating, feedbackScreen, ratingCounts, screenKeys, screenLabel,
  splitSummary } = await import('../app/utils/feedback.ts')

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
const tVi = (key: string): string => lookup(vi, key) ?? `?${key}`

// Ràng buộc feedback_screen trong migration 1792281602700: giao diện và CSDL phải cùng một khuôn
const migration = read('../../../db/migrations/default/1792281602700_feedback/up.sql')
const dbPattern = migration.match(/screen ~ '([^']+)'/)?.[1]
const dbMax = Number(migration.match(/char_length\(screen\) <= (\d+)/)?.[1])
const screenOk = (s: string) => dbPattern !== undefined && new RegExp(dbPattern).test(s) && s.length <= dbMax

const UUID = '3f0c7b9e-6a1d-4e2f-9b8a-0c1d2e3f4a5b'

const row = (screen: string | null, feedback: number, total: number, extra: Partial<FeedbackSummaryRow> = {}):
  FeedbackSummaryRow => ({
  sample: false, screen, feedback, rating_total: total, rating_1: 0, rating_2: 0, rating_3: 0, rating_4: 0,
  rating_5: 0, with_comment: 0, last_at: null, ...extra,
})

test('khuôn màn hình: id, mã tra cứu thành :id; bỏ chuỗi truy vấn, dấu #, gạch chéo thừa', () => {
  assert.equal(feedbackScreen('/'), '/')
  assert.equal(feedbackScreen(''), '/')
  assert.equal(feedbackScreen('/van-ban-den/tiep-nhan'), '/van-ban-den/tiep-nhan')
  assert.equal(feedbackScreen(`/van-ban/${UUID}`), '/van-ban/:id')
  assert.equal(feedbackScreen('/tim-kiem?q=001205000017'), '/tim-kiem')   // số CCCD gõ vào ô tìm không đi theo
  assert.equal(feedbackScreen('/so-do#bang'), '/so-do')
  assert.equal(feedbackScreen('/van-ban-den/'), '/van-ban-den')
  assert.equal(feedbackScreen('/xac-thuc/ABCDEFGH23'), '/xac-thuc/:id')
  assert.equal(feedbackScreen('/Van-Ban-Den'), '/:id')                     // chữ hoa không phải tên trang
  assert.equal(feedbackScreen('/tim-kiem/%C4%91'), '/tim-kiem/:id')
})

test('khuôn màn hình: tối đa 6 đoạn, 80 ký tự', () => {
  assert.equal(feedbackScreen('/a/b/c/d/e/f/g'), '/a/b/c/d/e/f')
  const long = `/${Array.from({ length: 6 }, () => 'a'.repeat(20)).join('/')}`
  assert.equal(feedbackScreen(long), `/${Array.from({ length: 3 }, () => 'a'.repeat(20)).join('/')}`)
  assert.equal(feedbackScreen(`/${'a'.repeat(100)}`), '/')
  for (const path of [long, '/a/b/c/d/e/f/g', `/${'a'.repeat(100)}`]) assert.ok(feedbackScreen(path).length <= 80)
})

test('mọi khuôn giao diện gửi đi đều qua ràng buộc feedback_screen của CSDL', () => {
  assert.ok(dbPattern, 'không tìm thấy regex của feedback_screen trong migration')
  assert.equal(dbMax, 80)
  const paths = ['/', '', '/van-ban-den/tiep-nhan', `/van-ban/${UUID}`, '/tim-kiem?q=001205000017', '/so-do#bang',
    '/xac-thuc/ABCDEFGH23', '/Van-Ban-Den', '/a/b/c/d/e/f/g', `/${'a'.repeat(100)}`, '/a-/b--c/-d', '/123/456',
    `/${Array.from({ length: 6 }, () => 'a'.repeat(20)).join('/')}`, '/tim-kiem/%C4%91', '//van-ban//den//']
  for (const path of paths) assert.ok(screenOk(feedbackScreen(path)), `${path} → ${feedbackScreen(path)}`)
  // CSDL vẫn chặn những thứ giao diện không bao giờ gửi
  for (const bad of ['/tim-kiem?q=1', `/van-ban/${UUID}`, '/Van-Ban', '/van-ban-den/', '/a/b/c/d/e/f/g', '']) {
    assert.equal(screenOk(bad), false, bad)
  }
})

test('mọi trang sau đăng nhập có khuôn hợp lệ và có tên màn hình', () => {
  const pagesDir = new URL('../app/pages/', import.meta.url)
  const route = (file: string) => {
    const path = file.replace(/\\/g, '/').replace(/\.vue$/, '').replace(/(^|\/)index$/, '').replace(/\[(\w+)\]/g, ':$1')
    return `/${path}`.replace(/\/$/, '') || '/'
  }
  const routes = (readdirSync(pagesDir, { recursive: true }) as string[])
    .filter((f) => f.endsWith('.vue'))
    .filter((f) => !/layout: (false|'public')/.test(readFileSync(new URL(f, pagesDir), 'utf8')))
    .map(route)
  assert.ok(routes.length >= 13, `chỉ thấy ${routes.length} trang`)
  for (const route of routes) {
    assert.ok(screenOk(route), route)
    assert.notEqual(screenLabel(tVi, route), route, `${route} chưa có tên màn hình`)
  }
  assert.ok(routes.includes('/van-ban/:id') && routes.includes('/so-do') && routes.includes('/gop-y'))
})

test('tên màn hình: theo thanh bên, khuôn lạ hiện nguyên, null là mọi màn hình', () => {
  assert.equal(screenLabel(tVi, '/'), 'Hộp việc')
  assert.equal(screenLabel(tVi, '/van-ban/:id'), 'Chi tiết văn bản')
  assert.equal(screenLabel(tVi, '/so-do'), 'Số đo')
  assert.equal(screenLabel(tVi, '/trang-moi'), '/trang-moi')
  assert.equal(screenLabel(tVi, null), 'Mọi màn hình')
})

test('điểm trung bình: không góp ý nào thì không có điểm (không phải 0)', () => {
  assert.equal(averageRating(null), null)
  assert.equal(averageRating(undefined), null)
  assert.equal(averageRating(row(null, 0, 0)), null)
  assert.equal(averageRating(row(null, 4, 14)), 3.5)
  assert.deepEqual(ratingCounts(row('/', 6, 20, { rating_1: 1, rating_3: 2, rating_5: 3 })), [1, 0, 2, 0, 3])
  assert.deepEqual([...FEEDBACK_RATINGS], [1, 2, 3, 4, 5])
  assert.equal(FEEDBACK_MAX, 500)
})

test('tổng hợp: dòng mọi màn hình tách riêng; nhiều góp ý trước, bằng nhau thì điểm thấp trước', () => {
  const rows = [row('/', 2, 9), row('/tim-kiem', 2, 3), row(null, 7, 17), row('/so-do', 1, 5), row('/gop-y', 2, 3)]
  const { total, screens } = splitSummary(rows)
  assert.equal(total?.feedback, 7)
  assert.deepEqual(screens.map((r) => r.screen), ['/gop-y', '/tim-kiem', '/', '/so-do'])
  assert.deepEqual(splitSummary([]), { total: null, screens: [] })
})

test('nút Góp ý ở thanh trên cho mọi vai trò; Số đo chỉ cho lãnh đạo đơn vị; Góp ý ở cuối thanh bên', () => {
  const layout = read('../app/layouts/default.vue')
  assert.match(layout, /<FeedbackButton v-if="claims\?\.role" \/>/)
  assert.match(layout, /if \(role === 'director'\) items\.push\(\{ to: '\/so-do', label: t\('nav\.metrics'\)/)
  assert.match(layout, /if \(role\) items\.push\(\{ to: '\/gop-y', label: t\('nav\.feedback'\)/)
  assert.ok(layout.indexOf("to: '/gop-y'") > layout.indexOf("to: '/so-kiem-toan'"))
  // trang Số đo tự chặn vai trò khác (Hasura từ chối khung nhìn số đo, trang báo rõ thay vì báo lỗi)
  const metricsPage = read('../app/pages/so-do.vue')
  assert.match(metricsPage, /const allowed = computed\(\(\) => claims\.value\?\.role === 'director'\)/)
})

test('lỗi feedback_* của CSDL có câu ở cả hai ngôn ngữ; không tên lỗi nào nằm trong tên khác', () => {
  const errors = read('../app/utils/errors.ts')
  const listed = errors.match(/const CONSTRAINTS = \[([^\]]+)\]/)?.[1] ?? ''
  const names = [...listed.matchAll(/'(\w+)'/g)].map((m) => m[1]!)
  for (const name of ['feedback_rate', 'feedback_rating', 'feedback_comment', 'feedback_screen']) {
    assert.ok(names.includes(name), name)
  }
  for (const a of names) for (const b of names) if (a !== b) assert.ok(!a.includes(b), `${a} chứa ${b}`)
  for (const messages of [vi, en]) for (const name of names) assert.ok(lookup(messages, `error.${name}`), name)
  // ràng buộc và lỗi chặn gửi dồn trong migration đúng là các tên này; câu lỗi raise mang tên lỗi, Hasura trả
  // "Check constraint violation. feedback_rate: …" nên errorText tìm được tên trong câu
  for (const name of ['feedback_rating', 'feedback_comment', 'feedback_screen']) {
    assert.match(migration, new RegExp(`constraint ${name}\\s+check`))
  }
  assert.match(migration, /raise exception 'feedback_rate: /)
})

test('khóa i18n của nút Góp ý, trang Góp ý, trang Số đo và tên màn hình có ở cả vi.json và en.json', () => {
  const files = ['../app/components/FeedbackButton.vue', '../app/pages/gop-y.vue', '../app/pages/so-do.vue',
    '../app/utils/feedback.ts', '../app/layouts/default.vue']
  let checked = 0
  for (const file of files) {
    for (const m of read(file).matchAll(/\bt\('([\w.-]+)'/g)) {
      assert.ok(lookup(vi, m[1]!) !== undefined, `vi: ${file} thiếu khóa ${m[1]}`)
      assert.ok(lookup(en, m[1]!) !== undefined, `en: ${file} thiếu khóa ${m[1]}`)
      checked++
    }
  }
  assert.ok(checked > 120, `chỉ thấy ${checked} khóa`)
  for (const key of screenKeys()) assert.ok(lookup(vi, key) && lookup(en, key), key)
})

test('câu chữ không hứa ẩn danh, nhắc không ghi thông tin cá nhân', () => {
  for (const key of ['feedback.anonymous', 'feedback.mineHint']) {
    assert.doesNotMatch(lookup(vi, key)!, /ẩn danh/i)
    assert.doesNotMatch(lookup(en, key)!, /anonymous/i)
  }
  assert.match(lookup(vi, 'feedback.anonymous')!, /^Không hiện người gửi/)
  assert.match(lookup(vi, 'feedback.privacy')!, /họ tên.*CCCD.*số điện thoại/)
  assert.match(read('../app/components/FeedbackButton.vue'), /t\('feedback\.privacy'\)/)
  // form góp ý không có ô nào khác ngoài mức và nội dung: màn hình tự gắn, không hỏi tên, email, số điện thoại
  const button = read('../app/components/FeedbackButton.vue')
  const send = button.match(/insert_office_feedback_one\(object: \{([^}]+)\}/)?.[1]
  assert.equal(send?.replace(/\s+/g, ' ').trim(), 'rating: $r, comment: $c, screen: $s')
})
