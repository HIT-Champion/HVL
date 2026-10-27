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

// Lịch hạn của hộp việc: hai tuần từ Thứ Hai tuần này, mỗi ngày đếm việc đến hạn (chấm đỏ là việc khẩn hoặc đã
// quá hạn), hai đầu là ô Quá hạn và Sau đó. Bấm một ô để chỉ xem việc của ô đó, bấm lại để bỏ. Thu gọn được; lựa
// chọn nhớ trong trình duyệt (chỉ cho tiện, không lưu được thì thôi).
interface DueTask { due_on: string | null; urgency: string }

const props = defineProps<{ tasks: DueTask[]; day: string }>()
const selected = defineModel<string | null>({ default: null })
const { t, locale } = useI18n()

const days = computed(() => Array.from({ length: 14 }, (_, i) => addDays(weekStart(props.day), i)))
const last = computed(() => days.value.at(-1)!)
const urgent = (task: DueTask) => !!task.urgency && task.urgency !== 'normal'
const perDay = computed(() => {
  const map = new Map<string, { n: number; hot: number }>()
  for (const task of props.tasks) {
    if (!task.due_on) continue
    const cell = map.get(task.due_on) ?? { n: 0, hot: 0 }
    cell.n++
    if (urgent(task) || task.due_on < props.day) cell.hot++
    map.set(task.due_on, cell)
  }
  return map
})
const overdue = computed(() => props.tasks.filter((task) => task.due_on && task.due_on < props.day).length)
const later = computed(() => props.tasks.filter((task) => task.due_on && task.due_on > last.value).length)
const noDue = computed(() => props.tasks.filter((task) => !task.due_on).length)

const long = (iso: string) => `${fmtWeekday(iso, locale.value)} ${fmtDate(iso)}`
const dayLabel = (iso: string) => {
  const n = perDay.value.get(iso)?.n ?? 0
  return n ? t('desk.dayTasks', { date: long(iso), n }, n) : t('desk.dayNone', { date: long(iso) })
}
// tối đa ba chấm mỗi ngày, chấm đỏ (khẩn, quá hạn) đứng trước
function dots(iso: string): boolean[] {
  const cell = perDay.value.get(iso)
  if (!cell) return []
  return Array.from({ length: Math.min(cell.n, 3) }, (_, i) => i < cell.hot)
}
function pick(key: string) {
  selected.value = selected.value === key ? null : key
}

const KEY = 'moc.inbox.calendar'
const open = ref(true)
const strip = ref<HTMLElement>()
// dải ngày cuộn ngang khi không đủ chỗ (trên điện thoại cả dải cuộn, ô Quá hạn bám mép trái): cuộn sẵn để hôm nay
// đứng thứ hai sau ô Quá hạn
async function reveal() {
  await nextTick()
  const today = strip.value?.querySelector<HTMLElement>('.is-today')
  const box = [strip.value, strip.value?.parentElement].find((el) => el && el.scrollWidth > el.clientWidth)
  if (!today || !box) return
  const edge = box === strip.value ? 0 : box.querySelector('.sg-calendar-edge')?.getBoundingClientRect().width ?? 0
  const at = today.getBoundingClientRect().left - box.getBoundingClientRect().left
  box.scrollLeft += at - edge - today.offsetWidth
}
// chưa chọn lần nào thì màn rộng mở lịch, điện thoại thu lại để việc đầu tiên lên gần đầu màn hình
onMounted(() => {
  let saved: string | null = null
  try { saved = localStorage.getItem(KEY) } catch { /* trình duyệt chặn lưu: theo mặc định */ }
  open.value = saved ? saved !== 'closed' : !matchMedia('(max-width: 640px)').matches
  if (open.value) reveal()
})
function toggle() {
  open.value = !open.value
  try { localStorage.setItem(KEY, open.value ? 'open' : 'closed') } catch { /* không lưu được thì thôi */ }
  if (open.value) reveal()
}
</script>

<template>
  <section class="sg-calendar" aria-labelledby="due-calendar-title">
    <div class="sg-calendar-head">
      <h2 id="due-calendar-title">{{ t('desk.calendar') }}</h2>
      <span class="sg-calendar-range">{{ fmtDate(days[0]).slice(0, 5) }} – {{ fmtDate(last).slice(0, 5) }}</span>
      <button
        v-if="!open && overdue" type="button" class="sg-calendar-flag" :aria-pressed="selected === 'overdue'"
        @click="pick('overdue')"
      >
        {{ t('fe.overdue') }} <b>{{ overdue }}</b>
      </button>
      <button
        type="button" class="btn-ghost sg-calendar-toggle" :aria-expanded="open" aria-controls="due-calendar-days"
        @click="toggle"
      >
        {{ open ? t('desk.hideCalendar') : t('desk.showCalendar') }}
        <svg
          width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
          aria-hidden="true"
        >
          <path :d="open ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'" />
        </svg>
      </button>
    </div>
    <div v-show="open" id="due-calendar-days" class="sg-calendar-strip">
      <button
        type="button" class="sg-calendar-edge" :class="{ 'is-over': overdue }" :disabled="!overdue"
        :aria-pressed="selected === 'overdue'" @click="pick('overdue')"
      >
        <span>{{ t('fe.overdue') }}</span>
        <b>{{ overdue }}</b>
      </button>
      <div ref="strip" class="sg-calendar-days">
        <button
          v-for="(iso, i) in days" :key="iso" type="button" class="sg-day"
          :class="{
            'is-today': iso === day, 'is-past': iso < day, 'is-week': i === 7,
            'has-tasks': perDay.get(iso)?.n,
          }"
          :disabled="!perDay.get(iso)?.n" :aria-pressed="selected === iso"
          :aria-current="iso === day ? 'date' : undefined" @click="pick(iso)"
        >
          <span class="sg-day-name">{{ iso === day ? t('fe.todayShort') : fmtWeekday(iso, locale, 'short') }}</span>
          <span class="sg-day-num">{{ Number(iso.slice(8)) }}</span>
          <span class="sr-only">, {{ dayLabel(iso) }}</span>
          <span class="sg-day-dots" aria-hidden="true">
            <i v-for="(hot, n) in dots(iso)" :key="n" :class="{ 'is-hot': hot }" />
          </span>
        </button>
      </div>
      <button
        type="button" class="sg-calendar-edge" :disabled="!later" :aria-pressed="selected === 'later'"
        @click="pick('later')"
      >
        <span>{{ t('desk.later') }}</span>
        <b>{{ later }}</b>
      </button>
      <button
        v-if="noDue" type="button" class="sg-calendar-edge" :aria-pressed="selected === 'none'" @click="pick('none')"
      >
        <span>{{ t('desk.noDeadline') }}</span>
        <b>{{ noDue }}</b>
      </button>
    </div>
  </section>
</template>
