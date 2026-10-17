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

// Tiếp nhận văn bản đến (F2.2). Poka-yoke lớp 1: kiểm ngay trên form theo đúng các ràng buộc của CSDL
// (db/migrations: documents_in_identity, độ dài trích yếu, chặn trùng) — CSDL vẫn kiểm lại lần cuối.

interface PendingFile {
  key: number
  name: string
  size: number
  progress: number
  state: 'uploading' | 'clean' | 'infected' | 'error'
  message?: string
  uploaded?: UploadedFile
}

const { t } = useI18n()
const { gql, upload } = useApi()
const notice = useNotice()
const router = useRouter()
const claims = useAuth().claims

const types = ref<{ code: string; name: string }[]>([])
const files = ref<PendingFile[]>([])
const dragging = ref(false)
const saving = ref(false)
const tried = ref(false)
const duplicate = ref<{ symbol: string; issuer_name: string; issued_on: string } | null>(null)
let nextKey = 1

const form = reactive({
  type_code: 'CV',
  symbol: '',
  issuer_name: '',
  issued_on: '',
  summary: '',
  urgency: 'normal',
  due_on: '',
  restricted: false,
})

onMounted(async () => {
  if (claims.value?.role !== 'clerk') return router.replace('/van-ban-den')
  const data = await gql<{ office_document_types: { code: string; name: string }[] }>(
    '{ office_document_types(order_by: {name: asc}) { code name } }',
  )
  types.value = data.office_document_types
})

const errors = computed(() => {
  const e: Record<string, string> = {}
  if (!form.symbol.trim()) e.symbol = t('validation.required')
  if (!form.issuer_name.trim()) e.issuer_name = t('validation.required')
  if (!form.issued_on) e.issued_on = t('validation.required')
  else if (form.issued_on > today()) e.issued_on = t('validation.dateFuture')
  const len = form.summary.trim().length
  if (len < 10 || len > 500) e.summary = t('validation.summaryLength')
  if (form.due_on && form.due_on < today()) e.due_on = t('validation.dueBefore')
  return e
})

const uploading = computed(() => files.value.some((f) => f.state === 'uploading'))
const cleanFiles = computed(() => files.value.filter((f) => f.state === 'clean'))

function addFiles(list: FileList | null) {
  for (const file of Array.from(list ?? [])) {
    const item = reactive<PendingFile>({ key: nextKey++, name: file.name, size: file.size, progress: 0, state: 'uploading' })
    files.value.push(item)
    upload(file, (p) => { item.progress = p })
      .then((res) => { item.state = 'clean'; item.uploaded = res })
      .catch((e) => {
        if (e?.code === 'infected') {
          item.state = 'infected'
          item.message = t('receive.infected', { sig: e.message })
        } else {
          item.state = 'error'
          item.message = errorText(t, e)
        }
      })
  }
}

function onDrop(e: DragEvent) {
  dragging.value = false
  addFiles(e.dataTransfer?.files ?? null)
}

function removeFile(key: number) {
  files.value = files.value.filter((f) => f.key !== key)
}

// Chặn trùng: cùng cơ quan ban hành, số ký hiệu, ngày ban hành (NĐ 30) — báo sớm trước khi bấm lưu
async function checkDuplicate() {
  duplicate.value = null
  if (!form.symbol.trim() || !form.issuer_name.trim() || !form.issued_on) return
  const data = await gql<{ office_documents: { symbol: string; issuer_name: string; issued_on: string }[] }>(`
    query ($s: String!, $i: String!, $d: date!) {
      office_documents(where: {direction: {_eq: "in"}, status: {_neq: "cancelled"}, symbol: {_eq: $s},
                               issuer_name: {_ilike: $i}, issued_on: {_eq: $d}}, limit: 1) { symbol issuer_name issued_on }
    }`, { s: form.symbol.trim(), i: form.issuer_name.trim(), d: form.issued_on })
  duplicate.value = data.office_documents[0] ?? null
}

async function save(register: boolean) {
  tried.value = true
  if (Object.keys(errors.value).length || uploading.value) return
  saving.value = true
  try {
    const object = {
      type_code: form.type_code,
      symbol: form.symbol.trim(),
      issuer_name: form.issuer_name.trim(),
      issued_on: form.issued_on,
      summary: form.summary.trim(),
      urgency: form.urgency,
      due_on: form.due_on || null,
      restricted: form.restricted,
      files: { data: cleanFiles.value.map((f, i) => ({ file_id: f.uploaded!.id, role: i === 0 ? 'main' : 'attachment' })) },
    }
    const data = await gql<{ insert_office_documents_one: { id: string } }>(
      'mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }',
      { o: object },
    )
    const id = data.insert_office_documents_one.id
    if (register) {
      const reg = await gql<{ registerIncoming: { register_number: number } }>(
        'mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }', { id },
      )
      notice.ok(t('receive.registered', { n: reg.registerIncoming.register_number }))
    } else {
      notice.ok(t('receive.saved'))
    }
    await router.push(`/van-ban/${id}`)
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    saving.value = false
  }
}

const show = (field: string) => (tried.value ? errors.value[field] : undefined)
</script>

