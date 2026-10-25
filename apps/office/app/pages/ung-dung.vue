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
import { appCatalog, appsQuery, isAppLeader } from '~/utils/apps';


// Danh mục ứng dụng chạy trên lõi Signet: ứng dụng có sẵn trong lõi và ứng dụng cắm bằng manifest (core.app_catalog).
// Ai đăng nhập cũng xem để mở ứng dụng; lãnh đạo, quản trị đơn vị xem thêm băm manifest và ứng dụng đã gỡ — Hasura
// không cho vai trò khác đọc hai cột đó (db/metadata/.../core_app_catalog.yaml). Chỉ để xem: cài, gỡ bằng `moc app`
// trên máy chủ. Phiên bản của ứng dụng có sẵn là phiên bản lõi (GET /api/status, công khai).

const { t } = useI18n();
const { gql } = useApi();
const notice = useNotice();
const claims = useAuth().claims;

const rows = ref([]);
const coreVersion = ref(null);
const loaded = ref(false);
const loading = ref(false);
const failure = ref('');
const leader = computed(() => isAppLeader(claims.value?.role));
const groups = computed(() => appCatalog(t, rows.value, coreVersion.value));

async function loadCoreVersion() {
  try {
    const res = await fetch('/api/status', { cache: 'no-store' });
    const version = res.ok ? (await res.json()).version : null;
    coreVersion.value = typeof version === 'string' && version ? version : null;
  } catch {
    coreVersion.value = null; // không biết thì ghi "theo bản lõi"
  }
}

async function load() {
  loading.value = true;
  failure.value = '';
  try {
    const [data] = await Promise.all([
    gql(appsQuery(claims.value?.role)),
    loadCoreVersion()]
    );
    rows.value = data.core_app_catalog;
    loaded.value = true;
  } catch (e) {
    failure.value = errorText(t, e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function copy(sha256) {
  try {
    await navigator.clipboard.writeText(sha256);
    notice.ok(t('apps.copied'));
  } catch {
    // ngoài https trình duyệt không cho chép: hiện đủ 64 ký tự trong thông báo để chọn tay
    notice.info(t('apps.copyFailed'), { detail: sha256 });
  }
}

const tone = {
  builtin: 'bg-brand-50 text-brand-800',
  installed: 'bg-emerald-100 text-emerald-800',
  removed: 'bg-stone-200 text-stone-600'
};
const sections = computed(() => [
{ id: 'builtin', title: t('apps.builtinTitle'), hint: t('apps.builtinHint'), entries: groups.value.builtin },
{ id: 'installed', title: t('apps.installedTitle'), hint: t('apps.installedHint'), entries: groups.value.installed },
...(leader.value ?
[{ id: 'removed', title: t('apps.removedTitle'), hint: t('apps.removedHint'), entries: groups.value.removed }] :
[])]
);
</script>

<template>
  <div>
    <PageHeader :title="t('apps.title')" :subtitle="t('apps.subtitle')">
      <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>
    <p v-if="failure" class="card mb-4 p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-if="!loaded && !failure" class="text-sm text-stone-500">{{ t('app.loading') }}</p>

    <div v-if="loaded" class="space-y-8">
      <p
        v-if="leader" class="rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm text-stone-600"
        data-testid="apps-hash-hint"
      >
        {{ t('apps.hashHint') }}
      </p>
      <section v-for="s in sections" :key="s.id" :data-testid="`apps-${s.id}`">
        <h2 class="font-medium text-stone-900">{{ s.title }}</h2>
        <p class="mt-1 text-sm text-stone-500">{{ s.hint }}</p>
        <p v-if="!s.entries.length" class="card mt-3 p-6 text-center text-sm text-stone-500">
          {{ t(`apps.none.${s.id}`) }}
        </p>
        <ul v-else class="mt-3 grid gap-4 md:grid-cols-2">
          <li v-for="a in s.entries" :key="a.name" class="card flex flex-col p-4" :data-testid="`app-${a.name}`">
            <div class="flex items-start gap-3">
              <div class="min-w-0 flex-1">
                <h3 class="font-medium" :class="a.state === 'removed' ? 'text-stone-500' : 'text-stone-900'">
                  {{ a.title }}
                </h3>
                <p class="font-mono text-xs text-stone-400">{{ a.name }} · {{ a.path }}</p>
              </div>
              <span class="chip" :class="tone[a.state]">{{ t(`apps.state.${a.state}`) }}</span>
            </div>
            <p v-if="a.description" class="mt-2 text-sm text-stone-600">{{ a.description }}</p>
            <dl class="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt class="text-stone-500">{{ t('apps.version') }}</dt>
              <dd class="font-mono text-stone-800">{{ a.version ?? t('apps.coreVersion') }}</dd>
              <template v-if="a.installedAt">
                <dt class="text-stone-500">{{ t('apps.installedAt') }}</dt>
                <dd class="text-stone-800">{{ fmtDateTime(a.installedAt) }}</dd>
              </template>
              <template v-if="a.updatedAt">
                <dt class="text-stone-500">{{ t('apps.updatedAt') }}</dt>
                <dd class="text-stone-800">{{ fmtDateTime(a.updatedAt) }}</dd>
              </template>
              <template v-if="a.removedAt">
                <dt class="text-stone-500">{{ t('apps.removedAt') }}</dt>
                <dd class="text-stone-800">{{ fmtDateTime(a.removedAt) }}</dd>
              </template>
              <template v-if="a.sha256">
                <dt class="text-stone-500">{{ t('apps.manifestHash') }}</dt>
                <dd class="flex flex-wrap items-center gap-2">
                  <code class="font-mono text-xs text-stone-800" :title="a.sha256" data-testid="app-hash">
                    {{ shortHash(a.sha256) }}
                  </code>
                  <button
                    type="button" class="btn-ghost px-2 py-0.5 text-xs"
                    :aria-label="t('apps.copyHashOf', { app: a.title })" @click="copy(a.sha256)"
                  >
                    {{ t('apps.copy') }}
                  </button>
                </dd>
              </template>
            </dl>
            <div v-if="a.href" class="mt-auto pt-4">
              <NuxtLink v-if="a.internal" :to="a.href" class="btn-secondary" :data-testid="`open-${a.name}`">
                {{ t('apps.open') }}
              </NuxtLink>
              <a v-else :href="a.href" class="btn-primary" :data-testid="`open-${a.name}`">{{ t('apps.open') }}</a>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
