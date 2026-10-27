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
}
</script>

<template>
  <div class="moc-public flex min-h-screen flex-col">
    <!-- thanh trên như khung chính: nền trắng, kẻ --edge; tên trang công khai đứng cạnh tên sản phẩm -->
    <header class="border-b border-stone-200 bg-white">
      <div class="mx-auto flex min-h-16 w-full items-center gap-4 px-4 py-2 sm:px-6" :class="width">
        <div class="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-0.5">
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
          <div class="min-w-0 text-[13px] text-stone-600 sm:border-l sm:border-stone-200 sm:pl-4 sm:text-sm">
            {{ subtitle }}
          </div>
        </div>
        <button class="btn-ghost text-[13px]" @click="toggleLocale">{{ t('nav.language') }}</button>
      </div>
    </header>
    <main class="mx-auto w-full flex-1 px-4 py-8 sm:px-6 sm:py-10" :class="width">
      <slot />
    </main>
    <footer class="border-t border-stone-100">
      <div
        class="mx-auto flex w-full flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-5 text-[13px]
          text-stone-500 sm:px-6"
        :class="width"
      >
        <p>{{ t('verify.footer') }}</p>
        <nav class="flex flex-wrap items-center gap-x-5">
          <NuxtLink to="/xac-thuc" class="moc-public-link">{{ t('verify.title') }}</NuxtLink>
          <NuxtLink to="/trang-thai" class="moc-public-link">{{ t('health.title') }}</NuxtLink>
        </nav>
      </div>
    </footer>
  </div>
</template>
