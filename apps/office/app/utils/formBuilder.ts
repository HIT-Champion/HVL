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

// #303 bước 1b: trình dựng form (trang /ung-dung/dung-form). Quản trị đơn vị khai danh sách trường; tệp này dựng thành
// tệp JSON Schema 2020-12 viết như form của ứng dụng mẫu (schemas/README.md, mục "Form dựng từ schema"), rồi kiểm bằng
// các luật riêng của trình dựng (tên trùng, lựa chọn trống, cặp ngày hỏng…) và luật lúc cài chép sang trình duyệt
// (formRules.ts). Trang xem trước bằng mountForm() của schema-form.js rồi cho tải tệp về; cài vẫn bằng
// `moc app install`.
//
// Không có ô nhiều lựa chọn (checkboxes của schema-form.js): luật lúc cài chỉ cho giá trị đơn, vì mỗi trường là một
// biến của quy trình. Không cho nhập pattern: ô chữ dùng hai $defs cố định (BUILDER_DEFS), và test_app_forms.py cho
// tệp mẫu của trình dựng (tests/form-builder.sample.json) qua cả hai luật chỉ máy chủ kiểm. Tệp này không dùng gì của
// Nuxt để Node chạy test được (tests/formBuilder.test.ts).

import type { Role } from '~/composables/useAuth'
import { FORM_LIMITS, checkForm } from './formRules.ts'
import type { FormRule } from './formRules.ts'

// Ai mở trang: quản trị đơn vị lo việc cài ứng dụng. Trang chỉ dựng tệp trên trình duyệt, không gọi API nào
export const FORM_BUILDER_ROLES: Role[] = ['tenant_admin']

export function canBuildForms(role: Role | null | undefined): boolean {
  return !!role && FORM_BUILDER_ROLES.includes(role)
}

export type BuilderWidget = 'text' | 'textarea' | 'date' | 'number' | 'select' | 'radio' | 'checkbox'
export type BuilderDateRule = '' | 'not-after-today' | 'not-before-today'

export const BUILDER_WIDGETS: BuilderWidget[] = ['text', 'textarea', 'date', 'number', 'select', 'radio', 'checkbox']
export const BUILDER_DATE_RULES: BuilderDateRule[] = ['', 'not-after-today', 'not-before-today']

export const BUILDER_LIMITS = {
  // tên ứng dụng như manifest (scripts/app-manifest.schema.json); phần sau dấu chấm của formKey như key_pattern của
  // svc_workflow/apps/bpmn.py
  APP: '[a-z][a-z0-9]*(-[a-z0-9]+)*',
  APP_MIN: 2,
  APP_MAX: 30,
  FORM_KEY: '[a-z][a-z0-9]*(-[a-z0-9]+)*',
  // cả formKey <app>.<key>: maxLength của tên trong workflow.forms (app-manifest.schema.json)
  FORM_KEY_MAX: 80,
  // độ dài tối đa (ký tự) mặc định của ô một dòng, ô nhiều dòng, và trần trình dựng cho đặt
  TEXT_LENGTH: 200,
  TEXTAREA_LENGTH: 2000,
  MAX_LENGTH: 10000,
  MAX_ROWS: 20,
  // tên, khóa suy từ nhãn cắt ở đây; tên biến tối đa 64 ký tự (VARIABLE của formRules.ts)
  SLUG_LENGTH: 40,
}

// Chữ hai tiếng; tiếng Anh để trống thì form hiện tiếng Việt (say() của schema-form.js)
export interface Bilingual {
  vi: string
  en: string
}

export interface BuilderOption {
  id: number
  value: string          // giá trị lưu vào biến quy trình
  named: boolean         // người dùng tự đặt giá trị: thôi suy từ nhãn
  label: Bilingual
}

export interface BuilderField {
  id: number             // khóa không đổi khi đổi tên: v-for, tiêu điểm, cặp ngày
  name: string           // tên biến
  named: boolean         // người dùng tự đặt tên: thôi suy từ nhãn
  widget: BuilderWidget
  label: Bilingual
  help: Bilingual
  required: boolean      // ô đánh dấu luôn gửi true/false nên luôn bắt buộc
  minLength: number | null
  maxLength: number | null
  rows: number | null
  integer: boolean
  minimum: number | null
  maximum: number | null
  options: BuilderOption[]
  dateRule: BuilderDateRule
  after: number | null   // id trường ngày mà trường này không được trước (x-moc-range)
}

