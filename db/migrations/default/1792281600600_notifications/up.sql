-- Copyright 2026 Signet Team
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--
-- SPDX-License-Identifier: Apache-2.0

-- Thông báo gửi từng người (F2.5): việc mới, nhắc hạn, báo lãnh đạo khi quá hạn, văn bản đã phát hành.
-- Mô tả: docs/mo-hinh-du-lieu.md §1.
--
-- Bảng này là nơi giữ thông báo; Centrifugo chỉ đẩy bản sao xuống trình duyệt đang mở. Người không mở trang
-- lúc đó vẫn thấy thông báo khi vào lại, và đẩy hỏng thì không mất gì. Dịch vụ ghi bằng vai trò service; người
-- dùng chỉ đọc thông báo của mình và đánh dấu đã đọc.
--
-- Không gắn sổ kiểm toán: thông báo là bản tin phái sinh từ các bước nghiệp vụ đã được kiểm toán.

create table core.notifications (
  id           bigint generated always as identity primary key,
  tenant_id    uuid not null references core.tenants,
  user_id      text not null,
  kind         text not null check (kind ~ '^[a-z]+(\.[a-z_]+)+$'),   -- task.assigned, task.overdue, …
  -- khóa chống gửi trùng: cùng người, cùng khóa thì chỉ một thông báo (gọi lại sau lỗi, timer bắn lại)
  key          text not null check (char_length(key) between 1 and 200),
  document_id  uuid,                                                     -- office.documents; core không phụ thuộc office
  data         jsonb not null default '{}' check (jsonb_typeof(data) = 'object'),
  created_at   timestamptz not null default now(),
  read_at      timestamptz,
  constraint notifications_once unique (tenant_id, user_id, key),
  foreign key (tenant_id, user_id) references core.users (tenant_id, id) on delete cascade
);

-- chuông thông báo: số chưa đọc và 20 thông báo mới nhất của một người
create index notifications_user_recent on core.notifications (user_id, created_at desc);
create index notifications_user_unread on core.notifications (user_id) where read_at is null;
