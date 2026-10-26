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

// F2.9: mọi chữ hiện trên giao diện đi qua vue-i18n, để bản tiếng Anh không lộ câu tiếng Việt và không hiện tên khóa
// thay cho câu. Quét mọi app/**/*.vue, app/**/*.ts bằng regex và một bộ tách chuỗi đơn giản, không phải trình phân
// tích TypeScript hay Vue đầy đủ:
//   * khóa viết thẳng trong t('…'), $t('…') là một câu (lá) trong vi.json — en.json cùng khóa, cùng tham số đã có test
//     ở answer.test.ts;
//   * khóa ghép t(`a.b.${x}`): phần viết thẳng "a.b." phải mở đầu ít nhất một khóa của vi.json;
//   * phần <template> không có chữ tiếng Việt có dấu, trừ trong chú thích HTML;
//   * chuỗi tiếng Việt trong mã chỉ được là trường `vi:` của dữ liệu song ngữ { vi, en } (vd app/utils/hpdi.ts).
// Không kiểm ở đây: khóa truyền qua biến (`t(n.label)` của pha-he.vue — nhãn lấy từ app/utils/lineage.ts, test riêng ở
// lineage.test.ts) và lời gọi qua đối tượng (`i18n.global.t(…)`, hiện không có).
// Hướng dẫn dịch cho người đóng góp: CONTRIBUTING.md, mục "Dịch giao diện".

import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'

const APP = new URL('../app/', import.meta.url)
type Messages = { [key: string]: string | Messages }
const vi = JSON.parse(readFileSync(new URL('locales/vi.json', APP), 'utf8')) as Messages

const sources = readdirSync(APP, { recursive: true, encoding: 'utf8' })
  .filter((f) => /\.(vue|ts)$/.test(f)).sort()
  .map((f) => ({ file: `app/${f}`, text: readFileSync(new URL(f, APP), 'utf8') }))

