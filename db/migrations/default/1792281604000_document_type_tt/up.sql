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

-- #424: thông tư của Bộ GD&ĐT nạp từ nguồn dữ liệu công khai (seed/du-lieu-mo/cong-bao-gddt) là văn bản đến loại
-- "Thông tư": văn bản quy phạm pháp luật, không có trong danh mục văn bản hành chính của NĐ 30. Danh mục dùng chung
-- cho cả văn bản đi, nhưng đơn vị trong trường không ban hành thông tư: loại này để vào sổ văn bản đến. in_symbol như
-- các loại có tên viết tắt trong ký hiệu (…/TT-BGDĐT).
insert into office.document_types (code, name, in_symbol) values ('TT', 'Thông tư', true)
on conflict (code) do nothing;
