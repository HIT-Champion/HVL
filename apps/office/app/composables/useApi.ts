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
  // fields: trường sai → mã lỗi do svc-workflow trả (cùng mã với app/utils/forms.ts)
  constructor(message: string, public code: string | null = null, public status = 0,
              public fields: Record<string, string> | null = null) {
    super(message)
  }
}

export interface UploadedFile {
  id: string
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
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

  /** Tải tệp lên svc-files (quét ClamAV trước khi lưu); onProgress nhận 0–100. */
  async function upload(file: File, onProgress?: (pct: number) => void): Promise<UploadedFile> {
    const token = await auth.accessToken()
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/files')
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

  return { gql, upload, download, preview, register, printRegister, search }
}
