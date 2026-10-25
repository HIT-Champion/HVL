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

-- Lô nạp khối lớn (bulk import): một người gửi một tệp nhiều dòng, dịch vụ xử lý nền từng mẻ và báo kết quả theo
-- dòng. Khung chung cho lõi: `kind` cho biết dòng được ghi bằng đường nào — hiện chỉ `incoming` (văn bản đến: svc-files
-- gọi đúng Action receiveIncoming, tùy chọn registerIncoming, của đường nhận từng văn bản, thay mặt văn thư tạo lô).
-- Thêm loại lô: migration mới mở rộng check `kind` và một handler trong services/svc-files/src/svc_files/imports/. Mô
-- tả: services/svc-files/README.md mục "Nạp lô văn bản đến".
--
-- - Lô và dòng là hàng đợi bền trong CSDL như hộp thư đi (core.notification_deliveries): svc-files khởi động lại thì
--   vòng nền đọc lại dòng `pending` và làm tiếp. Vòng nền lấy lô đến giờ (`run_after <= now()`, sớm nhất trước): làm
--   xong một mẻ thì đặt `run_after = now()` để nhường lô khác; gặp lỗi tạm (lõi bận) thì lùi `run_after` ra sau. Mỗi
--   dòng được giữ (`claimed_until`, `claim_id`) trong lúc một vòng đang làm: hai tiến trình chạy cùng không làm trùng
--   một dòng, và vòng đã mất dòng (quá hạn giữ, vòng khác nhận lại) không ghi được gì vào dòng nữa.
-- - `ok`, `duplicate`, `failed` là ảnh chụp lúc đóng lô (`done`); khi lô đang chạy, API đếm thẳng từ core.import_rows
--   nên không có bộ đếm nào trôi so với dòng.
-- - Dữ liệu của dòng (`data`) chỉ giữ khi còn chờ; xong (ok, duplicate, failed) thì xóa, chỉ còn mã lỗi, lời nhắn, lỗi
--   theo trường và kết quả (id văn bản, số đến) — văn bản thật nằm ở office.documents, có sổ kiểm toán chuỗi băm của
--   nó. Khi còn chờ, `result` giữ id các tệp đính kèm đã kiểm dịch, lưu xong: thử lại không lưu tệp lần hai.
-- - Hai bảng không gắn trigger core.audit(): mỗi mẻ đổi `run_after` và trạng thái từng dòng, gắn trigger thì lô vài
--   trăm dòng làm sổ phình mà không thêm gì. Thay vào đó có hai sự kiện: `import.created` do svc-files ghi cùng
--   mutation tạo lô (người làm là văn thư), `import.finished` do trigger `import_jobs_finished` bên dưới ghi đúng một
--   lần, trong giao dịch chuyển lô sang `done` (`actor_kind` service, người là văn thư).
--   Màn Sổ kiểm toán thấy loại lô, định dạng, có vào sổ không và số dòng (core.audit_overview bên dưới), không thấy
--   tên tệp.
-- - Không vai trò người dùng nào đọc hay ghi hai bảng qua GraphQL: chỉ svc-files (vai trò service của đúng đơn vị lô,
--   db/metadata) — API /api/imports kiểm token, vai trò văn thư và chỉ cho người tạo lô xem lô của mình. Vòng nền tìm
--   lô đến giờ của mọi đơn vị bằng khóa quản trị, chỉ đọc.

