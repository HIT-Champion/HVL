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
const {
  t
} = useI18n();
const {
  gql
} = useApi();
const tasks = ref([]);
const claims = useAuth().claims;
const query = useState('inbox-query', () => '');
const filter = useState('inbox-filter', () => 'all');
const category = useState('inbox-category', () => 'all');
const day = ref(today());

let clock;
onMounted(() => { clock = setInterval(() => { day.value = today(); }, 60000); });
onBeforeUnmount(() => clearInterval(clock));
const overdue = task => !!task.due_on && task.due_on < day.value;
const dueToday = task => task.due_on === day.value;
const urgent = task => task.urgency && task.urgency !== 'normal';
const normalize = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').toLowerCase();
const counts = computed(() => ({ all: tasks.value.length, overdue: tasks.value.filter(overdue).length, today: tasks.value.filter(dueToday).length, urgent: tasks.value.filter(urgent).length }));
const visible = computed(() => tasks.value.filter(task => {
  if (category.value === 'incoming' && !task.form_key.startsWith('vbden.')) return false;
  if (category.value === 'outgoing' && !task.form_key.startsWith('vbdi.')) return false;
  if (filter.value === 'overdue' && !overdue(task)) return false;
  if (filter.value === 'today' && !dueToday(task)) return false;
  if (filter.value === 'urgent' && !urgent(task)) return false;
  return normalize([task.document?.summary, task.document?.symbol, task.document?.issuer_name].join(' ')).includes(normalize(query.value));
}));
const attention = task => urgent(task) || overdue(task);
const attentionTasks = computed(() => visible.value.filter(attention));
const otherTasks = computed(() => visible.value.filter(task => !attention(task)));
const filtered = computed(() => !!query.value || filter.value !== 'all' || category.value !== 'all');
function clearFilters() { query.value = ''; filter.value = 'all'; category.value = 'all'; }
let version = 0;
onBeforeUnmount(() => { version++; });
const loading = ref(true);
const failure = ref('');
async function load() {
  const current = ++version;
  loading.value = true;
  failure.value = '';
  try {
    const data = await gql(`{
      myTasks { id name form_key created_at due_on urgency document_id
        document { symbol summary issuer_name register_number status } }
    }`);
    if (current === version) tasks.value = data.myTasks;
  } catch (e) {
    if (current === version) failure.value = errorText(t, e);
  } finally {
    if (current === version) loading.value = false;
  }
}
onMounted(() => { if (useAuth().claims.value?.role === 'tenant_admin') navigateTo('/so-kiem-toan', { replace: true }); else load(); });

// việc mới, nhắc hạn đẩy tới (F2.5): tải lại hộp việc, không phải bấm Làm mới
const {
  lastPush
} = useNotifications();
watch(lastPush, n => {
  if (n?.kind.startsWith('task.')) load();
});
</script>

<template>
  <div class="moc-desk">
    <div class="moc-desk-heading">
      <div><h1>{{ t('inbox.title') }}</h1><p aria-live="polite">{{ loading && !tasks.length ? t('fe.loading') : t('desk.pending', { n: counts.all }) }}</p></div>
      <NuxtLink v-if="claims?.role === 'clerk'" to="/van-ban-den/tiep-nhan" class="btn-primary">{{ t('fe.receiveNew') }}</NuxtLink>
      <NuxtLink v-if="claims?.role === 'staff'" to="/van-ban-di/soan" :aria-label="t('nav.compose')" class="btn-primary"><svg width="17" height="17" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M12 5v14m-7-7h14" /></svg>{{ t('desk.compose') }}</NuxtLink>
    </div>
    <div class="moc-inbox-toolbar">
      <div class="moc-desk-search"><svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M21 21l-4.3-4.3M10.5 18a7.5 7.5 0 110-15 7.5 7.5 0 010 15z" /></svg><input v-model="query" type="search" :placeholder="t('fe.searchTasks')" :aria-label="t('fe.searchTasks')"></div>
      <select v-model="category" class="input moc-inbox-filter" :aria-label="t('desk.category')"><option value="all">{{ t('desk.allDocuments') }}</option><option value="incoming">{{ t('nav.incoming') }}</option><option value="outgoing">{{ t('nav.outgoing') }}</option></select>
      <select v-model="filter" class="input moc-inbox-filter" :aria-label="t('desk.filter')"><option v-for="key in ['all','today','overdue','urgent']" :key="key" :value="key">{{ t('fe.' + (key === 'today' ? 'todayShort' : key)) }}</option></select>
      <button class="btn-secondary moc-inbox-refresh" :disabled="loading" :aria-label="t('app.refresh')" @click="load"><svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0112-1l2 3M4 15l2 3a7 7 0 0012-1" /></svg></button>
    </div>
    <div v-if="failure" class="moc-state" role="alert"><span>{{ failure }}</span><button class="btn-secondary" @click="load">{{ t('app.retry') }}</button></div>
    <div v-if="loading && !tasks.length" :aria-label="t('fe.loading')" aria-busy="true"><div v-for="n in 3" :key="n" class="moc-skeleton" /></div>
    <div v-else-if="!visible.length && !failure" class="moc-empty"><h2>{{ filtered ? t('fe.noTasks') : t('inbox.empty') }}</h2><p v-if="filtered">{{ t('fe.tryFilter') }}</p><button v-if="filtered" class="btn-secondary mt-4" @click="clearFilters">{{ t('desk.clearFilters') }}</button></div>
    <div v-else-if="visible.length" :aria-busy="loading" class="sg-task-groups" data-testid="inbox">
      <section v-if="attentionTasks.length" class="sg-attention" :aria-label="t('desk.attention')"><div class="sg-section-heading"><h2><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m12 3 10 18H2L12 3zm0 6v5m0 3v1" /></svg>{{ t('desk.attention') }}</h2><span>{{ t('fe.tasks', { n: attentionTasks.length }) }}</span></div><TransitionGroup name="sg-task" tag="ul"><TaskQueueItem v-for="task in attentionTasks" :key="task.id" :task="task" :overdue="overdue(task)" highlight /></TransitionGroup></section>
      <section v-if="otherTasks.length" :aria-label="attentionTasks.length ? t('desk.remaining') : t('desk.queue')"><div v-if="attentionTasks.length" class="sg-section-heading"><h2>{{ t('desk.remaining') }}</h2><span>{{ t('fe.tasks', { n: otherTasks.length }) }}</span></div><TransitionGroup name="sg-task" tag="ul" class="sg-task-list"><TaskQueueItem v-for="task in otherTasks" :key="task.id" :task="task" :overdue="overdue(task)" /></TransitionGroup></section>
    </div>
  </div>
</template>
