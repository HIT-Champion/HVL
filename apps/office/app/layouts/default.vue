<!--
  Copyright 2026 Mộc Team

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

const { t, locale } = useI18n()
const auth = useAuth()
const claims = auth.claims
const route = useRoute()
const open = ref(false)

const { gql } = useApi()
const tenantName = ref('')
onMounted(async () => {
  try {
    const data = await gql<{ core_tenants: { name: string }[] }>('{ core_tenants { name } }')
    tenantName.value = data.core_tenants[0]?.name ?? ''
  } catch {
    // tên đơn vị chỉ để hiển thị
  }
})

const nav = computed(() => {
  const role = claims.value?.role
  const items = [] as { to: string; label: string; icon: string }[]
  if (role && role !== 'tenant_admin') items.push({ to: '/', label: t('nav.inbox'), icon: 'M3 7l9 6 9-6M5 5h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z' })
  if (role && role !== 'tenant_admin') items.push({ to: '/van-ban-den', label: t('nav.incoming'), icon: 'M4 4h10l6 6v10a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1zm10 0v6h6' })
  if (role === 'clerk') items.push({ to: '/van-ban-den/tiep-nhan', label: t('nav.receive'), icon: 'M12 5v14m-7-7h14' })
  if (role && role !== 'tenant_admin') items.push({ to: '/van-ban-di', label: t('nav.outgoing'), icon: 'M4 12l16-8-6 16-2-7-8-1z' })
  if (role === 'staff') items.push({ to: '/van-ban-di/soan', label: t('nav.compose'), icon: 'M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17v3zM13.5 7.5l3 3' })
  if (role === 'clerk' || role === 'director') items.push({ to: '/so-dang-ky', label: t('nav.register'), icon: 'M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2V5zm0 16a2 2 0 012-2h13v2H6a2 2 0 01-2 0zM8 7h7M8 11h7' })
  items.push({ to: '/tim-kiem', label: t('nav.search'), icon: 'M21 21l-4.3-4.3M10.5 18a7.5 7.5 0 110-15 7.5 7.5 0 010 15z' })
  // Hỏi đáp trên kho văn bản (F4.2): vai trò nghiệp vụ; quản trị đơn vị không đọc văn bản nên không hỏi được
  if (role === 'clerk' || role === 'staff' || role === 'manager' || role === 'director') items.push({ to: '/hoi-dap', label: t('nav.ask'), icon: 'M8 10h8M8 14h5M21 12a9 9 0 01-13.2 8L3 21l1.1-4.6A9 9 0 1121 12z' })
  if (role === 'director') items.push({ to: '/dieu-hanh', label: t('nav.board'), icon: 'M3 3v18h18M8 17v-4m4 4V8m4 9v-6' })
  if (role === 'director' || role === 'tenant_admin') items.push({ to: '/so-kiem-toan', label: t('nav.audit'), icon: 'M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6l7-3zm-3 9l2 2 4-4' })
  return items
})

function active(to: string) {
  return route.path === to
}

function toggleLocale() {
  locale.value = locale.value === 'vi' ? 'en' : 'vi'
  try { localStorage.setItem('moc.locale', locale.value) } catch { /* bỏ qua */ }
  document.documentElement.lang = locale.value
}

watch(() => route.fullPath, () => { open.value = false })

// Thông báo (F2.5): một kết nối realtime cho cả phiên làm việc; mỗi lần (nối lại) kết nối thì tải lại danh sách,
// vì tin đẩy lúc mất kết nối không được gửi lại
const realtime = useRealtime()
const notifications = useNotifications()
const notice = useNotice()
const reload = () => notifications.load().catch(() => { /* chuông chỉ để hiển thị */ })
realtime.onConnected(reload)
realtime.onMessage((msg) => {
  notifications.receive(msg)
  const text = describeNotification(t, msg)
  notice.info(text.title, { detail: text.note || text.detail, to: msg.document_id ? `/van-ban/${msg.document_id}` : undefined })
})
onMounted(() => {
  reload()
  realtime.start()
  window.addEventListener('online', realtime.online)
})
onBeforeUnmount(() => {
  window.removeEventListener('online', realtime.online)
  realtime.stop()
})

async function logout() {
  realtime.stop()
  await auth.logout()
}
</script>

<template>
  <div class="min-h-screen md:flex">
    <!-- thanh bên -->
    <aside
      class="fixed inset-y-0 left-0 z-40 w-64 -translate-x-full border-r border-stone-200 bg-white transition md:static md:translate-x-0"
      :class="{ 'translate-x-0': open }"
    >
      <div class="flex h-16 items-center gap-3 border-b border-stone-200 px-5">
        <img src="/favicon.svg" alt="" class="h-8 w-8">
        <div>
          <div class="text-lg leading-none font-semibold text-brand-800">{{ t('app.name') }}</div>
          <div class="text-xs text-stone-500">{{ t('app.tagline') }}</div>
        </div>
      </div>
      <nav class="space-y-1 p-3">
        <NuxtLink
          v-for="item in nav" :key="item.to" :to="item.to"
          class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium"
          :class="active(item.to) ? 'bg-brand-50 text-brand-800' : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900'"
        >
          <svg class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" />
          </svg>
          {{ item.label }}
        </NuxtLink>
      </nav>
      <div class="absolute inset-x-0 bottom-0 border-t border-stone-200 p-4 text-xs text-stone-500">
        {{ tenantName }}
      </div>
    </aside>
    <div v-if="open" class="fixed inset-0 z-30 bg-black/30 md:hidden" @click="open = false" />

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- thanh trên -->
      <header class="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-stone-200 bg-white/90 px-4 backdrop-blur md:px-8">
        <button class="btn-ghost md:hidden" :aria-label="t('nav.inbox')" @click="open = !open">
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <div class="flex-1" />
        <button class="btn-ghost text-xs" @click="toggleLocale">{{ t('nav.language') }}</button>
        <NotificationBell v-if="claims?.role && claims.role !== 'tenant_admin'" />
        <div v-if="claims" class="hidden text-right sm:block">
          <div class="text-sm font-medium text-stone-900">{{ claims.name }}</div>
          <div class="text-xs text-stone-500">{{ claims.role ? t(`role.${claims.role}`) : t('error.noRole') }}</div>
        </div>
        <div class="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-800" aria-hidden="true">
          {{ claims?.name?.split(' ').pop()?.[0] ?? '?' }}
        </div>
        <button class="btn-secondary" @click="logout">{{ t('nav.logout') }}</button>
      </header>
      <main class="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">
        <slot />
      </main>
    </div>
  </div>
</template>
