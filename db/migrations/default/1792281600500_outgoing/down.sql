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

drop view office.issued_documents;
drop function office.number_outgoing(uuid, text, json);
alter table office.documents
  drop constraint documents_body_only_out,
  drop constraint documents_body_length,
  drop column body;
alter table core.tenants
  drop column head_title,
  drop column place_name,
  drop column parent_name;
