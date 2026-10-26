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
  const incoming = page.getByRole('link', { name: 'Văn bản đến', exact: true })
  await incoming.click()
  await expect(page).toHaveURL(/\/van-ban-den$/)
  await expect(shell).toHaveClass(/is-collapsed/)
  // con trỏ còn nằm trên biểu tượng vừa bấm: nhích 1px không làm thanh bên mở lại (chờ quá nhịp mở để chắc); ra hẳn
  // khỏi thanh bên rồi vào lại thì mở như thường
  const box = (await incoming.boundingBox())!
  const [x, y] = [box.x + 24, box.y + box.height / 2]
  await page.mouse.move(x + 1, y)
  await page.waitForTimeout(400)
  await expect(shell).toHaveClass(/is-collapsed/)
  // bấm mục của chính trang đang mở (route không đổi): vẫn thu lại, nhích chuột cũng không mở lại
  await page.mouse.move(800, 300)
  await page.mouse.move(x, y)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await page.mouse.click(x, y)
  await expect(page).toHaveURL(/\/van-ban-den$/)
  await expect(shell).toHaveClass(/is-collapsed/)
  await page.mouse.move(x + 1, y)
  await page.waitForTimeout(400)
  await expect(shell).toHaveClass(/is-collapsed/)
  await page.mouse.move(800, 300)
  await page.mouse.move(x, y)
  await expect(shell).not.toHaveClass(/is-collapsed/)
  await page.mouse.move(800, 300)
  await expect(shell).toHaveClass(/is-collapsed/)
  // bàn phím: Tab sang mục kế tiếp thì mở, focus rời thanh bên thì thu
  await page.keyboard.press('Tab')
  await expect(shell).not.toHaveClass(/is-collapsed/)
  // đổi từ bàn phím sang chuột: thanh bên đang mở theo focus, bấm chuột đúng mục đang focus (không có focusin mới) vẫn
  // thu, nhích chuột không mở lại; Tab tiếp thì mở theo bàn phím như thường
  const focused = page.locator('#app-navigation a:focus')
  const fbox = (await focused.boundingBox())!
  const href = (await focused.getAttribute('href'))!
  await page.mouse.click(fbox.x + 24, fbox.y + fbox.height / 2)
  await expect(page).toHaveURL(new RegExp(`${href}$`))
  await expect(shell).toHaveClass(/is-collapsed/)
  await page.mouse.move(fbox.x + 25, fbox.y + fbox.height / 2)
  await page.waitForTimeout(400)
  await expect(shell).toHaveClass(/is-collapsed/)
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

test('giao diện: màn hẹp 390×844 bằng bàn phím: không cuộn ngang, ngăn kéo giữ focus, viền focus đủ', async ({
  browser,
}) => {
  test.skip(!PASSWORD, 'Cần dữ liệu mẫu và MOC_DEMO_PASSWORD')
  const page = await signIn(browser, 'chuyenviendt')
  await page.setViewportSize({ width: 390, height: 844 })
  const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
  const menu = page.getByRole('button', { name: 'Mở điều hướng', exact: true })
  const drawer = page.locator('#app-navigation')

  // hộp việc, văn bản đến, soạn thảo: đợi dữ liệu hiện rồi mới đo, vì thẻ việc, dòng bảng mới làm trang rộng ra
  await expect(page.locator('[data-testid="inbox"], .moc-empty').first()).toBeVisible()
  expect(await fits(), 'hộp việc cuộn ngang ở 390px').toBe(true)
  await menu.click()
  await drawer.getByRole('link', { name: 'Văn bản đến', exact: true }).click()
  await expect(page.locator('tbody tr').first()).toBeVisible()
  expect(await fits(), 'văn bản đến cuộn ngang ở 390px').toBe(true)
  await menu.click()
  await drawer.getByRole('link', { name: 'Soạn văn bản đi', exact: true }).click()
  await expect(page.getByLabel('Loại văn bản', { exact: true })).toBeVisible()
  expect(await fits(), 'soạn thảo cuộn ngang ở 390px').toBe(true)

  // mở ngăn kéo bằng phím: focus vào mục đầu
  await menu.focus()
  await page.keyboard.press('Enter')
  await expect(drawer.locator('a').first()).toBeFocused()
  await expect.poll(async () => (await drawer.boundingBox())!.x).toBe(0)

  // Tab đi qua mọi mục theo thứ tự nhìn thấy (trên xuống, cùng hàng thì trái sang phải), mục nào cũng có viền focus
  // 2px nằm trọn trong vùng không bị cắt, rồi quay về mục đầu chứ không lọt ra trang phía sau
  const focused = () => page.evaluate(() => {
    const el = document.activeElement as HTMLElement
    const s = getComputedStyle(el)
    const r = el.getBoundingClientRect()
    // viền nằm từ cạnh + offset tới cạnh + offset + độ dày: phần tràn ra ngoài phần tử (offset 3px → 5px, -3px → 0)
    const grow = Math.max(0, parseFloat(s.outlineOffset) + parseFloat(s.outlineWidth))
    const clip = (el.closest('.sg-nav') ?? el.closest('#app-navigation'))?.getBoundingClientRect()
    return {
      name: el.getAttribute('aria-label') ?? el.textContent?.trim() ?? '',
      top: r.top,
      bottom: r.bottom,
      left: r.left,
      ring: s.outlineStyle === 'solid' && parseFloat(s.outlineWidth) >= 2,
      inside: !!clip && r.left - grow >= clip.left && r.right + grow <= clip.right
        && r.top - grow >= clip.top && r.bottom + grow <= clip.bottom,
    }
  })
  const count = await drawer.evaluate((nav) => [...nav.querySelectorAll<HTMLElement>('a, button')]
    .filter((el) => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden').length)
  expect(count).toBeGreaterThan(5)
  const first = await focused()
  let previous = first
  for (let i = 0; i < count; i++) {
    const now = i ? await focused() : first
    expect(now.ring, `${now.name}: không có viền focus 2px`).toBe(true)
    expect(now.inside, `${now.name}: viền focus bị cắt`).toBe(true)
    if (i) {
      const sameRow = now.top < previous.bottom && now.bottom > previous.top
      expect(sameRow ? now.left > previous.left : now.top > previous.top,
             `${previous.name} → ${now.name}: sai thứ tự nhìn thấy`).toBe(true)
    }
    previous = now
    await page.keyboard.press('Tab')
  }
  expect((await focused()).name, 'Tab sau mục cuối phải về mục đầu').toBe(first.name)
  await page.keyboard.press('Shift+Tab')
  expect((await focused()).name, 'Shift+Tab ở mục đầu phải về mục cuối').toBe(previous.name)

  // đóng bằng nút trong ngăn kéo, rồi bằng lớp phủ: ngăn kéo ẩn, focus về nút menu
  await drawer.getByRole('button', { name: 'Đóng điều hướng', exact: true }).click()
  await expect(drawer).toHaveCSS('visibility', 'hidden')
  await expect(menu).toBeFocused()
  await menu.click()
  await expect(drawer).toHaveCSS('visibility', 'visible')
  await page.mouse.click(370, 420)
  await expect(drawer).toHaveCSS('visibility', 'hidden')
  await expect(menu).toBeFocused()
  expect(await fits()).toBe(true)
})
