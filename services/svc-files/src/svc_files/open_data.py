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

"""Nguồn dữ liệu công khai (#424): nguồn gốc các bản chụp ``seed/du-lieu-mo/<mã nguồn>/`` cho ``GET /api/status``.

Bản cài không gọi nguồn ngoài lúc chạy: lệnh ``moc du-lieu-mo lay`` (scripts/du_lieu_mo.py) lấy bản chụp ở máy của
đội, đổi bản chụp đi qua PR. svc-files đọc thư mục đó qua mount chỉ đọc ``MOC_OPEN_DATA_DIR`` (mặc định
``/srv/du-lieu-mo``, rỗng: tắt), mỗi thư mục con có ``manifest.json`` là một nguồn. Mỗi nguồn trả nguồn gốc (tên, nơi
công bố, trang gốc, căn cứ dùng lại, ngày lấy, URL và SHA-256 từng tệp) cùng tuổi dữ liệu và trạng thái:
- ``broken``: manifest không đọc được hay sai khuôn, thiếu tệp, cỡ hoặc SHA-256 không khớp;
- ``stale``: tuổi (ngày, tính từ ``fetched_at``) quá ``max_age_days``;
- ``ok``: còn lại.

Trang không cần đăng nhập nên chỉ các khóa trong danh sách trắng đi ra; chuỗi cắt ngắn, URL chỉ nhận ``http(s)://``.
``meta`` tùy nguồn: chỉ giá trị đơn (chuỗi, số, đúng/sai), tối đa ``META_MAX`` khóa. Tên tệp là tên trơn trong thư
mục của nguồn hoặc trong một thư mục con (vd ``trich/a.txt`` của nguồn ``ngay-nghi-le``); không ``..``, không phần nào
bắt đầu bằng ``.``, không theo liên kết tượng trưng (cả thư mục con). SHA-256 từng tệp lưu đệm
theo (``st_ino``, ``st_mtime_ns``, ``st_size``): lượt gom sau không băm lại tệp chưa đổi. Lỗi chỉ vào nhật ký
(``core.open_data.changed``, ghi khi trạng thái một nguồn đổi), không bao giờ ném ra bảng trạng thái.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import pathlib
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger("svc_files")

SOURCE_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
FILE_RE = re.compile(r"(?:[0-9A-Za-z][0-9A-Za-z._-]{0,127}/)?[0-9A-Za-z][0-9A-Za-z._-]{0,127}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
META_KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
URL_RE = re.compile(r"https?://[^\s\x00-\x1f\x7f]{1,500}")
TEXT_MAX = 1000             # tên, nơi công bố, căn cứ dùng lại, giá trị chuỗi của meta
MANIFEST_MAX = 1024 * 1024  # manifest lớn hơn thì coi là hỏng, không đọc
SOURCES_MAX = 20
FILES_MAX = 100
META_MAX = 20

_TEXT = ("name", "publisher", "reuse_basis", "licence")


class Broken(Exception):
    """Manifest hay tệp của một nguồn không dùng được; thông điệp chỉ vào nhật ký."""


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()
    return value[:TEXT_MAX] or None


def _url(value: Any) -> str | None:
    return value if isinstance(value, str) and URL_RE.fullmatch(value) else None


def _when(value: Any) -> datetime:
    """Thời điểm ISO 8601 có múi giờ, vd 2026-10-30T03:10:00+07:00."""
    if not isinstance(value, str):
        raise Broken("fetched_at không phải chuỗi")
    try:
        at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise Broken(f"fetched_at sai: {value[:40]!r}") from exc
    if at.tzinfo is None:
        raise Broken("fetched_at thiếu múi giờ")
    return at


def _meta(value: Any) -> dict[str, str | int | float | bool | None]:
    out: dict[str, str | int | float | bool | None] = {}
    if not isinstance(value, dict):
        return out
    for key, item in value.items():
        if len(out) >= META_MAX:
            break
        if not isinstance(key, str) or not META_KEY_RE.fullmatch(key):
            continue
        if isinstance(item, str):
            out[key] = _url(item) if key.endswith("_url") else _text(item)
        elif item is None or isinstance(item, bool | int) or (isinstance(item, float) and math.isfinite(item)):
            out[key] = item
    return out


class OpenData:
    """Đọc ``<root>/*/manifest.json``; gọi được (đồng bộ, trong luồng riêng) → danh sách ``open_data``."""

    def __init__(self, root: str | pathlib.Path, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.root = pathlib.Path(root)
        self._now = now
        self._hashes: dict[str, tuple[tuple[int, int, int], str]] = {}
        self._last: dict[str, str] = {}
        self._lock = threading.Lock()

    def __call__(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._collect()

    def _collect(self) -> list[dict[str, Any]]:
        try:
            if self.root.is_symlink() or not self.root.is_dir():
                return []
            dirs = sorted(p for p in self.root.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError as exc:
            self._changed("*", "broken", f"{type(exc).__name__}: {exc}")
            return []
        out = []
        for path in dirs:
            if not SOURCE_RE.fullmatch(path.name) or not (path / "manifest.json").exists():
                continue        # thư mục khác (không phải nguồn): bỏ qua
            if len(out) >= SOURCES_MAX:
                self._changed("*", "broken", f"quá {SOURCES_MAX} nguồn, bỏ phần sau")
                break
            out.append(self._source(path))
        return out

    def _changed(self, source: str, state: str, reason: str | None = None) -> None:
        if self._last.get(source) == state:
            return
        self._last[source] = state
        record: dict[str, Any] = {"event": "core.open_data.changed", "source": source, "state": state}
        if reason:
            record["reason"] = reason
        log.log(logging.INFO if state == "ok" else logging.WARNING, json.dumps(record, ensure_ascii=False))

    def _source(self, path: pathlib.Path) -> dict[str, Any]:
        item: dict[str, Any] = {"source": path.name, **dict.fromkeys(_TEXT), "home_url": None, "fetched_at": None,
                                "age_days": None, "max_age_days": None, "state": "broken", "files": []}
        try:
            manifest = self._manifest(path)
            item.update({key: _text(manifest.get(key)) for key in _TEXT})
            item["home_url"] = _url(manifest.get("home_url"))
            fetched = _when(manifest.get("fetched_at"))
            item["fetched_at"] = fetched.isoformat(timespec="seconds")
            max_age = manifest.get("max_age_days")
            if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 1:
                raise Broken("max_age_days phải là số nguyên ≥ 1")
            item["max_age_days"] = max_age
            item["age_days"] = max(0, (self._now() - fetched).days)
            item["files"], problem = self._files(path, manifest.get("files"))
            if problem:
                raise Broken(problem)
        except Broken as exc:
            self._changed(path.name, "broken", str(exc))
            return item
        item["state"] = "stale" if item["age_days"] > max_age else "ok"
        self._changed(path.name, item["state"])
        return item

    def _manifest(self, path: pathlib.Path) -> dict[str, Any]:
        file = path / "manifest.json"
        try:
            if file.is_symlink() or file.stat().st_size > MANIFEST_MAX:
                raise Broken("manifest.json là liên kết tượng trưng hoặc quá lớn")
            data = json.loads(file.read_bytes())
        except (OSError, ValueError) as exc:
            raise Broken(f"manifest.json: {type(exc).__name__}: {exc}") from exc
        if not isinstance(data, dict):
            raise Broken("manifest.json không phải đối tượng JSON")
        if data.get("source") != path.name:
            raise Broken(f"source trong manifest khác tên thư mục {path.name!r}")
        return data

    def _files(self, path: pathlib.Path, files: Any) -> tuple[list[dict[str, Any]], str | None]:
        """Các tệp đã làm sạch, và lỗi đầu tiên (tệp thiếu, sai cỡ, sai băm) nếu có."""
        if not isinstance(files, list) or not files or len(files) > FILES_MAX:
            raise Broken(f"files phải là danh sách 1–{FILES_MAX} tệp")
        out, problem, seen = [], None, set()
        for entry in files:
            if not isinstance(entry, dict):
                raise Broken("mục của files không phải đối tượng")
            name, sha, size = entry.get("file"), entry.get("sha256"), entry.get("bytes")
            if not isinstance(name, str) or not FILE_RE.fullmatch(name) or ".." in name or name in seen:
                raise Broken(f"tên tệp không hợp lệ hoặc trùng: {str(name)[:80]!r}")
            if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
                raise Broken(f"{name}: sha256 phải là 64 ký tự hex chữ thường")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise Broken(f"{name}: bytes phải là số nguyên ≥ 0")
            seen.add(name)
            at = entry.get("fetched_at")
            out.append({"file": name, "url": _url(entry.get("url")), "sha256": sha, "bytes": size,
                        "fetched_at": _when(at).isoformat(timespec="seconds") if at is not None else None,
                        "meta": _meta(entry.get("meta"))})
            problem = problem or self._check(path / name, sha, size)
        return out, problem

    def _check(self, file: pathlib.Path, sha: str, size: int) -> str | None:
        try:
            if file.is_symlink() or file.parent.is_symlink():
                return f"{file.name}: liên kết tượng trưng"
            st = file.stat()
            if not file.is_file():
                return f"{file.name}: không phải tệp thường"
            if st.st_size != size:
                return f"{file.name}: cỡ {st.st_size} byte, manifest ghi {size}"
            key = (st.st_ino, st.st_mtime_ns, st.st_size)
            cached = self._hashes.get(str(file))
            if cached is None or cached[0] != key:
                digest = hashlib.sha256()
                with file.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        digest.update(chunk)
                cached = (key, digest.hexdigest())
                self._hashes[str(file)] = cached
        except OSError as exc:
            return f"{file.name}: {type(exc).__name__}"
        return None if cached[1] == sha else f"{file.name}: SHA-256 không khớp manifest"
