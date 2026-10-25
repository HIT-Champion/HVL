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

import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { PASSWORD, shot, signIn, textPdf } from './helpers'

// Ứng dụng thứ hai trên lõi (docs/them-ung-dung.md): Không gian cá nhân P.A.R.A ở /ca-nhan/, client Keycloak riêng
// app-ca-nhan. Đã đăng nhập Văn phòng điện tử thì vào thẳng, không nhập lại mật khẩu (SSO); tải tệp lên thư mục Dự án
// qua svc-files của lõi (ClamAV quét), chuyển sang Lưu trữ, tải về đúng tệp.

test('không gian cá nhân: SSO từ Văn phòng điện tử, tải lên, chuyển thư mục, tải về', async ({ browser }) => {
  test.skip(!PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')

  const page = await signIn(browser, 'giangvienktpm')
  await page.goto('/ca-nhan/')
  const folders = page.getByRole('navigation', { name: 'Thư mục P.A.R.A' })
  await expect(folders.getByRole('link')).toHaveText([/Dự án/, /Lĩnh vực/, /Tài nguyên/, /Lưu trữ/])
  await expect(page).toHaveURL(/\/ca-nhan\/$/)                 // không dừng ở trang đăng nhập Keycloak
  await expect(page.locator('#who')).toHaveText('Vũ Thị Mai')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Dự án')

  const tag = Date.now().toString(36).toUpperCase()
  const name = `de-cuong-${tag}.pdf`
  const content = textPdf('De cuong hoc phan', `Ma thu ${tag}`)
  await page.locator('#file').setInputFiles({ name, mimeType: 'application/pdf', buffer: content })
  await expect(page.getByText(`Đã tải ${name} lên, trạm quét báo sạch, đã xếp vào Dự án.`)).toBeVisible()
  await expect(page.getByRole('row', { name: new RegExp(name) })).toBeVisible()

  await page.getByRole('combobox', { name: `Chuyển ${name} sang thư mục` }).selectOption('archives')
  await expect(page.getByText(`Đã chuyển ${name} sang Lưu trữ.`)).toBeVisible()
  await expect(page.getByRole('row', { name: new RegExp(name) })).toHaveCount(0)

  await folders.getByRole('link', { name: /Lưu trữ/ }).click()
  await expect(page).toHaveURL(/#archives$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Lưu trữ')
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: `Tải về ${name}` }).click(),
  ])
  expect(download.suggestedFilename()).toBe(name)
  expect(readFileSync(await download.path()).equals(content)).toBe(true)
  await shot(page, '35-ca-nhan-luu-tru')
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
    await expect(page.getByRole('combobox', { name: `Chuyển ${name} sang thư mục` })).toBeVisible()
    await shot(page, `35-ca-nhan-${width}`)
  }
})
