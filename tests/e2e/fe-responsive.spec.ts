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

test('FE Butter: hover and keyboard navigation never cover the workspace', async ({ browser }) => {
  test.skip(!PASSWORD, 'Demo credentials required')
  const page = await signIn(browser, 'chuyenviendt')
  await page.setViewportSize({ width: 1440, height: 900 })
  const shell = page.locator('.sg-shell')
  const sidebar = page.locator('#app-navigation')
  const main = page.locator('#main-content')
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)
  const originalX = (await main.boundingBox())!.x
  // The center of a collapsed link must remain inside the visible 76px rail.
  const incoming = page.locator('.sg-nav a[href="/van-ban-den"]')
  const hit = (await incoming.boundingBox())!
  expect(hit.x + hit.width).toBeLessThanOrEqual(76)
  await incoming.click()
  await expect(page).toHaveURL(/\/van-ban-den$/)
  await page.goto('/')
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)
  const bounds = (await sidebar.boundingBox())!
  expect(bounds.x).toBe(0)
  expect(bounds.y).toBe(0)
  expect(bounds.height).toBe(900)
  await page.mouse.move(35, 200)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await expect(page.locator('.sg-brand-full')).toHaveCSS('opacity', '1')
  await expect.poll(async () => (await main.boundingBox())!.x).toBeGreaterThan(originalX + 160)
  expect((await main.boundingBox())!.x).toBeGreaterThanOrEqual(bounds.x + bounds.width)
  // Moving into the revealed area must not close it; repeated interruptions settle.
  await page.mouse.move(200, 220)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  for (let i = 0; i < 3; i++) {
    await page.mouse.move(800, 300)
    await page.mouse.move(35, 200)
  }
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)
  await page.locator('.sg-wordmark').focus()
  await page.keyboard.press('Tab')
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await page.getByRole('searchbox').focus()
  await expect(shell).toHaveClass(/is-collapsed/)
  // A clicked link must not pin the hover navigation open on the new route.
  await page.mouse.move(35, 200)
  await page.locator('.sg-nav a[href="/van-ban-den"]').click()
  await page.locator('h1').waitFor()
  await expect.poll(async () => (await main.boundingBox())!.x).toBeGreaterThanOrEqual(244)
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)
  await expect.poll(async () => (await main.boundingBox())!.x).toBe(originalX)
  await page.goto('/')
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

test('FE: populated reports and case files stay within tablet and phone viewports', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'Demo credentials required')
  for (const [username, otp, routes] of [
    ['chuyenviendt', false, ['/ho-so', '/cam-bien']],
    ['truongkhoa', true, ['/dieu-hanh', '/pha-he']],
  ] as const) {
    const page = await signIn(browser, username, { otp })
    for (const width of [768, 390]) {
      await page.setViewportSize({ width, height: 900 })
      for (const route of routes) {
        await page.goto(route)
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
        if (route === '/pha-he') await expect(page.getByTestId('lineage-graph').locator('svg').first()).toBeVisible()
        if (route === '/dieu-hanh') await expect(page.getByTestId('board-status').locator('svg').first()).toBeVisible()
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth), { message: `${route} at ${width}px` }).toBeLessThanOrEqual(0)
        if (width === 390) {
          const title = await page.getByRole('heading', { level: 1 }).boundingBox()
          expect(title!.width, `${route}: mobile heading needs a readable measure`).toBeGreaterThan(180)
          expect(title!.height, `${route}: mobile heading must not stack word by word`).toBeLessThan(100)
        }
        await page.screenshot({ path: `test-results/screens/fe-${route.slice(1)}-${width}.png`, fullPage: true, animations: 'disabled' })
      }
    }
  }
})

