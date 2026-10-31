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

// Phần không đụng trình duyệt (test bằng node --test): đường của API quy trình chung của lõi, dựng lời gọi, đọc câu trả
// lời, trạng thái một đề nghị qua hai cấp duyệt, ngày giờ, đối chiếu danh sách việc. Trang (app.js) chỉ vẽ. Câu báo lấy
// từ bảng dịch (i18n.js) theo ngôn ngữ đang dùng.

import { t } from './i18n.js'

/**
 * API chung của lõi cho quy trình của ứng dụng. APISIX kiểm token; svc-workflow chỉ nhận token của client
 * app-lich-giang (`azp`) ở đây.
 */
export const API = '/api/workflow/lich-giang'
export const QUY_TRINH = 'lich-giang.don'
export const FORM_DON = 'lich-giang.don'
export const FORM_BO_MON = 'lich-giang.bo-mon'
export const FORM_KHOA = 'lich-giang.khoa'

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

/** Mã trả lời của API (mang: không gọi được) → khóa câu báo trong bảng dịch; tests/i18n.test.js kiểm khóa có thật. */
export const LOI = Object.freeze({
  mang: 'error.network',
  401: 'error.session',
  403: 'error.forbidden',
  404: 'error.gone',
  409: 'error.conflict',
  429: 'error.rateLimited',
  500: 'error.unavailable',
})

const isMap = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)

/**
 * Trả lời của API → {ok: true, data} hoặc {ok: false, status, message, errors?}. 422 mang lỗi từng trường
 * {trường: mã} để form tự hiện câu dưới từng ô (schema-form.js); mã khác thành một câu đọc được, không đưa thân lỗi
 * thô ra trang.
 */
export function docTraLoi(status, body) {
  if (status >= 200 && status < 300) return { ok: true, data: body }
  if (status === 422 && isMap(body?.errors)) {
    return { ok: false, status, errors: body.errors, message: t('error.invalid') }
  }
  const key = LOI[status] || (status >= 500 ? LOI[500] : '')
  return { ok: false, status, message: key ? t(key) : t('error.rejected', { status }) }
}

/**
 * Trạng thái một đề nghị của tôi. Còn chạy: chờ bộ môn, hoặc chờ khoa khi bộ môn đã đồng ý. Kết thúc: bộ môn không
 * đồng ý thì dừng ở đó; còn lại theo quyết định của khoa.
 */
export function trangThai(don) {
  const d = don?.data ?? {}
  if (!don?.endedAt) {
    return d.quyetDinhBoMon === 'dong-y' ? { ma: 'cho', nhan: t('state.pendingFaculty') }
      : { ma: 'cho', nhan: t('state.pendingDepartment') }
  }
  if (d.quyetDinhBoMon === 'tu-choi') return { ma: 'tu-choi', nhan: t('state.declinedDepartment') }
  if (d.quyetDinhKhoa === 'dong-y') return { ma: 'dong-y', nhan: t('state.approved') }
  if (d.quyetDinhKhoa === 'tu-choi') return { ma: 'tu-choi', nhan: t('state.declinedFaculty') }
  return { ma: 'xong', nhan: t('state.ended') }
}

/** Quyết định trong dữ liệu một bước duyệt (bộ môn hoặc khoa) → 'dong-y' | 'tu-choi' | undefined. */
export const quyetDinh = (data) => data?.quyetDinhBoMon ?? data?.quyetDinhKhoa

/** Thời điểm theo giờ Việt Nam, dạng 26/10/2026 14:05 (cả khi dùng tiếng Anh: đơn theo giờ của đơn vị); sai thì
 *  rỗng. */
export function ngayGio(iso) {
  const d = new Date(iso)
  if (typeof iso !== 'string' || Number.isNaN(d.getTime())) return ''
  const p = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit',
    year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(d)
  const v = Object.fromEntries(p.map((x) => [x.type, x.value]))
  return `${v.day}/${v.month}/${v.year} ${v.hour}:${v.minute}`
}

const at = (iso) => {
  const ms = new Date(iso).getTime()
  return Number.isNaN(ms) ? 0 : ms
}

/** Đề nghị của tôi: mới gửi lên đầu. */
export const sapXepDon = (list) => [...list].sort((a, b) => at(b.startedAt) - at(a.startedAt))

/** Việc cần duyệt: đề nghị đến trước duyệt trước. */
export const sapXepViec = (list) => [...list].sort((a, b) => at(a.createdAt) - at(b.createdAt))

/**
 * Danh sách việc mới so với các thẻ đang hiện → thẻ cần thêm, thẻ cần bỏ. Thẻ còn việc thì giữ nguyên: làm mới danh
 * sách không xóa ghi chú người duyệt đang gõ.
 */
export function doiChieu(dangHien, moi) {
  const ids = new Set(moi.map((v) => v.id))
  return { them: sapXepViec(moi.filter((v) => !dangHien.includes(v.id))), bo: dangHien.filter((id) => !ids.has(id)) }
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
