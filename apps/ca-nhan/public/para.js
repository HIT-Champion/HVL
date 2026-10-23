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

// Phần thuần của Không gian cá nhân: thư mục P.A.R.A, câu GraphQL, định dạng, câu báo lỗi. Không đụng DOM hay mạng
// nên chạy được dưới `node --test` (tests/para.test.js).

/** Bốn thư mục P.A.R.A (Projects, Areas, Resources, Archives — phương pháp của Tiago Forte). `key` khớp ràng buộc
 *  items_para của bảng personal.items (db/migrations/default/1792281602500_personal_space); test so hai bên. */
export const FOLDERS = Object.freeze([
  { key: 'projects', name: 'Dự án', hint: 'Việc đang làm, có đích và có hạn: hồ sơ một đề tài, kế hoạch một sự kiện.' },
  { key: 'areas', name: 'Lĩnh vực', hint: 'Phần việc giữ lâu dài, không có ngày xong: giảng dạy, công tác đoàn thể.' },
  { key: 'resources', name: 'Tài nguyên', hint: 'Tài liệu tham khảo, chủ đề quan tâm, mở ra khi cần.' },
  { key: 'archives', name: 'Lưu trữ', hint: 'Đã xong hoặc tạm gác: chuyển từ ba thư mục trên sang đây.' },
])

export const DEFAULT_FOLDER = 'projects'

export function isFolder(key) {
  return FOLDERS.some((f) => f.key === key)
}

export function folderName(key) {
  return FOLDERS.find((f) => f.key === key)?.name ?? key
}

/** Thư mục đang mở theo phần # của địa chỉ (#archives); sai hoặc trống thì thư mục mặc định. */
export function folderFromHash(hash) {
  const key = String(hash ?? '').replace(/^#/, '')
  return isFolder(key) ? key : DEFAULT_FOLDER
}

// Câu GraphQL gửi Hasura qua /v1/graphql. Bảng personal.items của ứng dụng, quan hệ `file` tới core.files của lõi:
// người dùng đọc được tệp chính mình tải lên (db/metadata/.../core_files.yaml), không cần quyền gì thêm.
export const QUERY_ITEMS = `query CaNhan {
  personal_items(order_by: {updated_at: desc}) {
    file_id para created_at updated_at
    file { filename mime_type size_bytes scanned_at }
  }
}`

export const PLACE_ITEM = `mutation Dat($file: uuid!, $para: String!) {
  insert_personal_items_one(object: {file_id: $file, para: $para}) { file_id para }
}`

export const MOVE_ITEM = `mutation Chuyen($file: uuid!, $para: String!) {
  update_personal_items_by_pk(pk_columns: {file_id: $file}, _set: {para: $para}) { file_id para updated_at }
}`

/** Số tệp mỗi thư mục, đủ cả bốn khóa. */
export function countByFolder(items) {
  const counts = Object.fromEntries(FOLDERS.map((f) => [f.key, 0]))
  for (const item of items) if (item.para in counts) counts[item.para] += 1
  return counts
}

/** Tệp của một thư mục, mới đặt / mới chuyển tới trước; cùng lúc thì theo tên. */
export function itemsIn(items, key) {
  return items
    .filter((item) => item.para === key)
    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))
      || String(a.file?.filename ?? '').localeCompare(String(b.file?.filename ?? ''), 'vi'))
}

const UNITS = ['B', 'KB', 'MB', 'GB']

/** Dung lượng kiểu Việt Nam: dấu phẩy thập phân, một chữ số lẻ từ KB trở lên. */
export function formatSize(bytes) {
  let n = Number(bytes)
  if (!Number.isFinite(n) || n < 0) return '—'
  let unit = 0
  while (n >= 1024 && unit < UNITS.length - 1) {
    n /= 1024
    unit += 1
  }
  const text = unit === 0 ? String(n) : n.toFixed(1).replace(/\.0$/, '').replace('.', ',')
  return `${text} ${UNITS[unit]}`
}

