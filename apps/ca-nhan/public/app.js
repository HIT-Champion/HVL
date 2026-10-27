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
// từng dòng, sổ kiểm toán đều do lõi làm. Tên tệp và mọi chữ khác đều gán bằng textContent, không dựng HTML. Chữ lấy
// từ bảng dịch vi/en (i18n.js); câu trạng thái và câu báo giữ dạng hàm để đổi ngôn ngữ thì viết lại được ngay.

import { ApiError, createApi } from './api.js'
import { accessToken, relogin, signIn, signOut } from './auth.js'
import { locale, localize, saveLocale, savedLocale, setLocale, t } from './i18n.js'
import {
  FOLDERS, MOVE_ITEM, PLACE_ITEM, QUERY_ITEMS, countByFolder, folderFromHash, folderHint, folderName, formatSize,
  formatTime, graphqlError, hasSpace, itemsIn, readClaims,
} from './para.js'

const $ = (id) => document.getElementById(id)
const api = createApi({ token: accessToken, relogin })
const state = { items: [], folder: folderFromHash(window.location.hash), pending: null, ready: false,
                status: () => t('status.signingIn'), message: null }

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

/** Câu ở dòng trạng thái (đăng nhập, lỗi trước khi vào được không gian). text: hàm trả câu theo ngôn ngữ đang dùng. */
function status(text) {
  state.status = text
  $('status').textContent = text()
}

/** Câu báo trên danh sách; text là hàm như ở status(), không có thì ẩn khung báo. */
function message(text, kind = 'ok', retry = false) {
  state.message = text ? { text, kind, retry } : null
  $('message-text').textContent = text ? text() : ''
  $('message').className = `message ${kind}`
  $('message').setAttribute('role', kind === 'error' ? 'alert' : 'status')
  $('message').hidden = !text
  $('retry').hidden = !retry
}

function errorText(e) {
  if (e instanceof ApiError && e.status && !e.code) return t('error.status', { status: e.status })
  if (e instanceof ApiError) return graphqlError(e.code, e.message)
  return graphqlError(null, String(e?.message ?? e))
}

function renderFolders() {
  const counts = countByFolder(state.items)
  $('folders').replaceChildren(...FOLDERS.map((f) => el('li', {},
    el('a', { href: `#${f.key}`, ...(f.key === state.folder ? { 'aria-current': 'page' } : {}) },
      el('span', { text: folderName(f.key) }), el('span', { class: 'count', text: String(counts[f.key]) })))))
}

function row(item) {
  const name = item.file?.filename ?? item.file_id
  const picker = el('select', { 'aria-label': t('item.moveLabel', { name }),
                                 onchange: (e) => move(item, e.target.value) },
    el('option', { value: '', text: t('item.movePlaceholder') }),
    ...FOLDERS.filter((f) => f.key !== item.para).map((f) => el('option', { value: f.key, text: folderName(f.key) })))
  return el('tr', {},
    el('td', { class: 'name', text: name }),
    // data-label: nhãn cột khi bảng thành thẻ trên điện thoại (style.css), cùng khóa với đầu bảng trong index.html
    el('td', { class: 'num', 'data-label': t('column.size'), text: formatSize(item.file?.size_bytes) }),
    el('td', { 'data-label': t('column.scanned'), text: formatTime(item.file?.scanned_at) }),
    el('td', { class: 'actions' },
      el('button', { type: 'button', class: 'btn secondary', 'aria-label': t('item.downloadLabel', { name }),
                     text: t('item.download'), onclick: () => download(item) }),
      picker))
}

function render() {
  renderFolders()
  $('folder-title').textContent = folderName(state.folder)
  $('folder-hint').textContent = folderHint(state.folder)
  $('upload-label').textContent = t('upload.into', { folder: folderName(state.folder) })
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
    message(() => t('upload.notPlaced', { name: file.filename, folder: folderName(para), error: errorText(e) }),
      'error', true)
    return
  }
  state.pending = null
  await load()
  message(() => t('upload.done', { name: file.filename, folder: folderName(para) }))
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
  message(() => t('upload.progress', { name: file.name }))
  let stored
  try {
    stored = await api.upload(file, (pct) => { progress.value = pct })
  } catch (e) {
    // câu của lỗi tải lên dựng trong api.js lúc nhận phản hồi, theo ngôn ngữ lúc đó
    message(() => (e instanceof ApiError ? e.message : errorText(e)), 'error')
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
    message(() => t('move.done', { name, folder: folderName(para) }))
  } catch (e) {
    render()
    message(() => errorText(e), 'error')
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
    message(() => (e instanceof ApiError && e.code === 'not_found' ? t('download.notFound', { name }) : errorText(e)),
      'error')
  }
}

/** Nút đổi ngôn ngữ: lưu lựa chọn (chung với Văn phòng điện tử), gán lại phần tĩnh rồi vẽ lại phần đang hiện. */
function switchLocale() {
  saveLocale(setLocale(locale() === 'vi' ? 'en' : 'vi'))
  localize(document)
  $('status').textContent = state.status()
  if (state.ready) render()
  if (state.message) message(state.message.text, state.message.kind, state.message.retry)
}

async function main() {
  setLocale(savedLocale())
  localize(document)
  $('lang').addEventListener('click', switchLocale)
  let user
  try {
    user = await signIn()
  } catch (e) {
    status(() => t('status.signInFailed', { error: e?.message ?? e }))
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
    status(() => t('status.adminNoSpace'))
    return
  }
  try {
    await load()
  } catch (e) {
    status(() => errorText(e))
    return
  }
  state.ready = true
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
