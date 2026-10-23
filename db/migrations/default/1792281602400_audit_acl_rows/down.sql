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

-- Bỏ bộ lọc dòng danh sách được xem trong sổ (cùng lúc gỡ trường `visible` và bộ lọc của `director`, `tenant_admin`
-- khỏi core_audit_log.yaml). Dòng sổ không đổi gì ở cả hai chiều.
drop function office.audit_log_visible(core.audit_log, json);
