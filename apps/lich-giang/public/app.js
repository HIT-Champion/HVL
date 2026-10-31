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

// Đổi, bù lịch giảng: đăng nhập, nạp ba form từ lõi (JSON Schema), vẽ ba phần — Gửi đề nghị, Đề nghị của tôi, Việc cần
// duyệt (chỉ hiện khi có việc: trưởng bộ môn, lãnh đạo khoa). Mọi dữ liệu đi qua API quy trình chung của lõi bằng token
// của người dùng; lõi kiểm lại form và quyết định ai thấy việc nào. Chữ gán bằng textContent, không bao giờ gán HTML.
// Chữ lấy từ bảng dịch vi/en (i18n.js); phần đang hiện giữ lại để đổi ngôn ngữ thì vẽ lại ngay, không mất chữ đang gõ
// trong form.

import { signIn, signOut } from './auth.js'
import {
  FORM_BO_MON, FORM_DON, FORM_KHOA, LOI, docThan, docTraLoi, doiChieu, duong, ngayGio, quyetDinh, sapXepDon, tenNguoi,
  trangThai, yeuCau,
} from './don.js'
import { locale, localize, saveLocale, savedLocale, setLocale, t } from './i18n.js'
import { mountForm, summary } from './schema-form.js'

const el = (id) => document.getElementById(id)
const make = (tag, props = {}) => Object.assign(document.createElement(tag), props)
const LAM_MOI_MS = 30000

// Phần đang hiện. Tên người và hai dòng báo là hàm trả câu theo ngôn ngữ đang dùng; forms: ba mẫu đã nạp; don: đơn
// của tôi vừa tải (null khi chưa tải xong lần nào); formDon: form gửi đơn đang hiện
const view = {
  nguoi: () => t('status.signingIn'),
  tin: () => t('status.loadingForms'),
  loi: () => '',
  forms: null,
  don: null,
  formDon: null,
}

// Mọi chỗ dựng form, tóm tắt đơn đi qua hai hàm này: giao diện của schema-form.js đổi thì chỉ sửa ở đây. Cả hai theo
// ngôn ngữ đang dùng: nhãn, lựa chọn, gợi ý lấy {vi, en} trong x-moc-ui của tệp form, câu chung lấy từ i18n.js
function veForm(container, schema, { idPrefix, submitLabel, onSubmit, draft }) {
  return mountForm(container, schema, { lang: locale(), draft, idPrefix, submitLabel, onSubmit })
}
function tomTat(schema, data) {
  return summary(schema, data, locale())
}

/** Gọi API chung của lõi bằng token hiện tại → kết quả của docTraLoi. */
async function goi(method, path, data) {
  const user = await signIn()
  if (!user) return { ok: false, message: t('status.redirecting') }
  const [url, init] = yeuCau(user.access_token, method, path, data)
  try {
    const res = await fetch(url, init)
    return docTraLoi(res.status, docThan(await res.text()))
  } catch {
    return { ok: false, message: t(LOI.mang) }
  }
}

// --- thông báo: tin thường đọc lịch sự (role=status), lỗi đọc ngay (role=alert). Câu là hàm để đổi ngôn ngữ thì
// viết lại; câu báo của một lời gọi (kq.message) dựng lúc nhận trả lời, theo ngôn ngữ lúc đó ---
function thongBao() {
  el('tin').textContent = view.tin()
  el('loi').textContent = view.loi()
  el('loi').hidden = !el('loi').textContent
}
function baoTin(text) {
  view.tin = text
  view.loi = () => ''
  thongBao()
}
function baoLoi(text) {
  view.tin = () => ''
  view.loi = text
  thongBao()
}

// --- chuyển phần ---
const PHAN = ['gui-don', 'don-cua-toi', 'viec-can-duyet']
let phanHien = 'gui-don'

function moPhan(ten, { focus = true } = {}) {
  phanHien = ten
  for (const p of PHAN) {
    el(p).hidden = p !== ten
    const tab = document.querySelector(`[data-phan="${p}"]`)
    if (p === ten) tab.setAttribute('aria-current', 'true')
    else tab.removeAttribute('aria-current')
  }
  capNhatViec()
  if (focus) el(`tieu-de-${ten}`).focus()
}

/** Dòng nhãn — giá trị của một đề nghị hay một bước duyệt (dl). */
function bangDon(rows) {
  const dl = make('dl', { className: 'chi-tiet' })
  for (const r of rows) dl.append(make('dt', { textContent: r.label }), make('dd', { textContent: r.value }))
  return dl
}

