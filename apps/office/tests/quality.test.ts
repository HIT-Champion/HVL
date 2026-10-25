// Copyright 2026 Signet Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0


// Cờ kiểm chất lượng số liệu (F3.9, F3.11): cờ của biểu đồ từ các dòng office.report_checks (đúng khuôn CSDL trả,
// db/tests/test_report_checks.py), câu số liệu từng luật; cờ của lượt nộp lưu từ assertion nguyên văn trong sự kiện
// OpenLineage (đúng khuôn svc_files.lineage: bước tables ghi ở facet đầu ra, bước manifest ở inputFacets). Thêm: trang
// Điều hành đặt cờ cạnh đúng từng nút Nguồn số liệu, hỏi bằng truy vấn riêng; khóa i18n đủ hai thứ tiếng.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import type { LineageEvent } from '../app/utils/lineage.ts'
import type { ReportCheck } from '../app/utils/quality.ts'

const { BOARD_CHARTS } = await import('../app/utils/lineage.ts')
const { REPORT_RULES, assertionsByTable, chartCheck, checkMessages, checksFor, eventAssertions, parquetTable,
  runCheck, stepCheck, worstCheck } = await import('../app/utils/quality.ts')

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const board = read('../app/pages/dieu-hanh.vue')
const page = read('../app/pages/pha-he.vue')
const chartChecks = read('../app/components/ChartChecks.vue')
const flag = read('../app/components/QualityFlag.vue')
const qualitySource = read('../app/utils/quality.ts')
const svcLineage = read('../../../services/svc-files/src/svc_files/lineage.py')

type Messages = { [key: string]: string | Messages }
const vi = JSON.parse(read('../app/locales/vi.json')) as Messages
const en = JSON.parse(read('../app/locales/en.json')) as Messages
function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}
function keysOf(messages: Messages, prefix = ''): string[] {
  return Object.entries(messages)
    .flatMap(([k, v]) => (typeof v === 'string' ? [prefix + k] : keysOf(v, `${prefix}${k}.`)))
}

// --- Số liệu báo cáo ----------------------------------------------------------------------------------------------

const check = (rule: string, report: string, status: ReportCheck['status'], expected = 0, actual = 0, issues = 0,
  detail: string[] | null = null): ReportCheck => ({ rule, report, status, expected, actual, issues, detail })
// Như CSDL trả cho một đơn vị có văn bản đang xử lý chưa rõ phòng chủ trì
const CHECKS: ReportCheck[] = [
  check('status_total', 'office.v_document_counts', 'PASSED', 9, 9),
  check('department_total', 'office.v_overdue_by_department', 'WARNING', 4, 4, 2),
  check('processing_coverage', 'office.v_processing_time', 'PASSED', 2, 2),
  ...['office.v_document_counts', 'office.v_overdue_by_department', 'office.v_processing_time',
    'office.v_outgoing_by_month'].map((v) => check('unique_keys', v, 'PASSED', 2, 2)),
  ...['office.v_document_counts', 'office.v_overdue_by_department', 'office.v_processing_time',
    'office.v_outgoing_by_month', 'office.v_overdue_rate'].map((v) => check('no_personal_columns', v, 'PASSED')),
]

test('cờ nặng nhất: Trượt > Cảnh báo > Đạt, không có cờ nào thì null', () => {
  assert.equal(worstCheck([]), null)
  assert.equal(worstCheck([null, undefined]), null)
  assert.equal(worstCheck(['PASSED', 'PASSED']), 'PASSED')
  assert.equal(worstCheck(['PASSED', 'WARNING', null]), 'WARNING')
  assert.equal(worstCheck(['WARNING', 'FAILED', 'PASSED']), 'FAILED')
})

