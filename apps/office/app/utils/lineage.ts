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

// Phả hệ số liệu trên trang Phả hệ (F3.9, F3.11): biểu đồ của trang Điều hành ← khung nhìn báo cáo ← bảng, và bảng →
// Parquet → gói lưu trữ trong bucket lạnh của lượt nộp lưu gần nhất.
// - Biểu đồ → khung nhìn: khai ở BOARD_CHARTS, một chỗ duy nhất; tests/lineage.test.ts đối chiếu với truy vấn và mã
//   thật của pages/dieu-hanh.vue (biểu đồ nào dùng số của khung nhìn nào).
// - Khung nhìn → bảng: không khai ở đây — office.report_lineage tính từ catalog PostgreSQL lúc truy vấn (migration
//   1792281602900), kể cả view đọc view.
// - Nộp lưu: sự kiện OpenLineage trong core.lineage_events (svc_files.lineage), chỉ của đơn vị mình.

export type BoardChart = 'kpis' | 'status' | 'departments' | 'processing' | 'outgoing'

export interface BoardChartSource {
  id: BoardChart
  label: string     // khóa i18n của tiêu đề
  views: string[]   // schema.tên, đúng như trong catalog
}

// Thứ tự như trên trang Điều hành
export const BOARD_CHARTS: BoardChartSource[] = [
  { id: 'kpis', label: 'lineage.kpis', views: ['office.v_document_counts', 'office.v_processing_time'] },
  { id: 'status', label: 'board.byStatus', views: ['office.v_document_counts'] },
  { id: 'departments', label: 'board.byDepartment', views: ['office.v_overdue_by_department'] },
  { id: 'processing', label: 'board.processing', views: ['office.v_processing_time'] },
  { id: 'outgoing', label: 'board.outgoing', views: ['office.v_outgoing_by_month'] },
]

export function isBoardChart(value: unknown): value is BoardChart {
  return BOARD_CHARTS.some((c) => c.id === value)
}

// Một cạnh của office.report_lineage: consumer đọc source; report là khung nhìn báo cáo gốc, depth 1 là đọc trực tiếp
export interface CatalogEdge {
  report: string
  consumer: string
  source: string
  source_kind: string   // table, view, materialized_view, partitioned_table, foreign_table
  depth: number
}

// Một dòng core.lineage_events (event: nguyên văn sự kiện OpenLineage)
export interface LineageEvent {
  run_id: string
  parent_run_id: string | null
  job: string
  event_type: string
  event_time: string
  inputs: string[]
  outputs: string[]
  quality_ok: boolean | null
  event?: Record<string, unknown>
}

export type NodeKind = 'chart' | 'view' | 'table' | 'job' | 'object'   // job: một bước của lượt nộp lưu
export type EdgeKind = 'read' | 'archive' | 'commit'

export interface LineageNode {
  id: string
  kind: NodeKind
  label: string    // biểu đồ, bước nộp lưu: khóa i18n; còn lại: tên
  count?: number   // nút gộp nhiều đối tượng (tệp của hồ sơ): số đối tượng
  rows?: number    // bảng Parquet: số dòng đã kiểm (facet outputStatistics)
}

export interface LineageEdge {
  source: string
  target: string
  kind: EdgeKind
}

export interface LineageGraph {
  nodes: LineageNode[]
  edges: LineageEdge[]
}

export const ARCHIVE_JOB = 'moc.case_file.archive'

// Cùng quy ước tên dataset với svc_files.lineage: bảng là postgres://postgres:5432 + moc.<schema>.<bảng>
export const PG_NAMESPACE = 'postgres://postgres:5432'
const PG_DATABASE = 'moc'

export function chartNode(id: BoardChart): string {
  return `chart:${id}`
}

/** Tên dataset OpenLineage → nút trên đồ thị. Bảng mang tên như catalog (schema.tên) để nối với phả hệ báo cáo; tệp
 * của hồ sơ (…/files/<sha256>) và tệp trong bucket nóng gộp mỗi chỗ một nút; nhãn của đối tượng chỉ còn tên tệp, bỏ
 * băm (id giữ nguyên tên dataset, có bucket và đường dẫn). */
