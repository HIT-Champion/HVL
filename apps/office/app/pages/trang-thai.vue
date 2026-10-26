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
  <div>
    <PageHeader :title="t('health.title')" :subtitle="t('health.subtitle')">
      <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>

    <p v-if="failure" class="moc-state mb-6" role="alert" data-testid="status-failure">
      <span>{{ failure }}<span v-if="data" class="block text-[13px]">{{ t('health.stale') }}</span></span>
    </p>
    <p v-if="!data && !failure" class="moc-loading">{{ t('app.loading') }}</p>

    <div v-if="data" class="moc-stack">
      <!-- tình trạng chung: màu theo tình trạng, chữ đậm trên nền nhạt -->
      <section
        class="flex flex-wrap items-center gap-4 rounded-xl border px-6 py-5" :class="OVERALL_TONE[data.status]"
        role="status" aria-live="polite" data-testid="status-overall" :data-status="data.status"
      >
        <svg
          class="h-8 w-8 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
        >
          <path v-if="data.status === 'ok'" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          <path v-else d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
        </svg>
        <div class="min-w-48 flex-1">
          <div class="text-lg leading-7 font-semibold">{{ t(`health.overall.${data.status}`) }}</div>
          <p class="mt-0.5 text-sm">{{ t(`health.overallHint.${data.status}`) }}</p>
        </div>
        <div class="text-[13px] tabular-nums sm:text-right">
          <div>{{ t('health.checkedAt', { time: fmtClock(data.checked_at) }) }}</div>
          <div>{{ t('health.autoRefresh') }}</div>
        </div>
      </section>

      <!-- vận hành: một khối, bốn mục; dd thứ hai là chú thích -->
      <section class="moc-block">
        <dl class="moc-facts">
          <div>
            <dt>{{ t('health.version') }}</dt>
            <dd class="font-mono text-base" data-testid="status-version">{{ data.version }}</dd>
          </div>
          <div>
            <dt>{{ t('health.uptime') }}</dt>
            <dd class="text-base tabular-nums" data-testid="status-uptime">{{ uptime }}</dd>
            <dd>{{ t('health.uptimeHint') }}</dd>
          </div>
          <div>
            <dt>{{ t('health.backup') }}</dt>
            <dd class="text-base tabular-nums" data-testid="status-backup">
              {{ data.last_backup_at ? fmtDateTime(data.last_backup_at) : t('health.backupNone') }}
            </dd>
            <dd>{{ t('health.backupHint') }}</dd>
          </div>
          <div>
            <dt>{{ t('health.ai') }}</dt>
            <dd class="text-base" data-testid="status-ai">
              {{ data.ai.enabled ? t('health.aiOn') : t('health.aiOff') }}
              <span v-if="data.ai.enabled && data.ai.model" class="font-mono text-sm text-stone-600">
                · {{ data.ai.model }}
              </span>
            </dd>
            <dd>
              <template v-if="data.ai.enabled">
                {{ data.ai.semantic ? t('health.aiSemantic') : t('health.aiKeyword') }}
              </template>
              <template v-else>{{ data.ai.semantic ? t('health.aiSemanticOnly') : t('health.aiOffHint') }}</template>
            </dd>
          </div>
        </dl>
      </section>

      <!-- thành phần theo tầng: mỗi tầng một hàng, tên tầng bên trái, thành phần bên phải -->
      <div class="moc-block !py-1" data-testid="status-layers">
        <section
          v-for="(g, i) in groups" :key="g.id" :data-testid="`status-layer-${g.id}`"
          class="grid gap-3 border-t border-stone-100 py-5 first:border-t-0 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-6"
        >
          <h2 class="moc-block-title flex items-center gap-2.5">
            <span
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[13px]
                text-brand-800 tabular-nums"
            >{{ i + 1 }}</span>
            {{ layerLabel(g) }}
          </h2>
          <ul class="grid gap-x-8 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
            <li
              v-for="c in g.components" :key="c.id" class="flex min-w-0 items-start gap-2.5"
              :data-testid="`status-component-${c.id}`" :data-status="c.status"
            >
              <span
                class="mt-[7px] h-2.5 w-2.5 shrink-0 rounded-full" :class="STATE_TONE[c.status].dot" aria-hidden="true"
              />
              <div class="min-w-0 flex-1">
                <div class="text-sm font-medium text-stone-900">{{ componentLabel(c) }}</div>
                <div class="truncate text-[13px] text-stone-500">{{ c.software }}</div>
              </div>
              <span class="chip" :class="STATE_TONE[c.status].chip">{{ t(`health.state.${c.status}`) }}</span>
            </li>
          </ul>
        </section>
      </div>

      <p class="text-[13px] text-stone-500">{{ t('health.note') }}</p>
    </div>
  </div>
</template>
