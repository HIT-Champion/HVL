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

// Một việc trong hộp việc: cả dòng là một liên kết tới văn bản. Dòng 1: dấu độ khẩn và trích yếu; dòng 2: số ký hiệu,
// nơi gửi và bước phải làm. Cột phải: hạn và còn bao nhiêu ngày (quá hạn thì đỏ son), thẳng hàng giữa các dòng.
interface QueueTask {
  name: string
  form_key: string
  due_on: string | null
  urgency: string
  document_id: string
  document: { symbol: string | null; summary: string; issuer_name: string | null } | null
}

const props = defineProps<{ task: QueueTask; day: string; overdue?: boolean }>()
const { t } = useI18n()

const left = computed(() => props.task.due_on ? daysUntil(props.task.due_on, props.day) : null)
const dueNote = computed(() => {
  const n = left.value
  if (n === null) return t('desk.noDeadline')
  if (n < 0) return t('desk.overdueBy', { n: -n }, -n)
  if (n === 0) return t('desk.dueToday')
  return t('desk.dueIn', { n }, n)
})
</script>

<template>
  <li class="sg-task-item" :class="{ 'is-overdue': overdue }">
    <NuxtLink :to="{ path: `/van-ban/${task.document_id}`, query: { from: 'inbox' } }" class="sg-task-link">
      <div class="sg-task-identity">
        <h3>
          <UrgencyChip v-if="task.urgency && task.urgency !== 'normal'" :urgency="task.urgency" quiet />
          <span>{{ task.document?.summary || task.name }}</span>
        </h3>
        <p class="sg-task-meta">
          <strong>{{ task.document?.symbol || t('desk.draft') }}</strong>
          <span v-if="task.document?.issuer_name">{{ task.document.issuer_name }}</span>
          <span class="sg-task-step">{{ t(`task.${task.form_key}`) }}</span>
        </p>
      </div>
      <p class="sg-task-deadline" :class="{ 'is-overdue': overdue }">
        <span class="sr-only">{{ t('fe.due') }}</span>
        <strong>{{ task.due_on ? fmtDate(task.due_on) : '—' }}</strong>
        <span>{{ dueNote }}</span>
      </p>
      <svg
        class="sg-task-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="1.6" aria-hidden="true"
      >
        <path d="M5 12h14m-5-5l5 5-5 5" />
      </svg>
    </NuxtLink>
  </li>
</template>
