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

// #303 bước 1b: trình dựng form (/ung-dung/dung-form). Tệp form dựng ra qua luật lúc cài của trình duyệt và được đúng
// module form của ứng dụng nạp, vẽ, kiểm (lib/schema-form.js, bản chép từng byte của apps/nghi-phep); tệp mẫu
// form-builder.sample.json là đúng thứ trình dựng sinh ra, và test_app_forms.py của svc-workflow cho nó qua cả hai luật
// chỉ máy chủ kiểm (pattern, meta-schema). Tên biến, giá trị lựa chọn, khóa form suy từ nhãn; mỗi lỗi của trình dựng
// có câu ở cả hai ngôn ngữ. Chạy: npm test.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import {
  BUILDER_DATE_RULES, BUILDER_DEFS, BUILDER_LIMITS, BUILDER_PROBLEMS, BUILDER_WIDGETS, EL_KEYWORDS, FORM_BUILDER_ROLES,
  addBuilderField, addBuilderOption, builderFile, builderFormFrom, builderFormKey, builderName, builderProblems,
  builderSchema, builderSlug, canBuildForms, freezeBuilderNames, moveBuilderItem, newBuilderForm, removeBuilderField,
  setBuilderWidget, syncBuilderNames,
} from '../app/utils/formBuilder.ts'
import type { Bilingual, BuilderField, BuilderForm, BuilderWidget } from '../app/utils/formBuilder.ts'
import { FORM_LIMITS, checkForm } from '../app/utils/formRules.ts'
import { checkSchema, fields, formErrors, todayVN } from '../app/lib/schema-form.js'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const SAMPLE_FILE = new URL('form-builder.sample.json', import.meta.url)

function field(form: BuilderForm, widget: BuilderWidget, label: Bilingual, more: Partial<BuilderField> = {}) {
  const id = addBuilderField(form, widget)
  const f = form.fields.find((g) => g.id === id)!
  Object.assign(f, { label }, more)
  return f
}
function options(form: BuilderForm, f: BuilderField, labels: Bilingual[]) {
  f.options = []
  for (const label of labels) addBuilderOption(form, f)
  f.options.forEach((o, i) => { o.label = labels[i]! })
}

/** Đề nghị mua sắm: đủ bảy kiểu ô, hai luật so với hôm nay, một cặp ngày, nhãn có và không có tiếng Anh. */
export function sampleForm(): BuilderForm {
  const form = newBuilderForm()
  form.app = 'mua-sam'
  form.title = { vi: 'Đề nghị mua sắm', en: 'Purchase request' }
  field(form, 'text', { vi: 'Tên hàng', en: 'Item' }, { help: { vi: 'Ghi như trên báo giá.', en: 'As on the quote.' } })
  field(form, 'number', { vi: 'Số lượng', en: 'Quantity' }, { minimum: 1, maximum: 1000 })
  field(form, 'number', { vi: 'Đơn giá (đồng)', en: '' }, { integer: false, minimum: 0, required: false })
  options(form, field(form, 'select', { vi: 'Loại', en: 'Category' }), [
    { vi: 'Văn phòng phẩm', en: 'Stationery' }, { vi: 'Thiết bị', en: 'Equipment' }, { vi: 'Dịch vụ', en: '' },
  ])
  options(form, field(form, 'radio', { vi: 'Mức độ', en: 'Priority' }), [
    { vi: 'Thường', en: 'Normal' }, { vi: 'Gấp', en: 'Urgent' },
  ])
  const asked = field(form, 'date', { vi: 'Ngày đề nghị', en: 'Request date' }, { dateRule: 'not-after-today' })
  field(form, 'date', { vi: 'Cần trước ngày', en: 'Needed by' }, { dateRule: 'not-before-today', after: asked.id })
  field(form, 'textarea', { vi: 'Lý do', en: 'Reason' }, { required: false, maxLength: 1000, rows: 3 })
  field(form, 'checkbox', { vi: 'Đã có báo giá', en: 'Quote attached' })
  syncBuilderNames(form)
  return form
}

