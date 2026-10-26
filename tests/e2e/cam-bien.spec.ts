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
import { PASSWORD, shot, signIn } from './helpers'

// Sơ đồ cảm biến kho (F3.10) trên điện thoại (#235). Số đo giả qua page.route cho Action otSensorMap, không cần broker
// NGSI-LD hay bộ giả lập cảm biến. Ở 390px sơ đồ giữ bề rộng tối thiểu, cuộn ngang trong vùng cuộn có tên bằng phím
// mũi tên, cả trang không cuộn ngang; phòng có hai cờ hiện cờ đầu kèm "+1"; chú thích cờ dùng biểu tượng SVG, không
// dùng ký tự ⚠ (Be Vietnam Pro không có, trình duyệt lấy phông khác, có máy hiện emoji màu).

test('sơ đồ cảm biến: màn hẹp cuộn bằng phím, phòng nhiều cờ hiện cờ đầu và số cờ còn lại', async ({ browser }) => {
  test.skip(!PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')

  const page = await signIn(browser, 'chuyenviendt')
  const time = new Date().toISOString()
  await page.route('**/v1/graphql', async (route) => {
    if (!String(route.request().postDataJSON()?.query ?? '').includes('otSensorMap')) return route.continue()
    await route.fulfill({ json: { data: { otSensorMap: {
      status: 'ready', threshold: 35, stale_after_min: 15, range_min: -20, range_max: 80, checked_at: time,
      sensors: [
        { id: 'urn:ngsi-ld:Sensor:nong', room: 'kho-1', name: 'Cảm biến kiểm thử nóng', value: 38, observed_at: time,
          flags: [] },
        { id: 'urn:ngsi-ld:Sensor:hai-co', room: 'kho-2', name: 'Cảm biến kiểm thử hai cờ', value: 95,
          observed_at: time, flags: ['out_of_range', 'stale'] },
      ],
    } } } })
  })
  await page.setViewportSize({ width: 390, height: 900 })
  await page.goto('/cam-bien')

  const region = page.getByRole('region', { name: 'Mặt bằng kho lưu trữ' })
  const plan = region.locator('svg[role="img"]')
  await expect(plan).toBeVisible()
  expect((await plan.boundingBox())!.width).toBeGreaterThanOrEqual(540)
  await region.focus()
  await page.keyboard.press('ArrowRight')
  await expect.poll(() => region.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)

  // cờ theo thứ tự FLAG_ORDER: "Mất tín hiệu" trước "Ngoài dải"; đủ hai cờ ở bảng số đo
  const room = page.getByTestId('sensor-room-kho-2')
  await expect(room).toHaveAttribute('data-flags', 'stale out_of_range')
  await expect(room.locator('text').last()).toHaveText('Mất tín hiệu +1')
  await expect(page.getByTestId('sensor-row-hai-co')).toContainText('Mất tín hiệu')
  await expect(page.getByTestId('sensor-row-hai-co')).toContainText('Ngoài dải')
  await expect(page.getByTestId('sensor-legend')).not.toContainText('⚠')
  await region.evaluate((el) => { el.scrollLeft = 0 })
  await shot(page, '41-cam-bien-390')
})
