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

// Dashboard điều hành (F3.11), cho lãnh đạo đơn vị: văn bản đến theo trạng thái, quá hạn theo phòng, thời gian
// xử lý, văn bản khẩn, văn bản đi theo tháng. Số liệu lấy từ bốn khung nhìn chỉ có số đếm (migration
// 1792281601200) qua Hasura bằng token của người xem: Hasura lọc theo thuê ước trong token, vai trò khác bị từ
// chối. Văn bản hạn chế không vào phép chia nào, chỉ có con số tổng (lý do ở migration).

interface Count {
  direction: string
  restricted: boolean
  status: string | null
  urgency: string | null
  overdue: boolean | null
  documents: number
}
interface Department { department_id: string | null; code: string | null; name: string | null; in_progress: number; overdue: number }
interface Processing { month: string; documents: number; total_hours: number; with_due: number; on_time: number }
interface Outgoing { month: string; documents: number }

const QUERY = `{
  office_v_document_counts { direction restricted status urgency overdue documents }
  office_v_overdue_by_department(order_by: [{overdue: desc}, {in_progress: desc}, {code: asc}]) {
    department_id code name in_progress overdue
  }
  office_v_processing_time(order_by: {month: asc}) { month documents total_hours with_due on_time }
  office_v_outgoing_by_month(order_by: {month: asc}) { month documents }
}`
const IN_STATUSES = ['received', 'registered', 'in_progress', 'done', 'archived', 'cancelled'] as const
const OPEN = new Set(['received', 'registered', 'in_progress'])
const MONTHS = 12
const BRAND = '#0f766e'
const LATE = '#dc2626'
// giống grid.containLabel của ECharts 5: nhãn trục nằm trong khung
const GRID = { left: 8, right: 16, top: 16, bottom: 8, outerBoundsMode: 'same', outerBoundsContain: 'axisLabel' }

const { t, locale } = useI18n()
const { gql } = useApi()
const claims = useAuth().claims

const counts = ref<Count[]>([])
const departments = ref<Department[]>([])
const processing = ref<Processing[]>([])
const outgoing = ref<Outgoing[]>([])
const loaded = ref(false)
const loading = ref(false)
const failure = ref('')
const allowed = computed(() => claims.value?.role === 'director')

