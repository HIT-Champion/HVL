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

import { GraphChart } from 'echarts/charts';
import { use } from 'echarts/core';
import { useI18n } from 'vue-i18n';
import {
  ARCHIVE_JOB, BOARD_CHARTS, chartNode, datasetNode, isBoardChart, lineageGraph, lineageLayout, lineageUpstream,
  toOpenLineage } from
'~/utils/lineage';
import {
  checkMessages, checksFor, runCheck, worstCheck } from
'~/utils/quality';

// Phả hệ số liệu (F3.9, F3.11), cho lãnh đạo đơn vị — cùng quyền với trang Điều hành. Biểu đồ nào lấy số từ khung
// nhìn nào: khai ở app/utils/lineage.ts. Khung nhìn đọc bảng nào: office.report_lineage tính từ catalog PostgreSQL lúc
// truy vấn (migration 1792281602900) — chỉ có tên và cạnh, giống nhau cho mọi đơn vị. Lượt nộp lưu gần nhất: sự kiện
// OpenLineage trong core.lineage_events, Hasura lọc theo đơn vị trong token. Không có số dòng của bảng nguồn (lý do ở
// migration); số dòng của bảng Parquet lấy từ facet outputStatistics của chính sự kiện.
// Cờ kiểm chất lượng (Đạt / Cảnh báo / Trượt): số liệu báo cáo theo bộ luật tính trong CSDL (office.report_checks,
// migration 1792281603300), cùng quyền; nộp lưu theo assertion svc-files đã ghi trong sự kiện (facet
// dataQualityAssertions), lấy nguyên văn — kể cả lượt bị dừng vì trượt kiểm, vốn không có run COMPLETE nào.

// Đồ thị ECharts loại graph chỉ trang này dùng: đăng ký ở đây (use() của ECharts là đăng ký toàn cục, chạy trước khi
// EChart.vue vẽ) để trang Điều hành không phải tải thêm phần này
use([GraphChart]);

const QUERY = `{
  office_report_lineage { report consumer source source_kind depth }
  runs: core_lineage_events(where: {job: {_eq: "${ARCHIVE_JOB}"}, event_type: {_eq: "COMPLETE"}},
    order_by: {id: desc}, limit: 1) { run_id }
  archived: core_lineage_events_aggregate(where: {job: {_eq: "${ARCHIVE_JOB}"}, event_type: {_eq: "COMPLETE"}}) {
    aggregate { count } }
  failed: core_lineage_events_aggregate(where: {quality_ok: {_eq: false}}) { aggregate { count } }
  stopped: core_lineage_events(where: {quality_ok: {_eq: false}}, order_by: {id: desc}, limit: 1) {
    run_id parent_run_id job event_type event_time inputs outputs quality_ok event }
  office_report_checks { rule report status expected actual issues detail }
}`;
const RUN = `query ($run: uuid!) {
  core_lineage_events(where: {_or: [{run_id: {_eq: $run}}, {parent_run_id: {_eq: $run}}]}, order_by: {id: asc}) {
    run_id parent_run_id job event_type event_time inputs outputs quality_ok event
  }
}`;
const KINDS = ['chart', 'view', 'table', 'job', 'object'];
// Nút là hộp chữ cùng cỡ, đặt theo lưới điểm ảnh (cột COL, hàng ROW), giữ tỉ lệ để hộp không méo. Đồ thị vẽ
// đúng cỡ thật (5 cột vừa khung 1056 điểm ảnh của trang); màn hẹp hơn thì cuộn ngang trong khung, không bóp nhỏ
// chữ cho chồng lên nhau
const BOX = { width: 176, height: 26 };
const COL = 216;
const ROW = 40;
const STYLE = {
  chart: { fill: '#555b3f', text: '#ffffff' },
  view: { fill: '#53666b', text: '#ffffff' },
  table: { fill: '#e7e5e4', text: '#292524' },
  job: { fill: '#454b39', text: '#ffffff' },
  object: { fill: '#eee3bc', text: '#30342a' }
};
const STEPS = ['files', 'tables', 'manifest', 'commit'];

const { t, te } = useI18n();
const { gql } = useApi();
const claims = useAuth().claims;
const route = useRoute();
const router = useRouter();

