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

<script setup>
import { useI18n } from 'vue-i18n';
const {
  t,
  locale
} = useI18n();
const auth = useAuth();
const claims = auth.claims;
const route = useRoute();
const open = ref(false);
const collapsed = ref(false);
const calendarDay = ref(today());
const dateLabel = computed(() => new Intl.DateTimeFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(calendarDay.value + 'T12:00:00')));
let calendarClock;
function toggleSidebar() {
  collapsed.value = !collapsed.value;
  try { localStorage.setItem('signet.sidebar.collapsed', String(collapsed.value)); } catch { /* preference only */ }
}
const mobile = ref(false);
const menuButton = ref(null);
let media;
const updateViewport = () => { mobile.value = media.matches; if (!mobile.value) open.value = false; };
onMounted(() => { try { collapsed.value = localStorage.getItem('signet.sidebar.collapsed') === 'true'; } catch { /* preference only */ } calendarClock = setInterval(() => { calendarDay.value = today(); }, 60000); media = window.matchMedia('(max-width: 900px)'); updateViewport(); media.addEventListener('change', updateViewport); });
onBeforeUnmount(() => { media?.removeEventListener('change', updateViewport); clearInterval(calendarClock); document.body.style.overflow = ''; });
watch(open, async value => { document.body.style.overflow = value && mobile.value ? 'hidden' : ''; await nextTick(); if (value) document.querySelector('#app-navigation a')?.focus(); else if (mobile.value) menuButton.value?.focus(); });
const router = useRouter();
function keyboard(event) {
  if (event.key === 'Escape') open.value = false;
  if (event.key === 'Tab' && open.value && mobile.value) {
    const items = [...document.querySelectorAll('#app-navigation a, #app-navigation button')].filter(item => item.getClientRects().length && getComputedStyle(item).visibility !== 'hidden');
    const first = items[0], last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    router.push('/tim-kiem');
  }
}
onMounted(() => window.addEventListener('keydown', keyboard));
onBeforeUnmount(() => window.removeEventListener('keydown', keyboard));
const {
  gql
} = useApi();
const tenantName = ref('');
onMounted(async () => {
  try {
    const data = await gql('{ core_tenants { name } }');
    tenantName.value = data.core_tenants[0]?.name ?? '';
  } catch {
    // tên đơn vị chỉ để hiển thị
  }
});
const nav = computed(() => {
  const role = claims.value?.role;
  const items = [];
  if (role && role !== 'tenant_admin') items.push({
    to: '/',
    label: t('nav.inbox'),
    icon: 'M3 7l9 6 9-6M5 5h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z'
  });
  if (role && role !== 'tenant_admin') items.push({
    to: '/van-ban-den',
    label: t('nav.incoming'),
    icon: 'M4 4h10l6 6v10a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1zm10 0v6h6'
  });
  if (role === 'clerk') items.push({
    to: '/van-ban-den/tiep-nhan',
    label: t('nav.receive'),
    icon: 'M12 5v14m-7-7h14'
  });
  if (role && role !== 'tenant_admin') items.push({
    to: '/van-ban-di',
    label: t('nav.outgoing'),
    icon: 'M4 12l16-8-6 16-2-7-8-1z'
  });
  if (role === 'clerk' || role === 'director') items.push({
    to: '/so-dang-ky',
    label: t('nav.register'),
    icon: 'M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2V5zm0 16a2 2 0 012-2h13v2H6a2 2 0 01-2 0zM8 7h7M8 11h7'
  });
  if (['clerk', 'staff', 'manager', 'director'].includes(role)) items.push({ to: '/hoi-dap', label: t('nav.ask'), icon: 'M8 10h8M8 14h5M21 12a9 9 0 01-13.2 8L3 21l1.1-4.6A9 9 0 1121 12z' });
  if (role === 'director') items.push({
    to: '/dieu-hanh',
    label: t('nav.board'),
    icon: 'M3 3v18h18M8 17v-4m4 4V8m4 9v-6'
  });
  if (role === 'director' || role === 'tenant_admin') items.push({
    to: '/so-kiem-toan',
    label: t('nav.audit'),
    icon: 'M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6l7-3zm-3 9l2 2 4-4'
  });
  if (role && role !== 'tenant_admin') items.push({ to: '/ho-so', label: t('cases.title'), icon: 'M3 7h7l2 2h9v11H3V7zm0 0V4h7l2 3' });
  return items;
});
function active(to) {
  if (to === '/') return route.path === '/';
  return route.path === to || (route.path.startsWith(to + '/') && !nav.value.some(item => item.to !== to && route.path === item.to));
}
function toggleLocale() {
  locale.value = locale.value === 'vi' ? 'en' : 'vi';
  try {
    localStorage.setItem('moc.locale', locale.value);
  } catch {/* bỏ qua */}
  document.documentElement.lang = locale.value;
}
watch(() => route.fullPath, () => {
  open.value = false;
});

