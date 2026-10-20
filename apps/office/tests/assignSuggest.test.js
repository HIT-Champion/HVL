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

// Định dạng ngày giờ theo kiểu Việt Nam (dd/mm/yyyy), dùng chung cho mọi trang.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
const { MAX_EVIDENCE, MAX_POLLS, POLL_MS, SUGGEST_REASONS, SUMMARY_MAX, WAIT_MS, applyValues, clipSummary, confidenceTone, evidenceIds, matchState, pollState, readEvidence, reasonKey, shownEvidence } = await import('../app/utils/assignSuggest.js');
const load = (lang)=>JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`, import.meta.url), 'utf8'));
const vi = load('vi');
const en = load('en');
const source = (file)=>readFileSync(new URL(file, import.meta.url), 'utf8');
function lookup(messages, key) {
    let node = messages;
    for (const part of key.split('.'))node = typeof node === 'object' ? node[part] : undefined;
    return typeof node === 'string' ? node : undefined;
}
const translator = (messages)=>(key, named = {}, plural)=>{
        const message = lookup(messages, key);
        if (message === undefined) throw new Error(`thiếu khóa ${key}`);
        const choices = message.split(' | ');
        const chosen = choices.length === 2 && plural !== undefined ? choices[plural === 1 ? 0 : 1] : message;
        return chosen.replace(/\{(\w+)\}/g, (_, name)=>String(named[name]));
    };
const tVi = translator(vi);
const tEn = translator(en);
const id = (n)=>`00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const DT = '5cc3a1e0-0000-4000-8000-0000000000d7';
const KTPM = '8dec217d-0000-4000-8000-00000000004b';
const SAMPLE = {
    status: 'suggested',
    reason: null,
    department_id: DT,
    confidence: 'high',
    share: 0.82,
    due_days: 10,
    due_on: '2026-11-05',
    evidence: [
        {
            document_id: id(1),
            score: 0.91,
            department_id: DT,
            days: 7
        },
        {
            document_id: id(2),
            score: 0.77,
            department_id: DT,
            days: 10
        },
        {
            document_id: id(3),
            score: 0.64,
            department_id: KTPM,
            days: 14
        },
        {
            document_id: id(4),
            score: 0.52,
            department_id: DT,
            days: null
        }
    ],
    created_at: '2026-10-26T01:02:03.456789+00:00'
};
const READABLE = new Map([
    [
        id(1),
        {
            symbol: '88/CTSV',
            summary: 'Về việc xét học bổng khuyến khích học tập học kỳ I năm học 2026–2027'
        }
    ],
    [
        id(2),
        {
            symbol: '135/ĐT-ĐH',
            summary: 'Về việc xét cấp học bổng cho sinh viên có hoàn cảnh khó khăn'
        }
    ],
    [
        id(3),
        {
            symbol: '47/KHCN',
            summary: 'Về việc đăng ký đề tài nghiên cứu khoa học sinh viên'
        }
    ],
    [
        id(4),
        {
            symbol: '140/ĐT',
            summary: 'Về việc xét miễn giảm học phí'
        }
    ]
]);
test('hằng số giao diện theo hợp đồng: hỏi lại 3 giây một lần, tối đa 60 giây', ()=>{
    assert.equal(POLL_MS, 3000);
    assert.equal(WAIT_MS, 60000);
    assert.equal(MAX_POLLS, 20);
    assert.equal(MAX_EVIDENCE, 3);
    assert.equal(SUMMARY_MAX, 80);
});
test('hỏi lại: chưa có dòng và vào sổ chưa quá 60 giây; có dòng (kể cả none, failed) thì thôi', ()=>{
    const at = '2026-10-26T01:00:00.123456+00:00';
    const t0 = Date.parse('2026-10-26T01:00:00.123Z');
    assert.equal(pollState(null, at, t0 + 2_000), 'wait');
    assert.equal(pollState(null, at, t0 + 59_999), 'wait');
    assert.equal(pollState(null, at, t0 + 60_000), 'stop');
    assert.equal(pollState(null, at, t0 + 3_600_000), 'stop');
    assert.equal(pollState(null, at, t0 - 30_000), 'wait');
    for (const status of [
        'suggested',
        'none',
        'failed'
    ]){
        assert.equal(pollState({
            ...SAMPLE,
            status
        }, at, t0 + 1_000), 'stop');
    }
    assert.equal(pollState(null, null, t0), 'stop');
    assert.equal(pollState(null, undefined, t0), 'stop');
    assert.equal(pollState(null, 'không phải ngày', t0), 'stop');
});
test('chip độ tin cậy: bảng màu của nhãn gợi ý F4.1 (cao xanh lục, vừa hổ phách, thấp xám đá)', ()=>{
    assert.match(confidenceTone('high'), /emerald/);
    assert.match(confidenceTone('medium'), /amber/);
    assert.match(confidenceTone('low'), /stone/);
    assert.equal(confidenceTone(null), confidenceTone('low'));
    assert.equal(confidenceTone('lạ'), confidenceTone('low'));
    const tag = source('../app/components/SuggestTag.vue');
    for (const c of [
        'high',
        'medium',
        'low'
    ])assert.ok(tag.includes(`'${confidenceTone(c)}'`), c);
});
test('căn cứ hiện: theo thứ tự điểm, chỉ văn bản người xem đọc được, tối đa 3', ()=>{
    const shown = shownEvidence(SAMPLE.evidence, READABLE);
    assert.deepEqual(shown.map((e)=>e.symbol), [
        '88/CTSV',
        '135/ĐT-ĐH',
        '47/KHCN'
    ]);
    assert.deepEqual(shown[0], {
        document_id: id(1),
        score: 0.91,
        department_id: DT,
        days: 7,
        symbol: '88/CTSV',
        summary: 'Về việc xét học bổng khuyến khích học tập học kỳ I năm học 2026–2027'
    });
    const partial = new Map([
        ...READABLE
    ].filter(([k])=>k !== id(2)));
    assert.deepEqual(shownEvidence(SAMPLE.evidence, partial).map((e)=>e.document_id), [
        id(1),
        id(3),
        id(4)
    ]);
    assert.deepEqual(shownEvidence(SAMPLE.evidence, new Map()), []);
    assert.equal(shownEvidence(SAMPLE.evidence, READABLE, 1).length, 1);
    const shuffled = [
        ...SAMPLE.evidence
    ].reverse();
    assert.deepEqual(shownEvidence(shuffled, READABLE).map((e)=>e.document_id), [
        id(1),
        id(2),
        id(3)
    ]);
    const tie = [
        {
            document_id: id(3),
            score: 0.5,
            department_id: KTPM,
            days: 3
        },
        {
            document_id: id(1),
            score: 0.5,
            department_id: DT,
            days: 3
        }
    ];
    assert.deepEqual(shownEvidence(tie, READABLE).map((e)=>e.document_id), [
        id(3),
        id(1)
    ]);
});
test('cột evidence sai dạng không làm hỏng khối: bỏ phần tử lạ, id trùng, id không phải uuid', ()=>{
    const messy = [
        null,
        'x',
        7,
        {
            score: 0.9
        },
        {
            document_id: 'abc',
            score: 0.9
        },
        {
            document_id: id(1),
            score: '0.9'
        },
        {
            document_id: id(2),
            score: 0.8,
            department_id: '',
            days: 0
        },
        {
            document_id: id(2),
            score: 0.7,
            department_id: DT,
            days: 5
        },
        {
            document_id: id(3),
            score: 0.6,
            department_id: KTPM,
            days: 2.5
        }
    ];
    assert.deepEqual(readEvidence(messy), [
        {
            document_id: id(2),
            score: 0.8,
            department_id: null,
            days: null
        },
        {
            document_id: id(3),
            score: 0.6,
            department_id: KTPM,
            days: null
        }
    ]);
    for (const bad of [
        null,
        undefined,
        {},
        'chuỗi',
        3
    ])assert.deepEqual(readEvidence(bad), []);
    assert.deepEqual(evidenceIds(SAMPLE.evidence), [
        id(1),
        id(2),
        id(3),
        id(4)
    ]);
    assert.deepEqual(evidenceIds(messy), [
        id(2),
        id(3)
    ]);
});
test('trích yếu của căn cứ ≤ 80 ký tự, một dòng, NFC; không có số ký hiệu thì để trống', ()=>{
    const long = 'Về việc xét cấp học bổng khuyến khích học tập học kỳ II năm học 2026–2027 cho sinh viên các khóa đang học';
    const clipped = clipSummary(long);
    assert.equal(Array.from(clipped).length, 80);
    assert.ok(clipped.endsWith('…'));
    assert.ok(long.startsWith(clipped.slice(0, -1)));
    const exact = 'x'.repeat(80);
    assert.equal(clipSummary(exact), exact);
    assert.equal(clipSummary('  Về  việc\nhọc   bổng '), 'Về việc học bổng');
    assert.equal(clipSummary('Học bổng'.normalize('NFD')), 'Học bổng'.normalize('NFC'));
    assert.equal(clipSummary(null), '');
    const doc = new Map([
        [
            id(1),
            {
                symbol: '  ',
                summary: long
            }
        ]
    ]);
    const [e] = shownEvidence(SAMPLE.evidence, doc);
    assert.equal(e?.symbol, null);
    assert.equal(Array.from(e?.summary ?? '').length, 80);
});
test('"Dùng gợi ý" điền đơn vị và hạn; văn bản đã ghi hạn thì không đụng tới hạn', ()=>{
    assert.deepEqual(applyValues(SAMPLE, null), {
        department_id: DT,
        due_on: '2026-11-05'
    });
    assert.deepEqual(applyValues(SAMPLE, null, '2026-10-26'), {
        department_id: DT,
        due_on: '2026-11-05'
    });
    assert.deepEqual(applyValues(SAMPLE, '2026-11-20'), {
        department_id: DT,
        due_on: null
    });
    assert.deepEqual(applyValues(SAMPLE, null, '2026-11-06'), {
        department_id: DT,
        due_on: null
    });
    assert.deepEqual(applyValues(SAMPLE, null, '2026-11-05'), {
        department_id: DT,
        due_on: '2026-11-05'
    });
    assert.deepEqual(applyValues({
        ...SAMPLE,
        due_on: null
    }, null), {
        department_id: DT,
        due_on: null
    });
    assert.deepEqual(applyValues({
        ...SAMPLE,
        due_on: '05/11/2026'
    }, null), {
        department_id: DT,
        due_on: null
    });
    assert.equal(applyValues({
        ...SAMPLE,
        status: 'none',
        department_id: null
    }, null), null);
    assert.equal(applyValues({
        ...SAMPLE,
        status: 'failed',
        department_id: null
    }, null), null);
    assert.equal(applyValues({
        ...SAMPLE,
        department_id: null
    }, null), null);
    assert.equal(applyValues(null, null), null);
});
test('chip theo / khác gợi ý theo phòng chủ trì đang chọn; chưa chọn hay giao cho một người thì không có chip', ()=>{
    assert.equal(matchState(SAMPLE, DT), 'kept');
    assert.equal(matchState(SAMPLE, KTPM), 'changed');
    assert.equal(matchState(SAMPLE, null), null);
    assert.equal(matchState(SAMPLE, ''), null);
    assert.equal(matchState({
        ...SAMPLE,
        status: 'none',
        department_id: null
    }, DT), null);
    assert.equal(matchState(null, DT), null);
});
test('lý do không gợi ý: đủ sáu mã ở cả hai ngôn ngữ, mã lạ thì null', ()=>{
    assert.deepEqual([
        ...SUGGEST_REASONS
    ], [
        'no_similar',
        'no_history',
        'no_valid_unit',
        'low_confidence',
        'timeout',
        'unavailable'
    ]);
    for (const r of SUGGEST_REASONS){
        const key = reasonKey(r);
        assert.equal(key, `assign.suggest.reason.${r}`);
        assert.ok(lookup(vi, key), `vi ${key}`);
        assert.ok(lookup(en, key), `en ${key}`);
    }
    assert.equal(reasonKey('lạ'), null);
    assert.equal(reasonKey(null), null);
    assert.equal(reasonKey(undefined), null);
    assert.equal(tVi('assign.suggest.nothing', {
        reason: tVi(reasonKey('no_similar'))
    }), 'Không có gợi ý giao việc: chưa có văn bản tương tự đã giao.');
});
test('khóa ngôn ngữ của hợp đồng có ở vi.json và en.json, chữ tiếng Việt đúng như kịch bản demo', ()=>{
    const keys = [
        ...[
            'title',
            'searching',
            'unit',
            'due',
            'dueDays',
            'dueFromDocument',
            'evidence',
            'apply',
            'kept',
            'changed',
            'note'
        ].map((k)=>`assign.suggest.${k}`),
        ...[
            'high',
            'medium',
            'low'
        ].map((k)=>`assign.suggest.confidence.${k}`),
        ...[
            'suggested',
            'none',
            'failed'
        ].map((k)=>`assign.suggest.outcome.${k}`),
        'audit.agents.moc-assigner',
        'audit.action.assignment.suggested',
        ...[
            'outcome',
            'outcome_reason',
            'due_days',
            'confidence',
            'evidence',
            'candidates',
            'semantic',
            'duration_ms'
        ].map((k)=>`audit.col.${k}`)
    ];
    for (const messages of [
        vi,
        en
    ])for (const key of keys)assert.ok(lookup(messages, key), key);
    assert.equal(tVi('assign.suggest.title'), 'Gợi ý giao việc');
    assert.equal(tVi('assign.suggest.apply'), 'Dùng gợi ý');
    assert.equal(tVi('assign.suggest.kept'), 'Theo gợi ý');
    assert.equal(tVi('assign.suggest.changed'), 'Khác gợi ý');
    assert.equal(tVi('assign.suggest.confidence.high'), 'Tin cậy cao');
    assert.equal(tVi('audit.agents.moc-assigner'), 'Tác tử gợi ý giao việc');
    assert.equal(tVi('audit.action.assignment.suggested'), 'Gợi ý giao việc');
    assert.equal(tVi('assign.suggest.note'), 'Tác tử chỉ gợi ý, lãnh đạo quyết định. Gợi ý đã ghi vào sổ kiểm toán.');
    assert.equal(tVi('assign.suggest.dueDays', {
        date: '05/11/2026',
        n: 10
    }, 10), '05/11/2026 (10 ngày, như các văn bản tương tự)');
    assert.equal(tVi('assign.suggest.evidence', {
        n: 4
    }, 4), 'Căn cứ: 4 văn bản tương tự đã giao');
    assert.equal(tEn('assign.suggest.days', {
        n: 1
    }, 1), '1 day');
    assert.equal(tEn('assign.suggest.days', {
        n: 7
    }, 7), '7 days');
    assert.equal(tEn('assign.suggest.evidence', {
        n: 1
    }, 1), 'Based on 1 similar document assigned before');
});
test('khối gợi ý không có nhãn trùng tên ô của form chỉ đạo, không dựng HTML, nút không gửi form', ()=>{
    const vue = source('../app/components/AssignSuggestion.vue');
    const template = vue.slice(vue.indexOf('<template>'));
    assert.doesNotMatch(template, /<label\b/);
    assert.doesNotMatch(template, /aria-label(ledby)?\s*=/);
    assert.doesNotMatch(vue, /v-html/);
    const buttons = [
        ...template.matchAll(/<button\b[^>]*>/g)
    ].map((m)=>m[0]);
    assert.ok(buttons.length >= 1);
    for (const b of buttons)assert.match(b, /type="button"/);
    assert.match(template, /aria-live="polite"/);
    assert.match(template, /motion-safe:/);
    const forbidden = [
        'phòng chủ trì',
        'hạn xử lý',
        'ý kiến chỉ đạo'
    ];
    for (const messages of [
        vi
    ]){
        const block = JSON.stringify(messages.assign.suggest).toLowerCase();
        for (const word of forbidden)assert.ok(!block.includes(word), word);
    }
});
test('form chỉ đạo: khối gợi ý đứng đầu form, không hiện cho văn bản hạn chế', ()=>{
    const panel = source('../app/components/TaskPanel.vue');
    const form = panel.slice(panel.indexOf(`<form v-if="formKey === 'vbden.chiDao'"`));
    const block = form.indexOf('<AssignSuggestion');
    assert.ok(block > 0 && block < form.indexOf('id="instruction"'));
    assert.match(form.slice(block, form.indexOf('/>', block)), /v-if="!restricted"/);
});
test('khóa i18n viết thẳng trong khối gợi ý giao việc đều có trong vi.json', ()=>{
    const files = [
        '../app/components/AssignSuggestion.vue',
        '../app/utils/assignSuggest.js'
    ];
    let checked = 0;
    for (const file of files){
        const code = source(file);
        for (const m of code.matchAll(/\bt\('([\w.-]+)'/g)){
            assert.ok(lookup(vi, m[1]) !== undefined, `${file}: thiếu khóa ${m[1]}`);
            checked++;
        }
    }
    assert.ok(checked >= 10, `chỉ thấy ${checked} khóa`);
    for (const k of [
        'high',
        'medium',
        'low'
    ])assert.ok(lookup(vi, `assign.suggest.confidence.${k}`));
    for (const k of [
        'kept',
        'changed'
    ])assert.ok(lookup(vi, `assign.suggest.${k}`));
});
