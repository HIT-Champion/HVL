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

const items = ref([]);
const unread = ref(0);
const lastPush = ref(null);
export function describeNotification(t, n) {
    const d = n.data;
    const task = d.form_key ? t(`task.${d.form_key}`) : '';
    const someone = t('notify.someone');
    const doc = d.restricted ? t('notify.restricted') : [
        d.symbol,
        d.summary
    ].filter(Boolean).join(' — ');
    const note = d.note ? t('notify.note', {
        note: d.note
    }) : '';
    switch(n.kind){
        case 'task.assigned':
            return {
                title: t('notify.taskAssigned', {
                    task
                }),
                detail: doc,
                note
            };
        case 'task.overdue':
            return {
                title: t('notify.taskOverdue', {
                    task
                }),
                detail: doc,
                note
            };
        case 'task.escalated':
            return {
                title: t('notify.taskEscalated', {
                    task,
                    name: d.assignee_name || someone
                }),
                detail: doc,
                note
            };
        case 'document.issued':
            return {
                title: t('notify.documentIssued', {
                    symbol: d.symbol ?? ''
                }),
                detail: d.restricted ? doc : d.summary ?? '',
                note
            };
        case 'document.processed':
            return {
                title: t('notify.documentProcessed', {
                    name: d.by_name || someone
                }),
                detail: doc,
                note
            };
        case 'document.overdue':
            return {
                title: t('notify.documentOverdue', {
                    due: fmtDate(d.due_on)
                }),
                detail: doc,
                note
            };
        case 'ot.alarm':
            return {
                title: t('notify.otAlarm', {
                    name: d.name ?? '',
                    value: fmtNumber(d.temperature)
                }),
                detail: doc,
                note
            };
        case 'document.incoming':
            return {
                title: t('notify.documentIncoming', {
                    name: d.from_name ?? ''
                }),
                detail: doc,
                note
            };
        default:
            return {
                title: n.kind,
                detail: doc,
                note
            };
    }
}
export function useNotifications() {
    const { gql } = useApi();
    async function load() {
        const data = await gql(`{
      core_notifications(order_by: {id: desc}, limit: 20) { id kind document_id data created_at read_at }
      core_notifications_aggregate(where: {read_at: {_is_null: true}}) { aggregate { count } }
    }`);
        items.value = data.core_notifications;
        unread.value = data.core_notifications_aggregate.aggregate.count;
    }
    function receive(msg) {
        if (items.value.some((n)=>n.id === msg.id)) return;
        const n = {
            ...msg,
            read_at: null
        };
        items.value = [
            n,
            ...items.value
        ].slice(0, 20);
        unread.value += 1;
        lastPush.value = n;
    }
    async function markRead(n) {
        if (n.read_at) return;
        const at = new Date().toISOString();
        await gql('mutation ($id: bigint!, $at: timestamptz!) { update_core_notifications_by_pk(pk_columns: {id: $id}, _set: {read_at: $at}) { id } }', {
            id: n.id,
            at
        });
        n.read_at = at;
        unread.value = Math.max(unread.value - 1, 0);
    }
    async function markAllRead() {
        const at = new Date().toISOString();
        await gql('mutation ($at: timestamptz!) { update_core_notifications(where: {read_at: {_is_null: true}}, _set: {read_at: $at}) { affected_rows } }', {
            at
        });
        for (const n of items.value)n.read_at ??= at;
        unread.value = 0;
    }
    return {
        items,
        unread,
        lastPush,
        load,
        receive,
        markRead,
        markAllRead
    };
}
