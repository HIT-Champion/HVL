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

// Quản trị đơn vị gõ thẳng địa chỉ trang văn bản (#230): về sổ kiểm toán trước khi trang gửi câu hỏi; các vùng chặn
// khớp với quyền Hasura và menu.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const { closedToTenantAdmin } = await import('../app/utils/adminRoutes.ts')
const source = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf8')

test('vùng văn bản, hồ sơ, sổ đăng ký bị chặn cả trang con; trang của quản trị đơn vị thì không', () => {
  for (const path of ['/van-ban-den', '/van-ban-den/', '/van-ban-den/tiep-nhan', '/van-ban-di', '/van-ban-di/soan',
    '/van-ban/0b8f1c1e-1111-4222-8333-944445555666', '/ho-so', '/ho-so/abc', '/so-dang-ky']) {
    assert.equal(closedToTenantAdmin(path), true, path)
  }
  for (const path of ['/', '/so-kiem-toan', '/ung-dung', '/gop-y', '/tim-kiem', '/van-ban-denx', '/ho-so-cu']) {
    assert.equal(closedToTenantAdmin(path), false, path)
  }
})

test('Hasura không cho quản trị đơn vị đọc các bảng của vùng bị chặn', () => {
  for (const table of ['office_documents', 'office_case_files']) {
    const yaml = source(`../../../db/metadata/databases/default/tables/${table}.yaml`)
    const select = yaml.slice(yaml.indexOf('select_permissions:'))
    assert.doesNotMatch(select.slice(0, select.search(/\n\S|$/) + 1), /role: tenant_admin/, table)
  }
})

test('middleware chặn sau khi khôi phục phiên, về sổ kiểm toán bằng replace', () => {
  const mw = source('../app/middleware/auth.global.ts')
  assert.ok(mw.indexOf('auth.restore()') < mw.indexOf('closedToTenantAdmin(to.path)'))
  const guard = mw.slice(mw.indexOf("role === 'tenant_admin'"))
  assert.match(guard, /^role === 'tenant_admin' && closedToTenantAdmin\(to\.path\)\) \{\s+return navigateTo\(/)
  assert.match(guard, /navigateTo\('\/so-kiem-toan', \{ replace: true \}\)/)
})
