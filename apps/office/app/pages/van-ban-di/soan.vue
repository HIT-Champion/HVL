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
import type { UploadedFile } from '~/composables/useApi'

// Soạn hoặc sửa dự thảo văn bản đi (F2.4). Chuyên viên nhập trích yếu, nội dung, nơi nhận; svc-files dựng
// PDF đúng thể thức NĐ 30 từ đây. Số, ký hiệu, ngày ban hành do văn thư cấp khi phát hành, không nhập tay.
// Kiểm trên form theo ràng buộc của CSDL (độ dài trích yếu, nội dung); svc-workflow kiểm lại khi trình.

interface Attachment { key: number; name: string; state: 'uploading' | 'clean' | 'error'; message?: string; uploaded?: UploadedFile; existing?: boolean }

const { t } = useI18n()
const { gql, upload } = useApi()
const notice = useNotice()
const router = useRouter()
const route = useRoute()
const claims = useAuth().claims

const editId = computed(() => (route.query.id ? String(route.query.id) : null))
const types = ref<{ code: string; name: string }[]>([])
const incoming = ref<{ id: string; symbol: string | null; summary: string }[]>([])
const attachments = ref<Attachment[]>([])
const removed = ref<string[]>([])
const loading = ref(true)
const locked = ref(false)
const restricted = ref(false)   // văn bản hạn chế: không giữ bản dở trong trình duyệt
const saving = ref(false)
const tried = ref(false)
let nextKey = 1

const form = reactive({ type_code: 'CV', summary: '', body: '', recipients: '', urgency: 'normal', reply_to_id: '' })

const recipientList = computed(() => form.recipients.split('\n').map((r) => r.trim()).filter(Boolean))
const errors = computed(() => {
  const e: Record<string, string> = {}
  const len = form.summary.trim().length
  if (len < 10 || len > 500) e.summary = t('validation.summaryLength')
  if (!form.body.trim()) e.body = t('validation.required')
  else if (form.body.length > 20000) e.body = t('error.documents_body_length')
  if (!recipientList.value.length) e.recipients = t('validation.required')
  return e
})
const uploading = computed(() => attachments.value.some((a) => a.state === 'uploading'))

// Hết phiên giữa chừng: quay lại sau khi đăng nhập vẫn còn bản đang soạn (tệp đã tải lên giữ theo id)
interface Kept { form: typeof form; files: { name: string; uploaded: UploadedFile; existing?: boolean }[]; removed: string[] }
const draft = useFormDraft<Kept>(
  () => (claims.value ? `${claims.value.userId}:van-ban-di:${editId.value ?? 'moi'}` : null),
  () => (restricted.value ? null : {
    form: { ...form }, removed: [...removed.value],
    files: attachments.value.filter((a) => a.state === 'clean' && a.uploaded)
      .map((a) => ({ name: a.name, uploaded: a.uploaded!, existing: a.existing })),
  }),
  (kept) => {
    Object.assign(form, kept.form)
    removed.value = kept.removed
    attachments.value = kept.files.map((f) => ({ key: nextKey++, name: f.name, state: 'clean' as const, uploaded: f.uploaded, existing: f.existing }))
  },
)

onMounted(async () => {
  if (claims.value?.role !== 'staff') return router.replace('/van-ban-di')
  try {
    const data = await gql<{
      office_document_types: { code: string; name: string }[]
      office_documents: { id: string; symbol: string | null; summary: string }[]
    }>(`{
      office_document_types(order_by: {name: asc}) { code name }
      office_documents(where: {direction: {_eq: "in"}}, order_by: {created_at: desc}, limit: 50) { id symbol summary }
    }`)
    types.value = data.office_document_types
    incoming.value = data.office_documents
    if (route.query.reply) form.reply_to_id = String(route.query.reply)
    if (editId.value) await loadDraft(editId.value)
    if (restricted.value) draft.clear()
    else if (!locked.value && draft.resume()) notice.info(t('compose.restored'))
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    loading.value = false
  }
})

