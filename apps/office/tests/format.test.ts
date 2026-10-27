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


// Ngày giờ hiện theo giờ Việt Nam dù máy người dùng đặt múi giờ khác (review: fmtDate/fmtDateTime chưa đặt timeZone).

import assert from 'node:assert/strict'
import { test } from 'node:test'

process.env.TZ = 'America/Los_Angeles'   // máy ở múi giờ âm, có giờ mùa hè
const { addDays, dayOf, daysBetween, dueState, fmtDate, fmtDateTime, fmtMonth, fmtWeekday, initialOf, weekStart } =
  await import('../app/utils/format.ts')

test('ngày thuần (cột date) không lệch theo múi giờ của máy', () => {
  assert.equal(fmtDate('2026-10-20'), '20/10/2026')
  assert.equal(fmtDate(null), '—')
})

test('thời điểm hiện theo giờ Việt Nam', () => {
  // 18:30 UTC ngày 20 = 01:30 sáng 21 ở Việt Nam; ở Los Angeles vẫn là ngày 20
  assert.equal(fmtDate('2026-10-20T18:30:00Z'), '21/10/2026')
  assert.match(fmtDateTime('2026-10-20T18:30:00Z'), /^01:30,? 21\/10\/2026$/)
  assert.equal(dayOf('2026-10-20T18:30:00Z'), '2026-10-21')
})

test('cộng ngày qua tháng, qua năm, qua ngày đổi giờ mùa hè của máy', () => {
  assert.equal(addDays('2026-12-30', 3), '2027-01-02')
  assert.equal(addDays('2026-10-31', 1), '2026-11-01')
  assert.equal(addDays('2026-11-01', 1), '2026-11-02')
  assert.equal(addDays('2026-03-01', -1), '2026-02-28')
})

test('chữ đại diện: chữ đầu của tên, viết hoa; thiếu tên thì lấy từ cuối của họ tên', () => {
  assert.equal(initialOf('Giám khảo', 'Tài khoản Giám khảo'), 'G')
  assert.equal(initialOf('Thu', 'Trần Thị Thu'), 'T')
  assert.equal(initialOf('', 'Trần Thị thu'), 'T')
  assert.equal(initialOf('  đức ', ''), 'Đ')
  assert.equal(initialOf('', 'vanthu'), 'V')
  assert.equal(initialOf('', ''), '?')
})

test('lịch hạn: tuần bắt đầu từ Thứ Hai, đếm ngày qua tháng, hạn so với hôm nay', () => {
  assert.equal(weekStart('2026-10-26'), '2026-10-26')
  assert.equal(weekStart('2026-11-01'), '2026-10-26')
  assert.equal(weekStart('2026-10-31'), '2026-10-26')
  assert.equal(daysBetween('2026-10-26', '2026-11-03'), 8)
  assert.equal(daysBetween('2026-10-26', '2026-10-24'), -2)
  assert.deepEqual(dueState('2026-10-24', '2026-10-26'), { tone: 'over', n: 2 })
  assert.deepEqual(dueState('2026-10-26', '2026-10-26'), { tone: 'today', n: 0 })
  assert.deepEqual(dueState('2026-10-28', '2026-10-26'), { tone: 'soon', n: 2 })
  assert.deepEqual(dueState('2026-10-31', '2026-10-26'), { tone: 'ok', n: 5 })
})

test('lịch hạn: tên thứ, tháng theo ngôn ngữ, không lệch theo múi giờ của máy', () => {
  assert.equal(fmtWeekday('2026-10-31', 'vi'), 'Thứ Bảy')
  assert.equal(fmtWeekday('2026-10-31', 'vi', 'short'), 'T7')
  assert.equal(fmtWeekday('2026-11-01', 'vi', 'short'), 'CN')
  assert.equal(fmtWeekday('2026-10-31', 'en'), 'Saturday')
  assert.equal(fmtWeekday('2026-10-31', 'en', 'short'), 'Sat')
  assert.equal(fmtMonth('2026-10-31', 'vi', '2026'), 'tháng 10')
  assert.equal(fmtMonth('2027-01-04', 'vi', '2026'), 'tháng 1 năm 2027')
  assert.equal(fmtMonth('2026-10-31', 'en', '2026'), 'October')
})
