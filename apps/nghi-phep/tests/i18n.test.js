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

// #398: mọi chữ giao diện của Đơn nghỉ phép đi qua bảng dịch public/i18n.js, cùng cách kiểm với Bảng tin
// (apps/bang-tin/tests/i18n.test.js, #306). Kiểm bằng regex và một bộ tách chuỗi đơn giản (đủ cho mã của ứng dụng
// này: không có regex chứa dấu nháy, không có template lồng template), không phải trình phân tích JavaScript hay
// HTML đầy đủ:
//   * chuỗi viết thẳng trong public/*.js, trừ i18n.js, không có chữ tiếng Việt có dấu (chú thích được);
//   * chữ tĩnh của index.html chỉ nằm ở phần tử mang data-i18n hay thuộc tính có data-i18n-<thuộc tính>, và trùng
//     bản tiếng Việt của khóa đó;
//   * khóa t('…'), word(lang, '…') (câu chung của schema-form.js) viết thẳng và khóa câu báo theo mã trả lời (LOI)
//     có trong bảng, khóa nào của bảng cũng được dùng;
//   * vi và en cùng khóa, cùng tham số {x}; bản tiếng Anh không còn chữ tiếng Việt (trừ tên nút "Tiếng Việt");
//   * form dựng từ forms/*.json hiện nhãn, lựa chọn, gợi ý, câu báo lỗi bằng tiếng Anh khi chọn tiếng Anh.

import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'

import { LOI, docTraLoi, trangThai } from '../public/don.js'
import {
  MESSAGES, STORAGE_KEY, locale, localize, pickLocale, saveLocale, savedLocale, setLocale, t,
} from '../public/i18n.js'
import { PRIORITY, checkSchema, fields, formTitle, message, mountForm, summary } from '../public/schema-form.js'

const PUBLIC = new URL('../public/', import.meta.url)
const FORMS = new URL('../forms/', import.meta.url)
const ROOT = new URL('../../../', import.meta.url)
const scripts = readdirSync(PUBLIC).filter((f) => f.endsWith('.js')).sort()
  .map((file) => ({ file, text: readFileSync(new URL(file, PUBLIC), 'utf8') }))
const html = readFileSync(new URL('index.html', PUBLIC), 'utf8').replace(/<!--[\s\S]*?-->/g, '')
const form = (name) => JSON.parse(readFileSync(new URL(name, FORMS), 'utf8'))
const don = form('don.json')
const duyet = form('duyet.json')

