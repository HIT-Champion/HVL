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


// Danh mục ứng dụng (/ung-dung): câu GraphQL của từng vai trò đúng bằng cột Hasura cho vai trò đó đọc
// (core_app_catalog.yaml, không quyền ghi); chỉ đường đúng CHECK của core.apps (đọc thẳng migration 1792281603200) mới
// thành liên kết; ứng dụng có sẵn khớp tên giữ chỗ, đường giữ chỗ của `moc app` (scripts/ung_dung.py), route APISIX và
// service compose chạy cùng thẻ MOC_VERSION mà /api/status trả; sắp xếp có sẵn → đã cài (theo tên, kiểu tiếng Việt) →
// đã gỡ (gần nhất trước); mục thanh bên cho mọi vai trò; đủ khóa i18n ở cả hai ngôn ngữ.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import type { Role } from '../app/composables/useAuth.ts'
import type { InstalledApp } from '../app/utils/apps.ts'

const { APPS_QUERY, APPS_QUERY_LEADER, APP_LEADERS, APP_PATH, BUILTIN_APPS, OPTIONAL_APPS, appCatalog, appHref,
  appsQuery, isAppLeader, shortHash } = await import('../app/utils/apps.ts')

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const META = read('../../../db/metadata/databases/default/tables/core_app_catalog.yaml')
const TABLES = read('../../../db/metadata/databases/default/tables/tables.yaml')
const REGISTRY = read('../../../db/migrations/default/1792281603200_app_registry/up.sql')
const CATALOG_SQL = read('../../../db/migrations/default/1792281603400_app_catalog/up.sql')
const UNG_DUNG = read('../../../scripts/ung_dung.py')
const APISIX = read('../../../platform/apisix/apisix.yaml')
const COMPOSE = read('../../../docker-compose.yml')
const WIKI_IMAGE = read('../../../platform/wiki/Dockerfile')
const page = read('../app/pages/ung-dung.vue')
const layout = read('../app/layouts/default.vue')

type Messages = { [key: string]: string | Messages }
const load = (lang: string): Messages => JSON.parse(read(`../app/locales/${lang}.json`)) as Messages
const vi = load('vi')
const en = load('en')
function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}
const tVi = (key: string) => lookup(vi, key) ?? key

const ROLES: Role[] = ['clerk', 'staff', 'manager', 'director', 'tenant_admin']
const fields = (query: string) => (/core_app_catalog \{([^}]*)\}/.exec(query)?.[1] ?? '').trim().split(/\s+/).sort()

// Quyền đọc của từng vai trò trong core_app_catalog.yaml: cột và điều kiện dòng
function permission(role: Role): { columns: string[]; filter: string } | null {
  const m = new RegExp(`- role: ${role}\\n {4}permission:\\n {6}columns: \\[([^\\]]+)\\]\\n {6}filter: (.+)\\n`)
    .exec(META)
  return m ? { columns: m[1]!.split(', ').sort(), filter: m[2]! } : null
}

test('câu GraphQL của từng vai trò đúng bằng cột Hasura cho vai trò đó đọc; không ai ghi', () => {
  for (const role of ROLES) {
    const p = permission(role)
    assert.ok(p, `${role} không có quyền đọc core_app_catalog`)
    assert.deepEqual(fields(appsQuery(role)), p.columns, role)
    // băm manifest, đã gỡ: đúng các vai trò lãnh đạo, quản trị; vai trò khác chỉ thấy ứng dụng đang cài
    assert.equal(p.columns.includes('manifest_sha256'), isAppLeader(role), role)
    assert.equal(p.columns.includes('removed_at'), isAppLeader(role), role)
    assert.equal(p.filter, isAppLeader(role) ? '{}' : '{removed_at: {_is_null: true}}', role)
  }
  assert.deepEqual([...APP_LEADERS].sort(), ['director', 'tenant_admin'])
  assert.equal(appsQuery(null), APPS_QUERY)
  assert.equal(appsQuery('tenant_admin'), APPS_QUERY_LEADER)
  assert.doesNotMatch(META, /insert_permissions|update_permissions|delete_permissions|allow_aggregations|role: service/)
  assert.match(TABLES, /^- "!include core_app_catalog\.yaml"$/m)
  // scripts/demo.py (cai-ung-dung) đọc hai câu bằng regex: phải là chuỗi tĩnh
  const utils = read('../app/utils/apps.ts')
  for (const name of ['APPS_QUERY', 'APPS_QUERY_LEADER']) {
    const m = new RegExp(`export const ${name} = \`([^\`]*)\``).exec(utils)
    assert.ok(m && !m[1]!.includes('${'), name)
  }
})

