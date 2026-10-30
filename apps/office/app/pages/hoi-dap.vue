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
import { ApiError } from '~/composables/useApi'
import type { AskBody, AskResult, AskSource } from '~/composables/useApi'
import {
  ASK_ROLES, MAX_QUESTION, SCOPE_PARAM, SUGGEST_GROUPS, blocks, canView, citeLabel, cleanQuestion, fallbackSuggestions,
  hasMask, inAssistant, needsGenerate, pageUrl, previousFor, scopeOf, searched, sourceAnchor, tidy,
} from '~/utils/answer'

// Hỏi đáp trên kho văn bản (F4.2). Trợ lý moc-assistant (svc-files) chỉ tìm trong các văn bản người hỏi được xem,
// văn bản hạn chế không bao giờ vào chỉ mục. Hai pha cho mỗi câu hỏi: extract trả ngay câu trích nguyên văn kèm
// nguồn "số ký hiệu · tr. n" (< 1 giây, không cần mô hình); nếu mô hình sẵn sàng (ai_available) thì tự gọi generate
// với cùng ask_id — mô hình viết câu trả lời có trích dẫn [n] trong 15–40 giây, bấm Dừng hoặc Esc thì thôi, câu trích
// vẫn còn đó. Danh sách chỉ giữ trong bộ nhớ trang (tối đa 10), không lưu ở đâu cả. Câu hỏi mới gửi kèm câu hỏi của
// lượt ngay trước cùng phạm vi (previous) để svc-files hiểu câu nối tiếp ("Còn khoa Kinh tế thì sao?"); bộ định tuyến
// của svc-files trả đường đã chọn (route) và câu đã ghép (rewritten), trang hiện thành dòng "Đã hiểu là câu hỏi về: …".
// Mở từ nút "Hỏi về văn bản này" (?van_ban=<id>) thì chỉ hỏi trong văn bản đó; nhãn nguồn mở tệp đúng trang được trích.
// Bố cục như một cuộc trò chuyện: một cột giữa vùng làm việc, câu hỏi cũ ở trên, mới ở dưới, khung soạn câu hỏi dính
// đáy màn hình (main.css, mục "Hỏi đáp").

interface Turn {
  key: number
  question: string
  direction: '' | 'in' | 'out'
  year: number | null
  document: { id: string; label: string } | null   // hỏi trong một văn bản: id, nhãn lúc hỏi
  previous: string | undefined                       // câu trước đã gửi ở lượt extract, gửi lại y nguyên ở generate
  phase: 'searching' | 'error' | 'shown'
  result: AskResult | null
  error: string
  // pha viết câu trả lời: chờ lượt (một lượt viết một lúc), đang viết, đã dừng, lỗi, xong
  gen: 'idle' | 'waiting' | 'running' | 'stopped' | 'failed' | 'done'
  genError: string
  started: number
  showExtract: boolean     // đã có câu trả lời của mô hình: người dùng mở thêm khối câu trích nguyên văn
  opened: number[]         // nguồn đang mở phần chi tiết (trích yếu đủ, đoạn trích, loại, nơi ban hành)
}

const MAX_TURNS = 10

const { t, te } = useI18n()
const { ask, gql, viewFile } = useApi()
const notice = useNotice()
const route = useRoute()
const router = useRouter()
const claims = useAuth().claims

const allowed = computed(() => ASK_ROLES.includes(claims.value?.role ?? ''))
// Từ trang Tìm kiếm ("Hỏi trợ lý"): điền sẵn câu tìm, không tự gửi
const text = ref(typeof route.query.q === 'string' ? route.query.q.slice(0, MAX_QUESTION) : '')
watch(() => route.query.q, (q) => { if (typeof q === 'string') text.value = q.slice(0, MAX_QUESTION) })
const direction = ref<'' | 'in' | 'out'>('')
const year = ref<number | null>(null)
const thisYear = Number(today().slice(0, 4))
const years = Array.from({ length: 10 }, (_, i) => thisYear - i)

// Hỏi trong một văn bản (nút "Hỏi về văn bản này" ở trang chi tiết): svc-files thêm điều kiện văn bản vào bộ lọc, vẫn
// chỉ trong các văn bản người hỏi được xem, hậu kiểm bằng token như mọi lượt. Số ký hiệu, trích yếu đọc từ Hasura bằng
// token người dùng: không được xem thì không thấy gì — trang báo vậy, câu hỏi vẫn giữ phạm vi, không lặng lẽ hỏi cả kho
interface ScopeDoc {
  symbol: string | null
  summary: string
  restricted: boolean
  direction: string
  status: string
  document_type: { name: string } | null
}
const scopeId = computed(() => scopeOf(route.query))
const scopeDoc = ref<ScopeDoc | null>(null)
const scopeState = ref<'loading' | 'found' | 'missing' | 'error'>('loading')
const scopeLabel = computed(() => scopeDoc.value?.symbol?.trim() || scopeDoc.value?.document_type?.name
  || t('assist.scope.unnamed'))

