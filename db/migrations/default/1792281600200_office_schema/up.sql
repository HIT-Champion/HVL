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

-- Schema office: ứng dụng Văn phòng điện tử — văn bản đến / đi, sổ, giao việc.
-- Mô tả và lý do: docs/mo-hinh-du-lieu.md §2. Hồ sơ công việc (§2.4) và các view báo cáo (§2.5)
-- thêm ở Phase 2–3.
--
-- Khóa ngoại giữa các bảng nghiệp vụ đi kèm tenant_id: CSDL tự chặn việc trỏ sang phòng, sổ,
-- văn bản hay tệp của thuê ước khác, kể cả khi lớp quyền phía trên có lỗi.

create schema office;

create function office.touch_updated_at() returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end
$$;

-- ---------------------------------------------------------------------------
-- Danh mục
-- ---------------------------------------------------------------------------

create table office.departments (           -- phòng, bộ môn trong một đơn vị
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references core.tenants,
  code       text not null check (code ~ '^[^[:space:]/-]{1,20}$'),  -- viết tắt trong ký hiệu, vd 'ĐT'
  name       text not null check (btrim(name) <> ''),
  unique (tenant_id, code),
  unique (tenant_id, id)
);

create table office.document_types (        -- tên loại văn bản theo NĐ 30/2020/NĐ-CP
  code       text primary key check (code ~ '^[^[:space:]/-]{1,10}$'),
  name       text not null unique,
  in_symbol  boolean not null                -- công văn: false — ký hiệu không có tên loại
);

create table office.registers (             -- sổ đăng ký văn bản, mỗi năm một sổ
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references core.tenants,
  direction    text not null check (direction in ('in', 'out')),
  year         int  not null check (year between 2000 and 2100),
  last_number  int  not null default 0 check (last_number >= 0),
  unique (tenant_id, direction, year),
  unique (tenant_id, id, direction)          -- văn bản đến chỉ vào được sổ đến, văn bản đi chỉ sổ đi
);

-- ---------------------------------------------------------------------------
-- Văn bản
-- ---------------------------------------------------------------------------

create table office.documents (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references core.tenants,
  direction        text not null check (direction in ('in', 'out')),
  status           text not null,
  type_code        text not null references office.document_types,

  -- thông tin trên văn bản
  symbol           text check (symbol is null or btrim(symbol) <> ''),   -- số, ký hiệu: '123/ĐHCN-ĐT'
  issuer_name      text check (issuer_name is null or btrim(issuer_name) <> ''),
  issued_on        date,
  summary          text not null check (char_length(btrim(summary)) between 10 and 500),  -- trích yếu
  urgency          text not null default 'normal'
                   check (urgency in ('normal', 'khan', 'thuong_khan', 'hoa_toc')),
  restricted       boolean not null default false,   -- hạn chế truy cập (F3.7), KHÔNG phải văn bản mật
  is_public        boolean not null default false,   -- cổng xác thực được hiện trích yếu

  -- đăng ký
  register_id      uuid,
  register_number  int  check (register_number > 0),
  registered_at    timestamptz,
  due_on           date,                     -- hạn giải quyết chung của văn bản đến

  -- văn bản đi
  department_id    uuid,                     -- đơn vị soạn thảo
  signer_id        text,                     -- người ký (sub)
  recipients       text[] not null default '{}',     -- nơi nhận, như in trên văn bản
  reply_to_id      uuid,                     -- trả lời văn bản đến nào
  content_sha256   bytea unique check (content_sha256 is null or octet_length(content_sha256) = 32),
  verify_code      text unique check (verify_code is null or verify_code ~ '^[A-Z2-7]{10}$'),

  -- liên kết
  source_id        uuid references office.documents,  -- văn bản đi của đơn vị khác sinh ra văn bản đến này (F3.12)
  process_id       text unique,              -- processInstanceId của Flowable
  created_by       text not null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  unique (tenant_id, id),
  foreign key (tenant_id, register_id, direction) references office.registers (tenant_id, id, direction),
  foreign key (tenant_id, department_id) references office.departments (tenant_id, id),
  foreign key (tenant_id, reply_to_id) references office.documents (tenant_id, id),

  constraint documents_status_by_direction check (
       (direction = 'in'  and status in ('received', 'registered', 'in_progress', 'done', 'archived', 'cancelled'))
    or (direction = 'out' and status in ('draft', 'in_review', 'returned', 'approved', 'issued', 'archived', 'cancelled'))
  ),
  -- văn bản đến phải đủ thông tin nhận diện
  constraint documents_in_identity
    check (direction <> 'in' or (symbol is not null and issuer_name is not null and issued_on is not null)),
  -- đã vào sổ thì phải có số
  constraint documents_registered_has_number
    check (registered_at is null or (register_id is not null and register_number is not null)),
  constraint documents_register_pair check ((register_id is null) = (register_number is null)),
  constraint documents_in_registered
    check (direction <> 'in' or status in ('received', 'cancelled') or registered_at is not null),
  -- văn bản đi đã phát hành phải có đủ số, ký hiệu, ngày, băm, mã tra cứu
  constraint documents_out_issued_complete
    check (direction <> 'out' or status not in ('issued', 'archived')
         or (symbol is not null and register_number is not null and issued_on is not null
             and content_sha256 is not null and verify_code is not null and signer_id is not null)),
  constraint documents_due_after_registered
    check (due_on is null or registered_at is null or due_on >= registered_at::date),
  unique (register_id, register_number)
);

