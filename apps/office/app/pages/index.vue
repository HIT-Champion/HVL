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
import { useI18n } from 'vue-i18n'

interface InboxTask {
  id: string
  name: string
  form_key: string
  created_at: string
  due_on: string | null
  urgency: string
  document_id: string
  document: { symbol: string | null; summary: string; issuer_name: string | null; register_number: number | null; status: string } | null
}

type Filter = 'all' | 'today' | 'overdue' | 'urgent'
type Category = 'all' | 'incoming' | 'outgoing'

const { t } = useI18n()
const { gql } = useApi()
const tasks = ref<InboxTask[]>([])
const loading = ref(true)
const failure = ref('')

// Lọc, tìm trên các việc đã tải, không gọi lại máy chủ. Giữ qua lúc mở một văn bản rồi bấm "Về hộp việc"
const query = useState<string>('inbox-query', () => '')
const filter = useState<Filter>('inbox-filter', () => 'all')
const category = useState<Category>('inbox-category', () => 'all')
const filters: Record<Filter, string> = {
  all: 'fe.all',
  today: 'fe.todayShort',
  overdue: 'fe.overdue',
  urgent: 'fe.urgent',
}

// ngày hôm nay (giờ Việt Nam) để tính quá hạn, cập nhật mỗi phút: trang mở qua nửa đêm vẫn đúng
const day = ref(today())
let clock: ReturnType<typeof setInterval> | undefined
onMounted(() => { clock = setInterval(() => { day.value = today() }, 60_000) })
onBeforeUnmount(() => clearInterval(clock))

const overdue = (task: InboxTask) => !!task.due_on && task.due_on < day.value
const dueToday = (task: InboxTask) => task.due_on === day.value
const urgent = (task: InboxTask) => !!task.urgency && task.urgency !== 'normal'
// so khớp không dấu: gõ "dao tao" vẫn ra "Đào tạo"
const normalize = (value: string) =>
  value.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/g, 'd')

// số việc của từng thẻ lọc, trong phạm vi chiều văn bản và từ khóa đang tìm: đổi tìm kiếm thì số đổi theo
const scoped = computed(() => {
  const needle = normalize(query.value)
  return tasks.value.filter((task) => {
    if (category.value === 'incoming' && !task.form_key.startsWith('vbden.')) return false
    if (category.value === 'outgoing' && !task.form_key.startsWith('vbdi.')) return false
    const doc = task.document
    return normalize([doc?.summary, doc?.symbol, doc?.issuer_name].join(' ')).includes(needle)
  })
})
const counts = computed<Record<Filter, number>>(() => ({
  all: scoped.value.length,
  today: scoped.value.filter(dueToday).length,
  overdue: scoped.value.filter(overdue).length,
  urgent: scoped.value.filter(urgent).length,
}))
const visible = computed(() => scoped.value.filter((task) => {
  if (filter.value === 'overdue') return overdue(task)
  if (filter.value === 'today') return dueToday(task)
  if (filter.value === 'urgent') return urgent(task)
  return true
}))
// việc khẩn hoặc quá hạn tách lên nhóm "Cần chú ý"
const attention = (task: InboxTask) => urgent(task) || overdue(task)
const attentionTasks = computed(() => visible.value.filter(attention))
const otherTasks = computed(() => visible.value.filter((task) => !attention(task)))
const filtered = computed(() => !!query.value || filter.value !== 'all' || category.value !== 'all')
function clearFilters() {
  query.value = ''
  filter.value = 'all'
  category.value = 'all'
}

// việc mới đẩy tới lúc đang tải dở: lượt cũ về sau không đè danh sách mới hơn
let seq = 0
async function load() {
  const mine = ++seq
  loading.value = true
  failure.value = ''
  try {
    const data = await gql<{ myTasks: InboxTask[] }>(`{
      myTasks { id name form_key created_at due_on urgency document_id
        document { symbol summary issuer_name register_number status } }
    }`)
    if (mine === seq) tasks.value = data.myTasks
  } catch (e) {
    if (mine === seq) failure.value = errorText(t, e)
  } finally {
    if (mine === seq) loading.value = false
  }
}

// Quản trị đơn vị không có hộp việc (Action myTasks chỉ cho vai trò nghiệp vụ, menu cũng không có): trang đầu của
// họ là sổ kiểm toán
const claims = useAuth().claims
onMounted(() => {
  if (claims.value?.role === 'tenant_admin') void navigateTo('/so-kiem-toan', { replace: true })
  else void load()
})

// việc mới, nhắc hạn đẩy tới (F2.5): tải lại hộp việc, không phải bấm Làm mới
const { lastPush } = useNotifications()
watch(lastPush, (n) => { if (n?.kind.startsWith('task.')) load() })
</script>

