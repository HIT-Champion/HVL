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

const { t, locale } = useI18n()
const auth = useAuth()
const claims = auth.claims
const route = useRoute()

// Thanh bên: trên máy tính thu về một dải biểu tượng, mở ra khi rê chuột vào hoặc khi focus bằng bàn phím. Mở hay thu,
// nội dung đều dịch theo (main.css), không bị che. Chỉ con trỏ rời thanh bên mới thu lại: bấm một mục, kể cả mục của
// trang đang mở, hay đổi trang đều không thu. Màn hẹp hay màn cảm ứng: ngăn kéo mở bằng nút menu, Esc đóng, Tab chỉ đi
// vòng trong ngăn kéo.
const open = ref(false)
const mobile = ref(false)
const hovering = ref(false)
const keyboardFocus = ref(false)
const collapsed = computed(() => !mobile.value && !hovering.value && !keyboardFocus.value)
const menuButton = ref<HTMLButtonElement | null>(null)
let hoverExit: ReturnType<typeof setTimeout> | undefined
// Bấm một mục: đóng ngăn kéo. Bấm bằng chuột còn xóa focus bàn phím: Tab tới một mục rồi bấm chuột đúng mục đó thì
// không có focusin mới, thanh bên sẽ mở mãi theo focus cũ dù con trỏ đã rời đi. Enter bằng bàn phím (event.detail = 0)
// vẫn giữ thanh bên mở theo focus
function pickInNavigation(event: MouseEvent) {
  if (!(event.target as HTMLElement).closest('a[href]')) return
  open.value = false
  if (event.detail) keyboardFocus.value = false
}
// Mở theo pointermove có dịch chuyển, không theo pointerenter: Chrome bắn pointerenter lên thanh bên cả khi con trỏ
// đứng yên mà bố cục đổi (lúc chụp ảnh toàn trang cửa sổ thu về 1×1 rồi trả lại), thanh bên tự mở
function moveInNavigation(event: PointerEvent) {
  if (!event.movementX && !event.movementY) return
  clearTimeout(hoverExit)
  hovering.value = true
}
function leaveNavigation() {
  clearTimeout(hoverExit)
  hoverExit = setTimeout(() => { hovering.value = false }, 140)
}
function focusNavigation(event: FocusEvent) {
  keyboardFocus.value = (event.target as HTMLElement).matches(':focus-visible')
}
function blurNavigation(event: FocusEvent) {
  if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) keyboardFocus.value = false
}

let media: MediaQueryList | undefined
function updateViewport() {
  mobile.value = media?.matches ?? false
  if (!mobile.value) open.value = false
}
onMounted(() => {
  media = window.matchMedia('(max-width: 900px), (hover: none)')
  updateViewport()
  media.addEventListener('change', updateViewport)
})
watch(open, async (value) => {
  document.body.style.overflow = value && mobile.value ? 'hidden' : ''
  await nextTick()
  if (value) document.querySelector<HTMLElement>('#app-navigation a')?.focus()
  else if (mobile.value) menuButton.value?.focus()
})

function keyboard(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
  if (event.key === 'Tab' && open.value && mobile.value) {
    const items = [...document.querySelectorAll<HTMLElement>('#app-navigation a, #app-navigation button')]
      .filter((item) => item.getClientRects().length && getComputedStyle(item).visibility !== 'hidden')
    const first = items[0]
    const last = items.at(-1)
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }
}
onMounted(() => window.addEventListener('keydown', keyboard))

// Ngày trên thanh trên, đổi lúc qua nửa đêm
const calendarDay = ref(today())
let calendarClock: ReturnType<typeof setInterval> | undefined
onMounted(() => { calendarClock = setInterval(() => { calendarDay.value = today() }, 60_000) })
const dateLabel = computed(() => new Intl.DateTimeFormat(locale.value === 'vi' ? 'vi-VN' : 'en-GB', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
}).format(new Date(`${calendarDay.value}T12:00:00`)))

