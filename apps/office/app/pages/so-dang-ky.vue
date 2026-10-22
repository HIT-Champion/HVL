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
import type { RegisterBook } from '~/composables/useApi'

// Sổ đăng ký văn bản đến / đi theo năm (F2.8), cho văn thư và lãnh đạo đơn vị. NĐ 30/2020, Điều 16, 22: văn bản
// đăng ký trên hệ thống phải in ra giấy đủ các trường theo mẫu sổ (Phụ lục IV), ký nhận và đóng sổ. Màn này cho
// xem đúng các cột, các ô sẽ in (svc-files dựng cả hai từ một chỗ), kiểm sổ có liền số không, rồi in ra PDF.
// Văn bản hạn chế người xem không được đọc vẫn có dòng (sổ phải liền số) nhưng chỉ có số, ngày, số ký hiệu.

const books = { den: 'in', di: 'out' } as const
type Book = keyof typeof books
const FIRST_YEAR = 2020

const { t } = useI18n()
const { register, printRegister } = useApi()
const notice = useNotice()
const route = useRoute()
const router = useRouter()

const thisYear = Number(today().slice(0, 4))
const years = Array.from({ length: thisYear - FIRST_YEAR + 1 }, (_, i) => thisYear - i)
const book = computed<Book>(() => (String(route.query.so ?? '') in books ? (route.query.so as Book) : 'den'))
const year = computed(() => {
  const y = Number(route.query.nam)
  return Number.isInteger(y) && y >= FIRST_YEAR && y <= thisYear ? y : thisYear
})

const data = ref<RegisterBook | null>(null)
const loading = ref(true)
const failure = ref('')
const printing = ref(false)
let latest = 0 // đổi sổ, đổi năm khi lần tải trước chưa xong: bỏ kết quả cũ

async function load() {
  const mine = ++latest
  loading.value = true
  failure.value = ''
  try {
    const result = await register(books[book.value], year.value)
    if (mine === latest) data.value = result
  } catch (e) {
    if (mine === latest) failure.value = errorText(t, e)
  } finally {
    if (mine === latest) loading.value = false
  }
}

watch([book, year], load)
onMounted(load)

// Cột luôn trống trên hệ thống (Ký nhận, Số lượng bản) chỉ để ghi tay trên bản in: màn hình bỏ đi cho gọn
const shown = computed(() => {
  const d = data.value
  if (!d) return []
  const idx = d.columns.map((_, i) => i)
  return d.entries.length ? idx.filter((i) => d.entries.some((e) => e.cells[i])) : idx
})
const isDate = (cell: string | undefined) => /^\d\d\/\d\d\/\d{4}$/.test(cell ?? '')
const masked = computed(() => data.value?.entries.filter((e) => e.hidden).length ?? 0)

function pick(query: Record<string, string>) {
  router.replace({ query: { ...route.query, ...query } })
}

async function print() {
  printing.value = true
  try {
    await printRegister(books[book.value], year.value)
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    printing.value = false
  }
}
</script>

<template>
  <div>
    <PageHeader :title="t('register.title')" :subtitle="t('register.subtitle')">
      <label class="sr-only" for="register-year">{{ t('register.year') }}</label>
      <select id="register-year" class="input w-28" :value="year" @change="pick({ nam: ($event.target as HTMLSelectElement).value })">
        <option v-for="y in years" :key="y" :value="y">{{ t('register.yearOption', { year: y }) }}</option>
      </select>
      <button class="btn-primary" :disabled="printing || loading || !!failure" data-testid="register-print" @click="print">
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M7 9V3h10v6M7 17H5a2 2 0 01-2-2v-4a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2h-2M7 14h10v7H7z" /></svg>
        {{ printing ? t('register.printing') : t('register.print') }}
      </button>
    </PageHeader>

    <div class="mb-4 flex gap-1 border-b border-stone-200" role="tablist">
      <button
        v-for="(_, key) in books" :key="key" role="tab" :aria-selected="book === key"
        class="-mb-px border-b-2 px-4 py-2 text-sm font-medium"
        :class="book === key ? 'border-brand-700 text-brand-800' : 'border-transparent text-stone-500 hover:text-stone-800'"
        @click="pick({ so: key })"
      >
        {{ t(`register.book.${key}`) }}
      </button>
    </div>

    <p v-if="failure" class="card p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-else-if="loading" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <template v-else-if="data">
      <div class="card mb-4 flex flex-wrap items-start gap-3 p-4 text-sm" data-testid="register-check">
        <svg class="mt-0.5 h-5 w-5 shrink-0" :class="data.missing.length ? 'text-red-600' : 'text-emerald-600'" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" :d="data.missing.length ? 'M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z' : 'M5 13l4 4L19 7'" /></svg>
        <div class="min-w-0 flex-1">
          <p v-if="!data.last_number" class="font-medium text-stone-800">{{ t('register.none', { year: data.year }) }}</p>
          <p v-else-if="data.missing.length" class="font-medium text-red-700">{{ t('register.gaps', { numbers: data.missing.join(', ') }) }}</p>
          <p v-else class="font-medium text-stone-800">{{ t('register.continuous', { last: String(data.last_number).padStart(2, '0') }) }}</p>
          <p class="mt-0.5 text-stone-500">
            {{ t('register.how') }}
            <template v-if="masked"> {{ t('register.masked', { n: masked }) }}</template>
          </p>
        </div>
      </div>

      <div v-if="data.entries.length" class="card overflow-x-auto">
        <table class="w-full text-sm" data-testid="register-table">
          <thead class="border-b border-stone-200 bg-stone-50 text-left text-xs font-medium tracking-wide text-stone-500">
            <tr>
              <th v-for="i in shown" :key="i" class="px-3 py-3">{{ data.columns[i] }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100">
            <tr
              v-for="entry in data.entries" :key="entry.number" class="align-top"
              :class="entry.document_id ? 'cursor-pointer hover:bg-brand-50/40' : 'text-stone-500 italic'"
              @click="entry.document_id && router.push(`/van-ban/${entry.document_id}`)"
            >
              <td
                v-for="i in shown" :key="i" class="px-3 py-2"
                :class="{ 'font-semibold tabular-nums': data.direction === 'in' && i === 1, 'whitespace-nowrap': isDate(entry.cells[i]) }"
              >
                {{ entry.cells[i] }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
