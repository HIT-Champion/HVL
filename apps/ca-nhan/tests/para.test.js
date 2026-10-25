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

// Test phần thuần của Không gian cá nhân (node --test, không cần trình duyệt). Kèm kiểm khớp giữa ứng dụng và cấu hình
// nó cắm vào lõi: thư mục ↔ ràng buộc CSDL, cột trong câu GraphQL ↔ quyền Hasura, client Keycloak ↔ trang cấu hình.

import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'

import { ApiError, createApi } from '../public/api.js'
import {
  DEFAULT_FOLDER, FOLDERS, MOVE_ITEM, PLACE_ITEM, QUERY_ITEMS, countByFolder, folderFromHash, folderName, formatSize,
  formatTime, graphqlError, hasSpace, isFolder, itemsIn, readClaims, uploadError,
} from '../public/para.js'

const ROOT = new URL('../../../', import.meta.url)
const read = (path) => readFileSync(new URL(path, ROOT), 'utf8').replace(/\r\n/g, '\n')

function migration() {
  const dir = 'db/migrations/default/'
  const name = readdirSync(new URL(dir, ROOT)).find((d) => d.endsWith('_personal_space'))
  assert.ok(name, 'thiếu migration personal_space')
  return read(`${dir}${name}/up.sql`)
}

test('bốn thư mục P.A.R.A khớp ràng buộc items_para của personal.items', () => {
  const m = migration().match(/constraint items_para check \(para in \(([^)]*)\)\)/)
  assert.ok(m, 'không thấy ràng buộc items_para')
  const keys = [...m[1].matchAll(/'([a-z]+)'/g)].map((x) => x[1])
  assert.deepEqual(FOLDERS.map((f) => f.key), keys)
  assert.equal(new Set(FOLDERS.map((f) => f.name)).size, 4)
  assert.ok(isFolder(DEFAULT_FOLDER))
})

test('câu GraphQL chỉ dùng cột mà quyền Hasura cho người dùng đọc, ghi', () => {
  const items = read('db/metadata/databases/default/tables/personal_items.yaml')
  const files = read('db/metadata/databases/default/tables/core_files.yaml')
  const cols = (yaml, anchor) => yaml.match(new RegExp(`${anchor}\\s+columns: \\[([^\\]]*)\\]`))[1].split(/,\s*/)
  const select = cols(items, '&owner_select')
  const fileSelect = cols(files, '&user_select')
  const query = QUERY_ITEMS.match(/\{\s*([^{]*)file \{([^}]*)\}/)
  for (const c of query[1].trim().split(/\s+/)) assert.ok(select.includes(c), `personal_items.${c}`)
  for (const c of query[2].trim().split(/\s+/)) assert.ok(fileSelect.includes(c), `core_files.${c}`)
  assert.deepEqual(cols(items, '&owner_insert').sort(), ['file_id', 'para'])
  assert.deepEqual(cols(items, '&owner_update'), ['para'])
  assert.match(PLACE_ITEM, /insert_personal_items_one\(object: \{file_id: \$file, para: \$para\}\)/)
  assert.match(MOVE_ITEM, /update_personal_items_by_pk\(pk_columns: \{file_id: \$file\}, _set: \{para: \$para\}\)/)
  // không có quyền xóa: tệp chỉ đổi thư mục (docs/mo-hinh-du-lieu.md §0)
  assert.doesNotMatch(items, /delete_permissions/)
})

test('client Keycloak app-ca-nhan: trang cấu hình, đường nhận đăng nhập, claim của Hasura như app-office', () => {
  const nginx = read('apps/ca-nhan/nginx/default.conf.template')
  assert.match(nginx, /"clientId":"app-ca-nhan"/)
  const realm = JSON.parse(read('platform/keycloak/realm/moc-realm.json')
    .replace(/\$\{([A-Z_]+)(?::([^}]*))?\}/g, (_, name, dflt) => dflt ?? 'https://signet.example'))
  const client = realm.clients.find((c) => c.clientId === 'app-ca-nhan')
  const office = realm.clients.find((c) => c.clientId === 'app-office')
  assert.ok(client)
  assert.equal(client.publicClient, true)
  assert.equal(client.directAccessGrantsEnabled, false)
  assert.equal(client.attributes['pkce.code.challenge.method'], 'S256')
  assert.deepEqual(client.redirectUris, ['https://signet.example/ca-nhan/*'])
  assert.deepEqual(client.protocolMappers, office.protocolMappers)
  const auth = readFileSync(new URL('../public/auth.js', import.meta.url), 'utf8')
  assert.match(auth, /const CALLBACK = '\/ca-nhan\/dang-nhap'/)
})