test('lib/schema-form.js là bản chép từng byte của module form trong apps/nghi-phep', () => {
  assert.equal(read('../app/lib/schema-form.js'), read('../../nghi-phep/public/schema-form.js'),
    'sửa apps/nghi-phep/public/schema-form.js thì chép lại sang apps/office/app/lib/')
})

test('ô nhiều dòng dùng đúng $defs.text của form nghỉ phép; ô một dòng chặn thêm xuống dòng', () => {
  const { $comment: _, ...text } = JSON.parse(read('../../nghi-phep/forms/don.json')).$defs.text
  assert.deepEqual(BUILDER_DEFS.text, text)
  const line = structuredClone(text)
  const first = line.allOf[0].not
  first.pattern = first.pattern.replace('\u0000-\t\u000b\f\u000e-\u001f', '\u0000-\u001f')
  assert.notEqual(first.pattern, text.allOf[0].not.pattern)
  assert.deepEqual(BUILDER_DEFS.line, line)
  // cùng tập ký tự với schemas/van-ban-den.json, nơi ba điều gộp một pattern: so từng ký tự của BMP
  const defs = JSON.parse(read('../../../schemas/van-ban-den.json')).$defs
  for (const name of ['line', 'text'] as const) {
    const [hidden, ...edges] = defs[name].not.pattern.split('|')
    const theirs = new RegExp(hidden, 'u')
    const [control, invisible] = BUILDER_DEFS[name].allOf.map((s) => new RegExp(s.not.pattern, 'u'))
    for (let c = 0; c <= 0xffff; c++) {
      const ch = String.fromCharCode(c)
      if (theirs.test(ch) !== (control!.test(ch) || invisible!.test(ch))) assert.fail(`${name}: U+${c.toString(16)}`)
    }
    assert.deepEqual(BUILDER_DEFS[name].allOf.slice(2).map((s) => s.not.pattern), edges, name)
  }
})

test('kiểu ô: mọi kiểu của schema-form.js trừ checkboxes — luật lúc cài chỉ cho giá trị đơn', () => {
  assert.ok(!FORM_LIMITS.SCALAR_TYPES.includes('array'))
  const README = read('../../../schemas/README.md')
  const listed = /`widget` — ([^;]+);/.exec(README)?.[1]?.match(/`(\w+)`/g)?.map((w) => w.slice(1, -1))
  assert.deepEqual(listed?.filter((w) => w !== 'checkboxes'), BUILDER_WIDGETS)
  // module nhận đúng kiểu đã ghi, không tự suy kiểu khác
  const form = newBuilderForm()
  for (const w of BUILDER_WIDGETS) field(form, w, { vi: `Ô ${w}`, en: '' })
  for (const f of form.fields.filter((g) => g.widget === 'select' || g.widget === 'radio')) {
    options(form, f, [{ vi: 'Một', en: '' }])
  }
  syncBuilderNames(form)
  assert.deepEqual(fields(builderSchema(form)).map((f: { widget: string }) => f.widget), BUILDER_WIDGETS)
})

test('tệp mẫu đúng bằng thứ trình dựng sinh ra, qua mọi luật lúc cài của trình duyệt', () => {
  const form = sampleForm()
  const file = builderFile(form)
  assert.equal(file, readFileSync(SAMPLE_FILE, 'utf8'), 'chạy lại tests/formBuilder.test.ts sau khi sửa tệp mẫu')
  assert.deepEqual(builderProblems(form), [])
  assert.deepEqual(checkForm(file), [])
  assert.deepEqual(JSON.parse(file), builderSchema(form))
  assert.equal(builderFormKey(form), 'mua-sam.de-nghi-mua-sam')
  // không ký tự vô hình nào ngoài xuống dòng của phần thụt lề: pattern ghi bằng \uXXXX
  assert.doesNotMatch(file, /[^\n\P{Cc}]|[\p{Cf}\p{Zl}\p{Zp}\u115f\u1160\u3164\uffa0]|[^ \P{Zs}]/u)
  assert.match(file, /\\u200b-\\u200f/)
})

