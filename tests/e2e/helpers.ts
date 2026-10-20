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

import { createHmac } from 'node:crypto'
import { expect, type Browser, type Page } from '@playwright/test'

// Dùng chung cho các kịch bản e2e: đăng nhập qua Keycloak (kèm TOTP), chụp màn hình.

export const PASSWORD = process.env.MOC_DEMO_PASSWORD ?? ''
export const TOTP_SECRET = process.env.MOC_DEMO_TOTP_SECRET ?? ''
const SHOTS = process.env.MOC_E2E_SCREENSHOTS ?? 'test-results/screens'

// Tệp PDF một trang có lớp chữ (Helvetica, chỉ ASCII) để tải lên: ClamAV quét như tệp thật, svc-files đọc được chữ
// để tìm theo nội dung (F2.7)
export function textPdf(...lines: string[]): Buffer {
  const esc = (line: string) => line.replace(/[\\()]/g, (c) => `\\${c}`)
  const stream = `BT /F1 12 Tf 72 760 Td 14 TL ${lines.map((l) => `(${esc(l)}) '`).join(' ')} ET`
  const objs = ['<</Type/Catalog/Pages 2 0 R>>', '<</Type/Pages/Kids[3 0 R]/Count 1>>',
    '<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>',
    '<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>', `<</Length ${stream.length}>>\nstream\n${stream}\nendstream`]
  let out = '%PDF-1.4\n'
  const offsets = objs.map((obj, i) => {
    const at = out.length
    out += `${i + 1} 0 obj\n${obj}\nendobj\n`
    return at
  })
  const xref = out.length
  out += `xref\n0 6\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('')}`
  return Buffer.from(`${out}trailer\n<</Size 6/Root 1 0 R>>\nstartxref\n${xref}\n%%EOF\n`, 'latin1')
}

// Mã TOTP (RFC 6238: HMAC-SHA1, 6 số, 30 giây) từ khóa chung mà make seed cài cho văn thư, lãnh đạo.
// Keycloak dùng chính chuỗi khóa làm khóa HMAC.
export function totp(secret: string, at = Date.now()): string {
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)))
  const mac = createHmac('sha1', secret).update(counter).digest()
  const offset = mac[mac.length - 1] & 0x0f
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, '0')
}

export async function signIn(browser: Browser, username: string, { otp = false } = {}): Promise<Page> {
  const page = await (await browser.newContext()).newPage()
  await page.goto('/')
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  if (otp) {
    // Xác thực hai bước bắt buộc với văn thư, lãnh đạo (luồng moc-browser của realm). Keycloak không nhận lại
    // một mã đã dùng: cùng tài khoản đăng nhập hai lần trong 30 giây thì đợi sang mã kế tiếp rồi thử lại.
    for (let attempt = 0; attempt < 2; attempt++) {
      await page.locator('#otp').fill(totp(TOTP_SECRET))
      await page.locator('#kc-login').click()
      // trang của Keycloak (kể cả trang báo mã sai) nằm dưới /realms/; vào được ứng dụng là rời khỏi đó
      const accepted = await page.waitForURL((url) => !url.pathname.startsWith('/realms/'), { timeout: 5_000 })
        .then(() => true, () => false)
      if (accepted) break
      await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500)
    }
  }
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  return page
}

export async function shot(page: Page, name: string) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true })
}
