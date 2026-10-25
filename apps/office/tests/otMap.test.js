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

// Sơ đồ cảm biến kho (/cam-bien, F3.10): tô màu theo số đo so với ngưỡng (đúng luật subscription: vượt là > ngưỡng),
// cờ chất lượng svc-workflow trả về làm phòng "không tin được", phòng nhiều cảm biến lấy mức nặng nhất, cảm biến
// ngoài sơ đồ; sơ đồ mẫu không chồng phòng; đủ chữ hai thứ tiếng; trang chỉ gọi Action otSensorMap (không gọi thẳng
// broker, không tải gì ngoài), mục thanh bên đúng các vai trò có quyền Action trong db/metadata/actions.yaml.

import assert from 'node:assert/strict';
import { allNavigation } from '../app/utils/navigation.js';
import { readSource as readFileSync } from './source.mjs';
import { test } from 'node:test';

const {
  FLAG_ORDER, LEVEL_ORDER, LEVEL_TONE, NEAR_BAND, PLAN, doorOf, fmtTemp, knownFlags, placeSensors, roomLevel,
  sensorLevel
} = await import('../app/utils/otMap.js');
const { corridor: PLAN_CORRIDOR, outline: PLAN_OUTLINE, rooms: PLAN_ROOMS, view: PLAN_VIEW } = PLAN;


const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const vi = JSON.parse(read('../app/locales/vi.json'));
const en = JSON.parse(read('../app/locales/en.json'));
function lookup(messages, key) {
  let node = messages;
  for (const part of key.split('.')) node = typeof node === 'object' ? node[part] : undefined;
  return typeof node === 'string' ? node : undefined;
}

const sensor = (id, value, room = null, flags = []) => (
{ id: `urn:ngsi-ld:TemperatureSensor:${id}`, room, name: id, value, observed_at: null, flags });

test('mức của một cảm biến: vượt là lớn hơn ngưỡng (như q của subscription), dải gần ngưỡng 2 °C', () => {
  assert.equal(NEAR_BAND, 2);
  const at = (value, flags = []) => sensorLevel({ value, flags }, 35);
  assert.equal(at(35.1), 'over');
  assert.equal(at(35), 'near'); // bằng ngưỡng: chưa vượt, chưa có dự thảo
  assert.equal(at(33.1), 'near');
  assert.equal(at(33), 'normal');
  assert.equal(at(-10), 'normal');
  assert.equal(at(null), 'unknown');
  // mất tín hiệu, ngoài dải: số không tin được, không tô theo số dù số vượt ngưỡng
  assert.equal(at(41, ['stale']), 'unknown');
  assert.equal(at(-127, ['out_of_range']), 'unknown');
  // trùng giờ đo: vẫn tô theo số, chỉ thêm dấu cờ
  assert.equal(at(41, ['duplicate_time']), 'over');
  assert.equal(at(20, ['cờ-mới-chưa-biết']), 'normal');
  assert.equal(sensorLevel({ value: 30, flags: [] }, 37.5), 'normal');
  assert.equal(sensorLevel({ value: 36, flags: [] }, 37.5), 'near');
});

test('mức của một phòng: nặng nhất trong các cảm biến tin được; không có cảm biến là trống', () => {
  const s = (value, flags = []) => ({ value, flags });
  assert.equal(roomLevel([], 35), 'empty');
  assert.equal(roomLevel([s(20), s(41)], 35), 'over');
  assert.equal(roomLevel([s(20), s(34)], 35), 'near');
  assert.equal(roomLevel([s(20), s(41, ['stale'])], 35), 'normal'); // một cảm biến còn tin được
  assert.equal(roomLevel([s(null), s(41, ['stale'])], 35), 'unknown');
  assert.deepEqual(LEVEL_ORDER, ['over', 'near', 'normal', 'unknown', 'empty']);
  assert.deepEqual(Object.keys(LEVEL_TONE).sort(), [...LEVEL_ORDER].sort());
});

