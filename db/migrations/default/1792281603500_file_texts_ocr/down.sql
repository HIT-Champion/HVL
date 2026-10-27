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

-- Không đổi cấu trúc nào để trả lại. Chữ OCR đã ghi (`ok`, note "ocr …") vẫn giữ: cùng dạng với lớp chữ PDF, bản cũ
-- của svc-files tìm và trích được như thường. Dòng đã xóa ở up.sql không cần khôi phục: tệp chưa có dòng nào thì bản
-- cũ tự đọc lại, ghi `empty` như trước.
select 1;
