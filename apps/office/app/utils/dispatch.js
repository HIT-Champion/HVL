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

export function toggleRecipient(text, name, on) {
    const lines = text.split('\n');
    const same = (line)=>line.trim() === name.trim();
    if (on) {
        if (lines.some(same)) return text;
        const kept = text.replace(/\s+$/, '');
        return kept ? `${kept}\n${name}` : name;
    }
    return lines.filter((line)=>!same(line)).join('\n');
}
export function sameSha256(a, b) {
    const norm = (v)=>v.trim().replace(/^\\x/i, '').toLowerCase();
    if (!a || !b) return false;
    const x = norm(a);
    return /^[0-9a-f]{64}$/.test(x) && x === norm(b);
}
export function fmtVerifyCode(code) {
    return code ? `${code.slice(0, 5)}-${code.slice(5)}` : '';
}
