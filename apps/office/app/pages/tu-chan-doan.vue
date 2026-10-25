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
import data from '~/data/tu-chan-doan.json'
import type { HpdiAnswers, HpdiAssessmentRow, HpdiEvidence, HpdiEvidenceData, HpdiFramework, HpdiKey, HpdiLink,
  HpdiText } from '~/utils/hpdi'

// Tự chẩn đoán mức trưởng thành H-P-D-I (docs/tu-chan-doan.md). Bộ câu do đội tự viết (app/data/tu-chan-doan.json),
// không phải bộ chỉ số chính thức; cách chấm ở app/utils/hpdi.ts. Lãnh đạo đơn vị (director): trả lời, xem radar, lệch
// nền, bước tiếp theo; cạnh mỗi không gian là bằng chứng đo được — số đếm của đơn vị lấy từ các khung nhìn đã có
// (dashboard F3.11, số đo F4.6, độ chính xác tác tử F4.1/F4.3, hồ sơ F3.8) bằng token người xem, Hasura lọc theo đơn
// vị; lưu kết quả vào office.maturity_assessments (migration 1792281603100) để xem tiến bộ. Lãnh đạo phòng (manager)
// trả lời, xem kết quả nhưng không lưu, không có bằng chứng (các khung nhìn đó chỉ lãnh đạo đơn vị đọc).

const FRAMEWORK = data as HpdiFramework
const EVIDENCE = `{
  office_v_document_counts { direction restricted status overdue documents }
  office_v_time_to_assign(where: {month: {_is_null: true}}) { sample month assigned median_hours }
  office_v_overdue_rate(where: {month: {_is_null: true}}) { sample month judged late }
  office_v_feedback_summary(where: {screen: {_is_null: true}}) { sample screen feedback rating_total }
  office_v_intake_accuracy { suggested kept }
  office_v_assignment_suggestion_accuracy { decided kept_unit }
  office_case_files { status }
}`
const COLUMNS = 'id created_at framework answers h p d i note'
const HISTORY = `{ office_maturity_assessments(order_by: {created_at: desc}, limit: 20) { ${COLUMNS} } }`
const SAVE = `mutation ($o: office_maturity_assessments_insert_input!) {
  insert_office_maturity_assessments_one(object: $o) { ${COLUMNS} } }`
const NOTE_MAX = 300
const BRAND = '#0f766e'
const PREVIOUS = '#a8a29e'

const { t, locale } = useI18n()
const { gql } = useApi()
const notice = useNotice()
const claims = useAuth().claims
const role = computed(() => claims.value?.role ?? null)
const allowed = computed(() => hpdiAccess(role.value).open)
const leader = computed(() => hpdiAccess(role.value).leader)

const answers = reactive<HpdiAnswers>({})
const note = ref('')
const evidence = ref<HpdiEvidence[]>([])
const sample = ref(false)
const history = ref<HpdiAssessmentRow[]>([])
const savedId = ref<string | null>(null)
const loaded = ref(false)
const loading = ref(false)
const failure = ref('')
const saving = ref(false)
const saveFailure = ref('')

function setAnswers(next: HpdiAnswers) {
  for (const k of Object.keys(answers)) delete answers[k]
  Object.assign(answers, next)
}

// Bản dở giữ trong thẻ trình duyệt (như form soạn): hết phiên đăng nhập, quay lại vẫn còn câu đã chọn
const draft = useFormDraft<{ answers: HpdiAnswers; note: string }>(
  () => (claims.value ? `${claims.value.userId}:tu-chan-doan` : null),
  () => ({ answers: { ...answers }, note: note.value }),
  (kept) => {
    setAnswers(hpdiCleanAnswers(FRAMEWORK, kept.answers))
    note.value = typeof kept.note === 'string' ? kept.note.slice(0, NOTE_MAX) : ''
  },
)

