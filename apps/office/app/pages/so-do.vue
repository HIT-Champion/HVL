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
import type { FeedbackSummaryRow } from '~/utils/feedback'
import type { AssignRow, OverdueRow, SearchRun } from '~/utils/metrics'

// Số đo trước / sau theo đặc tả §8 (F4.6), cho lãnh đạo đơn vị. Cách đo, cách đọc: docs/so-lieu-sau.md.
// (a), (b) đọc hai khung nhìn chỉ có số đếm, số giờ (migration 1792281602750) bằng token người xem — Hasura lọc theo
// đơn vị, vai trò khác bị từ chối. (c) bấm giờ ngay trên trình duyệt khi lãnh đạo bấm nút: 5 lần tìm số ký hiệu của
// văn bản đến cũ nhất qua /api/search, kết quả không lưu. (d) chỉ so sánh định tính. Cột "trước" luôn là "chưa đo" khi
// chưa có đơn vị chạy thử; số trên đơn vị mẫu của make seed có dòng ghi rõ là dữ liệu mẫu.

const QUERY = `{
  office_v_time_to_assign { sample month arrived assigned median_hours p90_hours handled handled_median_hours
    handled_p90_hours waiting }
  office_v_overdue_rate { sample month judged on_time late late_open pending }
  office_v_feedback_summary(where: {screen: {_is_null: true}}) { sample screen feedback rating_total rating_1 rating_2
    rating_3 rating_4 rating_5 with_comment last_at }
}`
const OLDEST = `{ office_documents(where: {direction: {_eq: "in"}, restricted: {_eq: false}, status: {_neq: "cancelled"},
  symbol: {_is_null: false}}, order_by: [{created_at: asc}, {id: asc}], limit: 25) { id symbol } }`

const { t, locale } = useI18n()
const { gql, search } = useApi()
const claims = useAuth().claims

const assign = ref<AssignRow[]>([])
const overdue = ref<OverdueRow[]>([])
const feedback = ref<FeedbackSummaryRow[]>([])
const loaded = ref(false)
const loading = ref(false)
const failure = ref('')
const runs = ref<SearchRun[]>([])
const measuring = ref(false)
const searchFailure = ref('')
const allowed = computed(() => claims.value?.role === 'director')

async function load() {
  loading.value = true
  failure.value = ''
  try {
    const data = await gql<{
      office_v_time_to_assign: AssignRow[]
      office_v_overdue_rate: OverdueRow[]
      office_v_feedback_summary: FeedbackSummaryRow[]
    }>(QUERY)
    assign.value = data.office_v_time_to_assign
    overdue.value = data.office_v_overdue_rate
    feedback.value = data.office_v_feedback_summary
    loaded.value = true
  } catch (e) {
    failure.value = errorText(t, e)
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  if (allowed.value) load()
})

// (c) Mỗi lần: gọi /api/search với số ký hiệu, đo từ lúc gửi tới lúc có kết quả, xem văn bản cần tìm đứng thứ mấy.
// Lần lượt, không song song: đo độ trễ của từng lần tìm như một người tìm, không đo sức chịu tải
async function measureSearch() {
  measuring.value = true
  searchFailure.value = ''
  runs.value = []
  try {
    const targets = pickSearchTargets((await gql<{ office_documents: { id: string; symbol: string | null }[] }>(OLDEST))
      .office_documents)
    if (targets.length < SEARCH_RUNS) searchFailure.value = t('metrics.searchFew', { n: targets.length, want: SEARCH_RUNS })
    for (const target of targets) {
      const started = performance.now()
      const res = await search({ q: target.symbol, limit: 20 })
      runs.value = [...runs.value, { ...target, ms: performance.now() - started, rank: rankOf(res.hits, target.id) }]
    }
  } catch (e) {
    searchFailure.value = errorText(t, e)
  } finally {
    measuring.value = false
  }
}

