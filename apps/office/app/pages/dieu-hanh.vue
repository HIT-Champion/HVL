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
import type { ReportCheck } from '~/utils/quality'

// Dashboard điều hành (F3.11), cho lãnh đạo đơn vị: văn bản đến theo trạng thái, quá hạn theo phòng, thời gian
// xử lý, văn bản khẩn, văn bản đi theo tháng. Số liệu lấy từ bốn khung nhìn chỉ có số đếm (migration
// 1792281601200) qua Hasura bằng token của người xem: Hasura lọc theo thuê ước trong token, vai trò khác bị từ
// chối. Văn bản hạn chế không vào phép chia nào, chỉ có con số tổng (lý do ở migration).
// Nút "Nguồn số liệu" của từng biểu đồ mở trang Phả hệ (F3.9): biểu đồ nào dùng khung nhìn nào khai ở
// app/utils/lineage.ts, tests/lineage.test.ts đối chiếu với QUERY và các computed dưới đây.
// Cạnh nút đó là cờ kiểm chất lượng số liệu (Đạt / Cảnh báo / Trượt): bộ luật tính trong CSDL lúc truy vấn
// (office.report_checks, migration 1792281603300), hỏi bằng truy vấn riêng CHECKS ngay sau khi có số liệu — luật đọc
// lại đúng các khung nhìn đó, chạy song song thì tranh CPU của CSDL với chính truy vấn biểu đồ đang chờ.
// Lỗi thì cờ ghi "chưa kiểm được", số liệu vẫn hiện.

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
const CHECKS = '{ office_report_checks { rule report status expected actual issues detail } }'
const IN_STATUSES = ['received', 'registered', 'in_progress', 'done', 'archived', 'cancelled'] as const
const OPEN = new Set(['received', 'registered', 'in_progress'])
const MONTHS = 12
// màu biểu đồ theo giao diện "Lịch hạn": lục bảo của hành động chính, đỏ trầm cho quá hạn
const BRAND = '#0b6b53'
const LATE = '#9f2019'
// giống grid.containLabel của ECharts 5: nhãn trục nằm trong khung
const GRID = { left: 8, right: 16, top: 16, bottom: 8, outerBoundsMode: 'same', outerBoundsContain: 'axisLabel' }

const { t, locale } = useI18n()
const { gql } = useApi()
const claims = useAuth().claims

const counts = ref<Count[]>([])
const departments = ref<Department[]>([])
const processing = ref<Processing[]>([])
const outgoing = ref<Outgoing[]>([])
const checks = ref<ReportCheck[] | null>(null)
const checksFailed = ref(false)
const loaded = ref(false)
const loading = ref(false)
const failure = ref('')
const allowed = computed(() => claims.value?.role === 'director')

async function loadChecks() {
  try {
    checks.value = (await gql<{ office_report_checks: ReportCheck[] }>(CHECKS)).office_report_checks
    checksFailed.value = false
  } catch {
    checksFailed.value = true
  }
}

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
  if (loaded.value) await loadChecks()
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
// Thanh ngang: tên trạng thái đọc trọn trên trục dọc, trạng thái đầu quy trình ở trên cùng
const statusChart = computed(() => ({
  tooltip,
  grid: { ...GRID, right: 32 },
  xAxis: { type: 'value', minInterval: 1 },
  yAxis: {
    type: 'category',
    inverse: true,
    data: byStatus.value.map((r) => t(`status.${r.status}`)),
    axisLabel: { interval: 0, width: 105, fontSize: 13, overflow: 'break' },
  },
  series: [{
    type: 'bar',
    name: t('board.count'),
    data: byStatus.value.map((r) => r.documents),
    itemStyle: { color: BRAND },
    label: { show: true, position: 'right' },
  }],
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
  xAxis: { type: 'category', data: months.value.map(monthLabel), axisLabel: { showMaxLabel: true, hideOverlap: true } },
  yAxis: { type: 'value' },
  series: [{
    type: 'bar',
    name: inHours.value ? t('board.avgHours') : t('board.avgDays'),
    // tháng không có văn bản xong để trống (null); tháng xử lý rất nhanh vẫn có cột thấp nhất 2px, không thành 0
    data: processingByMonth.value.map((r) => (r.documents
      ? Math.round((r.total_hours / r.documents / (inHours.value ? 1 : 24)) * 100) / 100 : null)),
    barMinHeight: 2,
    itemStyle: { color: BRAND },
  }],
}))
const outgoingChart = computed(() => ({
  tooltip,
  grid: GRID,
  xAxis: { type: 'category', data: months.value.map(monthLabel), axisLabel: { showMaxLabel: true, hideOverlap: true } },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', name: t('board.issued'), data: outgoingByMonth.value.map((r) => r.documents), itemStyle: { color: BRAND } }],
}))
</script>