onBeforeUnmount(() => {
  media?.removeEventListener('change', updateViewport)
  window.removeEventListener('keydown', keyboard)
  clearInterval(calendarClock)
  clearTimeout(hoverExit)
  document.body.style.overflow = ''
})

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
  // Hồ sơ công việc, nộp lưu, phòng đọc (F3.8): chuyên viên, lãnh đạo phòng lập; văn thư, lãnh đạo đơn vị xem
  if (role === 'clerk' || role === 'staff' || role === 'manager' || role === 'director') {
    items.push({
      to: '/ho-so', label: t('cases.title'),
      icon: 'M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7zm6 6h6',
    })
  }
  // Sơ đồ cảm biến kho (F3.10, Action otSensorMap): cùng các vai trò đọc được dự thảo "Báo cáo sự cố" mà cảm biến
  // vượt ngưỡng dựng ra; quản trị đơn vị không đọc văn bản nên không có
  if (role === 'clerk' || role === 'staff' || role === 'manager' || role === 'director') items.push({ to: '/cam-bien',
    label: t('nav.sensors'), icon: 'M3 5h18v14H3zM3 11h7m4 0h7M9 5v6m6-6v6m-3 2v6' })
  items.push({ to: '/tim-kiem', label: t('nav.search'), icon: 'M21 21l-4.3-4.3M10.5 18a7.5 7.5 0 110-15 7.5 7.5 0 010 15z' })
  // Hỏi đáp trên kho văn bản (F4.2): vai trò nghiệp vụ; quản trị đơn vị không đọc văn bản nên không hỏi được
  if (role === 'clerk' || role === 'staff' || role === 'manager' || role === 'director') items.push({ to: '/hoi-dap', label: t('nav.ask'), icon: 'M8 10h8M8 14h5M21 12a9 9 0 01-13.2 8L3 21l1.1-4.6A9 9 0 1121 12z' })
  if (role === 'director') items.push({ to: '/dieu-hanh', label: t('nav.board'), icon: 'M3 3v18h18M8 17v-4m4 4V8m4 9v-6' })
  // Số đo "sau" theo đặc tả §8 (F4.6): khung nhìn số đo chỉ cho lãnh đạo đơn vị đọc, như dashboard điều hành
  if (role === 'director') items.push({ to: '/so-do', label: t('nav.metrics'), icon: 'M12 9v4l2.5 2.5M9 3h6M12 21a8 8 0 110-16 8 8 0 010 16z' })
  // Phả hệ số liệu (F3.9): biểu đồ của trang Điều hành ← khung nhìn ← bảng, lượt nộp lưu; cùng quyền với dashboard
  if (role === 'director') {
    items.push({ to: '/pha-he', label: t('lineage.nav'),
                 icon: 'M4 9h5v6H4zM15 3h5v6h-5zM15 15h5v6h-5zM9 12h3m0-6v12m0-12h3m-3 12h3' })
  }
  // Tự chẩn đoán H-P-D-I: lãnh đạo đơn vị trả lời, lưu, xem bằng chứng đo được; lãnh đạo phòng trả lời, không lưu
  if (role === 'director' || role === 'manager') items.push({ to: '/tu-chan-doan', label: t('nav.selfCheck'), icon: 'M12 3l8.5 6.2-3.2 10H6.7L3.5 9.2 12 3zm0 5l4 2.9-1.5 4.6h-5L8 10.9 12 8z' })
  if (role === 'director' || role === 'tenant_admin') items.push({ to: '/so-kiem-toan', label: t('nav.audit'), icon: 'M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6l7-3zm-3 9l2 2 4-4' })
  // Danh mục ứng dụng trên lõi: mọi vai trò xem để mở; lãnh đạo, quản trị đơn vị thấy thêm băm manifest, ứng dụng đã gỡ
  if (role) {
    items.push({ to: '/ung-dung', label: t('apps.nav'),
                 icon: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z' })
  }
  // Góp ý (F4.6): mọi vai trò gửi được; trang xem lại góp ý của mình, lãnh đạo, quản trị đơn vị xem thêm tổng hợp
  if (role) items.push({ to: '/gop-y', label: t('nav.feedback'), icon: 'M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2-5.5-2.9-5.5 2.9 1-6.2L3 9.6l6.2-.9L12 3z' })
  return items
})

// Mục đang mở: đúng đường dẫn, hoặc trang con của nó (/ho-so/… thuộc Hồ sơ công việc) trừ khi trang con đã có mục
// riêng (/van-ban-den/tiep-nhan)
function active(to: string) {
  if (to === '/') return route.path === '/'
  return route.path === to
    || (route.path.startsWith(`${to}/`) && !nav.value.some((item) => item.to !== to && route.path === item.to))
}

// Thanh trên: tên đơn vị › trang đang mở. Trang ngoài menu (văn bản đang đọc) tự đặt tên qua useState('sg-crumb');
// đổi trang thì xóa để tên cũ không còn treo lại
const crumb = useState<string>('sg-crumb', () => '')
const pageLabel = computed(() => crumb.value || nav.value.find((item) => active(item.to))?.label || '')

function toggleLocale() {
  locale.value = locale.value === 'vi' ? 'en' : 'vi'
  try { localStorage.setItem('moc.locale', locale.value) } catch { /* bỏ qua */ }
}

