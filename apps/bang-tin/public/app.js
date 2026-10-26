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

// Bảng tin: đăng nhập, hỏi bảng bang_tin.tin của ứng dụng qua cổng (/v1/graphql, APISIX kiểm token, Hasura xét quyền
// theo đơn vị và theo văn bản người xem được đọc), vẽ danh sách, hỏi lại mỗi 15 giây. Chữ lấy từ bảng dịch vi/en
// (i18n.js); phần đang hiện giữ lại để đổi ngôn ngữ thì vẽ lại ngay, không chờ lần hỏi sau.

import { signIn, signOut } from './auth.js'
import { locale, localize, saveLocale, savedLocale, setLocale, t } from './i18n.js'
import { QUERY_TIN, VAI_TRO_XEM, dong, loiTaiTin, tenNguoi, vaiTro } from './tin.js'

const el = (id) => document.getElementById(id)
// tên người (hay câu chờ) và câu trạng thái là hàm trả câu theo ngôn ngữ đang dùng; rows: tin đang hiện
const view = { nguoi: () => t('status.signingIn'), trangThai: () => '', rows: [] }

function trangThai(text) {
  view.trangThai = text
  el('trang-thai').textContent = text()
}

async function load(token) {
  const res = await fetch('/v1/graphql', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: QUERY_TIN }),
  })
  const body = await res.json()
  if (!res.ok || body.errors) throw new Error(loiTaiTin(body, res.status))
  return body.data.bang_tin_tin
}

function list(rows) {
  view.rows = rows
  el('tin').replaceChildren(...rows.map((tin) => {
    const d = dong(tin)
    const li = document.createElement('li')
    const loai = Object.assign(document.createElement('span'), { className: 'loai', textContent: d.loai })
    const gio = Object.assign(document.createElement('span'), { className: 'gio', textContent: d.gio })
    const so = Object.assign(document.createElement('p'), { className: 'so', textContent: d.so })
    const ty = Object.assign(document.createElement('p'), { className: 'trich-yeu', textContent: d.trichYeu })
    li.append(loai, gio, so, ty)
    return li
  }))
}

function draw(rows) {
  list(rows)
  trangThai(() => (rows.length ? '' : t('status.empty')))
}

/** Nút đổi ngôn ngữ: lưu lựa chọn (chung với Văn phòng điện tử), gán lại phần tĩnh rồi vẽ lại phần đang hiện. */
function switchLocale() {
  saveLocale(setLocale(locale() === 'vi' ? 'en' : 'vi'))
  localize(document)
  el('nguoi').textContent = view.nguoi()
  list(view.rows)
  el('trang-thai').textContent = view.trangThai()
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
  // quản trị đơn vị không đọc văn bản nên không có bảng tin: báo bằng câu đọc được, không hỏi để nhận lỗi GraphQL.
  // Kiểm cả ở mỗi lần làm mới: token gia hạn có thể mang vai trò khác, khi đó xóa tin đang hiện
  const khongXem = (token) => {
    if (VAI_TRO_XEM.includes(vaiTro(token))) return false
    list([])
    trangThai(() => t('status.adminNoBoard'))
    return true
  }
  if (khongXem(user.access_token)) return
  const refresh = async () => {
    try {
      const current = await signIn()
      if (current && !khongXem(current.access_token)) draw(await load(current.access_token))
    } catch (err) {
      // câu lỗi dựng lúc nhận phản hồi (loiTaiTin), theo ngôn ngữ lúc đó; lần hỏi sau viết lại
      trangThai(() => t('status.loadFailed', { error: err.message }))
    }
  }
  await refresh()
  setInterval(refresh, 15000)
}

main()
