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

test('FE Butter: hover and keyboard expand the edge sidebar without shifting content', async ({ browser }) => {
  test.skip(!PASSWORD, 'Demo credentials required')
  const page = await signIn(browser, 'chuyenviendt')
  await page.setViewportSize({ width: 1440, height: 900 })
  const shell = page.locator('.sg-shell')
  const sidebar = page.locator('#app-navigation')
  const main = page.locator('#main-content')
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)
  const originalX = (await main.boundingBox())!.x
  const bounds = (await sidebar.boundingBox())!
  expect(bounds.x).toBe(0)
  expect(bounds.y).toBe(0)
  expect(bounds.height).toBe(900)
  await page.mouse.move(35, 200)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await expect(page.locator('.sg-brand-full')).toHaveCSS('opacity', '1')
  expect((await main.boundingBox())!.x).toBe(originalX)
  // Moving into the revealed area must not close it; repeated interruptions settle.
  await page.mouse.move(200, 220)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  for (let i = 0; i < 3; i++) {
    await page.mouse.move(800, 300)
    await page.mouse.move(35, 200)
  }
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)
  const incoming = page.locator('.sg-nav').getByRole('link').nth(1)
  await incoming.focus()
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await page.getByRole('searchbox').focus()
  await expect(shell).toHaveClass(/is-collapsed/)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.mouse.move(35, 200)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await expect(sidebar).toHaveCSS('transition-duration', '0s')
  await page.mouse.move(800, 300)
  const bell = page.getByTestId('notification-bell')
  await bell.click()
  await expect(bell).toHaveAttribute('aria-expanded', 'true')
  await page.keyboard.press('Escape')
  await expect(bell).toHaveAttribute('aria-expanded', 'false')
  await page.reload()
  await expect(shell).toHaveClass(/is-collapsed/)
  await page.setViewportSize({ width: 390, height: 900 })
  await page.getByRole('button', { name: 'Mở điều hướng', exact: true }).click()
  await expect(sidebar).toHaveCSS('visibility', 'visible')
  expect((await sidebar.boundingBox())!.x).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Mở điều hướng', exact: true })).toBeFocused()
})
