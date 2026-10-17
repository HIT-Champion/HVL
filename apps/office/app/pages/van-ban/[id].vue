<!--
  Copyright 2026 Mộc Team

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
import type { PanelDepartment, PanelUser } from '~/components/TaskPanel.vue'

// Chi tiết văn bản: thông tin, tệp, giao xử lý, dòng thời gian (F2.6) và khung xử lý việc đang chờ người
// dùng. Hasura chỉ trả văn bản người dùng được đọc — không thấy thì báo "không tìm thấy".

interface Doc {
  id: string
  direction: string
  status: string
  type_code: string
  document_type: { name: string } | null
  symbol: string | null
  issuer_name: string | null
  issued_on: string | null
  summary: string
  urgency: string
  restricted: boolean
  register_number: number | null
  registered_at: string | null
  due_on: string | null
  created_by: string
  created_at: string
  files: { role: string; file: { id: string; filename: string; mime_type: string; size_bytes: number } | null }[]
  assignments: {
    id: string; parent_id: string | null; role: string; department: { name: string } | null; user_id: string | null
    instruction: string | null; due_on: string | null; status: string; result_note: string | null
    assigned_by: string; assigned_at: string; completed_at: string | null
  }[]
  events: { id: number; kind: string; actor_id: string; note: string | null; data: Record<string, any>; created_at: string }[]
}

const { t } = useI18n()
const { gql, download } = useApi()
const notice = useNotice()
const claims = useAuth().claims
const route = useRoute()

const doc = ref<Doc | null>(null)
const users = ref<PanelUser[]>([])
const departments = ref<PanelDepartment[]>([])
const task = ref<{ id: string; form_key: string } | null>(null)
const loading = ref(true)
const missing = ref(false)
const registering = ref(false)

const id = computed(() => String(route.params.id))
const nameOf = (uid: string | null) => users.value.find((u) => u.id === uid)?.full_name ?? (uid ? uid.slice(0, 8) : '')

async function load() {
  loading.value = true
  try {
    const data = await gql<{ office_documents_by_pk: Doc | null; core_users: PanelUser[]; office_departments: PanelDepartment[]; myTasks: { id: string; form_key: string; document_id: string }[] }>(`
      query ($id: uuid!) {
        office_documents_by_pk(id: $id) {
          id direction status type_code document_type { name } symbol issuer_name issued_on summary urgency restricted
          register_number registered_at due_on created_by created_at
          files(order_by: {added_at: asc}) { role file { id filename mime_type size_bytes } }
          assignments(order_by: {assigned_at: asc}) {
            id parent_id role department { name } user_id instruction due_on status result_note assigned_by assigned_at completed_at
          }
          events(order_by: {id: asc}) { id kind actor_id note data created_at }
        }
        core_users(order_by: {full_name: asc}) { id full_name role department_id }
        office_departments(order_by: {name: asc}) { id code name }
        myTasks { id form_key document_id }
      }`, { id: id.value })
    doc.value = data.office_documents_by_pk
    missing.value = !doc.value
    users.value = data.core_users
    departments.value = data.office_departments
    task.value = data.myTasks.find((x) => x.document_id === id.value) ?? null
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    loading.value = false
  }
}

async function register() {
  if (!confirm(t('doc.registerConfirm'))) return
  registering.value = true
  try {
    const data = await gql<{ registerIncoming: { register_number: number } }>(
      'mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }', { id: id.value },
    )
    notice.ok(t('receive.registered', { n: data.registerIncoming.register_number }))
    await load()
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    registering.value = false
  }
}

