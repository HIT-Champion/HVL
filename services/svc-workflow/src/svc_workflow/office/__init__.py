# Copyright 2026 Signet Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Phần Văn phòng điện tử của svc-workflow (ứng dụng đầu tiên trên lõi, docs/architecture.md §4.3).

- ``queries``: câu GraphQL trên schema ``office``.

Các mô-đun nghiệp vụ của Văn phòng (``workflow``, ``forms``, ``sla``, ``dispatch``, ``advisor``, ``suggest``, ``ot``,
``files``) còn ở gói cha; dời vào đây là bước 4 của §4.7. Gói này không nhập gì lúc khởi tạo.
"""