test('APISIX có route /ca-nhan tới app-ca-nhan, compose có dịch vụ cùng tên trong profile app', () => {
  const apisix = read('platform/apisix/apisix.yaml')
  const route = apisix.match(/- id: app-ca-nhan\n((?: {4}.*\n)+)/g).find((r) => r.includes('uris:'))
  assert.match(route, /uris: \["\/ca-nhan", "\/ca-nhan\/\*"\]/)
  assert.match(route, /methods: \[GET, HEAD\]/)
  assert.match(route, /upstream_id: app-ca-nhan/)
  assert.doesNotMatch(route, /plugin/)
  assert.match(apisix, /"app-ca-nhan:8080": 1/)
  const compose = read('docker-compose.yml')
  const service = compose.match(/\n {2}app-ca-nhan:\n((?: {4}.*\n)+)/)[1]
  assert.match(service, /^ {4}build: \.\/apps\/ca-nhan$/m)   // một dòng: make install thay bằng pull_policy
  assert.match(service, /^ {4}profiles: \[app\]$/m)
})

test('thư mục theo phần # của địa chỉ', () => {
  assert.equal(folderFromHash('#archives'), 'archives')
  assert.equal(folderFromHash('areas'), 'areas')
  assert.equal(folderFromHash(''), 'projects')
  assert.equal(folderFromHash('#khac'), 'projects')
  assert.equal(folderFromHash(undefined), 'projects')
  assert.equal(folderName('resources'), 'Tài nguyên')
  assert.equal(folderName('khac'), 'khac')
})

test('đếm theo thư mục, liệt kê mới chuyển tới trước rồi theo tên', () => {
  const items = [
    { file_id: '1', para: 'projects', updated_at: '2026-10-20T08:00:00Z', file: { filename: 'b.pdf' } },
    { file_id: '2', para: 'projects', updated_at: '2026-10-21T08:00:00Z', file: { filename: 'z.pdf' } },
    { file_id: '3', para: 'projects', updated_at: '2026-10-20T08:00:00Z', file: { filename: 'a.pdf' } },
    { file_id: '4', para: 'archives', updated_at: '2026-10-22T08:00:00Z', file: { filename: 'c.pdf' } },
    { file_id: '5', para: 'la', updated_at: '2026-10-22T08:00:00Z', file: { filename: 'd.pdf' } },
  ]
  assert.deepEqual(countByFolder(items), { projects: 3, areas: 0, resources: 0, archives: 1 })
  assert.deepEqual(itemsIn(items, 'projects').map((i) => i.file_id), ['2', '3', '1'])
  assert.deepEqual(itemsIn(items, 'areas'), [])
})

test('dung lượng, ngày giờ kiểu Việt Nam', () => {
  assert.equal(formatSize(0), '0 B')
  assert.equal(formatSize(1023), '1023 B')
  assert.equal(formatSize(1024), '1 KB')
  assert.equal(formatSize(1536), '1,5 KB')
  assert.equal(formatSize(25 * 1024 * 1024), '25 MB')
  assert.equal(formatSize(undefined), '—')
  assert.equal(formatSize(-1), '—')
  assert.equal(formatTime('2026-10-23T01:05:00Z'), '23/10/2026 08:05')
  assert.equal(formatTime('2026-10-23T23:30:00+07:00', 'UTC'), '23/10/2026 16:30')
  assert.equal(formatTime('không phải ngày'), '—')
})

test('câu báo khi tải lên không được: mã của svc-files, mã HTTP của cổng', () => {
  assert.match(uploadError(422, { detail: { code: 'infected', signature: 'Eicar-Test-Signature' } }),
    /mã độc.*Eicar-Test-Signature/)
  assert.match(uploadError(422, { detail: { code: 'unscannable' } }), /mật khẩu/)
  assert.equal(uploadError(413, { detail: { code: 'too_large', message: 'Tệp vượt giới hạn 25 MB' } }),
    'Tệp vượt giới hạn 25 MB.')
  assert.equal(uploadError(413, null), 'Tệp quá lớn.')
  assert.equal(uploadError(415, { detail: { code: 'type_mismatch', message: 'Nội dung tệp là trang HTML, không khớp '
    + 'đuôi .pdf' } }), 'Nội dung tệp là trang HTML, không khớp đuôi .pdf.')
  assert.equal(uploadError(415, { detail: { code: 'type_not_allowed' } }), 'Loại tệp này không được nhận nên chưa lưu.')
  assert.match(uploadError(422, { detail: { code: 'image_unreadable', message: 'Không bỏ được siêu dữ liệu' } }),
    /siêu dữ liệu\.$/)
  assert.match(uploadError(403, { detail: { code: 'no_tenant' } }), /chưa được gắn đơn vị/)
  assert.match(uploadError(0, null), /Không kết nối/)
  assert.match(uploadError(429, {}), /quá nhanh/)
  assert.match(uploadError(503, { detail: { code: 'scanner_unavailable' } }), /chưa sẵn sàng/)
  assert.equal(uploadError(500, { detail: 'x' }), 'Tải lên không được (mã 500).')
})

test('câu báo khi Hasura từ chối', () => {
  assert.match(graphqlError('validation-failed', "field 'personal_items' not found"), /không có không gian/)
  assert.match(graphqlError('constraint-violation', 'Check constraint violation. personal.items: … items_guard'),
    /chính bạn tải lên/)
  assert.match(graphqlError('constraint-violation', 'Uniqueness violation. duplicate key "items_pkey"'), /đã nằm/)
  assert.match(graphqlError('network'), /Không kết nối/)
  assert.equal(graphqlError(null, 'lạ'), 'Máy chủ báo lỗi: lạ')
})

