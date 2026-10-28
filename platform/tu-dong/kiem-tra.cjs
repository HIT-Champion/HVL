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

// Chạy lúc dựng image (Dockerfile): nạp settings.js bằng Node của image với giá trị giả, dựng chiến lược đăng nhập như
// Node-RED, thử verify với token có và không có vai trò operator, kiểm URL đăng nhập (PKCE S256, redirect công khai)

const assert = require('node:assert/strict')

process.env.MOC_PUBLIC_URL = 'https://signet.example'
process.env.MOC_TU_DONG_SECRET = 'khong-phai-khoa-that-'.repeat(2)
const settings = require('./settings.js')
assert.equal(process.env.MOC_TU_DONG_SECRET, undefined, 'khóa còn trong biến môi trường')
assert.equal(settings.httpNodeRoot, false)
assert.deepEqual(settings.nodesExcludes, ['90-exec.js'])
assert.equal(settings.functionExternalModules, false)
assert.equal(settings.externalModules.palette.allowInstall, false)

const { strategy } = settings.adminAuth
const instance = new strategy.strategy(strategy.options, strategy.options.verify)
assert.equal(instance.name, strategy.name)

// verify chỉ đọc claim của ID token đã kiểm; access token mang vai trò thì không tính
const jwt = (payload) => `h.${Buffer.from(JSON.stringify(payload)).toString('base64url')}.s`
const tokens = (username, client, inAccessToken = false) => {
  const resource_access = { [client]: { roles: ['operator'] } }
  return inAccessToken
    ? { claims: () => ({ preferred_username: username }), access_token: jwt({ resource_access }) }
    : { claims: () => ({ preferred_username: username, resource_access }), access_token: jwt({}) }
}
const verified = (t) => new Promise((resolve) => strategy.options.verify(t, (err, user) => resolve(err || user)))

async function main() {
  assert.deepEqual(await verified(tokens('vanhanh', 'tu-dong')), { username: 'vanhanh' })
  assert.equal(await verified(tokens('vanthu', 'app-office')), false)
  assert.equal(await verified(tokens('khach', 'tu-dong', true)), false)
  assert.equal(await verified(tokens('', 'tu-dong')), false)
  assert.deepEqual(await settings.adminAuth.users('vanhanh'), { username: 'vanhanh', permissions: '*' })
  assert.equal(await settings.adminAuth.users('vanthu'), null)

  const req = { session: {}, method: 'GET', protocol: 'http', get: () => 'tu-dong:1880', socket: {},
    originalUrl: '/tu-dong/auth/strategy', app: { get: () => () => false } }
  const url = await new Promise((resolve, reject) => {
    instance.redirect = resolve
    instance.error = reject
    instance.authenticate(req, {})
  })
  const u = new URL(url)
  assert.equal(u.origin + u.pathname, 'https://signet.example/realms/moc/protocol/openid-connect/auth')
  assert.equal(u.searchParams.get('client_id'), 'tu-dong')
  assert.equal(u.searchParams.get('code_challenge_method'), 'S256')
  assert.equal(u.searchParams.get('redirect_uri'), 'https://signet.example/tu-dong/auth/strategy/callback')
  console.log('settings.js: đạt')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