export interface BuilderForm {
  app: string            // tên ứng dụng: formKey là <app>.<key>
  key: string
  keyed: boolean         // người dùng tự đặt khóa: thôi suy từ tên form
  title: Bilingual
  fields: BuilderField[]
  next: number           // id kế tiếp cho trường, lựa chọn
}

export type BuilderProblemCode = 'app' | 'key' | 'title' | 'fields' | 'label' | 'name' | 'name-reserved'
  | 'name-taken' | 'length' | 'rows' | 'bounds' | 'options' | 'option-label' | 'option-value' | 'option-taken'
  | 'after' | 'after-loop' | 'rule'

// mỗi mã một câu formBuilder.problem.<mã> ở cả hai ngôn ngữ (test)
export const BUILDER_PROBLEMS: BuilderProblemCode[] = ['app', 'key', 'title', 'fields', 'label', 'name',
  'name-reserved', 'name-taken', 'length', 'rows', 'bounds', 'options', 'option-label', 'option-value', 'option-taken',
  'after', 'after-loop', 'rule']

export interface BuilderProblem {
  code: BuilderProblemCode
  field?: number         // id trường
  option?: number        // id lựa chọn
  rule?: FormRule        // với code 'rule': luật lúc cài mà các luật của trình dựng chưa bắt
}

const VARIABLE = new RegExp(`^(?:${FORM_LIMITS.VARIABLE})$`)
const APP = new RegExp(`^(?:${BUILDER_LIMITS.APP})$`)
const FORM_KEY = new RegExp(`^(?:${BUILDER_LIMITS.FORM_KEY})$`)
// tên luật lúc cài không cho: tên suy ra tránh, tên người dùng tự đặt thì báo name-reserved
const TAKEN = new Set([...FORM_LIMITS.RESERVED, ...FORM_LIMITS.ENGINE_NAMES, ...FORM_LIMITS.EL_KEYWORDS])
const empty = (): Bilingual => ({ vi: '', en: '' })

// Ô chữ: không ký tự điều khiển, ký tự vô hình; không khoảng trắng ở đầu hoặc cuối; ô một dòng không xuống dòng. Viết
// như $defs.text của form nghỉ phép (apps/nghi-phep/forms/don.json, test so): mỗi pattern một lớp ký tự, không nhánh |,
// không phần lặp, nên luật quay lui của máy chủ nhận mà không cần maxLength cạnh pattern. Cùng tập ký tự với
// schemas/van-ban-den.json, nơi ba điều gộp một pattern
const INVISIBLE_SET = '\u202a-\u202e\u2060-\u2064\u2066-\u2069\u3164\ufeff\uffa0\u2028\u2029'
const SPACE_SET = '\t\n\u000b\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'
const plain = (control: string) => ({
  type: 'string',
  allOf: [
    { not: { pattern: `[${control}\u007f-\u009f\u00ad\u115f\u1160\u200b-\u200f]` } },
    { not: { pattern: `[${INVISIBLE_SET}]` } },
    { not: { pattern: `^[${SPACE_SET}]` } },
    { not: { pattern: `[${SPACE_SET}]$` } },
  ],
})
export const BUILDER_DEFS = {
  line: plain('\u0000-\u001f'),
  text: plain('\u0000-\t\u000b\f\u000e-\u001f'),     // được xuống dòng (\n, \r)
}

// Chữ người dùng gõ vào nhãn, gợi ý, lựa chọn: NFC, một dòng, bỏ ký tự ẩn, gộp khoảng trắng, bỏ khoảng trắng hai đầu
function clean(text: string): string {
  return text.normalize('NFC').replace(/[\p{Cc}\p{Cf}]/gu, (c) => (/\s/.test(c) ? ' ' : ''))
    .replace(/\s+/gu, ' ').trim()
}

// Chỉ có tiếng Anh thì ghi chuỗi tiếng Anh: {vi: '', en} làm form tiếng Việt hiện chữ rỗng (say() lấy '' của vi)
function bilingual(text: Bilingual): string | Bilingual {
  const vi = clean(text.vi)
  const en = clean(text.en)
  if (!vi) return en
  return en && en !== vi ? { vi, en } : vi
}