test('cờ của biểu đồ: nặng nhất trong các luật trên các khung nhìn biểu đồ dùng', () => {
  const flags = Object.fromEntries(BOARD_CHARTS.map((c) => [c.id, chartCheck(CHECKS, c)]))
  assert.deepEqual(flags, { kpis: 'PASSED', status: 'PASSED', departments: 'WARNING', processing: 'PASSED',
    outgoing: 'PASSED' })
  // mọi biểu đồ có luật về số, không chỉ luật catalog
  for (const c of BOARD_CHARTS) {
    assert.ok(checksFor(CHECKS, c.views).some((r) => r.rule !== 'no_personal_columns'), c.id)
  }
  // nặng trước, rồi theo thứ tự REPORT_RULES, rồi tên khung nhìn; khung nhìn không có biểu đồ không lọt vào
  const failed = [...CHECKS, check('no_personal_columns', 'office.v_document_counts', 'FAILED', 0, 1, 1)]
  const kpis = checksFor(failed, BOARD_CHARTS.find((c) => c.id === 'kpis')!.views)
  assert.deepEqual(kpis.map((r) => `${r.status} ${r.rule} ${r.report}`), [
    'FAILED no_personal_columns office.v_document_counts',
    'PASSED status_total office.v_document_counts',
    'PASSED processing_coverage office.v_processing_time',
    'PASSED unique_keys office.v_document_counts',
    'PASSED unique_keys office.v_processing_time',
    'PASSED no_personal_columns office.v_document_counts',
    'PASSED no_personal_columns office.v_processing_time',
  ])
  assert.equal(chartCheck(failed, BOARD_CHARTS.find((c) => c.id === 'kpis')!), 'FAILED')
  assert.equal(chartCheck([], BOARD_CHARTS[0]!), null)
})

test('câu số liệu: câu chính của luật, thêm câu detail khi CSDL có detail', () => {
  assert.deepEqual(checkMessages(check('department_total', 'office.v_overdue_by_department', 'WARNING', 4, 4, 2)), [
    ['quality.rules.department_total.figures', { expected: 4, actual: 4, issues: 2, detail: '' }]])
  assert.deepEqual(checkMessages(check('processing_coverage', 'office.v_processing_time', 'FAILED', 4, 3, 1,
    ['2026-07', '2026-08'])).map(([key, p]) => `${key} ${p.detail}`), [
    'quality.rules.processing_coverage.figures 2026-07, 2026-08',
    'quality.rules.processing_coverage.detail 2026-07, 2026-08'])
  assert.equal(checkMessages(check('status_total', 'office.v_document_counts', 'PASSED', 9, 9, 0, [])).length, 1)
  // mọi câu có đủ hai thứ tiếng, tham số trong câu đều là tham số hàm truyền
  for (const rule of REPORT_RULES) {
    for (const [key, params] of checkMessages(check(rule, 'office.v_x', 'FAILED', 1, 2, 3, ['a']))) {
      for (const messages of [vi, en]) {
        const text = lookup(messages, key)
        assert.ok(text, key)
        for (const m of text.matchAll(/\{(\w+)\}/g)) assert.ok(m[1]! in params, `${key}: {${m[1]}}`)
      }
    }
  }
})

// --- Nộp lưu ------------------------------------------------------------------------------------------------------

const T = 'c300d5bb-028f-44cc-ba10-7b5277a4225d'
const PREFIX = `cold/${T}/case/7f1e6c1a-0000-4000-8000-000000000001/`
const H = (c: string) => c.repeat(64)
const REQUIRED: Record<string, string[]> = {
  documents: ['id', 'case_file_id', 'direction', 'status', 'type_code', 'summary', 'created_by', 'created_at'],
  assignments: ['id', 'document_id', 'role', 'status', 'assigned_by', 'assigned_at'],
}
// Đúng khuôn quality_facets của svc_files.lineage: số dòng khớp nguồn + không null từng cột bắt buộc
function assertions(table: string, failing: string[] = []) {
  return { dataQualityAssertions: { assertions: [
    { assertion: 'row_count_equals_source', success: !failing.includes('rows') },
    ...REQUIRED[table]!.map((column) => ({ assertion: 'not_null', column, success: !failing.includes(column) })),
  ] } }
}
const parquet = (table: string, i: number) => `${PREFIX}${table}-${H(String(i))}.parquet`
function step(name: string, event: Record<string, unknown>, extra: Partial<LineageEvent> = {}): LineageEvent {
  return { run_id: `${name}-run`, parent_run_id: 'run', job: `moc.case_file.archive.${name}`, event_type: 'COMPLETE',
    event_time: '2026-10-24T03:00:00Z', inputs: [], outputs: [], quality_ok: null, event, ...extra }
}
function archiveRun(failing: Record<string, string[]> = {}): LineageEvent[] {
  const tables = Object.keys(REQUIRED)
  return [
    step('files', { inputs: [{ name: 'tenant/x' }], outputs: [{ name: `${PREFIX}files/${H('b')}` }] }),
    step('tables', { outputs: tables.map((t, i) => ({ namespace: 's3://moc-cold', name: parquet(t, i + 1),
      facets: { schema: {}, ...assertions(t, failing[t]) }, outputFacets: { outputStatistics: { rowCount: 2 } } })) },
    { quality_ok: !Object.keys(failing).length }),
    // bước manifest mang lại đúng các mục đó ở inputFacets của đầu vào (quality_ok null: emit chỉ đọc facets)
    step('manifest', { inputs: tables.map((t, i) => ({ namespace: 's3://moc-cold', name: parquet(t, i + 1),
      facets: { schema: {} }, inputFacets: assertions(t, failing[t]) })),
    outputs: [{ name: `${PREFIX}manifest.json` }] }),
    step('commit', { inputs: [{ name: `${PREFIX}manifest.json` }], outputs: [] }),
  ]
}

