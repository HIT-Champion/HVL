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

// Sổ kiểm toán của đơn vị (F2.12), cho lãnh đạo và quản trị đơn vị: ai, lúc nào, làm gì, cột nào đổi, hash của
// từng dòng và dòng đó đã được neo ra ngoài CSDL chưa. Hasura chỉ trả `overview`: cột chứa nội dung (trích yếu,
// nội dung, tên tệp, ý kiến…) chỉ có tên, không có giá trị, để sổ không lộ văn bản hạn chế. Kiểm toàn bộ chuỗi
// là việc của lệnh `make audit` trên máy chủ, vì chuỗi chung cho mọi đơn vị.

interface Row {
  id: number
  occurred_at: string
  actor_id: string
  actor_kind: string
  action: string
  entity: string
  entity_id: string
  hash: string
  // trigger ghi {cột: [cũ, mới]}; sự kiện dịch vụ tự ghi (vd file.rejected) thì {trường: giá trị}
  overview: Record<string, unknown>
}

const PAGE = 50
const groups = {
  all: null,
  documents: ['office.documents', 'office.case_files', 'office.case_file_documents', 'office.dispatches'],
  assignments: ['office.assignments'],
  files: ['office.document_files', 'core.files'],
  people: ['core.users', 'office.document_acl'],
  catalog: ['office.departments', 'office.registers', 'office.document_types', 'core.tenants'],
} as const
type Group = keyof typeof groups

const { t } = useI18n()
const { gql } = useApi()
const route = useRoute()
const router = useRouter()

const group = computed<Group>(() => (String(route.query.loai ?? '') in groups ? (route.query.loai as Group) : 'all'))
const doc = computed(() => (typeof route.query.van_ban === 'string' ? route.query.van_ban : ''))
const rows = ref<Row[]>([])
const more = ref(false)
const anchor = ref<{ audit_id: number; anchored_at: string } | null>(null)
const names = ref(new Map<string, string>())
const departments = ref(new Map<string, string>())
const units = ref(new Map<string, string>())   // đơn vị khác (liên thông): tên thay cho id
const loading = ref(true)
const failure = ref('')
// quản trị đơn vị xem sổ nhưng không đọc văn bản nghiệp vụ: không có đường mở văn bản
const claims = useAuth().claims
const canOpen = computed(() => claims.value?.role !== 'tenant_admin')
let latest = 0 // đổi bộ lọc khi lần tải trước chưa xong: bỏ kết quả cũ

// Giao việc của văn bản đang lọc (dòng sổ của giao việc mang id giao việc, không mang id văn bản). Quản trị đơn vị
// không đọc được giao việc: chỉ lọc theo chính văn bản.
async function assignmentsOf(id: string): Promise<string[]> {
  try {
    const data = await gql<{ office_assignments: { id: string }[] }>(
      'query ($d: uuid!) { office_assignments(where: {document_id: {_eq: $d}}) { id } }', { d: id })
    return data.office_assignments.map((a) => a.id)
  } catch {
    return []
  }
}

async function where(before?: number) {
  const parts: Record<string, unknown>[] = []
  const entities = groups[group.value]
  if (entities) parts.push({ entity: { _in: entities } })
  // văn bản: chính dòng văn bản, tệp và quyền xem gắn với nó (entity_id "<văn bản>/<…>"), các lần giao việc
  if (doc.value) {
    parts.push({ _or: [
      { entity_id: { _eq: doc.value } },
      { entity_id: { _like: `${doc.value}/%` } },
      // văn bản trong hồ sơ (F3.8): entity_id "<hồ sơ>/<văn bản>"
      { entity: { _eq: 'office.case_file_documents' }, entity_id: { _like: `%/${doc.value}` } },
      { entity: { _eq: 'office.assignments' }, entity_id: { _in: await assignmentsOf(doc.value) } },
    ] })
  }
  if (before) parts.push({ id: { _lt: before } })
  return { _and: parts }
}

async function load(append = false) {
  const mine = ++latest
  if (!append) loading.value = true
  failure.value = ''
  try {
    const data = await gql<{
      core_audit_log: Row[]
      core_audit_anchors: { audit_id: number; anchored_at: string }[]
      core_users: { id: string; full_name: string }[]
      office_departments: { id: string; name: string }[]
      office_dispatch_units: { id: string; name: string }[]
    }>(`
      query ($where: core_audit_log_bool_exp!, $limit: Int!) {
        core_audit_log(where: $where, order_by: {id: desc}, limit: $limit) {
          id occurred_at actor_id actor_kind action entity entity_id hash overview
        }
        core_audit_anchors(order_by: {audit_id: desc}, limit: 1) { audit_id anchored_at }
        core_users { id full_name }
        office_departments { id name }
        office_dispatch_units { id name }
      }`, { where: await where(append ? rows.value.at(-1)?.id : undefined), limit: PAGE + 1 })
    if (mine !== latest) return
    const page = data.core_audit_log.slice(0, PAGE)
    more.value = data.core_audit_log.length > PAGE
    rows.value = append ? [...rows.value, ...page] : page
    anchor.value = data.core_audit_anchors[0] ?? null
    names.value = new Map(data.core_users.map((u) => [u.id, u.full_name]))
    departments.value = new Map(data.office_departments.map((d) => [d.id, d.name]))
    units.value = new Map(data.office_dispatch_units.map((u) => [u.id, u.name]))
  } catch (e) {
    if (mine === latest) failure.value = errorText(t, e)
  } finally {
    if (mine === latest) loading.value = false
  }
}

