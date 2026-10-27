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

// Bảng dịch vi/en của Không gian cá nhân và ngôn ngữ đang dùng (#306). Mọi chữ trên giao diện lấy từ đây: mã gọi
// t('khóa'), phần tĩnh của index.html mang data-i18n (tests/i18n.test.js kiểm cả hai). Ngôn ngữ chọn lưu ở
// localStorage khóa `moc.locale`, chung với Văn phòng điện tử (apps/office/app/plugins/i18n.ts): cùng tên miền nên đổi
// ở ứng dụng nào thì ứng dụng kia mở ra cũng theo. Mỗi ứng dụng giữ bảng của mình vì image dựng riêng từ thư mục ứng
// dụng. Không đụng DOM khi nạp nên chạy được dưới node --test.

export const STORAGE_KEY = 'moc.locale'

export const MESSAGES = Object.freeze({
  vi: Object.freeze({
    'page.title': 'Signet — Không gian cá nhân',
    'page.description': 'Signet — lưu trữ cá nhân theo P.A.R.A: Dự án, Lĩnh vực, Tài nguyên, Lưu trữ',
    'page.brand': 'Không gian cá nhân',
    'page.footer': 'Tệp tải lên được trạm quét mã độc của lõi kiểm trước khi lưu; mỗi lần xếp, chuyển tệp vào sổ kiểm '
      + 'toán chuỗi băm của đơn vị. Ứng dụng này không tự làm các việc đó — lõi Signet làm, cho mọi ứng dụng cắm vào '
      + 'nó.',
    'nav.apps': 'Ứng dụng',
    'nav.office': 'Văn phòng điện tử',
    'nav.logout': 'Đăng xuất',
    'nav.folders': 'Thư mục P.A.R.A',
    // nút đổi ngôn ngữ ghi tên ngôn ngữ kia bằng chính tiếng đó; lang.other là thuộc tính lang của nút
    'lang.switch': 'English',
    'lang.other': 'en',
    'status.signingIn': 'Đang đăng nhập…',
    'status.signInFailed': 'Đăng nhập không được: {error}. Tải lại trang để thử lại.',
    'status.adminNoSpace': 'Tài khoản quản trị đơn vị không có không gian cá nhân: lõi không cho vai trò này đọc tệp. '
      + 'Đăng nhập bằng tài khoản nghiệp vụ.',
    'folder.projects.name': 'Dự án',
    'folder.projects.hint': 'Việc đang làm, có đích và có hạn: hồ sơ một đề tài, kế hoạch một sự kiện.',
    'folder.areas.name': 'Lĩnh vực',
    'folder.areas.hint': 'Phần việc giữ lâu dài, không có ngày xong: giảng dạy, công tác đoàn thể.',
    'folder.resources.name': 'Tài nguyên',
    'folder.resources.hint': 'Tài liệu tham khảo, chủ đề quan tâm, mở ra khi cần.',
    'folder.archives.name': 'Lưu trữ',
    'folder.archives.hint': 'Đã xong hoặc tạm gác: chuyển từ ba thư mục trên sang đây.',
    'folder.empty': 'Thư mục trống. Tải tệp lên, hoặc chuyển tệp từ thư mục khác sang.',
    'column.name': 'Tên tệp',
    'column.size': 'Dung lượng',
    'column.scanned': 'Quét sạch lúc',
    'column.actions': 'Thao tác',
    'item.download': 'Tải về',
    'item.downloadLabel': 'Tải về {name}',
    'item.moveLabel': 'Chuyển {name} sang thư mục',
    'item.movePlaceholder': 'Chuyển sang…',
    'upload.button': 'Tải tệp lên',
    'upload.into': 'Tải tệp lên vào {folder}',
    'upload.progress': 'Đang tải {name} lên và quét mã độc…',
    'upload.done': 'Đã tải {name} lên, trạm quét báo sạch, đã xếp vào {folder}.',
    'upload.notPlaced': 'Tệp {name} đã lưu nhưng chưa xếp được vào {folder}: {error}',
    'upload.retry': 'Thử xếp lại',
    'upload.infected': 'Tệp chứa mã độc nên trạm quét đã chặn, không lưu.',
    'upload.infectedSignature': 'Tệp chứa mã độc nên trạm quét đã chặn, không lưu (mẫu {signature}).',
    'upload.unscannable': 'Tệp có mật khẩu hoặc nén nhiều lớp nên trạm quét không kiểm được bên trong — đã chặn. Bỏ '
      + 'mật khẩu hoặc giải nén rồi tải lên lại.',
    'upload.tooLarge': 'Tệp quá lớn.',
    'upload.typeRejected': 'Loại tệp này không được nhận nên chưa lưu.',
    'upload.empty': 'Tệp rỗng.',
    'upload.noTenant': 'Tài khoản chưa được gắn đơn vị nên chưa lưu được tệp. Báo quản trị đơn vị.',
    'upload.unavailable': 'Kho tệp hoặc trạm quét mã độc chưa sẵn sàng, tệp chưa được lưu. Thử lại sau.',
    'upload.failed': 'Tải lên không được (mã {status}).',
    'move.done': 'Đã chuyển {name} sang {folder}.',
    'download.notFound': 'Không tải được {name}: tệp không còn hoặc bạn không còn quyền xem.',
    'error.noSpaceRole': 'Vai trò của tài khoản này không có không gian cá nhân.',
    'error.notOwner': 'Chỉ xếp được tệp chính bạn tải lên.',
    'error.badFolder': 'Thư mục không hợp lệ.',
    'error.duplicate': 'Tệp này đã nằm trong không gian của bạn.',
    'error.rateLimited': 'Thao tác quá nhanh, thử lại sau ít giây.',
    'error.network': 'Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.',
    'error.status': 'Máy chủ báo lỗi (mã {status}).',
    'error.server': 'Máy chủ báo lỗi.',
    'error.serverMessage': 'Máy chủ báo lỗi: {message}',
  }),
  en: Object.freeze({
    'page.title': 'Signet — Personal space',
    'page.description': 'Signet — personal storage by P.A.R.A: Projects, Areas, Resources, Archives',
    'page.brand': 'Personal space',
    'page.footer': "Uploaded files are checked by the core's malware scanner before they are stored; every filing and "
      + "every move is recorded in the unit's hash-chained audit log. This application does none of that itself — the "
      + 'Signet core does it for every application plugged into it.',
    'nav.apps': 'Applications',
    'nav.office': 'e-Office',
    'nav.logout': 'Sign out',
    'nav.folders': 'P.A.R.A folders',
    'lang.switch': 'Tiếng Việt',
    'lang.other': 'vi',
    'status.signingIn': 'Signing in…',
    'status.signInFailed': 'Sign-in failed: {error}. Reload the page to try again.',
    'status.adminNoSpace': 'Unit administrator accounts have no personal space: the core does not let this role read '
      + 'files. Sign in with a staff account.',
    'folder.projects.name': 'Projects',
    'folder.projects.hint': "Work in progress with a goal and a deadline: a research project's files, an event plan.",
    'folder.areas.name': 'Areas',
    'folder.areas.hint': 'Ongoing responsibilities with no end date: teaching, union work.',
    'folder.resources.name': 'Resources',
    'folder.resources.hint': 'Reference material and topics of interest, opened when needed.',
    'folder.archives.name': 'Archives',
    'folder.archives.hint': 'Finished or on hold: move files here from the three folders above.',
    'folder.empty': 'This folder is empty. Upload a file, or move one here from another folder.',
    'column.name': 'File name',
    'column.size': 'Size',
    'column.scanned': 'Scanned clean at',
    'column.actions': 'Actions',
    'item.download': 'Download',
    'item.downloadLabel': 'Download {name}',
    'item.moveLabel': 'Move {name} to a folder',
    'item.movePlaceholder': 'Move to…',
    'upload.button': 'Upload a file',
    'upload.into': 'Upload a file to {folder}',
    'upload.progress': 'Uploading {name} and scanning it for malware…',
    'upload.done': 'Uploaded {name}: the scanner found it clean and it is filed in {folder}.',
    'upload.notPlaced': 'File {name} was stored but could not be filed in {folder}: {error}',
    'upload.retry': 'Try filing again',
    'upload.infected': 'The file contains malware, so the scanner blocked it and it was not stored.',
    'upload.infectedSignature': 'The file contains malware, so the scanner blocked it and it was not stored '
      + '(signature {signature}).',
    'upload.unscannable': 'The file is password-protected or nested too deeply for the scanner to check inside — '
      + 'blocked. Remove the password or unpack it, then upload it again.',
    'upload.tooLarge': 'The file is too large.',
    'upload.typeRejected': 'This file type is not accepted, so the file was not stored.',
    'upload.empty': 'The file is empty.',
    'upload.noTenant': 'Your account is not assigned to a unit, so the file was not stored. Contact your unit '
      + 'administrator.',
    'upload.unavailable': 'The file store or the malware scanner is not ready, so the file was not stored. Try again '
      + 'later.',
    'upload.failed': 'Upload failed (code {status}).',
    'move.done': 'Moved {name} to {folder}.',
    'download.notFound': 'Could not download {name}: the file is gone or you can no longer view it.',
    'error.noSpaceRole': "This account's role has no personal space.",
    'error.notOwner': 'You can only file files that you uploaded yourself.',
    'error.badFolder': 'Invalid folder.',
    'error.duplicate': 'This file is already in your space.',
    'error.rateLimited': 'Too many requests. Try again in a few seconds.',
    'error.network': 'Cannot reach the server. Check your connection and try again.',
    'error.status': 'The server returned an error (code {status}).',
    'error.server': 'The server returned an error.',
    'error.serverMessage': 'The server returned an error: {message}',
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
