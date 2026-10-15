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

export const POLL_MS = 3000;
export const WAIT_MS = 60000;
export const MAX_POLLS = Math.ceil(WAIT_MS / POLL_MS);
export const MAX_EVIDENCE = 3;
export const SUMMARY_MAX = 80;
export const SUGGEST_REASONS = [
    'no_similar',
    'no_history',
    'no_valid_unit',
    'low_confidence',
    'timeout',
    'unavailable'
];
export function pollState(row, registeredAt, now) {
    if (row) return 'stop';
    const at = registeredAt ? Date.parse(registeredAt) : Number.NaN;
    if (!Number.isFinite(at)) return 'stop';
    return now - at < WAIT_MS ? 'wait' : 'stop';
}
const TONES = {
    high: 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-300',
    medium: 'bg-amber-50 text-amber-900 ring-1 ring-amber-300',
    low: 'bg-stone-100 text-stone-700 ring-1 ring-stone-300'
};
export function confidenceTone(c) {
    return c === 'high' || c === 'medium' ? TONES[c] : TONES.low;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function readEvidence(evidence) {
    if (!Array.isArray(evidence)) return [];
    const seen = new Set();
    const out = [];
    for (const item of evidence){
        if (!item || typeof item !== 'object') continue;
        const e = item;
        const id = e.document_id;
        const score = e.score;
        if (typeof id !== 'string' || !UUID.test(id) || seen.has(id)) continue;
        if (typeof score !== 'number' || !Number.isFinite(score)) continue;
        seen.add(id);
        const days = e.days;
        out.push({
            document_id: id,
            score,
            department_id: typeof e.department_id === 'string' && e.department_id ? e.department_id : null,
            days: typeof days === 'number' && Number.isInteger(days) && days > 0 ? days : null
        });
    }
    return out.sort((a, b)=>b.score - a.score);
}
export function evidenceIds(evidence) {
    return readEvidence(evidence).map((e)=>e.document_id);
}
export function clipSummary(text, max = SUMMARY_MAX) {
    const clean = (text ?? '').normalize('NFC').replace(/\s+/gu, ' ').trim();
    const chars = Array.from(clean);
    if (chars.length <= max) return clean;
    return `${chars.slice(0, max - 1).join('').trimEnd()}…`;
}
export function shownEvidence(evidence, readable, max = MAX_EVIDENCE) {
    const out = [];
    for (const e of readEvidence(evidence)){
        if (out.length >= max) break;
        const doc = readable.get(e.document_id);
        if (!doc) continue;
        out.push({
            ...e,
            symbol: doc.symbol?.trim() || null,
            summary: clipSummary(doc.summary)
        });
    }
    return out;
}
const DATE = /^\d{4}-\d{2}-\d{2}$/;
export function applyValues(s, documentDue, today) {
    if (!s || s.status !== 'suggested' || !s.department_id) return null;
    let due = documentDue ? null : s.due_on;
    if (due && (!DATE.test(due) || today && due < today)) due = null;
    return {
        department_id: s.department_id,
        due_on: due ?? null
    };
}
export function matchState(s, chosen) {
    if (!s || s.status !== 'suggested' || !s.department_id || !chosen) return null;
    return chosen === s.department_id ? 'kept' : 'changed';
}
export function reasonKey(reason) {
    return reason && SUGGEST_REASONS.includes(reason) ? `assign.suggest.reason.${reason}` : null;
}
