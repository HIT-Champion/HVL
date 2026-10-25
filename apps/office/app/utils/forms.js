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

// Poka-yoke lớp 1 (F2.2): kiểm form theo JSON Schema dùng chung (schemas/*.json, biên dịch sẵn bởi
// scripts/forms.mjs). Lỗi quy về {trường: mã} giống hệt svc-workflow (lớp 2, schemas.py), nên hai bên chạy chung
// bộ ca thử schemas/*.cases.json (tests/forms.test.ts). Tệp này không dùng gì của Nuxt để Node chạy test được.



















// Một trường sai nhiều điều thì báo điều đứng trước — cùng thứ tự với svc-workflow
const PRIORITY = ['type', 'required', 'additionalProperties', 'enum', 'format', 'pattern', 'minLength', 'maxLength',
'not', 'x-moc-nfc', 'uniqueItems', 'maxItems', 'x-moc-date'];

function fieldOf(e) {
  if (e.keyword === 'required') return String(e.params.missingProperty);
  if (e.keyword === 'additionalProperties') return String(e.params.additionalProperty);
  const top = e.instancePath.split('/')[1];
  return top === undefined ? '' : top.replaceAll('~1', '/').replaceAll('~0', '~');
}

function rank(code) {
  const i = PRIORITY.indexOf(code);
  return i < 0 ? PRIORITY.length : i;
}

/**
 * Lỗi của dữ liệu theo schema, {} khi hợp lệ. today: YYYY-MM-DD theo giờ Việt Nam, cho từ khóa x-moc-date.
 * Hai từ khóa riêng JSON Schema không diễn đạt được, tự kiểm ở đây như svc-workflow: x-moc-date (ngày so với hôm
 * nay), x-moc-nfc ở gốc (mọi chuỗi ở dạng dựng sẵn NFC — dạng tổ hợp chép từ PDF làm hỏng chặn trùng).
 */
export function formErrors(validate, schema, data, today) {
  // Map chứ không phải {}: tên trường do người gửi đặt, có thể là "constructor", "toString"…
  // Một trường sai nhiều điều thì giữ ngay lúc gom điều đứng trước trong PRIORITY, cùng hạng thì điều gặp trước — như
  // min(codes, key=rank) của svc-workflow; không cần mảng mã rồi reduce() (mảng rỗng thì reduce() ném lỗi)
  const found = new Map();
  const add = (name, code) => {
    const kept = found.get(name);
    if (kept === undefined || rank(code) < rank(kept)) found.set(name, code);
  };
  if (!validate(data)) {
    for (const e of validate.errors ?? []) add(fieldOf(e), e.keyword);
  }
  if (data !== null && typeof data === 'object' && !Array.isArray(data)) {
    const props = new Map(Object.entries(schema.properties ?? {}));
    if (schema['x-moc-nfc'] === true) {
      for (const [name, value] of Object.entries(data)) {
        if (props.has(name) && typeof value === 'string' && value !== value.normalize('NFC')) add(name, 'x-moc-nfc');
      }
    }
    for (const [name, prop] of props) {
      const rule = prop['x-moc-date'];
      const value = data[name];
      if (!rule || found.has(name) || typeof value !== 'string') continue;
      if (rule === 'not-after-today' && value > today || rule === 'not-before-today' && value < today) {
        found.set(name, 'x-moc-date');
      }
    }
  }
  const errors = {};
  for (const [name, code] of found) {
    Object.defineProperty(errors, name, { value: code, enumerable: true, writable: true });
  }
  return errors;
}
