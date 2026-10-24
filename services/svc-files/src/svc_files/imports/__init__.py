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

"""Lô nạp khối lớn (bulk import) — khung chung cho lõi, hiện có một loại: văn bản đến (``incoming``).

Người dùng gửi một tệp NDJSON hoặc CSV (kèm zip tệp đính kèm tùy chọn) qua ``POST /api/imports/{kind}``; svc-files
kiểm cả tệp ngay trong yêu cầu, ghi lô + mọi dòng + một dòng sổ kiểm toán trong một mutation (core.import_jobs,
core.import_rows — migration 1792281602800), trả 202. Vòng nền xử lý từng mẻ dòng: mỗi dòng đi đúng đường của thao
tác lẻ tương ứng, nên lô không có đường ghi thứ hai.

- ``parse.py``: đọc NDJSON/CSV theo đặc tả cột của loại lô; lỗi một dòng thành dòng ``failed``, không hỏng cả tệp.
- ``spool.py``: zip tệp đính kèm giữ tạm (tmpfs) tới khi lô xong; kiểm, đọc từng mục có trần.
- ``store.py``: câu GraphQL trên hai bảng, vai trò ``service`` của đúng đơn vị lô.
- ``runner.py``: vòng nền ``Importer`` và handler của từng loại (``IncomingHandler``), phân loại lỗi tạm / vĩnh viễn.
- ``api.py``: route tạo lô, xem lô, xem dòng.

Thêm loại lô: migration mở rộng check ``kind`` của core.import_jobs; một handler mới (``kind``, vai trò được tạo lô,
đặc tả cột, ``process``) đăng ký trong app.py; giá trị mới trong ``Kind`` của api.py.
"""
