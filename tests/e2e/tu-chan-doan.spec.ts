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

// Tự chẩn đoán H-P-D-I (docs/tu-chan-doan.md): lãnh đạo khoa thấy bằng chứng đo được của đơn vị mẫu, trả lời đủ 12
// câu, thấy radar ECharts, lệch nền, không gian nên làm trước, bước tiếp theo trỏ trang có thật; lưu thì có dòng mới
// trong lịch sử. Tổ trưởng (lãnh đạo phòng) làm được nhưng không lưu, không có bằng chứng, và bước tiếp theo không dẫn
// tới trang chỉ lãnh đạo đơn vị mở được; văn thư không có mục này. Mỗi lần chạy lưu một lần trong đơn vị mẫu: CSDL cho
// mỗi đơn vị tối đa 5 lần lưu mỗi giờ (maturity_rate), nên chạy lại quá 5 lần trong một giờ trên cùng CSDL sẽ đỏ.

test('tự chẩn đoán H-P-D-I: lãnh đạo trả lời, xem radar, lệch nền, bước tiếp theo và lưu', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Tự chẩn đoán' }).click()
  await expect(director.getByRole('heading', { level: 1, name: 'Tự chẩn đoán H-P-D-I' })).toBeVisible()
  // make seed có văn bản nên [D] có số văn bản trên hệ thống; số lấy từ view, không kiểm giá trị cụ thể
  await expect(director.getByTestId('hpdi-ev-documents')).toBeVisible()

  // [H] 4, [P] 3, [D] 2, [I] 4: [I] vượt [D] 2 mức → lệch nền, nên làm [D] trước
  const levels: Record<string, number> = { h: 4, p: 3, d: 2, i: 4 }
  for (const [space, level] of Object.entries(levels)) {
    for (const n of [1, 2, 3]) {
      await director.getByTestId(`hpdi-q-${space}${n}`).getByRole('radio').nth(level - 1).check()
    }
  }
  await expect(director.getByTestId('hpdi-progress')).toHaveText('Đã trả lời 12/12 câu')
  await expect(director.getByTestId('hpdi-result').locator('svg').first()).toBeVisible()   // radar đã vẽ
  await expect(director.getByTestId('hpdi-score-d')).toHaveText('2')
  await expect(director.getByTestId('hpdi-gaps')).toContainText('[I] Trí tuệ cao hơn [D] Dữ liệu 2 mức')
  await expect(director.getByTestId('hpdi-focus')).toContainText('[D] Dữ liệu')
  const step = director.getByTestId('hpdi-step-d')
  await expect(step).toContainText('Làm trước')
  await shot(director, '41-tu-chan-doan')

  const note = `e2e ${Date.now()}`
  await director.getByLabel('Ghi chú').fill(note)
  await director.getByTestId('hpdi-save-button').click()
  await expect(director.getByTestId('hpdi-history').locator('tr', { hasText: note })).toBeVisible()

  // bước tiếp theo của [D] trỏ trang Điều hành có thật
  await step.getByRole('link', { name: 'Điều hành' }).click()
  await expect(director).toHaveURL(/\/dieu-hanh$/)
  await expect(director.getByRole('heading', { level: 1, name: 'Điều hành' })).toBeVisible()

  const manager = await signIn(browser, 'totruongdt', { otp: true })
  await manager.getByRole('link', { name: 'Tự chẩn đoán' }).click()
  await expect(manager.getByTestId('hpdi-manager-note')).toBeVisible()
  await expect(manager.getByTestId('hpdi-evidence-h')).toHaveCount(0)
  await expect(manager.getByTestId('hpdi-save')).toHaveCount(0)
  for (const space of ['h', 'p', 'd', 'i']) {
    for (const n of [1, 2, 3]) await manager.getByTestId(`hpdi-q-${space}${n}`).getByRole('radio').first().check()
  }
  // bước của [D] trỏ Điều hành, Số đo — trang của lãnh đạo đơn vị: chỉ hiện tên trang, không có liên kết
  const managerStep = manager.getByTestId('hpdi-step-d')
  await expect(managerStep).toContainText('Điều hành (trang của Lãnh đạo đơn vị)')
  await expect(managerStep.getByRole('link')).toHaveCount(0)
  await expect(manager.getByTestId('hpdi-step-p').getByRole('link', { name: 'Văn bản đến' })).toBeVisible()

  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await expect(clerk.getByRole('link', { name: 'Tự chẩn đoán' })).toHaveCount(0)
  await clerk.goto('/tu-chan-doan')
  await expect(clerk.getByText('Chỉ lãnh đạo đơn vị và lãnh đạo phòng dùng được trang này.')).toBeVisible()
})
