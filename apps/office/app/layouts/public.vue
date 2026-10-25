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

// Khung của trang công khai (cổng xác thực văn bản, trạng thái hệ thống): không cần đăng nhập, không gọi API nào cần
// token. Trang đặt tiêu đề phụ ở đầu khung bằng `publicTitle` (khóa i18n) và xin khung rộng hơn bằng `wide` trong
// definePageMeta; chân trang nối các trang công khai với nhau.
const { t, locale } = useI18n()
const route = useRoute()
const subtitle = computed(() => t(String(route.meta.publicTitle ?? 'verify.title')))
const width = computed(() => (route.meta.wide ? 'max-w-6xl' : 'max-w-3xl'))

function toggleLocale() {
  locale.value = locale.value === 'vi' ? 'en' : 'vi'
  try { localStorage.setItem('moc.locale', locale.value) } catch { /* bỏ qua */ }
  document.documentElement.lang = locale.value
}
</script>

<template>
  <div class="moc-public flex min-h-screen flex-col">
    <header class="border-b border-stone-200">
      <div class="mx-auto flex h-16 w-full items-center gap-3 px-4" :class="width">
        <div class="flex-1">
          <div class="moc-public-wordmark text-brand-800">
            <svg
              class="sg-brand-mark" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="9"
              stroke-linecap="round" aria-hidden="true"
            >
              <path d="M45 10H26c-9 0-16 7-16 16s7 16 16 16h12" />
              <path d="M19 54h19c9 0 16-7 16-16s-7-16-16-16H26" />
            </svg>
            <span>{{ t('app.name') }}</span>
          </div>
          <div class="text-xs text-stone-500">{{ subtitle }}</div>
        </div>
        <button class="btn-ghost text-xs" @click="toggleLocale">{{ t('nav.language') }}</button>
      </div>
    </header>
    <main class="mx-auto w-full flex-1 px-4 py-8" :class="width">
      <slot />
    </main>
    <footer class="space-y-1 py-6 text-center text-xs text-stone-500">
      <div>{{ t('verify.footer') }}</div>
      <nav class="flex justify-center gap-3">
        <NuxtLink to="/xac-thuc" class="hover:text-brand-700 hover:underline">{{ t('verify.title') }}</NuxtLink>
        <span aria-hidden="true">·</span>
        <NuxtLink to="/trang-thai" class="hover:text-brand-700 hover:underline">{{ t('health.title') }}</NuxtLink>
      </nav>
    </footer>
  </div>
</template>