test('khung nhìn chỉ có cột hiển thị được: không manifest, schema, cổng, biến môi trường', () => {
  const select = /create view core\.app_catalog as\n([\s\S]*?)\n {2}from core\.apps a;/.exec(CATALOG_SQL)?.[1] ?? ''
  const columns = [...select.matchAll(/(?:as |a\.)(\w+),?\s*$/gm)].map((m) => m[1]).sort()
  assert.deepEqual(columns, fields(APPS_QUERY_LEADER))
  assert.doesNotMatch(select, /schema_name|a\.manifest\b(?! ->>)|environment|port|image/)
  assert.match(select, /nullif\(btrim\(a\.manifest ->> 'description'\), ''\) as description/)
})

test('chỉ đường đúng CHECK của core.apps mới thành liên kết', () => {
  const db = /path +text not null check \(path ~ '([^']+)'\)/.exec(REGISTRY)?.[1]
  assert.ok(db, 'không tìm thấy CHECK của core.apps.path trong migration 1792281603200')
  assert.equal(APP_PATH.source, new RegExp(db).source)
  assert.equal(appHref('/bang-tin'), '/bang-tin/')
  assert.equal(appHref('/a1-b2'), '/a1-b2/')
  for (const bad of ['javascript:alert(1)', '//evil.example', '/a/../b', '/Bang', '/bang-tin/', '', '/', '/-x',
    '/bang--tin', 'https://evil.example/x', '/bang tin', '/bang-tin?x=1']) {
    assert.equal(appHref(bad), null, bad)
  }
})

test('ứng dụng có sẵn khớp tên, đường giữ chỗ của moc app, route APISIX và image thẻ MOC_VERSION', () => {
  const reservedNames = new Set([...(/^RESERVED_NAMES = \{([^}]*)\}/m.exec(UNG_DUNG)?.[1] ?? '').matchAll(/"([^"]+)"/g)]
    .map((m) => m[1]))
  const reservedPaths = new Set([...(/^RESERVED_PATHS = \{([^}]*)\}/m.exec(UNG_DUNG)?.[1] ?? '').matchAll(/"([^"]+)"/g)]
    .map((m) => m[1]))
  assert.ok(reservedPaths.has('/ung-dung'), 'trang mới phải là đường giữ chỗ: ứng dụng cài sau không che được')
  assert.deepEqual(BUILTIN_APPS.map((b) => b.name), ['office', 'ca-nhan'])
  for (const b of BUILTIN_APPS) {
    assert.ok(reservedNames.has(b.name), `${b.name} phải là tên giữ chỗ`)
    // service chạy image dựng cùng bản cài, thẻ MOC_VERSION — đúng phiên bản /api/status trả
    const image = `image: moc/${b.service}:\\$\\{MOC_VERSION:-dev\\}`
    assert.match(COMPOSE, new RegExp(`\\n {2}${b.service}:\\n(?: {4}.*\\n)*? {4}${image}\\n`), b.service)
    if (b.href === '/') {
      assert.match(APISIX, new RegExp(`- id: ${b.service}\\n {4}uri: /\\*\\n`))
    } else {
      const path = b.href.replace(/\/$/, '')
      assert.ok(reservedPaths.has(path), path)
      assert.match(APISIX, new RegExp(`- id: ${b.service}\\n {4}uris: \\["${path}", "${path}/\\*"\\]\\n`))
    }
  }
  assert.match(COMPOSE, /image: moc\/svc-files:\$\{MOC_VERSION:-dev\}/)
  assert.match(COMPOSE, /\n {6}MOC_VERSION: \$\{MOC_VERSION:-dev\}\n/)
})

