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

// Hỏi đáp trên kho văn bản (F4.2): phần thuần của trang Hỏi đáp. Câu trả lời (câu trích nguyên văn hoặc do mô hình
// viết) là chữ thuần có dấu [n] trỏ tới nguồn thứ n — tách thành đoạn chữ và dấu trích dẫn để giao diện dựng bằng nút
// chữ, không bao giờ dựng HTML từ chữ của văn bản hay của mô hình. Nhãn trích dẫn "88/CTSV · tr. 1", mở được tệp đúng
// trang đó; hỏi trong một văn bản bằng ?van_ban=<id>.
// Tệp này không dùng gì của Nuxt để Node chạy test được (tests/answer.test.ts).

import type { AskAnswer, AskResult, AskSource } from '../composables/useApi'

// Hàm dịch của vue-i18n (useI18n().t), chỉ phần dùng ở đây
export type Translate = (key: string, named?: Record<string, unknown>) => string

export type Segment = { text: string } | { n: number; source: AskSource }

// Độ dài tối đa câu hỏi (svc-files từ chối câu dài hơn: invalid_question)
export const MAX_QUESTION = 500

// [1], hoặc dạng gộp [1, 2] — svc-files đã chuẩn hóa thành [1][2] nhưng giao diện vẫn đọc được dạng gộp
const CITE = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g

/**
 * Tách câu trả lời thành đoạn chữ và dấu trích dẫn. Dấu [n] chỉ thành trích dẫn khi có nguồn số n; không có (mô hình
 * ghi sai, hay chính văn bản có "[5]") thì giữ nguyên là chữ. Dạng gộp [1, 2] thành hai trích dẫn khi đủ nguồn cho
 * mọi số, thiếu một số thì cả cụm giữ là chữ. Đoạn chữ liền nhau được gộp lại.
 */
export function segments(text: string | null | undefined, sources: readonly AskSource[]): Segment[] {
  const out: Segment[] = []
  if (!text) return out
  const byN = new Map(sources.map((s) => [s.n, s]))
  const push = (chunk: string) => {
    if (!chunk) return
    const last = out[out.length - 1]
    if (last && 'text' in last) last.text += chunk
    else out.push({ text: chunk })
  }
  let at = 0
  for (const m of text.matchAll(CITE)) {
    const start = m.index ?? 0
    push(text.slice(at, start))
    const ns = (m[1] ?? '').split(',').map((x) => Number(x.trim()))
    const found = ns.map((n) => byN.get(n))
    if (found.every((s) => s !== undefined)) found.forEach((s, i) => out.push({ n: ns[i]!, source: s! }))
    else push(m[0])
    at = start + m[0].length
  }
  push(text.slice(at))
  return out
}

/**
 * Nhãn trích dẫn của một nguồn: "88/CTSV · tr. 1", "88/CTSV · tài liệu kèm theo, tr. 2", "88/CTSV · trích yếu"
 * (văn bản chưa có chữ — bản scan, tệp lỗi — chỉ trích được trích yếu, không bịa trang). spoken: dạng đọc cho trình
 * đọc màn hình ("88/CTSV, trang 1"). Văn bản chưa có số ký hiệu thì dùng tên loại.
 */
export function citeLabel(source: Pick<AskSource, 'symbol' | 'type_name' | 'type_code' | 'kind' | 'file_role' | 'page'>,
  t: Translate, spoken = false): string {
  const name = source.symbol?.trim() || source.type_name?.trim() || source.type_code
  const where: string[] = []
  if (source.kind === 'meta') where.push(t('assist.summaryOnly'))
  else {
    if (source.file_role === 'attachment') where.push(t('assist.attachment'))
    if (source.page !== null && source.page !== undefined) where.push(t(spoken ? 'assist.pageSpoken' : 'assist.page', { n: source.page }))
  }
  return where.length ? t(spoken ? 'assist.citeSpoken' : 'assist.citeLabel', { symbol: name, where: where.join(', ') }) : name
}

/** id của mục nguồn trong danh sách (đích của liên kết [n]): duy nhất theo lượt hỏi. */
export function sourceAnchor(askId: string, n: number): string {
  return `nguon-${askId.replace(/[^A-Za-z0-9_-]/g, '')}-${n}`
}

/** Câu hỏi gửi đi: NFC, mọi khoảng trắng (cả xuống dòng do Shift+Enter) thành một dấu cách, bỏ ký tự điều khiển và
 *  ký tự vô hình (svc-files từ chối câu có ký tự điều khiển). */
export function cleanQuestion(s: string): string {
  return s.normalize('NFC').replace(/\s+/gu, ' ').replace(/[\p{Cc}\p{Cf}]/gu, '').replace(/ {2,}/g, ' ').trim()
}

/** Kết quả lượt extract có đáng nhờ mô hình viết câu trả lời không: mô hình sẵn sàng và có đoạn trích làm căn cứ. */
export function needsGenerate(res: Pick<AskResult, 'status' | 'ai_available' | 'sources'>): boolean {
  return res.ai_available === true && res.status !== 'no_evidence' && res.sources.length > 0
}