const catalog = ref([]);
const events = ref([]);
const checks = ref([]);
const stopped = ref(null);
const archivedRuns = ref(0);
const failedChecks = ref(0);
const readAt = ref('');
const loaded = ref(false);
const loading = ref(false);
const failure = ref('');
const allowed = computed(() => claims.value?.role === 'director');

async function load() {
  loading.value = true;
  failure.value = '';
  try {
    const data = await gql(






      QUERY);
    const run = data.runs[0]?.run_id;
    events.value = run ? (await gql(RUN, { run })).core_lineage_events : [];
    catalog.value = data.office_report_lineage;
    archivedRuns.value = data.archived.aggregate.count;
    failedChecks.value = data.failed.aggregate.count;
    stopped.value = data.stopped[0] ?? null;
    checks.value = data.office_report_checks;
    readAt.value = new Date().toISOString();
    loaded.value = true;
    // cờ trên trang Điều hành mở thẳng tới mục kiểm chất lượng (#chat-luong): mục chỉ có sau khi tải xong
    if (route.hash === '#chat-luong') nextTick(() => document.getElementById('chat-luong')?.scrollIntoView());
  } catch (e) {
    failure.value = errorText(t, e);
  } finally {
    loading.value = false;
  }
}
onMounted(() => {
  if (allowed.value) load();
});

// Biểu đồ đang xem theo ?bieu-do= (nút "Nguồn số liệu" của trang Điều hành mở thẳng tới đây); rỗng: mọi biểu đồ
const focus = computed({
  get: () => isBoardChart(route.query['bieu-do']) ? route.query['bieu-do'] : '',
  set: (value) => {router.replace({ query: { ...route.query, 'bieu-do': value || undefined } });}
});
const charts = computed(() => BOARD_CHARTS.filter((c) => !focus.value || c.id === focus.value));
const full = computed(() => lineageGraph(BOARD_CHARTS, catalog.value, events.value));
// Đồ thị mọi biểu đồ không vẽ cạnh commit (manifest → bảng, đi ngược qua cả đồ thị); chọn một biểu đồ thì có
const graph = computed(() => focus.value ? lineageUpstream(full.value, chartNode(focus.value)) :
{ nodes: full.value.nodes, edges: full.value.edges.filter((e) => e.kind !== 'commit') });
const placed = computed(() => lineageLayout(graph.value));
// Cỡ thật của đồ thị: đủ số cột, số hàng (hai dải), lề nửa hộp mỗi bên, chú giải ở dưới
const graphWidth = computed(() => Math.max(0, ...placed.value.map((p) => p.layer)) * COL + BOX.width + 16);
const graphHeight = computed(() => {
  const rows = placed.value.map((p) => p.row);
  return Math.max(160, (Math.max(0, ...rows) - Math.min(0, ...rows)) * ROW + BOX.height + 64);
});

