<!--
  Copyright 2026 Signet Team

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ApiError } from '~/composables/useApi'

// Kênh SMS, Zalo cho thông báo của chính người dùng (#365), ở cuối chuông thông báo. Bản cài chưa cấu hình kênh
// nào thì myChannels rỗng và mục này không hiện. SMS gửi tới số trong danh bạ (quản trị nhập ở Keycloak); Zalo liên
// kết bằng mã dùng một lần nhắn cho bot của đơn vị. Tải lại mỗi lần mở chuông: nhắn mã xong mở lại là thấy đã liên kết
interface MyChannel {
  channel: string
  enabled: boolean
  phone: string | null
  link_code: string | null
  link_expires_at: string | null
  bot_url: string | null
}

const FIELDS = 'channel enabled phone link_code link_expires_at bot_url'
const MINE = `query { myChannels { ${FIELDS} } }`
const SET = `mutation ($channel: String!, $enabled: Boolean!) {
  setMyChannel(channel: $channel, enabled: $enabled) { ${FIELDS} }
}`
// mã lỗi svc-workflow trả cho setMyChannel (subscriptions.py) → câu trong channels.error
const CODES = new Set(['channel_off', 'no_phone', 'not_synced'])

const { t } = useI18n()
const { gql } = useApi()
const notice = useNotice()
const channels = ref<MyChannel[]>([])
const busy = ref(false)

async function load() {
  try {
    channels.value = (await gql<{ myChannels: MyChannel[] }>(MINE)).myChannels
  } catch {
    channels.value = []        // lõi cũ chưa có action, mạng lỗi: ẩn mục này, chuông vẫn dùng được
  }
}

async function set(channel: string, enabled: boolean) {
  busy.value = true
  try {
    channels.value = (await gql<{ setMyChannel: MyChannel[] }>(SET, { channel, enabled })).setMyChannel
  } catch (e) {
    notice.error(e instanceof ApiError && e.code && CODES.has(e.code) ? t(`channels.error.${e.code}`) : errorText(t, e))
  } finally {
    busy.value = false
  }
}

async function check() {
  busy.value = true
  await load()
  busy.value = false
  if (channels.value.some((c) => c.channel === 'zalo' && c.enabled)) notice.ok(t('channels.zaloDone'))
}

// địa chỉ bot do người vận hành đặt (MOC_ZALO_BOT_URL): chỉ mở liên kết https
const botUrl = (c: MyChannel) => (c.bot_url?.startsWith('https://') ? c.bot_url : null)

onMounted(load)
</script>

<template>
  <section v-if="channels.length" class="border-t border-stone-200 px-4 py-3" data-testid="notification-channels">
    <h3 class="text-xs font-semibold text-stone-600">{{ t('channels.title') }}</h3>
    <ul class="mt-2 space-y-3">
      <li v-for="c in channels" :key="c.channel" class="text-sm" :data-testid="`channel-${c.channel}`">
        <div class="flex items-start justify-between gap-3">
          <div v-if="c.channel === 'sms'" class="min-w-0">
            <div class="font-medium text-stone-900">{{ t('channels.sms') }}</div>
            <div class="text-xs text-stone-500">
              {{ c.phone ? t('channels.smsTo', { phone: c.phone }) : t('channels.noPhone') }}
            </div>
          </div>
          <div v-else class="min-w-0">
            <div class="font-medium text-stone-900">{{ t('channels.zalo') }}</div>
            <div v-if="c.enabled" class="text-xs text-stone-500">{{ t('channels.zaloLinked') }}</div>
            <div v-else-if="c.link_code" class="text-xs text-stone-500">{{ t('channels.zaloPending') }}</div>
            <div v-else class="text-xs text-stone-500">{{ t('channels.zaloOff') }}</div>
          </div>
          <button
            v-if="c.channel === 'sms'" type="button" role="switch"
            :aria-checked="c.enabled" :aria-label="t('channels.sms')" :disabled="busy || (!c.phone && !c.enabled)"
            class="relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors
              disabled:opacity-50"
            :class="c.enabled ? 'bg-brand-700' : 'bg-stone-400'"
            @click="set('sms', !c.enabled)"
          >
            <span
              class="inline-block h-4 w-4 rounded-full bg-white shadow transition-transform" aria-hidden="true"
              :class="c.enabled ? 'translate-x-[1.125rem]' : 'translate-x-0.5'"
            />
          </button>
          <button
            v-else-if="c.enabled || c.link_code" type="button" :disabled="busy"
            class="shrink-0 text-xs font-medium text-stone-600 hover:underline" @click="set('zalo', false)"
          >{{ c.enabled ? t('channels.turnOff') : t('channels.cancel') }}</button>
          <button
            v-else type="button" :disabled="busy" data-testid="zalo-link"
            class="shrink-0 text-xs font-medium text-brand-700 hover:underline" @click="set('zalo', true)"
          >{{ t('channels.link') }}</button>
        </div>
        <div v-if="c.channel === 'zalo' && !c.enabled && c.link_code" class="mt-2 rounded-md bg-stone-50 p-3">
          <p class="text-xs text-stone-600">{{ t('channels.zaloStep') }}</p>
          <p class="mt-1 font-mono text-lg font-semibold tracking-widest text-stone-900" data-testid="zalo-code">
            {{ c.link_code }}
          </p>
          <p class="text-xs text-stone-600">{{ t('channels.expires', { at: fmtDateTime(c.link_expires_at) }) }}</p>
          <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-medium">
            <a
              v-if="botUrl(c)" :href="botUrl(c)!" target="_blank" rel="noopener noreferrer"
              class="text-brand-700 hover:underline"
            >{{ t('channels.openBot') }}</a>
            <button type="button" :disabled="busy" class="text-brand-700 hover:underline" @click="check">
              {{ t('channels.check') }}
            </button>
            <button type="button" :disabled="busy" class="text-stone-600 hover:underline" @click="set('zalo', true)">
              {{ t('channels.newCode') }}
            </button>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>
