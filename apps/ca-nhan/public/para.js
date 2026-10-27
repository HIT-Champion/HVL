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
// nên chạy được dưới `node --test` (tests/para.test.js). Chữ lấy từ bảng dịch (i18n.js) theo ngôn ngữ đang dùng.

import { locale, t } from './i18n.js'

/** Bốn thư mục P.A.R.A (Projects, Areas, Resources, Archives — phương pháp của Tiago Forte). `key` khớp ràng buộc
 *  items_para của bảng personal.items (db/migrations/default/1792281602500_personal_space); test so hai bên. Tên và
 *  lời gợi ý ở bảng dịch, khóa folder.<key>.name và folder.<key>.hint. */
export const FOLDERS = Object.freeze(['projects', 'areas', 'resources', 'archives']
  .map((key) => Object.freeze({ key })))

export const DEFAULT_FOLDER = 'projects'

export function isFolder(key) {
  return FOLDERS.some((f) => f.key === key)
}

export function folderName(key) {
  return isFolder(key) ? t(`folder.${key}.name`) : key
}

export function folderHint(key) {
  return isFolder(key) ? t(`folder.${key}.hint`) : ''
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

/** Dung lượng, một chữ số lẻ từ KB trở lên: dấu phẩy thập phân khi dùng tiếng Việt, dấu chấm khi dùng tiếng Anh. */
export function formatSize(bytes) {
  let n = Number(bytes)
  if (!Number.isFinite(n) || n < 0) return '—'
  let unit = 0
  while (n >= 1024 && unit < UNITS.length - 1) {
    n /= 1024
    unit += 1
  }
  const text = unit === 0 ? String(n) : n.toFixed(1).replace(/\.0$/, '').replace('.', locale() === 'vi' ? ',' : '.')
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
  // svc-files nhận loại theo nội dung sau ClamAV, bỏ EXIF của ảnh: câu của máy chủ nói rõ tệp là gì, vì sao chặn. Câu
  // đó viết tiếng Việt, nên khi dùng tiếng Anh lấy câu chung của bảng dịch
  const server = locale() === 'vi' && detail.message ? `${detail.message}.` : null
  switch (detail.code) {
    case 'infected':
      return detail.signature ? t('upload.infectedSignature', { signature: detail.signature }) : t('upload.infected')
    case 'unscannable':
      return t('upload.unscannable')
    case 'too_large':
      return server ?? t('upload.tooLarge')
    case 'type_mismatch':
    case 'type_not_allowed':
    case 'image_unreadable':
      return server ?? t('upload.typeRejected')
    case 'empty_file':
      return t('upload.empty')
    case 'no_tenant':
    case 'unknown_tenant':
      return t('upload.noTenant')
    default:
  }
  if (status === 0) return t('error.network')
  if (status === 413) return t('upload.tooLarge')
  if (status === 429) return t('error.rateLimited')
  if (status === 503) return t('upload.unavailable')
  return t('upload.failed', { status })
}

/** Câu báo khi Hasura trả lỗi. code: extensions.code của lỗi đầu tiên. */
export function graphqlError(code, message = '') {
  if (code === 'validation-failed') return t('error.noSpaceRole')
  if (code === 'constraint-violation' || code === 'permission-error') {
    if (/items_guard/.test(message)) return t('error.notOwner')
    if (/items_para/.test(message)) return t('error.badFolder')
    if (/items_pkey|Uniqueness/i.test(message)) return t('error.duplicate')
  }
  if (code === 'rate_limited') return t('error.rateLimited')
  if (code === 'network') return t('error.network')
  return message ? t('error.serverMessage', { message }) : t('error.server')
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
