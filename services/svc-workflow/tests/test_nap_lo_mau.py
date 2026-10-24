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

"""Lô văn bản đến mẫu của make demo-nap-lo (scripts/nap_lo_mau.py) qua đúng schema receiveIncoming kiểm: mọi dòng hợp
lệ trừ đúng các dòng sai cố ý, với đúng lỗi theo trường mà demo khẳng định — demo không đỏ vì dữ liệu mẫu lệch
schema."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date

import pytest

from conftest import SCHEMAS
from svc_workflow.schemas import FormSchema

INTAKE = FormSchema.load(SCHEMAS / "van-ban-den.json")
TODAY = date(2026, 10, 23)


@pytest.fixture(scope="module")
def mau():
    spec = importlib.util.spec_from_file_location("nap_lo_mau", SCHEMAS.parent / "scripts" / "nap_lo_mau.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["nap_lo_mau"] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("nap_lo_mau", None)


@pytest.mark.parametrize("today", [TODAY, date(2027, 6, 1)])
def test_sample_rows_pass_the_intake_schema_except_the_intended_ones(mau, today):
    for n, row in enumerate(mau.rows("A1B2C3"), 1):
        data = {k: v for k, v in row.items() if k != "files"}
        code, fields = mau.BAD.get(n, (None, None))
        # loại lạ: Action tra danh mục, không phải schema
        want = fields if code == "invalid" and n != mau.BAD_TYPE else {}
        assert INTAKE.errors(data, today) == want, n


def test_bad_type_is_not_in_the_catalog(mau):
    sql = (SCHEMAS.parent / "db" / "migrations" / "default" / "1792281600300_document_types" / "up.sql").read_text()
    assert "'XX'" not in sql
    assert mau.rows()[mau.BAD_TYPE - 1]["type_code"] == "XX"
