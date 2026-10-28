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
import { mountForm } from '~/lib/schema-form.js'
import {
  BUILDER_DATE_RULES, BUILDER_LIMITS, BUILDER_WIDGETS, addBuilderField, addBuilderOption, builderFile, builderFormFrom,
  builderFormKey, builderProblems, builderSchema, canBuildForms, freezeBuilderNames, moveBuilderItem, newBuilderForm,
  removeBuilderField, setBuilderWidget, syncBuilderNames,
} from '~/utils/formBuilder'
import type {
  BuilderField, BuilderForm, BuilderOption, BuilderProblem, BuilderProblemCode, BuilderWidget,
} from '~/utils/formBuilder'

// Trình dựng form (#303 bước 1b): khai trường, xem trước bằng đúng module form của ứng dụng (lib/schema-form.js, bản
// chép của apps/nghi-phep/public/schema-form.js — test so từng byte), tải tệp JSON Schema về để đặt vào gói ứng dụng.
// Không gọi API nào: form chỉ vào lõi khi người vận hành chạy `moc app install`, svc-workflow kiểm lại lúc đó. Bản đang
// dựng giữ trong sessionStorage (useFormDraft) để hết phiên đăng nhập không mất; rời trang là bỏ.

const { t, locale } = useI18n()
const notice = useNotice()
const claims = useAuth().claims
const allowed = computed(() => canBuildForms(claims.value?.role))

const form = reactive<BuilderForm>(newBuilderForm())
const open = ref<number | null>(null)               // id trường đang mở để sửa
const widget = ref<BuilderWidget>('text')            // kiểu ô của trường sắp thêm
watch(form, () => syncBuilderNames(form), { deep: true, immediate: true })

const problems = computed(() => builderProblems(form))
const file = computed(() => builderFile(form))
const fileName = computed(() => `${form.key || 'form'}.json`)
const manifest = computed(() => `workflow:\n  forms:\n    ${builderFormKey(form)}: forms/${fileName.value}\n`)

const draft = useFormDraft<BuilderForm>(
  () => (claims.value && allowed.value ? `${claims.value.userId}:dung-form` : null),
  () => ({ ...form }),
  (kept) => {
    Object.assign(form, builderFormFrom(kept))
  },
)

// Thanh trên ghi tên trang con thay cho "Ứng dụng" của mục menu
const crumb = useState<string>('sg-crumb', () => '')
watch(locale, () => { crumb.value = t('formBuilder.title') })

onMounted(() => {
  crumb.value = t('formBuilder.title')
  if (draft.resume()) notice.info(t('compose.restored'))
})

const fieldOf = (id: number) => form.fields.find((f) => f.id === id)
function fieldTitle(f: BuilderField | undefined): string {
  if (!f) return t('formBuilder.untitled')
  return (locale.value === 'en' && f.label.en.trim()) || f.label.vi.trim() || t('formBuilder.untitled')
}
const dates = (f: BuilderField) => form.fields.filter((g) => g.widget === 'date' && g.id !== f.id)

function problemText(p: BuilderProblem): string {
  const f = p.field === undefined ? undefined : fieldOf(p.field)
  const option = f && p.option !== undefined ? f.options.findIndex((o) => o.id === p.option) + 1 : 0
  return t(`formBuilder.problem.${p.code}`, {
    field: fieldTitle(f), option, rule: p.rule ?? '', max: BUILDER_LIMITS.MAX_LENGTH, rows: BUILDER_LIMITS.MAX_ROWS,
    keyMax: BUILDER_LIMITS.FORM_KEY_MAX,
  })
}
const problemsOf = (f: BuilderField) => problems.value.filter((p) => p.field === f.id)

// Tiêu điểm sau khi thêm, đổi chỗ, xóa: về đúng ô người dùng đang làm, không rơi về đầu trang
function focus(id: string) {
  void nextTick(() => document.getElementById(id)?.focus())
}

function addField() {
  const id = addBuilderField(form, widget.value)
  open.value = id
  focus(`fb-${id}-label`)
}

function toggle(f: BuilderField) {
  open.value = open.value === f.id ? null : f.id
}

function move(f: BuilderField, delta: -1 | 1) {
  const index = form.fields.indexOf(f)
  const to = moveBuilderItem(form.fields, index, delta)
  if (to < 0) return
  // nút vừa bấm bị khóa khi trường đã lên đầu hoặc xuống cuối: chuyển sang nút kia
  const stuck = delta === -1 ? to === 0 : to === form.fields.length - 1
  focus(`fb-${f.id}-${(delta === -1) !== stuck ? 'up' : 'down'}`)
}

