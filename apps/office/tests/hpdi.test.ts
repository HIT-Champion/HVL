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

// Tự chẩn đoán H-P-D-I (trang /tu-chan-doan, docs/tu-chan-doan.md): bộ câu qua JSON Schema, đủ bốn không gian đúng thứ
// tự, mỗi câu đúng 5 mức hai thứ tiếng; mọi liên kết "bước tiếp theo" trỏ trang có thật và chỉ dẫn người xem tới trang
// vai trò của họ mở được (đối chiếu điều kiện của menu); bộ mã câu, phiên bản bộ câu khớp điều CSDL kiểm (đọc thẳng
// migration 1792281603100); chấm điểm, lệch nền, nên làm trước, bước tiếp theo; tỷ trọng, hình dạng và cảnh báo "rác
// vào, rác ra" theo giáo trình DX-OS mục 2.4; bằng chứng đo được không bịa số khi chưa có dữ liệu; trang chỉ cho lãnh
// đạo, chỉ lãnh đạo đơn vị lưu; đủ khóa i18n.

import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'
import Ajv2020 from 'ajv/dist/2020.js'
import type { Role } from '../app/composables/useAuth.ts'
import type { HpdiEvidenceData, HpdiFramework, HpdiScores, HpdiShares } from '../app/utils/hpdi.ts'

const { HPDI_EVIDENCE, HPDI_KEYS, HPDI_QUALITY_LINK, HPDI_SHAPES, hpdiAccess, hpdiAnswered, hpdiCleanAnswers,
  hpdiComplete, hpdiEvidence, hpdiFocus, hpdiGaps, hpdiGigo, hpdiLinkOpen, hpdiNextSteps, hpdiQuestions,
  hpdiRadarValues, hpdiRowScores, hpdiSample, hpdiSaveInput, hpdiScores, hpdiShape, hpdiShares,
  hpdiText } = await import('../app/utils/hpdi.ts')
const { hasSpace } = await import('../../ca-nhan/public/para.js')

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const FRAMEWORK = JSON.parse(read('../app/data/tu-chan-doan.json')) as HpdiFramework
const SCHEMA = JSON.parse(read('../app/data/tu-chan-doan.schema.json'))
const MIGRATION = read('../../../db/migrations/default/1792281603100_maturity_assessments/up.sql')

type Messages = { [key: string]: string | Messages }
const load = (lang: string): Messages => JSON.parse(read(`../app/locales/${lang}.json`)) as Messages
const vi = load('vi')
const en = load('en')
function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}

const scores = (h: number | null, p: number | null, d: number | null, i: number | null): HpdiScores => ({ h, p, d, i })
// Trả lời mọi câu của một không gian cùng một mức
function all(levels: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {}
  for (const s of FRAMEWORK.spaces) for (const q of s.questions) out[q.id] = levels[s.key]!
  return out
}

// Trang của Văn phòng điện tử, như test "mọi trang sau đăng nhập có tên màn hình" (feedback.test.ts)
function officeRoutes(): Set<string> {
  const dir = new URL('../app/pages/', import.meta.url)
  return new Set((readdirSync(dir, { recursive: true }) as string[]).filter((f) => f.endsWith('.vue')).map((f) => {
    const path = f.replace(/\\/g, '/').replace(/\.vue$/, '').replace(/(^|\/)index$/, '').replace(/\[(\w+)\]/g, ':$1')
    return `/${path}`.replace(/\/$/, '') || '/'
  }))
}

