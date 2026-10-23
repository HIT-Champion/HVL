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

export class ApiError extends Error {
    code;
    status;
    fields;
    reason;
    constructor(message, code = null, status = 0, fields = null, reason = null){
        super(message), this.code = code, this.status = status, this.fields = fields, this.reason = reason;
    }
}
const READ_TIMEOUT_MS = 60_000;
const READ_STATUS_CODES = {
    403: 'forbidden',
    404: 'not_found',
    409: 'restricted',
    413: 'too_large',
    415: 'unsupported',
    422: 'unreadable'
};
const ASK_TIMEOUT_MS = {
    extract: 20_000,
    generate: 60_000
};
const ASK_STATUS_CODES = {
    400: 'invalid_question',
    403: 'forbidden',
    404: 'not_found',
    422: 'invalid_request',
    502: 'unavailable',
    503: 'unavailable',
    504: 'unavailable'
};
export function useApi() {
    const auth = useAuth();
    async function authFetch(url, init = {}) {
        const token = await auth.accessToken();
        let res;
        try {
            res = await fetch(url, {
                ...init,
                headers: {
                    ...init.headers ?? {},
                    Authorization: `Bearer ${token}`
                }
            });
        } catch  {
            throw new ApiError('network', 'network');
        }
        if (res.status === 401) {
            await auth.login(window.location.pathname + window.location.search);
            throw new ApiError('session', 'session', 401);
        }
        if (res.status === 429) throw new ApiError('rate_limited', 'rate_limited', 429);
        return res;
    }
    async function gql(query, variables = {}) {
        const res = await authFetch('/v1/graphql', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query,
                variables
            })
        });
        const body = await res.json();
        if (body.errors?.length) {
            const e = body.errors[0];
            throw new ApiError(e.message, e.extensions?.code ?? null, res.status, e.extensions?.fields ?? null);
        }
        return body.data;
    }
    async function upload(file, onProgress, restricted = false) {
        const token = await auth.accessToken();
        return new Promise((resolve, reject)=>{
            const xhr = new XMLHttpRequest();
            xhr.open('POST', restricted ? '/api/files?restricted=true' : '/api/files');
            xhr.setRequestHeader('Authorization', `Bearer ${token}`);
            xhr.upload.onprogress = (e)=>{
                if (e.lengthComputable && onProgress) onProgress(Math.round(e.loaded / e.total * 100));
            };
            xhr.onerror = ()=>reject(new ApiError('network', 'network'));
            xhr.onload = ()=>{
                let body = {};
                try {
                    body = JSON.parse(xhr.responseText);
                } catch  {}
                if (xhr.status === 201) return resolve(body);
                const detail = body.detail ?? {};
                const message = detail.code === 'infected' ? detail.signature ?? detail.message : detail.message;
                reject(new ApiError(message ?? `HTTP ${xhr.status}`, detail.code ?? null, xhr.status));
            };
            const form = new FormData();
            form.append('file', file);
            xhr.send(form);
        });
    }
    async function download(fileId, filename) {
        const res = await authFetch(`/api/files/${fileId}`);
        if (!res.ok) throw new ApiError(`HTTP ${res.status}`, null, res.status);
        const url = URL.createObjectURL(await res.blob());
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        setTimeout(()=>URL.revokeObjectURL(url), 10_000);
    }
    async function savePdf(path, filename) {
        const res = await authFetch(path);
        if (!res.ok) {
            const body = await res.json().catch(()=>({}));
            throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status);
        }
        const url = URL.createObjectURL(await res.blob());
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        setTimeout(()=>URL.revokeObjectURL(url), 10_000);
    }
    function preview(documentId) {
        return savePdf(`/api/documents/${documentId}/preview`, `du-thao-${documentId.slice(0, 8)}.pdf`);
    }
    async function register(direction, year) {
        const res = await authFetch(`/api/registers/${direction}/${year}`);
        const body = await res.json().catch(()=>({}));
        if (!res.ok) throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status);
        return body;
    }
    function printRegister(direction, year) {
        return savePdf(`/api/registers/${direction}/${year}/pdf`, `so-dang-ky-van-ban-${direction === 'in' ? 'den' : 'di'}-${year}.pdf`);
    }
    async function search(params) {
        const qs = new URLSearchParams();
        for (const [k, v] of Object.entries(params))if (v !== undefined && v !== '') qs.set(k, String(v));
        const res = await authFetch(`/api/search?${qs}`);
        const body = await res.json();
        if (!res.ok) throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status);
        return body;
    }
    async function readFile(fileId, force = false) {
        const ctrl = new AbortController();
        const timer = setTimeout(()=>ctrl.abort(), READ_TIMEOUT_MS);
        try {
            const res = await authFetch(`/api/files/${encodeURIComponent(fileId)}/read${force ? '?force=true' : ''}`, {
                method: 'POST',
                signal: ctrl.signal
            });
            if (res.ok) return await res.json();
            const body = await res.json().catch(()=>({}));
            const detail = typeof body.detail === 'object' && body.detail !== null ? body.detail : {};
            throw new ApiError(detail.message ?? `HTTP ${res.status}`, detail.code ?? READ_STATUS_CODES[res.status] ?? null, res.status, null, detail.reason ?? null);
        } catch (e) {
            if (ctrl.signal.aborted) throw new ApiError('client_timeout', 'client_timeout');
            throw e;
        } finally{
            clearTimeout(timer);
        }
    }
    async function ask(body, signal) {
        const ctrl = new AbortController();
        let timedOut = false;
        const timer = setTimeout(()=>{
            timedOut = true;
            ctrl.abort();
        }, ASK_TIMEOUT_MS[body.mode ?? 'extract']);
        const stop = ()=>ctrl.abort();
        if (signal?.aborted) ctrl.abort();
        else signal?.addEventListener('abort', stop, {
            once: true
        });
        try {
            const res = await authFetch('/api/documents/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body),
                signal: ctrl.signal
            });
            if (res.ok) return await res.json();
            const data = await res.json().catch(()=>({}));
            const detail = typeof data.detail === 'object' && data.detail !== null && !Array.isArray(data.detail) ? data.detail : {};
            throw new ApiError(detail.message ?? `HTTP ${res.status}`, detail.code ?? ASK_STATUS_CODES[res.status] ?? null, res.status);
        } catch (e) {
            if (ctrl.signal.aborted) {
                const code = timedOut ? 'client_timeout' : 'aborted';
                throw new ApiError(code, code);
            }
            throw e;
        } finally{
            clearTimeout(timer);
            signal?.removeEventListener('abort', stop);
        }
    }
    async function readArchive(caseId) {
        const res = await authFetch(`/api/case-files/${caseId}/archive`);
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new ApiError(body.detail?.message ?? `HTTP ${res.status}`, body.detail?.code ?? null, res.status);
        return body;
    }
    return {
        readArchive,
        gql,
        upload,
        download,
        preview,
        register,
        printRegister,
        search,
        readFile,
        ask
    };
}
