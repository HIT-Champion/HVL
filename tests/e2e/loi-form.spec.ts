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

// Lỗi nhập và hộp Góp ý cho người dùng bàn phím, trình đọc màn hình, điện thoại (#248, phần còn lại của #230).
// Bấm lưu khi còn ô sai thì tiêu điểm vào ô sai đầu tiên và ô trỏ tới câu báo lỗi; hộp Góp ý nằm trọn trong màn hình
// 390px. Không lần lưu nào hợp lệ nên test không tạo dữ liệu.

test('Góp ý trên điện thoại: hộp nằm trong màn hình, Esc đóng mà giữ chữ đang soạn', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần dữ liệu mẫu và MOC_DEMO_PASSWORD')
  const page = await signIn(browser, 'chuyenviendt')
  await page.setViewportSize({ width: 390, height: 700 })
  await page.goto('/')
  const opener = page.getByTestId('feedback-open')
  const panel = page.getByTestId('feedback-form')
  await opener.click()
  const box = (await panel.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(390)
  expect(box.y + box.height).toBeLessThanOrEqual(700)
  await page.locator('#feedback-comment').fill('Góp ý đang soạn')
  await page.keyboard.press('Escape')
  await expect(panel).toBeHidden()
  await expect(opener).toBeFocused()
  await opener.click()
  await expect(page.locator('#feedback-comment')).toHaveValue('Góp ý đang soạn')
})

test('soạn dự thảo, lập hồ sơ thiếu ô: tiêu điểm vào ô sai đầu tiên, ô trỏ tới câu báo lỗi', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần dữ liệu mẫu và MOC_DEMO_PASSWORD')
  const page = await signIn(browser, 'chuyenviendt')
  await page.goto('/van-ban-di/soan')
  const save = page.getByRole('button', { name: 'Lưu dự thảo', exact: true })
  for (const [id, value] of [['summary', 'Kiểm tra bàn phím'], ['body', 'Nội dung kiểm tra'],
    ['recipients', 'Phòng Đào tạo']]) {
    await save.click()
    const field = page.locator(`#${id}`)
    await expect(field).toBeFocused()
    await expect(field).toHaveAttribute('aria-invalid', 'true')
    await expect(field).toHaveAttribute('aria-describedby', `${id}-error`)
    await expect(page.locator(`#${id}-error`)).toBeVisible()
    await field.fill(value)
  }

  await page.goto('/ho-so')
  await page.getByTestId('case-file-new').click()
  const form = page.getByTestId('case-file-form')
  const create = form.getByRole('button', { name: 'Lập hồ sơ', exact: true })
  await create.click()
  await expect(page.locator('#cf-code')).toBeFocused()
  await expect(page.locator('#cf-code')).toHaveAttribute('aria-describedby', 'cf-code-error')
  await page.locator('#cf-code').fill('QA-FOCUS')
  await create.click()
  await expect(page.locator('#cf-title')).toBeFocused()
  await expect(page.locator('#cf-title')).toHaveAttribute('aria-describedby', 'cf-title-error')
})

test('tiếp nhận văn bản đến để trống: tiêu điểm vào ô bắt buộc đầu tiên; ô chọn tệp có viền bàn phím', async ({
  browser,
}) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'Cần dữ liệu mẫu, MOC_DEMO_PASSWORD và MOC_DEMO_TOTP_SECRET')
  const page = await signIn(browser, 'vanthu', { otp: true })
  await page.goto('/van-ban-den/tiep-nhan')
  await page.locator('form button[type="submit"]').click()
  await expect(page.locator('#symbol')).toBeFocused()
  await expect(page.locator('#symbol')).toHaveAttribute('aria-describedby', /symbol-error/)
  await expect(page.locator('#symbol-error')).toBeVisible()
  await page.locator('#incoming-files').focus()
  await expect(page.locator('#incoming-files').locator('..')).toHaveCSS('outline-style', 'solid')
})

for (const task of [
  { user: 'chuyenviendt', name: 'Xử lý văn bản', button: 'Báo cáo xong', field: 'result' },
  { user: 'truongkhoa', name: 'Cho ý kiến chỉ đạo', button: 'Giao xử lý', field: 'instruction' },
  { user: 'totruongdt', name: 'Phân công xử lý', button: 'Giao việc', field: 'assignee' },
]) {
  test(`khung xử lý việc để trống (${task.user}): tiêu điểm vào ô sai, ô trỏ tới câu báo lỗi`, async ({ browser }) => {
    test.skip(!PASSWORD || !TOTP_SECRET, 'Cần dữ liệu mẫu, MOC_DEMO_PASSWORD và MOC_DEMO_TOTP_SECRET')
    const page = await signIn(browser, task.user, { otp: task.user !== 'chuyenviendt' })
    await page.locator('.sg-task-link').filter({ hasText: task.name }).first().click()
    const submit = page.getByRole('button', { name: task.button, exact: true })
    await expect(submit).toBeEnabled()
    await submit.click()
    const field = page.locator(`#${task.field}`)
    await expect(field).toBeFocused()
    await expect(field).toHaveAttribute('aria-describedby', new RegExp(`\\b${task.field}-error\\b`))
    await expect(page.locator(`#${task.field}-error`)).toBeVisible()
  })
}
