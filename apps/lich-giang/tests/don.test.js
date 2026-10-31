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

// Phần thuần của trang Đổi, bù lịch giảng (public/don.js, node --test, không cần trình duyệt), kèm kiểm khớp: formKey,
// process id ↔ app.yaml và BPMN; trường trang đọc ↔ forms/*.json; trang chỉ dựng form qua một hàm; màu đủ tương phản.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import {
  API, FORM_BO_MON, FORM_DON, FORM_KHOA, LOI, QUY_TRINH, docThan, docTraLoi, doiChieu, duong, ngayGio, quyetDinh,
  sapXepDon, sapXepViec, tenNguoi, trangThai, yeuCau,
} from '../public/don.js'
import { t } from '../public/i18n.js'

const APP = new URL('../', import.meta.url)
const ROOT = new URL('../../../', import.meta.url)
const read = (base, path) => readFileSync(new URL(path, base), 'utf8')

test('lời gọi API chung: đường, token, thân {"data": …}', () => {
  const [url, init] = yeuCau('tok', 'POST', duong.guiDon(), { loai: 'day-bu' })
  assert.equal(url, '/api/workflow/lich-giang/processes/lich-giang.don')
  assert.equal(init.method, 'POST')
  assert.equal(init.headers.Authorization, 'Bearer tok')
  assert.equal(init.headers['Content-Type'], 'application/json')
  assert.deepEqual(JSON.parse(init.body), { data: { loai: 'day-bu' } })
  const [list, get] = yeuCau('tok', 'GET', duong.viec())
  assert.equal(list, `${API}/tasks`)
  assert.equal(get.body, undefined)
  assert.equal(get.headers['Content-Type'], undefined)
  assert.equal(`${API}${duong.form(FORM_KHOA)}`, '/api/workflow/lich-giang/forms/lich-giang.khoa')
  assert.equal(duong.donCuaToi(), '/processes')
  // mã việc lạ không thoát ra khỏi đường
  assert.equal(duong.xongViec('a/../b?c'), '/tasks/a%2F..%2Fb%3Fc')
})

test('trả lời: 2xx là xong, 422 giữ lỗi từng trường, mã khác thành câu đọc được', () => {
  assert.deepEqual(docTraLoi(201, { id: 'p1' }), { ok: true, data: { id: 'p1' } })
  assert.deepEqual(docTraLoi(204, null), { ok: true, data: null })
  const bad = docTraLoi(422, { errors: { ngayMoi: 'x-moc-date' } })
  assert.equal(bad.ok, false)
  assert.deepEqual(bad.errors, { ngayMoi: 'x-moc-date' })
  assert.equal(bad.status, 422)
  for (const status of [401, 403, 404, 409, 429]) {
    assert.deepEqual(docTraLoi(status, { error: 'x' }), { ok: false, status, message: t(LOI[status]) })
  }
  assert.equal(docTraLoi(503, null).message, t(LOI[500]))
  assert.match(docTraLoi(418, null).message, /HTTP 418/)
  // 422 không mang lỗi từng trường (cổng, WAF) thì không giả làm lỗi của form
  for (const body of [null, { errors: [] }, { errors: 'sai' }, { detail: 'x' }]) {
    assert.equal(docTraLoi(422, body).errors, undefined, JSON.stringify(body))
  }
  assert.equal(docThan(''), null)
  assert.equal(docThan('<html>502</html>'), null)
  assert.deepEqual(docThan('{"id":"p1"}'), { id: 'p1' })
})

