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

// Danh mục ứng dụng (/ung-dung): mục "Ứng dụng" ở thanh bên đưa lãnh đạo đơn vị tới trang; hai ứng dụng có sẵn trong
// lõi (Văn phòng điện tử, Không gian cá nhân) mang phiên bản lõi mà /api/status trả, nút Mở tới /ca-nhan/ chạy được;
// phần "Cài bằng manifest", "Đã gỡ" và câu hướng dẫn đối chiếu băm có mặt (job e2e không cài ứng dụng nào: chỉ kiểm
// phần có mặt — cài, gỡ thật kiểm ở make demo-cai-ung-dung). Chuyên viên thấy ứng dụng có sẵn, không thấy phần đã gỡ,
// băm.

test('danh mục ứng dụng: ứng dụng có sẵn mở được, phần kỹ thuật chỉ cho lãnh đạo, quản trị', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Ứng dụng', exact: true }).click()
  await expect(director).toHaveURL(/\/ung-dung\/?$/)
  await expect(director.getByRole('heading', { level: 1, name: 'Danh mục ứng dụng' })).toBeVisible()
  const builtin = director.getByTestId('apps-builtin')
  await expect(builtin.locator('li')).toHaveCount(2)
  await expect(builtin.getByTestId('app-office')).toContainText('Văn phòng điện tử')
  await expect(builtin.getByTestId('app-ca-nhan')).toContainText('Không gian cá nhân P.A.R.A')
  const status = await (await director.request.get('/api/status')).json() as { version: string }
  for (const name of ['office', 'ca-nhan']) {
    await expect(builtin.getByTestId(`app-${name}`)).toContainText('Có sẵn trong lõi')
    await expect(builtin.getByTestId(`app-${name}`)).toContainText(status.version)
  }
  await expect(director.getByTestId('open-ca-nhan')).toHaveAttribute('href', '/ca-nhan/')
  await expect(director.getByTestId('apps-installed')).toBeVisible()
  await expect(director.getByTestId('apps-removed')).toBeVisible()
  await expect(director.getByTestId('apps-hash-hint')).toContainText('sha256sum')
  await shot(director, 'ung-dung-1-lanh-dao')
  await director.getByTestId('open-ca-nhan').click()
  await expect(director).toHaveURL(/\/ca-nhan\//)

  const staff = await signIn(browser, 'chuyenviendt')
  await expect(staff.getByRole('link', { name: 'Ứng dụng', exact: true })).toBeVisible()
  await staff.goto('/ung-dung')
  await expect(staff.getByRole('heading', { level: 1, name: 'Danh mục ứng dụng' })).toBeVisible()
  await expect(staff.getByTestId('app-ca-nhan')).toBeVisible()
  await expect(staff.getByTestId('apps-installed')).toBeVisible()
  await expect(staff.getByTestId('apps-removed')).toHaveCount(0)
  await expect(staff.getByTestId('apps-hash-hint')).toHaveCount(0)
  await expect(staff.getByTestId('app-hash')).toHaveCount(0)
})
