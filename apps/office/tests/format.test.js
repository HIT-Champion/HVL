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
process.env.TZ = 'America/Los_Angeles';
const { addDays, fmtDate, fmtDateTime, initialOf } = await import('../app/utils/format.js');
test('ngày thuần (cột date) không lệch theo múi giờ của máy', ()=>{
    assert.equal(fmtDate('2026-10-20'), '20/10/2026');
    assert.equal(fmtDate(null), '—');
});
test('thời điểm hiện theo giờ Việt Nam', ()=>{
    assert.equal(fmtDate('2026-10-20T18:30:00Z'), '21/10/2026');
    assert.match(fmtDateTime('2026-10-20T18:30:00Z'), /^01:30,? 21\/10\/2026$/);
});
test('cộng ngày qua tháng, qua năm, qua ngày đổi giờ mùa hè của máy', ()=>{
    assert.equal(addDays('2026-12-30', 3), '2027-01-02');
    assert.equal(addDays('2026-10-31', 1), '2026-11-01');
    assert.equal(addDays('2026-11-01', 1), '2026-11-02');
    assert.equal(addDays('2026-03-01', -1), '2026-02-28');
});
test('chữ đại diện: chữ đầu của tên, viết hoa; thiếu tên thì lấy từ cuối của họ tên', ()=>{
    assert.equal(initialOf('Giám khảo', 'Tài khoản Giám khảo'), 'G');
    assert.equal(initialOf('Thu', 'Trần Thị Thu'), 'T');
    assert.equal(initialOf('', 'Trần Thị thu'), 'T');
    assert.equal(initialOf('  đức ', ''), 'Đ');
    assert.equal(initialOf('', 'vanthu'), 'V');
    assert.equal(initialOf('', ''), '?');
});
