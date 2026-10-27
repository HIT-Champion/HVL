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

// Bấm lưu khi còn ô sai: chuyển tiêu điểm vào ô sai đầu tiên, để người dùng bàn phím, trình đọc màn hình biết ngay ô
// nào cần sửa (ô sai trỏ tới câu báo lỗi bằng aria-describedby) thay vì tiêu điểm nằm lại ở nút lưu. Chờ một nhịp vẽ
// lại để aria-invalid, câu báo lỗi đã hiện.

import { nextTick } from 'vue'

export async function focusInvalidField(root: ParentNode = document) {
  await nextTick()
  root.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()
}