<template>
  <div class="moc-desk">
    <div class="moc-desk-heading">
      <div>
        <h1>{{ t('inbox.title') }}</h1>
        <p aria-live="polite">
          {{ loading && !tasks.length ? t('fe.loading') : t('desk.pending', { n: tasks.length }) }}
        </p>
      </div>
      <NuxtLink v-if="claims?.role === 'clerk'" to="/van-ban-den/tiep-nhan" class="btn-primary">
        {{ t('fe.receiveNew') }}
      </NuxtLink>
      <!-- không đặt aria-label "Soạn văn bản đi": trùng tên mục menu; chữ "Soạn mới" đủ nghĩa -->
      <NuxtLink v-if="claims?.role === 'staff'" to="/van-ban-di/soan" class="btn-primary">
        <svg
          width="17" height="17" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"
          aria-hidden="true"
        >
          <path d="M12 5v14m-7-7h14" />
        </svg>
        {{ t('desk.compose') }}
      </NuxtLink>
    </div>

    <div class="moc-inbox-toolbar">
      <div class="moc-desk-search">
        <svg
          width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"
          aria-hidden="true"
        >
          <path d="M21 21l-4.3-4.3M10.5 18a7.5 7.5 0 110-15 7.5 7.5 0 010 15z" />
        </svg>
        <input v-model="query" type="search" :placeholder="t('fe.searchTasks')" :aria-label="t('fe.searchTasks')">
      </div>
      <select v-model="category" class="input moc-inbox-filter" :aria-label="t('desk.category')">
        <option value="all">{{ t('desk.allDocuments') }}</option>
        <option value="incoming">{{ t('nav.incoming') }}</option>
        <option value="outgoing">{{ t('nav.outgoing') }}</option>
      </select>
      <button class="btn-secondary moc-inbox-refresh" :disabled="loading" :aria-label="t('app.refresh')" @click="load">
        <svg
          width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"
          aria-hidden="true"
        >
          <path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0112-1l2 3M4 15l2 3a7 7 0 0012-1" />
        </svg>
      </button>
    </div>

    <!-- thẻ lọc kèm số việc: một lần bấm thấy ngay việc hôm nay, quá hạn, khẩn -->
    <div class="moc-tabs moc-inbox-tabs" role="tablist" :aria-label="t('desk.filter')">
      <button
        v-for="(label, key) in filters" :key="key" role="tab" :aria-selected="filter === key"
        :class="{ 'is-alert': key === 'overdue' && counts.overdue > 0 }" @click="filter = key"
      >
        {{ t(label) }}<span>{{ counts[key] }}</span>
      </button>
    </div>

    <div v-if="failure" class="moc-state" role="alert">
      <span>{{ failure }}</span>
      <button class="btn-secondary" @click="load">{{ t('app.retry') }}</button>
    </div>
    <div v-if="loading && !tasks.length" :aria-label="t('fe.loading')" aria-busy="true">
      <div v-for="n in 3" :key="n" class="moc-skeleton" />
    </div>
    <div v-else-if="!visible.length && !failure" class="moc-empty">
      <h2>{{ filtered ? t('fe.noTasks') : t('inbox.empty') }}</h2>
      <p v-if="filtered">{{ t('fe.tryFilter') }}</p>
      <button v-if="filtered" class="btn-secondary mt-4" @click="clearFilters">{{ t('desk.clearFilters') }}</button>
    </div>
    <div v-else-if="visible.length" :aria-busy="loading" class="sg-task-groups" data-testid="inbox">
      <section v-if="attentionTasks.length" class="sg-attention" :aria-label="t('desk.attention')">
        <div class="sg-section-heading">
          <h2>{{ t('desk.attention') }}</h2>
          <span>{{ t('fe.tasks', { n: attentionTasks.length }) }}</span>
        </div>
        <TransitionGroup name="sg-task" tag="ul" class="sg-task-list">
          <TaskQueueItem
            v-for="task in attentionTasks" :key="task.id" :task="task" :day="day" :overdue="overdue(task)"
          />
        </TransitionGroup>
      </section>
      <section v-if="otherTasks.length" :aria-label="attentionTasks.length ? t('desk.remaining') : t('desk.queue')">
        <div v-if="attentionTasks.length" class="sg-section-heading">
          <h2>{{ t('desk.remaining') }}</h2>
          <span>{{ t('fe.tasks', { n: otherTasks.length }) }}</span>
        </div>
        <TransitionGroup name="sg-task" tag="ul" class="sg-task-list">
          <TaskQueueItem
            v-for="task in otherTasks" :key="task.id" :task="task" :day="day" :overdue="overdue(task)"
          />
        </TransitionGroup>
      </section>
    </div>
  </div>
</template>
