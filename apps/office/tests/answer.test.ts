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


// Hỏi đáp trên kho văn bản (F4.2): câu trả lời tách thành chữ và dấu trích dẫn [n] (không bao giờ thành HTML), nhãn
// trích dẫn "88/CTSV · tr. 1" theo đúng chữ trong vi.json / en.json, và hai bộ khóa ngôn ngữ khớp nhau. Hỏi trong một
// văn bản (?van_ban=<id>), nhãn nguồn mở tệp đúng trang (#page=n).

import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { test } from 'node:test'
import type { AskResult, AskSource } from '../app/composables/useApi.ts'

const {
  ASK_ROLES, DATA_GROUP, DATA_LINKS, DATA_ROUTES, MASK_RE, MAX_PREVIOUS, MAX_QUESTION, ROUTES, SCOPE_PARAM,
  SUGGEST_GROUPS,
  askAbout, blocks, canAskAbout, canView, citeLabel, cleanQuestion, fallbackSuggestions, hasMask, inAssistant,
  isIntro, needsGenerate, pageUrl, plainIntro, previousFor, scopeOf, searched, segments, sourceAnchor, tidy,
} = await import('../app/utils/answer.ts')

type Messages = { [key: string]: string | Messages }
const load = (lang: string): Messages =>
  JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`, import.meta.url), 'utf8')) as Messages
const vi = load('vi')
const en = load('en')

// Hàm dịch tối thiểu như vue-i18n: khóa có chấm, tham số {x}; thiếu khóa thì báo lỗi ngay
function lookup(messages: Messages, key: string): string | undefined {
  let node: string | Messages | undefined = messages
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined
  return typeof node === 'string' ? node : undefined
}
const translator = (messages: Messages) => (key: string, named: Record<string, unknown> = {}): string => {
  const message = lookup(messages, key)
  if (message === undefined) throw new Error(`thiếu khóa ${key}`)
  return message.replace(/\{(\w+)\}/g, (_, name: string) => String(named[name]))
}
const tVi = translator(vi)
const tEn = translator(en)

// Nguồn mẫu đúng như hợp đồng API (svc-files POST /api/documents/ask)
const source = (n: number, extra: Partial<AskSource> = {}): AskSource => ({
  n, document_id: `d${n}`, symbol: '88/CTSV', type_code: 'CV', type_name: 'Công văn',
  summary: 'Về việc xét học bổng khuyến khích học tập học kỳ I năm học 2026–2027',
  issuer_name: 'Phòng Công tác sinh viên', issued_on: '2026-10-15', direction: 'in', status: 'in_progress',
  kind: 'page', file_id: `f${n}`, file_role: 'main', page: 1,
  excerpt: 'Sinh viên có điểm trung bình chung học kỳ từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt.', cited: true,
  ...extra,
})
const SAMPLE: AskResult = {
  ask_id: '6f1c2a3b-0000-4000-8000-000000000001', status: 'answered',
  answer: { text: '“…từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt.” [1]', source: 'extract', model: null },
  extract: { text: '“…từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt.” [1]', source: 'extract', model: null },
  sources: [source(1)], semantic: false, ai_available: false, warnings: [], duration_ms: 142,
}

test('câu trích mẫu: chữ rồi một dấu trích dẫn trỏ đúng nguồn 1', () => {
  const parts = segments(SAMPLE.answer!.text, SAMPLE.sources)
  assert.deepEqual(parts, [{ text: '“…từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt.” ' }, { n: 1, source: SAMPLE.sources[0] }])
})

test('dấu [n] không có nguồn thì giữ nguyên là chữ, gộp với chữ liền kề', () => {
  const sources = [source(1), source(2)]
  assert.deepEqual(segments('Theo Điều [5] của quy chế [1].', sources),
    [{ text: 'Theo Điều [5] của quy chế ' }, { n: 1, source: sources[0] }, { text: '.' }])
  assert.deepEqual(segments('Mục [0] và [3]', sources), [{ text: 'Mục [0] và [3]' }])
  assert.deepEqual(segments('[1][2] đầu câu', sources),
    [{ n: 1, source: sources[0] }, { n: 2, source: sources[1] }, { text: ' đầu câu' }])
  // dấu ngoặc khác, số quá dài: không phải trích dẫn
  assert.deepEqual(segments('[a] [1000] [ 1] (1)', sources), [{ text: '[a] [1000] [ 1] (1)' }])
})

test('dạng gộp [1, 2]: đủ nguồn thì thành hai trích dẫn, thiếu một số thì cả cụm là chữ', () => {
  const sources = [source(1), source(2)]
  assert.deepEqual(segments('Hạn nộp 12/12/2026 [1, 2].', sources),
    [{ text: 'Hạn nộp 12/12/2026 ' }, { n: 1, source: sources[0] }, { n: 2, source: sources[1] }, { text: '.' }])
  assert.deepEqual(segments('x [1,2]', sources), [{ text: 'x ' }, { n: 1, source: sources[0] }, { n: 2, source: sources[1] }])
  assert.deepEqual(segments('x [1, 7]', sources), [{ text: 'x [1, 7]' }])
})

test('chữ có thẻ HTML vẫn chỉ là chữ; không có câu trả lời thì không có đoạn nào', () => {
  const sources = [source(1)]
  const text = '<img src=x onerror=alert(1)> <a href="javascript:x">[1]</a>'
  const parts = segments(text, sources)
  assert.deepEqual(parts, [{ text: '<img src=x onerror=alert(1)> <a href="javascript:x">' }, { n: 1, source: sources[0] }, { text: '</a>' }])
  assert.equal(parts.map((p) => ('text' in p ? p.text : `[${p.n}]`)).join(''), text)
  assert.deepEqual(segments('', sources), [])
  assert.deepEqual(segments(null, sources), [])
  assert.deepEqual(segments('Không có dấu nào', []), [{ text: 'Không có dấu nào' }])
  assert.deepEqual(segments('Có [1] mà không có nguồn', []), [{ text: 'Có [1] mà không có nguồn' }])
})

test('nhiều dòng câu trích: mỗi dòng một dấu, xuống dòng giữ nguyên trong chữ', () => {
  const sources = [source(1), source(2, { symbol: '131/ĐT-ĐH' })]
  const parts = segments('“Câu một.” [1]\n“Câu hai.” [2]', sources)
  assert.deepEqual(parts.map((p) => ('text' in p ? p.text : p.n)), ['“Câu một.” ', 1, '\n“Câu hai.” ', 2])
})

test('nhãn trích dẫn theo vi.json: trang, tài liệu kèm theo, trích yếu', () => {
  assert.equal(citeLabel(source(1), tVi), '88/CTSV · tr. 1')
  assert.equal(citeLabel(source(1, { file_role: 'attachment', page: 2 }), tVi), '88/CTSV · tài liệu kèm theo, tr. 2')
  assert.equal(citeLabel(source(1, { file_role: 'issued', page: 3 }), tVi), '88/CTSV · tr. 3')
  assert.equal(citeLabel(source(1, { kind: 'meta', file_id: null, file_role: null, page: null }), tVi), '88/CTSV · trích yếu')
  // chữ cũ chưa có ranh giới trang: không bịa số trang
  assert.equal(citeLabel(source(1, { page: null }), tVi), '88/CTSV')
  assert.equal(citeLabel(source(1, { file_role: 'attachment', page: null }), tVi), '88/CTSV · tài liệu kèm theo')
  // văn bản chưa có số ký hiệu: tên loại, không có thì mã loại
  assert.equal(citeLabel(source(1, { symbol: null }), tVi), 'Công văn · tr. 1')
  assert.equal(citeLabel(source(1, { symbol: '  ', type_name: null }), tVi), 'CV · tr. 1')
})

test('nhãn đọc cho trình đọc màn hình và tên liên kết [n]', () => {
  assert.equal(citeLabel(source(1), tVi, true), '88/CTSV, trang 1')
  assert.equal(tVi('assist.source.cite', { n: 1, label: citeLabel(source(1), tVi, true) }), 'Nguồn 1: 88/CTSV, trang 1')
  assert.equal(citeLabel(source(2, { file_role: 'attachment', page: 2 }), tVi, true), '88/CTSV, tài liệu kèm theo, trang 2')
  assert.equal(citeLabel(source(1), tEn), '88/CTSV · p. 1')
  assert.equal(citeLabel(source(1, { kind: 'meta', page: null }), tEn, true), '88/CTSV, summary')
})

test('id mục nguồn: duy nhất theo lượt hỏi, chỉ có ký tự an toàn', () => {
  assert.equal(sourceAnchor(SAMPLE.ask_id, 2), 'nguon-6f1c2a3b-0000-4000-8000-000000000001-2')
  assert.equal(sourceAnchor('a"b <c>#d', 1), 'nguon-abcd-1')
  assert.notEqual(sourceAnchor('x', 1), sourceAnchor('y', 1))
})

test('câu hỏi gửi đi: một dòng, NFC, không ký tự điều khiển hay vô hình', () => {
  assert.equal(cleanQuestion('  Điều kiện xét\nhọc bổng  là gì?\r\n'), 'Điều kiện xét học bổng là gì?')
  assert.equal(cleanQuestion('Hạn​ nộp­ hồ sơ\u0007?'), 'Hạn nộp hồ sơ?')
  assert.equal(cleanQuestion('Học bổng'.normalize('NFD')), 'Học bổng'.normalize('NFC'))
  assert.equal(cleanQuestion('\t\n ​'), '')
  assert.equal(MAX_QUESTION, 500)
})

test('tự nhờ mô hình viết câu trả lời chỉ khi mô hình sẵn sàng và có đoạn trích', () => {
  assert.equal(needsGenerate({ ...SAMPLE, ai_available: true }), true)
  assert.equal(needsGenerate({ ...SAMPLE, ai_available: true, status: 'passages_only' }), true)
  assert.equal(needsGenerate(SAMPLE), false)
  assert.equal(needsGenerate({ ...SAMPLE, ai_available: true, status: 'no_evidence', sources: [] }), false)
  assert.equal(needsGenerate({ ...SAMPLE, ai_available: true, sources: [] }), false)
})

test('khối hiện: câu trả lời của mô hình và câu trích; mô hình không đạt thì chỉ còn câu trích', () => {
  const model = { text: 'Điểm trung bình từ 3,2 trở lên [1].', source: 'model' as const, model: 'qwen3:1.7b' }
  assert.deepEqual(blocks({ answer: model, extract: SAMPLE.extract }), { model, extract: SAMPLE.extract, direct: null })
  // model_rejected / model_timeout: answer là chính câu trích
  assert.deepEqual(blocks({ answer: SAMPLE.answer, extract: SAMPLE.extract }),
    { model: null, extract: SAMPLE.extract, direct: null })
  // mô hình trả lời mà không trích được câu nào
  assert.deepEqual(blocks({ answer: model, extract: null }), { model, extract: null, direct: null })
  // thiếu extract nhưng answer là câu trích
  assert.deepEqual(blocks({ answer: SAMPLE.answer, extract: null }),
    { model: null, extract: SAMPLE.answer, direct: null })
  assert.deepEqual(blocks({ answer: null, extract: null }), { model: null, extract: null, direct: null })
  assert.deepEqual(blocks({ answer: { ...model, text: '' }, extract: null }),
    { model: null, extract: null, direct: null })
})

test('nhãn che thông tin cá nhân (F4.4): nhận đúng nhãn, không nhầm với dấu trích dẫn', () => {
  for (const s of ['Số liên hệ là [SĐT-1].', '[CCCD]', 'gửi [EMAIL-12]', '[STK-999]', 'CMND [CMND-3] cấp năm 2010']) {
    assert.equal(hasMask(s), true, s)
  }
  for (const s of ['[1]', '[SĐT-1000]', '[SDT-1]', '[sđt-1]', 'SĐT-1', '[SĐT 1]', '[EMAIL-]', '[SĐT-01x]', '', null, undefined]) {
    assert.equal(hasMask(s), false, String(s))
  }
  // nhãn giữ nguyên là chữ, dấu [n] cạnh nó vẫn là trích dẫn
  const sources = [source(1)]
  assert.deepEqual(segments('Số liên hệ là [SĐT-1] [1].', sources),
    [{ text: 'Số liên hệ là [SĐT-1] ' }, { n: 1, source: sources[0] }, { text: '.' }])
  // không có cờ g: gọi nhiều lần cùng một chữ cho cùng kết quả (lastIndex không đổi)
  assert.equal(MASK_RE.flags.includes('g'), false)
  assert.deepEqual([1, 2, 3].map(() => hasMask('[SĐT-1]')), [true, true, true])
})

test('mẫu nhãn che giống hệt LABEL_RE của svc-files (pii.py)', (t) => {
  const file = new URL('../../../services/svc-files/src/svc_files/pii.py', import.meta.url)
  if (!existsSync(file)) {
    t.skip('không có services/svc-files trong cây mã')
    return
  }
  const m = readFileSync(file, 'utf8').match(/^LABEL_RE = re\.compile\(r"(.+)"\)$/m)
  assert.ok(m, 'không thấy LABEL_RE trong pii.py')
  assert.equal(MASK_RE.source, m[1])
})

test('dòng nhắc che thông tin cá nhân có ở hai ngôn ngữ, chỉ tới câu trích nguyên văn', () => {
  assert.match(tVi('assist.maskedNote'), /câu trích nguyên văn/)
  assert.match(tEn('assist.maskedNote'), /verbatim quote/)
})

test('kết quả thiếu trường vẫn dùng được: mảng rỗng, nguồn theo n, cảnh báo không trùng', () => {
  const raw = { ...SAMPLE, sources: [source(2), source(1)], warnings: ['model_timeout', 'model_timeout', 7] } as unknown as AskResult
  const out = tidy(raw)
  assert.deepEqual(out.sources.map((s) => s.n), [1, 2])
  assert.deepEqual(out.warnings, ['model_timeout'])
  // nguồn chỉ có trích yếu mà máy chủ để đoạn trích null: thành chuỗi rỗng
  const meta = tidy({ ...SAMPLE, sources: [{ ...source(1, { kind: 'meta', page: null }), excerpt: null }] } as unknown as AskResult)
  assert.equal(meta.sources[0]?.excerpt, '')
  const bare = tidy({ ask_id: 'x', status: 'no_evidence', semantic: false, ai_available: false, duration_ms: 3 } as unknown as AskResult)
  assert.deepEqual([bare.sources, bare.warnings, bare.answer, bare.extract], [[], [], null, null])
})

// --- bộ định tuyến, câu nối tiếp, gợi ý theo loại câu (hợp đồng API: route, route_reason, rewritten, previous) -------

test('máy chủ chưa có bộ định tuyến: không có route, trang như cũ; route lạ coi như van_ban', () => {
  const old = tidy(SAMPLE)
  assert.equal('route' in old, false)
  assert.equal('route_reason' in old, false)
  assert.equal(old.rewritten, null)
  const odd = tidy({ ...SAMPLE, route: 'thoi_tiet', route_reason: 7, rewritten: '  ' } as unknown as AskResult)
  assert.equal(odd.route, 'van_ban')
  assert.equal('route_reason' in odd, false)
  assert.equal(odd.rewritten, null)
  const follow = tidy({ ...SAMPLE, route: 'van_ban', route_reason: 'mac-dinh', rewritten: ' Khoa Kinh tế học bổng ' })
  assert.deepEqual([follow.route, follow.route_reason, follow.rewritten],
    ['van_ban', 'mac-dinh', 'Khoa Kinh tế học bổng'])
  for (const route of ROUTES) assert.equal(tidy({ ...SAMPLE, route }).route, route)
})

test('liên kết của đường dữ liệu: chỉ các trang danh sách đã biết', () => {
  assert.equal(tidy(SAMPLE).link, null)
  for (const link of DATA_LINKS) assert.equal(tidy({ ...SAMPLE, route: 'dem_van_ban', link }).link, link)
  for (const link of ['//evil.example', 'https://evil.example', '/van-ban/1', 'javascript:alert(1)', 7]) {
    assert.equal(tidy({ ...SAMPLE, route: 'dem_van_ban', link } as unknown as AskResult).link, null)
  }
  assert.ok(tVi('assist.openList') && tEn('assist.openList'))
})

test('văn bản, hướng dẫn và giới thiệu nhờ mô hình viết; ngoài phạm vi, đường dữ liệu thì không', () => {
  const ready = { ...SAMPLE, ai_available: true }
  assert.equal(needsGenerate({ ...ready, route: undefined }), true)
  for (const route of ['van_ban', 'huong_dan', 'gioi_thieu'] as const) {
    assert.equal(needsGenerate({ ...ready, route }), true, route)
  }
  for (const route of ['ngoai_pham_vi', 'viec_cua_toi', 'dem_van_ban'] as const) {
    assert.equal(needsGenerate({ ...ready, route }), false, route)
  }
  // giới thiệu hiện như tin nhắn: không chip cách tìm, câu trích thành chữ thường
  assert.equal(searched('gioi_thieu'), false)
  assert.equal(isIntro({ route: 'gioi_thieu' }), true)
  assert.equal(isIntro({ route: 'van_ban' }), false)
  assert.equal(plainIntro('“Tôi là trợ lý. Tôi giúp bạn.” [1]'), 'Tôi là trợ lý. Tôi giúp bạn.')
  assert.equal(plainIntro('Chào bạn!'), 'Chào bạn!')
})

test('câu trả lời thẳng (fixed, data) là khối riêng, không phải câu trích hay câu của mô hình', () => {
  const data = { text: 'Bạn có 2 việc sắp quá hạn. Căn cứ: Hộp việc của bạn.', source: 'data' as const, model: null }
  assert.deepEqual(blocks({ answer: data, extract: null }), { model: null, extract: null, direct: data })
  const fixed = { ...data, source: 'fixed' as const, text: 'Trợ lý chỉ trả lời về văn bản và cách dùng hệ thống.' }
  assert.deepEqual(blocks({ answer: fixed, extract: null }), { model: null, extract: null, direct: fixed })
  assert.deepEqual(blocks({ answer: { ...data, text: '' }, extract: null }),
    { model: null, extract: null, direct: null })
})

test('nguồn guide (hướng dẫn, giới thiệu trợ lý): nhãn là tên tài liệu, không mở tệp', () => {
  const guide = source(1, {
    document_id: null, symbol: 'Hướng dẫn cho văn thư', type_code: null, type_name: 'Hướng dẫn sử dụng',
    summary: 'Tiếp nhận văn bản đến', issuer_name: null, issued_on: null, direction: null, status: null,
    kind: 'guide', file_id: null, file_role: null, page: null, path: 'docs/huong-dan/van-thu.md#tiep-nhan',
  })
  assert.equal(citeLabel(guide, tVi), 'Hướng dẫn cho văn thư')
  assert.equal(citeLabel({ ...guide, symbol: null, type_name: null }, tVi), '')
  assert.equal(canView(guide), false)
})

test('câu trước gửi kèm: chỉ lượt ngay trước, cùng phạm vi, đã có kết quả; câu đã ghép đi trước câu gốc', () => {
  const doc = '8c1d2e3f-0000-4000-8000-000000000088'
  const prior = { scope: null, question: 'Điều kiện xét học bổng là gì?', done: true }
  assert.equal(previousFor(undefined, null), undefined)                     // lượt đầu
  assert.equal(previousFor(prior, null), 'Điều kiện xét học bổng là gì?')
  assert.equal(previousFor({ ...prior, rewritten: null }, null), 'Điều kiện xét học bổng là gì?')
  // chuỗi ba câu: lượt trước là câu nối tiếp thì gửi câu máy chủ đã ghép
  assert.equal(previousFor({ ...prior, rewritten: 'học bổng Khoa Kinh tế' }, null), 'học bổng Khoa Kinh tế')
  assert.equal(previousFor({ ...prior, done: false }, null), undefined)      // lượt trước lỗi hay chưa xong
  assert.equal(previousFor(prior, doc), undefined)                          // vừa đổi sang hỏi trong một văn bản
  assert.equal(previousFor({ ...prior, scope: doc }, null), undefined)      // vừa bỏ phạm vi văn bản
  assert.equal(previousFor({ ...prior, scope: doc }, doc), 'Điều kiện xét học bổng là gì?')
  assert.equal(previousFor({ ...prior, question: ' Học\nbổng ​ ' }, null), 'Học bổng')
  assert.equal(previousFor({ ...prior, rewritten: 'x'.repeat(MAX_PREVIOUS + 1) }, null), undefined)
})

test('gợi ý theo loại câu: mọi câu, tên nhóm, dòng "trả lời được" có ở hai ngôn ngữ', () => {
  for (const group of [...SUGGEST_GROUPS, DATA_GROUP]) {
    for (const key of group.keys) assert.ok(tVi(key) && tEn(key), key)
    assert.ok(tVi(`assist.suggestGroup.${group.route}`) && tEn(`assist.suggestGroup.${group.route}`))
    assert.ok(tVi(`assist.can.${group.route}`) && tEn(`assist.can.${group.route}`))
  }
  for (const route of ROUTES) assert.ok(tVi(`assist.route.${route}`) && tEn(`assist.route.${route}`), route)
  assert.equal(tVi('assist.understood', { route: tVi('assist.route.gioi_thieu') }), 'Đã hiểu là câu hỏi về: trợ lý')
  // ba câu văn bản cũ vẫn là nhóm đầu tiên
  assert.deepEqual(SUGGEST_GROUPS[0], {
    route: 'van_ban', keys: ['assist.suggest.credits', 'assist.suggest.examDeadline', 'assist.suggest.language'],
  })
})

test('nhóm "Việc của tôi" chỉ hiện khi svc-files có đường dữ liệu; gợi ý dự phòng bỏ nhóm vừa hỏi', () => {
  const routes = SUGGEST_GROUPS.map((g) => g.route)
  assert.equal(routes.includes('viec_cua_toi'), DATA_ROUTES)
  assert.equal(new Set(routes).size, routes.length)
  assert.deepEqual(fallbackSuggestions('van_ban'), SUGGEST_GROUPS.slice(1).map((g) => g.keys[0]))
  assert.deepEqual(fallbackSuggestions(undefined), fallbackSuggestions('van_ban'))
  assert.deepEqual(fallbackSuggestions('ngoai_pham_vi'), SUGGEST_GROUPS.map((g) => g.keys[0]))
  assert.ok(!fallbackSuggestions('huong_dan').includes('assist.suggest.leave'))
})

// Hai bộ khóa ngôn ngữ phải giống hệt nhau, cùng tham số {x}
function flatten(messages: Messages, prefix = ''): Map<string, string> {
  const out = new Map<string, string>()
  for (const [k, v] of Object.entries(messages)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'string') out.set(key, v)
    else for (const [kk, vv] of flatten(v, key)) out.set(kk, vv)
  }
  return out
}
// (bản en có thể có dạng số nhiều "… | …" lặp lại tham số: so tập tham số)
const params = (s: string) => [...new Set([...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort().join(',')

test('vi.json và en.json: cùng khóa, cùng tham số', () => {
  const a = flatten(vi)
  const b = flatten(en)
  assert.deepEqual([...a.keys()].filter((k) => !b.has(k)), [], 'khóa có ở vi mà không có ở en')
  assert.deepEqual([...b.keys()].filter((k) => !a.has(k)), [], 'khóa có ở en mà không có ở vi')
  for (const [k, v] of a) assert.equal(params(v), params(b.get(k)!), `tham số khác nhau ở ${k}`)
})

test('mọi mã lỗi, cảnh báo, trạng thái của API hỏi đáp có câu hiển thị ở cả hai ngôn ngữ', () => {
  const errors = ['invalid_question', 'missing_token', 'invalid_token', 'forbidden', 'assistant_disabled', 'busy',
    'search_unavailable', 'database_unavailable', 'client_timeout', 'generic']
  const warnings = ['embed_unavailable', 'model_unavailable', 'model_timeout', 'model_rejected', 'model_declined']
  for (const messages of [vi, en]) {
    for (const code of errors) assert.ok(lookup(messages, `assist.error.${code}`), `assist.error.${code}`)
    for (const code of warnings) assert.ok(lookup(messages, `assist.warning.${code}`), `assist.warning.${code}`)
    for (const s of ['answered', 'passages_only', 'no_evidence']) assert.ok(lookup(messages, `assist.status.${s}`))
    for (const key of ['nav.ask', 'search.askAssistant', 'audit.agents.moc-assistant', 'audit.action.assistant.answered',
      'audit.entity.ai.questions', 'audit.askMode.extract', 'audit.askMode.generate', 'audit.answerSource.model']) {
      assert.ok(lookup(messages, key), key)
    }
    for (const col of ['ask_id', 'mode', 'answer_source', 'hits', 'cited', 'semantic', 'embed_model', 'warnings']) {
      assert.ok(lookup(messages, `audit.col.${col}`), `audit.col.${col}`)
    }
  }
  assert.equal(tVi('assist.title'), 'Hỏi đáp văn bản')
  assert.equal(tVi('audit.agents.moc-assistant'), 'Trợ lý hỏi đáp')
})

test('khóa i18n viết thẳng trong trang Hỏi đáp đều có trong vi.json', () => {
  const files = ['../app/pages/hoi-dap.vue', '../app/components/AnswerText.vue', '../app/utils/answer.ts']
  let checked = 0
  for (const file of files) {
    const code = readFileSync(new URL(file, import.meta.url), 'utf8')
    for (const m of code.matchAll(/\bt\('([\w.-]+)'/g)) {
      assert.ok(lookup(vi, m[1]!) !== undefined, `${file}: thiếu khóa ${m[1]}`)
      checked++
    }
  }
  assert.ok(checked > 40, `chỉ thấy ${checked} khóa`)
})

// --- hỏi trong một văn bản, xem trang được trích -----------------------------------------------------------------

const DOC_ID = '8c1d2e3f-0000-4000-8000-000000000088'

test('nút "Hỏi về văn bản này" mở trang Hỏi đáp với ?van_ban=<id>, trang Hỏi đáp đọc lại đúng id đó', () => {
  assert.deepEqual(askAbout(DOC_ID), { path: '/hoi-dap', query: { van_ban: DOC_ID } })
  assert.equal(SCOPE_PARAM, 'van_ban')
  assert.equal(scopeOf(askAbout(DOC_ID).query), DOC_ID)
  assert.equal(scopeOf({ van_ban: DOC_ID.toUpperCase() }), DOC_ID)
  // không phải UUID thì không có phạm vi: không gửi chuỗi lạ lên máy chủ
  for (const bad of [undefined, null, '', 'abc', [DOC_ID], `${DOC_ID}" OR 1`, ` ${DOC_ID}`]) {
    assert.equal(scopeOf({ van_ban: bad }), null, String(bad))
  }
  assert.equal(scopeOf({ q: 'học bổng' }), null)
})

