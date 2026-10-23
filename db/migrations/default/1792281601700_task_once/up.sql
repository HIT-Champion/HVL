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

-- Một việc trong quy trình chỉ ghi dữ liệu một lần. svc-workflow hỏi "đã có sự kiện mang task_id này chưa" rồi mới
-- ghi; hai lần gọi chen nhau (bấm lại khi chờ lâu, hai bản sao dịch vụ) cùng qua bước hỏi thì ghi đôi: hai phân
-- công, hai lần phát hành. Chỉ mục duy nhất theo task_id chặn lần ghi thứ hai, cả giao dịch của nó không ghi gì;
-- svc-workflow coi lỗi này như "đã ghi", chỉ hoàn thành nốt việc trong Flowable.
-- Sự kiện nhắc hạn (sla_task_id) và sự kiện không gắn việc (vào sổ, trình) không thuộc chỉ mục.
-- Dữ liệu cũ đã trùng thì không dựng được chỉ mục cho cả bảng: báo ra, chỉ chặn từ sau dòng trùng cuối — không sửa
-- sự kiện cũ (dòng thời gian là lịch sử), không để việc nâng cấp hỏng vì dữ liệu có từ trước.

do $$
declare
  last_dup bigint;
begin
  -- dòng cuối của các nhóm trùng: mọi dòng sau nó có task_id chưa từng gặp
  select max(last_id) into last_dup
  from (select max(id) as last_id from office.document_events
        where data->>'task_id' is not null group by data->>'task_id' having count(*) > 1) d;
  if last_dup is null then
    create unique index document_events_task_once on office.document_events ((data->>'task_id'))
      where data->>'task_id' is not null;
  else
    raise warning 'office.document_events có sự kiện trùng task_id (dòng cuối %); chỉ mục chỉ chặn từ dòng sau đó',
      last_dup;
    execute format('create unique index document_events_task_once on office.document_events ((data->>''task_id'')) '
                   'where data->>''task_id'' is not null and id > %s', last_dup);
  end if;
end $$;