test('module form nạp, vẽ, kiểm tệp mẫu như form của ứng dụng', () => {
  const schema = JSON.parse(readFileSync(SAMPLE_FILE, 'utf8'))
  checkSchema(schema)
  const vi = fields(schema, 'vi')
  assert.deepEqual(vi.map((f: { name: string }) => f.name),
    ['tenHang', 'soLuong', 'donGiaDong', 'loai', 'mucDo', 'ngayDeNghi', 'canTruocNgay', 'lyDo', 'daCoBaoGia'])
  assert.deepEqual(vi.filter((f: { required: boolean }) => !f.required).map((f: { name: string }) => f.name),
    ['donGiaDong', 'lyDo'])
  const en = fields(schema, 'en')
  assert.deepEqual(en.map((f: { label: string }) => f.label), ['Item', 'Quantity', 'Đơn giá (đồng)', 'Category',
    'Priority', 'Request date', 'Needed by', 'Reason', 'Quote attached'])
  assert.deepEqual(en[3].options.map((o: { value: string, label: string }) => [o.value, o.label]),
    [['van-phong-pham', 'Stationery'], ['thiet-bi', 'Equipment'], ['dich-vu', 'Dịch vụ']])
  assert.equal(en[0].help, 'As on the quote.')
  assert.equal(en[7].ui.rows, 3)

  const today = '2026-10-28'
  const ok = { tenHang: 'Giấy A4', soLuong: 10, loai: 'thiet-bi', mucDo: 'gap', ngayDeNghi: today,
    canTruocNgay: '2026-11-05', daCoBaoGia: false }
  assert.deepEqual(formErrors(schema, ok, today), {})
  assert.deepEqual(formErrors(schema, { ...ok, donGiaDong: 12500.5, lyDo: 'Hết giấy\nin' }, today), {})
  assert.deepEqual(formErrors(schema, {
    tenHang: ' Giấy', soLuong: 2.5, donGiaDong: -1, loai: 'khac', mucDo: 'gap', ngayDeNghi: '2026-10-29',
    canTruocNgay: '2026-10-27', lyDo: 'x'.repeat(1001), daCoBaoGia: 'co',
  }, today), {
    tenHang: 'not', soLuong: 'type', donGiaDong: 'minimum', loai: 'enum', ngayDeNghi: 'x-moc-date',
    canTruocNgay: 'x-moc-date', lyDo: 'maxLength', daCoBaoGia: 'type',
  })
  assert.deepEqual(formErrors(schema, { ...ok, ngayDeNghi: today, canTruocNgay: today }, today), {})
  // một dòng thì không được xuống dòng. Cặp ngày chỉ lộ ra khi bỏ luật so với hôm nay: hai luật đó đã buộc ngày đề
  // nghị không sau ngày cần trước
  const free = sampleForm()
  free.fields.find((f) => f.name === 'canTruocNgay')!.dateRule = ''
  assert.deepEqual(formErrors(builderSchema(free), { ...ok, tenHang: 'Giấy\nA4', ngayDeNghi: '2026-10-20',
    canTruocNgay: '2026-10-19' }, today), { tenHang: 'not', canTruocNgay: 'x-moc-range' })
  assert.deepEqual(formErrors(schema, {}, todayVN()), Object.fromEntries(['tenHang', 'soLuong', 'loai', 'mucDo',
    'ngayDeNghi', 'canTruocNgay', 'daCoBaoGia'].map((n) => [n, 'required'])))
})

