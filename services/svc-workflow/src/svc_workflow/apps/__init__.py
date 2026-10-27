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

"""Quy trình là dịch vụ của lõi (#301): ứng dụng cắm bằng manifest khai BPMN và form, chạy trên Flowable của lõi.

- ``bundle.py``, ``bpmn.py``, ``forms.py``: kiểm gói quy trình theo danh sách trắng trước khi triển khai — BPMN của
  ứng dụng chạy trong động cơ của lõi, nên không có script, lớp Java, biểu thức gọi hàm nào lọt vào;
- ``deploy.py``: lệnh ``moc app install | remove`` gọi trong container (``python -m svc_workflow.apps.deploy``);
- ``auth.py``, ``api.py``: API ``/api/workflow/{app}/…`` qua APISIX — bắt đầu quy trình, xem hộp việc, hoàn thành
  việc, chỉ với token của đúng client ``app-<tên>``.

Việc của ứng dụng không lọt vào hộp việc của Văn phòng điện tử: ``workflow.my_tasks`` chỉ trả việc của quy trình Office.
"""
