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

// Quản trị đơn vị không đọc văn bản: Hasura không cho vai trò này đọc office.documents, hồ sơ công việc, sổ đăng ký
// văn bản, nên menu không có các mục ấy. Gõ thẳng địa chỉ (hay mở lại một đường dẫn cũ) thì trang gửi câu hỏi rồi báo
// lỗi GraphQL "not found". Middleware auth.global đưa họ về sổ kiểm toán trước khi trang nào chạy. Tệp này không dùng
// gì của Nuxt để Node chạy test được (tests/adminRoutes.test.ts).

const DOCUMENT_AREAS = ['/van-ban-den', '/van-ban-di', '/van-ban', '/ho-so', '/so-dang-ky']

/** Đường dẫn thuộc vùng đọc văn bản, kể cả trang con (/van-ban-den/tiep-nhan, /van-ban/:id, /ho-so/:id). */
export function closedToTenantAdmin(path: string): boolean {
  const p = path.replace(/\/+$/, '')
  return DOCUMENT_AREAS.some((area) => p === area || p.startsWith(`${area}/`))
}
