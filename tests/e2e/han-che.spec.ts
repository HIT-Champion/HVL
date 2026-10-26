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
import { PASSWORD, SCAN_TIMEOUT, TOTP_SECRET, shot, signIn, textPdf } from './helpers'

// Văn bản hạn chế (F3.7) trên giao diện: văn thư tiếp nhận ở chế độ hạn chế (chỉ PDF, tệp mã hóa trước khi lưu) →
// màn văn bản có khóa ở tệp và danh sách người được xem, lãnh đạo khoa nhận việc đã tự có tên; văn thư gỡ rồi cấp
// lại được. Chuông của lãnh đạo chỉ ghi "Văn bản hạn chế", không trích yếu; tổ trưởng chưa có tên mở thẳng đường dẫn
// thì không thấy gì.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
const summary = `Về việc nâng lương trước hạn năm 2026 (thử ${tag})`
const DIRECTOR = 'Phạm Minh Đức'

test('văn bản hạn chế trên giao diện', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  // 1. Văn thư bật chế độ hạn chế trước khi tải tệp: chỉ nhận PDF; đã có tệp thì không đổi chế độ được nữa
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await clerk.getByRole('link', { name: 'Tiếp nhận văn bản' }).click()
  await clerk.getByTestId('restricted').check()
  await expect(clerk.getByText('tệp được mã hóa trước khi lưu')).toBeVisible()
  const files = clerk.locator('input[type=file]')
  await files.setInputFiles({ name: `anh-chup-${tag}.png`, mimeType: 'image/png', buffer: Buffer.from('89504e47', 'hex') })
  const png = clerk.getByRole('listitem').filter({ hasText: `anh-chup-${tag}.png` })
  await expect(png.getByText('Văn bản hạn chế chỉ nhận tệp PDF')).toBeVisible()
  await expect(clerk.getByTestId('restricted')).toBeDisabled()
  await png.getByRole('button').click()
  await files.setInputFiles({
    name: `nang-luong-${tag}.pdf`, mimeType: 'application/pdf',
    buffer: textPdf('Danh sach nang luong truoc han nam 2026', `Ma thu ${tag}`),
  })
  await expect(clerk.getByText('Đã quét — sạch, đã mã hóa')).toBeVisible({ timeout: SCAN_TIMEOUT })
  await expect(clerk.getByTestId('restricted')).toBeDisabled()
  await clerk.getByLabel('Số, ký hiệu').fill(`89/ĐHCN-TCCB${tag}`)
  await clerk.getByLabel('Ngày ban hành').fill(new Date().toISOString().slice(0, 10))
  await clerk.getByLabel('Cơ quan ban hành').fill('Trường Đại học Công nghiệp')
  await clerk.getByLabel('Trích yếu nội dung').fill(summary)
  await shot(clerk, '20-tiep-nhan-han-che')
  await clerk.getByRole('button', { name: 'Lưu và vào sổ' }).click()
  await expect(clerk.getByText(/Đã vào sổ — số đến \d+/)).toBeVisible()

  // 2. Màn văn bản: tệp có khóa; lãnh đạo khoa (người nhận việc chỉ đạo) đã tự có tên; gỡ rồi cấp lại
  await expect(clerk.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  await expect(clerk.getByTestId('file-sealed')).toBeVisible()
  const viewers = clerk.getByTestId('viewers')
  const director = viewers.getByRole('listitem').filter({ hasText: DIRECTOR })
  await expect(director).toHaveCount(1)
  await shot(clerk, '21-nguoi-duoc-xem')
  const docPath = new URL(clerk.url()).pathname
  await director.getByRole('button', { name: 'Gỡ' }).click()
  await expect(clerk.getByText(`Đã gỡ quyền xem của ${DIRECTOR}`)).toBeVisible()
  await expect(director).toHaveCount(0)
  await viewers.getByLabel('Chọn người').selectOption({ label: DIRECTOR })
  await viewers.getByRole('button', { name: 'Cấp quyền xem' }).click()
  await expect(clerk.getByText(`Đã cấp quyền xem cho ${DIRECTOR}`)).toBeVisible()
  await expect(director).toHaveCount(1)

  // 3. Tổ trưởng chưa có tên: mở thẳng đường dẫn cũng không thấy văn bản
  const manager = await signIn(browser, 'totruongdt', { otp: true })
  await manager.goto(docPath)
  await expect(manager.getByText('Không tìm thấy văn bản, hoặc bạn không có quyền xem.')).toBeVisible()
  await expect(manager.getByText(summary)).toHaveCount(0)

  // 4. Lãnh đạo khoa: chuông chỉ ghi "Văn bản hạn chế"; mở việc từ hộp việc thì đọc được văn bản
  const lead = await signIn(browser, 'truongkhoa', { otp: true })
  await lead.getByTestId('notification-bell').click()
  await expect(lead.getByRole('button', { name: /Việc mới.*Văn bản hạn chế/ }).first()).toBeVisible()
  await expect(lead.getByRole('button', { name: new RegExp(tag) })).toHaveCount(0)
  await shot(lead, '22-thong-bao-han-che')
  await lead.getByTestId('notification-bell').click()
  await lead.goto('/')
  await lead.getByRole('link', { name: new RegExp(tag) }).click()
  await expect(lead.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  await expect(lead.getByTestId('file-sealed')).toBeVisible()
  await expect(lead.getByTestId('viewers')).toBeVisible()
  await shot(lead, '23-lanh-dao-mo-van-ban-han-che')
})
