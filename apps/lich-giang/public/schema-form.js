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

// Form dựng từ JSON Schema (#303) cho ứng dụng cài thêm: thêm một form chỉ cần một tệp trong forms/, không viết mã
// giao diện. JS thuần, không thư viện, không bundler. Trang gọi mountForm(); phần còn lại không đụng trình duyệt nên
// test bằng node --test (tests/schema-form.test.js).
//
// Trình duyệt kiểm bằng đúng tệp schema mà svc-workflow kiểm lại khi nhận dữ liệu qua API của ứng dụng (#301). Lỗi
// quy về {trường: mã} giống hệt máy chủ (services/svc-workflow/src/svc_workflow/schemas.py) và form của Văn phòng,
// nên các bên chạy chung ca thử *.cases.json. Bộ kiểm đi từng từ khóa, không sinh mã (CSP không cho 'unsafe-eval'),
// và chỉ hiểu tập từ khóa ghi ở schemas/README.md: schema dùng điều khác thì báo ngay lúc nạp, không lặng lẽ bỏ qua.
//
// Gợi ý hiển thị nằm trong schema: x-moc-title, x-moc-order ở gốc; x-moc-ui ở từng trường (widget, label, note, help,
// rows, options, errors). Chữ là chuỗi hoặc {vi, en}. Câu chung (ô không bắt buộc, câu báo lỗi theo mã, schema hỏng)
// lấy từ bảng dịch của ứng dụng (i18n.js, khóa form.*, schema.*). Mọi chữ gán bằng textContent, không bao giờ
// innerHTML.

import { t } from './i18n.js'

// từ khóa chỉ để chú thích, không kiểm gì; x-moc-* do formErrors() hay phần vẽ form đọc
const NOTES = new Set(['$schema', '$id', '$defs', '$comment', 'title', 'description', 'default', 'examples'])
const TYPES = new Set(['string', 'number', 'integer', 'boolean', 'null', 'array', 'object'])

// Một trường sai nhiều điều thì báo điều đứng trước — cùng thứ tự với svc-workflow và Văn phòng
export const PRIORITY = ['type', 'required', 'additionalProperties', 'enum', 'format', 'pattern', 'minLength',
  'maxLength', 'not', 'x-moc-nfc', 'uniqueItems', 'maxItems', 'x-moc-date', 'x-moc-range']

// Định dạng viết khớp từng ký tự với svc-workflow: YYYY-MM-DD là ngày có thật, UUID đủ 36 ký tự
function isDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (!m) return false
  const y = Number(m[1]), mo = Number(m[2]), d = Number(m[3])
  const feb = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28
  return y >= 1 && mo >= 1 && mo <= 12 && d >= 1 && d <= [31, feb, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1]
}
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/
const FORMATS = { date: isDate, uuid: (s) => UUID.test(s) }

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)

// Từ khóa có tác dụng kiểm mà bộ này hiểu, kèm dạng giá trị hợp lệ: "required": "ab" hay "enum": "x" bị từ chối lúc
// nạp, không để bộ kiểm hiểu sai
const isCount = (v) => Number.isInteger(v) && v >= 0
const isSchema = (v) => typeof v === 'boolean' || isObject(v)
const SHAPES = {
  $ref: (v) => typeof v === 'string',
  type: (v) => (Array.isArray(v) ? v.length > 0 && v.every((t) => TYPES.has(t)) : TYPES.has(v)),
  enum: (v) => Array.isArray(v) && v.length > 0,
  const: () => true,
  required: (v) => Array.isArray(v) && v.every((n) => typeof n === 'string'),
  properties: (v) => isObject(v),
  additionalProperties: isSchema,
  items: isSchema,
  not: isSchema,
  allOf: (v) => Array.isArray(v) && v.length > 0,
  minItems: isCount,
  maxItems: isCount,
  uniqueItems: (v) => typeof v === 'boolean',
  minLength: isCount,
  maxLength: isCount,
  pattern: (v) => typeof v === 'string',
  format: (v) => typeof v === 'string' && Object.hasOwn(FORMATS, v),
  minimum: Number.isFinite,
  maximum: Number.isFinite,
}
// độ dài theo ký tự (code point) như Python len()
const length = (s) => [...s].length

