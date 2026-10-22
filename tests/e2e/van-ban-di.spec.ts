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


import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Kịch bản demo (docs/dac-ta-san-pham.md §7, màn 3–4) trên giao diện thật: chuyên viên soạn công văn, xem trước
// → trình → tổ trưởng trả lại → sửa, trình lại → tổ trưởng đồng ý → lãnh đạo khoa ký → văn thư cấp số, phát
// hành PDF có mã QR → người ngoài, không đăng nhập, tra mã và thả tệp: nguyên vẹn thì khớp, sửa một byte thì không.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
const summary = `Về việc báo cáo kết quả rà soát đề cương học phần (thử ${tag})`
const body = 'Thực hiện Công văn của Phòng Đào tạo, Khoa đã rà soát đề cương chi tiết các học phần theo chuẩn đầu ra mới.\n'
  + 'Kết quả rà soát chi tiết gửi kèm theo công văn này.'

async function openTask(page: Page, screenshot?: string) {
  await page.goto('/')
  const item = page.getByRole('link', { name: new RegExp(tag) })
  await expect(item).toBeVisible()
  if (screenshot) await shot(page, screenshot)
  await item.click()
  await expect(page.getByRole('heading', { level: 1, name: summary })).toBeVisible()
}

test('luồng văn bản đi và cổng xác thực trên giao diện', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  // 1. Chuyên viên soạn công văn, tải bản xem trước, trình lãnh đạo khoa ký
  const staff = await signIn(browser, 'chuyenviendt')
  await staff.getByRole('link', { name: 'Soạn văn bản đi' }).click()
  await staff.getByLabel('Loại văn bản').selectOption({ label: 'Công văn' })
  await staff.getByLabel('Trích yếu nội dung').fill(summary)
  await staff.getByLabel('Nội dung', { exact: true }).fill(body)
  await staff.getByLabel('Nơi nhận').fill('Phòng Đào tạo')
  await shot(staff, '7-soan-van-ban-di')
  await staff.getByRole('button', { name: 'Lưu dự thảo' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  const [draft] = await Promise.all([
    staff.waitForEvent('download'),
    staff.getByRole('button', { name: 'Tải bản xem trước (PDF)' }).click(),
  ])
  expect(readFileSync(await draft.path()).subarray(0, 5).toString()).toBe('%PDF-')
  await staff.getByLabel('Lãnh đạo đơn vị ký').selectOption({ label: 'Phạm Minh Đức' })
  await staff.getByRole('button', { name: 'Trình ký' }).click()
  await expect(staff.getByText('Đang trình').first()).toBeVisible()

  // 2. Tổ trưởng trả lại, yêu cầu bổ sung
  const manager = await signIn(browser, 'totruongdt', { otp: true })
  await openTask(manager, '8-hop-viec-duyet')
  await manager.getByLabel('Ý kiến').fill('Ghi rõ số học phần đã rà soát.')
  await manager.getByRole('button', { name: 'Trả lại' }).click()
  await expect(manager.getByText('Đã chuyển bước tiếp theo.')).toBeVisible()

  // 3. Chuyên viên sửa theo ý kiến, trình lại
  await staff.reload()
  await expect(staff.getByText('Dự thảo bị trả lại: Ghi rõ số học phần đã rà soát.')).toBeVisible()
  await staff.getByRole('link', { name: 'Sửa dự thảo' }).click()
  await staff.getByLabel('Nội dung', { exact: true }).fill(`${body}\nKhoa đã rà soát 42 học phần của 3 ngành đào tạo.`)
  await staff.getByRole('button', { name: 'Lưu dự thảo' }).click()
  await staff.getByRole('button', { name: 'Trình lại' }).click()
  await expect(staff.getByText('Đang trình').first()).toBeVisible()

  // 4. Tổ trưởng đồng ý, lãnh đạo khoa ký duyệt
  await openTask(manager)
  await manager.getByRole('button', { name: 'Đồng ý, trình ký' }).click()
  await expect(manager.getByText('Đã chuyển bước tiếp theo.')).toBeVisible()
  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await openTask(director)
  await director.getByRole('button', { name: 'Ký duyệt' }).click()
  await expect(director.getByText('Đã duyệt').first()).toBeVisible()

  // 5. Văn thư cấp số, phát hành; tải bản phát hành
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await openTask(clerk)
  clerk.once('dialog', (dialog) => dialog.accept())
  await clerk.getByRole('button', { name: 'Cấp số và phát hành' }).click()
  await expect(clerk.getByText('Đã phát hành').first()).toBeVisible()
  await expect(clerk.getByText(/\d{2,}\/CNTT-ĐT/).first()).toBeVisible()
  const code = (await clerk.getByTestId('verify-code').textContent())!.trim()
  await shot(clerk, '9-da-phat-hanh')
  const [released] = await Promise.all([
    clerk.waitForEvent('download'),
    clerk.getByRole('button', { name: 'Tải về bản phát hành' }).click(),
  ])
  const pdf = readFileSync(await released.path())

  // 6. Người ngoài, không đăng nhập: mở trang xác thực như khi quét mã QR, thả tệp nhận được để so
  const outsider = await (await browser.newContext()).newPage()
  await outsider.goto(`/xac-thuc/${code.replace('-', '')}`)
  await expect(outsider.getByTestId('verify-valid')).toContainText(/\d{2,}\/CNTT-ĐT/)
  await outsider.locator('#verify-file').setInputFiles({ name: 'cong-van-nhan-duoc.pdf', mimeType: 'application/pdf', buffer: pdf })
  await expect(outsider.getByTestId('verify-match')).toContainText('khớp từng byte')
  // bản phát hành có chữ ký số PAdES bằng PKI nội bộ trong két (F4.5), cổng nói rõ chỉ minh họa
  const signature = outsider.getByTestId('verify-signature')
  await expect(signature).toContainText('PAdES')
  await expect(signature).toContainText('minh họa')
  await shot(outsider, '10-xac-thuc-khop')
  const tampered = Buffer.from(pdf)
  tampered[Math.floor(tampered.length / 2)] ^= 1
  await outsider.locator('#verify-file').setInputFiles({ name: 'da-bi-sua.pdf', mimeType: 'application/pdf', buffer: tampered })
  await expect(outsider.getByTestId('verify-match')).toContainText('KHÔNG khớp')
  await shot(outsider, '11-xac-thuc-khong-khop')
})
