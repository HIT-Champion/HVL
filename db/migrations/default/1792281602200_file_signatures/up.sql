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

-- Ký số văn bản đi (F4.5) — CHỈ MINH HỌA, không có giá trị pháp lý như chữ ký số công cộng. svc-files ký bản phát hành
-- theo chuẩn PAdES B-B bằng khóa riêng của đơn vị nằm trong Transit của két OpenBao (khóa không rời két), chứng thư do
-- CA nội bộ trong két cấp, rồi mới băm: content_sha256, sổ kiểm toán, bản liên thông đều là bản đã ký. Mô tả:
-- docs/mo-hinh-du-lieu.md §1 (bảng), §2.5 (cột chữ ký của khung nhìn xác thực), §3 (quyền), §4.3 (/internal/issue);
-- quyết định kiến trúc: docs/architecture.md QĐ-007.
--
-- - Một dòng cho mỗi tệp đã ký (bản phát hành), ghi trong cùng mutation với dòng core.files: Hasura chạy hai trường
--   gốc trong một giao dịch, ghi chữ ký lỗi thì tệp cũng không được lưu. Phát hành không ký (văn bản hạn chế, két chưa
--   có PKI, ký lỗi, văn bản phát hành trước F4.5) thì không có dòng nào.
-- - Không lưu chứng thư (đã nằm trong PDF), chỉ vân tay SHA-256 của nó. Không thêm cột vào core.files: bảng chung cho
--   mọi tệp.
-- - Khóa ngoại kèm thuê ước: không gắn được chữ ký vào tệp của đơn vị khác; xóa tệp thì chữ ký mất theo.
-- - Trigger sổ kiểm toán (entity_id = file_id). Chưa thêm nhánh vào core.audit_overview (cắt giảm của F4.5): màn Sổ
--   kiểm toán thấy tên các cột của dòng này, giá trị chỉ có ở file_id (danh sách chung).

create table core.file_signatures (          -- chữ ký số PAdES của bản phát hành (F4.5, chỉ minh họa)
  file_id      uuid primary key,
  tenant_id    uuid not null,
  level        text not null default 'PAdES-B-B' check (level in ('PAdES-B-B')),
  signed_at    timestamptz not null,           -- giờ ký tự khai trong chữ ký (không có dấu thời gian tin cậy)
  signer_name  text not null check (char_length(signer_name) between 1 and 64),   -- CN chứng thư lá
  ca_name      text not null check (char_length(ca_name) between 1 and 64),       -- CN của CA
  serial       text not null check (serial ~ '^[0-9a-f]{2,64}$'),                 -- số sê-ri chứng thư lá, hex thường
  cert_sha256  bytea not null check (octet_length(cert_sha256) = 32),             -- vân tay SHA-256 (DER) chứng thư lá
  not_after    timestamptz not null,           -- hạn của chứng thư lá
  key_name     text not null check (key_name ~ '^moc-ky-so-[0-9a-f-]{36}$'),       -- khóa transit moc-ky-so-<đơn vị>
  key_version  int not null check (key_version > 0),
  created_at   timestamptz not null default now(),
  foreign key (tenant_id, file_id) references core.files (tenant_id, id) on delete cascade
);

create trigger audit after insert or update or delete on core.file_signatures
  for each row execute function core.audit('file_id');

-- ---------------------------------------------------------------------------
-- Cổng xác thực: thêm năm cột chữ ký ở cuối khung nhìn (create or replace chỉ thêm được cột ở cuối). Còn lại chép
-- nguyên migration 1792281601600. Văn bản phát hành không ký (trước F4.5, văn bản hạn chế) thì năm cột là null.
--
-- Chữ ký tìm theo băm, không qua office.document_files: nộp lưu (F3.8, office.archive_case_file) xóa dòng gắn tệp của
-- văn bản nhưng giữ dòng core.files (chuyển sang kho lạnh) và vì thế giữ dòng chữ ký — văn bản đã nộp lưu vẫn hiện
-- chữ ký. content_sha256 là băm của chính bản đã ký, nên tệp cùng đơn vị có đúng băm ấy và có dòng chữ ký là bản phát
-- hành; tệp chép lại cùng nội dung (tải lên lại, bản liên thông ở đơn vị nhận) không có dòng chữ ký. limit 1: khung
-- nhìn luôn một dòng mỗi văn bản. Chỉ mục (tenant_id, sha256) để lần tra của cổng không quét cả bảng tệp.
-- ---------------------------------------------------------------------------

create index files_tenant_sha256 on core.files (tenant_id, sha256);

-- cổng xác thực cũng không đọc trích yếu của văn bản hạn chế, kể cả dòng cũ chưa sửa
create or replace view office.issued_documents as
select d.verify_code,
       d.content_sha256,
       d.symbol,
       d.issued_on,
       d.type_code,
       dt.name   as type_name,
       t.name    as issuer_name,
       t.parent_name,
       case when d.is_public and not d.restricted then d.summary end as summary,
       d.status,
       s.level   as signature_level,
       s.signed_at,
       s.signer_name,
       s.ca_name as signer_ca,
       s.serial  as certificate_serial
  from office.documents d
  join core.tenants t on t.id = d.tenant_id
  join office.document_types dt on dt.code = d.type_code
  left join lateral (
    select fs.level, fs.signed_at, fs.signer_name, fs.ca_name, fs.serial
      from core.files f
      join core.file_signatures fs on fs.tenant_id = f.tenant_id and fs.file_id = f.id
     where f.tenant_id = d.tenant_id and f.sha256 = d.content_sha256
     order by fs.created_at, fs.file_id
     limit 1
  ) s on true
 where d.direction = 'out' and d.status in ('issued', 'archived');