function nodeName(n) {
  return n.kind === 'chart' || n.kind === 'job' ? t(n.label) : n.label;
}
function nodeText(n, short = false) {
  if (n.count) return `${nodeName(n)} (${short ? n.count : t('lineage.objects', { n: n.count })})`;
  if (n.rows !== undefined) return `${nodeName(n)} · ${t('lineage.rows', { n: n.rows })}`;
  return nodeName(n);
}
function escape(text) {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

const graphOption = computed(() => {
  const at = new Map(placed.value.map((p) => [p.id, p]));
  const byId = new Map(graph.value.nodes.map((n) => [n.id, n]));
  return {
    tooltip: {
      formatter: (p) => p.data.tip ?? ''
    },
    legend: { bottom: 0, data: KINDS.map((k) => t(`lineage.kind.${k}`)) },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: false, // vẽ đúng cỡ, màn hẹp cuộn ngang khung; thu phóng bằng con lăn sẽ cướp cuộn trang
      preserveAspect: 'contain',
      left: BOX.width / 2 + 8,
      right: BOX.width / 2 + 8,
      top: BOX.height / 2 + 8,
      bottom: BOX.height / 2 + 40,
      categories: KINDS.map((k) => ({ name: t(`lineage.kind.${k}`), itemStyle: { color: STYLE[k].fill } })),
      data: graph.value.nodes.map((n) => ({
        id: n.id,
        name: nodeText(n, true),
        x: (at.get(n.id)?.layer ?? 0) * COL,
        y: (at.get(n.id)?.row ?? 0) * ROW,
        category: KINDS.indexOf(n.kind),
        itemStyle: { color: STYLE[n.kind].fill },
        label: { color: STYLE[n.kind].text },
        tip: `${escape(t(`lineage.kind.${n.kind}`))}<br><b>${escape(nodeText(n))}</b>` + (
        n.kind === 'object' ? `<br>${escape(n.id)}` : '') + (
        n.kind === 'view' && viewFlag(n.id) ? `<br>${escape(t('lineage.quality'))}: ` +
        escape(t(`quality.status.${viewFlag(n.id)}`)) : '')
      })),
      links: graph.value.edges.map((e) => ({
        source: e.source,
        target: e.target,
        tip: `${escape(nodeName(byId.get(e.source)))} → ${escape(nodeName(byId.get(e.target)))}` +
        ` (${escape(t(`lineage.edge.${e.kind}`))})`,
        lineStyle: e.kind === 'commit' ? { type: 'dashed', color: '#d97706' } : undefined
      })),
      symbol: 'rect',
      symbolSize: [BOX.width, BOX.height],
      label: { show: true, position: 'inside', fontSize: 11, width: BOX.width - 12, overflow: 'truncate' },
      lineStyle: { color: '#a8a29e', width: 1.5, opacity: 0.9 },
      emphasis: { focus: 'adjacency' }
    }]
  };
});
// Tóm tắt cho trình đọc màn hình; bảng bên dưới có đủ chi tiết
const graphLabel = computed(() => charts.value.
map((c) => `${t(c.label)} ← ${c.views.join(', ')}`).join('; '));

// Bảng nguồn của từng biểu đồ: mỗi khung nhìn của biểu đồ, mọi quan hệ nó đọc (cả qua view lồng), theo catalog
const sourceRows = computed(() => charts.value.flatMap((c) => c.views.map((view) => ({
  chart: c,
  view,
  sources: catalog.value.filter((e) => e.report === view).
  sort((a, b) => a.depth - b.depth || a.source.localeCompare(b.source))
}))));
// Mọi khung nhìn báo cáo trong catalog, kể cả khung nhìn chưa có biểu đồ trên trang Điều hành
const reports = computed(() => [...new Set(catalog.value.map((e) => e.report))].sort().map((report) => ({
  report,
  tables: [...new Set(catalog.value.filter((e) => e.report === report && e.source_kind !== 'view').
  map((e) => e.source))].sort(),
  views: [...new Set(catalog.value.filter((e) => e.report === report && e.source_kind === 'view').
  map((e) => e.source))].sort(),
  charts: BOARD_CHARTS.filter((c) => c.views.includes(report))
})));

// Kiểm chất lượng số liệu của các khung nhìn mà (các) biểu đồ đang xem dùng; cờ của một khung nhìn là cờ nặng nhất
const checkRows = computed(() => checksFor(checks.value, [...new Set(charts.value.flatMap((c) => c.views))]));
function viewFlag(view) {
  return worstCheck(checksFor(checks.value, [view]).map((c) => c.status));
}
function checkText(c) {
  return checkMessages(c).map(([key, params]) => t(key, params)).join(' · ');
}
function viewDetail(view) {
  return checksFor(checks.value, [view]).
  map((c) => `${t(`quality.status.${c.status}`)} — ${t(`quality.rules.${c.rule}.name`)}: ${checkText(c)}`).
  join('\n');
}

