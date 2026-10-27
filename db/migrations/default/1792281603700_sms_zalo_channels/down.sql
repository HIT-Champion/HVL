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


-- Bỏ kênh SMS, Zalo. Dòng chờ, dòng đã gửi qua hai kênh này xóa khỏi hộp thư đi (sổ kiểm toán vẫn giữ, sổ chỉ được
-- ghi thêm); thông báo trên web không đổi, chỉ bỏ hai kênh khỏi cột channels.
create or replace function core.queue_notification_deliveries() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  insert into core.notification_deliveries (tenant_id, notification_id, user_id, channel)
  select distinct new.tenant_id, new.id, new.user_id, c from unnest(new.channels) as c
  on conflict on constraint notification_deliveries_once do nothing;
  return null;
end
$$;

drop table core.notification_subscriptions;

delete from core.notification_deliveries where channel in ('sms', 'zalo');
alter table core.notification_deliveries
  drop constraint notification_deliveries_channel,
  add constraint notification_deliveries_channel_check check (channel in ('email', 'webhook'));

update core.notifications set channels = array(select c from unnest(channels) as c where c in ('email', 'webhook'))
 where channels && array['sms', 'zalo']::text[];
alter table core.notifications
  drop constraint notifications_channels,
  add constraint notifications_channels check (channels <@ array['email', 'webhook']::text[]);

alter table core.users drop column phone;
