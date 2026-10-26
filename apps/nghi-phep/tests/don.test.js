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

// Phần thuần của trang Đơn nghỉ phép (public/don.js, node --test, không cần trình duyệt), kèm kiểm khớp: formKey,
// process id ↔ app.yaml và BPMN; trường trang đọc ↔ forms/*.json; trang chỉ dựng form qua một hàm; màu đủ tương phản.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import {
  API, FORM_DON, FORM_DUYET, LOI, QUY_TRINH, docThan, docTraLoi, doiChieu, duong, ngayGio, sapXepDon, sapXepViec,
  soNgay, tenNguoi, trangThai, yeuCau,
} from '../public/don.js'

const APP = new URL('../', import.meta.url)
const ROOT = new URL('../../../', import.meta.url)
const read = (base, path) => readFileSync(new URL(path, base), 'utf8')

test('lời gọi API chung: đường, token, thân {"data": …}', () => {
  const [url, init] = yeuCau('tok', 'POST', duong.guiDon(), { loai: 'om' })
  assert.equal(url, '/api/workflow/nghi-phep/processes/nghi-phep.don')
  assert.equal(init.method, 'POST')
  assert.equal(init.headers.Authorization, 'Bearer tok')
  assert.equal(init.headers['Content-Type'], 'application/json')
  assert.deepEqual(JSON.parse(init.body), { data: { loai: 'om' } })
  const [list, get] = yeuCau('tok', 'GET', duong.viec())
  assert.equal(list, `${API}/tasks`)
  assert.equal(get.body, undefined)
  assert.equal(get.headers['Content-Type'], undefined)
  assert.equal(`${API}${duong.form(FORM_DUYET)}`, '/api/workflow/nghi-phep/forms/nghi-phep.duyet')
  assert.equal(duong.donCuaToi(), '/processes')
  // mã việc lạ không thoát ra khỏi đường
  assert.equal(duong.xongViec('a/../b?c'), '/tasks/a%2F..%2Fb%3Fc')
})

test('trả lời: 2xx là xong, 422 giữ lỗi từng trường, mã khác thành câu đọc được', () => {
  assert.deepEqual(docTraLoi(201, { id: 'p1' }), { ok: true, data: { id: 'p1' } })
  assert.deepEqual(docTraLoi(204, null), { ok: true, data: null })
  const bad = docTraLoi(422, { errors: { denNgay: 'x-moc-range' } })
  assert.equal(bad.ok, false)
  assert.deepEqual(bad.errors, { denNgay: 'x-moc-range' })
  assert.equal(bad.status, 422)
  for (const status of [401, 403, 404, 409, 429]) {
    assert.deepEqual(docTraLoi(status, { error: 'x' }), { ok: false, status, message: LOI[status] })
  }
  assert.equal(docTraLoi(503, null).message, LOI[500])
  assert.match(docTraLoi(418, null).message, /HTTP 418/)
  // 422 không mang lỗi từng trường (cổng, WAF) thì không giả làm lỗi của form
  for (const body of [null, { errors: [] }, { errors: 'sai' }, { detail: 'x' }]) {
    assert.equal(docTraLoi(422, body).errors, undefined, JSON.stringify(body))
  }
  assert.equal(docThan(''), null)
  assert.equal(docThan('<html>502</html>'), null)
  assert.deepEqual(docThan('{"id":"p1"}'), { id: 'p1' })
})

test('trạng thái đơn theo lúc kết thúc và quyết định của trưởng phòng', () => {
  assert.deepEqual(trangThai({ endedAt: null, data: {} }), { ma: 'cho', nhan: 'Chờ trưởng phòng duyệt' })
  // quyết định chưa chốt (quy trình còn chạy) thì vẫn là chờ
  assert.equal(trangThai({ endedAt: null, data: { quyetDinh: 'dong-y' } }).ma, 'cho')
  assert.deepEqual(trangThai({ endedAt: '2026-10-26T03:00:00Z', data: { quyetDinh: 'dong-y' } }),
    { ma: 'dong-y', nhan: 'Đã duyệt' })
  assert.equal(trangThai({ endedAt: '2026-10-26T03:00:00Z', data: { quyetDinh: 'tu-choi' } }).nhan, 'Bị từ chối')
  assert.equal(trangThai({ endedAt: '2026-10-26T03:00:00Z', data: null }).ma, 'xong')
  assert.equal(trangThai(undefined).ma, 'cho')
})

