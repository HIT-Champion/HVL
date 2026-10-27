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

// Đơn nghỉ phép: đăng nhập, nạp hai form từ lõi (JSON Schema), vẽ ba phần — Gửi đơn, Đơn của tôi, Việc cần duyệt (chỉ
// hiện khi có việc). Mọi dữ liệu đi qua API quy trình chung của lõi bằng token của người dùng; lõi kiểm lại form và
// quyết định ai thấy việc nào. Chữ gán bằng textContent, không bao giờ gán HTML.

import { signIn, signOut } from './auth.js'
import {
  FORM_DON, FORM_DUYET, LOI, docThan, docTraLoi, doiChieu, duong, ngayGio, sapXepDon, soNgay, tenNguoi, trangThai,
  yeuCau,
} from './don.js'
import { mountForm, summary } from './schema-form.js'

const el = (id) => document.getElementById(id)
const make = (tag, props = {}) => Object.assign(document.createElement(tag), props)
const LAM_MOI_MS = 30000

// Mọi chỗ dựng form, tóm tắt đơn đi qua hai hàm này: giao diện của schema-form.js đổi thì chỉ sửa ở đây
function veForm(container, schema, { idPrefix, submitLabel, onSubmit }) {
  return mountForm(container, schema, { lang: 'vi', idPrefix, submitLabel, onSubmit })
}
function tomTat(schema, data) {
  return summary(schema, data, 'vi')
}

/** Gọi API chung của lõi bằng token hiện tại → kết quả của docTraLoi. */
async function goi(method, path, data) {
  const user = await signIn()
  if (!user) return { ok: false, message: 'Đang chuyển sang trang đăng nhập…' }
  const [url, init] = yeuCau(user.access_token, method, path, data)
  try {
    const res = await fetch(url, init)
    return docTraLoi(res.status, docThan(await res.text()))
  } catch {
    return { ok: false, message: LOI.mang }
  }
}

// --- thông báo: tin thường đọc lịch sự (role=status), lỗi đọc ngay (role=alert) ---
function baoTin(text) {
  el('loi').textContent = ''
  el('loi').hidden = true
  el('tin').textContent = text
}
function baoLoi(text) {
  el('tin').textContent = ''
  el('loi').textContent = text
  el('loi').hidden = !text
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

/** Dòng nhãn — giá trị của một đơn (dl), thêm số ngày nghỉ khi có đủ hai ngày. */
function bangDon(rows, data) {
  const dl = make('dl', { className: 'chi-tiet' })
  for (const r of rows) dl.append(make('dt', { textContent: r.label }), make('dd', { textContent: r.value }))
  const n = soNgay(data?.tuNgay, data?.denNgay)
  if (n) dl.append(make('dt', { textContent: 'Số ngày nghỉ' }), make('dd', { textContent: `${n} ngày` }))
  return dl
}

// --- Đơn của tôi ---
async function taiDon(forms) {
  const kq = await goi('GET', duong.donCuaToi())
  if (!kq.ok) {
    baoLoi(`Không tải được đơn của bạn: ${kq.message}`)
    return
  }
  const list = sapXepDon(Array.isArray(kq.data) ? kq.data : [])
  el('danh-sach-don').replaceChildren(...list.map((don) => {
    const tt = trangThai(don)
    const li = make('li', { className: 'the' })
    const dau = make('div', { className: 'the-dau' })
    dau.append(make('span', { className: `nhan nhan-${tt.ma}`, textContent: tt.nhan }),
      make('span', { className: 'gio', textContent: `Gửi lúc ${ngayGio(don.startedAt)}` }))
    li.append(dau, bangDon(tomTat(forms.don, don.data), don.data))
    if (don.endedAt) {
      const ketQua = tomTat(forms.duyet, don.data).filter((r) => don.data?.[r.name] !== undefined)
      if (ketQua.length) li.append(bangDon(ketQua))
      li.append(make('p', { className: 'gio', textContent: `Kết thúc lúc ${ngayGio(don.endedAt)}` }))
    }
    return li
  }))
  el('khong-co-don').hidden = list.length > 0
  el('dem-don').textContent = list.length ? String(list.length) : ''
}

// --- Việc cần duyệt: thẻ còn việc giữ nguyên khi làm mới, để không mất ghi chú đang gõ ---
const theViec = new Map()
let soThe = 0

function dungTheViec(task, forms) {
  const li = make('li', { className: 'the' })
  const h2 = make('h2', { textContent: `Đơn gửi lúc ${ngayGio(task.createdAt)}` })
  h2.tabIndex = -1
  li.append(h2, bangDon(tomTat(forms.don, task.data), task.data))
  if (task.dueAt) li.append(make('p', { className: 'gio', textContent: `Hạn duyệt: ${ngayGio(task.dueAt)}` }))
  const khung = make('div', { className: 'khung-form' })
  li.append(khung)
  // formKey lạ (quy trình đổi mà trang chưa tải lại): không đoán mẫu nào, báo trên thẻ
  if (!Object.hasOwn(forms.byKey, task.formKey)) {
    khung.append(make('p', { className: 'loi', textContent: `Trang chưa có mẫu "${task.formKey}" cho việc này. `
      + 'Tải lại trang để lấy mẫu mới.' }))
    return li
  }
  const form = veForm(khung, forms.byKey[task.formKey], {
    idPrefix: `viec-${++soThe}-`,
    submitLabel: 'Gửi quyết định',
    onSubmit: async (data) => {
      const kq = await goi('POST', duong.xongViec(task.id), data)
      if (kq.errors) {
        form.setErrors(kq.errors)
        return
      }
      if (!kq.ok) {
        baoLoi(kq.message)
        if (kq.status === 404 || kq.status === 409) await taiViec(forms)
        return
      }
      boTheViec(task.id)
      baoTin(data.quyetDinh === 'tu-choi' ? 'Đã từ chối đơn. Người gửi thấy kết quả trong "Đơn của tôi".'
        : 'Đã duyệt đơn. Người gửi thấy kết quả trong "Đơn của tôi".')
      capNhatViec()
      const tiep = el('danh-sach-viec').querySelector('h2')
      ;(tiep || el('tieu-de-viec-can-duyet')).focus()
    },
  })
  return li
}

function boTheViec(id) {
  theViec.get(id)?.remove()
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
    baoLoi(`Không tải được việc cần duyệt: ${kq.message}`)
    return
  }
  const { them, bo } = doiChieu([...theViec.keys()], Array.isArray(kq.data) ? kq.data : [])
  for (const id of bo) boTheViec(id)
  for (const task of them) {
    const li = dungTheViec(task, forms)
    theViec.set(task.id, li)
    el('danh-sach-viec').append(li)
  }
  capNhatViec()
}