function typeOf(v) {
  if (v === null) return 'null'
  if (Array.isArray(v)) return 'array'
  return typeof v
}
function hasType(want, v) {
  return (Array.isArray(want) ? want : [want]).some((t) => {
    if (t === 'integer') return typeof v === 'number' && Number.isInteger(v)
    return t === typeOf(v)
  })
}
function same(a, b) {
  if (a === b) return true
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => same(x, b[i]))
  if (isObject(a) && isObject(b)) {
    const keys = Object.keys(a)
    return keys.length === Object.keys(b).length && keys.every((k) => Object.hasOwn(b, k) && same(a[k], b[k]))
  }
  return false
}
// tên trường trong instancePath theo JSON Pointer: "~" thành "~0", "/" thành "~1"
const pointer = (key) => `/${String(key).replaceAll('~', '~0').replaceAll('/', '~1')}`

class Checker {
  #patterns = new Map()
  #root

  constructor(root) {
    this.#root = root
    this.#inspect(root, '#')
    this.#acyclic(root, [])
    this.#hints(root)
  }

  // Duyệt cả schema lúc nạp: từ khóa lạ, giá trị từ khóa sai dạng, kiểu lạ, định dạng lạ, $ref ra ngoài, pattern hỏng
  // đều ném lỗi ngay (câu theo ngôn ngữ đang dùng, trang hiện kèm câu "không nạp được mẫu đơn")
  #inspect(node, at) {
    if (typeof node === 'boolean') return
    if (!isObject(node)) throw new Error(t('schema.notObject', { at }))
    for (const [key, value] of Object.entries(node)) {
      if (key === '$defs' && !isObject(value)) throw new Error(t('schema.defs', { at }))
      if (NOTES.has(key) || key.startsWith('x-moc-')) continue
      if (!Object.hasOwn(SHAPES, key)) throw new Error(t('schema.keyword', { at, key }))
      if (key === 'type' && !SHAPES.type(value)) throw new Error(t('schema.type', { at, type: JSON.stringify(value) }))
      if (key === 'format' && !SHAPES.format(value)) throw new Error(t('schema.format', { at, format: String(value) }))
      if (!SHAPES[key](value)) throw new Error(t('schema.shape', { at, key, value: JSON.stringify(value) }))
      if (key === 'pattern') this.#regex(value)
      if (key === '$ref') this.#resolve(value)
    }
    for (const [name, sub] of Object.entries(node.$defs ?? {})) this.#inspect(sub, `${at}/$defs/${name}`)
    for (const [name, sub] of Object.entries(node.properties ?? {})) this.#inspect(sub, `${at}/${name}`)
    for (const key of ['items', 'not', 'additionalProperties']) {
      if (node[key] !== undefined) this.#inspect(node[key], `${at}/${key}`)
    }
    for (const [i, sub] of (node.allOf ?? []).entries()) this.#inspect(sub, `${at}/allOf/${i}`)
  }

  // cờ "u" cho mọi pattern như Ajv, để \p{…} và ký tự ngoài BMP khớp như Python re
  #regex(source) {
    let re = this.#patterns.get(source)
    if (!re) {
      re = new RegExp(source, 'u')
      this.#patterns.set(source, re)
    }
    return re
  }

  #resolve(ref) {
    const m = typeof ref === 'string' ? /^#\/\$defs\/([^/]+)$/.exec(ref) : null
    const defs = this.#root.$defs
    // Object.hasOwn: "#/$defs/constructor", "#/$defs/__proto__" không được trỏ vào prototype
    const target = m && isObject(defs) && Object.hasOwn(defs, m[1]) ? defs[m[1]] : undefined
    if (target === undefined) throw new Error(t('schema.ref', { ref: String(ref) }))
    return target
  }

  // $ref vòng (A → B → A, kể cả qua properties, items, allOf, not) thì từ chối: bộ kiểm có thể đệ quy mãi trên cùng
  // một dữ liệu. Form không cần schema đệ quy
  #acyclic(node, refs) {
    if (!isObject(node)) return
    if (node.$ref !== undefined) {
      if (refs.includes(node.$ref)) throw new Error(t('schema.cycle', { path: [...refs, node.$ref].join(' → ') }))
      this.#acyclic(this.#resolve(node.$ref), [...refs, node.$ref])
    }
    for (const sub of Object.values(node.properties ?? {})) this.#acyclic(sub, refs)
    for (const key of ['items', 'not', 'additionalProperties']) this.#acyclic(node[key], refs)
    for (const sub of node.allOf ?? []) this.#acyclic(sub, refs)
  }

  // Gợi ý hiển thị sai thì form thiếu ô, vẽ sai ô hay so sai cặp ngày mà không ai biết, nên cũng báo lúc nạp
  #hints(root) {
    const props = root.properties ?? {}
    const names = Object.keys(props)
    const order = root['x-moc-order']
    if (order !== undefined && !(Array.isArray(order) && order.length === names.length
      && names.every((n) => order.includes(n)))) {
      throw new Error(t('schema.order'))
    }
    const ranges = root['x-moc-range']
    if (ranges !== undefined && !Array.isArray(ranges)) throw new Error(t('schema.ranges'))
    for (const pair of ranges ?? []) {
      const dates = Array.isArray(pair) && pair.length === 2
        && pair.every((n) => typeof n === 'string' && Object.hasOwn(props, n) && props[n].format === 'date')
      if (!dates) throw new Error(t('schema.range', { pair: JSON.stringify(pair) }))
    }
    for (const [name, prop] of Object.entries(props)) {
      const ui = prop['x-moc-ui']
      if (ui === undefined) continue
      if (!isObject(ui)) throw new Error(t('schema.ui', { name }))
      if (ui.widget !== undefined && !WIDGETS.has(ui.widget)) {
        throw new Error(t('schema.widget', { name, widget: String(ui.widget) }))
      }
    }
  }

  /** Lỗi dạng {keyword, instancePath, params} như Ajv, đẩy vào out. */
  check(s, data, path, out) {
    if (s === true) return
    if (s === false) {
      out.push({ keyword: 'false schema', instancePath: path, params: {} })
      return
    }
    const fail = (keyword, params = {}) => out.push({ keyword, instancePath: path, params })
    if (s.$ref !== undefined) this.check(this.#resolve(s.$ref), data, path, out)
    // sai kiểu thì các điều khác của trường này không còn nghĩa; formErrors() vẫn chỉ giữ "type" vì nó đứng đầu
    if (s.type !== undefined && !hasType(s.type, data)) {
      fail('type', { type: s.type })
      return
    }
    if (Array.isArray(s.enum) && !s.enum.some((v) => same(v, data))) fail('enum', { allowedValues: s.enum })
    if (Object.hasOwn(s, 'const') && !same(s.const, data)) fail('const', { allowedValue: s.const })
    if (typeof data === 'string') {
      const n = length(data)
      if (typeof s.maxLength === 'number' && n > s.maxLength) fail('maxLength', { limit: s.maxLength })
      if (typeof s.minLength === 'number' && n < s.minLength) fail('minLength', { limit: s.minLength })
      if (typeof s.pattern === 'string' && !this.#regex(s.pattern).test(data)) fail('pattern', { pattern: s.pattern })
      if (typeof s.format === 'string' && !FORMATS[s.format](data)) fail('format', { format: s.format })
    }
    if (typeof data === 'number') {
      if (typeof s.maximum === 'number' && data > s.maximum) fail('maximum', { limit: s.maximum })
      if (typeof s.minimum === 'number' && data < s.minimum) fail('minimum', { limit: s.minimum })
    }
    if (Array.isArray(data)) {
      if (typeof s.maxItems === 'number' && data.length > s.maxItems) fail('maxItems', { limit: s.maxItems })
      if (typeof s.minItems === 'number' && data.length < s.minItems) fail('minItems', { limit: s.minItems })
      if (s.items !== undefined) data.forEach((item, i) => this.check(s.items, item, path + pointer(i), out))
      if (s.uniqueItems === true && data.some((x, k) => data.findIndex((y) => same(x, y)) !== k)) fail('uniqueItems')
    }
    if (isObject(data)) {
      const props = s.properties ?? {}
      for (const name of s.required ?? []) {
        if (!Object.hasOwn(data, name)) fail('required', { missingProperty: name })
      }
      for (const [name, value] of Object.entries(data)) {
        if (Object.hasOwn(props, name)) this.check(props[name], value, path + pointer(name), out)
        else if (s.additionalProperties === false) fail('additionalProperties', { additionalProperty: name })
        else if (s.additionalProperties !== undefined) {
          this.check(s.additionalProperties, value, path + pointer(name), out)
        }
      }
    }
    if (s.not !== undefined) {
      const inner = []
      this.check(s.not, data, path, inner)
      if (!inner.length) fail('not')
    }
    for (const sub of s.allOf ?? []) this.check(sub, data, path, out)
  }
}

const checkers = new WeakMap()
/** Nạp schema một lần; ném lỗi nếu schema dùng điều bộ kiểm không hiểu. */
export function checkSchema(schema) {
  let c = checkers.get(schema)
  if (!c) {
    c = new Checker(schema)
    checkers.set(schema, c)
  }
  return c
}

function fieldOf(e) {
  if (e.keyword === 'required') return String(e.params.missingProperty)
  if (e.keyword === 'additionalProperties') return String(e.params.additionalProperty)
  const top = e.instancePath.split('/')[1]
  return top === undefined ? '' : top.replaceAll('~1', '/').replaceAll('~0', '~')
}
const rank = (code) => (PRIORITY.includes(code) ? PRIORITY.indexOf(code) : PRIORITY.length)

/** Hôm nay theo giờ Việt Nam (UTC+7, không đổi theo mùa), YYYY-MM-DD. */
export function todayVN(now = new Date()) {
  return new Date(now.getTime() + 7 * 3600_000).toISOString().slice(0, 10)
}

/**
 * Lỗi của dữ liệu theo schema, {} khi hợp lệ. Ngoài từ khóa JSON Schema còn ba từ khóa riêng: x-moc-nfc ở gốc (mọi
 * chuỗi ở dạng dựng sẵn NFC) và x-moc-date ở trường (so với hôm nay), kiểm như svc-workflow; x-moc-range ở gốc
 * ([[a, b], …], hai trường ngày: b không được trước a; bỏ qua khi a hoặc b đã sai điều khác; mã gắn vào b),
 * svc-workflow thêm cùng #301.
 */
export function formErrors(schema, data, today = todayVN()) {
  // Map chứ không phải {}: tên trường do người gửi đặt, có thể là "constructor", "__proto__"…
  const found = new Map()
  const add = (name, code) => {
    const kept = found.get(name)
    if (kept === undefined || rank(code) < rank(kept)) found.set(name, code)
  }
  const out = []
  checkSchema(schema).check(schema, data, '', out)
  for (const e of out) add(fieldOf(e), e.keyword)
  if (isObject(data)) {
    const props = new Map(Object.entries(schema.properties ?? {}))
    if (schema['x-moc-nfc'] === true) {
      for (const [name, value] of Object.entries(data)) {
        if (props.has(name) && typeof value === 'string' && value !== value.normalize('NFC')) add(name, 'x-moc-nfc')
      }
    }
    for (const [name, prop] of props) {
      const rule = prop['x-moc-date']
      const value = data[name]
      if (!rule || found.has(name) || typeof value !== 'string') continue
      if ((rule === 'not-after-today' && value > today) || (rule === 'not-before-today' && value < today)) {
        found.set(name, 'x-moc-date')
      }
    }
    for (const [a, b] of schema['x-moc-range'] ?? []) {
      if (found.has(a) || found.has(b) || typeof data[a] !== 'string' || typeof data[b] !== 'string') continue
      if (data[b] < data[a]) found.set(b, 'x-moc-range')
    }
  }
  const errors = {}
  for (const [name, code] of found) {
    Object.defineProperty(errors, name, { value: code, enumerable: true, writable: true })
  }
  return errors
}

const WIDGETS = new Set(['text', 'textarea', 'date', 'number', 'select', 'radio', 'checkbox', 'checkboxes'])

/** Chữ trong schema theo ngôn ngữ: chuỗi giữ nguyên, {vi, en} lấy đúng tiếng, thiếu thì lấy tiếng kia. */
export function say(text, lang) {
  if (text === undefined || text === null) return ''
  if (typeof text === 'string') return text
  return text[lang] ?? text.vi ?? text.en ?? ''
}

/** Tên form theo ngôn ngữ (x-moc-title, không có thì title). */
export const formTitle = (schema, lang = 'vi') => say(schema['x-moc-title'], lang) || String(schema.title ?? '')

function widgetOf(prop, ui, types) {
  if (WIDGETS.has(ui.widget)) return ui.widget
  if (types.includes('array')) return 'checkboxes'
  if (Array.isArray(prop.enum)) return 'select'
  if (types.includes('boolean')) return 'checkbox'
  if (prop.format === 'date') return 'date'
  if (types.includes('integer') || types.includes('number')) return 'number'
  return typeof prop.maxLength === 'number' && prop.maxLength > 200 ? 'textarea' : 'text'
}

/**
 * Các ô của form theo x-moc-order (không có thì theo thứ tự trong properties), cả ô ẩn: tên, id, kiểu ô, nhãn,
 * gợi ý, các lựa chọn kèm nhãn. Chỉ đọc schema, không đụng trình duyệt.
 */
export function fields(schema, lang = 'vi', idPrefix = 'sf-') {
  const props = schema.properties ?? {}
  const order = Array.isArray(schema['x-moc-order']) ? schema['x-moc-order'] : Object.keys(props)
  const required = new Set(schema.required ?? [])
  return order.filter((name) => Object.hasOwn(props, name)).map((name) => {
    const prop = props[name]
    const ui = isObject(prop['x-moc-ui']) ? prop['x-moc-ui'] : {}
    const types = [prop.type].flat().filter((x) => x !== undefined)
    const widget = widgetOf(prop, ui, types)
    const values = (widget === 'checkboxes' ? prop.items?.enum : prop.enum) ?? []
    return {
      name,
      id: ui.id ?? `${idPrefix}${name}`,
      widget,
      required: required.has(name),
      nullable: types.includes('null'),
      hidden: ui.hidden === true,
      prop,
      ui,
      label: say(ui.label, lang) || String(prop.title ?? name),
      note: say(ui.note, lang),
      help: say(ui.help, lang),
      options: values.map((value) => ({ value, label: say(ui.options?.[String(value)], lang) || String(value) })),
    }
  })
}

// Dọn như form tiếp nhận văn bản đến của Văn phòng: đưa về NFC, bỏ ký tự ẩn và khoảng trắng hai đầu; ô một dòng gộp
// xuống dòng thành dấu cách. Schema vẫn từ chối dữ liệu bẩn gửi thẳng vào API, chỉ người gõ tay là được dọn giúp
export const oneLine = (s) => s.normalize('NFC').replace(/[\t\n\v\f\r\p{Zl}\p{Zp}]+/gu, ' ')
  .replace(/[\p{Cc}\p{Cf}]/gu, '').trim()
export const multiLine = (s) => s.normalize('NFC').replace(/\r\n?|[\p{Zl}\p{Zp}]/gu, '\n')
  .replace(/[\t\v\f]+/g, ' ').replace(/[^\n\P{Cc}]|\p{Cf}/gu, '').trim()

/** Dữ liệu gửi đi từ giá trị các ô: chuỗi đã dọn; ô để trống thì bỏ (thiếu ô bắt buộc thành lỗi required). */
export function clean(list, values) {
  const data = {}
  for (const f of list) {
    let value = values[f.name]
    if (typeof value === 'string' && f.widget === 'number') {
      const n = value.trim() === '' ? NaN : Number(value)
      value = value.trim() === '' ? '' : Number.isFinite(n) ? n : value
    } else if (typeof value === 'string' && f.widget !== 'select' && f.widget !== 'radio') {
      value = f.widget === 'textarea' ? multiLine(value) : oneLine(value)
    }
    const empty = value === undefined || value === '' || (Array.isArray(value) && !value.length && !f.required)
    if (!empty) data[f.name] = value
    else if (f.nullable && !f.required) data[f.name] = null
  }
  return data
}

// Câu chung theo ngôn ngữ truyền vào hàm (lang của form), không theo ngôn ngữ đang dùng của trang
const word = (lang, key, params = {}) => t(key, params, lang)

/** Câu báo cho một mã lỗi của một ô; x-moc-ui.errors của trường thay câu chung. list: mọi ô, để gọi tên ô kia. */
export function message(f, code, lang = 'vi', list = [], schema = {}) {
  const own = f.ui.errors?.[code]
  if (own) return say(own, lang)
  const p = f.prop
  switch (code) {
    case 'required': return word(lang, 'form.required')
    case 'minLength':
      if (typeof p.minLength !== 'number' || p.minLength <= 1) return word(lang, 'form.required')
      return typeof p.maxLength === 'number'
        ? word(lang, 'form.between', { min: p.minLength, max: p.maxLength })
        : word(lang, 'form.minLength', { min: p.minLength })
    case 'maxLength': return word(lang, 'form.maxLength', { max: p.maxLength })
    case 'minimum': return word(lang, 'form.minimum', { min: p.minimum })
    case 'maximum': return word(lang, 'form.maximum', { max: p.maximum })
    case 'minItems': return word(lang, 'form.minItems', { min: p.minItems })
    case 'maxItems': return word(lang, 'form.maxItems', { max: p.maxItems })
    case 'format': case 'pattern': return f.widget === 'date' ? word(lang, 'form.date') : word(lang, 'form.format')
    case 'x-moc-date':
      return p['x-moc-date'] === 'not-after-today'
        ? word(lang, 'form.notAfterToday')
        : word(lang, 'form.notBeforeToday')
    case 'x-moc-range': {
      const pair = (schema['x-moc-range'] ?? []).find(([, b]) => b === f.name)
      const other = list.find((g) => g.name === pair?.[0])
      return word(lang, 'form.range', { other: other?.label ?? pair?.[0] ?? '' })
    }
    case 'x-moc-nfc': return word(lang, 'form.nfc')
    case 'not': return word(lang, 'form.not')
    case 'enum': return word(lang, 'form.enum')
    case 'const': return word(lang, 'form.const')
    case 'type': return word(lang, 'form.type')
    case 'uniqueItems': return word(lang, 'form.uniqueItems')
    case 'additionalProperties': return word(lang, 'form.additionalProperties')
    // mã chỉ máy chủ biết (vd duplicate) mà schema không đặt câu riêng trong x-moc-ui.errors
    default: return word(lang, 'form.invalid')
  }
}

function shown(f, value, lang) {
  if (value === undefined || value === null || value === '') return word(lang, 'form.empty')
  if (Array.isArray(value)) {
    return value.length ? value.map((v) => shown(f, v, lang)).join(', ') : word(lang, 'form.empty')
  }
  const option = f.options.find((o) => same(o.value, value))
  if (option) return option.label
  if (typeof value === 'boolean') return value ? word(lang, 'form.yes') : word(lang, 'form.no')
  if (f.widget === 'date' && typeof value === 'string' && isDate(value)) return value.split('-').reverse().join('/')
  return String(value)
}

/** Dữ liệu một đơn để đọc (vd người duyệt xem đơn): nhãn ô và giá trị đã đổi ra chữ, theo thứ tự của form. */
export function summary(schema, data, lang = 'vi') {
  return fields(schema, lang).filter((f) => !f.hidden)
    .map((f) => ({ name: f.name, label: f.label, value: shown(f, data?.[f.name], lang) }))
}

/**
 * Dựng form vào container. onSubmit(data) chỉ được gọi với dữ liệu đã dọn và qua kiểm; nút gửi khóa đến khi promise
 * của nó xong. Trả về setErrors(lỗi {trường: mã}, vd từ 422 của máy chủ), values() (dữ liệu đã dọn) và reset().
 * options.draft: chữ đang gõ dở điền vào ô lúc dựng (trang dựng lại form khi đổi ngôn ngữ); khác values, reset() không
 * quay về draft mà về values hay default của schema.
 */
export function mountForm(container, schema, options = {}) {
  const { values: given = {}, draft, onSubmit, submitLabel, idPrefix = 'sf-' } = options
  const lang = String(options.lang ?? 'vi').toLowerCase().startsWith('en') ? 'en' : 'vi'
  checkSchema(schema)
  const list = fields(schema, lang, idPrefix)
  const doc = container.ownerDocument
  const make = (tag, props = {}) => Object.assign(doc.createElement(tag), props)
  const ranges = schema['x-moc-range'] ?? []
  const today = todayVN()

  // Trường ẩn (x-moc-ui.hidden) không có ô: giá trị lấy từ values hay default của schema, gửi đi nguyên như vậy. Bắt
  // buộc mà không có giá trị thì người dùng không bao giờ gửi được form, nên báo ngay lúc dựng
  const start = (f) => (Object.hasOwn(given, f.name) ? given[f.name] : f.prop.default)
  const hidden = list.filter((f) => f.hidden)
  for (const f of hidden) {
    if (f.required && start(f) === undefined) {
      throw new Error(word(lang, 'schema.hidden', { name: f.name }))
    }
  }

  const form = make('form', { className: 'sf', noValidate: true })
  const title = formTitle(schema, lang)
  if (title) form.setAttribute('aria-label', title)
  // lỗi của trường không có ô (trường ẩn, trường lạ máy chủ báo, cả đơn sai kiểu): báo ở đầu form. Dấu ":" trong id để
  // không trùng id của ô nào (id ô là idPrefix + tên trường, lỗi của ô thêm "-error")
  const top = make('div', { className: 'sf-error sf-top', id: `${idPrefix}:errors`, hidden: true })
  top.setAttribute('role', 'alert')
  form.append(top)

  const controls = new Map()
  for (const f of list.filter((g) => !g.hidden)) controls.set(f.name, field(f))

  const submit = make('button', { type: 'submit', className: 'sf-submit' })
  submit.textContent = submitLabel || word(lang, 'form.submit')
  const actions = make('div', { className: 'sf-actions' })
  actions.append(submit)
  form.append(actions)

  function field(f) {
    const group = f.widget === 'radio' || f.widget === 'checkboxes'
    const wrap = make(group ? 'fieldset' : 'div', { className: `sf-field sf-${f.widget}` })
    const caption = make(group ? 'legend' : 'label', { className: 'sf-label', textContent: f.label })
    if (!group) caption.htmlFor = f.id
    const mark = f.note || (f.required ? '' : word(lang, 'form.optional'))
    if (mark && f.widget !== 'checkbox') {
      caption.append(' ', make('span', { className: 'sf-note', textContent: `(${mark})` }))
    }
    const help = f.help ? make('p', { className: 'sf-help', id: `${f.id}-help`, textContent: f.help }) : null
    // Câu lỗi của từng ô không là role=alert (nhiều ô sai sẽ đọc dồn một lượt): ô sai đầu tiên nhận tiêu điểm và đọc
    // câu lỗi qua aria-describedby, các ô sau đọc khi người dùng tới
    const error = make('p', { className: 'sf-error', id: `${f.id}-error`, hidden: true })
    let inputs, get, set

    if (group) {
      const box = make('div', { className: 'sf-options' })
      const radio = f.widget === 'radio'
      inputs = f.options.map((o, i) => {
        // giá trị của ô là số thứ tự lựa chọn: lựa chọn trong enum có thể là số, null…, không chỉ chuỗi
        const input = make('input', { type: radio ? 'radio' : 'checkbox', name: f.id, value: String(i) })
        if (i === 0) input.id = f.id
        if (radio && f.required) input.required = true
        const option = make('label')
        option.append(input, make('span', { textContent: o.label }))
        box.append(option)
        return input
      })
      wrap.append(caption, box)
      get = () => (radio
        ? f.options[inputs.findIndex((x) => x.checked)]?.value
        : f.options.filter((_o, i) => inputs[i].checked).map((o) => o.value))
      set = (v) => inputs.forEach((x, i) => {
        x.checked = radio ? same(f.options[i].value, v) : [v].flat().some((y) => same(y, f.options[i].value))
      })
    } else if (f.widget === 'checkbox') {
      const input = make('input', { type: 'checkbox', id: f.id, name: f.id })
      caption.prepend(input, ' ')
      inputs = [input]
      wrap.append(caption)
      get = () => input.checked
      set = (v) => { input.checked = v === true }
    } else {
      let input
      if (f.widget === 'select') {
        input = make('select')
        input.append(make('option', { value: '', textContent: word(lang, 'form.pick') }))
        f.options.forEach((o, i) => input.append(make('option', { value: String(i), textContent: o.label })))
        get = () => (input.value === '' ? undefined : f.options[Number(input.value)]?.value)
        set = (v) => {
          const i = f.options.findIndex((o) => same(o.value, v))
          input.value = i < 0 ? '' : String(i)
        }
      } else {
        input = make(f.widget === 'textarea' ? 'textarea' : 'input')
        if (f.widget === 'textarea') input.rows = f.ui.rows ?? 4
        else input.type = f.widget === 'date' || f.widget === 'number' ? f.widget : 'text'
        if (typeof f.prop.maxLength === 'number') input.maxLength = f.prop.maxLength
        if (f.widget === 'number') {
          if (typeof f.prop.minimum === 'number') input.min = String(f.prop.minimum)
          if (typeof f.prop.maximum === 'number') input.max = String(f.prop.maximum)
          input.step = [f.prop.type].flat().includes('integer') ? '1' : 'any'
        }
        // bộ chọn ngày không mời chọn ngày sẽ bị từ chối
        if (f.prop['x-moc-date'] === 'not-before-today') input.min = today
        if (f.prop['x-moc-date'] === 'not-after-today') input.max = today
        get = () => input.value
        set = (v) => { input.value = v === undefined || v === null ? '' : String(v) }
      }
      // name là id chứ không là tên trường: ô tên "append", "submit"… sẽ che phương thức cùng tên của form
      Object.assign(input, { id: f.id, name: f.id, required: f.required })
      inputs = [input]
      wrap.append(caption, input)
    }
    if (help) wrap.append(help)
    wrap.append(error)
    form.append(wrap)
    // gợi ý và câu lỗi gắn vào từng ô (cả từng nút chọn), trình đọc màn hình đọc chắc hơn gắn vào fieldset
    const describe = (bad) => {
      const ids = [help?.id, bad ? error.id : ''].filter(Boolean).join(' ')
      for (const x of inputs) {
        if (ids) x.setAttribute('aria-describedby', ids)
        else x.removeAttribute('aria-describedby')
      }
    }
    describe(false)
    return {
      f, inputs, get, set,
      show(text) {
        error.textContent = text
        error.hidden = !text
        for (const x of inputs) x.setAttribute('aria-invalid', String(Boolean(text)))
        describe(Boolean(text))
      },
    }
  }

  // ô "đến" của một cặp x-moc-range không mời chọn ngày trước ô "từ"
  for (const [a, b] of ranges) {
    const from = controls.get(a), to = controls.get(b)
    if (from?.f.widget !== 'date' || to?.f.widget !== 'date') continue
    from.inputs[0].addEventListener('input', () => { to.inputs[0].min = from.get() })
  }

  const read = () => Object.fromEntries([
    ...hidden.map((f) => [f.name, start(f)]),
    ...[...controls].map(([name, c]) => [name, c.get()]),
  ])
  const current = () => clean(list, read())

  function setErrors(errors = {}) {
    const rest = []
    for (const c of controls.values()) c.show('')
    for (const [name, code] of Object.entries(errors ?? {})) {
      const c = controls.get(name)
      if (c) {
        c.show(message(c.f, code, lang, list, schema))
        continue
      }
      // ô ẩn, trường lạ máy chủ báo, hay cả đơn sai kiểu (tên rỗng)
      const f = list.find((g) => g.name === name) ?? { name, label: name, widget: 'text', ui: {}, prop: {} }
      const text = message(f, code, lang, list, schema)
      rest.push(f.label ? `${f.label}: ${text}` : text)
    }
    top.replaceChildren()
    if (rest.length) {
      top.append(make('p', { textContent: word(lang, 'form.top') }))
      const ul = make('ul')
      ul.append(...rest.map((text) => make('li', { textContent: text })))
      top.append(ul)
    }
    top.hidden = !rest.length
    // tiêu điểm về ô sai đầu tiên theo thứ tự trên form; chỉ có lỗi chung thì về dòng báo đầu form
    const first = list.map((f) => controls.get(f.name)).find((c) => c && Object.hasOwn(errors ?? {}, c.f.name))
    if (first) first.inputs[0].focus()
    else if (rest.length) {
      top.tabIndex = -1
      top.focus()
    }
  }

  // điền mọi ô theo value(trường), rồi đặt lại ngày nhỏ nhất của ô "đến" theo ô "từ"
  function fill(value) {
    for (const c of controls.values()) c.set(value(c.f))
    for (const [a, b] of ranges) {
      const from = controls.get(a), to = controls.get(b)
      if (from?.f.widget === 'date' && to?.f.widget === 'date') to.inputs[0].min = from.get()
    }
  }

  function reset() {
    fill(start)
    setErrors({})
  }

  let busy = false
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (busy) return
    const data = current()
    const errors = formErrors(schema, data, todayVN())
    setErrors(errors)
    if (Object.keys(errors).length || !onSubmit) return
    // aria-disabled chứ không disabled: nút disabled làm rơi tiêu điểm về đầu trang; bấm lại lúc đang gửi đã bị busy
    // chặn
    busy = true
    submit.setAttribute('aria-disabled', 'true')
    try {
      await onSubmit(data)
    } finally {
      busy = false
      submit.removeAttribute('aria-disabled')
    }
  })

  reset()
  if (isObject(draft)) fill((f) => (Object.hasOwn(draft, f.name) ? draft[f.name] : start(f)))
  container.replaceChildren(form)
  return { setErrors, values: current, reset }
}
