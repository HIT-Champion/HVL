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

import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'

// Đăng nhập một lần qua Keycloak (F2.1): luồng Authorization Code + PKCE, token giữ trong sessionStorage của
// tab, tự gia hạn bằng refresh token. Vai trò, đơn vị, phòng đọc từ claim của Hasura trong access token —
// chỉ để vẽ giao diện; quyền thật do Hasura và các dịch vụ kiểm lại ở phía máy chủ.

export type Role = 'clerk' | 'staff' | 'manager' | 'director' | 'tenant_admin'

export interface Claims {
  userId: string
  tenantId: string | null
  departmentId: string | null
  role: Role | null
  name: string
  username: string
}

interface AppConfig {
  realm: string
  clientId: string
}

const HASURA = 'https://hasura.io/jwt/claims'
const user = ref<User | null>(null)
let manager: Promise<UserManager> | null = null

async function loadConfig(): Promise<AppConfig> {
  try {
    const res = await fetch('/config.json', { cache: 'no-store' })
    if (res.ok) return (await res.json()) as AppConfig
  } catch {
    // dùng mặc định bên dưới
  }
  return { realm: 'moc', clientId: 'app-office' }
}

function decode(token: string): Record<string, unknown> {
  const part = token.split('.')[1] ?? ''
  const bin = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0))
  return JSON.parse(new TextDecoder().decode(bytes))
}

export function getManager(): Promise<UserManager> {
  if (!manager) {
    manager = loadConfig().then((cfg) => {
      const origin = window.location.origin
      const m = new UserManager({
        authority: `${origin}/realms/${cfg.realm}`,
        client_id: cfg.clientId,
        redirect_uri: `${origin}/dang-nhap`,
        post_logout_redirect_uri: `${origin}/`,
        response_type: 'code',
        scope: 'openid profile email',
        userStore: new WebStorageStateStore({ store: window.sessionStorage }),
        automaticSilentRenew: true,
        loadUserInfo: false,
      })
      m.events.addUserLoaded((u) => { user.value = u })
      m.events.addUserUnloaded(() => { user.value = null })
      m.events.addSilentRenewError(() => { user.value = null })
      return m
    })
  }
  return manager
}

export function useAuth() {
  const claims = computed<Claims | null>(() => {
    if (!user.value) return null
    const payload = decode(user.value.access_token)
    const h = (payload[HASURA] ?? {}) as Record<string, string>
    const profile = user.value.profile
    return {
      userId: h['x-hasura-user-id'] ?? String(payload.sub),
      tenantId: h['x-hasura-tenant-id'] ?? null,
      departmentId: h['x-hasura-department-id'] ?? null,
      role: (h['x-hasura-default-role'] as Role) ?? null,
      name: profile.name ?? profile.preferred_username ?? '',
      username: profile.preferred_username ?? '',
    }
  })

  async function restore(): Promise<User | null> {
    const m = await getManager()
    const u = await m.getUser()
    if (u && !u.expired) {
      user.value = u
      return u
    }
    if (u?.refresh_token) {
      try {
        user.value = await m.signinSilent()
        return user.value
      } catch {
        // refresh token hết hạn: đăng nhập lại
      }
    }
    user.value = null
    return null
  }

  async function login(returnTo = '/'): Promise<void> {
    await (await getManager()).signinRedirect({ state: { returnTo } })
  }

  async function finishLogin(): Promise<string> {
    const u = await (await getManager()).signinRedirectCallback()
    user.value = u
    const state = u.state as { returnTo?: string } | undefined
    return state?.returnTo && state.returnTo.startsWith('/') ? state.returnTo : '/'
  }

  async function logout(): Promise<void> {
    dropDrafts()
    await (await getManager()).signoutRedirect()
  }

  async function accessToken(): Promise<string> {
    let u = user.value
    if (!u || u.expired) u = await restore()
    if (!u) {
      await login(window.location.pathname + window.location.search)
      throw new Error('session')
    }
    return u.access_token
  }

  return { user, claims, restore, login, finishLogin, logout, accessToken }
}