// Từ chữ không dấu của nhãn: "Từ ngày" → ["tu", "ngay"]. Tên, khóa phải mở bằng chữ cái nên bỏ các từ đầu mở bằng
// chữ số; giá trị lựa chọn thì giữ ("3 ngày" → "3-ngay")
function words(text: string, letterFirst = true): string[] {
  const parts = text.normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
    .toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)
  while (letterFirst && parts.length && /^[0-9]/.test(parts[0]!)) parts.shift()
  return parts
}

/** Tên biến suy từ nhãn, kiểu camelCase không dấu: "Số ngày nghỉ" → "soNgayNghi". */
export function builderName(label: string): string {
  const [first = '', ...rest] = words(label)
  return (first + rest.map((w) => w[0]!.toUpperCase() + w.slice(1)).join('')).slice(0, BUILDER_LIMITS.SLUG_LENGTH)
}

/** Khóa form, giá trị lựa chọn suy từ chữ, kiểu gạch nối: "Phép năm" → "phep-nam". */
export function builderSlug(text: string, letterFirst = true): string {
  return words(text, letterFirst).join('-').slice(0, BUILDER_LIMITS.SLUG_LENGTH).replace(/-+$/, '')
}

function unique(base: string, taken: Set<string>): string {
  if (!base) return ''
  let name = base
  for (let n = 2; taken.has(name); n++) name = `${base}${n}`
  taken.add(name)
  return name
}

export function newBuilderForm(): BuilderForm {
  return { app: '', key: '', keyed: false, title: empty(), fields: [], next: 1 }
}

const isRecord = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v)
const textOf = (v: unknown) => (typeof v === 'string' ? v : '')
const numberOf = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const bilingualOf = (v: unknown): Bilingual => (isRecord(v) ? { vi: textOf(v.vi), en: textOf(v.en) } : empty())
const oneOf = <T extends string>(v: unknown, list: T[], fallback: T): T => (list.includes(v as T) ? v as T : fallback)

/** Form từ bản dở giữ trong trình duyệt (useFormDraft): giữ phần đúng kiểu, bỏ phần lạ; id cấp lại từ đầu. */
export function builderFormFrom(value: unknown): BuilderForm {
  const src = isRecord(value) ? value : {}
  const form = newBuilderForm()
  Object.assign(form, { app: textOf(src.app), key: textOf(src.key), keyed: src.keyed === true,
    title: bilingualOf(src.title) })
  const ids = new Map<number, number>()        // id cũ → id mới, để giữ cặp ngày
  const after = new Map<BuilderField, unknown>()
  for (const raw of Array.isArray(src.fields) ? src.fields : []) {
    if (!isRecord(raw)) continue
    const widget = oneOf(raw.widget, BUILDER_WIDGETS, 'text')
    const field: BuilderField = {
      id: form.next++, name: textOf(raw.name), named: raw.named === true, widget, label: bilingualOf(raw.label),
      help: bilingualOf(raw.help), required: raw.required !== false || widget === 'checkbox',
      minLength: numberOf(raw.minLength), maxLength: numberOf(raw.maxLength), rows: numberOf(raw.rows),
      integer: raw.integer !== false, minimum: numberOf(raw.minimum), maximum: numberOf(raw.maximum),
      options: (Array.isArray(raw.options) ? raw.options : []).filter(isRecord).map((o) => ({
        id: form.next++, value: textOf(o.value), named: o.named === true, label: bilingualOf(o.label),
      })),
      dateRule: oneOf(raw.dateRule, BUILDER_DATE_RULES, ''), after: null,
    }
    if (typeof raw.id === 'number') ids.set(raw.id, field.id)
    after.set(field, raw.after)
    form.fields.push(field)
  }
  for (const [field, old] of after) field.after = typeof old === 'number' ? ids.get(old) ?? null : null
  return form
}

