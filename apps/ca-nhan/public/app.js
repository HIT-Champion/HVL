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

// Không gian cá nhân P.A.R.A — ứng dụng thứ hai trên lõi Signet (docs/them-ung-dung.md). Bốn thư mục, tải tệp lên vào
// thư mục đang mở, chuyển tệp giữa các thư mục, tải về. Chỉ vẽ giao diện: kiểm token, quét mã độc, lưu tệp, quyền đến
// từng dòng, sổ kiểm toán đều do lõi làm. Tên tệp và mọi chữ khác đều gán bằng textContent, không dựng HTML.

import { ApiError, createApi } from './api.js'
import { accessToken, relogin, signIn, signOut } from './auth.js'
import {
  FOLDERS, MOVE_ITEM, PLACE_ITEM, QUERY_ITEMS, countByFolder, folderFromHash, folderName, formatSize, formatTime,
  graphqlError, hasSpace, itemsIn, readClaims,
} from './para.js'

const $ = (id) => document.getElementById(id)
const api = createApi({ token: accessToken, relogin })
const state = { items: [], folder: folderFromHash(window.location.hash), pending: null }

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'text') node.textContent = v
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v)
    else node.setAttribute(k, v)
  }
  node.append(...children)
  return node
}

function message(text, kind = 'ok', retry = false) {
  $('message-text').textContent = text
  $('message').className = `message ${kind}`
  $('message').setAttribute('role', kind === 'error' ? 'alert' : 'status')
  $('message').hidden = !text
  $('retry').hidden = !retry
}

function errorText(e) {
  if (e instanceof ApiError && e.status && !e.code) return `Máy chủ báo lỗi (mã ${e.status}).`
  if (e instanceof ApiError) return graphqlError(e.code, e.message)
  return graphqlError(null, String(e?.message ?? e))
}

function renderFolders() {
  const counts = countByFolder(state.items)
  $('folders').replaceChildren(...FOLDERS.map((f) => el('li', {},
    el('a', { href: `#${f.key}`, ...(f.key === state.folder ? { 'aria-current': 'page' } : {}) },
      el('span', { text: f.name }), el('span', { class: 'count', text: String(counts[f.key]) })))))
}

function row(item) {
  const name = item.file?.filename ?? item.file_id
  const picker = el('select', { 'aria-label': `Chuyển ${name} sang thư mục`,
                                 onchange: (e) => move(item, e.target.value) },
    el('option', { value: '', text: 'Chuyển sang…' }),
    ...FOLDERS.filter((f) => f.key !== item.para).map((f) => el('option', { value: f.key, text: f.name })))
  return el('tr', {},
    el('td', { class: 'name', text: name }),
    // data-label: nhãn cột khi bảng thành thẻ trên điện thoại (style.css), cùng chữ với đầu bảng trong index.html
    el('td', { class: 'num', 'data-label': 'Dung lượng', text: formatSize(item.file?.size_bytes) }),
    el('td', { 'data-label': 'Quét sạch lúc', text: formatTime(item.file?.scanned_at) }),
    el('td', { class: 'actions' },
      el('button', { type: 'button', class: 'btn secondary', 'aria-label': `Tải về ${name}`, text: 'Tải về',
                     onclick: () => download(item) }),
      picker))
}

function render() {
  const folder = FOLDERS.find((f) => f.key === state.folder)
  renderFolders()
  $('folder-title').textContent = folder.name
  $('folder-hint').textContent = folder.hint
  $('upload-label').textContent = `Tải tệp lên vào ${folder.name}`
  const items = itemsIn(state.items, state.folder)
  $('rows').replaceChildren(...items.map(row))
  $('items').hidden = items.length === 0
  $('empty').hidden = items.length > 0
}

async function load() {
  const data = await api.gql(QUERY_ITEMS)
  state.items = data.personal_items
  render()
}

/** Xếp tệp vừa tải lên vào thư mục: lỗi ở bước này thì tệp đã nằm trong kho, giữ lại để bấm "Thử xếp lại". */
async function place(file, para) {
  state.pending = { file, para }
  try {
    await api.gql(PLACE_ITEM, { file: file.id, para })
  } catch (e) {
    message(`Tệp ${file.filename} đã lưu nhưng chưa xếp được vào ${folderName(para)}: ${errorText(e)}`, 'error', true)
    return
  }
  state.pending = null
  await load()
  message(`Đã tải ${file.filename} lên, trạm quét báo sạch, đã xếp vào ${folderName(para)}.`)
}

async function onUpload() {
  const input = $('file')
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const para = state.folder
  const progress = $('progress')
  progress.value = 0
  progress.hidden = false
  message(`Đang tải ${file.name} lên và quét mã độc…`)
  let stored
  try {
    stored = await api.upload(file, (pct) => { progress.value = pct })
  } catch (e) {
    message(e instanceof ApiError ? e.message : errorText(e), 'error')
    return
  } finally {
    progress.hidden = true
  }
  await place(stored, para)
}

async function move(item, para) {
  if (!para) return
  const name = item.file?.filename ?? item.file_id
  try {
    await api.gql(MOVE_ITEM, { file: item.file_id, para })
    await load()
    message(`Đã chuyển ${name} sang ${folderName(para)}.`)
  } catch (e) {
    render()
    message(errorText(e), 'error')
  }
}

async function download(item) {
  const name = item.file?.filename ?? item.file_id
  try {
    const url = URL.createObjectURL(await api.fetchFile(item.file_id))
    const a = el('a', { href: url, download: name })
    document.body.append(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  } catch (e) {
    message(e instanceof ApiError && e.code === 'not_found' ? `Không tải được ${name}: tệp không còn hoặc bạn không `
      + 'còn quyền xem.' : errorText(e), 'error')
  }
}

async function main() {
  let user
  try {
    user = await signIn()
  } catch (e) {
    $('status').textContent = `Đăng nhập không được: ${e?.message ?? e}. Tải lại trang để thử lại.`
    return
  }
  if (!user) return   // đang chuyển sang trang đăng nhập của Keycloak
  // vừa từ Keycloak về: signIn đã đưa địa chỉ về thư mục đang mở trước khi đăng nhập (replaceState không báo
  // hashchange)
  state.folder = folderFromHash(window.location.hash)
  const claims = readClaims(user.access_token)
  $('who').textContent = claims?.name ?? ''
  $('logout').hidden = false
  $('logout').addEventListener('click', () => signOut())
  if (!hasSpace(claims?.role)) {
    $('status').textContent = 'Tài khoản quản trị đơn vị không có không gian cá nhân: lõi không cho vai trò này đọc '
      + 'tệp. Đăng nhập bằng tài khoản nghiệp vụ.'
    return
  }
  try {
    await load()
  } catch (e) {
    $('status').textContent = errorText(e)
    return
  }
  $('status').hidden = true
  $('space').hidden = false
  $('file').addEventListener('change', onUpload)
  $('retry').addEventListener('click', () => state.pending && place(state.pending.file, state.pending.para))
  window.addEventListener('hashchange', () => {
    state.folder = folderFromHash(window.location.hash)
    message('')
    render()
  })
}

main()