async function load() {
  loading.value = true
  failure.value = ''
  try {
    const [ev, hist] = await Promise.all([
      gql<{
        office_v_document_counts: HpdiEvidenceData['counts']
        office_v_time_to_assign: HpdiEvidenceData['assign']
        office_v_overdue_rate: HpdiEvidenceData['overdue']
        office_v_feedback_summary: HpdiEvidenceData['feedback']
        office_v_intake_accuracy: HpdiEvidenceData['intake']
        office_v_assignment_suggestion_accuracy: HpdiEvidenceData['suggestions']
        office_case_files: HpdiEvidenceData['caseFiles']
      }>(EVIDENCE),
      gql<{ office_maturity_assessments: HpdiAssessmentRow[] }>(HISTORY),
    ])
    const measured: HpdiEvidenceData = {
      counts: ev.office_v_document_counts,
      assign: ev.office_v_time_to_assign,
      overdue: ev.office_v_overdue_rate,
      feedback: ev.office_v_feedback_summary,
      intake: ev.office_v_intake_accuracy,
      suggestions: ev.office_v_assignment_suggestion_accuracy,
      caseFiles: ev.office_case_files,
    }
    evidence.value = hpdiEvidence(measured)
    sample.value = hpdiSample(measured)
    history.value = hist.office_maturity_assessments
    loaded.value = true
  } catch (e) {
    failure.value = errorText(t, e)
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  if (!allowed.value) return
  draft.resume()
  if (leader.value) load()
})

const total = hpdiQuestions(FRAMEWORK).length
const answered = computed(() => hpdiAnswered(FRAMEWORK, answers))
const complete = computed(() => answered.value === total)
const scores = computed(() => hpdiScores(FRAMEWORK, answers))
const gaps = computed(() => hpdiGaps(scores.value))
const focus = computed(() => hpdiFocus(scores.value))
// Tỷ trọng, hình dạng theo giáo trình DX-OS mục 2.4; GIGO: [I] trên nền [D] chưa vững hoặc Ảo giác công nghệ
const shares = computed(() => hpdiShares(scores.value))
const shape = computed(() => (shares.value ? hpdiShape(shares.value) : null))
const gigo = computed(() => hpdiGigo(scores.value, shape.value))
const steps = computed(() => hpdiNextSteps(FRAMEWORK, answers))
// So với lần lưu gần nhất trước đó (vừa lưu xong thì so với lần trước nữa, không so với chính nó)
const previous = computed(() => history.value.find((r) => r.id !== savedId.value) ?? null)
const previousScores = computed(() => (previous.value ? hpdiRowScores(previous.value) : null))

const number = computed(() => new Intl.NumberFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB',
  { maximumFractionDigits: 1 }))
const units = computed(() => ({ second: t('metrics.unit.second'), minute: t('metrics.unit.minute'),
  hour: t('metrics.unit.hour'), day: t('metrics.unit.day') }))
function text(x: HpdiText) {
  return hpdiText(x, locale.value)
}
function score(v: number | null) {
  return v === null ? '—' : number.value.format(v)
}
function spaceName(key: HpdiKey) {
  const s = FRAMEWORK.spaces.find((x) => x.key === key)
  return `[${key.toUpperCase()}] ${s ? text(s.name) : ''}`
}
// Liên kết tới trang người xem không mở được: tên trang và vai trò làm việc đó
function otherPage(l: HpdiLink) {
  return t('hpdi.linkFor', { page: text(l.label), roles: (l.roles ?? []).map((r) => t(`role.${r}`)).join(', ') })
}
function evidenceValue(e: HpdiEvidence) {
  const params = Object.fromEntries(Object.entries(e.values).map(([k, v]) =>
    [k, k === 'hours' ? fmtDuration(v, units.value, (n) => number.value.format(n)) : number.value.format(v)]))
  return t(`hpdi.evidence.${e.id}.value`, params)
}
const evidenceBySpace = computed(() => Object.fromEntries(HPDI_KEYS.map((k) =>
  [k, evidence.value.filter((e) => e.space === k)])) as Record<HpdiKey, HpdiEvidence[]>)

