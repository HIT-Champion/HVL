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

-- #398 (F2.9): văn bản đi soạn bằng tiếng Anh. Ngôn ngữ của văn bản quyết định phần cố định mà svc-files dựng
-- (quốc hiệu, tiêu ngữ, số, ngày, kính gửi, nơi nhận, khối xác thực, tên loại theo mã); thể thức vẫn của NĐ 30/2020.
-- Chữ người soạn gõ không dịch. Văn bản cũ, văn bản đến là 'vi'. Người soạn đổi được như các cột khác của dự thảo
-- (quyền update của staff: draft, returned); đã duyệt thì thôi, bản phát hành dựng đúng ngôn ngữ lúc duyệt.
alter table office.documents
  add column language text not null default 'vi',
  add constraint documents_language check (language in ('vi', 'en'));