export function datasetNode(name: string): Omit<LineageNode, 'count' | 'rows'> {
  const pg = /^postgres:\/\/[^/]+\/[^.]+\.(.+)$/.exec(name)
  if (pg) return { id: pg[1]!, kind: 'table', label: pg[1]! }
  const s3 = /^s3:\/\/([^/]+)\/(.*)$/.exec(name)
  if (!s3) return { id: name, kind: 'object', label: name }
  const [, bucket, key] = s3 as unknown as [string, string, string]
  if (key.startsWith('tenant/')) return { id: `s3://${bucket}/tenant/`, kind: 'object', label: `${bucket}/tenant/` }
  const dir = key.slice(0, key.lastIndexOf('/') + 1)
  if (dir.endsWith('/files/')) return { id: `s3://${bucket}/${dir}`, kind: 'object', label: 'files/' }
  return { id: name, kind: 'object', label: key.slice(dir.length).replace(/-[0-9a-f]{64}(?=\.)/, '') }
}

function rowCounts(events: LineageEvent[]): Map<string, number> {
  const rows = new Map<string, number>()
  for (const e of events) {
    const outputs = (e.event?.outputs ?? []) as Array<{ namespace: string; name: string; outputFacets?: {
      outputStatistics?: { rowCount?: number } } }>
    for (const o of outputs) {
      const n = o.outputFacets?.outputStatistics?.rowCount
      if (typeof n === 'number') rows.set(`${o.namespace}/${o.name}`, n)
    }
  }
  return rows
}

/** Đồ thị đầy đủ: bảng → khung nhìn → biểu đồ (catalog), và các bước con của một lượt nộp lưu như OpenLineage vẽ:
 * dataset → bước (files, tables, manifest) → dataset. Bước commit ghi ngược vào CSDL: cạnh nét đứt manifest → bảng, chỉ
 * tới bảng đã có trên đồ thị (không kéo thêm bảng không liên quan tới báo cáo). Hướng cạnh là hướng dữ liệu chảy. */
export function lineageGraph(charts: BoardChartSource[], catalog: CatalogEdge[], archive: LineageEvent[] = []):
  LineageGraph {
  const nodes = new Map<string, LineageNode>()
  const edges = new Map<string, LineageEdge>()
  const add = (node: LineageNode) => { if (!nodes.has(node.id)) nodes.set(node.id, node) }
  const link = (source: string, target: string, kind: EdgeKind) => {
    if (source !== target) edges.set(`${source}→${target}`, { source, target, kind })
  }
  const reach = new Set<string>()   // khung nhìn có biểu đồ dùng, và mọi thứ chúng đọc
  for (const c of charts) for (const v of c.views) reach.add(v)
  let grew = true
  while (grew) {
    grew = false
    for (const e of catalog) {
      if (reach.has(e.consumer) && !reach.has(e.source)) { reach.add(e.source); grew = true }
    }
  }
  for (const c of charts) {
    add({ id: chartNode(c.id), kind: 'chart', label: c.label })
    for (const v of c.views) {
      add({ id: v, kind: 'view', label: v })
      link(v, chartNode(c.id), 'read')
    }
  }
  for (const e of catalog) {
    if (!reach.has(e.consumer)) continue
    add({ id: e.consumer, kind: 'view', label: e.consumer })
    add({ id: e.source, kind: e.source_kind === 'table' || e.source_kind === 'partitioned_table' ||
      e.source_kind === 'foreign_table' ? 'table' : 'view', label: e.source })
    link(e.source, e.consumer, 'read')
  }

  const steps = archive.filter((e) => e.job.startsWith(`${ARCHIVE_JOB}.`) && e.event_type === 'COMPLETE')
  const rows = rowCounts(steps)
  const members = new Map<string, Set<string>>()
  const place = (name: string) => {
    const n = datasetNode(name)
    add({ ...n })
    const node = nodes.get(n.id)!
    if (rows.has(name)) node.rows = rows.get(name)
    if (n.kind === 'object' && n.id !== name) {
      const set = members.get(n.id) ?? new Set<string>()
      set.add(name)
      members.set(n.id, set)
    }
    return n.id
  }
  const commits = steps.filter((e) => e.job.endsWith('.commit'))
  for (const e of steps.filter((s) => !s.job.endsWith('.commit'))) {
    const step = e.job.slice(ARCHIVE_JOB.length + 1)
    add({ id: `job:${step}`, kind: 'job', label: `lineage.steps.${step}` })
    for (const i of e.inputs.map(place)) link(i, `job:${step}`, 'archive')
    for (const o of e.outputs.map(place)) link(`job:${step}`, o, 'archive')
  }
  for (const e of commits) {
    const ins = e.inputs.map((name) => datasetNode(name).id).filter((id) => nodes.has(id))
    for (const o of e.outputs.map((name) => datasetNode(name).id).filter((id) => nodes.has(id))) {
      for (const i of ins) link(i, o, 'commit')
    }
  }
  for (const [id, set] of members) nodes.get(id)!.count = set.size
  return { nodes: [...nodes.values()], edges: [...edges.values()] }
}

