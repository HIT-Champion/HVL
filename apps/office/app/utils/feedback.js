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

// Góp ý trong Văn phòng điện tử (F4.6, docs/so-lieu-sau.md): màn hình gắn vào góp ý, tên màn hình để hiện, điểm trung
// bình. Màn hình là khuôn đường dẫn chứ không phải đường dẫn thật: chỉ giữ đoạn toàn chữ thường và gạch nối, đoạn khác
// thành `:id`, bỏ chuỗi truy vấn — id văn bản, mã tra cứu, chữ người dùng gõ vào ô tìm (/tim-kiem?q=…) không rời trình
// duyệt. CSDL kiểm lại đúng khuôn này (ràng buộc feedback_screen, migration 1792281602700). CSDL cũng chặn gửi dồn: 3
// góp ý mỗi 10 phút, 20 mỗi 24 giờ cho mỗi người.

export const FEEDBACK_MAX = 500;
export const FEEDBACK_RATINGS = [1, 2, 3, 4, 5];
const SLUG = /^[a-z]+(-[a-z]+)*$/;
const MAX_SEGMENTS = 6;
const MAX_LENGTH = 80;

export function feedbackScreen(path) {
  const parts = (path.split(/[?#]/)[0] ?? '').split('/').filter(Boolean).slice(0, MAX_SEGMENTS).
  map((p) => SLUG.test(p) ? p : ':id');
  while (parts.length && `/${parts.join('/')}`.length > MAX_LENGTH) parts.pop();
  return `/${parts.join('/')}`;
}

// Tên màn hình theo khóa i18n của thanh bên; khuôn lạ (màn hình mới chưa có tên) thì hiện nguyên khuôn
const SCREEN_KEYS = {
  '/': 'nav.inbox',
  '/van-ban-den': 'nav.incoming',
  '/van-ban-den/tiep-nhan': 'nav.receive',
  '/van-ban-di': 'nav.outgoing',
  '/van-ban-di/soan': 'nav.compose',
  '/van-ban/:id': 'feedback.screenDocument',
  '/so-dang-ky': 'nav.register',
  '/ho-so': 'cases.title',
  '/ho-so/:id': 'cases.screenDetail',
  '/tim-kiem': 'nav.search',
  '/hoi-dap': 'nav.ask',
  '/dieu-hanh': 'nav.board',
  '/pha-he': 'lineage.nav',
  '/so-kiem-toan': 'nav.audit',
  '/so-do': 'nav.metrics',
  '/gop-y': 'nav.feedback',
  '/tu-chan-doan': 'nav.selfCheck',
  '/ung-dung': 'apps.nav',
  '/cam-bien': 'nav.sensors'
};

export function screenLabel(t, screen) {
  if (screen === null) return t('feedback.allScreens');
  const key = SCREEN_KEYS[screen];
  return key ? t(key) : screen;
}

export function screenKeys() {
  return Object.values(SCREEN_KEYS);
}

// Một dòng của office.v_feedback_summary (migration 1792281602750); screen null: mọi màn hình























export function averageRating(row)
{
  return row && row.feedback ? row.rating_total / row.feedback : null;
}

export function ratingCounts(row) {
  return [row.rating_1, row.rating_2, row.rating_3, row.rating_4, row.rating_5];
}

// Dòng mọi màn hình và các màn hình, nhiều góp ý trước, cùng số thì điểm thấp trước (chỗ cần sửa lên đầu)
export function splitSummary(rows)
{
  const screens = rows.filter((r) => r.screen !== null).
  sort((a, b) => b.feedback - a.feedback || (averageRating(a) ?? 0) - (averageRating(b) ?? 0) ||
  (a.screen ?? '').localeCompare(b.screen ?? ''));
  return { total: rows.find((r) => r.screen === null) ?? null, screens };
}
