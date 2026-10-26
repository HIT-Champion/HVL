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

// Một việc trong lịch hạn của hộp việc: cả dòng là một liên kết tới văn bản. Hạn nằm ở đầu nhóm nên dòng không nhắc
// lại; dòng chỉ có dấu độ khẩn, trích yếu, số ký hiệu, nơi gửi, ngày nhận việc và bước phải làm.
interface QueueTask {
  name: string
  form_key: string
  created_at: string
  due_on: string | null
  urgency: string
  document_id: string
  document: { symbol: string | null; summary: string; issuer_name: string | null } | null
}

defineProps<{ task: QueueTask }>()
const { t } = useI18n()
</script>

<template>
  <li class="sg-task-item">
    <NuxtLink :to="{ path: `/van-ban/${task.document_id}`, query: { from: 'inbox' } }" class="sg-task-link">
      <span class="sg-task-mark">
        <UrgencyChip v-if="task.urgency && task.urgency !== 'normal'" :urgency="task.urgency" quiet />
      </span>
      <span class="sg-task-identity">
        <span class="sg-task-title">{{ task.document?.summary || task.name }}</span>
        <span class="sg-task-meta">
          <strong>{{ task.document?.symbol || t('desk.draft') }}</strong>
          <span v-if="task.document?.issuer_name">{{ task.document.issuer_name }}</span>
          <span>{{ t('desk.received', { date: fmtDate(task.created_at).slice(0, 5) }) }}</span>
        </span>
      </span>
      <span class="sg-task-step">{{ t(`task.${task.form_key}`) }}</span>
      <svg
        class="sg-task-go" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="1.6" aria-hidden="true"
      >
        <path d="M5 12h14m-5-5l5 5-5 5" />
      </svg>
    </NuxtLink>
  </li>
</template>
