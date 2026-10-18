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
definePageMeta({
    layout: 'public'
});
const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const code = ref(String(route.params.code ?? ''));
const result = ref(null);
const found = ref(null);
const match = ref(null);
const fileName = ref('');
const checking = ref(false);
const failure = ref('');
const dragging = ref(false);
const readableCode = computed(()=>found.value ? `${found.value.verify_code.slice(0, 5)}-${found.value.verify_code.slice(5)}` : '');
async function call(url) {
    const res = await fetch(url, {
        cache: 'no-store'
    });
    if (res.status === 429) throw new Error(t('verify.rateLimited'));
    if (!res.ok) throw new Error(t('error.generic', {
        msg: `HTTP ${res.status}`
    }));
    return res.json();
}
async function run(job) {
    checking.value = true;
    failure.value = '';
    try {
        await job();
    } catch (e) {
        failure.value = e instanceof Error ? e.message : String(e);
    } finally{
        checking.value = false;
    }
}
function lookup(value) {
    return run(async ()=>{
        const body = await call(`/api/verify/${encodeURIComponent(value)}`);
        result.value = body.result;
        found.value = body.document;
        match.value = null;
        fileName.value = '';
    });
}
function submitCode() {
    const value = code.value.trim();
    if (!value) return;
    router.replace(`/xac-thuc/${encodeURIComponent(value)}`);
    lookup(value);
}
async function digest(file) {
    const hash = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
    return Array.from(new Uint8Array(hash), (b)=>b.toString(16).padStart(2, '0')).join('');
}
function onFile(file) {
    if (!file) return;
    if (!window.crypto?.subtle) {
        failure.value = t('verify.noCrypto');
        return;
    }
    run(async ()=>{
        const hash = await digest(file);
        fileName.value = file.name;
        if (found.value) {
            match.value = hash === found.value.sha256;
            return;
        }
        const body = await call(`/api/verify?sha256=${hash}`);
        result.value = body.result;
        found.value = body.document;
        match.value = body.result === 'valid' ? true : null;
    });
}
function onDrop(e) {
    dragging.value = false;
    onFile(e.dataTransfer?.files?.[0]);
}
onMounted(()=>{
    if (code.value) lookup(code.value);
});
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-2xl font-semibold tracking-tight text-stone-900">{{ t('verify.title') }}</h1>
      <p class="mt-1 text-sm text-stone-500">{{ t('verify.subtitle') }}</p>
    </div>

    <form class="card flex flex-wrap items-end gap-3 p-5" @submit.prevent="submitCode">
      <div class="min-w-48 flex-1">
        <label class="label" for="verify-code">{{ t('verify.code') }}</label>
        <input id="verify-code" v-model="code" class="input font-mono tracking-wider uppercase" maxlength="40" autocomplete="off"
               :placeholder="t('verify.codeHint')">
      </div>
      <button type="submit" class="btn-primary" :disabled="checking || !code.trim()">{{ t('verify.lookup') }}</button>
    </form>

    <p v-if="checking" class="text-sm text-stone-500">{{ t('verify.checking') }}</p>
    <p v-if="failure" class="card p-4 text-sm text-red-700">{{ failure }}</p>

    <!-- kết quả -->
    <section v-if="result === 'valid' && found" class="card overflow-hidden" data-testid="verify-valid">
      <div class="flex items-center gap-3 border-b border-emerald-100 bg-emerald-50 px-5 py-3 text-emerald-900">
        <svg class="h-6 w-6 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        <span class="font-semibold">{{ t('verify.valid') }}</span>
      </div>
      <dl class="grid gap-x-6 gap-y-3 p-5 text-sm sm:grid-cols-2">
        <div><dt class="text-stone-500">{{ t('verify.symbol') }}</dt><dd class="font-medium">{{ found.symbol }}</dd></div>
        <div><dt class="text-stone-500">{{ t('verify.issuedOn') }}</dt><dd class="font-medium">{{ fmtDate(found.issued_on) }}</dd></div>
        <div><dt class="text-stone-500">{{ t('verify.type') }}</dt><dd class="font-medium">{{ found.type_name }}</dd></div>
        <div>
          <dt class="text-stone-500">{{ t('verify.issuer') }}</dt>
          <dd class="font-medium">{{ found.issuer_name }}<span v-if="found.parent_name" class="block text-xs font-normal text-stone-500">{{ found.parent_name }}</span></dd>
        </div>
        <div class="sm:col-span-2">
          <dt class="text-stone-500">{{ t('verify.summary') }}</dt>
          <dd :class="found.summary ? 'font-medium' : 'text-stone-400'">{{ found.summary ?? t('verify.summaryHidden') }}</dd>
        </div>
        <div><dt class="text-stone-500">{{ t('verify.code') }}</dt><dd class="font-mono font-semibold tracking-wider">{{ readableCode }}</dd></div>
        <div class="sm:col-span-2"><dt class="text-stone-500">{{ t('verify.sha256') }}</dt><dd class="font-mono text-xs break-all text-stone-700">{{ found.sha256 }}</dd></div>
      </dl>
      <!-- chữ ký số PAdES (F4.5, chỉ minh họa): luôn kèm câu nói rõ không có giá trị pháp lý -->
      <div v-if="found.signature" class="mx-5 mb-5 rounded-md border border-stone-200 p-4" data-testid="verify-signature">
        <h2 class="flex items-center gap-2 text-sm font-semibold text-stone-900">
          <svg class="h-4 w-4 shrink-0 text-stone-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zM19.5 7.125L16.862 4.487" /></svg>
          {{ t('verify.signature.title') }}
        </h2>
        <dl class="mt-3 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div><dt class="text-stone-500">{{ t('verify.signature.level') }}</dt><dd class="font-medium">{{ found.signature.level }}</dd></div>
          <div><dt class="text-stone-500">{{ t('verify.signature.signedAt') }}</dt><dd class="font-medium">{{ fmtDateTime(found.signature.signed_at) }}</dd></div>
          <div><dt class="text-stone-500">{{ t('verify.signature.signer') }}</dt><dd class="font-medium">{{ found.signature.signer }}</dd></div>
          <div><dt class="text-stone-500">{{ t('verify.signature.ca') }}</dt><dd class="font-medium">{{ found.signature.ca }}</dd></div>
          <div class="sm:col-span-2"><dt class="text-stone-500">{{ t('verify.signature.serial') }}</dt><dd class="font-mono text-xs break-all text-stone-700">{{ found.signature.serial }}</dd></div>
        </dl>
        <p class="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">{{ t('verify.signature.illustrative') }}</p>
      </div>
      <p v-else class="mx-5 mb-5 text-xs text-stone-500" data-testid="verify-unsigned">{{ t('verify.signature.none') }}</p>
      <div v-if="match !== null" class="mx-5 mb-5 rounded-md px-4 py-3 text-sm font-medium" data-testid="verify-match"
           :class="match ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'">
        {{ match ? t('verify.match') : t('verify.mismatch') }}<span v-if="fileName" class="block text-xs font-normal opacity-90">{{ fileName }}</span>
      </div>
    </section>

    <section v-else-if="result === 'not_found'" class="card border-amber-200 bg-amber-50 p-5 text-amber-900" data-testid="verify-not-found">
      <div class="font-semibold">{{ t('verify.notFound') }}</div>
      <p class="mt-1 text-sm">{{ t('verify.notFoundHint') }}</p>
      <p v-if="fileName" class="mt-1 text-xs opacity-80">{{ fileName }}</p>
    </section>

    <!-- thả tệp: tra theo băm, hoặc so với văn bản vừa tra -->
    <label
      class="card flex cursor-pointer flex-col items-center gap-2 border-2 border-dashed p-8 text-center text-sm text-stone-600"
      :class="dragging ? 'border-brand-600 bg-brand-50' : 'border-stone-300'"
      @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop"
    >
      <input id="verify-file" type="file" accept="application/pdf,.pdf" class="sr-only"
             @change="onFile(($event.target ).files?.[0])">
      <svg class="h-8 w-8 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
      <span class="font-medium text-stone-800">{{ found ? t('verify.compare') : t('verify.file') }}</span>
      <span class="text-xs text-stone-500">{{ t('verify.fileHint') }}</span>
    </label>
  </div>
</template>
