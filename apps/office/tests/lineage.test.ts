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


// Phả hệ số liệu (F3.9, F3.11). Khai báo biểu đồ → khung nhìn (BOARD_CHARTS) phải khớp đúng mã thật của
// pages/dieu-hanh.vue: tập khung nhìn bằng đúng các trường gốc của QUERY, và từng biểu đồ (khối thẻ) dùng số của đúng
// các khung nhìn đã khai — lần theo các const / function của trang từ biểu thức Vue trong phần template của biểu đồ
// ({{ … }}, :x, v-…; bỏ chữ trong chuỗi và thuộc tính tĩnh) về tới dòng gán dữ liệu. Đồ thị: dựng từ cạnh catalog
// (đúng như office.report_lineage trả trên CSDL thật) và sự kiện của một lượt nộp lưu (khuôn của svc_files.lineage);
// lọc theo biểu đồ; xếp tầng; xuất OpenLineage. Thêm: khóa i18n đủ hai thứ tiếng, menu chỉ cho lãnh đạo đơn vị.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import type { CatalogEdge, LineageEvent, LineageGraph } from '../app/utils/lineage.ts'

const { BOARD_CHARTS, chartNode, datasetNode, isBoardChart, lineageGraph, lineageLayout, lineageUpstream,
  toOpenLineage } = await import('../app/utils/lineage.ts')

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const board = read('../app/pages/dieu-hanh.vue')
const page = read('../app/pages/pha-he.vue')
const sourceLink = read('../app/components/SourceLink.vue')
const echart = read('../app/components/EChart.vue')
const menu = read('../app/layouts/default.vue')

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

// --- Khai báo biểu đồ → khung nhìn khớp trang Điều hành --------------------------------------------------------------

/** Trường gốc của một truy vấn GraphQL (bỏ tham số, lựa chọn con, bí danh). */
function rootFields(query: string): string[] {
  let depth = 0
  let parens = 0
  let top = ''
  for (const ch of query) {
    if (ch === '(') parens++
    else if (ch === ')') parens--
    else if (parens) continue
    else if (ch === '{') { depth++; top += ' ' }
    else if (ch === '}') depth--
    else if (depth === 1) top += ch
  }
  return top.replace(/\w+\s*:/g, ' ').split(/\s+/).filter(Boolean)
}
// Trường gốc của Hasura cho bảng ngoài schema public là <schema>_<tên>
const viewOf = (field: string) => field.replace('_', '.')

const script = board.slice(board.indexOf('<script setup'), board.indexOf('</script>'))
const template = board.slice(board.indexOf('<template>'), board.lastIndexOf('</template>'))
const QUERY = /const QUERY = `([\s\S]*?)`/.exec(script)![1]!

/** Chỉ phần mã của một đoạn JS: bỏ chữ trong '…', "…"; với `…${x}…` chỉ giữ ${x} (lồng được). Chữ trong chuỗi —
 * khóa i18n như 'board.processing' — trùng tên ref dữ liệu thì không được tính là "dùng" ref đó. */
function codeOnly(src: string): string {
  let i = 0
  function skipQuoted(quote: string) {
    for (i++; i < src.length && src[i] !== quote; i++) if (src[i] === '\\') i++
    i++
  }
  function templateCode(): string {
    let out = ''
    for (i++; i < src.length && src[i] !== '`'; ) {
      if (src[i] === '\\') i += 2
      else if (src[i] === '$' && src[i + 1] === '{') {
        i += 2
        out += ` ${code(true)} `
      } else i++
    }
    i++
    return out
  }
  function code(inBraces: boolean): string {
    let out = ''
    let depth = 0
    while (i < src.length) {
      const ch = src[i]!
      if (ch === "'" || ch === '"') {
        skipQuoted(ch)
        out += ' '
      } else if (ch === '`') out += ` ${templateCode()} `
      else if (inBraces && ch === '}' && !depth) {
        i++
        return out
      } else {
        if (ch === '{') depth++
        else if (ch === '}') depth--
        out += ch
        i++
      }
    }
    return out
  }
  return code(false)
}
/** Các biểu thức Vue của một đoạn template: nội dung {{ … }} và giá trị của thuộc tính động (:x, @x, #x, v-…), đã bỏ
 * chữ trong chuỗi. Thuộc tính tĩnh (data-testid="board-processing", chart="processing", class) không phải mã. */
