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

// Biên dịch sẵn JSON Schema dùng chung (schemas/*.json ở gốc repo) thành hàm kiểm JavaScript lúc build —
// poka-yoke lớp 1 (F2.2). Ajv thường sinh mã bằng new Function ngay trên trình duyệt, mà CSP của ứng dụng
// không cho 'unsafe-eval' (nginx/security-headers.conf). Chế độ standalone sinh mã kiểm thành module lúc
// build, nên Ajv chỉ là phụ thuộc lúc dựng, không vào bundle.
//
// Ứng dụng nhập module ảo `virtual:moc-forms`: mỗi schema thành một hàm kiểm (van-ban-den.json → vanBanDen),
// kèm `schemas` để form đọc độ dài tối đa, danh mục, x-moc-date.

import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { _ } from 'ajv'
import Ajv2020 from 'ajv/dist/2020.js'
import standaloneCode from 'ajv/dist/standalone/index.js'

export const VIRTUAL = 'virtual:moc-forms'

// Định dạng tự viết cho khớp từng ký tự với svc-workflow (services/svc-workflow/src/svc_workflow/schemas.py):
// YYYY-MM-DD là ngày có thật, UUID đủ 36 ký tự có gạch nối.
function date(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (!m) return false
  const y = Number(m[1]), mo = Number(m[2]), d = Number(m[3])
  const feb = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28
  return y >= 1 && mo >= 1 && mo <= 12 && d >= 1 && d <= [31, feb, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1]
}
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/

// Độ dài theo ký tự (code point) như Python len() và PostgreSQL char_length(), không theo đơn vị UTF-16
function ucs2length(str) {
  let length = 0
  for (const _ch of str) length++
  return length
}

const path = (dir) => (dir instanceof URL ? fileURLToPath(dir) : dir)

/** Các tệp schema trong thư mục (đường dẫn hoặc URL file:, bỏ tệp ca thử *.cases.json). */
export function schemaFiles(dir) {
  dir = path(dir)
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json') && !f.endsWith('.cases.json'))
    .sort()
    .map((file) => ({
      name: file.replace(/\.json$/, '').replace(/-([a-z])/g, (_m, c) => c.toUpperCase()),
      file,
      schema: JSON.parse(readFileSync(join(dir, file), 'utf8')),
    }))
}

/** Mã nguồn module `virtual:moc-forms`: hàm kiểm của mọi schema, không cần eval, không require. */
export function formsSource(dir) {
  const files = schemaFiles(dir)
  const ajv = new Ajv2020({
    allErrors: true, strict: true, allowUnionTypes: true,
    code: { source: true, esm: true, formats: _`formats` },
  })
  // Hai từ khóa chú thích JSON Schema không diễn đạt được (ngày so với hôm nay, chuỗi dạng NFC):
  // app/utils/forms.ts và svc-workflow tự kiểm
  ajv.addKeyword({ keyword: 'x-moc-date', schemaType: 'string' })
  ajv.addKeyword({ keyword: 'x-moc-nfc', schemaType: 'boolean' })
  ajv.addFormat('date', date)
  ajv.addFormat('uuid', UUID)
  for (const f of files) ajv.addSchema(f.schema)
  const code = standaloneCode(ajv, Object.fromEntries(files.map((f) => [f.name, f.schema.$id])))
    .replaceAll('require("ajv/dist/runtime/ucs2length").default', 'ucs2length')
  const left = code.match(/require\([^)]*\)/)
  if (left) throw new Error(`Mã kiểm sinh từ schemas/ còn ${left[0]}: thêm hàm thay thế vào scripts/forms.mjs`)
  return [
    `const formats = { date: ${date} };`,
    `${ucs2length}`,
    code,
    `export const schemas = ${JSON.stringify(Object.fromEntries(files.map((f) => [f.name, f.schema])))};`,
  ].join('\n')
}

/** Plugin Vite: phục vụ `virtual:moc-forms`, dựng lại khi sửa schema lúc `nuxt dev`. */
export function formsPlugin(dir) {
  const resolved = `\0${VIRTUAL}`
  return {
    name: 'moc-forms',
    resolveId: (id) => (id === VIRTUAL ? resolved : null),
    load(id) {
      if (id !== resolved) return null
      for (const f of schemaFiles(dir)) this.addWatchFile(join(path(dir), f.file))
      return formsSource(dir)
    },
  }
}
