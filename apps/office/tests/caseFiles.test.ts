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

// Hồ sơ, nộp lưu, phòng đọc (F3.8): ai làm được gì trên màn hồ sơ (đúng quyền Hasura, svc-files), văn bản đưa vào được,
// form lập hồ sơ theo ràng buộc CSDL, hạn khóa ghi dự kiến như archive.py, lỗi thành câu cho người dùng.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const {
  canArchive, canCreate, canEdit, caseFileErrorKey, caseFileErrorText, caseFileInput, containsPattern, fileableWhere,
  filesByDocument, hexOf, isViewable, retainUntil, validateCaseFile,
} = await import('../app/utils/caseFiles.ts')

const DEPT = 'd-dao-tao'
const staff = { role: 'staff', departmentId: DEPT, userId: 'u-nam' }
const manager = { role: 'manager', departmentId: DEPT, userId: 'u-hoa' }
const otherManager = { role: 'manager', departmentId: 'd-ktpm', userId: 'u-huy' }
const clerk = { role: 'clerk', departmentId: 'd-van-phong', userId: 'u-thu' }
const director = { role: 'director', departmentId: 'd-van-phong', userId: 'u-duc' }
const cf = (status: 'open' | 'closed' | 'archived', department_id = DEPT) => ({ status, department_id })

test('lập hồ sơ: chuyên viên, lãnh đạo phòng có phòng; văn thư, lãnh đạo đơn vị, quản trị thì không', () => {
  assert.equal(canCreate(staff), true)
  assert.equal(canCreate(manager), true)
  for (const v of [clerk, director, { role: 'tenant_admin', departmentId: null, userId: 'u-tin' },
    { role: 'staff', departmentId: null, userId: 'u-x' }, { role: null, departmentId: DEPT, userId: 'u-y' }]) {
    assert.equal(canCreate(v), false)
  }
})

test('thêm, gỡ văn bản, đóng: chỉ người của phòng có hồ sơ, chỉ khi hồ sơ còn mở', () => {
  assert.equal(canEdit(staff, cf('open')), true)
  assert.equal(canEdit(manager, cf('open')), true)
  assert.equal(canEdit(otherManager, cf('open')), false)
  assert.equal(canEdit(clerk, cf('open', 'd-van-phong')), false)   // văn thư chỉ xem, kể cả hồ sơ cùng "phòng"
  assert.equal(canEdit(staff, cf('closed')), false)
  assert.equal(canEdit(staff, cf('archived')), false)
})

test('nộp lưu ngay: lãnh đạo phòng của phòng có hồ sơ, hồ sơ đã đóng — như POST /api/case-files/{id}/archive', () => {
  assert.equal(canArchive(manager, cf('closed')), true)
  assert.equal(canArchive(manager, cf('open')), false)
  assert.equal(canArchive(manager, cf('archived')), false)
  assert.equal(canArchive(otherManager, cf('closed')), false)
  for (const v of [staff, clerk, director]) assert.equal(canArchive(v, cf('closed', v.departmentId)), false)
})

test('văn bản đưa vào được: đúng check của Hasura và trigger, lọc chữ không coi % _ là ký tự đại diện', () => {
  const where = fileableWhere(staff) as { _and: unknown[] }
  assert.deepEqual(where._and, [
    { restricted: { _eq: false } },
    {
      _or: [
        { direction: { _eq: 'in' }, status: { _eq: 'done' } },
        { direction: { _eq: 'out' }, status: { _eq: 'issued' } },
      ],
    },
    { _or: [{ department_id: { _eq: DEPT } }, { assignments: { department_id: { _eq: DEPT } } },
      { assignments: { user_id: { _eq: 'u-nam' } } }] },
  ])
  const filtered = fileableWhere(staff, '  12/TB_CNTT 50% ') as { _and: unknown[] }
  assert.equal(filtered._and.length, 4)
  assert.deepEqual(filtered._and[3], { _or: [{ symbol: { _ilike: '%12/TB\\_CNTT 50\\%%' } },
    { summary: { _ilike: '%12/TB\\_CNTT 50\\%%' } }] })
  assert.equal(containsPattern('a\\b'), '%a\\\\b%')
  assert.equal((fileableWhere(staff, '   ') as { _and: unknown[] })._and.length, 3)
})