/** Thêm một trường, trả id (trang đọc lại trường qua form để giữ tính phản ứng của Vue). */
export function addBuilderField(form: BuilderForm, widget: BuilderWidget = 'text'): number {
  const field: BuilderField = {
    id: form.next++, name: '', named: false, widget: 'text', label: empty(), help: empty(), required: true,
    minLength: null, maxLength: null, rows: null, integer: true, minimum: null, maximum: null, options: [],
    dateRule: '', after: null,
  }
  form.fields.push(field)
  setBuilderWidget(form, form.fields.at(-1)!, widget)
  return field.id
}

export function addBuilderOption(form: BuilderForm, field: BuilderField): number {
  const id = form.next++
  field.options.push({ id, value: '', named: false, label: empty() })
  return id
}

/** Đổi kiểu ô, đặt giá trị mặc định hợp với kiểu mới (độ dài của ô chữ, một lựa chọn trống). */
export function setBuilderWidget(form: BuilderForm, field: BuilderField, widget: BuilderWidget): void {
  field.widget = widget
  const { TEXT_LENGTH, TEXTAREA_LENGTH } = BUILDER_LIMITS
  if (widget === 'text' && (field.maxLength === null || field.maxLength === TEXTAREA_LENGTH)) {
    field.maxLength = TEXT_LENGTH
  }
  if (widget === 'textarea' && (field.maxLength === null || field.maxLength === TEXT_LENGTH)) {
    field.maxLength = TEXTAREA_LENGTH
  }
  if ((widget === 'select' || widget === 'radio') && field.options.length === 0) addBuilderOption(form, field)
  if (widget === 'checkbox') field.required = true
}

/** Đổi chỗ phần tử index với phần tử kề (delta -1: lên, 1: xuống); trả chỗ mới, -1 nếu đã ở đầu hoặc cuối. */
export function moveBuilderItem<T>(list: T[], index: number, delta: -1 | 1): number {
  const to = index + delta
  if (index < 0 || index >= list.length || to < 0 || to >= list.length) return -1
  const [item] = list.splice(index, 1)
  list.splice(to, 0, item!)
  return to
}

export function removeBuilderField(form: BuilderForm, id: number): void {
  form.fields = form.fields.filter((f) => f.id !== id)
  for (const f of form.fields) if (f.after === id) f.after = null
}

/**
 * Suy lại khóa form, tên trường, giá trị lựa chọn chưa được người dùng tự đặt; tên suy ra không trùng tên đã có, không
 * trùng biến hệ thống hay tên Flowable (thêm số). Chỉ ghi khi khác, nên gọi lại trong watch không lặp mãi.
 */
export function syncBuilderNames(form: BuilderForm): void {
  if (!form.keyed) {
    const key = builderSlug(form.title.vi)
    if (form.key !== key) form.key = key
  }
  const taken = new Set([...TAKEN, ...form.fields.filter((f) => f.named).map((f) => f.name)])
  for (const f of form.fields) {
    if (!f.named) {
      const name = unique(builderName(f.label.vi), taken)
      if (f.name !== name) f.name = name
    }
    const values = new Set(f.options.filter((o) => o.named).map((o) => o.value))
    for (const o of f.options) {
      if (o.named) continue
      const value = unique(builderSlug(o.label.vi, false), values)
      if (o.value !== value) o.value = value
    }
  }
}

/**
 * Giữ nguyên khóa form, tên trường, giá trị lựa chọn đang có (gọi khi tải tệp về): quy trình viết theo tệp đã tải không
 * đổi nghĩa khi sau đó xóa hay đổi thứ tự trường làm tên suy ra (ngay, ngay2…) đổi chỗ cho nhau.
 */
export function freezeBuilderNames(form: BuilderForm): void {
  if (form.key) form.keyed = true
  for (const f of form.fields) {
    if (f.name) f.named = true
    for (const o of f.options) if (o.value) o.named = true
  }
}

export function builderFormKey(form: BuilderForm): string {
  return `${form.app}.${form.key}`
}

