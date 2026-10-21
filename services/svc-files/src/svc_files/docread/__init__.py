# Copyright 2026 Mộc Team
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

"""Đọc văn bản đến (F4.1): tác tử ``moc-doc-reader`` đọc tệp văn thư vừa tải lên, gợi ý thông tin tiếp nhận.

- ``layout``: chữ của trang (lớp chữ PDF theo bố cục, hoặc TSV của Tesseract) → các dòng có vị trí trên trang.
- ``rules``: quy tắc thuần Python, không I/O: dòng → số ký hiệu, ngày ban hành, cơ quan ban hành, loại, độ khẩn,
  trích yếu, mỗi trường kèm độ tin cậy. Mô hình ngôn ngữ (nếu bật) chỉ viết trích yếu, không quyết trường nào khác.

Gói này không nhập gì lúc khởi tạo: ``pdflayout.py``, ``ocr.py`` chạy thành tiến trình con bằng ``python -I``.
"""