/** Các bước duyệt đã xong của một đề nghị (bộ môn, rồi khoa), mỗi bước một bảng; bước chưa làm thì không có. */
function ketQuaDuyet(forms, data, buoc = [forms.boMon, forms.khoa]) {
  return buoc.map((schema) => tomTat(schema, data).filter((r) => data?.[r.name] !== undefined))
    .filter((rows) => rows.length).map((rows) => bangDon(rows))
}

// --- Đơn của tôi ---
async function taiDon(forms) {
  const kq = await goi('GET', duong.donCuaToi())
  if (!kq.ok) {
    baoLoi(() => t('error.loadMine', { error: kq.message }))
    return
  }
  view.don = sapXepDon(Array.isArray(kq.data) ? kq.data : [])
  veDon(forms)
}

function veDon(forms) {
  const list = view.don
  el('danh-sach-don').replaceChildren(...list.map((don) => {
    const tt = trangThai(don)
    const li = make('li', { className: 'the' })
    const dau = make('div', { className: 'the-dau' })
    dau.append(make('span', { className: `nhan nhan-${tt.ma}`, textContent: tt.nhan }),
      make('span', { className: 'gio', textContent: t('mine.sentAt', { time: ngayGio(don.startedAt) }) }))
    li.append(dau, bangDon(tomTat(forms.don, don.data)), ...ketQuaDuyet(forms, don.data))
    if (don.endedAt) {
      li.append(make('p', { className: 'gio', textContent: t('mine.endedAt', { time: ngayGio(don.endedAt) }) }))
    }
    return li
  }))
  el('khong-co-don').hidden = list.length > 0
  el('dem-don').textContent = list.length ? String(list.length) : ''
}

// --- Việc cần duyệt: thẻ còn việc giữ nguyên khi làm mới, để không mất ghi chú đang gõ. Mỗi việc: {task, li, form} ---
const theViec = new Map()
let soThe = 0

function dungTheViec(task, forms, draft) {
  const li = make('li', { className: 'the' })
  const h2 = make('h2', { textContent: t('review.sentAt', { time: ngayGio(task.createdAt) }) })
  h2.tabIndex = -1
  li.append(h2, bangDon(tomTat(forms.don, task.data)))
  // bước của khoa: lãnh đạo khoa đọc ý kiến của trưởng bộ môn trước khi quyết định
  if (task.formKey === FORM_KHOA) li.append(...ketQuaDuyet(forms, task.data, [forms.boMon]))
  if (task.dueAt) {
    li.append(make('p', { className: 'gio', textContent: t('review.due', { time: ngayGio(task.dueAt) }) }))
  }
  const khung = make('div', { className: 'khung-form' })
  li.append(khung)
  const the = { task, li, form: null }
  // formKey lạ (quy trình đổi mà trang chưa tải lại): không đoán mẫu nào, báo trên thẻ
  if (!Object.hasOwn(forms.byKey, task.formKey)) {
    khung.append(make('p', { className: 'loi', textContent: t('review.unknownForm', { formKey: task.formKey }) }))
    return the
  }
  the.form = veForm(khung, forms.byKey[task.formKey], {
    idPrefix: `viec-${++soThe}-`,
    submitLabel: t('review.submit'),
    draft,
    onSubmit: async (data) => {
      const kq = await goi('POST', duong.xongViec(task.id), data)
      if (kq.errors) {
        // thẻ có thể vừa được vẽ lại (đổi ngôn ngữ lúc đang gửi): báo vào form đang hiện của việc này
        theViec.get(task.id)?.form?.setErrors(kq.errors)
        return
      }
      if (!kq.ok) {
        baoLoi(() => kq.message)
        if (kq.status === 404 || kq.status === 409) await taiViec(forms)
        return
      }
      boTheViec(task.id)
      const q = quyetDinh(data)
      baoTin(() => (q === 'tu-choi' ? t('notice.declined')
        : task.formKey === FORM_BO_MON ? t('notice.forwarded') : t('notice.approved')))
      capNhatViec()
      const tiep = el('danh-sach-viec').querySelector('h2')
      ;(tiep || el('tieu-de-viec-can-duyet')).focus()
    },
  })
  return the
}

function boTheViec(id) {
  theViec.get(id)?.li.remove()
  theViec.delete(id)
}