const run = computed(() => events.value.find((e) => e.job === ARCHIVE_JOB && e.event_type === 'COMPLETE') ?? null);
const steps = computed(() => STEPS.map((name) => events.value.find((e) => e.job === `${ARCHIVE_JOB}.${name}`)).
filter((e) => !!e));
// Kiểm của lượt nộp lưu gần nhất: assertion nguyên văn của các bước. Lượt bị dừng vì trượt kiểm (không có run COMPLETE)
// mới hơn lượt đó thì hiện riêng, cờ Trượt kèm các mục trượt
const runQuality = computed(() => runCheck(events.value));
const stoppedRun = computed(() => stopped.value && (!run.value ||
Date.parse(stopped.value.event_time) > Date.parse(run.value.event_time)) ? stopped.value : null);
const stoppedQuality = computed(() => stoppedRun.value ? runCheck([stoppedRun.value]) : null);
function assertionText(a) {
  return te(`quality.assertion.${a.assertion}`) ? t(`quality.assertion.${a.assertion}`, { column: a.column ?? '' }) :
  [a.assertion, a.column].filter(Boolean).join(' ');
}
// Một dòng mỗi bảng của gói: số mục đạt / tổng, rồi các mục trượt
function tableText(g) {
  return t('quality.archive.table', { table: g.dataset, passed: g.total - g.failed.length, total: g.total });
}
function failedText(g) {
  return t('quality.archive.failedItems', { items: g.failed.map(assertionText).join(', ') });
}
function stepName(e) {
  return t(`lineage.steps.${e.job.slice(ARCHIVE_JOB.length + 1)}`);
}
// Tên dataset gọn như trên đồ thị; nhiều đối tượng gộp một nút thì ghi số đối tượng
function datasets(names) {
  const count = new Map();
  for (const name of names) {
    const d = datasetNode(name);
    const seen = count.get(d.id);
    count.set(d.id, { label: d.label, n: (seen?.n ?? 0) + 1 });
  }
  return [...count.values()].map((d) => d.n > 1 ? `${d.label} (${t('lineage.objects', { n: d.n })})` : d.label);
}

