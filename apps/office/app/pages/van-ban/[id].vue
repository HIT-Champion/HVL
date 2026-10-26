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
import type { PanelDepartment, PanelUser } from '~/components/TaskPanel.vue'
import { askAbout, canAskAbout } from '~/utils/answer'
import { documentBackTarget, processingBrief } from '~/utils/taskContext'

// Chi tiết văn bản đến hoặc đi: thông tin, tệp, giao xử lý, dòng thời gian (F2.6), lịch sử thay đổi (F3.5) và
// khung xử lý việc đang chờ người dùng. Văn bản đi có thêm nội dung, nơi nhận, người ký, bản xem trước, trình ký và mã xác thực.
// Hasura chỉ trả văn bản người dùng được đọc — không thấy thì báo "không tìm thấy".
// Liên thông trong hệ thống (F3.12): văn bản đi gửi đơn vị khác cùng dùng Signet có thẻ trạng thái chuyển từng đơn vị;
// văn bản đến nhận theo đường này có thẻ "Nhận từ …" với mã xác thực của bên gửi và đối chiếu SHA-256 tệp.
// Nút "Hỏi về văn bản này" (F4.2) mở trang Hỏi đáp chỉ hỏi trong văn bản này — chỉ khi văn bản có trong kho của trợ lý.

interface Dispatch {
  id: string
  to_tenant_id: string
  status: string            // pending | delivered | duplicate | failed
  attempts: number
  last_error: string | null
  delivered_at: string | null
  to_unit: { name: string } | null
}

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
  body: string | null
  recipients: string[]
  signer_id: string | null
  verify_code: string | null
  source_id: string | null
  recipient_tenant_ids: string[]
  department: { name: string } | null
  reply_to: { id: string; symbol: string | null; summary: string } | null
  files: { role: string; file: { id: string; filename: string; mime_type: string; size_bytes: number; encrypted: boolean; sha256: string } | null }[]
  assignments: {
    id: string; parent_id: string | null; role: string; department: { name: string } | null; user_id: string | null
    instruction: string | null; due_on: string | null; status: string; result_note: string | null
    assigned_by: string; assigned_at: string; completed_at: string | null
  }[]
  events: DocEvent[]
  dispatches: Dispatch[]
  dispatch_in: { source_verify_code: string; source_sha256: string; from_unit: { name: string } | null } | null
}
interface DocEvent { id: number; kind: string; actor_id: string; actor_kind: string; note: string | null; data: Record<string, any>; created_at: string }

const { t } = useI18n()
const { gql, download, preview } = useApi()
const notice = useNotice()
const claims = useAuth().claims
const route = useRoute()

const doc = ref<Doc | null>(null)
const users = ref<PanelUser[]>([])
const departments = ref<PanelDepartment[]>([])
const units = ref<{ id: string; name: string }[]>([])   // đơn vị khác trong hệ thống (liên thông)
const task = ref<{ id: string; form_key: string } | null>(null)
const loading = ref(true)
const missing = ref(false)
const failure = ref('')
const registering = ref(false)
const submitting = ref(false)
const signer = ref('')

const id = computed(() => String(route.params.id))
// mở từ hộp việc (?from=inbox): quay lại hộp việc; chuyên viên thấy phần việc của mình ngay trong khung báo kết quả
const backTarget = computed(() => documentBackTarget(route.query.from, doc.value?.direction))
const brief = computed(() => processingBrief(doc.value?.assignments ?? [], claims.value?.userId, doc.value?.due_on))

// Lịch sử (F3.5): các dòng sổ kiểm toán về văn bản — ai sửa gì, lúc nào — cho mọi người đọc được văn bản. Tải khi mở
// tab; cột nội dung (trích yếu, tên tệp…) chỉ báo là đã đổi, như màn Sổ kiểm toán.
interface HistoryRow {
  id: number
  occurred_at: string
  actor_id: string
  actor_kind: string
  action: string
  entity: string
  overview: Record<string, unknown>
}
const side = ref<'timeline' | 'history'>('timeline')
const history = ref<HistoryRow[] | null>(null)
const historyLoading = ref(false)
const historyFailure = ref('')
// hai tab Dòng thời gian / Lịch sử theo mẫu tab của WAI-ARIA: mũi tên trái phải, Home, End chuyển tab và đưa tiêu điểm
const timelineTab = ref<HTMLButtonElement | null>(null)
const historyTab = ref<HTMLButtonElement | null>(null)
function sideKey(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const other = side.value === 'timeline' ? 'history' : 'timeline'
  const next = event.key === 'Home' ? 'timeline' : event.key === 'End' ? 'history' : other
  if (next === 'history') void openHistory()
  else side.value = 'timeline'
  nextTick(() => (next === 'history' ? historyTab.value : timelineTab.value)?.focus())
}
const userNames = computed(() => new Map(users.value.map((u) => [u.id, u.full_name])))
const departmentNames = computed(() => new Map(departments.value.map((d) => [d.id, d.name])))
const unitNames = computed(() => new Map(units.value.map((u) => [u.id, u.name])))
const { label, action, who, changes } = useAuditFormat(userNames, departmentNames, unitNames)

