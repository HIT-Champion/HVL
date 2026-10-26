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

// Phần không đụng trình duyệt (test bằng node --test): đường của API quy trình chung của lõi, dựng lời gọi, đọc câu
// trả lời, trạng thái một đơn, ngày giờ, đối chiếu danh sách việc. Trang (app.js) chỉ vẽ.

/** API chung của lõi cho quy trình của ứng dụng; APISIX chỉ nhận token của client app-nghi-phep ở đây. */
export const API = '/api/workflow/nghi-phep'
export const QUY_TRINH = 'nghi-phep.don'
export const FORM_DON = 'nghi-phep.don'
export const FORM_DUYET = 'nghi-phep.duyet'

export const duong = {
  form: (formKey) => `/forms/${encodeURIComponent(formKey)}`,
  guiDon: () => `/processes/${encodeURIComponent(QUY_TRINH)}`,
  donCuaToi: () => '/processes',
  viec: () => '/tasks',
  xongViec: (taskId) => `/tasks/${encodeURIComponent(taskId)}`,
}

/** Một lời gọi API → [địa chỉ, tham số của fetch]. Có dữ liệu thì gửi {"data": …} như API chung quy định. */
export function yeuCau(token, method, path, data) {
  const headers = { Authorization: `Bearer ${token}`, Accept: 'application/json' }
  const init = { method, headers, cache: 'no-store' }
  if (data !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify({ data })
  }
  return [`${API}${path}`, init]
}

/** Thân trả lời dạng chữ → JSON; rỗng (204) hay không phải JSON (trang lỗi của cổng) → null. */
export function docThan(text) {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export const LOI = {
  mang: 'Không gọi được Signet. Kiểm tra kết nối mạng rồi thử lại.',
  401: 'Phiên đăng nhập đã hết. Tải lại trang để đăng nhập lại.',
  403: 'Tài khoản này không được làm việc đó trong ứng dụng Đơn nghỉ phép.',
  404: 'Không còn mục này — có thể đơn đã có người duyệt. Danh sách vừa được tải lại.',
  409: 'Đơn vừa có người khác xử lý. Danh sách vừa được tải lại.',
  429: 'Gửi quá nhiều yêu cầu trong thời gian ngắn. Đợi một phút rồi thử lại.',
  500: 'Hệ thống quy trình của Signet chưa trả lời. Thử lại sau ít phút.',
}

const isMap = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)

/**
 * Trả lời của API → {ok: true, data} hoặc {ok: false, status, message, errors?}. 422 mang lỗi từng trường
 * {trường: mã} để form tự hiện câu dưới từng ô (schema-form.js); mã khác thành một câu đọc được, không đưa thân lỗi
 * thô ra trang.
 */
export function docTraLoi(status, body) {
  if (status >= 200 && status < 300) return { ok: true, data: body }
  if (status === 422 && isMap(body?.errors)) {
    return { ok: false, status, errors: body.errors, message: 'Dữ liệu chưa hợp lệ: xem lời báo ở từng ô.' }
  }
  const message = LOI[status] || (status >= 500 ? LOI[500] : `Signet từ chối yêu cầu (HTTP ${status}).`)
  return { ok: false, status, message }
}

/** Trạng thái một đơn của tôi: còn chạy là chờ duyệt; kết thúc thì theo quyết định của trưởng phòng. */
export function trangThai(don) {
  if (!don?.endedAt) return { ma: 'cho', nhan: 'Chờ trưởng phòng duyệt' }
  const q = don.data?.quyetDinh
  if (q === 'dong-y') return { ma: 'dong-y', nhan: 'Đã duyệt' }
  if (q === 'tu-choi') return { ma: 'tu-choi', nhan: 'Bị từ chối' }
  return { ma: 'xong', nhan: 'Đã kết thúc' }
}

const NGAY = /^(\d{4})-(\d{2})-(\d{2})$/

function utc(text) {
  const m = typeof text === 'string' ? NGAY.exec(text) : null
  if (!m) return null
  const t = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return new Date(t).toISOString().slice(0, 10) === text ? t : null       // 2026-02-30 không phải ngày có thật
}

/** Số ngày nghỉ, tính cả hai đầu; ngày sai hay đến trước từ → null. */
export function soNgay(tuNgay, denNgay) {
  const a = utc(tuNgay), b = utc(denNgay)
  if (a === null || b === null || b < a) return null
  return Math.round((b - a) / 86400000) + 1
}

/** Thời điểm theo giờ Việt Nam, dạng 26/10/2026 14:05; sai thì rỗng. */
export function ngayGio(iso) {
  const d = new Date(iso)
  if (typeof iso !== 'string' || Number.isNaN(d.getTime())) return ''
  const p = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit',
    year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(d)
  const v = Object.fromEntries(p.map((x) => [x.type, x.value]))
  return `${v.day}/${v.month}/${v.year} ${v.hour}:${v.minute}`
}

const at = (iso) => {
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? 0 : t
}

/** Đơn của tôi: mới gửi lên đầu. */
export const sapXepDon = (list) => [...list].sort((a, b) => at(b.startedAt) - at(a.startedAt))

/** Việc cần duyệt: đơn đến trước duyệt trước. */
export const sapXepViec = (list) => [...list].sort((a, b) => at(a.createdAt) - at(b.createdAt))

/**
 * Danh sách việc mới so với các thẻ đang hiện → thẻ cần thêm, thẻ cần bỏ. Thẻ còn việc thì giữ nguyên: làm mới danh
 * sách không xóa ghi chú người duyệt đang gõ.
 */
export function doiChieu(dangHien, moi) {
  const ids = new Set(moi.map((t) => t.id))
  return { them: sapXepViec(moi.filter((t) => !dangHien.includes(t.id))), bo: dangHien.filter((id) => !ids.has(id)) }
}

function claims(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const c = JSON.parse(decodeURIComponent(Array.from(atob(part), (ch) =>
      '%' + ch.charCodeAt(0).toString(16).padStart(2, '0')).join('')))
    return isMap(c) ? c : null
  } catch {
    return null
  }
}

/** Tên người dùng trong access token (claim name, không thì preferred_username) — chỉ để chào, không để phân quyền. */
export function tenNguoi(token) {
  const c = claims(token)
  return c?.name || c?.preferred_username || ''
}