/** Phần đồ thị dẫn tới một biểu đồ: đi ngược theo cạnh đọc (khung nhìn, bảng, view lồng); bảng nào được bước commit
 * của nộp lưu ghi vào thì giữ thêm cạnh đó và manifest — một bước, không kéo cả gói lưu trữ vào. */
export function lineageUpstream(graph: LineageGraph, target: string): LineageGraph {
  const keep = new Set([target])
  const stack = [target]
  while (stack.length) {
    const id = stack.pop()!
    for (const e of graph.edges) {
      if (e.target === id && e.kind === 'read' && !keep.has(e.source)) { keep.add(e.source); stack.push(e.source) }
    }
  }
  const reads = graph.edges.filter((e) => e.kind === 'read' && keep.has(e.target))
  const commits = graph.edges.filter((e) => e.kind === 'commit' && keep.has(e.target))
  for (const e of commits) keep.add(e.source)
  return { nodes: graph.nodes.filter((n) => keep.has(n.id)), edges: [...reads, ...commits] }
}

export interface Placed {
  id: string
  layer: number   // cột, từ trái (nguồn) sang phải (biểu đồ, gói lưu trữ)
  row: number     // hàng, từ trên xuống; có thể lẻ nửa hàng (cột canh giữa trong dải của nó)
}

const KIND_ORDER: Record<NodeKind, number> = { chart: 0, view: 1, table: 2, job: 3, object: 4 }

/** Xếp tầng: cột = đường dài nhất từ nguồn. Hai dải: trên là mọi nút dẫn tới một biểu đồ (bảng → khung nhìn → biểu đồ),
 * dưới là phần chỉ của nộp lưu; trong mỗi cột, mỗi dải sắp theo trọng tâm hàng của hàng xóm (quét trái → phải, phải →
 * trái, trái → phải cho ít cạnh cắt nhau) rồi canh giữa trong dải. Cạnh commit khép vòng bảng → Parquet → manifest →
 * bảng nên bị bỏ khi đồ thị có các bước nộp lưu; đồ thị lọc theo một biểu đồ thì không có vòng, manifest đứng trước
 * bảng nó ghi vào. */
