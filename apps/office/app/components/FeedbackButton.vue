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

// Góp ý (F4.6) trên thanh trên, ở mọi trang sau đăng nhập: mức hài lòng 1–5, vài dòng không bắt buộc; màn hình đang
// dùng tự gắn dưới dạng khuôn đường dẫn (app/utils/feedback.ts). Thuê ước, người gửi, giờ gửi do Hasura và CSDL đặt;
// CSDL chặn gửi dồn và báo lỗi feedback_rate (app/utils/errors.ts dịch thành câu).
const { t } = useI18n();
const { gql } = useApi();
const notice = useNotice();
const route = useRoute();
const open = ref(false);
const rating = ref(null);
const comment = ref('');
const sending = ref(false);
const failure = ref('');
const root = ref(null);
const screen = computed(() => feedbackScreen(route.path));

const SEND = `mutation ($r: Int!, $c: String, $s: String!) {
  insert_office_feedback_one(object: {rating: $r, comment: $c, screen: $s}) { id }
}`;

function outside(e) {
  if (open.value && root.value && !root.value.contains(e.target)) open.value = false;
}
onMounted(() => document.addEventListener('click', outside));
onBeforeUnmount(() => document.removeEventListener('click', outside));
watch(() => route.fullPath, () => {open.value = false;});

async function send() {
  if (!rating.value || sending.value) return;
  sending.value = true;
  failure.value = '';
  try {
    await gql(SEND, { r: rating.value, c: comment.value.trim() || null, s: screen.value });
    notice.ok(t('feedback.sent'));
    open.value = false;
    rating.value = null;
    comment.value = '';
  } catch (e) {
    failure.value = errorText(t, e);
  } finally {
    sending.value = false;
  }
}
</script>

<template>
  <div ref="root" class="relative" @keydown.esc.stop="open = false">
    <button class="btn-ghost text-xs" type="button" :aria-label="t('feedback.button')" :aria-expanded="open" data-testid="feedback-open" @click="open = !open">
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 10h8M8 14h5M21 12a9 9 0 01-13.2 8L3 21l1.1-4.6A9 9 0 1121 12z" /></svg><span class="hidden sm:inline">{{ t('feedback.button') }}</span>
    </button>
    <form
      v-if="open" class="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-stone-200 bg-white p-4 shadow-xl"
      :aria-label="t('feedback.title')" data-testid="feedback-form" @submit.prevent="send"
    >
      <div class="font-semibold text-stone-900">{{ t('feedback.title') }}</div>
      <p class="mt-1 text-xs text-stone-500" data-testid="feedback-screen">{{ t('feedback.screen', { screen: screenLabel(t, screen) }) }}</p>
      <fieldset class="mt-3">
        <legend class="label">{{ t('feedback.rating') }}</legend>
        <div class="flex gap-1">
          <button
            v-for="n in FEEDBACK_RATINGS" :key="n" type="button" class="btn flex-1 border"
            :class="rating === n ? 'border-brand-700 bg-brand-700 text-white' : 'border-stone-300 bg-white text-stone-700 hover:bg-stone-100'"
            :aria-pressed="rating === n" :aria-label="t('feedback.ratingValue', { n })" @click="rating = n"
          >{{ n }}</button>
        </div>
        <div class="mt-1 flex justify-between text-[11px] text-stone-400"><span>{{ t('feedback.low') }}</span><span>{{ t('feedback.high') }}</span></div>
      </fieldset>
      <label class="label mt-3" for="feedback-comment">
        {{ t('feedback.comment') }} <span class="font-normal text-stone-400">({{ t('app.optional') }})</span>
      </label>
      <textarea
        id="feedback-comment" v-model="comment" class="input" rows="3" :maxlength="FEEDBACK_MAX"
        :placeholder="t('feedback.placeholder')"
      />
      <div class="mt-1 flex justify-between gap-2 text-xs text-stone-500">
        <span>{{ t('feedback.privacy') }}</span><span class="tabular-nums">{{ comment.length }}/{{ FEEDBACK_MAX }}</span>
      </div>
      <p v-if="failure" class="mt-2 text-sm text-red-700" role="alert">{{ failure }}</p>
      <div class="mt-3 flex items-center justify-between gap-2">
        <NuxtLink to="/gop-y" class="text-xs text-brand-700 hover:underline">{{ t('feedback.mineLink') }}</NuxtLink>
        <button class="btn-primary" type="submit" :disabled="!rating || sending" data-testid="feedback-send">
          {{ t('feedback.send') }}
        </button>
      </div>
    </form>
  </div>
</template>
