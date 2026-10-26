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

// Đăng nhập một lần qua Keycloak bằng client `app-nghi-phep` do `moc app install` tạo: Authorization Code + PKCE (S256)
// với oidc-client-ts (bản cho trình duyệt trong lib/, cùng phiên bản ca-nhan dùng). response_mode=fragment: mã cấp
// quyền về sau dấu # nên không đi qua máy chủ nào (không vào nhật ký, WAF không phải soi). Token giữ trong
// sessionStorage của tab.

const BASE = '/nghi-phep/'
const CALLBACK = '/nghi-phep/dang-nhap'
let manager = null

async function loadConfig() {
  try {
    const res = await fetch('/nghi-phep/config.json', { cache: 'no-store' })
    if (res.ok) return await res.json()
  } catch {
    // dùng mặc định bên dưới
  }
  return { realm: 'moc', clientId: 'app-nghi-phep' }
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

/** Người dùng đã đăng nhập; chưa thì chuyển sang Keycloak và trả null (đã đăng nhập Văn phòng điện tử thì không hỏi
 *  lại mật khẩu — cùng phiên SSO). */
export async function signIn() {
  const m = await getManager()
  if (window.location.pathname === CALLBACK) {
    const params = new URLSearchParams(window.location.hash.slice(1))
    if (params.has('code') || params.has('error')) {
      await m.signinRedirectCallback()
    }
    window.history.replaceState(null, '', BASE)
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
  await m.signinRedirect()
  return null
}

export async function signOut() {
  await (await getManager()).signoutRedirect()
}
