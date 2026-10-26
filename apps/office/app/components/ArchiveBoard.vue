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
import { ApiError } from '~/composables/useApi'
import { departmentRows, isEmptyArchive, typeRows, yearRows, type ArchiveStats } from '~/utils/archiveStats'

// Phần "Văn bản đã nộp lưu" của trang Điều hành (#304, nguyên lý (i)): dữ liệu đã chuyển sang kho lạnh vẫn dùng để
// phân tích được. svc-files cho DuckDB đếm trên các gói Parquet trong bucket lạnh — chỉ lãnh đạo đơn vị, chỉ đơn vị
// trong token, như các biểu đồ nóng (svc_files/archive_stats.py); tên loại văn bản, tên phòng đọc từ Hasura. Thành phần
// tự tải khi trang mở, trang Điều hành chỉ thêm một dòng. Kho trống thì báo rõ, không phải lỗi.

const NAMES = '{ office_document_types { code name } office_departments { id name } }'
// màu theo token của main.css như biểu đồ nóng: olive (--color-brand-700) cho văn bản đến, vàng đất
// (--color-amber-300) cho văn bản đi
const INCOMING = '#555b3f'
const OUTGOING = '#bfa46b'
const GRID = { left: 8, right: 16, top: 16, bottom: 32, outerBoundsMode: 'same', outerBoundsContain: 'axisLabel' }

const { t, locale } = useI18n()
const api = useApi()
const stats = ref<ArchiveStats | null>(null)
const typeNames = ref(new Map<string, string>())
const departmentNames = ref(new Map<string, string>())
const loading = ref(false)
const failure = ref('')

// Chỉ là tên để đọc cho dễ: không đọc được thì hiện mã loại, "Chưa rõ phòng"
async function loadNames() {
  try {
    const data = await api.gql<{
      office_document_types: { code: string; name: string }[]
      office_departments: { id: string; name: string }[]
    }>(NAMES)
    typeNames.value = new Map(data.office_document_types.map((r) => [r.code, r.name]))
    departmentNames.value = new Map(data.office_departments.map((r) => [r.id, r.name]))
  } catch {
    // giữ tên cũ (nếu có)
  }
}

async function load() {
  loading.value = true
  failure.value = ''
  try {
    const [result] = await Promise.all([api.archiveStats(), loadNames()])
    stats.value = result
  } catch (e) {
    failure.value = e instanceof ApiError && (e.code === 'storage_unavailable' || e.code === 'database_unavailable')
      ? t('archiveBoard.unavailable') : errorText(t, e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const years = computed(() => yearRows(stats.value?.by_year ?? []))
const types = computed(() => typeRows(stats.value?.by_type ?? [], typeNames.value))
const departments = computed(() => departmentRows(stats.value?.by_department ?? [], departmentNames.value))
const empty = computed(() => stats.value !== null && isEmptyArchive(stats.value))
const computedAt = computed(() => stats.value ? new Intl.DateTimeFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB', {
  dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh',
}).format(new Date(stats.value.computed_at)) : '')

function yearLabel(year: number | null) {
  return year === null ? t('archiveBoard.unknownYear') : String(year)
}

const yearChart = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { bottom: 0 },
  grid: GRID,
  xAxis: { type: 'category', data: years.value.map((r) => yearLabel(r.year)) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [
    { type: 'bar', stack: 'all', name: t('archiveBoard.incoming'), data: years.value.map((r) => r.incoming),
      itemStyle: { color: INCOMING } },
    { type: 'bar', stack: 'all', name: t('archiveBoard.outgoing'), data: years.value.map((r) => r.outgoing),
      itemStyle: { color: OUTGOING } },
  ],
}))
const unreadableCodes = computed(() => (stats.value?.unreadable ?? []).map((u) => u.code).join(', '))
const kpis = computed(() => [
  { id: 'case-files', label: 'archiveBoard.caseFiles', value: stats.value?.case_files ?? 0 },
  { id: 'incoming', label: 'archiveBoard.incomingDocuments', value: stats.value?.incoming ?? 0 },
  { id: 'outgoing', label: 'archiveBoard.outgoingDocuments', value: stats.value?.outgoing ?? 0 },
])
const yearSummary = computed(() => years.value.filter((r) => r.incoming || r.outgoing)
  .map((r) => t('archiveBoard.yearSummary', { year: yearLabel(r.year), incoming: r.incoming, outgoing: r.outgoing }))
  .join('; '))
