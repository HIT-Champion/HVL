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
import {
  FLAG_ORDER, LEVEL_ORDER, LEVEL_TONE, NEAR_BAND, PLAN, SENSOR_REFRESH_MS, doorOf, fmtTemp, knownFlags, placeSensors,
  sensorLevel, type OtSensor, type OtSensorMap, type RoomView,
} from '~/utils/otMap'

// Sơ đồ cảm biến kho (F3.10): mặt bằng kho lưu trữ, mỗi phòng tô màu theo số đo mới nhất của cảm biến đặt trong phòng
// so với ngưỡng, kèm ba cờ chất lượng dữ liệu OT do svc-workflow tính. Đọc qua Hasura Action otSensorMap bằng token
// người xem (APISIX và Hasura kiểm JWT; svc-workflow chỉ đọc tenant NGSI-LD của đơn vị trong phiên) — trình duyệt
// không gọi thẳng broker. Cùng các vai trò đọc được dự thảo "Báo cáo sự cố". Tự làm mới mỗi 30 giây khi tab đang mở.

const QUERY = `{ otSensorMap { status threshold stale_after_min range_min range_max checked_at
  sensors { id room name value observed_at flags } } }`
const ROLES = ['clerk', 'staff', 'manager', 'director']

const { t, te, locale } = useI18n()
const { gql } = useApi()
const claims = useAuth().claims
const allowed = computed(() => ROLES.includes(claims.value?.role ?? ''))

const data = ref<OtSensorMap | null>(null)
const loading = ref(false)
const failure = ref('')
let loadedAt = 0
let timer: ReturnType<typeof setInterval> | undefined

const ready = computed(() => data.value?.status === 'ready')
const placed = computed(() => data.value ? placeSensors(data.value) : { rooms: [], outside: [] })
const sensors = computed(() => data.value?.sensors ?? [])
const nearFrom = computed(() => fmtTemp((data.value?.threshold ?? 0) - NEAR_BAND, locale.value))
const threshold = computed(() => fmtTemp(data.value?.threshold ?? null, locale.value))

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    data.value = (await gql<{ otSensorMap: OtSensorMap }>(QUERY)).otSensorMap
    failure.value = ''
    loadedAt = Date.now()
  } catch (e) {
    failure.value = errorText(t, e)
  } finally {
    loading.value = false
  }
}

function onVisible() {
  if (!document.hidden && Date.now() - loadedAt >= SENSOR_REFRESH_MS) load()
}

onMounted(() => {
  if (!allowed.value) return
  load()
  timer = setInterval(() => { if (!document.hidden) load() }, SENSOR_REFRESH_MS)
  document.addEventListener('visibilitychange', onVisible)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisible)
})

// Mã phòng do thiết bị khai: có nhãn thì dùng nhãn, không thì hiện nguyên mã
function roomLabel(code: string | null) {
  if (!code) return t('sensors.outside')
  return te(`sensors.room.${code}`) ? t(`sensors.room.${code}`) : code
}
const levelHint = (level: string) => t(`sensors.levelHint.${level}`, {
  threshold: threshold.value, from: nearFrom.value,
})
const flagHint = (flag: string) => t(`sensors.flagHint.${flag}`, {
  n: data.value?.stale_after_min ?? 0, min: fmtTemp(data.value?.range_min ?? null, locale.value),
  max: fmtTemp(data.value?.range_max ?? null, locale.value),
})
const shownValue = (r: RoomView) => r.sensors.length === 1 ? fmtTemp(r.sensors[0]!.value, locale.value)
  : r.sensors.length ? t('sensors.count', { n: r.sensors.length }) : ''
function roomTitle(r: RoomView) {
  const parts = [roomLabel(r.room.code), t(`sensors.level.${r.level}`)]
  for (const s of r.sensors) parts.push(`${s.name}: ${fmtTemp(s.value, locale.value)}`)
  for (const f of r.flags) parts.push(t(`sensors.flag.${f}`))
  return parts.join(' · ')
}
const sensorFlags = (s: OtSensor) => knownFlags(s.flags)
</script>

