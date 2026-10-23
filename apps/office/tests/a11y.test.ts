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

// Hai luật giao diện của SonarQube kiểm lại ngay trong npm test (CI không chạy SonarQube): ô nhập có tên cho trình
// đọc màn hình (Web:InputWithoutLabelCheck) và nút trong <form> ghi rõ type (S9011, button-has-type). Đọc phần
// <template> của mọi app/**/*.vue bằng bộ tách thẻ regex có xét giá trị trong nháy (@click="(e) => …" chứa ">"), không
// phải trình phân tích Vue đầy đủ; xét từng tệp như SonarQube, không theo component con.

import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'

const APP = new URL('../app/', import.meta.url)
const VOID = new Set(['area', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'])
const FIELDS = new Set(['input', 'select', 'textarea'])
const NO_LABEL = new Set(['hidden', 'submit', 'button', 'image'])     // input không cần nhãn
const TAG = /<\/?([A-Za-z][\w-]*)((?:\s+[^\s"'=<>/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?)*)\s*(\/?)>/g
const ATTR = /([^\s"'=<>/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g

interface Tag { name: string, attrs: Map<string, string>, line: number }
interface Audit { problems: string[], fields: number, buttons: number }

/** Phần template, giữ nguyên vị trí (phần trước thay bằng khoảng trắng, chú thích HTML xóa trắng) để báo đúng dòng. */
function template(source: string): string {
  const start = source.indexOf('<template')
  const end = source.lastIndexOf('</template>')
  if (start < 0 || end < start) return ''
  const blank = (s: string) => s.replace(/[^\n]/g, ' ')
  return (blank(source.slice(0, start)) + source.slice(start, end)).replace(/<!--[\s\S]*?-->/g, blank)
}

function attrsOf(text: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const m of text.matchAll(ATTR)) out.set(m[1]!, m[2] ?? m[3] ?? m[4] ?? '')
  return out
}

// thuộc tính viết tĩnh, :tên hoặc v-bind:tên
const has = (tag: Tag, name: string) => [name, `:${name}`, `v-bind:${name}`].some((n) => tag.attrs.has(n))
const bound = (tag: Tag, name: string) => tag.attrs.has(`:${name}`) || tag.attrs.has(`v-bind:${name}`)

function audit(file: string, source: string): Audit {
  const text = template(source)
  const stack: string[] = []
  const labelFor = new Set<string>()
  const fields: Array<{ tag: Tag, inLabel: boolean }> = []
  const buttons: Tag[] = []
  for (const m of text.matchAll(TAG)) {
    const name = m[1]!
    if (m[0].startsWith('</')) {
      const open = stack.lastIndexOf(name)
      if (open >= 0) stack.length = open
      continue
    }
    const tag: Tag = { name, attrs: attrsOf(m[2] ?? ''), line: text.slice(0, m.index).split('\n').length }
    if (name === 'label' && tag.attrs.has('for')) labelFor.add(tag.attrs.get('for')!)
    if (FIELDS.has(name) && !(name === 'input' && NO_LABEL.has(tag.attrs.get('type') ?? ''))) {
      fields.push({ tag, inLabel: stack.includes('label') })
    }
    if (name === 'button' && stack.includes('form')) buttons.push(tag)
    if (!VOID.has(name) && m[3] !== '/') stack.push(name)
  }
  const problems: string[] = []
  for (const { tag, inLabel } of fields) {
    const id = tag.attrs.get('id')
    // id động: không đối chiếu được với <label for>, coi là có nhãn như SonarQube
    const named = inLabel || has(tag, 'aria-label') || has(tag, 'aria-labelledby') || bound(tag, 'id')
      || (id !== undefined && labelFor.has(id))
    if (!named) problems.push(`${file}:${tag.line}: <${tag.name}> không có nhãn (label, aria-label)`)
  }
  for (const tag of buttons) {
    if (!has(tag, 'type')) problems.push(`${file}:${tag.line}: <button> trong <form> không ghi type`)
  }
  return { problems, fields: fields.length, buttons: buttons.length }
}

test('mọi ô nhập có tên cho trình đọc màn hình, mọi nút trong form ghi type', () => {
  const files = readdirSync(APP, { recursive: true, encoding: 'utf8' }).filter((f) => f.endsWith('.vue')).sort()
  const problems: string[] = []
  let fields = 0
  let buttons = 0
  for (const file of files) {
    const result = audit(`app/${file}`, readFileSync(new URL(file, APP), 'utf8'))
    problems.push(...result.problems)
    fields += result.fields
    buttons += result.buttons
  }
  // duyệt thật, không đạt suông
  assert.ok(files.length >= 20, `chỉ thấy ${files.length} tệp .vue`)
  assert.ok(fields >= 20, `chỉ xét ${fields} ô nhập`)
  assert.ok(buttons >= 5, `chỉ xét ${buttons} nút trong form`)
  assert.deepEqual(problems, [])
})

test('bộ tách thẻ: bắt ô thiếu nhãn và nút thiếu type, nhận đủ các cách đặt tên', () => {
  const source = [
    '<script setup lang="ts">const ok = 1 < 2 && 3 > 2</script>',
    '<template>',
    '  <form @submit.prevent="(e) => e.timeStamp > 0 && go()">',
    '    <!-- <input v-model="trong-chu-thich"> -->',
    '    <input v-model="a" placeholder="Chỉ có placeholder">',
    '    <label>Tên <input v-model="b"></label>',
    '    <label for="c">C</label><input id="c" v-model="c">',
    '    <input :id="`o-${i}`" v-model="d"><textarea aria-labelledby="h" />',
    '    <select :aria-label="t(\'x\')"><option>1</option></select>',
    '    <input type="hidden" name="e"><input id="khong-co-label" v-model="f">',
    '    <button :disabled="n > 0">Gửi</button>',
    '    <button type="button" @click="n > 0 ? a() : b()">Thôi</button>',
    '    <Child />',
    '  </form>',
    '  <button>Ngoài form</button>',
    '</template>',
  ].join('\n')
  assert.deepEqual(audit('X.vue', source), {
    problems: [
      'X.vue:5: <input> không có nhãn (label, aria-label)',
      'X.vue:10: <input> không có nhãn (label, aria-label)',
      'X.vue:11: <button> trong <form> không ghi type',
    ],
    fields: 7,
    buttons: 2,
  })
})