async function loadScope(id: string | null) {
  scopeDoc.value = null
  if (!id) return
  scopeState.value = 'loading'
  try {
    const data = await gql<{ office_documents_by_pk: ScopeDoc | null }>(`
      query ($id: uuid!) {
        office_documents_by_pk(id: $id) { symbol summary restricted direction status document_type { name } }
      }`, { id })
    if (id !== scopeId.value) return       // đã đổi sang văn bản khác giữa chừng
    scopeDoc.value = data.office_documents_by_pk
    scopeState.value = scopeDoc.value ? 'found' : 'missing'
  } catch {
    if (id === scopeId.value) scopeState.value = 'error'   // vẫn hỏi trong văn bản đó, chỉ không có nhãn
  }
}
watch(scopeId, loadScope, { immediate: true })

function clearScope() {
  router.replace({ query: { ...route.query, [SCOPE_PARAM]: undefined } })
}

// Gợi ý ở trang trống, chia theo loại câu (SUGGEST_GROUPS): câu hỏi lấy từ bộ câu hỏi thử của trợ lý
// (seed/hoi-dap/cau-hoi.json), không gọi thêm API. Bấm chỉ điền vào ô câu hỏi, không tự gửi (như khi mở từ trang Tìm
// kiếm). Không có căn cứ hay câu hỏi ngoài phạm vi thì lượt đó nói trợ lý trả lời được gì, kèm vài câu gợi ý
const field = ref<HTMLTextAreaElement | null>(null)

function suggest(key: string) {
  text.value = t(key)
  nextTick(() => field.value?.focus())
}

const turns = ref<Turn[]>([])
const controllers = new Map<number, AbortController>()   // nút Dừng của lượt viết, theo khóa lượt hỏi
let nextKey = 1
let genChain: Promise<void> = Promise.resolve()          // lượt viết nối đuôi nhau: svc-files chỉ viết một lượt một lúc
const announce = ref('')                                   // vùng aria-live: đang tìm, tìm thấy, đã trả lời, lỗi
const now = ref(Date.now())

const searching = computed(() => turns.value.some((x) => x.phase === 'searching'))
const ready = computed(() => allowed.value && !searching.value && cleanQuestion(text.value).length > 0)
const find = (key: number) => turns.value.find((x) => x.key === key)

// Báo cho trình đọc màn hình (aria-live): xóa rồi mới đặt, để câu trùng lần trước vẫn được đọc; không đổi tiêu điểm
function say(message: string) {
  announce.value = ''
  nextTick(() => { announce.value = message })
}

// Đồng hồ giây của lượt đang viết
const writing = computed(() => turns.value.some((x) => x.gen === 'running'))
let ticker: ReturnType<typeof setInterval> | undefined
watch(writing, (on) => {
  clearInterval(ticker)
  if (!on) return
  now.value = Date.now()
  ticker = setInterval(() => { now.value = Date.now() }, 1000)
})
const elapsed = (turn: Turn) => Math.max(0, Math.floor((now.value - turn.started) / 1000))

// Mã lỗi của svc-files → câu cho người hỏi (mã riêng của chức năng hỏi đáp, không dùng utils/errors.ts); mạng, hết
// phiên, giới hạn tốc độ, chặn của cổng thì như mọi trang
function askError(e: unknown): string {
  if (e instanceof ApiError && e.code && te(`assist.error.${e.code}`)) return t(`assist.error.${e.code}`)
  if (e instanceof ApiError && !['network', 'session', 'rate_limited', 'blocked'].includes(e.code ?? '')) {
    return t('assist.error.generic', { msg: e.message })
  }
  return errorText(t, e)
}

function warningTexts(res: AskResult): string[] {
  return res.warnings.filter((code) => te(`assist.warning.${code}`)).map((code) => t(`assist.warning.${code}`))
}

function body(turn: Turn, mode: 'extract' | 'generate'): AskBody {
  return {
    question: turn.question,
    mode,
    ...(turn.direction ? { direction: turn.direction } : {}),
    ...(turn.year ? { year: turn.year } : {}),
    ...(turn.document ? { document_id: turn.document.id } : {}),
    ...(turn.previous ? { previous: turn.previous } : {}),
    ...(mode === 'generate' && turn.result ? { ask_id: turn.result.ask_id } : {}),
  }
}

// Dòng "Đã hiểu là câu hỏi về: …" của một lượt: chỉ khi svc-files có bộ định tuyến (trả route); mã lý do để ở title
const understood = (res: AskResult) =>
  (res.route ? t('assist.understood', { route: t(`assist.route.${res.route}`) }) : '')
const outOfScope = (res: AskResult) => res.route === 'ngoai_pham_vi'

function onKey(e: KeyboardEvent) {
  // Enter gửi, Shift+Enter xuống dòng; đang gõ dở bằng bộ gõ tiếng Việt (composition) thì Enter là của bộ gõ
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  submit()
}