function remove(f: BuilderField) {
  const index = form.fields.indexOf(f)
  const title = fieldTitle(f)
  removeBuilderField(form, f.id)
  if (open.value === f.id) open.value = null
  notice.info(t('formBuilder.removed', { field: title }))
  const next = form.fields[index] ?? form.fields[index - 1]
  focus(next ? `fb-${next.id}-edit` : 'fb-add')
}

function changeWidget(f: BuilderField, event: Event) {
  setBuilderWidget(form, f, (event.target as HTMLSelectElement).value as BuilderWidget)
}

// Ô số: để trống là không đặt (null), không phải 0
function numberInput(event: Event): number | null {
  const value = (event.target as HTMLInputElement).valueAsNumber
  return Number.isNaN(value) ? null : value
}

// Gõ tên, khóa, giá trị là tự đặt, kể cả khi đang xóa trắng để gõ lại (suy ngay thì ô điền lại chữ cũ, phím sau gõ
// nối vào đó). Rời ô mà vẫn trống mới quay về suy theo nhãn
const typed = (event: Event) => (event.target as HTMLInputElement).value.trim()
function setName(f: BuilderField, event: Event) {
  f.named = true
  f.name = typed(event)
}
function setKey(event: Event) {
  form.keyed = true
  form.key = typed(event)
}
function setValue(o: BuilderOption, event: Event) {
  o.named = true
  o.value = typed(event)
}
function unsetName(f: BuilderField) {
  if (!f.name) f.named = false
}
function unsetKey() {
  if (!form.key) form.keyed = false
}
function unsetValue(o: BuilderOption) {
  if (!o.value) o.named = false
}

function addOption(f: BuilderField) {
  const id = addBuilderOption(form, f)
  focus(`fb-${id}-label`)
}
function removeOption(f: BuilderField, index: number) {
  f.options.splice(index, 1)
  focus(`fb-${f.id}-add-option`)
}

// Bấm một lỗi thì tới ô phải sửa: ô của form, ô trong trường (id fb-<trường>-<ô>) hay ô của lựa chọn
const FORM_INPUTS: Partial<Record<BuilderProblemCode, string>> = {
  app: 'fb-app', key: 'fb-key', title: 'fb-title', fields: 'fb-add',
}
const FIELD_INPUTS: Partial<Record<BuilderProblemCode, string>> = {
  'name': 'name', 'name-reserved': 'name', 'name-taken': 'name', 'length': 'max', 'rows': 'rows', 'bounds': 'minimum',
  'options': 'add-option', 'after': 'after', 'after-loop': 'after',
}
function showProblem(p: BuilderProblem) {
  if (p.field === undefined) {
    focus(FORM_INPUTS[p.code] ?? 'fb-title')
    return
  }
  open.value = p.field
  if (p.option !== undefined) focus(`fb-${p.option}-${p.code === 'option-label' ? 'label' : 'value'}`)
  else focus(`fb-${p.field}-${FIELD_INPUTS[p.code] ?? 'label'}`)
}

