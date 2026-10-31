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

// Form dựng từ schema (public/schema-form.js), phần không cần trình duyệt. Bộ kiểm phải cho đúng mã lỗi trên mọi ca
// thử: schemas/*.cases.json (Ajv của Văn phòng, svc-workflow, CSDL cũng chạy) và forms/*.cases.json của ứng dụng.
// Phía máy chủ của forms/*.cases.json đến cùng #301 (x-moc-range trong FormSchema, test Python đọc
// apps/*/forms/*.cases.json); trước đó gọi thẳng API vẫn nhận đến ngày trước từ ngày. Kèm kiểm tệp form: đủ nhãn
// hai thứ tiếng, thứ tự ô đủ.

import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'

import {
  PRIORITY, checkSchema, clean, fields, formErrors, formTitle, message, summary, todayVN,
} from '../public/schema-form.js'

const SHARED = new URL('../../../schemas/', import.meta.url)
const FORMS = new URL('../forms/', import.meta.url)
const TODAY = '2026-10-19'
const json = (base, name) => JSON.parse(readFileSync(new URL(name, base), 'utf8'))

// Giá trị trong ca thử: 'today', 'today±N' theo TODAY; {$repeat, times}; {$nfd} (dạng tổ hợp, như chép từ PDF)
function value(v) {
  if (v !== null && typeof v === 'object' && '$repeat' in v) return v.$repeat.repeat(v.times)
  if (v !== null && typeof v === 'object' && '$nfd' in v) return v.$nfd.normalize('NFD')
  const m = typeof v === 'string' ? /^today([+-]\d+)?$/.exec(v) : null
  if (!m) return v
  const [y, mo, d] = TODAY.split('-').map(Number)
  return new Date(Date.UTC(y, mo - 1, d + Number(m[1] ?? 0))).toISOString().slice(0, 10)
}

const suites = [
  ...readdirSync(SHARED).filter((f) => f.endsWith('.cases.json')).map((f) => [SHARED, f]),
  ...readdirSync(FORMS).filter((f) => f.endsWith('.cases.json')).map((f) => [FORMS, f]),
]
for (const [base, file] of suites) {
  const schema = json(base, file.replace('.cases.json', '.json'))
  const cases = json(base, file)
  for (const c of [...cases.valid, ...cases.invalid]) {
    test(`${file}: ${c.name}`, () => {
      const data = Object.fromEntries(Object.entries(cases.base).map(([k, v]) => [k, value(v)]))
      for (const [k, v] of Object.entries(c.set ?? {})) data[k] = value(v)
      for (const k of c.unset ?? []) delete data[k]
      assert.deepEqual(formErrors(schema, data, TODAY), c.error ?? {})
    })
  }
}

test('có ca thử cho cả schemas/ lẫn mọi form của ứng dụng', () => {
  assert.ok(suites.some(([base]) => base === SHARED))
  const forms = readdirSync(FORMS).filter((f) => f.endsWith('.json') && !f.endsWith('.cases.json'))
  assert.ok(forms.length >= 2)
  for (const f of forms) assert.ok(suites.some(([, c]) => c === f.replace('.json', '.cases.json')), `${f} thiếu ca thử`)
})

test('thứ tự ưu tiên mã lỗi giữ nguyên thứ tự của svc-workflow, thêm x-moc-range ở cuối', () => {
  const server = readFileSync(new URL('../../../services/svc-workflow/src/svc_workflow/schemas.py', import.meta.url),
    'utf8')
  const tuple = server.match(/PRIORITY = \(([^)]*)\)/)[1]
  const codes = [...tuple.matchAll(/"([^"]+)"/g)].map((m) => m[1])
  assert.deepEqual(PRIORITY.slice(0, codes.length), codes)
  assert.deepEqual(PRIORITY.slice(codes.length).filter((c) => c !== 'x-moc-range'), [])
})

