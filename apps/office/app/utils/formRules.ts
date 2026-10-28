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

// #303 bước 1a: luật mà svc-workflow kiểm một tệp form của ứng dụng lúc `moc app install` (check_form trong
// services/svc-workflow/src/svc_workflow/apps/forms.py), chép sang trình duyệt để trình dựng form báo lỗi ngay. Mỗi
// luật trả một mã thay cho câu tiếng Việt của máy chủ, để giao diện tự dịch. Hai bên chạy chung bộ ca thử
// services/svc-workflow/tests/app_form_rules.cases.json, gồm cả các hằng số dưới đây (tests/formRules.test.ts,
// test_app_forms.py): sửa luật ở máy chủ thì sửa cả tệp này và tệp ca thử.
//
// Hai luật chỉ máy chủ kiểm (SERVER_ONLY_RULES): pattern dễ quay lui bùng nổ (cần bộ phân tích biểu thức của re) và
// JSON Schema 2020-12 hợp lệ theo meta-schema (Ajv biên dịch lúc chạy cần 'unsafe-eval', CSP không cho). Vì vậy số bước
// ước lượng ở đây không cộng phần của pattern. Tệp này không dùng gì của Nuxt để Node chạy test được.

export type FormRule = 'size' | 'json' | 'depth' | 'root' | 'draft' | 'root-type' | 'additional-properties'
  | 'properties' | 'reserved' | 'engine-name' | 'field-name' | 'field-schema' | 'scalar' | 'enum' | 'x-moc-date'
  | 'required' | 'x-moc-range' | 'root-only' | 'ref-external' | 'dynamic-ref' | 'format' | 'pattern-properties'
  | 'ref-target' | 'ref-loop' | 'steps' | 'pattern' | 'schema'

export interface FormProblem {
  rule: FormRule
  // trường gây lỗi, với các luật theo từng trường
  field?: string
  // phần gây lỗi: từ khóa, giá trị format, $ref, các tên trường thiếu, số bước ước lượng
  detail?: string
}

type Json = null | boolean | number | string | Json[] | { [key: string]: Json }
type JsonObject = { [key: string]: Json }
type Cost = [steps: number, refDepth: number, levels: number]

// Cùng tên, cùng giá trị với forms.py; tập hợp ghi thành mảng đã sắp xếp
export const FORM_LIMITS = {
  DRAFT: 'https://json-schema.org/draft/2020-12/schema',
  // biến hệ thống svc-workflow đặt từ token lúc bắt đầu quy trình
  RESERVED: ['tenantId', 'departmentId', 'initiator'],
  // tên Flowable giải thành giá trị của động cơ trong biểu thức BPMN, trước khi tìm biến
  ENGINE_NAMES: ['execution', 'task', 'authenticatedUserId', 'currentTenantId'],
  VARIABLE: '[a-z][A-Za-z0-9]{0,63}',
  SCALAR_TYPES: ['boolean', 'integer', 'null', 'number', 'string'],
  FORMATS: ['date', 'uuid'],
  DATE_RULES: ['not-after-today', 'not-before-today'],
  MAX_FORM_BYTES: 256 * 1024,
  MAX_DEPTH: 32,
  MAX_REF_DEPTH: 16,
  // chỉ số mảng trong JSON Pointer của $ref
  ARRAY_INDEX: '0|[1-9][0-9]{0,8}',
  NODE_STEPS: 3000,
  MAX_FORM_STEPS: 3 * 10 ** 7,
  ROOT_ONLY: ['$id', '$anchor', '$dynamicAnchor', '$recursiveAnchor'],
  SUBSCHEMA: ['not', 'if', 'then', 'else', 'items', 'contains', 'additionalProperties', 'propertyNames',
    'unevaluatedItems', 'unevaluatedProperties'],
  SUBSCHEMA_LISTS: ['allOf', 'anyOf', 'oneOf', 'prefixItems'],
  SUBSCHEMA_MAPS: ['properties', 'patternProperties', 'dependentSchemas'],
}

export const FORM_RULES: FormRule[] = ['size', 'json', 'depth', 'root', 'draft', 'root-type', 'additional-properties',
  'properties', 'reserved', 'engine-name', 'field-name', 'field-schema', 'scalar', 'enum', 'x-moc-date', 'required',
  'x-moc-range', 'root-only', 'ref-external', 'dynamic-ref', 'format', 'pattern-properties', 'ref-target', 'ref-loop',
  'steps', 'pattern', 'schema']

export const SERVER_ONLY_RULES: FormRule[] = ['pattern', 'schema']

const VARIABLE = new RegExp(`^(?:${FORM_LIMITS.VARIABLE})$`)
const ARRAY_INDEX = new RegExp(`^(?:${FORM_LIMITS.ARRAY_INDEX})$`)
const encoder = new TextEncoder()
const decoder = new TextDecoder()

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

