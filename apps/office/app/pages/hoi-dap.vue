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

<script setup>

import { useI18n } from 'vue-i18n';
import { ApiError } from '~/composables/useApi';

import {
  ASK_ROLES, MAX_QUESTION, SCOPE_PARAM, blocks, canView, citeLabel, cleanQuestion, hasMask, needsGenerate,
  scopeOf, tidy } from
'~/utils/answer';

// Hỏi đáp trên kho văn bản (F4.2). Trợ lý moc-assistant (svc-files) chỉ tìm trong các văn bản người hỏi được xem,
// văn bản hạn chế không bao giờ vào chỉ mục. Hai pha cho mỗi câu hỏi: extract trả ngay câu trích nguyên văn kèm
// nguồn "số ký hiệu · tr. n" (< 1 giây, không cần mô hình); nếu mô hình sẵn sàng (ai_available) thì tự gọi generate
// với cùng ask_id — mô hình viết câu trả lời có trích dẫn [n] trong 15–40 giây, bấm Dừng hoặc Esc thì thôi, câu trích
// vẫn còn đó. Mỗi câu hỏi độc lập; danh sách chỉ giữ trong bộ nhớ trang (tối đa 10), không lưu ở đâu cả.
// Mở từ nút "Hỏi về văn bản này" (?van_ban=<id>) thì chỉ hỏi trong văn bản đó; nhãn nguồn mở tệp đúng trang được trích.


















const MAX_TURNS = 10;
const LONG_EXCERPT = 240;

const { t, te } = useI18n();
const { ask, gql, viewFile } = useApi();
const notice = useNotice();
const route = useRoute();
const router = useRouter();
const claims = useAuth().claims;

const allowed = computed(() => ASK_ROLES.includes(claims.value?.role ?? ''));
// Từ trang Tìm kiếm ("Hỏi trợ lý"): điền sẵn câu tìm, không tự gửi
const text = ref(typeof route.query.q === 'string' ? route.query.q.slice(0, MAX_QUESTION) : '');
watch(() => route.query.q, (q) => {if (typeof q === 'string') text.value = q.slice(0, MAX_QUESTION);});
const direction = ref('');
const year = ref(null);
const thisYear = Number(today().slice(0, 4));
const years = Array.from({ length: 10 }, (_, i) => thisYear - i);

// Hỏi trong một văn bản (nút "Hỏi về văn bản này" ở trang chi tiết): svc-files thêm điều kiện văn bản vào bộ lọc, vẫn
// chỉ trong các văn bản người hỏi được xem, hậu kiểm bằng token như mọi lượt. Số ký hiệu, trích yếu đọc từ Hasura bằng
// token người dùng: không được xem thì không thấy gì — trang báo vậy, câu hỏi vẫn giữ phạm vi, không lặng lẽ hỏi cả kho








const scopeId = computed(() => scopeOf(route.query));
const scopeDoc = ref(null);
const scopeState = ref('loading');
const scopeLabel = computed(() => scopeDoc.value?.symbol?.trim() || scopeDoc.value?.document_type?.name ||
t('assist.scope.unnamed'));

async function loadScope(id) {
  scopeDoc.value = null;
  if (!id) return;
  scopeState.value = 'loading';
  try {
    const data = await gql(`
      query ($id: uuid!) {
        office_documents_by_pk(id: $id) { symbol summary restricted direction status document_type { name } }
      }`, { id });
    if (id !== scopeId.value) return; // đã đổi sang văn bản khác giữa chừng
    scopeDoc.value = data.office_documents_by_pk;
    scopeState.value = scopeDoc.value ? 'found' : 'missing';
  } catch {
    if (id === scopeId.value) scopeState.value = 'error'; // vẫn hỏi trong văn bản đó, chỉ không có nhãn
  }
}
watch(scopeId, loadScope, { immediate: true });

function clearScope() {
  router.replace({ query: { ...route.query, [SCOPE_PARAM]: undefined } });
}

const turns = ref([]);
const controllers = new Map(); // nút Dừng của lượt viết, theo khóa lượt hỏi
let nextKey = 1;
let genChain = Promise.resolve(); // lượt viết nối đuôi nhau: svc-files chỉ viết một lượt một lúc
const announce = ref(''); // vùng aria-live: đang tìm, tìm thấy, đã trả lời, lỗi
const now = ref(Date.now());

