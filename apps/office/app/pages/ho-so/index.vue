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
import {
  RETENTION_CHOICES, STATUS_TONE, caseFileErrorText, caseFileInput, canCreate, validateCaseFile,
} from '~/utils/caseFiles'
import type { CaseFileForm, CaseFileStatus } from '~/utils/caseFiles'

// Hồ sơ công việc (F3.8; NĐ 30/2020, Điều 28–31). Hasura chỉ trả hồ sơ người dùng được xem: chuyên viên, lãnh đạo
// phòng thấy hồ sơ của phòng mình và lập được hồ sơ mới; văn thư, lãnh đạo đơn vị thấy mọi hồ sơ của đơn vị (phòng
// đọc). Mở một hồ sơ để thêm văn bản, đóng, nộp lưu, xem gói đã nộp lưu — trang ho-so/[id].

interface Row {
  id: string
  year: number
  code: string
  title: string
  status: CaseFileStatus
  retention_years: number | null
  closed_on: string | null
  archived_at: string | null
  department: { name: string } | null
  case_file_documents: { document_id: string }[]
}

const { t } = useI18n()
const { gql } = useApi()
const claims = useAuth().claims
const notice = useNotice()
const route = useRoute()
const router = useRouter()

const tabs = { open: ['open'], closed: ['closed'], archived: ['archived'], all: null } as const
type Tab = keyof typeof tabs
const tab = computed<Tab>(() => (String(route.query.tab ?? '') in tabs ? (route.query.tab as Tab) : 'all'))

const viewer = computed(() => ({
  role: claims.value?.role ?? null,
  departmentId: claims.value?.departmentId ?? null,
  userId: claims.value?.userId ?? '',
}))

const rows = ref<Row[]>([])
const loading = ref(true)
const failure = ref('')
const more = ref(false)
let seq = 0

async function load(append = false) {
  const mine = ++seq
  loading.value = true
  if (!append) {
    failure.value = ''
    rows.value = []
  }
  const page = nextPage(rows.value.length)
  const statuses = tabs[tab.value]
  try {
    const data = await gql<{ office_case_files: Row[] }>(`
      query ($where: office_case_files_bool_exp!, $offset: Int!, $limit: Int!) {
        office_case_files(where: $where, order_by: [{created_at: desc}, {id: asc}], limit: $limit, offset: $offset) {
          id year code title status retention_years closed_on archived_at department { name }
          case_file_documents { document_id }
        }
      }`, { where: statuses ? { status: { _in: statuses } } : {}, ...page })
    if (mine !== seq) return
    const merged = mergePage(rows.value, data.office_case_files)
    rows.value = merged.rows
    more.value = merged.more
  } catch (e) {
    if (mine === seq && append) notice.error(errorText(t, e))
    else if (mine === seq) failure.value = errorText(t, e)
  } finally {
    if (mine === seq) loading.value = false
  }
}

watch(tab, () => load())
onMounted(() => load())

// --- lập hồ sơ: phòng, người lập, đơn vị do Hasura đặt từ phiên --------------------------------------------------

const creating = ref(false)
const saving = ref(false)
const form = reactive<CaseFileForm>({ year: Number(today().slice(0, 4)), code: '', title: '', retention: '10' })
const errors = ref<Record<string, string>>({})

const errorOf = (e: unknown) => caseFileErrorText(t, e, (x) => errorText(t, x))

