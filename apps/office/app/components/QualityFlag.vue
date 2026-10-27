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
import type { CheckStatus } from '~/utils/quality'

// Cờ kiểm chất lượng số liệu (F3.9, F3.11): Đạt / Cảnh báo / Trượt; không có luật nào thì "Không kiểm" (hay chữ do nơi
// dùng đặt, vd "Chưa kiểm được"). Chữ tự nói đủ, mỗi mức một biểu tượng riêng — không chỉ dựa vào màu; chi tiết (luật
// nào, số nào) trong title khi rê chuột và cho trình đọc màn hình.
const props = defineProps<{ status: CheckStatus | null; detail?: string; empty?: string }>()
const { t } = useI18n()

const tone: Record<CheckStatus | 'NONE', string> = {
  PASSED: 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-300',
  WARNING: 'bg-amber-50 text-amber-900 ring-1 ring-amber-300',
  FAILED: 'bg-red-50 text-red-800 ring-1 ring-red-300',
  NONE: 'bg-stone-100 text-stone-600 ring-1 ring-stone-300',
}
// dấu tích, tam giác chấm than, dấu nhân; "Không kiểm" không có biểu tượng
const ICON: Record<CheckStatus | 'NONE', string> = {
  PASSED: 'M5 13l4 4L19 7',
  WARNING: 'M12 9v4m0 4h.01M10.3 3.9L2.4 17.5A2 2 0 004.1 20.5h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  FAILED: 'M6 6l12 12M18 6L6 18',
  NONE: '',
}
const level = computed(() => props.status ?? 'NONE')
const label = computed(() => (props.status ? t(`quality.status.${props.status}`)
  : props.empty ?? t('quality.status.NONE')))
</script>

<template>
  <span class="chip relative gap-1" :class="tone[level]" :title="detail || undefined" :data-status="level">
    <svg
      v-if="level !== 'NONE'" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"
      stroke-width="2.5" aria-hidden="true"
    >
      <path stroke-linecap="round" stroke-linejoin="round" :d="ICON[level]" />
    </svg>
    {{ label }}<span v-if="detail" class="sr-only">. {{ detail }}</span>
  </span>
</template>
