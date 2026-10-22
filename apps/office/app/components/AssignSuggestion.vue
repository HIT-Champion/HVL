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
import {
  MAX_POLLS, POLL_MS, applyValues, confidenceTone, evidenceIds, matchState, pollState, readEvidence, reasonKey,
  shownEvidence,
} from '~/utils/assignSuggest'
import type { AssignSuggestionRow, SuggestApply, SuggestReadable } from '~/utils/assignSuggest'

// Gợi ý giao việc (F4.3) ở đầu form chỉ đạo: tác tử moc-assigner chạy song song từ lúc vào sổ, gợi ý đơn vị chủ trì
// và hạn theo các văn bản tương tự đã giao. Mọi truy vấn bằng token người xem: căn cứ chỉ hiện văn bản người xem đọc
// được (đã loại văn bản hạn chế). "Dùng gợi ý" chỉ điền form, không gửi — lãnh đạo vẫn tự bấm "Giao xử lý".
// Không dùng <label> / aria-label trong khối: tên ô của form ("Phòng chủ trì", "Hạn giải quyết"…) và tên phòng chỉ
// được là nhãn của chính ô đó (kịch bản e2e tìm ô theo nhãn, chế độ strict).
const props = defineProps<{
  documentId: string
  departments: { id: string; name: string }[]
  chosen: string | null
  documentDue: string | null
}>()
const emit = defineEmits<{ apply: [SuggestApply] }>()

const { t } = useI18n()
const { gql } = useApi()

const row = ref<AssignSuggestionRow | null>(null)
const waiting = ref(false)
const readable = ref(new Map<string, SuggestReadable>())
let timer: ReturnType<typeof setTimeout> | null = null
let polls = 0
let alive = true

const GOI_Y = `query GoiYGiaoViec($id: uuid!) {
  office_assignment_suggestions_by_pk(document_id: $id) {
    status reason department_id confidence share due_days due_on evidence created_at }
  office_documents_by_pk(id: $id) { registered_at } }`
const CAN_CU = `query CanCuGoiY($ids: [uuid!]!) {
  office_documents(where: {id: {_in: $ids}, restricted: {_eq: false}}) { id symbol summary } }`

function stop() {
  if (timer) clearTimeout(timer)
  timer = null
}

async function load() {
  timer = null
  const want = props.documentId
  try {
    const data = await gql<{
      office_assignment_suggestions_by_pk: AssignSuggestionRow | null
      office_documents_by_pk: { registered_at: string | null } | null
    }>(GOI_Y, { id: want })
    if (!alive || want !== props.documentId) return
    const found = data.office_assignment_suggestions_by_pk
    polls += 1
    if (found) {
      row.value = found
      waiting.value = false
      if (found.status === 'suggested') void loadEvidence(want, evidenceIds(found.evidence))
      return
    }
    // chưa có dòng: tác tử còn đang tìm (vào sổ chưa quá 60 giây) thì hỏi lại sau 3 giây, quá thì thôi không hiện
    waiting.value = pollState(found, data.office_documents_by_pk?.registered_at, Date.now()) === 'wait' && polls < MAX_POLLS
    if (waiting.value) timer = setTimeout(load, POLL_MS)
  } catch {
    // gợi ý chỉ là phần thêm: lỗi mạng, lỗi quyền thì không hiện gì, lãnh đạo giao việc như thường lệ
    if (alive && want === props.documentId) waiting.value = false
  }
}

// Căn cứ: hỏi lại bằng token người xem — văn bản không đọc được (hay vừa bị đặt hạn chế) không có trong kết quả
async function loadEvidence(want: string, ids: string[]) {
  if (!ids.length) return
  try {
    const data = await gql<{ office_documents: { id: string; symbol: string | null; summary: string | null }[] }>(
      CAN_CU, { ids })
    if (!alive || want !== props.documentId) return
    readable.value = new Map(data.office_documents.map((d) => [d.id, { symbol: d.symbol, summary: d.summary }]))
  } catch {
    // không đọc được căn cứ: vẫn hiện gợi ý, chỉ không có liên kết
  }
}

function reset() {
  stop()
  row.value = null
  waiting.value = false
  readable.value = new Map()
  polls = 0
}

onMounted(load)
watch(() => props.documentId, () => {
  reset()
  void load()
})
onBeforeUnmount(() => {
  alive = false
  stop()
})

const deptName = (id: string | null) => (id ? props.departments.find((d) => d.id === id)?.name ?? '' : '')
const unitName = computed(() => deptName(row.value?.department_id ?? null))