/** Ngày giờ dd/mm/yyyy hh:mm theo múi giờ cho trước (mặc định giờ Việt Nam). */
export function formatTime(iso, timeZone = 'Asia/Ho_Chi_Minh') {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(d).map((p) => [p.type, p.value]))
  return `${parts.day}/${parts.month}/${parts.year} ${parts.hour}:${parts.minute}`
}

/** Câu báo cho người dùng khi tải tệp lên svc-files không được. status 0: không tới được máy chủ. body: thân JSON của
 *  svc-files ({detail: {code, message, signature}}), có thể rỗng khi cổng trả lỗi. */
export function uploadError(status, body) {
  const detail = body && typeof body.detail === 'object' && body.detail !== null ? body.detail : {}
  switch (detail.code) {
    case 'infected':
      return `Tệp chứa mã độc nên trạm quét đã chặn, không lưu${detail.signature ? ` (mẫu ${detail.signature})` : ''}.`
    case 'unscannable':
      return 'Tệp có mật khẩu hoặc nén nhiều lớp nên trạm quét không kiểm được bên trong — đã chặn. Bỏ mật khẩu hoặc '
        + 'giải nén rồi tải lên lại.'
    case 'too_large':
      return detail.message ? `${detail.message}.` : 'Tệp quá lớn.'
    case 'empty_file':
      return 'Tệp rỗng.'
    case 'no_tenant':
    case 'unknown_tenant':
      return 'Tài khoản chưa được gắn đơn vị nên chưa lưu được tệp. Báo quản trị đơn vị.'
    default:
  }
  if (status === 0) return 'Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.'
  if (status === 413) return 'Tệp quá lớn.'
  if (status === 429) return 'Thao tác quá nhanh, thử lại sau ít giây.'
  if (status === 503) return 'Kho tệp hoặc trạm quét mã độc chưa sẵn sàng, tệp chưa được lưu. Thử lại sau.'
  return `Tải lên không được (mã ${status}).`
}

/** Câu báo khi Hasura trả lỗi. code: extensions.code của lỗi đầu tiên. */
export function graphqlError(code, message = '') {
  if (code === 'validation-failed') return 'Vai trò của tài khoản này không có không gian cá nhân.'
  if (code === 'constraint-violation' || code === 'permission-error') {
    if (/items_guard/.test(message)) return 'Chỉ xếp được tệp chính bạn tải lên.'
    if (/items_para/.test(message)) return 'Thư mục không hợp lệ.'
    if (/items_pkey|Uniqueness/i.test(message)) return 'Tệp này đã nằm trong không gian của bạn.'
  }
  if (code === 'rate_limited') return 'Thao tác quá nhanh, thử lại sau ít giây.'
  if (code === 'network') return 'Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.'
  return message ? `Máy chủ báo lỗi: ${message}` : 'Máy chủ báo lỗi.'
}

const HASURA = 'https://hasura.io/jwt/claims'

/** Đọc claim của access token chỉ để vẽ giao diện (tên, vai trò); quyền thật do Hasura, svc-files kiểm lại. */
export function readClaims(token) {
  try {
    const part = String(token).split('.')[1] ?? ''
    const bin = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    const payload = JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0))))
    const h = payload[HASURA] ?? {}
    return {
      userId: h['x-hasura-user-id'] ?? payload.sub ?? null,
      tenantId: h['x-hasura-tenant-id'] ?? null,
      role: h['x-hasura-default-role'] ?? null,
      name: payload.name ?? payload.preferred_username ?? '',
      client: payload.azp ?? null,
    }
  } catch {
    return null
  }
}

/** Vai trò có không gian cá nhân: vai trò đọc được tệp mình tải lên (quản trị đơn vị không đọc core.files). */
export function hasSpace(role) {
  return role === 'clerk' || role === 'staff' || role === 'manager' || role === 'director'
}
