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

// Nguồn dữ liệu công khai (đề trường mục 3.3): mỗi nguồn là một bản chụp trong seed/du-lieu-mo/<nguồn>/ kèm
// manifest.json (URL, ngày lấy, căn cứ dùng lại, SHA-256 từng tệp). Bản cài không gọi nguồn lúc chạy; svc-files đọc
// các manifest và trả khóa open_data trong GET /api/status (công khai). Trang Trạng thái liệt kê nguồn và tuổi dữ liệu;
// trang văn bản nhận ra văn bản nạp từ nguồn công khai khi SHA-256 của một tệp đính kèm trùng một tệp của nguồn.
// Tệp này không dùng gì của Nuxt để Node chạy test được (tests/openData.test.ts).

import { sameSha256 } from './dispatch.ts'

export type OpenDataState = 'ok' | 'stale' | 'broken'

export interface OpenDataFile {
  file: string
  url: string
  sha256: string
  fetched_at: string
  meta: Record<string, unknown>   // tùy nguồn; nguồn Công báo có symbol, issued_on, page_url, gazette…
}

export interface OpenDataSource {
  source: string                  // mã nguồn, cũng là tên thư mục bản chụp
  name: string
  publisher: string
  home_url: string
  reuse_basis: string             // căn cứ dùng lại: giấy phép hoặc điều luật
  licence: string | null
  fetched_at: string
  age_days: number
  max_age_days: number
  state: OpenDataState            // stale: quá max_age_days chưa lấy lại; broken: manifest hỏng, thiếu tệp, sai băm
  files: OpenDataFile[]
}

const STATES: readonly OpenDataState[] = ['ok', 'stale', 'broken']

const text = (v: unknown): string => (typeof v === 'string' ? v : '')

/** Liên kết ra ngoài chỉ nhận http(s): chữ trong manifest không bao giờ thành javascript: hay data: trên trang. */
export function safeUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

/** Danh sách nguồn trong kết quả GET /api/status. svc-files chưa có nguồn nào hoặc bản cũ chưa có khóa open_data thì
 *  là mảng rỗng; mục thiếu mã nguồn bị bỏ, trường thiếu thành chuỗi rỗng, trạng thái lạ coi như hỏng. */
export function openDataOf(status: unknown): OpenDataSource[] {
  const list = (status as { open_data?: unknown } | null)?.open_data
  if (!Array.isArray(list)) return []
  return list.filter((s): s is Record<string, unknown> => !!s && typeof s === 'object' && !!text(s.source))
    .map((s) => ({
      source: text(s.source),
      name: text(s.name) || text(s.source),
      publisher: text(s.publisher),
      home_url: text(s.home_url),
      reuse_basis: text(s.reuse_basis),
      licence: typeof s.licence === 'string' && s.licence ? s.licence : null,
      fetched_at: text(s.fetched_at),
      age_days: Number.isFinite(s.age_days) ? Math.max(0, Math.floor(s.age_days as number)) : 0,
      max_age_days: Number.isFinite(s.max_age_days) ? Math.max(0, Math.floor(s.max_age_days as number)) : 0,
      state: STATES.includes(s.state as OpenDataState) ? s.state as OpenDataState : 'broken',
      files: (Array.isArray(s.files) ? s.files : [])
        .filter((f): f is Record<string, unknown> => !!f && typeof f === 'object' && !!text(f.sha256))
        .map((f) => ({
          file: text(f.file),
          url: text(f.url),
          sha256: text(f.sha256),
          fetched_at: text(f.fetched_at),
          meta: f.meta && typeof f.meta === 'object' && !Array.isArray(f.meta) ? f.meta as Record<string, unknown> : {},
        })),
    }))
}

/** Văn bản nạp từ nguồn công khai: nguồn, tệp của nguồn, liên kết trang gốc (trang văn bản trên Công báo, không có
 *  thì địa chỉ tải tệp), số Công báo, ngày lấy của tệp. */
export interface PublicOrigin {
  source: OpenDataSource
  file: OpenDataFile
  link: string | null
  gazette: string
  fetched_at: string
}

/** Tệp đính kèm nào của văn bản trùng SHA-256 với một tệp của nguồn công khai (Hasura trả băm dạng "\x…"). Nguồn hỏng
 *  (broken) không tính: băm của nó chưa đáng tin. */
export function publicOrigin(hashes: readonly (string | null | undefined)[],
  sources: readonly OpenDataSource[]): PublicOrigin | null {
  for (const hash of hashes) {
    for (const source of sources) {
      if (source.state === 'broken') continue
      const file = source.files.find((f) => sameSha256(hash, f.sha256))
      if (file) {
        return {
          source, file, link: safeUrl(file.meta.page_url) ?? safeUrl(file.url),
          gazette: text(file.meta.gazette), fetched_at: file.fetched_at || source.fetched_at,
        }
      }
    }
  }
  return null
}

/** SHA-256 viết liền 64 ký tự, chữ thường, bỏ tiền tố "\x" của Hasura: hiện để người đọc so với manifest. */
export function hexOf(hash: string | null | undefined): string {
  return (hash ?? '').trim().replace(/^\\x/i, '').toLowerCase()
}

// Màu theo trạng thái của nguồn, cùng thang với thành phần ở trang Trạng thái
export const OPEN_DATA_TONE: Record<OpenDataState, string> = {
  ok: 'bg-emerald-100 text-emerald-800',
  stale: 'bg-amber-100 text-amber-800',
  broken: 'bg-red-100 text-red-800',
}

// Trang văn bản hỏi /api/status (công khai, svc-files lưu đệm 10 giây, APISIX giới hạn 30 lượt/phút mỗi IP) một lần
// rồi dùng lại trong 5 phút cho mọi trang văn bản mở sau đó; tải lỗi thì không giữ, lần sau hỏi lại
export const OPEN_DATA_TTL_MS = 5 * 60_000
let cached: { at: number; sources: Promise<OpenDataSource[]> } | null = null

export function loadOpenData(get: (url: string) => Promise<{ ok: boolean; json(): Promise<unknown> }>,
  now: () => number = Date.now): Promise<OpenDataSource[]> {
  if (cached && now() - cached.at < OPEN_DATA_TTL_MS) return cached.sources
  const entry = {
    at: now(),
    sources: get('/api/status').then(async (res) => {
      if (!res.ok) throw new Error('status')
      return openDataOf(await res.json())
    }).catch(() => {
      if (cached === entry) cached = null
      return [] as OpenDataSource[]
    }),
  }
  cached = entry
  return entry.sources
}
