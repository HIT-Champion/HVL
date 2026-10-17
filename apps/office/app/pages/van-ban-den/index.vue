<!--
  Copyright 2026 Mộc Team

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

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

interface Row {
  id: string
  symbol: string | null
  issuer_name: string | null
  summary: string
  status: string
  urgency: string
  register_number: number | null
  registered_at: string | null
  due_on: string | null
  issued_on: string | null
  restricted: boolean
}

const { t } = useI18n()
const { gql } = useApi()
const claims = useAuth().claims
const route = useRoute()
const router = useRouter()

const tabs = {
  received: ['received'],
  active: ['registered', 'in_progress'],
  done: ['done', 'archived'],
  all: null,
} as const
type Tab = keyof typeof tabs

const tab = computed<Tab>(() => (String(route.query.tab ?? '') in tabs ? (route.query.tab as Tab) : 'all'))
const rows = ref<Row[]>([])
const loading = ref(true)
const failure = ref('')

async function load() {
  loading.value = true
  failure.value = ''
  const statuses = tabs[tab.value]
  try {
    const data = await gql<{ office_documents: Row[] }>(`
      query ($where: office_documents_bool_exp!) {
        office_documents(where: $where, order_by: [{registered_at: desc_nulls_first}, {created_at: desc}], limit: 200) {
          id symbol issuer_name summary status urgency register_number registered_at due_on issued_on restricted
        }
      }`, { where: { direction: { _eq: 'in' }, ...(statuses ? { status: { _in: statuses } } : {}) } })
    rows.value = data.office_documents
  } catch (e) {
    failure.value = errorText(t, e)
  } finally {
    loading.value = false
  }
}

watch(tab, load)
onMounted(load)
</script>

<template>
  <div>
    <PageHeader :title="t('incoming.title')">
      <NuxtLink v-if="claims?.role === 'clerk'" to="/van-ban-den/tiep-nhan" class="btn-primary">
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" d="M12 5v14m-7-7h14" /></svg>
        {{ t('incoming.receive') }}
      </NuxtLink>
    </PageHeader>

    <div class="mb-4 flex gap-1 border-b border-stone-200" role="tablist">
      <button
        v-for="(_, key) in tabs" :key="key" role="tab" :aria-selected="tab === key"
        class="-mb-px border-b-2 px-4 py-2 text-sm font-medium"
        :class="tab === key ? 'border-brand-700 text-brand-800' : 'border-transparent text-stone-500 hover:text-stone-800'"
        @click="router.replace({ query: { tab: key } })"
      >
        {{ t(`incoming.tab.${key}`) }}
      </button>
    </div>

    <p v-if="failure" class="card p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-else-if="loading" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <p v-else-if="!rows.length" class="card p-12 text-center text-stone-500">{{ t('incoming.empty') }}</p>
    <div v-else class="card overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="border-b border-stone-200 bg-stone-50 text-left text-xs font-medium tracking-wide text-stone-500 uppercase">
          <tr>
            <th class="px-4 py-3">{{ t('incoming.number') }}</th>
            <th class="px-4 py-3">{{ t('incoming.symbol') }}</th>
            <th class="px-4 py-3">{{ t('incoming.summary') }}</th>
            <th class="px-4 py-3">{{ t('incoming.status') }}</th>
            <th class="px-4 py-3">{{ t('incoming.due') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-stone-100">
          <tr v-for="row in rows" :key="row.id" class="cursor-pointer hover:bg-brand-50/40" @click="router.push(`/van-ban/${row.id}`)">
            <td class="px-4 py-3 font-semibold text-stone-700 tabular-nums">{{ row.register_number ?? '—' }}</td>
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
            <td class="px-4 py-3 whitespace-nowrap text-stone-600">{{ fmtDate(row.due_on) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
