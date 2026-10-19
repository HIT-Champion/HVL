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

-- Neo hash đầu chuỗi và màn xem sổ kiểm toán (F2.12). Mô tả: docs/mo-hinh-du-lieu.md §1.
--
-- svc-files định kỳ chép đầu chuỗi (last_id, last_hash) ra bucket lạnh có khóa ghi (S3 Object Lock, chế độ
-- COMPLIANCE): không ai xóa, sửa hay rút ngắn hạn giữ được, kể cả quản trị kho. core.audit_anchors chỉ là bản
-- tra cứu trong CSDL; khi kiểm, lệnh `moc audit verify` đọc mốc từ bucket, không tin bảng này.

-- Ghi lại cùng một mốc (vòng neo chạy lại sau khi ghi bucket xong mà chưa ghi được CSDL) không thành hai dòng.
-- Ràng buộc chứ không chỉ chỉ mục: Hasura cần tên ràng buộc cho on_conflict.
alter table core.audit_anchors add constraint audit_anchors_once unique (audit_id, location);

-- Màn xem sổ cho lãnh đạo, quản trị đơn vị: cột nào đổi, nhưng chỉ hiện giá trị của các cột không chứa nội
-- dung (trạng thái, số, ngày, cờ, mã người, mã văn bản). Trích yếu, nội dung, tên tệp, ý kiến… hiện null: lãnh đạo
-- không đọc được văn bản hạn chế (office.document_visible) thì sổ cũng không được lộ nội dung đó. Hash tệp và
-- hash văn bản cũng null: có hash là tra được văn bản ở cổng xác thực công khai, kể cả văn bản hạn chế.
-- Giá trị đầy đủ chỉ kiểm trên máy chủ, bằng lệnh `moc audit verify`.
create function core.audit_overview(r core.audit_log) returns jsonb
language sql stable
as $$
  select case when jsonb_typeof(r.diff) <> 'object' then '{}'::jsonb else (
    select coalesce(jsonb_object_agg(k, case when k = any (array[
             'status', 'urgency', 'direction', 'register_number', 'registered_at', 'due_on', 'issued_on',
             'restricted', 'is_public', 'role', 'enabled', 'department_id', 'user_id', 'signer_id',
             'document_id', 'file_id'
           ]) then r.diff -> k end), '{}'::jsonb)
      from jsonb_object_keys(r.diff) as k
  ) end
$$;
