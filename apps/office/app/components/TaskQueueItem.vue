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

<script setup>
import { useI18n } from 'vue-i18n';
defineProps({ task: { type: Object, required: true }, highlight: Boolean, overdue: Boolean });
const { t } = useI18n();
</script>
<template>
  <li class="sg-task-item" :class="{ 'is-highlight': highlight }"><NuxtLink :to="'/van-ban/' + task.document_id" class="sg-task-link">
    <div class="sg-task-identity"><div v-if="highlight" class="sg-task-alert"><UrgencyChip v-if="task.urgency && task.urgency !== 'normal'" :urgency="task.urgency" quiet /><span v-if="overdue" class="chip bg-red-100 text-red-800">{{ t('fe.overdue') }}</span></div><h3>{{ task.document?.summary || task.name }}</h3><div class="sg-task-meta"><strong>{{ task.document?.symbol || t('desk.draft') }}</strong><span v-if="task.document?.issuer_name">{{ task.document.issuer_name }}</span></div><p v-if="!highlight" class="sg-task-work">{{ t('task.' + task.form_key) }}</p></div>
    <div class="sg-task-deadline" :class="{ 'is-overdue': overdue }"><span>{{ t('fe.due') }}</span><strong>{{ task.due_on ? fmtDate(task.due_on) : t('desk.noDeadline') }}</strong></div>
    <span class="sg-task-action"><span v-if="highlight">{{ t('task.' + task.form_key) }}</span><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M5 12h14m-5-5l5 5-5 5" /></svg></span>
  </NuxtLink></li>
</template>
