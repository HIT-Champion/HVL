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
import { PASSWORD, TOTP_SECRET, signIn } from './helpers'

// Màn hẹp và quyền trên giao diện (#230): mở trang ở 1440px, thu xuống 768 rồi 390 (như người dùng thu cửa sổ,
// biểu đồ vẽ ở khổ rộng phải tự co lại) mà trang không cuộn ngang; nút ở tiêu đề trang nằm trong khung; quản trị
// đơn vị gõ thẳng địa chỉ trang văn bản thì về sổ kiểm toán, không gửi câu hỏi văn bản nào.

// Trang hay vùng nội dung rộng hơn khung thì trả về mô tả (các phần tử sâu nhất lố ra ngoài, không kể phần nằm trong
// vùng cuộn ngang riêng), không thì chuỗi rỗng. Đo cả #main-content để overflow ẩn ở đó không che được lỗi
function overflow() {
  const root = document.documentElement
  const main = document.getElementById('main-content')
  if (root.scrollWidth <= root.clientWidth && (!main || main.scrollWidth <= main.clientWidth)) return ''
  const limit = (main ?? root).getBoundingClientRect().right
  const scrolls = (el: Element) => {
    for (let p = el.parentElement; p && p !== main; p = p.parentElement) {
      if (getComputedStyle(p).overflowX !== 'visible') return true
    }
    return false
  }
  const wide = [...(main ?? document.body).querySelectorAll('*')]
    .filter((el) => el.getBoundingClientRect().right > limit + 1 && !scrolls(el))
  const leaves = wide.filter((el) => !wide.some((other) => other !== el && el.contains(other))).slice(0, 4)
  return `trang ${root.scrollWidth}/${root.clientWidth}px, main ${main?.scrollWidth}/${main?.clientWidth}px; lố: `
    + leaves.map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].slice(0, 3).join('.')} tới `
      + `${Math.round(el.getBoundingClientRect().right)}px`).join(', ')
}

// Nút, liên kết ở tiêu đề trang (PageHeader) lố khỏi khung tiêu đề hay chữ bị cắt: trả về nhãn của chúng
function headerSpill() {
  const header = document.querySelector('.moc-page-header')
  if (!header) return 'không có .moc-page-header'
  const box = header.getBoundingClientRect()
  return [...header.querySelectorAll('a, button')].filter((el) => {
    const r = el.getBoundingClientRect()
    return r.right > box.right + 1 || r.left < box.left - 1 || el.scrollWidth > el.clientWidth + 1
  }).map((el) => el.textContent?.trim()).join(', ')
}

async function shrink(page: Page, where: string, { header = false } = {}) {
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect.poll(() => page.evaluate(overflow), { message: `${where} cuộn ngang ở ${width}px` }).toBe('')
    if (header) {
      await expect.poll(() => page.evaluate(headerSpill), { message: `${where}: nút tiêu đề lố ở ${width}px` }).toBe('')
    }
  }
}

test('màn hẹp: trang lãnh đạo thu từ 1440 xuống 768, 390 không cuộn ngang', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'Cần dữ liệu mẫu, MOC_DEMO_PASSWORD và MOC_DEMO_TOTP_SECRET')
  const director = await signIn(browser, 'truongkhoa', { otp: true })

  await director.setViewportSize({ width: 1440, height: 900 })
  await director.goto('/dieu-hanh')
  await expect(director.locator('[role="img"] svg').first()).toBeVisible()
  await shrink(director, '/dieu-hanh')

  await director.setViewportSize({ width: 1440, height: 900 })
  await director.goto('/pha-he')
  await expect(director.getByTestId('lineage-graph').locator('svg').first()).toBeVisible()
  await expect(director.locator('[data-status]').first()).toBeVisible()
  await shrink(director, '/pha-he')

  // văn bản đã xử lý: nhiều mục nhất (luồng xử lý, lịch sử, tệp)
  await director.setViewportSize({ width: 1440, height: 900 })
  await director.goto('/van-ban-den?tab=done')
  await director.locator('tbody tr a').first().click()
  await expect(director).toHaveURL(/\/van-ban\/[0-9a-f-]{36}/)
  await expect(director.locator('main h2').first()).toBeVisible()
  await shrink(director, 'văn bản đã xử lý')
})

test('màn hẹp: nút ở tiêu đề hồ sơ, cảm biến nằm trong khung ở 768, 390', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần dữ liệu mẫu và MOC_DEMO_PASSWORD')
  const staff = await signIn(browser, 'chuyenviendt')
  for (const [path, button] of [['/ho-so', 'case-file-new'], ['/cam-bien', null]] as const) {
    await staff.setViewportSize({ width: 1440, height: 900 })
    await staff.goto(path)
    const header = staff.locator('.moc-page-header')
    await expect(button ? header.getByTestId(button) : header.getByRole('button').first()).toBeVisible()
    await shrink(staff, path, { header: true })
  }
})

test('quản trị đơn vị gõ địa chỉ trang văn bản: về sổ kiểm toán, không hỏi văn bản', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'Cần dữ liệu mẫu, MOC_DEMO_PASSWORD và MOC_DEMO_TOTP_SECRET')
  const admin = await signIn(browser, 'quantri', { otp: true })
  const asked: string[] = []
  admin.on('request', (req) => {
    if (!req.url().includes('/v1/graphql')) return
    const query = String(req.postDataJSON()?.query ?? '')
    if (/\boffice_(documents|case_files)\b/.test(query)) asked.push(`${admin.url()}: ${query.slice(0, 80)}`)
  })
  for (const path of ['/van-ban-den', '/van-ban-den/tiep-nhan', '/van-ban-di', '/van-ban-di/soan',
    '/van-ban/00000000-0000-4000-8000-000000000000', '/ho-so', '/so-dang-ky']) {
    await admin.goto(path)
    await expect(admin, path).toHaveURL(/\/so-kiem-toan$/)
    await expect(admin.getByRole('heading', { level: 1, name: 'Sổ kiểm toán' })).toBeVisible()
  }
  expect(asked).toEqual([])
})