export function lineageLayout(graph: LineageGraph): Placed[] {
  const archived = graph.edges.some((e) => e.kind === 'archive')
  const flow = graph.edges.filter((e) => e.kind !== 'commit' || !archived)
  const preds = new Map<string, string[]>()
  const succs = new Map<string, string[]>()
  for (const e of flow) {
    preds.set(e.target, [...(preds.get(e.target) ?? []), e.source])
    succs.set(e.source, [...(succs.get(e.source) ?? []), e.target])
  }
  const layer = new Map<string, number>()
  const depth = (id: string, path: Set<string>): number => {
    if (layer.has(id)) return layer.get(id)!
    if (path.has(id)) return 0   // không có vòng khi đã bỏ cạnh commit; chặn cho chắc
    path.add(id)
    const ps = preds.get(id) ?? []
    const d = ps.length ? 1 + Math.max(...ps.map((p) => depth(p, path))) : 0
    path.delete(id)
    layer.set(id, d)
    return d
  }
  for (const n of graph.nodes) depth(n.id, new Set())
  const last = Math.max(0, ...layer.values())
  // dải 0: nút dẫn tới một biểu đồ (đi ngược từ các biểu đồ); dải 1: còn lại
  const band = new Map(graph.nodes.map((n) => [n.id, 1]))
  const stack = graph.nodes.filter((n) => n.kind === 'chart').map((n) => n.id)
  while (stack.length) {
    const id = stack.pop()!
    if (band.get(id) === 0) continue
    band.set(id, 0)
    stack.push(...(preds.get(id) ?? []))
  }

  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  const columns: string[][] = Array.from({ length: last + 1 }, () => [])
  for (const n of [...graph.nodes].sort((a, b) => band.get(a.id)! - band.get(b.id)! ||
    KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || a.label.localeCompare(b.label))) columns[layer.get(n.id)!]!.push(n.id)
  const position = new Map<string, number>()
  const remember = () => columns.forEach((col) => col.forEach((id, i) => position.set(id, (i + 0.5) / col.length)))
  remember()
  const sweep = (col: string[], neighbours: Map<string, string[]>) => {
    const key = new Map(col.map((id) => {
      const ns = (neighbours.get(id) ?? []).filter((n) => position.has(n))
      return [id, ns.length ? ns.reduce((s, n) => s + position.get(n)!, 0) / ns.length : position.get(id)!]
    }))
    col.sort((a, b) => band.get(a)! - band.get(b)! || key.get(a)! - key.get(b)! ||
      byId.get(a)!.label.localeCompare(byId.get(b)!.label))
    remember()
  }
  for (let l = 1; l <= last; l++) sweep(columns[l]!, preds)
  for (let l = last - 1; l >= 0; l--) sweep(columns[l]!, succs)
  for (let l = 1; l <= last; l++) sweep(columns[l]!, preds)
  // chiều cao mỗi dải = cột đông nhất trong dải; dải dưới cách dải trên nửa hàng
  const count = (col: string[], b: number) => col.filter((id) => band.get(id) === b).length
  const height = [0, 1].map((b) => Math.max(0, ...columns.map((col) => count(col, b))))
  const top = [0, height[0]! ? height[0]! + 0.5 : 0]
  return columns.flatMap((col, l) => [0, 1].flatMap((b) => {
    const ids = col.filter((id) => band.get(id) === b)
    return ids.map((id, i) => ({ id, layer: l, row: top[b]! + (height[b]! - ids.length) / 2 + i }))
  }))
}

const PRODUCER = 'https://github.com/HIT-Champion/Signet/tree/main/apps/office'
const JOB_EVENT = 'https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/JobEvent'

function pgDataset(name: string) {
  return { namespace: PG_NAMESPACE, name: `${PG_DATABASE}.${name}`, facets: {} }
}

/** Xuất phả hệ dạng OpenLineage, mỗi dòng một sự kiện (JSON Lines): phả hệ tĩnh — một JobEvent cho mỗi khung nhìn
 * (đọc các quan hệ catalog ghi nhận → ghi ra chính nó) và mỗi biểu đồ (đọc khung nhìn) — rồi nguyên văn các RunEvent
 * của lượt nộp lưu. Tên dataset theo cùng quy ước với svc_files.lineage nên hai phần nối được với nhau. */
export function toOpenLineage(charts: BoardChartSource[], catalog: CatalogEdge[], archive: LineageEvent[],
  now: Date): string {
  const eventTime = now.toISOString()
  const job = (name: string, inputs: string[], outputs: string[]) => ({
    eventTime, producer: PRODUCER, schemaURL: JOB_EVENT,
    job: { namespace: 'moc', name, facets: {} },
    inputs: inputs.map(pgDataset), outputs: outputs.map(pgDataset),
  })
  const reads = new Map<string, Set<string>>()
  for (const e of catalog) reads.set(e.consumer, (reads.get(e.consumer) ?? new Set()).add(e.source))
  const events: unknown[] = [...reads.keys()].sort().map((view) =>
    job(`moc.view.${view}`, [...reads.get(view)!].sort(), [view]))
  for (const c of charts) events.push(job(`moc.office.dieu-hanh.${c.id}`, c.views, []))
  for (const e of archive) if (e.event) events.push(e.event)
  return events.map((e) => JSON.stringify(e)).join('\n') + '\n'
}
