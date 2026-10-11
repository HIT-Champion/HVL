<!--
  Copyright 2026 Signet Team

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  SPDX-License-Identifier: Apache-2.0
-->

<script setup>
import { useI18n } from 'vue-i18n';
const {
  t
} = useI18n();
const {
  gql
} = useApi();
const claims = useAuth().claims;
const route = useRoute();
const router = useRouter();
const tabs = {
  received: ['received'],
  active: ['registered', 'in_progress'],
  done: ['done', 'archived'],
  all: null
};
const tab = computed(() => String(route.query.tab ?? '') in tabs ? route.query.tab : 'all');
const rows = ref([]);
const query = ref('');
const page = ref(1);
const pageSize = 20;
const normalize = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').toLowerCase();
const filteredRows = computed(() => rows.value.filter(row => normalize([row.symbol, row.summary, row.issuer_name, row.department?.name, row.creator?.full_name].join(' ')).includes(normalize(query.value))));
const pages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize)));
const pageRows = computed(() => filteredRows.value.slice((page.value - 1) * pageSize, page.value * pageSize));
watch([query, tab], () => { page.value = 1; });
watch(pages, value => { page.value = Math.min(page.value, value); });
let version = 0;
onBeforeUnmount(() => { version++; });
const loading = ref(true);
const failure = ref('');
async function load() {
  const current = ++version;
  loading.value = true;
  failure.value = '';
  const statuses = tabs[tab.value];
  try {
    const data = await gql(`
      query ($where: office_documents_bool_exp!) {
        office_documents(where: $where, order_by: [{registered_at: desc_nulls_first}, {created_at: desc}], limit: 200) {
          id symbol issuer_name summary status urgency register_number registered_at due_on issued_on restricted
        }
      }`, {
      where: {
        direction: {
          _eq: 'in'
        },
        ...(statuses ? {
          status: {
            _in: statuses
          }
        } : {})
      }
    });
    if (current === version) rows.value = data.office_documents;
  } catch (e) {
    if (current === version) failure.value = errorText(t, e);
  } finally {
    if (current === version) loading.value = false;
  }
}
watch(tab, load);
onMounted(load);
</script>

<template>
  <div>
    <PageHeader :title="t('incoming.title')" :subtitle="t('fe.listHint')">
      <NuxtLink v-if="claims?.role === 'clerk'" to="/van-ban-den/tiep-nhan" class="btn-primary">
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" d="M12 5v14m-7-7h14" /></svg>
        {{ t('incoming.receive') }}
      </NuxtLink>
    </PageHeader>

    <div class="moc-tabs" role="tablist">
      <button
        v-for="(_, key) in tabs" :key="key" role="tab" :aria-selected="tab === key"
        class="-mb-px border-b-2 px-4 py-2 text-sm font-medium"
        :class="tab === key ? 'border-brand-700 text-brand-800' : 'border-transparent text-stone-500 hover:text-stone-800'"
        @click="router.replace({ query: { tab: key } })"
      >
        {{ t(`incoming.tab.${key}`) }}
      </button>
    </div>

    <div class="moc-toolbar"><input v-model="query" type="search" class="input" :aria-label="t('fe.filterDocuments')" :placeholder="t('fe.filterDocuments')"><span class="moc-count" aria-live="polite">{{ t('fe.loaded', { n: filteredRows.length }) }}</span></div>
    <div v-if="failure" class="moc-state" role="alert"><span>{{ failure }}</span><button class="btn-secondary" @click="load">{{ t('app.retry') }}</button></div>
    <div v-else-if="loading" aria-busy="true" :aria-label="t('fe.loading')"><div v-for="n in 5" :key="n" class="moc-skeleton" /></div>
    <p v-else-if="!filteredRows.length" class="card p-12 text-center text-stone-500">{{ t('incoming.empty') }}</p>
    <div v-else class="moc-doc-table moc-incoming-table overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="border-b border-stone-200 text-left text-xs font-medium text-stone-500">
          <tr>
            <th class="px-4 py-3">{{ t('incoming.number') }}</th>
            <th class="px-4 py-3">{{ t('incoming.symbol') }}</th>
            <th class="px-4 py-3">{{ t('incoming.summary') }}</th>
            <th class="px-4 py-3">{{ t('incoming.status') }}</th>
            <th class="px-4 py-3">{{ t('incoming.due') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-stone-100">
          <tr v-for="row in pageRows" :key="row.id" class="cursor-pointer hover:bg-brand-50/40" @click="router.push(`/van-ban/${row.id}`)">
            <td :data-label="t('incoming.number')" class="px-4 py-3 font-semibold text-stone-700 tabular-nums">{{ row.register_number ?? '—' }}</td>
            <td class="px-4 py-3 whitespace-nowrap">
              <div class="font-medium">{{ row.symbol }}</div>
              <div class="text-xs text-stone-500">{{ fmtDate(row.issued_on) }}</div>
            </td>
            <td class="max-w-md px-4 py-3">
              <NuxtLink :to="`/van-ban/${row.id}`" class="line-clamp-2 text-stone-900 hover:text-brand-800" @click.stop>{{ row.summary }}</NuxtLink>
              <div class="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-stone-500">
                {{ row.issuer_name }}
                <UrgencyChip :urgency="row.urgency" quiet />
                <span v-if="row.restricted" class="chip bg-stone-800 text-white">{{ t('doc.restricted') }}</span>
              </div>
            </td>
            <td class="px-4 py-3"><StatusChip :status="row.status" /></td>
            <td :data-label="t('incoming.due')" class="px-4 py-3 whitespace-nowrap text-stone-600">{{ fmtDate(row.due_on) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
