// Copyright 2026 Mộc Team
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

// Định dạng ngày giờ theo kiểu Việt Nam (dd/mm/yyyy), dùng chung cho mọi trang.

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value)
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(d)
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

// Hôm nay theo giờ Việt Nam (YYYY-MM-DD), như svc-workflow và CSDL — không theo múi giờ của máy người dùng
export function today(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date())
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// Số đo (nhiệt độ cảm biến…) theo kiểu Việt Nam: 41,5
export function fmtNumber(value: unknown): string {
  const n = Number(value)
  return Number.isFinite(n) ? new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(n) : '—'
}

export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
