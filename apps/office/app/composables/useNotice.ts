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

// Thông báo ngắn ở góc màn hình (đã lưu, lỗi…; tin realtime có thể kèm đường dẫn tới văn bản)
export interface Notice { id: number; kind: 'ok' | 'error' | 'info'; text: string; detail?: string; to?: string }

const notices = ref<Notice[]>([])
let next = 1

export function useNotice() {
  function push(kind: Notice['kind'], text: string, ms = 5000, extra: Pick<Notice, 'detail' | 'to'> = {}) {
    const id = next++
    notices.value.push({ id, kind, text, ...extra })
    setTimeout(() => { notices.value = notices.value.filter((n) => n.id !== id) }, ms)
  }
  return {
    notices,
    ok: (t: string) => push('ok', t),
    error: (t: string) => push('error', t, 8000),
    info: (t: string, extra: Pick<Notice, 'detail' | 'to'> = {}) => push('info', t, 8000, extra),
  }
}
