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

"""Nguồn dữ liệu công khai (#424, open_data.py): đọc manifest.json của từng bản chụp, tính tuổi dữ liệu, kiểm cỡ và
SHA-256 từng tệp (băm lưu đệm tới khi tệp đổi); manifest hỏng, thiếu tệp, sai băm, tên tệp thoát ra ngoài thư mục là
``broken`` chứ không ném lỗi; chỉ các khóa trong danh sách trắng đi ra."""

import hashlib
import json
import logging
import os
from datetime import UTC, datetime

import pytest

from svc_files.open_data import OpenData

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
PDF = b"%PDF-1.7 thong tu mau\n"


def manifest(**extra) -> dict:
    return {
        "source": "cong-bao-gddt",
        "name": "Văn bản của Bộ Giáo dục và Đào tạo đăng Công báo",
        "publisher": "Văn phòng Chính phủ",
        "home_url": "https://congbao.chinhphu.vn/",
        "reuse_basis": "Khoản 2 Điều 15 Luật Sở hữu trí tuệ",
        "licence": None,
        "fetched_at": "2026-10-30T02:10:00+07:00",
        "max_age_days": 400,
        "files": [{"file": "tt-26.pdf", "url": "https://g7.example/tt-26.pdf",
                   "sha256": hashlib.sha256(PDF).hexdigest(), "bytes": len(PDF),
                   "fetched_at": "2026-10-30T02:05:00+07:00",
                   "meta": {"symbol": "26/2026/TT-BGDĐT", "page_url": "https://congbao.chinhphu.vn/van-ban/a.htm",
                            "pages": 9}}],
        **extra,
    }


def write(root, data, *, name: str = "cong-bao-gddt", content: bytes | None = PDF, raw: str | None = None):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(raw if raw is not None else json.dumps(data, ensure_ascii=False))
    if content is not None:
        (folder / "tt-26.pdf").write_bytes(content)
    return folder


def read(root, now: datetime = NOW) -> list[dict]:
    return OpenData(root, now=lambda: now)()


def test_ok_source_passes_only_allowlisted_keys(tmp_path):
    data = manifest(secret="x")
    data["files"][0]["extra"] = "y"
    data["files"][0]["meta"].update({"Bad-Key": 1, "nested": {"a": 1}, "home_url": "javascript:alert(1)"})
    write(tmp_path, data)
    (tmp_path / "README.md").write_text("không phải nguồn")
    (tmp_path / "chua-co-manifest").mkdir()
    [src] = read(tmp_path)
    assert src == {
        "source": "cong-bao-gddt", "name": data["name"], "publisher": "Văn phòng Chính phủ",
        "home_url": "https://congbao.chinhphu.vn/", "reuse_basis": data["reuse_basis"], "licence": None,
        "fetched_at": "2026-10-30T02:10:00+07:00", "age_days": 0, "max_age_days": 400, "state": "ok",
        "files": [{"file": "tt-26.pdf", "url": "https://g7.example/tt-26.pdf", "sha256": data["files"][0]["sha256"],
                   "bytes": len(PDF), "fetched_at": "2026-10-30T02:05:00+07:00",
                   "meta": {"symbol": "26/2026/TT-BGDĐT", "page_url": "https://congbao.chinhphu.vn/van-ban/a.htm",
                            "pages": 9, "home_url": None}}],
    }


def test_stale_when_older_than_max_age(tmp_path):
    write(tmp_path, manifest(max_age_days=30))       # lấy 30/10 02:10 +07:00, tức 29/10 19:10 UTC
    [src] = read(tmp_path, datetime(2026, 11, 28, 19, 10, tzinfo=UTC))
    assert (src["state"], src["age_days"]) == ("ok", 30)
    [src] = read(tmp_path, datetime(2026, 11, 29, 19, 10, tzinfo=UTC))
    assert (src["state"], src["age_days"]) == ("stale", 31)


@pytest.mark.parametrize("case", ["missing", "sha", "size", "json", "not-object", "source", "traversal", "slash",
                                  "deep", "hidden", "fetched_at", "naive", "max_age", "no-files", "bad-sha",
                                  "duplicate"])
