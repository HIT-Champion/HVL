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
const { t } = useI18n();
const { gql, readArchive } = useApi();
const notice = useNotice();
const role = useAuth().claims;
const canEdit = computed(() => ['staff', 'manager'].includes(role.value?.role));
const allowed = computed(() => role.value?.role !== 'tenant_admin');
const cases = ref([]);
const documents = ref([]);
const selectedId = ref('');
const selected = computed(() => visible.value.find(row => row.id === selectedId.value) ?? visible.value[0] ?? null);
const loading = ref(false);
const busy = ref(false);
const failure = ref('');
const query = ref('');
const visible = computed(() => cases.value.filter(row => `${row.code} ${row.title}`.toLocaleLowerCase().includes(query.value.toLocaleLowerCase())));
const showCreate = ref(false);
const form = reactive({ year: Number(today().slice(0, 4)), code: '', title: '', retention: 5 });
const documentId = ref('');
const archive = ref(null);
const reading = ref(false);
const archiveError = ref('');
let readVersion = 0;
watch(() => selected.value?.id, () => { archive.value = null; archiveError.value = ''; documentId.value = ''; readVersion++; reading.value = false; });
const available = computed(() => documents.value.filter(doc => !cases.value.some(row => row.case_file_documents.some(link => link.document_id === doc.id))));
async function load() {
  loading.value = true;
  failure.value = '';
  try {
    const result = await gql(`{
      office_case_files(order_by: [{year: desc}, {created_at: desc}], limit: 200) {
        id code title year retention_years status closed_on archived_at department { name }
        case_file_documents { document_id document { id symbol summary status } }
      }
      office_documents(where: {status: {_in: ["done", "issued"]}, restricted: {_eq: false}}, order_by: {updated_at: desc}, limit: 200) { id symbol summary }
    }`);
    cases.value = result.office_case_files;
    documents.value = result.office_documents;
  } catch (error) { failure.value = errorText(t, error); }
  finally { loading.value = false; }
}
onMounted(() => { if (allowed.value) load(); });
async function mutate(queryText, variables) {
  busy.value = true;
  try { await gql(queryText, variables); await load(); return true; }
  catch (error) { notice.error(errorText(t, error)); return false; }
  finally { busy.value = false; }
}
async function create() {
  if (!form.code.trim() || form.title.trim().length < 5 || form.title.trim().length > 500 || !Number.isInteger(form.year) || form.year < 2000 || form.year > 2999 || (form.retention !== '' && (!Number.isInteger(Number(form.retention)) || Number(form.retention) < 1 || Number(form.retention) > 100))) {
    notice.error(t('cases.invalid')); return;
  }
  const ok = await mutate('mutation ($o: office_case_files_insert_input!) { insert_office_case_files_one(object: $o) { id } }', { o: { year: form.year, code: form.code.trim(), title: form.title.trim(), retention_years: form.retention === '' ? null : Number(form.retention) } });
  if (ok) { showCreate.value = false; selectedId.value = cases.value.find(row => row.code === form.code.trim() && row.year === form.year)?.id ?? ''; form.code = ''; form.title = ''; notice.ok(t('cases.created')); }
}
async function addDocument() {
  if (!selected.value || !documentId.value) return;
  const ok = await mutate('mutation ($c: uuid!, $d: uuid!) { insert_office_case_file_documents_one(object: {case_file_id: $c, document_id: $d}) { document_id } }', { c: selected.value.id, d: documentId.value });
  if (ok) documentId.value = '';
}
async function removeDocument(id) {
  if (!selected.value || !confirm(t('cases.removeConfirm'))) return;
  await mutate('mutation ($c: uuid!, $d: uuid!) { delete_office_case_file_documents_by_pk(case_file_id: $c, document_id: $d) { document_id } }', { c: selected.value.id, d: id });
}
async function closeCase() {
  if (!selected.value || !confirm(t('cases.closeConfirm', { code: selected.value.code }))) return;
  await mutate('mutation ($id: uuid!) { update_office_case_files_by_pk(pk_columns: {id: $id}, _set: {status: "closed"}) { id status } }', { id: selected.value.id });
}
async function read() {
  const id = selected.value?.id;
  if (!id) return;
  const version = ++readVersion;
  reading.value = true;
  archiveError.value = '';
  try { const result = await readArchive(id); if (version === readVersion) archive.value = result; }
  catch (error) { if (version === readVersion) archiveError.value = errorText(t, error); }
  finally { if (version === readVersion) reading.value = false; }
}
</script>

