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
import { NuxtLink } from '#components';
const {
  notices
} = useNotice();
</script>

<template>
  <div class="pointer-events-none fixed right-4 bottom-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
    <component
      :is="n.to ? NuxtLink : 'div'"
      v-for="n in notices" :key="n.id" :to="n.to"
      class="pointer-events-auto block rounded-lg px-4 py-3 text-sm shadow-lg"
      :class="n.kind === 'ok' ? 'bg-brand-800 text-white' : n.kind === 'info' ? 'bg-white text-stone-900 ring-1 ring-stone-200 hover:ring-brand-600' : 'bg-red-600 text-white'"
      :role="n.kind === 'error' ? 'alert' : 'status'"
      :data-testid="n.kind === 'info' ? 'realtime-notice' : undefined"
    >
      <div :class="{ 'font-medium': n.kind === 'info' }">{{ n.text }}</div>
      <div v-if="n.detail" class="mt-0.5 truncate text-stone-500">{{ n.detail }}</div>
    </component>
  </div>
</template>
