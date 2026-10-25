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

"""Kết nối rảnh giữa APISIX và dịch vụ phía sau: chỉ APISIX được đóng. Dịch vụ đóng trước thì yêu cầu gửi đúng lúc
đó trên kết nối cũ nhận EOF/RST, một node không thử lại nên cổng trả 502 (svc-files: #138, Hasura: #173).
Kiểm chữ (không có PyYAML, không cần Docker). Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APISIX_IDLE = 60    # giây APISIX 3.18 giữ kết nối rảnh tới upstream khi upstream không đặt keepalive_pool
WARP_SWEEP = 30     # Hasura (Warp) quét kết nối mỗi 30 giây, kết nối rảnh bị đóng sớm nhất sau một nhịp


def upstream(name: str) -> str:
    """Khối của một upstream trong mục upstreams: của apisix.yaml (route cùng id ở mục routes: không tính)."""
    text = (ROOT / "platform" / "apisix" / "apisix.yaml").read_text(encoding="utf-8")
    section = re.search(r"^upstreams:\n(.*?)^\S", text, re.M | re.S)
    assert section, "apisix.yaml thiếu mục upstreams:"
    block = re.search(rf"^  - id: {re.escape(name)}\n(.*?)(?=^  - id: |\Z)", section.group(1), re.M | re.S)
    assert block, f"không có upstream {name}"
    return block.group(1)


class IdleCloseTest(unittest.TestCase):
    def test_hasura_pool_closes_before_warp(self) -> None:
        m = re.search(r"^    keepalive_pool: \{size: \d+, idle_timeout: (\d+), requests: \d+\}$", upstream("hasura"),
                      re.M)
        self.assertIsNotNone(m, "upstream hasura thiếu keepalive_pool")
        assert m
        self.assertLess(int(m.group(1)), WARP_SWEEP)

    def test_svc_files_keeps_connections_longer_than_apisix(self) -> None:
        self.assertNotIn("keepalive_pool", upstream("svc-files"))
        m = re.search(r'"--timeout-keep-alive", "(\d+)"',
                      (ROOT / "services" / "svc-files" / "Dockerfile").read_text(encoding="utf-8"))
        self.assertIsNotNone(m, "svc-files: uvicorn thiếu --timeout-keep-alive")
        assert m
        self.assertGreater(int(m.group(1)), APISIX_IDLE)


if __name__ == "__main__":
    unittest.main()
