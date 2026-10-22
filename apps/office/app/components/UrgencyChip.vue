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
const props = defineProps<{ urgency: string; quiet?: boolean }>()
const tone: Record<string, string> = {
  khan: 'bg-amber-100 text-amber-900 ring-1 ring-amber-300',
  thuong_khan: 'bg-orange-100 text-orange-900 ring-1 ring-orange-300',
  hoa_toc: 'bg-red-100 text-red-800 ring-1 ring-red-300',
}
</script>

<template>
  <span v-if="props.urgency !== 'normal' || !props.quiet" class="chip" :class="tone[props.urgency] ?? 'bg-stone-100 text-stone-600'">
    {{ $t(`urgency.${props.urgency}`) }}
  </span>
</template>