function token(payload) {
  const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url')
  return `${b64({ alg: 'RS256' })}.${b64(payload)}.chu-ky`
}

test('đọc claim của token: vai trò, tên có dấu, client', () => {
  const claims = readClaims(token({
    sub: 'u-1', azp: 'app-ca-nhan', name: 'Vũ Thị Mai',
    'https://hasura.io/jwt/claims': { 'x-hasura-user-id': 'u-1', 'x-hasura-tenant-id': 't-1',
                                      'x-hasura-default-role': 'staff' },
  }))
  assert.deepEqual(claims, { userId: 'u-1', tenantId: 't-1', role: 'staff', name: 'Vũ Thị Mai', client: 'app-ca-nhan' })
  assert.equal(readClaims('hỏng'), null)
  assert.ok(hasSpace('staff') && hasSpace('clerk') && hasSpace('manager') && hasSpace('director'))
  assert.ok(!hasSpace('tenant_admin') && !hasSpace(null))
})

function fakeFetch(responses, calls) {
  return async (url, init) => {
    calls.push({ url, init })
    const r = responses.shift()
    if (r instanceof Error) throw r
    return { status: r.status, ok: r.status >= 200 && r.status < 300, json: async () => r.body,
             blob: async () => new Blob([r.body ?? '']) }
  }
}

test('gọi GraphQL qua cổng kèm token; 401 thì đăng nhập lại; lỗi Hasura thành ApiError', async () => {
  const calls = []
  let relogins = 0
  const api = createApi({
    token: async () => 'tok', relogin: async () => { relogins += 1 },
    fetchImpl: fakeFetch([
      { status: 200, body: { data: { personal_items: [] } } },
      { status: 200, body: { errors: [{ message: 'field not found', extensions: { code: 'validation-failed' } }] } },
      { status: 401, body: {} },
      { status: 429, body: {} },
      new TypeError('mất mạng'),
    ], calls),
  })
  assert.deepEqual(await api.gql(QUERY_ITEMS), { personal_items: [] })
  assert.equal(calls[0].url, '/v1/graphql')
  assert.equal(calls[0].init.headers.Authorization, 'Bearer tok')
  assert.deepEqual(JSON.parse(calls[0].init.body).variables, {})
  await assert.rejects(api.gql(QUERY_ITEMS), (e) => e instanceof ApiError && e.code === 'validation-failed')
  await assert.rejects(api.gql(QUERY_ITEMS), (e) => e.code === 'session' && e.status === 401)
  assert.equal(relogins, 1)
  await assert.rejects(api.gql(QUERY_ITEMS), (e) => e.code === 'rate_limited')
  await assert.rejects(api.gql(QUERY_ITEMS), (e) => e.code === 'network')
})

test('tải tệp về qua /api/files/{id}; 404 là không còn quyền hoặc không có', async () => {
  const calls = []
  const api = createApi({
    token: async () => 'tok', relogin: async () => {},
    fetchImpl: fakeFetch([{ status: 200, body: 'noi dung' }, { status: 404, body: {} }], calls),
  })
  const blob = await api.fetchFile('a/b')
  assert.equal(await blob.text(), 'noi dung')
  assert.equal(calls[0].url, '/api/files/a%2Fb')
  await assert.rejects(api.fetchFile('x'), (e) => e.code === 'not_found' && e.status === 404)
})

class FakeXHR {
  static next = []
  static sent = []
  upload = {}
  headers = {}
  open(method, url) { this.method = method; this.url = url }
  setRequestHeader(k, v) { this.headers[k] = v }
  send(body) {
    FakeXHR.sent.push(this)
    const { status, body: resp } = FakeXHR.next.shift()
    this.body = body
    this.status = status
    this.responseText = JSON.stringify(resp)
    this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 })
    queueMicrotask(() => this.onload())
  }
}

test('tải tệp lên svc-files: multipart trường file kèm token; tệp nhiễm thành câu báo', async () => {
  const api = createApi({ token: async () => 'tok', relogin: async () => {}, XHR: FakeXHR })
  FakeXHR.next.push({ status: 201, body: { id: 'f-1', filename: 'a.pdf' } },
    { status: 422, body: { detail: { code: 'infected', signature: 'Eicar-Test-Signature' } } })
  const progress = []
  const file = new Blob(['%PDF-1.4'])
  assert.deepEqual(await api.upload(file, (p) => progress.push(p)), { id: 'f-1', filename: 'a.pdf' })
  const [xhr] = FakeXHR.sent
  assert.equal(xhr.method, 'POST')
  assert.equal(xhr.url, '/api/files')
  assert.equal(xhr.headers.Authorization, 'Bearer tok')
  assert.ok(xhr.body.get('file'))
  assert.deepEqual(progress, [50])
  await assert.rejects(api.upload(file), (e) => e.code === 'infected' && /Eicar-Test-Signature/.test(e.message))
})