create table core.import_jobs (
  id               uuid primary key,                -- svc-files sinh; mã yêu cầu của từng dòng là "<lô>:<dòng>"
  tenant_id        uuid not null references core.tenants,
  kind             text not null check (kind in ('incoming')),
  -- sub của người tạo lô (từ token); mọi dòng được ghi thay mặt người này
  created_by       text not null check (char_length(created_by) between 1 and 255),
  department_id    uuid,                            -- phòng trong token lúc tạo lô (phiên Hasura khi gọi Action)
  status           text not null default 'queued' check (status in ('queued', 'running', 'done')),
  filename         text not null check (char_length(filename) between 1 and 255),
  format           text not null check (format in ('ndjson', 'csv')),
  data_sha256      text not null check (data_sha256 ~ '^[0-9a-f]{64}$'),
  archive_sha256   text check (archive_sha256 ~ '^[0-9a-f]{64}$'),
  archive_bytes    bigint check (archive_bytes >= 0),
  options          jsonb not null default '{}' check (jsonb_typeof(options) = 'object'),   -- {"register": bool}
  -- Idempotency-Key của yêu cầu tạo lô: ký tự ASCII in được, không khoảng trắng
  idempotency_key  text check (idempotency_key ~ '^[!-~]{1,200}$'),
  total            int not null check (total between 1 and 100000),
  ok               int not null default 0 check (ok >= 0),
  duplicate        int not null default 0 check (duplicate >= 0),
  failed           int not null default 0 check (failed >= 0),
  note             text check (char_length(note) <= 500),   -- vd tạm dừng vì lõi bận, tệp nén mất sau khi khởi động lại
  created_at       timestamptz not null default now(),
  started_at       timestamptz,
  run_after        timestamptz not null default now(),       -- vòng nền làm lô này từ lúc này trở đi
  finished_at      timestamptz,
  constraint import_jobs_tenant unique (id, tenant_id),
  -- gửi lại cùng Idempotency-Key thì trả lô cũ, không tạo lô thứ hai (nhiều lô không có khóa vẫn được: null khác nhau)
  constraint import_jobs_key unique (tenant_id, created_by, idempotency_key),
  constraint import_jobs_counts check (ok + duplicate + failed <= total),
  -- lô đóng thì mọi dòng đã xong: số đếm khớp tổng
  constraint import_jobs_closed check (status <> 'done' or ok + duplicate + failed = total),
  constraint import_jobs_done check ((status = 'done') = (finished_at is not null)),
  constraint import_jobs_archive check ((archive_sha256 is null) = (archive_bytes is null))
);

-- vòng nền: lô chưa xong đến giờ, sớm nhất trước
create index import_jobs_due on core.import_jobs (run_after) where status <> 'done';
-- danh sách lô của một người
create index import_jobs_creator on core.import_jobs (tenant_id, created_by, created_at desc);

create table core.import_rows (
  job_id     uuid not null,
  tenant_id  uuid not null,
  line       int not null check (line >= 1),          -- dòng của tệp gửi lên (NDJSON: dòng vật lý; CSV: tiêu đề là 1)
  data       jsonb check (jsonb_typeof(data) = 'object'),
  files      text[] not null default '{}' check (cardinality(files) <= 20),  -- tên tệp trong zip đính kèm
  status     text not null default 'pending' check (status in ('pending', 'ok', 'duplicate', 'failed')),
  attempts   int not null default 0 check (attempts between 0 and 20),       -- số lượt đã bắt đầu xử lý dòng
  -- id văn bản đã tạo, số đến; khi còn chờ: id tệp đính kèm đã kiểm dịch, lưu xong — thử lại không lưu lần hai
  result     jsonb check (jsonb_typeof(result) = 'object'),
  code       text check (code ~ '^[a-z_]{1,40}$'),
  message    text check (char_length(message) <= 500),
  fields     jsonb check (jsonb_typeof(fields) = 'object'),
  done_at    timestamptz,
  -- vòng nền đang giữ dòng tới lúc này: nhận dòng là cập nhật có điều kiện (chưa ai giữ hoặc đã quá hạn), nên hai vòng
  -- không cùng làm một dòng; tiến trình chết giữa chừng thì hết hạn là dòng nhận lại được
  claimed_until timestamptz,
  -- mã lượt giữ (svc-files sinh mỗi lần nhận dòng): lưu tiến độ, thả, ghi kết quả đều kèm mã này trong điều kiện, nên
  -- vòng đã mất dòng (quá hạn giữ, vòng khác nhận lại) không ghi đè được gì
  claim_id   uuid,
  primary key (job_id, line),
  foreign key (job_id, tenant_id) references core.import_jobs (id, tenant_id) on delete cascade,
  constraint import_rows_done check ((status = 'pending') = (done_at is null)),
  -- dữ liệu chỉ giữ khi còn chờ; dòng hỏng lúc đọc tệp (JSON sai…) thất bại ngay, không có dữ liệu
  constraint import_rows_data check (status <> 'pending' or data is not null),
  constraint import_rows_cleared check (status = 'pending' or data is null),
  constraint import_rows_failed check ((status = 'failed') = (code is not null))
);

