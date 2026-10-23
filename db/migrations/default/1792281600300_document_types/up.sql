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

-- Loại văn bản hành chính (NĐ 30/2020/NĐ-CP, Điều 7) và tên viết tắt dùng trong ký hiệu (Phụ lục III).
-- Công văn không có tên loại trong ký hiệu: số/viết tắt cơ quan-viết tắt đơn vị soạn thảo.
-- Thư công không có tên viết tắt và hầu như không dùng ở cấp khoa, nên chưa đưa vào.

insert into office.document_types (code, name, in_symbol) values
  ('CV',  'Công văn',          false),
  ('NQ',  'Nghị quyết',        true),
  ('QĐ',  'Quyết định',        true),
  ('CT',  'Chỉ thị',           true),
  ('QC',  'Quy chế',           true),
  ('QYĐ', 'Quy định',          true),
  ('TC',  'Thông cáo',         true),
  ('TB',  'Thông báo',         true),
  ('HD',  'Hướng dẫn',         true),
  ('CTr', 'Chương trình',      true),
  ('KH',  'Kế hoạch',          true),
  ('PA',  'Phương án',         true),
  ('ĐA',  'Đề án',             true),
  ('DA',  'Dự án',             true),
  ('BC',  'Báo cáo',           true),
  ('BB',  'Biên bản',          true),
  ('TTr', 'Tờ trình',          true),
  ('HĐ',  'Hợp đồng',          true),
  ('CĐ',  'Công điện',         true),
  ('BGN', 'Bản ghi nhớ',       true),
  ('BTT', 'Bản thỏa thuận',    true),
  ('GUQ', 'Giấy ủy quyền',     true),
  ('GM',  'Giấy mời',          true),
  ('GGT', 'Giấy giới thiệu',   true),
  ('GNP', 'Giấy nghỉ phép',    true),
  ('PG',  'Phiếu gửi',         true),
  ('PC',  'Phiếu chuyển',      true),
  ('PB',  'Phiếu báo',         true);
