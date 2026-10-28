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


// Chuông thông báo: câu của cảnh báo vận hành (F3.13, #284), đường dẫn khi bấm thông báo (chuông, toast), chuông hiện
// cho mọi vai trò — cả quản trị đơn vị, vai trò duy nhất nhận ops.alert.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

// useNotifications.ts dùng ref của Vue do Nuxt tự import: giả bản tối thiểu trước khi nạp
Object.assign(globalThis, { ref: <T>(value: T) => ({ value }) })
const { describeNotification, notificationLink } = await import('../app/composables/useNotifications.ts')

const t = (key: string, params?: Record<string, unknown>) => (params ? `${key} ${JSON.stringify(params)}` : key)
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('cảnh báo vận hành: câu theo trạng thái, chi tiết là thành phần và route', () => {
  const data = { status: 'firing', message: 'Thành phần hasura gián đoạn', component: 'hasura', route: '/v1/graphql' }
  assert.deepEqual(describeNotification(t, { kind: 'ops.alert', data }), {
    title: 'notify.opsAlert {"message":"Thành phần hasura gián đoạn"}', detail: 'hasura — /v1/graphql', note: '',
  })
  const resolved = { status: 'resolved', message: 'ComponentDown' }
  assert.deepEqual(describeNotification(t, { kind: 'ops.alert', data: resolved }), {
    title: 'notify.opsResolved {"message":"ComponentDown"}', detail: '', note: '',
  })
})

test('bấm thông báo: văn bản gắn kèm, cảnh báo vận hành mở trang trạng thái, còn lại không đi đâu', () => {
  assert.equal(notificationLink({ kind: 'task.assigned', document_id: 'd-1' }), '/van-ban/d-1')
  assert.equal(notificationLink({ kind: 'ops.alert', document_id: null }), '/trang-thai')
  assert.equal(notificationLink({ kind: 'task.assigned', document_id: null }), undefined)
})

test('câu cảnh báo có ở cả hai ngôn ngữ, cùng tham số message', () => {
  for (const lang of ['vi', 'en']) {
    const notify = JSON.parse(read(`../app/locales/${lang}.json`)).notify as Record<string, string>
    for (const key of ['opsAlert', 'opsResolved']) assert.match(notify[key] ?? '', /\{message\}/, `${lang} ${key}`)
  }
})

test('chuông hiện cho mọi vai trò đã đăng nhập, kể cả quản trị đơn vị', () => {
  const bell = read('../app/layouts/default.vue').split('\n').filter((line) => line.includes('<NotificationBell'))
  assert.deepEqual(bell.map((line) => line.trim()), ['<NotificationBell v-if="claims?.role" />'])
})
