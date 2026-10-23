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

// Mọi trang cần đăng nhập, trừ trang nhận kết quả đăng nhập từ Keycloak, cổng xác thực văn bản và trạng thái hệ thống
// (công khai).
export default defineNuxtRouteMiddleware(async (to) => {
  if (to.path.replace(/\/$/, '') === '/dang-nhap') return
  if (to.path === '/xac-thuc' || to.path.startsWith('/xac-thuc/')) return
  if (to.path.replace(/\/$/, '') === '/trang-thai') return
  const auth = useAuth()
  if (auth.user.value && !auth.user.value.expired) return
  const restored = await auth.restore()
  if (!restored) {
    await auth.login(to.fullPath)
    return abortNavigation()
  }
})