watch([group, doc], () => load())
onMounted(() => load())

const { label, action, who, changes } = useAuditFormat(names, departments, units)

// Văn bản mà dòng sổ thuộc về, để mở trang văn bản
function documentOf(row: Row): string | null {
  if (row.entity === 'office.documents') return row.entity_id
  if (row.entity === 'office.document_files' || row.entity === 'office.document_acl') return row.entity_id.split('/')[0] ?? null
  const ref = row.overview.document_id
  return Array.isArray(ref) ? String(ref[1] ?? ref[0] ?? '') || null : null
}

function anchored(row: Row) {
  return anchor.value !== null && row.id <= anchor.value.audit_id
}
</script>

<template>
  <div>
    <PageHeader :title="t('audit.title')" :subtitle="t('audit.subtitle')" />

    <div class="card mb-4 flex flex-wrap items-start gap-3 p-4 text-sm" data-testid="audit-anchor">
      <svg class="mt-0.5 h-5 w-5 shrink-0" :class="anchor ? 'text-emerald-600' : 'text-stone-400'" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6l7-3zm-3 9l2 2 4-4" /></svg>
      <div class="min-w-0 flex-1">
        <p v-if="anchor" class="font-medium text-stone-800">{{ t('audit.anchored', { id: anchor.audit_id, at: fmtDateTime(anchor.anchored_at) }) }}</p>
        <p v-else class="font-medium text-stone-800">{{ t('audit.notAnchored') }}</p>
        <p class="mt-0.5 text-stone-500">{{ t('audit.how') }}</p>
      </div>
    </div>

    <div class="mb-4 flex flex-wrap items-center gap-2">
      <div class="flex flex-wrap gap-1 border-b border-stone-200" role="tablist">
        <button
          v-for="(_, key) in groups" :key="key" role="tab" :aria-selected="group === key"
          class="-mb-px border-b-2 px-3 py-2 text-sm font-medium"
          :class="group === key ? 'border-brand-700 text-brand-800' : 'border-transparent text-stone-500 hover:text-stone-800'"
          @click="router.replace({ query: { ...route.query, loai: key } })"
        >
          {{ t(`audit.group.${key}`) }}
        </button>
      </div>
      <span v-if="doc" class="chip bg-brand-50 text-brand-800">
        {{ t('audit.forDocument') }}
        <button class="ml-1 font-bold" :aria-label="t('audit.clear')" @click="router.replace({ query: { ...route.query, van_ban: undefined } })">×</button>
      </span>
    </div>

    <p v-if="failure" class="card p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-else-if="loading" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <p v-else-if="!rows.length" class="card p-12 text-center text-stone-500">{{ t('audit.empty') }}</p>
    <div v-else class="card overflow-x-auto">
      <table class="w-full text-sm" data-testid="audit-table">
        <thead class="border-b border-stone-200 bg-stone-50 text-left text-xs font-medium tracking-wide text-stone-500 uppercase">
          <tr>
            <th class="px-4 py-3">{{ t('audit.when') }}</th>
            <th class="px-4 py-3">{{ t('audit.who') }}</th>
            <th class="px-4 py-3">{{ t('audit.what') }}</th>
            <th class="px-4 py-3">{{ t('audit.changes') }}</th>
            <th class="px-4 py-3">{{ t('audit.chain') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-stone-100">
          <tr v-for="row in rows" :key="row.id" class="align-top">
            <td class="px-4 py-3 whitespace-nowrap text-stone-600">{{ fmtDateTime(row.occurred_at) }}</td>
            <td class="px-4 py-3">{{ who(row) }}</td>
            <td class="px-4 py-3">
              <div class="font-medium whitespace-nowrap">{{ action(row) }} · {{ label('audit.entity', row.entity) }}</div>
              <NuxtLink v-if="canOpen && documentOf(row)" :to="`/van-ban/${documentOf(row)}`" class="text-xs text-brand-700 hover:underline">{{ t('audit.openDocument') }}</NuxtLink>
            </td>
            <td class="max-w-md px-4 py-3">
              <div v-for="c in changes(row).shown" :key="c.col" class="text-stone-700"><span class="text-stone-500">{{ c.col }}:</span> {{ c.text }}</div>
              <div v-if="changes(row).hidden.length" class="text-xs text-stone-500" :title="t('audit.hiddenHint')">
                {{ t('audit.hidden', { cols: changes(row).hidden.join(', ') }) }}
              </div>
            </td>
            <td class="px-4 py-3 whitespace-nowrap">
              <div class="font-mono text-xs text-stone-700" :title="row.hash">#{{ row.id }} · {{ row.hash.slice(2, 12) }}…</div>
              <div class="mt-0.5 text-xs" :class="anchored(row) ? 'text-emerald-700' : 'text-stone-400'">
                {{ anchored(row) ? t('audit.isAnchored') : t('audit.notYet') }}
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="more" class="border-t border-stone-100 p-3 text-center">
        <button class="btn-secondary" @click="load(true)">{{ t('audit.more') }}</button>
      </div>
    </div>
  </div>
</template>