function download() {
  if (problems.value.length) return
  freezeBuilderNames(form)
  const url = URL.createObjectURL(new Blob([file.value], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = fileName.value
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
  notice.ok(t('formBuilder.downloaded', { file: fileName.value }))
}

// Xem trước: dựng lại khi nội dung tệp hay ngôn ngữ đổi. Vue không vẽ gì trong khung này, mountForm() thay cả nội dung
const preview = ref<HTMLElement | null>(null)
const previewError = ref('')
const sent = ref('')
function render() {
  const el = preview.value
  if (!el) return
  sent.value = ''
  previewError.value = ''
  if (!form.fields.length) {
    el.replaceChildren()
    return
  }
  try {
    mountForm(el, builderSchema(form), {
      lang: locale.value,
      idPrefix: 'xem-truoc-',
      submitLabel: t('formBuilder.previewSubmit'),
      onSubmit: (data: unknown) => {
        sent.value = JSON.stringify(data, null, 2)
      },
    })
  } catch (e) {
    el.replaceChildren()
    previewError.value = e instanceof Error ? e.message : String(e)
  }
}
watch([file, locale, preview], render, { flush: 'post' })
</script>

<template>
  <div>
    <NuxtLink to="/ung-dung" class="moc-back">
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
      </svg>
      {{ t('formBuilder.back') }}
    </NuxtLink>
    <PageHeader :title="t('formBuilder.title')" :subtitle="t('formBuilder.subtitle')" />
    <p v-if="!allowed" class="moc-state" data-testid="form-builder-denied">{{ t('formBuilder.onlyAdmin') }}</p>

    <div v-else class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,27rem)] xl:items-start">
      <div class="moc-stack">
        <section class="moc-block" data-testid="form-builder-form">
          <h2 class="moc-block-title">{{ t('formBuilder.formBlock') }}</h2>
          <p class="moc-block-hint">{{ t('formBuilder.formHint') }}</p>
          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <label class="label" for="fb-title">{{ t('formBuilder.titleVi') }}</label>
              <input id="fb-title" v-model="form.title.vi" class="input" maxlength="200">
            </div>
            <div>
              <label class="label" for="fb-title-en">{{ t('formBuilder.titleEn') }}</label>
              <input id="fb-title-en" v-model="form.title.en" class="input" maxlength="200" lang="en">
            </div>
            <div>
              <label class="label" for="fb-app">{{ t('formBuilder.app') }}</label>
              <input
                id="fb-app" v-model.trim="form.app" class="input font-mono" maxlength="30" spellcheck="false"
                autocomplete="off" aria-describedby="fb-app-help"
              >
              <p id="fb-app-help" class="moc-foot mt-1">{{ t('formBuilder.appHint') }}</p>
            </div>
            <div>
              <label class="label" for="fb-key">{{ t('formBuilder.key') }}</label>
              <input
                id="fb-key" :value="form.key" class="input font-mono" maxlength="60" spellcheck="false"
                autocomplete="off" aria-describedby="fb-key-help" @input="setKey" @change="unsetKey"
              >
              <p id="fb-key-help" class="moc-foot mt-1">{{ t('formBuilder.keyHint') }}</p>
            </div>
          </div>
        </section>

        <!-- danh sách trường đã có viền: không đặt trong moc-block, như danh sách của trang Ứng dụng -->
        <section data-testid="form-builder-fields">
          <h2 class="moc-block-title">{{ t('formBuilder.fieldsBlock') }}</h2>
          <p class="moc-block-hint">{{ t('formBuilder.fieldsHint') }}</p>
          <p v-if="!form.fields.length" class="moc-empty mt-3">{{ t('formBuilder.noFields') }}</p>
          <ol v-else class="moc-list mt-3">
            <li v-for="(f, i) in form.fields" :key="f.id" :data-testid="`fb-field-${i}`">
              <div class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                <span class="w-6 shrink-0 text-right text-sm text-stone-500 tabular-nums">{{ i + 1 }}</span>
                <div class="min-w-0 flex-1 basis-48">
                  <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span class="font-medium text-stone-900 wrap-anywhere">{{ fieldTitle(f) }}</span>
                    <span class="chip bg-stone-100 text-stone-700">{{ t(`formBuilder.widgets.${f.widget}`) }}</span>
                    <span v-if="f.required" class="chip bg-brand-50 text-brand-800">
                      {{ t('formBuilder.required') }}
                    </span>
                    <span v-if="problemsOf(f).length" class="chip bg-red-50 text-red-800">
                      {{ t('formBuilder.fieldProblems', { n: problemsOf(f).length }) }}
                    </span>
                  </div>
                  <p class="mt-0.5 font-mono text-xs text-stone-500 wrap-anywhere">{{ f.name || '—' }}</p>
                </div>
                <div class="flex flex-wrap gap-1">
                  <button
                    :id="`fb-${f.id}-up`" type="button" class="btn-ghost min-h-9 px-2.5" :disabled="i === 0"
                    :aria-label="t('formBuilder.upOf', { field: fieldTitle(f) })" @click="move(f, -1)"
                  >
                    {{ t('formBuilder.up') }}
                  </button>
                  <button
                    :id="`fb-${f.id}-down`" type="button" class="btn-ghost min-h-9 px-2.5"
                    :disabled="i === form.fields.length - 1"
                    :aria-label="t('formBuilder.downOf', { field: fieldTitle(f) })" @click="move(f, 1)"
                  >
                    {{ t('formBuilder.down') }}
                  </button>
                  <button
                    :id="`fb-${f.id}-edit`" type="button" class="btn-secondary min-h-9 px-2.5"
                    :aria-expanded="open === f.id" :aria-controls="open === f.id ? `fb-${f.id}-editor` : undefined"
                    :aria-label="t(open === f.id ? 'formBuilder.collapseOf' : 'formBuilder.editOf',
                                   { field: fieldTitle(f) })"
                    @click="toggle(f)"
                  >
                    {{ open === f.id ? t('formBuilder.collapse') : t('formBuilder.edit') }}
                  </button>
                  <button
                    type="button" class="btn-ghost min-h-9 px-2.5 text-red-700"
                    :aria-label="t('formBuilder.removeOf', { field: fieldTitle(f) })" @click="remove(f)"
                  >
                    {{ t('formBuilder.remove') }}
                  </button>
                </div>
              </div>

              <div
                v-if="open === f.id" :id="`fb-${f.id}-editor`" class="border-t border-stone-100 bg-stone-50 px-4 py-4"
                :data-testid="`fb-editor-${i}`"
              >
                <ul v-if="problemsOf(f).length" class="mb-4 space-y-1">
                  <li v-for="(p, k) in problemsOf(f)" :key="k" class="field-error mt-0 text-[13px]">
                    {{ problemText(p) }}
                  </li>
                </ul>
                <div class="grid gap-4 md:grid-cols-2">
                  <div>
                    <label class="label" :for="`fb-${f.id}-label`">{{ t('formBuilder.labelVi') }}</label>
                    <input :id="`fb-${f.id}-label`" v-model="f.label.vi" class="input" maxlength="200">
                  </div>
                  <div>
                    <label class="label" :for="`fb-${f.id}-label-en`">{{ t('formBuilder.labelEn') }}</label>
                    <input :id="`fb-${f.id}-label-en`" v-model="f.label.en" class="input" maxlength="200" lang="en">
                  </div>
                  <div>
                    <label class="label" :for="`fb-${f.id}-name`">{{ t('formBuilder.name') }}</label>
                    <input
                      :id="`fb-${f.id}-name`" :value="f.name" class="input font-mono" maxlength="64" spellcheck="false"
                      autocomplete="off" :aria-describedby="`fb-${f.id}-name-help`" @input="setName(f, $event)"
                      @change="unsetName(f)"
                    >
                    <p :id="`fb-${f.id}-name-help`" class="moc-foot mt-1">{{ t('formBuilder.nameHint') }}</p>
                  </div>
                  <div>
                    <label class="label" :for="`fb-${f.id}-widget`">{{ t('formBuilder.widget') }}</label>
                    <select :id="`fb-${f.id}-widget`" :value="f.widget" class="input" @change="changeWidget(f, $event)">
                      <option v-for="w in BUILDER_WIDGETS" :key="w" :value="w">
                        {{ t(`formBuilder.widgets.${w}`) }}
                      </option>
                    </select>
                  </div>
                  <div>
                    <label class="label" :for="`fb-${f.id}-help`">{{ t('formBuilder.helpVi') }}</label>
                    <input :id="`fb-${f.id}-help`" v-model="f.help.vi" class="input" maxlength="300">
                  </div>
                  <div>
                    <label class="label" :for="`fb-${f.id}-help-en`">{{ t('formBuilder.helpEn') }}</label>
                    <input :id="`fb-${f.id}-help-en`" v-model="f.help.en" class="input" maxlength="300" lang="en">
                  </div>
                  <div class="md:col-span-2">
                    <label v-if="f.widget !== 'checkbox'" class="inline-flex min-h-11 items-center gap-2 text-sm">
                      <input v-model="f.required" type="checkbox" class="h-4 w-4">
                      {{ t('formBuilder.requiredField') }}
                    </label>
                    <p v-else class="moc-foot mt-0">{{ t('formBuilder.checkboxNote') }}</p>
                  </div>

                  <template v-if="f.widget === 'text' || f.widget === 'textarea'">
                    <div>
                      <label class="label" :for="`fb-${f.id}-min`">{{ t('formBuilder.minLength') }}</label>
                      <input
                        :id="`fb-${f.id}-min`" :value="f.minLength ?? ''" type="number" min="0" step="1" class="input"
                        @input="f.minLength = numberInput($event)"
                      >
                    </div>
                    <div>
                      <label class="label" :for="`fb-${f.id}-max`">{{ t('formBuilder.maxLength') }}</label>
                      <input
                        :id="`fb-${f.id}-max`" :value="f.maxLength ?? ''" type="number" min="1"
                        :max="BUILDER_LIMITS.MAX_LENGTH" step="1" class="input"
                        @input="f.maxLength = numberInput($event)"
                      >
                    </div>
                    <div v-if="f.widget === 'textarea'">
                      <label class="label" :for="`fb-${f.id}-rows`">{{ t('formBuilder.rows') }}</label>
                      <input
                        :id="`fb-${f.id}-rows`" :value="f.rows ?? ''" type="number" min="1"
                        :max="BUILDER_LIMITS.MAX_ROWS" step="1" class="input" placeholder="4"
                        @input="f.rows = numberInput($event)"
                      >
                    </div>
                  </template>

                  <template v-if="f.widget === 'number'">
                    <div class="md:col-span-2">
                      <label class="inline-flex min-h-11 items-center gap-2 text-sm">
                        <input v-model="f.integer" type="checkbox" class="h-4 w-4">
                        {{ t('formBuilder.integer') }}
                      </label>
                    </div>
                    <div>
                      <label class="label" :for="`fb-${f.id}-minimum`">{{ t('formBuilder.minimum') }}</label>
                      <input
                        :id="`fb-${f.id}-minimum`" :value="f.minimum ?? ''" type="number" step="any" class="input"
                        @input="f.minimum = numberInput($event)"
                      >
                    </div>
                    <div>
                      <label class="label" :for="`fb-${f.id}-maximum`">{{ t('formBuilder.maximum') }}</label>
                      <input
                        :id="`fb-${f.id}-maximum`" :value="f.maximum ?? ''" type="number" step="any" class="input"
                        @input="f.maximum = numberInput($event)"
                      >
                    </div>
                  </template>

                  <template v-if="f.widget === 'date'">
                    <div>
                      <label class="label" :for="`fb-${f.id}-today`">{{ t('formBuilder.dateRule') }}</label>
                      <select :id="`fb-${f.id}-today`" v-model="f.dateRule" class="input">
                        <option v-for="r in BUILDER_DATE_RULES" :key="r" :value="r">
                          {{ t(`formBuilder.dateRules.${r || 'none'}`) }}
                        </option>
                      </select>
                    </div>
                    <div>
                      <label class="label" :for="`fb-${f.id}-after`">{{ t('formBuilder.after') }}</label>
                      <select :id="`fb-${f.id}-after`" v-model="f.after" class="input">
                        <option :value="null">{{ t('formBuilder.afterNone') }}</option>
                        <option v-for="g in dates(f)" :key="g.id" :value="g.id">{{ fieldTitle(g) }}</option>
                      </select>
                    </div>
                  </template>

                  <fieldset v-if="f.widget === 'select' || f.widget === 'radio'" class="min-w-0 md:col-span-2">
                    <legend class="label">{{ t('formBuilder.options') }}</legend>
                    <p class="moc-foot mt-0 mb-3">{{ t('formBuilder.optionsHint') }}</p>
                    <ol class="divide-y divide-stone-200 border-y border-stone-200">
                      <li v-for="(o, k) in f.options" :key="o.id" class="grid gap-2 py-3 sm:grid-cols-3">
                        <div>
                          <label class="label mb-1 text-xs" :for="`fb-${o.id}-label`">
                            {{ t('formBuilder.optionLabelVi', { n: k + 1 }) }}
                          </label>
                          <input :id="`fb-${o.id}-label`" v-model="o.label.vi" class="input" maxlength="200">
                        </div>
                        <div>
                          <label class="label mb-1 text-xs" :for="`fb-${o.id}-label-en`">
                            {{ t('formBuilder.optionLabelEn', { n: k + 1 }) }}
                          </label>
                          <input
                            :id="`fb-${o.id}-label-en`" v-model="o.label.en" class="input" maxlength="200" lang="en"
                          >
                        </div>
                        <div>
                          <label class="label mb-1 text-xs" :for="`fb-${o.id}-value`">
                            {{ t('formBuilder.optionValue', { n: k + 1 }) }}
                          </label>
                          <div class="flex gap-2">
                            <input
                              :id="`fb-${o.id}-value`" :value="o.value" class="input font-mono" maxlength="100"
                              spellcheck="false" autocomplete="off" @input="setValue(o, $event)"
                              @change="unsetValue(o)"
                            >
                            <button
                              type="button" class="btn-ghost px-2.5 text-red-700"
                              :aria-label="t('formBuilder.removeOption', { n: k + 1 })" @click="removeOption(f, k)"
                            >
                              {{ t('formBuilder.remove') }}
                            </button>
                          </div>
                        </div>
                      </li>
                    </ol>
                    <button
                      :id="`fb-${f.id}-add-option`" type="button" class="btn-secondary mt-3" @click="addOption(f)"
                    >
                      {{ t('formBuilder.addOption') }}
                    </button>
                  </fieldset>
                </div>
              </div>
            </li>
          </ol>
          <div class="mt-4 flex flex-wrap items-end gap-3">
            <div class="min-w-48">
              <label class="label" for="fb-widget">{{ t('formBuilder.newWidget') }}</label>
              <select id="fb-widget" v-model="widget" class="input">
                <option v-for="w in BUILDER_WIDGETS" :key="w" :value="w">{{ t(`formBuilder.widgets.${w}`) }}</option>
              </select>
            </div>
            <button id="fb-add" type="button" class="btn-primary" data-testid="fb-add" @click="addField">
              {{ t('formBuilder.add') }}
            </button>
          </div>
        </section>
      </div>

      <div class="moc-stack xl:sticky xl:top-6">
        <section class="moc-block" data-testid="form-builder-check" aria-labelledby="fb-check-title">
          <h2 id="fb-check-title" class="moc-block-title">{{ t('formBuilder.check') }}</h2>
          <!-- chỉ dòng tóm tắt là vùng thông báo: đọc cả danh sách lỗi sau mỗi phím gõ thì quá ồn -->
          <p
            role="status" class="mt-2 text-sm text-stone-700"
            :data-testid="problems.length ? 'fb-count' : 'fb-passed'"
          >
            {{ problems.length ? t('formBuilder.problemsCount', { n: problems.length }) : t('formBuilder.passed') }}
          </p>
          <ul v-if="problems.length" class="mt-2 space-y-1.5" data-testid="fb-problems">
            <li v-for="(p, k) in problems" :key="k">
              <button
                type="button" class="text-left text-sm text-red-800 underline decoration-red-300 underline-offset-2"
                @click="showProblem(p)"
              >
                {{ problemText(p) }}
              </button>
            </li>
          </ul>
          <button
            type="button" class="btn-primary mt-4" :disabled="problems.length > 0" data-testid="fb-download"
            @click="download"
          >
            {{ t('formBuilder.download', { file: fileName }) }}
          </button>
          <h3 class="moc-subtitle mt-5">{{ t('formBuilder.manifest') }}</h3>
          <pre
            class="mt-2 overflow-x-auto rounded-lg bg-stone-50 p-3 font-mono text-xs text-stone-800"
            data-testid="fb-manifest"
          >{{ manifest }}</pre>
          <details class="mt-4">
            <summary class="cursor-pointer text-sm font-medium text-stone-800">{{ t('formBuilder.showJson') }}</summary>
            <pre
              class="mt-2 max-h-96 overflow-auto rounded-lg bg-stone-50 p-3 font-mono text-xs text-stone-800"
              data-testid="fb-json"
            >{{ file }}</pre>
          </details>
        </section>

        <section class="moc-block" data-testid="form-builder-preview" aria-labelledby="fb-preview-title">
          <h2 id="fb-preview-title" class="moc-block-title">{{ t('formBuilder.preview') }}</h2>
          <p class="moc-block-hint">{{ t('formBuilder.previewHint') }}</p>
          <p v-if="!form.fields.length" class="moc-empty mt-3">{{ t('formBuilder.previewEmpty') }}</p>
          <p v-if="previewError" class="moc-state mt-3">
            {{ t('formBuilder.previewFailed') }} <code class="wrap-anywhere">{{ previewError }}</code>
          </p>
          <div ref="preview" class="mt-4" />
          <div v-if="sent" class="mt-4" data-testid="fb-sent">
            <h3 class="moc-subtitle">{{ t('formBuilder.previewData') }}</h3>
            <pre
              class="mt-2 overflow-x-auto rounded-lg bg-stone-50 p-3 font-mono text-xs text-stone-800"
            >{{ sent }}</pre>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
