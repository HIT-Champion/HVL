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

// Đọc văn bản đến (F4.1): gợi ý của tác tử đọc văn bản vào form tiếp nhận thế nào. Luật quan trọng nhất: KHÔNG BAO GIỜ
// ghi đè chữ văn thư đã gõ. Chỉ điền ô văn thư chưa chạm tới (chưa gõ, chọn, soạn chữ, không đang có focus) mà còn
// trống, còn giá trị mặc định (loại CV, độ khẩn Thường), hoặc do chính tác tử điền ở lần đọc trước. Độ tin cậy thấp
// thì không điền, chỉ đưa ra "Gợi ý: … [Dùng]". Chỉ kết quả của tệp nguồn (tệp form đang theo) mới được điền; đọc
// tệp khác (vd phụ lục) chỉ đưa ra gợi ý.
// Tệp này không dùng gì của Nuxt để Node chạy test được (tests/suggest.test.ts).

import type { ReadField, ReadFieldKey, ReadResult } from '../composables/useApi'

export const READ_KEYS: readonly ReadFieldKey[] = ['type_code', 'symbol', 'issued_on', 'issuer_name', 'summary', 'urgency']

export type SuggestForm = Record<ReadFieldKey, string>
export type SuggestMap = Partial<Record<ReadFieldKey, ReadField>>

// Cảnh báo của lần đọc gắn với một ô (hiện ngay dưới ô đó); cảnh báo khác hiện ở dòng tệp
export const FIELD_WARNINGS: Readonly<Record<string, ReadFieldKey>> = {
  future_date: 'issued_on',
  invalid_date: 'issued_on',
  symbol_no_number: 'symbol',
  type_conflict: 'type_code',
}

export interface SuggestOptions {
  types?: readonly string[]      // mã loại văn bản có trong danh mục; không có thì không lọc
  urgencies?: readonly string[]  // danh mục độ khẩn của schema
  // ô văn thư đã chạm (gõ, chọn, đang soạn chữ bằng bộ gõ, bấm Dùng) hoặc đang có focus: không bao giờ tự đổi, dù giá
  // trị trong ô còn trống hay bằng mặc định (ô ngày gõ dở, chữ đang soạn chưa vào v-model, chủ động chọn lại CV)
  touched?: Iterable<ReadFieldKey>
  // kết quả của một tệp khác tệp nguồn của form: không điền, không đưa ô về mặc định, giữ nguyên nhãn — chỉ đưa ra
  offerOnly?: boolean
}

export interface Suggestion {
  values: Partial<SuggestForm>   // ô cần đổi giá trị: khóa → giá trị mới (chỉ ô văn thư chưa chạm)
  filled: ReadFieldKey[]         // ô lần đọc này điền
  suggested: SuggestMap          // ô đang mang giá trị của tác tử (nhãn "Gợi ý" / "Đã sửa"); là `previous` của lần sau
  offers: SuggestMap             // gợi ý không điền vào ô: độ tin cậy thấp, hoặc ô đã có chữ văn thư gõ
}

const DATE = /^(19|20)\d{2}-\d{2}-\d{2}$/
// Ngày có thật trên lịch (không 31/02)
function realDate(v: string): boolean {
  const day = new Date(`${v}T00:00:00Z`)
  return DATE.test(v) && !Number.isNaN(day.getTime()) && day.toISOString().slice(0, 10) === v
}

// Giá trị gợi ý dùng được cho form: đúng kiểu, mã loại / độ khẩn có trong danh mục, ngày có thật; còn lại bỏ hẳn
function usable(key: ReadFieldKey, field: unknown, opts: SuggestOptions): ReadField | undefined {
  if (!field || typeof field !== 'object') return undefined
  const { value, confidence, source } = field as Partial<ReadField>
  if (typeof value !== 'string' || !['high', 'medium', 'low'].includes(String(confidence))) return undefined
  const v = value.normalize('NFC').trim()
  if (!v) return undefined
  if (key === 'type_code' && opts.types?.length && !opts.types.includes(v)) return undefined
  if (key === 'urgency' && opts.urgencies?.length && !opts.urgencies.includes(v)) return undefined
  if (key === 'issued_on' && !realDate(v)) return undefined
  return { value: v, confidence: confidence as ReadField['confidence'], source: source === 'model' ? 'model' : 'rule' }
}

