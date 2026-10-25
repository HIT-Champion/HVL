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
// Keycloak chuyển về đây sau khi đăng nhập (redirect_uri); đổi mã lấy token rồi về trang đang mở dở.
definePageMeta({
  layout: false
});
const auth = useAuth();
const router = useRouter();
const failed = ref(false);
onMounted(async () => {
  try {
    await router.replace(await auth.finishLogin());
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <main class="flex min-h-screen items-center justify-center px-5 py-10">
    <section class="w-full max-w-md" aria-labelledby="callback-title">
      <div class="moc-public-wordmark mb-7 justify-center"><img src="/brand/signet-symbol.svg" alt="" class="h-9 w-9"><span>{{ $t('app.name') }}</span></div>
      <div class="card p-7 sm:p-8" aria-live="polite">
        <h1 id="callback-title" class="text-2xl font-bold">{{ $t(failed ? 'authCallback.failed' : 'authCallback.title') }}</h1>
        <p class="mt-3 text-sm leading-relaxed text-stone-600">{{ $t(failed ? 'authCallback.retryDetail' : 'authCallback.detail') }}</p>
        <button v-if="failed" class="btn-primary mt-6 w-full" @click="auth.login('/')">{{ $t('app.retry') }}</button>
        <NuxtLink to="/trang-thai" v-if="failed" class="mt-4 block text-center text-sm text-brand-700 underline">{{ $t('health.title') }}</NuxtLink>
      </div>
    </section>
  </main>
</template>