// Thanh bên (layouts/default.vue): mỗi mục menu là `if (<điều kiện theo role>) items.push({ to: '…'` (hoặc khối
// `if (…) {` chỉ có lệnh push đó, vd /ho-so, /pha-he) hoặc không điều kiện. Chạy đúng điều kiện đó với từng vai trò
// để biết vai trò nào mở được trang nào — trang đích chặn vai trò khác theo cùng điều kiện (Hasura từ chối, trang báo
// không có quyền, hoặc chuyển hướng như /van-ban-den/tiep-nhan).
const ROLES = SCHEMA.$defs.link.properties.roles.items.enum as Role[]
function menu(): Map<string, (role: Role) => boolean> {
  const out = new Map<string, (role: Role) => boolean>()
  const layout = read('../app/layouts/default.vue')
  for (const m of layout.matchAll(/^\s*(?:if \((.+?)\) \{?\s*)?items\.push\(\{\s*to: '([^']+)'/gm)) {
    out.set(m[2]!, new Function('role', `return Boolean(${m[1] ?? 'true'})`) as (role: Role) => boolean)
  }
  return out
}
// Không gian cá nhân /ca-nhan/ là ứng dụng khác: điều kiện vai trò của nó (para.js)
function opens(nav: Map<string, (role: Role) => boolean>, to: string, role: Role): boolean {
  return to === '/ca-nhan/' ? hasSpace(role) : nav.get(to)!(role)
}

test('bộ câu qua JSON Schema (Ajv, strict)', () => {
  const validate = new Ajv2020({ allErrors: true, strict: true }).compile(SCHEMA)
  assert.ok(validate(FRAMEWORK), JSON.stringify(validate.errors))
  // schema bắt được dữ liệu sai, không đạt suông
  const broken = structuredClone(FRAMEWORK)
  broken.spaces[0]!.questions[0]!.levels.pop()
  broken.spaces[1]!.questions[0]!.links[0]!.to = 'https://example.org'
  broken.spaces[2]!.questions[0]!.links[0]!.roles = ['admin' as Role]
  assert.equal(validate(broken), false)
  assert.equal(validate.errors?.length, 3)
})

test('đủ bốn không gian theo thứ tự H, P, D, I; mỗi câu đúng 5 mức hai thứ tiếng, không mức nào trùng', () => {
  assert.deepEqual(FRAMEWORK.spaces.map((s) => s.key), [...HPDI_KEYS])
  const ids = hpdiQuestions(FRAMEWORK).map((q) => q.id)
  assert.equal(new Set(ids).size, ids.length)
  for (const s of FRAMEWORK.spaces) {
    assert.ok(s.questions.length >= 3, `${s.key}: ít hơn 3 câu`)
    s.questions.forEach((q, n) => {
      assert.equal(q.id, `${s.key}${n + 1}`, 'mã câu là chữ của không gian và số thứ tự')
      assert.equal(q.levels.length, 5, q.id)
      for (const lang of ['vi', 'en'] as const) {
        assert.equal(new Set(q.levels.map((l) => l[lang])).size, 5, `${q.id} ${lang}: hai mức trùng chữ`)
        for (const x of [q.title, q.text, q.next, ...q.levels]) assert.ok(x[lang].trim(), `${q.id} ${lang}: trống`)
      }
      assert.notEqual(q.levels[0]!.vi, q.levels[0]!.en, `${q.id}: chưa dịch`)
    })
  }
  assert.equal(hpdiText(FRAMEWORK.spaces[0]!.name, 'en'), 'Human')
  assert.equal(hpdiText(FRAMEWORK.spaces[0]!.name, 'vi'), 'Con người')
})

test('bước tiếp theo trỏ trang có thật: trang của Văn phòng điện tử hoặc /ca-nhan/ qua APISIX', () => {
  const routes = officeRoutes()
  const apisix = read('../../../platform/apisix/apisix.yaml')
  const used = new Set<string>()
  for (const q of hpdiQuestions(FRAMEWORK)) {
    for (const link of q.links) {
      used.add(link.to)
      if (link.to === '/ca-nhan/') {
        assert.match(apisix, /uris: \["\/ca-nhan", "\/ca-nhan\/\*"\]/)
        assert.ok(readdirSync(new URL('../../ca-nhan/public/', import.meta.url)).includes('index.html'))
      } else {
        assert.ok(routes.has(link.to), `${q.id}: ${link.to} không phải trang của Văn phòng điện tử`)
      }
    }
  }
  // dùng thật nhiều phân hệ, không trỏ hết về một trang
  assert.ok(used.size >= 8, `chỉ trỏ ${used.size} trang`)
  for (const to of ['/dieu-hanh', '/so-do', '/hoi-dap', '/so-kiem-toan', '/van-ban-den/tiep-nhan']) {
    assert.ok(used.has(to), to)
  }
})

test('bộ mã câu, phiên bản bộ câu khớp đúng điều CSDL kiểm (migration 1792281603100)', () => {
  // trigger đòi đủ, không thừa các mã câu của phiên bản: đổi câu trong JSON mà quên migration thì lưu không được
  const codes = MIGRATION.match(/when '([a-z0-9-]+)' then '\{([^}]+)\}'::text\[\]/)
  assert.ok(codes, 'không đọc được bộ mã câu trong migration')
  assert.equal(codes[1], FRAMEWORK.id)
  assert.deepEqual(codes[2]!.split(','), hpdiQuestions(FRAMEWORK).map((q) => q.id))
  assert.match(MIGRATION, new RegExp(`constraint maturity_framework check \\(framework in \\('${FRAMEWORK.id}'\\)\\)`))
  // điểm CSDL tính: trung bình, làm tròn 2 chữ số, như hpdiScores
  assert.match(MIGRATION, /round\(avg\(a\.value::text::int\) filter \(where left\(a\.key, 1\) = 'h'\), 2\)/)
})

test('điểm: trung bình các câu đã trả lời, 2 chữ số; chưa trả lời câu nào thì không có điểm', () => {
  assert.deepEqual(hpdiScores(FRAMEWORK, {}), scores(null, null, null, null))
  assert.deepEqual(hpdiScores(FRAMEWORK, { h1: 2, h2: 3, h3: 3, p1: 5, d2: 1 }), scores(2.67, 5, 1, null))
  assert.deepEqual(hpdiScores(FRAMEWORK, all({ h: 4, p: 3, d: 2, i: 1 })), scores(4, 3, 2, 1))
  assert.equal(hpdiAnswered(FRAMEWORK, { h1: 2, h2: 9, x1: 3 }), 1)
  assert.equal(hpdiComplete(FRAMEWORK, { h1: 2 }), false)
  assert.equal(hpdiComplete(FRAMEWORK, all({ h: 1, p: 1, d: 1, i: 1 })), true)
  assert.deepEqual(hpdiRadarValues(scores(2.67, null, 1, 5)), [2.67, 0, 1, 5])
})

test('làm sạch câu trả lời: bỏ mã lạ, mức ngoài 1–5, số lẻ, dữ liệu không phải đối tượng', () => {
  assert.deepEqual(hpdiCleanAnswers(FRAMEWORK, { h1: 3, h2: 0, h3: 6, p1: 2.5, p2: '4', z9: 1, d1: 5 }),
    { h1: 3, d1: 5 })
  for (const raw of [null, undefined, 'h1', [3, 4], 7]) assert.deepEqual(hpdiCleanAnswers(FRAMEWORK, raw), {})
})

test('lệch nền: không gian sau vượt không gian ngay trước từ 1 mức trở lên', () => {
  assert.deepEqual(hpdiGaps(scores(4, 3, 2, 1)), [])
  assert.deepEqual(hpdiGaps(scores(3, 2, 4, 1)), [{ from: 'p', to: 'd', diff: 2 }])
  assert.deepEqual(hpdiGaps(scores(2, 3, 3.67, 4.67)),
    [{ from: 'h', to: 'p', diff: 1 }, { from: 'd', to: 'i', diff: 1 }])
  assert.deepEqual(hpdiGaps(scores(2, 2.67, 3.33, 4)), [])                // chênh dưới một mức
  assert.deepEqual(hpdiGaps(scores(1, null, 5, 5)), [])                   // thiếu điểm thì không so
})

test('nên làm trước: điểm thấp nhất từ [H] tới trước chỗ lệch nền đầu tiên, bằng nhau lấy không gian trước', () => {
  assert.equal(hpdiFocus(scores(3, 2, 4, 1)), 'p')       // [D] vượt [P]: làm [P] trước, chưa tính [I]
  assert.equal(hpdiFocus(scores(4, 3, 2, 1)), 'i')       // không lệch: không gian thấp nhất
  assert.equal(hpdiFocus(scores(3, 3, 2, 2)), 'd')       // bằng nhau: không gian đứng trước
  assert.equal(hpdiFocus(scores(2, 2, 2, 2)), 'h')
  assert.equal(hpdiFocus(scores(1, 3, 3, 3)), 'h')
  assert.equal(hpdiFocus(scores(3, 3, 1, 4)), 'd')       // AI vượt dữ liệu: làm [D] trước
  assert.equal(hpdiFocus(scores(5, 5, 4, 5)), 'd')
  assert.equal(hpdiFocus(scores(5, 5, 5, 5)), null)
  assert.equal(hpdiFocus(scores(null, null, null, null)), null)
})

test('tỷ trọng theo giáo trình 2.4.2: mức 1 → 0 %, mức 5 → 30 %, [H] là phần dư; thiếu [P], [D], [I] thì không', () => {
  assert.deepEqual(hpdiShares(scores(1, 1, 1, 1)), { h: 100, p: 0, d: 0, i: 0 })
  // đủ mức 5 ra đúng Kim cương của giáo trình: [H] 10 %, ba trục kia 30 %
  assert.deepEqual(hpdiShares(scores(5, 5, 5, 5)), { h: 10, p: 30, d: 30, i: 30 })
  assert.deepEqual(hpdiShares(scores(2, 3, 2, 4)), { h: 55, p: 15, d: 7.5, i: 22.5 })
  // điểm không gian [H] không vào công thức: [H] của giáo trình là việc còn lại trên vai con người
  assert.deepEqual(hpdiShares(scores(5, 3, 3, 3)), hpdiShares(scores(1, 3, 3, 3)))
  assert.deepEqual(hpdiShares(scores(1, 2.67, 1, 1)), { h: 87.5, p: 12.5, d: 0, i: 0 })
  assert.equal(hpdiShares(scores(3, null, 3, 3)), null)
  assert.equal(hpdiShares(scores(null, 3, 3, 3))?.h, 55)
})

test('hình dạng theo giáo trình 2.4.3, luật đầu tiên khớp; ngưỡng đúng chỗ giáo trình ghi số', () => {
  const shape = (p: number, d: number, i: number) => hpdiShape(hpdiShares(scores(3, p, d, i))!)
  assert.equal(shape(5, 5, 5), 'diamond')
  assert.equal(shape(4, 4, 4), 'diamond')
  assert.equal(shape(1, 1, 4), 'illusion')        // AI khi chưa có móng quy trình
  assert.equal(shape(2, 3, 1), 'illusion')        // phân tích (BI) đi trước quy trình
  assert.equal(shape(4, 1, 1), 'kite')
  assert.equal(shape(1, 1, 1), 'spear')
  assert.equal(shape(3, 3, 3), 'transitional')
  assert.equal(shape(4, 3, 1), 'transitional')    // [D] đã nhích khỏi tâm nhưng chưa vượt [P]
  // ví dụ đối soát của giáo trình: P 10 %, D 0 %, I 0 % → H 90 %, Mức 1
  assert.equal(hpdiShape({ h: 90, p: 10, d: 0, i: 0 }), 'spear')
  const at = (p: number, d: number, i: number): HpdiShares => ({ h: 100 - p - d - i, p, d, i })
  assert.equal(hpdiShape(at(22.5, 22.5, 22.5)), 'diamond')
  assert.equal(hpdiShape(at(22.4, 22.5, 22.5)), 'transitional')
  assert.equal(hpdiShape(at(19.9, 20, 0)), 'illusion')
  assert.equal(hpdiShape(at(20, 20.1, 0)), 'transitional')   // [P] đã tới dải Cánh diều: không còn "suy giảm"
  assert.equal(hpdiShape(at(9.9, 9.9, 0)), 'spear')           // chưa trục nào "vươn dài" (một phần ba trục)
  assert.equal(hpdiShape(at(10, 10, 0)), 'spear')             // [D] bằng [P] không phải đi trước [P]; [H] 80 %
  assert.equal(hpdiShape(at(20, 9.9, 9.9)), 'kite')
  assert.equal(hpdiShape(at(20, 10, 0)), 'transitional')     // [D] tới một phần ba trục: không còn "triệt tiêu"
  assert.equal(hpdiShape(at(10, 5, 5)), 'spear')              // [H] 80 %
  assert.equal(hpdiShape(at(10, 5, 5.1)), 'transitional')
  assert.deepEqual([...new Set([[5, 5, 5], [1, 1, 4], [4, 1, 1], [1, 1, 1], [3, 3, 3]].map(([p, d, i]) =>
    shape(p!, d!, i!)))], HPDI_SHAPES)
})

test('rác vào, rác ra: [I] vượt [D] từ 1 mức, hoặc Ảo giác công nghệ; trỏ tới cờ chất lượng ở Phả hệ số liệu', () => {
  const gigo = (h: number, p: number, d: number, i: number) => {
    const sc = scores(h, p, d, i)
    const shares = hpdiShares(sc)
    return hpdiGigo(sc, shares ? hpdiShape(shares) : null)
  }
  assert.equal(gigo(4, 4, 2, 3), true)            // lệch nền D → I
  assert.equal(gigo(4, 4, 2.5, 3), false)
  assert.equal(gigo(3, 1, 3, 2), true)            // Ảo giác: [D] đi trước [P], dù [I] không vượt [D]
  assert.equal(gigo(3, 4, 1, 1), false)           // Cánh diều: chưa có [I] nào để cảnh báo
  assert.equal(gigo(3, 3, 3, 3), false)
  assert.equal(gigo(5, 5, 5, 5), false)
  assert.equal(hpdiGigo(scores(3, 3, 2, null), null), false)
  // liên kết: đúng điều kiện vai trò của mục /pha-he trên thanh bên; lãnh đạo phòng chỉ thấy tên trang
  const nav = menu()
  assert.deepEqual(HPDI_QUALITY_LINK.roles, ROLES.filter((r) => opens(nav, HPDI_QUALITY_LINK.to, r)))
  assert.equal(hpdiLinkOpen(HPDI_QUALITY_LINK, 'director'), true)
  assert.equal(hpdiLinkOpen(HPDI_QUALITY_LINK, 'manager'), false)
  assert.match(read('../app/pages/tu-chan-doan.vue'), /path: HPDI_QUALITY_LINK\.to, hash: '#chat-luong'/)
})

test('bước tiếp theo: câu có mức thấp nhất của mỗi không gian, bằng nhau lấy câu đầu, mức 5 thì thôi', () => {
  const steps = hpdiNextSteps(FRAMEWORK, { ...all({ h: 5, p: 3, d: 2, i: 4 }), p2: 1, d3: 1, i2: 2, i3: 2 })
  assert.deepEqual(steps.map((s) => [s.space, s.question.id, s.level]),
    [['p', 'p2', 1], ['d', 'd3', 1], ['i', 'i2', 2]])
  assert.ok(steps.every((s) => s.question.next.vi && s.question.links.length))
  assert.deepEqual(hpdiNextSteps(FRAMEWORK, {}), [])
})

test('lịch sử: cột numeric đọc được cả số và chuỗi', () => {
  const row = { id: 'x', created_at: '2026-10-25T01:00:00Z', framework: 'hpdi-1', answers: {}, note: null }
  assert.deepEqual(hpdiRowScores({ ...row, h: '2.67', p: 3, d: '1.00', i: 4.33 }), scores(2.67, 3, 1, 4.33))
})

const EMPTY: HpdiEvidenceData = { counts: [], assign: [], overdue: [], feedback: [], intake: [], suggestions: [],
  caseFiles: [] }

test('bằng chứng: chưa có dữ liệu thì không có chỉ số nào, mẫu số 0 không thành 0 %', () => {
  assert.deepEqual(hpdiEvidence(EMPTY), [])
  const zero: HpdiEvidenceData = {
    ...EMPTY,
    assign: [{ sample: false, month: null, assigned: 0, median_hours: null }],
    overdue: [{ sample: false, month: null, judged: 0, late: 0 }],
    feedback: [{ sample: false, screen: null, feedback: 0, rating_total: 0 }],
    intake: [{ suggested: 0, kept: 0 }],
    suggestions: [{ decided: 0, kept_unit: 0 }],
  }
  assert.deepEqual(hpdiEvidence(zero), [])
  assert.equal(hpdiSample(zero), false)
})

test('bằng chứng: tính đúng từ dòng của các view, văn bản hạn chế chỉ vào tổng, văn bản đã hủy không tính', () => {
  const data: HpdiEvidenceData = {
    counts: [
      { direction: 'in', restricted: false, status: 'cancelled', overdue: false, documents: 7 },
      { direction: 'out', restricted: false, status: 'cancelled', overdue: false, documents: 2 },
      { direction: 'in', restricted: false, status: 'in_progress', overdue: true, documents: 2 },
      { direction: 'in', restricted: false, status: 'in_progress', overdue: false, documents: 5 },
      { direction: 'in', restricted: false, status: 'archived', overdue: false, documents: 3 },
      { direction: 'out', restricted: false, status: 'archived', overdue: false, documents: 1 },
      { direction: 'out', restricted: false, status: 'issued', overdue: false, documents: 4 },
      { direction: 'in', restricted: true, status: null, overdue: null, documents: 6 },
    ],
    assign: [{ sample: true, month: '2026-10-01', assigned: 9, median_hours: 1 },
      { sample: true, month: null, assigned: 10, median_hours: 0.5 }],
    overdue: [{ sample: true, month: null, judged: 8, late: 2 }],
    feedback: [{ sample: true, screen: '/', feedback: 1, rating_total: 5 },
      { sample: true, screen: null, feedback: 4, rating_total: 14 }],
    intake: [{ suggested: 6, kept: 5 }, { suggested: 4, kept: 4 }],
    suggestions: [{ decided: 3, kept_unit: 2 }, { decided: 1, kept_unit: 1 }],
    caseFiles: [{ status: 'open' }, { status: 'archived' }, { status: 'closed' }, { status: 'archived' }],
  }
  const got = Object.fromEntries(hpdiEvidence(data).map((e) => [e.id, { space: e.space, ...e.values }]))
  assert.deepEqual(got, {
    feedback: { space: 'h', avg: 3.5, n: 4 },
    overdueNow: { space: 'p', n: 2 },
    overdueRate: { space: 'p', pct: 25, late: 2, n: 8 },
    timeToAssign: { space: 'p', hours: 0.5, n: 10 },
    documents: { space: 'd', n: 21, incoming: 16, outgoing: 5 },
    archivedDocuments: { space: 'd', n: 4 },
    caseFiles: { space: 'd', archived: 2, n: 4 },
    intakeKept: { space: 'i', pct: 90, kept: 9, n: 10 },
    suggestionKept: { space: 'i', pct: 75, kept: 3, n: 4 },
  })
  assert.equal(hpdiSample(data), true)
  // chỉ có văn bản đã hủy: không có chỉ số văn bản nào
  const cancelled = { direction: 'in', restricted: false, status: 'cancelled', overdue: false, documents: 3 }
  assert.deepEqual(hpdiEvidence({ ...EMPTY, counts: [cancelled] }), [])
  // thứ tự hiện trên trang theo HPDI_EVIDENCE, mỗi chỉ số đúng không gian khai ở đó
  const listed = HPDI_KEYS.flatMap((k) => HPDI_EVIDENCE[k].map((id) => [k, id]))
  assert.deepEqual(hpdiEvidence(data).map((e) => [e.space, e.id]), listed)
})

test('bằng chứng chỉ đọc các view đã có, không có số ký số (chưa có view cho lãnh đạo)', () => {
  const page = read('../app/pages/tu-chan-doan.vue')
  const query = page.match(/const EVIDENCE = `([^`]+)`/)?.[1] ?? ''
  const roots = [...query.matchAll(/^\s+(\w+)/gm)].map((m) => m[1])
  assert.deepEqual(roots, ['office_v_document_counts', 'office_v_time_to_assign', 'office_v_overdue_rate',
    'office_v_feedback_summary', 'office_v_intake_accuracy', 'office_v_assignment_suggestion_accuracy',
    'office_case_files'])
  assert.doesNotMatch(page, /signature|file_signatures|issued_documents/)
})

test('thanh bên, quyền trên trang: lãnh đạo đơn vị và lãnh đạo phòng mở, chỉ lãnh đạo đơn vị lưu', () => {
  const nav = menu()
  assert.ok(nav.size >= 10 && nav.has('/tu-chan-doan'), `chỉ đọc được ${nav.size} mục menu`)
  assert.deepEqual(ROLES, Object.keys(vi.role as Messages))
  for (const role of ROLES) assert.equal(hpdiAccess(role).open, nav.get('/tu-chan-doan')!(role), role)
  assert.deepEqual(ROLES.filter((r) => hpdiAccess(r).open), ['manager', 'director'])
  assert.deepEqual(ROLES.filter((r) => hpdiAccess(r).leader), ['director'])
  assert.deepEqual(hpdiAccess(null), { open: false, leader: false })
  // radar của ECharts được nạp (bản ECharts rút gọn chỉ vẽ loại biểu đồ đã đăng ký; test node không vẽ được)
  assert.match(read('../app/components/EChart.vue'), /use\(\[RadarChart, RadarComponent\]\)/)
})

test('bước tiếp theo chỉ dẫn người xem tới trang vai trò của họ mở được, đúng như menu', () => {
  const nav = menu()
  const viewers = ROLES.filter((r) => hpdiAccess(r).open)
  const links = hpdiQuestions(FRAMEWORK).flatMap((q) => q.links)
  for (const link of links) {
    assert.ok(link.to === '/ca-nhan/' || nav.has(link.to), `${link.to}: không có trong menu`)
    for (const role of viewers) {
      assert.equal(hpdiLinkOpen(link, role), opens(nav, link.to, role), `${role} → ${link.to}`)
    }
    // roles khai đúng điều kiện của mục menu, với mọi vai trò (trang hiện tên các vai trò này)
    if (link.roles) assert.deepEqual(link.roles, ROLES.filter((r) => opens(nav, link.to, r)), link.to)
  }
  const open = (role: Role) => [...new Set(links.filter((l) => hpdiLinkOpen(l, role)).map((l) => l.to))].sort()
  assert.deepEqual(open('manager'),
    ['/', '/ca-nhan/', '/gop-y', '/hoi-dap', '/tim-kiem', '/van-ban-den', '/van-ban-di'])
  assert.deepEqual(open('director'), ['/', '/ca-nhan/', '/dieu-hanh', '/gop-y', '/hoi-dap', '/so-dang-ky', '/so-do',
    '/so-kiem-toan', '/tim-kiem', '/van-ban-den', '/van-ban-di'])
  // tiếp nhận văn bản là việc của văn thư (trang chuyển vai trò khác về /van-ban-den): chỉ hiện tên, không dẫn tới
  assert.equal(nav.get('/van-ban-den/tiep-nhan')!('director'), false)
  assert.equal(hpdiLinkOpen(links[0]!, null), false)
})

test('lưu: gửi đúng ba cột được phép, câu trả lời lọc theo bộ câu, ghi chú gọt (trống thì null)', () => {
  const full = all({ h: 2, p: 3, d: 4, i: 5 })
  assert.deepEqual(hpdiSaveInput(FRAMEWORK, { ...full, x1: 3, h9: 2 }, '  Sau đợt triển khai \n'),
    { framework: 'hpdi-1', answers: full, note: 'Sau đợt triển khai' })
  assert.equal(hpdiSaveInput(FRAMEWORK, full, ' \n\t ').note, null)
  const meta = read('../../../db/metadata/databases/default/tables/office_maturity_assessments.yaml')
  const insert = /insert_permissions:\n {2}- role: director\n {4}permission:\n {6}columns: \[([^\]]+)\]/
  assert.deepEqual(meta.match(insert)?.[1]?.split(', '), Object.keys(hpdiSaveInput(FRAMEWORK, full, '')))
})

test('khóa i18n của trang có ở cả vi.json và en.json, kể cả khóa ghép theo mã chỉ số', () => {
  const page = read('../app/pages/tu-chan-doan.vue')
  let checked = 0
  for (const m of page.matchAll(/\bt\('([\w.-]+)'/g)) {
    assert.ok(lookup(vi, m[1]!) !== undefined, `vi thiếu ${m[1]}`)
    assert.ok(lookup(en, m[1]!) !== undefined, `en thiếu ${m[1]}`)
    checked++
  }
  assert.ok(checked > 40, `chỉ thấy ${checked} khóa`)
  assert.match(page, /t\(`hpdi\.evidence\.\$\{e\.id\}\.name`\)/)
  assert.match(page, /t\(`hpdi\.shape\.\$\{shape\}\.name`\)/)
  for (const shape of HPDI_SHAPES) {
    for (const part of ['name', 'text']) {
      assert.ok(lookup(vi, `hpdi.shape.${shape}.${part}`) && lookup(en, `hpdi.shape.${shape}.${part}`), shape)
    }
  }
  for (const id of Object.values(HPDI_EVIDENCE).flat()) {
    for (const part of ['name', 'value']) {
      assert.ok(lookup(vi, `hpdi.evidence.${id}.${part}`) && lookup(en, `hpdi.evidence.${id}.${part}`), `${id}.${part}`)
    }
  }
  for (const key of ['nav.selfCheck', 'audit.entity.office.maturity_assessments', 'error.maturity_rate']) {
    assert.ok(lookup(vi, key) && lookup(en, key), key)
  }
  // [I] là không gian cuối: câu "nên làm trước" của nó không nhắc "không gian sau"
  assert.doesNotMatch(lookup(vi, 'hpdi.focusLast')!, /không gian sau/)
  assert.doesNotMatch(lookup(en, 'hpdi.focusLast')!, /later/)
  assert.match(lookup(vi, 'hpdi.focus')!, /không gian sau/)
})

test('câu chữ nói rõ là tự đánh giá, không phải bộ chỉ số chính thức, có dẫn nguồn', () => {
  assert.match(lookup(vi, 'hpdi.disclaimer')!, /không phải bộ chỉ số chính thức/)
  assert.match(lookup(en, 'hpdi.disclaimer')!, /not an official/)
  const urls = FRAMEWORK.sources.map((s) => s.url)
  assert.ok(urls.some((u) => u.includes('vfossa.vn') && u.includes('761')), 'thiếu bài 761')
  assert.ok(urls.some((u) => u.startsWith('https://opendigitransform.gitbook.io/dx-os/')), 'thiếu giáo trình DX-OS')
  // CC BY 4.0: ghi công tác giả và giấy phép ở nguồn hiện trên trang, cả câu giải thích tỷ trọng
  const book = FRAMEWORK.sources.find((x) => x.url.startsWith('https://opendigitransform.gitbook.io/'))!
  for (const lang of ['vi', 'en'] as const) {
    assert.match(book.title[lang], /Tạ Tuấn Anh, CC BY 4\.0/)
    assert.match(lookup(lang === 'vi' ? vi : en, 'hpdi.shapeHint')!, /Tạ Tuấn Anh, CC BY 4\.0/)
  }
})