const number = computed(() => new Intl.NumberFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB', { maximumFractionDigits: 1 }))
const units = computed(() => ({ second: t('metrics.unit.second'), minute: t('metrics.unit.minute'),
  hour: t('metrics.unit.hour'), day: t('metrics.unit.day') }))
function duration(hours: number | null) {
  return fmtDuration(hours, units.value, (n) => number.value.format(n))
}
function monthLabel(iso: string | null) {
  if (!iso) return t('metrics.allMonths')
  const [y, m] = iso.split('-')
  return `${Number(m)}/${y}`
}
const sample = computed(() => isSample(assign.value, overdue.value, feedback.value))
const assignTotal = computed(() => totalRow(assign.value))
const overdueTotal = computed(() => totalRow(overdue.value))
const lateTotal = computed(() => overduePct(overdueTotal.value))
const searched = computed(() => searchSummary(runs.value))
const feedbackTotal = computed(() => feedback.value[0] ?? null)
const feedbackAverage = computed(() => averageRating(feedbackTotal.value))
</script>

<template>
  <div>
    <PageHeader :title="t('metrics.title')" :subtitle="t('metrics.subtitle')">
      <button v-if="allowed" class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>
    <p v-if="!allowed" class="card p-12 text-center text-stone-500">{{ t('metrics.forbidden') }}</p>
    <p v-else-if="failure" class="card mb-4 p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-if="allowed && !loaded && !failure" class="text-sm text-stone-500">{{ t('app.loading') }}</p>

    <div v-if="allowed && loaded" class="space-y-4">
      <p v-if="sample" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" data-testid="metrics-sample">
        {{ t('metrics.sampleNote') }}
      </p>

      <section class="card overflow-x-auto p-4" data-testid="metrics-table">
        <h2 class="font-medium text-stone-900">{{ t('metrics.table') }}</h2>
        <table class="mt-2 w-full min-w-[40rem] text-sm">
          <thead class="text-left text-xs text-stone-500">
            <tr>
              <th class="py-1 pr-3 font-medium">{{ t('metrics.indicator') }}</th>
              <th class="py-1 pr-3 font-medium">{{ t('metrics.before') }}</th>
              <th class="py-1 pr-3 font-medium">{{ t('metrics.after') }}</th>
              <th class="py-1 font-medium">{{ t('metrics.how') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100 align-top">
            <tr data-testid="metrics-assign">
              <td class="py-2 pr-3 font-medium text-stone-800">{{ t('metrics.assign.name') }}</td>
              <td class="py-2 pr-3 text-stone-500">{{ t('metrics.notMeasured') }}</td>
              <td class="py-2 pr-3">
                <template v-if="assignTotal && assignTotal.assigned">
                  <div class="font-medium tabular-nums">{{ t('metrics.assign.value', { median: duration(assignTotal.median_hours), p90: duration(assignTotal.p90_hours) }) }}</div>
                  <div class="text-xs text-stone-500">{{ t('metrics.assign.count', { n: assignTotal.assigned, waiting: assignTotal.waiting }) }}</div>
                </template>
                <span v-else class="text-stone-500">{{ t('metrics.noData') }}</span>
              </td>
              <td class="py-2 text-xs text-stone-500">{{ t('metrics.assign.how') }}</td>
            </tr>
            <tr data-testid="metrics-overdue">
              <td class="py-2 pr-3 font-medium text-stone-800">{{ t('metrics.overdue.name') }}</td>
              <td class="py-2 pr-3 text-stone-500">{{ t('metrics.notMeasured') }}</td>
              <td class="py-2 pr-3">
                <template v-if="overdueTotal && lateTotal !== null">
                  <div class="font-medium tabular-nums">{{ t('metrics.overdue.value', { pct: number.format(lateTotal), late: overdueTotal.late, judged: overdueTotal.judged }) }}</div>
                  <div class="text-xs text-stone-500">{{ t('metrics.overdue.count', { open: overdueTotal.late_open, pending: overdueTotal.pending }) }}</div>
                </template>
                <span v-else class="text-stone-500">{{ t('metrics.noData') }}</span>
              </td>
              <td class="py-2 text-xs text-stone-500">{{ t('metrics.overdue.how') }}</td>
            </tr>
            <tr data-testid="metrics-search">
              <td class="py-2 pr-3 font-medium text-stone-800">{{ t('metrics.search.name') }}</td>
              <td class="py-2 pr-3 text-stone-500">{{ t('metrics.notMeasured') }}</td>
              <td class="py-2 pr-3">
                <template v-if="runs.length">
                  <div class="font-medium tabular-nums">{{ t('metrics.search.value', { median: fmtMs(searched.median_ms, (n) => number.format(n)), max: fmtMs(searched.max_ms, (n) => number.format(n)) }) }}</div>
                  <div class="text-xs text-stone-500">{{ t('metrics.search.count', { n: searched.runs, found: searched.found }) }}</div>
                </template>
                <button class="btn-secondary mt-1" :disabled="measuring" data-testid="metrics-search-run" @click="measureSearch">
                  {{ measuring ? t('metrics.search.running') : t('metrics.search.run', { n: SEARCH_RUNS }) }}
                </button>
                <p v-if="searchFailure" class="mt-1 text-xs text-red-700">{{ searchFailure }}</p>
              </td>
              <td class="py-2 text-xs text-stone-500">{{ t('metrics.search.how') }}</td>
            </tr>
            <tr data-testid="metrics-handoffs">
              <td class="py-2 pr-3 font-medium text-stone-800">{{ t('metrics.handoffs.name') }}</td>
              <td class="py-2 pr-3 text-stone-500">{{ t('metrics.notMeasured') }}</td>
              <td class="py-2 pr-3 text-stone-700">{{ t('metrics.handoffs.value') }}</td>
              <td class="py-2 text-xs text-stone-500">{{ t('metrics.handoffs.how') }}</td>
            </tr>
          </tbody>
        </table>
        <p class="mt-3 text-xs text-stone-500">{{ t('metrics.beforeNote') }}</p>
      </section>

      <div class="grid gap-4 xl:grid-cols-2">
        <section class="card overflow-x-auto p-4" data-testid="metrics-assign-months">
          <h2 class="font-medium text-stone-900">{{ t('metrics.assign.byMonth') }}</h2>
          <p v-if="!monthRows(assign).length" class="py-8 text-center text-sm text-stone-500">{{ t('metrics.noData') }}</p>
          <table v-else class="mt-2 w-full text-sm">
            <thead class="text-left text-xs text-stone-500">
              <tr>
                <th class="py-1 font-medium">{{ t('metrics.month') }}</th>
                <th class="py-1 text-right font-medium">{{ t('metrics.assign.arrived') }}</th>
                <th class="py-1 text-right font-medium">{{ t('metrics.assign.assigned') }}</th>
                <th class="py-1 text-right font-medium">{{ t('metrics.median') }}</th>
                <th class="py-1 text-right font-medium">p90</th>
                <th class="py-1 text-right font-medium">{{ t('metrics.assign.handled') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="r in [...monthRows(assign), ...(assignTotal ? [assignTotal] : [])]" :key="r.month ?? 'all'" :class="r.month ? '' : 'font-medium'">
                <td class="py-1 text-stone-600">{{ monthLabel(r.month) }}</td>
                <td class="py-1 text-right tabular-nums">{{ r.arrived }}</td>
                <td class="py-1 text-right tabular-nums">{{ r.assigned }}</td>
                <td class="py-1 text-right tabular-nums">{{ duration(r.median_hours) }}</td>
                <td class="py-1 text-right tabular-nums">{{ duration(r.p90_hours) }}</td>
                <td class="py-1 text-right tabular-nums">{{ duration(r.handled_median_hours) }}</td>
              </tr>
            </tbody>
          </table>
          <p class="mt-2 text-xs text-stone-500">{{ t('metrics.assign.monthHint') }}</p>
        </section>

        <section class="card overflow-x-auto p-4" data-testid="metrics-overdue-months">
          <h2 class="font-medium text-stone-900">{{ t('metrics.overdue.byMonth') }}</h2>
          <p v-if="!monthRows(overdue).length" class="py-8 text-center text-sm text-stone-500">{{ t('metrics.noData') }}</p>
          <table v-else class="mt-2 w-full text-sm">
            <thead class="text-left text-xs text-stone-500">
              <tr>
                <th class="py-1 font-medium">{{ t('metrics.overdue.dueMonth') }}</th>
                <th class="py-1 text-right font-medium">{{ t('metrics.overdue.judged') }}</th>
                <th class="py-1 text-right font-medium">{{ t('metrics.overdue.late') }}</th>
                <th class="py-1 text-right font-medium">{{ t('metrics.overdue.open') }}</th>
                <th class="py-1 text-right font-medium">{{ t('metrics.overdue.pending') }}</th>
                <th class="py-1 text-right font-medium">%</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="r in [...monthRows(overdue), ...(overdueTotal ? [overdueTotal] : [])]" :key="r.month ?? 'all'" :class="r.month ? '' : 'font-medium'">
                <td class="py-1 text-stone-600">{{ monthLabel(r.month) }}</td>
                <td class="py-1 text-right tabular-nums">{{ r.judged }}</td>
                <td class="py-1 text-right tabular-nums" :class="r.late ? 'text-red-700' : ''">{{ r.late }}</td>
                <td class="py-1 text-right tabular-nums">{{ r.late_open }}</td>
                <td class="py-1 text-right tabular-nums">{{ r.pending }}</td>
                <td class="py-1 text-right tabular-nums">{{ overduePct(r) === null ? '—' : number.format(overduePct(r)!) }}</td>
              </tr>
            </tbody>
          </table>
          <p class="mt-2 text-xs text-stone-500">{{ t('metrics.overdue.monthHint') }}</p>
        </section>
      </div>

      <section v-if="runs.length" class="card overflow-x-auto p-4" data-testid="metrics-search-runs">
        <h2 class="font-medium text-stone-900">{{ t('metrics.search.runs') }}</h2>
        <table class="mt-2 w-full text-sm">
          <thead class="text-left text-xs text-stone-500">
            <tr>
              <th class="py-1 font-medium">{{ t('metrics.search.symbol') }}</th>
              <th class="py-1 text-right font-medium">{{ t('metrics.search.latency') }}</th>
              <th class="py-1 text-right font-medium">{{ t('metrics.search.rank') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100">
            <tr v-for="r in runs" :key="r.id">
              <td class="py-1"><NuxtLink :to="`/van-ban/${r.id}`" class="text-brand-700 hover:underline">{{ r.symbol }}</NuxtLink></td>
              <td class="py-1 text-right tabular-nums">{{ fmtMs(r.ms, (n) => number.format(n)) }}</td>
              <td class="py-1 text-right tabular-nums" :class="r.rank === null ? 'text-red-700' : ''">{{ r.rank ?? t('metrics.search.notFound') }}</td>
            </tr>
          </tbody>
        </table>
        <p class="mt-2 text-xs text-stone-500">{{ t('metrics.search.note') }}</p>
      </section>

      <section class="card p-4" data-testid="metrics-feedback">
        <h2 class="font-medium text-stone-900">{{ t('metrics.feedback') }}</h2>
        <p v-if="!feedbackTotal" class="mt-1 text-sm text-stone-500">{{ t('feedback.none') }}</p>
        <p v-else class="mt-1 text-sm text-stone-700">
          {{ t('metrics.feedbackValue', { avg: feedbackAverage === null ? '—' : number.format(feedbackAverage), n: feedbackTotal.feedback }) }}
        </p>
        <NuxtLink to="/gop-y" class="mt-2 inline-block text-sm text-brand-700 hover:underline">{{ t('metrics.feedbackLink') }}</NuxtLink>
      </section>
    </div>
  </div>
</template>
