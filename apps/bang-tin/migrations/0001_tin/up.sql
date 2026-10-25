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

-- Bảng tin đơn vị (apps/bang-tin). moc app install chạy tệp này bằng vai trò CSDL riêng moc_appdb_bang_tin, chỉ làm
-- chủ schema bang_tin (lõi tạo schema theo manifest): không thấy core, office — nên không khóa ngoại tới core.tenants,
-- không gắn trigger core.audit(). Mỗi dòng là một sự kiện của lõi (core.app_events, đã có trong sổ kiểm toán của lõi
-- qua office.document_events) mà phần máy chủ của ứng dụng nhận qua webhook rồi ghi lại bằng vai trò Hasura
-- app_bang_tin.

create table bang_tin.tin (
  event_id     bigint primary key,           -- = core.app_events.id: Hasura gửi lại thì không thành hai dòng
  tenant_id    uuid not null,                -- đơn vị của sự kiện (core.app_events.tenant_id)
  -- không khóa ngoại tới office.documents: nộp lưu (F3.8) gỡ văn bản khỏi CSDL nghiệp vụ, bảng tin không được chặn
  -- việc đó
  document_id  uuid not null,
  kind         text not null check (kind in ('office.document.registered', 'office.document.issued')),
  occurred_at  timestamptz not null,
  received_at  timestamptz not null default now()
);

create index tin_tenant_occurred on bang_tin.tin (tenant_id, occurred_at desc);
