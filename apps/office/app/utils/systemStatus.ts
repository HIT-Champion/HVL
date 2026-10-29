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

import type { OpenDataSource } from './openData'

// Trang trạng thái hệ thống (/trang-thai, công khai): dạng dữ liệu GET /api/status của svc-files và các hàm dựng trang.
// svc-files lưu đệm 10 giây, APISIX giới hạn theo IP (MOC_RATE_STATUS_PER_MIN, mặc định 30/phút): trang tự làm mới
// mỗi 30 giây là 2 lần mỗi phút một tab.

export const STATUS_REFRESH_MS = 30_000

export type ComponentState = 'ok' | 'degraded' | 'down' | 'off'
export type OverallState = 'ok' | 'degraded' | 'down'

export interface StatusComponent {
  id: string
  layer: string
  label: string
  software: string
  status: ComponentState
}

export interface SystemStatus {
  status: OverallState
  checked_at: string
  version: string
  uptime_s: number
  last_backup_at: string | null
  ai: { enabled: boolean; model: string | null; semantic: boolean }
  layers: { id: string; label: string }[]
  components: StatusComponent[]
  // nguồn dữ liệu công khai và tuổi dữ liệu; bản svc-files cũ chưa có khóa này (đọc bằng openDataOf)
  open_data?: OpenDataSource[]
}

export interface StatusGroup {
  id: string
  label: string
  components: StatusComponent[]
}

// Thành phần theo tầng, đúng thứ tự `layers` (người dùng → lõi → quy trình → dữ liệu → trí tuệ nhân tạo); thành phần
// mang tầng lạ (bản svc-files mới hơn giao diện) vẫn hiện, ở cuối
export function groupByLayer(data: Pick<SystemStatus, 'layers' | 'components'>): StatusGroup[] {
  const groups: StatusGroup[] = data.layers.map((l) => ({ ...l, components: [] }))
  for (const c of data.components) {
    let group = groups.find((g) => g.id === c.layer)
    if (!group) {
      group = { id: c.layer, label: c.layer, components: [] }
      groups.push(group)
    }
    group.components.push(c)
  }
  return groups.filter((g) => g.components.length)
}

// Thời gian chạy liên tục: hai đơn vị lớn nhất khác 0, vd "3 ngày 4 giờ", "5 giờ 12 phút"; dưới một phút thì `less`
export function fmtUptime(seconds: number, units: { day: string; hour: string; minute: string; less: string }): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return units.less
  const parts: [number, string][] = [[Math.floor(s / 86_400), units.day], [Math.floor(s / 3600) % 24, units.hour],
    [Math.floor(s / 60) % 60, units.minute]]
  const first = parts.findIndex(([n]) => n > 0)
  return parts.slice(first, first + 2).filter(([n]) => n > 0).map(([n, u]) => `${n} ${u}`).join(' ')
}

// Giờ:phút:giây theo giờ Việt Nam (như fmtDateTime), cho dòng "kiểm lúc"
export function fmtClock(value: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).format(new Date(value))
}

// Màu theo trạng thái: chấm và nhãn của từng thành phần, khung của dòng tổng
export const STATE_TONE: Record<ComponentState, { dot: string; chip: string }> = {
  ok: { dot: 'bg-emerald-500', chip: 'bg-emerald-100 text-emerald-800' },
  degraded: { dot: 'bg-amber-500', chip: 'bg-amber-100 text-amber-800' },
  down: { dot: 'bg-red-500', chip: 'bg-red-100 text-red-800' },
  off: { dot: 'bg-stone-300', chip: 'bg-stone-100 text-stone-600' },
}

export const OVERALL_TONE: Record<OverallState, string> = {
  ok: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  degraded: 'border-amber-200 bg-amber-50 text-amber-900',
  down: 'border-red-200 bg-red-50 text-red-900',
}
