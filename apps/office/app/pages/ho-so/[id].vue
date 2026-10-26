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
import type { ArchivePackage, ArchivedFile } from '~/composables/useApi'
import {
  STATUS_TONE, canArchive, canEdit, caseFileErrorText, fileableWhere, filesByDocument, hexOf, retainUntil,
} from '~/utils/caseFiles'
import type { CaseFileStatus } from '~/utils/caseFiles'

// Một hồ sơ công việc (F3.8). Hồ sơ mở: chuyên viên, lãnh đạo phòng thêm, gỡ văn bản, đóng hồ sơ (ngày đóng do CSDL
// đặt). Hồ sơ đã đóng: lãnh đạo phòng nộp lưu ngay (svc-files ghi gói Parquet + tệp + manifest có băm vào bucket lạnh
// khóa ghi), không thì hệ thống tự nộp lưu sau thời hạn cấu hình. Hồ sơ đã nộp lưu: phòng đọc — gói đọc lại từ bucket
// lạnh, so băm với CSDL; tệp PDF mở trong khung xem, bản có dấu tên người xem, giờ xem; mỗi lần mở ghi sổ kiểm toán.

interface DocRow {
  id: string
  direction: 'in' | 'out'
  status: string
  type_code: string
  symbol: string | null
  summary: string
  issued_on: string | null
}

interface CaseFile {
  id: string
  year: number
  code: string
  title: string
  status: CaseFileStatus
  retention_years: number | null
  closed_on: string | null
  archived_at: string | null
  archive_key: string | null
  archive_sha256: string | null
  department_id: string
  department: { name: string } | null
  case_file_documents: { document_id: string; document: DocRow | null }[]
}

const { t } = useI18n()
const { gql, archiveCaseFile, readingRoom, viewArchivedFile } = useApi()
const claims = useAuth().claims
const notice = useNotice()
const route = useRoute()
const id = computed(() => String(route.params.id))

const viewer = computed(() => ({
  role: claims.value?.role ?? null,
  departmentId: claims.value?.departmentId ?? null,
  userId: claims.value?.userId ?? '',
}))
const errorOf = (e: unknown) => caseFileErrorText(t, e, (x) => errorText(t, x))

const cf = ref<CaseFile | null>(null)
const loading = ref(true)
const failure = ref('')
const busy = ref('')   // thao tác đang chạy: close, archive, add:<id>, remove:<id>

const editable = computed(() => !!cf.value && canEdit(viewer.value, cf.value))
const archivable = computed(() => !!cf.value && canArchive(viewer.value, cf.value))
const sha = computed(() => hexOf(cf.value?.archive_sha256))