test('ứng dụng tùy chọn (#367): đường giữ chỗ, route APISIX, profile riêng, phiên bản đúng image ghim', () => {
  const reservedPaths = new Set([...(/^RESERVED_PATHS = \{([^}]*)\}/m.exec(UNG_DUNG)?.[1] ?? '').matchAll(/"([^"]+)"/g)]
    .map((m) => m[1]))
  assert.deepEqual(OPTIONAL_APPS.map((o) => o.name), ['wiki'])
  for (const o of OPTIONAL_APPS) {
    const path = o.href.replace(/\/$/, '')
    assert.ok(reservedPaths.has(path), path)
    assert.ok(o.probe.startsWith(o.href), o.probe)
    assert.match(APISIX, new RegExp(`- id: ${o.name}\\n {4}uris: \\["${path}", "${path}/\\*"\\]\\n`))
    // tắt mặc định: chỉ chạy khi bật profile cùng tên
    assert.match(COMPOSE, new RegExp(`\\n {2}${o.name}:\\n(?: {4}.*\\n)*? {4}profiles: \\[${o.name}\\]\\n`))
  }
  const tag = /\nFROM dokuwiki\/dokuwiki:([0-9a-z-]+)@sha256:/.exec(WIKI_IMAGE)?.[1]
  assert.equal(OPTIONAL_APPS[0]!.version, `DokuWiki ${tag}`)
})

test('ứng dụng tùy chọn chỉ vào danh mục khi đường kiểm sức khỏe trả lời "ok"', () => {
  assert.deepEqual(appCatalog(tVi, [], 'v1.3.0').builtin.map((e) => e.name), ['office', 'ca-nhan'])
  const c = appCatalog(tVi, [], 'v1.3.0', ['wiki'])
  assert.deepEqual(c.builtin.map((e) => [e.name, e.title, e.href, e.internal, e.version, e.state]).at(-1),
    ['wiki', 'Wiki nội bộ', '/wiki/', false, 'DokuWiki 2026-07-14c', 'builtin'])
  assert.deepEqual(appCatalog(tVi, [], null, ['khac']).builtin.length, 2)
  assert.match(page, /fetch\(a\.probe, \{ cache: 'no-store' \}\)/)
  assert.match(page, /res\.ok && \(await res\.text\(\)\)\.trim\(\) === 'ok' \? a\.name : null/)
  assert.match(page, /appCatalog\(t, rows\.value, coreVersion\.value, optional\.value\)/)
})

const SHA = 'ab'.repeat(32)
const row = (name: string, title: string, extra: Partial<InstalledApp> = {}): InstalledApp => ({
  name, title, description: null, path: `/${name}`, version: '1.0.0', installed_at: '2026-10-20T01:00:00+00:00',
  updated_at: '2026-10-20T01:00:00+00:00', ...extra,
})

