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
import type { SuggestApply } from '~/utils/assignSuggest'
import type { ProcessingBrief } from '~/utils/taskContext'

// Khung xử lý việc đang chờ người dùng trên một văn bản (formKey trong services/svc-workflow/processes/*.bpmn20.xml).
// Gửi completeTask; svc-workflow kiểm lại dữ liệu và quyền, Flowable chuyển sang bước tiếp theo.

export interface PanelUser { id: string; full_name: string; role: string; department_id: string | null }
export interface PanelDepartment { id: string; code: string; name: string }

const props = defineProps<{
  taskId: string
  formKey: string
  documentId: string
  documentDue: string | null
  restricted?: boolean
  users: PanelUser[]
  departments: PanelDepartment[]
  myDepartment: string | null
  myId: string
  // phần việc được giao cho người xem (vbden.xuLy), trang văn bản tính từ các lượt giao
  brief?: ProcessingBrief | null
}>()
const emit = defineEmits<{ done: [] }>()

const { t } = useI18n()
const { gql, preview } = useApi()
const notice = useNotice()
const busy = ref(false)
const tried = ref(false)

// vbden.chiDao
const direct = reactive({
  instruction: '',
  leadKind: 'department' as 'department' | 'user',
  lead_department_id: '',
  lead_user_id: '',
  supports: [] as string[],
  due_on: props.documentDue ?? addDays(today(), 7),
})
const fileNote = ref('')
// vbden.phanCong
const assign = reactive({ user_id: '', note: '' })
// vbden.xuLy
const result = ref('')
const resultField = ref<HTMLTextAreaElement | null>(null)
// vbdi.duyetPhong, vbdi.duyetDonVi: ý kiến; trả lại thì bắt buộc
const reviewNote = ref('')
const returning = ref(false)
// vbdi.phatHanh: mặc định không công khai trích yếu — phần lớn văn bản đi chỉ lưu hành nội bộ;
// văn bản hạn chế thì không bao giờ (CSDL và svc-workflow cũng chặn)
const isPublic = ref(false)

const handlers = computed(() => props.users.filter((u) => u.role === 'staff' || u.role === 'manager'))
const myPeople = computed(() => props.users.filter((u) => u.department_id === props.myDepartment && u.id !== props.myId && (u.role === 'staff' || u.role === 'manager')))
const deptName = (id: string | null) => props.departments.find((d) => d.id === id)?.name ?? ''

const directErrors = computed(() => {
  const e: Record<string, string> = {}
  if (!direct.instruction.trim()) e.instruction = t('validation.required')
  if (direct.leadKind === 'department' && !direct.lead_department_id) e.lead = t('validation.required')
  if (direct.leadKind === 'user' && !direct.lead_user_id) e.lead = t('validation.required')
  if (direct.due_on && direct.due_on < today()) e.due_on = t('validation.dueBefore')
  return e
})

async function complete(outcome: string, data: Record<string, unknown>) {
  // bấm hai lần lúc đang gửi: lượt sau không gửi lại completeTask
  if (busy.value) return
  busy.value = true
  try {
    await gql(
      'mutation ($t: String!, $o: String!, $d: jsonb) { completeTask(taskId: $t, outcome: $o, data: $d) { task_id } }',
      { t: props.taskId, o: outcome, d: data },
    )
    notice.ok(t('form.done'))
    emit('done')
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    busy.value = false
  }
}

// Gợi ý giao việc (F4.3): "Dùng gợi ý" chỉ điền form — giao cho phòng được gợi ý (bỏ phòng đó khỏi phòng phối hợp),
// đặt hạn nếu có hạn gợi ý. Không gửi gì: lãnh đạo sửa nếu muốn rồi tự bấm "Giao xử lý".
const suggestedLead = computed(() => (direct.leadKind === 'department' ? direct.lead_department_id || null : null))
function takeSuggestion(p: SuggestApply) {
  direct.leadKind = 'department'
  direct.lead_department_id = p.department_id
  direct.supports = direct.supports.filter((d) => d !== p.department_id)
  if (p.due_on) direct.due_on = p.due_on
}

