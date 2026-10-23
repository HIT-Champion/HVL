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

-- Không gian cá nhân P.A.R.A (ứng dụng thứ hai trên lõi, apps/ca-nhan, không gian [H]): schema riêng `personal` của
-- ứng dụng, không sửa gì trong `core` (docs/mo-hinh-du-lieu.md §0). Tệp vẫn là dòng core.files do svc-files thêm sau
-- khi ClamAV quét sạch; bảng ở đây chỉ ghi tệp nào của ai nằm ở thư mục nào trong bốn thư mục P.A.R.A (Projects,
-- Areas, Resources, Archives). Sổ kiểm toán dùng trigger core.audit() có sẵn. Mô tả: docs/mo-hinh-du-lieu.md §2.6,
-- cách thêm một ứng dụng: docs/them-ung-dung.md.

create schema personal;

create table personal.items (               -- một tệp đã qua kiểm dịch, đặt vào một thư mục P.A.R.A
  file_id     uuid primary key,
  tenant_id   uuid not null references core.tenants,
  owner_id    text not null,                -- sub Keycloak; phải là người tải tệp lên (trigger items_guard)
  para        text not null
              constraint items_para check (para in ('projects', 'areas', 'resources', 'archives')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  -- khóa ngoại kèm thuê ước: không đặt được tệp của đơn vị khác. Tệp bị xóa khỏi core.files thì mục xóa theo, không
  -- chặn việc của lõi
  constraint items_file foreign key (tenant_id, file_id) references core.files (tenant_id, id) on delete cascade
);

create index items_owner_para on personal.items (tenant_id, owner_id, para, updated_at desc);

-- Chỉ đặt vào không gian của mình tệp chính mình tải lên và không mã hóa: tệp mã hóa thuộc văn bản hạn chế, đi theo
-- quyền đọc văn bản chứ không theo người tải lên (F3.7). Thêm rồi thì không đổi tệp, chủ, đơn vị; chỉ đổi thư mục.
-- Hasura đặt sẵn owner_id, tenant_id từ token; trigger giữ đúng quy tắc đó cả khi ghi thẳng CSDL. Mốc thời gian do
-- CSDL đặt.
create function personal.items_guard() returns trigger
language plpgsql
as $$
begin
  if tg_op = 'UPDATE' then
    if new.file_id <> old.file_id or new.owner_id <> old.owner_id or new.tenant_id <> old.tenant_id then
      raise exception 'personal.items: chỉ đổi được thư mục, không đổi tệp, chủ hay đơn vị'
        using errcode = 'check_violation', constraint = 'items_guard';
    end if;
    new.created_at := old.created_at;
    new.updated_at := now();
    return new;
  end if;
  if not exists (select 1 from core.files f
                  where f.id = new.file_id and f.tenant_id = new.tenant_id
                    and f.created_by = new.owner_id and not f.encrypted) then
    raise exception 'personal.items: chỉ đặt được tệp chính mình tải lên, không mã hóa'
      using errcode = 'check_violation', constraint = 'items_guard';
  end if;
  new.created_at := now();
  new.updated_at := new.created_at;
  return new;
end
$$;

create trigger items_guard before insert or update on personal.items
  for each row execute function personal.items_guard();

-- Sổ kiểm toán chuỗi băm của lõi: mỗi lần đặt, chuyển thư mục là một dòng, người làm lấy từ phiên Hasura
create trigger audit after insert or update or delete on personal.items
  for each row execute function core.audit('file_id');

comment on table personal.items is 'Không gian cá nhân P.A.R.A: tệp đã qua kiểm dịch của chính người dùng, xếp vào '
  'một trong bốn thư mục projects, areas, resources, archives';
