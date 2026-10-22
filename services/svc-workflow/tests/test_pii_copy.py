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

"""svc_workflow/pii.py là bản chép y hệt byte của svc_files/pii.py (F4.4): hai dịch vụ là hai gói, hai image riêng,
chỉ dùng chung một tệp nên chép thay vì dựng gói chung. Bộ test đầy đủ nằm ở svc-files (test_pii*.py); ở đây chỉ giữ
hai bản không lệch nhau và CLI của bản này chạy được.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import sys

import pytest

from svc_workflow import pii

ORIGINAL = pathlib.Path(__file__).resolve().parents[2] / "svc-files" / "src" / "svc_files" / "pii.py"


def test_copy_is_byte_identical_to_svc_files():
    if not ORIGINAL.is_file():
        pytest.skip("không có services/svc-files (chạy trong image svc-workflow)")
    assert pathlib.Path(pii.__file__).read_bytes() == ORIGINAL.read_bytes(), (
        "svc_workflow/pii.py lệch svc_files/pii.py — sửa ở svc-files rồi chép lại y hệt")


def test_cli_count_runs():
    # giá trị giả lập; count chỉ in số đếm, không in giá trị
    text = "Đơn (giả lập): CCCD 001205000017, ĐT 0912 345 678, email nguyenvanb@example.com\n"
    src = os.path.dirname(os.path.dirname(pii.__file__))
    env = {**os.environ, "PYTHONPATH": src, "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, "-m", "svc_workflow.pii", "count"], input=text.encode(),
                          capture_output=True, env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {"chars": len(text), "total": 3, "spans": {"cccd": 1, "phone": 1, "email": 1}}
    assert b"0912" not in done.stdout and b"@" not in done.stdout


def test_log_filter_masks_this_service_records():
    record = logging.LogRecord("svc_workflow", logging.ERROR, __file__, 1, "office.action.failed %s",
                               ("CCCD 001205000017",), None)
    assert pii.PiiFilter().filter(record) and record.getMessage() == "office.action.failed CCCD [CCCD]"
