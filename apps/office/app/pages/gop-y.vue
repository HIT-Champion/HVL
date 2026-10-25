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


// Góp ý (F4.6): ai cũng xem lại góp ý mình đã gửi (trường `mine`). Lãnh đạo, quản trị đơn vị xem thêm tổng hợp của đơn
// vị — điểm trung bình, số góp ý theo màn hình (office.v_feedback_summary) — và các góp ý gần đây, không có người gửi:
// Hasura không cho hai vai trò này đọc cột user_id (db/metadata/.../office_feedback.yaml). Gửi góp ý ở nút trên thanh
// trên (components/FeedbackButton.vue).

const MINE = `{ office_feedback(where: {mine: {_eq: true}}, order_by: {created_at: desc}, limit: 50) {
  id rating comment screen created_at mine } }`;
const UNIT = `{
  office_v_feedback_summary { sample screen feedback rating_total rating_1 rating_2 rating_3 rating_4 rating_5
    with_comment last_at }
  office_feedback(order_by: {created_at: desc}, limit: 50) { id rating comment screen created_at mine }
}`;

const { t, locale } = useI18n();
const { gql } = useApi();
const claims = useAuth().claims;

const mine = ref([]);
const summary = ref([]);
const recent = ref([]);
const loaded = ref(false);
const loading = ref(false);
const failure = ref('');
const leader = computed(() => claims.value?.role === 'director' || claims.value?.role === 'tenant_admin');

async function load() {
  loading.value = true;
  failure.value = '';
  try {
    mine.value = (await gql(MINE)).office_feedback;
    if (leader.value) {
      const data = await gql(UNIT);
      summary.value = data.office_v_feedback_summary;
      recent.value = data.office_feedback;
    }
    loaded.value = true;
  } catch (e) {
    failure.value = errorText(t, e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const number = computed(() => new Intl.NumberFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB', { maximumFractionDigits: 1 }));
const split = computed(() => splitSummary(summary.value));
const sample = computed(() => isSample(summary.value));
function average(row) {
  const avg = averageRating(row);
  return avg === null ? '—' : number.value.format(avg);
}
</script>

<template>
  <div>
    <PageHeader :title="t('feedback.pageTitle')" :subtitle="t('feedback.pageSubtitle')">
      <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>
    <p v-if="failure" class="card mb-4 p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-if="!loaded && !failure" class="text-sm text-stone-500">{{ t('app.loading') }}</p>

    <div v-if="loaded" class="space-y-4">
      <template v-if="leader">
        <p v-if="sample" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" data-testid="feedback-sample">
          {{ t('feedback.sampleNote') }}
        </p>
        <section class="card p-4" data-testid="feedback-summary">
          <h2 class="font-medium text-stone-900">{{ t('feedback.summary') }}</h2>
          <p v-if="!split.total" class="py-8 text-center text-sm text-stone-500">{{ t('feedback.none') }}</p>
          <template v-else>
            <div class="mt-2 flex flex-wrap gap-6">
              <div>
                <div class="text-sm text-stone-500">{{ t('feedback.average') }}</div>
                <div class="text-3xl font-semibold text-stone-900" data-testid="feedback-average">{{ average(split.total) }}<span class="text-base font-normal text-stone-500"> / 5</span></div>
              </div>
              <div>
                <div class="text-sm text-stone-500">{{ t('feedback.count') }}</div>
                <div class="text-3xl font-semibold text-stone-900">{{ split.total.feedback }}</div>
              </div>
              <div class="min-w-48 flex-1">
                <div class="text-sm text-stone-500">{{ t('feedback.distribution') }}</div>
                <div class="mt-1 space-y-0.5 text-xs">
                  <div v-for="(n, i) in ratingCounts(split.total)" :key="i" class="flex items-center gap-2">
                    <span class="w-3 text-right tabular-nums text-stone-500">{{ i + 1 }}</span>
                    <span class="h-2 rounded bg-brand-600" :style="{ width: `${split.total.feedback ? (n / split.total.feedback) * 100 : 0}%` }" />
                    <span class="tabular-nums text-stone-600">{{ n }}</span>
                  </div>
                </div>
              </div>
            </div>
            <table class="mt-4 w-full text-sm">
              <thead class="text-left text-xs text-stone-500">
                <tr>
                  <th class="py-1 font-medium">{{ t('feedback.screenColumn') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('feedback.count') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('feedback.average') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('feedback.withComment') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('feedback.last') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-stone-100">
                <tr v-for="r in split.screens" :key="r.screen ?? ''">
                  <td class="py-1 text-stone-700">{{ screenLabel(t, r.screen) }} <span class="text-xs text-stone-400">{{ r.screen }}</span></td>
                  <td class="py-1 text-right tabular-nums">{{ r.feedback }}</td>
                  <td class="py-1 text-right font-medium tabular-nums">{{ average(r) }}</td>
                  <td class="py-1 text-right tabular-nums">{{ r.with_comment }}</td>
                  <td class="py-1 text-right text-stone-500">{{ fmtDateTime(r.last_at) }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </section>

        <section class="card p-4" data-testid="feedback-recent">
          <h2 class="font-medium text-stone-900">{{ t('feedback.recent') }}</h2>
          <p class="mt-1 text-xs text-stone-500">{{ t('feedback.anonymous') }}</p>
          <p v-if="!recent.length" class="py-8 text-center text-sm text-stone-500">{{ t('feedback.none') }}</p>
          <ul v-else class="mt-2 divide-y divide-stone-100">
            <li v-for="f in recent" :key="f.id" class="py-2 text-sm">
              <div class="flex flex-wrap items-center gap-2">
                <span class="chip bg-brand-50 text-brand-800">{{ t('feedback.ratingValue', { n: f.rating }) }}</span>
                <span class="text-stone-600">{{ screenLabel(t, f.screen) }}</span>
                <span v-if="f.mine" class="chip bg-stone-100 text-stone-600">{{ t('feedback.yours') }}</span>
                <span class="ml-auto text-xs text-stone-400">{{ fmtDateTime(f.created_at) }}</span>
              </div>
              <p v-if="f.comment" class="mt-1 whitespace-pre-line text-stone-700">{{ f.comment }}</p>
            </li>
          </ul>
        </section>
      </template>

      <section class="card p-4" data-testid="feedback-mine">
        <h2 class="font-medium text-stone-900">{{ t('feedback.mine') }}</h2>
        <p class="mt-1 text-xs text-stone-500">{{ t('feedback.mineHint') }}</p>
        <p v-if="!mine.length" class="py-8 text-center text-sm text-stone-500">{{ t('feedback.noneMine') }}</p>
        <ul v-else class="mt-2 divide-y divide-stone-100">
          <li v-for="f in mine" :key="f.id" class="py-2 text-sm">
            <div class="flex flex-wrap items-center gap-2">
              <span class="chip bg-brand-50 text-brand-800">{{ t('feedback.ratingValue', { n: f.rating }) }}</span>
              <span class="text-stone-600">{{ screenLabel(t, f.screen) }}</span>
              <span class="ml-auto text-xs text-stone-400">{{ fmtDateTime(f.created_at) }}</span>
            </div>
            <p v-if="f.comment" class="mt-1 whitespace-pre-line text-stone-700">{{ f.comment }}</p>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