const searching = computed(() => turns.value.some((x) => x.phase === 'searching'));
const ready = computed(() => allowed.value && !searching.value && cleanQuestion(text.value).length > 0);
const find = (key) => turns.value.find((x) => x.key === key);

// Báo cho trình đọc màn hình (aria-live): xóa rồi mới đặt, để câu trùng lần trước vẫn được đọc; không đổi tiêu điểm
function say(message) {
  announce.value = '';
  nextTick(() => {announce.value = message;});
}

// Đồng hồ giây của lượt đang viết
const writing = computed(() => turns.value.some((x) => x.gen === 'running'));
let ticker;
watch(writing, (on) => {
  clearInterval(ticker);
  if (!on) return;
  now.value = Date.now();
  ticker = setInterval(() => {now.value = Date.now();}, 1000);
});
const elapsed = (turn) => Math.max(0, Math.floor((now.value - turn.started) / 1000));

// Mã lỗi của svc-files → câu cho người hỏi (mã riêng của chức năng hỏi đáp, không dùng utils/errors.ts); mạng, hết
// phiên, giới hạn tốc độ, chặn của cổng thì như mọi trang
function askError(e) {
  if (e instanceof ApiError && e.code && te(`assist.error.${e.code}`)) return t(`assist.error.${e.code}`);
  if (e instanceof ApiError && !['network', 'session', 'rate_limited', 'blocked'].includes(e.code ?? '')) {
    return t('assist.error.generic', { msg: e.message });
  }
  return errorText(t, e);
}

function warningTexts(res) {
  return res.warnings.filter((code) => te(`assist.warning.${code}`)).map((code) => t(`assist.warning.${code}`));
}

function body(turn, mode) {
  return {
    question: turn.question,
    mode,
    ...(turn.direction ? { direction: turn.direction } : {}),
    ...(turn.year ? { year: turn.year } : {}),
    ...(turn.document ? { document_id: turn.document.id } : {}),
    ...(mode === 'generate' && turn.result ? { ask_id: turn.result.ask_id } : {})
  };
}

function onKey(e) {
  // Enter gửi, Shift+Enter xuống dòng; đang gõ dở bằng bộ gõ tiếng Việt (composition) thì Enter là của bộ gõ
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  submit();
}

function submit() {
  const question = cleanQuestion(text.value);
  if (!question || !ready.value) return;
  // hỏi trong một văn bản: bộ lọc chiều, năm không còn nghĩa (đã ẩn), không gửi
  const scoped = scopeId.value;
  const turn = {
    key: nextKey++, question, direction: scoped ? '' : direction.value, year: scoped ? null : year.value,
    document: scoped ? { id: scoped, label: scopeLabel.value } : null, phase: 'searching', result: null,
    error: '', gen: 'idle', genError: '', started: 0, showExtract: false, opened: []
  };
  // mới nhất trên cùng; quá 10 thì bỏ câu cũ nhất (đang viết thì dừng, đang xem tệp thì đóng)
  const all = [turn, ...turns.value];
  for (const old of all.slice(MAX_TURNS)) controllers.get(old.key)?.abort();
  turns.value = all.slice(0, MAX_TURNS);
  if (viewer.value && !turns.value.some((x) => x.key === viewer.value?.turn)) closeViewer();
  text.value = '';
  search(turn.key);
}

async function search(key) {
  const turn = find(key);
  if (!turn) return;
  turn.phase = 'searching';
  turn.error = '';
  say(t('assist.searching'));
  let res;
  try {
    res = tidy(await ask(body(turn, 'extract')));
  } catch (e) {
    const cur = find(key);
    if (!cur) return;
    cur.phase = 'error';
    cur.error = askError(e);
    say(cur.error);
    return;
  }
  const cur = find(key);
  if (!cur) return;
  cur.result = res;
  cur.phase = 'shown';
  if (res.status === 'no_evidence') {
    say(t('assist.noEvidence'));
    return;
  }
  const found = t('assist.live.found', { n: res.sources.length });
  if (!needsGenerate(res)) {
    say(found);
    return;
  }
  say(`${found} ${t('assist.live.generating')}`);
  queueGenerate(key);
}