test('FE: sensor map renders populated and flagged readings (API fixture, not a live broker)', async ({ browser }) => {
  test.skip(!PASSWORD, 'Demo credentials required')
  const page = await signIn(browser, 'chuyenviendt')
  const time = new Date().toISOString()
  await page.route('**/v1/graphql', async route => {
    if (!(route.request().postDataJSON()?.query ?? '').includes('otSensorMap')) return route.continue()
    await route.fulfill({ json: { data: { otSensorMap: {
      status: 'ready', threshold: 35, stale_after_min: 15, range_min: -20, range_max: 80, checked_at: time,
      sensors: [
        { id: 'urn:sensor:hot', room: 'kho-1', name: 'Cảm biến kiểm thử nhiệt độ cao', value: 38, observed_at: time, flags: [] },
        { id: 'urn:sensor:stale', room: 'kho-2', name: 'Cảm biến kiểm thử mất tín hiệu', value: 22, observed_at: time, flags: ['stale'] },
        { id: 'urn:sensor:future', room: 'kho-3', name: 'Cảm biến kiểm thử đồng hồ chạy nhanh', value: 38, observed_at: new Date(Date.now()+5*60000).toISOString(), flags: ['future_time'] },
      ],
    } } } })
  })
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/cam-bien')
    await expect(page.getByTestId('sensor-plan').locator('svg[role="img"]')).toBeVisible()
    await expect(page.getByTestId('sensor-plan').locator('text svg')).toHaveCount(0)
    if (width === 390) {
      expect((await page.getByTestId('sensor-plan').locator('svg[role="img"]').boundingBox())!.width).toBeGreaterThanOrEqual(700)
      const region = page.getByTestId('sensor-plan-scroll')
      await region.focus()
      await page.keyboard.press('ArrowRight')
      await expect.poll(() => region.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
      await region.evaluate(el => { el.scrollLeft = 0 })
    }
    await expect(page.getByTestId('sensor-row-hot')).toContainText('38')
    await expect(page.getByTestId('sensor-row-stale')).toContainText('Mất tín hiệu')
    await expect(page.getByTestId('sensor-row-future')).toContainText("Giờ đo ở tương lai")
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: `test-results/screens/fe-sensors-fixture-${width}.png`, fullPage: true, animations: 'disabled' })
  }
})

test('FE: feedback preserves input after a failed request and can retry to the real API', async ({ browser }) => {
  test.skip(!PASSWORD, 'Demo credentials required')
  const page = await signIn(browser, 'chuyenviendt')
  let fail = true
  await page.route('**/v1/graphql', async route => {
    const query = route.request().postDataJSON()?.query ?? ''
    if (fail && query.includes('insert_office_feedback_one')) return route.fulfill({ status: 503, json: {} })
    return route.continue()
  })
  await page.getByTestId('feedback-open').click()
  const form = page.getByTestId('feedback-form')
  const comment = `Góp ý kiểm thử giao diện ${Date.now()}`
  await form.locator('button[aria-pressed]').nth(3).click()
  await form.locator('textarea').fill(comment)
  await form.locator('button[type="submit"]').click()
  await expect(form.getByRole('alert')).toBeVisible()
  await expect(form.locator('textarea')).toHaveValue(comment)
  fail = false
  await form.locator('button[type="submit"]').click()
  await expect(form).toHaveCount(0)
  await page.goto('/gop-y')
  await expect(page.getByText(comment, { exact: true })).toBeVisible()
})

test('FE: task context, validation, return queue and detail tabs work with keyboard', async ({ browser }) => {
  test.skip(!PASSWORD, 'Demo credentials required')
  const page = await signIn(browser, 'chuyenviendt')
  const search = page.getByRole('searchbox')
  await search.fill('đề cương')
  await page.locator('.sg-task-link').first().click()
  await expect(page.getByTestId('processing-brief')).toBeVisible()
  await expect(page.getByTestId('processing-brief')).toContainText('Hạn giải quyết')
  const result = page.locator('#result')
  await page.getByRole('button', { name: 'Báo cáo xong', exact: true }).click()
  await expect(result).toBeFocused()
  await expect(result).toHaveAttribute('aria-invalid','true')
  await expect(page.locator('#result-error')).toBeVisible()
  const timeline = page.getByRole('tab', { name: 'Dòng thời gian', exact: true })
  await timeline.focus()
  await page.keyboard.press('ArrowRight')
  const history = page.getByRole('tab', { name: 'Lịch sử', exact: true })
  await expect(history).toBeFocused()
  await expect(history).toHaveAttribute('aria-selected','true')
  await expect(page.getByRole('tabpanel', { name: 'Lịch sử' })).toBeVisible()
  await page.keyboard.press('Home')
  await expect(timeline).toBeFocused()
  await page.getByRole('link', { name: 'Về hộp việc', exact: true }).click()
  await expect(page.getByRole('searchbox')).toHaveValue('đề cương')
  await page.setViewportSize({ width: 390, height: 900 })
  await page.reload()
  await expect(page.getByRole('heading', { level: 1, name: 'Hộp việc', exact: true })).toBeVisible()
  const menu = page.getByRole('button', { name: 'Mở điều hướng', exact: true })
  await menu.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#app-navigation a').first()).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.locator('.sg-logout')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(menu).toBeFocused()
})
