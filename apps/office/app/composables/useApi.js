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

// Gọi lõi Signet qua APISIX cùng tên miền: GraphQL (Hasura) cho dữ liệu và thao tác nghiệp vụ, REST của
// svc-files cho tệp và tìm kiếm. Mọi yêu cầu mang access token của người dùng.

export class ApiError extends Error {
  // fields: trường sai → mã lỗi do svc-workflow trả (cùng mã với app/utils/forms.ts); reason: lý do chi tiết của
  // một số mã (vd đọc văn bản unreadable → password, corrupt, timeout…); requestId: X-Request-Id của phản hồi (mã
  // blocked: người quản trị tra nhật ký chặn của cổng theo mã này)
  constructor(message, code = null, status = 0,
  fields = null, reason = null,
  requestId = null) {
    super(message);this.code = code;this.status = status;this.fields = fields;this.reason = reason;this.requestId = requestId;
  }
}

// Cổng chặn (F3.15): tường lửa ứng dụng web ở APISIX trả 403 kèm trang HTML của APISIX — không phải JSON như 403 của
// Hasura, svc-files — và tiêu đề X-Request-Id (platform/apisix/README.md, "Đọc nhật ký chặn"). Trả null khi không phải
// trường hợp này: nơi gọi xử lý lỗi như cũ
function gatewayBlock(status, headers) {
  if (status !== 403 || /\bjson\b/i.test(headers.get('Content-Type') ?? '')) return null;
  return new ApiError('blocked', 'blocked', 403, null, null, headers.get('X-Request-Id'));
}

// Kiểu của object URL trong khung xem tệp nguồn (F4.2): object URL cùng origin với ứng dụng, nên chỉ ảnh raster giữ
// kiểu svc-files trả (bản scan có đoạn kind=page); mọi thứ khác — kể cả HTML, SVG — ép application/pdf như phòng đọc
const VIEWER_IMAGES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp']);

export function viewerType(contentType) {
  const type = (contentType ?? '').split(';')[0].trim().toLowerCase();
  return VIEWER_IMAGES.has(type) ? type : 'application/pdf';
}



























// Sổ đăng ký văn bản đến / đi một năm (F2.8): đúng các cột, các ô sẽ in (svc-files, registers.py)


















// Đọc văn bản đến (F4.1): tác tử moc-doc-reader trong svc-files đọc tệp vừa tải lên (lớp chữ PDF, không có thì
// nhận dạng chữ) và gợi ý thông tin tiếp nhận. Chỉ là gợi ý: văn thư đối chiếu, sửa, rồi mới lưu (app/utils/suggest.ts).
























// Hỏi đáp trên kho văn bản (F4.2): trợ lý moc-assistant trong svc-files chỉ tìm trong các văn bản người hỏi được
// xem (lọc theo vai trò trong chỉ mục, rồi hậu kiểm bằng chính token người hỏi), văn bản hạn chế không bao giờ vào
// chỉ mục. Hai pha: extract trả câu trích nguyên văn (< 1 giây, không cần mô hình); generate nhờ mô hình ngôn ngữ
// viết câu trả lời có trích dẫn [n], đã qua kiểm trích dẫn. Câu hỏi, câu trả lời không lưu ở đâu cả.



















































// Hồ sơ đã nộp lưu (F3.8): gói đọc lại từ bucket lạnh, manifest đã so băm với CSDL (svc-files, archive.py). Chỉ văn
// bản người xem đọc được; tệp gắn với các văn bản đó, PDF mở được trong phòng đọc (bản có dấu tên người xem)















































// Hạn chờ một lần đọc: svc-files tự dừng ở 50 s, APISIX ở 60 s
const READ_TIMEOUT_MS = 60_000;
// Mã lỗi khi máy chủ không trả thân lỗi chuẩn (vd route chưa có, cổng trả lỗi)
const READ_STATUS_CODES = { 403: 'forbidden', 404: 'not_found', 409: 'restricted',
  413: 'too_large', 415: 'unsupported', 422: 'unreadable' };
