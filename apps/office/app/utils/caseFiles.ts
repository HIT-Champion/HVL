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

// Hồ sơ công việc và nộp lưu (F3.8): phần tính toán thuần của màn Hồ sơ, tách ra để kiểm thử. Quy tắc chép đúng quyền
// Hasura (db/metadata: office_case_files.yaml, office_case_file_documents.yaml), trigger của migration
// 1792281601300_case_files và svc-files (archive.py, app.py) — chỉ để ẩn nút không dùng được; máy chủ vẫn kiểm lại.

export type CaseFileStatus = 'open' | 'closed' | 'archived'

export interface Viewer {
  role: string | null
  departmentId: string | null
  userId: string
}

export interface CaseFileScope {
  status: CaseFileStatus
  department_id: string
}

const OWNERS = new Set(['staff', 'manager'])
// Hồ sơ bảo quản vĩnh viễn (retention_years null) khóa ghi 100 năm — archive.PERMANENT_YEARS
export const PERMANENT_YEARS = 100
// Thời hạn bảo quản chọn được trên form (năm); CSDL nhận 1–100 hoặc null (vĩnh viễn)
export const RETENTION_CHOICES = [5, 10, 15, 20, 30, 50, 70] as const

/** Màu nhãn trạng thái hồ sơ (danh sách, trang hồ sơ). */
export const STATUS_TONE: Record<CaseFileStatus, string> = {
  open: 'bg-stone-100 text-stone-700', closed: 'bg-sky-100 text-sky-800', archived: 'bg-emerald-100 text-emerald-800',
}

/** Lập hồ sơ: chuyên viên, lãnh đạo phòng — hồ sơ của phòng mình (Hasura đặt department_id từ phiên). */
export function canCreate(v: Viewer): boolean {
  return OWNERS.has(v.role ?? '') && !!v.departmentId
}

/** Thêm, gỡ văn bản, đóng hồ sơ: chuyên viên, lãnh đạo phòng của phòng có hồ sơ, khi hồ sơ còn mở. */
export function canEdit(v: Viewer, cf: CaseFileScope): boolean {
  return canCreate(v) && cf.department_id === v.departmentId && cf.status === 'open'
}

/** Nộp lưu ngay (POST /api/case-files/{id}/archive): lãnh đạo phòng của phòng có hồ sơ, hồ sơ đã đóng. */
export function canArchive(v: Viewer, cf: CaseFileScope): boolean {
  return v.role === 'manager' && !!v.departmentId && cf.department_id === v.departmentId && cf.status === 'closed'
}

/** Mẫu _ilike "chứa chuỗi" của Hasura: % và _ người dùng gõ là chữ thường, không phải ký tự đại diện. */
export function containsPattern(text: string): string {
  return `%${text.trim().replace(/[\\%_]/g, (c) => `\\${c}`)}%`
}

/**
 * Điều kiện (where của Hasura) cho văn bản đưa vào hồ sơ được: đúng check khi thêm (văn bản mình đọc được, thuộc phòng
 * mình — văn bản của phòng, hay giao cho phòng, cho mình) và trigger (đến đã xong, đi đã phát hành, không hạn chế).
 * query: lọc thêm theo số ký hiệu hoặc trích yếu. Văn bản đã thuộc hồ sơ khác thì CSDL từ chối (mỗi văn bản một hồ sơ).
 */
export function fileableWhere(v: Viewer, query = ''): Record<string, unknown> {
  const pattern = containsPattern(query)
  return {
    _and: [
      { restricted: { _eq: false } },
      {
        _or: [
          { direction: { _eq: 'in' }, status: { _eq: 'done' } },
          { direction: { _eq: 'out' }, status: { _eq: 'issued' } },
        ],
      },
      {
        _or: [
          { department_id: { _eq: v.departmentId } },
          { assignments: { department_id: { _eq: v.departmentId } } },
          { assignments: { user_id: { _eq: v.userId } } },
        ],
      },
      ...(query.trim() ? [{ _or: [{ symbol: { _ilike: pattern } }, { summary: { _ilike: pattern } }] }] : []),
    ],
  }
}

export interface CaseFileForm {
  year: number | string
  code: string
  title: string
  retention: string // số năm, hoặc 'permanent'
}

export interface CaseFileInput {
  year: number
  code: string
  title: string
  retention_years: number | null
}

