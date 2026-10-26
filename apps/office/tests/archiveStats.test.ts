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

// Số liệu văn bản đã nộp lưu trên trang Điều hành (#304): hàng cho biểu đồ theo năm (năm trống vẫn có cột), tên loại
// văn bản, tên phòng; kho trống thì là trạng thái trống, không phải lỗi; trang chỉ thêm đúng một dòng gọi thành phần.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const { MAX_YEAR_GAP, departmentRows, isEmptyArchive, typeRows, yearRows } =
  await import('../app/utils/archiveStats.ts')

const stats = (over: Record<string, unknown> = {}) => ({
  case_files: 0, documents: 0, incoming: 0, outgoing: 0, by_year: [], by_type: [], by_department: [], unreadable: [],
  bucket: 'moc-cold', computed_at: '2026-10-27T08:00:00Z', ...over,
})

test('theo năm: năm không có văn bản vẫn có cột, dòng không rõ năm ở cuối', () => {
  assert.deepEqual(yearRows([
    { year: null, incoming: 1, outgoing: 0 },
    { year: 2026, incoming: 2, outgoing: 1 },
    { year: 2023, incoming: 1, outgoing: 1 },
  ]), [
    { year: 2023, incoming: 1, outgoing: 1 },
    { year: 2024, incoming: 0, outgoing: 0 },
    { year: 2025, incoming: 0, outgoing: 0 },
    { year: 2026, incoming: 2, outgoing: 1 },
    { year: null, incoming: 1, outgoing: 0 },
  ])
  assert.deepEqual(yearRows([]), [])
  assert.deepEqual(yearRows([{ year: null, incoming: 0, outgoing: 3 }]), [{ year: null, incoming: 0, outgoing: 3 }])
  // khoảng quá dài (dữ liệu nhập sai năm): chỉ các năm có số, trục không thành hàng trăm cột
  const far = yearRows([{ year: 1900, incoming: 1, outgoing: 0 }, { year: 1900 + MAX_YEAR_GAP + 1, incoming: 1,
    outgoing: 0 }])
  assert.deepEqual(far.map((r) => r.year), [1900, 1900 + MAX_YEAR_GAP + 1])
})

test('loại văn bản, phòng mang tên đọc từ Hasura; thiếu tên thì giữ mã, phòng là "chưa rõ"', () => {
  const types = new Map([['CV', 'Công văn']])
  assert.deepEqual(typeRows([{ type_code: 'CV', incoming: 2, outgoing: 1 }, { type_code: 'XX', incoming: 0,
    outgoing: 4 }], types), [
    { type_code: 'CV', incoming: 2, outgoing: 1, name: 'Công văn', total: 3 },
    { type_code: 'XX', incoming: 0, outgoing: 4, name: 'XX', total: 4 },
  ])
  const departments = new Map([['d-1', 'Phòng Đào tạo']])
  assert.deepEqual(departmentRows([
    { department_id: 'd-1', case_files: 2, documents: 5 },
    { department_id: 'd-cu', case_files: 1, documents: 1 },
    { department_id: null, case_files: 1, documents: 0 },
  ], departments).map((r) => r.name), ['Phòng Đào tạo', null, null])
})

test('kho trống là trạng thái trống; có gói hỏng thì không coi là trống (phải báo ra)', () => {
  assert.equal(isEmptyArchive(stats()), true)
  assert.equal(isEmptyArchive(stats({ case_files: 1, documents: 2 })), false)
  assert.equal(isEmptyArchive(stats({ unreadable: [{ case_file_id: 'c-1', code: 'HS-01' }] })), false)
})

test('trang Điều hành chỉ thêm một dòng gọi thành phần, chỉ cho lãnh đạo đơn vị; thành phần gọi đúng API', () => {
  const page = readFileSync(new URL('../app/pages/dieu-hanh.vue', import.meta.url), 'utf8')
  assert.deepEqual(page.match(/<ArchiveBoard\b[^>]*>/g), ['<ArchiveBoard v-if="allowed" class="mt-4" />'])
  const component = readFileSync(new URL('../app/components/ArchiveBoard.vue', import.meta.url), 'utf8')
  assert.match(component, /api\.archiveStats\(\)/)
  assert.match(component, /data-testid="archive-empty"/)
  const api = readFileSync(new URL('../app/composables/useApi.ts', import.meta.url), 'utf8')
  assert.match(api, /authFetch\('\/api\/case-files\/archive-stats'\)/)
})
