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


// Cổng xác thực (F2.13) với khối chữ ký số (F4.5, chỉ minh họa): câu chữ đúng hợp đồng ở cả hai ngôn ngữ, luôn nói rõ
// không có giá trị pháp lý; chuỗi e2e tìm ("khớp từng byte", "KHÔNG khớp") giữ nguyên; khóa viết thẳng trong trang đều
// có trong vi.json / en.json; khối chữ ký nằm trong kết quả hợp lệ, văn bản không có chữ ký thì hiện câu thay thế.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

type Messages = { [key: string]: string | Messages }
const load = (lang: string): Messages =>
  JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`, import.meta.url), 'utf8')) as Messages
const vi = load('vi')
const en = load('en')

function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}
const tVi = (key: string): string => lookup(vi, key) ?? assert.fail(`thiếu khóa ${key}`)
const tEn = (key: string): string => lookup(en, key) ?? assert.fail(`thiếu khóa ${key}`)

const page = readFileSync(new URL('../app/pages/xac-thuc/[[code]].vue', import.meta.url), 'utf8')
const template = page.slice(page.indexOf('<template>'))

const SIGNATURE_KEYS = ['title', 'level', 'signer', 'ca', 'serial', 'signedAt', 'illustrative', 'none']
  .map((k) => `verify.signature.${k}`)

test('khối chữ ký số: chữ tiếng Việt đúng hợp đồng, có ở cả hai ngôn ngữ', () => {
  for (const messages of [vi, en]) for (const key of SIGNATURE_KEYS) assert.ok(lookup(messages, key), key)
  assert.equal(tVi('verify.signature.title'), 'Chữ ký số (minh họa)')
  assert.equal(tVi('verify.signature.level'), 'Chuẩn chữ ký')
  assert.equal(tVi('verify.signature.signer'), 'Ký bởi')
  assert.equal(tVi('verify.signature.ca'), 'Chứng thư do')
  assert.equal(tVi('verify.signature.serial'), 'Số sê-ri chứng thư')
  assert.equal(tVi('verify.signature.signedAt'), 'Ký lúc (giờ tự ghi trong chữ ký)')
  // không ký vì két cũ chưa có PKI hay ký lỗi lúc phát hành cũng là "không có chữ ký": câu không đoán nguyên nhân
  assert.equal(tVi('verify.signature.none'), 'Văn bản này không có chữ ký số (phát hành khi ký số chưa bật hoặc ký lỗi, '
    + 'hoặc là văn bản hạn chế). Tính nguyên vẹn vẫn kiểm bằng SHA-256 như trên.')
})

test('chú thích minh họa nói rõ không có giá trị pháp lý, không trỏ tới link tải CA (đã cắt)', () => {
  const note = tVi('verify.signature.illustrative')
  assert.match(note, /chỉ để minh họa/)
  assert.match(note, /không có giá trị pháp lý như chữ ký số công cộng/)
  assert.match(note, /chưa tin cậy/)
  assert.doesNotMatch(note, /dưới đây|\.pem/)
  const noteEn = tEn('verify.signature.illustrative')
  assert.match(noteEn, /illustration only/)
  assert.match(noteEn, /no legal standing/)
  assert.doesNotMatch(noteEn, /below|\.pem/)
  // e2e tìm "minh họa" trong khối chữ ký
  assert.match(tVi('verify.signature.title'), /minh họa/)
})

test('chuỗi e2e tìm vẫn nguyên, câu mới không chứa chúng', () => {
  assert.match(tVi('verify.match'), /khớp từng byte/)
  assert.match(tVi('verify.mismatch'), /KHÔNG khớp/)
  for (const key of SIGNATURE_KEYS) {
    assert.doesNotMatch(tVi(key), /khớp từng byte|KHÔNG khớp/, key)
  }
})

test('khóa i18n viết thẳng trong trang xác thực đều có trong vi.json và en.json', () => {
  let checked = 0
  for (const m of page.matchAll(/\bt\('([\w.-]+)'/g)) {
    assert.ok(lookup(vi, m[1]!) !== undefined, `vi: thiếu khóa ${m[1]}`)
    assert.ok(lookup(en, m[1]!) !== undefined, `en: thiếu khóa ${m[1]}`)
    checked++
  }
  assert.ok(checked >= 30, `chỉ thấy ${checked} khóa`)
  for (const key of SIGNATURE_KEYS) assert.ok(page.includes(`t('${key}')`), `trang chưa dùng ${key}`)
})

test('trang: khối chữ ký trong kết quả hợp lệ, có thì hiện chi tiết, không có thì hiện câu thay thế', () => {
  assert.match(page, /signature: VerifiedSignature \| null/)
  const valid = template.slice(template.indexOf('data-testid="verify-valid"'), template.indexOf('</section>'))
  assert.match(valid, /<div v-if="found\.signature"[^>]*data-testid="verify-signature"/)
  assert.match(valid, /<p v-else[^>]*data-testid="verify-unsigned"/)
  // khối chữ ký đứng trước kết quả so tệp
  assert.ok(valid.indexOf('verify-signature') < valid.indexOf('data-testid="verify-match"'))
  // chú thích minh họa luôn hiện cùng khối chữ ký, không phụ thuộc cờ nào khác
  const block = valid.slice(valid.indexOf('data-testid="verify-signature"'), valid.indexOf('data-testid="verify-unsigned"'))
  const at = block.indexOf("t('verify.signature.illustrative')")
  assert.ok(at > 0)
  assert.doesNotMatch(block.slice(block.lastIndexOf('<p', at), at), /v-if|v-show/)
  // giờ ký theo giờ Việt Nam như mọi trang; số sê-ri xuống dòng được
  assert.match(block, /fmtDateTime\(found\.signature\.signed_at\)/)
  assert.match(block, /break-all[^>]*>\{\{ found\.signature\.serial \}\}/)
  assert.doesNotMatch(page, /v-html/)
})