// chữ cái tiếng Việt có dấu: đủ để nhận ra một câu tiếng Việt (câu viết không dấu thì không bắt được)
const VIET = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/iu
// t('khóa' …), $t("khóa" …) và t(`khóa`) không có ${}; không bắt te(, rt(, hay .t( của đối tượng khác
const LITERAL = /(?<![\w$.])\$?t\(\s*(['"`])([\w.-]+)\1/g
const DYNAMIC = /(?<![\w$.])\$?t\(\s*`([^`$]*)\$\{/g

const keys: string[] = []
;(function flatten(node: Messages, prefix: string) {
  for (const [k, v] of Object.entries(node)) {
    if (typeof v === 'string') keys.push(prefix + k)
    else flatten(v, `${prefix}${k}.`)
  }
})(vi, '')
const leaves = new Set(keys)

const lineOf = (text: string, at: number) => text.slice(0, at).split('\n').length

test('khóa viết thẳng trong t() là một câu có trong vi.json', () => {
  const missing: string[] = []
  let calls = 0
  for (const { file, text } of sources) {
    for (const m of text.matchAll(LITERAL)) {
      calls++
      if (!leaves.has(m[2]!)) missing.push(`${file}:${lineOf(text, m.index)}: ${m[2]}`)
    }
  }
  assert.deepEqual(missing, [])
  // cận dưới, không phải số đúng (26/10: 72 tệp, 1011 lời gọi): bộ quét hỏng thì đỏ, sửa mã bình thường thì không
  assert.ok(sources.length >= 60, `chỉ quét ${sources.length} tệp`)
  assert.ok(calls >= 900, `chỉ thấy ${calls} lời gọi t('…')`)
})

test("khóa ghép t(`a.b.${x}`): phần viết thẳng mở đầu một khóa có trong vi.json", () => {
  const missing: string[] = []
  let calls = 0
  for (const { file, text } of sources) {
    for (const m of text.matchAll(DYNAMIC)) {
      if (!m[1]) continue                              // cả khóa là biểu thức: không có phần viết thẳng để kiểm
      calls++
      if (!keys.some((k) => k.startsWith(m[1]!))) missing.push(`${file}:${lineOf(text, m.index)}: ${m[1]}`)
    }
  }
  assert.deepEqual(missing, [])
  assert.ok(calls >= 80, `chỉ thấy ${calls} lời gọi t(\`…\${…}\`)`)    // 26/10: 93
})

// Phần template, chú thích HTML thay bằng khoảng trắng để giữ đúng số dòng
function template(text: string): { body: string, offset: number } {
  const start = text.indexOf('<template')
  const end = text.lastIndexOf('</template>')
  if (start < 0 || end < start) return { body: '', offset: 0 }
  return { body: text.slice(start, end).replace(/<!--[\s\S]*?-->/g, (c) => c.replace(/[^\n]/g, ' ')), offset: start }
}

test('template không có chữ tiếng Việt viết cứng, mọi câu đi qua t()', () => {
  const found: string[] = []
  let templates = 0
  for (const { file, text } of sources.filter((s) => s.file.endsWith('.vue'))) {
    const { body, offset } = template(text)
    if (body) templates++
    for (const [i, line] of body.split('\n').entries()) {
      if (VIET.test(line)) found.push(`${file}:${lineOf(text, offset) + i}: ${line.trim().slice(0, 100)}`)
    }
  }
  assert.deepEqual(found, [])
  assert.ok(templates >= 35, `chỉ thấy ${templates} template`)        // 26/10: 41
})

interface Str { at: number, value: string }
const REGEX_AFTER = new Set(['return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete', 'void', 'throw',
  'yield', 'await'])

// Các chuỗi '…', "…" và phần chữ của `…` trong mã, kể cả chuỗi nằm trong ${…} lồng nhau; bỏ qua chú thích // và
// /* */, biểu thức chính quy /…/. Comment trong repo viết tiếng Việt và chuỗi có thể chứa "//" (URL), nên phải tách
// theo token chứ không xóa comment trên văn bản thô.
function strings(code: string): Str[] {
  const out: Str[] = []
  // "/" ngay sau từ khóa (return /…/, typeof /…/) mở regex, sau tên biến hay số là phép chia
  const afterKeyword = (i: number, prev: string) =>
    /[\w$]/.test(prev) && REGEX_AFTER.has(/[\w$]+$/.exec(code.slice(Math.max(0, i - 20), i).trimEnd())?.[0] ?? '')
  // quét mã từ i tới khi gặp "}" đóng ${…} (depth về 0) hoặc hết; trả vị trí dừng
  function scan(i: number, closing: boolean): number {
    let prev = ''                                       // ký tự có nghĩa gần nhất: "/" là phép chia hay mở regex
    let depth = 0
    for (; i < code.length; i++) {
      const c = code[i]!
      if (c === '/' && code[i + 1] === '/') {
        const eol = code.indexOf('\n', i)
        i = eol < 0 ? code.length : eol
      } else if (c === '/' && code[i + 1] === '*') {
        const end = code.indexOf('*/', i + 2)
        i = end < 0 ? code.length : end + 1
      } else if (c === '/' && (prev === '' || '(,=:[!&|?{};+-*%<>~^'.includes(prev) || afterKeyword(i, prev))) {
        let inClass = false
        for (i++; i < code.length && (code[i] !== '/' || inClass); i++) {
          if (code[i] === '\\') i++
          else if (code[i] === '[') inClass = true
          else if (code[i] === ']') inClass = false
        }
        prev = '/'
      } else if (c === "'" || c === '"') {
        const start = i
        for (i++; i < code.length && code[i] !== c && code[i] !== '\n'; i++) if (code[i] === '\\') i++
        out.push({ at: start, value: code.slice(start + 1, i) })
        prev = c
      } else if (c === '`') {
        i = backtick(i)
        prev = c
      } else if (c === '{') {
        depth++
        prev = c
      } else if (c === '}') {
        if (closing && depth === 0) return i
        depth--
        prev = c
      } else if (!/\s/.test(c)) {
        prev = c
      }
    }
    return i
  }
  // `…`: từng đoạn chữ giữa các ${…} là một chuỗi; phần trong ${…} là mã, quét lại như trên
  function backtick(i: number): number {
    let start = i + 1
    for (i++; i < code.length && code[i] !== '`'; i++) {
      if (code[i] === '\\') i++
      else if (code[i] === '$' && code[i + 1] === '{') {
        out.push({ at: start - 1, value: code.slice(start, i) })
        i = scan(i + 2, true)
        start = i + 1
      }
    }
    out.push({ at: start - 1, value: code.slice(start, i) })
    return i
  }
  scan(0, false)
  return out
}

function scripts(file: string, text: string): { body: string, offset: number }[] {
  if (file.endsWith('.ts')) return [{ body: text, offset: 0 }]
  return [...text.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
    .map((m) => ({ body: m[1]!, offset: m.index + m[0].indexOf('>') + 1 }))
}

test('chuỗi tiếng Việt trong mã chỉ là trường vi: của dữ liệu song ngữ { vi, en }', () => {
  const found: string[] = []
  let bilingual = 0
  for (const { file, text } of sources) {
    for (const { body, offset } of scripts(file, text)) {
      for (const s of strings(body)) {
        if (!VIET.test(s.value)) continue
        if (/\bvi\s*:\s*$/.test(body.slice(Math.max(0, s.at - 20), s.at))) {
          bilingual++
          continue
        }
        found.push(`${file}:${lineOf(text, offset + s.at)}: ${s.value.slice(0, 100)}`)
      }
    }
  }
  assert.deepEqual(found, [])
  assert.ok(bilingual >= 1, 'bộ tách chuỗi không thấy trường vi: nào (app/utils/hpdi.ts có)')
})