test('gắn cảm biến vào phòng theo mã; mã lạ hay không có mã thì ra ngoài sơ đồ; cờ gộp theo thứ tự', () => {
  const placed = placeSensors({
    threshold: 35,
    sensors: [
    sensor('kho-1a', 21, 'kho-1'), sensor('kho-1b', 34, 'kho-1', ['duplicate_time']),
    sensor('kho-2', -127, 'kho-2', ['out_of_range', 'stale']), sensor('may-chu', 41, 'may-chu'),
    sensor('hanh-lang', 22), sensor('tang-2', 22, 'kho-9')]

  });
  const room = (code) => placed.rooms.find((r) => r.room.code === code);
  assert.deepEqual(placed.rooms.map((r) => r.room.code), PLAN_ROOMS.map((r) => r.code));
  assert.deepEqual(room('kho-1').sensors.map((s) => s.name), ['kho-1a', 'kho-1b']);
  assert.equal(room('kho-1').level, 'near');
  assert.deepEqual(room('kho-1').flags, ['duplicate_time']);
  assert.equal(room('kho-2').level, 'unknown');
  assert.deepEqual(room('kho-2').flags, ['stale', 'out_of_range']);
  assert.equal(room('may-chu').level, 'over');
  assert.equal(room('kho-3').level, 'empty');
  assert.deepEqual(placed.outside.map((s) => s.name), ['hanh-lang', 'tang-2']);
  assert.deepEqual(knownFlags(['duplicate_time', 'x', 'stale', 'stale']), ['stale', 'duplicate_time']);
  assert.deepEqual(FLAG_ORDER, ['stale', 'out_of_range', 'duplicate_time', 'future_time']);
});

test('sơ đồ mẫu: phòng trong khung nhà, không chồng nhau, không đè hành lang; cửa nằm trên cạnh giáp hành lang', () => {
  const inside = (a, b) =>
  a.x >= b.x && a.y >= b.y && a.x + a.w <= b.x + b.w && a.y + a.h <= b.y + b.h;
  const overlap = (a, b) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  assert.ok(inside(PLAN_OUTLINE, { x: 0, y: 0, w: PLAN_VIEW.width, h: PLAN_VIEW.height }));
  assert.ok(inside(PLAN_CORRIDOR, PLAN_OUTLINE));
  const codes = PLAN_ROOMS.map((r) => r.code);
  assert.equal(new Set(codes).size, codes.length);
  for (const r of PLAN_ROOMS) {
    // cùng luật mã phòng với svc-workflow (_ROOM trong ot.py) và sensor.py --room
    assert.match(r.code, /^[a-z0-9-]{1,40}$/);
    assert.ok(inside(r, PLAN_OUTLINE), r.code);
    assert.ok(!overlap(r, PLAN_CORRIDOR), r.code);
    for (const o of PLAN_ROOMS) if (o !== r) assert.ok(!overlap(r, o), `${r.code} chồng ${o.code}`);
    const door = doorOf(r);
    const wall = r.door === 'top' ? r.y : r.y + r.h;
    assert.equal(door.y1, wall);
    assert.ok(door.x1 > r.x && door.x2 < r.x + r.w);
    // cạnh có cửa chạm hành lang (cách 10 đơn vị)
    assert.equal(r.door === 'top' ? r.y - (PLAN_CORRIDOR.y + PLAN_CORRIDOR.h) : PLAN_CORRIDOR.y - (r.y + r.h), 10);
  }
});

test('nhiệt độ theo ngôn ngữ', () => {
  assert.equal(fmtTemp(22.5, 'vi'), '22,5 °C');
  assert.equal(fmtTemp(22.5, 'en'), '22.5 °C');
  assert.equal(fmtTemp(41.25, 'vi'), '41,3 °C');
  assert.equal(fmtTemp(-127, 'en'), '-127 °C');
  assert.equal(fmtTemp(null, 'vi'), '—');
  assert.equal(fmtTemp(Number.NaN, 'vi'), '—');
});