// Dòng thời gian: bước tiếp nhận lấy từ chính văn bản, các bước sau từ office.document_events
const timeline = computed(() => {
  if (!doc.value) return []
  const items = [{ key: 'received', title: t('event.received'), who: nameOf(doc.value.created_by), at: doc.value.created_at, note: null as string | null }]
  for (const e of doc.value.events) {
    const title = e.kind === 'office.document.registered'
      ? t('event.office.document.registered', { n: e.data.register_number })
      : e.kind === 'office.document.assigned'
        ? t('event.office.document.assigned', { name: nameOf(e.data.user_id) })
        : t(`event.${e.kind}`)
    let note = e.note
    if (e.kind === 'office.document.directed') {
      const lead = e.data.lead_department_id
        ? departments.value.find((d) => d.id === e.data.lead_department_id)?.name
        : nameOf(e.data.lead_user_id)
      note = [e.note, lead ? `${t('doc.lead')}: ${lead}` : '', e.data.due_on ? `${t('doc.due')}: ${fmtDate(e.data.due_on)}` : ''].filter(Boolean).join(' · ')
    }
    items.push({ key: String(e.id), title, who: nameOf(e.actor_id), at: e.created_at, note })
  }
  return items.reverse()
})

// Chủ trì trước, người được phân công ngay dưới phòng của họ, rồi phối hợp, để biết
const assignments = computed(() => {
  if (!doc.value) return []
  const all = doc.value.assignments
  const rank = (role: string) => (role === 'lead' ? 0 : role === 'support' ? 1 : 2)
  const roots = all.filter((a) => !a.parent_id).sort((a, b) => rank(a.role) - rank(b.role))
  return roots.flatMap((r) => [r, ...all.filter((c) => c.parent_id === r.id)])
})

watch(id, load)
onMounted(load)
</script>

