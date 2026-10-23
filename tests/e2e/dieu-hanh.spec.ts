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

import { expect, test, type Locator } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Dashboard điều hành (F3.11) trên giao diện: lãnh đạo khoa thấy số liệu văn bản của đơn vị kèm biểu đồ ECharts;
// văn thư không có mục này, mở thẳng đường dẫn cũng không thấy số liệu. Không giả định dữ liệu có sẵn: chỉ kiểm
// các con số khớp nhau giữa thẻ tổng và bảng.

async function cell(table: Locator, row: string): Promise<number> {
  return Number(await table.locator('tr', { hasText: row }).locator('td').last().innerText())
}

test('dashboard điều hành: chỉ lãnh đạo đơn vị xem, số liệu khớp giữa thẻ và bảng', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Điều hành' }).click()
  await expect(director.getByRole('heading', { level: 1, name: 'Điều hành' })).toBeVisible()

  const status = director.getByTestId('board-status')
  await expect(status.locator('svg').first()).toBeVisible()       // biểu đồ ECharts đã vẽ
  const open = await cell(status, 'Chờ vào sổ') + await cell(status, 'Chờ chỉ đạo') + await cell(status, 'Đang xử lý')
  await expect(director.getByTestId('kpi-open')).toHaveText(String(open))
  // mỗi phòng của đơn vị một dòng, kể cả phòng chưa có việc
  await expect(director.getByTestId('board-departments').locator('tbody tr').first()).toBeVisible()
  await expect(director.getByTestId('board-outgoing').locator('svg').first()).toBeVisible()
  await shot(director, '18-dieu-hanh')

  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await expect(clerk.getByRole('link', { name: 'Sổ đăng ký' })).toBeVisible()
  await expect(clerk.getByRole('link', { name: 'Điều hành' })).toHaveCount(0)
  await clerk.goto('/dieu-hanh')
  await expect(clerk.getByText('Chỉ lãnh đạo đơn vị xem được trang này.')).toBeVisible()
  await expect(clerk.getByTestId('board-kpis')).toHaveCount(0)
})
