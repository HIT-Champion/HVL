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

// Bảng dịch vi/en của Đơn nghỉ phép và ngôn ngữ đang dùng (#398), cùng cách làm với apps/bang-tin/public/i18n.js
// (#306). Mọi chữ trên giao diện lấy từ đây: mã gọi t('khóa'), phần tĩnh của index.html mang data-i18n
// (tests/i18n.test.js kiểm cả hai). Câu chung của form dựng từ schema (form.*, schema.*) cũng ở đây; nhãn, gợi ý, tên
// lựa chọn của từng ô nằm trong x-moc-ui của chính tệp form ({vi, en}, schemas/README.md). Ngôn ngữ chọn lưu ở
// localStorage khóa `moc.locale`, chung với Văn phòng điện tử (apps/office/app/plugins/i18n.ts), Không gian cá nhân và
// Bảng tin: cùng tên miền nên đổi ở ứng dụng nào thì ứng dụng kia mở ra cũng theo. Không đụng DOM khi nạp nên chạy
// được dưới node --test.

export const STORAGE_KEY = 'moc.locale'

export const MESSAGES = Object.freeze({
  vi: Object.freeze({
    'page.title': 'Đơn nghỉ phép — Signet',
    'page.description': 'Signet — gửi đơn nghỉ phép, trưởng phòng duyệt trên quy trình của lõi',
    'page.skip': 'Bỏ qua, tới nội dung chính',
    'page.brand': 'Đơn nghỉ phép',
    'page.tagline': 'Signet · quy trình trên lõi',
    'page.footer': 'Ứng dụng này không có máy chủ nghiệp vụ: đơn, việc duyệt, ai được thấy việc nào đều do động cơ '
      + 'quy trình của lõi Signet giữ và kiểm. Mẫu đơn là tệp JSON Schema, quy trình là tệp BPMN nằm trong thư mục của '
      + 'ứng dụng.',
    'nav.apps': 'Ứng dụng',
    'nav.office': 'Văn phòng điện tử',
    'nav.logout': 'Đăng xuất',
    'nav.sections': 'Các phần của ứng dụng',
    // nút đổi ngôn ngữ ghi tên ngôn ngữ kia bằng chính tiếng đó; lang.other là thuộc tính lang của nút
    'lang.switch': 'English',
    'lang.other': 'en',
    'status.signingIn': 'Đang đăng nhập…',
    'status.signedIn': 'Đã đăng nhập',
    'status.loadingForms': 'Đang nạp mẫu đơn…',
    'status.redirecting': 'Đang chuyển sang trang đăng nhập…',
    'tab.request': 'Gửi đơn',
    'tab.mine': 'Đơn của tôi',
    'tab.review': 'Việc cần duyệt',
    'request.heading': 'Gửi đơn nghỉ phép',
    'request.hint': 'Trưởng phòng của phòng bạn nhận đơn và duyệt. Kết quả hiện ở phần "Đơn của tôi".',
    'request.submit': 'Gửi đơn',
    'mine.heading': 'Đơn của tôi',
    'mine.empty': 'Bạn chưa gửi đơn nào.',
    'mine.sentAt': 'Gửi lúc {time}',
    'mine.endedAt': 'Kết thúc lúc {time}',
    'review.heading': 'Việc cần duyệt',
    'review.hint': 'Đơn của nhân viên trong phòng bạn đang chờ quyết định. Người gửi đọc được ghi chú.',
    'review.empty': 'Không còn đơn nào chờ duyệt.',
    'review.sentAt': 'Đơn gửi lúc {time}',
    'review.due': 'Hạn duyệt: {time}',
    'review.unknownForm': 'Trang chưa có mẫu "{formKey}" cho việc này. Tải lại trang để lấy mẫu mới.',
    'review.submit': 'Gửi quyết định',
    'detail.days': 'Số ngày nghỉ',
    // tiếng Anh phân biệt số ít, số nhiều: một ngày dùng khóa riêng
    'detail.oneDay': '1 ngày',
    'detail.dayCount': '{n} ngày',
    'state.pending': 'Chờ trưởng phòng duyệt',
    'state.approved': 'Đã duyệt',
    'state.declined': 'Bị từ chối',
    'state.ended': 'Đã kết thúc',
    'notice.sent': 'Đã gửi đơn. Trưởng phòng của phòng bạn sẽ duyệt; theo dõi ở "Đơn của tôi".',
    'notice.sentDays': 'Đã gửi đơn nghỉ {days}. Trưởng phòng của phòng bạn sẽ duyệt; theo dõi ở "Đơn của tôi".',
    'notice.approved': 'Đã duyệt đơn. Người gửi thấy kết quả trong "Đơn của tôi".',
    'notice.declined': 'Đã từ chối đơn. Người gửi thấy kết quả trong "Đơn của tôi".',
    'error.loadForms': 'Không nạp được mẫu đơn từ Signet: {error}',
    'error.emptyForm': 'form rỗng',
    'error.loadMine': 'Không tải được đơn của bạn: {error}',
    'error.loadReview': 'Không tải được việc cần duyệt: {error}',
    'error.sendFailed': 'Chưa gửi được đơn: {error}',
    'error.reload': 'Không tải lại được danh sách: {error}',
    // câu theo mã trả lời của API (LOI trong don.js)
    'error.network': 'Không gọi được Signet. Kiểm tra kết nối mạng rồi thử lại.',
    'error.session': 'Phiên đăng nhập đã hết. Tải lại trang để đăng nhập lại.',
    'error.forbidden': 'Tài khoản này không được làm việc đó trong ứng dụng Đơn nghỉ phép.',
    'error.gone': 'Không còn mục này — có thể đơn đã có người duyệt. Danh sách vừa được tải lại.',
    'error.conflict': 'Đơn vừa có người khác xử lý. Danh sách vừa được tải lại.',
    'error.rateLimited': 'Gửi quá nhiều yêu cầu trong thời gian ngắn. Đợi một phút rồi thử lại.',
    'error.unavailable': 'Hệ thống quy trình của Signet chưa trả lời. Thử lại sau ít phút.',
    'error.invalid': 'Dữ liệu chưa hợp lệ: xem lời báo ở từng ô.',
    'error.rejected': 'Signet từ chối yêu cầu (HTTP {status}).',
    // câu chung của form dựng từ schema (schema-form.js); x-moc-ui.errors của từng trường thay câu chung
    'form.optional': 'không bắt buộc',
    'form.pick': '— Chọn —',
    'form.submit': 'Gửi',
    'form.yes': 'Có',
    'form.no': 'Không',
    'form.empty': '—',
    'form.top': 'Chưa gửi được, kiểm tra lại:',
    'form.required': 'Không được để trống',
    'form.between': 'Cần {min}–{max} ký tự',
    'form.minLength': 'Cần ít nhất {min} ký tự',
    'form.maxLength': 'Tối đa {max} ký tự',
    'form.minimum': 'Nhỏ nhất là {min}',
    'form.maximum': 'Lớn nhất là {max}',
    'form.minItems': 'Chọn ít nhất {min} mục',
    'form.maxItems': 'Chọn tối đa {max} mục',
    'form.uniqueItems': 'Có mục được chọn hai lần',
    'form.date': 'Ngày không có thật hoặc sai dạng',
    'form.format': 'Không đúng định dạng',
    'form.notAfterToday': 'Không được sau hôm nay',
    'form.notBeforeToday': 'Không được trước hôm nay',
    'form.range': 'Không được trước «{other}»',
    'form.nfc': 'Chữ tiếng Việt chưa ở dạng dựng sẵn (Unicode NFC)',
    'form.not': 'Có khoảng trắng thừa ở đầu hoặc cuối, xuống dòng hoặc ký tự ẩn',
    'form.enum': 'Không có trong danh sách',
    'form.const': 'Không đúng giá trị yêu cầu',
    'form.type': 'Sai kiểu dữ liệu',
    'form.additionalProperties': 'Trường không có trong mẫu',
    'form.invalid': 'Giá trị chưa hợp lệ',
    // schema dùng điều bộ kiểm không hiểu: báo lúc nạp (trang hiện qua error.loadForms)
    'schema.notObject': 'Schema {at}: phải là đối tượng',
    'schema.defs': 'Schema {at}: $defs phải là đối tượng',
    'schema.keyword': 'Schema {at}: không hỗ trợ từ khóa {key}',
    'schema.type': 'Schema {at}: kiểu {type} không có',
    'schema.format': 'Schema {at}: định dạng {format} không hỗ trợ (chỉ date, uuid)',
    'schema.shape': 'Schema {at}: {key} sai dạng ({value})',
    'schema.ref': 'Schema: $ref {ref} không trỏ tới #/$defs/… có sẵn',
    'schema.cycle': 'Schema: $ref vòng {path}',
    'schema.order': 'Schema: x-moc-order phải liệt kê đủ và đúng các trường trong properties',
    'schema.ranges': 'Schema: x-moc-range phải là mảng các cặp',
    'schema.range': 'Schema: x-moc-range {pair} phải là cặp hai trường format date',
    'schema.ui': 'Schema: x-moc-ui của {name} phải là đối tượng',
    'schema.widget': 'Schema: x-moc-ui.widget của {name} không có ({widget})',
    'schema.hidden': 'Schema: trường ẩn {name} bắt buộc mà không có giá trị',
  }),
  en: Object.freeze({
    'page.title': 'Leave requests — Signet',
    'page.description': 'Signet — request leave and have it approved by your department head on the core workflow',
    'page.skip': 'Skip to main content',
    'page.brand': 'Leave requests',
    'page.tagline': 'Signet · workflow on the core',
    'page.footer': "This app has no business server of its own: requests, approval tasks and who may see each task are "
      + "kept and checked by the Signet core's workflow engine. The forms are JSON Schema files and the workflow is a "
      + "BPMN file in the app's folder.",
    'nav.apps': 'Applications',
    'nav.office': 'e-Office',
    'nav.logout': 'Sign out',
    'nav.sections': 'App sections',
    'lang.switch': 'Tiếng Việt',
    'lang.other': 'vi',
    'status.signingIn': 'Signing in…',
    'status.signedIn': 'Signed in',
    'status.loadingForms': 'Loading forms…',
    'status.redirecting': 'Redirecting to the sign-in page…',
    'tab.request': 'New request',
    'tab.mine': 'My requests',
    'tab.review': 'To review',
    'request.heading': 'Request leave',
    'request.hint': 'Your department head receives and reviews the request. The outcome appears under "My requests".',
    'request.submit': 'Send request',
    'mine.heading': 'My requests',
    'mine.empty': 'You have not sent any requests yet.',
    'mine.sentAt': 'Sent {time}',
    'mine.endedAt': 'Closed {time}',
    'review.heading': 'Requests to review',
    'review.hint': 'Leave requests from your department waiting for your decision. The requester can read your note.',
    'review.empty': 'No requests are waiting for review.',
    'review.sentAt': 'Request sent {time}',
    'review.due': 'Review by {time}',
    'review.unknownForm': 'This page does not have the form "{formKey}" for this task yet. Reload the page to get it.',
    'review.submit': 'Submit decision',
    'detail.days': 'Days of leave',
    'detail.oneDay': '1 day',
    'detail.dayCount': '{n} days',
    'state.pending': 'Awaiting department head',
    'state.approved': 'Approved',
    'state.declined': 'Declined',
    'state.ended': 'Closed',
    'notice.sent': 'Request sent. Your department head will review it; follow it under "My requests".',
    'notice.sentDays': 'Request for {days} of leave sent. Your department head will review it; follow it under "My '
      + 'requests".',
    'notice.approved': 'Request approved. The requester sees the outcome under "My requests".',
    'notice.declined': 'Request declined. The requester sees the outcome under "My requests".',
    'error.loadForms': 'Could not load the forms from Signet: {error}',
    'error.emptyForm': 'empty form',
    'error.loadMine': 'Could not load your requests: {error}',
    'error.loadReview': 'Could not load the requests to review: {error}',
    'error.sendFailed': 'The request was not sent: {error}',
    'error.reload': 'Could not refresh the lists: {error}',
    'error.network': 'Could not reach Signet. Check your network connection and try again.',
    'error.session': 'Your session has expired. Reload the page to sign in again.',
    'error.forbidden': 'This account is not allowed to do that in the Leave requests app.',
    'error.gone': 'This item is gone — someone may already have reviewed the request. The list has been reloaded.',
    'error.conflict': 'Someone else has just handled this request. The list has been reloaded.',
    'error.rateLimited': 'Too many requests in a short time. Wait a minute and try again.',
    'error.unavailable': 'The Signet workflow service is not responding. Try again in a few minutes.',
    'error.invalid': 'Some fields are not valid: see the message under each field.',
    'error.rejected': 'Signet refused the request (HTTP {status}).',
    'form.optional': 'optional',
    'form.pick': '— Choose —',
    'form.submit': 'Submit',
    'form.yes': 'Yes',
    'form.no': 'No',
    'form.empty': '—',
    'form.top': 'Not sent yet. Please check:',
    'form.required': 'Required',
    'form.between': '{min}–{max} characters',
    'form.minLength': 'At least {min} characters',
    'form.maxLength': 'At most {max} characters',
    'form.minimum': 'At least {min}',
    'form.maximum': 'At most {max}',
    'form.minItems': 'Choose at least {min}',
    'form.maxItems': 'Choose at most {max}',
    'form.uniqueItems': 'An item is chosen twice',
    'form.date': 'Not a real date, or not in the right format',
    'form.format': 'Invalid format',
    'form.notAfterToday': 'Cannot be in the future',
    'form.notBeforeToday': 'Cannot be before today',
    'form.range': 'Cannot be before "{other}"',
    'form.nfc': 'Text is not in composed Unicode form (NFC)',
    'form.not': 'Extra spaces at the start or end, line breaks or hidden characters',
    'form.enum': 'Not in the list',
    'form.const': 'Not the required value',
    'form.type': 'Wrong data type',
    'form.additionalProperties': 'Field not in the form',
    'form.invalid': 'Invalid value',
    'schema.notObject': 'Schema {at}: must be an object',
    'schema.defs': 'Schema {at}: $defs must be an object',
    'schema.keyword': 'Schema {at}: keyword {key} is not supported',
    'schema.type': 'Schema {at}: type {type} does not exist',
    'schema.format': 'Schema {at}: format {format} is not supported (only date, uuid)',
    'schema.shape': 'Schema {at}: {key} has the wrong shape ({value})',
    'schema.ref': 'Schema: $ref {ref} does not point to an existing #/$defs/…',
    'schema.cycle': 'Schema: circular $ref {path}',
    'schema.order': 'Schema: x-moc-order must list exactly the fields in properties',
    'schema.ranges': 'Schema: x-moc-range must be an array of pairs',
    'schema.range': 'Schema: x-moc-range {pair} must be a pair of two fields with format date',
    'schema.ui': 'Schema: x-moc-ui of {name} must be an object',
    'schema.widget': 'Schema: x-moc-ui.widget of {name} does not exist ({widget})',
    'schema.hidden': 'Schema: hidden field {name} is required but has no value',
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

/** Câu theo khóa, {tên} thay bằng tham số cùng tên. lang bỏ trống là ngôn ngữ đang dùng; schema-form.js truyền ngôn
 *  ngữ của form. Thiếu bản tiếng Anh thì lấy tiếng Việt, thiếu cả hai thì trả khóa (test bắt trường hợp này trước khi
 *  tới trình duyệt). */
export function t(key, params = {}, lang = current) {
  const text = lookup(MESSAGES[pickLocale(lang)], key) ?? lookup(MESSAGES.vi, key) ?? key
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
 *  tử (phần tử chỉ chứa chữ), data-i18n-<thuộc tính>="khóa" là thuộc tính, vd data-i18n-aria-label. */
export function localize(doc) {
  doc.documentElement.lang = current
  for (const node of doc.querySelectorAll('*')) {
    for (const { name, value } of [...node.attributes]) {
      if (name === 'data-i18n') node.textContent = t(value)
      else if (name.startsWith('data-i18n-')) node.setAttribute(name.slice('data-i18n-'.length), t(value))
    }
  }
}