function queueGenerate(key) {
  const turn = find(key);
  if (!turn?.result) return;
  turn.gen = 'waiting';
  turn.genError = '';
  const ctrl = new AbortController();
  controllers.set(key, ctrl);
  genChain = genChain.then(() => generate(key, ctrl)).catch(() => {/* generate tự bắt lỗi */});
}

async function generate(key, ctrl) {
  try {
    const turn = find(key);
    if (!turn || ctrl.signal.aborted || turn.gen !== 'waiting') return; // đã dừng, hoặc đã bị bỏ khỏi danh sách
    turn.gen = 'running';
    turn.started = Date.now();
    let res;
    try {
      res = tidy(await ask(body(turn, 'generate'), ctrl.signal));
    } catch (e) {
      const cur = find(key);
      if (!cur) return;
      if (e instanceof ApiError && e.code === 'aborted') {
        cur.gen = 'stopped';
        say(t('assist.stopped'));
      } else {
        cur.gen = 'failed';
        cur.genError = askError(e);
        say(t('assist.generateFailed', { reason: cur.genError }));
      }
      return;
    }
    const cur = find(key);
    if (!cur) return;
    // lượt generate tìm lại từ đầu: [n] của câu trả lời trỏ vào nguồn của chính lượt này
    cur.result = res;
    cur.gen = 'done';
    // câu trả lời có nhãn che (F4.4: mô hình chỉ thấy [SĐT-1]…) thì mở sẵn câu trích nguyên văn — số thật ở đó
    cur.showExtract = hasMask(blocks(res).model?.text);
    cur.opened = [];
    if (blocks(res).model) say(t('assist.live.answered'));else
    if (res.status === 'no_evidence') say(t('assist.noEvidence'));else
    say(warningTexts(res)[0] ?? t('assist.live.extractOnly'));
  } finally {
    if (controllers.get(key) === ctrl) controllers.delete(key);
  }
}

function stop(key) {
  const turn = find(key);
  if (turn?.gen === 'waiting') {
    turn.gen = 'stopped';
    say(t('assist.stopped'));
  }
  controllers.get(key)?.abort();
}

// Esc: dừng mọi lượt đang viết hoặc đang chờ lượt viết
function onEscape(e) {
  if (e.key !== 'Escape') return;
  for (const turn of turns.value) if (turn.gen === 'waiting' || turn.gen === 'running') stop(turn.key);
}

function toggleExcerpt(turn, n) {
  turn.opened = turn.opened.includes(n) ? turn.opened.filter((x) => x !== n) : [...turn.opened, n];
}

// Xem trang được trích: tải tệp bằng token (như phòng đọc hồ sơ, F3.8) thành object URL kiểu PDF, hiện trong khung xem
// PDF có sẵn của trình duyệt, mở đúng trang bằng #page=n — không thêm thư viện xem PDF. Một khung xem cho cả trang, đặt
// dưới danh sách nguồn của lượt hỏi vừa mở nó; nguồn khác cùng tệp dùng lại tệp đã tải

const viewer = ref(null);
const opening = ref(''); // nguồn đang tải tệp: `${lượt}-${n}`
const viewKey = (turn, s) => `${turn.key}-${s.n}`;

function closeViewer() {
  if (viewer.value) URL.revokeObjectURL(viewer.value.url);
  viewer.value = null;
}

async function viewSource(turn, s) {
  if (!canView(s) || !s.file_id || opening.value) return;
  const label = citeLabel(s, t);
  const shown = viewer.value;
  if (shown?.fileId === s.file_id) {
    viewer.value = { ...shown, turn: turn.key, page: s.page, label };
  } else {
    opening.value = viewKey(turn, s);
    try {
      const url = await viewFile(s.file_id);
      closeViewer();
      viewer.value = { turn: turn.key, fileId: s.file_id, url, page: s.page, label };
    } catch (e) {
      notice.error(errorText(t, e));
      return;
    } finally {
      opening.value = '';
    }
  }
  // khung xem vào tầm nhìn, tiêu điểm vào đó (người dùng bàn phím, trình đọc màn hình)
  await nextTick();
  const el = document.getElementById(`xem-${turn.key}`);
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  el?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' });
  el?.focus({ preventScroll: true });
}