// Trạng thái hiện: đang tìm, có gợi ý, không gợi ý / lỗi (một dòng mờ), hoặc không hiện gì. Gợi ý một phòng không
// có trong danh mục (phòng vừa bị xóa) thì không hiện — không có gì để điền vào form.
const state = computed<'off' | 'waiting' | 'suggested' | 'none'>(() => {
  const r = row.value
  if (!r) return waiting.value ? 'waiting' : 'off'
  if (r.status === 'suggested') return unitName.value && r.confidence ? 'suggested' : 'off'
  return 'none'
})

const evidenceCount = computed(() => readEvidence(row.value?.evidence).length)
const links = computed(() => shownEvidence(row.value?.evidence, readable.value))
const match = computed(() => matchState(row.value, props.chosen))
const reasonText = computed(() => {
  const key = reasonKey(row.value?.reason)
  return key ? t('assign.suggest.nothing', { reason: t(key) }) : t('assign.suggest.nothingPlain')
})

// "Hạn đề xuất": văn bản đã ghi hạn thì theo hạn đó (tác tử không gợi ý hạn); không thì hạn tác tử tính từ số ngày
// các văn bản tương tự đã được giao
const dueText = computed(() => {
  const r = row.value
  if (props.documentDue) return t('assign.suggest.dueFromDocument', { date: fmtDate(props.documentDue) })
  if (!r?.due_on) return ''
  const n = r.due_days ?? 0
  return n > 0 ? t('assign.suggest.dueDays', { date: fmtDate(r.due_on), n }, n) : fmtDate(r.due_on)
})

function apply() {
  const values = applyValues(row.value, props.documentDue, today())
  if (values) emit('apply', values)
}
</script>

<template>
  <div aria-live="polite" data-testid="assign-suggestion" :data-state="state">
    <p v-if="state === 'waiting'" class="flex items-center gap-2 text-sm text-stone-500">
      <span class="h-2 w-2 shrink-0 rounded-full bg-stone-400 motion-safe:animate-pulse" aria-hidden="true" />
      {{ t('assign.suggest.searching') }}
    </p>

    <p v-else-if="state === 'none'" class="text-sm text-stone-500" data-testid="assign-suggest-none">{{ reasonText }}</p>

    <div v-else-if="state === 'suggested' && row" class="space-y-2 rounded-lg border border-stone-200 bg-stone-50 p-4 text-sm text-stone-700">
      <div class="flex flex-wrap items-center gap-2">
        <svg class="h-4 w-4 text-brand-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4L12 3zM18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8L18 15z" /></svg>
        <h3 class="font-semibold text-stone-900">{{ t('assign.suggest.title') }}</h3>
        <span class="chip" :class="confidenceTone(row.confidence)" data-testid="assign-suggest-confidence">
          {{ t(`assign.suggest.confidence.${row.confidence}`) }}
        </span>
      </div>
      <p>{{ t('assign.suggest.unit') }}: <strong class="font-semibold text-stone-900" data-testid="assign-suggest-unit">{{ unitName }}</strong></p>
      <p v-if="dueText">{{ t('assign.suggest.due') }}: <span class="font-medium text-stone-900">{{ dueText }}</span></p>
      <div v-if="evidenceCount">
        <p>{{ t('assign.suggest.evidence', { n: evidenceCount }, evidenceCount) }}</p>
        <ul v-if="links.length" class="mt-1 space-y-1 pl-1" data-testid="assign-suggest-evidence">
          <li v-for="e in links" :key="e.document_id" class="flex gap-1.5">
            <span class="text-stone-400" aria-hidden="true">•</span>
            <span>
              <NuxtLink :to="`/van-ban/${e.document_id}`" class="font-medium text-brand-700 underline-offset-2 hover:underline focus-visible:underline">
                <template v-if="e.symbol">{{ e.symbol }} — </template>{{ e.summary }}
              </NuxtLink>
              <span v-if="deptName(e.department_id)" class="text-stone-500"> → {{ deptName(e.department_id) }}</span>
              <span v-if="e.days" class="text-stone-500"> · {{ t('assign.suggest.days', { n: e.days }, e.days) }}</span>
            </span>
          </li>
        </ul>
      </div>
      <div class="flex flex-wrap items-center gap-3 pt-1">
        <button type="button" class="btn-secondary" aria-describedby="assign-suggest-hint" @click="apply">
          {{ t('assign.suggest.apply') }}
        </button>
        <span
          v-if="match" class="chip" data-testid="assign-suggest-match"
          :class="match === 'kept' ? 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-300' : 'bg-stone-100 text-stone-700 ring-1 ring-stone-300'"
        >
          {{ t(`assign.suggest.${match}`) }}
        </span>
        <span id="assign-suggest-hint" class="text-xs text-stone-500">{{ t('assign.suggest.applyHint') }}</span>
      </div>
      <p class="text-xs text-stone-500">{{ t('assign.suggest.note') }}</p>
    </div>
  </div>
</template>