/** Hai khối hiện được: câu trả lời do mô hình viết (đã qua kiểm trích dẫn) và câu trích nguyên văn. Mô hình không
 *  đạt / quá giờ / từ chối thì answer là chính câu trích, chỉ còn khối câu trích. */
export function blocks(res: Pick<AskResult, 'answer' | 'extract'>): { model: AskAnswer | null; extract: AskAnswer | null } {
  const model = res.answer?.source === 'model' && res.answer.text ? res.answer : null
  const extract = res.extract?.text ? res.extract : res.answer?.source === 'extract' && res.answer.text ? res.answer : null
  return { model, extract }
}

// Nhãn che thông tin cá nhân (F4.4) mà svc-files đặt vào chữ gửi mô hình: [SĐT-1], [CCCD-2], [EMAIL], [STK-3]… —
// đúng mẫu LABEL_RE của services/svc-files/src/svc_files/pii.py (test so hai mẫu). Không phải dấu trích dẫn: CITE chỉ
// nhận số trong ngoặc vuông
export const MASK_RE = /\[(?:CCCD|CMND|SĐT|EMAIL|STK)(?:-\d{1,3})?\]/u

/** Câu trả lời của mô hình có nhãn che không: mô hình chỉ thấy nhãn, số thật nằm trong văn bản nguồn. */
export function hasMask(text: string | null | undefined): boolean {
  return !!text && MASK_RE.test(text)
}

/** Kết quả từ máy chủ, phòng trường thiếu: sources, warnings luôn là mảng; nguồn xếp theo n, đoạn trích luôn là chuỗi;
 *  cảnh báo không trùng. */
export function tidy(res: AskResult): AskResult {
  const sources = Array.isArray(res.sources)
    ? res.sources.map((s) => ({ ...s, excerpt: typeof s.excerpt === 'string' ? s.excerpt : '' })).sort((a, b) => a.n - b.n)
    : []
  const warnings = Array.isArray(res.warnings) ? [...new Set(res.warnings.filter((w) => typeof w === 'string'))] : []
  return { ...res, sources, warnings, answer: res.answer ?? null, extract: res.extract ?? null }
}

// --- hỏi trong một văn bản, xem trang được trích ---------------------------------------------------------------------

// Vai trò hỏi được (svc-files trả 403 forbidden với vai trò khác)
export const ASK_ROLES: readonly string[] = ['clerk', 'staff', 'manager', 'director']

// Tham số của trang Hỏi đáp: ?van_ban=<id> — chỉ hỏi trong văn bản đó (nút "Hỏi về văn bản này" ở trang chi tiết)
export const SCOPE_PARAM = 'van_ban'
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Đường tới trang Hỏi đáp chỉ hỏi trong một văn bản. */
export function askAbout(documentId: string): { path: string; query: Record<string, string> } {
  return { path: '/hoi-dap', query: { [SCOPE_PARAM]: documentId } }
}

/** Id văn bản phạm vi trong query của trang Hỏi đáp: chỉ nhận UUID (đưa về chữ thường), còn lại null — không gửi chuỗi
 *  lạ lên máy chủ (svc-files trả 422). */
export function scopeOf(query: Record<string, unknown>): string | null {
  const value = query[SCOPE_PARAM]
  return typeof value === 'string' && UUID_RE.test(value) ? value.toLowerCase() : null
}

/** Văn bản có trong kho của trợ lý không — đúng như chunks.eligible của svc-files: không hạn chế; văn bản đến chưa
 *  hủy; văn bản đi đã phát hành hoặc đã nộp lưu. */
export function inAssistant(doc: { restricted: boolean; direction: string; status: string }): boolean {
  if (doc.restricted) return false
  if (doc.direction === 'in') return doc.status !== 'cancelled'
  if (doc.direction === 'out') return doc.status === 'issued' || doc.status === 'archived'
  return false
}

/** Hiện nút "Hỏi về văn bản này" không: người xem hỏi được và văn bản có trong kho của trợ lý. Chỉ là giao diện —
 *  svc-files vẫn lọc theo vai trò và hậu kiểm bằng token người hỏi như mọi lượt. */
export function canAskAbout(doc: { restricted: boolean; direction: string; status: string },
  role: string | null | undefined): boolean {
  return ASK_ROLES.includes(role ?? '') && inAssistant(doc)
}

/** Nguồn có tệp để mở không: đoạn chữ của một tệp. Đoạn "trích yếu" (meta: bản scan chưa có chữ, tệp lỗi, văn bản chưa
 *  có tệp) không có tệp, không có trang. */
export function canView(source: Pick<AskSource, 'kind' | 'file_id'>): boolean {
  return source.kind === 'page' && !!source.file_id
}

/** Địa chỉ mở tệp PDF đúng trang: thêm #page=n (tham số mở PDF, RFC 8118 — trình xem PDF có sẵn của trình duyệt hiểu);
 *  không có số trang (chữ chưa có ranh giới trang) thì mở từ đầu. */
export function pageUrl(url: string, page: number | null | undefined): string {
  return typeof page === 'number' && Number.isInteger(page) && page > 0 ? `${url}#page=${page}` : url
}
