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
import { OVERALL_TONE, STATE_TONE, STATUS_REFRESH_MS, fmtClock, fmtUptime, groupByLayer } from '~/utils/systemStatus'
import type { StatusComponent, StatusGroup, SystemStatus } from '~/utils/systemStatus'

// Trạng thái hệ thống, công khai: tình trạng vận hành các thành phần của Signet theo tầng người dùng → lõi → quy trình
// → dữ liệu → trí tuệ nhân tạo, phiên bản, thời gian chạy liên tục, lượt sao lưu gần nhất, trợ lý AI bật hay tắt.
// GET /api/status không cần token, chỉ trả chữ cố định đã làm sạch (svc-files, status.py). Tự làm mới mỗi 30 giây khi
// tab đang mở; tab ẩn thì thôi, hiện lại thì tải ngay nếu đã quá hạn.

definePageMeta({ layout: 'public', publicTitle: 'health.title', wide: true })

const { t, te } = useI18n()

const data = ref<SystemStatus | null>(null)
const loading = ref(false)
const failure = ref('')
let loadedAt = 0
let timer: ReturnType<typeof setInterval> | undefined

const groups = computed(() => (data.value ? groupByLayer(data.value) : []))
const uptime = computed(() => data.value ? fmtUptime(data.value.uptime_s, {
  day: t('health.units.day'), hour: t('health.units.hour'), minute: t('health.units.minute'),
  less: t('health.units.less'),
}) : '')

// Nhãn theo ngôn ngữ đang chọn; mã svc-files mới thêm mà giao diện chưa có thì dùng nhãn tiếng Việt từ API
const componentLabel = (c: StatusComponent) => te(`health.component.${c.id}`) ? t(`health.component.${c.id}`) : c.label
const layerLabel = (g: StatusGroup) => te(`health.layer.${g.id}`) ? t(`health.layer.${g.id}`) : g.label

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const res = await fetch('/api/status', { cache: 'no-store' })
    if (res.status === 429) throw new Error(t('health.rateLimited'))
    if (!res.ok) throw new Error(t('health.unreachable'))
    data.value = await res.json()
    failure.value = ''
    loadedAt = Date.now()
  } catch (e) {
    failure.value = e instanceof TypeError ? t('health.unreachable') : e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function onVisible() {
  if (!document.hidden && Date.now() - loadedAt >= STATUS_REFRESH_MS) load()
}

onMounted(() => {
  load()
  timer = setInterval(() => { if (!document.hidden) load() }, STATUS_REFRESH_MS)
  document.addEventListener('visibilitychange', onVisible)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisible)
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight text-stone-900">{{ t('health.title') }}</h1>
        <p class="mt-1 text-sm text-stone-500">{{ t('health.subtitle') }}</p>
      </div>
      <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </div>

    <p v-if="failure" class="card p-4 text-sm text-red-700" role="alert" data-testid="status-failure">
      {{ failure }}<span v-if="data" class="block text-xs text-stone-500">{{ t('health.stale') }}</span>
    </p>
    <p v-if="!data && !failure" class="text-sm text-stone-500">{{ t('app.loading') }}</p>

    <template v-if="data">
      <!-- tình trạng chung -->
      <section class="card flex flex-wrap items-center gap-4 border p-5" :class="OVERALL_TONE[data.status]"
               role="status" aria-live="polite" data-testid="status-overall" :data-status="data.status">
        <svg class="h-8 w-8 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path v-if="data.status === 'ok'" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          <path v-else d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
        </svg>
        <div class="min-w-48 flex-1">
          <div class="text-lg font-semibold">{{ t(`health.overall.${data.status}`) }}</div>
          <p class="text-sm opacity-90">{{ t(`health.overallHint.${data.status}`) }}</p>
        </div>
        <div class="text-right text-xs opacity-80">
          <div>{{ t('health.checkedAt', { time: fmtClock(data.checked_at) }) }}</div>
          <div>{{ t('health.autoRefresh') }}</div>
        </div>
      </section>

      <!-- vận hành -->
      <dl class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div class="card p-4">
          <dt class="text-sm text-stone-500">{{ t('health.version') }}</dt>
          <dd class="mt-1 font-mono text-lg font-semibold text-stone-900" data-testid="status-version">
            {{ data.version }}
          </dd>
        </div>
        <div class="card p-4">
          <dt class="text-sm text-stone-500">{{ t('health.uptime') }}</dt>
          <dd class="mt-1 text-lg font-semibold text-stone-900" data-testid="status-uptime">{{ uptime }}</dd>
          <dd class="mt-1 text-xs text-stone-500">{{ t('health.uptimeHint') }}</dd>
        </div>
        <div class="card p-4">
          <dt class="text-sm text-stone-500">{{ t('health.backup') }}</dt>
          <dd class="mt-1 text-lg font-semibold text-stone-900" data-testid="status-backup">
            {{ data.last_backup_at ? fmtDateTime(data.last_backup_at) : t('health.backupNone') }}
          </dd>
          <dd class="mt-1 text-xs text-stone-500">{{ t('health.backupHint') }}</dd>
        </div>
        <div class="card p-4">
          <dt class="text-sm text-stone-500">{{ t('health.ai') }}</dt>
          <dd class="mt-1 text-lg font-semibold text-stone-900" data-testid="status-ai">
            {{ data.ai.enabled ? t('health.aiOn') : t('health.aiOff') }}
            <span v-if="data.ai.enabled && data.ai.model" class="font-mono text-sm font-normal text-stone-600">
              · {{ data.ai.model }}
            </span>
          </dd>
          <dd class="mt-1 text-xs text-stone-500">
            <template v-if="data.ai.enabled">
              {{ data.ai.semantic ? t('health.aiSemantic') : t('health.aiKeyword') }}
            </template>
            <template v-else>{{ data.ai.semantic ? t('health.aiSemanticOnly') : t('health.aiOffHint') }}</template>
          </dd>
        </div>
      </dl>

      <!-- thành phần theo tầng -->
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-5" data-testid="status-layers">
        <section v-for="(g, i) in groups" :key="g.id" class="card p-4" :data-testid="`status-layer-${g.id}`">
          <h2 class="flex items-center gap-2 text-sm font-semibold text-stone-900">
            <span
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs text-brand-800">
              {{ i + 1 }}
            </span>
            {{ layerLabel(g) }}
          </h2>
          <ul class="mt-3 space-y-3">
            <li v-for="c in g.components" :key="c.id" class="flex items-start gap-2"
                :data-testid="`status-component-${c.id}`" :data-status="c.status">
              <span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" :class="STATE_TONE[c.status].dot"
                    aria-hidden="true" />
              <div class="min-w-0 flex-1">
                <div class="text-sm font-medium text-stone-900">{{ componentLabel(c) }}</div>
                <div class="truncate text-xs text-stone-500">{{ c.software }}</div>
              </div>
              <span class="chip" :class="STATE_TONE[c.status].chip">{{ t(`health.state.${c.status}`) }}</span>
            </li>
          </ul>
        </section>
      </div>

      <p class="text-xs text-stone-500">{{ t('health.note') }}</p>
    </template>
  </div>
</template>
