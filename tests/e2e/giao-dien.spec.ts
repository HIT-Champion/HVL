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

// Giao diện Liền mạch (#116): khung ứng dụng, thanh bên, ngăn kéo trên màn hẹp, chuyển động có tôn trọng
// prefers-reduced-motion, trạng thái lỗi có nút thử lại. Không đổi dữ liệu.

test('giao diện: lọc hộp việc, ngăn kéo trên màn hẹp, đổi ngôn ngữ', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'Cần dữ liệu mẫu, MOC_DEMO_PASSWORD và MOC_DEMO_TOTP_SECRET')
  const page = await signIn(browser, 'truongkhoa', { otp: true })
  const search = page.getByRole('searchbox', { name: 'Tìm trong hộp việc…' })
  await search.fill('khong-co-viec-nao-ten-the-nay-987654321')
  await expect(page.getByText('Không có việc phù hợp', { exact: true })).toBeVisible()
  await search.clear()
  await expect(page.getByText('Không có việc phù hợp', { exact: true })).toHaveCount(0)

  const menu = page.getByRole('button', { name: 'Mở điều hướng', exact: true })
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(menu).toBeVisible()
    // không có thanh cuộn ngang
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await menu.click()
    await expect(page.getByRole('link', { name: 'Văn bản đến', exact: true })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(menu).toBeFocused()
  }

  await page.getByRole('button', { name: 'English', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'My tasks', exact: true })).toBeVisible()
})

test('giao diện: lỗi tải danh mục ở trang soạn thảo có nút thử lại', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần dữ liệu mẫu và MOC_DEMO_PASSWORD')
  const page = await signIn(browser, 'chuyenviendt')
  let fail = true
  await page.route('**/v1/graphql', async (route) => {
    const query = route.request().postDataJSON()?.query ?? ''
    if (fail && query.includes('office_document_types')) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
    } else {
      await route.continue()
    }
  })
  await page.goto('/van-ban-di/soan')
  await expect(page.getByRole('alert')).toBeVisible()
  fail = false
  await page.getByRole('button', { name: 'Thử lại', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByLabel('Loại văn bản', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Lưu dự thảo', exact: true })).toBeVisible()
})

test('giao diện: thanh bên mở khi rê chuột hoặc dùng bàn phím, không đẩy nội dung', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần dữ liệu mẫu và MOC_DEMO_PASSWORD')
  const page = await signIn(browser, 'chuyenviendt')
  await page.setViewportSize({ width: 1440, height: 900 })
  const shell = page.locator('.sg-shell')
  const sidebar = page.locator('#app-navigation')
  const main = page.locator('#main-content')

  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)
  await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeLessThanOrEqual(76)
  const x = (await main.boundingBox())!.x
  const bounds = (await sidebar.boundingBox())!
  expect([bounds.x, bounds.y, bounds.height]).toEqual([0, 0, 900])

  // rê chuột vào dải biểu tượng: mở ra, nằm đè, nội dung không bị đẩy; đi tiếp vào phần vừa mở vẫn mở
  await page.mouse.move(35, 200)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await expect(page.locator('.sg-brand-full')).toHaveCSS('opacity', '1')
  expect((await main.boundingBox())!.x).toBe(x)
  await page.mouse.move(200, 220)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)

  // bấm một mục: sang trang mới và thu lại dù chuột còn trên thanh bên, focus do chuột không giữ thanh bên mở
  await page.getByRole('link', { name: 'Văn bản đến', exact: true }).click()
  await expect(page).toHaveURL(/\/van-ban-den$/)
  await expect(shell).toHaveClass(/is-collapsed/)
  // bàn phím: Tab sang mục kế tiếp thì mở, focus rời thanh bên thì thu
  await page.keyboard.press('Tab')
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await page.getByTestId('notification-bell').focus()
  await expect(shell).toHaveClass(/is-collapsed/)

  // giảm chuyển động: vẫn mở, đóng nhưng không có thời gian chuyển (chuột còn trên thanh bên từ lần bấm ở trên: ra
  // ngoài trước rồi mới rê vào)
  await page.mouse.move(800, 300)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.mouse.move(35, 200)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await expect(sidebar).toHaveCSS('transition-duration', '0s')
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)

  const bell = page.getByTestId('notification-bell')
  await bell.click()
  await expect(bell).toHaveAttribute('aria-expanded', 'true')
  await page.keyboard.press('Escape')
  await expect(bell).toHaveAttribute('aria-expanded', 'false')

  // màn hẹp: ngăn kéo sát mép trái, không cuộn ngang, Esc đóng và trả focus về nút menu
  await page.setViewportSize({ width: 390, height: 900 })
  const menu = page.getByRole('button', { name: 'Mở điều hướng', exact: true })
  await menu.click()
  await expect(sidebar).toHaveCSS('visibility', 'visible')
  expect((await sidebar.boundingBox())!.x).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.keyboard.press('Escape')
  await expect(menu).toBeFocused()
})