// --- Gửi đơn ---
function veFormDon(forms) {
  const form = veForm(el('form-don'), forms.don, {
    idPrefix: 'don-',
    submitLabel: 'Gửi đơn',
    onSubmit: async (data) => {
      const kq = await goi('POST', duong.guiDon(), data)
      if (kq.errors) {
        form.setErrors(kq.errors)
        return
      }
      if (!kq.ok) {
        baoLoi(`Chưa gửi được đơn: ${kq.message}`)
        return
      }
      form.reset()
      const n = soNgay(data.tuNgay, data.denNgay)
      baoTin(`Đã gửi đơn${n ? ` nghỉ ${n} ngày` : ''}. Trưởng phòng của phòng bạn sẽ duyệt; theo dõi ở "Đơn của tôi".`)
      await taiDon(forms)
    },
  })
}

async function napForm(formKey) {
  const kq = await goi('GET', duong.form(formKey))
  if (!kq.ok || !kq.data || typeof kq.data !== 'object') throw new Error(kq.message || 'form rỗng')
  return kq.data
}

async function main() {
  const user = await signIn()
  if (!user) return
  el('nguoi').textContent = tenNguoi(user.access_token) || 'Đã đăng nhập'
  el('thoat').hidden = false
  el('thoat').addEventListener('click', () => signOut())

  let forms
  try {
    const [don, duyet] = await Promise.all([napForm(FORM_DON), napForm(FORM_DUYET)])
    forms = { don, duyet, byKey: { [FORM_DON]: don, [FORM_DUYET]: duyet } }
    veFormDon(forms)       // mountForm ném lỗi khi schema không dùng được: báo như không nạp được mẫu
  } catch (err) {
    el('tin').textContent = ''
    baoLoi(`Không nạp được mẫu đơn từ Signet: ${err.message}`)
    return
  }
  el('tin').textContent = ''
  el('ung-dung').hidden = false
  for (const p of PHAN) {
    document.querySelector(`[data-phan="${p}"]`).addEventListener('click', () => moPhan(p))
  }
  moPhan('gui-don', { focus: false })
  // một lượt tải lại mỗi lúc: lượt trước chậm quá LAM_MOI_MS thì lượt sau dùng chung, không chồng kết quả cũ lên mới
  let dangTai = null
  const lamMoi = () => (dangTai ??= Promise.all([taiDon(forms), taiViec(forms)])
    .catch((err) => baoLoi(`Không tải lại được danh sách: ${err.message}`))
    .finally(() => { dangTai = null }))
  await lamMoi()
  setInterval(lamMoi, LAM_MOI_MS)
}

main()
