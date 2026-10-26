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

// Phần thuần của Bảng tin (node --test, không cần trình duyệt), kèm kiểm khớp với manifest: cột trong câu GraphQL ↔
// quyền đọc trong app.yaml và quyền đọc văn bản của lõi; loại tin ↔ events.kinds; đăng nhập chỉ dưới đường của ứng
// dụng.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import { LOAI, QUERY_TIN, VAI_TRO_XEM, dong, gio, tenNguoi, vaiTro } from '../public/tin.js'

const APP = new URL('../', import.meta.url)
const ROOT = new URL('../../../', import.meta.url)
const read = (base, path) => readFileSync(new URL(path, base), 'utf8')
const list = (text) => text.split(',').map((s) => s.trim()).filter(Boolean)

function selectedColumns(query) {
  const body = query.slice(query.indexOf('{', query.indexOf(')', query.indexOf('bang_tin_tin'))) + 1)
  const top = body.slice(0, body.indexOf('document {')).split(/\s+/).filter(Boolean)
  const doc = body.slice(body.indexOf('document {') + 'document {'.length, body.indexOf('}')).split(/\s+/)
  return { top, doc: doc.filter(Boolean) }
}

test('cột trang hỏi nằm trong quyền đọc của app.yaml và của office.documents', () => {
  const manifest = read(APP, 'app.yaml')
  const select = manifest.slice(manifest.indexOf('select_permissions:'))
  const allowed = list(select.match(/columns: \[([^\]]*)\]/)[1])
  const { top, doc } = selectedColumns(QUERY_TIN)
  for (const c of top) assert.ok(allowed.includes(c), `bang_tin.tin.${c} chưa có trong select_permissions`)
  const core = read(ROOT, 'db/metadata/databases/default/tables/office_documents.yaml')
  const staff = core.slice(core.indexOf('select_permissions:'))
  const coreCols = list(staff.match(/columns: \[([^\]]*)\]/s)[1].replace(/\s+/g, ' '))
  for (const c of doc) assert.ok(coreCols.includes(c), `office.documents.${c} người dùng không đọc được`)
  assert.match(select, /document: \{visible: \{_eq: true\}\}/)
  assert.match(select, /tenant_id: \{_eq: X-Hasura-Tenant-Id\}/)
})

test('mỗi loại tin ứng dụng nghe có nhãn', () => {
  const kinds = list(read(APP, 'app.yaml').match(/kinds: \[([^\]]*)\]/)[1])
  assert.deepEqual(Object.keys(LOAI).sort(), kinds.sort())
})

test('giờ Việt Nam, dòng hiển thị, không có văn bản thì ghi rõ', () => {
  assert.equal(gio('2026-10-25T07:05:00Z'), '25/10/2026 14:05')
  assert.equal(gio('khong-phai-gio'), '')
  assert.deepEqual(dong({ kind: 'office.document.issued', occurred_at: '2026-10-25T00:00:00Z',
    document: { symbol: '12/UBND-VP', summary: 'Về việc <b>họp</b>' } }),
  { loai: 'Văn bản đi đã phát hành', gio: '25/10/2026 07:00', so: '12/UBND-VP', trichYeu: 'Về việc <b>họp</b>' })
  assert.deepEqual(dong({ kind: 'office.document.registered', occurred_at: 'x', document: null }),
    { loai: 'Văn bản đến đã vào sổ', gio: '', so: '(chưa có số)', trichYeu: '' })
})

test('tên trong token có dấu tiếng Việt, token hỏng thì rỗng', () => {
  const part = Buffer.from(JSON.stringify({ name: 'Nguyễn Thị Hà', preferred_username: 'ha' })).toString('base64url')
  assert.equal(tenNguoi(`h.${part}.s`), 'Nguyễn Thị Hà')
  assert.equal(tenNguoi('khong-phai-token'), '')
})

test('vai trò đọc được bảng tin khớp select_permissions của app.yaml; vai trò lấy từ token', () => {
  const manifest = read(APP, 'app.yaml')
  const select = manifest.slice(manifest.indexOf('select_permissions:'), manifest.indexOf('insert_permissions:'))
  assert.deepEqual([...select.matchAll(/role: (\w+)/g)].map((m) => m[1]).sort(), [...VAI_TRO_XEM].sort())
  assert.ok(!VAI_TRO_XEM.includes('tenant_admin'))
  const claims = { 'https://hasura.io/jwt/claims': { 'x-hasura-default-role': 'tenant_admin' } }
  assert.equal(vaiTro(`h.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.s`), 'tenant_admin')
  assert.equal(vaiTro('khong-phai-token'), null)
  assert.match(read(APP, 'public/app.js'), /if \(!VAI_TRO_XEM\.includes\(vaiTro\(user\.access_token\)\)\) \{/)
})

test('trang không có script nội tuyến, đăng nhập dùng client và đường của ứng dụng', () => {
  const html = read(APP, 'public/index.html')
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/)
  assert.doesNotMatch(html, /\son[a-z]+=/i)
  const app = read(APP, 'public/app.js')
  assert.doesNotMatch(app, /innerHTML|insertAdjacentHTML|document\.write/)
  const auth = read(APP, 'public/auth.js')
  assert.match(auth, /const CALLBACK = '\/bang-tin\/dang-nhap'/)
  assert.match(auth, /response_mode: 'fragment'/)
  assert.match(auth, /clientId: 'app-bang-tin'/)
  const pkg = JSON.parse(read(APP, 'package.json'))
  const ref = JSON.parse(read(ROOT, 'apps/ca-nhan/package.json'))
  assert.equal(pkg.dependencies['oidc-client-ts'], ref.dependencies['oidc-client-ts'])
})