test('mỗi tệp form: nạp được, x-moc-order đủ trường, nhãn và lựa chọn có đủ tiếng Việt và tiếng Anh', () => {
  for (const file of readdirSync(FORMS).filter((f) => f.endsWith('.json') && !f.endsWith('.cases.json'))) {
    const schema = json(FORMS, file)
    assert.doesNotThrow(() => checkSchema(schema), file)
    assert.deepEqual([...schema['x-moc-order']].sort(), Object.keys(schema.properties).sort(), file)
    assert.ok(schema['x-moc-title']?.vi && schema['x-moc-title']?.en, `${file}: x-moc-title`)
    for (const [a, b] of schema['x-moc-range'] ?? []) {
      assert.ok(schema.properties[a] && schema.properties[b], `${file}: x-moc-range ${a}, ${b}`)
    }
    for (const lang of ['vi', 'en']) {
      for (const f of fields(schema, lang)) {
        const ui = f.prop['x-moc-ui'] ?? {}
        assert.ok(ui.label?.[lang], `${file}: ${f.name} thiếu nhãn ${lang}`)
        for (const o of f.options) assert.ok(ui.options?.[o.value]?.[lang], `${file}: ${f.name}.${o.value} ${lang}`)
        if (ui.help) assert.ok(ui.help[lang], `${file}: ${f.name} thiếu gợi ý ${lang}`)
      }
    }
  }
})

test('đề nghị đổi, bù lịch giảng: ô theo thứ tự, kiểu ô suy từ schema, nhãn theo ngôn ngữ', () => {
  const don = json(FORMS, 'don.json')
  const vi = fields(don, 'vi')
  assert.deepEqual(vi.map((f) => [f.name, f.widget, f.required]), [
    ['loai', 'select', true], ['hocPhan', 'text', true], ['lopHocPhan', 'text', true], ['ngayCu', 'date', true],
    ['tietCu', 'text', true], ['ngayMoi', 'date', true], ['tietMoi', 'text', true], ['phongMoi', 'text', true],
    ['lyDo', 'textarea', true],
  ])
  assert.equal(vi[0].id, 'sf-loai')
  assert.equal(fields(don, 'vi', 'don-')[0].id, 'don-loai')
  assert.deepEqual(vi[0].options.map((o) => o.label),
    ['Đổi lịch (dời buổi dạy sang ngày khác)', 'Dạy bù (bù buổi đã nghỉ)'])
  assert.equal(fields(don, 'en')[0].options[1].label, 'Make up a missed class')
  assert.equal(formTitle(don, 'en'), 'Teaching schedule change request')
  for (const file of ['bo-mon.json', 'khoa.json']) assert.equal(fields(json(FORMS, file), 'vi')[0].widget, 'radio')
})

test('kiểu ô khi schema không ghi widget', () => {
  const schema = {
    type: 'object',
    properties: {
      a: { type: 'array', items: { enum: ['x', 'y'] } },
      b: { type: 'boolean' },
      c: { type: 'integer', minimum: 1 },
      d: { type: 'string', maxLength: 201 },
      e: { type: 'string', maxLength: 50 },
      f: { type: ['string', 'null'], format: 'date' },
    },
  }
  assert.deepEqual(fields(schema).map((f) => f.widget),
    ['checkboxes', 'checkbox', 'number', 'textarea', 'text', 'date'])
  assert.deepEqual(fields(schema)[0].options.map((o) => o.value), ['x', 'y'])
  assert.equal(fields(schema)[5].nullable, true)
})

test('dọn dữ liệu trước khi kiểm: NFC, ký tự ẩn, khoảng trắng; ô trống thì bỏ', () => {
  const don = fields(json(FORMS, 'don.json'))
  const nfd = 'Đi công tác'.normalize('NFD')
  const raw = { loai: 'doi-lich', ngayCu: '2026-10-27', phongMoi: ' A1-301 ', lyDo: `  ${nfd}\u200b\r\n` }
  assert.deepEqual(clean(don, raw),
    { loai: 'doi-lich', ngayCu: '2026-10-27', phongMoi: 'A1-301', lyDo: 'Đi công tác' })
  assert.deepEqual(clean(don, { loai: undefined, ngayCu: '', tietCu: ' ', lyDo: '   ' }), {})
  assert.deepEqual(clean(don, { lyDo: 'dòng một\r\ndòng hai' }), { lyDo: 'dòng một\ndòng hai' })
  const n = fields({ type: 'object', properties: { so: { type: 'integer' }, ghi: { type: ['string', 'null'] } } })
  assert.deepEqual(clean(n, { so: ' 3 ', ghi: '' }), { so: 3, ghi: null })
  assert.deepEqual(clean(n, { so: 'ba' }), { so: 'ba', ghi: null })
})

