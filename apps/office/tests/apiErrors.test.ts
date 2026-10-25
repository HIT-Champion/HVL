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

// Cổng chặn (F3.15): tường lửa ở APISIX trả 403 kèm trang HTML (không phải JSON) và X-Request-Id. Mọi hàm của useApi
// đọc thân lỗi ném ApiError mã blocked mang mã đó, errorText hiện câu "Cổng an ninh chặn…" ở cả hai ngôn ngữ thay cho
// lỗi đọc JSON ("Unexpected token '<'…"); 403 JSON của Hasura, svc-files giữ mã cũ. Chạy thật useApi.ts và
// utils/errors.ts; fetch, XMLHttpRequest, useAuth (Nuxt tự import) là bản giả.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { registerHooks, stripTypeScriptTypes } from 'node:module'
import { test } from 'node:test'

// Node chỉ tự bỏ được kiểu dạng xóa được, còn ApiError dùng tham số `public …` (phải biến đổi) và utils/errors.ts
// import theo bí danh ~/ của Nuxt: nạp tệp trong app/ qua hook — ~/ về app/, biến đổi TypeScript bằng chính Node
const APP = new URL('../app/', import.meta.url)
registerHooks({
  resolve(specifier, context, next) {
    return next(specifier.startsWith('~/') ? new URL(`${specifier.slice(2)}.ts`, APP).href : specifier, context)
  },
  load(url, context, next) {
    if (!url.startsWith(APP.href) || !url.endsWith('.ts')) return next(url, context)
    const source = stripTypeScriptTypes(readFileSync(new URL(url), 'utf8'), { mode: 'transform', sourceUrl: url })
    return { format: 'module', source, shortCircuit: true }
  },
})

