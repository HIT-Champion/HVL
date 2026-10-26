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

// #306: mọi chữ giao diện của Bảng tin đi qua bảng dịch public/i18n.js, như #267 làm cho Văn phòng điện tử. Cùng
// cách kiểm với apps/ca-nhan/tests/i18n.test.js.
// Kiểm bằng regex và một bộ tách chuỗi đơn giản (đủ cho mã của ứng dụng này: không có regex chứa dấu nháy, không có
// template lồng template), không phải trình phân tích JavaScript hay HTML đầy đủ:
//   * chuỗi viết thẳng trong public/*.js, trừ i18n.js, không có chữ tiếng Việt có dấu (chú thích được);
//   * chữ tĩnh của index.html chỉ nằm ở phần tử mang data-i18n hay thuộc tính có data-i18n-<thuộc tính>, và trùng
//     bản tiếng Việt của khóa đó;
//   * khóa t('…') viết thẳng và nhãn loại tin (LOAI) có trong bảng, khóa nào của bảng cũng được dùng;
//   * vi và en cùng khóa, cùng tham số {x}; bản tiếng Anh không còn chữ tiếng Việt (trừ tên nút "Tiếng Việt").

import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'

import {
  MESSAGES, STORAGE_KEY, locale, localize, pickLocale, saveLocale, savedLocale, setLocale, t,
} from '../public/i18n.js'
import { LOAI, dong, loiTaiTin } from '../public/tin.js'

const PUBLIC = new URL('../public/', import.meta.url)
const ROOT = new URL('../../../', import.meta.url)
const scripts = readdirSync(PUBLIC).filter((f) => f.endsWith('.js')).sort()
  .map((file) => ({ file, text: readFileSync(new URL(file, PUBLIC), 'utf8') }))
const html = readFileSync(new URL('index.html', PUBLIC), 'utf8').replace(/<!--[\s\S]*?-->/g, '')

