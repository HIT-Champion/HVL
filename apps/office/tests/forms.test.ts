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

// Poka-yoke lớp 1 (F2.2): mã kiểm sinh lúc build từ schemas/van-ban-den.json cho đúng kết quả của bộ ca thử dùng
// chung với svc-workflow và CSDL. Chạy: npm test (node --test, không cần trình duyệt).

import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { formsSource } from '../scripts/forms.mjs'
import { formErrors } from '../app/utils/forms.ts'
import type { JsonSchema, SchemaError, Validate } from '../app/utils/forms.ts'

interface Case { name: string, set?: Record<string, unknown>, unset?: string[], error?: Record<string, string> }

const SCHEMAS = fileURLToPath(new URL('../../../schemas/', import.meta.url))
const CASES = JSON.parse(readFileSync(join(SCHEMAS, 'van-ban-den.cases.json'), 'utf8'))
const TODAY = '2026-10-19'

// Nạp đúng module mà Vite đưa vào bundle
const source = formsSource(SCHEMAS)
const dir = mkdtempSync(join(tmpdir(), 'moc-forms-'))
writeFileSync(join(dir, 'forms.mjs'), source)
const forms = await import(pathToFileURL(join(dir, 'forms.mjs')).href)
after(() => rmSync(dir, { recursive: true, force: true }))
const validate: Validate = forms.vanBanDen
const schema: JsonSchema = forms.schemas.vanBanDen

function value(v: unknown): unknown {
  if (v !== null && typeof v === 'object' && '$repeat' in v) {
    const r = v as { $repeat: string, times: number }
    return r.$repeat.repeat(r.times)
  }
  if (v !== null && typeof v === 'object' && '$nfd' in v) return (v as { $nfd: string }).$nfd.normalize('NFD')
  const m = typeof v === 'string' ? /^today([+-]\d+)?$/.exec(v) : null
  if (!m) return v
  const [y, mo, d] = TODAY.split('-').map(Number)
  return new Date(Date.UTC(y!, mo! - 1, d! + Number(m[1] ?? 0))).toISOString().slice(0, 10)
}

function build(c: Case): Record<string, unknown> {
  const data: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(CASES.base)) data[k] = value(v)
  for (const [k, v] of Object.entries(c.set ?? {})) data[k] = value(v)
  for (const k of c.unset ?? []) delete data[k]
  return data
}

for (const c of CASES.valid as Case[]) {
  test(`hợp lệ: ${c.name}`, () => {
    assert.deepEqual(formErrors(validate, schema, build(c), TODAY), {})
  })
}

for (const c of CASES.invalid as Case[]) {
  test(`bị chặn: ${c.name}`, () => {
    assert.deepEqual(formErrors(validate, schema, build(c), TODAY), c.error)
  })
}

test('không phải đối tượng thì sai kiểu ở gốc', () => {
  assert.deepEqual(formErrors(validate, schema, ['CV'], TODAY), { '': 'type' })
  assert.deepEqual(formErrors(validate, schema, null, TODAY), { '': 'type' })
})

test('mã kiểm chạy được dưới CSP không có unsafe-eval: không new Function, không require', () => {
  assert.doesNotMatch(source, /new Function|\beval\(|require\(/)
})

test('một tệp schema thành một hàm kiểm, ca thử không bị coi là schema', () => {
  assert.equal(typeof forms.vanBanDen, 'function')
  assert.deepEqual(Object.keys(forms.schemas), ['vanBanDen'])
})

test('một trường sai nhiều điều: giữ điều đứng trước trong PRIORITY, cùng hạng thì điều gặp trước', () => {
  const failing = (...errors: SchemaError[]): Validate => Object.assign(() => false, { errors })
  const at = (keyword: string, field: string): SchemaError => ({ keyword, instancePath: `/${field}`, params: {} })
  const plain: JsonSchema = { properties: { so_ky_hieu: {}, trich_yeu: {} } }
  // từ khóa lạ cùng xếp sau mọi từ khóa đã biết: giữ cái gặp trước
  const mixed = failing(at('maxLength', 'so_ky_hieu'), at('pattern', 'so_ky_hieu'), at('x-la', 'trich_yeu'),
    at('x-khac', 'trich_yeu'))
  assert.deepEqual(formErrors(mixed, plain, {}, TODAY), { so_ky_hieu: 'pattern', trich_yeu: 'x-la' })
  // x-moc-nfc gom sau lỗi của schema: đứng trước uniqueItems thì thay, đứng sau maxLength thì không
  const nfc: JsonSchema = { 'x-moc-nfc': true, properties: { ten: {} } }
  const decomposed = { ten: 'Hoà'.normalize('NFD') }
  assert.deepEqual(formErrors(failing(at('uniqueItems', 'ten')), nfc, decomposed, TODAY), { ten: 'x-moc-nfc' })
  assert.deepEqual(formErrors(failing(at('maxLength', 'ten')), nfc, decomposed, TODAY), { ten: 'maxLength' })
  // x-moc-date chỉ báo cho trường chưa có lỗi
  const dated: JsonSchema = {
    properties: { ngay: { 'x-moc-date': 'not-after-today' }, han: { 'x-moc-date': 'not-before-today' } },
  }
  assert.deepEqual(formErrors(failing(at('format', 'ngay')), dated, { ngay: '2999-01-01', han: '2000-01-01' }, TODAY),
    { ngay: 'format', han: 'x-moc-date' })
  assert.deepEqual(formErrors(Object.assign(() => true, { errors: null }), plain, {}, TODAY), {})
})
