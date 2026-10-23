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
// Keycloak chuyển về đây sau khi đăng nhập (redirect_uri); đổi mã lấy token rồi về trang đang mở dở.
definePageMeta({ layout: false })

const auth = useAuth()
const router = useRouter()
const failed = ref(false)

onMounted(async () => {
  try {
    await router.replace(await auth.finishLogin())
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <div class="flex min-h-screen items-center justify-center p-6">
    <div class="card w-full max-w-sm p-8 text-center">
      <img src="/favicon.svg" alt="" class="mx-auto mb-4 h-12 w-12">
      <h1 class="text-xl font-semibold text-brand-800">{{ $t('app.name') }}</h1>
      <p class="mt-1 text-sm text-stone-500">{{ $t('app.tagline') }}</p>
      <p v-if="!failed" class="mt-6 text-sm text-stone-600">{{ $t('app.loading') }}</p>
      <button v-else class="btn-primary mt-6 w-full" @click="auth.login('/')">{{ $t('app.retry') }}</button>
    </div>
  </div>
</template>
