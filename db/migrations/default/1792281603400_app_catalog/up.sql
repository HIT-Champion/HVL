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

-- Danh mục ứng dụng (trang /ung-dung của Văn phòng điện tử, docs/them-ung-dung.md mục 1): ứng dụng cắm bằng manifest
-- đã cài, đã gỡ — khung nhìn HẸP trên core.apps (migration 1792281603200). core.apps vẫn không vào GraphQL: cột
-- manifest (jsonb) mang image, cổng container, healthcheck, biến môi trường, cổng webhook; schema_name là chi tiết CSDL
-- của ứng dụng. Ở đây chỉ có 9 cột hiển thị được, mô tả lấy từ manifest (lõi đã kiểm lúc cài: ≤ 500 ký tự, không ký
-- tự điều khiển). Dữ liệu toàn hệ thống, mọi đơn vị cùng một danh sách: không có cột đơn vị nào.
-- Quyền (core_app_catalog.yaml): người dùng đọc ứng dụng đang cài; lãnh đạo, quản trị đơn vị đọc thêm băm manifest và
-- ứng dụng đã gỡ. Không vai trò nào ghi. Ứng dụng có sẵn trong lõi (Văn phòng điện tử, Không gian cá nhân) không cài
-- bằng manifest nên không có ở đây — trang khai chúng trong apps/office/app/utils/apps.ts.
create view core.app_catalog as
select a.name,
       a.title,
       nullif(btrim(a.manifest ->> 'description'), '') as description,
       a.path,
       a.version,
       a.installed_at,
       a.updated_at,
       a.removed_at,
       a.manifest_sha256
  from core.apps a;

comment on view core.app_catalog is 'Danh mục ứng dụng cắm vào lõi bằng manifest: tên, mô tả, đường, phiên bản, lúc '
  'cài, lúc gỡ, SHA-256 tệp app.yaml lúc cài; không manifest, cổng, biến môi trường';
