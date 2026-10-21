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

-- Trợ lý hỏi đáp trên kho văn bản (F4.2): người dùng hỏi bằng câu tự nhiên, svc-files tìm trong chỉ mục đoạn
-- Meilisearch `chunks` (chỉ đoạn của văn bản người hỏi được xem, văn bản hạn chế không bao giờ vào chỉ mục), trả câu
-- trích nguyên văn kèm số ký hiệu và trang; bật profile ai thì Qwen3 viết thêm câu trả lời có trích dẫn. Mô tả:
-- docs/mo-hinh-du-lieu.md §1 (page_starts), §3 (tác tử moc-assistant), §4.3 (POST /api/documents/ask), §5 (sự kiện
-- assistant.answered).
--
-- - Không bảng mới: câu hỏi, câu trả lời không lưu ở đâu cả (mỗi câu hỏi độc lập, giao diện chỉ giữ trong bộ nhớ
--   trang). Chỉ mục đoạn là dữ liệu dẫn xuất, dựng lại được từ core.file_texts và office.documents.
-- - Trích dẫn cần số trang, mà core.file_texts.content (F2.7) nối chữ mọi trang nên mất ranh giới trang: thêm cột
--   page_starts — vị trí ký tự đầu mỗi trang trong content. Trang trống mang cùng vị trí với trang sau; trang bắt đầu
--   sau điểm cắt 50 000 ký tự thì không có trong mảng.
-- - Mỗi câu trả lời là một dòng sổ `assistant.answered` của tác tử `moc-assistant` (vai trò Hasura agent, như F4.1),
--   chỉ có siêu dữ liệu: không câu hỏi, câu trả lời, số ký hiệu, đoạn trích.

alter table core.file_texts add column page_starts int[];

-- null: tệp không đọc được chữ (empty, failed) hoặc dòng đọc trước F4.2 — svc-files coi cả nội dung là một "trang"
-- không số. Mảng một chiều, không phần tử null (so sánh với null ra null, check sẽ cho qua).
alter table core.file_texts add constraint file_texts_page_starts check (page_starts is null or (status = 'ok'
  and cardinality(page_starts) between 1 and 200 and page_starts[1] = 0
  and page_starts[cardinality(page_starts)] <= char_length(content)
  and array_ndims(page_starts) = 1 and array_position(page_starts, null) is null));

-- dữ liệu dẫn xuất: xóa để vòng nền F2.7 đọc lại, lần này có ranh giới trang. Chữ đọc lại giống hệt; mỗi PDF đọc lại
-- một lần (vài phút với dữ liệu demo). Bảng không gắn sổ kiểm toán nên lệnh xóa không ghi sổ.
delete from core.file_texts where status = 'ok';

-- ---------------------------------------------------------------------------
-- Màn Sổ kiểm toán: dòng `assistant.answered` của trợ lý hiện chế độ (extract | generate), nguồn câu trả lời, số đoạn
-- tìm được, số nguồn được trích, có tìm theo nghĩa không, tên mô hình sinh và mô hình nhúng, thời gian, mã cảnh báo.
-- status, user_id (người hỏi) đã có trong danh sách chung. `documents` (id các văn bản nguồn) cố ý không hiện: chỉ
-- vai trò service đọc được diff. Khóa khác cố tình nhét vào diff (câu hỏi, câu trả lời…) vẫn chỉ có tên. Còn lại như
-- migration 1792281601900, giữ nguyên các khóa của F3.12 và F4.1.
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
           then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;