test('form lập hồ sơ theo ràng buộc CSDL: năm, ký hiệu, tiêu đề 5–500 ký tự, thời hạn 1–100 năm hoặc vĩnh viễn', () => {
  const ok = { year: 2026, code: ' 01.TS ', title: '  Hồ sơ tuyển sinh 2026 ', retention: '10' }
  assert.deepEqual(validateCaseFile(ok), {})
  assert.deepEqual(caseFileInput(ok),
    { year: 2026, code: '01.TS', title: 'Hồ sơ tuyển sinh 2026', retention_years: 10 })
  assert.deepEqual(caseFileInput({ ...ok, year: '2025', retention: 'permanent' }).retention_years, null)
  assert.deepEqual(validateCaseFile({ year: '1999', code: '  ', title: ' Hồ ', retention: '0' }),
    { year: 'year', code: 'code', title: 'title', retention: 'retention' })
  assert.deepEqual(validateCaseFile({ ...ok, title: 'x'.repeat(501), retention: '101' }),
    { title: 'title', retention: 'retention' })
  assert.deepEqual(validateCaseFile({ ...ok, year: 2026.5, retention: 'permanent' }), { year: 'year' })
})

test('hạn khóa ghi dự kiến: cộng năm theo lịch từ ngày đóng như archive._add_years; vĩnh viễn 100 năm', () => {
  assert.equal(retainUntil('2026-10-01', 10), '2036-10-01')
  assert.equal(retainUntil('2028-02-29', 1), '2029-02-28')   // 29/02 sang năm không nhuận
  assert.equal(retainUntil('2028-02-29', 4), '2032-02-29')
  assert.equal(retainUntil('2026-10-01', null), '2126-10-01')
  assert.equal(retainUntil('2000-02-29', 100), '2100-02-28')  // 2100 không nhuận
})

test('băm bytea của Hasura thành hex; phòng đọc chỉ mở PDF', () => {
  assert.equal(hexOf('\\xABCDEF'), 'abcdef')
  assert.equal(hexOf('abcdef'), 'abcdef')
  assert.equal(hexOf(null), null)
  assert.equal(isViewable('application/pdf'), true)
  for (const mime of ['image/png', 'application/octet-stream', '', null]) assert.equal(isViewable(mime), false)
})

test('lỗi: mã của svc-files và tên ràng buộc của Hasura thành câu riêng, lỗi khác để errorText lo', () => {
  assert.equal(caseFileErrorKey('not_closed'), 'not_closed')
  // archive_failed: giữ câu máy chủ
  assert.equal(caseFileErrorKey('archive_failed', 'Chưa nộp lưu được: văn bản 5/TB còn đang gửi'), null)
  assert.equal(caseFileErrorKey('constraint-violation',
    'Uniqueness violation. duplicate key value violates unique constraint "case_files_tenant_id_year_code_key"'),
  'duplicateCode')
  assert.equal(caseFileErrorKey(null, 'violates unique constraint "case_file_documents_document_id_key"'),
    'alreadyFiled')
  assert.equal(caseFileErrorKey('network', 'network'), null)
  const t = (key: string) => `[${key}]`
  const fallback = (e: unknown) => `fallback:${(e as Error).message}`
  assert.equal(caseFileErrorText(t, Object.assign(new Error('x'), { code: 'busy' }), fallback), '[cases.error.busy]')
  assert.equal(caseFileErrorText(t, new Error('hồ sơ HS-01 chưa có văn bản nào'), fallback),
    'fallback:hồ sơ HS-01 chưa có văn bản nào')
  assert.equal(caseFileErrorText(t, 'chuỗi', (e) => `fallback:${String(e)}`), 'fallback:chuỗi')
})

test('tệp trong gói theo văn bản, giữ thứ tự manifest; tệp gắn hai văn bản hiện ở cả hai', () => {
  const files = [{ file_id: 'f1', document_ids: ['d1'] }, { file_id: 'f2', document_ids: ['d2', 'd1'] }]
  const by = filesByDocument(files)
  assert.deepEqual(by.get('d1')!.map((f) => f.file_id), ['f1', 'f2'])
  assert.deepEqual(by.get('d2')!.map((f) => f.file_id), ['f2'])
  assert.equal(by.get('d3'), undefined)
})

test('mọi câu cases.error.* mà màn hồ sơ có thể dùng đều có ở cả vi và en', () => {
  const locale = (lang: string) =>
    JSON.parse(readFileSync(new URL(`../app/locales/${lang}.json`, import.meta.url), 'utf8'))
  for (const lang of ['vi', 'en']) {
    const errors = locale(lang).cases.error
    for (const key of ['duplicateCode', 'alreadyFiled', 'titleLength', 'codeRequired', 'forbidden', 'not_found',
      'not_closed', 'already_archived', 'archive_conflict', 'not_archived', 'busy', 'not_viewable', 'unstampable',
      'archive_mismatch', 'storage_unavailable', 'database_unavailable']) {
      assert.equal(typeof errors[key], 'string', `${lang}: cases.error.${key}`)
    }
  }
})