async function submitDirect() {
  tried.value = true
  if (Object.keys(directErrors.value).length) {
    await focusInvalidField()
    return
  }
  complete('direct', {
    instruction: direct.instruction.trim(),
    ...(direct.leadKind === 'department' ? { lead_department_id: direct.lead_department_id } : { lead_user_id: direct.lead_user_id }),
    supports: direct.supports.filter((d) => d !== direct.lead_department_id),
    due_on: direct.due_on || null,
  })
}

async function submitAssign() {
  tried.value = true
  if (!assign.user_id) {
    await focusInvalidField()
    return
  }
  complete('assign', { user_id: assign.user_id, note: assign.note.trim() || null })
}

function approve() {
  complete('approve', { note: reviewNote.value.trim() || null })
}

async function sendBack() {
  returning.value = true
  if (!reviewNote.value.trim()) {
    await focusInvalidField()
    return
  }
  complete('return', { note: reviewNote.value.trim() })
}

function issue() {
  if (!confirm(t('form.phatHanh.confirm'))) return
  complete('issue', { is_public: isPublic.value && !props.restricted })
}

function submitDone() {
  tried.value = true
  if (!result.value.trim()) {
    resultField.value?.focus()
    return
  }
  complete('done', { result_note: result.value.trim() })
}
</script>