function finite(value: number | null): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function property(field: BuilderField, widget: BuilderWidget): Record<string, unknown> {
  const prop: Record<string, unknown> = {}
  const label = clean(field.label.vi)
  if (label) prop.title = label
  if (widget === 'text' || widget === 'textarea') {
    prop.type = 'string'
    const min = field.required ? Math.max(1, field.minLength ?? 0) : field.minLength ?? 0
    if (finite(min) && min > 0) prop.minLength = min
    if (finite(field.maxLength)) prop.maxLength = field.maxLength
    prop.$ref = widget === 'text' ? '#/$defs/line' : '#/$defs/text'
  } else if (widget === 'date') {
    Object.assign(prop, { type: 'string', format: 'date' })
    if (field.dateRule) prop['x-moc-date'] = field.dateRule
  } else if (widget === 'number') {
    prop.type = field.integer ? 'integer' : 'number'
    if (finite(field.minimum)) prop.minimum = field.minimum
    if (finite(field.maximum)) prop.maximum = field.maximum
  } else if (widget === 'select' || widget === 'radio') {
    prop.type = 'string'
    // không lựa chọn nào thì không có enum (enum rỗng làm hỏng cả bản xem trước); trình dựng báo lỗi "options"
    if (field.options.length) prop.enum = field.options.map((o) => clean(o.value))
  } else {
    prop.type = 'boolean'
  }
  const ui: Record<string, unknown> = { widget, label: bilingual(field.label) }
  if (clean(field.help.vi) || clean(field.help.en)) ui.help = bilingual(field.help)
  if (widget === 'textarea' && finite(field.rows)) ui.rows = field.rows
  if ((widget === 'select' || widget === 'radio') && field.options.length) {
    ui.options = Object.fromEntries(field.options.map((o) => [clean(o.value), bilingual(o.label)]))
  }
  prop['x-moc-ui'] = ui
  return prop
}

/**
 * Tệp form dưới dạng đối tượng. Dựng được cả khi còn lỗi (để xem trước): trường trùng tên thì trường sau đè trường
 * trước, cặp ngày hỏng bị bỏ — builderProblems() báo những chỗ đó.
 */
export function builderSchema(form: BuilderForm): Record<string, unknown> {
  const byId = new Map(form.fields.map((f) => [f.id, f]))
  const properties: Record<string, unknown> = {}
  const required: string[] = []
  const ranges: [string, string][] = []
  const defs = new Set<'line' | 'text'>()
  for (const f of form.fields) {
    Object.defineProperty(properties, f.name, { value: property(f, f.widget), enumerable: true, writable: true,
      configurable: true })
    if ((f.required || f.widget === 'checkbox') && !required.includes(f.name)) required.push(f.name)
    if (f.widget === 'text') defs.add('line')
    if (f.widget === 'textarea') defs.add('text')
    const from = f.after === null ? undefined : byId.get(f.after)
    if (f.widget === 'date' && from?.widget === 'date' && from.name && f.name && from.name !== f.name) {
      ranges.push([from.name, f.name])
    }
  }
  const title = clean(form.title.vi)
  const schema: Record<string, unknown> = { $schema: FORM_LIMITS.DRAFT }
  if (APP.test(form.app) && FORM_KEY.test(form.key)) schema.$id = `urn:moc:app:${form.app}:form:${form.key}`
  if (title) schema.title = title
  schema['x-moc-title'] = bilingual(form.title)
  schema['x-moc-order'] = [...new Set(form.fields.map((f) => f.name))]
  if (ranges.length) schema['x-moc-range'] = ranges
  Object.assign(schema, { 'x-moc-nfc': true, type: 'object', additionalProperties: false, required, properties })
  if (defs.size) schema.$defs = Object.fromEntries([...defs].sort().map((d) => [d, BUILDER_DEFS[d]]))
  return schema
}

// Ký tự vô hình trong chuỗi (pattern của $defs, dấu cách đặc biệt) ghi thành \uXXXX để tệp tải về đọc được bằng mắt.
// Ngoài chuỗi JSON chỉ có dấu cách và xuống dòng của phần thụt lề; xuống dòng trong chuỗi JSON.stringify đã ghi là \n
const INVISIBLE = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\u115f\u1160\u3164\uffa0]|[^ \P{Zs}]/gu
const escape = (c: string) => [...Array(c.length).keys()]
  .map((i) => `\\u${c.charCodeAt(i).toString(16).padStart(4, '0')}`).join('')

/** Nội dung tệp tải về: JSON thụt hai dấu cách, kết thúc bằng xuống dòng. */
export function builderFile(form: BuilderForm): string {
  return `${JSON.stringify(builderSchema(form), null, 2).replace(INVISIBLE, (c) => (c === '\n' ? c : escape(c)))}\n`
}