async function openHistory() {
  side.value = 'history'
  historyLoading.value = true
  historyFailure.value = ''
  const want = id.value      // đổi sang văn bản khác giữa chừng: bỏ kết quả của văn bản cũ
  try {
    const data = await gql<{ office_document_history: HistoryRow[] }>(`
      query ($id: uuid!) {
        office_document_history(where: {document_id: {_eq: $id}}, order_by: {id: desc}) {
          id occurred_at actor_id actor_kind action entity overview
        }
      }`, { id: want })
    if (want === id.value) history.value = data.office_document_history
  } catch (e) {
    // báo lỗi ngay trong tab, kèm nút thử lại, thay vì một thông báo nổi tự tắt
    if (want === id.value) historyFailure.value = errorText(t, e)
  } finally {
    if (want === id.value) historyLoading.value = false
  }
}
const nameOf = (uid: string | null) => users.value.find((u) => u.id === uid)?.full_name ?? (uid ? uid.slice(0, 8) : '')
const unitName = (tid: string) => unitNames.value.get(tid) ?? tid.slice(0, 8)

const EVENT_FIELDS = 'id kind actor_id actor_kind note data created_at'
const DISPATCH_FIELDS = 'id to_tenant_id status attempts last_error delivered_at to_unit { name }'

// Liên thông (F3.12): phát hành xong, svc-workflow chuyển văn bản sang từng đơn vị nhận ngay sau đó (lỗi thì tự thử
// lại). Bên nhận không báo ngược lại cho bên gửi, nên còn dòng "đang chuyển" thì hỏi lại trạng thái (và dòng thời
// gian) 5 giây một lần, tối đa 2 phút; quá thế thì tải lại trang để xem
let dispatchTimer: ReturnType<typeof setTimeout> | null = null
let dispatchPolls = 0
function followDispatches() {
  if (dispatchTimer) clearTimeout(dispatchTimer)
  dispatchTimer = null
  if (!doc.value?.dispatches.some((d) => d.status === 'pending') || dispatchPolls >= 24) return
  dispatchTimer = setTimeout(refreshDispatches, 5_000)
}
async function refreshDispatches() {
  dispatchPolls += 1
  const want = id.value
  try {
    const data = await gql<{ office_documents_by_pk: Pick<Doc, 'dispatches' | 'events'> | null }>(`
      query ($id: uuid!) {
        office_documents_by_pk(id: $id) {
          dispatches(order_by: {created_at: asc}) { ${DISPATCH_FIELDS} }
          events(order_by: {id: asc}) { ${EVENT_FIELDS} }
        }
      }`, { id: want })
    const fresh = data.office_documents_by_pk
    if (fresh && doc.value && want === id.value) Object.assign(doc.value, fresh)
  } catch {
    // mạng chập chờn: lần hỏi sau thử lại
  }
  followDispatches()
}
onBeforeUnmount(() => { if (dispatchTimer) clearTimeout(dispatchTimer) })

