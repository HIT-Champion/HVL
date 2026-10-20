-- Copyright 2026 Mộc Team
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

-- Phả hệ dữ liệu (F3.9): sự kiện OpenLineage của job nộp lưu (svc_files.lineage), mỗi bước một run. Bảng chỉ thêm,
-- không sửa, không xóa — như sổ kiểm toán, nhưng không vào chuỗi băm (phả hệ là số liệu vận hành, không phải chứng
-- cứ nghiệp vụ). Cột `event` giữ nguyên sự kiện theo đặc tả OpenLineage để chuyển sang máy chủ khác (Marquez) khi cần;
-- các cột còn lại tách sẵn để tra theo hồ sơ, theo dataset. Không chứa tên hồ sơ, trích yếu: chỉ id, key đối tượng,
-- số dòng, băm.

create table core.lineage_events (
  id             bigint generated always as identity primary key,
  tenant_id      uuid references core.tenants,                  -- null: việc của nền tảng
  run_id         uuid not null,
  parent_run_id  uuid,
  job            text not null,
  event_type     text not null check (event_type in ('START', 'RUNNING', 'COMPLETE', 'ABORT', 'FAIL', 'OTHER')),
  event_time     timestamptz not null,
  inputs         text[] not null default '{}',                  -- "<namespace>/<name>"
  outputs        text[] not null default '{}',
  quality_ok     boolean,                                        -- null: bước này không kiểm chất lượng
  event          jsonb not null,
  recorded_at    timestamptz not null default now()
);
create index lineage_events_run on core.lineage_events (run_id);
create index lineage_events_parent on core.lineage_events (parent_run_id);
create index lineage_events_outputs on core.lineage_events using gin (outputs);

create function core.lineage_events_append_only() returns trigger language plpgsql as $$
begin
  raise exception 'phả hệ dữ liệu chỉ thêm, không sửa hay xóa được' using errcode = 'check_violation';
end $$;
create trigger lineage_events_append_only before update or delete on core.lineage_events
  for each row execute function core.lineage_events_append_only();