/** Lỗi của form lập hồ sơ theo ràng buộc CSDL: trường → khóa câu (cases.validation.*). Rỗng là hợp lệ. */
export function validateCaseFile(form: CaseFileForm): Record<string, string> {
  const errors: Record<string, string> = {}
  const year = Number(form.year)
  if (!Number.isInteger(year) || year < 2000 || year > 2999) errors.year = 'year'
  if (!form.code.trim()) errors.code = 'code'
  const title = form.title.trim().length
  if (title < 5 || title > 500) errors.title = 'title'
  if (form.retention !== 'permanent') {
    const years = Number(form.retention)
    if (!Number.isInteger(years) || years < 1 || years > 100) errors.retention = 'retention'
  }
  return errors
}

/** Thân insert_office_case_files_one từ form đã hợp lệ (tenant, phòng, người lập do Hasura đặt từ phiên). */
export function caseFileInput(form: CaseFileForm): CaseFileInput {
  return {
    year: Number(form.year),
    code: form.code.trim(),
    title: form.title.trim(),
    retention_years: form.retention === 'permanent' ? null : Number(form.retention),
  }
}

/**
 * Hạn khóa ghi của gói lưu trữ (YYYY-MM-DD) như archive.py tính: ngày đóng hồ sơ cộng thời hạn bảo quản theo năm lịch
 * (29/02 sang năm không nhuận thành 28/02), vĩnh viễn thì 100 năm. Máy chủ còn giữ tối thiểu tới hết ngày mai nếu hạn
 * đã qua — chỉ dùng để hiện "dự kiến" trước khi nộp lưu; sau khi nộp lưu, hạn thật đọc từ manifest.
 */
export function retainUntil(closedOn: string, years: number | null): string {
  const [y, m, d] = closedOn.split('-').map(Number) as [number, number, number]
  const year = y + (years ?? PERMANENT_YEARS)
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0
  const day = m === 2 && d === 29 && !leap ? 28 : d
  return `${String(year).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/** Băm SHA-256 Hasura trả cho cột bytea dạng "\x…" → hex thường; null giữ null. */
export function hexOf(bytea: string | null | undefined): string | null {
  return bytea ? bytea.trim().replace(/^\\x/i, '').toLowerCase() : null
}

/** Phòng đọc chỉ mở bản PDF (svc-files đóng dấu người xem lên PDF); tệp khác chỉ hiện băm, cỡ. */
export function isViewable(mime: string | null | undefined): boolean {
  return mime === 'application/pdf'
}

// Lỗi ràng buộc CSDL (Hasura trả tên ràng buộc trong câu lỗi) → khóa câu cases.error.*
const CONSTRAINT_KEYS: Array<[string, string]> = [
  ['case_files_tenant_id_year_code_key', 'duplicateCode'],
  ['case_file_documents_document_id_key', 'alreadyFiled'],
  ['case_file_documents_pkey', 'alreadyFiled'],
  ['case_files_title_check', 'titleLength'],
  ['case_files_code_check', 'codeRequired'],
]

// Mã lỗi svc-files của nộp lưu, phòng đọc có câu riêng; archive_failed hiện nguyên câu của máy chủ (nêu văn bản nào)
const SERVICE_CODES = new Set(['forbidden', 'not_found', 'not_closed', 'already_archived', 'archive_conflict',
  'not_archived', 'busy', 'not_viewable', 'unstampable', 'archive_mismatch', 'storage_unavailable',
  'database_unavailable'])

/** Khóa câu (cases.error.*) cho một lỗi: theo mã của svc-files, hoặc theo tên ràng buộc trong câu lỗi của Hasura. */
export function caseFileErrorKey(code: string | null | undefined, message = ''): string | null {
  if (code && SERVICE_CODES.has(code)) return code
  for (const [name, key] of CONSTRAINT_KEYS) if (message.includes(name)) return key
  return null
}

/** Câu lỗi cho người dùng: cases.error.* khi biết mã hay tên ràng buộc, không thì `fallback` (errorText của
 *  utils/errors — mạng, phiên đăng nhập, câu lỗi tiếng Việt của trigger). */
export function caseFileErrorText(t: (key: string) => string, e: unknown, fallback: (e: unknown) => string): string {
  const err = typeof e === 'object' && e !== null ? e as { code?: string | null, message?: string } : null
  const key = err ? caseFileErrorKey(err.code, err.message ?? '') : null
  return key ? t(`cases.error.${key}`) : fallback(e)
}

export interface ArchivedFileRef {
  file_id: string
  document_ids: string[]
}

/** Tệp trong gói theo văn bản (một tệp gắn nhiều văn bản thì hiện ở mỗi văn bản), giữ thứ tự của manifest. */
export function filesByDocument<T extends ArchivedFileRef>(files: T[]): Map<string, T[]> {
  const out = new Map<string, T[]>()
  for (const f of files) {
    for (const doc of f.document_ids) out.set(doc, [...(out.get(doc) ?? []), f])
  }
  return out
}