// Chọn xong một trang thì đóng ngăn kéo; thanh bên trên máy tính giữ nguyên, chỉ thu khi con trỏ rời đi
watch(() => route.fullPath, () => { open.value = false })
watch(() => route.path, () => { crumb.value = '' })

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
  notice.info(text.title, { detail: text.note || text.detail, to: notificationLink(msg) })
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
  <div class="sg-shell" :class="{ 'is-collapsed': collapsed, 'is-mobile-open': open }">
    <a
      href="#main-content"
      class="btn-primary sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50"
    >
      {{ t('fe.skip') }}
    </a>
    <aside
      id="app-navigation" class="sg-sidebar" :aria-label="t('fe.navigation')"
      :inert="mobile && !open ? true : undefined"
      @pointermove="moveInNavigation" @pointerleave="leaveNavigation" @click="pickInNavigation"
      @focusin="focusNavigation" @focusout="blurNavigation"
    >
      <div class="sg-brand-row">
        <NuxtLink to="/" class="sg-wordmark" :aria-label="t('app.name')">
          <svg
            class="sg-brand-mark" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="9"
            stroke-linecap="round" aria-hidden="true"
          >
            <path d="M45 10H26c-9 0-16 7-16 16s7 16 16 16h12" />
            <path d="M19 54h19c9 0 16-7 16-16s-7-16-16-16H26" />
          </svg>
          <span class="sg-brand-full"><b>Signet</b><small>{{ t('app.tagline') }}</small></span>
        </NuxtLink>
        <button class="btn-ghost sg-close-menu" :aria-label="t('shell.closeNav')" @click="open = false">
          <svg
            width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
            aria-hidden="true"
          >
            <path d="m6 6 12 12M6 18 18 6" />
          </svg>
        </button>
      </div>
      <nav class="sg-nav" :aria-label="t('fe.navigation')">
        <NuxtLink
          v-for="item in nav" :key="item.to" :to="item.to" class="sg-nav-link" :class="{ 'is-active': active(item.to) }"
          :aria-label="item.label" :title="collapsed ? item.label : undefined"
          :aria-current="active(item.to) ? 'page' : undefined"
        >
          <svg
            width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"
            aria-hidden="true"
          >
            <path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" />
          </svg>
          <span class="sg-nav-label">{{ item.label }}</span>
        </NuxtLink>
      </nav>
      <div class="sg-sidebar-bottom">
        <div class="sg-utility">
          <NuxtLink to="/xac-thuc" class="sg-nav-link" :aria-label="t('fe.verify')"
            :title="collapsed ? t('fe.verify') : undefined"
          >
            <svg
              width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"
              aria-hidden="true"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4M12 3a9 9 0 110 18 9 9 0 010-18z" />
            </svg>
            <span class="sg-nav-label">{{ t('fe.verify') }}</span>
          </NuxtLink>
          <NuxtLink to="/trang-thai" class="sg-nav-link" :aria-label="t('health.title')"
            :title="collapsed ? t('health.title') : undefined"
          >
            <svg
              width="19" height="19" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"
              aria-hidden="true"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M3 12h4l3-8 4 16 3-8h4" />
            </svg>
            <span class="sg-nav-label">{{ t('health.title') }}</span>
          </NuxtLink>
        </div>
        <div class="sg-account">
          <span class="sg-avatar" data-testid="avatar-initial" aria-hidden="true">
            {{ initialOf(claims?.givenName ?? '', claims?.name ?? '') }}
          </span>
          <div class="sg-account-name sg-nav-label">
            <strong>{{ claims?.name }}</strong>
            <small>{{ claims?.role ? t(`role.${claims.role}`) : t('error.noRole') }}</small>
          </div>
          <button class="btn-ghost sg-logout" :aria-label="t('nav.logout')" :title="t('nav.logout')" @click="logout">
            <svg
              width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
              aria-hidden="true"
            >
              <path d="M9 4H4v16h5m6-4l4-4-4-4m-7 4h11" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
    <Transition name="sg-scrim">
      <button v-if="open" class="sg-scrim" :aria-label="t('shell.closeNav')" tabindex="-1" @click="open = false" />
    </Transition>

    <div class="sg-workspace" :inert="mobile && open ? true : undefined">
      <header class="sg-topbar">
        <div class="sg-topbar-context">
          <button
            ref="menuButton" class="btn-ghost sg-mobile-menu" :aria-label="t('fe.menu')"
            aria-controls="app-navigation" :aria-expanded="open" @click="open = !open"
          >
            <svg
              width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
              aria-hidden="true"
            >
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <p class="sg-crumb">
            <b>{{ tenantName || t('fe.organization') }}</b>
            <template v-if="pageLabel">
              <svg
                width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
                aria-hidden="true"
              >
                <path d="M9 6l6 6-6 6" />
              </svg>
              <span>{{ pageLabel }}</span>
            </template>
          </p>
        </div>
        <div class="sg-topbar-tools">
          <time :datetime="calendarDay">{{ dateLabel }}</time>
          <FeedbackButton v-if="claims?.role" />
          <NotificationBell v-if="claims?.role" />
          <button class="btn-ghost sg-language" :aria-label="t('nav.language')" @click="toggleLocale">
            {{ locale === 'vi' ? 'EN' : 'VI' }}
          </button>
        </div>
      </header>
      <main id="main-content" class="moc-sheet">
        <slot />
      </main>
    </div>
  </div>
</template>
