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
import type { SearchHit } from '~/composables/useApi'

// Tìm kiếm (F1.7, F2.7): Meilisearch xếp hạng, Hasura lọc theo quyền — chỉ hiện văn bản người dùng được đọc.
const { t } = useI18n()
const { search } = useApi()
const route = useRoute()
const router = useRouter()

const q = ref(String(route.query.q ?? ''))
const direction = ref(String(route.query.direction ?? ''))
// "Hỏi trợ lý" (F4.2): mang câu đang tìm sang trang Hỏi đáp, điền sẵn, không tự gửi
const claims = useAuth().claims
const canAsk = computed(() => ['clerk', 'staff', 'manager', 'director'].includes(claims.value?.role ?? ''))
const askLink = computed(() => (q.value.trim() ? { path: '/hoi-dap', query: { q: q.value.trim() } } : { path: '/hoi-dap' }))
const hits = ref<SearchHit[]>([])
const next = ref<string | null>(null)
// "Xem thêm" lấy tiếp đúng câu tìm đang hiện kết quả, dù ô tìm đã gõ khác: trang sau gắn với câu tìm (svc-files)
let shown: { q: string; direction?: string } = { q: '' }
const loading = ref(false)
const searched = ref(false)
const failure = ref('')

async function run(more = false) {
  if (!more && !q.value.trim()) return
  const params = more ? shown : { q: q.value.trim(), direction: direction.value || undefined }
  loading.value = true
  failure.value = ''
  try {
    const res = await search({ ...params, limit: 20, cursor: more ? next.value ?? undefined : undefined })
    hits.value = more ? [...hits.value, ...res.hits] : res.hits
    next.value = res.next_cursor
    shown = params
    searched.value = true
    if (!more) router.replace({ query: { q: q.value.trim(), ...(direction.value ? { direction: direction.value } : {}) } })
  } catch (e) {
    failure.value = errorText(t, e)
  } finally {
    loading.value = false
  }
}

onMounted(() => { if (q.value) run() })
</script>

<template>
  <div>
    <PageHeader :title="t('search.title')">
      <NuxtLink v-if="canAsk" :to="askLink" class="btn-secondary" data-testid="ask-assistant">
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 10h8M8 14h5M21 12a9 9 0 01-13.2 8L3 21l1.1-4.6A9 9 0 1121 12z" /></svg>
        {{ t('search.askAssistant') }}
      </NuxtLink>
    </PageHeader>
    <form class="mb-6 flex max-w-4xl flex-col gap-2 sm:flex-row" @submit.prevent="run()">
      <input v-model="q" type="search" class="input flex-1" :aria-label="t('search.title')" :placeholder="t('search.placeholder')" maxlength="200" autofocus>
      <select v-model="direction" class="input sm:w-44" :aria-label="t('search.directionLabel')">
        <option value="">{{ t('search.any') }}</option>
        <option value="in">{{ t('search.direction.in') }}</option>
        <option value="out">{{ t('search.direction.out') }}</option>
      </select>
      <button type="submit" class="btn-primary" :disabled="loading || !q.trim()">{{ t('search.button') }}</button>
    </form>

    <p v-if="failure" class="moc-state text-red-700" role="alert">{{ failure }}</p>
    <div v-else-if="searched && !hits.length" class="moc-empty"><h2>{{ t('search.empty') }}</h2></div>
    <!-- kết quả là danh sách hai dòng như hộp việc: trích yếu trước, số ký hiệu, nơi ban hành sau; trạng thái ở
      cột phải -->
    <ul v-else class="sg-task-list max-w-5xl">
      <li v-for="h in hits" :key="h.id" class="sg-task-item">
        <NuxtLink :to="`/van-ban/${h.id}`" class="sg-result">
          <div class="sg-task-identity">
            <h3>
              <UrgencyChip :urgency="h.urgency" quiet />
              <span>{{ h.summary }}</span>
            </h3>
            <p class="sg-task-meta">
              <strong>{{ h.symbol }}</strong>
              <span v-if="h.issuer_name">{{ h.issuer_name }}</span>
              <span>{{ fmtDate(h.issued_on) }}</span>
              <span>
                {{ t(`search.direction.${h.direction}`) }}<template v-if="h.register_number">
                  {{ t('incoming.number').toLowerCase() }} {{ h.register_number }}</template>
              </span>
            </p>
          </div>
          <div class="sg-result-side">
            <StatusChip :status="h.status" />
            <span
              v-if="h.matched_content" class="chip bg-amber-50 text-amber-900" :title="t('search.matchedContentHint')"
            >{{ t('search.matchedContent') }}</span>
          </div>
        </NuxtLink>
      </li>
    </ul>
    <div v-if="next !== null" class="mt-4 text-center">
      <button class="btn-secondary" :disabled="loading" @click="run(true)">{{ t('search.more') }}</button>
    </div>
  </div>
</template>