// Hỏi đáp: tìm và trích dưới 1 giây nên chờ 20 s là đủ; viết câu trả lời thì svc-files tự dừng ở 50 s
const ASK_TIMEOUT_MS = { extract: 20_000, generate: 60_000 };
const ASK_STATUS_CODES = { 400: 'invalid_question', 403: 'forbidden', 404: 'not_found',
  422: 'invalid_request', 502: 'unavailable', 503: 'unavailable', 504: 'unavailable' };

export function useApi() {
  const auth = useAuth();

  async function authFetch(url, init = {}) {
    const token = await auth.accessToken();
    let res;
    try {
      res = await fetch(url, { ...init, headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` } });
    } catch {
      throw new ApiError('network', 'network');
    }
    if (res.status === 401) {
      await auth.login(window.location.pathname + window.location.search);
      throw new ApiError('session', 'session', 401);
    }
    // APISIX giới hạn tốc độ theo phiên (platform/apisix/apisix.yaml)
    if (res.status === 429) throw new ApiError('rate_limited', 'rate_limited', 429);
    return res;
  }

  async function gql(query, variables = {}) {
    const res = await authFetch('/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, variables })
    });
    const blocked = gatewayBlock(res.status, res.headers);
    if (blocked) throw blocked;
    // thân không phải JSON (cổng trả trang lỗi 502, 504…): báo mã HTTP, không để lỗi đọc JSON lọt ra giao diện
    const body = await res.json().catch(() => null);
    if (!body) throw new ApiError(`HTTP ${res.status}`, null, res.status);
    if (body.errors?.length) {
      const e = body.errors[0];
      throw new ApiError(e.message, e.extensions?.code ?? null, res.status, e.extensions?.fields ?? null);
    }
    // A JSON body is not proof that a mutation succeeded (gateways may return {} with 503).
    if (!res.ok || !Object.hasOwn(body, 'data')) throw new ApiError(`HTTP ${res.status}`, null, res.status);
    return body.data;
  }

  /** Tải tệp lên svc-files (quét ClamAV trước khi lưu); onProgress nhận 0–100. restricted: tệp của văn bản hạn chế
   *  (F3.7) — chỉ PDF, svc-files mã hóa trước khi lưu. */
  async function upload(file, onProgress, restricted = false) {
    const token = await auth.accessToken();
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', restricted ? '/api/files?restricted=true' : '/api/files');
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {if (e.lengthComputable && onProgress) onProgress(Math.round(e.loaded / e.total * 100));};
      xhr.onerror = () => reject(new ApiError('network', 'network'));
      xhr.onload = () => {
        let body = {};
        try {body = JSON.parse(xhr.responseText);} catch {/* không phải JSON */}
        if (xhr.status === 201) return resolve(body);
        const blocked = gatewayBlock(xhr.status, { get: (name) => xhr.getResponseHeader(name) });
        if (blocked) return reject(blocked);
        const detail = body.detail ?? {};
        // tệp nhiễm: thông điệp là mẫu mã độc ClamAV báo, để trang tiếp nhận nói rõ tệp nhiễm gì
        const message = detail.code === 'infected' ? detail.signature ?? detail.message : detail.message;
        reject(new ApiError(message ?? `HTTP ${xhr.status}`, detail.code ?? null, xhr.status));
      };
      const form = new FormData();
      form.append('file', file);
      xhr.send(form);
    });
  }

  /** Tải tệp về máy: cần token nên không dùng được thẻ <a href> trực tiếp. */
  async function download(fileId, filename) {
    const res = await authFetch(`/api/files/${fileId}`);
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`, null, res.status);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }

  /** PDF do svc-files dựng, tải về máy với tên filename. */
  async function savePdf(path, filename) {
    const res = await authFetch(path);
    if (!res.ok) {
      const blocked = gatewayBlock(res.status, res.headers);
      if (blocked) throw blocked;
      const body = await res.json().catch(() => ({}));
      throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status);
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }

  /** Bản PDF xem trước của dự thảo văn bản đi (svc-files dựng đúng thể thức, in chữ DỰ THẢO), tải về máy. */
  function preview(documentId) {
    return savePdf(`/api/documents/${documentId}/preview`, `du-thao-${documentId.slice(0, 8)}.pdf`);
  }

  /** Sổ đăng ký một năm để xem trên màn hình. */
  async function register(direction, year) {
    const res = await authFetch(`/api/registers/${direction}/${year}`);
    const blocked = gatewayBlock(res.status, res.headers);
    if (blocked) throw blocked;
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status);
    return body;
  }

  /** In sổ đăng ký ra PDF (A4 ngang) để ký nhận, đóng sổ; mỗi lần in được ghi vào sổ kiểm toán. */
  function printRegister(direction, year) {
    return savePdf(`/api/registers/${direction}/${year}/pdf`,
    `so-dang-ky-van-ban-${direction === 'in' ? 'den' : 'di'}-${year}.pdf`);
  }

  async function search(params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') qs.set(k, String(v));
    const res = await authFetch(`/api/search?${qs}`);
    const blocked = gatewayBlock(res.status, res.headers);
    if (blocked) throw blocked;
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status);
    return body;
  }

  /** Tác tử đọc tệp đã quét sạch (chỉ văn thư, chỉ tệp mình tải lên, không đọc tệp của văn bản hạn chế) và trả gợi ý
   *  thông tin tiếp nhận. force: đọc lại dù đã có gợi ý lưu từ lần trước. Mỗi lần đọc thật được ghi vào sổ kiểm toán
   *  (sự kiện intake.suggested, chỉ siêu dữ liệu). Lỗi: ApiError với mã của svc-files (restricted, unreadable +
   *  reason, busy…), hoặc client_timeout khi quá 60 giây. */
  async function readFile(fileId, force = false) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), READ_TIMEOUT_MS);
    try {
      const res = await authFetch(`/api/files/${encodeURIComponent(fileId)}/read${force ? '?force=true' : ''}`,
      { method: 'POST', signal: ctrl.signal });
      if (res.ok) return await res.json();
      const blocked = gatewayBlock(res.status, res.headers);
      if (blocked) throw blocked;
      const body = await res.json().catch(() => ({}));
      const detail = typeof body.detail === 'object' && body.detail !== null ? body.detail : {};
      throw new ApiError(detail.message ?? `HTTP ${res.status}`,
      detail.code ?? READ_STATUS_CODES[res.status] ?? null, res.status, null, detail.reason ?? null);
    } catch (e) {
      if (ctrl.signal.aborted) throw new ApiError('client_timeout', 'client_timeout');
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Hỏi trợ lý trên kho văn bản (F4.2). mode extract (mặc định): câu trích nguyên văn; generate: mô hình viết câu
   *  trả lời — gửi kèm ask_id của lượt extract. signal: người dùng bấm Dừng. Lỗi: ApiError với mã của svc-files
   *  (invalid_question, forbidden, assistant_disabled, busy, search_unavailable, database_unavailable…),
   *  client_timeout khi quá hạn chờ, aborted khi người dùng dừng. */
  async function ask(body, signal) {
    const ctrl = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {timedOut = true;ctrl.abort();}, ASK_TIMEOUT_MS[body.mode ?? 'extract']);
    const stop = () => ctrl.abort();
    if (signal?.aborted) ctrl.abort();else
    signal?.addEventListener('abort', stop, { once: true });
    try {
      const res = await authFetch('/api/documents/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal
      });
      if (res.ok) return await res.json();
      // câu hỏi có chữ dạng tấn công (SQLi, XSS…) bị cổng chặn: blocked, không phải forbidden (không có quyền)
      const blocked = gatewayBlock(res.status, res.headers);
      if (blocked) throw blocked;
      const data = await res.json().catch(() => ({}));
      // lỗi của svc-files: {detail: {code, message}}; 422 của FastAPI: detail là mảng lỗi từng trường
      const detail = typeof data.detail === 'object' && data.detail !== null && !Array.isArray(data.detail) ? data.detail : {};
      throw new ApiError(detail.message ?? `HTTP ${res.status}`, detail.code ?? ASK_STATUS_CODES[res.status] ?? null, res.status);
    } catch (e) {
      if (ctrl.signal.aborted) {
        const code = timedOut ? 'client_timeout' : 'aborted';
        throw new ApiError(code, code);
      }
      throw e;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', stop);
    }
  }

  // --- hồ sơ, nộp lưu, phòng đọc (F3.8) ---------------------------------------------------------------------------

  /** Lỗi của svc-files ({detail: {code, message, reason}}) thành ApiError; cổng chặn thì blocked. */
  async function serviceError(res) {
    const blocked = gatewayBlock(res.status, res.headers);
    if (blocked) return blocked;
    const body = await res.json().catch(() => ({}));
    const raw = body.detail;
    const detail = typeof raw === 'object' && raw !== null && !Array.isArray(raw) ? raw : {};
    return new ApiError(detail.message ?? `HTTP ${res.status}`, detail.code ?? null, res.status, null,
    detail.reason ?? null);
  }

  /** Nộp lưu ngay hồ sơ đã đóng (chỉ lãnh đạo phòng của phòng có hồ sơ): svc-files ghi gói Parquet + tệp + manifest có
   *  băm vào bucket lạnh khóa ghi, đọc lại so băm rồi mới chuyển CSDL sang archived. Lỗi: ApiError với mã của svc-files
   *  (forbidden, not_closed, already_archived, archive_failed, busy…). */
  async function archiveCaseFile(id) {
    const res = await authFetch(`/api/case-files/${encodeURIComponent(id)}/archive`, { method: 'POST' });
    if (!res.ok) throw await serviceError(res);
    return await res.json();
  }

  /** Phòng đọc: gói lưu trữ của hồ sơ đã nộp lưu, đọc lại từ bucket lạnh (mỗi lần mở ghi case_file.read vào sổ). */
  async function readingRoom(id) {
    const res = await authFetch(`/api/case-files/${encodeURIComponent(id)}/archive`);
    if (!res.ok) throw await serviceError(res);
    return await res.json();
  }

  /** Phòng đọc xem một tệp PDF trong gói: bản có dấu tên người xem, giờ xem (mỗi lần mở ghi case_file.file_viewed).
   *  Trả object URL để hiện trong khung xem — gọi URL.revokeObjectURL khi đóng. */
  async function viewArchivedFile(caseFileId, fileId) {
    const path = `${encodeURIComponent(caseFileId)}/archive/files/${encodeURIComponent(fileId)}`;
    const res = await authFetch(`/api/case-files/${path}`);
    if (!res.ok) throw await serviceError(res);
    // ép kiểu application/pdf: khung xem chỉ hiện PDF, không bao giờ coi byte trả về là một trang HTML
    return URL.createObjectURL(new Blob([await res.arrayBuffer()], { type: 'application/pdf' }));
  }

  /** Xem tệp của một nguồn trợ lý trích (F4.2) trong khung xem của trang Hỏi đáp: tải bằng token (svc-files kiểm quyền
   *  đọc như nút Tải về), trả object URL kiểu PDF như viewArchivedFile — riêng bản scan JPEG, PNG… giữ kiểu ảnh
   *  (viewerType) — gọi URL.revokeObjectURL khi đóng. */
  async function viewFile(fileId) {
    const res = await authFetch(`/api/files/${encodeURIComponent(fileId)}`);
    if (!res.ok) throw await serviceError(res);
    const type = viewerType(res.headers.get('Content-Type'));
    return URL.createObjectURL(new Blob([await res.arrayBuffer()], { type }));
  }

  return { gql, upload, download, preview, register, printRegister, search, readFile, ask, archiveCaseFile, readingRoom,
    viewArchivedFile, viewFile, readArchive: readingRoom };
}
