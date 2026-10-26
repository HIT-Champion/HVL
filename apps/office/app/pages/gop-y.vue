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
import type { FeedbackRow, FeedbackSummaryRow } from '~/utils/feedback'

// Góp ý (F4.6): ai cũng xem lại góp ý mình đã gửi (trường `mine`). Lãnh đạo, quản trị đơn vị xem thêm tổng hợp của đơn
// vị — điểm trung bình, số góp ý theo màn hình (office.v_feedback_summary) — và các góp ý gần đây, không có người gửi:
// Hasura không cho hai vai trò này đọc cột user_id (db/metadata/.../office_feedback.yaml). Gửi góp ý ở nút trên thanh
// trên (components/FeedbackButton.vue).

const MINE = `{ office_feedback(where: {mine: {_eq: true}}, order_by: {created_at: desc}, limit: 50) {
  id rating comment screen created_at mine } }`
const UNIT = `{
  office_v_feedback_summary { sample screen feedback rating_total rating_1 rating_2 rating_3 rating_4 rating_5
    with_comment last_at }
  office_feedback(order_by: {created_at: desc}, limit: 50) { id rating comment screen created_at mine }
}`

const { t, locale } = useI18n()
const { gql } = useApi()
const claims = useAuth().claims

const mine = ref<FeedbackRow[]>([])
const summary = ref<FeedbackSummaryRow[]>([])
const recent = ref<FeedbackRow[]>([])
const loaded = ref(false)
const loading = ref(false)
const failure = ref('')
const leader = computed(() => claims.value?.role === 'director' || claims.value?.role === 'tenant_admin')

