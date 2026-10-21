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

import { existsSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { expect, test } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Đọc văn bản đến (F4.1) trên giao diện: văn thư tải công văn mẫu 01 (PDF có lớp chữ) → ClamAV quét sạch → tác tử
// moc-doc-reader tự đọc, không cần bấm → ô Số ký hiệu, Ngày ban hành, Cơ quan ban hành điền sẵn đúng nhãn của mẫu,
// mang nhãn "Gợi ý" → văn thư sửa số ký hiệu, nhãn thành "Đã sửa" → lưu và vào sổ. Lãnh đạo khoa thấy lần đọc trong
// sổ kiểm toán: tác tử thực hiện, chỉ siêu dữ liệu, không có số ký hiệu hay trích yếu.
// Mẫu và nhãn đúng của mẫu ở seed/van-ban-den (scripts/van_ban_mau.py sinh, nhan.json); make e2e gắn thư mục đó vào
// container và đặt MOC_SAMPLES_DIR.

const SAMPLES = resolve(__dirname, process.env.MOC_SAMPLES_DIR ?? '../../seed/van-ban-den')
const SAMPLE = '01-cong-van.pdf'
const tag = Math.random().toString(36).slice(2, 7).toUpperCase()

interface Label { file: string; kind: 'text' | 'scan'; fields: Record<string, string> }

// So như phép đo của tác tử: số ký hiệu bỏ khoảng trắng, cơ quan ban hành gộp khoảng trắng, không phân biệt hoa thường
const normSymbol = (s: string) => s.normalize('NFC').replace(/\s+/g, '').toLocaleLowerCase('vi')
const normName = (s: string) => s.normalize('NFC').replace(/\s+/g, ' ').trim().toLocaleLowerCase('vi')

function labelOf(file: string): Record<string, string> {
  const path = join(SAMPLES, 'nhan.json')
  expect(existsSync(path), `không thấy ${path}: chạy từ gốc kho, hoặc đặt MOC_SAMPLES_DIR (make e2e gắn seed/van-ban-den)`).toBe(true)
  const { samples } = JSON.parse(readFileSync(path, 'utf8')) as { samples: Label[] }
  const fields = samples.find((s) => s.file === file)?.fields
  expect(fields, `nhan.json không có nhãn của ${file}`).toBeTruthy()
  return fields!
}

test('đọc văn bản đến: tác tử điền sẵn, văn thư sửa rồi vào sổ', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')
  const want = labelOf(SAMPLE)

  // 1. Văn thư tải công văn: quét sạch thì tự đọc (lớp chữ PDF), các ô có giá trị đúng nhãn của mẫu, nhãn "Gợi ý"
  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await clerk.getByRole('link', { name: 'Tiếp nhận văn bản' }).click()
  await clerk.locator('input[type=file]').setInputFiles(join(SAMPLES, SAMPLE))
  const row = clerk.getByRole('listitem').filter({ hasText: SAMPLE })
  await expect(row.getByText('Đã quét — sạch')).toBeVisible()
  await expect(row.getByText(/Đã đọc bằng lớp chữ PDF — điền sẵn \d+ ô/)).toBeVisible({ timeout: 60_000 })

  const symbol = clerk.getByLabel('Số, ký hiệu')
  const issuedOn = clerk.getByLabel('Ngày ban hành')
  const issuer = clerk.getByLabel('Cơ quan ban hành')
  await expect.poll(async () => normSymbol(await symbol.inputValue())).toBe(normSymbol(want.symbol!))
  await expect(issuedOn).toHaveValue(want.issued_on!)
  await expect.poll(async () => normName(await issuer.inputValue())).toBe(normName(want.issuer_name!))
  for (const key of ['symbol', 'issued_on', 'issuer_name']) {
    await expect(clerk.getByTestId(`suggest-${key}`)).toContainText('Gợi ý')
  }
  await expect(clerk.getByTestId('suggest-note')).toContainText('bấm lưu là văn thư xác nhận')
  await shot(clerk, '29-doc-van-ban-goi-y')

  // 2. Văn thư sửa số ký hiệu (thêm hậu tố để không trùng lần chạy trước): nhãn thành "Đã sửa"; đọc lại không đè
  await symbol.fill(`${want.symbol}-${tag}`)
  await symbol.blur()
  await expect(clerk.getByTestId('suggest-symbol')).toContainText('Đã sửa')
  await row.getByRole('button', { name: /^Đọc lại/ }).click()
  await expect(row.getByText(/Đã đọc bằng lớp chữ PDF/)).toBeVisible({ timeout: 60_000 })
  await expect(symbol).toHaveValue(`${want.symbol}-${tag}`)
  await expect(clerk.getByTestId('suggest-symbol')).toContainText('Đã sửa')
  await expect(clerk.getByRole('alert').filter({ hasText: 'có thể đã được tiếp nhận' })).toHaveCount(0)
  await shot(clerk, '30-doc-van-ban-da-sua')

  // 3. Lưu và vào sổ như mọi văn bản đến
  await clerk.getByRole('button', { name: 'Lưu và vào sổ' }).click()
  await expect(clerk.getByText(/Đã vào sổ — số đến \d+/)).toBeVisible()
  await expect(clerk.getByText('Chờ chỉ đạo').first()).toBeVisible()
  await shot(clerk, '31-doc-van-ban-da-vao-so')

  // 4. Sổ kiểm toán: lần đọc do tác tử thực hiện, chỉ có siêu dữ liệu — không có số ký hiệu, cơ quan, trích yếu
  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Sổ kiểm toán' }).click()
  await director.getByRole('tab', { name: 'Tệp' }).click()
  const entry = director.getByTestId('audit-table').locator('tr', { hasText: 'Đọc văn bản, gợi ý thông tin tiếp nhận' }).first()
  await expect(entry).toContainText('(tác tử)')
  await expect(entry).toContainText('Cách đọc: lớp chữ PDF')
  await expect(entry).toContainText('Trường đọc được:')
  for (const key of ['symbol', 'issuer_name', 'summary']) {
    if (want[key]) await expect(entry).not.toContainText(want[key]!)
  }
  await shot(director, '32-doc-van-ban-so-kiem-toan')
})