// chữ cái tiếng Việt có dấu, như apps/office/tests/i18n.test.ts
const VIET = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/iu
const LITERAL = /(?<![\w$.])(?:t\(|word\(\s*lang,)\s*(['"`])([\w.-]+)\1/g
const DYNAMIC = /(?<![\w$.])(?:t\(|word\(\s*lang,)\s*`([^`$]*)\$\{/g
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
  // bộ tách thấy được chuỗi: don.js có đường API, schema-form.js có tên từ khóa
  const seen = (file, part) => literals(scripts.find((s) => s.file === file).text).some((l) => l.value.includes(part))
  assert.ok(seen('don.js', '/api/workflow/nghi-phep'))
  assert.ok(seen('schema-form.js', 'x-moc-range'))
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
  // nhãn của tab nằm trong span riêng: gán chữ không xóa số đếm (dem-don, dem-viec) bên cạnh
  for (const id of ['dem-don', 'dem-viec']) {
    assert.match(html, new RegExp(`<span data-i18n="tab\\.\\w+">[^<]+</span> <span id="${id}"`))
  }
})

test('khóa dùng trong mã và trong trang có trong bảng; khóa nào của bảng cũng được dùng', () => {
  const keys = Object.keys(MESSAGES.vi)
  // câu báo theo mã trả lời: docTraLoi() gọi t(LOI[status]), app.js gọi t(LOI.mang)
  const used = new Set(Object.values(LOI))
  for (const key of used) assert.ok(Object.hasOwn(MESSAGES.vi, key), `LOI: ${key}`)
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
  // bộ đọc thấy cả hai cách gọi
  assert.ok(used.has('state.pending') && used.has('form.required') && used.has('schema.keyword'))
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

test('ngôn ngữ lưu chung khóa với Văn phòng điện tử và các ứng dụng khác; chỉ "en" là tiếng Anh', () => {
  const office = readFileSync(new URL('apps/office/app/plugins/i18n.ts', ROOT), 'utf8')
  assert.ok(office.includes(`localStorage.getItem('${STORAGE_KEY}')`), 'khóa lưu khác Văn phòng điện tử')
  for (const app of ['bang-tin', 'ca-nhan']) {
    const other = readFileSync(new URL(`apps/${app}/public/i18n.js`, ROOT), 'utf8')
    assert.ok(other.includes(`export const STORAGE_KEY = '${STORAGE_KEY}'`), `khóa lưu khác ${app}`)
  }
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
  const tabs = node({ 'data-i18n-aria-label': 'nav.sections' })
  const doc = { documentElement: { lang: 'vi' }, querySelectorAll: () => [button, tabs] }
  try {
    setLocale('en')
    localize(doc)
    assert.equal(doc.documentElement.lang, 'en')
    assert.equal(button.textContent, 'Tiếng Việt')
    assert.deepEqual(button.set, { lang: 'vi' })
    assert.deepEqual(tabs.set, { 'aria-label': 'App sections' })
    setLocale('vi')
    localize(doc)
    assert.equal(doc.documentElement.lang, 'vi')
    assert.equal(button.textContent, 'English')
    assert.deepEqual(tabs.set, { 'aria-label': 'Các phần của ứng dụng' })
  } finally {
    setLocale('vi')
  }
})

test('tiếng Anh: trạng thái đơn, câu báo theo mã trả lời, số ngày; tham số, khóa thiếu, lang truyền thẳng', () => {
  const xong = (quyetDinh) => trangThai({ endedAt: '2026-10-26T03:00:00Z', data: { quyetDinh } }).nhan
  try {
    setLocale('en')
    assert.deepEqual(trangThai({ endedAt: null, data: {} }), { ma: 'cho', nhan: 'Awaiting department head' })
    assert.deepEqual([xong('dong-y'), xong('tu-choi'), xong(undefined)], ['Approved', 'Declined', 'Closed'])
    assert.equal(docTraLoi(401, null).message, 'Your session has expired. Reload the page to sign in again.')
    assert.equal(docTraLoi(503, null).message, 'The Signet workflow service is not responding. Try again in a few '
      + 'minutes.')
    assert.equal(docTraLoi(418, null).message, 'Signet refused the request (HTTP 418).')
    assert.equal(docTraLoi(422, { errors: { denNgay: 'x-moc-range' } }).message,
      'Some fields are not valid: see the message under each field.')
    for (const key of Object.values(LOI)) assert.doesNotMatch(t(key), VIET, key)
    assert.equal(t('notice.sentDays', { days: t('detail.dayCount', { n: 3 }) }),
      'Request for 3 days of leave sent. Your department head will review it; follow it under "My requests".')
    assert.equal(t('detail.oneDay'), '1 day')
    assert.equal(t('mine.sentAt', { time: '26/10/2026 14:05' }), 'Sent 26/10/2026 14:05')
  } finally {
    setLocale('vi')
  }
  assert.equal(xong('tu-choi'), 'Bị từ chối')
  assert.equal(docTraLoi(418, null).message, 'Signet từ chối yêu cầu (HTTP 418).')
  assert.equal(t('error.loadMine'), 'Không tải được đơn của bạn: {error}')
  assert.equal(t('khong.co'), 'khong.co')
  assert.equal(t('constructor'), 'constructor')
  // schema-form.js truyền ngôn ngữ của form: thắng ngôn ngữ đang dùng; ngôn ngữ lạ là tiếng Việt
  assert.equal(t('form.required', {}, 'en'), 'Required')
  assert.equal(t('form.required', {}, 'fr'), 'Không được để trống')
})

test('form dựng từ schema bằng tiếng Anh: nhãn, lựa chọn, gợi ý, câu báo, tóm tắt; schema hỏng theo ngôn ngữ', () => {
  // mọi chữ của tệp form và mọi câu báo theo mã đều có bản tiếng Anh, không lẫn tiếng Việt
  const codes = [...PRIORITY, 'minimum', 'maximum', 'minItems', 'const', 'duplicate']
  for (const [file, schema] of [['don.json', don], ['duyet.json', duyet]]) {
    assert.doesNotMatch(formTitle(schema, 'en'), VIET, file)
    const list = fields(schema, 'en')
    for (const f of list) {
      for (const text of [f.label, f.help, f.note, ...f.options.map((o) => o.label)]) {
        assert.doesNotMatch(text, VIET, `${file}: ${f.name}`)
      }
      for (const [code, own] of Object.entries(f.ui.errors ?? {})) assert.ok(own.en, `${file}: ${f.name} ${code}`)
      for (const code of codes) assert.doesNotMatch(message(f, code, 'en', list, schema), VIET, `${f.name} ${code}`)
    }
  }
  assert.deepEqual(fields(don, 'en').map((f) => f.label), ['Leave type', 'From', 'To', 'Reason'])
  assert.deepEqual(fields(duyet, 'en')[0].options.map((o) => o.label), ['Approve', 'Decline'])
  assert.deepEqual(summary(don, { loai: 'viec-rieng', tuNgay: '2026-10-27', denNgay: '2026-10-28' }, 'en'), [
    { name: 'loai', label: 'Leave type', value: 'Personal leave' },
    { name: 'tuNgay', label: 'From', value: '27/10/2026' },
    { name: 'denNgay', label: 'To', value: '28/10/2026' },
    { name: 'lyDo', label: 'Reason', value: '—' },
  ])
  assert.deepEqual(summary(duyet, { quyetDinh: 'dong-y', ghiChu: 'OK' }, 'en').map((r) => [r.label, r.value]),
    [['Decision', 'Approve'], ['Note', 'OK']])
  // câu chung theo ngôn ngữ của form, không theo ngôn ngữ đang dùng
  const lyDo = fields(don, 'vi').find((f) => f.name === 'lyDo')
  try {
    setLocale('en')
    assert.equal(message(lyDo, 'required', 'vi'), 'Không được để trống')
    // schema hỏng: câu theo ngôn ngữ đang dùng (trang hiện kèm "Could not load the forms")
    assert.throws(() => checkSchema({ type: 'text' }), { message: 'Schema #: type "text" does not exist' })
    assert.throws(() => checkSchema({ type: 'object', properties: { a: { oneOf: [] } } }),
      { message: 'Schema #/a: keyword oneOf is not supported' })
  } finally {
    setLocale('vi')
  }
  assert.throws(() => checkSchema({ type: 'text' }), { message: 'Schema #: kiểu "text" không có' })
  // trang dựng form và tóm tắt theo ngôn ngữ đang dùng
  const app = scripts.find((s) => s.file === 'app.js').text
  assert.match(app, /mountForm\(container, schema, \{ lang: locale\(\),/)
  assert.match(app, /summary\(schema, data, locale\(\)\)/)
})

// DOM giả vừa đủ cho mountForm (gói không có jsdom): phần tử là đối tượng thường, chữ đọc lại bằng text()
function fakeDocument() {
  const doc = {
    focused: null,
    createElement: (tag) => ({
      tag, children: [], attrs: {}, on: {}, textContent: '', ownerDocument: doc,
      append(...nodes) { this.children.push(...nodes) },
      prepend(...nodes) { this.children.unshift(...nodes) },
      replaceChildren(...nodes) { this.children = nodes },
      setAttribute(name, value) { this.attrs[name] = String(value) },
      removeAttribute(name) { delete this.attrs[name] },
      addEventListener(type, fn) { this.on[type] = fn },
      focus() { doc.focused = this },
    }),
  }
  return doc
}
const text = (node) => (typeof node === 'string' ? node : node.textContent + node.children.map(text).join(''))
const nodes = (node) => (typeof node === 'string' ? [] : [node, ...node.children.flatMap(nodes)])

test('form vẽ ra bằng tiếng Anh: nhãn, lựa chọn, lời báo khi gửi thiếu; dựng lại giữ chữ đang gõ (draft)', async () => {
  const doc = fakeDocument()
  const box = doc.createElement('div')
  const sent = []
  const handle = mountForm(box, don, { lang: 'en', idPrefix: 'don-', onSubmit: (data) => sent.push(data) })
  const byId = (id) => nodes(box).find((n) => n.id === id)
  const root = box.children[0]
  assert.equal(root.attrs['aria-label'], 'Leave request')
  assert.deepEqual(nodes(box).filter((n) => n.className === 'sf-label').map(text),
    ['Leave type', 'From', 'To', 'Reason (optional)'])
  assert.deepEqual(byId('don-loai').children.map(text),
    ['— Choose —', 'Annual leave', 'Sick leave', 'Personal leave', 'Unpaid leave'])
  assert.equal(text(byId('don-denNgay-help')), 'Inclusive. For a single day, pick the start date again.')
  assert.equal(text(nodes(box).find((n) => n.className === 'sf-submit')), 'Submit')
  // gửi form trống: câu báo tiếng Anh dưới từng ô bắt buộc, tiêu điểm về ô sai đầu tiên, không gửi gì
  await root.on.submit({ preventDefault() {} })
  assert.deepEqual(sent, [])
  for (const name of ['loai', 'tuNgay', 'denNgay']) assert.equal(text(byId(`don-${name}-error`)), 'Required')
  assert.equal(byId('don-lyDo-error').hidden, true)
  assert.equal(doc.focused, byId('don-loai'))
  // lỗi 422 của lõi, cả trường không có ô
  handle.setErrors({ denNgay: 'x-moc-range', tuNgay: 'pattern', soNgay: 'additionalProperties' })
  assert.equal(text(byId('don-denNgay-error')), 'Cannot be before "From"')
  assert.equal(text(byId('don-tuNgay-error')), 'The year must be between 2000 and 2099')
  assert.deepEqual(byId('don-:errors').children.map(text),
    ['Not sent yet. Please check:', 'soNgay: Field not in the form'])

  // form duyệt: nhóm nút chọn, nhãn nút gửi do trang đặt
  const card = doc.createElement('div')
  mountForm(card, duyet, { lang: 'en', idPrefix: 'viec-1-', submitLabel: t('review.submit', {}, 'en') })
  assert.deepEqual(nodes(card).filter((n) => n.tag === 'span' && !n.className).map(text), ['Approve', 'Decline'])
  assert.deepEqual(nodes(card).filter((n) => n.className === 'sf-label').map(text), ['Decision', 'Note (optional)'])
  assert.equal(text(nodes(card).find((n) => n.className === 'sf-submit')), 'Submit decision')

  // đổi ngôn ngữ: trang dựng lại form với draft là chữ đang gõ; reset() sau khi gửi về form trống, không về draft
  const draft = { loai: 'om', tuNgay: '2026-10-27', lyDo: 'Sốt' }
  const again = mountForm(box, don, { lang: 'vi', idPrefix: 'don-', draft })
  assert.deepEqual(again.values(), draft)
  assert.equal(byId('don-denNgay').min, '2026-10-27')
  assert.equal(text(nodes(box).find((n) => n.className === 'sf-label')), 'Loại nghỉ')
  again.reset()
  assert.deepEqual(again.values(), {})
})
