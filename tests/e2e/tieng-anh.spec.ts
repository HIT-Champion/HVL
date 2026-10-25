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
import { PASSWORD, shot, signIn } from './helpers'

// Giao diện tiếng Anh (F2.9) trên trình duyệt thật: chuyên viên vào ứng dụng bằng tiếng Việt (mặc định), bấm nút
// "English" ở thanh trên → menu, hộp việc, chuông thông báo, danh sách văn bản đến đổi sang tiếng Anh; soạn dự thảo hết
// bằng tiếng Anh: form trống bị chặn với lời báo tiếng Anh, lưu được, trang văn bản và danh sách văn bản đi hiện nhãn,
// trạng thái tiếng Anh; tải lại trang vẫn giữ (moc.locale trong localStorage); bấm "Tiếng Việt" thì về lại. Chữ so
// khớp lấy nguyên văn từ apps/office/app/locales/en.json. Trang công khai (trạng thái hệ thống, xác thực văn bản):
// người ngoài dùng trình duyệt tiếng Anh vẫn mở ra tiếng Việt, đổi bằng nút, không cần đăng nhập. PDF phát hành, sổ
// in vẫn theo thể thức tiếng Việt, không kiểm ở đây.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()
const summary = `Invitation to the joint seminar with partner universities in November (test ${tag})`

const savedLocale = (page: Page) => page.evaluate(() => localStorage.getItem('moc.locale'))

