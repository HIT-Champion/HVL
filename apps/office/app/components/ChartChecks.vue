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
import { checkMessages, checksFor, worstCheck } from '~/utils/quality';

// Cờ kiểm chất lượng số liệu cạnh nút "Nguồn số liệu" của từng biểu đồ trang Điều hành (F3.11): cờ nặng nhất trong các
// luật của office.report_checks trên các khung nhìn biểu đồ dùng (BOARD_CHARTS); rê chuột xem từng luật, bấm mở mục
// Kiểm chất lượng của trang Phả hệ lọc đúng biểu đồ. Chưa tải xong: không hiện gì; tải lỗi: "Chưa kiểm được".
const props = defineProps({ chart: { type: String, required: true }, checks: { type: Array, default: null }, failed: { type: Boolean, default: false } });
const { t } = useI18n();

const title = computed(() => t(BOARD_CHARTS.find((c) => c.id === props.chart)?.label ?? 'lineage.title'));
const rows = computed(() => checksFor(props.checks ?? [],
BOARD_CHARTS.find((c) => c.id === props.chart)?.views ?? []));
const status = computed(() => props.failed ? null : worstCheck(rows.value.map((r) => r.status)));
const detail = computed(() => props.failed ? t('quality.unavailable') : rows.value.map((r) =>
`${t(`quality.status.${r.status}`)} — ${t(`quality.rules.${r.rule}.name`)} (${r.report}): ` +
checkMessages(r).map(([key, params]) => t(key, params)).join('; ')).join('\n'));
</script>

<template>
  <NuxtLink
    v-if="checks || failed"
    :to="{ path: '/pha-he', query: { 'bieu-do': chart }, hash: '#chat-luong' }"
    class="inline-flex shrink-0 rounded-full focus-visible:outline-2 focus-visible:outline-offset-2
      focus-visible:outline-brand-700"
    :data-testid="`checks-${chart}`"
  >
    <span class="sr-only">{{ t('quality.flagOf', { chart: title }) }}: </span>
    <QualityFlag :status="status" :detail="detail" :empty="failed ? t('quality.unavailable') : undefined" />
  </NuxtLink>
</template>
