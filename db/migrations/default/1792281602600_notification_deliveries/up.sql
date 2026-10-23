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

-- Định tuyến thông báo đa kênh: ngoài chuông trên web (core.notifications + Centrifugo), svc-workflow gửi thêm qua
-- email (SMTP) và webhook (Mattermost, Slack, ntfy) khi được cấu hình. Mô tả: services/svc-workflow/README.md mục
-- "Thông báo qua email, webhook".
--
-- Hộp thư đi trong CSDL, như liên thông (office.dispatches): lúc ghi thông báo, svc-workflow khai kênh ngoài cần gửi ở
-- cột channels; trigger tạo một dòng core.notification_deliveries `pending` cho mỗi kênh trong cùng giao dịch — thông
-- báo đã lưu thì chắc chắn có dòng chờ gửi, dịch vụ dừng giữa chừng không làm mất thư. Gọi lại cùng khóa
-- (notifications_once) không thêm dòng thông báo nên cũng không thêm dòng chờ. Vòng nền của svc-workflow gửi rồi ghi
-- kết quả: sent, failed (hết lượt thử hoặc bị từ chối hẳn), skipped (chưa có email, văn bản hạn chế trên webhook…).
--
-- Dòng không chứa địa chỉ email, URL webhook hay nội dung: người nhận lấy từ danh bạ lúc gửi, nội dung dựng lại từ
-- thông báo, last_error chỉ có tên lỗi và mã SMTP/HTTP. Gắn sổ kiểm toán chuỗi băm: lần gửi, lần thử, lúc gửi được ghi
-- lại và không sửa lén được (chống chối bỏ); sổ thấy trạng thái, số lần thử, người nhận như với dòng liên thông. Không
-- vai trò người dùng nào đọc bảng qua GraphQL; svc-workflow (service) chỉ đọc và ghi kết quả, không thêm, không xóa.

alter table core.notifications
  add column channels text[] not null default '{}',
  add constraint notifications_channels check (channels <@ array['email', 'webhook']::text[]);

create table core.notification_deliveries (
  id               bigint generated always as identity primary key,
  tenant_id        uuid not null references core.tenants,
  notification_id  bigint not null references core.notifications on delete cascade,
  user_id          text not null,                -- người nhận của thông báo, chép để nối danh bạ lúc gửi
  channel          text not null check (channel in ('email', 'webhook')),
  status           text not null default 'pending' check (status in ('pending', 'sent', 'failed', 'skipped')),
  attempts         int not null default 0 check (attempts between 0 and 20),     -- số lần đã thử gửi
  last_error       text check (char_length(last_error) <= 200),
  next_attempt_at  timestamptz not null default now(),
  sent_at          timestamptz,
  created_at       timestamptz not null default now(),
  constraint notification_deliveries_once unique (notification_id, channel),
  constraint notification_deliveries_sent check ((status = 'sent') = (sent_at is not null))
);

-- vòng nền của svc-workflow: dòng chờ đã đến hạn thử
create index notification_deliveries_due on core.notification_deliveries (next_attempt_at) where status = 'pending';

create function core.queue_notification_deliveries() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  insert into core.notification_deliveries (tenant_id, notification_id, user_id, channel)
  select distinct new.tenant_id, new.id, new.user_id, c from unnest(new.channels) as c
  on conflict on constraint notification_deliveries_once do nothing;
  return null;
end
$$;

-- AFTER INSERT không chạy cho dòng bị bỏ qua vì trùng khóa (on conflict do nothing của svc-workflow)
create trigger notifications_deliveries after insert on core.notifications
  for each row when (cardinality(new.channels) > 0) execute function core.queue_notification_deliveries();

create trigger audit after insert or update or delete on core.notification_deliveries
  for each row execute function core.audit();
