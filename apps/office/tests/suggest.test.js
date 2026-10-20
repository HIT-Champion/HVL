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
import { test } from 'node:test';
const { READ_KEYS, acceptOffer, applySuggestion, openOffer, tagState } = await import('../app/utils/suggest.js');
const DEFAULTS = {
    type_code: 'CV',
    urgency: 'normal'
};
const OPTS = {
    types: [
        'CV',
        'QĐ',
        'TB',
        'KH'
    ],
    urgencies: [
        'normal',
        'khan',
        'thuong_khan',
        'hoa_toc'
    ]
};
const blank = ()=>({
        type_code: 'CV',
        symbol: '',
        issued_on: '',
        issuer_name: '',
        summary: '',
        urgency: 'normal'
    });
const high = (value)=>({
        value,
        confidence: 'high',
        source: 'rule'
    });
const medium = (value)=>({
        value,
        confidence: 'medium',
        source: 'rule'
    });
const low = (value)=>({
        value,
        confidence: 'low',
        source: 'rule'
    });
const SAMPLE = {
    file_id: '2b0c',
    status: 'ok',
    method: 'text',
    pages: 1,
    fields: {
        symbol: {
            value: '123/QĐ-UBND',
            confidence: 'high',
            source: 'rule'
        },
        issued_on: {
            value: '2026-10-15',
            confidence: 'high',
            source: 'rule'
        },
        issuer_name: {
            value: 'Ủy ban nhân dân tỉnh Mẫu',
            confidence: 'medium',
            source: 'rule'
        },
        type_code: {
            value: 'QĐ',
            confidence: 'high',
            source: 'rule'
        },
        urgency: {
            value: 'khan',
            confidence: 'high',
            source: 'rule'
        },
        summary: {
            value: 'Quyết định ban hành Quy chế làm việc',
            confidence: 'medium',
            source: 'model'
        }
    },
    warnings: [
        'future_date'
    ],
    summary_source: 'model',
    model: 'qwen3:1.7b',
    duration_ms: 8123,
    cached: false,
    read_at: '2026-10-21T08:00:00Z'
};
test('form trống: điền đủ sáu ô của kết quả mẫu, kể cả loại CV và độ khẩn Thường đang để mặc định', ()=>{
    const out = applySuggestion(blank(), DEFAULTS, {}, SAMPLE, OPTS);
    assert.deepEqual(out.values, {
        type_code: 'QĐ',
        symbol: '123/QĐ-UBND',
        issued_on: '2026-10-15',
        issuer_name: 'Ủy ban nhân dân tỉnh Mẫu',
        summary: 'Quyết định ban hành Quy chế làm việc',
        urgency: 'khan'
    });
    assert.deepEqual([
        ...out.filled
    ].sort(), [
        ...READ_KEYS
    ].sort());
    assert.deepEqual(out.offers, {});
    assert.equal(out.suggested.summary?.source, 'model');
});
test('không bao giờ ghi đè chữ văn thư đã gõ: mọi ô × độ tin cậy × nguồn × kiểu chữ', ()=>{
    const typed = {
        type_code: [
            'TB',
            'KH'
        ],
        urgency: [
            'khan',
            'hoa_toc'
        ],
        issued_on: [
            '2026-01-02',
            '2025-12-31'
        ],
        symbol: [
            '12/TB-ĐHM',
            ' 12/TB '
        ],
        issuer_name: [
            'Sở Tài chính',
            'x'
        ],
        summary: [
            'Về việc khác hẳn',
            'Một dòng\nhai dòng'
        ]
    };
    const suggestions = {
        type_code: 'QĐ',
        urgency: 'thuong_khan',
        issued_on: '2026-10-15',
        symbol: '123/QĐ-UBND',
        issuer_name: 'Ủy ban nhân dân tỉnh Mẫu',
        summary: 'Quyết định ban hành Quy chế'
    };
    let cases = 0;
    for (const key of READ_KEYS){
        for (const mine of typed[key]){
            for (const confidence of [
                'high',
                'medium',
                'low'
            ]){
                for (const source of [
                    'rule',
                    'model'
                ]){
                    for (const previous of [
                        {},
                        {
                            [key]: high(`${suggestions[key]}-cu`)
                        }
                    ]){
                        const form = {
                            ...blank(),
                            [key]: mine
                        };
                        const out = applySuggestion(form, DEFAULTS, previous, {
                            fields: {
                                [key]: {
                                    value: suggestions[key],
                                    confidence,
                                    source
                                }
                            }
                        }, OPTS);
                        assert.equal(out.values[key], undefined, `${key}=${JSON.stringify(mine)} bị ghi đè (${confidence}, ${source})`);
                        assert.ok(!out.filled.includes(key));
                        cases++;
                    }
                }
            }
        }
    }
    assert.equal(cases, 6 * 2 * 3 * 2 * 2);
});
test('ô văn thư đã chạm không bao giờ tự đổi, kể cả khi giá trị trong ô còn trống hoặc bằng mặc định', ()=>{
    let cases = 0;
    for (const key of READ_KEYS){
        const base = DEFAULTS[key] ?? '';
        const suggestion = {
            type_code: 'QĐ',
            urgency: 'khan',
            issued_on: '2026-10-15'
        }[key] ?? 'Giá trị đọc được';
        for (const [current, previous] of [
            [
                base,
                {}
            ],
            [
                '  ',
                {}
            ],
            [
                'Giá trị tác tử',
                {
                    [key]: high('Giá trị tác tử')
                }
            ]
        ]){
            for (const confidence of [
                'high',
                'medium',
                'low'
            ]){
                for (const source of [
                    'rule',
                    'model'
                ]){
                    const form = {
                        ...blank(),
                        [key]: current
                    };
                    const out = applySuggestion(form, DEFAULTS, previous, {
                        fields: {
                            [key]: {
                                value: suggestion,
                                confidence,
                                source
                            }
                        }
                    }, {
                        ...OPTS,
                        touched: [
                            key
                        ]
                    });
                    assert.equal(out.values[key], undefined, `${key}=${JSON.stringify(current)} đã chạm mà bị đổi (${confidence}, ${source})`);
                    assert.ok(!out.filled.includes(key));
                    assert.deepEqual(out.offers[key], suggestion === current ? undefined : {
                        value: suggestion,
                        confidence,
                        source
                    });
                    cases++;
                }
            }
        }
        const kept = applySuggestion({
            ...blank(),
            [key]: 'Giá trị tác tử'
        }, DEFAULTS, {
            [key]: high('Giá trị tác tử')
        }, {
            fields: {}
        }, {
            touched: [
                key
            ]
        });
        assert.equal(kept.values[key], undefined);
        const removed = applySuggestion({
            ...blank(),
            [key]: 'Giá trị tác tử'
        }, DEFAULTS, {
            [key]: high('Giá trị tác tử')
        }, null, {
            touched: [
                key
            ]
        });
        assert.equal(removed.values[key], undefined);
    }
    assert.equal(cases, 6 * 3 * 3 * 2);
    const out = applySuggestion(blank(), DEFAULTS, {}, SAMPLE, {
        ...OPTS,
        touched: [
            'issued_on',
            'type_code'
        ]
    });
    assert.deepEqual(Object.keys(out.values).sort(), [
        'issuer_name',
        'summary',
        'symbol',
        'urgency'
    ]);
    assert.deepEqual(Object.keys(out.offers).sort(), [
        'issued_on',
        'type_code'
    ]);
});
test('đọc lại tệp nguồn khi văn thư đang ở trong ô tác tử điền: không đổi ô đó, giữ nhãn, kết quả mới chỉ đưa ra', ()=>{
    const form = blank();
    const first = applySuggestion(form, DEFAULTS, {}, SAMPLE, OPTS);
    Object.assign(form, first.values);
    const again = applySuggestion(form, DEFAULTS, first.suggested, {
        fields: {
            symbol: high('124/QĐ-UBND'),
            issued_on: high('2026-10-16')
        }
    }, {
        ...OPTS,
        touched: [
            'symbol',
            'urgency'
        ]
    });
    assert.equal(again.values.symbol, undefined);
    assert.equal(tagState(again.suggested.symbol, form.symbol), 'high');
    assert.deepEqual(again.offers.symbol, high('124/QĐ-UBND'));
    assert.equal(again.values.urgency, undefined);
    assert.equal(tagState(again.suggested.urgency, form.urgency), 'high');
    assert.equal(again.values.issued_on, '2026-10-16');
    assert.equal(again.values.type_code, 'CV');
});
test('đọc tệp khác tệp nguồn (vd phụ lục): không điền, không đưa ô nào về mặc định, giữ nhãn, chỉ đưa ra gợi ý', ()=>{
    const form = blank();
    const main = applySuggestion(form, DEFAULTS, {}, SAMPLE, OPTS);
    Object.assign(form, main.values);
    const before = {
        ...form
    };
    const annex = applySuggestion(form, DEFAULTS, main.suggested, {
        fields: {
            symbol: high('01/PL-UBND'),
            summary: low('Phụ lục danh sách đơn vị'),
            issued_on: high('2026-10-15')
        }
    }, {
        ...OPTS,
        offerOnly: true
    });
    assert.deepEqual(annex.values, {});
    assert.deepEqual(annex.filled, []);
    assert.deepEqual(annex.suggested, main.suggested);
    assert.deepEqual(annex.offers, {
        symbol: high('01/PL-UBND'),
        summary: low('Phụ lục danh sách đơn vị')
    });
    assert.deepEqual(form, before);
    assert.deepEqual(applySuggestion(form, DEFAULTS, main.suggested, {
        fields: {}
    }, {
        offerOnly: true
    }).values, {});
    const empty = applySuggestion(blank(), DEFAULTS, {}, SAMPLE, {
        ...OPTS,
        offerOnly: true
    });
    assert.deepEqual(empty.values, {});
    assert.equal(Object.keys(empty.offers).length, 6);
    assert.deepEqual(applySuggestion(blank(), DEFAULTS, {}, {
        fields: {
            type_code: high('CV')
        }
    }, {
        offerOnly: true
    }).offers, {});
    const used = acceptOffer(annex.suggested, annex.offers, 'symbol');
    assert.equal(used?.value, '01/PL-UBND');
    assert.equal(tagState(used?.suggested.symbol, '01/PL-UBND'), 'high');
});
test('ô văn thư đã gõ mà gợi ý khác: đưa ra "Gợi ý: … [Dùng]", không điền', ()=>{
    const form = {
        ...blank(),
        symbol: '45/TB-ĐHM'
    };
    const out = applySuggestion(form, DEFAULTS, {}, {
        fields: {
            symbol: high('123/QĐ-UBND')
        }
    }, OPTS);
    assert.deepEqual(out.values, {});
    assert.deepEqual(out.offers.symbol, high('123/QĐ-UBND'));
    assert.equal(out.suggested.symbol, undefined);
    const same = applySuggestion({
        ...blank(),
        symbol: '123/QĐ-UBND'
    }, DEFAULTS, {}, {
        fields: {
            symbol: high('123/QĐ-UBND')
        }
    }, OPTS);
    assert.deepEqual(same.values, {});
    assert.deepEqual(same.offers, {});
    assert.equal(tagState(same.suggested.symbol, '123/QĐ-UBND'), 'high');
});
test('ô trống hoặc chỉ có khoảng trắng, ô bằng mặc định: coi là trống', ()=>{
    const form = {
        ...blank(),
        symbol: '   ',
        summary: '\n '
    };
    const out = applySuggestion(form, DEFAULTS, {}, {
        fields: {
            symbol: high('07/CV-ĐHCN'),
            summary: high('Về việc cử cán bộ dự hội thảo'),
            type_code: medium('CV'),
            urgency: high('hoa_toc')
        }
    }, OPTS);
    assert.deepEqual(out.values, {
        symbol: '07/CV-ĐHCN',
        summary: 'Về việc cử cán bộ dự hội thảo',
        urgency: 'hoa_toc'
    });
    assert.ok(out.filled.includes('type_code'));
    assert.equal(tagState(out.suggested.type_code, 'CV'), 'medium');
});
test('độ tin cậy thấp: không điền, chỉ đưa ra; bấm Dùng thì ô nhận giá trị và mang nhãn Gợi ý', ()=>{
    const form = blank();
    const out = applySuggestion(form, DEFAULTS, {}, {
        fields: {
            summary: low('Kính gửi các đơn vị trực thuộc về việc báo cáo'),
            issued_on: low('2027-01-05')
        }
    }, OPTS);
    assert.deepEqual(out.values, {});
    assert.deepEqual(out.filled, []);
    assert.deepEqual(Object.keys(out.offers).sort(), [
        'issued_on',
        'summary'
    ]);
    const used = acceptOffer(out.suggested, out.offers, 'summary');
    assert.ok(used);
    assert.equal(used.value, 'Kính gửi các đơn vị trực thuộc về việc báo cáo');
    assert.ok(used.suggested.summary && !used.offers.summary && used.offers.issued_on);
    assert.equal(acceptOffer(used.suggested, used.offers, 'summary'), null);
    const same = applySuggestion(blank(), DEFAULTS, {}, {
        fields: {
            type_code: low('CV')
        }
    }, OPTS);
    assert.deepEqual(same.suggested, {});
    assert.deepEqual(same.offers, {});
});
test('đọc lại không đè ô đã sửa; ô tác tử điền mà văn thư chưa sửa thì nhận kết quả mới', ()=>{
    const form = blank();
    const first = applySuggestion(form, DEFAULTS, {}, SAMPLE, OPTS);
    Object.assign(form, first.values);
    form.symbol = '123/QĐ-UBND-SUA';
    form.issuer_name = 'UBND tỉnh Mẫu';
    assert.equal(tagState(first.suggested.symbol, form.symbol), 'edited');
    assert.equal(tagState(first.suggested.issued_on, form.issued_on), 'high');
    assert.equal(tagState(first.suggested.summary, form.summary), 'model');
    const again = applySuggestion(form, DEFAULTS, first.suggested, {
        fields: {
            symbol: high('123/QĐ-UBND'),
            issuer_name: high('Ủy ban nhân dân tỉnh Mẫu'),
            issued_on: high('2026-10-16'),
            type_code: high('QĐ'),
            summary: low('Quyết định ban hành quy chế')
        }
    }, OPTS);
    assert.equal(again.values.symbol, undefined);
    assert.equal(again.values.issuer_name, undefined);
    assert.equal(again.values.issued_on, '2026-10-16');
    assert.equal(again.values.urgency, 'normal');
    assert.equal(again.values.summary, '');
    assert.deepEqual(again.offers.summary, low('Quyết định ban hành quy chế'));
    assert.equal(again.values.type_code, undefined);
    assert.ok(again.filled.includes('type_code'));
    assert.equal(tagState(again.suggested.symbol, form.symbol), 'edited');
    assert.equal(again.offers.symbol, undefined);
    const fixed = applySuggestion({
        ...form,
        symbol: '123/QĐ-UBND'
    }, DEFAULTS, first.suggested, {
        fields: {
            symbol: high('123/QĐ-UBND')
        }
    }, OPTS);
    assert.equal(fixed.values.symbol, undefined);
    assert.equal(tagState(fixed.suggested.symbol, '123/QĐ-UBND'), 'high');
});
test('gỡ tệp đã đọc: ô tác tử điền chưa sửa về mặc định, ô văn thư đã sửa hoặc tự gõ giữ nguyên', ()=>{
    const form = blank();
    const first = applySuggestion(form, DEFAULTS, {}, SAMPLE, OPTS);
    Object.assign(form, first.values);
    form.summary = 'Về việc văn thư tự viết lại trích yếu';
    const out = applySuggestion(form, DEFAULTS, first.suggested, null, OPTS);
    assert.deepEqual(out.values, {
        type_code: 'CV',
        symbol: '',
        issued_on: '',
        issuer_name: '',
        urgency: 'normal'
    });
    assert.deepEqual(out.suggested, {});
    assert.deepEqual(out.offers, {});
});
test('gợi ý không dùng được thì bỏ: mã loại ngoài danh mục, độ khẩn lạ, ngày sai dạng, khóa lạ, giá trị rỗng', ()=>{
    const out = applySuggestion(blank(), DEFAULTS, {}, {
        fields: {
            type_code: high('XYZ'),
            urgency: high('rat_khan'),
            issued_on: high('15/10/2026'),
            symbol: high('   '),
            summary: {
                value: 42,
                confidence: 'high',
                source: 'rule'
            },
            issuer_name: {
                value: 'Sở Mẫu',
                confidence: 'chac'
            },
            body: high('không phải trường của form')
        }
    }, OPTS);
    assert.deepEqual(out, {
        values: {},
        filled: [],
        suggested: {},
        offers: {}
    });
    for (const day of [
        '2026-13-01',
        '2026-02-31',
        '2026-00-10',
        '2026-10-32'
    ]){
        assert.deepEqual(applySuggestion(blank(), DEFAULTS, {}, {
            fields: {
                issued_on: high(day)
            }
        }, OPTS).values, {}, day);
    }
    assert.equal(applySuggestion(blank(), DEFAULTS, {}, {
        fields: {
            issued_on: high('2028-02-29')
        }
    }, OPTS).values.issued_on, '2028-02-29');
    assert.equal(applySuggestion(blank(), DEFAULTS, {}, {
        fields: {
            type_code: high('XYZ')
        }
    }).values.type_code, 'XYZ');
});
test('giá trị gợi ý được chuẩn hóa NFC, bỏ khoảng trắng đầu cuối', ()=>{
    const decomposed = 'Ủy ban nhân dân tỉnh Mẫu'.normalize('NFD');
    const out = applySuggestion(blank(), DEFAULTS, {}, {
        fields: {
            issuer_name: medium(` ${decomposed} `)
        }
    }, OPTS);
    assert.equal(out.values.issuer_name, 'Ủy ban nhân dân tỉnh Mẫu'.normalize('NFC'));
});
test('nhãn cạnh ô và gợi ý còn hiện', ()=>{
    assert.equal(tagState(undefined, 'x'), null);
    assert.equal(tagState(high('a'), 'a'), 'high');
    assert.equal(tagState(medium('a'), 'a'), 'medium');
    assert.equal(tagState({
        value: 'a',
        confidence: 'medium',
        source: 'model'
    }, 'a'), 'model');
    assert.equal(tagState({
        value: 'a',
        confidence: 'medium',
        source: 'model'
    }, 'b'), 'edited');
    const form = {
        ...blank(),
        symbol: '12/TB'
    };
    assert.equal(openOffer({
        symbol: high('12/TB')
    }, form, 'symbol'), undefined);
    assert.deepEqual(openOffer({
        symbol: high('13/TB')
    }, form, 'symbol'), high('13/TB'));
    assert.equal(openOffer({}, form, 'symbol'), undefined);
});
