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

// Định dạng ngày giờ theo kiểu Việt Nam (dd/mm/yyyy), dùng chung cho mọi trang.

export const MAX_QUESTION = 500;
const CITE = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;
export function segments(text, sources) {
    const out = [];
    if (!text) return out;
    const byN = new Map(sources.map((s)=>[
            s.n,
            s
        ]));
    const push = (chunk)=>{
        if (!chunk) return;
        const last = out[out.length - 1];
        if (last && 'text' in last) last.text += chunk;
        else out.push({
            text: chunk
        });
    };
    let at = 0;
    for (const m of text.matchAll(CITE)){
        const start = m.index ?? 0;
        push(text.slice(at, start));
        const ns = (m[1] ?? '').split(',').map((x)=>Number(x.trim()));
        const found = ns.map((n)=>byN.get(n));
        if (found.every((s)=>s !== undefined)) found.forEach((s, i)=>out.push({
                n: ns[i],
                source: s
            }));
        else push(m[0]);
        at = start + m[0].length;
    }
    push(text.slice(at));
    return out;
}
export function citeLabel(source, t, spoken = false) {
    const name = source.symbol?.trim() || source.type_name?.trim() || source.type_code;
    const where = [];
    if (source.kind === 'meta') where.push(t('assist.summaryOnly'));
    else {
        if (source.file_role === 'attachment') where.push(t('assist.attachment'));
        if (source.page !== null && source.page !== undefined) where.push(t(spoken ? 'assist.pageSpoken' : 'assist.page', {
            n: source.page
        }));
    }
    return where.length ? t(spoken ? 'assist.citeSpoken' : 'assist.citeLabel', {
        symbol: name,
        where: where.join(', ')
    }) : name;
}
export function sourceAnchor(askId, n) {
    return `nguon-${askId.replace(/[^A-Za-z0-9_-]/g, '')}-${n}`;
}
export function cleanQuestion(s) {
    return s.normalize('NFC').replace(/\s+/gu, ' ').replace(/[\p{Cc}\p{Cf}]/gu, '').replace(/ {2,}/g, ' ').trim();
}
export function needsGenerate(res) {
    return res.ai_available === true && res.status !== 'no_evidence' && res.sources.length > 0;
}
export function blocks(res) {
    const model = res.answer?.source === 'model' && res.answer.text ? res.answer : null;
    const extract = res.extract?.text ? res.extract : res.answer?.source === 'extract' && res.answer.text ? res.answer : null;
    return {
        model,
        extract
    };
}
export const MASK_RE = /\[(?:CCCD|CMND|SĐT|EMAIL|STK)(?:-\d{1,3})?\]/u;
export function hasMask(text) {
    return !!text && MASK_RE.test(text);
}
export function tidy(res) {
    const sources = Array.isArray(res.sources) ? res.sources.map((s)=>({
            ...s,
            excerpt: typeof s.excerpt === 'string' ? s.excerpt : ''
        })).sort((a, b)=>a.n - b.n) : [];
    const warnings = Array.isArray(res.warnings) ? [
        ...new Set(res.warnings.filter((w)=>typeof w === 'string'))
    ] : [];
    return {
        ...res,
        sources,
        warnings,
        answer: res.answer ?? null,
        extract: res.extract ?? null
    };
}