test('tên biến, giá trị lựa chọn, khóa form suy từ chữ không dấu', () => {
  for (const [label, name] of [['Từ ngày', 'tuNgay'], ['Số ngày nghỉ', 'soNgayNghi'], ['ĐƠN VỊ', 'donVi'],
    ['3 ngày', 'ngay'], ['Ngày 2', 'ngay2'], ['  Họ  và tên  ', 'hoVaTen'], ['Người dùng: email', 'nguoiDungEmail'],
    ['', ''], ['!!!', ''], ['123', ''], ['日本', '']]) {
    assert.equal(builderName(label!), name, label)
  }
  assert.equal(builderName('a '.repeat(60)).length, BUILDER_LIMITS.SLUG_LENGTH)
  for (const [text, slug] of [['Phép năm', 'phep-nam'], ['Nghỉ ốm', 'nghi-om'], ['Đề nghị mua sắm', 'de-nghi-mua-sam'],
    ['2 Đơn', 'don'], ['', '']]) {
    assert.equal(builderSlug(text!), slug, text)
  }
  assert.equal(builderSlug('abc '.repeat(30)), 'abc-'.repeat(10).slice(0, -1))
  // giá trị lựa chọn không phải mở bằng chữ: giữ số đầu
  for (const [text, slug] of [['3 ngày', '3-ngay'], ['5', '5'], ['Ngày 2', 'ngay-2']]) {
    assert.equal(builderSlug(text!, false), slug, text)
  }
})

test('tên suy ra không trùng nhau, không trùng biến hệ thống, nhường tên người dùng tự đặt', () => {
  const form = newBuilderForm()
  form.title.vi = 'Đơn xin nghỉ'
  const a = field(form, 'text', { vi: 'Ngày', en: '' })
  const b = field(form, 'text', { vi: 'Ngày', en: '' })
  const c = field(form, 'text', { vi: 'Initiator', en: '' })
  const d = field(form, 'text', { vi: 'Task', en: '' })
  syncBuilderNames(form)
  assert.deepEqual([a.name, b.name, c.name, d.name], ['ngay', 'ngay2', 'initiator2', 'task2'])
  assert.equal(form.key, 'don-xin-nghi')
  Object.assign(b, { name: 'ngay', named: true })
  form.key = 'don'
  form.keyed = true
  form.title.vi = 'Đơn khác'
  syncBuilderNames(form)
  assert.deepEqual([a.name, b.name], ['ngay2', 'ngay'])
  assert.equal(form.key, 'don')
  // gọi lại không đổi gì: watch của trang không lặp mãi
  const before = JSON.stringify(form)
  syncBuilderNames(form)
  assert.equal(JSON.stringify(form), before)

  const s = field(form, 'select', { vi: 'Có không', en: '' })
  options(form, s, [{ vi: 'Có', en: '' }, { vi: 'Có', en: 'Yes' }, { vi: 'Không', en: '' }])
  syncBuilderNames(form)
  assert.deepEqual(s.options.map((o) => o.value), ['co', 'co2', 'khong'])

  // từ khóa EL như biến thường thì `${le == 'x'}` trong BPMN không dịch được: tên suy ra tránh
  const le = field(form, 'text', { vi: 'Lễ', en: '' })
  const not = field(form, 'text', { vi: 'Not', en: '' })
  const score = field(form, 'radio', { vi: 'Điểm', en: '' })
  options(form, score, ['1', '2', '3 ngày', '3 Ngày'].map((vi) => ({ vi, en: '' })))
  syncBuilderNames(form)
  assert.deepEqual([le.name, not.name], ['le2', 'not2'])
  assert.deepEqual(score.options.map((o) => o.value), ['1', '2', '3-ngay', '3-ngay2'])
  assert.equal(EL_KEYWORDS.length, 16)
})

test('tải tệp rồi thì tên, khóa, giá trị đang có giữ nguyên khi xóa, đổi chỗ, đổi nhãn', () => {
  const form = newBuilderForm()
  form.title.vi = 'Đơn'
  const a = field(form, 'date', { vi: 'Ngày', en: '' })
  const b = field(form, 'date', { vi: 'Ngày', en: '' })
  const c = field(form, 'select', { vi: 'Loại', en: '' })
  options(form, c, [{ vi: 'Có', en: '' }, { vi: 'Có', en: '' }])
  syncBuilderNames(form)
  // chưa tải: xóa trường đầu thì trường sau lấy lại tên "ngay"
  const draft = builderFormFrom(JSON.parse(JSON.stringify(form)))
  removeBuilderField(draft, draft.fields[0]!.id)
  syncBuilderNames(draft)
  assert.equal(draft.fields[0]!.name, 'ngay')

  freezeBuilderNames(form)
  removeBuilderField(form, a.id)
  c.options.shift()
  form.title.vi = 'Đơn khác'
  c.label.vi = 'Kiểu'
  syncBuilderNames(form)
  assert.deepEqual([b.name, c.name, c.options[0]!.value, form.key], ['ngay2', 'loai', 'co2', 'don'])
  // trường thêm sau lần tải vẫn suy theo nhãn
  const d = field(form, 'text', { vi: 'Ghi chú', en: '' })
  syncBuilderNames(form)
  assert.equal(d.name, 'ghiChu')
  assert.equal(d.named, false)
})

