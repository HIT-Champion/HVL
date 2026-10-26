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

const { t, locale } = useI18n()
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

const visible = computed(() => {
  const needle = normalize(query.value)
  return tasks.value.filter((task) => {
    if (category.value === 'incoming' && !task.form_key.startsWith('vbden.')) return false
    if (category.value === 'outgoing' && !task.form_key.startsWith('vbdi.')) return false
    if (filter.value === 'overdue' && !overdue(task)) return false
    if (filter.value === 'today' && !dueToday(task)) return false
    if (filter.value === 'urgent' && !urgent(task)) return false
    const doc = task.document
    return normalize([doc?.summary, doc?.symbol, doc?.issuer_name].join(' ')).includes(needle)
  })
})
// Lịch hạn: chọn một ô (một ngày, quá hạn, sau hai tuần, chưa có hạn) thì chỉ xem việc của ô đó
const picked = useState<string | null>('inbox-day', () => null)
const calendarEnd = computed(() => addDays(weekStart(day.value), 13))
function inPicked(task: InboxTask) {
  const due = task.due_on
  if (!picked.value) return true
  if (picked.value === 'overdue') return !!due && due < day.value
  if (picked.value === 'later') return !!due && due > calendarEnd.value
  if (picked.value === 'none') return !due
  return due === picked.value
}
const shown = computed(() => visible.value.filter(inPicked))
// ô đang chọn hết việc (lọc khác đổi, việc vừa xong) thì bỏ chọn
watch(visible, (list) => { if (picked.value && !list.some(inPicked)) picked.value = null })

// Nhóm theo ngày hạn, sớm trước; trong một ngày việc khẩn hơn đứng trước; việc chưa có hạn ở cuối
const RANK: Record<string, number> = { hoa_toc: 0, thuong_khan: 1, khan: 2 }
const groups = computed(() => {
  const map = new Map<string | null, InboxTask[]>()
  for (const task of shown.value) map.set(task.due_on, [...(map.get(task.due_on) ?? []), task])
  for (const list of map.values()) {
    list.sort((a, b) => (RANK[a.urgency] ?? 3) - (RANK[b.urgency] ?? 3) || b.created_at.localeCompare(a.created_at))
  }
  return [...map.entries()].sort(([a], [b]) => (a === null ? 1 : b === null ? -1 : a.localeCompare(b)))
})
const dueText = (due: string) => {
  const state = dueState(due, day.value)
  if (state.tone === 'over') return t('desk.dueOver', { n: state.n }, state.n)
  if (state.tone === 'today') return t('desk.dueToday')
  return t('desk.dueLeft', { n: state.n }, state.n)
}
const longDate = (iso: string) => `${fmtWeekday(iso, locale.value)} ${fmtDate(iso).slice(0, 5)}`
// câu mở đầu: bao nhiêu việc, hạn gần nhất là ngày nào, còn hay quá bao lâu
const finding = computed(() => {
  const n = tasks.value.length
  if (!n) return t('inbox.empty')
  const nearest = tasks.value.map((task) => task.due_on).filter((due): due is string => !!due).sort()[0]
  if (!nearest) return t('desk.findingNoDue', { n }, n)
  return t('desk.finding', { n, date: longDate(nearest), left: dueText(nearest) }, n)
})
const pickedText = computed(() => {
  if (picked.value === 'overdue') return t('desk.showingOverdue')
  if (picked.value === 'later') return t('desk.showingLater', { date: fmtDate(calendarEnd.value) })
  if (picked.value === 'none') return t('desk.showingNoDue')
  if (!picked.value) return ''
  return t('desk.showingDay', { date: `${fmtWeekday(picked.value, locale.value)} ${fmtDate(picked.value)}` })
})

const filtered = computed(() => !!query.value || filter.value !== 'all' || category.value !== 'all' || !!picked.value)
function clearFilters() {
  query.value = ''
  filter.value = 'all'
  category.value = 'all'
  picked.value = null
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
        <p aria-live="polite">{{ loading && !tasks.length ? t('fe.loading') : finding }}</p>
      </div>
      <NuxtLink v-if="claims?.role === 'clerk'" to="/van-ban-den/tiep-nhan" class="btn-primary">
        {{ t('fe.receiveNew') }}
      </NuxtLink>
      <!-- không đặt aria-label "Soạn văn bản đi": trùng tên mục menu; chữ "Soạn mới" đủ nghĩa -->
      <NuxtLink v-if="claims?.role === 'staff'" to="/van-ban-di/soan" class="btn-secondary">
        <svg
          width="17" height="17" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"
          aria-hidden="true"
        >
          <path d="M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17v3zM13.5 7.5l3 3" />
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
      <select v-model="filter" class="input moc-inbox-filter" :aria-label="t('desk.filter')">
        <option v-for="(label, key) in filters" :key="key" :value="key">{{ t(label) }}</option>
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

    <DueCalendar v-if="tasks.length" v-model="picked" :tasks="visible" :day="day" />
    <p v-if="picked" class="sg-picked">
      {{ pickedText }}
      <button type="button" class="sg-link" @click="picked = null">
        {{ t('desk.showAll', { n: visible.length }, visible.length) }}
      </button>
    </p>

    <div v-if="failure" class="moc-state" role="alert">
      <span>{{ failure }}</span>
      <button class="btn-secondary" @click="load">{{ t('app.retry') }}</button>
    </div>
    <div v-if="loading && !tasks.length" :aria-label="t('fe.loading')" aria-busy="true">
      <div v-for="n in 3" :key="n" class="moc-skeleton" />
    </div>
    <div v-else-if="!shown.length && !failure" class="moc-empty">
      <h2>{{ filtered ? t('fe.noTasks') : t('inbox.empty') }}</h2>
      <p v-if="filtered">{{ t('fe.tryFilter') }}</p>
      <button v-if="filtered" class="btn-secondary mt-4" @click="clearFilters">{{ t('desk.clearFilters') }}</button>
    </div>
    <div v-else-if="shown.length" :aria-busy="loading" class="sg-agenda" data-testid="inbox">
      <section
        v-for="[due, list] in groups" :key="due ?? 'none'" class="sg-due-group"
        :class="due ? `is-${dueState(due, day).tone}` : 'is-none'" :aria-labelledby="`due-${due ?? 'none'}`"
      >
        <h2 :id="`due-${due ?? 'none'}`" class="sg-due-when">
          <!-- {{ ' ' }} giữ dấu cách giữa các phần khi đọc thành tiếng: "31 Thứ Bảy tháng 10 còn 5 ngày" -->
          <template v-if="due">
            <span class="sg-due-num">{{ Number(due.slice(8)) }}</span>{{ ' ' }}<span class="sg-due-text">
              <b>{{ fmtWeekday(due, locale) }}</b>{{ ' ' }}<span>{{ fmtMonth(due, locale, day.slice(0, 4)) }}</span>
              {{ ' ' }}<em>{{ dueText(due) }}</em>
            </span>
          </template>
          <span v-else class="sg-due-text"><b>{{ t('desk.noDeadline') }}</b></span>
        </h2>
        <TransitionGroup name="sg-task" tag="ul" class="sg-task-list">
          <TaskQueueItem v-for="task in list" :key="task.id" :task="task" />
        </TransitionGroup>
      </section>
    </div>
  </div>
</template>