// Thông báo (F2.5): một kết nối realtime cho cả phiên làm việc; mỗi lần (nối lại) kết nối thì tải lại danh sách,
// vì tin đẩy lúc mất kết nối không được gửi lại
const realtime = useRealtime();
const notifications = useNotifications();
const notice = useNotice();
let notificationPoll;
const reload = () => notifications.load().catch(() => {/* chuông chỉ để hiển thị */});
realtime.onConnected(reload);
realtime.onMessage(msg => {
  notifications.receive(msg);
  const text = describeNotification(t, msg);
  notice.info(text.title, {
    detail: text.note || text.detail,
    to: msg.document_id ? `/van-ban/${msg.document_id}` : undefined
  });
});
onMounted(() => {
  reload();
  // HMR dev server is a different origin; production receives the secured WebSocket.
  if (import.meta.dev) notificationPoll = setInterval(reload, 15000);
  else realtime.start();
  window.addEventListener('online', realtime.online);
});
onBeforeUnmount(() => {
  window.removeEventListener('online', realtime.online);
  realtime.stop();
  clearInterval(notificationPoll);
});
async function logout() {
  realtime.stop();
  await auth.logout();
}
</script>

<template>
  <div class="sg-shell" :class="{ 'is-collapsed': collapsed, 'is-mobile-open': open }">
    <a href="#main-content" class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 btn-primary">{{ t('fe.skip') }}</a>
    <aside id="app-navigation" class="sg-sidebar" :inert="mobile && !open ? true : undefined" :aria-label="t('fe.navigation')">
      <div class="sg-brand-row"><NuxtLink to="/" class="sg-wordmark" :aria-label="t('app.name')"><span class="sg-brand-full">Signet</span><span class="sg-brand-short" aria-hidden="true">S</span></NuxtLink><button class="btn-ghost sg-close-menu" :aria-label="t('shell.closeNav')" @click="open = false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button></div>
      <nav class="sg-nav" :aria-label="t('fe.navigation')"><NuxtLink v-for="item in nav" :key="item.to" :to="item.to" class="sg-nav-link" :class="{ 'is-active': active(item.to) }" :aria-label="item.label" :title="collapsed ? item.label : undefined" :aria-current="active(item.to) ? 'page' : undefined"><svg width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" /></svg><span class="sg-nav-label">{{ item.label }}</span></NuxtLink></nav>
      <div class="sg-sidebar-bottom">
        <NuxtLink to="/tim-kiem" class="sg-nav-link sg-search-link" :aria-label="t('nav.search')" :title="collapsed ? t('nav.search') : undefined"><svg width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M21 21l-4.3-4.3M10.5 18a7.5 7.5 0 110-15 7.5 7.5 0 010 15z" /></svg><span class="sg-nav-label">{{ t('nav.search') }}</span></NuxtLink>
        <button class="sg-sidebar-toggle sg-nav-link" :aria-label="t(collapsed ? 'shell.expand' : 'shell.collapse')" :title="t(collapsed ? 'shell.expand' : 'shell.collapse')" aria-controls="app-navigation" :aria-expanded="!collapsed" @click="toggleSidebar"><svg width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 4h16v16H4zM9 4v16m6-11-3 3 3 3" /></svg><span class="sg-nav-label">{{ t('shell.collapse') }}</span></button>
        <div class="sg-account"><span class="sg-avatar" aria-hidden="true">{{ initialOf(claims?.givenName || '', claims?.name || '') }}</span><div class="sg-account-name sg-nav-label"><strong>{{ claims?.name }}</strong><small>{{ claims?.role ? t('role.' + claims.role) : t('error.noRole') }}</small></div><button class="btn-ghost sg-logout" :aria-label="t('nav.logout')" :title="t('nav.logout')" @click="logout"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M9 4H4v16h5m6-4l4-4-4-4m-7 4h11" /></svg></button></div>
      </div>
    </aside>
    <button v-if="open" class="sg-scrim" :aria-label="t('shell.closeNav')" tabindex="-1" @click="open = false" />
    <div class="sg-workspace" :inert="mobile && open ? true : undefined">
      <header class="sg-topbar"><div class="sg-topbar-context"><button ref="menuButton" class="btn-secondary sg-mobile-menu" :aria-label="t('fe.menu')" aria-controls="app-navigation" :aria-expanded="open" @click="open = !open"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button><span>{{ tenantName || t('fe.organization') }}</span></div><div class="sg-topbar-tools"><time :datetime="calendarDay">{{ dateLabel }}</time><NotificationBell /><button class="btn-ghost sg-language" :aria-label="t('nav.language')" @click="toggleLocale">{{ locale === 'vi' ? 'EN' : 'VI' }}</button></div></header>
      <main id="main-content" class="moc-sheet"><slot /></main>
      <footer class="moc-shell-footer"><span>Signet <span aria-hidden="true">/</span> {{ t('app.tagline') }}</span><NuxtLink to="/xac-thuc" class="moc-footer-verify">{{ t('fe.verify') }}</NuxtLink><span>{{ t('fe.localData') }}</span></footer>
    </div>
  </div>
</template>