def test_broken_never_raises(tmp_path, case, caplog):
    data = manifest()
    content: bytes | None = PDF
    raw = None
    entry = data["files"][0]
    if case == "missing":
        content = None
    elif case == "sha":
        content = PDF.replace(b"mau", b"sua")       # cùng cỡ, khác nội dung
    elif case == "size":
        content = PDF + b"x"
    elif case == "json":
        raw = "{không phải JSON"
    elif case == "not-object":
        raw = "[]"
    elif case == "source":
        data["source"] = "nguon-khac"
    elif case == "traversal":
        entry["file"] = "..passwd"
    elif case == "slash":
        entry["file"] = "../ngay-nghi-le/manifest.json"
    elif case == "deep":
        entry["file"] = "a/b/tt-26.pdf"             # chỉ một tầng thư mục con
    elif case == "hidden":
        entry["file"] = ".tt-26.pdf"
    elif case == "fetched_at":
        data["fetched_at"] = "hôm qua"
    elif case == "naive":
        data["fetched_at"] = "2026-10-30T02:10:00"
    elif case == "max_age":
        data["max_age_days"] = True
    elif case == "no-files":
        data["files"] = []
    elif case == "bad-sha":
        entry["sha256"] = entry["sha256"].upper()
    elif case == "duplicate":
        data["files"].append(dict(entry))
    write(tmp_path, data, content=content, raw=raw)
    with caplog.at_level(logging.INFO, logger="svc_files"):
        [src] = read(tmp_path)
    assert src["source"] == "cong-bao-gddt" and src["state"] == "broken"
    assert set(src) == {"source", "name", "publisher", "home_url", "reuse_basis", "licence", "fetched_at", "age_days",
                        "max_age_days", "state", "files"}
    [record] = [json.loads(r.getMessage()) for r in caplog.records if "core.open_data.changed" in r.getMessage()]
    assert record["state"] == "broken" and record["source"] == "cong-bao-gddt" and record["reason"]


def test_symlink_out_of_folder_is_broken(tmp_path):
    outside = tmp_path / "ngoai.pdf"
    outside.write_bytes(PDF)
    folder = write(tmp_path / "goc", manifest(), content=None)
    os.symlink(outside, folder / "tt-26.pdf")
    [src] = read(tmp_path / "goc")
    assert src["state"] == "broken"


def test_file_in_a_subfolder_is_ok_unless_the_subfolder_is_a_symlink(tmp_path):
    # khuôn của nguồn ngay-nghi-le: câu trích nằm ở trich/
    data = manifest()
    data["files"][0]["file"] = "trich/tt-26.pdf"
    folder = write(tmp_path / "goc", data, content=None)
    (folder / "trich").mkdir()
    (folder / "trich" / "tt-26.pdf").write_bytes(PDF)
    [src] = read(tmp_path / "goc")
    assert src["state"] == "ok" and src["files"][0]["file"] == "trich/tt-26.pdf"
    (folder / "trich").rename(tmp_path / "ngoai")
    os.symlink(tmp_path / "ngoai", folder / "trich")
    [src] = OpenData(tmp_path / "goc", now=lambda: NOW)()
    assert src["state"] == "broken"


def test_missing_or_empty_root_is_empty(tmp_path):
    assert read(tmp_path / "khong-co") == []
    assert read(tmp_path) == []


def test_sorted_by_source_and_bad_folder_names_skipped(tmp_path):
    write(tmp_path, manifest())
    write(tmp_path, manifest(source="ngay-nghi-le"), name="ngay-nghi-le")
    write(tmp_path, manifest(source="Hoa_Thuong"), name="Hoa_Thuong")
    assert [s["source"] for s in read(tmp_path)] == ["cong-bao-gddt", "ngay-nghi-le"]


def test_hash_cached_until_file_changes(tmp_path, monkeypatch):
    folder = write(tmp_path, manifest())
    calls = []
    real = hashlib.sha256

    def counting(*args):
        calls.append(1)
        return real(*args)

    monkeypatch.setattr("svc_files.open_data.hashlib.sha256", counting)
    reader = OpenData(tmp_path, now=lambda: NOW)
    assert reader()[0]["state"] == "ok" and reader()[0]["state"] == "ok"
    assert len(calls) == 1
    (folder / "tt-26.pdf").write_bytes(PDF.replace(b"mau", b"sua"))
    os.utime(folder / "tt-26.pdf", ns=(1, 1))
    assert reader()[0]["state"] == "broken" and len(calls) == 2


def test_state_change_logged_once(tmp_path, caplog):
    write(tmp_path, manifest())
    reader = OpenData(tmp_path, now=lambda: NOW)
    with caplog.at_level(logging.INFO, logger="svc_files"):
        reader()
        reader()
    events = [r for r in caplog.records if "core.open_data.changed" in r.getMessage()]
    assert len(events) == 1 and json.loads(events[0].getMessage())["state"] == "ok"
