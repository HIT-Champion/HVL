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

// Gợi ý giao việc (F4.3): phần thuần của khối "Gợi ý giao việc" ở bước chỉ đạo. Tác tử moc-assigner (svc-workflow)
// chạy song song từ lúc vào sổ, ghi một dòng office.assignment_suggestions cho mỗi văn bản đến: đơn vị chủ trì, hạn
// đề xuất, độ tin cậy, căn cứ (id các văn bản tương tự đã giao — chỉ id và số, không có chữ). Giao diện chỉ hiện căn
// cứ người xem đọc được, và "Dùng gợi ý" chỉ điền form — lãnh đạo vẫn là người bấm "Giao xử lý".
// Tệp này không dùng gì của Nuxt để Node chạy test được (tests/assignSuggest.test.ts).

// Hỏi lại 3 giây một lần khi chưa có dòng gợi ý, chỉ trong 60 giây đầu kể từ lúc vào sổ: tác tử thường xong sau vài
// giây; quá 60 giây vẫn chưa có thì coi như không có (svc-files tắt, svc-workflow dừng vòng nền) và thôi không hiện
export const POLL_MS = 3000
export const WAIT_MS = 60000
// Trần số lần hỏi kể từ lúc mở form: đồng hồ máy người xem chạy chậm thì "60 giây từ lúc vào sổ" không bao giờ hết
export const MAX_POLLS = Math.ceil(WAIT_MS / POLL_MS)
// Số căn cứ hiện thành liên kết; độ dài trích yếu của mỗi căn cứ
export const MAX_EVIDENCE = 3
export const SUMMARY_MAX = 80

export type SuggestStatus = 'suggested' | 'none' | 'failed'
export type SuggestConfidence = 'high' | 'medium' | 'low'

// Lý do không có gợi ý (CSDL ràng buộc đúng danh sách này: assignment_suggestions_shape)
export const SUGGEST_REASONS = ['no_similar', 'no_history', 'no_valid_unit', 'low_confidence', 'timeout', 'unavailable'] as const
export type SuggestReason = (typeof SUGGEST_REASONS)[number]

/** Một căn cứ trong cột evidence (jsonb): văn bản tương tự đã giao, điểm tìm kiếm, đơn vị chủ trì, số ngày đã giao. */
export interface SuggestEvidence {
  document_id: string
  score: number
  department_id: string | null
  days: number | null
}

/** Dòng office.assignment_suggestions người xem (lãnh đạo đơn vị) đọc được. */
export interface AssignSuggestionRow {
  status: SuggestStatus
  reason: string | null
  department_id: string | null
  confidence: SuggestConfidence | null
  share: number | null
  due_days: number | null
  due_on: string | null
  evidence: unknown
  created_at: string
}

/** Văn bản căn cứ người xem đọc được (kết quả truy vấn CanCuGoiY bằng token của chính người xem). */
export interface SuggestReadable { symbol: string | null; summary: string | null }

export interface ShownEvidence extends SuggestEvidence { symbol: string | null; summary: string }

/** Giá trị "Dùng gợi ý" điền vào form chỉ đạo; due_on null = giữ hạn đang có trong form. */
export interface SuggestApply { department_id: string; due_on: string | null }

/**
 * Còn hỏi lại không: đã có dòng (gợi ý, không gợi ý, lỗi) thì thôi; chưa có thì hỏi tiếp khi văn bản vào sổ chưa
 * quá WAIT_MS. Không biết lúc vào sổ thì thôi.
 */
export function pollState(row: unknown, registeredAt: string | null | undefined, now: number): 'wait' | 'stop' {
  if (row) return 'stop'
  const at = registeredAt ? Date.parse(registeredAt) : Number.NaN
  if (!Number.isFinite(at)) return 'stop'
  return now - at < WAIT_MS ? 'wait' : 'stop'
}

// Bảng màu như nhãn gợi ý của form tiếp nhận (SuggestTag.vue): cao = xanh lục, vừa = hổ phách, thấp = xám đá.
// Chip luôn ghi chữ ("Tin cậy cao"…), màu chỉ là phần thêm.
const TONES: Record<SuggestConfidence, string> = {
  high: 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-300',
  medium: 'bg-amber-50 text-amber-900 ring-1 ring-amber-300',
  low: 'bg-stone-100 text-stone-700 ring-1 ring-stone-300',
}

