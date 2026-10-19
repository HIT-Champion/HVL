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

const VN = 'Asia/Ho_Chi_Minh';
export function fmtDate(value) {
    if (!value) return '—';
    const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (day) return `${day[3]}/${day[2]}/${day[1]}`;
    return new Intl.DateTimeFormat('vi-VN', {
        timeZone: VN,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    }).format(new Date(value));
}
export function fmtDateTime(value) {
    if (!value) return '—';
    return new Intl.DateTimeFormat('vi-VN', {
        timeZone: VN,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }).format(new Date(value));
}
export function today() {
    return new Intl.DateTimeFormat('en-CA', {
        timeZone: VN
    }).format(new Date());
}
export function addDays(iso, days) {
    const d = new Date(`${iso}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
}
export function fmtNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? new Intl.NumberFormat('vi-VN', {
        maximumFractionDigits: 2
    }).format(n) : '—';
}
export function initialOf(givenName, name) {
    const word = givenName.trim() || name.trim().split(/\s+/).pop() || '';
    return word ? word.charAt(0).toLocaleUpperCase('vi') : '?';
}
export function fmtSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