<template>
  <div>
    <PageHeader :title="t('sensors.title')" :subtitle="t('sensors.subtitle')">
      <button v-if="allowed" class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>
    <p v-if="!allowed" class="card p-12 text-center text-stone-500">{{ t('sensors.forbidden') }}</p>
    <p v-else-if="failure" class="card mb-4 p-4 text-sm text-red-700" role="alert">{{ failure }}</p>
    <p v-if="allowed && !data && !failure" class="text-sm text-stone-500">{{ t('app.loading') }}</p>

    <section v-if="allowed && data && !ready" class="card border border-amber-200 bg-amber-50 p-5 text-amber-900"
             role="status" data-testid="sensors-off" :data-status="data.status">
      <h2 class="text-lg font-semibold">{{ t('sensors.off') }}</h2>
      <p class="mt-1 text-sm">{{ t(`sensors.offHint.${data.status}`) }}</p>
    </section>

    <div v-if="allowed && data && ready" class="space-y-4">
      <div class="grid gap-4 lg:grid-cols-3">
        <section class="card p-4 lg:col-span-2" data-testid="sensor-plan">
          <div class="mb-2 flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <h2 class="font-medium text-stone-900">{{ t('sensors.plan') }}</h2>
            <span class="text-xs text-stone-500">
              {{ t('sensors.checkedAt', { time: fmtDateTime(data.checked_at) }) }}
            </span>
          </div>
          <svg :viewBox="`0 0 ${PLAN.view.width} ${PLAN.view.height}`" class="h-auto w-full" role="img"
               :aria-label="t('sensors.planLabel')">
            <defs>
              <pattern id="sensor-hatch" width="8" height="8" patternUnits="userSpaceOnUse"
                       patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="8" class="stroke-stone-400" stroke-width="2" />
              </pattern>
            </defs>
            <rect :x="PLAN.outline.x" :y="PLAN.outline.y" :width="PLAN.outline.w" :height="PLAN.outline.h" rx="6"
                  class="fill-stone-50 stroke-stone-500" stroke-width="3" />
            <rect :x="PLAN.corridor.x" :y="PLAN.corridor.y" :width="PLAN.corridor.w" :height="PLAN.corridor.h"
                  class="fill-stone-100" />
            <text :x="PLAN.corridor.x + PLAN.corridor.w / 2" :y="PLAN.corridor.y + PLAN.corridor.h / 2 + 5"
                  text-anchor="middle" class="fill-stone-400 text-sm">{{ t('sensors.corridor') }}</text>
            <g v-for="r in placed.rooms" :key="r.room.code" :data-testid="`sensor-room-${r.room.code}`"
               :data-level="r.level" :data-flags="r.flags.join(' ')">
              <title>{{ roomTitle(r) }}</title>
              <rect :x="r.room.x" :y="r.room.y" :width="r.room.w" :height="r.room.h" rx="3"
                    :class="[LEVEL_TONE[r.level].fill, LEVEL_TONE[r.level].stroke]" stroke-width="2" />
              <rect v-if="r.level === 'unknown'" :x="r.room.x" :y="r.room.y" :width="r.room.w" :height="r.room.h"
                    rx="3" fill="url(#sensor-hatch)" opacity="0.35" />
              <line v-bind="doorOf(r.room)" class="stroke-stone-50" stroke-width="5" />
              <text :x="r.room.x + 12" :y="r.room.y + 24" class="fill-stone-700 text-sm font-medium">
                {{ roomLabel(r.room.code) }}
              </text>
              <text :x="r.room.x + r.room.w / 2" :y="r.room.y + r.room.h / 2 + 10" text-anchor="middle"
                    class="fill-stone-900 text-3xl font-semibold">{{ shownValue(r) }}</text>
              <text v-if="r.flags.length" :x="r.room.x + 12" :y="r.room.y + r.room.h - 14"
                    class="fill-red-700 text-xs font-medium">
                ⚠ {{ r.flags.map((f) => t(`sensors.flag.${f}`)).join(', ') }}
              </text>
            </g>
          </svg>
        </section>

        <aside class="card space-y-4 p-4 text-sm" data-testid="sensor-legend">
          <div>
            <h2 class="font-medium text-stone-900">{{ t('sensors.legend') }}</h2>
            <p class="mt-1 text-xs text-stone-500">{{ t('sensors.threshold', { threshold }) }}</p>
            <ul class="mt-2 space-y-1.5">
              <li v-for="level in LEVEL_ORDER" :key="level" class="flex items-start gap-2">
                <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 16 16" aria-hidden="true">
                  <rect x="1" y="1" width="14" height="14" rx="2" stroke-width="2"
                        :class="[LEVEL_TONE[level].fill, LEVEL_TONE[level].stroke]" />
                </svg>
                <span><span class="font-medium text-stone-800">{{ t(`sensors.level.${level}`) }}</span>
                  <span class="text-stone-500"> — {{ levelHint(level) }}</span></span>
              </li>
            </ul>
          </div>
          <div>
            <h2 class="font-medium text-stone-900">{{ t('sensors.flags') }}</h2>
            <ul class="mt-2 space-y-1.5">
              <li v-for="flag in FLAG_ORDER" :key="flag" :data-testid="`sensor-flag-${flag}`">
                <span class="font-medium text-red-700">⚠ {{ t(`sensors.flag.${flag}`) }}</span>
                <span class="text-stone-500"> — {{ flagHint(flag) }}</span>
              </li>
            </ul>
            <p class="mt-2 text-xs text-stone-500">{{ t('sensors.flagsNote') }}</p>
          </div>
        </aside>
      </div>

      <section class="card overflow-x-auto p-4" data-testid="sensor-table">
        <h2 class="font-medium text-stone-900">{{ t('sensors.table') }}</h2>
        <p v-if="!sensors.length" class="mt-2 text-sm text-stone-500">{{ t('sensors.none') }}</p>
        <table v-else class="mt-2 w-full min-w-[40rem] text-sm">
          <thead class="text-left text-xs text-stone-500">
            <tr>
              <th class="py-1 pr-3 font-medium">{{ t('sensors.colRoom') }}</th>
              <th class="py-1 pr-3 font-medium">{{ t('sensors.colSensor') }}</th>
              <th class="py-1 pr-3 font-medium">{{ t('sensors.colValue') }}</th>
              <th class="py-1 pr-3 font-medium">{{ t('sensors.colAt') }}</th>
              <th class="py-1 font-medium">{{ t('sensors.colFlags') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100">
            <tr v-for="s in sensors" :key="s.id" :data-testid="`sensor-row-${s.id.split(':').pop()}`">
              <td class="py-1.5 pr-3">{{ roomLabel(s.room) }}</td>
              <td class="py-1.5 pr-3">
                <div class="text-stone-900">{{ s.name }}</div>
                <div class="font-mono text-xs text-stone-500">{{ s.id.split(':').pop() }}</div>
              </td>
              <td class="py-1.5 pr-3">
                <span class="chip" :class="LEVEL_TONE[sensorLevel(s, data.threshold)].chip">
                  {{ fmtTemp(s.value, locale) }}
                </span>
              </td>
              <td class="py-1.5 pr-3 text-stone-600">{{ fmtDateTime(s.observed_at) }}</td>
              <td class="py-1.5">
                <span v-for="f in sensorFlags(s)" :key="f" class="chip mr-1 bg-red-50 text-red-700"
                      :title="flagHint(f)">{{ t(`sensors.flag.${f}`) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="placed.outside.length" class="mt-2 text-xs text-stone-500" data-testid="sensor-outside">
          {{ t('sensors.outsideHint', { n: placed.outside.length }) }}
        </p>
      </section>

      <p class="text-xs text-stone-500">{{ t('sensors.note') }}</p>
    </div>
  </div>
</template>
