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

import { expect, test, type Page } from '@playwright/test'
import { PASSWORD, shot, signIn } from './helpers'

// Trang Tài liệu API (apps/tai-lieu-api, #357): Swagger UI ở /tai-lieu-api/, ứng dụng Tầng 2 với client Keycloak
// riêng app-tai-lieu-api. Chưa đăng nhập vẫn đọc được hai bộ (lõi, Văn phòng điện tử) và gọi thử được đường không cần
// token; đường cần token thì cổng trả 401. Đã đăng nhập Văn phòng điện tử thì "Đăng nhập để gọi thử" vào thẳng (SSO),
// token của người dùng được điền sẵn, "Try it out" qua cổng APISIX trả 200.

/** "Try it out" một thao tác theo operationId: điền tham số, Execute → header Authorization đã gửi, mã HTTP hiện ra. */
async function tryOut(page: Page, operationId: string, params: Record<string, string> = {}) {
  const op = page.locator(`[id$="-${operationId}"]`)
  await op.locator('.opblock-summary-control').click()
  await op.locator('button.try-out__btn').click()
  for (const [name, value] of Object.entries(params)) await op.locator(`input[placeholder="${name}"]`).fill(value)
  const [request] = await Promise.all([
    page.waitForRequest((req) => new URL(req.url()).pathname.startsWith('/api/')),
    op.locator('button.execute').click(),
  ])
  const status = op.locator('.live-responses-table tbody .response-col_status')
  await expect(status).toHaveText(/\d{3}/)
  return { auth: await request.headerValue('authorization'), status: (await status.innerText()).trim().slice(0, 3) }
}

test('tài liệu API: đọc không cần đăng nhập, SSO rồi gọi thử qua cổng bằng token của mình', async ({ browser }) => {
  test.skip(!PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')

  const outsider = await (await browser.newContext()).newPage()
  await outsider.goto('/tai-lieu-api/')
  await expect(outsider.getByRole('heading', { level: 1, name: 'API của Signet' })).toBeVisible()
  await expect(outsider).toHaveURL(/\/tai-lieu-api\/$/)                   // không bị chuyển sang Keycloak
  await expect(outsider.locator('.info .title')).toContainText('API lõi')
  expect(await tryOut(outsider, 'system_status_api_status_get')).toEqual({ auth: null, status: '200' })
  expect(await tryOut(outsider, 'search_api_search_get', { q: 'công văn' })).toEqual({ auth: null, status: '401' })

  await outsider.locator('[data-bo="van-phong"]').click()
  await expect(outsider.locator('.info .title')).toContainText('Văn phòng điện tử')
  await expect(outsider).toHaveURL(/\?bo=van-phong$/)
  await expect(outsider.locator('[id$="-search_api_search_get"]')).toHaveCount(0)   // đường lõi chỉ ở bộ lõi

  const judge = await signIn(browser, 'giamkhao')
  await judge.goto('/tai-lieu-api/')
  await judge.getByRole('button', { name: 'Đăng nhập để gọi thử' }).click()
  await expect(judge.locator('#nguoi')).toContainText('Đã đăng nhập:')
  await expect(judge).toHaveURL(/\/tai-lieu-api\/$/)                       // SSO: không dừng ở trang đăng nhập
  await expect(judge.locator('.btn.authorize.locked')).toBeVisible()       // token đã điền vào HTTPBearer
  const call = await tryOut(judge, 'search_api_search_get', { q: 'công văn' })
  expect(call.auth).toMatch(/^Bearer \S+$/)
  expect(call.status).toBe('200')
  await expect(judge.locator('[id$="-search_api_search_get"] .curl-command')).toContainText('Authorization: Bearer')
  await shot(judge, '47-tai-lieu-api')
})