test('nút chỉ hiện khi người xem hỏi được và văn bản có trong kho của trợ lý', () => {
  const doc = (direction: string, status: string, restricted = false) => ({ direction, status, restricted })
  assert.equal(inAssistant(doc('in', 'received')), true)
  assert.equal(inAssistant(doc('in', 'cancelled')), false)
  assert.equal(inAssistant(doc('in', 'received', true)), false)       // hạn chế: không bao giờ vào chỉ mục
  assert.equal(inAssistant(doc('out', 'draft')), false)               // dự thảo chưa phát hành
  assert.equal(inAssistant(doc('out', 'issued')), true)
  assert.equal(inAssistant(doc('out', 'archived')), true)
  assert.equal(inAssistant(doc('x', 'received')), false)
  for (const role of ['clerk', 'staff', 'manager', 'director']) {
    assert.equal(canAskAbout(doc('in', 'received'), role), true, role)
  }
  for (const role of ['tenant_admin', 'verifier', '', null, undefined]) {
    assert.equal(canAskAbout(doc('in', 'received'), role), false, String(role))
  }
  assert.equal(canAskAbout(doc('out', 'draft'), 'staff'), false)
})

test('vai trò hỏi được và văn bản có trong kho của trợ lý khớp svc-files (scope.py, chunks.eligible)', (t) => {
  const dir = new URL('../../../services/svc-files/src/svc_files/assist/', import.meta.url)
  if (!existsSync(dir)) {
    t.skip('không có services/svc-files trong cây mã')
    return
  }
  const scope = readFileSync(new URL('scope.py', dir), 'utf8')
  const roles = [...scope.matchAll(/^(?:READ_ALL = frozenset\(\{|ROLES = READ_ALL \| \{)([^}]*)\}/gm)]
    .flatMap((m) => [...m[1]!.matchAll(/"(\w+)"/g)].map((x) => x[1]))
  assert.deepEqual(roles.sort(), [...ASK_ROLES].sort())
  const chunks = readFileSync(new URL('chunks.py', dir), 'utf8')
  const eligible = chunks.match(/^def eligible\(.*\n((?: {4}.*\n)+)/m)?.[1] ?? ''
  assert.match(eligible, /if doc\.get\("restricted"\):\n\s+return False/)
  assert.match(eligible, /== "in":\n\s+return doc\.get\("status"\) != "cancelled"/)
  assert.match(eligible, /== "out":\n\s+return doc\.get\("status"\) in \("issued", "archived"\)/)
})

test('nhãn nguồn mở tệp đúng trang được trích: #page=n, không có trang thì mở từ đầu', () => {
  assert.equal(canView(source(1)), true)
  assert.equal(canView(source(1, { kind: 'meta', file_id: null, file_role: null, page: null })), false)   // trích yếu
  assert.equal(canView(source(1, { file_id: null })), false)
  const url = 'blob:https://signet.example/6f1c2a3b'
  assert.equal(pageUrl(url, 3), `${url}#page=3`)
  for (const page of [null, undefined, 0, -1, 1.5]) assert.equal(pageUrl(url, page), url, String(page))
  assert.equal(tVi('assist.viewSource', { label: citeLabel(source(1), tVi, true) }), 'Xem tệp: 88/CTSV, trang 1')
  assert.equal(tVi('assist.viewPage', { n: 2 }), 'Xem trang 2')
  assert.equal(tEn('assist.viewSource', { label: citeLabel(source(1), tEn, true) }), 'View file: 88/CTSV, page 1')
  assert.equal(tVi('assist.scope.chip', { label: '88/CTSV' }), 'Trong 88/CTSV')
  assert.equal(tVi('doc.askAbout'), 'Hỏi về văn bản này')
  assert.equal(tEn('doc.askAbout'), 'Ask about this document')
})