// Thông báo realtime của văn bản và nút thao tác (phát hành, vào sổ…) có thể cùng gọi load(): lượt cũ về sau không
// được đè lượt mới — không thì văn bản vừa phát hành hiện lại "Đã duyệt" và thẻ liên thông thôi hỏi lại
let seq = 0
async function load() {
  const mine = ++seq
  loading.value = true
  failure.value = ''
  try {
    const data = await gql<{
      office_documents_by_pk: Doc | null; core_users: PanelUser[]; office_departments: PanelDepartment[]
      office_dispatch_units: { id: string; name: string }[]; myTasks: { id: string; form_key: string; document_id: string }[]
    }>(`
      query ($id: uuid!) {
        office_documents_by_pk(id: $id) {
          id direction status type_code document_type { name } symbol issuer_name issued_on summary urgency restricted
          register_number registered_at due_on created_by created_at body recipients signer_id verify_code
          source_id recipient_tenant_ids
          department { name } reply_to { id symbol summary }
          files(order_by: {added_at: asc}) { role file { id filename mime_type size_bytes encrypted sha256 } }
          assignments(order_by: {assigned_at: asc}) {
            id parent_id role department { name } user_id instruction due_on status result_note assigned_by assigned_at completed_at
          }
          events(order_by: {id: asc}) { ${EVENT_FIELDS} }
          dispatches(order_by: {created_at: asc}) { ${DISPATCH_FIELDS} }
          dispatch_in { source_verify_code source_sha256 from_unit { name } }
        }
        core_users(order_by: {full_name: asc}) { id full_name role department_id }
        office_departments(order_by: {name: asc}) { id code name }
        office_dispatch_units(order_by: {name: asc}) { id name }
        myTasks { id form_key document_id }
      }`, { id: id.value })
    if (mine !== seq) return
    doc.value = data.office_documents_by_pk
    missing.value = !doc.value
    users.value = data.core_users
    departments.value = data.office_departments
    units.value = data.office_dispatch_units
    dispatchPolls = 0
    followDispatches()
    // bước "sửa dự thảo" làm bằng nút Trình lại ở dưới, không hiện khung xử lý riêng
    task.value = data.myTasks.find((x) => x.document_id === id.value && x.form_key !== 'vbdi.chinhSua') ?? null
    signer.value = doc.value?.signer_id ?? directors.value[0]?.id ?? ''
    // tab Lịch sử đang mở: thao tác vừa xong (vào sổ, trình ký, xử lý) có dòng sổ mới
    if (side.value === 'history') void openHistory()
    viewers.value = null
    if (doc.value?.restricted && canManageViewers.value) void loadViewers()
  } catch (e) {
    if (mine !== seq) return
    // lần đầu chưa có gì để hiện: báo lỗi ngay trên trang thay vì để trang trắng
    if (doc.value) notice.error(errorText(t, e))
    else failure.value = errorText(t, e)
  } finally {
    if (mine === seq) loading.value = false
  }
}

// Văn bản hạn chế (F3.7): văn thư, lãnh đạo đơn vị đang đọc được văn bản thì xem và sửa danh sách người được xem
// (hàm office.grant_document_access / revoke_document_access kiểm lại vai trò, thuê ước, quyền đọc)
interface Viewer { user_id: string; granted_by: string; granted_at: string }
const viewers = ref<Viewer[] | null>(null)
const viewerPick = ref('')
const viewerBusy = ref(false)
const canManageViewers = computed(() => ['clerk', 'director'].includes(claims.value?.role ?? ''))
const viewerChoices = computed(() => users.value.filter((u) => u.role !== 'tenant_admin' && u.id !== doc.value?.created_by
  && !viewers.value?.some((v) => v.user_id === u.id)))

async function loadViewers() {
  const want = id.value
  try {
    const data = await gql<{ office_document_acl: Viewer[] }>(`
      query ($id: uuid!) {
        office_document_acl(where: {document_id: {_eq: $id}}, order_by: {granted_at: asc}) { user_id granted_by granted_at }
      }`, { id: want })
    if (want === id.value) viewers.value = data.office_document_acl
  } catch (e) {
    notice.error(errorText(t, e))
  }
}

