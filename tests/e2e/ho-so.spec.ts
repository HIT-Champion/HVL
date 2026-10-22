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
import { PASSWORD, signIn, shot } from './helpers'

test('hồ sơ: lập, thêm văn bản, đóng và khóa thao tác sửa', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần dữ liệu mẫu và MOC_DEMO_PASSWORD')
  const page = await signIn(browser, 'chuyenviendt')
  await page.getByRole('link', { name: 'Hồ sơ công việc', exact: true }).click()
  await page.getByRole('button', { name: 'Lập hồ sơ', exact: true }).click()
  const code = `FE-${Date.now()}`
  const title = `Hồ sơ nghiệm thu giao diện ${code}`
  await page.getByLabel('Mã hồ sơ', { exact: true }).fill(code)
  await page.getByLabel('Tên hồ sơ', { exact: true }).fill(title)
  await page.getByRole('button', { name: 'Lưu', exact: true }).click()
  const detail = page.getByTestId('case-detail')
  await expect(detail.getByRole('heading', { name: title })).toBeVisible()
  await expect(detail.getByRole('button', { name: 'Đóng hồ sơ' })).toBeDisabled()
  const select = detail.getByLabel('Thêm văn bản', { exact: true })
  const options = await select.locator('option').evaluateAll(nodes => nodes.map(node => (node as HTMLOptionElement).value).filter(Boolean))
  expect(options.length).toBeGreaterThan(0)
  await select.selectOption(options[0])
  await detail.getByRole('button', { name: 'Thêm văn bản', exact: true }).click()
  await expect(detail.locator('li')).toHaveCount(1)
  page.once('dialog', dialog => dialog.accept())
  await detail.getByRole('button', { name: 'Đóng hồ sơ', exact: true }).click()
  await expect(detail.getByText('Đã đóng', { exact: true })).toBeVisible()
  await expect(detail.getByRole('button', { name: 'Thêm văn bản', exact: true })).toHaveCount(0)
  await shot(page, '20-ho-so-da-dong')
  await page.reload()
  await page.getByRole('searchbox', { name: 'Tìm mã hoặc tên hồ sơ…' }).fill(code)
  await expect(page.getByTestId('case-detail').getByRole('heading', { name: title })).toBeVisible()
})