<template>
  <div>
    <PageHeader :title="t('cases.title')" :subtitle="t('cases.subtitle')">
      <button v-if="canEdit" class="btn-primary" @click="showCreate = !showCreate">{{ t('cases.create') }}</button>
      <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
    </PageHeader>
    <p v-if="!allowed" class="moc-state">{{ t('error.noRole') }}</p>
    <form v-if="canEdit && showCreate" class="card mb-6 grid gap-4 p-5 sm:grid-cols-2" @submit.prevent="create">
      <div><label for="case-code" class="label">{{ t('cases.code') }}</label><input id="case-code" v-model="form.code" class="input" required maxlength="100"></div>
      <div><label for="case-year" class="label">{{ t('cases.year') }}</label><input id="case-year" v-model.number="form.year" class="input" type="number" min="2000" max="2999" required></div>
      <div class="sm:col-span-2"><label for="case-title" class="label">{{ t('cases.name') }}</label><input id="case-title" v-model="form.title" class="input" required minlength="5" maxlength="500"></div>
      <div><label for="case-retention" class="label">{{ t('cases.retention') }}</label><input id="case-retention" v-model="form.retention" class="input" type="number" min="1" max="100"><p class="mt-2 text-xs text-stone-500">{{ t('cases.permanentHint') }}</p></div>
      <div class="flex items-end justify-end gap-2"><button type="button" class="btn-secondary" @click="showCreate = false">{{ t('app.cancel') }}</button><button class="btn-primary" :disabled="busy">{{ t('app.save') }}</button></div>
    </form>
    <div v-if="failure" class="moc-state" role="alert">{{ failure }}<button class="btn-secondary" @click="load">{{ t('app.retry') }}</button></div>
    <div v-if="loading && !cases.length" aria-busy="true"><div v-for="n in 3" :key="n" class="moc-skeleton" /></div>
    <template v-else-if="allowed && !failure">
      <div class="moc-toolbar"><input v-model="query" class="input" type="search" :aria-label="t('cases.search')" :placeholder="t('cases.search')"><span class="moc-count">{{ t('cases.count', { n: visible.length }) }}</span></div>
      <p v-if="!visible.length" class="moc-empty">{{ t('cases.empty') }}</p>
      <div v-else class="grid items-start gap-6 lg:grid-cols-[minmax(230px,0.75fr)_minmax(0,1.25fr)]">
        <ul><li v-for="row in visible" :key="row.id"><button class="moc-task" :class="{ 'is-selected': selected?.id === row.id }" :aria-pressed="selected?.id === row.id" @click="selectedId = row.id"><span class="text-xs text-stone-500">{{ row.code }} · {{ row.year }}</span><h2>{{ row.title }}</h2><p>{{ t('cases.status.' + row.status) }} · {{ row.department?.name }}</p></button></li></ul>
        <section v-if="selected" class="card p-5" data-testid="case-detail">
          <div class="flex items-center justify-between gap-3"><span class="text-xs text-stone-500">{{ selected.code }}</span><span class="chip bg-brand-50 text-brand-800">{{ t('cases.status.' + selected.status) }}</span></div>
          <h2 class="mt-3 text-xl font-medium">{{ selected.title }}</h2>
          <p class="mt-2 text-sm text-stone-500">{{ selected.retention_years === null ? t('cases.permanent') : t('cases.years', { n: selected.retention_years }) }}</p>
          <ul class="mt-5 divide-y divide-stone-100">
            <li v-for="link in selected.case_file_documents" :key="link.document_id" class="flex items-start justify-between gap-3 py-3"><NuxtLink v-if="link.document" :to="'/van-ban/' + link.document_id" class="text-sm hover:underline"><span class="block text-xs text-stone-500">{{ link.document.symbol || '—' }}</span>{{ link.document.summary }}</NuxtLink><span v-else class="text-sm text-stone-500">{{ t('cases.hidden') }}</span><button v-if="canEdit && selected.status === 'open'" class="btn-ghost text-xs" :disabled="busy" @click="removeDocument(link.document_id)">{{ t('cases.remove') }}</button></li>
          </ul>
          <p v-if="!selected.case_file_documents.length" class="mt-4 text-sm text-stone-500">{{ t('cases.noDocuments') }}</p>
          <form v-if="canEdit && selected.status === 'open'" class="mt-5 space-y-3 border-t border-stone-200 pt-5" @submit.prevent="addDocument">
            <label for="case-document" class="label">{{ t('cases.add') }}</label><select id="case-document" v-model="documentId" class="input"><option value="">{{ t('form.pick') }}</option><option v-for="doc in available" :key="doc.id" :value="doc.id">{{ doc.symbol || '—' }} · {{ doc.summary }}</option></select>
            <p class="text-xs text-stone-500">{{ t('cases.addHint') }}</p>
            <div class="flex flex-wrap justify-between gap-2"><button class="btn-secondary" :disabled="busy || !documentId">{{ t('cases.add') }}</button><button type="button" class="btn-primary" :disabled="busy || !selected.case_file_documents.length" @click="closeCase">{{ t('cases.close') }}</button></div>
          </form>
          <p v-if="selected.status === 'closed'" class="mt-5 text-sm text-stone-500">{{ t('cases.pendingArchive', { at: fmtDate(selected.closed_on) }) }}</p>
          <button v-if="selected.status === 'archived'" class="btn-primary mt-5" :disabled="reading" @click="read">{{ t('cases.read') }}</button>
          <p v-if="archiveError" class="mt-4 text-sm text-red-700" role="alert">{{ archiveError }}</p>
          <div v-if="archive" class="mt-5 space-y-3 border-t border-stone-200 pt-5" data-testid="case-archive">
            <h3 class="font-medium text-brand-800">{{ t('cases.verifiedArchive') }}</h3>
            <p class="text-xs text-stone-500">{{ t('cases.lockedUntil', { at: fmtDate(archive.retain_until) }) }}</p>
            <p class="break-all font-mono text-xs">{{ archive.manifest_sha256 }}</p>
            <ul class="space-y-2"><li v-for="doc in archive.documents" :key="doc.id" class="text-sm">{{ doc.symbol }} · {{ doc.summary }}</li></ul>
            <p v-if="archive.hidden" class="text-xs text-stone-500">{{ t('cases.hiddenCount', { n: archive.hidden }) }}</p>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>
