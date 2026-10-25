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

// Danh mục ứng dụng (/ung-dung): ứng dụng chạy trên lõi Signet, dùng chung một lần đăng nhập. Hai nguồn:
// - ứng dụng có sẵn trong lõi (BUILTIN_APPS): cùng bản cài, cùng thẻ image MOC_VERSION với lõi, không cài bằng
//   manifest — phiên bản lấy từ GET /api/status (công khai);
// - ứng dụng cắm bằng manifest (`moc app install`, docs/them-ung-dung.md mục 1): khung nhìn core.app_catalog
//   (migration 1792281603400). Mọi vai trò đọc ứng dụng đang cài; lãnh đạo, quản trị đơn vị đọc thêm băm manifest và
//   ứng dụng đã gỡ (core_app_catalog.yaml — test so câu truy vấn với cột từng vai trò được đọc).
// Trạng thái là "đã cài", không phải "đang chạy": CSDL chỉ biết lệnh cài đã xong, không biết container có khỏe không.

import type { Role } from '~/composables/useAuth'

// Câu GraphQL của trang; scripts/demo.py (cai-ung-dung) chạy đúng hai câu này trên hệ thống thật
export const APPS_QUERY = `{ core_app_catalog { name title description path version installed_at updated_at } }`
export const APPS_QUERY_LEADER = `{ core_app_catalog {
  name title description path version installed_at updated_at manifest_sha256 removed_at } }`

export const APP_LEADERS: readonly Role[] = ['director', 'tenant_admin']

export function isAppLeader(role: Role | null | undefined): boolean {
  return !!role && APP_LEADERS.includes(role)
}

export function appsQuery(role: Role | null | undefined): string {
  return isAppLeader(role) ? APPS_QUERY_LEADER : APPS_QUERY
}

// Một dòng core.app_catalog; hai cột cuối chỉ có khi vai trò được đọc
export interface InstalledApp {
  name: string
  title: string
  description: string | null
  path: string
  version: string
  installed_at: string
  updated_at: string
  manifest_sha256?: string
  removed_at?: string | null
}

// Ứng dụng có sẵn trong lõi. Tên, mô tả: apps.builtin.<key>.title|description. Test đối chiếu: tên trong RESERVED_NAMES
// và đường trong RESERVED_PATHS của scripts/ung_dung.py, route APISIX, service compose chạy image thẻ MOC_VERSION
export const BUILTIN_APPS = [
  { name: 'office', key: 'office', href: '/', service: 'app-office' },
  { name: 'ca-nhan', key: 'personal', href: '/ca-nhan/', service: 'app-ca-nhan' },
] as const

export type AppState = 'builtin' | 'installed' | 'removed'

export interface CatalogEntry {
  name: string
  title: string
  description: string | null
  path: string
  href: string | null          // null: đã gỡ (route đã mất) hoặc đường không đúng khuôn
  internal: boolean            // trang của chính Văn phòng điện tử: chuyển trang không tải lại
  version: string | null       // null: không biết (ứng dụng có sẵn khi /api/status không trả lời)
  installedAt: string | null
  updatedAt: string | null     // chỉ khi khác lúc cài và lúc gỡ
  removedAt: string | null
  sha256: string | null
  state: AppState
}

export interface Catalog {
  builtin: CatalogEntry[]
  installed: CatalogEntry[]
  removed: CatalogEntry[]
}

// Đúng CHECK của core.apps.path (migration 1792281603200, test so): chỉ đường như vậy mới thành liên kết
export const APP_PATH = /^\/[a-z][a-z0-9]*(-[a-z0-9]+)*$/

export function appHref(path: string): string | null {
  return APP_PATH.test(path) ? `${path}/` : null
}

export function shortHash(sha256: string): string {
  return sha256.length > 12 ? `${sha256.slice(0, 12)}…` : sha256
}

function entry(row: InstalledApp): CatalogEntry {
  const removedAt = row.removed_at ?? null
  return {
    name: row.name,
    title: row.title,
    description: row.description,
    path: row.path,
    href: removedAt ? null : appHref(row.path),
    internal: false,
    version: row.version,
    installedAt: row.installed_at,
    updatedAt: row.updated_at !== row.installed_at && row.updated_at !== removedAt ? row.updated_at : null,
    removedAt,
    sha256: row.manifest_sha256 ?? null,
    state: removedAt ? 'removed' : 'installed',
  }
}

// Có sẵn theo thứ tự khai; đã cài theo tên; đã gỡ: gỡ gần nhất trước
export function appCatalog(t: (key: string) => string, rows: InstalledApp[], coreVersion: string | null): Catalog {
  const builtin = BUILTIN_APPS.map((b): CatalogEntry => ({
    name: b.name,
    title: t(`apps.builtin.${b.key}.title`),
    description: t(`apps.builtin.${b.key}.description`),
    path: b.href,
    href: b.href,
    internal: b.href === '/',
    version: coreVersion,
    installedAt: null,
    updatedAt: null,
    removedAt: null,
    sha256: null,
    state: 'builtin',
  }))
  const entries = rows.map(entry)
  const installed = entries.filter((e) => e.state === 'installed')
    .sort((a, b) => a.title.localeCompare(b.title, 'vi') || a.name.localeCompare(b.name))
  const removed = entries.filter((e) => e.state === 'removed')
    .sort((a, b) => Date.parse(b.removedAt!) - Date.parse(a.removedAt!) || a.name.localeCompare(b.name))
  return { builtin, installed, removed }
}