test('assertion lấy nguyên văn từ sự kiện: facet đầu ra của bước tables, inputFacets của bước manifest', () => {
  const [files, tables, manifest, commit] = archiveRun()
  assert.equal(eventAssertions(tables!).length, 1 + 8 + 1 + 6)
  assert.deepEqual(eventAssertions(manifest!), eventAssertions(tables!))
  assert.deepEqual(eventAssertions(tables!)[0], { dataset: 'documents', assertion: 'row_count_equals_source',
    success: true })
  assert.deepEqual(eventAssertions(tables!)[1], { dataset: 'documents', assertion: 'not_null', column: 'id',
    success: true })
  assert.deepEqual([files, tables, manifest, commit].map((e) => stepCheck(e!)), [null, 'PASSED', 'PASSED', null])
  assert.equal(parquetTable(parquet('events', 3)), 'events')
  assert.equal(parquetTable('s3://khac/ten-la'), 's3://khac/ten-la')
  // sự kiện không kèm nguyên văn (chỉ cột tóm tắt): theo quality_ok
  const bare = { ...tables!, event: undefined }
  assert.equal(stepCheck(bare), 'PASSED')
  assert.equal(stepCheck({ ...bare, quality_ok: false }), 'FAILED')
  assert.equal(stepCheck({ ...bare, quality_ok: null }), null)
})

test('cờ của lượt nộp lưu: gộp trùng giữa các bước, trượt một mục là Trượt, không ghi mục nào là Cảnh báo', () => {
  const ok = runCheck(archiveRun())
  assert.equal(ok.status, 'PASSED')
  assert.equal(ok.assertions.length, 16)   // tables và manifest cùng mục: không đếm hai lần
  assert.deepEqual(assertionsByTable(ok.assertions).map((g) => [g.dataset, g.total, g.failed.length]),
    [['documents', 9, 0], ['assignments', 7, 0]])

  const bad = runCheck(archiveRun({ documents: ['summary'], assignments: ['rows'] }))
  assert.equal(bad.status, 'FAILED')
  assert.deepEqual(assertionsByTable(bad.assertions).map((g) => [g.dataset, g.failed.map((a) => a.column ??
    a.assertion)]), [['documents', ['summary']], ['assignments', ['row_count_equals_source']]])
  assert.equal(stepCheck(archiveRun({ documents: ['id'] })[1]!), 'FAILED')

  // cùng một mục, bước này đạt bước kia trượt: giữ trượt
  const [, tables] = archiveRun()
  const [, , manifest] = archiveRun({ documents: ['created_by'] })
  assert.equal(runCheck([tables!, manifest!]).status, 'FAILED')

  // lượt không ghi mục kiểm nào (vd ghi phả hệ của bước tables lỗi): không có gì bảo chứng
  assert.deepEqual(runCheck(archiveRun().filter((e) => !/tables|manifest/.test(e.job))),
    { status: 'WARNING', assertions: [] })
})

