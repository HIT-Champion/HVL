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
import { citeLabel, segments, sourceAnchor } from '~/utils/answer';
const props = defineProps({
    text: {
        type: String,
        required: true
    },
    sources: {
        type: Array,
        required: true
    },
    ask: {
        type: String,
        required: true
    }
});
const { t } = useI18n();
const parts = computed(()=>segments(props.text, props.sources));
function jump(e, n) {
    const el = document.getElementById(sourceAnchor(props.ask, n));
    if (!el) return;
    e.preventDefault();
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({
        behavior: reduce ? 'auto' : 'smooth',
        block: 'nearest'
    });
    el.focus({
        preventScroll: true
    });
}
</script>

<template>
  <p class="leading-relaxed break-words whitespace-pre-line text-stone-900"><template v-for="(part, i) in parts" :key="i"><a v-if="'n' in part" :href="`#${sourceAnchor(ask, part.n)}`" class="mx-0.5 rounded px-0.5 align-baseline text-sm font-semibold text-brand-700 underline decoration-brand-300 underline-offset-2 hover:bg-brand-50 hover:decoration-brand-700 focus-visible:outline-2 focus-visible:outline-brand-700" :aria-label="t('assist.source.cite', { n: part.n, label: citeLabel(part.source, t, true) })" :title="citeLabel(part.source, t)" @click="jump($event, part.n)">[{{ part.n }}]</a><template v-else>{{ part.text }}</template></template></p>
</template>
