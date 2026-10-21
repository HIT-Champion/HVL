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

interface InboxTask {
  id: string
  name: string
  form_key: string
  created_at: string
  due_on: string | null
  urgency: string
  document_id: string
  document: { symbol: string | null; summary: string; issuer_name: string | null; register_number: number | null; status: string } | null
}

const { t } = useI18n()
const { gql } = useApi()
const tasks = ref<InboxTask[]>([])
const loading = ref(true)
const failure = ref('')

async function load() {
  loading.value = true
  failure.value = ''
  try {
    const data = await gql<{ myTasks: InboxTask[] }>(`{
      myTasks { id name form_key created_at due_on urgency document_id
        document { symbol summary issuer_name register_number status } }
    }`)
    tasks.value = data.myTasks
  } catch (e) {
    failure.value = errorText(t, e)
  } finally {
    loading.value = false
  }
}

// Quản trị đơn vị không có hộp việc (Action myTasks chỉ cho vai trò nghiệp vụ, menu cũng không có): trang đầu của
// họ là sổ kiểm toán
const claims = useAuth().claims
onMounted(() => {
  if (claims.value?.role === 'tenant_admin') void navigateTo('/so-kiem-toan', { replace: true })
  else void load()
})

// việc mới, nhắc hạn đẩy tới (F2.5): tải lại hộp việc, không phải bấm Làm mới
const { lastPush } = useNotifications()
watch(lastPush, (n) => { if (n?.kind.startsWith('task.')) load() })
</script>

<template>
  <div>
    <PageHeader :title="t('inbox.title')" :subtitle="t('inbox.subtitle')">
      <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>

    <p v-if="failure" class="card p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-else-if="loading && !tasks.length" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <div v-else-if="!tasks.length" class="card flex flex-col items-center gap-2 p-12 text-center text-stone-500">
      <svg class="h-10 w-10 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
      {{ t('inbox.empty') }}
    </div>

    <ul v-else class="space-y-3" data-testid="inbox">
      <li v-for="task in tasks" :key="task.id">
        <NuxtLink
          :to="`/van-ban/${task.document_id}`"
          class="card flex flex-col gap-3 p-4 transition hover:border-brand-600 hover:shadow-md sm:flex-row sm:items-center"
        >
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <span class="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">{{ t(`task.${task.form_key}`) }}</span>
              <UrgencyChip :urgency="task.urgency" quiet />
              <span v-if="task.document?.register_number" class="text-xs text-stone-500">
                {{ t('incoming.number') }} {{ task.document.register_number }}
              </span>
            </div>
            <div class="truncate font-medium text-stone-900">{{ task.document?.summary }}</div>
            <div class="mt-0.5 text-sm text-stone-500">
              {{ task.document?.symbol }}<span v-if="task.document?.issuer_name"> · {{ task.document.issuer_name }}</span>
            </div>
          </div>
          <div class="shrink-0 text-sm text-stone-500 sm:text-right">
            <div>{{ t('inbox.received') }}: {{ fmtDateTime(task.created_at) }}</div>
            <div v-if="task.due_on" class="font-medium text-amber-700">{{ t('inbox.due') }}: {{ fmtDate(task.due_on) }}</div>
          </div>
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>