test('trạng thái đề nghị qua hai cấp: chờ bộ môn, chờ khoa, kết quả của từng cấp', () => {
  assert.deepEqual(trangThai({ endedAt: null, data: {} }), { ma: 'cho', nhan: 'Chờ trưởng bộ môn duyệt' })
  assert.deepEqual(trangThai({ endedAt: null, data: { quyetDinhBoMon: 'dong-y' } }),
    { ma: 'cho', nhan: 'Bộ môn đã đồng ý, chờ khoa phê duyệt' })
  const xong = '2026-10-26T03:00:00Z'
  assert.deepEqual(trangThai({ endedAt: xong, data: { quyetDinhBoMon: 'tu-choi' } }),
    { ma: 'tu-choi', nhan: 'Bộ môn không đồng ý' })
  assert.deepEqual(trangThai({ endedAt: xong, data: { quyetDinhBoMon: 'dong-y', quyetDinhKhoa: 'dong-y' } }),
    { ma: 'dong-y', nhan: 'Đã duyệt' })
  assert.deepEqual(trangThai({ endedAt: xong, data: { quyetDinhBoMon: 'dong-y', quyetDinhKhoa: 'tu-choi' } }),
    { ma: 'tu-choi', nhan: 'Khoa không duyệt' })
  assert.equal(trangThai({ endedAt: xong, data: null }).ma, 'xong')
  assert.equal(trangThai(undefined).ma, 'cho')
  // quyết định của bước vừa gửi, bước nào cũng được
  assert.equal(quyetDinh({ quyetDinhBoMon: 'tu-choi', ghiChuBoMon: 'x' }), 'tu-choi')
  assert.equal(quyetDinh({ quyetDinhKhoa: 'dong-y' }), 'dong-y')
  assert.equal(quyetDinh({}), undefined)
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
  const keys = [...manifest.matchAll(/^ {4}(lich-giang\.[a-z-]+): (\S+)$/gm)]
  const forms = Object.fromEntries(keys.map((m) => [m[1], m[2]]))
  assert.deepEqual(forms,
    { [FORM_DON]: 'forms/don.json', [FORM_BO_MON]: 'forms/bo-mon.json', [FORM_KHOA]: 'forms/khoa.json' })
  assert.match(manifest, /^path: \/lich-giang$/m)
  const bpmn = read(APP, 'workflow/doi-lich-giang.bpmn20.xml')
  assert.match(bpmn, new RegExp(`<process id="${QUY_TRINH.replace('.', '\\.')}"`))
  assert.match(bpmn, new RegExp(`<startEvent [^>]*flowable:formKey="${FORM_DON}"`))
  for (const key of [FORM_BO_MON, FORM_KHOA]) {
    assert.match(bpmn, new RegExp(`<userTask [^>]*flowable:formKey="${key}"`))
  }
  const don = JSON.parse(read(APP, forms[FORM_DON]))
  for (const name of ['loai', 'ngayCu', 'ngayMoi']) assert.ok(don.properties[name], `forms/don.json thiếu ${name}`)
  // trang đọc quyetDinhBoMon, quyetDinhKhoa; nhánh của mỗi cổng rẽ đúng các giá trị quyết định của form bước đó
  for (const [key, field] of [[FORM_BO_MON, 'quyetDinhBoMon'], [FORM_KHOA, 'quyetDinhKhoa']]) {
    const form = JSON.parse(read(APP, forms[key]))
    assert.deepEqual(form.properties[field].enum, ['dong-y', 'tu-choi'])
    const conditions = [...bpmn.matchAll(new RegExp(`\\$\\{${field} == '([a-z-]+)'\\}`, 'g'))].map((m) => m[1])
    assert.deepEqual(conditions.sort(), [...form.properties[field].enum].sort())
  }
})

test('trang không có script nội tuyến, không innerHTML; form chỉ dựng qua một hàm; đăng nhập đúng client', () => {
  const html = read(APP, 'public/index.html')
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/)
  assert.doesNotMatch(html, /\son[a-z]+=/i)
  for (const id of ['tieu-de-gui-don', 'tieu-de-don-cua-toi', 'tieu-de-viec-can-duyet']) {
    assert.match(html, new RegExp(`<h1 id="${id}" tabindex="-1"[^>]*>`))
  }
  assert.match(html, /role="status"/)
  assert.match(html, /role="alert"/)
  const app = read(APP, 'public/app.js')
  assert.doesNotMatch(app, /innerHTML|insertAdjacentHTML|document\.write/)
  assert.equal(app.match(/mountForm\(/g).length, 1, 'chỉ veForm() gọi mountForm')
  assert.equal(app.match(/summary\(/g).length, 1, 'chỉ tomTat() gọi summary')
  const auth = read(APP, 'public/auth.js')
  assert.match(auth, /const CALLBACK = '\/lich-giang\/dang-nhap'/)
  assert.match(auth, /response_mode: 'fragment'/)
  assert.match(auth, /clientId: 'app-lich-giang'/)
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