<template>
  <div>
    <PageHeader :title="t('receive.title')" :subtitle="t('receive.subtitle')" />

    <form class="grid gap-6 lg:grid-cols-5" novalidate @submit.prevent="save(true)">
      <!-- tệp -->
      <section class="card p-5 lg:col-span-2">
        <h2 class="mb-3 text-sm font-semibold text-stone-800">{{ t('receive.file') }}</h2>
        <label
          class="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-10 text-center text-sm transition"
          :class="dragging ? 'border-brand-600 bg-brand-50' : 'border-stone-300 hover:border-brand-500 hover:bg-stone-50'"
          @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop"
        >
          <svg class="h-8 w-8 text-brand-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
          <span class="text-stone-600">{{ t('receive.drop') }}</span>
          <input type="file" class="sr-only" multiple accept="application/pdf,image/*" @change="addFiles(($event.target as HTMLInputElement).files)">
        </label>

        <ul class="mt-4 space-y-2">
          <li v-for="f in files" :key="f.key" class="rounded-md border border-stone-200 p-3 text-sm">
            <div class="flex items-center gap-2">
              <span class="min-w-0 flex-1 truncate font-medium">{{ f.name }}</span>
              <span class="text-xs text-stone-500">{{ fmtSize(f.size) }}</span>
              <button type="button" class="text-stone-400 hover:text-red-600" :aria-label="t('app.cancel')" @click="removeFile(f.key)">✕</button>
            </div>
            <div v-if="f.state === 'uploading'" class="mt-2">
              <div class="h-1.5 overflow-hidden rounded bg-stone-200"><div class="h-full bg-brand-600 transition-all" :style="{ width: f.progress + '%' }" /></div>
              <div class="mt-1 text-xs text-stone-500">{{ t('receive.scanning') }}</div>
            </div>
            <div v-else-if="f.state === 'clean'" class="mt-1 flex items-center gap-1 text-xs text-emerald-700">
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.6-4.4A11.9 11.9 0 0112 3a11.9 11.9 0 01-8.6 3.6A12 12 0 003 9c0 5.6 3.8 10.3 9 11.6 5.2-1.3 9-6 9-11.6 0-1-.1-2-.4-3z" /></svg>
              {{ t('receive.clean') }}
            </div>
            <div v-else class="mt-1 text-xs font-medium text-red-600">{{ f.message }}</div>
          </li>
        </ul>
      </section>

      <!-- thông tin văn bản -->
      <section class="card space-y-4 p-5 lg:col-span-3">
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="type">{{ t('receive.type') }}</label>
            <select id="type" v-model="form.type_code" class="input">
              <option v-for="ty in types" :key="ty.code" :value="ty.code">{{ ty.name }}</option>
            </select>
          </div>
          <div>
            <label class="label" for="urgency">{{ t('receive.urgency') }}</label>
            <select id="urgency" v-model="form.urgency" class="input">
              <option v-for="u in ['normal', 'khan', 'thuong_khan', 'hoa_toc']" :key="u" :value="u">{{ t(`urgency.${u}`) }}</option>
            </select>
          </div>
          <div>
            <label class="label" for="symbol">{{ t('receive.symbol') }}</label>
            <input id="symbol" v-model="form.symbol" class="input" :placeholder="t('receive.symbolHint')" :aria-invalid="!!show('symbol')" @blur="checkDuplicate">
            <p v-if="show('symbol')" class="field-error">{{ show('symbol') }}</p>
          </div>
          <div>
            <label class="label" for="issued_on">{{ t('receive.issuedOn') }}</label>
            <input id="issued_on" v-model="form.issued_on" type="date" class="input" :max="today()" :aria-invalid="!!show('issued_on')" @change="checkDuplicate">
            <p v-if="show('issued_on')" class="field-error">{{ show('issued_on') }}</p>
          </div>
        </div>
        <div>
          <label class="label" for="issuer">{{ t('receive.issuer') }}</label>
          <input id="issuer" v-model="form.issuer_name" class="input" :aria-invalid="!!show('issuer_name')" @blur="checkDuplicate">
          <p v-if="show('issuer_name')" class="field-error">{{ show('issuer_name') }}</p>
        </div>
        <div>
          <label class="label" for="summary">{{ t('receive.summary') }} <span class="font-normal text-stone-400">({{ t('receive.summaryHint') }})</span></label>
          <textarea id="summary" v-model="form.summary" rows="3" class="input" maxlength="500" :aria-invalid="!!show('summary')" />
          <div class="mt-1 flex justify-between text-xs">
            <span class="field-error !mt-0">{{ show('summary') }}</span>
            <span class="text-stone-400 tabular-nums">{{ form.summary.trim().length }}/500</span>
          </div>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="due_on">{{ t('receive.dueOn') }} <span class="font-normal text-stone-400">({{ t('app.optional') }})</span></label>
            <input id="due_on" v-model="form.due_on" type="date" class="input" :min="today()" :aria-invalid="!!show('due_on')">
            <p v-if="show('due_on')" class="field-error">{{ show('due_on') }}</p>
          </div>
          <label class="flex items-start gap-3 rounded-md border border-stone-200 p-3 text-sm">
            <input v-model="form.restricted" type="checkbox" class="mt-0.5 h-4 w-4 accent-brand-700">
            <span><span class="font-medium">{{ t('receive.restricted') }}</span><br><span class="text-xs text-stone-500">{{ t('receive.restrictedHint') }}</span></span>
          </label>
        </div>

        <p v-if="duplicate" class="rounded-md bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200" role="alert">
          {{ t('receive.duplicate', { symbol: duplicate.symbol, issuer: duplicate.issuer_name, date: fmtDate(duplicate.issued_on) }) }}
        </p>

        <div class="flex flex-wrap justify-end gap-2 border-t border-stone-100 pt-4">
          <button type="button" class="btn-secondary" :disabled="saving || uploading" @click="save(false)">{{ t('receive.save') }}</button>
          <button type="submit" class="btn-primary" :disabled="saving || uploading">{{ t('receive.saveAndRegister') }}</button>
        </div>
      </section>
    </form>
  </div>
</template>
