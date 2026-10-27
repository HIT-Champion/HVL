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

-- Thôi ghi office.document.received. Sự kiện đã ghi giữ nguyên trong dòng thời gian, core.app_events (đã gửi cho ứng
-- dụng); giao diện bỏ qua kind này nên không hiện hai bước tiếp nhận.
drop trigger documents_received on office.documents;
drop function office.document_received();