test('dữ liệu người dùng gõ, sau khi dọn, qua được chính schema đó', () => {
  const don = json(FORMS, 'don.json')
  const data = clean(fields(don), {
    loai: 'day-bu', hocPhan: ' Phát triển phần mềm nguồn mở ', lopHocPhan: '20261IT6060001', ngayCu: '2026-10-16',
    tietCu: '1-3', ngayMoi: '2026-10-21', tietMoi: '7-9', phongMoi: 'A1-301', lyDo: ' Ốm\u00ad '
  })
  assert.deepEqual(formErrors(don, data, TODAY), {})
})

test('câu báo lỗi hai thứ tiếng, theo mã và theo ô', () => {
  const don = json(FORMS, 'don.json')
  for (const lang of ['vi', 'en']) {
    const list = fields(don, lang)
    const at = (name) => list.find((f) => f.name === name)
    const say = (name, code) => message(at(name), code, lang, list, don)
    for (const code of [...PRIORITY, 'minimum', 'maximum', 'minItems', 'const', 'không-biết']) {
      assert.ok(say('lyDo', code).length > 0, `${lang} ${code}`)
    }
    const vi = lang === 'vi'
    assert.equal(say('ngayMoi', 'x-moc-date'), vi ? 'Không được trước hôm nay' : 'Cannot be before today')
    assert.equal(say('ngayCu', 'pattern'), vi ? 'Năm phải từ 2000 đến 2099' : 'The year must be between 2000 and 2099')
    assert.equal(say('tietMoi', 'pattern'),
      vi ? 'Ghi số tiết, ví dụ 4 hoặc 1-3' : 'Write the periods, for example 4 or 1-3')
    assert.equal(say('lyDo', 'maxLength'), lang === 'vi' ? 'Tối đa 500 ký tự' : 'At most 500 characters')
    // minLength 1 nghĩa là không được để trống, không phải "cần ít nhất 1 ký tự"
    assert.equal(say('lyDo', 'minLength'), say('lyDo', 'required'))
    assert.notEqual(say('ngayCu', 'format'), say('lyDo', 'format'))
    // mã chỉ máy chủ biết: câu chung "chưa hợp lệ", không nói sai thành "sai định dạng"
    assert.equal(say('lyDo', 'duplicate'), vi ? 'Giá trị chưa hợp lệ' : 'Invalid value')
  }
})

test('tóm tắt một đề nghị cho người duyệt: nhãn, tên lựa chọn, ngày dd/mm/yyyy, ô trống là —', () => {
  const don = json(FORMS, 'don.json')
  assert.deepEqual(summary(don, { loai: 'day-bu', ngayCu: '2026-10-27', ngayMoi: '2026-10-28', tietMoi: '7-9' })
    .filter((r) => ['loai', 'ngayCu', 'ngayMoi', 'tietMoi', 'phongMoi'].includes(r.name)), [
    { name: 'loai', label: 'Loại đề nghị', value: 'Dạy bù (bù buổi đã nghỉ)' },
    { name: 'ngayCu', label: 'Ngày dạy theo lịch', value: '27/10/2026' },
    { name: 'ngayMoi', label: 'Ngày dạy mới', value: '28/10/2026' },
    { name: 'tietMoi', label: 'Tiết dạy mới', value: '7-9' },
    { name: 'phongMoi', label: 'Phòng học', value: '—' },
  ])
  assert.equal(summary(don, { loai: 'mot-loai-moi' }, 'en')[0].value, 'mot-loai-moi')
  assert.equal(summary(json(FORMS, 'khoa.json'), { quyetDinhKhoa: 'tu-choi' }, 'en')[0].value, 'Decline')
})

