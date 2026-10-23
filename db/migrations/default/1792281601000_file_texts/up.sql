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

-- Lớp chữ của tệp PDF (F2.7): svc-files đọc chữ trong PDF đã gắn vào văn bản rồi ghi ở đây, vòng đồng bộ tìm kiếm
-- đưa vào trường `content` của Meilisearch. Lưu trong CSDL để dựng lại chỉ mục (svc-files khởi động lại, đổi cấu
-- hình Meilisearch) mà không phải đọc lại mọi tệp.
--
-- - Không vai trò người dùng nào đọc được bảng này (không có quyền trong Hasura): nội dung chỉ đi vào chỉ mục, kết
--   quả tìm kiếm vẫn qua Hasura lọc theo quyền.
-- - Tệp của văn bản hạn chế không có bản chữ, vì bản chữ trần sẽ vô hiệu việc lưu mã hóa tệp (F3.7). svc-files
--   không đọc các tệp đó; trigger bên dưới chặn thêm ở CSDL cho cả lúc văn bản bật hạn chế sau khi tệp đã được
--   đọc chữ, hoặc trong lúc đang đọc.
-- - Không gắn trigger sổ kiểm toán: đây là dữ liệu dẫn xuất, tính lại được từ tệp mà băm SHA-256 đã nằm trong
--   core.files và trong sổ; ghi cả nội dung vào sổ chỉ làm sổ phình ra.
-- - Mỗi tệp đọc một lần. empty: PDF không có lớp chữ (bản scan, để dành OCR — F4.1); failed: không đọc được
--   (mật khẩu, hỏng, quá giờ), note ghi lý do.
create table core.file_texts (
  file_id       uuid primary key,
  tenant_id     uuid not null,
  status        text not null check (status in ('ok', 'empty', 'failed')),
  pages         int  check (pages >= 0),
  content       text not null default '' check (char_length(content) <= 50000),
  note          text check (char_length(note) <= 200),
  extracted_at  timestamptz not null default now(),
  foreign key (tenant_id, file_id) references core.files (tenant_id, id) on delete cascade,
  constraint file_texts_content check ((status = 'ok') = (content <> ''))
);

create index file_texts_extracted on core.file_texts (extracted_at);

-- Chữ của tệp gắn vào văn bản hạn chế: bỏ qua, không báo lỗi. Báo lỗi thì svc-files ghi lại "failed" mà dòng đó
-- cũng bị bỏ; còn bỏ qua thì tệp vẫn không vào hàng đợi nữa (PENDING_TEXTS loại tệp của văn bản hạn chế).
create function core.file_texts_skip_restricted() returns trigger
language plpgsql as $$
begin
  if exists (select 1 from office.document_files f
               join office.documents d on d.tenant_id = f.tenant_id and d.id = f.document_id
              where f.file_id = new.file_id and d.restricted) then
    return null;
  end if;
  return new;
end $$;

create trigger file_texts_skip_restricted before insert on core.file_texts
  for each row execute function core.file_texts_skip_restricted();

-- Văn bản vừa bật hạn chế, hoặc tệp vừa gắn vào văn bản hạn chế: xóa chữ đã đọc. Vòng đồng bộ tìm kiếm thấy
-- văn bản đổi (updated_at) và đẩy lại với nội dung rỗng.
create function office.drop_restricted_texts() returns trigger
language plpgsql as $$
begin
  if tg_table_name = 'documents' then
    delete from core.file_texts t using office.document_files f
     where f.document_id = new.id and t.file_id = f.file_id;
  elsif exists (select 1 from office.documents d
                 where d.tenant_id = new.tenant_id and d.id = new.document_id and d.restricted) then
    delete from core.file_texts where file_id = new.file_id;
  end if;
  return null;
end $$;

create trigger documents_drop_restricted_texts after update of restricted on office.documents
  for each row when (new.restricted and not old.restricted) execute function office.drop_restricted_texts();

create trigger document_files_drop_restricted_texts after insert on office.document_files
  for each row execute function office.drop_restricted_texts();
