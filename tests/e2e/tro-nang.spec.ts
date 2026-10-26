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

import AxeBuilder from '@axe-core/playwright'
import { mkdirSync, writeFileSync } from 'node:fs'
import { expect, test, type Locator, type Page } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, signIn } from './helpers'

// Trợ năng tự động (#246): axe-core quét cả trang theo WCAG 2.0, 2.1 mức A, AA và tiêu chí mới của 2.2 mức AA (#250,
// như cỡ vùng bấm 2.5.8). Mỗi vai trò đăng nhập một lần rồi quét nhiều trang (tài khoản có TOTP phải chờ khoảng mã
// mới). Lỗi chưa sửa nằm trong ALLOW, mỗi dòng có rule, trang, lý do và issue; danh sách chỉ ngắn đi: dòng nào không
// còn khớp lỗi nào ở trang đã quét thì test đỏ. Kết quả từng trang ở test-results/axe/ (CI giữ lại khi test hỏng).

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

interface Allowed { rule: string, page: string, reason: string, issue: number }
const ALLOW: Allowed[] = []

const scanned = new Set<string>()
const used = new Set<Allowed>()

// quét một trang đã mở; trả về các lỗi ngoài ALLOW, mỗi lỗi một dòng: trang, rule, mức, số chỗ, 3 chỗ đầu
async function scan(page: Page, name: string, ready?: Locator): Promise<string[]> {
  // axe đo màu đúng lúc quét: trang còn chạy hiệu ứng vào (sg-page-in, opacity từ 0) thì chữ nhạt hơn màu thật và
  // lỗi tương phản lúc có lúc không (#263). Bật giảm chuyển động như người dùng chọn trong hệ điều hành: CSS bỏ mọi
  // animation, trang ở ngay trạng thái cuối
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect(ready ?? page.getByRole('heading', { level: 1 }).first()).toBeVisible()
  await expect(page.getByText('Đang tải…')).toHaveCount(0)
  await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {})
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  scanned.add(name)
  mkdirSync('test-results/axe', { recursive: true })
  writeFileSync(`test-results/axe/${name.replace(/[^a-z0-9]+/gi, '_')}.json`, JSON.stringify(violations, null, 2))
  const left: string[] = []
  for (const v of violations) {
    const allow = ALLOW.find((a) => a.rule === v.id && a.page === name)
    if (allow) {
      used.add(allow)
      continue
    }
    const where = v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')
    left.push(`${name}: ${v.id} (${v.impact}, ${v.nodes.length} chỗ) ${v.help} — ${where}`)
  }
  return left
}

async function scanAll(page: Page, paths: string[]): Promise<string[]> {
  const left: string[] = []
  for (const path of paths) {
    await page.goto(path)
    left.push(...await scan(page, path))
  }
  return left
}

// Bảng tin (#250) là ứng dụng cắm bằng manifest: phần e2e của CI cài nó trước make seed (ci.yml) nên ở đó phải có;
// máy chưa cài thì /bang-tin/ ra trang của Văn phòng, bỏ phần này và ghi chú vào báo cáo, không im lặng. h1 có sẵn
// trong HTML tĩnh, nên chờ đăng nhập SSO xong và danh sách tin hay câu trạng thái hiện; câu trạng thái mà là lỗi tải
// thì không quét (giamkhao phải thấy tin của văn bản mẫu)
async function scanBoard(page: Page): Promise<string[]> {
  const installed = (await (await page.request.get('/bang-tin/')).text()).includes('id="tin"')
  if (!installed) {
    expect(process.env.CI, 'CI phải cài Bảng tin trước make e2e (ci.yml, bước make app-install)').toBeFalsy()
    test.info().annotations.push({ type: 'bỏ qua /bang-tin/',
      description: 'chưa cài Bảng tin: make app-install APP=apps/bang-tin/app.yaml' })
    return []
  }
  await page.goto('/bang-tin/')
  await expect(page.locator('#tin li, #trang-thai:not(:empty)').first()).toBeVisible()
  const status = await page.locator('#trang-thai').textContent()
  await expect(page.locator('#tin li').first(), `Bảng tin không có tin: ${status}`).toBeVisible({ timeout: 1_000 })
  return scan(page, '/bang-tin/', page.locator('#tin li').first())
}

test.afterAll(() => {
  const stale = ALLOW.filter((a) => scanned.has(a.page) && !used.has(a))
    .map((a) => `${a.page}: ${a.rule} (#${a.issue}) không còn lỗi, bỏ khỏi ALLOW`)
  expect(stale).toEqual([])
})

test('trợ năng: trang công khai (đăng nhập, xác thực văn bản, trạng thái hệ thống)', async ({ page }) => {
  await page.goto('/')
  const left = await scan(page, 'dang-nhap', page.locator('#username'))
  await page.goto('/xac-thuc')
  left.push(...await scan(page, '/xac-thuc'))
  await page.goto('/trang-thai')
  left.push(...await scan(page, '/trang-thai'))
  expect(left).toEqual([])
})

test('trợ năng: các trang của giám khảo (chuyên viên)', async ({ browser }) => {
  test.skip(!PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')
  test.setTimeout(300_000)
  const judge = await signIn(browser, 'giamkhao')
  const left = await scan(judge, '/')
  // văn bản có việc đang chờ: khung báo kết quả, luồng xử lý, tệp
  await judge.getByTestId('inbox').getByRole('listitem').filter({ hasText: '152/ĐT-ĐH' }).getByRole('link').click()
  await expect(judge).toHaveURL(/\/van-ban\/[0-9a-f-]{36}/)
  left.push(...await scan(judge, '/van-ban/[id]'))
  left.push(...await scanAll(judge, ['/van-ban-den', '/van-ban-di', '/van-ban-di/soan', '/ho-so', '/cam-bien',
    '/tim-kiem', '/hoi-dap', '/ung-dung', '/gop-y', '/ca-nhan/']))
  left.push(...await scanBoard(judge))
  expect(left).toEqual([])
})

test('trợ năng: các trang của lãnh đạo đơn vị và văn thư', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'Cần dữ liệu mẫu, MOC_DEMO_PASSWORD và MOC_DEMO_TOTP_SECRET')
  test.setTimeout(300_000)
  const director = await signIn(browser, 'truongkhoa', { otp: true })
  const left = await scanAll(director, ['/dieu-hanh', '/so-do', '/pha-he', '/tu-chan-doan', '/so-kiem-toan',
    '/so-dang-ky'])
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  left.push(...await scanAll(clerk, ['/van-ban-den/tiep-nhan']))
  expect(left).toEqual([])
})