// Đọc khóa của đối tượng JSON: chỉ khóa của chính nó, không lấy constructor, toString… của prototype
function own(node: JsonObject, key: string): Json | undefined {
  return Object.hasOwn(node, key) ? node[key] : undefined
}

function oneOf(value: unknown, allowed: string[]): boolean {
  return typeof value === 'string' && allowed.includes(value)
}

function scalar(value: Json): boolean {
  return value === null || typeof value !== 'object'
}

// Số tầng đối tượng, mảng lồng nhau; đi bằng vòng lặp như _depth của máy chủ
function depth(value: Json): number {
  let deepest = 0
  const stack: [Json, number][] = [[value, 1]]
  while (stack.length > 0) {
    const [node, level] = stack.pop()!
    if (node === null || typeof node !== 'object') continue
    deepest = Math.max(deepest, level)
    for (const child of Array.isArray(node) ? node : Object.values(node)) stack.push([child, level + 1])
  }
  return deepest
}

// Như _walk: schema = đang ở trong schema (dưới x-moc-* là câu chữ cho giao diện), root = đang ở gốc form. Từ khóa
// pattern (chỉ máy chủ kiểm) bỏ qua
function walk(node: Json, problems: FormProblem[], schema = true, root = true): void {
  if (Array.isArray(node)) {
    for (const value of node) walk(value, problems, schema, false)
    return
  }
  if (!isObject(node)) return
  for (const [key, value] of Object.entries(node)) {
    if (FORM_LIMITS.ROOT_ONLY.includes(key) && schema && !root) {
      problems.push({ rule: 'root-only', detail: key })
    } else if (key === '$ref' && typeof value === 'string' && !value.startsWith('#')) {
      problems.push({ rule: 'ref-external', detail: value })
    } else if (key === '$dynamicRef' || key === '$recursiveRef') {
      problems.push({ rule: 'dynamic-ref', detail: key })
    } else if (key === 'format' && typeof value === 'string' && !FORM_LIMITS.FORMATS.includes(value)) {
      problems.push({ rule: 'format', detail: value })
    } else if ((key === 'patternProperties' || key === 'propertyNames') && schema) {
      problems.push({ rule: 'pattern-properties', detail: key })
    }
    walk(value, problems, schema && !key.startsWith('x-moc'), false)
  }
}

class RefProblem extends Error {
  problem: FormProblem

  constructor(rule: 'ref-target' | 'ref-loop' | 'depth', ref?: string) {
    super(rule)
    this.problem = ref === undefined ? { rule } : { rule, detail: ref }
  }
}

// %XX liền nhau là các byte UTF-8, byte sai thành U+FFFD — như urllib.parse.unquote
function unquote(text: string): string {
  return text.replace(/(?:%[0-9A-Fa-f]{2})+/g,
    (run) => decoder.decode(Uint8Array.from(run.slice(1).split('%'), (hex) => parseInt(hex, 16))))
}

// "#/…" (JSON Pointer) trong chính form → đích. Giải %XX cả chuỗi rồi mới tách theo "/", như _resolve
function resolve(root: JsonObject, ref: string): Json {
  if (ref !== '#' && !ref.startsWith('#/')) throw new RefProblem('ref-target', ref)
  let node: Json = root
  for (const raw of ref === '#' ? [] : unquote(ref.slice(2)).split('/')) {
    const part = raw.replaceAll('~1', '/').replaceAll('~0', '~')
    if (isObject(node) && Object.hasOwn(node, part)) node = node[part]!
    else if (Array.isArray(node) && ARRAY_INDEX.test(part) && Number(part) < node.length) node = node[Number(part)]!
    else throw new RefProblem('ref-target', ref)
  }
  return node
}

function* subschemas(node: JsonObject): Generator<Json | undefined> {
  for (const key of FORM_LIMITS.SUBSCHEMA) yield own(node, key)
  for (const key of FORM_LIMITS.SUBSCHEMA_LISTS) {
    const list = own(node, key)
    if (Array.isArray(list)) yield* list
  }
  for (const key of FORM_LIMITS.SUBSCHEMA_MAPS) {
    const map = own(node, key)
    if (isObject(map)) yield* Object.values(map)
  }
}