-- chặn vào sổ trùng: cùng cơ quan ban hành, cùng số ký hiệu, cùng ngày
create unique index documents_in_dedup on office.documents
  (tenant_id, lower(issuer_name), symbol, issued_on)
  where direction = 'in' and status <> 'cancelled';

create index documents_tenant_status on office.documents (tenant_id, direction, status);
create index documents_tenant_created on office.documents (tenant_id, created_at desc);
create index documents_department on office.documents (department_id);

create trigger touch before update on office.documents
  for each row execute function office.touch_updated_at();

create table office.document_files (
  tenant_id    uuid not null references core.tenants,
  document_id  uuid not null,
  file_id      uuid not null,
  role         text not null check (role in ('main', 'attachment', 'draft', 'issued')),
  version      int  not null default 1 check (version > 0),
  added_by     text not null,
  added_at     timestamptz not null default now(),
  primary key (document_id, file_id),
  foreign key (tenant_id, document_id) references office.documents (tenant_id, id),
  foreign key (tenant_id, file_id) references core.files (tenant_id, id)
);

create index document_files_file on office.document_files (file_id);
-- mỗi văn bản đi có đúng một bản phát hành (content_sha256 là băm của tệp này)
create unique index document_files_one_issued on office.document_files (document_id) where role = 'issued';

create table office.document_acl (          -- ai được xem văn bản hạn chế (F3.7)
  tenant_id    uuid not null references core.tenants,
  document_id  uuid not null,
  user_id      text not null,
  granted_by   text not null,
  granted_at   timestamptz not null default now(),
  primary key (document_id, user_id),
  foreign key (tenant_id, document_id) references office.documents (tenant_id, id)
);

-- ---------------------------------------------------------------------------
-- Giao việc và dòng thời gian
-- ---------------------------------------------------------------------------

create table office.assignments (           -- ý kiến chỉ đạo và giao việc (NĐ 30, Điều 23)
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references core.tenants,
  document_id    uuid not null,
  parent_id      uuid,                       -- phòng được giao → phân công tiếp cho người
  department_id  uuid,
  user_id        text,
  role           text not null check (role in ('lead', 'support', 'info')),  -- chủ trì / phối hợp / để biết
  instruction    text,                       -- ý kiến chỉ đạo
  due_on         date,
  status         text not null default 'open' check (status in ('open', 'done', 'cancelled')),
  result_note    text,
  assigned_by    text not null,
  assigned_at    timestamptz not null default now(),
  completed_at   timestamptz,
  unique (tenant_id, id),
  foreign key (tenant_id, document_id) references office.documents (tenant_id, id),
  foreign key (tenant_id, parent_id) references office.assignments (tenant_id, id),
  foreign key (tenant_id, department_id) references office.departments (tenant_id, id),
  constraint assignments_has_assignee check (department_id is not null or user_id is not null),
  constraint assignments_done_has_time check ((status = 'done') = (completed_at is not null)),
  constraint assignments_done_has_result check (status <> 'done' or role = 'info' or result_note is not null)
);

