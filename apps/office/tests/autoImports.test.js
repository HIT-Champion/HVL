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

// Nuxt tự import các tên export trong app/utils/ theo danh sách unimport quét được, và unimport đọc export bằng
// findExports của mlly (biểu thức chính quy). Tên mlly bỏ sót thì trang dùng tên đó mà không import vẫn dựng được —
// nuxt generate, vue-tsc đều qua — nhưng lỗi ReferenceError trên trình duyệt: `export const HPDI_TOP` đứng ngay sau một
// dòng `export const … = [1, 2, …] as const` bị đọc lố vào dòng trước, trang Tự chẩn đoán chết khi đủ 12 câu (e2e
// tu-chan-doan.spec.ts). Test chạy đúng bộ quét đó trên từng tệp, bắt cả loại lỗi này ở mọi tiện ích.

import assert from 'node:assert/strict';
import { readdirSync } from 'node:fs';
import { readSource as readFileSync } from './source.mjs';
import { test } from 'node:test';
import { findExports } from 'mlly';

const UTILS = new URL('../app/utils/', import.meta.url);

test('mọi tên export chạy được trong app/utils đều vào danh sách tự import của Nuxt', () => {
  const files = readdirSync(UTILS).filter((f) => f.endsWith('.js'));
  assert.ok(files.includes('hpdi.js'));
  for (const file of files) {
    const code = readFileSync(new URL(file, UTILS), 'utf8');
    const declared = [...code.matchAll(/^export (?:const|let|function|async function|class) ([\w$]+)/gm)].map((m) => m[1]);
    const scanned = new Set(findExports(code).flatMap((e) => e.names));
    assert.deepEqual(declared.filter((name) => !scanned.has(name)), [], `${file}: Nuxt không thấy các tên này`);
  }
});
