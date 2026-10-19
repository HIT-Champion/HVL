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

import { ApiError } from '~/composables/useApi';
const CONSTRAINTS = [
    'documents_in_dedup',
    'documents_due_after_registered',
    'documents_body_length',
    'document_files_sealed',
    'documents_restricted_sealed',
    'documents_restricted_local',
    'documents_recipient_units'
];
export function errorText(t, e) {
    if (e instanceof ApiError) {
        if (e.code === 'network') return t('error.network');
        if (e.code === 'session') return t('error.session');
        if (e.code === 'infected') return t('error.infected');
        if (e.code === 'unscannable') return t('error.unscannable');
        if (e.code === 'invalid' && e.fields?.recipient_tenant_ids) {
            return t(e.fields.recipient_tenant_ids === 'restricted' ? 'error.documents_restricted_local' : 'error.documents_recipient_units');
        }
        if (e.code === 'invalid') return t('error.invalid');
        if (e.code === 'duplicate') return t('error.documents_in_dedup');
        if (e.status === 413) return t('error.too_large');
        if (e.status === 429) return t('error.rate_limited');
        for (const name of CONSTRAINTS)if (e.message.includes(name)) return t(`error.${name}`);
        if (e.message.includes('summary')) return t('error.documents_summary');
        return e.message;
    }
    return t('error.generic', {
        msg: e instanceof Error ? e.message : String(e)
    });
}
