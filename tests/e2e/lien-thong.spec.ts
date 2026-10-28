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

import { expect, test, type Page } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Liên thông văn bản trong hệ thống (F3.12) trên giao diện: chuyên viên Khoa CNTT soạn công văn, tích "Khoa Kinh tế"
// trong danh sách đơn vị cùng dùng Signet (tên tự vào ô nơi nhận) → trình → tổ trưởng đồng ý → lãnh đạo khoa ký → văn
// thư CNTT phát hành, thẻ liên thông báo "Đã chuyển" → văn thư Khoa Kinh tế được báo, thấy văn bản đến chip
// "Liên thông", mở ra có "Nhận từ Khoa Công nghệ thông tin", mã xác thực của bên gửi, tệp cùng SHA-256 với bản phát
// hành; vào sổ như mọi văn bản đến.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
const summary = `Về việc phối hợp tổ chức hội thảo khoa học liên khoa (thử ${tag})`
const body = 'Khoa Công nghệ thông tin đề nghị Khoa Kinh tế cử đại diện tham gia ban tổ chức hội thảo khoa học liên khoa.\n'
  + 'Danh sách đề nghị gửi về Văn phòng khoa trước ngày 30 tháng 11.'
const SENDER = 'Khoa Công nghệ thông tin'
const RECEIVER = 'Khoa Kinh tế'

async function openTask(page: Page) {
  await page.goto('/')
  // trong hộp việc: tin realtime ở góc màn hình cũng là liên kết mang trích yếu (#415)
  await page.getByTestId('inbox').getByRole('link', { name: new RegExp(tag) }).click()
  await expect(page.getByRole('heading', { level: 1, name: summary })).toBeVisible()
}

test('liên thông văn bản giữa hai khoa trên giao diện', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  // 1. Chuyên viên soạn, tích Khoa Kinh tế: tên vào ô nơi nhận; bỏ tích thì gỡ, tích lại thì thêm lại
  const staff = await signIn(browser, 'chuyenviendt')
  await staff.getByRole('link', { name: 'Soạn văn bản đi' }).click()
  await staff.getByLabel('Loại văn bản').selectOption({ label: 'Công văn' })
  await staff.getByLabel('Trích yếu nội dung').fill(summary)
  await staff.getByLabel('Nội dung', { exact: true }).fill(body)
  await staff.getByLabel('Nơi nhận').fill('Phòng Đào tạo')
  const unit = staff.getByTestId('units').getByRole('checkbox', { name: new RegExp(RECEIVER) })
  await unit.check()
  await expect(staff.getByLabel('Nơi nhận')).toHaveValue(`Phòng Đào tạo\n${RECEIVER}`)
  await unit.uncheck()
  await expect(staff.getByLabel('Nơi nhận')).toHaveValue('Phòng Đào tạo')
  await unit.check()
  await shot(staff, '24-soan-lien-thong')
  await staff.getByRole('button', { name: 'Lưu dự thảo' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  await expect(staff.getByTestId('dispatch')).toContainText(RECEIVER)
  await staff.getByLabel('Lãnh đạo đơn vị ký').selectOption({ label: 'Phạm Minh Đức' })
  await staff.getByRole('button', { name: 'Trình ký' }).click()
  await expect(staff.getByText('Đang trình').first()).toBeVisible()

  // 2. Tổ trưởng đồng ý, lãnh đạo khoa ký duyệt
  const manager = await signIn(browser, 'totruongdt', { otp: true })
  await openTask(manager)
  await manager.getByRole('button', { name: 'Đồng ý, trình ký' }).click()
  await expect(manager.getByText('Đã chuyển bước tiếp theo.')).toBeVisible()
  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await openTask(director)
  await director.getByRole('button', { name: 'Ký duyệt' }).click()
  await expect(director.getByText('Đã duyệt').first()).toBeVisible()

  // 3. Văn thư CNTT cấp số, phát hành: thẻ liên thông chuyển từ "Đang chuyển" sang "Đã chuyển" (trang tự hỏi lại)
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await openTask(clerk)
  clerk.once('dialog', (dialog) => dialog.accept())
  await clerk.getByRole('button', { name: 'Cấp số và phát hành' }).click()
  await expect(clerk.getByText('Đã phát hành').first()).toBeVisible()
  const sent = clerk.getByTestId('dispatch').getByRole('listitem').filter({ hasText: RECEIVER })
  await expect(sent.getByText('Đã chuyển', { exact: true })).toBeVisible({ timeout: 60_000 })
  const code = (await clerk.getByTestId('verify-code').textContent())!.trim()
  await shot(clerk, '25-da-chuyen-lien-thong')

  // 4. Văn thư Khoa Kinh tế: chuông báo văn bản đến liên thông; danh sách chờ vào sổ có chip "Liên thông"
  const receiver = await signIn(browser, 'vanthukt', { otp: true })
  await receiver.getByTestId('notification-bell').click()
  await expect(receiver.getByRole('button', { name: new RegExp(`Văn bản đến liên thông từ ${SENDER}.*${tag}`) })).toBeVisible()
  await receiver.getByTestId('notification-bell').click()
  await receiver.goto('/van-ban-den?tab=received')
  const row = receiver.getByRole('row').filter({ hasText: tag })
  await expect(row.getByTestId('dispatched-chip')).toHaveText('Liên thông')
  await shot(receiver, '26-van-ban-den-lien-thong')

  // 5. Mở văn bản: nhận từ đâu, mã xác thực của bên gửi, tệp cùng SHA-256 với bản phát hành; vào sổ như thường
  await row.getByRole('link', { name: new RegExp(tag) }).click()
  await expect(receiver.getByRole('heading', { level: 1, name: new RegExp(tag) })).toBeVisible()
  await expect(receiver.getByTestId('dispatched-chip')).toBeVisible()
  const card = receiver.getByTestId('dispatch-in')
  await expect(card).toContainText(`Nhận từ ${SENDER}`)
  await expect(card.getByTestId('source-code')).toHaveText(code)
  await expect(card.getByTestId('source-hash')).toHaveText('SHA-256 khớp bản phát hành')
  await expect(card.getByRole('link', { name: /Mở trang xác thực/ })).toHaveAttribute('href', `/xac-thuc/${code.replace('-', '')}`)
  // dòng thời gian bắt đầu bằng "nhận liên thông" (dịch vụ tạo văn bản), không có bước "tiếp nhận" của văn thư
  const timeline = receiver.getByTestId('timeline')
  await expect(timeline.getByText(`Nhận liên thông từ ${SENDER}`)).toBeVisible()
  await expect(timeline.getByText('Tiếp nhận văn bản', { exact: true })).toHaveCount(0)
  await shot(receiver, '27-nhan-lien-thong')
  receiver.once('dialog', (dialog) => dialog.accept())
  await receiver.getByRole('button', { name: 'Vào sổ', exact: true }).click()
  await expect(receiver.getByText(/Đã vào sổ — số đến \d+/)).toBeVisible()
  await expect(receiver.getByText('Chờ chỉ đạo').first()).toBeVisible()
  await shot(receiver, '28-lien-thong-da-vao-so')
})
