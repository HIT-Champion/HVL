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

// Cấu hình Node-RED của Signet (#366, profile tu-dong; docs/van-hanh.md mục Tự động hóa bằng Node-RED).
//
// Đăng nhập: chỉ qua Keycloak (client công khai tu-dong, luồng code + PKCE do openid-client làm ở phía máy chủ), chỉ
// người có vai trò client "operator" của tu-dong. Không có tài khoản, mật khẩu riêng của Node-RED. Container chỉ ở
// mạng apps: đổi mã lấy token, tải khóa ký qua cổng APISIX như ứng dụng cắm khác; trình duyệt đi địa chỉ công khai.
//
// Khóa: không cài node, module từ npm trên giao diện; node Function không nạp module ngoài; bỏ node exec (chạy lệnh
// shell) và các node đọc, ghi, theo dõi tệp (file, file in, watch: đọc được flows_cred.json, phiên trình soạn,
// /proc/self/environ); không mở endpoint HTTP của flow (httpNodeRoot) ở bước này; tắt diagnostics, runtimeState,
// telemetry.
// Kiểm: kiem-tra.cjs nạp thật tệp này lúc dựng image (Dockerfile); scripts/tests/test_tu_dong.py đọc chữ tệp này.

const { Configuration, None, allowInsecureRequests } = require('openid-client')
const { Strategy } = require('openid-client/passport')

const CLIENT_ID = 'tu-dong'
const ROLE = 'operator'
// Hạn token của trình soạn: hết hạn thì đăng nhập lại qua Keycloak, bị gỡ vai trò thì không vào lại được
const SESSION_S = 8 * 60 * 60
const GATEWAY = process.env.MOC_TU_DONG_GATEWAY || 'http://apisix:9080'
const PUBLIC_URL = (process.env.MOC_PUBLIC_URL || '').replace(/\/+$/, '')
const REALM = process.env.MOC_REALM || 'moc'
const SECRET = process.env.MOC_TU_DONG_SECRET || ''
// node Function đọc được biến môi trường của tiến trình (env.get): không để lại khóa mã hóa thông tin đăng nhập.
// Khối biến lúc khởi động (/proc/self/environ) vẫn giữ khóa: vì vậy bỏ cả node đọc tệp (nodesExcludes)
delete process.env.MOC_TU_DONG_SECRET

if (!/^https?:\/\/[^/]+$/.test(PUBLIC_URL)) {
  throw new Error('MOC_PUBLIC_URL phải là địa chỉ gốc, vd https://signet.example')
}
if (!/^[A-Za-z0-9._-]{1,64}$/.test(REALM)) {
  throw new Error('MOC_REALM sai dạng')
}
if (SECRET.length < 32) {
  throw new Error('MOC_TU_DONG_SECRET cần ít nhất 32 ký tự (make tu-dong-env sinh)')
}

const issuer = `${PUBLIC_URL}/realms/${REALM}`
const internal = `${GATEWAY}/realms/${REALM}/protocol/openid-connect`
// Metadata viết sẵn thay vì discovery: settings.js nạp đồng bộ, và trình duyệt tới authorization_endpoint qua địa chỉ
// công khai còn máy chủ gọi token, certs qua cổng trong mạng apps. iss trong token vẫn là địa chỉ công khai
// (KC_HOSTNAME của Keycloak), openid-client kiểm đúng giá trị đó
const config = new Configuration({
  issuer,
  authorization_endpoint: `${issuer}/protocol/openid-connect/auth`,
  token_endpoint: `${internal}/token`,
  jwks_uri: `${internal}/certs`,
  code_challenge_methods_supported: ['S256'],
  authorization_response_iss_parameter_supported: true,
  id_token_signing_alg_values_supported: ['RS256'],
}, CLIENT_ID, undefined, None())
// Gọi cổng bằng http trong mạng apps (không ra ngoài máy); địa chỉ công khai https không đi qua đây
allowInsecureRequests(config)

// Người đã qua Keycloak với vai trò operator trong lần chạy này. Node-RED hỏi lại users() ở mỗi lời gọi API: khởi
// động lại thì danh sách rỗng, mọi người đăng nhập lại
const operators = new Set()

// Vai trò client của tu-dong trong ID token (mapper tu-dong-roles, scripts/tu_dong.py): openid-client đã kiểm chữ ký,
// iss, aud của ID token trước khi gọi verify
function roles(claims) {
  const mine = claims.resource_access && claims.resource_access[CLIENT_ID]
  return Array.isArray(mine && mine.roles) ? mine.roles : []
}

function verify(tokens, done) {
  const claims = tokens.claims() || {}
  const username = typeof claims.preferred_username === 'string' ? claims.preferred_username : ''
  if (!username || !roles(claims).includes(ROLE)) {
    return done(null, false, { message: `Tài khoản không có vai trò ${ROLE} của client ${CLIENT_ID}` })
  }
  operators.add(username)
  return done(null, { username })
}

function operator(username) {
  return operators.has(username) ? { username, permissions: '*' } : null
}

module.exports = {
  uiPort: 1880,
  flowFile: 'flows.json',
  credentialSecret: SECRET,
  httpAdminRoot: '/tu-dong',
  httpNodeRoot: false,
  // cookie phiên chỉ dùng trong lúc bắt tay với Keycloak (giữ PKCE): chỉ gửi về /tu-dong
  httpAdminCookieOptions: { path: '/tu-dong', sameSite: 'lax' },
  sessionExpiryTime: SESSION_S,
  adminAuth: {
    type: 'strategy',
    strategy: {
      name: 'keycloak',
      label: 'Đăng nhập bằng tài khoản Signet',
      autoLogin: true,
      strategy: Strategy,
      options: {
        name: 'keycloak',
        config,
        scope: 'openid',
        callbackURL: `${PUBLIC_URL}/tu-dong/auth/strategy/callback`,
        verify,
      },
    },
    users: (username) => Promise.resolve(operator(username)),
    authenticate: (profile) => Promise.resolve(profile && operator(profile.username)),
  },
  externalModules: {
    autoInstall: false,
    palette: { allowInstall: false, allowUpload: false },
    modules: { allowInstall: false },
  },
  functionExternalModules: false,
  functionGlobalContext: {},
  exportGlobalContextKeys: false,
  nodesExcludes: ['90-exec.js', '10-file.js', '23-watch.js'],
  diagnostics: { enabled: false, ui: false },
  runtimeState: { enabled: false, ui: false },
  telemetry: { enabled: false, updateNotification: false },
  logging: { console: { level: 'info', metrics: false, audit: true } },
  editorTheme: {
    page: { title: 'Signet · Tự động hóa' },
    header: { title: 'Signet · Tự động hóa' },
    tours: false,
    projects: { enabled: false },
  },
}
