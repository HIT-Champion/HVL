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

-- #381: sự kiện office.document.received ("văn thư thêm văn bản đến") nằm trong danh sách trắng cho ứng dụng
-- (migration 1792281603200_app_registry, scripts/ung_dung.py) nhưng chưa nơi nào ghi, nên ứng dụng nghe nó không nhận
-- được gì. Ghi bằng trigger cho mọi đường tạo văn bản đến: Action receiveIncoming (form tiếp nhận, nạp lô, make seed).
-- - Chỉ văn bản đến mới ở trạng thái received. Văn bản nhận liên thông (source_id) đã có office.document.arrived do
--   office.deliver_dispatch ghi (migration 1792281601800), không ghi thêm.
-- - Người làm là người tạo văn bản (created_by: văn thư, svc-workflow ghi thay), như office.document.registered.
-- - Lúc xảy ra là created_at của văn bản: mốc "văn bản đến" của số đo (office.v_time_to_assign) và của dòng thời gian.
-- - Văn bản hạn chế vẫn có dòng trong dòng thời gian; core.app_events_publish không chép sang ứng dụng (F3.7).
-- - Không ghi bù cho văn bản đã có: trigger chép sang core.app_events sẽ gửi cho ứng dụng đang nghe cả loạt sự kiện cũ.

create function office.document_received() returns trigger
language plpgsql set search_path = pg_catalog, pg_temp
as $$
begin
  insert into office.document_events (tenant_id, document_id, kind, actor_id, actor_kind, created_at)
  values (new.tenant_id, new.id, 'office.document.received', new.created_by, 'user', new.created_at);
  return null;
end
$$;

create trigger documents_received after insert on office.documents
  for each row when (new.direction = 'in' and new.status = 'received' and new.source_id is null)
  execute function office.document_received();