<template>
  <div>
    <NuxtLink to="/van-ban-den" class="mb-4 inline-flex items-center gap-1 text-sm text-stone-500 hover:text-brand-800">← {{ t('app.back') }}</NuxtLink>

    <p v-if="loading && !doc" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <p v-else-if="missing" class="card p-8 text-center text-stone-500">{{ t('doc.notFound') }}</p>

    <div v-else-if="doc" class="space-y-6">
      <!-- tiêu đề -->
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
          <div class="mb-2 flex flex-wrap items-center gap-2">
            <StatusChip :status="doc.status" />
            <UrgencyChip :urgency="doc.urgency" quiet />
            <span v-if="doc.restricted" class="chip bg-stone-800 text-white">{{ t('doc.restricted') }}</span>
            <span class="text-sm text-stone-500">{{ doc.document_type?.name }}</span>
          </div>
          <h1 class="text-xl font-semibold text-stone-900">{{ doc.summary }}</h1>
          <p class="mt-1 text-sm text-stone-500">{{ doc.symbol }} · {{ doc.issuer_name }} · {{ fmtDate(doc.issued_on) }}</p>
        </div>
        <button v-if="claims?.role === 'clerk' && doc.status === 'received'" class="btn-primary" :disabled="registering" @click="register">
          {{ t('doc.register') }}
        </button>
      </div>

      <div class="grid gap-6 lg:grid-cols-3">
        <div class="space-y-6 lg:col-span-2">
          <TaskPanel
            v-if="task" :key="task.id" :task-id="task.id" :form-key="task.form_key" :document-due="doc.due_on"
            :users="users" :departments="departments" :my-department="claims?.departmentId ?? null" :my-id="claims?.userId ?? ''"
            @done="load"
          />

          <!-- thông tin -->
          <section class="card p-5">
            <h2 class="mb-4 text-sm font-semibold text-stone-800">{{ t('doc.info') }}</h2>
            <dl class="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              <div><dt class="text-stone-500">{{ t('doc.symbol') }}</dt><dd class="font-medium">{{ doc.symbol ?? '—' }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.issuedOn') }}</dt><dd class="font-medium">{{ fmtDate(doc.issued_on) }}</dd></div>
              <div class="sm:col-span-2"><dt class="text-stone-500">{{ t('doc.issuer') }}</dt><dd class="font-medium">{{ doc.issuer_name ?? '—' }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.number') }}</dt><dd class="font-medium tabular-nums">{{ doc.register_number ?? '—' }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.registered') }}</dt><dd class="font-medium">{{ fmtDateTime(doc.registered_at) }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.due') }}</dt><dd class="font-medium">{{ fmtDate(doc.due_on) }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.urgency') }}</dt><dd class="font-medium">{{ t(`urgency.${doc.urgency}`) }}</dd></div>
            </dl>
          </section>

          <!-- tệp -->
          <section class="card p-5">
            <h2 class="mb-3 text-sm font-semibold text-stone-800">{{ t('doc.files') }}</h2>
            <p v-if="!doc.files.length" class="text-sm text-stone-500">{{ t('doc.noFiles') }}</p>
            <ul v-else class="divide-y divide-stone-100">
              <li v-for="f in doc.files.filter((x) => x.file)" :key="f.file!.id" class="flex items-center gap-3 py-2 text-sm">
                <svg class="h-5 w-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M7 3h7l5 5v13H7a2 2 0 01-2-2V5a2 2 0 012-2zm7 0v5h5" /></svg>
                <span class="min-w-0 flex-1 truncate">{{ f.file!.filename }}</span>
                <span class="text-xs text-stone-500">{{ fmtSize(f.file!.size_bytes) }}</span>
                <button class="btn-ghost text-brand-800" @click="download(f.file!.id, f.file!.filename).catch((e) => notice.error(errorText(t, e)))">{{ t('doc.download') }}</button>
              </li>
            </ul>
          </section>

          <!-- giao xử lý -->
          <section v-if="doc.assignments.length" class="card p-5">
            <h2 class="mb-3 text-sm font-semibold text-stone-800">{{ t('doc.assignments') }}</h2>
            <ul class="space-y-3 text-sm">
              <li v-for="a in assignments" :key="a.id" class="flex gap-3" :class="{ 'ml-6': a.parent_id }">
                <span class="chip h-fit" :class="a.role === 'lead' ? 'bg-brand-100 text-brand-800' : 'bg-stone-100 text-stone-700'">
                  {{ a.role === 'lead' ? t('doc.lead') : a.role === 'support' ? t('doc.support') : t('doc.info_role') }}
                </span>
                <div class="min-w-0 flex-1">
                  <div class="font-medium">{{ a.department?.name ?? nameOf(a.user_id) }}</div>
                  <div v-if="a.instruction" class="text-stone-600">{{ a.instruction }}</div>
                  <div v-if="a.result_note" class="mt-1 rounded bg-emerald-50 px-2 py-1 text-emerald-900">{{ a.result_note }}</div>
                </div>
                <span class="h-fit text-xs" :class="a.status === 'done' ? 'text-emerald-700' : 'text-stone-500'">
                  {{ a.status === 'done' ? t('doc.assignmentDone') : t('doc.assignmentOpen') }}
                </span>
              </li>
            </ul>
          </section>
        </div>

        <!-- dòng thời gian -->
        <aside class="card h-fit p-5">
          <h2 class="mb-4 text-sm font-semibold text-stone-800">{{ t('doc.timeline') }}</h2>
          <ol class="relative space-y-5 border-l border-stone-200 pl-5">
            <li v-for="(item, i) in timeline" :key="item.key" class="relative">
              <span class="absolute top-1 -left-[25px] h-2.5 w-2.5 rounded-full ring-4 ring-white" :class="i === 0 ? 'bg-brand-600' : 'bg-stone-300'" />
              <div class="text-sm font-medium text-stone-900">{{ item.title }}</div>
              <div class="text-xs text-stone-500">{{ item.who }} · {{ fmtDateTime(item.at) }}</div>
              <p v-if="item.note" class="mt-1 text-sm text-stone-600">{{ item.note }}</p>
            </li>
          </ol>
        </aside>
      </div>
    </div>
  </div>
</template>