test('số ngày nghỉ tính cả hai đầu; ngày sai, ngược thì không có', () => {
  assert.equal(soNgay('2026-10-27', '2026-10-27'), 1)
  assert.equal(soNgay('2026-10-27', '2026-10-29'), 3)
  assert.equal(soNgay('2026-12-30', '2027-01-02'), 4)
  assert.equal(soNgay('2028-02-28', '2028-03-01'), 3)          // năm nhuận
  assert.equal(soNgay('2026-10-29', '2026-10-27'), null)
  assert.equal(soNgay('2026-02-30', '2026-03-01'), null)
  assert.equal(soNgay('27/10/2026', '2026-10-29'), null)
  assert.equal(soNgay(undefined, '2026-10-29'), null)
})

test('giờ Việt Nam; thứ tự đơn, thứ tự việc', () => {
  assert.equal(ngayGio('2026-10-26T07:05:00Z'), '26/10/2026 14:05')
  assert.equal(ngayGio('khong-phai-gio'), '')
  assert.equal(ngayGio(null), '')
  const don = [{ id: 'a', startedAt: '2026-10-20T01:00:00Z' }, { id: 'b', startedAt: '2026-10-25T01:00:00Z' },
    { id: 'c', startedAt: null }]
  assert.deepEqual(sapXepDon(don).map((d) => d.id), ['b', 'a', 'c'])
  assert.deepEqual(don.map((d) => d.id), ['a', 'b', 'c'])                    // không sửa mảng gốc
  const viec = [{ id: 'x', createdAt: '2026-10-25T01:00:00Z' }, { id: 'y', createdAt: '2026-10-20T01:00:00Z' }]
  assert.deepEqual(sapXepViec(viec).map((t) => t.id), ['y', 'x'])
})

test('làm mới việc cần duyệt: thêm việc mới, bỏ việc đã xong, giữ thẻ đang mở', () => {
  const moi = [{ id: 't3', createdAt: '2026-10-26T02:00:00Z' }, { id: 't1', createdAt: '2026-10-26T01:00:00Z' },
    { id: 't4', createdAt: '2026-10-26T00:00:00Z' }]
  assert.deepEqual(doiChieu(['t1', 't2'], moi), { them: [moi[2], moi[0]], bo: ['t2'] })
  assert.deepEqual(doiChieu([], []), { them: [], bo: [] })
  assert.deepEqual(doiChieu(['t1'], []), { them: [], bo: ['t1'] })
})

test('tên trong token có dấu tiếng Việt, token hỏng thì rỗng', () => {
  const part = Buffer.from(JSON.stringify({ name: 'Vũ Thị Mai', preferred_username: 'mai' })).toString('base64url')
  assert.equal(tenNguoi(`h.${part}.s`), 'Vũ Thị Mai')
  const only = Buffer.from(JSON.stringify({ preferred_username: 'mai' })).toString('base64url')
  assert.equal(tenNguoi(`h.${only}.s`), 'mai')
  for (const token of ['khong-phai-token', `h.${Buffer.from('[1]').toString('base64url')}.s`, undefined]) {
    assert.equal(tenNguoi(token), '')
  }
})