async function load() {
  loading.value = true
  failure.value = ''
  try {
    mine.value = (await gql<{ office_feedback: FeedbackRow[] }>(MINE)).office_feedback
    if (leader.value) {
      const data = await gql<{ office_v_feedback_summary: FeedbackSummaryRow[]; office_feedback: FeedbackRow[] }>(UNIT)
      summary.value = data.office_v_feedback_summary
      recent.value = data.office_feedback
    }
    loaded.value = true
  } catch (e) {
    failure.value = errorText(t, e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const number = computed(() => new Intl.NumberFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB', { maximumFractionDigits: 1 }))
const split = computed(() => splitSummary(summary.value))
const sample = computed(() => isSample(summary.value))
function average(row: FeedbackSummaryRow | null) {
  const avg = averageRating(row)
  return avg === null ? '—' : number.value.format(avg)
}
</script>

<template>
  <div>
    <PageHeader :title="t('feedback.pageTitle')" :subtitle="t('feedback.pageSubtitle')">
      <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>
    <p v-if="failure" class="moc-state mb-6">{{ failure }}</p>
    <p v-if="!loaded && !failure" class="moc-loading">{{ t('app.loading') }}</p>

    <!-- chữ góp ý, đường dẫn màn hình là chữ người dùng gõ: chuỗi dài không dấu cách phải xuống dòng (wrap-anywhere),
         không đẩy trang cuộn ngang -->
    <div v-if="loaded" class="moc-stack">
      <template v-if="leader">
        <p v-if="sample" class="moc-note" data-testid="feedback-sample">
          {{ t('feedback.sampleNote') }}
        </p>
        <section class="moc-block" data-testid="feedback-summary">
          <h2 class="moc-block-title">{{ t('feedback.summary') }}</h2>
          <p v-if="!split.total" class="moc-empty">{{ t('feedback.none') }}</p>
          <template v-else>
            <div class="mt-3 flex flex-wrap gap-x-10 gap-y-4">
              <div>
                <div class="text-[13px] text-stone-500">{{ t('feedback.average') }}</div>
                <div
                  class="text-[28px] leading-9 font-semibold text-stone-900 tabular-nums" data-testid="feedback-average"
                >{{ average(split.total) }}<span class="text-base font-normal text-stone-500"> / 5</span></div>
              </div>
              <div>
                <div class="text-[13px] text-stone-500">{{ t('feedback.count') }}</div>
                <div class="text-[28px] leading-9 font-semibold text-stone-900 tabular-nums">
                  {{ split.total.feedback }}
                </div>
              </div>
              <div class="min-w-0 flex-1 basis-56">
                <div class="text-[13px] text-stone-500">{{ t('feedback.distribution') }}</div>
                <div class="mt-1.5 max-w-md space-y-1 text-[13px]">
                  <div
                    v-for="(n, i) in ratingCounts(split.total)" :key="i"
                    class="grid grid-cols-[1rem_minmax(0,1fr)_2.5rem] items-center gap-2"
                  >
                    <span class="text-right text-stone-500 tabular-nums">{{ i + 1 }}</span>
                    <span class="h-2 rounded-full bg-stone-100">
                      <span
                        class="block h-2 rounded-full bg-brand-600"
                        :style="{ width: `${split.total.feedback ? (n / split.total.feedback) * 100 : 0}%` }"
                      />
                    </span>
                    <span class="text-stone-600 tabular-nums">{{ n }}</span>
                  </div>
                </div>
              </div>
            </div>
            <table class="moc-table mt-5">
              <thead>
                <tr>
                  <th>{{ t('feedback.screenColumn') }}</th>
                  <th class="text-right">{{ t('feedback.count') }}</th>
                  <th class="text-right">{{ t('feedback.average') }}</th>
                  <th class="text-right">{{ t('feedback.withComment') }}</th>
                  <th class="text-right">{{ t('feedback.last') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in split.screens" :key="r.screen ?? ''">
                  <td class="text-stone-800 wrap-anywhere">
                    {{ screenLabel(t, r.screen) }}
                    <span class="block font-mono text-xs text-stone-500">{{ r.screen }}</span>
                  </td>
                  <td class="text-right">{{ r.feedback }}</td>
                  <td class="text-right font-medium">{{ average(r) }}</td>
                  <td class="text-right">{{ r.with_comment }}</td>
                  <td class="text-right text-stone-600">{{ fmtDateTime(r.last_at) }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </section>

        <section class="moc-block" data-testid="feedback-recent">
          <h2 class="moc-block-title">{{ t('feedback.recent') }}</h2>
          <p class="moc-block-hint">{{ t('feedback.anonymous') }}</p>
          <p v-if="!recent.length" class="moc-empty">{{ t('feedback.none') }}</p>
          <ul v-else class="moc-rows mt-4">
            <li v-for="f in recent" :key="f.id" class="text-sm">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span class="chip bg-brand-50 text-brand-800">{{ t('feedback.ratingValue', { n: f.rating }) }}</span>
                <span class="min-w-0 text-stone-700 wrap-anywhere">{{ screenLabel(t, f.screen) }}</span>
                <span v-if="f.mine" class="chip bg-stone-100 text-stone-700">{{ t('feedback.yours') }}</span>
                <span class="ml-auto text-[13px] text-stone-500 tabular-nums">{{ fmtDateTime(f.created_at) }}</span>
              </div>
              <p v-if="f.comment" class="mt-1.5 whitespace-pre-line text-stone-800 wrap-anywhere">{{ f.comment }}</p>
            </li>
          </ul>
        </section>
      </template>

      <section class="moc-block" data-testid="feedback-mine">
        <h2 class="moc-block-title">{{ t('feedback.mine') }}</h2>
        <p class="moc-block-hint">{{ t('feedback.mineHint') }}</p>
        <p v-if="!mine.length" class="moc-empty">{{ t('feedback.noneMine') }}</p>
        <ul v-else class="moc-rows mt-4">
          <li v-for="f in mine" :key="f.id" class="text-sm">
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span class="chip bg-brand-50 text-brand-800">{{ t('feedback.ratingValue', { n: f.rating }) }}</span>
              <span class="min-w-0 text-stone-700 wrap-anywhere">{{ screenLabel(t, f.screen) }}</span>
              <span class="ml-auto text-[13px] text-stone-500 tabular-nums">{{ fmtDateTime(f.created_at) }}</span>
            </div>
            <p v-if="f.comment" class="mt-1.5 whitespace-pre-line text-stone-800 wrap-anywhere">{{ f.comment }}</p>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
