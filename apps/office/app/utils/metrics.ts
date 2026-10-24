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

// Số đo "sau" của đặc tả §8 (F4.6) trên trang Số đo, cho lãnh đạo đơn vị. Cách đo và cách đọc: docs/so-lieu-sau.md.
// - (a), (b) đọc từ office.v_time_to_assign, office.v_overdue_rate (migration 1792281602750): một dòng mỗi tháng và một
//   dòng month null tính lại trên mọi văn bản.
// - (c) bấm giờ 5 lần tìm thật ngay trên trình duyệt, mỗi lần tìm số ký hiệu của một văn bản đến cũ nhất: là độ trễ hệ
//   thống (gọi /api/search qua APISIX tới khi có kết quả), không gồm thời gian người gõ, đọc, bấm.
// - (d) số bước chuyển tay chỉ so sánh định tính, không có số.
// Cột "trước" là số đo ở đơn vị chạy thử: chưa có đơn vị nào nên luôn là "chưa đo" — không điền số nào khác.

export interface AssignRow {
  sample: boolean
  month: string | null
  arrived: number
  assigned: number
  median_hours: number | null
  p90_hours: number | null
  handled: number
  handled_median_hours: number | null
  handled_p90_hours: number | null
  waiting: number
}

export interface OverdueRow {
  sample: boolean
  month: string | null
  judged: number
  on_time: number
  late: number
  late_open: number
  pending: number
}

export const SEARCH_RUNS = 5

export interface SearchTarget {
  id: string
  symbol: string
}

export interface SearchRun extends SearchTarget {
  ms: number
  rank: number | null // vị trí của văn bản cần tìm trong kết quả, 1 là đầu; null: không thấy
}

// Văn bản cần tìm lại: văn bản đến cũ nhất trước (danh sách đã xếp theo lúc tạo), mỗi số ký hiệu một lần
export function pickSearchTargets(docs: { id: string; symbol: string | null }[], n = SEARCH_RUNS): SearchTarget[] {
  const seen = new Set<string>()
  const out: SearchTarget[] = []
  for (const d of docs) {
    const symbol = d.symbol?.trim()
    if (!symbol || seen.has(symbol)) continue
    seen.add(symbol)
    out.push({ id: d.id, symbol })
    if (out.length === n) break
  }
  return out
}

export function rankOf(hits: { id: string }[], id: string): number | null {
  const i = hits.findIndex((h) => h.id === id)
  return i < 0 ? null : i + 1
}

export function median(values: number[]): number | null {
  if (!values.length) return null
  const s = [...values].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2
}

export interface SearchSummary {
  runs: number
  found: number
  median_ms: number | null
  max_ms: number | null
}

export function searchSummary(runs: SearchRun[]): SearchSummary {
  const ms = runs.map((r) => r.ms)
  return {
    runs: runs.length,
    found: runs.filter((r) => r.rank !== null).length,
    median_ms: median(ms),
    max_ms: ms.length ? Math.max(...ms) : null,
  }
}

// Phần trăm quá hạn trong số văn bản đã rõ đúng hay trễ; chưa có văn bản nào thì null (không phải 0 %)
export function overduePct(row: OverdueRow | null | undefined): number | null {
  return row && row.judged ? (row.late / row.judged) * 100 : null
}

export function totalRow<T extends { month: string | null }>(rows: T[]): T | null {
  return rows.find((r) => r.month === null) ?? null
}

// Các tháng có số, mới nhất trước, tối đa n tháng
export function monthRows<T extends { month: string | null }>(rows: T[], n = 12): T[] {
  return rows.filter((r) => r.month !== null).sort((a, b) => (b.month ?? '').localeCompare(a.month ?? '')).slice(0, n)
}

export interface DurationUnits {
  second: string
  minute: string
  hour: string
  day: string
}

// Khoảng thời gian (giờ) đọc được: dưới 1 phút ra giây, dưới 1 giờ ra phút, dưới 2 ngày ra giờ, còn lại ra ngày. Dữ
// liệu mẫu (make seed) đi hết các bước trong vài giây nên phải hiện được giây, không làm tròn thành "0 giờ"
export function fmtDuration(hours: number | null | undefined, units: DurationUnits,
  format: (n: number) => string = (n) => String(Math.round(n * 10) / 10)): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours)) return '—'
  const h = Math.max(0, hours)
  if (h < 1 / 60) return `${format(Math.round(h * 3600))} ${units.second}`
  if (h < 1) return `${format(h * 60)} ${units.minute}`
  if (h < 48) return `${format(h)} ${units.hour}`
  return `${format(h / 24)} ${units.day}`
}

export function fmtMs(ms: number | null | undefined, format: (n: number) => string = (n) => String(Math.round(n))):
  string {
  return ms === null || ms === undefined ? '—' : `${format(ms)} ms`
}

export function isSample(...groups: { sample: boolean }[][]): boolean {
  return groups.some((rows) => rows.some((r) => r.sample))
}
