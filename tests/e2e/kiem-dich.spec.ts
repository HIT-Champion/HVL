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

// Kiểm dịch tại cửa ngõ (F3.1, màn (iv) trong docs/demo-script.md) trên giao diện: văn thư tải tệp nhiễm thì bị
// chặn ngay, không lưu; lãnh đạo khoa thấy lần chặn trong sổ kiểm toán, kèm mẫu mã độc, không kèm tên tệp.

// Chuỗi kiểm thử chuẩn EICAR (không phải mã độc thật), ghép từ hai nửa để chính tệp này không bị phần mềm diệt virus chặn
const EICAR = Buffer.from('X5O!P%@AP[4\\PZX54(P^)7CC)7}$' + 'EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*')

test('kiểm dịch: tệp nhiễm bị chặn khi tải lên, lần chặn nằm trong sổ kiểm toán', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await clerk.getByRole('link', { name: 'Tiếp nhận văn bản' }).click()
  await clerk.locator('input[type=file]').setInputFiles({ name: 'hoa-don.pdf', mimeType: 'application/pdf', buffer: EICAR })
  await expect(clerk.getByText(/Tệp nhiễm mã độc \(Eicar-Test-Signature\) — đã bị chặn, không lưu/)).toBeVisible()
  await shot(clerk, '16-kiem-dich-chan-tep')

  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Sổ kiểm toán' }).click()
  await director.getByRole('tab', { name: 'Tệp' }).click()
  const row = director.getByTestId('audit-table').locator('tr', { hasText: 'Chặn tệp nhiễm mã độc' }).first()
  await expect(row).toContainText('Eicar-Test-Signature')
  await expect(row).toContainText('68 B')
  await expect(row).not.toContainText('hoa-don.pdf')         // tên tệp do người dùng đặt: ẩn
  await shot(director, '17-kiem-dich-so-kiem-toan')
})