test('đủ chữ hai thứ tiếng cho mọi phòng, mức, cờ, trạng thái của trang', () => {
  const keys = ['nav.sensors', 'sensors.title', 'sensors.subtitle', 'sensors.forbidden', 'sensors.off',
  'sensors.offHint.off', 'sensors.offHint.unavailable', 'sensors.plan', 'sensors.planLabel', 'sensors.corridor',
  'sensors.checkedAt', 'sensors.outside', 'sensors.outsideHint', 'sensors.count', 'sensors.legend',
  'sensors.threshold', 'sensors.flags', 'sensors.flagsNote', 'sensors.table', 'sensors.colRoom', 'sensors.colSensor',
  'sensors.colValue', 'sensors.colAt', 'sensors.colFlags', 'sensors.none', 'sensors.note',
  ...PLAN_ROOMS.map((r) => `sensors.room.${r.code}`),
  ...LEVEL_ORDER.flatMap((l) => [`sensors.level.${l}`, `sensors.levelHint.${l}`]),
  ...FLAG_ORDER.flatMap((f) => [`sensors.flag.${f}`, `sensors.flagHint.${f}`])];
  for (const key of keys) {
    assert.ok(lookup(vi, key), `vi thiếu ${key}`);
    assert.ok(lookup(en, key), `en thiếu ${key}`);
  }
  // chữ dùng tham số đúng tên trang truyền vào
  assert.match(lookup(vi, 'sensors.flagHint.stale'), /\{n\}/);
  assert.match(lookup(en, 'sensors.flagHint.out_of_range'), /\{min\}.*\{max\}/);
  for (const messages of [vi, en]) {
    for (const key of keys) assert.doesNotMatch(lookup(messages, key), /[|@$]/, `${key}: ký tự đặc biệt của vue-i18n`);
  }
});

test('trang chỉ đọc qua Action otSensorMap, không gọi broker, không tải gì ngoài; báo rõ khi chưa bật cảm biến', () => {
  const page = read('../app/pages/cam-bien.vue');
  assert.match(page, /otSensorMap \{ status threshold stale_after_min range_min range_max checked_at/);
  assert.match(page, /sensors \{ id room name value observed_at flags \}/);
  assert.doesNotMatch(page, /fetch\(|XMLHttpRequest|new WebSocket|https?:\/\/(?!www\.apache\.org)/);
  assert.doesNotMatch(page, /<img|<image|<iframe/);
  assert.match(page, /data-testid="sensors-off"/);
  assert.match(page, /sensors\.offHint\.\$\{data\.status\}/);
});

test('mục thanh bên đúng các vai trò có quyền Action otSensorMap (db/metadata/actions.yaml)', () => {
  const roles = ['clerk', 'staff', 'manager', 'director', 'tenant_admin'].filter(role => allNavigation(role).some(item => item.to === '/cam-bien'));
  const meta = read('../../../db/metadata/actions.yaml');
  const block = /^ {2}- name: otSensorMap\n([\s\S]*?)(?=^ {2}- name: |^custom_types:)/m.exec(meta);
  assert.ok(block, 'thiếu Action otSensorMap');
  assert.deepEqual(roles, [...block[1].matchAll(/- role: (\w+)/g)].map((m) => m[1]));
  const page = read('../app/pages/cam-bien.vue');
  assert.match(page, new RegExp(`const ROLES = \\[${roles.map((r) => `'${r}'`).join(', ')}\\]`));
});


test('future sensor clocks retain the measured level but remain explicitly flagged', () => {
  assert.equal(sensorLevel({value:41,flags:['future_time']},35),'over');
  assert.equal(sensorLevel({value:41,flags:['future_time','stale']},35),'unknown');
  assert.deepEqual(knownFlags(['future_time','stale','future_time']),['stale','future_time']);
  for(const lang of ['vi','en']){
    const messages=JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`,import.meta.url),'utf8'));
    assert.ok(messages.sensors.flag.future_time);
    assert.match(messages.sensors.flagHint.future_time,/\{slack\}/);
  }
});
