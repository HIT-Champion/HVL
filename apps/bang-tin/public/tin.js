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

// Phần không đụng trình duyệt (test bằng node --test): câu GraphQL, nhãn loại tin, giờ, dựng dòng hiển thị.

/** Đúng câu trang gửi lên /v1/graphql (tests/ kiểm câu này theo quyền trong app.yaml). */
export const QUERY_TIN = `query BangTin {
  bang_tin_tin(order_by: {occurred_at: desc}, limit: 50) {
    event_id kind occurred_at document_id
    document { symbol summary direction }
  }
}`

export const LOAI = {
  'office.document.registered': 'Văn bản đến đã vào sổ',
  'office.document.issued': 'Văn bản đi đã phát hành',
}

/** Giờ Việt Nam, dạng 25/10/2026 14:05 */
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
    loai: LOAI[tin.kind] || tin.kind,
    gio: gio(tin.occurred_at),
    so: tin.document?.symbol || '(chưa có số)',
    trichYeu: tin.document?.summary || '',
  }
}

/** Tên người dùng trong access token (claim name, không thì preferred_username) — chỉ để chào, không để phân quyền. */
export function tenNguoi(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const claims = JSON.parse(decodeURIComponent(Array.from(atob(part), (c) =>
      '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join('')))
    return claims.name || claims.preferred_username || ''
  } catch {
    return ''
  }
}
