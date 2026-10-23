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

// Đăng nhập một lần qua Keycloak bằng client riêng `app-ca-nhan`: Authorization Code + PKCE (S256) với oidc-client-ts —
// bản dựng cho trình duyệt (lib/oidc-client-ts.min.js, biến toàn cục `oidc`), cùng phiên bản app-office dùng. Cùng
// phiên Keycloak với Văn phòng điện tử: đã đăng nhập bên đó thì vào đây không phải nhập lại mật khẩu. Token giữ trong
// sessionStorage của tab, tự gia hạn bằng refresh token.

const BASE = '/ca-nhan/'
const CALLBACK = '/ca-nhan/dang-nhap'
let manager = null

async function loadConfig() {
  try {
    const res = await fetch('/ca-nhan/config.json', { cache: 'no-store' })
    if (res.ok) return await res.json()
  } catch {
    // dùng mặc định bên dưới
  }
  return { realm: 'moc', clientId: 'app-ca-nhan' }
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
        scope: 'openid profile email',
        userStore: new window.oidc.WebStorageStateStore({ store: window.sessionStorage }),
        automaticSilentRenew: true,
        loadUserInfo: false,
      })
    })
  }
  return manager
}

/** Người dùng đã đăng nhập; chưa thì chuyển sang trang đăng nhập của Keycloak và trả null. Trang nhận kết quả đăng
 *  nhập (/ca-nhan/dang-nhap) đổi mã lấy token rồi quay về thư mục đang mở trước đó. */
export async function signIn() {
  const m = await getManager()
  if (window.location.pathname === CALLBACK) {
    const params = new URLSearchParams(window.location.search)
    if (params.has('code') || params.has('error')) {
      const user = await m.signinRedirectCallback()
      const back = user.state?.returnTo
      window.history.replaceState(null, '', typeof back === 'string' && back.startsWith(BASE) ? back : BASE)
      return user
    }
    window.history.replaceState(null, '', BASE)   // mở lại trang nhận kết quả mà không có mã: về trang chính
  }
  const user = await m.getUser()
  if (user && !user.expired) return user
  if (user?.refresh_token) {
    try {
      return await m.signinSilent()
    } catch {
      // refresh token hết hạn: đăng nhập lại
    }
  }
  await m.signinRedirect({ state: { returnTo: window.location.pathname + window.location.hash } })
  return null
}

/** Access token còn hạn (oidc-client-ts tự gia hạn; hết hạn thật thì đăng nhập lại). */
export async function accessToken() {
  const m = await getManager()
  let user = await m.getUser()
  if (!user || user.expired) user = await signIn()
  if (!user) throw new Error('session')
  return user.access_token
}

export async function relogin() {
  const m = await getManager()
  await m.removeUser()
  await m.signinRedirect({ state: { returnTo: window.location.pathname + window.location.hash } })
}

export async function signOut() {
  await (await getManager()).signoutRedirect()
}
