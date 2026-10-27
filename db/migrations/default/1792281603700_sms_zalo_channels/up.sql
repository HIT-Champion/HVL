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


-- Kênh SMS, Zalo của thông báo (#365), tắt mặc định: svc-workflow chỉ gửi khi được cấu hình (MOC_SMS_GATEWAY_URL,
-- MOC_ZALO_BOT_TOKEN) và chỉ tới người đã tự bật kênh. Mô tả: services/svc-workflow/README.md mục "Thông báo qua SMS,
-- Zalo".
--
-- - core.users.phone: số điện thoại dạng E.164 (+84…), svc-workflow đồng bộ từ thuộc tính phone_number của Keycloak
--   như email. Chỉ dịch vụ đọc được: người trong đơn vị chọn người giao việc không cần thấy số của nhau.
-- - core.notification_subscriptions: người dùng tự bật SMS, Zalo (Action setMyChannel của svc-workflow). Zalo bật được
--   khi đã liên kết: Signet hiện một mã dùng một lần (link_code, hạn link_expires_at), người dùng nhắn mã đó cho bot
--   Zalo của đơn vị, svc-workflow đọc tin của bot (getUpdates) rồi ghi zalo_chat_id. Không vai trò người dùng nào đọc
--   bảng qua GraphQL; chỉ svc-workflow (service) đọc, ghi trong đơn vị của phiên.
-- - Trigger hộp thư đi chỉ tạo dòng sms, zalo cho người đã bật kênh (SMS: thêm điều kiện danh bạ có số), tài khoản
--   còn mở: thông báo khai cả bốn kênh nhưng người chưa bật thì không có dòng chờ nào, không có dòng skipped.

alter table core.users
  add column phone text constraint users_phone check (phone ~ '^\+[1-9][0-9]{7,14}$');

alter table core.notifications
  drop constraint notifications_channels,
  add constraint notifications_channels check (channels <@ array['email', 'webhook', 'sms', 'zalo']::text[]);

alter table core.notification_deliveries
  drop constraint notification_deliveries_channel_check,
  add constraint notification_deliveries_channel check (channel in ('email', 'webhook', 'sms', 'zalo'));

create table core.notification_subscriptions (
  tenant_id        uuid not null,
  user_id          text not null,
  channel          text not null check (channel in ('sms', 'zalo')),
  enabled          boolean not null default false,
  zalo_chat_id     text check (char_length(zalo_chat_id) between 1 and 64),    -- chat.id của tin người dùng gửi bot
  -- mã liên kết Zalo: 8 ký tự không có I, O, 0, 1 dễ đọc nhầm (40 bit), hết hạn sau ít phút
  link_code        text check (link_code ~ '^[A-HJ-NP-Z2-9]{8}$'),
  link_expires_at  timestamptz,
  primary key (tenant_id, user_id, channel),
  constraint notification_subscriptions_user foreign key (tenant_id, user_id) references core.users (tenant_id, id),
  constraint notification_subscriptions_zalo_only
    check (channel = 'zalo' or (zalo_chat_id is null and link_code is null)),
  constraint notification_subscriptions_linked check (channel = 'sms' or not enabled or zalo_chat_id is not null),
  constraint notification_subscriptions_code check ((link_code is null) = (link_expires_at is null))
);

-- vòng đọc tin của bot tìm mã trên mọi đơn vị (một bot cho cả bản cài); mã trùng thì svc-workflow sinh mã khác
create unique index notification_subscriptions_link_code on core.notification_subscriptions (link_code)
  where link_code is not null;

create trigger audit after insert or update or delete on core.notification_subscriptions
  for each row execute function core.audit('tenant_id', 'user_id', 'channel');

comment on table core.notification_subscriptions is 'Kênh SMS, Zalo người dùng tự bật cho thông báo của mình; Zalo '
  'kèm chat_id sau khi liên kết bằng mã dùng một lần';

create or replace function core.queue_notification_deliveries() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  insert into core.notification_deliveries (tenant_id, notification_id, user_id, channel)
  select distinct new.tenant_id, new.id, new.user_id, c from unnest(new.channels) as c
   where c in ('email', 'webhook')
      or exists (select 1
                   from core.notification_subscriptions s
                   join core.users u on u.tenant_id = s.tenant_id and u.id = s.user_id
                  where s.tenant_id = new.tenant_id and s.user_id = new.user_id and s.channel = c and s.enabled
                    and u.enabled and (c <> 'sms' or u.phone is not null))
  on conflict on constraint notification_deliveries_once do nothing;
  return null;
end
$$;
