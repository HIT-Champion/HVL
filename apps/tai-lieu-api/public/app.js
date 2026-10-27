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

// Trang Tài liệu API: Swagger UI (lib/swagger-ui/, lấy từ npm lúc dựng image) đọc một trong hai bộ OpenAPI chia lúc
// dựng (openapi/loi.json, openapi/van-phong.json — chia_openapi.py). Đăng nhập thì token của người dùng được điền sẵn
// vào HTTPBearer (nút Authorize) và làm mới theo phiên; "Try it out" gọi lõi qua đúng cổng APISIX như mọi ứng dụng.
// Chưa đăng nhập vẫn đọc được, gọi được các đường không cần token, hoặc dán token khác (vd của client moc-cli) vào
// Authorize.

import { currentUser, onUserChange, signIn, signOut } from './auth.js'

const SPECS = ['loi', 'van-phong']
const $ = (id) => document.getElementById(id)
let token = null
let ui = null
let filled = false          // token đã điền vào HTTPBearer của bản Swagger UI đang hiện

function say(text) {
  $('tin').textContent = text
}

function fail(text) {
  $('loi').textContent = text
  $('loi').hidden = false
}

/** Bộ tài liệu theo ?bo= của địa chỉ; mặc định bộ lõi. */
function chosen() {
  const bo = new URLSearchParams(window.location.search).get('bo')
  return SPECS.includes(bo) ? bo : SPECS[0]
}

function authorize() {
  if (!ui) return
  if (token) {
    ui.preauthorizeApiKey('HTTPBearer', token)
    filled = true
  } else if (filled) {      // chỉ gỡ token trang đã điền: logout khi chưa có gì thì Swagger UI ném lỗi
    ui.authActions.logout(['HTTPBearer'])
    filled = false
  }
}

function show(name, { keepHash = false } = {}) {
  for (const tab of document.querySelectorAll('[data-bo]')) {
    tab.setAttribute('aria-current', String(tab.dataset.bo === name))
  }
  const url = new URL(window.location.href)
  if (name === SPECS[0]) url.searchParams.delete('bo')
  else url.searchParams.set('bo', name)
  if (!keepHash) url.hash = ''
  window.history.replaceState(null, '', url)
  filled = false
  ui = window.SwaggerUIBundle({
    url: `/tai-lieu-api/openapi/${name}.json`,
    dom_id: '#swagger-ui',
    presets: [window.SwaggerUIBundle.presets.apis],
    layout: 'BaseLayout',
    deepLinking: true,
    docExpansion: 'list',
    defaultModelsExpandDepth: 0,
    displayRequestDuration: true,
    filter: true,
    persistAuthorization: false,
    validatorUrl: null,
    onComplete: () => {
      authorize()
      say('')
    },
  })
}

function setUser(user) {
  token = user && !user.expired ? user.access_token : null
  const name = user ? user.profile.name || user.profile.preferred_username : ''
  $('nguoi').textContent = name ? `Đã đăng nhập: ${name}` : ''
  $('nguoi').hidden = !token
  $('thoat').hidden = !token
  $('dang-nhap').hidden = Boolean(token)
  authorize()
}

async function start() {
  for (const tab of document.querySelectorAll('[data-bo]')) {
    tab.addEventListener('click', () => show(tab.dataset.bo))
  }
  $('dang-nhap').addEventListener('click', () => signIn().catch(() => fail('Không mở được trang đăng nhập.')))
  $('thoat').addEventListener('click', () => signOut().catch(() => fail('Không đăng xuất được, tải lại trang.')))
  if (!window.SwaggerUIBundle || !window.oidc) {
    fail('Không nạp được Swagger UI. Tải lại trang.')
    return
  }
  let user = null
  try {
    user = await currentUser()
  } catch {
    fail('Đăng nhập không thành công. Bạn vẫn đọc được tài liệu và gọi các đường không cần token.')
  }
  setUser(user)
  onUserChange(setUser)
  say('Đang nạp tài liệu…')
  show(chosen(), { keepHash: true })
}

start()
