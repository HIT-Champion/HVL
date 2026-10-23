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

// Lật trang danh sách văn bản bằng offset trong lúc danh sách vẫn đổi (văn bản mới vào sổ, văn bản đổi trạng thái
// rời khỏi tab): mỗi lần "Xem thêm" lấy lùi vài dòng đã hiện rồi bỏ dòng trùng. Văn bản chen lên đầu không làm lặp
// dòng; tới OVERLAP văn bản rời danh sách không làm sót dòng kế tiếp.
const PAGE = 50
const OVERLAP = 5

/** offset, limit của lần lấy tiếp theo khi đang hiện `shown` dòng (0: trang đầu). Lấy dư một dòng để biết còn nữa. */
export function nextPage(shown: number): { offset: number, limit: number } {
  const offset = Math.max(0, shown - OVERLAP)
  return { offset, limit: shown - offset + PAGE + 1 }
}

/** Nối kết quả của nextPage(rows.length) vào các dòng đang hiện, bỏ dòng đã có. */
export function mergePage<T extends { id: string }>(rows: T[], got: T[]): { rows: T[], more: boolean } {
  const { limit } = nextPage(rows.length)
  const known = new Set(rows.map((r) => r.id))
  return { rows: [...rows, ...got.slice(0, limit - 1).filter((r) => !known.has(r.id))], more: got.length >= limit }
}