test('danh mục: có sẵn trước, đã cài theo tên kiểu tiếng Việt, đã gỡ gần nhất trước, không liên kết', () => {
  const rows = [
    row('zeta', 'Zeta'),
    row('bang-tin', 'Bảng tin đơn vị', { manifest_sha256: SHA, removed_at: null, description: 'Tin mới',
      updated_at: '2026-10-21T02:00:00+00:00' }),
    row('anh', 'Ảnh hồ sơ'),
    row('cu', 'Ứng dụng cũ', { removed_at: '2026-10-22T03:00:00+00:00', updated_at: '2026-10-22T03:00:00+00:00' }),
    row('cu-hon', 'Ứng dụng cũ hơn',
      { removed_at: '2026-10-21T03:00:00+00:00', updated_at: '2026-10-21T03:00:00+00:00' }),
  ]
  const c = appCatalog(tVi, rows, 'v1.1.0')
  assert.deepEqual(c.builtin.map((e) => [e.name, e.title, e.href, e.internal, e.version, e.state]), [
    ['office', 'Văn phòng điện tử', '/', true, 'v1.1.0', 'builtin'],
    ['ca-nhan', 'Không gian cá nhân P.A.R.A', '/ca-nhan/', false, 'v1.1.0', 'builtin'],
  ])
  assert.ok(c.builtin.every((e) => e.description && !e.sha256 && !e.installedAt && !e.removedAt))
  // "Ảnh" trước "Bảng" (so theo mã ký tự thì Ả đứng sau Z)
  assert.deepEqual(c.installed.map((e) => e.name), ['anh', 'bang-tin', 'zeta'])
  const bang = c.installed[1]!
  assert.deepEqual([bang.href, bang.sha256, bang.description, bang.updatedAt, bang.state],
    ['/bang-tin/', SHA, 'Tin mới', '2026-10-21T02:00:00+00:00', 'installed'])
  assert.equal(c.installed[0]!.updatedAt, null)            // cài một lần, chưa cập nhật
  assert.equal(c.installed[0]!.sha256, null)               // vai trò thường: không có cột băm
  assert.deepEqual(c.removed.map((e) => e.name), ['cu', 'cu-hon'])
  assert.ok(c.removed.every((e) => e.href === null && e.state === 'removed' && e.updatedAt === null))
  // không gọi được /api/status: phiên bản để trống, trang ghi "theo bản lõi"
  assert.ok(appCatalog(tVi, [], null).builtin.every((e) => e.version === null))
  // đường lạ (không qua CHECK) không thành liên kết
  assert.equal(appCatalog(tVi, [row('x', 'X', { path: '//evil.example' })], null).installed[0]!.href, null)
})

test('băm rút gọn 12 ký tự, đủ 64 ký tự để chép', () => {
  assert.equal(shortHash(SHA), `${SHA.slice(0, 12)}…`)
  assert.equal(shortHash('abc'), 'abc')
  assert.match(page, /:title="a\.sha256"/)
  assert.match(page, /navigator\.clipboard\.writeText\(sha256\)/)
  assert.match(page, /\{ detail: sha256 \}/)                // chép không được: hiện đủ băm để chọn tay
})

test('mục thanh bên cho mọi vai trò đăng nhập; câu hỏi theo vai trò, phần đã gỡ chỉ cho lãnh đạo, quản trị', () => {
  assert.match(layout, /\n {2}if \(role\) \{\n {4}items\.push\(\{ to: '\/ung-dung', label: t\('apps\.nav'\),/)
  assert.match(page, /gql<\{ core_app_catalog: InstalledApp\[\] \}>\(appsQuery\(claims\.value\?\.role\)\)/)
  assert.match(page, /\.\.\.\(leader\.value\n\s+\? \[\{ id: 'removed'/)
  assert.doesNotMatch(page, /core_apps\b|manifest \{|environment/)
})

test('khóa i18n của trang có ở cả vi.json và en.json', () => {
  const keys = new Set<string>(['apps.nav'])
  for (const m of page.matchAll(/\bt\('([\w.]+)'/g)) keys.add(m[1]!)
  for (const state of ['builtin', 'installed', 'removed']) keys.add(`apps.state.${state}`).add(`apps.none.${state}`)
  for (const b of [...BUILTIN_APPS, ...OPTIONAL_APPS]) {
    keys.add(`apps.builtin.${b.key}.title`).add(`apps.builtin.${b.key}.description`)
  }
  assert.ok(keys.size > 30, `chỉ thấy ${keys.size} khóa`)
  for (const key of keys) {
    assert.ok(lookup(vi, key), `vi thiếu ${key}`)
    assert.ok(lookup(en, key), `en thiếu ${key}`)
  }
  assert.match(page, /t\(`apps\.state\.\$\{a\.state\}`\)/)
  assert.match(page, /t\(`apps\.none\.\$\{s\.id\}`\)/)
  // trạng thái là "đã cài", không hứa "đang chạy": CSDL không biết container có khỏe không
  assert.doesNotMatch(JSON.stringify(vi.apps), /đang chạy/i)
  assert.doesNotMatch(JSON.stringify(en.apps), /running\b(?! on)/i)
})
