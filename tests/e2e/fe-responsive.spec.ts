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

import { expect, test } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, signIn } from './helpers'

test('FE: bộ lọc rỗng, phục hồi, menu bàn phím và màn hình nhỏ', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'Cần thông tin đăng nhập demo')
  const page = await signIn(browser, 'truongkhoa', { otp: true })
  const search = page.getByRole('searchbox', { name: 'Tìm trong hộp việc…' })
  await search.fill('khong-co-ho-so-fe-987654321')
  await expect(page.getByText('Không có việc phù hợp', { exact: true })).toBeVisible()
  await search.clear()
  await expect(page.getByText('Không có việc phù hợp', { exact: true })).toHaveCount(0)
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(page.getByRole('button', { name: 'Mở điều hướng', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.getByRole('button', { name: 'Mở điều hướng', exact: true }).click()
    await expect(page.getByRole('link', { name: 'Văn bản đến', exact: true })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'Mở điều hướng', exact: true })).toBeFocused()
  }
  await page.getByRole('button', { name: 'English', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'My tasks', exact: true })).toBeVisible()
})

test('FE: lỗi tải danh mục soạn thảo cho phép thử lại', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần thông tin đăng nhập demo')
  const page = await signIn(browser, 'chuyenviendt')
  let fail = true
  await page.route('**/v1/graphql', async route => {
    const query = route.request().postDataJSON()?.query ?? ''
    if (fail && query.includes('office_document_types')) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
    } else await route.continue()
  })
  await page.goto('/van-ban-di/soan')
  await expect(page.getByRole('alert')).toBeVisible()
  fail = false
  await page.getByRole('button', { name: 'Thử lại', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByLabel('Loại văn bản', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Lưu dự thảo', exact: true })).toBeVisible()
})

test('FE Butter: thu mở sidebar vẫn truy cập được điều hướng và nhớ lựa chọn', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần thông tin đăng nhập demo')
  const page = await signIn(browser, 'chuyenviendt')
  await page.setViewportSize({ width: 1440, height: 900 })
  const main = page.locator('#main-content')
  const originalX = (await main.boundingBox())!.x
  await page.getByRole('button', { name: 'Thu gọn thanh bên', exact: true }).click()
  const expand = page.getByRole('button', { name: 'Mở rộng thanh bên', exact: true })
  await expect(expand).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(async () => (await main.boundingBox())!.x).toBeLessThan(originalX - 100)
  await expect(page.getByRole('link', { name: 'Văn bản đến', exact: true })).toBeVisible()
  await page.reload()
  await expect(expand).toBeVisible()
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expand.click()
  await expect(page.getByRole('button', { name: 'Thu gọn thanh bên', exact: true })).toHaveAttribute('aria-expanded', 'true')
  await page.getByRole('combobox', { name: 'Loại văn bản', exact: true }).selectOption('outgoing')
  await expect(page.getByRole('heading', { name: 'Cần chú ý', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /Báo cáo khối lượng giảng dạy/ })).toBeVisible()
})