</script>

<template>
  <section class="card p-4" data-testid="board-archive" aria-labelledby="board-archive-title">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 id="board-archive-title" class="font-medium text-stone-900">{{ t('archiveBoard.title') }}</h2>
        <p class="mt-1 text-xs text-stone-500" data-testid="archive-source">
          {{ stats && !empty
            ? t('archiveBoard.source', { n: stats.case_files, bucket: stats.bucket, at: computedAt })
            : t('archiveBoard.sourceShort') }}
        </p>
      </div>
      <button type="button" class="btn-secondary shrink-0" :disabled="loading" @click="load">
        {{ t('app.refresh') }}
      </button>
    </div>

    <p v-if="failure" class="mt-4 text-sm text-red-700" data-testid="archive-error">{{ failure }}</p>
    <p v-else-if="!stats" class="mt-4 text-sm text-stone-500">{{ t('app.loading') }}</p>
    <p v-else-if="empty" class="py-10 text-center text-sm text-stone-500" data-testid="archive-empty">
      {{ t('archiveBoard.empty') }}
    </p>
    <template v-else>
      <p v-if="stats.unreadable.length" class="mt-3 text-sm text-red-700" data-testid="archive-unreadable">
        {{ t('archiveBoard.unreadable', { n: stats.unreadable.length, codes: unreadableCodes }) }}
      </p>
      <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div v-for="k in kpis" :key="k.id">
          <div class="text-sm text-stone-500">{{ t(k.label) }}</div>
          <div class="mt-1 text-2xl font-semibold tabular-nums text-stone-900" :data-testid="`archive-${k.id}`">
            {{ k.value }}
          </div>
        </div>
      </div>

      <div class="mt-4 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div class="min-w-0" data-testid="archive-by-year">
          <h3 class="text-sm font-medium text-stone-900">{{ t('archiveBoard.byYear') }}</h3>
          <EChart :option="yearChart" :label="yearSummary || t('archiveBoard.empty')" />
          <div class="overflow-x-auto">
            <table class="mt-2 w-full text-sm">
              <thead class="text-left text-xs text-stone-500">
                <tr>
                  <th class="py-1 font-medium">{{ t('archiveBoard.year') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('archiveBoard.incoming') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('archiveBoard.outgoing') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-stone-100">
                <tr v-for="r in years.filter((y) => y.incoming || y.outgoing)" :key="r.year ?? 'none'">
                  <td class="py-1 text-stone-600">{{ yearLabel(r.year) }}</td>
                  <td class="py-1 text-right tabular-nums">{{ r.incoming }}</td>
                  <td class="py-1 text-right tabular-nums">{{ r.outgoing }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="min-w-0 space-y-6">
          <div class="overflow-x-auto" data-testid="archive-by-type">
            <h3 class="text-sm font-medium text-stone-900">{{ t('archiveBoard.byType') }}</h3>
            <table class="mt-2 w-full text-sm">
              <thead class="text-left text-xs text-stone-500">
                <tr>
                  <th class="py-1 font-medium">{{ t('archiveBoard.type') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('archiveBoard.incoming') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('archiveBoard.outgoing') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('archiveBoard.total') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-stone-100">
                <tr v-for="r in types" :key="r.type_code">
                  <td class="py-1 text-stone-600">{{ r.name }}</td>
                  <td class="py-1 text-right tabular-nums">{{ r.incoming }}</td>
                  <td class="py-1 text-right tabular-nums">{{ r.outgoing }}</td>
                  <td class="py-1 text-right font-medium tabular-nums">{{ r.total }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="overflow-x-auto" data-testid="archive-by-department">
            <h3 class="text-sm font-medium text-stone-900">{{ t('archiveBoard.byDepartment') }}</h3>
            <table class="mt-2 w-full text-sm">
              <thead class="text-left text-xs text-stone-500">
                <tr>
                  <th class="py-1 font-medium">{{ t('archiveBoard.department') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('archiveBoard.caseFilesShort') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('archiveBoard.documents') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-stone-100">
                <tr v-for="r in departments" :key="r.department_id ?? 'none'">
                  <td class="py-1 text-stone-600">{{ r.name ?? t('archiveBoard.noDepartment') }}</td>
                  <td class="py-1 text-right tabular-nums">{{ r.case_files }}</td>
                  <td class="py-1 text-right font-medium tabular-nums">{{ r.documents }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
