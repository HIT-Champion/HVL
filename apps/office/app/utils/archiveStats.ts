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

// Số liệu văn bản đã nộp lưu trên trang Điều hành (#304): svc-files GET /api/case-files/archive-stats — DuckDB đếm
// trên các gói Parquet trong bucket lạnh (svc_files/archive_stats.py). Ở đây chỉ dựng hàng cho biểu đồ, bảng: điền
// năm trống, gắn tên loại văn bản, tên phòng (đọc từ Hasura). Không phụ thuộc Vue: chạy được thẳng bằng node --test.

export interface ArchiveYear { year: number | null; incoming: number; outgoing: number }
export interface ArchiveType { type_code: string; incoming: number; outgoing: number }
export interface ArchiveDepartment { department_id: string | null; case_files: number; documents: number }

export interface ArchiveStats {
  case_files: number           // hồ sơ có gói đọc được, khớp băm
  documents: number
  incoming: number
  outgoing: number
  by_year: ArchiveYear[]
  by_type: ArchiveType[]
  by_department: ArchiveDepartment[]
  unreadable: { case_file_id: string; code: string }[]   // gói lệch băm, thiếu: không vào số liệu
  bucket: string
  computed_at: string
}

// Năm liền nhau từ năm sớm nhất tới muộn nhất (năm không có văn bản vẫn có cột, như tháng ở biểu đồ nóng); dòng không
// rõ năm (null) ở cuối. Khoảng quá MAX_YEAR_GAP năm thì chỉ giữ các năm có số, để trục không thành hàng trăm cột.
export const MAX_YEAR_GAP = 30

export function yearRows(rows: ArchiveYear[]): ArchiveYear[] {
  const known = rows.filter((r) => r.year !== null).sort((a, b) => a.year! - b.year!)
  const unknown = rows.filter((r) => r.year === null)
  if (!known.length) return unknown
  const first = known[0]!.year!
  const last = known[known.length - 1]!.year!
  if (last - first > MAX_YEAR_GAP) return [...known, ...unknown]
  const byYear = new Map(known.map((r) => [r.year, r]))
  const filled = Array.from({ length: last - first + 1 }, (_, i) => byYear.get(first + i)
    ?? { year: first + i, incoming: 0, outgoing: 0 })
  return [...filled, ...unknown]
}

export interface NamedType extends ArchiveType { name: string; total: number }
export interface NamedDepartment extends ArchiveDepartment { name: string | null }

/** Loại văn bản kèm tên (office.document_types); mã không có trong danh mục thì giữ mã làm tên. */
export function typeRows(rows: ArchiveType[], names: Map<string, string>): NamedType[] {
  return rows.map((r) => ({ ...r, name: names.get(r.type_code) ?? r.type_code, total: r.incoming + r.outgoing }))
}

/** Phòng lập hồ sơ kèm tên (office.departments); không có phòng, hay phòng không còn trong danh bạ thì tên null. */
export function departmentRows(rows: ArchiveDepartment[], names: Map<string, string>): NamedDepartment[] {
  return rows.map((r) => ({ ...r, name: r.department_id === null ? null : names.get(r.department_id) ?? null }))
}

export function isEmptyArchive(stats: ArchiveStats): boolean {
  return stats.case_files === 0 && stats.unreadable.length === 0
}
