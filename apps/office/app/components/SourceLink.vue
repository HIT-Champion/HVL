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
import { BOARD_CHARTS } from '~/utils/lineage';

// Nút "Nguồn số liệu" trên từng biểu đồ của trang Điều hành (F3.11): mở trang Phả hệ (F3.9) lọc đúng biểu đồ đó —
// biểu đồ ← khung nhìn ← bảng. Biểu đồ nào dùng khung nhìn nào khai ở app/utils/lineage.ts (BOARD_CHARTS).
const props = defineProps({ chart: { type: String, required: true } });
const { t } = useI18n();
const title = computed(() => t(BOARD_CHARTS.find((c) => c.id === props.chart)?.label ?? 'lineage.title'));
</script>

<template>
  <NuxtLink
    :to="{ path: '/pha-he', query: { 'bieu-do': chart } }"
    class="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-brand-700 hover:underline"
    :aria-label="t('lineage.sourceOf', { chart: title })"
    :data-testid="`source-${chart}`"
  >
    <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path
        stroke-linecap="round" stroke-linejoin="round"
        d="M4 9h5v6H4zM15 3h5v6h-5zM15 15h5v6h-5zM9 12h3m0-6v12m0-12h3m-3 12h3"
      />
    </svg>
    {{ t('lineage.source') }}
  </NuxtLink>
</template>
