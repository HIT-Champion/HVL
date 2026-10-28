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

// Gợi ý giao việc (F4.3) trên giao diện: văn thư vào sổ công văn xét cấp học bổng → lãnh đạo khoa mở việc "Cho ý
// kiến chỉ đạo", trong 30 giây thấy khối "Gợi ý giao việc": Tổ Đào tạo chủ trì, căn cứ có 88/CTSV (công văn seed đã
// giao Tổ Đào tạo). "Dùng gợi ý" chỉ điền form, không gửi gì; lãnh đạo nhập ý kiến rồi tự bấm "Giao xử lý". Tab Lịch
// sử có dòng của "Tác tử gợi ý giao việc", không có trích yếu. Độ tin cậy tùy dữ liệu đã có: chỉ kiểm có chip.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
// câu tìm của tác tử lấy tối đa 10 từ đầu của trích yếu (đã bỏ "Về việc"): tag đứng sau từ thứ 10 nên không làm lệch
const summary = `Về việc xét cấp học bổng khuyến khích học tập học kỳ II năm học 2026–2027 (thử ${tag})`

test('gợi ý giao việc: lãnh đạo thấy đơn vị chủ trì và căn cứ, "Dùng gợi ý" chỉ điền form', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')
  // hai lần đăng nhập có mã TOTP (có thể phải đợi sang khoảng 30 giây mới) cộng thời gian đợi tác tử
  test.setTimeout(180_000)

  // 1. Văn thư tiếp nhận, vào sổ. Không ghi hạn: hạn do tác tử đề xuất theo các văn bản tương tự. Chữ trong tệp không
  //    nói về học bổng để không chen vào câu trích của kịch bản hỏi đáp (hoi-dap.spec.ts)
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await clerk.getByRole('link', { name: 'Tiếp nhận văn bản' }).click()
  const pdf = textPdf('Kinh gui Lanh dao Khoa', `Ma ho so ${tag}`)
  await clerk.locator('input[type=file]').setInputFiles({ name: `hoc-bong-${tag}.pdf`, mimeType: 'application/pdf', buffer: pdf })
  await expect(clerk.getByText('Đã quét — sạch')).toBeVisible({ timeout: SCAN_TIMEOUT })
  await clerk.getByLabel('Số, ký hiệu').fill(`52/CTSV-${tag}`)
  await clerk.getByLabel('Ngày ban hành').fill(new Date().toISOString().slice(0, 10))
  await clerk.getByLabel('Cơ quan ban hành').fill('Phòng Công tác sinh viên')
  await clerk.getByLabel('Trích yếu nội dung').fill(summary)
  await clerk.getByRole('button', { name: 'Lưu và vào sổ' }).click()
  await expect(clerk.getByText(/Đã vào sổ — số đến \d+/)).toBeVisible()

  // 2. Lãnh đạo khoa mở việc. Tác tử chạy song song với bước chỉ đạo, khối tự hỏi lại 3 giây một lần trong 60 giây đầu
  //    kể từ lúc vào sổ; quá 20 giây chưa thấy thì tải lại trang một lần (dòng gợi ý đã có thì hiện ngay khi mở)
  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.goto('/')
  // trong hộp việc: tin realtime ở góc màn hình cũng là liên kết mang trích yếu (#415)
  const item = director.getByTestId('inbox').getByRole('link', { name: new RegExp(tag) })
  await expect(item).toBeVisible()
  await item.click()
  await expect(director.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  const block = director.getByTestId('assign-suggestion')
  const ready = await block.and(director.locator('[data-state="suggested"]')).waitFor({ timeout: 20_000 })
    .then(() => true, () => false)
  if (!ready) {
    await director.reload()
    await expect(block).toHaveAttribute('data-state', 'suggested', { timeout: 10_000 })
  }
  await expect(block.getByRole('heading', { name: 'Gợi ý giao việc' })).toBeVisible()
  await expect(block.getByTestId('assign-suggest-unit')).toHaveText('Tổ Đào tạo')
  await expect(block.getByTestId('assign-suggest-confidence')).toContainText('Tin cậy')
  // căn cứ có 88/CTSV — trừ khi kho đã chạy make demo-giao-viec hay đã chạy smoke / e2e này vài lần: nhiều văn bản
  // học bổng giao Tổ Đào tạo giống bằng hoặc hơn thì 3 căn cứ khối hiện ra (MAX_EVIDENCE trong
  // apps/office/app/utils/assignSuggest.ts) có thể đều là chúng; khi đó cả 3 phải là văn bản học bổng giao Tổ Đào tạo
  const evidence = block.getByTestId('assign-suggest-evidence').getByRole('listitem')
  await expect(evidence.first()).toBeVisible()
  if ((await block.getByRole('link', { name: /88\/CTSV/ }).count()) === 0) {
    await expect(evidence).toHaveCount(3)
    for (const item of await evidence.all()) {
      await expect(item).toContainText('học bổng')
      await expect(item).toContainText('Tổ Đào tạo')
    }
  }
  const basis = evidence.first().getByRole('link')
  await expect(basis).toHaveAttribute('href', /^\/van-ban\/[0-9a-f-]{36}$/)
  await expect(block).toContainText('Tác tử chỉ gợi ý, lãnh đạo quyết định.')
  // chưa chọn phòng chủ trì: chưa có chip theo / khác gợi ý
  await expect(block.getByTestId('assign-suggest-match')).toHaveCount(0)

  // 3. "Dùng gợi ý": ô Phòng chủ trì nhận Tổ Đào tạo, chip "Theo gợi ý"; không có yêu cầu completeTask nào
  const sent: string[] = []
  director.on('request', (r) => { if (r.postData()?.includes('completeTask')) sent.push(r.url()) })
  const lead = director.getByLabel('Phòng chủ trì')
  const dt = await lead.locator('option', { hasText: 'Tổ Đào tạo' }).getAttribute('value')
  expect(dt).toBeTruthy()
  await block.getByRole('button', { name: 'Dùng gợi ý' }).click()
  await expect(lead).toHaveValue(dt!)
  await expect(block.getByTestId('assign-suggest-match')).toHaveText('Theo gợi ý')
  await expect(director.getByRole('button', { name: 'Giao xử lý' })).toBeVisible()
  expect(sent).toEqual([])
  await shot(director, 'giao-viec-1-goi-y')

  // lãnh đạo đổi ý: chip "Khác gợi ý"; dùng lại gợi ý thì về "Theo gợi ý"
  await lead.selectOption({ label: 'Bộ môn Kỹ thuật phần mềm' })
  await expect(block.getByTestId('assign-suggest-match')).toHaveText('Khác gợi ý')
  await block.getByRole('button', { name: 'Dùng gợi ý' }).click()
  await expect(lead).toHaveValue(dt!)
  await expect(block.getByTestId('assign-suggest-match')).toHaveText('Theo gợi ý')
  expect(sent).toEqual([])

  // 4. Lãnh đạo nhập ý kiến, tự bấm "Giao xử lý" → tab Lịch sử có dòng của tác tử, không có trích yếu
  await director.getByLabel('Ý kiến chỉ đạo').fill('Giao Tổ Đào tạo chủ trì xét cấp học bổng theo quy định hiện hành.')
  await director.getByRole('button', { name: 'Giao xử lý' }).click()
  await expect(director.getByText('Đã chuyển bước tiếp theo.')).toBeVisible()
  expect(sent).toHaveLength(1)
  await director.getByRole('tab', { name: 'Lịch sử' }).click()
  const row = director.getByTestId('history').locator('li', { hasText: 'Tác tử gợi ý giao việc' })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('Gợi ý giao việc · Văn bản')
  await expect(row).toContainText('Tổ Đào tạo')
  await expect(row).toContainText('Tin cậy')
  await expect(row).not.toContainText('học bổng')
  await shot(director, 'giao-viec-2-lich-su')
})
