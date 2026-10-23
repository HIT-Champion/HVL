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

// Gọi lõi Signet qua APISIX cùng tên miền, đúng các API mà Văn phòng điện tử dùng: GraphQL của Hasura (/v1/graphql)
// cho danh sách và thư mục, REST của svc-files (/api/files) để tải tệp lên — ClamAV quét trước khi lưu — và tải về.
// Mọi yêu cầu mang access token của người dùng; quyền do Hasura, svc-files kiểm.

import { uploadError } from './para.js'

export class ApiError extends Error {
  constructor(message, code = null, status = 0) {
    super(message)
    this.code = code
    this.status = status
  }
}

/** token(): access token còn hạn; relogin(): chuyển sang đăng nhập lại khi cổng trả 401. */
export function createApi({ token, relogin, fetchImpl = (...a) => fetch(...a), XHR = globalThis.XMLHttpRequest }) {
  async function authFetch(url, init = {}) {
    const bearer = await token()
    let res
    try {
      res = await fetchImpl(url, { ...init, headers: { ...(init.headers ?? {}), Authorization: `Bearer ${bearer}` } })
    } catch {
      throw new ApiError('network', 'network')
    }
    if (res.status === 401) {
      await relogin()
      throw new ApiError('session', 'session', 401)
    }
    // APISIX giới hạn tốc độ theo phiên (platform/apisix/apisix.yaml)
    if (res.status === 429) throw new ApiError('rate_limited', 'rate_limited', 429)
    return res
  }

  async function gql(query, variables = {}) {
    const res = await authFetch('/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, variables }),
    })
    const body = await res.json().catch(() => ({}))
    if (body.errors?.length) {
      const e = body.errors[0]
      throw new ApiError(e.message ?? '', e.extensions?.code ?? null, res.status)
    }
    if (!res.ok || !body.data) throw new ApiError(`HTTP ${res.status}`, null, res.status)
    return body.data
  }

  /** Tải tệp lên svc-files; onProgress nhận 0–100. Trả {id, filename, size_bytes, sha256, …}; lỗi là ApiError có
   *  câu báo tiếng Việt (tệp nhiễm, quá lớn, trạm quét chưa sẵn sàng…). */
  async function upload(file, onProgress) {
    const bearer = await token()
    return new Promise((resolve, reject) => {
      const xhr = new XHR()
      xhr.open('POST', '/api/files')
      xhr.setRequestHeader('Authorization', `Bearer ${bearer}`)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
      }
      xhr.onerror = () => reject(new ApiError(uploadError(0, null), 'network', 0))
      xhr.onload = () => {
        let body = {}
        try { body = JSON.parse(xhr.responseText) } catch { /* không phải JSON */ }
        if (xhr.status === 201) return resolve(body)
        if (xhr.status === 401) {
          relogin()
          return reject(new ApiError('session', 'session', 401))
        }
        reject(new ApiError(uploadError(xhr.status, body), body?.detail?.code ?? null, xhr.status))
      }
      const form = new FormData()
      form.append('file', file)
      xhr.send(form)
    })
  }

  /** Nội dung tệp (Blob) — cần token nên không dùng thẻ <a href> thẳng tới /api/files/{id}. */
  async function fetchFile(fileId) {
    const res = await authFetch(`/api/files/${encodeURIComponent(fileId)}`)
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`, res.status === 404 ? 'not_found' : null, res.status)
    return res.blob()
  }

  return { gql, upload, fetchFile }
}