test('mỗi lỗi của trình dựng chỉ ra đúng trường, đúng lựa chọn', () => {
  const codes = (form: BuilderForm) => builderProblems(form).map((p) => [p.code, p.field, p.option])
  const empty = newBuilderForm()
  assert.deepEqual(codes(empty), [['app'], ['key'], ['title'], ['fields']].map(([c]) => [c, undefined, undefined]))
  for (const app of ['a', 'Mua-sam', 'mua_sam', '-ab', 'ab-', 'a'.repeat(31)]) {
    assert.ok(builderProblems({ ...sampleForm(), app }).some((p) => p.code === 'app'), app)
  }
  assert.ok(builderProblems({ ...sampleForm(), key: '1don', keyed: true }).some((p) => p.code === 'key'))
  // tên trong workflow.forms là cả <app>.<key>: tới 80 ký tự
  const long = (key: string) => builderProblems({ ...sampleForm(), app: 'a'.repeat(30), key, keyed: true })
  assert.deepEqual(long('b'.repeat(49)), [])
  assert.deepEqual(long('b'.repeat(50)), [{ code: 'key' }])

  const form = sampleForm()
  const [text, qty, , select, , asked, needed, reason] = form.fields as BuilderField[]
  text!.label.vi = ' '                 // tên đã suy từ trước vẫn đúng: chỉ báo nhãn
  qty!.minimum = 5.5
  select!.options[1]!.label.vi = ''
  select!.options[2]!.value = 'van-phong-pham'
  select!.options[2]!.named = true
  needed!.after = reason!.id
  reason!.maxLength = BUILDER_LIMITS.MAX_LENGTH + 1
  asked!.name = 'Tenant'
  asked!.named = true
  assert.deepEqual(codes(form), [
    ['label', text!.id, undefined],
    ['bounds', qty!.id, undefined],
    ['option-label', select!.id, select!.options[1]!.id],
    ['option-taken', select!.id, select!.options[2]!.id],
    ['name', asked!.id, undefined],
    ['after', needed!.id, undefined],
    ['length', reason!.id, undefined],
  ])

  const more = sampleForm()
  const [first, , , choice, , , , notes, box] = more.fields as BuilderField[]
  Object.assign(first!, { name: 'initiator', named: true })
  Object.assign(box!, { name: 'loai', named: true })
  choice!.options = []
  notes!.rows = 21
  notes!.minLength = 2000
  const [, qty2, price] = more.fields as BuilderField[]
  Object.assign(qty2!, { name: 'or', named: true })
  Object.assign(price!, { name: 'empty', named: true })
  assert.deepEqual(codes(more), [
    ['name-reserved', first!.id, undefined],
    ['name-reserved', qty2!.id, undefined],
    ['name-reserved', price!.id, undefined],
    ['options', choice!.id, undefined],
    ['length', notes!.id, undefined],
    ['rows', notes!.id, undefined],
    ['name-taken', box!.id, undefined],
  ])

  // A không trước B, B không trước A: chỉ gửi được khi hai ngày bằng nhau
  const loop = sampleForm()
  const dates = loop.fields.filter((f) => f.widget === 'date')
  const third = field(loop, 'date', { vi: 'Ngày giao', en: '' })
  syncBuilderNames(loop)
  dates[0]!.after = third.id
  third.after = dates[1]!.id
  assert.deepEqual(codes(loop), [dates[0]!, dates[1]!, third].map((f) => ['after-loop', f.id, undefined]))
  third.after = null
  assert.deepEqual(codes(loop), [])

  // trường, lựa chọn chưa có nhãn: tên, giá trị suy ra rỗng nhưng chỉ báo nhãn; có nhãn mà không suy được thì báo
  const opt = sampleForm()
  const kind = opt.fields[3]!
  addBuilderOption(opt, kind)
  const blank = field(opt, 'text', { vi: '', en: 'Note' })
  syncBuilderNames(opt)
  const added = kind.options.at(-1)!
  assert.deepEqual(codes(opt), [['option-label', kind.id, added.id], ['label', blank.id, undefined]])
  removeBuilderField(opt, blank.id)
  added.label.vi = '…'
  syncBuilderNames(opt)
  assert.deepEqual(codes(opt), [['option-value', kind.id, added.id]])
})