test('formKey, process id khớp app.yaml, BPMN và tệp form; trường trang đọc có trong form', () => {
  const manifest = read(APP, 'app.yaml')
  const keys = [...manifest.matchAll(/^ {4}(nghi-phep\.[a-z-]+): (\S+)$/gm)]
  const forms = Object.fromEntries(keys.map((m) => [m[1], m[2]]))
  assert.deepEqual(forms, { [FORM_DON]: 'forms/don.json', [FORM_DUYET]: 'forms/duyet.json' })
  assert.match(manifest, /^path: \/nghi-phep$/m)
  const bpmn = read(APP, 'workflow/don-nghi-phep.bpmn20.xml')
  assert.match(bpmn, new RegExp(`<process id="${QUY_TRINH.replace('.', '\\.')}"`))
  assert.match(bpmn, new RegExp(`<startEvent [^>]*flowable:formKey="${FORM_DON}"`))
  assert.match(bpmn, new RegExp(`<userTask [^>]*flowable:formKey="${FORM_DUYET}"`))
  const don = JSON.parse(read(APP, forms[FORM_DON]))
  const duyet = JSON.parse(read(APP, forms[FORM_DUYET]))
  for (const name of ['tuNgay', 'denNgay']) assert.ok(don.properties[name], `forms/don.json thiếu ${name}`)
  assert.deepEqual(duyet.properties.quyetDinh.enum, ['dong-y', 'tu-choi'])
  // nhánh của cổng rẽ đúng các giá trị quyết định của form
  const conditions = [...bpmn.matchAll(/\$\{quyetDinh == '([a-z-]+)'\}/g)].map((m) => m[1])
  assert.deepEqual(conditions.sort(), [...duyet.properties.quyetDinh.enum].sort())
})

test('trang không có script nội tuyến, không innerHTML; form chỉ dựng qua một hàm; đăng nhập đúng client', () => {
  const html = read(APP, 'public/index.html')
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/)
  assert.doesNotMatch(html, /\son[a-z]+=/i)
  for (const id of ['tieu-de-gui-don', 'tieu-de-don-cua-toi', 'tieu-de-viec-can-duyet']) {
    assert.match(html, new RegExp(`<h1 id="${id}" tabindex="-1">`))
  }
  assert.match(html, /role="status"/)
  assert.match(html, /role="alert"/)
  const app = read(APP, 'public/app.js')
  assert.doesNotMatch(app, /innerHTML|insertAdjacentHTML|document\.write/)
  assert.equal(app.match(/mountForm\(/g).length, 1, 'chỉ veForm() gọi mountForm')
  assert.equal(app.match(/summary\(/g).length, 1, 'chỉ tomTat() gọi summary')
  const auth = read(APP, 'public/auth.js')
  assert.match(auth, /const CALLBACK = '\/nghi-phep\/dang-nhap'/)
  assert.match(auth, /response_mode: 'fragment'/)
  assert.match(auth, /clientId: 'app-nghi-phep'/)
  const pkg = JSON.parse(read(APP, 'package.json'))
  const ref = JSON.parse(read(ROOT, 'apps/bang-tin/package.json'))
  assert.equal(pkg.dependencies['oidc-client-ts'], ref.dependencies['oidc-client-ts'])
})

function contrast(a, b) {
  const lum = (hex) => {
    const [r, g, bl] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl
  }
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

test('các cặp chữ/nền của style.css đạt WCAG AA (4,5:1)', () => {
  const css = read(APP, 'public/style.css')
  const v = Object.fromEntries([...css.matchAll(/--([a-z0-9-]+): (#[0-9a-f]{6});/g)].map((m) => [m[1], m[2]]))
  const pairs = [['stone-900', 'stone-50'], ['stone-600', 'stone-50'], ['stone-600', 'butter'], ['brand-800', 'butter'],
    ['red-700', 'red-50'], ['green-800', 'green-50'], ['amber-800', 'amber-50'], ['stone-900', 'stone-100']]
  for (const [fg, bg] of pairs) assert.ok(contrast(v[fg], v[bg]) >= 4.5, `${fg} trên ${bg}`)
  for (const bg of ['brand-700', 'brand-800']) assert.ok(contrast('#ffffff', v[bg]) >= 4.5, `chữ trắng trên ${bg}`)
  assert.ok(contrast(v['stone-600'], '#ffffff') >= 4.5)
  assert.ok(contrast(v.focus, v['stone-50']) >= 3, 'viền tiêu điểm')
})
