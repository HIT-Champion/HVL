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
import { PASSWORD, signIn } from './helpers'

// Tài sản tĩnh của giao diện Liền mạch (#196) trên bản dựng thật (nuxt generate, nginx của app-office, theme signet
// của Keycloak): phông Be Vietnam Pro, logo, CSS, mã. Kịch bản khác chỉ nhìn chữ và nút nên không thấy phông hay ảnh
// hỏng. nginx trả index.html (200) cho tệp không có, vì thế kiểm phông tải được, ảnh giải mã được, kiểu nội dung, chứ
// không chỉ mã trạng thái. Không đổi dữ liệu.

const WEIGHTS = [400, 500, 600, 700]

// Lỗi CSP trên console (CSS hay mã nhận về index.html cũng ra "Refused to …" vì nosniff) và tài nguyên tĩnh cùng
// origin trả >= 400. Lỗi console khác (Keycloak có cảnh báo riêng) không tính
function watch(page: Page): string[] {
  const bad: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) bad.push(msg.text())
  })
  page.on('response', (res) => {
    const type = res.request().resourceType()
    const sameOrigin = new URL(res.url()).origin === new URL(page.url()).origin
    if (sameOrigin && ['stylesheet', 'script', 'font', 'image'].includes(type) && res.status() >= 400) {
      bad.push(`${res.status()} ${res.url()}`)
    }
  })
  return bad
}

// Độ đậm nào tải được tệp phông của nó. check() một mình trả true cả khi không có @font-face nào khớp
async function fontWeights(page: Page): Promise<number[]> {
  return page.evaluate(async (weights) => {
    await document.fonts.ready
    const ok: number[] = []
    for (const w of weights) {
      const font = `${w} 16px "Be Vietnam Pro"`
      const faces = await document.fonts.load(font).catch(() => [])
      if (faces.length > 0 && faces.every((f) => f.status === 'loaded') && document.fonts.check(font)) ok.push(w)
    }
    return ok
  }, WEIGHTS)
}

// Ảnh đã tải xong mà không giải mã được (404, hay index.html thay cho SVG)
async function brokenImages(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const done = [...document.images].filter((img) => img.complete && img.currentSrc)
    const res = await Promise.all(done.map((img) => img.decode().then(() => '', () => img.currentSrc)))
    return res.filter(Boolean)
  })
}

test('tài sản: phông, logo, CSS của trang đăng nhập và của ứng dụng tải được', async ({ browser }) => {
  test.skip(!PASSWORD, 'Cần dữ liệu mẫu và MOC_DEMO_PASSWORD')

  // Trang đăng nhập (theme signet): phông và logo nằm trong resources của theme, CSS gọi ../fonts/…, ../img/…
  const login = await (await browser.newContext()).newPage()
  const loginBad = watch(login)
  await login.goto('/')
  await expect(login.locator('#username')).toBeVisible()
  await login.waitForFunction(() => [...document.images].every((img) => img.complete))
  expect(await fontWeights(login)).toEqual(WEIGHTS)
  expect(await brokenImages(login)).toEqual([])
  expect(loginBad).toEqual([])

  // Ứng dụng: lần tải đầu nằm trong signIn, nên nghe rồi tải lại
  const page = await signIn(browser, 'giangvienktpm')
  const bad = watch(page)
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.waitForFunction(() => [...document.images].every((img) => img.complete))
  expect(await fontWeights(page)).toEqual(WEIGHTS)
  expect(await brokenImages(page)).toEqual([])
  expect(bad).toEqual([])

  for (const path of ['/favicon.svg', '/brand/signet-symbol.svg']) {
    const res = await page.request.get(path)
    expect(res.status(), path).toBe(200)
    expect(res.headers()['content-type'], path).toContain('image/svg+xml')
  }
})
