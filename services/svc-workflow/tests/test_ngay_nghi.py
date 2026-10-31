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

"""Lịch nghỉ chính thức của nguồn công khai B (#427): svc-workflow đọc ``seed/du-lieu-mo/ngay-nghi-le/ngay-nghi.json``
cộng với ``MOC_HOLIDAYS`` cho hạn gợi ý (config.read_holidays_file, thoi_gian.holidays_from_data)."""

from __future__ import annotations

import json
import pathlib
from datetime import date

import pytest

from svc_workflow.config import HOLIDAYS_FILE, ConfigError, Settings, read_holidays_file
from svc_workflow.thoi_gian import Holidays, holidays_from_data, next_workday
from test_app import ENV

SNAPSHOT = pathlib.Path(__file__).resolve().parents[3] / "seed" / "du-lieu-mo" / "ngay-nghi-le" / "ngay-nghi.json"


@pytest.fixture(scope="module")
def official() -> Holidays:
    got = read_holidays_file(str(SNAPSHOT))
    assert got is not None
    return got


def test_the_snapshot_covers_the_official_days_off(official):
    # Điều 112 BLLĐ + Ngày Văn hóa Việt Nam (NQ 28/2026/QH16) lặp hằng năm
    assert official.yearly == {(1, 1), (4, 30), (5, 1), (9, 2), (11, 24)}
    for d in ("2026-02-16", "2026-02-20", "2026-04-27", "2026-08-31", "2026-09-01", "2026-11-24", "2027-02-04",
              "2027-02-10", "2027-09-03"):
        assert date.fromisoformat(d) in official, d
    assert date(2026, 2, 13) not in official and date(2027, 2, 11) not in official
    assert official.workdays == {date(2026, 8, 22)}


@pytest.mark.parametrize(("due", "moved"), [
    ("2027-02-04", "2027-02-11"),   # Tết Đinh Mùi 04–10/02/2027: sang thứ Năm 11/02
    ("2026-02-16", "2026-02-23"),   # Tết Bính Ngọ 16–20/02/2026 rồi cuối tuần
    ("2026-04-26", "2026-04-28"),   # Giỗ Tổ là Chủ nhật 26/4, nghỉ bù thứ Hai 27/4
    ("2026-08-29", "2026-09-03"),   # Quốc khánh 2026 nghỉ 29/8–02/9 (thứ Hai 31/8 hoán đổi)
    ("2026-11-24", "2026-11-25"),   # Ngày Văn hóa Việt Nam
    ("2026-08-22", "2026-08-22"),   # thứ Bảy làm bù là ngày làm việc
    ("2026-08-23", "2026-08-24"),   # Chủ nhật sau đó vẫn nghỉ
])
def test_due_dates_skip_the_official_days_off(official, due, moved):
    assert next_workday(date.fromisoformat(due), official) == date.fromisoformat(moved)


def test_a_holiday_on_a_make_up_saturday_is_still_a_holiday():
    h = Holidays(dates=frozenset({date(2026, 8, 22)}), workdays=frozenset({date(2026, 8, 22)}))
    assert not h.is_workday(date(2026, 8, 22))


def test_settings_add_the_file_to_moc_holidays():
    s = Settings.from_env({**ENV, "MOC_HOLIDAYS": "01-01,2026-12-31", "MOC_HOLIDAYS_FILE": str(SNAPSHOT)})
    assert s.holidays_file == str(SNAPSHOT)
    assert date(2026, 12, 31) in s.holidays and date(2027, 2, 5) in s.holidays and (11, 24) in s.holidays.yearly
    assert date(2026, 8, 22) in s.holidays.workdays


@pytest.mark.parametrize("value", ["", "  ", "/khong-co/ngay-nghi.json"])
def test_no_file_keeps_only_moc_holidays(value):
    s = Settings.from_env({**ENV, "MOC_HOLIDAYS_FILE": value})
    assert s.holidays_file == "" and s.holidays == Settings.from_env({**ENV, "MOC_HOLIDAYS_FILE": ""}).holidays
    assert not s.holidays.dates and not s.holidays.workdays


def test_the_default_path_is_the_compose_mount():
    compose = (SNAPSHOT.parents[3] / "docker-compose.yml").read_text(encoding="utf-8")
    assert f"./seed/du-lieu-mo/ngay-nghi-le:{pathlib.PurePosixPath(HOLIDAYS_FILE).parent}:ro" in compose
    assert f"MOC_HOLIDAYS_FILE: ${{MOC_HOLIDAYS_FILE-{HOLIDAYS_FILE}}}" in compose


@pytest.mark.parametrize("data", [
    [],
    {"fixed": "01-01"},
    {"fixed": [{"date": "13-01"}]},
    {"fixed": [{"day": "01-01"}]},
    {"days_off": [{"from": "2027-02-10", "to": "2027-02-04"}]},     # ngược
    {"days_off": [{"from": "2027-01-01", "to": "2027-03-01"}]},     # dài quá 31 ngày
    {"days_off": [{"from": "2027-02-30", "to": "2027-03-01"}]},     # không có ngày này
    {"workdays": [{"date": "2026-08-24"}]},                        # thứ Hai không thể là ngày làm bù
    {"workdays": [{"date": 20260822}]},
])
def test_a_broken_file_stops_the_service(tmp_path, data):
    file = tmp_path / "ngay-nghi.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        holidays_from_data(data)
    with pytest.raises(ConfigError, match="MOC_HOLIDAYS_FILE"):
        Settings.from_env({**ENV, "MOC_HOLIDAYS_FILE": str(file)})


def test_a_file_that_is_not_json_stops_the_service(tmp_path):
    file = tmp_path / "ngay-nghi.json"
    file.write_text("{không phải JSON", encoding="utf-8")
    with pytest.raises(ConfigError, match="MOC_HOLIDAYS_FILE"):
        Settings.from_env({**ENV, "MOC_HOLIDAYS_FILE": str(file)})
