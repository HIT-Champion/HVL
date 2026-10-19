// Copyright 2026 Mộc Team
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

import tailwindcss from '@tailwindcss/vite'
import { formsPlugin } from './scripts/forms.mjs'

// JSON Schema dùng chung với svc-workflow (poka-yoke F2.2): schemas/ ở gốc repo; bản dựng Docker chép vào cùng
// vị trí tương đối (Dockerfile, additional_contexts trong docker-compose.yml)
const schemas = new URL('../../schemas/', import.meta.url)

// Giao diện chạy hoàn toàn trên trình duyệt (SPA): dựng thành trang tĩnh, nginx phục vụ, mọi dữ liệu lấy
// qua APISIX cùng tên miền — không có máy chủ Node nào phải chạy ở bản triển khai.
export default defineNuxtConfig({
  compatibilityDate: '2026-08-01',
  ssr: false,
  devtools: { enabled: false },
  telemetry: false,
  css: ['~/assets/css/main.css'],
  vite: { plugins: [tailwindcss(), formsPlugin(schemas)] },
  app: {
    head: {
      title: 'Mộc — Văn phòng điện tử',
      htmlAttrs: { lang: 'vi' },
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Mộc — văn phòng điện tử nguồn mở: văn bản đến, văn bản đi, hộp việc' },
      ],
      link: [{ rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    },
  },
})
