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

// Phả hệ số liệu (F3.9, F3.11) trên giao diện: nút "Nguồn số liệu" của biểu đồ thời gian xử lý trên trang Điều hành
// mở trang Phả hệ lọc đúng biểu đồ đó — khung nhìn office.v_processing_time và các bảng nó đọc (tính từ catalog CSDL),
// đồ thị ECharts đã vẽ; bỏ lọc thì đủ bốn khung nhìn; tải được tệp OpenLineage. Văn thư không có mục này, mở thẳng
// đường dẫn cũng không thấy gì. Không giả định đã có lượt nộp lưu: chỉ kiểm khối nộp lưu có mặt. Cờ kiểm chất lượng số
// liệu (office.report_checks): có cạnh nút Nguồn số liệu của từng biểu đồ, trang Phả hệ có mục kiểm chất lượng của
// khung nhìn đang xem — không giả định cờ nào (dữ liệu CI có thể có cảnh báo), chỉ kiểm chữ của cờ.

test('phả hệ số liệu: biểu đồ ← khung nhìn ← bảng, chỉ lãnh đạo đơn vị xem', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Điều hành' }).click()
  for (const chart of ['kpis', 'status', 'departments', 'processing', 'outgoing']) {
    await expect(director.getByTestId(`checks-${chart}`)).toHaveText(/Đạt|Cảnh báo|Trượt/)
  }
  await director.getByTestId('source-processing').click()
  await expect(director).toHaveURL(/\/pha-he\/?\?bieu-do=processing$/)
  await expect(director.getByRole('heading', { level: 1, name: 'Phả hệ số liệu' })).toBeVisible()
  await expect(director.getByTestId('lineage-chart')).toHaveValue('processing')
  const sources = director.getByTestId('lineage-sources')
  await expect(sources.locator('tbody tr')).toHaveCount(1)
  const checks = director.getByTestId('lineage-checks')
  await expect(checks.locator('tr[data-rule="processing_coverage"]')).toHaveCount(1)
  await expect(checks.locator('tr[data-rule="no_personal_columns"]')).toContainText('office.v_processing_time')
  for (const name of ['office.v_processing_time', 'office.documents', 'office.document_events',
    'office.archived_document_facts']) await expect(sources).toContainText(name)
  await expect(director.getByTestId('lineage-graph').locator('svg').first()).toBeVisible()
  await expect(director.getByTestId('lineage-archive-totals')).toBeVisible()

  // mọi biểu đồ: đủ bốn khung nhìn của trang Điều hành
  await director.getByTestId('lineage-chart').selectOption('')
  await expect(director).toHaveURL(/\/pha-he\/?$/)
  for (const view of ['office.v_document_counts', 'office.v_overdue_by_department', 'office.v_outgoing_by_month']) {
    await expect(sources).toContainText(view)
  }
  const download = director.waitForEvent('download')
  await director.getByTestId('lineage-export').click()
  expect((await download).suggestedFilename()).toBe('pha-he-openlineage.jsonl')
  await shot(director, '18b-pha-he')

  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await expect(clerk.getByRole('link', { name: 'Sổ đăng ký' })).toBeVisible()
  await expect(clerk.getByRole('link', { name: 'Phả hệ số liệu' })).toHaveCount(0)
  await clerk.goto('/pha-he')
  await expect(clerk.getByText('Chỉ lãnh đạo đơn vị xem được trang này.')).toBeVisible()
  await expect(clerk.getByTestId('lineage-graph')).toHaveCount(0)
})