// Radar 4 trục 0–5 như bài 2.4 của giáo trình DX-OS vẽ HPDI, nhưng trục là mức tự đánh giá chứ không phải tỷ trọng %
const radar = computed(() => {
  const series: Record<string, unknown>[] = [{
    name: t('hpdi.now'),
    value: hpdiRadarValues(scores.value),
    itemStyle: { color: BRAND },
    lineStyle: { color: BRAND },
    areaStyle: { color: BRAND, opacity: 0.15 },
  }]
  if (previousScores.value && previous.value) {
    series.push({
      name: t('hpdi.previous', { date: fmtDate(previous.value.created_at) }),
      value: hpdiRadarValues(previousScores.value),
      itemStyle: { color: PREVIOUS },
      lineStyle: { color: PREVIOUS, type: 'dashed' },
    })
  }
  return {
    tooltip: {},
    legend: { bottom: 0 },
    radar: {
      indicator: HPDI_KEYS.map((k) => ({ name: spaceName(k), min: 0, max: HPDI_TOP })),
      splitNumber: HPDI_TOP,
      radius: '60%',
      center: ['50%', '46%'],
    },
    series: [{ type: 'radar', data: series }],
  }
})
const radarLabel = computed(() => HPDI_KEYS.map((k) => `${spaceName(k)}: ${score(scores.value[k])}`).join(', '))

function fillFromPrevious() {
  const last = history.value[0]
  if (last) setAnswers(hpdiCleanAnswers(FRAMEWORK, last.answers))
}
function reset() {
  setAnswers({})
  note.value = ''
}

