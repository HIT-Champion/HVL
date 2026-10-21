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
import type { ReadField } from '~/composables/useApi'
import { tagState } from '~/utils/suggest'

// Nhãn cạnh tên ô của form tiếp nhận (F4.1): ô do tác tử đọc văn bản điền sẵn. Chữ trên nhãn tự nói đủ (không chỉ
// dựa vào màu): "Gợi ý" (độ tin cậy cao), "Gợi ý (chưa chắc)", "Gợi ý của mô hình", "Đã sửa" khi văn thư sửa khác
// gợi ý. Ô nhập trỏ tới nhãn bằng aria-describedby để trình đọc màn hình đọc kèm độ tin cậy.
const props = defineProps<{
  suggestion?: ReadField
  value: string
  display?: string   // giá trị gợi ý để hiện khi đã sửa (vd tên loại văn bản thay cho mã)
}>()

const { t } = useI18n()

const tone = {
  high: 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-300',
  medium: 'bg-amber-50 text-amber-900 ring-1 ring-amber-300',
  model: 'bg-sky-50 text-sky-900 ring-1 ring-sky-300',
  edited: 'bg-stone-100 text-stone-700 ring-1 ring-stone-300',
} as const

const state = computed(() => tagState(props.suggestion, props.value))
const hint = computed(() => {
  const s = props.suggestion
  if (!s || !state.value) return ''
  if (state.value === 'edited') return t('receive.suggest.editedHint', { value: props.display ?? s.value })
  return t('receive.suggest.hint', {
    source: t(`receive.suggest.source.${s.source}`), confidence: t(`receive.suggest.confidence.${s.confidence}`),
  })
})
</script>

<template>
  <span v-if="state" class="chip gap-1" :class="tone[state]" :title="hint">
    <svg v-if="state === 'edited'" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M15.2 5.2l3.6 3.6M4 20l4.2-1 10.6-10.6a2.5 2.5 0 00-3.6-3.6L4.6 15.4 4 20z" /></svg>
    <svg v-else class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4L12 3zM18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8L18 15z" /></svg>
    {{ t(`receive.suggest.${state}`) }}<span class="sr-only">. {{ hint }}</span>
  </span>
</template>
