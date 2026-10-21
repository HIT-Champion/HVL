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

// Gọi lõi Mộc qua APISIX cùng tên miền: GraphQL (Hasura) cho dữ liệu và thao tác nghiệp vụ, REST của
// svc-files cho tệp và tìm kiếm. Mọi yêu cầu mang access token của người dùng.

export class ApiError extends Error {
  // fields: trường sai → mã lỗi do svc-workflow trả (cùng mã với app/utils/forms.ts); reason: lý do chi tiết của
  // một số mã (vd đọc văn bản unreadable → password, corrupt, timeout…)
  constructor(message: string, public code: string | null = null, public status = 0,
              public fields: Record<string, string> | null = null, public reason: string | null = null) {
    super(message)
  }
}

export interface UploadedFile {
  id: string
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  encrypted?: boolean
}

export interface SearchHit {
  id: string
  direction: 'in' | 'out'
  status: string
  type_code: string
  symbol: string | null
  issuer_name: string | null
  issued_on: string | null
  summary: string
  urgency: string
  register_number: number | null
  registered_at: string | null
  due_on: string | null
  // khớp trong nội dung (văn bản đi, chữ của tệp PDF đính kèm — F2.7), không khớp số ký hiệu, trích yếu, cơ quan
  matched_content: boolean
}

// Sổ đăng ký văn bản đến / đi một năm (F2.8): đúng các cột, các ô sẽ in (svc-files, registers.py)
export interface RegisterEntry {
  number: number
  document_id: string | null // null: văn bản hạn chế người xem không được đọc, chỉ có số, ngày, số ký hiệu
  hidden: boolean
  cells: string[]
}

export interface RegisterBook {
  direction: 'in' | 'out'
  year: number
  title: string
  org_name: string
  columns: string[]
  entries: RegisterEntry[]
  last_number: number
  missing: number[]
}

// Đọc văn bản đến (F4.1): tác tử moc-doc-reader trong svc-files đọc tệp vừa tải lên (lớp chữ PDF, không có thì
// nhận dạng chữ) và gợi ý thông tin tiếp nhận. Chỉ là gợi ý: văn thư đối chiếu, sửa, rồi mới lưu (app/utils/suggest.ts).
export type ReadFieldKey = 'type_code' | 'symbol' | 'issued_on' | 'issuer_name' | 'summary' | 'urgency'

export interface ReadField {
  value: string
  confidence: 'high' | 'medium' | 'low'
  source: 'rule' | 'model'   // model: mô hình ngôn ngữ viết (chỉ trích yếu)
}

export interface ReadResult {
  file_id: string
  status: 'ok' | 'empty'     // empty: đọc được mà không ra trường nào
  method: 'text' | 'ocr'
  pages: number
  fields: Partial<Record<ReadFieldKey, ReadField>>   // chỉ trường tìm thấy; issued_on dạng YYYY-MM-DD
  // future_date, invalid_date, symbol_no_number, type_conflict, low_text, truncated, model_unavailable,
  // model_timeout, model_rejected, model_skipped
  warnings: string[]
  summary_source: 'rule' | 'model' | 'none'
  model: string | null
  duration_ms: number
  cached: boolean            // gợi ý đã lưu từ lần đọc trước, không đọc lại
  read_at: string
}

// Hạn chờ một lần đọc: svc-files tự dừng ở 50 s, APISIX ở 60 s
const READ_TIMEOUT_MS = 60_000
// Mã lỗi khi máy chủ không trả thân lỗi chuẩn (vd route chưa có, cổng trả lỗi)
const READ_STATUS_CODES: Record<number, string> = { 403: 'forbidden', 404: 'not_found', 409: 'restricted',
  413: 'too_large', 415: 'unsupported', 422: 'unreadable' }

