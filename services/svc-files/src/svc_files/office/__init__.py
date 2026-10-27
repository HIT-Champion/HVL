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

"""Phần của Văn phòng điện tử trong svc-files — ứng dụng đầu tiên chạy chung tiến trình với lõi (docs/architecture.md
§4.3, §4.7).

- ``hasura.py``: ``OfficeHasura`` — máy khách Hasura chung (``svc_files.hasura``) cộng các câu GraphQL chỉ Văn phòng
  dùng: dựng văn bản đi, sổ đăng ký, cổng xác thực, liên thông, phòng đọc, văn bản đích của gợi ý giao việc.

Lõi và mô-đun dáng nghiệp vụ không nhập gì từ gói này. Gói này không nhập gì lúc khởi tạo.
"""
