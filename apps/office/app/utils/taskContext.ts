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

// Ngữ cảnh việc trên trang văn bản: mở từ hộp việc (?from=inbox) thì nút quay lại về hộp việc, và chuyên viên thấy
// tóm tắt phần việc được giao cho mình (chỉ đạo của phòng và của người giao, người giao, hạn) ngay trong khung báo kết
// quả. Tệp này không dùng gì của Nuxt để Node chạy test được (tests/taskContext.test.ts).

export interface BriefAssignment {
  id: string
  parent_id: string | null
  user_id: string | null
  instruction: string | null
  due_on: string | null
  status: string
  assigned_by: string
}

export interface ProcessingBrief {
  instructions: string[]
  dueOn: string | null
  assignedBy: string | null
}

/**
 * Đích của nút quay lại. Chỉ nhận đúng chuỗi "inbox": tham số khác (đường dẫn, địa chỉ ngoài, mảng do lặp tham số)
 * không bao giờ thành đích, mà về sổ văn bản theo chiều văn bản như trước.
 */
export function documentBackTarget(from: unknown, direction: string | null | undefined): string {
  if (from === 'inbox') return '/'
  return direction === 'out' ? '/van-ban-di' : '/van-ban-den'
}

/**
 * Phần việc của người xem: lượt giao chưa xong gần nhất cho chính họ, chỉ đạo của lượt cha (giao phòng) rồi của lượt
 * đó, bỏ dòng trống và dòng trùng; hạn lấy của lượt đó, không có thì của lượt cha, rồi của văn bản. Chỉ dùng các lượt
 * giao Hasura đã trả theo quyền của người xem; không phải người được giao thì không có tóm tắt.
 */
export function processingBrief(
  assignments: readonly BriefAssignment[], userId: string | null | undefined, documentDue: string | null = null,
): ProcessingBrief | null {
  if (!userId) return null
  const mine = assignments.filter((a) => a.user_id === userId && a.status !== 'done').at(-1)
  if (!mine) return null
  const parent = mine.parent_id ? assignments.find((a) => a.id === mine.parent_id) : undefined
  const texts = [parent?.instruction, mine.instruction].map((x) => x?.trim() ?? '').filter(Boolean)
  return {
    instructions: [...new Set(texts)],
    dueOn: mine.due_on || parent?.due_on || documentDue,
    assignedBy: mine.assigned_by || null,
  }
}
