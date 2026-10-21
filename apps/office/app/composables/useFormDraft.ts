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

// Bản đang soạn dở giữ trong sessionStorage của thẻ trình duyệt: hết phiên đăng nhập thì ứng dụng chuyển sang
// Keycloak rồi quay lại đúng trang (useApi, useAuth) — chữ đã gõ, tệp đã tải lên (id trong kho) không mất. Chỉ thẻ
// này đọc được, đóng thẻ là hết; khóa theo người dùng nên người khác đăng nhập cùng thẻ không thấy. read() trả null
// là không giữ (vd văn bản hạn chế: không để trích yếu nằm lại trong trình duyệt). Rời trang trong ứng dụng là bỏ
// bản dở (mở lại trang soạn thì bắt đầu mới); đăng xuất bỏ mọi bản dở của thẻ (dropDrafts).

const PREFIX = 'moc-draft:'

export function dropDrafts() {
  try {
    for (const k of Object.keys(sessionStorage)) if (k.startsWith(PREFIX)) sessionStorage.removeItem(k)
  } catch {
    // trình duyệt chặn sessionStorage: không có gì để bỏ
  }
}

export function useFormDraft<T>(key: () => string | null, read: () => T | null, write: (value: T) => void) {
  let enabled = false
  const storageKey = () => {
    const k = key()
    return k ? `${PREFIX}${k}` : null
  }

  watch(read, (value) => {
    const k = storageKey()
    if (!enabled || !k) return
    try {
      if (value === null) sessionStorage.removeItem(k)
      else sessionStorage.setItem(k, JSON.stringify(value))
    } catch {
      // trình duyệt chặn, hết chỗ: chỉ là mất tiện ích, không chặn việc soạn
    }
  }, { deep: true })

  // Gọi sau khi form đã nạp dữ liệu gốc: có bản dở thì đè lên → true. Từ đây mỗi lần sửa đều được giữ.
  function resume(): boolean {
    enabled = true
    const k = storageKey()
    if (!k) return false
    try {
      const raw = sessionStorage.getItem(k)
      if (!raw) return false
      write(JSON.parse(raw) as T)
      return true
    } catch {
      return false
    }
  }

  // Lưu xong: bỏ bản dở
  function clear() {
    enabled = false
    const k = storageKey()
    if (!k) return
    try {
      sessionStorage.removeItem(k)
    } catch {
      // như trên
    }
  }

  // Chuyển trang trong ứng dụng là rời có chủ ý; hết phiên thì chuyển cả trang sang Keycloak, không qua đây
  onBeforeRouteLeave(() => clear())

  return { resume, clear }
}
