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

import { createI18n } from 'vue-i18n'
import en from '~/locales/en.json'
import vi from '~/locales/vi.json'

// Khóa i18n từ ngày đầu (F2.9). Ngôn ngữ chọn được lưu trên trình duyệt.
export default defineNuxtPlugin((nuxtApp) => {
  let saved: string | null = null
  try {
    saved = localStorage.getItem('moc.locale')
  } catch {
    // trình duyệt chặn bộ nhớ cục bộ: dùng tiếng Việt
  }
  const i18n = createI18n({
    legacy: false,
    globalInjection: true,
    locale: saved === 'en' ? 'en' : 'vi',
    fallbackLocale: 'vi',
    messages: { vi, en },
  })
  nuxtApp.vueApp.use(i18n)
  // <html lang> theo ngôn ngữ đang dùng, kể cả ngay sau khi tải lại trang (#205): mục này đè lên `lang: 'vi'` ghi cứng
  // trong nuxt.config.ts và đổi theo mỗi lần bấm nút đổi ngôn ngữ
  useHead({ htmlAttrs: { lang: computed(() => i18n.global.locale.value) } })
})