async function changeViewer(userId: string, grant: boolean) {
  viewerBusy.value = true
  try {
    const fn = grant ? 'office_grant_document_access' : 'office_revoke_document_access'
    await gql(`mutation ($d: uuid!, $u: String!) { ${fn}(args: {document_id: $d, user_id: $u}) { user_id } }`,
      { d: id.value, u: userId })
    notice.ok(t(grant ? 'doc.viewerGranted' : 'doc.viewerRevoked', { name: nameOf(userId) }))
    viewerPick.value = ''
    await loadViewers()
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    viewerBusy.value = false
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

const outgoing = computed(() => doc.value?.direction === 'out')
const directors = computed(() => users.value.filter((u) => u.role === 'director'))
// Người soạn sửa, trình được khi dự thảo còn ở bước đầu hoặc bị trả lại
const canEdit = computed(() => outgoing.value && claims.value?.role === 'staff' && doc.value?.created_by === claims.value?.userId
  && ['draft', 'returned'].includes(doc.value?.status ?? ''))
const lastReturn = computed(() => [...(doc.value?.events ?? [])].reverse().find((e) => e.kind === 'office.document.returned')?.note ?? '')
const issuedFile = computed(() => doc.value?.files.find((f) => f.role === 'issued')?.file ?? null)
const verifyCode = computed(() => fmtVerifyCode(doc.value?.verify_code))

// Văn bản đi gửi trong hệ thống: chưa phát hành thì là danh sách sẽ gửi, phát hành rồi thì trạng thái từng đơn vị
const dispatches = computed(() => doc.value?.dispatches ?? [])
const DISPATCH_TONE: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800',
  delivered: 'bg-emerald-100 text-emerald-800',
  duplicate: 'bg-sky-100 text-sky-800',
  failed: 'bg-rose-100 text-rose-800',
}
// Văn bản đến nhận liên thông: tệp chính (bản sao của bản phát hành) phải cùng SHA-256 với bản bên gửi đã phát hành.
// null: không còn tệp để so (vd đã nộp lưu), hoặc văn bản do văn thư tiếp nhận tay mà lần liên thông chỉ nối vào
// (trùng — không có source_id): tệp là bản scan của văn thư, khác băm là đương nhiên
const sourceMatch = computed(() => {
  const main = doc.value?.files.find((f) => f.role === 'main')?.file
  return doc.value?.dispatch_in && doc.value.source_id && main
    ? sameSha256(main.sha256, doc.value.dispatch_in.source_sha256) : null
})

async function submit() {
  if (!signer.value) return
  submitting.value = true
  try {
    await gql('mutation ($d: uuid!, $s: String!) { submitOutgoing(documentId: $d, signerId: $s) { status } }',
      { d: id.value, s: signer.value })
    notice.ok(t('doc.submitted'))
    await load()
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    submitting.value = false
  }
}

function showPreview() {
  preview(id.value).catch((e) => notice.error(errorText(t, e)))
}

function eventTitle(e: DocEvent): string {
  switch (e.kind) {
    case 'office.document.registered': return t('event.office.document.registered', { n: e.data.register_number })
    case 'office.document.assigned': return t('event.office.document.assigned', { name: nameOf(e.data.user_id) })
    case 'office.document.numbered': return t('event.office.document.numbered', { symbol: e.data.symbol })
    case 'office.task.overdue':
    case 'office.task.escalated': return t(`event.${e.kind}`, { task: t(`task.${e.data.form_key}`) })
    case 'office.document.overdue': return t('event.office.document.overdue', { due: fmtDate(e.data.due_on) })
    case 'ot.alarm':
      return t('event.ot.alarm', { name: e.data.name, value: fmtNumber(e.data.temperature), threshold: fmtNumber(e.data.threshold) })
    // liên thông (F3.12): bên gửi ghi tên đơn vị nhận, bên nhận ghi tên đơn vị gửi
    case 'office.document.dispatched':
    case 'office.document.dispatch_duplicate': return t(`event.${e.kind}`, { name: e.data.to_name ?? '' })
    case 'office.document.arrived': return t('event.office.document.arrived', { name: e.data.from_name ?? '' })
    default: return t(`event.${e.kind}`)
  }
}

// Dòng thời gian: bước đầu (tiếp nhận / tạo dự thảo) lấy từ chính văn bản, các bước sau từ office.document_events.
// Văn bản đến nhận liên thông do dịch vụ tạo: bước đầu là sự kiện "nhận liên thông", không thêm bước "tiếp nhận"
const timeline = computed(() => {
  if (!doc.value) return []
  const first = outgoing.value ? t('event.drafted') : t('event.received')
  const items: { key: string; title: string; who: string; at: string; note: string | null }[] = doc.value.source_id
    ? []
    : [{ key: 'first', title: first, who: nameOf(doc.value.created_by), at: doc.value.created_at, note: null }]
  for (const e of doc.value.events) {
    const title = eventTitle(e)
    let note = e.note
    if (e.kind === 'office.document.arrived' && e.data.verify_code) {
      note = t('event.sourceCode', { code: fmtVerifyCode(e.data.verify_code) })
    }
    // nhắc hạn do hệ thống gửi: ghi ai đã được báo
    if (Array.isArray(e.data.notified) && e.data.notified.length) {
      note = t('event.notified', { names: e.data.notified.map(nameOf).join(', ') })
    }
    if (e.kind === 'office.document.directed') {
      const lead = e.data.lead_department_id
        ? departments.value.find((d) => d.id === e.data.lead_department_id)?.name
        : nameOf(e.data.lead_user_id)
      note = [e.note, lead ? `${t('doc.lead')}: ${lead}` : '', e.data.due_on ? `${t('doc.due')}: ${fmtDate(e.data.due_on)}` : ''].filter(Boolean).join(' · ')
    }
    items.push({ key: String(e.id), title, who: e.actor_kind === 'service' ? t('event.system') : nameOf(e.actor_id), at: e.created_at, note })
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

watch(id, () => {
  side.value = 'timeline'
  historyFailure.value = ''
  historyLoading.value = false
  history.value = null      // lịch sử của văn bản trước: không hiện nhầm trong lúc tải
  load()
})
onMounted(load)

// có người vừa làm một bước với văn bản này (F2.5): tải lại để thấy trạng thái, việc và dòng thời gian mới
const { lastPush } = useNotifications()
watch(lastPush, (n) => { if (n?.document_id === id.value) load() })
</script>

<template>
  <div>
    <NuxtLink :to="backTarget" class="mb-4 inline-flex items-center gap-1 text-sm text-stone-500 hover:text-brand-800">
      ← {{ t(route.query.from === 'inbox' ? 'fe.backInbox' : 'app.back') }}
    </NuxtLink>

    <p v-if="loading && !doc" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <p v-else-if="missing" class="card p-8 text-center text-stone-500">{{ t('doc.notFound') }}</p>
    <div v-else-if="failure" class="card flex flex-col items-center gap-3 p-8 text-center text-sm text-red-700" data-testid="doc-failure">
      {{ failure }}
      <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.retry') }}</button>
    </div>

    <div v-else-if="doc" class="space-y-6">
      <!-- tiêu đề -->
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
          <div class="mb-2 flex flex-wrap items-center gap-2">
            <StatusChip :status="doc.status" />
            <UrgencyChip :urgency="doc.urgency" quiet />
            <span v-if="doc.restricted" class="chip bg-stone-800 text-white">{{ t('doc.restricted') }}</span>
            <span v-if="doc.source_id" class="chip bg-brand-100 text-brand-800" data-testid="dispatched-chip">{{ t('incoming.dispatched') }}</span>
            <span class="text-sm text-stone-500">{{ doc.document_type?.name }}</span>
          </div>
          <h1 class="text-xl font-semibold text-stone-900">{{ doc.summary }}</h1>
          <p v-if="outgoing" class="mt-1 text-sm text-stone-500">
            {{ doc.symbol ?? t('doc.draft') }} · {{ doc.department?.name }}<span v-if="doc.issued_on"> · {{ fmtDate(doc.issued_on) }}</span>
          </p>
          <p v-else class="mt-1 text-sm text-stone-500">{{ doc.symbol }} · {{ doc.issuer_name }} · {{ fmtDate(doc.issued_on) }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            v-if="claims?.role === 'clerk' && doc.status === 'received'" class="btn-primary" :disabled="registering"
            :aria-busy="registering" @click="register"
          >
            {{ registering ? t('doc.registering') : t('doc.register') }}
          </button>
          <NuxtLink v-if="canEdit" :to="`/van-ban-di/soan?id=${doc.id}`" class="btn-secondary">{{ t('doc.edit') }}</NuxtLink>
          <NuxtLink
            v-if="canAskAbout(doc, claims?.role)" :to="askAbout(doc.id)" class="btn-secondary" data-testid="ask-about"
          >
            {{ t('doc.askAbout') }}
          </NuxtLink>
          <button v-if="outgoing && !issuedFile" class="btn-secondary" @click="showPreview">{{ t('doc.preview') }}</button>
          <button v-if="issuedFile" class="btn-primary" @click="download(issuedFile.id, issuedFile.filename).catch((e) => notice.error(errorText(t, e)))">
            {{ t('doc.download') }} {{ t('doc.fileRole.issued').toLowerCase() }}
          </button>
        </div>
      </div>

      <div class="grid gap-6 lg:grid-cols-3">
        <div class="space-y-6 lg:col-span-2">
          <TaskPanel
            v-if="task" :key="task.id" :task-id="task.id" :form-key="task.form_key" :document-due="doc.due_on"
            :document-id="doc.id" :restricted="doc.restricted" :users="users" :departments="departments"
            :my-department="claims?.departmentId ?? null" :my-id="claims?.userId ?? ''" :brief="brief" @done="load"
          />

          <!-- trình dự thảo: lần đầu, hoặc trình lại sau khi bị trả lại -->
          <section v-if="canEdit" class="card overflow-hidden border-brand-200 ring-2 ring-brand-100">
            <div class="border-b border-brand-100 bg-brand-50 px-5 py-3">
              <h2 class="text-sm font-semibold text-brand-900">{{ t('doc.submitTitle') }}</h2>
            </div>
            <form class="space-y-4 p-5" @submit.prevent="submit">
              <p v-if="doc.status === 'returned' && lastReturn" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-900">
                {{ t('doc.returnedHint', { note: lastReturn }) }}
              </p>
              <p class="text-sm text-stone-600">{{ t('doc.submitHint') }}</p>
              <div class="max-w-sm">
                <label class="label" for="signer">{{ t('doc.signerPick') }}</label>
                <select id="signer" v-model="signer" class="input">
                  <option v-for="u in directors" :key="u.id" :value="u.id">{{ u.full_name }}</option>
                </select>
              </div>
              <div class="flex justify-end border-t border-stone-100 pt-4">
                <button type="submit" class="btn-primary" :disabled="submitting || !signer">
                  {{ doc.status === 'returned' ? t('doc.resubmit') : t('doc.submit') }}
                </button>
              </div>
            </form>
          </section>

          <!-- mã xác thực của văn bản đã phát hành -->
          <section v-if="outgoing && doc.verify_code && issuedFile" class="card flex flex-wrap items-center justify-between gap-3 p-5">
            <div>
              <div class="text-sm text-stone-500">{{ t('doc.verifyCode') }}</div>
              <div class="font-mono text-lg font-semibold tracking-wider text-stone-900" data-testid="verify-code">{{ verifyCode }}</div>
            </div>
            <a :href="`/xac-thuc/${doc.verify_code}`" target="_blank" rel="noopener" class="btn-secondary">{{ t('doc.verifyOpen') }} ↗</a>
          </section>

          <!-- gửi trong hệ thống (F3.12): chưa phát hành thì là danh sách sẽ gửi, phát hành rồi thì trạng thái từng đơn vị -->
          <section v-if="outgoing && (dispatches.length || doc.recipient_tenant_ids.length)" class="card p-5" data-testid="dispatch">
            <h2 class="mb-1 text-sm font-semibold text-stone-800">{{ t('doc.dispatch.title') }}</h2>
            <p class="mb-3 text-xs text-stone-500">{{ dispatches.length ? t('doc.dispatch.sentHint') : t('doc.dispatch.plannedHint') }}</p>
            <ul v-if="dispatches.length" class="divide-y divide-stone-100">
              <li v-for="d in dispatches" :key="d.id" class="flex items-start gap-3 py-2 text-sm">
                <span class="min-w-0 flex-1">
                  <span class="font-medium">{{ d.to_unit?.name ?? unitName(d.to_tenant_id) }}</span>
                  <span v-if="d.delivered_at" class="block text-xs text-stone-500">{{ t('doc.dispatch.deliveredAt', { at: fmtDateTime(d.delivered_at) }) }}</span>
                  <span v-if="d.status === 'duplicate'" class="block text-xs text-stone-500">{{ t('doc.dispatch.duplicateHint') }}</span>
                  <span v-if="d.last_error && d.status === 'pending'" class="block text-xs text-amber-800">{{ t('doc.dispatch.retrying', { n: d.attempts, error: d.last_error }) }}</span>
                  <span v-else-if="d.last_error && d.status === 'failed'" class="block text-xs text-rose-700">{{ d.last_error }}</span>
                </span>
                <span class="chip" :class="DISPATCH_TONE[d.status] ?? 'bg-stone-100 text-stone-700'">{{ t(`doc.dispatch.status.${d.status}`) }}</span>
              </li>
            </ul>
            <ul v-else class="flex flex-wrap gap-2">
              <li v-for="u in doc.recipient_tenant_ids" :key="u" class="chip bg-stone-100 text-stone-700">{{ unitName(u) }}</li>
            </ul>
          </section>

          <!-- nhận liên thông từ đơn vị khác trong hệ thống (F3.12) -->
          <section v-if="!outgoing && doc.dispatch_in" class="card p-5" data-testid="dispatch-in">
            <h2 class="mb-3 text-sm font-semibold text-stone-800">{{ t('doc.dispatch.from', { name: doc.dispatch_in.from_unit?.name ?? doc.issuer_name ?? '' }) }}</h2>
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div class="text-sm text-stone-500">{{ t('doc.dispatch.sourceCode') }}</div>
                <div class="font-mono text-lg font-semibold tracking-wider text-stone-900" data-testid="source-code">{{ fmtVerifyCode(doc.dispatch_in.source_verify_code) }}</div>
              </div>
              <a :href="`/xac-thuc/${doc.dispatch_in.source_verify_code}`" target="_blank" rel="noopener" class="btn-secondary">{{ t('doc.verifyOpen') }} ↗</a>
            </div>
            <p v-if="sourceMatch === true" class="mt-3 flex items-center gap-2 text-sm font-medium text-emerald-800" data-testid="source-hash">
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
              {{ t('doc.dispatch.hashMatch') }}
            </p>
            <p v-else-if="sourceMatch === false" class="mt-3 text-sm font-medium text-red-700" data-testid="source-hash">{{ t('doc.dispatch.hashMismatch') }}</p>
            <p class="mt-2 text-xs text-stone-500">{{ t(doc.source_id ? 'doc.dispatch.fromHint' : 'doc.dispatch.manualHint') }}</p>
          </section>

          <!-- nội dung văn bản đi -->
          <section v-if="outgoing" class="card p-5">
            <h2 class="mb-3 text-sm font-semibold text-stone-800">{{ t('doc.body') }}</h2>
            <div class="space-y-2 font-sans text-[15px] leading-relaxed whitespace-pre-line text-stone-800">
              {{ doc.body }}
            </div>
          </section>

          <!-- thông tin -->
          <section v-if="outgoing" class="card p-5">
            <h2 class="mb-4 text-sm font-semibold text-stone-800">{{ t('doc.info') }}</h2>
            <dl class="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              <div><dt class="text-stone-500">{{ t('doc.symbol') }}</dt><dd class="font-medium">{{ doc.symbol ?? '—' }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.issuedOn') }}</dt><dd class="font-medium">{{ fmtDate(doc.issued_on) }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.department') }}</dt><dd class="font-medium">{{ doc.department?.name ?? '—' }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.createdBy') }}</dt><dd class="font-medium">{{ nameOf(doc.created_by) }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.signer') }}</dt><dd class="font-medium">{{ doc.signer_id ? nameOf(doc.signer_id) : '—' }}</dd></div>
              <div><dt class="text-stone-500">{{ t('doc.urgency') }}</dt><dd class="font-medium">{{ t(`urgency.${doc.urgency}`) }}</dd></div>
              <div class="sm:col-span-2"><dt class="text-stone-500">{{ t('doc.recipients') }}</dt><dd class="font-medium">{{ doc.recipients.join('; ') || '—' }}</dd></div>
              <div v-if="doc.reply_to" class="sm:col-span-2">
                <dt class="text-stone-500">{{ t('doc.replyTo') }}</dt>
                <dd><NuxtLink :to="`/van-ban/${doc.reply_to.id}`" class="font-medium text-brand-800 hover:underline">{{ doc.reply_to.symbol }} — {{ doc.reply_to.summary }}</NuxtLink></dd>
              </div>
            </dl>
          </section>
          <section v-else class="card p-5">
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
                <span class="min-w-0 flex-1 break-words">{{ f.file!.filename }}</span>
                <span v-if="f.file!.encrypted" class="chip gap-1 bg-stone-800 text-white" :title="t('doc.sealedHint')" data-testid="file-sealed">
                  <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M7 11V8a5 5 0 0110 0v3M6 11h12v9H6z" /></svg>
                  {{ t('doc.sealed') }}
                </span>
                <span class="chip bg-stone-100 text-stone-600">{{ t(`doc.fileRole.${f.role}`) }}</span>
                <span class="text-xs text-stone-500">{{ fmtSize(f.file!.size_bytes) }}</span>
                <button
                  class="btn-ghost text-brand-800" :aria-label="t('doc.downloadNamed', { name: f.file!.filename })"
                  @click="download(f.file!.id, f.file!.filename).catch((e) => notice.error(errorText(t, e)))"
                >
                  {{ t('doc.download') }}
                </button>
              </li>
            </ul>
          </section>

          <!-- người được xem văn bản hạn chế (F3.7) -->
          <section v-if="doc.restricted && canManageViewers && viewers" class="card p-5" data-testid="viewers">
            <h2 class="mb-1 text-sm font-semibold text-stone-800">{{ t('doc.viewers') }}</h2>
            <p class="mb-3 text-xs text-stone-500">{{ t('doc.viewersHint') }}</p>
            <p v-if="!viewers.length" class="text-sm text-stone-500">{{ t('doc.viewersEmpty') }}</p>
            <ul v-else class="mb-3 divide-y divide-stone-100">
              <li v-for="v in viewers" :key="v.user_id" class="flex items-center gap-3 py-2 text-sm">
                <span class="min-w-0 flex-1">
                  <span class="font-medium">{{ nameOf(v.user_id) }}</span>
                  <span class="block text-xs text-stone-500">{{ t('doc.viewerBy', { by: nameOf(v.granted_by), at: fmtDateTime(v.granted_at) }) }}</span>
                </span>
                <button
                  v-if="v.user_id !== claims?.userId" class="btn-ghost text-rose-700" :disabled="viewerBusy"
                  @click="changeViewer(v.user_id, false)"
                >
                  {{ t('doc.viewerRemove') }}
                </button>
              </li>
            </ul>
            <form class="flex flex-wrap items-end gap-2" @submit.prevent="viewerPick && changeViewer(viewerPick, true)">
              <div class="min-w-48 flex-1">
                <label class="label" for="viewer">{{ t('doc.viewerPick') }}</label>
                <select id="viewer" v-model="viewerPick" class="input">
                  <option value="" disabled>—</option>
                  <option v-for="u in viewerChoices" :key="u.id" :value="u.id">{{ u.full_name }}</option>
                </select>
              </div>
              <button type="submit" class="btn-secondary" :disabled="viewerBusy || !viewerPick">{{ t('doc.viewerAdd') }}</button>
            </form>
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
          <div
            role="tablist" :aria-label="t('doc.activity')"
            class="mb-4 flex gap-4 border-b border-stone-200 text-sm font-semibold" @keydown="sideKey"
          >
            <button
              id="document-timeline-tab" ref="timelineTab" role="tab" aria-controls="document-timeline"
              :tabindex="side === 'timeline' ? 0 : -1" :aria-selected="side === 'timeline'"
              class="-mb-px border-b-2 pb-2"
              :class="side === 'timeline' ? 'border-brand-600 text-stone-900' : 'border-transparent text-stone-500'"
              @click="side = 'timeline'"
            >
              {{ t('doc.timeline') }}
            </button>
            <button
              id="document-history-tab" ref="historyTab" role="tab" aria-controls="document-history"
              :tabindex="side === 'history' ? 0 : -1" :aria-selected="side === 'history'"
              class="-mb-px border-b-2 pb-2"
              :class="side === 'history' ? 'border-brand-600 text-stone-900' : 'border-transparent text-stone-500'"
              @click="openHistory"
            >
              {{ t('doc.history') }}
            </button>
          </div>
          <ol
            id="document-timeline" v-show="side === 'timeline'" role="tabpanel" aria-labelledby="document-timeline-tab"
            tabindex="0" class="relative space-y-5 border-l border-stone-200 pl-5" data-testid="timeline"
          >
            <li v-for="(item, i) in timeline" :key="item.key" class="relative">
              <span class="absolute top-1 -left-[25px] h-2.5 w-2.5 rounded-full ring-4 ring-white" :class="i === 0 ? 'bg-brand-600' : 'bg-stone-300'" />
              <div class="text-sm font-medium text-stone-900">{{ item.title }}</div>
              <div class="text-xs text-stone-500">{{ item.who }} · {{ fmtDateTime(item.at) }}</div>
              <p v-if="item.note" class="mt-1 text-sm text-stone-600">{{ item.note }}</p>
            </li>
          </ol>
          <div
            id="document-history" v-show="side === 'history'" role="tabpanel" aria-labelledby="document-history-tab"
            tabindex="0" :aria-busy="historyLoading" data-testid="history"
          >
            <p v-if="historyLoading" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
            <div v-if="historyFailure" class="text-sm" role="alert">
              {{ historyFailure }}
              <button class="btn-secondary mt-2" @click="openHistory">{{ t('app.retry') }}</button>
            </div>
            <p class="mb-3 text-xs text-stone-500">{{ t('doc.historyHint') }}</p>
            <p v-if="history && !history.length" class="text-sm text-stone-500">{{ t('doc.historyEmpty') }}</p>
            <ol class="space-y-4">
              <li v-for="row in history ?? []" :key="row.id" class="text-sm">
                <div class="font-medium text-stone-900">{{ action(row) }} · {{ label('audit.entity', row.entity) }}</div>
                <div class="text-xs text-stone-500">{{ who(row) }} · {{ fmtDateTime(row.occurred_at) }}</div>
                <div v-for="c in changes(row).shown" :key="c.col" class="text-stone-700"><span class="text-stone-500">{{ c.col }}:</span> {{ c.text }}</div>
                <div v-if="changes(row).hidden.length" class="text-xs text-stone-500" :title="t('audit.hiddenHint')">
                  {{ t('audit.hidden', { cols: changes(row).hidden.join(', ') }) }}
                </div>
              </li>
            </ol>
          </div>
          <NuxtLink
            v-if="claims?.role === 'director'" :to="{ path: '/so-kiem-toan', query: { van_ban: doc.id } }"
            class="mt-5 inline-block text-xs font-medium text-brand-700 hover:underline"
          >
            {{ t('audit.openAudit') }}
          </NuxtLink>
        </aside>
      </div>
    </div>
  </div>
</template>
