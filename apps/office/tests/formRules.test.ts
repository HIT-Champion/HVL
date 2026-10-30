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

// #303 bước 1a: luật kiểm tệp form lúc cài, bản trên trình duyệt, chạy đúng bộ ca thử mà check_form của svc-workflow
// chạy (services/svc-workflow/tests/app_form_rules.cases.json, cách viết ở $comment của tệp). Chạy: npm test.

import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'
import { FORM_LIMITS, FORM_RULES, SERVER_ONLY_RULES, checkForm } from '../app/utils/formRules.ts'
import type { FormRule } from '../app/utils/formRules.ts'

interface Case {
  name: string
  set?: Record<string, unknown>
  unset?: string[]
  text?: unknown[]
  errors?: FormRule[]
}

const ROOT = new URL('../../../', import.meta.url)
const CASES = JSON.parse(readFileSync(new URL('services/svc-workflow/tests/app_form_rules.cases.json', ROOT), 'utf8'))

// DSL của tệp ca thử: {"$repeat": s, "times": n} và {"$nest": k, "times": n, "leaf": v}
function value(v: unknown): unknown {
  if (v !== null && typeof v === 'object' && '$repeat' in v) {
    const { $repeat, times } = v as { $repeat: string, times: number }
    return $repeat.repeat(times)
  }
  if (v !== null && typeof v === 'object' && '$nest' in v) {
    const { $nest, times, leaf } = v as { $nest: string, times: number, leaf: unknown }
    let node = leaf
    for (let i = 0; i < times; i++) node = { [$nest]: node }
    return node
  }
  return v
}

// Nội dung tệp form của một ca: text ghép lại, hoặc base sửa theo set, unset (JSON Pointer, "" là cả tệp)
function file(c: Case): string {
  if (c.text) return c.text.map((part) => value(part)).join('')
  let form: unknown = structuredClone(CASES.base)
  const parent = (pointer: string): [Record<string, unknown>, string] => {
    const path = pointer.slice(1).split('/')
    const last = path.pop()!
    let node = form as Record<string, unknown>
    for (const part of path) node = node[part] as Record<string, unknown>
    return [node, last]
  }
  for (const [pointer, v] of Object.entries(c.set ?? {})) {
    if (pointer === '') {
      form = value(v)
    } else {
      const [node, key] = parent(pointer)
      node[key] = value(v)
    }
  }
  for (const pointer of c.unset ?? []) {
    const [node, key] = parent(pointer)
    delete node[key]
  }
  return JSON.stringify(form)
}

for (const kind of ['valid', 'invalid']) {
  for (const c of CASES[kind] as Case[]) {
    test(`${kind}: ${c.name}`, () => {
      const want = (c.errors ?? []).filter((rule) => !SERVER_ONLY_RULES.includes(rule)).sort()
      assert.deepEqual(checkForm(file(c)).map((p) => p.rule).sort(), want)
    })
  }
}

test('mã luật, luật chỉ máy chủ kiểm và hằng số giống tệp ca thử chung', () => {
  assert.deepEqual(FORM_RULES, CASES.rules)
  assert.deepEqual(SERVER_ONLY_RULES, CASES.serverOnly)
  assert.deepEqual(FORM_LIMITS, CASES.constants)
  const covered = new Set((CASES.invalid as Case[]).flatMap((c) => c.errors ?? []))
  assert.deepEqual(FORM_RULES.filter((rule) => !covered.has(rule)), [])
})

test('form thật của các ứng dụng mẫu qua mọi luật', () => {
  const apps = new URL('apps/', ROOT)
  let checked = 0
  for (const app of readdirSync(apps)) {
    const forms = new URL(`${app}/forms/`, apps)
    let files: string[]
    try {
      files = readdirSync(forms)
    } catch {
      continue
    }
    for (const name of files.filter((f) => f.endsWith('.json') && !f.endsWith('.cases.json'))) {
      assert.deepEqual(checkForm(readFileSync(new URL(name, forms), 'utf8')), [], `${app}/forms/${name}`)
      checked++
    }
  }
  assert.ok(checked >= 2)
})

test('luật theo từng trường báo tên trường, các luật khác báo chỗ sai', () => {
  const form = JSON.parse(file({ name: 'base' }))
  form.properties.tenantId = { type: 'string' }
  form.properties.soLuong.format = 'email'
  form.required.push('mauSac')
  assert.deepEqual(checkForm(JSON.stringify(form)), [
    { rule: 'reserved', field: 'tenantId' },
    { rule: 'required', detail: '"mauSac"' },
    { rule: 'format', detail: 'email' },
  ])
})

test('tên trường như constructor, __proto__ không đọc nhầm prototype', () => {
  const form = JSON.parse(file({ name: 'base' }))
  form.required = ['constructor']
  assert.deepEqual(checkForm(JSON.stringify(form)).map((p) => p.rule), ['required'])
  const text = file({ name: 'base' }).replace('"properties":{', '"properties":{"__proto__":{"type":"string"},')
  assert.deepEqual(checkForm(text), [{ rule: 'field-name', field: '__proto__' }])
})
