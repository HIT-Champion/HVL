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

// Định dạng ngày giờ theo kiểu Việt Nam (dd/mm/yyyy), dùng chung cho mọi trang.

import assert from 'node:assert/strict';
import { test } from 'node:test';
const { fmtVerifyCode, sameSha256, toggleRecipient } = await import('../app/utils/dispatch.js');
test('tích đơn vị: thêm một dòng tên đơn vị, có rồi thì thôi', ()=>{
    assert.equal(toggleRecipient('', 'Khoa Kinh tế', true), 'Khoa Kinh tế');
    assert.equal(toggleRecipient('Phòng Đào tạo', 'Khoa Kinh tế', true), 'Phòng Đào tạo\nKhoa Kinh tế');
    assert.equal(toggleRecipient('Phòng Đào tạo\n\n', 'Khoa Kinh tế', true), 'Phòng Đào tạo\nKhoa Kinh tế');
    assert.equal(toggleRecipient('Khoa Kinh tế\nPhòng Đào tạo', 'Khoa Kinh tế', true), 'Khoa Kinh tế\nPhòng Đào tạo');
    assert.equal(toggleRecipient('  Khoa Kinh tế  ', 'Khoa Kinh tế', true), '  Khoa Kinh tế  ');
});
test('bỏ tích: chỉ gỡ dòng đúng bằng tên đơn vị, chữ tự gõ giữ nguyên', ()=>{
    assert.equal(toggleRecipient('Phòng Đào tạo\nKhoa Kinh tế', 'Khoa Kinh tế', false), 'Phòng Đào tạo');
    assert.equal(toggleRecipient('Khoa Kinh tế (để phối hợp)', 'Khoa Kinh tế', false), 'Khoa Kinh tế (để phối hợp)');
    assert.equal(toggleRecipient('Phòng Đào tạo', 'Khoa Kinh tế', false), 'Phòng Đào tạo');
    const before = 'Phòng Đào tạo\nCác bộ môn';
    assert.equal(toggleRecipient(toggleRecipient(before, 'Khoa Kinh tế', true), 'Khoa Kinh tế', false), before);
});
test('băm SHA-256 dạng bytea của Hasura: bỏ tiền tố \\x, không phân biệt hoa thường', ()=>{
    const hex = 'ab'.repeat(32);
    assert.equal(sameSha256(`\\x${hex}`, `\\x${hex}`), true);
    assert.equal(sameSha256(`\\x${hex}`, hex.toUpperCase()), true);
    assert.equal(sameSha256(`\\x${hex}`, `\\x${'ab'.repeat(31)}ac`), false);
    assert.equal(sameSha256(null, `\\x${hex}`), false);
    assert.equal(sameSha256('\\x', '\\x'), false);
});
test('mã xác thực in thành hai nhóm năm ký tự', ()=>{
    assert.equal(fmtVerifyCode('ABCDE23456'), 'ABCDE-23456');
    assert.equal(fmtVerifyCode(null), '');
});
