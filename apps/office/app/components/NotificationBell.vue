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
import type { AppNotification } from '~/composables/useNotifications'

// Chuông thông báo trên thanh trên: số chưa đọc, 20 tin mới nhất, chấm xanh khi đang nhận tin trực tiếp
const { t } = useI18n()
const { items, unread, markRead, markAllRead } = useNotifications()
const { state } = useRealtime()
const notice = useNotice()
const open = ref(false)
const root = ref<HTMLElement | null>(null)

function outside(e: MouseEvent) {
  if (open.value && root.value && !root.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('click', outside))
onBeforeUnmount(() => document.removeEventListener('click', outside))

const URGENT = new Set(['task.overdue', 'task.escalated', 'document.overdue', 'ot.alarm'])
const rows = computed(() => items.value.map((n) => ({ n, ...describeNotification(t, n), urgent: URGENT.has(n.kind) })))

async function go(n: AppNotification) {
  open.value = false
  markRead(n).catch(() => { /* lần sau tải lại vẫn thấy chưa đọc */ })
  if (n.document_id) await navigateTo(`/van-ban/${n.document_id}`)
}

async function readAll() {
  try {
    await markAllRead()
  } catch (e) {
    notice.error(errorText(t, e))
  }
}
</script>

<template>
  <div ref="root" class="relative" @keydown.esc.stop="open = false">
    <button
      class="btn-ghost relative" :aria-label="t('notify.title')" :aria-expanded="open" data-testid="notification-bell"
      @click="open = !open"
    >
      <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
      </svg>
      <span
        v-if="unread" data-testid="notification-count"
        class="absolute -top-0.5 -right-0.5 min-w-[1.15rem] rounded-full bg-red-600 px-1 text-center text-[11px] leading-[1.15rem] font-semibold text-white"
      >{{ unread > 99 ? '99+' : unread }}</span>
      <span
        class="absolute right-1 bottom-1 h-2 w-2 rounded-full ring-2 ring-white"
        :class="state === 'online' ? 'bg-emerald-500' : 'bg-stone-300'" aria-hidden="true"
      />
    </button>

    <Transition name="sg-popover">
    <div
      v-if="open"
      class="absolute right-0 z-50 mt-2 w-96 max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-stone-200 bg-white shadow-xl"
    >
      <div class="flex items-center justify-between border-b border-stone-200 px-4 py-3">
        <div class="font-semibold text-stone-900">{{ t('notify.title') }}</div>
        <button v-if="unread" class="text-xs font-medium text-brand-700 hover:underline" @click="readAll">
          {{ t('notify.markAll') }}
        </button>
      </div>
      <p class="border-b border-stone-100 px-4 py-2 text-xs" :class="state === 'online' ? 'text-emerald-700' : 'text-stone-500'">
        {{ state === 'online' ? t('notify.live') : t('notify.offline') }}
      </p>
      <ul v-if="rows.length" class="max-h-[60vh] divide-y divide-stone-100 overflow-y-auto">
        <li v-for="row in rows" :key="row.n.id">
          <button class="flex w-full gap-3 px-4 py-3 text-left hover:bg-stone-50" @click="go(row.n)">
            <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" :class="row.n.read_at ? 'bg-transparent' : 'bg-brand-600'" aria-hidden="true" />
            <span class="min-w-0 flex-1">
              <span
                class="block text-sm"
                :class="[row.n.read_at ? 'text-stone-700' : 'font-medium', row.urgent ? 'text-amber-800' : row.n.read_at ? '' : 'text-stone-900']"
              >{{ row.title }}</span>
              <span v-if="row.detail" class="block truncate text-sm text-stone-500">{{ row.detail }}</span>
              <span v-if="row.note" class="block truncate text-sm text-stone-600 italic">{{ row.note }}</span>
              <span class="mt-0.5 block text-xs text-stone-400">{{ fmtDateTime(row.n.created_at) }}</span>
            </span>
          </button>
        </li>
      </ul>
      <p v-else class="px-4 py-10 text-center text-sm text-stone-500">{{ t('notify.empty') }}</p>
    </div>
    </Transition>
  </div>
</template>
