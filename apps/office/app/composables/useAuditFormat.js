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

import { useI18n } from 'vue-i18n';
const HIDDEN = new Set([
    'id',
    'tenant_id',
    'created_at',
    'updated_at',
    'created_by',
    'object_key',
    'document_id',
    'file_id',
    'case_file_id'
]);
const META_ONLY = new Set([
    'intake.suggested',
    'assistant.answered',
    'assignment.suggested'
]);
export function useAuditFormat(names, departments, units) {
    const { t, te } = useI18n();
    function label(map, key) {
        return te(`${map}.${key}`) ? t(`${map}.${key}`) : key;
    }
    function action(row) {
        const sig = row.overview.signature;
        if (row.action === 'file.rejected' && typeof sig === 'string' && (sig.startsWith('Heuristics.Encrypted.') || sig.startsWith('Heuristics.Limits.Exceeded'))) {
            return label('audit.action', 'file.unscannable');
        }
        return label('audit.action', row.action);
    }
    function who(row) {
        if (row.actor_kind === 'agent') return t('audit.agent', {
            name: label('audit.agents', row.actor_id)
        });
        const name = names.value.get(row.actor_id);
        if (row.actor_kind === 'service') return name ? t('audit.service', {
            name
        }) : t('event.system');
        if (row.actor_kind === 'system') return t('event.system');
        return name ?? row.actor_id;
    }
    function show(col, value) {
        if (value === null || value === undefined || value === '') return '—';
        if (typeof value === 'boolean') return value ? t('audit.yes') : t('audit.no');
        if (typeof value === 'string' && value.startsWith('\\x')) return `${value.slice(2, 12)}…`;
        if (col === 'status') {
            if (te(`status.${value}`)) return t(`status.${value}`);
            return te(`audit.readStatus.${value}`) ? t(`audit.readStatus.${value}`) : label('assist.status', String(value));
        }
        if (col === 'urgency') return label('urgency', String(value));
        if (col === 'direction' || col === 'role') return label(`audit.${col}`, String(value));
        if (col === 'user_id' || col === 'signer_id') return names.value.get(String(value)) ?? String(value);
        if (col === 'department_id') return departments.value.get(String(value)) ?? String(value);
        if (col === 'to_tenant_id') return units?.value.get(String(value)) ?? String(value);
        if (col === 'registered_at' || col === 'archived_at' || col === 'delivered_at') return fmtDateTime(String(value));
        if (col === 'due_on' || col === 'issued_on' || col === 'closed_on') return fmtDate(String(value));
        if (col === 'archive_sha256') return `${String(value).replace(/^\\x/, '').slice(0, 10)}…`;
        if (col === 'size_bytes' && typeof value === 'number') return fmtSize(value);
        if (col === 'found') {
            return String(value).split(',').map((k)=>k.trim()).filter(Boolean).map((k)=>label('receive.read.field', k)).join(', ') || '—';
        }
        if (col === 'duration_ms' && Number.isFinite(Number(value))) {
            return t('audit.seconds', {
                n: fmtNumber(Math.round(Number(value) / 100) / 10)
            });
        }
        if (col === 'method') return label('receive.read.method', String(value));
        if (col === 'summary_source') return label('audit.summarySource', String(value));
        if (col === 'reason') return label('receive.read.reason', String(value));
        if (col === 'mode') return label('audit.askMode', String(value));
        if (col === 'answer_source') return label('audit.answerSource', String(value));
        if (col === 'warnings') {
            return String(value).split(',').map((k)=>k.trim()).filter(Boolean).map((k)=>label('assist.warning', k)).join('; ') || '—';
        }
        if (col === 'outcome') return label('assign.suggest.outcome', String(value));
        if (col === 'outcome_reason') return label('assign.suggest.reason', String(value));
        if (col === 'confidence') return label('assign.suggest.confidence', String(value));
        if (col === 'due_days' && Number.isInteger(Number(value))) {
            return t('assign.suggest.days', {
                n: Number(value)
            }, Number(value));
        }
        return String(value);
    }
    function changes(row) {
        const shown = [];
        const hidden = [];
        for (const [col, value] of Object.entries(row.overview)){
            if (HIDDEN.has(col)) continue;
            if (value === null && META_ONLY.has(row.action)) continue;
            if (value === null) {
                hidden.push(label('audit.col', col));
                continue;
            }
            if (!Array.isArray(value)) {
                shown.push({
                    col: label('audit.col', col),
                    text: show(col, value)
                });
                continue;
            }
            const [before, after] = value;
            if (row.action === 'insert' && (after === null || after === false)) continue;
            const text = row.action === 'insert' ? show(col, after) : row.action === 'delete' ? show(col, before) : `${show(col, before)} → ${show(col, after)}`;
            shown.push({
                col: label('audit.col', col),
                text
            });
        }
        return {
            shown,
            hidden
        };
    }
    return {
        label,
        action,
        who,
        show,
        changes
    };
}
