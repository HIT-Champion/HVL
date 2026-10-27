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

// Phần không đụng trình duyệt (test bằng node --test): câu GraphQL, nhãn loại tin, giờ, dựng dòng hiển thị. Chữ lấy
// từ bảng dịch (i18n.js) theo ngôn ngữ đang dùng.

import { t } from './i18n.js'

/** Đúng câu trang gửi lên /v1/graphql (tests/ kiểm câu này theo quyền trong app.yaml). */
export const QUERY_TIN = `query BangTin {
  bang_tin_tin(order_by: {occurred_at: desc}, limit: 50) {
    event_id kind occurred_at document_id
    document { symbol summary direction }
  }
}`

/** Loại tin ứng dụng nghe (events.kinds của app.yaml) → khóa nhãn trong bảng dịch. */
export const LOAI = Object.freeze({
  'office.document.registered': 'kind.registered',
  'office.document.issued': 'kind.issued',
})

/** Giờ Việt Nam, dạng 25/10/2026 14:05 (cả khi dùng tiếng Anh: văn bản theo giờ của đơn vị) */
export function gio(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const p = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit',
    year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(d)
  const v = Object.fromEntries(p.map((x) => [x.type, x.value]))
  return `${v.day}/${v.month}/${v.year} ${v.hour}:${v.minute}`
}

/** Một tin → các chữ hiển thị (trang gán bằng textContent, không bao giờ innerHTML). */
export function dong(tin) {
  return {
    loai: Object.hasOwn(LOAI, tin.kind) ? t(LOAI[tin.kind]) : tin.kind,
    gio: gio(tin.occurred_at),
    so: tin.document?.symbol || t('news.noSymbol'),
    trichYeu: tin.document?.summary || '',
  }
}

function claims(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const c = JSON.parse(decodeURIComponent(Array.from(atob(part), (ch) =>
      '%' + ch.charCodeAt(0).toString(16).padStart(2, '0')).join('')))
    return c && typeof c === 'object' && !Array.isArray(c) ? c : null
  } catch {
    return null
  }
}

/** Tên người dùng trong access token (claim name, không thì preferred_username) — chỉ để chào, không để phân quyền. */
export function tenNguoi(token) {
  const c = claims(token)
  return c?.name || c?.preferred_username || ''
}

/** Vai trò trong access token, chỉ để vẽ trang; quyền thật do Hasura xét theo app.yaml. */
export function vaiTro(token) {
  return claims(token)?.['https://hasura.io/jwt/claims']?.['x-hasura-default-role'] ?? null
}

/**
 * Vai trò đọc được bảng tin: đúng các vai trò có select_permissions trong app.yaml (quản trị đơn vị không đọc văn
 * bản).
 */
export const VAI_TRO_XEM = ['clerk', 'staff', 'manager', 'director']

/**
 * Câu báo khi không tải được tin. Hasura trả validation-failed khi vai trò không thấy bảng (vd token vừa đổi vai trò):
 * báo bằng câu đọc được, không đưa tên bảng, query_root của GraphQL ra trang.
 */
export function loiTaiTin(body, status) {
  if (body?.errors?.some((e) => e.extensions?.code === 'validation-failed')) {
    return t('error.noAccess')
  }
  return body?.errors?.[0]?.message || `HTTP ${status}`
}
