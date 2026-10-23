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

"""Văn bản mẫu của make seed (scripts/seed_documents.py) nhất quán với seed/users.csv: người xử lý thuộc phòng chủ
trì, người soạn có tổ trưởng cùng phòng duyệt, văn bản trả lời có văn bản đến tương ứng; tài khoản giám khảo có sẵn việc
trong hộp việc. Không cần Docker, không đọc .env. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import importlib
import pathlib
import sys
import types
import unittest
from typing import Any

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent

seed: Any = None
_saved: Any = None


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp: thay bằng bản giả chỉ có những gì seed_documents.py nhập."""
    global seed, _saved
    _saved = {name: sys.modules.pop(name, None) for name in ("moc_env", "seed_documents")}
    stub = types.ModuleType("moc_env")

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng, Docker")

    stub.Session = type("Session", (), {"__init__": no_network})
    stub.compose = no_network
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    seed = importlib.import_module("seed_documents")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


def users() -> dict[str, list[str]]:
    """seed/users.csv: username → [username, họ, tên, vai trò, tenant, phòng]."""
    return {line.split(",")[0]: line.split(",") for line in (ROOT / "seed" / "users.csv").read_text(
        encoding="utf-8").splitlines() if line and not line.startswith("#")}


class SeedSamplesTest(unittest.TestCase):
    def test_handlers_belong_to_lead_unit(self) -> None:
        people = users()
        for s in [*seed.CNTT, *seed.KT]:
            if s.stop in ("assigned", "done"):
                self.assertEqual(people[s.handler][5], seed.DEPT[s.lead],
                                 f"{s.symbol}: {s.handler} không thuộc {s.lead}")
                self.assertEqual(people[s.handler][3], "staff", s.symbol)

    def test_drafters_have_manager_of_same_unit(self) -> None:
        people = users()
        for d in seed.OUT_CNTT:
            manager = seed.MANAGER[d.drafter]
            self.assertEqual(people[manager][3], "manager", d.summary)
            self.assertEqual(people[manager][5], people[d.drafter][5], f"{d.summary}: {manager} khác phòng {d.drafter}")

    def test_keys_unique_and_replies_resolve(self) -> None:
        symbols = [s.symbol for s in [*seed.CNTT, *seed.KT]]
        self.assertEqual(len(symbols), len(set(symbols)))
        # seed bỏ qua văn bản đi đã có theo trích yếu: trùng thì văn bản sau không bao giờ được tạo
        summaries = [d.summary for d in seed.OUT_CNTT]
        self.assertEqual(len(summaries), len(set(summaries)))
        for d in seed.OUT_CNTT:
            if d.reply_to:
                self.assertIn(d.reply_to, symbols, d.summary)

    def test_judge_inbox_not_empty(self) -> None:
        """README hứa giamkhao đăng nhập là thấy việc: một văn bản đến giao xử lý, một dự thảo bị trả lại chờ sửa."""
        handle = [s for s in seed.CNTT if s.handler == "giamkhao" and s.stop == "assigned"]
        redraft = [d for d in seed.OUT_CNTT if d.drafter == "giamkhao" and d.stop == "returned"]
        self.assertTrue(handle and redraft)


if __name__ == "__main__":
    unittest.main()