export function useApi() {
  const auth = useAuth()

  async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
    const token = await auth.accessToken()
    let res: Response
    try {
      res = await fetch(url, { ...init, headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` } })
    } catch {
      throw new ApiError('network', 'network')
    }
    if (res.status === 401) {
      await auth.login(window.location.pathname + window.location.search)
      throw new ApiError('session', 'session', 401)
    }
    // APISIX giới hạn tốc độ theo phiên (gateway/apisix.yaml)
    if (res.status === 429) throw new ApiError('rate_limited', 'rate_limited', 429)
    return res
  }

  async function gql<T = Record<string, unknown>>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
    const res = await authFetch('/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, variables }),
    })
    const body = await res.json()
    if (body.errors?.length) {
      const e = body.errors[0]
      throw new ApiError(e.message, e.extensions?.code ?? null, res.status, e.extensions?.fields ?? null)
    }
    return body.data as T
  }

  /** Tải tệp lên svc-files (quét ClamAV trước khi lưu); onProgress nhận 0–100. restricted: tệp của văn bản hạn chế
   *  (F3.7) — chỉ PDF, svc-files mã hóa trước khi lưu. */
  async function upload(file: File, onProgress?: (pct: number) => void, restricted = false): Promise<UploadedFile> {
    const token = await auth.accessToken()
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', restricted ? '/api/files?restricted=true' : '/api/files')
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100)) }
      xhr.onerror = () => reject(new ApiError('network', 'network'))
      xhr.onload = () => {
        let body: Record<string, any> = {}
        try { body = JSON.parse(xhr.responseText) } catch { /* không phải JSON */ }
        if (xhr.status === 201) return resolve(body as UploadedFile)
        const detail = body.detail ?? {}
        // tệp nhiễm: thông điệp là mẫu mã độc ClamAV báo, để trang tiếp nhận nói rõ tệp nhiễm gì
        const message = detail.code === 'infected' ? detail.signature ?? detail.message : detail.message
        reject(new ApiError(message ?? `HTTP ${xhr.status}`, detail.code ?? null, xhr.status))
      }
      const form = new FormData()
      form.append('file', file)
      xhr.send(form)
    })
  }

  /** Tải tệp về máy: cần token nên không dùng được thẻ <a href> trực tiếp. */
  async function download(fileId: string, filename: string): Promise<void> {
    const res = await authFetch(`/api/files/${fileId}`)
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`, null, res.status)
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }

  /** PDF do svc-files dựng, tải về máy với tên filename. */
  async function savePdf(path: string, filename: string): Promise<void> {
    const res = await authFetch(path)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status)
    }
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }

  /** Bản PDF xem trước của dự thảo văn bản đi (svc-files dựng đúng thể thức, in chữ DỰ THẢO), tải về máy. */
  function preview(documentId: string): Promise<void> {
    return savePdf(`/api/documents/${documentId}/preview`, `du-thao-${documentId.slice(0, 8)}.pdf`)
  }

  /** Sổ đăng ký một năm để xem trên màn hình. */
  async function register(direction: 'in' | 'out', year: number): Promise<RegisterBook> {
    const res = await authFetch(`/api/registers/${direction}/${year}`)
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status)
    return body
  }

  /** In sổ đăng ký ra PDF (A4 ngang) để ký nhận, đóng sổ; mỗi lần in được ghi vào sổ kiểm toán. */
  function printRegister(direction: 'in' | 'out', year: number): Promise<void> {
    return savePdf(`/api/registers/${direction}/${year}/pdf`,
      `so-dang-ky-van-ban-${direction === 'in' ? 'den' : 'di'}-${year}.pdf`)
  }

  async function search(params: Record<string, string | number | undefined>): Promise<{ hits: SearchHit[]; next_cursor: string | null }> {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') qs.set(k, String(v))
    const res = await authFetch(`/api/search?${qs}`)
    const body = await res.json()
    if (!res.ok) throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status)
    return body
  }

  /** Tác tử đọc tệp đã quét sạch (chỉ văn thư, chỉ tệp mình tải lên, không đọc tệp của văn bản hạn chế) và trả gợi ý
   *  thông tin tiếp nhận. force: đọc lại dù đã có gợi ý lưu từ lần trước. Mỗi lần đọc thật được ghi vào sổ kiểm toán
   *  (sự kiện intake.suggested, chỉ siêu dữ liệu). Lỗi: ApiError với mã của svc-files (restricted, unreadable +
   *  reason, busy…), hoặc client_timeout khi quá 60 giây. */
  async function readFile(fileId: string, force = false): Promise<ReadResult> {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), READ_TIMEOUT_MS)
    try {
      const res = await authFetch(`/api/files/${encodeURIComponent(fileId)}/read${force ? '?force=true' : ''}`,
        { method: 'POST', signal: ctrl.signal })
      if (res.ok) return await res.json() as ReadResult
      const body = await res.json().catch(() => ({}))
      const detail = typeof body.detail === 'object' && body.detail !== null ? body.detail : {}
      throw new ApiError(detail.message ?? `HTTP ${res.status}`,
        detail.code ?? READ_STATUS_CODES[res.status] ?? null, res.status, null, detail.reason ?? null)
    } catch (e) {
      if (ctrl.signal.aborted) throw new ApiError('client_timeout', 'client_timeout')
      throw e
    } finally {
      clearTimeout(timer)
    }
  }

  return { gql, upload, download, preview, register, printRegister, search, readFile }
}
