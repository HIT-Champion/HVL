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

"""Trợ lý hỏi đáp trên kho văn bản (F4.2): tìm đoạn liên quan trong các văn bản người hỏi được xem, trích nguyên văn.

Chỉ mục và truy xuất:

- ``chunks``: thuần, không I/O — văn bản (chữ theo trang của F2.7) → các đoạn ≤ 1 200 ký tự mang số trang và thuộc
  tính quyền; văn bản hạn chế, văn bản đến đã hủy, văn bản đi chưa phát hành không có đoạn nào.
- ``meili``: chỉ mục Meilisearch ``chunks`` (một tài liệu/đoạn), embedder ``userProvided`` đặt tên theo mô hình.
- ``index``: vòng nền đồng bộ đoạn từ Hasura sang Meilisearch, rồi nhúng các đoạn chưa có véc-tơ.
- ``scope``: điều kiện lọc trước theo vai trò, viết đúng như ``office.document_visible``.
- ``retrieve``: lọc trước trong Meilisearch rồi hậu kiểm bằng Hasura với token người hỏi — quy tắc quyền chỉ nằm ở
  CSDL; lọc trước chỉ quyết độ phủ, hậu kiểm quyết an toàn.

Gói này không nhập gì lúc khởi tạo.
"""