async function save() {
  if (!leader.value || !complete.value) return
  saving.value = true
  saveFailure.value = ''
  try {
    const row = (await gql<{ insert_office_maturity_assessments_one: HpdiAssessmentRow }>(SAVE, {
      o: hpdiSaveInput(FRAMEWORK, answers, note.value),
    })).insert_office_maturity_assessments_one
    savedId.value = row.id
    history.value = [row, ...history.value]
    note.value = ''
    notice.ok(t('hpdi.saved'))
  } catch (e) {
    saveFailure.value = errorText(t, e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <PageHeader :title="t('hpdi.title')" :subtitle="t('hpdi.subtitle')">
      <button v-if="allowed && leader" class="btn-secondary" :disabled="loading" @click="load">
        {{ t('app.refresh') }}
      </button>
    </PageHeader>
    <p v-if="!allowed" class="card p-12 text-center text-stone-500">{{ t('hpdi.forbidden') }}</p>

    <div v-else class="space-y-4">
      <section class="card space-y-2 p-4 text-sm text-stone-600" data-testid="hpdi-intro">
        <p>{{ t('hpdi.intro') }}</p>
        <p class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-900">{{ t('hpdi.disclaimer') }}</p>
        <p v-if="!leader" class="text-stone-500" data-testid="hpdi-manager-note">{{ t('hpdi.managerNote') }}</p>
        <div class="flex flex-wrap items-center gap-2 pt-1">
          <span class="font-medium text-stone-900" data-testid="hpdi-progress">
            {{ t('hpdi.progress', { n: answered, total }) }}
          </span>
          <button v-if="leader && history.length" type="button" class="btn-secondary" data-testid="hpdi-fill"
            @click="fillFromPrevious">
            {{ t('hpdi.fill') }}
          </button>
          <button v-if="answered" type="button" class="btn-ghost" @click="reset">{{ t('hpdi.reset') }}</button>
        </div>
      </section>

      <p v-if="leader && failure" class="card p-4 text-sm text-red-700">{{ failure }}</p>
      <p v-if="leader && sample" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        data-testid="hpdi-sample">
        {{ t('metrics.sampleNote') }}
      </p>

      <section v-for="s in FRAMEWORK.spaces" :key="s.key" class="card p-4" :data-testid="`hpdi-space-${s.key}`">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="font-medium text-stone-900">{{ spaceName(s.key) }}</h2>
          <span class="text-sm text-stone-500 tabular-nums">
            {{ t('hpdi.spaceScore', { score: score(scores[s.key]) }) }}
          </span>
        </div>
        <p class="mt-1 text-sm text-stone-600">{{ text(s.summary) }}</p>
        <div class="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
          <div class="space-y-5">
            <fieldset v-for="q in s.questions" :key="q.id" class="space-y-1.5" :data-testid="`hpdi-q-${q.id}`">
              <legend class="mb-1 text-sm font-medium text-stone-900">
                {{ q.id.toUpperCase() }}. {{ text(q.title) }}
                <span class="block font-normal text-stone-600">{{ text(q.text) }}</span>
              </legend>
              <label
                v-for="(level, n) in q.levels" :key="n"
                class="flex cursor-pointer gap-3 rounded-md border px-3 py-2 text-sm"
                :class="answers[q.id] === n + 1 ? 'border-brand-600 bg-brand-50' : 'border-stone-200 hover:bg-stone-50'"
              >
                <input v-model="answers[q.id]" type="radio" :name="q.id" :value="n + 1" class="mt-0.5 accent-brand-700">
                <span>
                  <span class="font-medium text-stone-900">{{ t('hpdi.level', { n: n + 1 }) }}</span>
                  · {{ text(level) }}
                </span>
              </label>
            </fieldset>
          </div>
          <aside v-if="leader" class="self-start rounded-lg bg-stone-50 p-3 text-sm"
            :data-testid="`hpdi-evidence-${s.key}`">
            <h3 class="text-xs font-medium tracking-wide text-stone-500 uppercase">{{ t('hpdi.evidenceTitle') }}</h3>
            <p v-if="!loaded" class="mt-2 text-stone-500">{{ loading ? t('app.loading') : '—' }}</p>
            <dl v-else-if="evidenceBySpace[s.key].length" class="mt-2 space-y-2">
              <div v-for="e in evidenceBySpace[s.key]" :key="e.id" :data-testid="`hpdi-ev-${e.id}`">
                <dt class="text-stone-500">{{ t(`hpdi.evidence.${e.id}.name`) }}</dt>
                <dd class="font-medium text-stone-900 tabular-nums">{{ evidenceValue(e) }}</dd>
              </div>
            </dl>
            <p v-else class="mt-2 text-stone-500">{{ t('hpdi.evidenceNone') }}</p>
            <p class="mt-3 text-xs text-stone-500">{{ t('hpdi.evidenceHint') }}</p>
          </aside>
        </div>
      </section>

      <section class="card p-4" data-testid="hpdi-result">
        <h2 class="font-medium text-stone-900">{{ t('hpdi.result') }}</h2>
        <p v-if="!complete" class="py-8 text-center text-sm text-stone-500">
          {{ t('hpdi.answerAll', { n: total - answered }) }}
        </p>
        <div v-else class="mt-2 grid gap-4 lg:grid-cols-2">
          <div>
            <EChart :option="radar" :height="320" :label="radarLabel" />
            <table class="mt-2 w-full text-sm" data-testid="hpdi-scores">
              <thead class="text-left text-xs text-stone-500">
                <tr>
                  <th class="py-1 font-medium">{{ t('hpdi.space') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('hpdi.now') }}</th>
                  <th v-if="previousScores" class="py-1 text-right font-medium">{{ t('hpdi.previousShort') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-stone-100">
                <tr v-for="k in HPDI_KEYS" :key="k">
                  <td class="py-1 text-stone-600">{{ spaceName(k) }}</td>
                  <td class="py-1 text-right font-medium tabular-nums" :data-testid="`hpdi-score-${k}`">
                    {{ score(scores[k]) }}
                  </td>
                  <td v-if="previousScores" class="py-1 text-right text-stone-500 tabular-nums">
                    {{ score(previousScores[k]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="space-y-4 text-sm">
            <div data-testid="hpdi-focus">
              <h3 class="font-medium text-stone-900">{{ t('hpdi.focusTitle') }}</h3>
              <!-- [I] là không gian cuối: không còn "không gian sau" để nói tới -->
              <p v-if="focus === 'i'" class="mt-1 text-stone-700">
                {{ t('hpdi.focusLast', { space: spaceName(focus) }) }}
              </p>
              <p v-else-if="focus" class="mt-1 text-stone-700">{{ t('hpdi.focus', { space: spaceName(focus) }) }}</p>
              <p v-else class="mt-1 text-stone-700">{{ t('hpdi.focusNone') }}</p>
            </div>
            <div data-testid="hpdi-gaps">
              <h3 class="font-medium text-stone-900">{{ t('hpdi.gapsTitle') }}</h3>
              <p v-if="!gaps.length" class="mt-1 text-stone-700">{{ t('hpdi.gapsNone') }}</p>
              <ul v-else class="mt-1 space-y-1">
                <li v-for="g in gaps" :key="g.to" class="rounded-md bg-amber-50 px-3 py-2 text-amber-900">
                  {{ t('hpdi.gap', { to: spaceName(g.to), from: spaceName(g.from), diff: number.format(g.diff) }) }}
                </li>
              </ul>
              <p class="mt-1 text-xs text-stone-500">{{ t('hpdi.gapsHint') }}</p>
            </div>
            <div v-if="shape && shares" data-testid="hpdi-shape">
              <h3 class="font-medium text-stone-900">{{ t('hpdi.shapeTitle') }}</h3>
              <p class="mt-1 text-stone-700">
                <span class="font-medium" :data-testid="`hpdi-shape-${shape}`">
                  {{ t(`hpdi.shape.${shape}.name`) }}</span>: {{ t(`hpdi.shape.${shape}.text`) }}
              </p>
              <p class="mt-1 text-stone-600 tabular-nums" data-testid="hpdi-shares">
                {{ t('hpdi.shares', { h: number.format(shares.h), p: number.format(shares.p),
                                      d: number.format(shares.d), i: number.format(shares.i) }) }}
              </p>
              <p class="mt-1 text-xs text-stone-500">{{ t('hpdi.shapeHint') }}</p>
            </div>
            <div v-if="gigo" class="rounded-md bg-red-50 px-3 py-2 text-red-900" data-testid="hpdi-gigo">
              <h3 class="font-medium">{{ t('hpdi.gigoTitle') }}</h3>
              <p class="mt-1">{{ t('hpdi.gigo') }}</p>
              <p class="mt-1">
                <span v-if="!hpdiLinkOpen(HPDI_QUALITY_LINK, role)" data-testid="hpdi-gigo-other">
                  {{ otherPage(HPDI_QUALITY_LINK) }}
                </span>
                <!-- #chat-luong: mục "Kiểm chất lượng số liệu" của trang Phả hệ số liệu -->
                <NuxtLink v-else :to="{ path: HPDI_QUALITY_LINK.to, hash: '#chat-luong' }"
                          class="font-medium underline">
                  {{ text(HPDI_QUALITY_LINK.label) }}
                </NuxtLink>
              </p>
            </div>
          </div>
        </div>
      </section>

      <section v-if="steps.length" class="card p-4" data-testid="hpdi-steps">
        <h2 class="font-medium text-stone-900">{{ t('hpdi.steps') }}</h2>
        <ul class="mt-2 divide-y divide-stone-100">
          <li v-for="st in steps" :key="st.space" class="py-3 text-sm" :data-testid="`hpdi-step-${st.space}`">
            <div class="flex flex-wrap items-center gap-2">
              <span class="chip bg-brand-50 text-brand-800">{{ spaceName(st.space) }}</span>
              <span v-if="st.space === focus" class="chip bg-amber-100 text-amber-900">{{ t('hpdi.first') }}</span>
              <span class="text-stone-500">
                {{ t('hpdi.stepFrom', { q: st.question.id.toUpperCase(), title: text(st.question.title),
                                        n: st.level }) }}
              </span>
            </div>
            <p class="mt-1 text-stone-700">{{ text(st.question.next) }}</p>
            <p class="mt-1 flex flex-wrap gap-x-4 gap-y-1">
              <template v-for="l in st.question.links" :key="l.to">
                <!-- trang người xem không mở được: hiện tên trang và vai trò làm việc đó, không dẫn tới -->
                <span v-if="!hpdiLinkOpen(l, role)" class="text-stone-500" data-testid="hpdi-link-other">
                  {{ otherPage(l) }}
                </span>
                <a v-else-if="l.to.startsWith('/ca-nhan')" :href="l.to" class="text-brand-700 hover:underline">
                  {{ text(l.label) }}
                </a>
                <NuxtLink v-else :to="l.to" class="text-brand-700 hover:underline">{{ text(l.label) }}</NuxtLink>
              </template>
            </p>
          </li>
        </ul>
      </section>

      <section v-if="leader" class="card p-4" data-testid="hpdi-save">
        <h2 class="font-medium text-stone-900">{{ t('hpdi.saveTitle') }}</h2>
        <p class="mt-1 text-sm text-stone-500">{{ t('hpdi.saveHint') }}</p>
        <form class="mt-3 space-y-2" @submit.prevent="save">
          <label class="label" for="hpdi-note">{{ t('hpdi.note') }}</label>
          <textarea id="hpdi-note" v-model="note" class="input" rows="2" :maxlength="NOTE_MAX"
            :placeholder="t('hpdi.notePlaceholder')" />
          <p v-if="saveFailure" class="text-sm text-red-700">{{ saveFailure }}</p>
          <button type="submit" class="btn-primary" :disabled="!complete || saving" data-testid="hpdi-save-button">
            {{ saving ? t('hpdi.saving') : t('hpdi.save') }}
          </button>
          <span v-if="!complete" class="ml-2 text-xs text-stone-500">
            {{ t('hpdi.answerAll', { n: total - answered }) }}
          </span>
        </form>

        <h3 class="mt-6 font-medium text-stone-900">{{ t('hpdi.history') }}</h3>
        <p v-if="!history.length" class="py-6 text-center text-sm text-stone-500">{{ t('hpdi.historyNone') }}</p>
        <div v-else class="overflow-x-auto">
          <table class="mt-2 w-full min-w-[32rem] text-sm" data-testid="hpdi-history">
            <thead class="text-left text-xs text-stone-500">
              <tr>
                <th class="py-1 font-medium">{{ t('hpdi.when') }}</th>
                <th v-for="k in HPDI_KEYS" :key="k" class="py-1 text-right font-medium">[{{ k.toUpperCase() }}]</th>
                <th class="py-1 pl-3 font-medium">{{ t('hpdi.note') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="r in history" :key="r.id">
                <td class="py-1 whitespace-nowrap text-stone-600">{{ fmtDateTime(r.created_at) }}</td>
                <td v-for="k in HPDI_KEYS" :key="k" class="py-1 text-right font-medium tabular-nums">
                  {{ score(hpdiRowScores(r)[k]) }}
                </td>
                <td class="py-1 pl-3 text-stone-600">{{ r.note ?? '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card p-4 text-sm" data-testid="hpdi-sources">
        <h2 class="font-medium text-stone-900">{{ t('hpdi.sources') }}</h2>
        <ul class="mt-2 list-disc space-y-1 pl-5 text-stone-600">
          <li v-for="src in FRAMEWORK.sources" :key="src.url">
            <a :href="src.url" class="text-brand-700 hover:underline" target="_blank" rel="noopener noreferrer">
              {{ text(src.title) }}
            </a>
          </li>
        </ul>
        <p class="mt-2 text-xs text-stone-500">{{ t('hpdi.sourcesNote', { id: FRAMEWORK.id }) }}</p>
      </section>
    </div>
  </div>
</template>