// Làm mới giữ số cũ trên trang tới khi có số mới, không vẽ lại từ đầu
async function load() {
  loading.value = true
  failure.value = ''
  try {
    const data = await gql<{
      office_v_document_counts: Count[]
      office_v_overdue_by_department: Department[]
      office_v_processing_time: Processing[]
      office_v_outgoing_by_month: Outgoing[]
    }>(QUERY)
    counts.value = data.office_v_document_counts
    departments.value = data.office_v_overdue_by_department
    processing.value = data.office_v_processing_time
    outgoing.value = data.office_v_outgoing_by_month
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

function sum<T>(rows: T[], pick: (row: T) => number) {
  return rows.reduce((n, r) => n + pick(r), 0)
}
const number = computed(() => new Intl.NumberFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB', { maximumFractionDigits: 1 }))
// Dưới một ngày thì tính giờ: văn bản xử lý trong ngày không hiện thành "0 ngày"
function duration(hours: number) {
  if (hours < 1) return t('board.underHour')
  return hours < 24 ? t('board.hoursValue', { n: number.value.format(hours) })
    : t('board.daysValue', { n: number.value.format(hours / 24) })
}

// 12 tháng gần nhất theo giờ Việt Nam, tháng không có số liệu vẫn có cột
const months = computed(() => {
  const [y, m] = today().split('-').map(Number) as [number, number]
  return Array.from({ length: MONTHS }, (_, i) => {
    const d = new Date(y, m - 1 - (MONTHS - 1 - i), 1)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
  })
})
function monthLabel(iso: string) {
  const [y, m] = iso.split('-')
  return `${Number(m)}/${y}`
}

const incoming = computed(() => counts.value.filter((r) => r.direction === 'in' && !r.restricted))
const restricted = computed(() => sum(counts.value.filter((r) => r.restricted), (r) => r.documents))
const processingByMonth = computed(() => months.value.map((month) => processing.value.find((r) => r.month === month)
  ?? { month, documents: 0, total_hours: 0, with_due: 0, on_time: 0 }))
const kpis = computed(() => {
  const open = incoming.value.filter((r) => OPEN.has(r.status ?? ''))
  const recent = processingByMonth.value
  const done = sum(recent, (r) => r.documents)
  const withDue = sum(recent, (r) => r.with_due)
  return {
    open: sum(open, (r) => r.documents),
    overdue: sum(incoming.value.filter((r) => r.overdue), (r) => r.documents),
    urgent: sum(open.filter((r) => r.urgency !== 'normal'), (r) => r.documents),
    done,
    hours: done ? sum(recent, (r) => r.total_hours) / done : null,
    onTimePct: withDue ? Math.round((sum(recent, (r) => r.on_time) / withDue) * 100) : null,
  }
})

const byStatus = computed(() => IN_STATUSES.map((s) => ({
  status: s,
  documents: sum(incoming.value.filter((r) => r.status === s), (r) => r.documents),
})))
const outgoingByMonth = computed(() => months.value.map((month) => ({
  month,
  documents: outgoing.value.find((r) => r.month === month)?.documents ?? 0,
})))
function departmentName(r: Department) {
  return r.name ?? t('board.noDepartment')
}
// Biểu đồ theo phòng cao theo số phòng, để không phòng nào mất nhãn
const departmentHeight = computed(() => Math.max(256, departments.value.length * 36 + 72))
// Thời gian xử lý vẽ theo giờ nếu mọi tháng đều xong trong ngày, không thì theo ngày
const inHours = computed(() => processingByMonth.value.every((r) => !r.documents || r.total_hours / r.documents < 24))

const tooltip = { trigger: 'axis', axisPointer: { type: 'shadow' } }
const statusChart = computed(() => ({
  tooltip,
  grid: GRID,
  xAxis: { type: 'category', data: byStatus.value.map((r) => t(`status.${r.status}`)), axisLabel: { interval: 0, width: 72, overflow: 'break' } },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', name: t('board.count'), data: byStatus.value.map((r) => r.documents), itemStyle: { color: BRAND }, label: { show: true, position: 'top' } }],
}))
const departmentChart = computed(() => {
  const rows = [...departments.value].reverse() // nhiều quá hạn nhất ở trên cùng
  return {
    tooltip,
    legend: { bottom: 0 },
    grid: { ...GRID, bottom: 32 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: rows.map(departmentName) },
    series: [
      { type: 'bar', stack: 'all', name: t('board.inTime'), data: rows.map((r) => r.in_progress - r.overdue), itemStyle: { color: BRAND } },
      { type: 'bar', stack: 'all', name: t('board.late'), data: rows.map((r) => r.overdue), itemStyle: { color: LATE } },
    ],
  }
})
const processingChart = computed(() => ({
  tooltip,
  grid: GRID,
  xAxis: { type: 'category', data: months.value.map(monthLabel) },
  yAxis: { type: 'value' },
  series: [{
    type: 'bar',
    name: inHours.value ? t('board.avgHours') : t('board.avgDays'),
    data: processingByMonth.value.map((r) => (r.documents ? Math.round((r.total_hours / r.documents / (inHours.value ? 1 : 24)) * 100) / 100 : 0)),
    itemStyle: { color: BRAND },
  }],
}))
const outgoingChart = computed(() => ({
  tooltip,
  grid: GRID,
  xAxis: { type: 'category', data: months.value.map(monthLabel) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', name: t('board.issued'), data: outgoingByMonth.value.map((r) => r.documents), itemStyle: { color: BRAND } }],
}))
</script>

<template>
  <div>
    <PageHeader :title="t('board.title')" :subtitle="t('board.subtitle')">
      <button v-if="allowed" class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>
    <p v-if="!allowed" class="card p-12 text-center text-stone-500">{{ t('board.forbidden') }}</p>
    <p v-else-if="failure" class="card mb-4 p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-if="allowed && !loaded && !failure" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <div v-if="allowed && loaded" class="space-y-4">
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="board-kpis">
        <div class="card p-4">
          <div class="text-sm text-stone-500">{{ t('board.open') }}</div>
          <div class="mt-1 text-3xl font-semibold text-stone-900" data-testid="kpi-open">{{ kpis.open }}</div>
          <div class="mt-1 text-xs text-stone-500">{{ t('board.openHint') }}</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-stone-500">{{ t('board.overdue') }}</div>
          <div class="mt-1 text-3xl font-semibold" :class="kpis.overdue ? 'text-red-700' : 'text-stone-900'" data-testid="kpi-overdue">{{ kpis.overdue }}</div>
          <div class="mt-1 text-xs text-stone-500">{{ t('board.overdueHint') }}</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-stone-500">{{ t('board.urgent') }}</div>
          <div class="mt-1 text-3xl font-semibold text-stone-900" data-testid="kpi-urgent">{{ kpis.urgent }}</div>
          <div class="mt-1 text-xs text-stone-500">{{ t('board.urgentHint') }}</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-stone-500">{{ t('board.avgTime') }}</div>
          <div class="mt-1 text-3xl font-semibold text-stone-900" data-testid="kpi-time">{{ kpis.hours === null ? '—' : duration(kpis.hours) }}</div>
          <div class="mt-1 text-xs text-stone-500">
            {{ kpis.hours === null ? t('board.noneDone') : t('board.avgHint', { done: kpis.done }) }}
            <template v-if="kpis.onTimePct !== null"> · {{ t('board.onTimePct', { pct: kpis.onTimePct }) }}</template>
          </div>
        </div>
      </div>
      <p v-if="restricted" class="text-xs text-stone-500" data-testid="board-restricted">{{ t('board.restricted', { n: restricted }) }}</p>

      <div class="grid gap-4 xl:grid-cols-2">
        <section class="card p-4" data-testid="board-status">
          <h2 class="font-medium text-stone-900">{{ t('board.byStatus') }}</h2>
          <EChart :option="statusChart" :label="byStatus.map((r) => `${t(`status.${r.status}`)}: ${r.documents}`).join(', ')" />
          <table class="mt-2 w-full text-sm">
            <thead class="text-left text-xs text-stone-500">
              <tr><th class="py-1 font-medium">{{ t('board.status') }}</th><th class="py-1 text-right font-medium">{{ t('board.count') }}</th></tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="r in byStatus" :key="r.status">
                <td class="py-1 text-stone-600">{{ t(`status.${r.status}`) }}</td>
                <td class="py-1 text-right font-medium tabular-nums">{{ r.documents }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="card p-4" data-testid="board-departments">
          <h2 class="font-medium text-stone-900">{{ t('board.byDepartment') }}</h2>
          <p v-if="!departments.length" class="py-12 text-center text-sm text-stone-500">{{ t('board.empty') }}</p>
          <template v-else>
            <EChart :option="departmentChart" :height="departmentHeight" :label="departments.map((r) => `${departmentName(r)}: ${r.in_progress}, ${t('board.late')} ${r.overdue}`).join('; ')" />
            <table class="mt-2 w-full text-sm">
              <thead class="text-left text-xs text-stone-500">
                <tr><th class="py-1 font-medium">{{ t('board.department') }}</th><th class="py-1 text-right font-medium">{{ t('board.inProgress') }}</th><th class="py-1 text-right font-medium">{{ t('board.late') }}</th></tr>
              </thead>
              <tbody class="divide-y divide-stone-100">
                <tr v-for="r in departments" :key="r.department_id ?? 'none'">
                  <td class="py-1 text-stone-600">{{ departmentName(r) }}</td>
                  <td class="py-1 text-right tabular-nums">{{ r.in_progress }}</td>
                  <td class="py-1 text-right font-medium tabular-nums" :class="r.overdue ? 'text-red-700' : ''">{{ r.overdue }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </section>

        <section class="card p-4" data-testid="board-processing">
          <h2 class="font-medium text-stone-900">{{ t('board.processing') }} <span class="text-sm font-normal text-stone-500">({{ inHours ? t('board.unitHours') : t('board.unitDays') }})</span></h2>
          <EChart :option="processingChart" :label="processingByMonth.filter((r) => r.documents).map((r) => `${monthLabel(r.month)}: ${duration(r.total_hours / r.documents)}`).join(', ') || t('board.noneDone')" />
          <table class="mt-2 w-full text-sm">
            <thead class="text-left text-xs text-stone-500">
              <tr><th class="py-1 font-medium">{{ t('board.month') }}</th><th class="py-1 text-right font-medium">{{ t('board.finished') }}</th><th class="py-1 text-right font-medium">{{ t('board.onTime') }}</th><th class="py-1 text-right font-medium">{{ t('board.average') }}</th></tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="r in processingByMonth.filter((p) => p.documents)" :key="r.month">
                <td class="py-1 text-stone-600">{{ monthLabel(r.month) }}</td>
                <td class="py-1 text-right tabular-nums">{{ r.documents }}</td>
                <td class="py-1 text-right tabular-nums">{{ r.with_due ? `${r.on_time}/${r.with_due}` : '—' }}</td>
                <td class="py-1 text-right font-medium tabular-nums">{{ duration(r.total_hours / r.documents) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="card p-4" data-testid="board-outgoing">
          <h2 class="font-medium text-stone-900">{{ t('board.outgoing') }}</h2>
          <EChart :option="outgoingChart" :label="outgoingByMonth.filter((r) => r.documents).map((r) => `${monthLabel(r.month)}: ${r.documents}`).join(', ') || t('board.empty')" />
          <table class="mt-2 w-full text-sm">
            <thead class="text-left text-xs text-stone-500">
              <tr><th class="py-1 font-medium">{{ t('board.month') }}</th><th class="py-1 text-right font-medium">{{ t('board.issued') }}</th></tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="r in outgoingByMonth.filter((o) => o.documents)" :key="r.month">
                <td class="py-1 text-stone-600">{{ monthLabel(r.month) }}</td>
                <td class="py-1 text-right font-medium tabular-nums">{{ r.documents }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>
  </div>
</template>