type Messages = { [key: string]: string | Messages }
const load = (lang: string): Messages =>
  JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`, import.meta.url), 'utf8')) as Messages
const vi = load('vi')
const en = load('en')

function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}
const translator = (messages: Messages) => (key: string, params: Record<string, string> = {}): string =>
  (lookup(messages, key) ?? `?${key}`).replace(/\{(\w+)\}/g, (_, name: string) => params[name] ?? `{${name}}`)
const tVi = translator(vi)
const tEn = translator(en)

// Phản hồi thật của cổng thử (APISIX 3.18 + coraza-proxy-wasm 0.6.0, cấu hình của platform/apisix) khi chặn
const PAGE_403 = '<html>\r\n<head><title>403 Forbidden</title></head>\r\n<body>\r\n<center><h1>403 Forbidden</h1>'
  + '</center>\r\n<hr><center>openresty</center>\r\n<p><em>Powered by <a href="https://apisix.apache.org/">APISIX</a>.'
  + '</em></p></body>\r\n</html>\r\n'
const RID = '104b7476-9d11-42d7-acdf-fd4fab456460'
const HTML = 'text/html; charset=utf-8'

interface Reply { status: number; body: string; headers: Record<string, string> }
const blockedReply = (requestId: string | null = RID): Reply => ({
  status: 403, body: PAGE_403, headers: { 'Content-Type': HTML, ...(requestId ? { 'X-Request-Id': requestId } : {}) },
})
const jsonReply = (status: number, body: unknown): Reply =>
  ({ status, body: JSON.stringify(body), headers: { 'Content-Type': 'application/json', 'X-Request-Id': RID } })

let reply: Reply = jsonReply(200, {})
const header = (name: string) =>
  Object.entries(reply.headers).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? null

class FakeXhr {
  status = 0
  responseText = ''
  upload: { onprogress?: unknown } = {}
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  open() {}
  setRequestHeader() {}
  getResponseHeader(name: string) { return header(name) }
  send() {
    this.status = reply.status
    this.responseText = reply.body
    queueMicrotask(() => this.onload?.())
  }
}

Object.assign(globalThis, {
  useAuth: () => ({ accessToken: async () => 'token-thu', login: async () => {} }),
  fetch: async () => new Response(reply.body, { status: reply.status, headers: reply.headers }),
  XMLHttpRequest: FakeXhr,
})

const { ApiError, useApi } = await import('../app/composables/useApi.ts')
const { errorText } = await import('../app/utils/errors.ts')
const api = useApi()

// mọi hàm của useApi đọc thân lỗi; preview đi qua savePdf, printRegister cũng vậy
const calls: Record<string, () => Promise<unknown>> = {
  gql: () => api.gql('mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }',
    { o: { recipients: ['http://192.168.1.10:8080/van-ban/12'] } }),
  upload: () => api.upload(new File(['%PDF-1.4'], 'thu.pdf', { type: 'application/pdf' })),
  preview: () => api.preview('00000000-0000-0000-0000-000000000001'),
  register: () => api.register('in', 2026),
  search: () => api.search({ q: '${jndi:ldap://x/a}' }),
  readFile: () => api.readFile('00000000-0000-0000-0000-000000000001'),
  ask: () => api.ask({ question: "x' UNION SELECT password FROM users --" }),
}

async function failure(call: () => Promise<unknown>): Promise<InstanceType<typeof ApiError>> {
  try {
    await call()
  } catch (e) {
    assert.ok(e instanceof ApiError, `không phải ApiError: ${e}`)
    return e
  }
  assert.fail('không ném lỗi')
}

test('403 HTML của cổng → ApiError blocked kèm X-Request-Id ở mọi hàm đọc thân lỗi', async () => {
  reply = blockedReply()
  for (const [name, call] of Object.entries(calls)) {
    const e = await failure(call)
    assert.equal(e.code, 'blocked', name)
    assert.equal(e.status, 403, name)
    assert.equal(e.requestId, RID, name)
  }
})

test('403 HTML không có X-Request-Id (vd proxy khác đứng trước cổng) → vẫn blocked, không mã', async () => {
  reply = blockedReply(null)
  for (const [name, call] of Object.entries(calls)) {
    const e = await failure(call)
    assert.equal(e.code, 'blocked', name)
    assert.equal(e.requestId, null, name)
  }
})

test('403 JSON của Hasura, svc-files giữ mã cũ, không thành blocked', async () => {
  reply = jsonReply(403, { errors: [{ message: 'field "x" not found', extensions: { code: 'validation-failed' } }] })
  const gqlError = await failure(calls.gql)
  assert.equal(gqlError.code, 'validation-failed')
  assert.equal(gqlError.message, 'field "x" not found')

  reply = jsonReply(403, { detail: { code: 'forbidden', message: 'Không có quyền với tệp này' } })
  for (const name of ['upload', 'preview', 'register', 'search', 'readFile', 'ask']) {
    const e = await failure(calls[name])
    assert.equal(e.code, 'forbidden', name)
    assert.equal(e.message, 'Không có quyền với tệp này', name)
  }

  // 403 JSON không theo khuôn {detail: {code}}: đọc văn bản, hỏi đáp vẫn ánh xạ theo mã HTTP như trước
  reply = jsonReply(403, { detail: 'Not authenticated' })
  assert.equal((await failure(calls.readFile)).code, 'forbidden')
  assert.equal((await failure(calls.ask)).code, 'forbidden')
  assert.equal((await failure(calls.search)).code, null)
})

test('gql: trang lỗi không phải JSON ở mã khác (502 của cổng) → ApiError HTTP 502, không lỗi đọc JSON', async () => {
  reply = { status: 502, body: '<html><body>502 Bad Gateway</body></html>', headers: { 'Content-Type': HTML } }
  const e = await failure(calls.gql)
  assert.equal(e.message, 'HTTP 502')
  assert.equal(e.code, null)
  assert.equal(e.status, 502)

  reply = jsonReply(200, { data: { insert_office_documents_one: { id: 'abc' } } })
  assert.deepEqual(await calls.gql(), { insert_office_documents_one: { id: 'abc' } })
})

test('errorText: blocked → câu của cổng kèm mã, hai ngôn ngữ; không còn "Unexpected token"', async () => {
  reply = blockedReply()
  const e = await failure(calls.gql)
  const textVi = errorText(tVi as never, e)
  assert.match(textVi, /^Cổng an ninh chặn nội dung này/)
  assert.ok(textVi.includes(`(mã ${RID})`), textVi)
  assert.doesNotMatch(textVi, /Unexpected token|Có lỗi xảy ra|blocked/)
  const textEn = errorText(tEn as never, e)
  assert.match(textEn, /^The security gateway blocked this content/)
  assert.ok(textEn.includes(`(ID ${RID})`), textEn)

  reply = blockedReply(null)
  const bare = await failure(calls.search)
  assert.equal(errorText(tVi as never, bare), lookup(vi, 'error.blocked'))
  assert.equal(errorText(tEn as never, bare), lookup(en, 'error.blocked'))

  // lỗi khác giữ câu cũ
  const limited = new ApiError('rate_limited', 'rate_limited', 429)
  assert.equal(errorText(tVi as never, limited), lookup(vi, 'error.rate_limited'))
  assert.equal(errorText(tVi as never, new ApiError('HTTP 502', null, 502)), 'HTTP 502')
})

test('khóa i18n của lỗi cổng chặn đủ hai ngôn ngữ; trang Hỏi đáp chuyển blocked cho errorText', () => {
  for (const messages of [vi, en]) {
    assert.ok(lookup(messages, 'error.blocked'))
    assert.doesNotMatch(lookup(messages, 'error.blocked')!, /\{/)
    assert.match(lookup(messages, 'error.blockedId') ?? '', /\{id\}/)
  }
  // askError tự dịch mã của svc-files (assist.error.*); mã chung của cổng phải sang errorText, không thành
  // "assist.error.generic: blocked"
  const page = readFileSync(new URL('../app/pages/hoi-dap.vue', import.meta.url), 'utf8')
  const passed = page.match(/!\[([^\]]+)\]\.includes\(e\.code/)?.[1] ?? ''
  assert.ok(passed.includes("'blocked'"), passed)
  assert.equal(lookup(vi, 'assist.error.blocked'), undefined)
})
