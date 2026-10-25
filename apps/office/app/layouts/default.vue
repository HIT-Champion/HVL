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
const hovering = ref(false);
const navigationFocused = ref(false);
const collapsed = computed(() => !mobile.value && !hovering.value && !navigationFocused.value);
let hoverExit;
function enterNavigation() { clearTimeout(hoverExit); hovering.value = true; }
function leaveNavigation() { clearTimeout(hoverExit); hoverExit = setTimeout(() => { hovering.value = false; }, 140); }
function focusNavigation(event) { navigationFocused.value = event.target.matches(':focus-visible'); }
function blurNavigation(event) { navigationFocused.value = navigationFocused.value && event.currentTarget.contains(event.relatedTarget); }
const calendarDay = ref(today());
const dateLabel = computed(() => new Intl.DateTimeFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(calendarDay.value + 'T12:00:00')));
let calendarClock;
const mobile = ref(false);
const menuButton = ref(null);
let media;
const updateViewport = () => { mobile.value = media.matches; if (!mobile.value) open.value = false; };
onMounted(() => { calendarClock = setInterval(() => { calendarDay.value = today(); }, 60000); media = window.matchMedia('(max-width: 900px), (hover: none)'); updateViewport(); media.addEventListener('change', updateViewport); });
onBeforeUnmount(() => { media?.removeEventListener('change', updateViewport); clearInterval(calendarClock); clearTimeout(hoverExit); document.body.style.overflow = ''; });
function focusMobileNavigation(event) {
  if (event && (event.target !== event.currentTarget || event.propertyName !== 'transform')) return;
  if (!open.value || !mobile.value) return;
  const navigation = document.querySelector('#app-navigation');
  if (navigation && !navigation.contains(document.activeElement) && getComputedStyle(navigation).visibility === 'visible') navigation.querySelector('a')?.focus({ preventScroll: true });
}
watch(open, async value => {
  document.body.style.overflow = value && mobile.value ? 'hidden' : '';
  await nextTick();
  await new Promise(requestAnimationFrame);
  if (value && open.value) {
    focusMobileNavigation();
    requestAnimationFrame(() => focusMobileNavigation());
  } else if (mobile.value && !open.value) menuButton.value?.focus();
});
const router = useRouter();
function keyboard(event) {
  if (event.key === 'Escape') open.value = false;
  if (event.key === 'Tab' && open.value && mobile.value) {
    const items = [...document.querySelectorAll('#app-navigation a, #app-navigation button')].filter(item => item.getClientRects().length && getComputedStyle(item).visibility !== 'hidden');
    const first = items[0], last = items.at(-1);
    if (!document.querySelector('#app-navigation')?.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first)?.focus(); return; }
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
const nav = computed(() => primaryNavigation(claims.value?.role, t));
const toolNav = computed(() => toolNavigation(claims.value?.role, t));
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
    <aside id="app-navigation" @transitionend="focusMobileNavigation" class="sg-sidebar" @pointerenter="enterNavigation" @pointerleave="leaveNavigation" @pointerdown="navigationFocused = false" @focusin="focusNavigation" @focusout="blurNavigation" :inert="mobile && !open ? true : undefined" :aria-label="t('fe.navigation')">
      <div class="sg-brand-row"><NuxtLink to="/" class="sg-wordmark" :aria-label="t('app.name')"><svg class="sg-brand-mark" viewBox="0 0 64 64" fill="none" aria-hidden="true"><path d="M45 10H26c-9 0-16 7-16 16s7 16 16 16h12" stroke="currentColor" stroke-width="9" stroke-linecap="round"/><path d="M19 54h19c9 0 16-7 16-16s-7-16-16-16H26" stroke="currentColor" stroke-width="9" stroke-linecap="round"/></svg><span class="sg-brand-full">Signet</span></NuxtLink><button class="btn-ghost sg-close-menu" :aria-label="t('shell.closeNav')" @click="open = false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button></div>
      <nav class="sg-nav" :aria-label="t('fe.navigation')"><NuxtLink v-for="item in nav" :key="item.to" :to="item.to" class="sg-nav-link" :class="{ 'is-active': active(item.to) }" :aria-label="item.label" :title="collapsed ? item.label : undefined" :aria-current="active(item.to) ? 'page' : undefined"><svg width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" /></svg><span class="sg-nav-label">{{ item.label }}</span></NuxtLink><div v-if="toolNav.length" class="sg-nav-section"><span class="sg-nav-label">{{ t('fe.tools') }}</span></div><NuxtLink v-for="item in toolNav" :key="item.to" :to="item.to" class="sg-nav-link" :class="{ 'is-active': active(item.to) }" :aria-label="item.label" :title="collapsed ? item.label : undefined" :aria-current="active(item.to) ? 'page' : undefined"><svg width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" /></svg><span class="sg-nav-label">{{ item.label }}</span></NuxtLink></nav>
      <div class="sg-sidebar-bottom">
        <NuxtLink to="/tim-kiem" class="sg-nav-link sg-search-link" :aria-label="t('nav.search')" :title="collapsed ? t('nav.search') : undefined"><svg width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M21 21l-4.3-4.3M10.5 18a7.5 7.5 0 110-15 7.5 7.5 0 010 15z" /></svg><span class="sg-nav-label">{{ t('nav.search') }}</span></NuxtLink>
        <div class="sg-account"><span class="sg-avatar" data-testid="avatar-initial" aria-hidden="true">{{ initialOf(claims?.givenName || '', claims?.name || '') }}</span><div class="sg-account-name sg-nav-label"><strong>{{ claims?.name }}</strong><small>{{ claims?.role ? t('role.' + claims.role) : t('error.noRole') }}</small></div><button class="btn-ghost sg-logout" :aria-label="t('nav.logout')" :title="t('nav.logout')" @click="logout"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M9 4H4v16h5m6-4l4-4-4-4m-7 4h11" /></svg></button></div>
      </div>
    </aside>
    <Transition name="sg-scrim"><button v-if="open" class="sg-scrim" :aria-label="t('shell.closeNav')" tabindex="-1" @click="open = false" /></Transition>
    <div class="sg-workspace" :inert="mobile && open ? true : undefined">
      <header class="sg-topbar"><div class="sg-topbar-context"><button ref="menuButton" class="btn-secondary sg-mobile-menu" :aria-label="t('fe.menu')" aria-controls="app-navigation" :aria-expanded="open" @click="open = !open"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button><span>{{ tenantName || t('fe.organization') }}</span></div><div class="sg-topbar-tools"><time :datetime="calendarDay">{{ dateLabel }}</time><FeedbackButton v-if="claims?.role" /><NotificationBell v-if="claims?.role && claims.role !== 'tenant_admin'" /><button class="btn-ghost sg-language" :aria-label="t('nav.language')" @click="toggleLocale">{{ locale === 'vi' ? 'EN' : 'VI' }}</button></div></header>
      <main id="main-content" class="moc-sheet"><slot /></main>
      <footer class="moc-shell-footer"><span>Signet <span aria-hidden="true">/</span> {{ t('app.tagline') }}</span><NuxtLink to="/trang-thai" class="moc-footer-status">{{ t('health.title') }}</NuxtLink><NuxtLink to="/xac-thuc" class="moc-footer-verify">{{ t('fe.verify') }}</NuxtLink><span>{{ t('fe.localData') }}</span></footer>
    </div>
  </div>
</template>