/** Lớp màu của chip độ tin cậy; giá trị lạ thì như "thấp". */
export function confidenceTone(c: string | null | undefined): string {
  return c === 'high' || c === 'medium' ? TONES[c] : TONES.low
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Đọc cột evidence (jsonb) cho chắc: chỉ giữ phần tử có id văn bản dạng uuid và điểm là số, không trùng id; xếp theo
 * điểm giảm dần (hòa điểm giữ thứ tự ghi trong CSDL). Phần tử sai dạng bị bỏ, không làm hỏng cả khối.
 */
export function readEvidence(evidence: unknown): SuggestEvidence[] {
  if (!Array.isArray(evidence)) return []
  const seen = new Set<string>()
  const out: SuggestEvidence[] = []
  for (const item of evidence as unknown[]) {
    if (!item || typeof item !== 'object') continue
    const e = item as Record<string, unknown>
    const id = e.document_id
    const score = e.score
    if (typeof id !== 'string' || !UUID.test(id) || seen.has(id)) continue
    if (typeof score !== 'number' || !Number.isFinite(score)) continue
    seen.add(id)
    const days = e.days
    out.push({
      document_id: id, score,
      department_id: typeof e.department_id === 'string' && e.department_id ? e.department_id : null,
      days: typeof days === 'number' && Number.isInteger(days) && days > 0 ? days : null,
    })
  }
  // sort của JS ổn định: hòa điểm giữ thứ tự cũ
  return out.sort((a, b) => b.score - a.score)
}

/** id các căn cứ để hỏi lại bằng token người xem (truy vấn CanCuGoiY). */
export function evidenceIds(evidence: unknown): string[] {
  return readEvidence(evidence).map((e) => e.document_id)
}

/** Trích yếu ngắn cho dòng căn cứ: NFC, gộp khoảng trắng, quá max ký tự thì cắt và thêm "…". */
export function clipSummary(text: string | null | undefined, max = SUMMARY_MAX): string {
  const clean = (text ?? '').normalize('NFC').replace(/\s+/gu, ' ').trim()
  const chars = Array.from(clean)
  if (chars.length <= max) return clean
  return `${chars.slice(0, max - 1).join('').trimEnd()}…`
}

/**
 * Căn cứ hiện thành liên kết: theo thứ tự điểm, bỏ văn bản người xem không đọc được (không có trong `readable` — kết
 * quả hỏi bằng token của chính người xem, đã loại văn bản hạn chế), tối đa `max` văn bản.
 */
export function shownEvidence(evidence: unknown, readable: ReadonlyMap<string, SuggestReadable>,
  max = MAX_EVIDENCE): ShownEvidence[] {
  const out: ShownEvidence[] = []
  for (const e of readEvidence(evidence)) {
    if (out.length >= max) break
    const doc = readable.get(e.document_id)
    if (!doc) continue
    out.push({ ...e, symbol: doc.symbol?.trim() || null, summary: clipSummary(doc.summary) })
  }
  return out
}

const DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Giá trị "Dùng gợi ý" điền vào form: đơn vị chủ trì, và hạn khi văn bản không ghi hạn (hạn ghi trên văn bản thắng
 * thói quen nội bộ; tác tử cũng không gợi ý hạn khi đó). Hạn gợi ý đã qua (mở việc muộn nhiều ngày) thì không điền —
 * form sẽ báo lỗi "hạn trước hôm nay". Không phải dòng "suggested" thì null.
 */
export function applyValues(s: Pick<AssignSuggestionRow, 'status' | 'department_id' | 'due_on'> | null | undefined,
  documentDue: string | null | undefined, today?: string): SuggestApply | null {
  if (!s || s.status !== 'suggested' || !s.department_id) return null
  let due = documentDue ? null : s.due_on
  if (due && (!DATE.test(due) || (today && due < today))) due = null
  return { department_id: s.department_id, due_on: due ?? null }
}

/**
 * Lãnh đạo đang theo hay lệch gợi ý: chosen là phòng chủ trì đang chọn trong form (null khi chưa chọn, hoặc giao
 * cho một người). null: không hiện chip.
 */
export function matchState(s: Pick<AssignSuggestionRow, 'status' | 'department_id'> | null | undefined,
  chosen: string | null | undefined): 'kept' | 'changed' | null {
  if (!s || s.status !== 'suggested' || !s.department_id || !chosen) return null
  return chosen === s.department_id ? 'kept' : 'changed'
}

/** Khóa i18n của lý do không có gợi ý; lý do lạ thì null (giao diện ghi chung "không có gợi ý"). */
export function reasonKey(reason: string | null | undefined): string | null {
  return reason && (SUGGEST_REASONS as readonly string[]).includes(reason) ? `assign.suggest.reason.${reason}` : null
}