test('luật lúc cài là lưới cuối khi các luật của trình dựng đã qua', () => {
  const form = sampleForm()
  // 400 ô gợi ý dài: tệp quá 256 KB
  for (let i = 0; i < 400; i++) {
    field(form, 'checkbox', { vi: `Mục ${i}`, en: '' }, { help: { vi: 'x'.repeat(700), en: '' } })
  }
  syncBuilderNames(form)
  assert.deepEqual(builderProblems(form), [{ code: 'rule', rule: 'size', field: undefined }])
})

test('đổi kiểu ô đặt giá trị mặc định hợp kiểu mới; ô đánh dấu luôn bắt buộc', () => {
  const form = newBuilderForm()
  const f = field(form, 'text', { vi: 'Ghi chú', en: '' })
  assert.equal(f.maxLength, BUILDER_LIMITS.TEXT_LENGTH)
  setBuilderWidget(form, f, 'textarea')
  assert.equal(f.maxLength, BUILDER_LIMITS.TEXTAREA_LENGTH)
  f.maxLength = 500
  setBuilderWidget(form, f, 'text')
  assert.equal(f.maxLength, 500)
  setBuilderWidget(form, f, 'radio')
  assert.equal(f.options.length, 1)
  f.required = false
  setBuilderWidget(form, f, 'checkbox')
  assert.equal(f.required, true)
  // ô đánh dấu luôn gửi true/false: tệp ghi bắt buộc dù cờ bị tắt
  f.required = false
  syncBuilderNames(form)
  assert.deepEqual((builderSchema(form) as { required: string[] }).required, ['ghiChu'])
})

test('đổi thứ tự, xóa trường: cặp ngày trỏ tới trường đã xóa thì bỏ', () => {
  const form = sampleForm()
  const names = () => form.fields.map((f) => f.name)
  assert.equal(moveBuilderItem(form.fields, 0, -1), -1)
  assert.equal(moveBuilderItem(form.fields, form.fields.length - 1, 1), -1)
  assert.equal(moveBuilderItem(form.fields, 0, 1), 1)
  assert.deepEqual(names().slice(0, 2), ['soLuong', 'tenHang'])
  assert.deepEqual((builderSchema(form) as { 'x-moc-order': string[] })['x-moc-order'].slice(0, 2),
    ['soLuong', 'tenHang'])
  const asked = form.fields.find((f) => f.name === 'ngayDeNghi')!
  removeBuilderField(form, asked.id)
  assert.equal(form.fields.find((f) => f.name === 'canTruocNgay')!.after, null)
  assert.equal((builderSchema(form) as Record<string, unknown>)['x-moc-range'], undefined)
  assert.deepEqual(builderProblems(form), [])
})