async function load() {
  loading.value = true
  failure.value = ''
  try {
    const data = await gql<{ office_case_files_by_pk: CaseFile | null }>(`
      query ($id: uuid!) {
        office_case_files_by_pk(id: $id) {
          id year code title status retention_years closed_on archived_at archive_key archive_sha256 department_id
          department { name }
          case_file_documents(order_by: {added_at: asc}) {
            document_id document { id direction status type_code symbol summary issued_on }
          }
        }
      }`, { id: id.value })
    cf.value = data.office_case_files_by_pk
    if (!cf.value) failure.value = t('cases.notFound')
    else if (cf.value.status === 'archived') void loadRoom()
    else if (editable.value) void loadCandidates()
  } catch (e) {
    failure.value = errorOf(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

// --- thêm, gỡ văn bản, đóng, nộp lưu ---------------------------------------------------------------------------

const candidates = ref<DocRow[]>([])
const candidatesLoading = ref(false)
const query = ref('')
let candidateSeq = 0

async function loadCandidates() {
  const mine = ++candidateSeq
  candidatesLoading.value = true
  try {
    const data = await gql<{ office_documents: DocRow[] }>(`
      query ($where: office_documents_bool_exp!) {
        office_documents(where: $where, order_by: [{issued_on: desc_nulls_last}, {id: asc}], limit: 50) {
          id direction status type_code symbol summary issued_on
        }
      }`, { where: fileableWhere(viewer.value, query.value) })
    // bỏ văn bản đã nằm trong hồ sơ (người dùng thấy được) — mỗi văn bản thuộc một hồ sơ
    const ids = data.office_documents.map((d) => d.id)
    const filed = ids.length ? await gql<{ office_case_file_documents: { document_id: string }[] }>(`
      query ($ids: [uuid!]!) { office_case_file_documents(where: {document_id: {_in: $ids}}) { document_id } }`,
    { ids }) : { office_case_file_documents: [] }
    const taken = new Set(filed.office_case_file_documents.map((r) => r.document_id))
    if (mine === candidateSeq) candidates.value = data.office_documents.filter((d) => !taken.has(d.id))
  } catch (e) {
    if (mine === candidateSeq) notice.error(errorOf(e))
  } finally {
    if (mine === candidateSeq) candidatesLoading.value = false
  }
}

async function run(action: string, work: () => Promise<void>) {
  busy.value = action
  try {
    await work()
  } catch (e) {
    notice.error(errorOf(e))
  } finally {
    busy.value = ''
  }
}

function addDocument(doc: DocRow) {
  return run(`add:${doc.id}`, async () => {
    await gql(`mutation ($o: office_case_file_documents_insert_input!) {
      insert_office_case_file_documents_one(object: $o) { document_id } }`,
    { o: { case_file_id: id.value, document_id: doc.id } })
    notice.ok(t('cases.added'))
    await load()
  })
}

function removeDocument(documentId: string) {
  if (!confirm(t('cases.removeConfirm'))) return
  return run(`remove:${documentId}`, async () => {
    await gql(`mutation ($cf: uuid!, $doc: uuid!) {
      delete_office_case_file_documents_by_pk(case_file_id: $cf, document_id: $doc) { document_id } }`,
    { cf: id.value, doc: documentId })
    notice.ok(t('cases.removed'))
    await load()
  })
}

function closeCaseFile() {
  if (!cf.value || !confirm(t('cases.closeConfirm', { code: cf.value.code }))) return
  const code = cf.value.code
  return run('close', async () => {
    await gql(`mutation ($id: uuid!) {
      update_office_case_files_by_pk(pk_columns: {id: $id}, _set: {status: "closed"}) { id } }`, { id: id.value })
    notice.ok(t('cases.closedOk', { code }))
    await load()
  })
}

function archiveNow() {
  if (!cf.value || !confirm(t('cases.archiveConfirm', { code: cf.value.code }))) return
  return run('archive', async () => {
    try {
      const done = await archiveCaseFile(id.value)
      notice.ok(t('cases.archivedOk', { code: done.code, documents: done.documents, files: done.files }))
    } finally {
      await load()   // lỗi giữa chừng (cổng hết giờ chờ) vẫn tải lại: lượt nộp lưu có thể đã xong ở máy chủ
    }
  })
}

// --- phòng đọc ---------------------------------------------------------------------------------------------------

const room = ref<ArchivePackage | null>(null)
const roomLoading = ref(false)
const roomError = ref('')
const filesOf = computed(() => filesByDocument(room.value?.files ?? []))
const viewing = ref('')
const viewerUrl = ref<string | null>(null)
const viewerName = ref('')

async function loadRoom() {
  roomLoading.value = true
  roomError.value = ''
  try {
    room.value = await readingRoom(id.value)
  } catch (e) {
    roomError.value = errorOf(e)
  } finally {
    roomLoading.value = false
  }
}

function closeViewer() {
  if (viewerUrl.value) URL.revokeObjectURL(viewerUrl.value)
  viewerUrl.value = null
  viewerName.value = ''
}

async function view(file: ArchivedFile) {
  viewing.value = file.file_id
  try {
    const url = await viewArchivedFile(id.value, file.file_id)
    closeViewer()
    viewerUrl.value = url
    viewerName.value = file.filename
  } catch (e) {
    notice.error(errorOf(e))
  } finally {
    viewing.value = ''
  }
}

onBeforeUnmount(closeViewer)

const retention = computed(() => {
  const c = cf.value
  if (!c) return ''
  return c.retention_years ? t('cases.retentionYears', { n: c.retention_years }) : t('cases.permanent')
})
const lockedUntil = computed(() => {
  const c = cf.value
  if (room.value) return fmtDate(room.value.retain_until)
  if (c?.closed_on) {
    return t('cases.retainUntilExpected', { date: fmtDate(retainUntil(c.closed_on, c.retention_years)) })
  }
  return '—'
})
</script>

<template>
  <div>
    <NuxtLink to="/ho-so" class="moc-back">
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
      </svg>
      {{ t('cases.back') }}
    </NuxtLink>

    <p v-if="loading && !cf" class="moc-loading">{{ t('app.loading') }}</p>
    <div v-else-if="failure" class="moc-state" data-testid="case-file-error">
      <span>{{ failure }}</span>
      <button class="btn-secondary" @click="load()">{{ t('app.retry') }}</button>
    </div>
    <template v-else-if="cf">
      <PageHeader :title="cf.title" :subtitle="`${cf.code} · ${cf.year} · ${cf.department?.name ?? ''}`">
        <span class="chip" :class="STATUS_TONE[cf.status]" data-testid="case-file-status">
          {{ t(`cases.status.${cf.status}`) }}
        </span>
        <button
          v-if="editable" class="btn-secondary" :disabled="!!busy || !cf.case_file_documents.length"
          data-testid="case-file-close" @click="closeCaseFile"
        >
          {{ t('cases.close') }}
        </button>
        <button
          v-if="archivable" class="btn-primary" :disabled="!!busy" data-testid="case-file-archive"
          @click="archiveNow"
        >
          {{ busy === 'archive' ? t('cases.archiving') : t('cases.archive') }}
        </button>
      </PageHeader>

      <div class="moc-stack">
        <section class="moc-block" data-testid="case-file-info">
          <h2 class="moc-block-title mb-3">{{ t('cases.info') }}</h2>
          <dl class="moc-facts">
            <div>
              <dt>{{ t('cases.department') }}</dt>
              <dd>{{ cf.department?.name ?? '—' }}</dd>
            </div>
            <div><dt>{{ t('cases.retention') }}</dt><dd>{{ retention }}</dd></div>
            <div><dt>{{ t('cases.closedOn') }}</dt><dd class="tabular-nums">{{ fmtDate(cf.closed_on) }}</dd></div>
            <div>
              <dt>{{ t('cases.archiveStatus') }}</dt>
              <dd v-if="cf.archived_at">{{ t('cases.status.archived') }} · {{ fmtDateTime(cf.archived_at) }}</dd>
              <dd v-else>{{ t('cases.notArchived') }}</dd>
            </div>
            <div>
              <dt>{{ t('cases.retainUntil') }}</dt>
              <dd data-testid="case-file-retain">{{ lockedUntil }}</dd>
            </div>
            <div v-if="cf.archive_key" class="is-wide">
              <dt>{{ t('cases.archiveKey') }}</dt>
              <dd class="font-mono text-xs break-all">{{ cf.archive_key }}</dd>
            </div>
            <div v-if="sha" class="is-wide">
              <dt>{{ t('cases.manifestSha') }}</dt>
              <dd class="font-mono text-xs break-all" data-testid="case-file-sha">{{ sha }}</dd>
            </div>
          </dl>
          <p v-if="editable" class="moc-foot">{{ t('cases.closeHint') }}</p>
          <p v-if="cf.status === 'closed'" class="moc-foot">{{ t('cases.archiveHint') }}</p>
        </section>

        <section class="moc-block" data-testid="case-file-documents">
          <h2 class="moc-block-title mb-1">{{ t('cases.inCase') }}</h2>
          <p v-if="!cf.case_file_documents.length" class="moc-empty">{{ t('cases.noDocuments') }}</p>
          <div v-else class="moc-scroll">
            <table class="moc-table">
              <thead>
                <tr>
                  <th>{{ t('outgoing.symbol') }}</th>
                  <th>{{ t('outgoing.summary') }}</th>
                  <th>{{ t('outgoing.status') }}</th>
                  <th>{{ t('outgoing.issuedOn') }}</th>
                  <th v-if="editable"><span class="sr-only">{{ t('cases.remove') }}</span></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="link in cf.case_file_documents" :key="link.document_id">
                  <template v-if="link.document">
                    <td class="whitespace-nowrap">
                      <div class="font-medium">{{ link.document.symbol ?? '—' }}</div>
                      <div class="text-[13px] text-stone-500">
                        {{ t(`search.direction.${link.document.direction}`) }} · {{ link.document.type_code }}
                      </div>
                    </td>
                    <td class="min-w-60">
                      <NuxtLink
                        :to="`/van-ban/${link.document.id}`"
                        class="moc-doc-title"
                      >
                        {{ link.document.summary }}
                      </NuxtLink>
                    </td>
                    <td><StatusChip :status="link.document.status" /></td>
                    <td class="whitespace-nowrap text-stone-600">{{ fmtDate(link.document.issued_on) }}</td>
                  </template>
                  <td v-else colspan="4" class="text-stone-500 italic">{{ t('cases.hidden') }}</td>
                  <td v-if="editable" class="text-right">
                    <button
                      class="btn-ghost min-h-9 text-red-700 hover:bg-red-50" :disabled="!!busy"
                      @click="removeDocument(link.document_id)"
                    >
                      {{ t('cases.remove') }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="editable" class="moc-block" data-testid="case-file-add">
          <h2 class="moc-block-title">{{ t('cases.add') }}</h2>
          <p class="moc-block-hint">{{ t('cases.addHint') }}</p>
          <form class="mt-4 flex gap-2" @submit.prevent="loadCandidates">
            <input v-model="query" class="input" :aria-label="t('cases.search')" :placeholder="t('cases.search')">
            <button type="submit" class="btn-secondary">{{ t('search.button') }}</button>
          </form>
          <p v-if="candidatesLoading && !candidates.length" class="moc-loading mt-3">{{ t('app.loading') }}</p>
          <p v-else-if="!candidates.length" class="moc-empty" data-testid="case-file-no-candidates">
            {{ t('cases.noCandidates') }}
          </p>
          <ul v-else class="moc-rows mt-4">
            <li v-for="doc in candidates" :key="doc.id" class="flex items-center gap-3 text-sm">
              <div class="min-w-0 flex-1">
                <div class="font-medium">
                  {{ doc.symbol ?? '—' }}
                  <span class="text-[13px] font-normal text-stone-500">
                    · {{ t(`search.direction.${doc.direction}`) }} · {{ fmtDate(doc.issued_on) }}
                  </span>
                </div>
                <div class="truncate text-stone-600">{{ doc.summary }}</div>
              </div>
              <button class="btn-secondary" :disabled="!!busy" @click="addDocument(doc)">
                {{ busy === `add:${doc.id}` ? t('app.loading') : t('cases.addOne') }}
              </button>
            </li>
          </ul>
        </section>

        <section v-if="cf.status === 'archived'" class="moc-block" data-testid="reading-room">
          <h2 class="moc-block-title">{{ t('cases.room.title') }}</h2>
          <p class="moc-block-hint">{{ t('cases.room.subtitle') }}</p>
          <p v-if="roomLoading" class="moc-loading mt-3">{{ t('cases.room.loading') }}</p>
          <div v-else-if="roomError" class="moc-state mt-3">
            <span>{{ roomError }}</span>
            <button class="btn-secondary" @click="loadRoom">{{ t('app.retry') }}</button>
          </div>
          <template v-else-if="room">
            <p
              class="mt-4 flex items-start gap-2 rounded-lg bg-brand-50 px-3.5 py-3 text-sm text-brand-900"
              data-testid="reading-room-verified"
            >
              <svg
                class="mt-0.5 h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"
                stroke-width="2.5" aria-hidden="true"
              >
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              <span class="min-w-0">
                {{ t('cases.room.verified') }} —
                <span class="font-mono text-xs break-all">{{ room.manifest_sha256 }}</span>
              </span>
            </p>
            <ul class="moc-rows mt-4">
              <li v-for="doc in room.documents" :key="doc.id" class="text-sm">
                <div class="font-medium">
                  {{ doc.symbol ?? '—' }}
                  <span class="text-[13px] font-normal text-stone-500">
                    · {{ t(`search.direction.${doc.direction}`) }} · {{ fmtDate(doc.issued_on) }}
                  </span>
                </div>
                <div class="text-stone-700 wrap-anywhere">{{ doc.summary }}</div>
                <p v-if="!filesOf.get(doc.id)?.length" class="mt-1 text-[13px] text-stone-500">
                  {{ t('cases.room.noFiles') }}
                </p>
                <ul v-else class="mt-2 space-y-1">
                  <li
                    v-for="file in filesOf.get(doc.id)" :key="file.file_id"
                    class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-stone-600"
                  >
                    <span class="min-w-0 font-medium text-stone-800 wrap-anywhere">{{ file.filename }}</span>
                    <span class="tabular-nums">{{ fmtSize(file.bytes) }}</span>
                    <span class="font-mono text-xs" :title="file.sha256">{{ file.sha256.slice(0, 16) }}…</span>
                    <button
                      v-if="file.viewable" class="btn-ghost min-h-9 px-2 py-1 text-brand-800" :disabled="!!viewing"
                      :data-testid="`view-${file.file_id}`" @click="view(file)"
                    >
                      {{ viewing === file.file_id ? t('cases.room.viewing') : t('cases.room.view') }}
                    </button>
                    <span v-else class="text-stone-500">{{ t('cases.room.notViewable') }}</span>
                  </li>
                </ul>
              </li>
            </ul>
            <p v-if="room.hidden" class="moc-foot">{{ t('cases.room.hidden', { n: room.hidden }) }}</p>

            <div
              v-if="viewerUrl" class="mt-5 overflow-hidden rounded-lg border border-stone-200"
              data-testid="reading-room-viewer"
            >
              <div class="flex flex-wrap items-center gap-3 border-b border-stone-200 bg-stone-50 px-4 py-2 text-sm">
                <span class="min-w-0 flex-1 truncate font-medium">
                  {{ t('cases.room.viewer', { name: viewerName }) }}
                </span>
                <a :href="viewerUrl" target="_blank" rel="noopener" class="text-brand-800 hover:underline">
                  {{ t('cases.room.newTab') }}
                </a>
                <button class="btn-ghost" @click="closeViewer">{{ t('cases.room.closeViewer') }}</button>
              </div>
              <iframe :src="viewerUrl" :title="t('cases.room.viewer', { name: viewerName })" class="h-[75vh] w-full" />
              <p class="border-t border-stone-200 px-4 py-2 text-xs text-stone-500">{{ t('cases.room.stampNote') }}</p>
            </div>
          </template>
        </section>
      </div>
    </template>
  </div>
</template>
