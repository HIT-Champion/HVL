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

// Liên thông văn bản trong hệ thống (F3.12): phần tính toán thuần của màn soạn và màn văn bản, tách ra để kiểm thử.

/**
 * Tích / bỏ tích một đơn vị nhận trong hệ thống thì sửa ô "Nơi nhận" (mỗi dòng một nơi nhận) cho khớp: tích thì
 * thêm một dòng đúng tên đơn vị nếu chưa có dòng nào như vậy; bỏ tích thì chỉ gỡ dòng đúng bằng tên đơn vị — chữ
 * người soạn tự gõ (vd "Khoa Kinh tế (để phối hợp)") giữ nguyên.
 */
export function toggleRecipient(text: string, name: string, on: boolean): string {
  const lines = text.split('\n')
  const same = (line: string) => line.trim() === name.trim()
  if (on) {
    if (lines.some(same)) return text
    const kept = text.replace(/\s+$/, '')
    return kept ? `${kept}\n${name}` : name
  }
  return lines.filter((line) => !same(line)).join('\n')
}

/** Băm SHA-256 Hasura trả cho cột bytea dạng "\x…" (hex); so không phân biệt hoa thường, bỏ tiền tố. */
export function sameSha256(a: string | null | undefined, b: string | null | undefined): boolean {
  const norm = (v: string) => v.trim().replace(/^\\x/i, '').toLowerCase()
  if (!a || !b) return false
  const x = norm(a)
  return /^[0-9a-f]{64}$/.test(x) && x === norm(b)
}

/** Mã xác thực 10 ký tự in như trên văn bản: ABCDE-23456. */
export function fmtVerifyCode(code: string | null | undefined): string {
  return code ? `${code.slice(0, 5)}-${code.slice(5)}` : ''
}