test('bản dở giữ trong trình duyệt nạp lại đúng form, bỏ phần lạ', () => {
  const form = sampleForm()
  const back = builderFormFrom(JSON.parse(JSON.stringify(form)))
  assert.equal(builderFile(back), builderFile(form))
  // id cấp lại nhưng cặp ngày vẫn trỏ đúng trường
  const needed = back.fields.find((f) => f.name === 'canTruocNgay')!
  assert.equal(back.fields.find((f) => f.id === needed.after)?.name, 'ngayDeNghi')
  assert.ok(back.next > Math.max(...back.fields.flatMap((f) => [f.id, ...f.options.map((o) => o.id)])))
  for (const junk of [null, 1, 'x', [], { fields: 'x' }, { fields: [null, 1, { widget: 'checkboxes', after: 'x' }] }]) {
    const f = builderFormFrom(junk)
    assert.ok(f.fields.every((g) => BUILDER_WIDGETS.includes(g.widget) && g.after === null), JSON.stringify(junk))
  }
  const odd = builderFormFrom({ fields: [{ widget: 'date', dateRule: 'hom-qua', minimum: 'x', label: { vi: 1 } }] })
  assert.deepEqual([odd.fields[0]!.dateRule, odd.fields[0]!.minimum, odd.fields[0]!.label.vi], ['', null, ''])
})

test('chỉ quản trị đơn vị mở trình dựng; trang Ứng dụng chỉ đưa nút cho vai trò đó', () => {
  assert.deepEqual(FORM_BUILDER_ROLES, ['tenant_admin'])
  assert.equal(canBuildForms('tenant_admin'), true)
  for (const role of ['clerk', 'staff', 'manager', 'director', null, undefined] as const) {
    assert.equal(canBuildForms(role), false, String(role))
  }
  const page = read('../app/pages/ung-dung/index.vue')
  assert.match(page, /<NuxtLink v-if="builder" to="\/ung-dung\/dung-form"/)
  assert.match(page, /const builder = computed\(\(\) => canBuildForms\(claims\.value\?\.role\)\)/)
  const builder = read('../app/pages/ung-dung/dung-form.vue')
  assert.match(builder, /import \{ mountForm \} from '~\/lib\/schema-form\.js'/)
  assert.match(builder, /const allowed = computed\(\(\) => canBuildForms\(claims\.value\?\.role\)\)/)
})

test('chữ chỉ có tiếng Anh thì tệp ghi chuỗi tiếng Anh: form tiếng Việt không hiện chữ rỗng', () => {
  const form = newBuilderForm()
  field(form, 'text', { vi: 'Ghi chú', en: 'Note' }, { help: { vi: ' ', en: 'Optional.' } })
  syncBuilderNames(form)
  type Props = { properties: Record<string, { 'x-moc-ui': Record<string, unknown> }> }
  const ui = (builderSchema(form) as Props).properties.ghiChu!['x-moc-ui']
  assert.deepEqual([ui.label, ui.help], [{ vi: 'Ghi chú', en: 'Note' }, 'Optional.'])
})

test('tên ứng dụng, khóa form theo đúng luật của app-manifest.schema.json', () => {
  const manifest = JSON.parse(read('../../../scripts/app-manifest.schema.json'))
  const { APP, APP_MIN, APP_MAX, FORM_KEY, FORM_KEY_MAX } = BUILDER_LIMITS
  const name = manifest.properties.name
  assert.deepEqual([name.pattern, name.minLength, name.maxLength], [`^${APP}$`, APP_MIN, APP_MAX])
  const keys = manifest.properties.workflow.properties.forms.propertyNames
  assert.deepEqual([keys.pattern, keys.maxLength], [`^${APP}\\.${FORM_KEY}$`, FORM_KEY_MAX])
})

test('mỗi kiểu ô, luật ngày, lỗi của trình dựng có câu ở cả hai ngôn ngữ', () => {
  for (const lang of ['vi', 'en']) {
    const fb = JSON.parse(read(`../app/locales/${lang}.json`)).formBuilder
    for (const w of BUILDER_WIDGETS) assert.equal(typeof fb.widgets[w], 'string', `${lang} widgets.${w}`)
    for (const r of BUILDER_DATE_RULES) assert.equal(typeof fb.dateRules[r || 'none'], 'string', `${lang} ${r}`)
    assert.deepEqual(Object.keys(fb.problem).sort(), [...BUILDER_PROBLEMS].sort(), lang)
  }
})