test('giao diện tiếng Anh: đổi ngôn ngữ, danh sách, soạn dự thảo, giữ sau khi tải lại', async ({ browser }) => {
  test.skip(!PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')

  // 1. Mặc định tiếng Việt dù chưa chọn gì
  const staff = await signIn(browser, 'chuyenviendt')
  const html = staff.locator('html')
  await expect(staff.getByRole('heading', { level: 1, name: 'Hộp việc' })).toBeVisible()
  await expect(html).toHaveAttribute('lang', 'vi')

  // 2. Nút đổi ngôn ngữ ở thanh trên: menu, tiêu đề, vai trò, nút đăng xuất sang tiếng Anh; chữ tiếng Việt không còn
  await staff.getByRole('button', { name: 'English', exact: true }).click()
  await expect(html).toHaveAttribute('lang', 'en')
  await expect(staff.getByRole('heading', { level: 1, name: 'My tasks' })).toBeVisible()
  await expect(staff.getByText('Tasks waiting for you — urgent first')).toBeVisible()
  for (const name of ['My tasks', 'Incoming documents', 'Outgoing', 'Draft a document', 'Search', 'Ask']) {
    await expect(staff.getByRole('link', { name, exact: true })).toBeVisible()
  }
  await expect(staff.getByRole('link', { name: 'Hộp việc' })).toHaveCount(0)
  // tên, vai trò nằm ở cuối thanh bên (#116), chỉ hiện khi thanh bên mở: rê chuột vào rồi giữ đó tới khi bấm chuông
  await staff.locator('#app-navigation').hover()
  await expect(staff.getByText('Officer', { exact: true })).toBeVisible()
  await expect(staff.getByRole('button', { name: 'Sign out' })).toBeVisible()
  await expect(staff.getByRole('button', { name: 'Tiếng Việt', exact: true })).toBeVisible()
  await expect.poll(() => savedLocale(staff)).toBe('en')

  // chuông thông báo: tên cho trình đọc màn hình và khung tin cũng tiếng Anh (đã nối kênh trực tiếp hay chưa)
  const bell = staff.getByRole('button', { name: 'Notifications', exact: true })
  await bell.click()
  await expect(staff.getByText('Notifications', { exact: true })).toBeVisible()
  await expect(staff.getByText('Receiving live notifications')
    .or(staff.getByText('Live channel not connected — existing notifications are still shown, reconnecting')))
    .toBeVisible()
  await shot(staff, '42-tieng-anh-hop-viec')
  await bell.click()

  // 3. Danh sách văn bản đến (văn bản mẫu của make seed): tiêu đề, tab, cột, trạng thái tiếng Anh
  await staff.getByRole('link', { name: 'Incoming documents', exact: true }).click()
  await expect(staff.getByRole('heading', { level: 1, name: 'Incoming documents' })).toBeVisible()
  for (const name of ['To register', 'In progress', 'Done', 'All']) {
    await expect(staff.getByRole('tab', { name, exact: true })).toBeVisible()
  }
  for (const name of ['No.', 'Reference', 'Summary', 'Status', 'Due']) {
    await expect(staff.getByRole('columnheader', { name, exact: true })).toBeVisible()
  }
  // dòng nào cũng được (văn bản mẫu ở đủ các bước): ô trạng thái là một trong các nhãn status.* tiếng Anh
  const statuses = ['Awaiting registration', 'Awaiting direction', 'In progress', 'Done', 'Archived', 'Cancelled']
  await expect(staff.getByRole('cell', { name: new RegExp(`^(${statuses.join('|')})$`) }).first()).toBeVisible()

  // 4. Soạn dự thảo bằng tiếng Anh. Form trống bị chặn ngay trên trình duyệt, lời báo tiếng Anh, chưa gửi gì đi
  await staff.getByRole('link', { name: 'Draft a document', exact: true }).click()
  await expect(staff.getByRole('heading', { level: 1, name: 'Draft an outgoing document' })).toBeVisible()
  const sent: string[] = []
  staff.on('request', (r) => { if (r.postData()?.includes('insert_office_documents_one')) sent.push(r.url()) })
  await staff.getByRole('button', { name: 'Save draft' }).click()
  await expect(staff.getByText('Required', { exact: true })).toHaveCount(2)
  await expect(staff.getByLabel('Subject', { exact: true })).toHaveAttribute('aria-invalid', 'true')
  expect(sent).toEqual([])

  await expect(staff.getByLabel('Document type', { exact: true })).toBeVisible()
  await staff.getByLabel('Urgency', { exact: true }).selectOption({ label: 'Urgent' })
  await staff.getByLabel('Subject', { exact: true }).fill(summary)
  await staff.getByLabel('Body', { exact: true }).fill(
    'The Faculty of Information Technology invites partner universities to a joint seminar in November.')
  await staff.getByLabel('Recipients', { exact: true }).fill('International Cooperation Office')
  await staff.getByRole('button', { name: 'Save draft' }).click()
  await expect(staff.getByText('Draft saved.')).toBeVisible()

  // trang văn bản vừa lưu: trạng thái, độ khẩn, các mục, nút trình ký, dòng thời gian, lịch sử đều tiếng Anh
  await expect(staff.getByRole('heading', { level: 1, name: summary })).toBeVisible()
  await expect(staff.getByText('Draft', { exact: true })).toBeVisible()
  await expect(staff.getByText('Urgent', { exact: true }).first()).toBeVisible()
  for (const name of ['Submit draft', 'Body', 'Document details', 'Files']) {
    await expect(staff.getByRole('heading', { level: 2, name, exact: true })).toBeVisible()
  }
  await expect(staff.getByLabel('Signing director')).toBeVisible()
  await expect(staff.getByRole('button', { name: 'Submit for signing' })).toBeVisible()
  await expect(staff.getByRole('button', { name: 'Download preview (PDF)' })).toBeVisible()
  await expect(staff.getByTestId('timeline').getByText('Draft created', { exact: true })).toBeVisible()
  await staff.getByRole('tab', { name: 'History', exact: true }).click()
  await expect(staff.getByTestId('history').getByText('Created · Document', { exact: true })).toBeVisible()
  await shot(staff, '43-tieng-anh-du-thao')

  // 5. Danh sách văn bản đi: dòng của dự thảo vừa lưu mang nhãn tiếng Anh; lọc theo tab "Drafts"
  await staff.getByRole('link', { name: 'Outgoing', exact: true }).click()
  await expect(staff.getByRole('heading', { level: 1, name: 'Outgoing documents' })).toBeVisible()
  for (const name of ['Number', 'Subject', 'Status', 'Issued on']) {
    await expect(staff.getByRole('columnheader', { name, exact: true })).toBeVisible()
  }
  await staff.getByRole('tab', { name: 'Drafts', exact: true }).click()
  await expect(staff.getByRole('tab', { name: 'Drafts', exact: true })).toHaveAttribute('aria-selected', 'true')
  const row = staff.getByRole('row').filter({ hasText: tag })
  await expect(row.getByText('Not numbered', { exact: true })).toBeVisible()
  await expect(row.getByText('Draft', { exact: true })).toBeVisible()
  await expect(row.getByText('Urgent', { exact: true })).toBeVisible()

  // 6. Tải lại trang: ứng dụng đọc lại moc.locale, vẫn tiếng Anh
  await staff.reload()
  await expect(staff.getByRole('heading', { level: 1, name: 'Outgoing documents' })).toBeVisible()
  await expect(staff.getByRole('tab', { name: 'Drafts', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(row.getByText('Draft', { exact: true })).toBeVisible()
  await expect(staff.getByRole('link', { name: 'My tasks', exact: true })).toBeVisible()
  expect(await savedLocale(staff)).toBe('en')
  await shot(staff, '44-tieng-anh-tai-lai')

  // 7. Về lại tiếng Việt: cùng dòng đó hiện trạng thái tiếng Việt
  await staff.getByRole('button', { name: 'Tiếng Việt', exact: true }).click()
  await expect(html).toHaveAttribute('lang', 'vi')
  await expect(staff.getByRole('heading', { level: 1, name: 'Văn bản đi' })).toBeVisible()
  await expect(row.getByText('Dự thảo', { exact: true })).toBeVisible()
  await expect(staff.getByRole('link', { name: 'Hộp việc', exact: true })).toBeVisible()
  await expect(staff.getByRole('link', { name: 'My tasks' })).toHaveCount(0)
  await expect.poll(() => savedLocale(staff)).toBe('vi')
})

test('trang công khai đổi sang tiếng Anh không cần đăng nhập', async ({ browser }) => {
  // trình duyệt tiếng Anh: ứng dụng không theo ngôn ngữ trình duyệt, vẫn mở ra tiếng Việt cho tới khi bấm nút
  const outsider = await (await browser.newContext({ locale: 'en-GB' })).newPage()
  await outsider.goto('/trang-thai')
  await expect(outsider.getByRole('heading', { level: 1, name: 'Trạng thái hệ thống' })).toBeVisible()
  await expect(outsider.locator('html')).toHaveAttribute('lang', 'vi')

  await outsider.getByRole('button', { name: 'English', exact: true }).click()
  await expect(outsider.locator('html')).toHaveAttribute('lang', 'en')
  await expect(outsider.getByRole('heading', { level: 1, name: 'System status' })).toBeVisible()
  await expect(outsider.getByTestId('status-component-dang-nhap')).toContainText('Single sign-on')
  await expect(outsider.getByTestId('status-overall')).toContainText('Checked at')

  // chân trang sang cổng xác thực văn bản; tải lại vẫn tiếng Anh
  await outsider.getByRole('link', { name: 'Verify a document', exact: true }).click()
  await expect(outsider.getByRole('heading', { level: 1, name: 'Verify a document' })).toBeVisible()
  await outsider.reload()
  await expect(outsider.getByRole('heading', { level: 1, name: 'Verify a document' })).toBeVisible()
  expect(await savedLocale(outsider)).toBe('en')

  await outsider.getByRole('button', { name: 'Tiếng Việt', exact: true }).click()
  await expect(outsider.getByRole('heading', { level: 1, name: 'Xác thực văn bản' })).toBeVisible()
  await expect(outsider.locator('html')).toHaveAttribute('lang', 'vi')
})
