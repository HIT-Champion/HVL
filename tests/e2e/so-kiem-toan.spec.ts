// Copyright 2026 Mộc Team
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

// Sổ kiểm toán (F2.12) trên giao diện: lãnh đạo khoa mở sổ của đơn vị, thấy chuỗi đã neo ra ngoài CSDL tới đâu,
// ai đổi gì; từ một văn bản mở thẳng các dòng sổ của văn bản đó.

test('sổ kiểm toán: lãnh đạo xem ai đổi gì, chuỗi đã neo tới đâu', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Sổ kiểm toán' }).click()
  await expect(director.getByRole('heading', { level: 1, name: 'Sổ kiểm toán' })).toBeVisible()
  // svc-files neo ngay khi khởi động, rồi định kỳ
  await expect(director.getByTestId('audit-anchor')).toContainText(/neo ra ngoài CSDL đến dòng #\d+/)

  await director.getByRole('tab', { name: 'Văn bản' }).click()
  const table = director.getByTestId('audit-table')
  await expect(table.getByText('Thêm · Văn bản').first()).toBeVisible()
  await expect(table.getByText('Trạng thái:').first()).toBeVisible()
  await shot(director, '14-so-kiem-toan')

  // Từ trang văn bản → các dòng sổ của riêng văn bản đó
  await table.getByRole('link', { name: 'Mở văn bản' }).first().click()
  await expect(director.getByRole('heading', { level: 1 })).toBeVisible()
  await director.getByRole('link', { name: 'Xem trong sổ kiểm toán' }).click()
  await expect(director.getByText('Của một văn bản')).toBeVisible()
  // đúng nhãn: văn bản đã vào hồ sơ (F3.8) còn có dòng "Thêm · Văn bản trong hồ sơ"
  await expect(table.getByText('Thêm · Văn bản', { exact: true })).toHaveCount(1)
})