const INTERPOLATION = /\{\{([\s\S]*?)\}\}/g
const BOUND_ATTRIBUTE = /\s(?:[:@#]|v-)[^\s=>]*\s*=\s*"([^"]*)"/g
function expressionsIn(html: string): string {
  return [...html.matchAll(INTERPOLATION), ...html.matchAll(BOUND_ATTRIBUTE)]
    .map((m) => codeOnly(m[1]!)).join('\n')
}

// Các khai báo cấp ngoài cùng của <script setup> (const, function) và tên chúng dùng tới — bỏ chú thích và chữ
// trong chuỗi
const declarations = new Map<string, string>()
{
  const heads = [...script.matchAll(/^(?:const|let|function|async function)\s+(\w+)/gm)]
  heads.forEach((m, i) => declarations.set(m[1]!, codeOnly(script.slice(m.index, heads[i + 1]?.index ?? script.length)
    .replace(/\/\/.*$/gm, ''))))
}
function namesIn(text: string): Set<string> {
  return new Set([...text.matchAll(/[A-Za-z_]\w*/g)].map((m) => m[0]).filter((w) => declarations.has(w)))
}
function closure(start: Set<string>): Set<string> {
  const seen = new Set<string>()
  const stack = [...start]
  while (stack.length) {
    const name = stack.pop()!
    if (seen.has(name)) continue
    seen.add(name)
    for (const dep of namesIn(declarations.get(name)!)) if (!seen.has(dep)) stack.push(dep)
  }
  return seen
}
// Dữ liệu của từng khung nhìn vào ref nào: `counts.value = data.office_v_document_counts`
const refView = new Map([...script.matchAll(/(\w+)\.value = data\.(\w+)/g)].map((m) => [m[1]!, viewOf(m[2]!)]))

/** Khung nhìn mà một đoạn template dùng số: tên trong biểu thức Vue → lần theo khai báo → ref dữ liệu. */
function viewsUsedBy(html: string): string[] {
  return [...closure(namesIn(expressionsIn(html)))].filter((n) => refView.has(n)).map((n) => refView.get(n)!).sort()
}

/** Phần template của phần tử mang data-testid (tới thẻ đóng cùng tên). */
function block(testid: string): string {
  const at = template.indexOf(`data-testid="${testid}"`)
  assert.ok(at > 0, `trang Điều hành không có ${testid}`)
  const start = template.lastIndexOf('<', at)
  const tag = /^<(\w+)/.exec(template.slice(start))![1]!
  const re = new RegExp(`<(/?)${tag}\\b`, 'g')
  re.lastIndex = start
  let depth = 0
  for (let m = re.exec(template); m; m = re.exec(template)) {
    depth += m[1] ? -1 : 1
    if (!depth) return template.slice(start, m.index)
  }
  throw new Error(`không đóng được ${testid}`)
}

test('khai báo biểu đồ → khung nhìn: đúng các khung nhìn mà trang Điều hành truy vấn, không thừa không thiếu', () => {
  const queried = rootFields(QUERY).map(viewOf).sort()
  assert.deepEqual(queried, ['office.v_document_counts', 'office.v_outgoing_by_month', 'office.v_overdue_by_department',
    'office.v_processing_time'])
  assert.deepEqual([...new Set(BOARD_CHARTS.flatMap((c) => c.views))].sort(), queried)
  // mỗi khung nhìn truy vấn được gán vào đúng một ref dữ liệu
  assert.deepEqual([...refView.values()].sort(), queried)
  assert.equal(new Set(BOARD_CHARTS.map((c) => c.id)).size, BOARD_CHARTS.length)
})

test('từng biểu đồ của trang Điều hành dùng số của đúng các khung nhìn đã khai', () => {
  for (const chart of BOARD_CHARTS) {
    assert.deepEqual(viewsUsedBy(block(`board-${chart.id}`)), [...chart.views].sort(), `biểu đồ ${chart.id}`)
  }
  // bộ lần theo tên thật sự lần qua nhiều tầng: biểu đồ trạng thái → byStatus → incoming → counts
  assert.ok(closure(new Set(['statusChart'])).has('counts'))
  assert.ok(!closure(new Set(['outgoingChart'])).has('counts'))
})

test('đối chiếu biểu đồ → khung nhìn chỉ tính mã: khối thôi đọc dữ liệu thì không còn khung nhìn nào', () => {
  // data-testid="board-departments", chart="departments", t('board.processing') trùng tên ref departments,
  // processing — chữ tĩnh của từng khối (bỏ hết {{ … }} và thuộc tính động) không được dẫn tới khung nhìn nào
  for (const chart of BOARD_CHARTS) {
    const html = block(`board-${chart.id}`)
    const staticOnly = html.replace(INTERPOLATION, '').replace(BOUND_ATTRIBUTE, '')
    assert.ok(/\w+="[^"]*"/.test(staticOnly), `khối ${chart.id} còn thuộc tính tĩnh để thử`)
    assert.deepEqual(viewsUsedBy(staticOnly), [], `chữ tĩnh của khối ${chart.id}`)
  }
  // khối phòng ban giả: tên ref chỉ nằm trong chuỗi, thuộc tính tĩnh, khóa i18n → rỗng; dùng thật trong mã → có
  const fake = (code: string) => `<section data-testid="board-departments"><h2>{{ t('board.processing') }}</h2>
    <SourceLink chart="outgoing" /><EChart :label="'departments' + \`counts \${'processing'}\`" />${code}</section>`
  assert.deepEqual(viewsUsedBy(fake('')), [])
  assert.deepEqual(viewsUsedBy(fake('<p v-if="!departments.length" />')), ['office.v_overdue_by_department'])
  assert.deepEqual(viewsUsedBy(fake("<b>{{ `${t('x')}: ${processing.length}` }}</b>")), ['office.v_processing_time'])
  assert.deepEqual(viewsUsedBy(fake('<i :title="departmentName(departments[0]!)" />')),
    ['office.v_overdue_by_department'])
})

test('mỗi biểu đồ có đúng một nút "Nguồn số liệu" trỏ tới biểu đồ đã khai', () => {
  const links = [...template.matchAll(/<SourceLink chart="(\w+)"/g)].map((m) => m[1]!).sort()
  assert.deepEqual(links, BOARD_CHARTS.map((c) => c.id).sort())
  assert.match(sourceLink, /path: '\/pha-he', query: \{ 'bieu-do': chart \}/)
  assert.ok(isBoardChart('processing') && !isBoardChart('khac') && !isBoardChart(['processing']))
})

test('menu Phả hệ chỉ cho lãnh đạo đơn vị, như Điều hành', () => {
  assert.match(menu, /if \(role === 'director'\) \{\s*items\.push\(\{ to: '\/pha-he'/)
  assert.match(page, /const allowed = computed\(\(\) => claims\.value\?\.role === 'director'\)/)
})

test('loại đồ thị graph của ECharts chỉ trang Phả hệ nạp, trang Điều hành không tải thêm', () => {
  assert.match(page, /^import \{ GraphChart \} from 'echarts\/charts'$/m)
  assert.match(page, /^use\(\[GraphChart\]\)$/m)
  assert.doesNotMatch(echart, /GraphChart/)
  assert.doesNotMatch(board, /GraphChart/)
})

// --- Đồ thị ----------------------------------------------------------------------------------------------------

const edge = (report: string, source: string, kind = 'table', consumer = report, depth = 1): CatalogEdge =>
  ({ report, consumer, source, source_kind: kind, depth })
// Đúng các cạnh của bốn khung nhìn Điều hành mà office.report_lineage trả trên CSDL thật (db/tests), thêm một khung
// nhìn chưa có biểu đồ
const CATALOG: CatalogEdge[] = [
  edge('office.v_document_counts', 'office.documents'),
  edge('office.v_overdue_by_department', 'core.users'),
  edge('office.v_overdue_by_department', 'office.assignments'),
  edge('office.v_overdue_by_department', 'office.departments'),
  edge('office.v_overdue_by_department', 'office.documents'),
  edge('office.v_processing_time', 'office.archived_document_facts'),
  edge('office.v_processing_time', 'office.document_events'),
  edge('office.v_processing_time', 'office.documents'),
  edge('office.v_outgoing_by_month', 'office.documents'),
  edge('office.v_overdue_rate', 'office.documents'),
]
const T = 'c300d5bb-028f-44cc-ba10-7b5277a4225d'
const COLD = `s3://moc-cold/cold/${T}/case/7f1e6c1a-0000-4000-8000-000000000001/`
const H = (c: string) => c.repeat(64)
const PG = (table: string) => `postgres://postgres:5432/moc.${table}`
const RUN = '5b0c2c4e-1111-4000-8000-000000000001'
const step = (name: string, inputs: string[], outputs: string[], extra: Partial<LineageEvent> = {}): LineageEvent => ({
  run_id: `${name}-run`, parent_run_id: RUN, job: `moc.case_file.archive.${name}`, event_type: 'COMPLETE',
  event_time: '2026-10-24T03:00:00Z', inputs, outputs, quality_ok: null, ...extra,
})
const PARQUET = ['documents', 'assignments', 'events'].map((n, i) => `${COLD}${n}-${H(String(i + 1))}.parquet`)
const MANIFEST = `${COLD}manifest-${H('a')}.json`
const ARCHIVE: LineageEvent[] = [
  { ...step('x', [PG('office.documents')], []), run_id: RUN, parent_run_id: null, job: 'moc.case_file.archive',
    event_type: 'START', event: { eventType: 'START' } },
  step('files', [`s3://moc-files/tenant/${T}/2026/10/f1`, `s3://moc-files/tenant/${T}/2026/10/f2`],
    [`${COLD}files/${H('b')}`, `${COLD}files/${H('c')}`]),
  step('tables', [PG('office.documents'), PG('office.assignments'), PG('office.document_events')], PARQUET, {
    quality_ok: true,
    event: { outputs: PARQUET.map((p, i) => ({ namespace: 's3://moc-cold', name: p.slice('s3://moc-cold/'.length),
      outputFacets: { outputStatistics: { rowCount: [2, 1, 3][i] } } })) },
  }),
  step('manifest', [...PARQUET, `${COLD}files/${H('b')}`, `${COLD}files/${H('c')}`], [MANIFEST]),
  step('commit', [MANIFEST], ['office.case_files', 'office.documents', 'office.document_events',
    'office.document_files', 'core.files', 'core.audit_log', 'office.archived_document_facts'].map(PG)),
  { ...step('y', [], [MANIFEST]), run_id: RUN, parent_run_id: null, job: 'moc.case_file.archive',
    event: { eventType: 'COMPLETE' } },
]
const ids = (g: LineageGraph, kind?: string) => g.nodes.filter((n) => !kind || n.kind === kind).map((n) => n.id).sort()
const has = (g: LineageGraph, source: string, target: string, kind?: string) =>
  g.edges.some((e) => e.source === source && e.target === target && (!kind || e.kind === kind))

test('tên dataset OpenLineage → nút: bảng theo tên catalog, tệp gộp, băm bỏ khỏi nhãn', () => {
  assert.deepEqual(datasetNode(PG('office.documents')),
    { id: 'office.documents', kind: 'table', label: 'office.documents' })
  assert.deepEqual(datasetNode(`s3://moc-files/tenant/${T}/2026/10/f1`),
    { id: 's3://moc-files/tenant/', kind: 'object', label: 'moc-files/tenant/' })
  assert.deepEqual(datasetNode(`${COLD}files/${H('b')}`), { id: `${COLD}files/`, kind: 'object', label: 'files/' })
  assert.deepEqual(datasetNode(PARQUET[0]!), { id: PARQUET[0], kind: 'object', label: 'documents.parquet' })
  assert.equal(datasetNode(MANIFEST).label, 'manifest.json')
  assert.equal(datasetNode('kafka://x/y').id, 'kafka://x/y')
})

test('đồ thị đầy đủ: biểu đồ ← khung nhìn ← bảng, và lượt nộp lưu qua từng bước', () => {
  const g = lineageGraph(BOARD_CHARTS, CATALOG, ARCHIVE)
  assert.deepEqual(ids(g, 'chart'), BOARD_CHARTS.map((c) => chartNode(c.id)).sort())
  // khung nhìn chưa có biểu đồ (v_overdue_rate) không lên đồ thị
  assert.deepEqual(ids(g, 'view'), ['office.v_document_counts', 'office.v_outgoing_by_month',
    'office.v_overdue_by_department', 'office.v_processing_time'])
  assert.deepEqual(ids(g, 'table'), ['core.users', 'office.archived_document_facts', 'office.assignments',
    'office.departments', 'office.document_events', 'office.documents'])
  assert.deepEqual(ids(g, 'job'), ['job:files', 'job:manifest', 'job:tables'])
  assert.ok(has(g, 'office.v_processing_time', chartNode('processing'), 'read'))
  assert.ok(has(g, 'office.v_processing_time', chartNode('kpis')))
  assert.ok(has(g, 'office.v_document_counts', chartNode('kpis')))
  assert.ok(has(g, 'office.document_events', 'office.v_processing_time', 'read'))
  assert.ok(has(g, 'office.documents', 'job:tables', 'archive') && has(g, 'job:tables', PARQUET[2]!, 'archive'))
  assert.ok(has(g, PARQUET[0]!, 'job:manifest') && has(g, 'job:manifest', MANIFEST))
  // tệp gộp một nút mỗi chỗ, có số đối tượng; Parquet có số dòng đã kiểm
  const node = (id: string) => g.nodes.find((n) => n.id === id)!
  assert.equal(node('s3://moc-files/tenant/').count, 2)
  assert.equal(node(`${COLD}files/`).count, 2)
  assert.deepEqual(PARQUET.map((p) => node(p).rows), [2, 1, 3])
  assert.ok(g.nodes.filter((n) => n.kind !== 'object').every((n) => n.count === undefined && n.rows === undefined))
  // commit chỉ nối tới bảng đã có trên đồ thị; bảng chỉ commit ghi (case_files, audit_log…) không lên
  assert.deepEqual(g.edges.filter((e) => e.kind === 'commit').map((e) => e.target).sort(),
    ['office.archived_document_facts', 'office.document_events', 'office.documents'])
  assert.ok(!g.nodes.some((n) => n.id === 'core.audit_log' || n.id === 'office.case_files'))
  // sự kiện của run cha (START, COMPLETE) không thành cạnh
  assert.equal(g.nodes.length, 5 + 4 + 6 + 3 + 6)
  // chưa có lượt nộp lưu: chỉ còn phần báo cáo
  const reportOnly = lineageGraph(BOARD_CHARTS, CATALOG)
  assert.equal(reportOnly.nodes.length, 5 + 4 + 6)
  assert.ok(reportOnly.edges.every((e) => e.kind === 'read'))
})

test('view đọc view: đi tiếp tới bảng, cạnh nối đúng tầng', () => {
  const catalog = [
    edge('office.v_x', 'office.issued_documents', 'view'),
    edge('office.v_x', 'office.documents', 'table', 'office.issued_documents', 2),
    edge('office.v_x', 'office.registers', 'table', 'office.issued_documents', 2),
  ]
  const g = lineageGraph([{ id: 'status', label: 'board.byStatus', views: ['office.v_x'] }], catalog)
  assert.ok(has(g, 'office.issued_documents', 'office.v_x') && has(g, 'office.documents', 'office.issued_documents'))
  assert.deepEqual(ids(g, 'view'), ['office.issued_documents', 'office.v_x'])
  const at = new Map(lineageLayout(g).map((p) => [p.id, p.layer]))
  assert.deepEqual([at.get('office.documents'), at.get('office.issued_documents'), at.get('office.v_x'),
    at.get(chartNode('status'))], [0, 1, 2, 3])
})

test('lọc theo một biểu đồ: chỉ phần dẫn tới nó, bảng nộp lưu ghi vào kèm manifest', () => {
  const g = lineageGraph(BOARD_CHARTS, CATALOG, ARCHIVE)
  const p = lineageUpstream(g, chartNode('processing'))
  assert.deepEqual(ids(p), [MANIFEST, chartNode('processing'), 'office.archived_document_facts',
    'office.document_events', 'office.documents', 'office.v_processing_time'].sort())
  assert.equal(p.edges.filter((e) => e.kind === 'read').length, 4)
  assert.ok(has(p, MANIFEST, 'office.archived_document_facts', 'commit'))
  assert.ok(p.edges.every((e) => e.kind !== 'archive'))
  const d = lineageUpstream(g, chartNode('departments'))
  assert.deepEqual(ids(d, 'table'), ['core.users', 'office.assignments', 'office.departments', 'office.documents'])
  assert.ok(!ids(d).includes('office.v_processing_time'))
  // khối thẻ đọc hai khung nhìn
  assert.deepEqual(ids(lineageUpstream(g, chartNode('kpis')), 'view'), ['office.v_document_counts',
    'office.v_processing_time'])
})

test('xếp tầng: nguồn bên trái, dữ liệu đi sang phải; phần báo cáo ở dải trên, phần chỉ của nộp lưu ở dải dưới', () => {
  const g = lineageGraph(BOARD_CHARTS, CATALOG, ARCHIVE)
  const placed = lineageLayout(g)
  assert.equal(placed.length, g.nodes.length)
  const at = new Map(placed.map((p) => [p.id, p]))
  for (const e of g.edges.filter((x) => x.kind !== 'commit')) {
    assert.ok(at.get(e.source)!.layer < at.get(e.target)!.layer, `${e.source} → ${e.target}`)
  }
  assert.equal(at.get('office.documents')!.layer, 0)
  assert.equal(at.get('office.v_processing_time')!.layer, 1)
  assert.equal(at.get(chartNode('status'))!.layer, 2)
  assert.equal(at.get(MANIFEST)!.layer, 4)
  assert.equal(new Set(placed.map((p) => `${p.layer}/${p.row}`)).size, placed.length)
  // dải trên: 6 bảng là cột đông nhất (hàng 0–5); dải dưới bắt đầu sau nửa hàng
  const report = new Set(ids(lineageUpstream(g, chartNode('kpis'))).concat(...BOARD_CHARTS.map((c) =>
    ids(lineageUpstream(g, chartNode(c.id))))).filter((id) => !id.startsWith('s3://')))
  for (const p of placed) {
    if (report.has(p.id)) assert.ok(p.row >= 0 && p.row <= 5, `${p.id} ở hàng ${p.row}`)
    else assert.ok(p.row >= 6.5, `${p.id} ở hàng ${p.row}`)
  }
  assert.deepEqual(placed.filter((p) => p.layer === 0).map((p) => p.row), [0, 1, 2, 3, 4, 5, 8])
  // dải dưới cao 4 hàng (3 Parquet + tệp ở cột 2), bắt đầu ở 6,5; bucket nóng một mình canh giữa dải
  assert.deepEqual(placed.filter((p) => p.layer === 2 && !report.has(p.id)).map((p) => p.row), [6.5, 7.5, 8.5, 9.5])
  // cột ít nút canh giữa trong dải: 4 khung nhìn ở hàng 1–4
  assert.deepEqual(placed.filter((p) => p.layer === 1 && report.has(p.id)).map((p) => p.row), [1, 2, 3, 4])
  // lọc theo biểu đồ (không có bước nộp lưu): manifest đứng trước bảng mà commit ghi vào, cùng dải
  const focus = lineageLayout(lineageUpstream(g, chartNode('processing')))
  const f = new Map(focus.map((p) => [p.id, p]))
  assert.ok(f.get(MANIFEST)!.layer < f.get('office.archived_document_facts')!.layer)
  assert.ok(f.get('office.v_processing_time')!.layer < f.get(chartNode('processing'))!.layer)
  assert.ok(focus.every((p) => p.row < 6))
  // có vòng (dữ liệu lạ) vẫn không treo
  const loop: LineageGraph = { nodes: [{ id: 'a', kind: 'view', label: 'a' }, { id: 'b', kind: 'view', label: 'b' }],
    edges: [{ source: 'a', target: 'b', kind: 'read' }, { source: 'b', target: 'a', kind: 'read' }] }
  assert.equal(lineageLayout(loop).length, 2)
})

test('xuất OpenLineage: JobEvent cho từng khung nhìn và biểu đồ, rồi nguyên văn RunEvent của lượt nộp lưu', () => {
  const now = new Date('2026-10-25T01:02:03Z')
  const nested = [...CATALOG, edge('office.v_x', 'office.issued_documents', 'view'),
    edge('office.v_x', 'office.documents', 'table', 'office.issued_documents', 2)]
  const lines = toOpenLineage(BOARD_CHARTS, nested, ARCHIVE, now).trimEnd().split('\n').map((l) => JSON.parse(l))
  const jobs = lines.filter((e) => String(e.schemaURL).endsWith('#/$defs/JobEvent'))
  assert.equal(jobs.length, 7 + BOARD_CHARTS.length)   // 6 khung nhìn (kể cả view lồng) + 5 biểu đồ
  const processing = jobs.find((e) => e.job.name === 'moc.view.office.v_processing_time')
  assert.deepEqual(processing.inputs.map((d: { name: string }) => d.name), ['moc.office.archived_document_facts',
    'moc.office.document_events', 'moc.office.documents'])
  assert.deepEqual(processing.outputs, [{ namespace: 'postgres://postgres:5432', name: 'moc.office.v_processing_time',
    facets: {} }])
  // view lồng: một JobEvent riêng, đầu vào là bảng nó đọc
  assert.deepEqual(jobs.find((e) => e.job.name === 'moc.view.office.issued_documents').inputs[0].name,
    'moc.office.documents')
  const kpis = jobs.find((e) => e.job.name === 'moc.office.dieu-hanh.kpis')
  assert.deepEqual(kpis.inputs.map((d: { name: string }) => d.name), ['moc.office.v_document_counts',
    'moc.office.v_processing_time'])
  for (const e of jobs) {
    assert.equal(e.eventTime, now.toISOString())
    assert.equal(e.job.namespace, 'moc')
    assert.ok(!('run' in e) && !('eventType' in e))
    assert.match(e.producer, /^https:\/\//)
  }
  // RunEvent của nộp lưu: đúng nguyên văn, theo thứ tự
  assert.deepEqual(lines.slice(jobs.length), ARCHIVE.filter((e) => e.event).map((e) => e.event))
})

// --- Chữ trên giao diện -----------------------------------------------------------------------------------------

test('mọi khóa i18n của trang Phả hệ, nút Nguồn số liệu có đủ tiếng Việt và tiếng Anh', () => {
  const keys = new Set([
    ...[...page.matchAll(/'((?:lineage|board|app)\.[\w.]+)'/g)].map((m) => m[1]!),
    ...[...sourceLink.matchAll(/'(lineage\.[\w.]+)'/g)].map((m) => m[1]!),
    ...BOARD_CHARTS.map((c) => c.label),
    ...['chart', 'view', 'table', 'job', 'object'].map((k) => `lineage.kind.${k}`),
    ...['read', 'archive', 'commit'].map((k) => `lineage.edge.${k}`),
    ...['files', 'tables', 'manifest', 'commit'].map((k) => `lineage.steps.${k}`),
    ...['table', 'partitioned_table', 'view', 'materialized_view', 'foreign_table']
      .map((k) => `lineage.sourceKind.${k}`),
  ])
  assert.ok(keys.size > 40, `chỉ thấy ${keys.size} khóa`)
  for (const key of keys) {
    assert.ok(lookup(vi, key), `vi thiếu ${key}`)
    assert.ok(lookup(en, key), `en thiếu ${key}`)
  }
  assert.deepEqual(keysOf(vi.lineage as Messages).sort(), keysOf(en.lineage as Messages).sort())
})
