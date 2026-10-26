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
import { PASSWORD, shot, signIn } from './helpers'

// Tài khoản cho ban giám khảo (README): chuyên viên, không cần TOTP. Sau make seed hộp việc có sẵn công văn khẩn
// 152/ĐT-ĐH chờ xử lý và dự thảo phúc đáp bị tổ trưởng trả lại chờ sửa (scripts/seed_documents.py), không phải hộp việc
// trống. Ô chữ đại diện ở đầu trang là chữ đầu của tên, viết hoa: "Tài khoản Giám khảo" ra G, không phải "k".

test('giám khảo: hộp việc có sẵn việc mẫu, chữ đại diện là chữ đầu của tên', async ({ browser }) => {
  test.skip(!PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')

  const judge = await signIn(browser, 'giamkhao')
  const tasks = judge.getByTestId('inbox').getByRole('listitem')
  const handle = tasks.filter({ hasText: '152/ĐT-ĐH' }).filter({ hasText: 'Xử lý văn bản' })
  await expect(handle).toHaveCount(1)
  await expect(handle).toContainText('Khẩn')
  const redraft = tasks.filter({ hasText: 'Sửa dự thảo theo ý kiến' })
    .filter({ hasText: 'góp ý dự thảo Quy định đào tạo trình độ đại học' })
  await expect(redraft).toHaveCount(1)
  await expect(judge.getByTestId('avatar-initial')).toHaveText('G')
  await shot(judge, '30-giam-khao')

  // việc sửa dự thảo mở ra đúng văn bản đi, có ý kiến trả lại của tổ trưởng; nút quay lại về hộp việc
  await redraft.getByRole('link').click()
  await expect(judge).toHaveURL(/\/van-ban\/[0-9a-f-]{36}\?from=inbox$/)
  await expect(judge.getByText('Bổ sung ý kiến của Bộ môn Kỹ thuật phần mềm').first()).toBeVisible()
  await judge.getByRole('link', { name: 'Về hộp việc' }).click()
  await expect(judge.getByTestId('inbox')).toBeVisible()

  // ngữ cảnh việc (#235): khung báo kết quả có chỉ đạo của phòng và ghi chú phân công; gửi trống thì tiêu điểm về ô
  // kết quả, không gửi gì
  const search = judge.getByRole('searchbox', { name: 'Tìm trong hộp việc…' })
  await search.fill('152')
  await handle.getByRole('link').click()
  const brief = judge.getByTestId('processing-brief')
  await expect(brief).toContainText('Giao Tổ Đào tạo chủ trì thực hiện, báo cáo đúng hạn.')
  await expect(brief).toContainText('Đề nghị xử lý và báo cáo kết quả.')
  await expect(brief).toContainText('Hạn giải quyết')
  await judge.getByRole('button', { name: 'Báo cáo xong', exact: true }).click()
  const result = judge.getByLabel('Kết quả xử lý')
  await expect(result).toBeFocused()
  await expect(result).toHaveAttribute('aria-invalid', 'true')
  await shot(judge, '30-giam-khao-yeu-cau')

  // tab Dòng thời gian / Lịch sử bằng bàn phím; Esc đóng khung Góp ý và trả tiêu điểm về nút
  const timelineTab = judge.getByRole('tab', { name: 'Dòng thời gian', exact: true })
  const historyTab = judge.getByRole('tab', { name: 'Lịch sử', exact: true })
  await timelineTab.focus()
  await judge.keyboard.press('ArrowRight')
  await expect(historyTab).toBeFocused()
  await expect(historyTab).toHaveAttribute('aria-selected', 'true')
  await expect(judge.getByRole('tabpanel', { name: 'Lịch sử' })).toBeVisible()
  await judge.keyboard.press('Home')
  await expect(timelineTab).toBeFocused()
  await expect(judge.getByRole('tabpanel', { name: 'Dòng thời gian' })).toBeVisible()
  await judge.getByTestId('feedback-open').click()
  await expect(judge.getByTestId('feedback-form')).toBeVisible()
  await judge.keyboard.press('Escape')
  await expect(judge.getByTestId('feedback-form')).toHaveCount(0)
  await expect(judge.getByTestId('feedback-open')).toBeFocused()

  // quay lại hộp việc: ô tìm còn nguyên
  await judge.getByRole('link', { name: 'Về hộp việc' }).click()
  await expect(search).toHaveValue('152')
})