-- vòng nền: dòng còn chờ của một lô, theo thứ tự trong tệp
create index import_rows_pending on core.import_rows (job_id, line) where status = 'pending';

-- Đóng lô (status → done) ghi đúng một dòng sổ `import.finished`, trong cùng giao dịch với lệnh đóng: hai vòng nền (hai
-- tiến trình svc-files) cùng đóng một lô thì lệnh của bên sau không đổi dòng nào (`status <> 'done'` trong điều kiện,
-- svc-files imports/store.py) nên không ghi sổ lần hai. Người làm là văn thư tạo lô, `actor_kind` service, mã yêu cầu
-- là id lô; `diff` là loại, định dạng, có vào sổ không và số dòng chụp lúc đóng — tên tệp không vào sổ.
create function core.import_finished() returns trigger
language plpgsql security definer set search_path = pg_catalog, pg_temp
as $$
begin
  insert into core.audit_log (tenant_id, actor_id, actor_kind, request_id, action, entity, entity_id, diff)
  values (new.tenant_id, new.created_by, 'service', new.id::text, 'import.finished', 'core.import_jobs', new.id::text,
          jsonb_build_object('kind', new.kind, 'format', new.format,
                             'register', coalesce(new.options -> 'register' = 'true'::jsonb, false),
                             'total', new.total, 'ok', new.ok, 'duplicate', new.duplicate, 'failed', new.failed));
  return null;
end
$$;

create trigger import_jobs_finished after update of status on core.import_jobs
  for each row when (old.status <> 'done' and new.status = 'done') execute function core.import_finished();

-- ---------------------------------------------------------------------------
-- Màn Sổ kiểm toán: dòng `import.created`, `import.finished` hiện loại lô, định dạng, có vào sổ không, tổng số dòng và
-- số dòng đạt / trùng / lỗi. Tên tệp (`filename`), băm tệp chỉ có tên khóa. Còn lại như migration 1792281602100.
-- ---------------------------------------------------------------------------

create or replace function core.audit_overview(r core.audit_log) returns jsonb
language sql stable
as $$
  select case when jsonb_typeof(r.diff) <> 'object' then '{}'::jsonb else (
    select coalesce(jsonb_object_agg(k, case when k = any (array[
             'status', 'urgency', 'direction', 'register_number', 'registered_at', 'due_on', 'issued_on',
             'restricted', 'is_public', 'role', 'enabled', 'department_id', 'user_id', 'signer_id',
             'document_id', 'file_id', 'year', 'entries', 'masked',
             'to_tenant_id', 'incoming_document_id', 'source_id', 'attempts', 'delivered_at'
           ]) or (r.action = 'file.rejected' and k in ('signature', 'size_bytes'))
              or (r.entity in ('office.case_files', 'office.case_file_documents')
                  and k in ('code', 'closed_on', 'retention_years', 'archived_at', 'archive_sha256', 'case_file_id'))
              or (r.action = 'case_file.archived' and k in ('code', 'archive_sha256', 'documents', 'files'))
              or (r.action = 'case_file.read' and k in ('code', 'archive_sha256'))
              or (r.action = 'intake.suggested'
                  and k in ('method', 'pages', 'found', 'summary_source', 'model', 'duration_ms', 'reason'))
              or (r.action = 'assistant.answered'
                  and k in ('ask_id', 'mode', 'answer_source', 'hits', 'cited', 'semantic', 'model', 'embed_model',
                            'duration_ms', 'warnings'))
              or (r.action = 'assignment.suggested'
                  and k in ('outcome', 'outcome_reason', 'due_days', 'confidence', 'evidence', 'candidates', 'semantic',
                            'duration_ms'))
              or (r.action in ('import.created', 'import.finished')
                  and k in ('kind', 'format', 'register', 'total', 'ok', 'duplicate', 'failed'))
           then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;