test('tên mục kiểm mà svc-files ghi đều có chữ hai thứ tiếng', () => {
  const names = new Set([...svcLineage.matchAll(/"assertion": "(\w+)"/g)].map((m) => m[1]!))
  assert.deepEqual([...names].sort(), ['not_null', 'row_count_equals_source'])
  for (const name of names) {
    assert.ok(lookup(vi, `quality.assertion.${name}`) && lookup(en, `quality.assertion.${name}`), name)
  }
})

// --- Trang ------------------------------------------------------------------------------------------------------

test('trang Điều hành: cờ cạnh đúng từng nút Nguồn số liệu, hỏi bằng truy vấn riêng sau số liệu', () => {
  const template = board.slice(board.indexOf('<template>'))
  const sources = [...template.matchAll(/<SourceLink chart="(\w+)"/g)].map((m) => m[1]!)
  const flags = [...template.matchAll(
    /<ChartChecks chart="(\w+)" :checks="checks" :failed="checksFailed" \/>\s*<SourceLink chart="(\w+)"/g)]
  assert.deepEqual(flags.map((m) => m[1]), flags.map((m) => m[2]))
  assert.deepEqual(flags.map((m) => m[1]).sort(), sources.sort())
  assert.deepEqual(sources.sort(), BOARD_CHARTS.map((c) => c.id).sort())
  // truy vấn riêng: QUERY của số liệu không đổi (lineage.test.ts), CHECKS lấy đủ trường của ReportCheck
  const fields = /export interface ReportCheck \{([\s\S]*?)\n\}/.exec(qualitySource)![1]!
    .split('\n').map((l) => /^\s*(\w+):/.exec(l)?.[1]).filter(Boolean)
  const query = /const CHECKS = '\{ office_report_checks \{ ([\w ]+) \} \}'/.exec(board)
  assert.ok(query, 'dieu-hanh.vue không có CHECKS')
  assert.deepEqual(query[1]!.split(' '), fields)
  assert.doesNotMatch(/const QUERY = `([\s\S]*?)`/.exec(board)![1]!, /report_checks/)
  // hỏi cờ sau khi biểu đồ đã có số (không tranh CSDL với truy vấn biểu đồ đang chờ), chỉ khi có số để kiểm
  assert.match(board, /finally \{\n\s*loading\.value = false\n\s*\}\n\s*if \(loaded\.value\) await loadChecks\(\)\n\}/)
  assert.equal([...board.matchAll(/(?<!function )loadChecks\(\)/g)].length, 1)
  // bấm cờ mở mục kiểm chất lượng của trang Phả hệ, lọc đúng biểu đồ
  assert.match(chartChecks, /:to="\{ path: '\/pha-he', query: \{ 'bieu-do': chart \}, hash: '#chat-luong' \}"/)
  assert.match(page, /<section id="chat-luong"/)
  assert.match(page, /office_report_checks \{ rule report status expected actual issues detail \}/)
  assert.match(page,
    /stopped: core_lineage_events\(where: \{quality_ok: \{_eq: false\}\}, order_by: \{id: desc\}, limit: 1\)/)
})

test('mọi khóa i18n của cờ kiểm chất lượng có đủ tiếng Việt và tiếng Anh', () => {
  const keys = new Set([
    ...[board, page, chartChecks, flag].flatMap((src) => [...src.matchAll(/'(quality\.[\w.]+)'/g)].map((m) => m[1]!)),
    ...['PASSED', 'WARNING', 'FAILED', 'NONE'].map((s) => `quality.status.${s}`),
    ...REPORT_RULES.flatMap((r) => ['name', 'what', 'figures'].map((k) => `quality.rules.${r}.${k}`)),
  ])
  assert.ok(keys.size > 25, `chỉ thấy ${keys.size} khóa`)
  for (const key of keys) {
    assert.ok(lookup(vi, key), `vi thiếu ${key}`)
    assert.ok(lookup(en, key), `en thiếu ${key}`)
  }
  assert.deepEqual(keysOf(vi.quality as Messages).sort(), keysOf(en.quality as Messages).sort())
  // chữ trên cờ đúng như đề: Đạt / Cảnh báo / Trượt
  assert.deepEqual(['PASSED', 'WARNING', 'FAILED'].map((s) => lookup(vi, `quality.status.${s}`)),
    ['Đạt', 'Cảnh báo', 'Trượt'])
})
