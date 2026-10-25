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

// Hồ sơ, nộp lưu, phòng đọc (F3.8) trên giao diện: chuyên viên lập hồ sơ, đưa vào một văn bản đã xong của phòng
// (văn bản mẫu của make seed), đóng hồ sơ — không có nút nộp lưu; tổ trưởng (lãnh đạo phòng) nộp lưu, băm manifest
// hiện ra; văn thư mở phòng đọc: gói khớp băm, xem tệp PDF trong khung (bản có dấu người xem, inline); lãnh đạo khoa
// thấy dòng "Xem tệp trong phòng đọc" trong sổ kiểm toán.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
const code = `HS-E2E-${tag}`
const title = `Hồ sơ thử giao diện ${tag}`

test('lập hồ sơ, nộp lưu, phòng đọc xem tệp', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  // 1. Chuyên viên lập hồ sơ của phòng mình
  const staff = await signIn(browser, 'chuyenviendt')
  await staff.getByRole('link', { name: 'Hồ sơ công việc' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: 'Hồ sơ công việc' })).toBeVisible()
  await staff.getByTestId('case-file-new').click()
  await staff.getByLabel('Ký hiệu hồ sơ').fill(code)
  await staff.getByLabel('Tiêu đề hồ sơ').fill(title)
  await staff.getByLabel('Thời hạn bảo quản').selectOption({ label: '10 năm' })
  await staff.getByTestId('case-file-form').getByRole('button', { name: 'Lập hồ sơ' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await expect(staff.getByTestId('case-file-status')).toHaveText('Đang lập')
  const casePath = new URL(staff.url()).pathname

  // 2. Đưa vào một văn bản đưa vào được (đến đã xong, đi đã phát hành của phòng — make seed có sẵn); ưu tiên văn bản
  // đi: bản phát hành là PDF do svc-files dựng, chắc chắn xem được trong phòng đọc
  const add = staff.getByTestId('case-file-add')
  const items = add.getByRole('listitem')
  await expect(items.first().or(add.getByTestId('case-file-no-candidates'))).toBeVisible()
  // hết văn bản thì đỏ, không bỏ qua: luồng chính của F3.8 phải chạy thật mỗi lượt
  await expect(add.getByTestId('case-file-no-candidates'),
    'không còn văn bản đã xong nào của phòng chưa vào hồ sơ — chạy make seed để có thêm').toHaveCount(0)
  const outgoing = items.filter({ hasText: 'Văn bản đi' })
  const first = (await outgoing.count()) ? outgoing.first() : items.first()
  const summary = (await first.locator('.truncate').textContent())?.trim() ?? ''
  await first.getByRole('button', { name: 'Thêm vào hồ sơ' }).click()
  await expect(staff.getByText('Đã thêm văn bản vào hồ sơ')).toBeVisible()
  await expect(staff.getByTestId('case-file-documents').getByText(summary)).toBeVisible()
  await shot(staff, '37-ho-so-mo')

  // 3. Đóng hồ sơ: ngày đóng do CSDL đặt; chuyên viên không có nút nộp lưu
  staff.once('dialog', (dialog) => dialog.accept())
  await staff.getByTestId('case-file-close').click()
  await expect(staff.getByTestId('case-file-status')).toHaveText('Đã đóng')
  await expect(staff.getByTestId('case-file-add')).toHaveCount(0)
  await expect(staff.getByTestId('case-file-archive')).toHaveCount(0)

  // 4. Tổ trưởng nộp lưu: gói Parquet + tệp + manifest lên kho lạnh khóa ghi, băm manifest hiện trên màn hồ sơ
  const manager = await signIn(browser, 'totruongdt', { otp: true })
  await manager.goto(casePath)
  manager.once('dialog', (dialog) => dialog.accept())
  await manager.getByTestId('case-file-archive').click()
  await expect(manager.getByText(new RegExp(`Đã nộp lưu hồ sơ ${code}`))).toBeVisible({ timeout: 60_000 })
  await expect(manager.getByTestId('case-file-status')).toHaveText('Đã nộp lưu')
  const sha = manager.getByTestId('case-file-sha')
  await expect(sha).toHaveText(/^[0-9a-f]{64}$/)
  const manifest = (await sha.textContent())?.trim() ?? ''
  await shot(manager, '38-ho-so-da-nop-luu')

  // 5. Văn thư mở phòng đọc: gói đọc lại từ kho lạnh khớp băm; xem tệp PDF — bản có dấu, hiện ngay trong trang
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await clerk.goto(casePath)
  const room = clerk.getByTestId('reading-room')
  await expect(room.getByTestId('reading-room-verified')).toContainText(manifest)
  await expect(room.getByText(summary)).toBeVisible()
  const opened = clerk.waitForResponse((r) => r.url().includes('/archive/files/'))
  await room.getByRole('button', { name: 'Xem', exact: true }).first().click()
  const response = await opened
  expect(response.status()).toBe(200)
  expect(response.headers()['content-type']).toBe('application/pdf')
  expect(response.headers()['content-disposition']).toMatch(/^inline;/)
  expect(response.headers()['cache-control']).toBe('no-store')
  await expect(clerk.getByTestId('reading-room-viewer').locator('iframe')).toHaveAttribute('src', /^blob:/)
  await shot(clerk, '39-phong-doc-xem-tep')

  // 6. Lãnh đạo khoa: sổ kiểm toán có dòng xem tệp trong phòng đọc (ký hiệu hồ sơ, băm gói; tên hồ sơ không hiện)
  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Sổ kiểm toán' }).click()
  await director.getByRole('tab', { name: 'Văn bản' }).click()
  const table = director.getByTestId('audit-table')
  await expect(table.getByText('Xem tệp trong phòng đọc · Hồ sơ').first()).toBeVisible()
  await expect(table.getByText('Yêu cầu nộp lưu hồ sơ · Hồ sơ').first()).toBeVisible()
  await expect(table.getByText(title)).toHaveCount(0)
})