<template>
  <section
    class="card sg-action-panel" :aria-busy="busy" data-testid="task-panel"
  >
    <div class="sg-action-head">
      <h2>{{ t(`task.${formKey}`) }}</h2>
      <span v-if="busy" class="text-sm text-stone-600" role="status">{{ t('form.processing') }}</span>
    </div>

    <!-- Lãnh đạo đơn vị chỉ đạo -->
    <form v-if="formKey === 'vbden.chiDao'" class="space-y-4 p-5" novalidate @submit.prevent="submitDirect">
      <!-- gợi ý của tác tử; văn bản hạn chế không bao giờ có gợi ý -->
      <AssignSuggestion
        v-if="!restricted" :document-id="documentId" :departments="departments" :chosen="suggestedLead"
        :document-due="documentDue" @apply="takeSuggestion"
      />
      <div>
        <label class="label" for="instruction">{{ t('form.chiDao.instruction') }}</label>
        <textarea id="instruction" v-model="direct.instruction" rows="3" class="input" maxlength="2000"
                  required :aria-invalid="tried && !!directErrors.instruction"
                  :aria-describedby="tried && directErrors.instruction ? 'instruction-error' : undefined" />
        <p v-if="tried && directErrors.instruction" id="instruction-error" class="field-error">
          {{ directErrors.instruction }}
        </p>
      </div>
      <fieldset>
        <legend class="label">{{ t('form.chiDao.leadKind') }}</legend>
        <div class="flex gap-4 text-sm">
          <label class="flex items-center gap-2"><input v-model="direct.leadKind" type="radio" value="department" class="accent-brand-700"> {{ t('form.chiDao.leadDepartment') }}</label>
          <label class="flex items-center gap-2"><input v-model="direct.leadKind" type="radio" value="user" class="accent-brand-700"> {{ t('form.chiDao.leadUser') }}</label>
        </div>
      </fieldset>
      <div v-if="direct.leadKind === 'department'">
        <label class="label" for="lead_dept">{{ t('form.chiDao.department') }}</label>
        <select
          id="lead_dept" v-model="direct.lead_department_id" class="input" required
          :aria-invalid="tried && !!directErrors.lead"
          :aria-describedby="tried && directErrors.lead ? 'lead-error' : undefined"
        >
          <option value="">{{ t('form.pick') }}</option>
          <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
      </div>
      <div v-else>
        <label class="label" for="lead_user">{{ t('form.chiDao.user') }}</label>
        <select
          id="lead_user" v-model="direct.lead_user_id" class="input" required
          :aria-invalid="tried && !!directErrors.lead"
          :aria-describedby="tried && directErrors.lead ? 'lead-error' : undefined"
        >
          <option value="">{{ t('form.pick') }}</option>
          <option v-for="u in handlers" :key="u.id" :value="u.id">{{ u.full_name }} — {{ deptName(u.department_id) }}</option>
        </select>
      </div>
      <p v-if="tried && directErrors.lead" id="lead-error" class="field-error">{{ directErrors.lead }}</p>
      <fieldset>
        <legend class="label">{{ t('form.chiDao.supports') }} <span class="font-normal text-stone-400">({{ t('app.optional') }})</span></legend>
        <div class="grid gap-1.5 sm:grid-cols-2">
          <label v-for="d in departments.filter((x) => x.id !== direct.lead_department_id)" :key="d.id" class="flex items-center gap-2 text-sm">
            <input v-model="direct.supports" type="checkbox" :value="d.id" class="h-4 w-4 accent-brand-700"> {{ d.name }}
          </label>
        </div>
      </fieldset>
      <div class="max-w-xs">
        <label class="label" for="due">{{ t('form.chiDao.due') }}</label>
        <input
          id="due" v-model="direct.due_on" type="date" class="input" :min="today()"
          :aria-invalid="tried && !!directErrors.due_on"
          :aria-describedby="tried && directErrors.due_on ? 'due-error' : undefined"
        >
        <p v-if="tried && directErrors.due_on" id="due-error" class="field-error">{{ directErrors.due_on }}</p>
      </div>
      <div class="flex flex-wrap items-end justify-between gap-3 border-t border-stone-100 pt-4">
        <div class="flex min-w-0 flex-wrap items-end gap-2">
          <input
            v-model="fileNote" class="input w-full sm:w-56" :aria-label="t('form.chiDao.fileNote')"
            :placeholder="t('form.chiDao.fileNote')"
          >
          <button type="button" class="btn-secondary" :disabled="busy" @click="complete('file', { note: fileNote.trim() || null })">{{ t('form.chiDao.file') }}</button>
        </div>
        <button type="submit" class="btn-primary" :disabled="busy">{{ t('form.chiDao.direct') }}</button>
      </div>
    </form>

    <!-- Lãnh đạo phòng phân công -->
    <form v-else-if="formKey === 'vbden.phanCong'" class="space-y-4 p-5" novalidate @submit.prevent="submitAssign">
      <div>
        <label class="label" for="assignee">{{ t('form.phanCong.user') }}</label>
        <select id="assignee" v-model="assign.user_id" class="input" required :aria-invalid="tried && !assign.user_id"
          :aria-describedby="tried && !assign.user_id ? 'assignee-error' : undefined">
          <option value="">{{ t('form.pick') }}</option>
          <option v-for="u in myPeople" :key="u.id" :value="u.id">{{ u.full_name }}</option>
        </select>
        <p v-if="tried && !assign.user_id" id="assignee-error" class="field-error">{{ t('validation.required') }}</p>
      </div>
      <div>
        <label class="label" for="note">{{ t('form.phanCong.note') }} <span class="font-normal text-stone-400">({{ t('app.optional') }})</span></label>
        <textarea id="note" v-model="assign.note" rows="2" class="input" maxlength="2000" />
      </div>
      <div class="flex flex-wrap justify-end gap-2 border-t border-stone-100 pt-4">
        <button type="button" class="btn-secondary" :disabled="busy" @click="complete('self', { note: assign.note.trim() || null })">{{ t('form.phanCong.self') }}</button>
        <button type="submit" class="btn-primary" :disabled="busy">{{ t('form.phanCong.assign') }}</button>
      </div>
    </form>

    <!-- Chuyên viên báo kết quả -->
    <form v-else-if="formKey === 'vbden.xuLy'" class="space-y-4 p-5" novalidate @submit.prevent="submitDone">
      <!-- chỉ đạo, người giao, hạn của phần việc này: không phải cuộn xuống dòng xử lý để đọc lại -->
      <div v-if="brief" class="sg-assignment-brief" data-testid="processing-brief">
        <h3 class="text-sm font-semibold">{{ t('form.xuLy.brief') }}</h3>
        <p v-for="line in brief.instructions" :key="line" class="mt-2 whitespace-pre-line text-sm">{{ line }}</p>
        <dl class="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <div v-if="brief.assignedBy">
            <dt class="text-stone-500">{{ t('form.xuLy.assignedBy') }}</dt>
            <dd class="font-medium">{{ users.find((u) => u.id === brief?.assignedBy)?.full_name || t('app.none') }}</dd>
          </div>
          <div>
            <dt class="text-stone-500">{{ t('doc.due') }}</dt>
            <dd class="font-medium">{{ brief.dueOn ? fmtDate(brief.dueOn) : t('desk.noDeadline') }}</dd>
          </div>
        </dl>
      </div>
      <div>
        <label class="label" for="result">
          {{ t('form.xuLy.result') }} <span class="font-normal text-stone-500">({{ t('form.xuLy.required') }})</span>
        </label>
        <textarea
          id="result" ref="resultField" v-model="result" rows="4" class="input" maxlength="4000" required
          aria-required="true" aria-describedby="result-help result-error" :aria-invalid="tried && !result.trim()"
        />
        <p id="result-help" class="mt-2 text-sm text-stone-500">{{ t('form.xuLy.consequence') }}</p>
        <p id="result-error" v-show="tried && !result.trim()" class="field-error" role="alert">
          {{ t('validation.required') }}
        </p>
      </div>
      <div class="flex justify-end border-t border-stone-100 pt-4">
        <button type="submit" class="btn-primary" :disabled="busy">{{ t('form.xuLy.done') }}</button>
      </div>
    </form>

    <!-- Lãnh đạo phòng, người ký duyệt dự thảo văn bản đi -->
    <form v-else-if="formKey === 'vbdi.duyetPhong' || formKey === 'vbdi.duyetDonVi'" class="space-y-4 p-5" novalidate @submit.prevent="approve">
      <button type="button" class="btn-secondary" @click="preview(documentId).catch((e) => notice.error(errorText(t, e)))">
        {{ t('form.duyet.preview') }}
      </button>
      <div>
        <label class="label" for="review-note">{{ t('form.duyet.note') }}</label>
        <textarea id="review-note" v-model="reviewNote" rows="3" class="input" maxlength="2000"
                  :placeholder="t('form.duyet.returnNote')" :aria-invalid="returning && !reviewNote.trim()"
                  :aria-describedby="returning && !reviewNote.trim() ? 'review-note-error' : undefined" />
        <p v-if="returning && !reviewNote.trim()" id="review-note-error" class="field-error">
          {{ t('form.duyet.returnNote') }}
        </p>
      </div>
      <div class="flex flex-wrap justify-end gap-2 border-t border-stone-100 pt-4">
        <button type="button" class="btn-secondary" :disabled="busy" @click="sendBack">{{ t('form.duyet.return') }}</button>
        <button type="submit" class="btn-primary" :disabled="busy">
          {{ formKey === 'vbdi.duyetDonVi' ? t('form.duyet.sign') : t('form.duyet.approve') }}
        </button>
      </div>
    </form>

    <!-- Văn thư cấp số, phát hành -->
    <form v-else-if="formKey === 'vbdi.phatHanh'" class="space-y-4 p-5" @submit.prevent="issue">
      <p v-if="restricted" class="text-sm text-stone-600" data-testid="issue-private">{{ t('form.phatHanh.restricted') }}</p>
      <label v-else class="flex items-start gap-2 text-sm">
        <input v-model="isPublic" type="checkbox" class="mt-0.5 h-4 w-4 accent-brand-700">
        <span>{{ t('form.phatHanh.public') }}<span class="block text-xs text-stone-500">{{ t('form.phatHanh.publicHint') }}</span></span>
      </label>
      <div class="flex flex-wrap justify-end gap-2 border-t border-stone-100 pt-4">
        <button type="button" class="btn-secondary" @click="preview(documentId).catch((e) => notice.error(errorText(t, e)))">
          {{ t('form.duyet.preview') }}
        </button>
        <button type="submit" class="btn-primary" :disabled="busy">{{ t('form.phatHanh.issue') }}</button>
      </div>
    </form>
  </section>
</template>