async function loadDraft(id: string) {
  const data = await gql<{ office_documents_by_pk: {
    status: string; created_by: string; restricted: boolean; type_code: string; summary: string; body: string | null
    recipients: string[]
    urgency: string; reply_to_id: string | null; files: { role: string; file: { id: string; filename: string } | null }[]
  } | null }>(`
    query ($id: uuid!) { office_documents_by_pk(id: $id) {
      status created_by restricted type_code summary body recipients urgency reply_to_id
      files(where: {role: {_eq: "attachment"}}) { role file { id filename } }
    } }`, { id })
  const doc = data.office_documents_by_pk
  if (!doc || doc.created_by !== claims.value?.userId || !['draft', 'returned'].includes(doc.status)) {
    locked.value = true
    return
  }
  restricted.value = doc.restricted
  Object.assign(form, {
    type_code: doc.type_code, summary: doc.summary, body: doc.body ?? '', recipients: doc.recipients.join('\n'),
    urgency: doc.urgency, reply_to_id: doc.reply_to_id ?? '',
  })
  attachments.value = doc.files.filter((f) => f.file).map((f) => ({
    key: nextKey++, name: f.file!.filename, state: 'clean' as const, existing: true,
    uploaded: { id: f.file!.id, filename: f.file!.filename } as UploadedFile,
  }))
}

function addFiles(list: FileList | null) {
  for (const file of Array.from(list ?? [])) {
    const item = reactive<Attachment>({ key: nextKey++, name: file.name, state: 'uploading' })
    attachments.value.push(item)
    upload(file)
      .then((res) => { item.state = 'clean'; item.uploaded = res })
      .catch((e) => { item.state = 'error'; item.message = errorText(t, e) })
  }
}

function removeAttachment(a: Attachment) {
  if (a.existing && a.uploaded) removed.value.push(a.uploaded.id)
  attachments.value = attachments.value.filter((x) => x.key !== a.key)
}

