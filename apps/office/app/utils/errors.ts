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

import type { Composer } from 'vue-i18n'
import { ApiError } from '~/composables/useApi'

// Lỗi từ máy chủ → câu cho người dùng. Hasura trả tên ràng buộc trong CSDL (db/README.md: đặt tên cho
// ràng buộc check) nên dịch được thành câu tiếng Việt cụ thể; svc-workflow đã trả câu tiếng Việt sẵn.
const CONSTRAINTS = ['documents_in_dedup', 'documents_due_after_registered']

export function errorText(t: Composer['t'], e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 'network') return t('error.network')
    if (e.code === 'session') return t('error.session')
    if (e.code === 'infected') return t('error.infected')
    if (e.status === 413) return t('error.too_large')
    for (const name of CONSTRAINTS) if (e.message.includes(name)) return t(`error.${name}`)
    if (e.message.includes('summary')) return t('error.documents_summary')
    return e.message
  }
  return t('error.generic', { msg: e instanceof Error ? e.message : String(e) })
}