function submit() {
  const question = cleanQuestion(text.value)
  if (!question || !ready.value) return
  // hỏi trong một văn bản: bộ lọc chiều, năm không còn nghĩa (đã ẩn), không gửi
  const scoped = scopeId.value
  const last = turns.value.at(-1)
  const previous = previousFor(last && {
    scope: last.document?.id ?? null, question: last.question, rewritten: last.result?.rewritten,
    done: last.phase === 'shown' && !!last.result,
  }, scoped)
  const turn: Turn = {
    key: nextKey++, question, direction: scoped ? '' : direction.value, year: scoped ? null : year.value,
    document: scoped ? { id: scoped, label: scopeLabel.value } : null, previous, phase: 'searching', result: null,
    error: '', gen: 'idle', genError: '', started: 0, showExtract: false, opened: [],
  }
  // mới nhất ở cuối, như một cuộc trò chuyện; quá 10 thì bỏ câu cũ nhất ở đầu (đang viết thì dừng, đang xem tệp thì
  // đóng)
  const all = [...turns.value, turn]
  for (const old of all.slice(0, -MAX_TURNS)) controllers.get(old.key)?.abort()
  turns.value = all.slice(-MAX_TURNS)
  if (viewer.value && !turns.value.some((x) => x.key === viewer.value?.turn)) closeViewer()
  text.value = ''
  pin = true
  search(turn.key)
}

// Cuộn theo lượt mới nhất. Vừa gửi câu hỏi thì luôn đưa lượt đó vào tầm nhìn; kết quả về sau (tìm xong, soạn xong) chỉ
// cuộn khi người dùng đang ở cuối trang, không kéo người đang đọc lượt cũ đi chỗ khác. Không bao giờ cuộn quá đầu lượt
// (câu trả lời dài thì đọc từ câu hỏi xuống); khung soạn câu hỏi dính đáy nên phần nhìn thấy kết thúc ở mép trên của nó
const dock = ref<HTMLElement | null>(null)
let pin = false
const atBottom = () => document.documentElement.scrollHeight - (window.scrollY + window.innerHeight) < 64

function follow() {
  const last = turns.value.at(-1)
  const el = last ? document.querySelector<HTMLElement>(`[data-turn="${last.key}"]`) : null
  if (!el) return
  const box = el.getBoundingClientRect()
  const by = Math.min(box.bottom - (window.innerHeight - (dock.value?.offsetHeight ?? 0)), box.top - 24)
  if (by <= 0) return
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  window.scrollBy({ top: by, behavior: reduce ? 'auto' : 'smooth' })
}
// flush 'pre': đo "đang ở cuối trang" trước khi trang vẽ lại với nội dung mới
watch(() => turns.value.map((x) => `${x.key}:${x.phase}:${x.gen}`).join(), () => {
  if (!pin && !atBottom()) return
  pin = false
  nextTick(follow)
}, { flush: 'pre' })

async function search(key: number) {
  const turn = find(key)
  if (!turn) return
  turn.phase = 'searching'
  turn.error = ''
  say(t('assist.searching'))
  let res: AskResult
  try {
    res = tidy(await ask(body(turn, 'extract')))
  } catch (e) {
    const cur = find(key)
    if (!cur) return
    cur.phase = 'error'
    cur.error = askError(e)
    say(cur.error)
    return
  }
  const cur = find(key)
  if (!cur) return
  cur.result = res
  cur.phase = 'shown'
  if (res.status === 'no_evidence') {
    say(outOfScope(res) ? t('assist.outOfScope') : t('assist.noEvidence'))
    return
  }
  if (blocks(res).direct) {
    say(t('assist.live.answered'))
    return
  }
  const found = t('assist.live.found', { n: res.sources.length })
  if (!needsGenerate(res)) {
    say(found)
    return
  }
  say(`${found} ${t('assist.live.generating')}`)
  queueGenerate(key)
}

function queueGenerate(key: number) {
  const turn = find(key)
  if (!turn?.result) return
  turn.gen = 'waiting'
  turn.genError = ''
  const ctrl = new AbortController()
  controllers.set(key, ctrl)
  genChain = genChain.then(() => generate(key, ctrl)).catch(() => { /* generate tự bắt lỗi */ })
}

async function generate(key: number, ctrl: AbortController) {
  try {
    const turn = find(key)
    if (!turn || ctrl.signal.aborted || turn.gen !== 'waiting') return   // đã dừng, hoặc đã bị bỏ khỏi danh sách
    turn.gen = 'running'
    turn.started = Date.now()
    let res: AskResult
    try {
      res = tidy(await ask(body(turn, 'generate'), ctrl.signal))
    } catch (e) {
      const cur = find(key)
      if (!cur) return
      if (e instanceof ApiError && e.code === 'aborted') {
        cur.gen = 'stopped'
        say(t('assist.stopped'))
      } else {
        cur.gen = 'failed'
        cur.genError = askError(e)
        say(t('assist.generateFailed', { reason: cur.genError }))
      }
      return
    }
    const cur = find(key)
    if (!cur) return
    // lượt generate tìm lại từ đầu: [n] của câu trả lời trỏ vào nguồn của chính lượt này
    cur.result = res
    cur.gen = 'done'
    // câu trả lời có nhãn che (F4.4: mô hình chỉ thấy [SĐT-1]…) thì mở sẵn câu trích nguyên văn — số thật ở đó
    cur.showExtract = hasMask(blocks(res).model?.text)
    cur.opened = []
    if (blocks(res).model) say(t('assist.live.answered'))
    else if (res.status === 'no_evidence') say(t('assist.noEvidence'))
    else say(warningTexts(res)[0] ?? t('assist.live.extractOnly'))
  } finally {
    if (controllers.get(key) === ctrl) controllers.delete(key)
  }
}

