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

// Lọc nhanh trên các dòng đã tải, không gọi lại máy chủ; so khớp không dấu ("dao tao" ra "Đào tạo")
const query = ref('')
const normalize = (value: string) =>
  value.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/g, 'd')
const filteredRows = computed(() => {
  const needle = normalize(query.value)
  return rows.value.filter((row) =>
    normalize([row.symbol, row.summary, row.department?.name, row.creator?.full_name].join(' ')).includes(needle))
})
</script>

<template>
  <div>
    <PageHeader :title="t('outgoing.title')" :subtitle="t('fe.listHint')">
      <NuxtLink v-if="claims?.role === 'staff'" to="/van-ban-di/soan" class="btn-primary">
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" d="M12 5v14m-7-7h14" /></svg>
        {{ t('outgoing.compose') }}
      </NuxtLink>
    </PageHeader>

    <div class="moc-tabs" role="tablist">
      <button
        v-for="(_, key) in tabs" :key="key" role="tab" :aria-selected="tab === key"
        @click="router.replace({ query: { tab: key } })"
      >
        {{ t(`outgoing.tab.${key}`) }}
      </button>
    </div>

    <div class="moc-toolbar">
      <input
        v-model="query" type="search" class="input" :aria-label="t('fe.filterDocuments')"
        :placeholder="t('fe.filterDocuments')"
      >
      <span class="moc-count" aria-live="polite">{{ t('fe.loaded', { n: filteredRows.length }) }}</span>
    </div>
    <div v-if="failure" class="moc-state" role="alert">
      <span>{{ failure }}</span>
      <button class="btn-secondary" @click="load()">{{ t('app.retry') }}</button>
    </div>
    <div v-else-if="loading && !rows.length" role="status" aria-busy="true" :aria-label="t('fe.loading')">
      <div v-for="n in 5" :key="n" class="moc-skeleton" />
    </div>
    <p v-else-if="!filteredRows.length" class="moc-empty">{{ t('outgoing.empty') }}</p>
    <div v-else class="moc-doc-table moc-outgoing-table overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr>
            <th class="px-4">{{ t('outgoing.symbol') }}</th>
            <th class="px-4">{{ t('outgoing.summary') }}</th>
            <th class="px-4">{{ t('outgoing.status') }}</th>
            <th class="px-4">{{ t('outgoing.issuedOn') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredRows" :key="row.id" class="cursor-pointer"
            @click="router.push(`/van-ban/${row.id}`)"
          >
            <td class="px-4 whitespace-nowrap">
              <div v-if="row.symbol" class="font-medium tabular-nums">{{ row.symbol }}</div>
              <div v-else class="text-stone-500">{{ t('outgoing.unnumbered') }}</div>
              <div class="mt-0.5 text-[13px] text-stone-500">{{ row.type_code }}</div>
            </td>
            <td class="max-w-xl px-4">
              <NuxtLink :to="`/van-ban/${row.id}`" class="moc-doc-title" @click.stop>{{ row.summary }}</NuxtLink>
              <div class="moc-doc-meta">
                {{ row.department?.name }}<span v-if="row.creator"> · {{ row.creator.full_name }}</span>
                <UrgencyChip :urgency="row.urgency" quiet />
              </div>
            </td>
            <td class="px-4"><StatusChip :status="row.status" /></td>
            <td :data-label="t('outgoing.issuedOn')" class="px-4 whitespace-nowrap text-stone-600 tabular-nums">
              {{ fmtDate(row.issued_on) }}
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="more" class="moc-more">
        <button class="btn-secondary" :disabled="loading" data-testid="list-more" @click="load(true)">
          {{ t('app.more') }}
        </button>
      </div>
    </div>
  </div>
</template>
