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
import { expect, test } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Sổ đăng ký văn bản (F2.8) trên giao diện: văn thư mở sổ đến năm nay, thấy sổ liền số, in ra PDF để ký nhận và
// đóng sổ (NĐ 30/2020, Điều 16, 22); chuyển sang sổ đi, mở văn bản từ một dòng của sổ.

test('sổ đăng ký: văn thư xem sổ đến, sổ đi năm nay và in ra PDF', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await clerk.getByRole('link', { name: 'Sổ đăng ký' }).click()
  await expect(clerk.getByRole('heading', { level: 1, name: 'Sổ đăng ký văn bản' })).toBeVisible()
  await expect(clerk.getByTestId('register-check')).toContainText(/Sổ liền số, từ số 01 đến số \d{2,}/)
  const table = clerk.getByTestId('register-table')
  await expect(table.getByRole('columnheader', { name: 'Số đến', exact: true })).toBeVisible()
  await shot(clerk, '15-so-dang-ky')

  const [book] = await Promise.all([
    clerk.waitForEvent('download'),
    clerk.getByTestId('register-print').click(),
  ])
  expect(book.suggestedFilename()).toMatch(/^so-dang-ky-van-ban-den-\d{4}\.pdf$/)
  expect(readFileSync(await book.path()).subarray(0, 5).toString()).toBe('%PDF-')

  await clerk.getByRole('tab', { name: 'Sổ văn bản đi' }).click()
  await expect(table.getByRole('columnheader', { name: 'Người ký', exact: true })).toBeVisible()
  await expect(table.locator('tbody td').first()).toHaveText(/^\d{2,}\//)       // cột (1): số, ký hiệu văn bản
  // dòng của văn bản người xem được đọc thì mở được văn bản
  await table.locator('tbody tr.cursor-pointer').first().click()
  await expect(clerk).toHaveURL(/\/van-ban\/[0-9a-f-]{36}$/)
})