function stop(key: number) {
  const turn = find(key)
  if (turn?.gen === 'waiting') {
    turn.gen = 'stopped'
    say(t('assist.stopped'))
  }
  controllers.get(key)?.abort()
}

// Esc: dừng mọi lượt đang viết hoặc đang chờ lượt viết
function onEscape(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  for (const turn of turns.value) if (turn.gen === 'waiting' || turn.gen === 'running') stop(turn.key)
}

// Mỗi nguồn là một dòng gọn; "Chi tiết" mở trích yếu đủ, loại, nơi ban hành và đoạn trích. Bấm dấu [n] trong câu trả
// lời đưa tiêu điểm vào nguồn đó (AnswerText) và mở luôn phần chi tiết
function toggleSource(turn: Turn, n: number) {
  turn.opened = turn.opened.includes(n) ? turn.opened.filter((x) => x !== n) : [...turn.opened, n]
}
function openSource(turn: Turn, n: number) {
  if (!turn.opened.includes(n)) turn.opened = [...turn.opened, n]
}

// Xem trang được trích: tải tệp bằng token (như phòng đọc hồ sơ, F3.8) thành object URL kiểu PDF, hiện trong khung xem
// PDF có sẵn của trình duyệt, mở đúng trang bằng #page=n — không thêm thư viện xem PDF. Một khung xem cho cả trang, đặt
// dưới danh sách nguồn của lượt hỏi vừa mở nó; nguồn khác cùng tệp dùng lại tệp đã tải
interface Viewer { turn: number; fileId: string; url: string; page: number | null; label: string }
const viewer = ref<Viewer | null>(null)
const opening = ref('')                    // nguồn đang tải tệp: `${lượt}-${n}`
const viewKey = (turn: Turn, s: AskSource) => `${turn.key}-${s.n}`

function closeViewer() {
  if (viewer.value) URL.revokeObjectURL(viewer.value.url)
  viewer.value = null
}

async function viewSource(turn: Turn, s: AskSource) {
  if (!canView(s) || !s.file_id || opening.value) return
  const label = citeLabel(s, t)
  const shown = viewer.value
  if (shown?.fileId === s.file_id) {
    viewer.value = { ...shown, turn: turn.key, page: s.page, label }
  } else {
    opening.value = viewKey(turn, s)
    try {
      const url = await viewFile(s.file_id)
      closeViewer()
      viewer.value = { turn: turn.key, fileId: s.file_id, url, page: s.page, label }
    } catch (e) {
      notice.error(errorText(t, e))
      return
    } finally {
      opening.value = ''
    }
  }
  // khung xem vào tầm nhìn, tiêu điểm vào đó (người dùng bàn phím, trình đọc màn hình)
  await nextTick()
  const el = document.getElementById(`xem-${turn.key}`)
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  el?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' })
  el?.focus({ preventScroll: true })
}

// Nguồn guide (mục hướng dẫn sử dụng, giới thiệu trợ lý) không phải văn bản: không có nơi ban hành, ngày, chiều; hiện
// tệp và mục như chữ, không dựng liên kết
function metaLine(s: AskSource): string {
  return [s.type_name || s.type_code, s.issuer_name, s.issued_on ? fmtDate(s.issued_on) : '',
    s.direction && te(`assist.direction.${s.direction}`) ? t(`assist.direction.${s.direction}`) : '',
    s.kind === 'guide' ? s.path : ''].filter(Boolean).join(' · ')
}

const took = (res: AskResult) => t('assist.took', { s: fmtNumber(Math.round(Number(res.duration_ms) / 100) / 10) })
const stateOf = (turn: Turn) => (turn.phase === 'shown' ? turn.result?.status ?? 'error' : turn.phase)

onMounted(() => window.addEventListener('keydown', onEscape))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onEscape)
  clearInterval(ticker)
  for (const ctrl of controllers.values()) ctrl.abort()
  closeViewer()
})
</script>

