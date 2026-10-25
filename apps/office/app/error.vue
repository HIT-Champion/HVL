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
import type { NuxtError } from '#app'
import { useI18n } from 'vue-i18n'

// Trang lỗi của cả ứng dụng (đường dẫn không có, trang lỗi lúc tải): cùng khung với trang đăng nhập, đưa về hộp việc
const props = defineProps<{ error: NuxtError }>()
const { t } = useI18n()
const missing = computed(() => Number(props.error.statusCode) === 404)
</script>

<template>
  <main class="flex min-h-screen items-center justify-center px-5 py-10">
    <section class="w-full max-w-md" aria-labelledby="error-title">
      <div class="moc-public-wordmark mb-7 justify-center">
        <img src="/brand/signet-symbol.svg" alt="" class="h-9 w-9">
        <span>{{ t('app.name') }}</span>
      </div>
      <div class="card p-7 sm:p-8">
        <h1 id="error-title" class="text-2xl font-bold">{{ t(missing ? 'pageError.notFound' : 'pageError.title') }}</h1>
        <p class="mt-3 text-sm leading-relaxed text-stone-600">
          {{ t(missing ? 'pageError.notFoundDetail' : 'pageError.detail') }}
        </p>
        <button class="btn-primary mt-6 w-full" @click="clearError({ redirect: '/' })">
          {{ t('pageError.home') }}
        </button>
        <a href="/xac-thuc" class="mt-4 block text-center text-sm text-brand-700 underline">{{ t('fe.verify') }}</a>
      </div>
    </section>
  </main>
</template>