async function save() {
  tried.value = true
  if (Object.keys(errors.value).length || uploading.value) return
  saving.value = true
  const fields = {
    type_code: form.type_code, summary: form.summary.trim(), body: form.body.trim(), recipients: recipientList.value,
    urgency: form.urgency, reply_to_id: form.reply_to_id || null,
  }
  const fresh = attachments.value.filter((a) => a.state === 'clean' && !a.existing)
  try {
    let id = editId.value
    if (id) {
      const data = await gql<{ update_office_documents_by_pk: { id: string } | null }>(`
        mutation ($id: uuid!, $set: office_documents_set_input!, $files: [office_document_files_insert_input!]!, $removed: [uuid!]!) {
          update_office_documents_by_pk(pk_columns: {id: $id}, _set: $set) { id }
          insert_office_document_files(objects: $files) { affected_rows }
          delete_office_document_files(where: {document_id: {_eq: $id}, file_id: {_in: $removed}}) { affected_rows }
        }`, {
        id, set: fields, removed: removed.value,
        files: fresh.map((a) => ({ document_id: id, file_id: a.uploaded!.id, role: 'attachment' })),
      })
      // Hasura trả null khi dòng không còn khớp quyền sửa (vừa trình ở thẻ khác…): không có gì được lưu — quyền gắn,
      // gỡ tệp cùng điều kiện — nên không báo "Đã lưu"
      if (!data.update_office_documents_by_pk) {
        notice.error(t('compose.notEditable'))
        return
      }
    } else {
      const data = await gql<{ insert_office_documents_one: { id: string } }>(
        'mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }',
        { o: { ...fields, files: { data: fresh.map((a) => ({ file_id: a.uploaded!.id, role: 'attachment' })) } } },
      )
      id = data.insert_office_documents_one.id
    }
    draft.clear()
    notice.ok(t('compose.saved'))
    await router.push(`/van-ban/${id}`)
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="max-w-3xl">
    <NuxtLink :to="editId ? `/van-ban/${editId}` : '/van-ban-di'" class="mb-4 inline-flex items-center gap-1 text-sm text-stone-500 hover:text-brand-800">← {{ t('app.back') }}</NuxtLink>
    <PageHeader :title="editId ? t('compose.editTitle') : t('compose.title')" :subtitle="t('compose.subtitle')" />

    <p v-if="loading" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <p v-else-if="locked" class="card p-8 text-center text-stone-500">{{ t('compose.notEditable') }}</p>

    <form v-else class="card space-y-5 p-6" novalidate @submit.prevent="save">
      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label class="label" for="type">{{ t('compose.type') }}</label>
          <select id="type" v-model="form.type_code" class="input">
            <option v-for="ty in types" :key="ty.code" :value="ty.code">{{ ty.name }}</option>
          </select>
        </div>
        <div>
          <label class="label" for="urgency">{{ t('compose.urgency') }}</label>
          <select id="urgency" v-model="form.urgency" class="input">
            <option v-for="u in ['normal', 'khan', 'thuong_khan', 'hoa_toc']" :key="u" :value="u">{{ t(`urgency.${u}`) }}</option>
          </select>
        </div>
      </div>

      <div>
        <label class="label" for="summary">{{ t('compose.summary') }}</label>
        <input id="summary" v-model="form.summary" class="input" maxlength="500" :aria-invalid="tried && !!errors.summary">
        <p v-if="tried && errors.summary" class="field-error">{{ errors.summary }}</p>
        <p v-else class="mt-1 text-xs text-stone-500">{{ t('compose.summaryHint') }}</p>
      </div>

      <div>
        <label class="label" for="body">{{ t('compose.body') }}</label>
        <textarea id="body" v-model="form.body" rows="12" class="input font-serif leading-relaxed" :aria-invalid="tried && !!errors.body" />
        <p v-if="tried && errors.body" class="field-error">{{ errors.body }}</p>
        <p v-else class="mt-1 text-xs text-stone-500">{{ t('compose.bodyHint') }}</p>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label class="label" for="recipients">{{ t('compose.recipients') }}</label>
          <textarea id="recipients" v-model="form.recipients" rows="3" class="input" :aria-invalid="tried && !!errors.recipients" />
          <p v-if="tried && errors.recipients" class="field-error">{{ errors.recipients }}</p>
          <p v-else class="mt-1 text-xs text-stone-500">{{ t('compose.recipientsHint') }}</p>
        </div>
        <div>
          <label class="label" for="reply">{{ t('compose.replyTo') }} <span class="font-normal text-stone-400">({{ t('app.optional') }})</span></label>
          <select id="reply" v-model="form.reply_to_id" class="input">
            <option value="">{{ t('compose.replyNone') }}</option>
            <option v-for="d in incoming" :key="d.id" :value="d.id">{{ d.symbol }} — {{ d.summary }}</option>
          </select>
        </div>
      </div>

      <div>
        <span class="label">{{ t('compose.attachments') }} <span class="font-normal text-stone-400">({{ t('app.optional') }})</span></span>
        <ul v-if="attachments.length" class="mb-2 divide-y divide-stone-100 rounded-md border border-stone-200 text-sm">
          <li v-for="a in attachments" :key="a.key" class="flex items-center gap-3 px-3 py-2">
            <span class="min-w-0 flex-1 truncate">{{ a.name }}</span>
            <span v-if="a.state === 'uploading'" class="text-xs text-stone-500">{{ t('receive.scanning') }}</span>
            <span v-else-if="a.state === 'error'" class="text-xs text-red-600">{{ a.message }}</span>
            <span v-else class="text-xs text-emerald-700">{{ t('receive.clean') }}</span>
            <button type="button" class="btn-ghost text-xs" @click="removeAttachment(a)">✕</button>
          </li>
        </ul>
        <label class="btn-secondary cursor-pointer">
          <input type="file" class="sr-only" multiple @change="addFiles(($event.target as HTMLInputElement).files)">
          + {{ t('compose.attachments') }}
        </label>
        <p class="mt-1 text-xs text-stone-500">{{ t('compose.attachmentsHint') }}</p>
      </div>

      <div class="flex justify-end gap-2 border-t border-stone-100 pt-4">
        <button type="submit" class="btn-primary" :disabled="saving || uploading">{{ t('compose.save') }}</button>
      </div>
    </form>
  </div>
</template>