test('kiểu, danh mục, số, mảng, đối tượng lồng: cùng mã lỗi như Ajv và svc-workflow', () => {
  const schema = {
    type: 'object',
    additionalProperties: false,
    required: ['so_ngay', 'loai'],
    properties: {
      so_ngay: { type: 'integer', minimum: 1, maximum: 30 },
      loai: { enum: ['phep', 'om'] },
      ghi_chu: { type: ['string', 'null'], maxLength: 5 },
      nguoi: { type: 'array', items: { type: 'string', format: 'uuid' }, uniqueItems: true, minItems: 1 },
    },
  }
  const errs = (data) => formErrors(schema, data, TODAY)
  assert.deepEqual(errs({ so_ngay: 2, loai: 'phep' }), {})
  assert.deepEqual(errs({ so_ngay: 2.5, loai: 'phep' }), { so_ngay: 'type' })
  assert.deepEqual(errs({ so_ngay: 0, loai: 'x' }), { so_ngay: 'minimum', loai: 'enum' })
  assert.deepEqual(errs({ so_ngay: 31, loai: 'om', ghi_chu: 'dài quá' }), { so_ngay: 'maximum', ghi_chu: 'maxLength' })
  assert.deepEqual(errs({ loai: 'om', la: 1 }), { so_ngay: 'required', la: 'additionalProperties' })
  const id = '0b7c6f1e-3a52-4f0e-9a51-2d4f3c6e8a10'
  assert.deepEqual(errs({ so_ngay: 1, loai: 'om', nguoi: [id, id] }), { nguoi: 'uniqueItems' })
  assert.deepEqual(errs({ so_ngay: 1, loai: 'om', nguoi: ['x'] }), { nguoi: 'format' })
  assert.deepEqual(errs({ so_ngay: 1, loai: 'om', nguoi: [] }), { nguoi: 'minItems' })
  assert.deepEqual(errs({ so_ngay: 1, loai: 'om', ghi_chu: null }), {})
  assert.deepEqual(errs('x'), { '': 'type' })
  // tên trường lạ như "constructor" không đụng vào prototype
  assert.deepEqual(errs({ so_ngay: 1, loai: 'om', constructor: 1 }), { constructor: 'additionalProperties' })
})

test('schema dùng điều không hỗ trợ thì báo ngay lúc nạp', () => {
  assert.throws(() => checkSchema({ type: 'object', properties: { a: { oneOf: [] } } }), /oneOf/)
  assert.throws(() => checkSchema({ type: 'string', format: 'email' }), /email/)
  assert.throws(() => checkSchema({ type: 'text' }), /kiểu/)
  assert.throws(() => checkSchema({ $ref: 'https://x.test/s.json' }), /\$ref/)
  assert.throws(() => checkSchema({ type: 'string', pattern: '(' }))
  assert.doesNotThrow(() => checkSchema({ type: 'string', title: 'x', 'x-moc-ui': { widget: 'textarea' } }))
  // $ref chỉ tới $defs có thật, không tới prototype; $ref vòng bị từ chối thay vì đệ quy mãi lúc gửi
  assert.throws(() => checkSchema({ $defs: {}, $ref: '#/$defs/constructor' }), /\$ref/)
  assert.throws(() => checkSchema({ $defs: {}, $ref: '#/$defs/__proto__' }), /\$ref/)
  assert.throws(() => checkSchema({ $defs: { a: { $ref: '#/$defs/b' }, b: { allOf: [{ $ref: '#/$defs/a' }] } },
    $ref: '#/$defs/a' }), /vòng/)
  // giá trị từ khóa sai dạng
  for (const bad of [{ required: 'ab' }, { enum: 'x' }, { minLength: -1 }, { maxItems: 1.5 }, { properties: [] },
    { items: 'x' }, { allOf: [] }, { uniqueItems: 'yes' }, { minimum: '1' }]) {
    assert.throws(() => checkSchema(bad), /sai dạng/, JSON.stringify(bad))
  }
})

test('gợi ý hiển thị sai thì báo lúc nạp', () => {
  const props = { a: { type: 'string', format: 'date' }, b: { type: 'string', format: 'date' }, c: { type: 'string' } }
  const base = { type: 'object', properties: props }
  assert.doesNotThrow(() => checkSchema({ ...base, 'x-moc-order': ['c', 'a', 'b'], 'x-moc-range': [['a', 'b']] }))
  assert.throws(() => checkSchema({ ...base, 'x-moc-order': ['a', 'b'] }), /x-moc-order/)
  assert.throws(() => checkSchema({ ...base, 'x-moc-order': ['a', 'b', 'c', 'd'] }), /x-moc-order/)
  assert.throws(() => checkSchema({ ...base, 'x-moc-range': [['a', 'c']] }), /x-moc-range/)
  assert.throws(() => checkSchema({ ...base, 'x-moc-range': [['a', 'z']] }), /x-moc-range/)
  assert.throws(() => checkSchema({ ...base, 'x-moc-range': ['a', 'b'] }), /x-moc-range/)
  const slider = { type: 'object', properties: { a: { 'x-moc-ui': { widget: 'slider' } } } }
  assert.throws(() => checkSchema(slider), /widget/)
})

test('hôm nay theo giờ Việt Nam', () => {
  assert.equal(todayVN(new Date('2026-10-26T16:59:59Z')), '2026-10-26')
  assert.equal(todayVN(new Date('2026-10-26T17:00:00Z')), '2026-10-27')
})
