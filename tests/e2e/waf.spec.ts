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
import { PASSWORD, shot, signIn, textPdf } from './helpers'

// Tường lửa ứng dụng web ở cổng (F3.15, platform/apisix/README.md, mục WAF) trên trình duyệt thật: chữ thật mà OWASP
// CRS từng chặn nhầm — tên tệp có ' ; =, nội dung có đề mục La Mã và đường dẫn theo IP, câu tìm "File …?" — đi qua
// được theo đúng đường trình duyệt gửi (FormData của Chrome, biến GraphQL của trang Soạn, vue-router); ô chữ ngắn không
// được loại trừ thì vẫn bị chặn, và giao diện nói rõ "Cổng an ninh chặn…" kèm mã X-Request-Id thay cho lỗi đọc JSON.
// Ca chặn cần MOC_WAF=On (mặc định của .env.example, CI dùng giá trị đó).

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
const URL_IP = 'http://192.168.1.10:8080/van-ban/12'
const FILE_NAME = "Tờ trình 'gấp'; đợt 1 = mới.pdf"
const QUESTION = 'File đính kèm ở đâu?'
const BODY = [
  'I. MỤC ĐÍCH, YÊU CẦU',
  'Rà soát đề cương chi tiết các học phần theo chuẩn đầu ra mới.',
  'II. NỘI DUNG',
  'Các bộ môn cập nhật đề cương, gửi về Tổ Đào tạo trước ngày 15.',
  'III. TỔ CHỨC THỰC HIỆN',
  'Danh sách học phần xem tại:',
  URL_IP,
].join('\n')

// Chuyên viên (không cần mã TOTP) mở trang Soạn văn bản đi, điền trích yếu, nội dung, nơi nhận
async function compose(page: Page, summary: string, body: string, recipients: string) {
  await page.getByRole('link', { name: 'Soạn văn bản đi' }).click()
  await page.getByLabel('Trích yếu nội dung').fill(summary)
  await page.getByLabel('Nội dung', { exact: true }).fill(body)
  await page.getByLabel('Nơi nhận').fill(recipients)
}

test.skip(() => !PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')

test("tải lên tệp tên có ' ; = qua cổng, trang văn bản hiện đúng tên", async ({ browser }) => {
  const staff = await signIn(browser, 'chuyenviendt')
  const summary = `Về việc gửi tờ trình kèm tệp có tên đặc biệt (thử ${tag})`
  await compose(staff, summary, 'Gửi kèm tờ trình để Phòng Đào tạo xem xét.', 'Phòng Đào tạo')
  // loại trừ 10040: chỉ tên tệp trên đường tải lên; ClamAV vẫn quét nội dung
  await staff.locator('input[type=file]').setInputFiles({ name: FILE_NAME, mimeType: 'application/pdf',
    buffer: textPdf(`To trinh gap dot 1 ${tag}`) })
  await expect(staff.getByRole('listitem').filter({ hasText: FILE_NAME }).getByText('Đã quét — sạch')).toBeVisible()
  await staff.getByRole('button', { name: 'Lưu dự thảo' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  const files = staff.locator('section').filter({ has: staff.getByRole('heading', { name: 'Tệp đính kèm' }) })
  await expect(files.getByText(FILE_NAME, { exact: true })).toBeVisible()
  await shot(staff, 'waf-1-ten-tep')
})

test('nội dung có đề mục I. II. III. và đường dẫn theo IP: lưu nháp, mở lại nguyên văn', async ({ browser }) => {
  const staff = await signIn(browser, 'chuyenviendt')
  const summary = `Về việc kế hoạch rà soát đề cương học phần (thử ${tag})`
  // loại trừ 10031 trên o.body khi thêm mới, set.body khi sửa
  await compose(staff, summary, BODY, 'Phòng Đào tạo')
  await staff.getByRole('button', { name: 'Lưu dự thảo' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  await expect(staff.getByText('III. TỔ CHỨC THỰC HIỆN')).toBeVisible()
  await staff.getByRole('link', { name: 'Sửa dự thảo' }).click()
  await expect(staff.getByLabel('Nội dung', { exact: true })).toHaveValue(BODY)
  await shot(staff, 'waf-2-de-muc-la-ma')
  await staff.getByRole('button', { name: 'Lưu dự thảo' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  await staff.getByRole('link', { name: 'Sửa dự thảo' }).click()
  await expect(staff.getByLabel('Nội dung', { exact: true })).toHaveValue(BODY)
})

test('ô Tìm kiếm: "File đính kèm ở đâu?" mở được trang kết quả, tải lại vẫn mở', async ({ browser }) => {
  const staff = await signIn(browser, 'chuyenviendt')
  await staff.getByRole('link', { name: 'Tìm kiếm', exact: true }).click()
  const box = staff.getByRole('searchbox', { name: 'Tìm kiếm văn bản' })
  await box.fill(QUESTION)
  await box.press('Enter')
  // loại trừ 10033 trên q của /api/search và của chính trang /tim-kiem (tải lại, mở từ đường dẫn)
  const outcome = staff.locator('a[href^="/van-ban/"]').first().or(staff.getByText('Không có văn bản nào khớp.'))
  await expect(outcome).toBeVisible()
  await expect(staff).toHaveURL(/\/tim-kiem\?q=/)
  await staff.reload()
  await expect(box).toHaveValue(QUESTION)
  await expect(outcome).toBeVisible()
  await expect(staff.getByText(/Cổng an ninh chặn|Unexpected token|Có lỗi xảy ra/)).toHaveCount(0)
  await shot(staff, 'waf-3-tim-kiem')
})

test('ô chữ ngắn không được loại trừ: cổng chặn, giao diện báo rõ kèm mã X-Request-Id', async ({ browser }) => {
  test.skip((process.env.MOC_WAF ?? 'On') !== 'On', `MOC_WAF=${process.env.MOC_WAF}: cổng không chặn`)
  const staff = await signIn(browser, 'chuyenviendt')
  // Nơi nhận chỉ là một đường dẫn theo IP: o.recipients không có trong loại trừ 10031 → luật 931100 (RFI) → 403
  await compose(staff, `Về việc thử cổng an ninh với ô Nơi nhận (thử ${tag})`, 'Nội dung thử.', URL_IP)
  const [response] = await Promise.all([
    staff.waitForResponse((r) => r.url().endsWith('/v1/graphql')
      && (r.request().postData() ?? '').includes('insert_office_documents_one')),
    staff.getByRole('button', { name: 'Lưu dự thảo' }).click(),
  ])
  expect(response.status()).toBe(403)
  const requestId = response.headers()['x-request-id']
  expect(requestId).toMatch(/^[0-9a-f-]{36}$/)
  const alert = staff.getByRole('alert').filter({ hasText: 'Cổng an ninh chặn' })
  await expect(alert).toContainText(`(mã ${requestId})`)
  await expect(alert).not.toContainText('Unexpected token')
  await shot(staff, 'waf-4-cong-chan')
  // không lưu gì: vẫn ở trang soạn, chữ đã gõ còn nguyên để sửa
  await expect(staff).toHaveURL(/\/van-ban-di\/soan/)
  await expect(staff.getByLabel('Nơi nhận')).toHaveValue(URL_IP)
})