function metaLine(s) {
  return [s.type_name || s.type_code, s.issuer_name, s.issued_on ? fmtDate(s.issued_on) : '',
  te(`assist.direction.${s.direction}`) ? t(`assist.direction.${s.direction}`) : ''].filter(Boolean).join(' · ');
}

const took = (res) => t('assist.took', { s: fmtNumber(Math.round(Number(res.duration_ms) / 100) / 10) });
const stateOf = (turn) => turn.phase === 'shown' ? turn.result?.status ?? 'error' : turn.phase;

onMounted(() => window.addEventListener('keydown', onEscape));
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onEscape);
  clearInterval(ticker);
  for (const ctrl of controllers.values()) ctrl.abort();
  closeViewer();
});
</script>

<template>
  <div>
    <PageHeader :title="t('assist.title')" :subtitle="t('assist.intro')" />

    <!-- trình đọc màn hình: đang tìm, tìm thấy mấy đoạn, đã trả lời, không tìm thấy, lỗi -->
    <p class="sr-only" aria-live="polite" data-testid="ask-live">{{ announce }}</p>

    <p v-if="!allowed" class="card p-4 text-sm text-stone-700">{{ t('assist.error.forbidden') }}</p>
    <form v-else class="card mb-6 space-y-3 p-4" @submit.prevent="submit">
      <!-- hỏi trong một văn bản: văn bản nào, bỏ phạm vi được -->
      <div
        v-if="scopeId" data-testid="ask-scope"
        class="flex flex-wrap items-start gap-3 rounded-lg border border-brand-200 bg-brand-50 p-3 text-sm"
      >
        <div class="min-w-0 flex-1">
          <p class="font-medium text-brand-900">{{ t('assist.scope.title') }}</p>
          <p v-if="scopeState === 'loading'" class="text-stone-600">{{ t('app.loading') }}</p>
          <template v-else-if="scopeDoc">
            <p class="break-words text-stone-800">
              <NuxtLink
                :to="`/van-ban/${scopeId}`"
                class="font-semibold text-brand-800 underline underline-offset-2 hover:text-brand-900"
              >{{ scopeLabel }}</NuxtLink>
              — {{ scopeDoc.summary }}
            </p>
            <p v-if="!inAssistant(scopeDoc)" class="mt-1 text-amber-900">{{ t('assist.scope.notIndexed') }}</p>
          </template>
          <p v-else-if="scopeState === 'missing'" class="text-amber-900">{{ t('assist.scope.missing') }}</p>
          <p v-else class="text-stone-700">{{ scopeLabel }}</p>
        </div>
        <button type="button" class="btn-secondary !px-2.5 !py-1 !text-xs" @click="clearScope">
          {{ t('assist.scope.clear') }}
        </button>
      </div>
      <label class="label" for="ask-question">{{ t('assist.label') }}</label>
      <textarea
        id="ask-question" v-model="text" rows="3" :maxlength="MAX_QUESTION" class="input resize-y" autofocus
        :placeholder="t('assist.placeholder')" aria-describedby="ask-keys" @keydown="onKey"
      />
      <div class="flex flex-wrap items-end gap-3">
        <p id="ask-keys" class="min-w-48 flex-1 text-xs text-stone-500">
          {{ t('assist.keysHint') }} · <span class="tabular-nums">{{ t('assist.count', { n: text.length, max: MAX_QUESTION }) }}</span>
        </p>
        <!-- chiều, năm: không cần khi đã hỏi trong một văn bản -->
        <template v-if="!scopeId">
          <div>
            <label class="label" for="ask-direction">{{ t('assist.direction.label') }}</label>
            <select id="ask-direction" v-model="direction" class="input sm:w-40">
              <option value="">{{ t('assist.any') }}</option>
              <option value="in">{{ t('assist.direction.in') }}</option>
              <option value="out">{{ t('assist.direction.out') }}</option>
            </select>
          </div>
          <div>
            <label class="label" for="ask-year">{{ t('assist.year') }}</label>
            <select id="ask-year" v-model="year" class="input sm:w-32">
              <option :value="null">{{ t('assist.anyYear') }}</option>
              <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
            </select>
          </div>
        </template>
        <button type="submit" class="btn-primary" :disabled="!ready">{{ t('assist.ask') }}</button>
      </div>
    </form>

    <section v-if="turns.length" :aria-label="t('assist.history')">
      <p class="mb-3 text-xs text-stone-500">{{ t('assist.historyNote') }}</p>
      <div class="space-y-4">
        <article
          v-for="turn in turns" :key="turn.key" class="card p-5"
          :aria-labelledby="`hoi-${turn.key}`"
          :aria-busy="turn.phase === 'searching' || turn.gen === 'running' || turn.gen === 'waiting'"
          :data-state="stateOf(turn)" :data-gen="turn.gen" data-testid="ask-turn"
        >
          <!-- câu hỏi, phạm vi, cách tìm -->
          <div class="flex flex-wrap items-start gap-x-3 gap-y-2">
            <h2 :id="`hoi-${turn.key}`" class="min-w-0 flex-1 font-medium break-words text-stone-900">{{ turn.question }}</h2>
            <div class="flex flex-wrap items-center gap-1.5">
              <span
                v-if="turn.document" class="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200"
                data-testid="ask-scope-chip"
              >
                {{ t('assist.scope.chip', { label: turn.document.label }) }}
              </span>
              <span v-if="turn.direction" class="chip bg-stone-100 text-stone-700">{{ t(`assist.direction.${turn.direction}`) }}</span>
              <span v-if="turn.year" class="chip bg-stone-100 text-stone-700">{{ t('assist.yearValue', { year: turn.year }) }}</span>
              <template v-if="turn.result">
                <span class="chip bg-stone-100 text-stone-700" data-testid="ask-mode">{{ turn.result.semantic ? t('assist.semantic') : t('assist.keyword') }}</span>
                <span class="text-xs text-stone-500 tabular-nums">{{ took(turn.result) }}</span>
              </template>
            </div>
          </div>

          <!-- đang tìm -->
          <div v-if="turn.phase === 'searching'" class="mt-3 flex items-center gap-2 text-sm text-stone-700">
            <svg class="h-4 w-4 text-brand-700 motion-safe:animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" /></svg>
            {{ t('assist.searching') }}
          </div>

          <!-- lỗi tìm -->
          <div v-else-if="turn.phase === 'error'" class="mt-3 flex flex-wrap items-center gap-3 text-sm" data-testid="ask-error">
            <span class="font-medium text-red-700"><svg class="inline-block mr-1 align-text-bottom" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3v.5"/></svg>{{ turn.error }}</span>
            <button type="button" class="btn-secondary !px-2.5 !py-1 !text-xs" :disabled="searching" @click="search(turn.key)">{{ t('app.retry') }}</button>
          </div>

          <template v-else-if="turn.result">
            <!-- không có căn cứ: câu giống hệt nhau dù văn bản không tồn tại hay người hỏi không được xem -->
            <div v-if="turn.result.status === 'no_evidence'" class="mt-3 rounded-lg border border-stone-200 bg-stone-50 p-4 text-sm text-stone-700" data-testid="ask-none">
              <p>{{ t('assist.noEvidence') }}</p>
              <NuxtLink :to="{ path: '/tim-kiem', query: { q: turn.question.slice(0, 200) } }" class="mt-2 inline-block font-medium text-brand-700 underline underline-offset-2">{{ t('assist.openSearch') }}</NuxtLink>
            </div>

            <template v-else>
              <p v-if="turn.result.status === 'passages_only'" class="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" data-testid="ask-passages">
                {{ t('assist.passagesOnly') }}
              </p>

              <!-- câu trả lời do mô hình viết (đã qua kiểm trích dẫn) -->
              <section v-if="blocks(turn.result).model" class="mt-3 rounded-lg border border-sky-200 bg-sky-50/60 p-4" data-testid="ask-model">
                <div class="mb-2 flex flex-wrap items-center gap-2">
                  <h3 class="text-sm font-semibold text-stone-800">{{ t('assist.modelTitle') }}</h3>
                  <span class="chip gap-1 bg-white text-sky-900 ring-1 ring-sky-300">
                    <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4L12 3z" /></svg>
                    {{ t('assist.modelNote') }}
                  </span>
                </div>
                <AnswerText :text="blocks(turn.result).model.text" :sources="turn.result.sources" :ask="turn.result.ask_id" />
                <!-- F4.4: chữ gửi mô hình đã che, mô hình viết nhãn [SĐT-1] thay cho số -->
                <p v-if="hasMask(blocks(turn.result).model.text)" class="mt-2 text-xs text-sky-900" data-testid="ask-masked">
                  {{ t('assist.maskedNote') }}
                </p>
                <button
                  v-if="blocks(turn.result).extract" type="button"
                  class="mt-3 text-xs font-medium text-brand-700 underline underline-offset-2"
                  :aria-expanded="turn.showExtract" :aria-controls="`trich-${turn.key}`"
                  @click="turn.showExtract = !turn.showExtract"
                >
                  {{ turn.showExtract ? t('assist.hideExtract') : t('assist.showExtract') }}
                </button>
              </section>

              <!-- câu trích nguyên văn từ văn bản -->
              <section
                v-if="blocks(turn.result).extract && (!blocks(turn.result).model || turn.showExtract)"
                :id="`trich-${turn.key}`" class="mt-3 rounded-lg border border-stone-200 bg-stone-50 p-4" data-testid="ask-extract"
              >
                <h3 class="mb-2 text-sm font-semibold text-stone-800">{{ t('assist.extractTitle') }}</h3>
                <AnswerText :text="blocks(turn.result).extract.text" :sources="turn.result.sources" :ask="turn.result.ask_id" />
              </section>

              <!-- đang viết câu trả lời -->
              <div v-if="turn.gen === 'waiting' || turn.gen === 'running'" class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-dashed border-sky-300 p-3 text-sm text-stone-700" data-testid="ask-generating">
                <svg class="h-4 w-4 text-brand-700 motion-safe:animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" /></svg>
                <span class="font-medium">{{ turn.gen === 'waiting' ? t('assist.waiting') : t('assist.generating') }}</span>
                <span v-if="turn.gen === 'running'" class="text-stone-500 tabular-nums">{{ t('assist.elapsed', { s: elapsed(turn) }) }}</span>
                <button type="button" class="btn-secondary ml-auto !px-2.5 !py-1 !text-xs" @click="stop(turn.key)">{{ t('assist.stop') }}</button>
                <span class="basis-full text-xs text-stone-500">{{ t('assist.generatingHint') }}</span>
              </div>
              <div v-else-if="turn.gen === 'stopped' || turn.gen === 'failed'" class="mt-3 flex flex-wrap items-center gap-3 text-sm text-amber-900" data-testid="ask-generate-note">
                <span><svg class="inline-block mr-1 align-text-bottom" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3v.5"/></svg>{{ turn.gen === 'stopped' ? t('assist.stopped') : t('assist.generateFailed', { reason: turn.genError }) }}</span>
                <button v-if="needsGenerate(turn.result)" type="button" class="btn-secondary !px-2.5 !py-1 !text-xs" @click="queueGenerate(turn.key)">{{ t('assist.retryGenerate') }}</button>
              </div>

              <ul v-if="warningTexts(turn.result).length" class="mt-3 space-y-1 text-xs text-amber-900" data-testid="ask-warnings">
                <li v-for="w in warningTexts(turn.result)" :key="w"><svg class="inline-block mr-1 align-text-bottom" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3v.5"/></svg>{{ w }}</li>
              </ul>

              <!-- nguồn -->
              <div v-if="turn.result.sources.length" class="mt-4">
                <h3 class="mb-2 text-sm font-semibold text-stone-800">{{ t('assist.source.title') }}</h3>
                <ol class="space-y-2" data-testid="ask-sources">
                  <li
                    v-for="s in turn.result.sources" :id="sourceAnchor(turn.result.ask_id, s.n)" :key="s.n" tabindex="-1"
                    class="scroll-mt-20 rounded-lg border border-stone-200 p-3 focus:outline-2 focus:outline-brand-600"
                  >
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="font-mono text-xs font-semibold text-brand-800" aria-hidden="true">[{{ s.n }}]</span>
                      <span class="sr-only">{{ t('assist.source.n', { n: s.n }) }}</span>
                      <!-- nhãn trích dẫn: mở tệp đúng trang được trích -->
                      <button
                        v-if="canView(s)" type="button" data-testid="ask-view"
                        class="text-left text-sm font-semibold text-brand-800 underline decoration-brand-300
                          underline-offset-2 hover:decoration-brand-700 disabled:opacity-60"
                        :aria-label="t('assist.viewSource', { label: citeLabel(s, t, true) })"
                        :title="s.page ? t('assist.viewPage', { n: s.page }) : t('assist.viewFile')"
                        :disabled="opening !== ''" :aria-busy="opening === viewKey(turn, s)"
                        @click="viewSource(turn, s)"
                      >
                        {{ citeLabel(s, t) }}
                      </button>
                      <span v-else class="text-sm font-semibold text-stone-900">{{ citeLabel(s, t) }}</span>
                      <span v-if="s.cited" class="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">{{ t('assist.source.cited') }}</span>
                      <StatusChip :status="s.status" />
                    </div>
                    <p class="mt-1 text-sm text-stone-800">{{ s.summary }}</p>
                    <p class="mt-0.5 text-xs text-stone-500">{{ metaLine(s) }}</p>
                    <p
                      v-if="s.excerpt" :id="`${sourceAnchor(turn.result.ask_id, s.n)}-trich`"
                      class="mt-2 border-l-2 border-stone-200 pl-3 text-sm break-words whitespace-pre-line text-stone-600"
                      :class="{ 'line-clamp-3': s.excerpt.length > LONG_EXCERPT && !turn.opened.includes(s.n) }"
                    >
                      <span class="sr-only">{{ t('assist.source.excerpt') }}: </span>{{ s.excerpt }}
                    </p>
                    <div class="mt-2 flex flex-wrap items-center gap-4 text-xs">
                      <button
                        v-if="s.excerpt.length > LONG_EXCERPT" type="button" class="font-medium text-stone-600 underline underline-offset-2 hover:text-stone-900"
                        :aria-expanded="turn.opened.includes(s.n)" :aria-controls="`${sourceAnchor(turn.result.ask_id, s.n)}-trich`"
                        @click="toggleExcerpt(turn, s.n)"
                      >
                        {{ turn.opened.includes(s.n) ? t('assist.source.less') : t('assist.source.more') }}
                      </button>
                      <NuxtLink
                        :to="`/van-ban/${s.document_id}`" class="font-medium text-brand-700 underline underline-offset-2 hover:text-brand-900"
                        :aria-label="t('assist.openDocumentFor', { label: citeLabel(s, t, true) })"
                      >
                        {{ t('assist.openDocument') }}
                      </NuxtLink>
                    </div>
                  </li>
                </ol>

                <!-- khung xem tệp, mở đúng trang được trích -->
                <div
                  v-if="viewer && viewer.turn === turn.key" :id="`xem-${turn.key}`" tabindex="-1"
                  class="mt-4 rounded-lg border border-stone-200 focus:outline-2 focus:outline-brand-600"
                  data-testid="ask-viewer"
                >
                  <div class="flex flex-wrap items-center gap-3 border-b border-stone-200 px-4 py-2 text-sm">
                    <span class="min-w-0 flex-1 truncate font-medium">
                      {{ t('assist.viewer.title', { label: viewer.label }) }}
                    </span>
                    <a
                      :href="pageUrl(viewer.url, viewer.page)" target="_blank" rel="noopener"
                      class="text-brand-800 hover:underline"
                    >
                      {{ t('assist.viewer.newTab') }}
                    </a>
                    <button type="button" class="btn-ghost" @click="closeViewer">{{ t('assist.viewer.close') }}</button>
                  </div>
                  <iframe
                    :key="pageUrl(viewer.url, viewer.page)" :src="pageUrl(viewer.url, viewer.page)"
                    :title="t('assist.viewer.title', { label: viewer.label })" class="h-[75vh] w-full"
                  />
                  <p class="border-t border-stone-200 px-4 py-2 text-xs text-stone-500">
                    {{ t('assist.viewer.note') }}
                  </p>
                </div>
              </div>
            </template>
          </template>
        </article>
      </div>
    </section>
  </div>
</template>