// chữ cái tiếng Việt có dấu, như apps/office/tests/i18n.test.ts
const VIET = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/iu
const LITERAL = /(?<![\w$.])t\(\s*(['"`])([\w.-]+)\1/g
const DYNAMIC = /(?<![\w$.])t\(\s*`([^`$]*)\$\{/g
const PARAMS = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()
const collapse = (text) => text.replace(/\s+/g, ' ').trim()

/** Chuỗi viết thẳng (nháy đơn, nháy kép, backtick) kèm số dòng; bỏ qua chú thích. */
function literals(text) {
  const out = []
  let line = 1
  let i = 0
  while (i < text.length) {
    if (text.startsWith('//', i)) {
      i = text.indexOf('\n', i)
      if (i < 0) break
    } else if (text.startsWith('/*', i)) {
      const end = text.indexOf('*/', i + 2) + 2
      line += text.slice(i, end).split('\n').length - 1
      i = end
    } else if (`'"\``.includes(text[i])) {
      const quote = text[i]
      const start = line
      let j = i + 1
      while (j < text.length && text[j] !== quote) {
        if (text[j] === '\n') line += 1
        j += text[j] === '\\' ? 2 : 1
      }
      out.push({ line: start, value: text.slice(i + 1, j) })
      i = j + 1
    } else {
      if (text[i] === '\n') line += 1
      i += 1
    }
  }
  return out
}

test('chuỗi trong mã không có chữ tiếng Việt viết thẳng, ngoài bảng dịch', () => {
  const found = []
  for (const { file, text } of scripts.filter((s) => s.file !== 'i18n.js')) {
    for (const { line, value } of literals(text)) if (VIET.test(value)) found.push(`${file}:${line}: ${value}`)
  }
  assert.deepEqual(found, [])
  // bộ tách thấy được chuỗi: tin.js có câu GraphQL
  assert.ok(literals(scripts.find((s) => s.file === 'tin.js').text).some((l) => l.value.includes('bang_tin_tin')))
})

test('chữ tĩnh của index.html nằm trong bảng dịch, trùng bản tiếng Việt', () => {
  const vi = MESSAGES.vi
  let rest = html.replace(/<(\w+)\b([^>]*)>([^<]*)<\/\1>/g, (all, tag, attrs, text) => {
    const key = attrs.match(/\sdata-i18n="([^"]+)"/)?.[1]
    if (!key) return all
    assert.equal(collapse(text), vi[key], `<${tag} data-i18n="${key}">`)
    return `<${tag}${attrs}></${tag}>`
  })
  // phần tử mang data-i18n chỉ chứa chữ (localize gán textContent): mọi data-i18n đã được kiểm ở trên
  assert.equal((rest.match(/\sdata-i18n="/g) ?? []).length, (html.match(/\sdata-i18n="/g) ?? []).length)
  assert.equal([...rest.matchAll(/<(\w+)\b[^>]*\sdata-i18n="[^"]+"[^>]*>[^<]/g)].length, 0)
  rest = rest.replace(/<\w+\b[^>]*>/g, (tag) => {
    let out = tag
    for (const [, attr, key] of tag.matchAll(/\sdata-i18n-([\w-]+)="([^"]+)"/g)) {
      const value = tag.match(new RegExp(`\\s${attr}="([^"]*)"`))
      assert.ok(value, `${tag}: thiếu ${attr}`)
      assert.equal(value[1], vi[key], `${attr} của ${tag}`)
      out = out.replace(value[0], ` ${attr}=""`)
    }
    return out
  })
  assert.doesNotMatch(rest, VIET)
  // nút đổi ngôn ngữ ghi "English" bằng tiếng Anh khi trang đang là tiếng Việt
  assert.match(html, /<button id="doi-ngon-ngu" type="button"[^>]*\slang="en"[^>]*>English<\/button>/)
})

test('khóa dùng trong mã và trong trang có trong bảng; khóa nào của bảng cũng được dùng', () => {
  const keys = Object.keys(MESSAGES.vi)
  // nhãn loại tin: dong() gọi t(LOAI[kind]); tin.test.js kiểm LOAI đủ các loại ứng dụng nghe
  const used = new Set(Object.values(LOAI))
  for (const key of used) assert.ok(Object.hasOwn(MESSAGES.vi, key), `LOAI: ${key}`)
  const prefixes = []
  for (const { file, text } of scripts) {
    for (const [, , key] of text.matchAll(LITERAL)) {
      assert.ok(Object.hasOwn(MESSAGES.vi, key), `${file}: t('${key}')`)
      used.add(key)
    }
    for (const [, prefix] of text.matchAll(DYNAMIC)) {
      assert.ok(keys.some((k) => k.startsWith(prefix)), `${file}: t(\`${prefix}\${…}\`)`)
      prefixes.push(prefix)
    }
  }
  for (const [, key] of html.matchAll(/\sdata-i18n(?:-[\w-]+)?="([^"]+)"/g)) {
    assert.ok(Object.hasOwn(MESSAGES.vi, key), `index.html: ${key}`)
    used.add(key)
  }
  assert.deepEqual(prefixes, [])
  assert.deepEqual(keys.filter((k) => !used.has(k)), [])
})

test('vi và en cùng khóa, cùng tham số; bản tiếng Anh không còn chữ tiếng Việt', () => {
  assert.deepEqual(Object.keys(MESSAGES.en).sort(), Object.keys(MESSAGES.vi).sort())
  for (const [key, vi] of Object.entries(MESSAGES.vi)) {
    const en = MESSAGES.en[key]
    assert.ok(vi.trim() && en.trim(), key)
    assert.deepEqual(PARAMS(en), PARAMS(vi), key)
    if (key !== 'lang.switch') assert.doesNotMatch(en, VIET, key)
  }
  assert.deepEqual([MESSAGES.vi['lang.switch'], MESSAGES.vi['lang.other']], ['English', 'en'])
  assert.deepEqual([MESSAGES.en['lang.switch'], MESSAGES.en['lang.other']], ['Tiếng Việt', 'vi'])
})

test('ngôn ngữ lưu chung khóa với Văn phòng điện tử; chỉ "en" là tiếng Anh, mặc định tiếng Việt', () => {
  const office = readFileSync(new URL('apps/office/app/plugins/i18n.ts', ROOT), 'utf8')
  assert.ok(office.includes(`localStorage.getItem('${STORAGE_KEY}')`), 'khóa lưu khác Văn phòng điện tử')
  assert.equal(pickLocale('en'), 'en')
  for (const v of ['vi', 'EN', 'fr', '', null, undefined]) assert.equal(pickLocale(v), 'vi')
  const saved = new Map()
  const storage = () => ({ getItem: (k) => saved.get(k) ?? null, setItem: (k, v) => saved.set(k, v) })
  assert.equal(savedLocale(storage), 'vi')
  saveLocale('en', storage)
  assert.deepEqual([...saved], [['moc.locale', 'en']])
  assert.equal(savedLocale(storage), 'en')
  // trình duyệt chặn localStorage (đọc thuộc tính cũng ném lỗi): tiếng Việt, không ném ra ngoài
  const blocked = () => { throw new Error('SecurityError') }
  assert.equal(savedLocale(blocked), 'vi')
  assert.doesNotThrow(() => saveLocale('en', blocked))
  assert.equal(locale(), 'vi')
})

test('localize gán chữ, thuộc tính và <html lang> theo ngôn ngữ đang dùng', () => {
  const node = (attrs) => ({
    attributes: Object.entries(attrs).map(([name, value]) => ({ name, value })),
    textContent: '',
    set: {},
    setAttribute(name, value) { this.set[name] = value },
  })
  const button = node({ id: 'doi-ngon-ngu', 'data-i18n': 'lang.switch', 'data-i18n-lang': 'lang.other' })
  const nav = node({ 'data-i18n-aria-label': 'nav.office' })
  const doc = { documentElement: { lang: 'vi' }, querySelectorAll: () => [button, nav] }
  try {
    setLocale('en')
    localize(doc)
    assert.equal(doc.documentElement.lang, 'en')
    assert.equal(button.textContent, 'Tiếng Việt')
    assert.deepEqual(button.set, { lang: 'vi' })
    assert.deepEqual(nav.set, { 'aria-label': 'e-Office' })
    setLocale('vi')
    localize(doc)
    assert.equal(doc.documentElement.lang, 'vi')
    assert.equal(button.textContent, 'English')
    assert.deepEqual(nav.set, { 'aria-label': 'Văn phòng điện tử' })
  } finally {
    setLocale('vi')
  }
})

test('tiếng Anh: nhãn loại tin, văn bản chưa có số, câu báo; tham số, khóa thiếu', () => {
  const tin = { kind: 'office.document.registered', occurred_at: '2026-10-25T07:05:00Z', document: null }
  const error = { errors: [{ message: "field 'bang_tin_tin' not found", extensions: { code: 'validation-failed' } }] }
  try {
    setLocale('en')
    assert.deepEqual(dong(tin), { loai: 'Incoming document registered', gio: '25/10/2026 14:05', so: '(no number yet)',
                                  trichYeu: '' })
    assert.equal(dong({ ...tin, kind: 'office.document.issued' }).loai, 'Outgoing document issued')
    assert.equal(dong({ ...tin, kind: 'constructor' }).loai, 'constructor')
    assert.match(loiTaiTin(error, 200), /^This account cannot read the news board\./)
    assert.equal(loiTaiTin({}, 503), 'HTTP 503')
    assert.equal(t('status.loadFailed', { error: 'HTTP 503' }), 'Could not load the news board: HTTP 503')
  } finally {
    setLocale('vi')
  }
  assert.equal(dong(tin).loai, 'Văn bản đến đã vào sổ')
  assert.equal(t('status.loadFailed'), 'Không tải được bảng tin: {error}')
  assert.equal(t('khong.co'), 'khong.co')
  assert.equal(t('constructor'), 'constructor')
})
