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
import { PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Thông báo realtime (F2.5) trên hai trình duyệt cùng lúc: tổ trưởng mở sẵn hộp việc, chuyên viên trình dự thảo
// → bên tổ trưởng hiện tin "Việc mới" và hộp việc có dự thảo đó mà không phải tải lại trang; bấm tin thì mở văn
// bản; chuông giữ tin, đánh dấu đã đọc được.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
const summary = `Thông báo lịch họp giao ban tháng 11 (thử ${tag})`

test('thông báo realtime giữa hai người dùng', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  // 1. Tổ trưởng mở hộp việc, kênh thông báo trực tiếp đã nối
  const manager = await signIn(browser, 'totruongdt', { otp: true })
  const bell = manager.getByTestId('notification-bell')
  await bell.click()
  await expect(manager.getByText('Đang nhận thông báo trực tiếp')).toBeVisible()
  await bell.click()
  // chỉ trong danh sách hộp việc: tin ở góc màn hình cũng mang trích yếu, không được tính là "hộp việc đã có"
  const inboxItem = manager.getByTestId('inbox').getByRole('link', { name: new RegExp(tag) })
  await expect(inboxItem).toHaveCount(0)

  // 2. Chuyên viên (trình duyệt khác) soạn và trình dự thảo
  const staff = await signIn(browser, 'chuyenviendt')
  await staff.getByRole('link', { name: 'Soạn văn bản đi' }).click()
  await staff.getByLabel('Loại văn bản').selectOption({ label: 'Thông báo' })
  await staff.getByLabel('Trích yếu nội dung').fill(summary)
  await staff.getByLabel('Nội dung', { exact: true }).fill('Khoa thông báo lịch họp giao ban tháng 11 tại phòng họp tầng 3.')
  await staff.getByLabel('Nơi nhận').fill('Các bộ môn')
  await staff.getByRole('button', { name: 'Lưu dự thảo' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  await staff.getByLabel('Lãnh đạo đơn vị ký').selectOption({ label: 'Phạm Minh Đức' })
  await staff.getByRole('button', { name: 'Trình ký' }).click()
  await expect(staff.getByText('Đang trình').first()).toBeVisible()

  // 3. Bên tổ trưởng, không tải lại trang: tin hiện ở góc, hộp việc đã có dự thảo, chuông tăng số
  const toast = manager.getByTestId('realtime-notice').filter({ hasText: tag })
  await expect(toast).toBeVisible()
  await expect(toast).toContainText('Việc mới: Duyệt dự thảo cấp phòng')
  // tin có đường dẫn là liên kết có tên với trình đọc màn hình (#407: role status làm mất tên, axe báo link-name)
  await expect(toast).toHaveRole('link')
  await expect(toast).toHaveAccessibleName(new RegExp(`Việc mới: Duyệt dự thảo cấp phòng.*${tag}`))
  await expect(inboxItem).toBeVisible()
  await expect(manager.getByTestId('notification-count')).toBeVisible()
  await shot(manager, '12-thong-bao-realtime')

  // 4. Bấm tin → mở văn bản; chuông giữ tin, đánh dấu đã đọc hết thì hết số
  await toast.click()
  await expect(manager.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  await bell.click()
  await expect(manager.getByRole('button', { name: new RegExp(`Việc mới: Duyệt dự thảo cấp phòng.*${tag}`) })).toBeVisible()
  await shot(manager, '13-chuong-thong-bao')
  await manager.getByRole('button', { name: 'Đánh dấu đã đọc hết' }).click()
  await expect(manager.getByTestId('notification-count')).toHaveCount(0)
})