function capNhatViec() {
  const n = theViec.size
  el('khong-co-viec').hidden = n > 0
  el('dem-viec').textContent = n ? String(n) : ''
  // chỉ người có việc mới thấy phần này; đang đứng ở đó thì giữ lại để đọc câu "không còn đơn"
  document.querySelector('[data-phan="viec-can-duyet"]').hidden = n === 0 && phanHien !== 'viec-can-duyet'
}

async function taiViec(forms) {
  const kq = await goi('GET', duong.viec())
  if (!kq.ok) {
    baoLoi(() => t('error.loadReview', { error: kq.message }))
    return
  }
  const { them, bo } = doiChieu([...theViec.keys()], Array.isArray(kq.data) ? kq.data : [])
  for (const id of bo) boTheViec(id)
  for (const task of them) {
    const the = dungTheViec(task, forms)
    theViec.set(task.id, the)
    el('danh-sach-viec').append(the.li)
  }
  capNhatViec()
}

// --- Gửi đơn ---
function veFormDon(forms, draft) {
  return veForm(el('form-don'), forms.don, {
    idPrefix: 'don-',
    submitLabel: t('request.submit'),
    draft,
    onSubmit: async (data) => {
      // view.formDon, không phải form lúc dựng: đổi ngôn ngữ lúc đang gửi thì form đã được vẽ lại
      const kq = await goi('POST', duong.guiDon(), data)
      if (kq.errors) {
        view.formDon.setErrors(kq.errors)
        return
      }
      if (!kq.ok) {
        baoLoi(() => t('error.sendFailed', { error: kq.message }))
        return
      }
      view.formDon.reset()
      baoTin(() => t('notice.sent'))
      await taiDon(forms)
    },
  })
}

async function napForm(formKey) {
  const kq = await goi('GET', duong.form(formKey))
  if (!kq.ok || !kq.data || typeof kq.data !== 'object') throw new Error(kq.message || t('error.emptyForm'))
  return kq.data
}

/** Nút đổi ngôn ngữ: lưu lựa chọn (chung với Văn phòng điện tử), gán lại phần tĩnh rồi vẽ lại phần đang hiện; form
 *  dựng lại theo ngôn ngữ mới, giữ chữ đang gõ (draft). */
function switchLocale() {
  saveLocale(setLocale(locale() === 'vi' ? 'en' : 'vi'))
  localize(document)
  el('nguoi').textContent = view.nguoi()
  thongBao()
  const forms = view.forms
  if (!forms) return
  view.formDon = veFormDon(forms, view.formDon.values())
  if (view.don) veDon(forms)
  for (const [id, cu] of theViec) {
    const moi = dungTheViec(cu.task, forms, cu.form?.values())
    cu.li.replaceWith(moi.li)
    theViec.set(id, moi)
  }
}

async function main() {
  setLocale(savedLocale())
  localize(document)
  el('doi-ngon-ngu').addEventListener('click', switchLocale)
  const user = await signIn()
  if (!user) return
  view.nguoi = () => tenNguoi(user.access_token) || t('status.signedIn')
  el('nguoi').textContent = view.nguoi()
  el('thoat').hidden = false
  el('thoat').addEventListener('click', () => signOut())

  let forms
  try {
    const [don, boMon, khoa] = await Promise.all([napForm(FORM_DON), napForm(FORM_BO_MON), napForm(FORM_KHOA)])
    forms = { don, boMon, khoa, byKey: { [FORM_DON]: don, [FORM_BO_MON]: boMon, [FORM_KHOA]: khoa } }
    view.formDon = veFormDon(forms)       // mountForm ném lỗi khi schema không dùng được: báo như không nạp được mẫu
  } catch (err) {
    baoLoi(() => t('error.loadForms', { error: err.message }))
    return
  }
  view.forms = forms
  baoTin(() => '')
  el('ung-dung').hidden = false
  for (const p of PHAN) {
    document.querySelector(`[data-phan="${p}"]`).addEventListener('click', () => moPhan(p))
  }
  moPhan('gui-don', { focus: false })
  // một lượt tải lại mỗi lúc: lượt trước chậm quá LAM_MOI_MS thì lượt sau dùng chung, không chồng kết quả cũ lên mới
  let dangTai = null
  const lamMoi = () => (dangTai ??= Promise.all([taiDon(forms), taiViec(forms)])
    .catch((err) => baoLoi(() => t('error.reload', { error: err.message })))
    .finally(() => { dangTai = null }))
  await lamMoi()
  setInterval(lamMoi, LAM_MOI_MS)
}

main()