/**
 * Áp kết quả một lần đọc lên form. form: giá trị hiện tại của sáu ô; defaults: giá trị ban đầu của form (ô bằng mặc
 * định coi như trống); previous: `suggested` của lần áp trước (ô tác tử đã điền); result: kết quả đọc, null = bỏ
 * gợi ý (vd văn thư gỡ tệp đã đọc).
 *
 * Với mỗi ô: "của tác tử" khi văn thư chưa chạm (opts.touched) và ô trống / bằng mặc định / bằng đúng giá trị tác tử
 * điền lần trước. Chỉ ô của tác tử mới được đổi: gợi ý cao, trung bình thì điền; gợi ý thấp hoặc lần này không đọc ra
 * thì ô tác tử điền lần trước trả về mặc định (không để lại giá trị cũ mang nhãn "Gợi ý"). Ô văn thư đã chạm giữ
 * nguyên — gợi ý khác thì chỉ đưa ra để văn thư tự bấm Dùng; ô tác tử điền mà văn thư đã sửa thì giữ nhãn "Đã sửa"
 * (so với gợi ý mới), không đưa ra lại. opts.offerOnly (đọc tệp không phải tệp nguồn): không đổi ô nào, giữ nhãn cũ,
 * mọi giá trị đọc được khác ô hiện tại đều chỉ là gợi ý đưa ra.
 * Hàm thuần: không sửa form, trả về các ô cần đổi.
 */
export function applySuggestion(form: SuggestForm, defaults: Partial<SuggestForm>, previous: SuggestMap,
  result: Pick<ReadResult, 'fields'> | null, opts: SuggestOptions = {}): Suggestion {
  const out: Suggestion = { values: {}, filled: [], suggested: {}, offers: {} }
  const touched = new Set(opts.touched ?? [])
  if (opts.offerOnly) {
    out.suggested = { ...previous }
    for (const key of READ_KEYS) {
      const field = usable(key, result?.fields?.[key], opts)
      if (field && field.value !== (form[key] ?? '')) out.offers[key] = field
    }
    return out
  }
  for (const key of READ_KEYS) {
    const field = usable(key, result?.fields?.[key], opts)
    const current = form[key] ?? ''
    const base = defaults[key] ?? ''
    const free = !touched.has(key)
    const agentValue = previous[key] !== undefined && current === previous[key]!.value   // ô vẫn đúng giá trị tác tử điền
    const fromAgent = free && agentValue
    const owned = free && (fromAgent || current.trim() === '' || current === base)
    let value = fromAgent ? base : current
    if (field && field.confidence !== 'low' && owned) {
      value = field.value
      out.suggested[key] = field
      out.filled.push(key)
    } else if (agentValue && !free) {
      // ô văn thư đã chạm (bấm Dùng, đang có focus…) mà vẫn đúng giá trị tác tử điền: giữ nhãn cũ, kết quả mới chỉ đưa ra
      out.suggested[key] = previous[key]
      if (field && field.value !== current) out.offers[key] = field
    } else if (field && previous[key] && !owned) {
      // ô tác tử điền, văn thư đã sửa: giữ chữ văn thư, nhãn so với gợi ý mới ("Đã sửa", hoặc "Gợi ý" nếu trùng)
      out.suggested[key] = field
    } else if (field && field.value === value) {
      // ô đã có đúng giá trị đọc được (văn thư tự gõ trùng): gắn nhãn, không đổi gì; gợi ý thấp thì thôi
      if (field.confidence !== 'low') out.suggested[key] = field
    } else if (field) {
      out.offers[key] = field
    }
    if (value !== current) out.values[key] = value
  }
  return out
}

/** Văn thư bấm "Dùng" ở một gợi ý chưa điền: ô nhận giá trị gợi ý, mang nhãn "Gợi ý" như ô tác tử điền. */
export function acceptOffer(suggested: SuggestMap, offers: SuggestMap, key: ReadFieldKey):
  { value: string; suggested: SuggestMap; offers: SuggestMap } | null {
  const field = offers[key]
  if (!field) return null
  const rest = { ...offers }
  delete rest[key]
  return { value: field.value, suggested: { ...suggested, [key]: field }, offers: rest }
}

export type TagState = 'high' | 'medium' | 'model' | 'edited'

/** Nhãn cạnh ô: "Gợi ý" (cao; trung bình, thấp là "chưa chắc"), "Gợi ý của mô hình", "Đã sửa" khi giá trị khác
 *  gợi ý; null: không nhãn. */
export function tagState(field: ReadField | undefined, value: string): TagState | null {
  if (!field) return null
  if (value !== field.value) return 'edited'
  if (field.source === 'model') return 'model'
  return field.confidence === 'high' ? 'high' : 'medium'
}

/** Gợi ý còn đáng hiện dưới ô: ô đã có đúng giá trị đó (văn thư tự gõ) thì thôi. */
export function openOffer(offers: SuggestMap, form: SuggestForm, key: ReadFieldKey): ReadField | undefined {
  const field = offers[key]
  return field && field.value !== form[key] ? field : undefined
}
