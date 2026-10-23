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

-- Kiểm dịch (F3.1): svc-files ghi mỗi tệp bị ClamAV chặn vào sổ kiểm toán (action file.rejected, entity_id là
-- SHA-256 của tệp) kèm tên tệp, cỡ, mẫu mã độc. Mẫu mã độc và cỡ tệp của tệp bị chặn không chứa nội dung văn bản,
-- nên màn "Sổ kiểm toán" được thấy. Chỉ mở cho dòng file.rejected: cỡ của tệp đã lưu (dòng core.files) vẫn ẩn,
-- vì tệp có thể thuộc văn bản hạn chế. Tên tệp vẫn ẩn — do người dùng đặt, có thể nói lên nội dung.
create or replace function core.audit_overview(r core.audit_log) returns jsonb
language sql stable
as $$
  select case when jsonb_typeof(r.diff) <> 'object' then '{}'::jsonb else (
    select coalesce(jsonb_object_agg(k, case when k = any (array[
             'status', 'urgency', 'direction', 'register_number', 'registered_at', 'due_on', 'issued_on',
             'restricted', 'is_public', 'role', 'enabled', 'department_id', 'user_id', 'signer_id',
             'document_id', 'file_id', 'year', 'entries', 'masked'
           ]) or (r.action = 'file.rejected' and k in ('signature', 'size_bytes')) then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;
