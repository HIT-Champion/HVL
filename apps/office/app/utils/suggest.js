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

export const READ_KEYS = [
    'type_code',
    'symbol',
    'issued_on',
    'issuer_name',
    'summary',
    'urgency'
];
export const FIELD_WARNINGS = {
    future_date: 'issued_on',
    invalid_date: 'issued_on',
    symbol_no_number: 'symbol',
    type_conflict: 'type_code'
};
const DATE = /^(19|20)\d{2}-\d{2}-\d{2}$/;
function realDate(v) {
    const day = new Date(`${v}T00:00:00Z`);
    return DATE.test(v) && !Number.isNaN(day.getTime()) && day.toISOString().slice(0, 10) === v;
}
function usable(key, field, opts) {
    if (!field || typeof field !== 'object') return undefined;
    const { value, confidence, source } = field;
    if (typeof value !== 'string' || ![
        'high',
        'medium',
        'low'
    ].includes(String(confidence))) return undefined;
    const v = value.normalize('NFC').trim();
    if (!v) return undefined;
    if (key === 'type_code' && opts.types?.length && !opts.types.includes(v)) return undefined;
    if (key === 'urgency' && opts.urgencies?.length && !opts.urgencies.includes(v)) return undefined;
    if (key === 'issued_on' && !realDate(v)) return undefined;
    return {
        value: v,
        confidence: confidence,
        source: source === 'model' ? 'model' : 'rule'
    };
}
export function applySuggestion(form, defaults, previous, result, opts = {}) {
    const out = {
        values: {},
        filled: [],
        suggested: {},
        offers: {}
    };
    const touched = new Set(opts.touched ?? []);
    if (opts.offerOnly) {
        out.suggested = {
            ...previous
        };
        for (const key of READ_KEYS){
            const field = usable(key, result?.fields?.[key], opts);
            if (field && field.value !== (form[key] ?? '')) out.offers[key] = field;
        }
        return out;
    }
    for (const key of READ_KEYS){
        const field = usable(key, result?.fields?.[key], opts);
        const current = form[key] ?? '';
        const base = defaults[key] ?? '';
        const free = !touched.has(key);
        const agentValue = previous[key] !== undefined && current === previous[key].value;
        const fromAgent = free && agentValue;
        const owned = free && (fromAgent || current.trim() === '' || current === base);
        let value = fromAgent ? base : current;
        if (field && field.confidence !== 'low' && owned) {
            value = field.value;
            out.suggested[key] = field;
            out.filled.push(key);
        } else if (agentValue && !free) {
            out.suggested[key] = previous[key];
            if (field && field.value !== current) out.offers[key] = field;
        } else if (field && previous[key] && !owned) {
            out.suggested[key] = field;
        } else if (field && field.value === value) {
            if (field.confidence !== 'low') out.suggested[key] = field;
        } else if (field) {
            out.offers[key] = field;
        }
        if (value !== current) out.values[key] = value;
    }
    return out;
}
export function acceptOffer(suggested, offers, key) {
    const field = offers[key];
    if (!field) return null;
    const rest = {
        ...offers
    };
    delete rest[key];
    return {
        value: field.value,
        suggested: {
            ...suggested,
            [key]: field
        },
        offers: rest
    };
}
export function tagState(field, value) {
    if (!field) return null;
    if (value !== field.value) return 'edited';
    if (field.source === 'model') return 'model';
    return field.confidence === 'high' ? 'high' : 'medium';
}
export function openOffer(offers, form, key) {
    const field = offers[key];
    return field && field.value !== form[key] ? field : undefined;
}