<template>
  <div class="sg-ask" :class="{ 'is-empty': !turns.length }">
    <header class="sg-ask-head">
      <h1>{{ t('assist.title') }}</h1>
    </header>

    <!-- trình đọc màn hình: đang tìm, tìm thấy mấy đoạn, đã trả lời, không tìm thấy, lỗi -->
    <p class="sr-only" aria-live="polite" data-testid="ask-live">{{ announce }}</p>

    <p v-if="!allowed" class="moc-empty">{{ t('assist.error.forbidden') }}</p>
    <template v-else>
      <!-- trang trống: lời giới thiệu ngắn ở giữa vùng còn lại, câu hỏi mẫu chia theo loại câu, bấm để điền -->
      <section v-if="!turns.length" class="sg-ask-empty" aria-labelledby="ask-empty-title">
        <h2 id="ask-empty-title">{{ t('assist.emptyTitle') }}</h2>
        <p>{{ t('assist.intro') }}</p>
        <div v-if="!scopeId" class="sg-ask-suggest">
          <h3>{{ t('assist.suggestTitle') }}</h3>
          <div class="sg-ask-groups">
            <section
              v-for="group in SUGGEST_GROUPS" :key="group.route" class="sg-ask-group"
              :aria-labelledby="`goi-y-${group.route}`" data-testid="ask-suggest-group" :data-route="group.route"
            >
              <h4 :id="`goi-y-${group.route}`">{{ t(`assist.suggestGroup.${group.route}`) }}</h4>
              <ul>
                <li v-for="key in group.keys" :key="key">
                  <button type="button" data-testid="ask-suggestion" @click="suggest(key)">{{ t(key) }}</button>
                </li>
              </ul>
            </section>
          </div>
        </div>
      </section>

      <!-- cuộc trò chuyện: câu hỏi cũ ở trên, mới ở dưới -->
      <section v-else class="sg-ask-thread" :aria-label="t('assist.history')">
        <p class="sg-ask-session">{{ t('assist.historyNote') }}</p>
        <article
          v-for="turn in turns" :key="turn.key" class="sg-turn" :data-turn="turn.key"
          :aria-labelledby="`hoi-${turn.key}`"
          :aria-busy="turn.phase === 'searching' || turn.gen === 'running' || turn.gen === 'waiting'"
          :data-state="stateOf(turn)" :data-gen="turn.gen" data-testid="ask-turn"
        >
          <!-- câu hỏi của người dùng, phạm vi đã chọn lúc hỏi -->
          <div class="sg-turn-q">
            <h2 :id="`hoi-${turn.key}`" class="sg-turn-bubble">{{ turn.question }}</h2>
            <div v-if="turn.document || turn.direction || turn.year" class="sg-turn-tags">
              <span
                v-if="turn.document" class="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200"
                data-testid="ask-scope-chip"
              >
                {{ t('assist.scope.chip', { label: turn.document.label }) }}
              </span>
              <span v-if="turn.direction" class="chip bg-stone-100 text-stone-700">
                {{ t(`assist.direction.${turn.direction}`) }}
              </span>
              <span v-if="turn.year" class="chip bg-stone-100 text-stone-700">
                {{ t('assist.yearValue', { year: turn.year }) }}
              </span>
            </div>
          </div>

          <!-- câu trả lời: chữ thường trên nền trang, không đóng khung -->
          <div class="sg-turn-a">
            <p class="sg-turn-by">
              <b>{{ t('assist.answerBy') }}</b>
              <template v-if="turn.result">
                <span
                  v-if="searched(turn.result.route)" class="chip bg-stone-100 text-stone-700" data-testid="ask-mode"
                >
                  {{ turn.result.semantic ? t('assist.semantic') : t('assist.keyword') }}
                </span>
                <span class="tabular-nums">{{ took(turn.result) }}</span>
              </template>
            </p>
            <!-- bộ định tuyến: trợ lý đã hiểu câu hỏi là loại nào, câu nối tiếp đã ghép với câu trước thành câu gì -->
            <p
              v-if="turn.result && understood(turn.result)" class="sg-turn-route" data-testid="ask-route"
              :data-route="turn.result.route"
              :title="turn.result.route_reason
                ? t('assist.routeReason', { code: turn.result.route_reason }) : undefined"
            >
              <span>{{ understood(turn.result) }}</span>
              <span v-if="turn.result.rewritten" data-testid="ask-rewritten">
                {{ t('assist.rewritten', { text: turn.result.rewritten }) }}
              </span>
            </p>

            <!-- đang tìm: chỗ của câu trả lời giữ sẵn bằng vài vạch xám -->
            <div v-if="turn.phase === 'searching'" class="sg-turn-wait">
              <p>
                <svg
                  class="h-4 w-4 text-brand-700 motion-safe:animate-spin" viewBox="0 0 24 24" fill="none"
                  aria-hidden="true"
                >
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                {{ t('assist.searching') }}
              </p>
              <div class="sg-turn-skeleton" aria-hidden="true"><span /><span /><span /></div>
            </div>

            <!-- lỗi tìm -->
            <div v-else-if="turn.phase === 'error'" class="moc-state" data-testid="ask-error">
              <span class="font-medium">
                <svg
                  class="mr-1 inline-block h-4 w-4 align-text-bottom" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="1.6" aria-hidden="true"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" d="m12 3 10 18H2L12 3Zm0 6v4m0 4h.01" />
                </svg>{{ turn.error }}
              </span>
              <button
                type="button" class="btn-secondary !px-2.5 !py-1 !text-xs" :disabled="searching"
                @click="search(turn.key)"
              >
                {{ t('app.retry') }}
              </button>
            </div>

            <template v-else-if="turn.result">
              <!-- không có căn cứ: câu giống hệt nhau dù văn bản không tồn tại hay người hỏi không được xem. Câu hỏi
                   ngoài phạm vi (thời tiết, tin tức…): nói thẳng như vậy. Cả hai nói trợ lý trả lời được gì, kèm
                   gợi ý -->
              <div v-if="turn.result.status === 'no_evidence'" class="sg-turn-none" data-testid="ask-none">
                <p>{{ outOfScope(turn.result) ? t('assist.outOfScope') : t('assist.noEvidence') }}</p>
                <NuxtLink
                  v-if="!outOfScope(turn.result)"
                  :to="{ path: '/tim-kiem', query: { q: turn.question.slice(0, 200) } }"
                  class="mt-2 inline-block font-medium text-brand-700 underline underline-offset-2"
                >
                  {{ t('assist.openSearch') }}
                </NuxtLink>
                <div class="sg-turn-can" data-testid="ask-can">
                  <p>{{ t('assist.can.title') }}</p>
                  <ul>
                    <li v-for="group in SUGGEST_GROUPS" :key="group.route">{{ t(`assist.can.${group.route}`) }}</li>
                  </ul>
                  <p>{{ t('assist.suggestTitle') }}</p>
                  <ul class="sg-turn-chips">
                    <li v-for="key in fallbackSuggestions(turn.result.route)" :key="key">
                      <button type="button" data-testid="ask-fallback" @click="suggest(key)">{{ t(key) }}</button>
                    </li>
                  </ul>
                </div>
              </div>

              <!-- câu trả lời thẳng, không qua tìm đoạn: số lấy từ dữ liệu bạn được xem, kèm "Căn cứ: …" -->
              <section v-else-if="blocks(turn.result).direct" class="sg-answer" data-testid="ask-direct">
                <h3 class="sr-only">{{ t('assist.directTitle') }}</h3>
                <AnswerText
                  :text="blocks(turn.result).direct!.text" :sources="turn.result.sources" :ask="turn.result.ask_id"
                />
                <p v-if="blocks(turn.result).direct!.source === 'data'" class="sg-answer-note">
                  {{ t('assist.dataNote') }}
                </p>
                <NuxtLink
                  v-if="turn.result.link" :to="turn.result.link" data-testid="ask-data-link"
                  class="mt-2 inline-block font-medium text-brand-700 underline underline-offset-2"
                >
                  {{ t(turn.result.route === 'viec_cua_toi' ? 'assist.openInbox' : 'assist.openList') }}
                </NuxtLink>
              </section>

              <template v-else>
                <p v-if="turn.result.status === 'passages_only'" class="moc-note" data-testid="ask-passages">
                  {{ t('assist.passagesOnly') }}
                </p>

                <!-- câu trả lời do mô hình viết (đã qua kiểm trích dẫn) -->
                <section v-if="blocks(turn.result).model" class="sg-answer" data-testid="ask-model">
                  <h3 class="sr-only">{{ t('assist.modelTitle') }}</h3>
                  <AnswerText
                    :text="blocks(turn.result).model!.text" :sources="turn.result.sources" :ask="turn.result.ask_id"
                  />
                  <p class="sg-answer-note">
                    <svg
                      class="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"
                      stroke-width="2" aria-hidden="true"
                    >
                      <path
                        stroke-linecap="round" stroke-linejoin="round"
                        d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4L12 3z"
                      />
                    </svg>
                    {{ t('assist.modelNote') }}
                  </p>
                  <!-- F4.4: chữ gửi mô hình đã che, mô hình viết nhãn [SĐT-1] thay cho số -->
                  <p v-if="hasMask(blocks(turn.result).model!.text)" class="sg-answer-note" data-testid="ask-masked">
                    {{ t('assist.maskedNote') }}
                  </p>
                  <button
                    v-if="blocks(turn.result).extract" type="button"
                    class="mt-2 min-h-6 text-[13px] font-medium text-brand-700 underline underline-offset-2"
                    :aria-expanded="turn.showExtract" :aria-controls="`trich-${turn.key}`"
                    @click="turn.showExtract = !turn.showExtract"
                  >
                    {{ turn.showExtract ? t('assist.hideExtract') : t('assist.showExtract') }}
                  </button>
                </section>

                <!-- câu trích nguyên văn: là câu trả lời khi không có mô hình, là khối phụ khi có -->
                <section
                  v-if="blocks(turn.result).extract && (!blocks(turn.result).model || turn.showExtract)"
                  :id="`trich-${turn.key}`" class="sg-answer" :class="{ 'is-quote': blocks(turn.result).model }"
                  data-testid="ask-extract"
                >
                  <h3 class="sg-answer-label">{{ t('assist.extractTitle') }}</h3>
                  <AnswerText
                    :text="blocks(turn.result).extract!.text" :sources="turn.result.sources"
                    :ask="turn.result.ask_id"
                  />
                </section>

                <!-- đang viết câu trả lời -->
                <div
                  v-if="turn.gen === 'waiting' || turn.gen === 'running'" data-testid="ask-generating"
                  class="sg-turn-writing"
                >
                  <svg
                    class="h-4 w-4 text-brand-700 motion-safe:animate-spin" viewBox="0 0 24 24" fill="none"
                    aria-hidden="true"
                  >
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  <span class="font-medium">
                    {{ turn.gen === 'waiting' ? t('assist.waiting') : t('assist.generating') }}
                  </span>
                  <span v-if="turn.gen === 'running'" class="text-stone-500 tabular-nums">
                    {{ t('assist.elapsed', { s: elapsed(turn) }) }}
                  </span>
                  <button type="button" class="btn-secondary ml-auto !px-2.5 !py-1 !text-xs" @click="stop(turn.key)">
                    {{ t('assist.stop') }}
                  </button>
                  <span class="basis-full text-[13px] text-stone-500">{{ t('assist.generatingHint') }}</span>
                </div>
                <div
                  v-else-if="turn.gen === 'stopped' || turn.gen === 'failed'" data-testid="ask-generate-note"
                  class="mt-4 flex flex-wrap items-center gap-3 text-sm text-amber-900"
                >
                  <span>
                    <svg
                      class="mr-1 inline-block h-4 w-4 align-text-bottom" viewBox="0 0 24 24" fill="none"
                      stroke="currentColor" stroke-width="1.6" aria-hidden="true"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" d="m12 3 10 18H2L12 3Zm0 6v4m0 4h.01" />
                    </svg>{{ turn.gen === 'stopped'
                      ? t('assist.stopped') : t('assist.generateFailed', { reason: turn.genError }) }}
                  </span>
                  <button
                    v-if="needsGenerate(turn.result)" type="button" class="btn-secondary !px-2.5 !py-1 !text-xs"
                    @click="queueGenerate(turn.key)"
                  >
                    {{ t('assist.retryGenerate') }}
                  </button>
                </div>

                <ul
                  v-if="warningTexts(turn.result).length" class="mt-3 space-y-1 text-[13px] text-amber-900"
                  data-testid="ask-warnings"
                >
                  <li v-for="w in warningTexts(turn.result)" :key="w">
                    <svg
                      class="mr-1 inline-block h-4 w-4 align-text-bottom" viewBox="0 0 24 24" fill="none"
                      stroke="currentColor" stroke-width="1.6" aria-hidden="true"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" d="m12 3 10 18H2L12 3Zm0 6v4m0 4h.01" />
                    </svg>{{ w }}
                  </li>
                </ul>

                <!-- nguồn: mỗi nguồn một dòng gọn, "Chi tiết" mở đoạn trích -->
                <section
                  v-if="turn.result.sources.length" class="sg-sources" :aria-labelledby="`nguon-${turn.key}`"
                >
                  <h3 :id="`nguon-${turn.key}`" class="sg-sources-title">
                    {{ t('assist.source.title') }} <span class="tabular-nums">({{ turn.result.sources.length }})</span>
                  </h3>
                  <ol data-testid="ask-sources">
                    <li
                      v-for="s in turn.result.sources" :id="sourceAnchor(turn.result.ask_id, s.n)" :key="s.n"
                      tabindex="-1" class="sg-source" :class="{ 'is-open': turn.opened.includes(s.n) }"
                      @focus="openSource(turn, s.n)"
                    >
                      <div class="sg-source-row">
                        <span class="sg-source-n" aria-hidden="true">[{{ s.n }}]</span>
                        <span class="sr-only">{{ t('assist.source.n', { n: s.n }) }}</span>
                        <!-- nhãn trích dẫn: mở tệp đúng trang được trích -->
                        <button
                          v-if="canView(s)" type="button" data-testid="ask-view" class="sg-source-label"
                          :aria-label="t('assist.viewSource', { label: citeLabel(s, t, true) })"
                          :title="s.page ? t('assist.viewPage', { n: s.page }) : t('assist.viewFile')"
                          :disabled="opening !== ''" :aria-busy="opening === viewKey(turn, s)"
                          @click="viewSource(turn, s)"
                        >
                          {{ citeLabel(s, t) }}
                        </button>
                        <span v-else class="sg-source-label is-plain">{{ citeLabel(s, t) }}</span>
                        <span v-if="s.cited" class="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">
                          {{ t('assist.source.cited') }}
                        </span>
                        <span class="sg-source-tools">
                          <NuxtLink
                            v-if="s.document_id" :to="`/van-ban/${s.document_id}`"
                            :aria-label="t('assist.openDocumentFor', { label: citeLabel(s, t, true) })"
                          >
                            {{ t('assist.openDocument') }}
                          </NuxtLink>
                          <button
                            type="button" :aria-expanded="turn.opened.includes(s.n)"
                            :aria-controls="`${sourceAnchor(turn.result.ask_id, s.n)}-chi-tiet`"
                            @click="toggleSource(turn, s.n)"
                          >
                            {{ t('assist.source.details') }}
                            <span class="sr-only">{{ t('assist.source.n', { n: s.n }) }}</span>
                            <svg
                              class="sg-source-chevron h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                              stroke-width="1.8" aria-hidden="true"
                            >
                              <path stroke-linecap="round" stroke-linejoin="round" d="m6 9 6 6 6-6" />
                            </svg>
                          </button>
                        </span>
                      </div>
                      <p class="sg-source-summary">{{ s.summary }}</p>
                      <div
                        v-show="turn.opened.includes(s.n)" :id="`${sourceAnchor(turn.result.ask_id, s.n)}-chi-tiet`"
                        class="sg-source-detail"
                      >
                        <p class="sg-source-meta">
                          <span>{{ metaLine(s) }}</span>
                          <StatusChip v-if="s.document_id && s.status" :status="s.status" />
                        </p>
                        <p
                          v-if="s.excerpt" :id="`${sourceAnchor(turn.result.ask_id, s.n)}-trich`"
                          class="sg-source-excerpt"
                        >
                          <span class="sr-only">{{ t('assist.source.excerpt') }}: </span>{{ s.excerpt }}
                        </p>
                      </div>
                    </li>
                  </ol>

                  <!-- khung xem tệp, mở đúng trang được trích -->
                  <div
                    v-if="viewer && viewer.turn === turn.key" :id="`xem-${turn.key}`" tabindex="-1"
                    class="mt-4 scroll-mb-44 overflow-hidden rounded-xl border border-stone-200 focus:outline-2
                      focus:outline-brand-600"
                    data-testid="ask-viewer"
                  >
                    <div
                      class="flex flex-wrap items-center gap-3 border-b border-stone-200 bg-stone-50 px-4 py-2 text-sm"
                    >
                      <span class="min-w-0 flex-1 truncate font-medium">
                        {{ t('assist.viewer.title', { label: viewer.label }) }}
                      </span>
                      <a
                        :href="pageUrl(viewer.url, viewer.page)" target="_blank" rel="noopener"
                        class="text-brand-800 hover:underline"
                      >
                        {{ t('assist.viewer.newTab') }}
                      </a>
                      <button type="button" class="btn-ghost" @click="closeViewer">
                        {{ t('assist.viewer.close') }}
                      </button>
                    </div>
                    <iframe
                      :key="pageUrl(viewer.url, viewer.page)" :src="pageUrl(viewer.url, viewer.page)"
                      :title="t('assist.viewer.title', { label: viewer.label })" class="h-[75vh] w-full"
                    />
                    <p class="border-t border-stone-200 px-4 py-2 text-xs text-stone-500">
                      {{ t('assist.viewer.note') }}
                    </p>
                  </div>
                </section>
              </template>
            </template>
          </div>
        </article>
      </section>

      <!-- khung soạn câu hỏi: dính đáy màn hình, chiếm chỗ của nó nên không che câu trả lời cuối -->
      <form ref="dock" class="sg-ask-dock" @submit.prevent="submit">
        <div class="sg-composer">
          <!-- hỏi trong một văn bản: văn bản nào, bỏ phạm vi được -->
          <div v-if="scopeId" data-testid="ask-scope" class="sg-composer-scope">
            <div class="min-w-0 flex-1">
              <p class="font-medium text-brand-900">{{ t('assist.scope.title') }}</p>
              <p v-if="scopeState === 'loading'" class="text-stone-600">{{ t('app.loading') }}</p>
              <template v-else-if="scopeDoc">
                <p class="sg-composer-doc">
                  <NuxtLink
                    :to="`/van-ban/${scopeId}`"
                    class="font-semibold text-brand-800 underline underline-offset-2 hover:text-brand-900"
                  >{{ scopeLabel }}</NuxtLink>
                  <span>{{ scopeDoc.summary }}</span>
                </p>
                <p v-if="!inAssistant(scopeDoc)" class="mt-1 text-amber-900">{{ t('assist.scope.notIndexed') }}</p>
              </template>
              <p v-else-if="scopeState === 'missing'" class="text-amber-900">{{ t('assist.scope.missing') }}</p>
              <p v-else class="text-stone-700">{{ scopeLabel }}</p>
            </div>
            <button type="button" class="btn-secondary !min-h-8 !px-2.5 !py-1 !text-xs" @click="clearScope">
              {{ t('assist.scope.clear') }}
            </button>
          </div>
          <label class="sr-only" for="ask-question">{{ t('assist.label') }}</label>
          <textarea
            id="ask-question" ref="field" v-model="text" rows="2" :maxlength="MAX_QUESTION" class="sg-composer-input"
            autofocus :placeholder="t('assist.placeholder')" aria-describedby="ask-keys" @keydown="onKey"
          />
          <div class="sg-composer-bar">
            <!-- chiều, năm: không cần khi đã hỏi trong một văn bản -->
            <template v-if="!scopeId">
              <span class="sg-composer-filter">
                <label for="ask-direction">{{ t('assist.direction.label') }}</label>
                <select id="ask-direction" v-model="direction">
                  <option value="">{{ t('assist.any') }}</option>
                  <option value="in">{{ t('assist.direction.in') }}</option>
                  <option value="out">{{ t('assist.direction.out') }}</option>
                </select>
              </span>
              <span class="sg-composer-filter">
                <label for="ask-year">{{ t('assist.year') }}</label>
                <select id="ask-year" v-model="year">
                  <option :value="null">{{ t('assist.anyYear') }}</option>
                  <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
                </select>
              </span>
            </template>
            <button type="submit" class="btn-primary sg-composer-send" :disabled="!ready">
              <svg
                class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                aria-hidden="true"
              >
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 19V5m-6 6 6-6 6 6" />
              </svg>
              {{ t('assist.ask') }}
            </button>
          </div>
        </div>
        <p id="ask-keys" class="sg-composer-hint">
          {{ t('assist.keysHint') }} ·
          <span class="tabular-nums">{{ t('assist.count', { n: text.length, max: MAX_QUESTION }) }}</span>
        </p>
      </form>
    </template>
  </div>
</template>
