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

// Đăng nhập một lần qua Keycloak bằng client `app-tai-lieu-api`: Authorization Code + PKCE (S256) với oidc-client-ts
// (bản cho trình duyệt trong lib/, cùng phiên bản apps/nghi-phep dùng). Khác Đơn nghỉ phép, trang đọc được khi chưa
// đăng nhập: chỉ sang Keycloak khi người dùng bấm "Đăng nhập". response_mode=fragment: mã cấp quyền về sau dấu # nên
// không đi qua máy chủ nào (không vào nhật ký, WAF không phải soi). Token giữ trong sessionStorage của tab.

const BASE = '/tai-lieu-api/'
const CALLBACK = '/tai-lieu-api/dang-nhap'
let manager = null

async function loadConfig() {
  try {
    const res = await fetch('/tai-lieu-api/config.json', { cache: 'no-store' })
    if (res.ok) return await res.json()
  } catch {
    // dùng mặc định bên dưới
  }
  return { realm: 'moc', clientId: 'app-tai-lieu-api' }
}

function getManager() {
  if (!manager) {
    manager = loadConfig().then((cfg) => {
      const origin = window.location.origin
      return new window.oidc.UserManager({
        authority: `${origin}/realms/${cfg.realm}`,
        client_id: cfg.clientId,
        redirect_uri: `${origin}${CALLBACK}`,
        post_logout_redirect_uri: `${origin}${BASE}`,
        response_type: 'code',
        response_mode: 'fragment',
        scope: 'openid profile',
        userStore: new window.oidc.WebStorageStateStore({ store: window.sessionStorage }),
        automaticSilentRenew: true,
        loadUserInfo: false,
      })
    })
  }
  return manager
}

/** Người dùng đang đăng nhập, hoặc null; không tự chuyển sang Keycloak. Lượt quay về từ Keycloak thì nhận token rồi
 *  trả về đúng bộ tài liệu đang xem; Keycloak báo lỗi (vd bấm hủy) thì ném lỗi sau khi đã dọn địa chỉ. */
export async function currentUser() {
  const m = await getManager()
  if (window.location.pathname === CALLBACK) {
    const params = new URLSearchParams(window.location.hash.slice(1))
    let back = BASE
    let failed = null
    if (params.has('code') || params.has('error')) {
      try {
        const user = await m.signinRedirectCallback()
        if (typeof user.state === 'string' && user.state.startsWith(BASE)) back = user.state
      } catch (err) {
        failed = err
      }
    }
    window.history.replaceState(null, '', back)
    if (failed) throw failed
  }
  const user = await m.getUser()
  if (user && !user.expired) return user
  if (user?.refresh_token) {
    try {
      return await m.signinSilent()
    } catch {
      // refresh token hết hạn: coi như chưa đăng nhập
    }
  }
  return null
}

/** Sang trang đăng nhập của Keycloak; đã đăng nhập Văn phòng điện tử thì không hỏi lại mật khẩu (cùng phiên SSO). */
export async function signIn() {
  const { pathname, search } = window.location
  await (await getManager()).signinRedirect({ state: pathname.startsWith(BASE) ? pathname + search : BASE })
}

export async function signOut() {
  await (await getManager()).signoutRedirect()
}

/** Gọi `fn(user)` mỗi lần token được làm mới, `fn(null)` khi phiên kết thúc. */
export async function onUserChange(fn) {
  const m = await getManager()
  m.events.addUserLoaded(fn)
  m.events.addUserUnloaded(() => fn(null))
  m.events.addAccessTokenExpired(() => fn(null))
}
