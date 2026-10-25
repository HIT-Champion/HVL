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

import type { Composer } from 'vue-i18n'
import { ApiError } from '~/composables/useApi'

// Lỗi từ máy chủ → câu cho người dùng. Hasura trả tên ràng buộc trong CSDL (db/README.md: đặt tên cho
// ràng buộc check) nên dịch được thành câu tiếng Việt cụ thể; svc-workflow đã trả câu tiếng Việt sẵn.
// documents_recipient_units gồm cả documents_recipient_units_out, _other và lỗi của trigger cùng tiền tố (F3.12).
// feedback_*: góp ý (F4.6) — feedback_rate là lỗi chặn gửi dồn của trigger, tên đứng đầu câu lỗi.
// maturity_rate: tự chẩn đoán H-P-D-I (F4.7) — chặn lưu dồn theo đơn vị, như feedback_rate.
const CONSTRAINTS = ['documents_in_dedup', 'documents_due_after_registered', 'documents_body_length',
  'document_files_sealed', 'documents_restricted_sealed', 'documents_restricted_local', 'documents_recipient_units',
  'feedback_rate', 'feedback_rating', 'feedback_comment', 'feedback_screen', 'maturity_rate']

export function errorText(t: Composer['t'], e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 'network') return t('error.network')
    if (e.code === 'session') return t('error.session')
    // tường lửa ở cổng chặn (F3.15): kèm X-Request-Id để người quản trị tra nhật ký chặn
    if (e.code === 'blocked') return e.requestId ? t('error.blockedId', { id: e.requestId }) : t('error.blocked')
    if (e.code === 'infected') return t('error.infected')
    if (e.code === 'unscannable') return t('error.unscannable')    // có mật khẩu, nén quá sâu: ClamAV không quét hết
    // svc-files nhận loại theo nội dung sau ClamAV: sai đuôi, tệp chạy được (415); ảnh không bỏ được EXIF, GPS (422)
    if (e.code === 'type_mismatch' || e.code === 'type_not_allowed' || e.code === 'image_unreadable') {
      return t(`error.${e.code}`)
    }
    // submitOutgoing kiểm đơn vị nhận (restricted / self / unknown) ở trang văn bản, nơi không có ô nào để đánh dấu
    if (e.code === 'invalid' && e.fields?.recipient_tenant_ids) {
      return t(e.fields.recipient_tenant_ids === 'restricted' ? 'error.documents_restricted_local' : 'error.documents_recipient_units')
    }
    if (e.code === 'invalid') return t('error.invalid')            // svc-workflow trả lỗi từng trường (fields)
    if (e.code === 'duplicate') return t('error.documents_in_dedup')
    if (e.status === 413) return t('error.too_large')
    if (e.status === 429) return t('error.rate_limited')
    for (const name of CONSTRAINTS) if (e.message.includes(name)) return t(`error.${name}`)
    if (e.message.includes('summary')) return t('error.documents_summary')
    return e.message
  }
  return t('error.generic', { msg: e instanceof Error ? e.message : String(e) })
}
