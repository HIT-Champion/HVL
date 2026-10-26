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
import { PASSWORD, SCAN_TIMEOUT, TOTP_SECRET, shot, signIn, textPdf } from './helpers'

// Kịch bản demo (docs/dac-ta-san-pham.md §7, màn 1–2) trên giao diện thật: form sai bị chặn, văn thư tiếp nhận và
// vào sổ → lãnh đạo khoa chỉ đạo → tổ trưởng phân công → chuyên viên báo xong → tìm lại được bằng chữ không dấu,
// và bằng chữ chỉ có trong tệp PDF đính kèm.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
const summary = `Về việc rà soát chương trình đào tạo ngành Kỹ thuật phần mềm năm 2027 (thử ${tag})`

async function openTask(page: Page, screenshot?: string) {
  await page.goto('/')
  const item = page.getByRole('link', { name: new RegExp(tag) })
  await expect(item).toBeVisible()
  if (screenshot) await shot(page, screenshot)
  await item.click()
  await expect(page.getByRole('heading', { level: 1, name: summary })).toBeVisible()
}

test.describe.configure({ mode: 'serial' })

test('luồng văn bản đến trên giao diện', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  // 1. Văn thư tiếp nhận, tải tệp (quét ClamAV), nhập thông tin, vào sổ
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await clerk.getByRole('link', { name: 'Tiếp nhận văn bản' }).click()
  const pdf = textPdf('De nghi Khoa ra soat chuong trinh dao tao', `Phu luc kem theo: bang doi chieu chuan dau ra ${tag}`)
  await clerk.locator('input[type=file]').setInputFiles({ name: `cong-van-${tag}.pdf`, mimeType: 'application/pdf', buffer: pdf })
  await expect(clerk.getByText('Đã quét — sạch')).toBeVisible({ timeout: SCAN_TIMEOUT })

  // Poka-yoke lớp 1 (F2.2): form sai bị chặn ngay trên trình duyệt theo schemas/van-ban-den.json, chưa gửi gì đi
  const sent: string[] = []
  clerk.on('request', (r) => { if (r.postData()?.includes('receiveIncoming')) sent.push(r.url()) })
  await clerk.getByRole('button', { name: 'Lưu và vào sổ' }).click()
  await expect(clerk.getByText('Không được để trống')).toHaveCount(4)
  await clerk.getByLabel('Trích yếu nội dung').fill('Ngắn quá')
  await clerk.getByLabel('Ngày ban hành').fill(new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10))
  await expect(clerk.getByText('Cần 10–500 ký tự')).toBeVisible()
  await expect(clerk.getByText('Không được sau hôm nay')).toBeVisible()
  await shot(clerk, '0-form-sai-bi-chan')
  expect(sent).toEqual([])

  await clerk.getByLabel('Số, ký hiệu').fill(`45/ĐHCN-ĐT${tag}`)
  await clerk.getByLabel('Ngày ban hành').fill(new Date().toISOString().slice(0, 10))
  await clerk.getByLabel('Cơ quan ban hành').fill('Trường Đại học Công nghiệp')
  await clerk.getByLabel('Trích yếu nội dung').fill(summary)
  await clerk.getByLabel('Độ khẩn').selectOption('khan')
  await shot(clerk, '1-tiep-nhan')
  await clerk.getByRole('button', { name: 'Lưu và vào sổ' }).click()
  await expect(clerk.getByText(/Đã vào sổ — số đến \d+/)).toBeVisible()
  await expect(clerk.getByText('Chờ chỉ đạo').first()).toBeVisible()
  await shot(clerk, '2-da-vao-so')

  // 2. Lãnh đạo khoa: việc khẩn trong hộp việc → chỉ đạo, giao Tổ Đào tạo chủ trì, Bộ môn KTPM phối hợp
  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await openTask(director, '3-hop-viec-lanh-dao')
  await director.getByLabel('Ý kiến chỉ đạo').fill('Giao Tổ Đào tạo chủ trì rà soát, Bộ môn KTPM phối hợp. Báo cáo trước hạn.')
  await director.getByLabel('Phòng chủ trì').selectOption({ label: 'Tổ Đào tạo' })
  await director.getByLabel('Bộ môn Kỹ thuật phần mềm').check()
  await shot(director, '4-chi-dao')
  await director.getByRole('button', { name: 'Giao xử lý' }).click()
  await expect(director.getByText('Đã chuyển bước tiếp theo.')).toBeVisible()
  await expect(director.getByText('Đang xử lý').first()).toBeVisible()

  // 3. Tổ trưởng Đào tạo phân công chuyên viên
  const manager = await signIn(browser, 'totruongdt', { otp: true })
  await openTask(manager)
  await manager.getByLabel('Giao cho').selectOption({ label: 'Hoàng Văn Nam' })
  await manager.getByLabel('Lời dặn').fill('Em rà soát và dự thảo công văn trả lời.')
  await manager.getByRole('button', { name: 'Giao việc' }).click()
  await expect(manager.getByText('Đã chuyển bước tiếp theo.')).toBeVisible()

  // 4. Chuyên viên báo kết quả
  const staff = await signIn(browser, 'chuyenviendt')
  await openTask(staff)
  await staff.getByLabel('Kết quả xử lý').fill('Đã rà soát chương trình, gửi báo cáo cho lãnh đạo khoa.')
  await staff.getByRole('button', { name: 'Báo cáo xong' }).click()
  await expect(staff.getByText('Đã xử lý').first()).toBeVisible()
  await expect(staff.getByText('Báo cáo kết quả')).toBeVisible()
  await shot(staff, '5-da-xu-ly')

  // Lịch sử (F3.5): chuyên viên — không riêng lãnh đạo — xem từng lần sửa văn bản, đọc từ sổ kiểm toán
  await staff.getByRole('tab', { name: 'Lịch sử' }).click()
  const history = staff.getByTestId('history')
  await expect(history.getByText('Thêm · Văn bản', { exact: true })).toBeVisible()
  await expect(history.getByText('Trạng thái:').first()).toBeVisible()
  await shot(staff, '5b-lich-su')

  // 5. Tìm lại bằng chữ không dấu (Meilisearch đồng bộ sau vài giây)
  await expect(async () => {
    await staff.goto(`/tim-kiem?q=${encodeURIComponent(`ra soat chuong trinh ${tag}`)}`)
    await expect(staff.getByRole('link', { name: new RegExp(tag) })).toBeVisible({ timeout: 3_000 })
  }).toPass({ timeout: 30_000 })
  await shot(staff, '6-tim-kiem')

  // 6. Tìm bằng chữ chỉ có trong tệp PDF (F2.7): svc-files đọc lớp chữ ở vòng nền rồi đồng bộ sang Meilisearch
  await expect(async () => {
    await staff.goto(`/tim-kiem?q=${encodeURIComponent(`bang doi chieu chuan dau ra ${tag}`)}`)
    const hit = staff.getByRole('link', { name: new RegExp(tag) })
    await expect(hit).toBeVisible({ timeout: 3_000 })
    await expect(hit.getByText('Khớp trong nội dung')).toBeVisible()
  }).toPass({ timeout: 60_000 })
  await shot(staff, '6b-tim-theo-noi-dung')
})