<template>
  <div>
    <PageHeader :title="t('board.title')" :subtitle="t('board.subtitle')">
      <button v-if="allowed" class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>
    <p v-if="!allowed" class="moc-empty">{{ t('board.forbidden') }}</p>
    <p v-else-if="failure" class="moc-state mb-6">{{ failure }}</p>
    <p v-if="allowed && !loaded && !failure" class="moc-loading">{{ t('app.loading') }}</p>
    <div v-if="allowed && loaded" class="moc-stack">
      <!-- bốn con số chính đứng thành một hàng, không thành thẻ; các bảng bên dưới là số liệu chi tiết -->
      <div>
        <div class="moc-board-kpis" data-testid="board-kpis">
          <div class="card p-4">
            <div class="text-sm text-stone-600">{{ t('board.open') }}</div>
            <div class="mt-1 text-stone-900" data-testid="kpi-open">{{ kpis.open }}</div>
            <div class="mt-1 text-xs text-stone-500">{{ t('board.openHint') }}</div>
          </div>
          <div class="card p-4">
            <div class="text-sm text-stone-600">{{ t('board.overdue') }}</div>
            <div class="mt-1" :class="kpis.overdue ? 'text-red-700' : 'text-stone-900'" data-testid="kpi-overdue">
              {{ kpis.overdue }}
            </div>
            <div class="mt-1 text-xs text-stone-500">{{ t('board.overdueHint') }}</div>
          </div>
          <div class="card p-4">
            <div class="text-sm text-stone-600">{{ t('board.urgent') }}</div>
            <div class="mt-1 text-stone-900" data-testid="kpi-urgent">{{ kpis.urgent }}</div>
            <div class="mt-1 text-xs text-stone-500">{{ t('board.urgentHint') }}</div>
          </div>
          <div class="card p-4">
            <div class="text-sm text-stone-600">{{ t('board.avgTime') }}</div>
            <div class="mt-1 text-stone-900" data-testid="kpi-time">
              {{ kpis.hours === null ? '—' : duration(kpis.hours) }}
            </div>
            <div class="mt-1 text-xs text-stone-500">
              {{ kpis.hours === null ? t('board.noneDone') : t('board.avgHint', { done: kpis.done }) }}
              <template v-if="kpis.onTimePct !== null"> · {{ t('board.onTimePct', { pct: kpis.onTimePct }) }}</template>
            </div>
          </div>
        </div>
        <div class="mt-3 flex flex-wrap items-start justify-between gap-2">
          <p v-if="restricted" class="text-[13px] text-stone-500" data-testid="board-restricted">
            {{ t('board.restricted', { n: restricted }) }}
          </p>
          <div class="ml-auto flex items-center gap-2">
            <ChartChecks chart="kpis" :checks="checks" :failed="checksFailed" />
            <SourceLink chart="kpis" />
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section class="moc-block" data-testid="board-status">
          <div class="moc-block-head">
            <h2 class="moc-block-title">{{ t('board.byStatus') }}</h2>
            <div class="moc-block-tools">
              <ChartChecks chart="status" :checks="checks" :failed="checksFailed" />
              <SourceLink chart="status" />
            </div>
          </div>
          <EChart
            :option="statusChart"
            :label="byStatus.map((r) => `${t(`status.${r.status}`)}: ${r.documents}`).join(', ')"
          />
          <table class="moc-table mt-3">
            <thead>
              <tr><th>{{ t('board.status') }}</th><th class="text-right">{{ t('board.count') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in byStatus" :key="r.status">
                <td class="text-stone-700">{{ t(`status.${r.status}`) }}</td>
                <td class="text-right font-medium">{{ r.documents }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="moc-block" data-testid="board-departments">
          <div class="moc-block-head">
            <h2 class="moc-block-title">{{ t('board.byDepartment') }}</h2>
            <div class="moc-block-tools">
              <ChartChecks chart="departments" :checks="checks" :failed="checksFailed" />
              <SourceLink chart="departments" />
            </div>
          </div>
          <p v-if="!departments.length" class="moc-empty">{{ t('board.empty') }}</p>
          <template v-else>
            <EChart
              :option="departmentChart" :height="departmentHeight"
              :label="departments.map((r) => `${departmentName(r)}: ${r.in_progress}, ${t('board.late')} ${r.overdue}`)
                .join('; ')"
            />
            <table class="moc-table mt-3">
              <thead>
                <tr>
                  <th>{{ t('board.department') }}</th>
                  <th class="text-right">{{ t('board.inProgress') }}</th>
                  <th class="text-right">{{ t('board.late') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in departments" :key="r.department_id ?? 'none'">
                  <td class="text-stone-700 wrap-anywhere">{{ departmentName(r) }}</td>
                  <td class="text-right">{{ r.in_progress }}</td>
                  <td class="text-right font-medium" :class="r.overdue ? 'text-red-700' : ''">{{ r.overdue }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </section>

        <section class="moc-block" data-testid="board-processing">
          <div class="moc-block-head">
            <h2 class="moc-block-title">
              {{ t('board.processing') }}
              <span class="text-sm font-normal text-stone-500"
                >({{ inHours ? t('board.unitHours') : t('board.unitDays') }})</span>
            </h2>
            <div class="moc-block-tools">
              <ChartChecks chart="processing" :checks="checks" :failed="checksFailed" />
              <SourceLink chart="processing" />
            </div>
          </div>
          <EChart
            :option="processingChart"
            :label="processingByMonth.filter((r) => r.documents)
              .map((r) => `${monthLabel(r.month)}: ${duration(r.total_hours / r.documents)}`).join(', ')
              || t('board.noneDone')"
          />
          <table class="moc-table mt-3">
            <thead>
              <tr>
                <th>{{ t('board.month') }}</th>
                <th class="text-right">{{ t('board.finished') }}</th>
                <th class="text-right">{{ t('board.onTime') }}</th>
                <th class="text-right">{{ t('board.average') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in processingByMonth.filter((p) => p.documents)" :key="r.month">
                <td class="text-stone-700">{{ monthLabel(r.month) }}</td>
                <td class="text-right">{{ r.documents }}</td>
                <td class="text-right">{{ r.with_due ? `${r.on_time}/${r.with_due}` : '—' }}</td>
                <td class="text-right font-medium">{{ duration(r.total_hours / r.documents) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="moc-block" data-testid="board-outgoing">
          <div class="moc-block-head">
            <h2 class="moc-block-title">{{ t('board.outgoing') }}</h2>
            <div class="moc-block-tools">
              <ChartChecks chart="outgoing" :checks="checks" :failed="checksFailed" />
              <SourceLink chart="outgoing" />
            </div>
          </div>
          <EChart
            :option="outgoingChart"
            :label="outgoingByMonth.filter((r) => r.documents).map((r) => `${monthLabel(r.month)}: ${r.documents}`)
              .join(', ') || t('board.empty')"
          />
          <table class="moc-table mt-3">
            <thead>
              <tr><th>{{ t('board.month') }}</th><th class="text-right">{{ t('board.issued') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in outgoingByMonth.filter((o) => o.documents)" :key="r.month">
                <td class="text-stone-700">{{ monthLabel(r.month) }}</td>
                <td class="text-right font-medium">{{ r.documents }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>
  </div>
</template>