function exportOpenLineage() {
  const body = toOpenLineage(BOARD_CHARTS, catalog.value, events.value, new Date());
  const url = URL.createObjectURL(new Blob([body], { type: 'application/x-ndjson' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'pha-he-openlineage.jsonl';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
</script>

<template>
  <div class="sg-lineage min-w-0">
    <PageHeader :title="t('lineage.title')" :subtitle="t('lineage.subtitle')">
      <template v-if="allowed">
        <button class="btn-secondary" :disabled="!loaded" data-testid="lineage-export" @click="exportOpenLineage">
          {{ t('lineage.export') }}
        </button>
        <button class="btn-secondary" :disabled="loading" @click="load">{{ t('app.refresh') }}</button>
      </template>
    </PageHeader>
    <p v-if="!allowed" class="card p-12 text-center text-stone-500">{{ t('board.forbidden') }}</p>
    <p v-else-if="failure" class="card mb-4 p-4 text-sm text-red-700">{{ failure }}</p>
    <p v-if="allowed && !loaded && !failure" class="text-sm text-stone-500">{{ t('app.loading') }}</p>
    <div v-if="allowed && loaded" class="space-y-4">
      <section class="card min-w-0 p-4" data-testid="lineage-graph">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="font-medium text-stone-900">{{ t('lineage.graph') }}</h2>
            <p class="mt-1 text-xs text-stone-500">{{ t('lineage.graphHint') }}</p>
          </div>
          <div>
            <label for="lineage-chart" class="label">{{ t('lineage.chart') }}</label>
            <select id="lineage-chart" v-model="focus" class="input w-auto" data-testid="lineage-chart">
              <option value="">{{ t('lineage.allCharts') }}</option>
              <option v-for="c in BOARD_CHARTS" :key="c.id" :value="c.id">{{ t(c.label) }}</option>
            </select>
          </div>
        </div>
        <div class="mt-2 overflow-x-auto" tabindex="0" role="region" :aria-label="t('lineage.title')">
          <div :style="{ minWidth: `${graphWidth}px` }">
            <EChart :option="graphOption" :height="graphHeight" :label="graphLabel" />
          </div>
        </div>
        <p class="mt-2 text-xs text-stone-500" data-testid="lineage-read-at">
          {{ t('lineage.readAt', { time: fmtDateTime(readAt) }) }}
        </p>
      </section>

      <section class="card p-4" data-testid="lineage-sources">
        <h2 class="font-medium text-stone-900">{{ t('lineage.sources') }}</h2>
        <div class="mt-2 overflow-x-auto" tabindex="0" role="region" :aria-label="t('lineage.title')">
          <table class="w-full min-w-[680px] text-sm">
            <thead class="text-left text-xs text-stone-500">
              <tr>
                <th class="py-1 font-medium">{{ t('lineage.chart') }}</th>
                <th class="py-1 font-medium">{{ t('lineage.view') }}</th>
                <th class="py-1 font-medium">{{ t('lineage.readsFrom') }}</th>
                <th class="py-1 text-right font-medium">{{ t('lineage.quality') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="r in sourceRows" :key="`${r.chart.id}/${r.view}`" class="align-top">
                <td class="py-1.5 pr-3 text-stone-600">{{ t(r.chart.label) }}</td>
                <td class="py-1.5 pr-3 font-mono text-xs text-stone-900">{{ r.view }}</td>
                <td class="py-1.5">
                  <p v-if="!r.sources.length" class="text-xs text-red-700">{{ t('lineage.missing') }}</p>
                  <ul v-else class="space-y-0.5">
                    <li
                      v-for="s in r.sources" :key="`${s.consumer}/${s.source}`" class="font-mono text-xs text-stone-700"
                      :style="{ paddingLeft: `${(s.depth - 1) * 16}px` }"
                    >
                      {{ s.source }}
                      <span class="font-sans text-stone-500"> · {{ t(`lineage.sourceKind.${s.source_kind}`) }}</span>
                      <span v-if="s.depth > 1" class="font-sans text-stone-500">
                        · {{ t('lineage.through', { view: s.consumer }) }}
                      </span>
                    </li>
                  </ul>
                </td>
                <td class="py-1.5 pl-3 text-right">
                  <QualityFlag :status="viewFlag(r.view)" :detail="viewDetail(r.view)" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section id="chat-luong" class="card scroll-mt-4 p-4" data-testid="lineage-checks">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="font-medium text-stone-900">{{ t('quality.title') }}</h2>
          <QualityFlag :status="worstCheck(checkRows.map((c) => c.status))" />
        </div>
        <p class="mt-1 text-xs text-stone-500">{{ t('quality.hint') }}</p>
        <div class="mt-2 overflow-x-auto" tabindex="0" role="region" :aria-label="t('lineage.title')">
          <table class="w-full min-w-[680px] text-sm">
            <thead class="text-left text-xs text-stone-500">
              <tr>
                <th class="py-1 font-medium">{{ t('quality.view') }}</th>
                <th class="py-1 font-medium">{{ t('quality.rule') }}</th>
                <th class="py-1 font-medium">{{ t('quality.result') }}</th>
                <th class="py-1 font-medium">{{ t('quality.figures') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="c in checkRows" :key="`${c.rule}/${c.report}`" class="align-top" :data-rule="c.rule">
                <td class="py-1.5 pr-3 font-mono text-xs text-stone-900">{{ c.report }}</td>
                <td class="py-1.5 pr-3">
                  <div class="text-stone-800">{{ t(`quality.rules.${c.rule}.name`) }}</div>
                  <div class="text-xs text-stone-500">{{ t(`quality.rules.${c.rule}.what`) }}</div>
                </td>
                <td class="py-1.5 pr-3"><QualityFlag :status="c.status" /></td>
                <td class="py-1.5 text-xs text-stone-700">{{ checkText(c) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card p-4" data-testid="lineage-archive">
        <h2 class="font-medium text-stone-900">{{ t('lineage.archive') }}</h2>
        <p class="mt-1 text-xs text-stone-500" data-testid="lineage-archive-totals">
          {{ t('lineage.archiveTotals', { runs: archivedRuns, failed: failedChecks }) }}
        </p>
        <div
          v-if="stoppedRun && stoppedQuality" class="mt-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm"
          data-testid="lineage-archive-stopped"
        >
          <div class="flex flex-wrap items-center gap-2">
            <QualityFlag :status="stoppedQuality.status" />
            <span class="text-red-800">
              {{ t('quality.archive.stopped', { time: fmtDateTime(stoppedRun.event_time) }) }}
            </span>
          </div>
          <ul class="mt-1 space-y-0.5 text-xs text-stone-700">
            <li v-for="g in assertionsByTable(stoppedQuality.assertions)" :key="g.dataset">
              {{ tableText(g) }}<span v-if="g.failed.length" class="text-red-700"> · {{ failedText(g) }}</span>
            </li>
          </ul>
        </div>
        <p v-if="!run" class="py-6 text-center text-sm text-stone-500">{{ t('lineage.archiveNone') }}</p>
        <template v-else>
          <p class="mt-2 text-sm text-stone-700">
            {{ t('lineage.archiveRun', { run: run.run_id.slice(0, 8), time: fmtDateTime(run.event_time) }) }}
          </p>
          <div class="mt-2 rounded-md border border-stone-200 p-3" data-testid="lineage-archive-quality">
            <div class="flex flex-wrap items-center gap-2 text-sm">
              <span class="text-stone-700">{{ t('quality.archive.run') }}</span>
              <QualityFlag :status="runQuality.status" />
            </div>
            <p v-if="!runQuality.assertions.length" class="mt-1 text-xs text-amber-900">
              {{ t('quality.archive.none') }}
            </p>
            <ul v-else class="mt-1 space-y-0.5 text-xs text-stone-700">
              <li v-for="g in assertionsByTable(runQuality.assertions)" :key="g.dataset">
                {{ tableText(g) }}<span v-if="g.failed.length" class="text-red-700"> · {{ failedText(g) }}</span>
              </li>
            </ul>
            <p class="mt-1 text-xs text-stone-500">{{ t('quality.archive.source') }}</p>
          </div>
          <div class="mt-2 overflow-x-auto" tabindex="0" role="region" :aria-label="t('lineage.title')">
            <table class="w-full min-w-[680px] text-sm">
              <thead class="text-left text-xs text-stone-500">
                <tr>
                  <th class="py-1 font-medium">{{ t('lineage.step') }}</th>
                  <th class="py-1 font-medium">{{ t('lineage.inputs') }}</th>
                  <th class="py-1 font-medium">{{ t('lineage.outputs') }}</th>
                  <th class="py-1 text-right font-medium">{{ t('lineage.quality') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-stone-100">
                <tr v-for="e in steps" :key="e.run_id" class="align-top">
                  <td class="py-1.5 pr-3 text-stone-600">{{ stepName(e) }}</td>
                  <td class="py-1.5 pr-3 font-mono text-xs text-stone-700">
                    <div v-for="d in datasets(e.inputs)" :key="d">{{ d }}</div>
                  </td>
                  <td class="py-1.5 pr-3 font-mono text-xs text-stone-700">
                    <div v-for="d in datasets(e.outputs)" :key="d">{{ d }}</div>
                  </td>
                  <td class="py-1.5 text-right">
                    <QualityFlag :status="stepCheck(e)" :empty="t('lineage.notChecked')" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>

      <section class="card p-4" data-testid="lineage-reports">
        <h2 class="font-medium text-stone-900">{{ t('lineage.reports', { n: reports.length }) }}</h2>
        <p class="mt-1 text-xs text-stone-500">{{ t('lineage.reportsHint') }}</p>
        <div class="mt-2 overflow-x-auto" tabindex="0" role="region" :aria-label="t('lineage.title')">
          <table class="w-full min-w-[680px] text-sm">
            <thead class="text-left text-xs text-stone-500">
              <tr>
                <th class="py-1 font-medium">{{ t('lineage.view') }}</th>
                <th class="py-1 font-medium">{{ t('lineage.readsFrom') }}</th>
                <th class="py-1 font-medium">{{ t('lineage.usedBy') }}</th>
                <th class="py-1 text-right font-medium">{{ t('lineage.quality') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="r in reports" :key="r.report" class="align-top">
                <td class="py-1.5 pr-3 font-mono text-xs text-stone-900">{{ r.report }}</td>
                <td class="py-1.5 pr-3 font-mono text-xs text-stone-700">{{ [...r.views, ...r.tables].join(', ') }}</td>
                <td class="py-1.5 text-stone-600">
                  <template v-if="r.charts.length">
                    <NuxtLink
                      v-for="c in r.charts" :key="c.id" :to="{ query: { 'bieu-do': c.id } }"
                      class="mr-2 inline-block text-brand-700 hover:underline"
                    >{{ t(c.label) }}</NuxtLink>
                  </template>
                  <span v-else class="text-stone-400">{{ t('app.none') }}</span>
                </td>
                <td class="py-1.5 pl-3 text-right">
                  <QualityFlag :status="viewFlag(r.report)" :detail="viewDetail(r.report)" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