function lengthOk(f: BuilderField): boolean {
  const { maxLength: max, minLength: min } = f
  return finite(max) && Number.isInteger(max) && max >= 1 && max <= BUILDER_LIMITS.MAX_LENGTH
    && (min === null || (finite(min) && Number.isInteger(min) && min >= 0 && min <= max))
}

function fieldProblems(form: BuilderForm, f: BuilderField, seen: Set<string>): BuilderProblem[] {
  const out: BuilderProblem[] = []
  const add = (code: BuilderProblemCode, option?: number) => out.push({ code, field: f.id, option })
  const labelled = Boolean(clean(f.label.vi))
  if (!labelled) add('label')
  // tên suy từ nhãn rỗng vì chưa có nhãn: lỗi "label" đã đủ
  if (TAKEN.has(f.name)) add('name-reserved')
  else if (!VARIABLE.test(f.name)) {
    if (f.named || labelled) add('name')
  } else if (seen.has(f.name)) add('name-taken')
  seen.add(f.name)
  if ((f.widget === 'text' || f.widget === 'textarea') && !lengthOk(f)) add('length')
  if (f.widget === 'textarea' && f.rows !== null
    && !(Number.isInteger(f.rows) && f.rows >= 1 && f.rows <= BUILDER_LIMITS.MAX_ROWS)) add('rows')
  if (f.widget === 'number') {
    const bounds = [f.minimum, f.maximum].filter((b) => b !== null)
    if (!bounds.every((b) => finite(b) && (!f.integer || Number.isInteger(b)))
      || (finite(f.minimum) && finite(f.maximum) && f.minimum > f.maximum)) add('bounds')
  }
  if (f.widget === 'select' || f.widget === 'radio') {
    if (!f.options.length) add('options')
    const values = new Set<string>()
    for (const o of f.options) {
      const value = clean(o.value)
      const labelled = Boolean(clean(o.label.vi))
      if (!labelled) add('option-label', o.id)
      if (!value) {
        if (o.named || labelled) add('option-value', o.id)
      } else if (values.has(value)) add('option-taken', o.id)
      values.add(value)
    }
  }
  if (f.widget === 'date' && f.after !== null) {
    const from = form.fields.find((g) => g.id === f.after)
    if (!from || from.widget !== 'date' || from.id === f.id) add('after')
    else if (inLoop(form, f)) add('after-loop')
  }
  return out
}

// A không trước B, B không trước A (hay vòng dài hơn): form chỉ gửi được khi mọi ngày trong vòng bằng nhau
function inLoop(form: BuilderForm, f: BuilderField): boolean {
  const after = new Map(form.fields.map((g) => [g.id, g.after]))
  const seen = new Set<number>()
  for (let id = f.after; id !== null && !seen.has(id); id = after.get(id) ?? null) {
    if (id === f.id) return true
    seen.add(id)
  }
  return false
}

/**
 * Lỗi của form đang dựng, theo thứ tự trên trang; [] là tải được. Luật lúc cài (checkForm) chỉ chạy khi các luật của
 * trình dựng đã qua, làm lưới cuối cho điều trình dựng không tự bắt (tệp quá lớn, quá nhiều bước kiểm).
 */
export function builderProblems(form: BuilderForm): BuilderProblem[] {
  const out: BuilderProblem[] = []
  const { APP_MIN, APP_MAX, FORM_KEY_MAX } = BUILDER_LIMITS
  if (!(APP.test(form.app) && form.app.length >= APP_MIN && form.app.length <= APP_MAX)) out.push({ code: 'app' })
  if (!FORM_KEY.test(form.key) || builderFormKey(form).length > FORM_KEY_MAX) out.push({ code: 'key' })
  if (!clean(form.title.vi)) out.push({ code: 'title' })
  if (!form.fields.length) out.push({ code: 'fields' })
  const seen = new Set<string>()
  for (const f of form.fields) out.push(...fieldProblems(form, f, seen))
  if (out.length) return out
  return checkForm(builderFile(form)).map((p) => ({
    code: 'rule', rule: p.rule, field: form.fields.find((f) => f.name === p.field)?.id,
  }))
}