-- mỗi văn bản chỉ có một đầu mối chủ trì ở cấp giao đầu tiên
create unique index assignments_one_lead on office.assignments (document_id)
  where role = 'lead' and parent_id is null and status <> 'cancelled';
create index assignments_document on office.assignments (document_id);
create index assignments_open_user on office.assignments (tenant_id, user_id) where status = 'open';
create index assignments_open_department on office.assignments (tenant_id, department_id) where status = 'open';

create table office.document_events (       -- dòng thời gian hiển thị cho người dùng (F2.6)
  id           bigint generated always as identity primary key,
  tenant_id    uuid not null references core.tenants,
  document_id  uuid not null,
  kind         text not null,                -- danh sách sự kiện: docs/mo-hinh-du-lieu.md §5
  actor_id     text not null,
  actor_kind   text not null check (actor_kind in ('user', 'service', 'agent')),
  note         text,
  data         jsonb not null default '{}',
  created_at   timestamptz not null default now(),
  foreign key (tenant_id, document_id) references office.documents (tenant_id, id)
);

create index document_events_document on office.document_events (document_id, created_at);

-- ---------------------------------------------------------------------------
-- Ai được đọc văn bản nào (docs/mo-hinh-du-lieu.md §3)
--
-- Hasura gắn hàm này vào office.documents thành trường tính toán `visible` và dùng trong quyền đọc
-- của mọi bảng con, nên quy tắc chỉ viết một lần. hasura_session là biến phiên lấy từ JWT.
-- ---------------------------------------------------------------------------

create function office.document_visible(d office.documents, hasura_session json)
returns boolean
language sql stable
as $$
  select coalesce(
        d.tenant_id::text = hasura_session ->> 'x-hasura-tenant-id'
    and (   not d.restricted
         or d.created_by = hasura_session ->> 'x-hasura-user-id'
         or exists (select 1 from office.document_acl a
                     where a.document_id = d.id
                       and a.user_id = hasura_session ->> 'x-hasura-user-id'))
    and case hasura_session ->> 'x-hasura-role'
          when 'clerk'    then true
          when 'director' then true
          when 'manager'  then
                d.department_id::text = hasura_session ->> 'x-hasura-department-id'
             or exists (select 1 from office.assignments s
                         where s.document_id = d.id and s.status <> 'cancelled'
                           and s.department_id::text = hasura_session ->> 'x-hasura-department-id')
          when 'staff'    then
                d.created_by = hasura_session ->> 'x-hasura-user-id'
             or (d.direction = 'out'
                 and d.department_id::text = hasura_session ->> 'x-hasura-department-id')
             or exists (select 1 from office.assignments s
                         where s.document_id = d.id and s.status <> 'cancelled'
                           and s.user_id = hasura_session ->> 'x-hasura-user-id')
          else false
        end,
    false)
$$;

-- ---------------------------------------------------------------------------
-- Sổ kiểm toán: mọi bảng nghiệp vụ trừ document_events (bản thân nó đã là nhật ký hiển thị)
-- ---------------------------------------------------------------------------

create trigger audit after insert or update or delete on office.departments
  for each row execute function core.audit();
create trigger audit after insert or update or delete on office.document_types
  for each row execute function core.audit('code');
create trigger audit after insert or update or delete on office.registers
  for each row execute function core.audit();
create trigger audit after insert or update or delete on office.documents
  for each row execute function core.audit();
create trigger audit after insert or update or delete on office.document_files
  for each row execute function core.audit('document_id', 'file_id');
create trigger audit after insert or update or delete on office.document_acl
  for each row execute function core.audit('document_id', 'user_id');
create trigger audit after insert or update or delete on office.assignments
  for each row execute function core.audit();
