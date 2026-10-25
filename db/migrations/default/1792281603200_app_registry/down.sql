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

-- Gỡ cơ chế cắm ứng dụng. Schema và vai trò CSDL (moc_appdb_*) của các ứng dụng đã cài không bị đụng tới (gỡ ứng dụng
-- không xóa dữ liệu); dòng đã ghi vào core.audit_log vẫn giữ.
drop schema moc_app cascade;
drop trigger app_events on office.document_events;
drop function core.app_events_publish();
drop table core.app_events;
drop table core.app_migrations;
drop table core.apps;
