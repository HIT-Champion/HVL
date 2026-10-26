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

// Bảng dịch vi/en của Bảng tin đơn vị và ngôn ngữ đang dùng (#306). Mọi chữ trên giao diện lấy từ đây: mã gọi
// t('khóa'), phần tĩnh của index.html mang data-i18n (tests/i18n.test.js kiểm cả hai). Ngôn ngữ chọn lưu ở
// localStorage khóa `moc.locale`, chung với Văn phòng điện tử (apps/office/app/plugins/i18n.ts) và Không gian cá nhân:
// cùng tên miền nên đổi ở ứng dụng nào thì ứng dụng kia mở ra cũng theo. Ứng dụng cắm thêm dựng image từ thư mục của
// mình nên giữ bảng và phần dưới đây riêng (cùng cách làm với apps/ca-nhan/public/i18n.js). Không đụng DOM khi nạp nên
// chạy được dưới node --test.

export const STORAGE_KEY = 'moc.locale'

export const MESSAGES = Object.freeze({
  vi: Object.freeze({
    'page.title': 'Bảng tin đơn vị — Signet',
    'page.heading': 'Bảng tin đơn vị',
    'page.intro': 'Văn bản vừa vào sổ, vừa phát hành trong đơn vị. Tin đến theo sự kiện của lõi Signet; chỉ hiện văn '
      + 'bản bạn được xem.',
    'nav.office': 'Văn phòng điện tử',
    'nav.logout': 'Đăng xuất',
    // nút đổi ngôn ngữ ghi tên ngôn ngữ kia bằng chính tiếng đó; lang.other là thuộc tính lang của nút
    'lang.switch': 'English',
    'lang.other': 'en',
    'status.signingIn': 'Đang đăng nhập…',
    'status.signedIn': 'Đã đăng nhập',
    'status.empty': 'Chưa có tin nào.',
    'status.adminNoBoard': 'Tài khoản quản trị đơn vị không xem được bảng tin: bảng tin chỉ hiện văn bản người xem '
      + 'được đọc. Đăng nhập bằng tài khoản nghiệp vụ.',
    'status.loadFailed': 'Không tải được bảng tin: {error}',
    'error.noAccess': 'Tài khoản này không đọc được bảng tin. Kiểm tra vai trò của tài khoản hoặc hỏi quản trị đơn '
      + 'vị.',
    'kind.registered': 'Văn bản đến đã vào sổ',
    'kind.issued': 'Văn bản đi đã phát hành',
    'news.noSymbol': '(chưa có số)',
  }),
  en: Object.freeze({
    'page.title': 'Unit news board — Signet',
    'page.heading': 'Unit news board',
    'page.intro': 'Documents just registered or issued in your unit. News arrives with events from the Signet core; '
      + 'only documents you may view are shown.',
    'nav.office': 'e-Office',
    'nav.logout': 'Sign out',
    'lang.switch': 'Tiếng Việt',
    'lang.other': 'vi',
    'status.signingIn': 'Signing in…',
    'status.signedIn': 'Signed in',
    'status.empty': 'No news yet.',
    'status.adminNoBoard': 'Unit administrator accounts cannot see the news board: it only shows documents the '
      + 'viewer may read. Sign in with a staff account.',
    'status.loadFailed': 'Could not load the news board: {error}',
    'error.noAccess': "This account cannot read the news board. Check the account's role or ask your unit "
      + 'administrator.',
    'kind.registered': 'Incoming document registered',
    'kind.issued': 'Outgoing document issued',
    'news.noSymbol': '(no number yet)',
  }),
})

let current = 'vi'

/** 'en' khi đã chọn tiếng Anh, còn lại tiếng Việt: mặc định như Văn phòng điện tử. */
export function pickLocale(value) {
  return value === 'en' ? 'en' : 'vi'
}

export function locale() {
  return current
}

export function setLocale(value) {
  current = pickLocale(value)
  return current
}

const lookup = (table, key) => (Object.hasOwn(table, key) ? table[key] : undefined)

/** Câu theo khóa, {tên} thay bằng tham số cùng tên. Thiếu bản tiếng Anh thì lấy tiếng Việt, thiếu cả hai thì trả
 *  khóa (test bắt trường hợp này trước khi tới trình duyệt). */
export function t(key, params = {}) {
  const text = lookup(MESSAGES[current], key) ?? lookup(MESSAGES.vi, key) ?? key
  return text.replace(/\{(\w+)\}/g, (all, name) => (Object.hasOwn(params, name) ? String(params[name]) : all))
}

/** Ngôn ngữ đã lưu. storage() trả localStorage; trình duyệt chặn bộ nhớ cục bộ thì dùng tiếng Việt. */
export function savedLocale(storage = () => globalThis.localStorage) {
  try {
    return pickLocale(storage().getItem(STORAGE_KEY))
  } catch {
    return 'vi'
  }
}

export function saveLocale(value, storage = () => globalThis.localStorage) {
  try {
    storage().setItem(STORAGE_KEY, value)
  } catch {
    // trình duyệt chặn bộ nhớ cục bộ: chỉ đổi ở trang đang mở
  }
}

/** Gán câu cho phần tĩnh của trang theo ngôn ngữ đang dùng và đặt <html lang>. data-i18n="khóa" là chữ của phần
 *  tử (phần tử chỉ chứa chữ), data-i18n-<thuộc tính>="khóa" là thuộc tính đó, vd data-i18n-aria-label. */
export function localize(doc) {
  doc.documentElement.lang = current
  for (const node of doc.querySelectorAll('*')) {
    for (const { name, value } of [...node.attributes]) {
      if (name === 'data-i18n') node.textContent = t(value)
      else if (name.startsWith('data-i18n-')) node.setAttribute(name.slice('data-i18n-'.length), t(value))
    }
  }
}
