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

// Định dạng ngày giờ theo kiểu Việt Nam (dd/mm/yyyy), dùng chung cho mọi trang. Luôn theo giờ Việt Nam như
// svc-workflow và CSDL, không theo múi giờ của máy người dùng (đi công tác, máy đặt sai múi giờ).

const VN = 'Asia/Ho_Chi_Minh'

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  // ngày thuần (cột date: ngày ban hành, hạn giải quyết) không gắn múi giờ nào: đọc thẳng
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (day) return `${day[3]}/${day[2]}/${day[1]}`
  return new Intl.DateTimeFormat('vi-VN', { timeZone: VN, day: '2-digit', month: '2-digit', year: 'numeric' })
    .format(new Date(value))
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VN, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

// Hôm nay theo giờ Việt Nam (YYYY-MM-DD)
export function today(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: VN }).format(new Date())
}

// Cộng ngày trên lịch (YYYY-MM-DD), tính theo UTC để không vướng giờ mùa hè của máy người dùng
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

// Số ngày từ hôm nay tới hạn (YYYY-MM-DD): 0 là hạn hôm nay, âm là đã quá hạn bấy nhiêu ngày
export function daysUntil(due: string, day: string): number {
  return Math.round((Date.parse(`${due}T00:00:00Z`) - Date.parse(`${day}T00:00:00Z`)) / 86_400_000)
}

// Số đo (nhiệt độ cảm biến…) theo kiểu Việt Nam: 41,5
export function fmtNumber(value: unknown): string {
  const n = Number(value)
  return Number.isFinite(n) ? new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(n) : '—'
}

// Chữ trong ô đại diện ở đầu trang: chữ đầu của tên, viết hoa — "Giám khảo" ra G, không phải "k" của "khảo" như khi
// lấy từ cuối của họ tên. Thiếu tên thì lấy từ cuối của họ tên
export function initialOf(givenName: string, name: string): string {
  const word = givenName.trim() || name.trim().split(/\s+/).pop() || ''
  return word ? word.charAt(0).toLocaleUpperCase('vi') : '?'
}

export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