async function create() {
  errors.value = validateCaseFile(form)
  if (Object.keys(errors.value).length) {
    await focusInvalidField()
    return
  }
  saving.value = true
  try {
    const data = await gql<{ insert_office_case_files_one: { id: string, code: string } }>(`
      mutation ($o: office_case_files_insert_input!) { insert_office_case_files_one(object: $o) { id code } }`,
    { o: caseFileInput(form) })
    notice.ok(t('cases.created', { code: data.insert_office_case_files_one.code }))
    await router.push(`/ho-so/${data.insert_office_case_files_one.id}`)
  } catch (e) {
    notice.error(errorOf(e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <PageHeader :title="t('cases.title')" :subtitle="t('cases.subtitle')">
      <button
        v-if="canCreate(viewer) && !creating" class="btn-primary" data-testid="case-file-new"
        @click="creating = true"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
          <path stroke-linecap="round" d="M12 5v14m-7-7h14" />
        </svg>
        {{ t('cases.create') }}
      </button>
    </PageHeader>

    <form
      v-if="creating" class="moc-block mb-6 grid gap-4 sm:grid-cols-2" data-testid="case-file-form" novalidate
      @submit.prevent="create"
    >
      <div>
        <label class="label" for="cf-code">{{ t('cases.code') }}</label>
        <input
          id="cf-code" v-model="form.code" class="input" :placeholder="t('cases.codeHint')" maxlength="50"
          required :aria-invalid="!!errors.code" :aria-describedby="errors.code ? 'cf-code-error' : undefined"
        >
        <p v-if="errors.code" id="cf-code-error" class="field-error">{{ t(`cases.validation.${errors.code}`) }}</p>
      </div>
      <div>
        <label class="label" for="cf-year">{{ t('cases.year') }}</label>
        <input
          id="cf-year" v-model="form.year" type="number" min="2000" max="2999" class="input"
          required :aria-invalid="!!errors.year" :aria-describedby="errors.year ? 'cf-year-error' : undefined"
        >
        <p v-if="errors.year" id="cf-year-error" class="field-error">{{ t(`cases.validation.${errors.year}`) }}</p>
      </div>
      <div class="sm:col-span-2">
        <label class="label" for="cf-title">{{ t('cases.name') }}</label>
        <input id="cf-title" v-model="form.title" class="input" maxlength="500" required
          :aria-invalid="!!errors.title" :aria-describedby="errors.title ? 'cf-title-error' : undefined">
        <p v-if="errors.title" id="cf-title-error" class="field-error">{{ t(`cases.validation.${errors.title}`) }}</p>
      </div>
      <div>
        <label class="label" for="cf-retention">{{ t('cases.retention') }}</label>
        <select id="cf-retention" v-model="form.retention" class="input">
          <option v-for="n in RETENTION_CHOICES" :key="n" :value="String(n)">
            {{ t('cases.retentionYears', { n }) }}
          </option>
          <option value="permanent">{{ t('cases.permanent') }}</option>
        </select>
      </div>
      <div class="flex items-end justify-end gap-2">
        <button type="button" class="btn-secondary" @click="creating = false">{{ t('app.cancel') }}</button>
        <button type="submit" class="btn-primary" :disabled="saving">
          {{ saving ? t('cases.creating') : t('cases.create') }}
        </button>
      </div>
    </form>

    <div class="moc-tabs" role="tablist">
      <button
        v-for="(_, key) in tabs" :key="key" role="tab" :aria-selected="tab === key"
        @click="router.replace({ query: { tab: key } })"
      >
        {{ t(`cases.tab.${key}`) }}
      </button>
    </div>

    <div v-if="failure" class="moc-state" role="alert">
      <span>{{ failure }}</span>
      <button class="btn-secondary" @click="load()">{{ t('app.retry') }}</button>
    </div>
    <div v-else-if="loading && !rows.length" role="status" aria-busy="true" :aria-label="t('app.loading')">
      <div v-for="n in 5" :key="n" class="moc-skeleton" />
    </div>
    <p v-else-if="!rows.length" class="moc-empty">{{ t('cases.empty') }}</p>
    <div v-else class="moc-doc-table moc-case-table overflow-x-auto">
      <table class="w-full text-sm" data-testid="case-file-table">
        <thead>
          <tr>
            <th class="px-4">{{ t('cases.code') }}</th>
            <th class="px-4">{{ t('cases.name') }}</th>
            <th class="px-4">{{ t('cases.archiveStatus') }}</th>
            <th class="px-4">{{ t('cases.retention') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="cursor-pointer" @click="router.push(`/ho-so/${row.id}`)">
            <td class="px-4 whitespace-nowrap">
              <div class="font-medium tabular-nums">{{ row.code }}</div>
              <div class="mt-0.5 text-[13px] text-stone-500 tabular-nums">{{ row.year }}</div>
            </td>
            <td class="max-w-xl px-4">
              <NuxtLink :to="`/ho-so/${row.id}`" class="moc-doc-title" @click.stop>
                {{ row.title }}
              </NuxtLink>
              <div class="moc-doc-meta">
                {{ row.department?.name }} · {{ t('cases.documentCount', { n: row.case_file_documents.length }) }}
              </div>
            </td>
            <td class="px-4 whitespace-nowrap">
              <span class="chip" :class="STATUS_TONE[row.status]">
                {{ t(`cases.status.${row.status}`) }}
              </span>
              <div class="mt-0.5 text-[13px] text-stone-500 tabular-nums">
                {{ row.archived_at ? fmtDate(row.archived_at) : row.closed_on ? fmtDate(row.closed_on) : '' }}
              </div>
            </td>
            <td :data-label="t('cases.retention')" class="px-4 whitespace-nowrap text-stone-600">
              {{ row.retention_years ? t('cases.retentionYears', { n: row.retention_years }) : t('cases.permanent') }}
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="more" class="moc-more">
        <button class="btn-secondary" :disabled="loading" data-testid="list-more" @click="load(true)">
          {{ t('app.more') }}
        </button>
      </div>
    </div>
  </div>
</template>
