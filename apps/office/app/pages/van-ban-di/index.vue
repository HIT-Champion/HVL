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

// Văn bản đi (F2.4): dự thảo của phòng, văn bản đang trình, đã phát hành. Hasura chỉ trả văn bản người dùng
// được đọc: chuyên viên thấy văn bản đi của phòng mình, văn thư và lãnh đạo đơn vị thấy cả đơn vị.

interface Row {
  id: string
  symbol: string | null
  summary: string
  status: string
  urgency: string
  type_code: string
  issued_on: string | null
  updated_at: string
  department: { name: string } | null
  creator: { full_name: string } | null
}

const { t } = useI18n()
const { gql } = useApi()
const claims = useAuth().claims
const route = useRoute()
const router = useRouter()

const tabs = {
  drafts: ['draft', 'returned'],
  review: ['in_review', 'approved'],
  issued: ['issued', 'archived'],
  all: null,
} as const
type Tab = keyof typeof tabs

const tab = computed<Tab>(() => (String(route.query.tab ?? '') in tabs ? (route.query.tab as Tab) : 'all'))
const rows = ref<Row[]>([])
const loading = ref(true)
const failure = ref('')
const more = ref(false)
// Từng trang, "Xem thêm" nối tiếp — không cắt cứng ở một số dòng (văn bản cũ, dễ quá hạn, vẫn tới được).
// Danh sách đổi giữa hai lần lấy thì nextPage/mergePage (utils/paging.ts) lo không lặp, không sót dòng
const notice = useNotice()
let seq = 0

async function load(append = false) {
  const mine = ++seq
  loading.value = true
  if (!append) {
    failure.value = ''
    rows.value = []
  }
  const page = nextPage(rows.value.length)
  const statuses = tabs[tab.value]
  try {
    const data = await gql<{ office_documents: Row[] }>(`
      query ($where: office_documents_bool_exp!, $offset: Int!, $limit: Int!) {
        office_documents(where: $where, order_by: [{issued_on: desc_nulls_first}, {updated_at: desc}, {id: asc}], limit: $limit, offset: $offset) {
          id symbol summary status urgency type_code issued_on updated_at department { name } creator { full_name }
        }
      }`, {
      where: { direction: { _eq: 'out' }, ...(statuses ? { status: { _in: statuses } } : {}) },
      ...page,
    })
    if (mine !== seq) return   // đã đổi tab trong lúc chờ: bỏ kết quả cũ
    const merged = mergePage(rows.value, data.office_documents)
    rows.value = merged.rows
    more.value = merged.more
  } catch (e) {
    // lỗi khi "Xem thêm": giữ nguyên bảng đang hiện, báo ở góc màn hình — bấm lại được
    if (mine === seq && append) notice.error(errorText(t, e))
    else if (mine === seq) failure.value = errorText(t, e)
  } finally {
    if (mine === seq) loading.value = false
  }
}

watch(tab, () => load())
onMounted(() => load())
</script>

<template>
  <div>
    <PageHeader :title="t('outgoing.title')">
      <NuxtLink v-if="claims?.role === 'staff'" to="/van-ban-di/soan" class="btn-primary">
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" d="M12 5v14m-7-7h14" /></svg>
        {{ t('outgoing.compose') }}
      </NuxtLink>
    </PageHeader>

    <div class="mb-4 flex gap-1 border-b border-stone-200" role="tablist">
      <button
        v-for="(_, key) in tabs" :key="key" role="tab" :aria-selected="tab === key"
        class="-mb-px border-b-2 px-4 py-2 text-sm font-medium"
        :class="tab === key ? 'border-brand-700 text-brand-800' : 'border-transparent text-stone-500 hover:text-stone-800'"
        @click="router.replace({ query: { tab: key } })"
      >
        {{ t(`outgoing.tab.${key}`) }}
      </button>
    </div>

    <p v-if="failure" class="card p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-else-if="loading && !rows.length" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <p v-else-if="!rows.length" class="card p-12 text-center text-stone-500">{{ t('outgoing.empty') }}</p>
    <div v-else class="card overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="border-b border-stone-200 bg-stone-50 text-left text-xs font-medium tracking-wide text-stone-500 uppercase">
          <tr>
            <th class="px-4 py-3">{{ t('outgoing.symbol') }}</th>
            <th class="px-4 py-3">{{ t('outgoing.summary') }}</th>
            <th class="px-4 py-3">{{ t('outgoing.status') }}</th>
            <th class="px-4 py-3">{{ t('outgoing.issuedOn') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-stone-100">
          <tr v-for="row in rows" :key="row.id" class="cursor-pointer hover:bg-brand-50/40" @click="router.push(`/van-ban/${row.id}`)">
            <td class="px-4 py-3 whitespace-nowrap">
              <div v-if="row.symbol" class="font-medium">{{ row.symbol }}</div>
              <div v-else class="text-stone-400">{{ t('outgoing.unnumbered') }}</div>
              <div class="text-xs text-stone-500">{{ row.type_code }}</div>
            </td>
            <td class="max-w-md px-4 py-3">
              <NuxtLink :to="`/van-ban/${row.id}`" class="line-clamp-2 text-stone-900 hover:text-brand-800" @click.stop>{{ row.summary }}</NuxtLink>
              <div class="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-stone-500">
                {{ row.department?.name }}<span v-if="row.creator"> · {{ row.creator.full_name }}</span>
                <UrgencyChip :urgency="row.urgency" quiet />
              </div>
            </td>
            <td class="px-4 py-3"><StatusChip :status="row.status" /></td>
            <td class="px-4 py-3 whitespace-nowrap text-stone-600">{{ fmtDate(row.issued_on) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="more" class="border-t border-stone-100 p-3 text-center">
        <button class="btn-secondary" :disabled="loading" data-testid="list-more" @click="load(true)">{{ t('app.more') }}</button>
      </div>
    </div>
  </div>
</template>