// Như _cost: [số bước, số tầng $ref sâu nhất bên dưới, số tầng schema từ node trở xuống kể cả qua $ref], node ở tầng
// level tính từ gốc. refs: các đích $ref đang đi qua; memo: kết quả theo đích (so bằng chính đối tượng, như id() của
// Python)
function cost(node: Json | undefined, root: JsonObject, refs: Json[], memo: Map<Json, Cost>, level: number): Cost {
  if (!isObject(node)) return [0, 0, 0]
  if (level > FORM_LIMITS.MAX_DEPTH) throw new RefProblem('depth')
  let steps = FORM_LIMITS.NODE_STEPS
  let deepest = 0
  let levels = 1
  const ref = own(node, '$ref')
  if (typeof ref === 'string' && ref.startsWith('#')) {
    const target = resolve(root, ref)
    if (refs.includes(target) || refs.length >= FORM_LIMITS.MAX_REF_DEPTH) throw new RefProblem('ref-loop', ref)
    if (!memo.has(target)) memo.set(target, cost(target, root, [...refs, target], memo, level + 1))
    const [subSteps, subDepth, subLevels] = memo.get(target)!
    // đích đã tính từ chỗ nông hơn, chỗ này lồng sâu hơn
    if (refs.length + 1 + subDepth > FORM_LIMITS.MAX_REF_DEPTH) throw new RefProblem('ref-loop', ref)
    if (level + subLevels > FORM_LIMITS.MAX_DEPTH) throw new RefProblem('depth')
    steps += subSteps
    deepest = subDepth + 1
    levels = subLevels + 1
  }
  for (const sub of subschemas(node)) {
    const [subSteps, subDepth, subLevels] = cost(sub, root, refs, memo, level + 1)
    steps += subSteps
    deepest = Math.max(deepest, subDepth)
    levels = Math.max(levels, subLevels + 1)
  }
  return [steps, deepest, levels]
}

/** Nội dung một tệp form → các luật bị vi phạm, [] khi qua mọi luật trình duyệt kiểm được. */
export function checkForm(text: string): FormProblem[] {
  if (encoder.encode(text).length > FORM_LIMITS.MAX_FORM_BYTES) return [{ rule: 'size' }]
  let schema: Json
  try {
    schema = JSON.parse(text)
  } catch {
    return [{ rule: 'json' }]
  }
  if (depth(schema) > FORM_LIMITS.MAX_DEPTH) return [{ rule: 'depth' }]
  if (!isObject(schema)) return [{ rule: 'root' }]
  const problems: FormProblem[] = []
  if (own(schema, '$schema') !== FORM_LIMITS.DRAFT) problems.push({ rule: 'draft' })
  if (own(schema, 'type') !== 'object') problems.push({ rule: 'root-type' })
  if (own(schema, 'additionalProperties') !== false) problems.push({ rule: 'additional-properties' })
  const props = own(schema, 'properties')
  if (!isObject(props) || Object.keys(props).length === 0) return [...problems, { rule: 'properties' }]
  for (const [name, prop] of Object.entries(props)) {
    if (FORM_LIMITS.RESERVED.includes(name)) problems.push({ rule: 'reserved', field: name })
    else if (FORM_LIMITS.ENGINE_NAMES.includes(name)) problems.push({ rule: 'engine-name', field: name })
    else if (!VARIABLE.test(name)) problems.push({ rule: 'field-name', field: name })
    if (!isObject(prop)) {
      problems.push({ rule: 'field-schema', field: name })
      continue
    }
    const type = own(prop, 'type')
    const types = type === undefined ? [] : Array.isArray(type) ? type : [type]
    if (!types.every((t) => oneOf(t, FORM_LIMITS.SCALAR_TYPES))) problems.push({ rule: 'scalar', field: name })
    const values = own(prop, 'enum')
    if (Array.isArray(values) && !values.every(scalar)) problems.push({ rule: 'enum', field: name })
    if (Object.hasOwn(prop, 'x-moc-date') && !oneOf(prop['x-moc-date'], FORM_LIMITS.DATE_RULES)) {
      problems.push({ rule: 'x-moc-date', field: name })
    }
  }
  const required = Object.hasOwn(schema, 'required') ? schema.required : []
  if (!Array.isArray(required)) {
    problems.push({ rule: 'required' })
  } else {
    const missing = required.filter((r) => !(typeof r === 'string' && Object.hasOwn(props, r)))
    const detail = missing.map((r) => JSON.stringify(r)).join(', ')
    if (missing.length > 0) problems.push({ rule: 'required', detail })
  }
  const dates = Object.keys(props).filter((name) => {
    const prop = props[name]
    return isObject(prop) && own(prop, 'format') === 'date'
  })
  const ranges = Object.hasOwn(schema, 'x-moc-range') ? schema['x-moc-range'] : []
  if (!Array.isArray(ranges) || !ranges.every((pair) => Array.isArray(pair) && pair.length === 2
    && pair[0] !== pair[1] && pair.every((name) => oneOf(name, dates)))) {
    problems.push({ rule: 'x-moc-range' })
  }
  walk(schema, problems)
  try {
    const [steps] = cost(schema, schema, [], new Map(), 1)
    if (steps > FORM_LIMITS.MAX_FORM_STEPS) problems.push({ rule: 'steps', detail: String(steps) })
  } catch (e) {
    if (!(e instanceof RefProblem)) throw e
    problems.push(e.problem)
  }
  return problems
}
