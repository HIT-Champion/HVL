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

import { expect, test, type Locator, type Page } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Hỏi đáp trên kho văn bản (F4.2) trên giao diện: văn thư mở "Hỏi đáp", hỏi điều kiện xét học bổng khuyến khích học
// tập → khối "Câu trích nguyên văn" có "3,2", nguồn "88/CTSV · tr. 1" (công văn seed của Phòng Công tác sinh viên);
// dấu [1] đưa tới mục nguồn. Giảng viên Bộ môn KTPM hỏi đúng câu đó → không thấy 88/CTSV (công văn giao Tổ Đào tạo),
// có câu "Không tìm thấy…". "Hỏi về văn bản này" ở trang chi tiết chỉ hỏi trong văn bản đó; nhãn nguồn mở tệp đúng
// trang. CI không bật mô hình ngôn ngữ: chỉ kiểm phần trích nguyên văn, chạy được cả khi có mô hình (câu trích hiện
// ngay, câu trả lời của mô hình đến sau).

const QUESTION = 'Điều kiện xét học bổng khuyến khích học tập là gì?'
const DONE = /^(answered|passages_only|no_evidence|error)$/

// Hỏi một câu và chờ xong pha tìm; như một cuộc trò chuyện, lượt mới nhất nằm cuối
async function ask(page: Page, question: string): Promise<Locator> {
  await page.getByLabel('Câu hỏi', { exact: true }).fill(question)
  await page.getByRole('button', { name: 'Hỏi', exact: true }).click()
  const turn = page.getByTestId('ask-turn').last()
  await expect(turn).toHaveAttribute('data-state', DONE, { timeout: 30_000 })
  return turn
}

test('hỏi đáp: văn thư thấy câu trích nguyên văn và nguồn; giảng viên đơn vị khác không thấy', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  // 1. Từ Tìm kiếm, "Hỏi trợ lý" mang câu đang tìm sang trang Hỏi đáp: điền sẵn, không tự gửi
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await clerk.getByRole('link', { name: 'Tìm kiếm', exact: true }).click()
  await clerk.getByRole('searchbox', { name: 'Tìm kiếm văn bản' }).fill('học bổng')
  await clerk.getByRole('link', { name: 'Hỏi trợ lý' }).click()
  await expect(clerk).toHaveURL(/\/hoi-dap\?q=/)
  await expect(clerk.getByRole('heading', { level: 1, name: 'Hỏi đáp văn bản' })).toBeVisible()
  await expect(clerk.getByText('văn bản hạn chế không bao giờ được đưa vào')).toBeVisible()
  await expect(clerk.getByLabel('Câu hỏi', { exact: true })).toHaveValue('học bổng')
  await expect(clerk.getByTestId('ask-turn')).toHaveCount(0)

  // 2. Hỏi: câu trích có "3,2", nguồn 88/CTSV. Chỉ mục đoạn đồng bộ vài giây sau make seed: hỏi lại tới 60 giây
  let turn = clerk.getByTestId('ask-turn').last()
  await expect(async () => {
    turn = await ask(clerk, QUESTION)
    await expect(turn.getByTestId('ask-extract')).toContainText('3,2', { timeout: 1_000 })
    await expect(turn.getByTestId('ask-sources')).toContainText('88/CTSV', { timeout: 1_000 })
  }).toPass({ timeout: 60_000, intervals: [3_000, 5_000] })
  await expect(turn.getByTestId('ask-sources')).toContainText('88/CTSV · tr. 1')
  await expect(turn.getByTestId('ask-mode')).toContainText('Tìm theo từ khóa')
  await expect(clerk.getByTestId('ask-live')).toContainText(/Đã tìm thấy \d+ đoạn liên quan/)
  await shot(clerk, '33-hoi-dap-cau-trich')

  // dấu [n] là liên kết có tên đọc được, đưa tiêu điểm tới mục nguồn
  const cite = turn.getByTestId('ask-extract').getByRole('link', { name: /^Nguồn \d+: 88\/CTSV, trang 1$/ }).first()
  await cite.click()
  await expect(turn.locator('li:focus')).toContainText('88/CTSV')

  // "Mở văn bản" của nguồn đi tới đúng văn bản
  await turn.getByRole('link', { name: 'Mở văn bản 88/CTSV, trang 1' }).first().click()
  await expect(clerk).toHaveURL(/\/van-ban\/[0-9a-f-]{36}$/)
  await expect(clerk.getByText('88/CTSV').first()).toBeVisible()

  // 3. "Hỏi về văn bản này": trang Hỏi đáp chỉ hỏi trong 88/CTSV, mọi nguồn của văn bản đó; nhãn nguồn mở tệp ở khung
  // xem, đúng trang được trích (#page=n); bỏ phạm vi thì về hỏi cả kho
  await clerk.getByTestId('ask-about').click()
  await expect(clerk).toHaveURL(/\/hoi-dap\?van_ban=[0-9a-f-]{36}$/)
  await expect(clerk.getByTestId('ask-scope')).toContainText('88/CTSV')
  const scoped = await ask(clerk, QUESTION)
  await expect(scoped).toHaveAttribute('data-state', 'answered')
  await expect(scoped.getByTestId('ask-scope-chip')).toContainText('88/CTSV')
  const items = await scoped.getByTestId('ask-sources').locator('li').allInnerTexts()
  expect(items.length).toBeGreaterThan(0)
  for (const item of items) expect(item).toContain('88/CTSV')
  await scoped.getByRole('button', { name: 'Xem tệp: 88/CTSV, trang 1' }).first().click()
  await expect(scoped.getByTestId('ask-viewer').locator('iframe')).toHaveAttribute('src', /^blob:.+#page=1$/)
  await clerk.getByTestId('ask-scope').getByRole('button', { name: 'Hỏi trong mọi văn bản' }).click()
  await expect(clerk).toHaveURL(/\/hoi-dap$/)
  await expect(clerk.getByTestId('ask-scope')).toHaveCount(0)

  // 4. Giảng viên Bộ môn KTPM: công văn giao Tổ Đào tạo, không được xem → không có nguồn nào, câu "Không tìm thấy"
  const lecturer = await signIn(browser, 'giangvienktpm')
  await lecturer.getByRole('link', { name: 'Hỏi đáp', exact: true }).click()
  const other = await ask(lecturer, QUESTION)
  await expect(other).toHaveAttribute('data-state', 'no_evidence')
  await expect(other.getByTestId('ask-none')).toContainText('Không tìm thấy văn bản nào bạn được xem có nội dung này')
  await expect(other.getByTestId('ask-sources')).toHaveCount(0)
  await expect(lecturer.getByText('88/CTSV')).toHaveCount(0)
  await shot(lecturer, '34-hoi-dap-khong-thay')
})
