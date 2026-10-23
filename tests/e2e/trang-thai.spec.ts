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
import { shot } from './helpers'

// Trạng thái hệ thống (trang công khai): người ngoài không đăng nhập mở /trang-thai, không bị chuyển sang Keycloak,
// thấy tình trạng chung và từng thành phần theo tầng người dùng → lõi → quy trình → dữ liệu → trí tuệ nhân tạo; từ
// chân trang của cổng xác thực đi được tới trang. Không đòi mọi thành phần "Hoạt động" ở đây (ca thêm của CI kiểm qua
// API).

const LAYERS = ['nguoi-dung', 'loi', 'quy-trinh', 'du-lieu', 'tri-tue']
const COMPONENTS = ['cong-api', 'dang-nhap', 'csdl', 'ket-khoa', 'quet-ma-doc', 'quy-trinh', 'luu-tru', 'tim-kiem',
  'tro-ly-ai']

test('trạng thái hệ thống: không cần đăng nhập, đủ thành phần theo tầng', async ({ browser }) => {
  const outsider = await (await browser.newContext()).newPage()
  await outsider.goto('/trang-thai')
  await expect(outsider.getByRole('heading', { level: 1, name: 'Trạng thái hệ thống' })).toBeVisible()
  await expect(outsider).toHaveURL(/\/trang-thai$/)

  const overall = outsider.getByTestId('status-overall')
  await expect(overall).toHaveAttribute('data-status', /^(ok|degraded|down)$/)
  await expect(overall).toContainText(/Kiểm lúc \d{2}:\d{2}:\d{2}/)
  for (const id of LAYERS) await expect(outsider.getByTestId(`status-layer-${id}`)).toBeVisible()
  for (const id of COMPONENTS) {
    await expect(outsider.getByTestId(`status-component-${id}`))
      .toHaveAttribute('data-status', /^(ok|degraded|down|off)$/)
  }
  await expect(outsider.getByTestId('status-component-dang-nhap')).toContainText('Đăng nhập một lần')
  await expect(outsider.getByTestId('status-component-dang-nhap')).toContainText('Keycloak')
  await expect(outsider.getByTestId('status-version')).not.toBeEmpty()
  await expect(outsider.getByTestId('status-ai')).toContainText(/Bật|Tắt/)
  await shot(outsider, '36-trang-thai')

  // từ chân trang của cổng xác thực văn bản (cũng là trang công khai)
  await outsider.goto('/xac-thuc')
  await outsider.getByRole('link', { name: 'Trạng thái hệ thống' }).click()
  await expect(outsider.getByRole('heading', { level: 1, name: 'Trạng thái hệ thống' })).toBeVisible()
})
