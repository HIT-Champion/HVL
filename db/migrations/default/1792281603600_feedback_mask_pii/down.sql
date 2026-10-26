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

-- Trả trigger về bản của migration 1792281602700_feedback (không che). Chỗ đã che trong các góp ý không mở lại được:
-- số gốc không lưu ở đâu cả.
create or replace function office.feedback_guard() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
declare
  recent int;
  today  int;
begin
  new.comment := nullif(regexp_replace(new.comment, '^\s+|\s+$', '', 'g'), '');
  new.created_at := now();
  perform pg_advisory_xact_lock(hashtextextended('office.feedback:' || new.tenant_id || ':' || new.user_id, 0));
  select count(*) filter (where f.created_at > now() - interval '10 minutes'), count(*)
    into recent, today
    from office.feedback f
   where f.tenant_id = new.tenant_id and f.user_id = new.user_id and f.created_at > now() - interval '24 hours';
  if recent >= 3 or today >= 20 then
    raise exception 'feedback_rate: gửi quá nhiều góp ý — tối đa 3 góp ý mỗi 10 phút, 20 góp ý mỗi 24 giờ'
      using errcode = 'check_violation';
  end if;
  return new;
end
$$;

drop function office.mask_pii(text);
