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

// Khung của trang công khai (cổng xác thực văn bản): không cần đăng nhập, không gọi API nào cần token.
const { t, locale } = useI18n()

function toggleLocale() {
  locale.value = locale.value === 'vi' ? 'en' : 'vi'
  try { localStorage.setItem('moc.locale', locale.value) } catch { /* bỏ qua */ }
  document.documentElement.lang = locale.value
}
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <header class="border-b border-stone-200 bg-white">
      <div class="mx-auto flex h-16 w-full max-w-3xl items-center gap-3 px-4">
        <img src="/favicon.svg" alt="" class="h-8 w-8">
        <div class="flex-1">
          <div class="text-lg leading-none font-semibold text-brand-800">{{ t('app.name') }}</div>
          <div class="text-xs text-stone-500">{{ t('verify.title') }}</div>
        </div>
        <button class="btn-ghost text-xs" @click="toggleLocale">{{ t('nav.language') }}</button>
      </div>
    </header>
    <main class="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
      <slot />
    </main>
    <footer class="py-6 text-center text-xs text-stone-500">{{ t('verify.footer') }}</footer>
  </div>
</template>
