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

"""Zip tệp đính kèm của lô nạp, giữ tạm tới khi lô xong.

Thư mục spool nằm trên tmpfs ``/tmp`` của svc-files (compose), như Starlette vẫn đệm tệp tải lên ở đó: zip **chưa
quét** không bao giờ vào kho đối tượng (F1.6 — kho chỉ có tệp đã quét). Không quét nguyên khối zip lúc tạo lô: một mục
nhiễm sẽ làm hỏng cả lô; từng mục được ClamAV quét đúng như tải lên lẻ (``ingest``) trước khi vào kho. Container khởi
động lại thì tmpfs mất zip: dòng còn cần tệp báo ``archive_lost`` (runner.py).

Đọc một mục: ``zf.open(info).read(limit + 1)`` — giải nén dừng ở trần dù kích thước khai trong zip nói gì, không sợ bom
zip. Mục có mật khẩu không mở (trạm quét không kiểm được bên trong).
"""

from __future__ import annotations

import hashlib
import os
import unicodedata
import uuid
import zipfile
import zlib
from pathlib import Path
from typing import BinaryIO

from .parse import ParseError, Row

ZIP_MAX_ENTRIES = 5000
CHUNK = 1024 * 1024


class EntryError(Exception):
    """Một mục của zip không đọc được: dòng trỏ tới nó thành ``failed`` với mã này."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _mb(n: int) -> int:
    return n // (1024 * 1024)


class Spool:
    def __init__(self, directory: str, max_bytes: int) -> None:
        self.dir = Path(directory)
        self.max_bytes = max_bytes

    def path(self, job_id: uuid.UUID | str) -> Path:
        return self.dir / f"{job_id}.zip"

    def _part(self, job_id: uuid.UUID | str) -> Path:
        return self.dir / f"{job_id}.zip.part"

    def _ensure(self) -> None:
        self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def used(self) -> int:
        """Tổng byte đang giữ (zip của lô chưa xong và phần đang nhận)."""
        try:
            return sum(p.stat().st_size for p in self.dir.iterdir() if p.is_file())
        except FileNotFoundError:
            return 0

    def prepare(self, keep: set[str] | None, *, before: float) -> int:
        """Lúc khởi động: tạo thư mục (0700), xóa phần nhận dở và zip của lô đã xong hoặc không còn (``keep``: id lô
        chưa xong; None: chưa đọc được CSDL thì chỉ xóa phần nhận dở). Chỉ xóa tệp cũ hơn ``before`` (lúc dịch vụ khởi
        động) để không đụng zip của lô vừa tạo trong lúc dọn. Trả số tệp đã xóa."""
        self._ensure()
        os.chmod(self.dir, 0o700)
        removed = 0
        for p in self.dir.iterdir():
            if not p.is_file() or p.stat().st_mtime >= before:
                continue
            stale = p.name.endswith(".part") or (
                keep is not None and p.name.endswith(".zip") and p.name.removesuffix(".zip") not in keep)
            if stale:
                p.unlink(missing_ok=True)
                removed += 1
        return removed

    def receive(self, src: BinaryIO, job_id: uuid.UUID, limit: int) -> tuple[str, int]:
        """Chép zip từ thân yêu cầu vào ``<lô>.zip.part``, tính SHA-256 và cỡ trong cùng lượt; quá ``limit`` thì xóa
        phần đã chép, 413. Chạy trong thread (đọc ghi đồng bộ)."""
        self._ensure()
        part, digest, size = self._part(job_id), hashlib.sha256(), 0
        try:
            with open(part, "wb", opener=lambda p, f: os.open(p, f, 0o600)) as out:
                while chunk := src.read(CHUNK):
                    size += len(chunk)
                    if size > limit:
                        raise ParseError(413, "too_large", f"Tệp nén vượt giới hạn {_mb(limit)} MB")
                    digest.update(chunk)
                    out.write(chunk)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        if size == 0:
            part.unlink(missing_ok=True)
            raise ParseError(400, "bad_archive", "Tệp nén rỗng")
        return digest.hexdigest(), size

    def entries(self, job_id: uuid.UUID) -> dict[str, zipfile.ZipInfo]:
        """Mục của zip vừa nhận theo tên chuẩn hóa NFC, bỏ thư mục. Zip hỏng, quá nhiều mục, hai mục trùng tên: 400."""
        try:
            with zipfile.ZipFile(self._part(job_id)) as zf:
                return index(zf)
        except (zipfile.BadZipFile, zlib.error, ValueError, OSError, EOFError) as exc:
            raise ParseError(400, "bad_archive", f"Tệp nén không mở được (không phải zip hợp lệ: {exc})") from None

    def commit(self, job_id: uuid.UUID) -> None:
        os.replace(self._part(job_id), self.path(job_id))

    def drop(self, job_id: uuid.UUID | str) -> None:
        self._part(job_id).unlink(missing_ok=True)
        self.path(job_id).unlink(missing_ok=True)

    def open(self, job_id: str, size: int | None) -> zipfile.ZipFile | None:
        """Zip của lô; không còn (dịch vụ khởi động lại — tmpfs mất) hay khác cỡ lúc nhận thì None."""
        p = self.path(job_id)
        try:
            if size is None or p.stat().st_size != int(size):
                return None
            return zipfile.ZipFile(p)
        except (FileNotFoundError, zipfile.BadZipFile, OSError):
            return None


def index(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = zf.infolist()
    if len(infos) > ZIP_MAX_ENTRIES:
        raise ParseError(400, "bad_archive", f"Tệp nén có {len(infos)} mục, tối đa {ZIP_MAX_ENTRIES}")
    out: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        if info.is_dir():
            continue
        name = unicodedata.normalize("NFC", info.filename)
        if name in out:
            raise ParseError(400, "bad_archive", f"Tệp nén có hai mục cùng tên {name!r} (sau chuẩn hóa NFC)")
        out[name] = info
    return out


def check_rows(rows: list[Row], entries: dict[str, zipfile.ZipInfo] | None, max_bytes: int, total_max: int) -> None:
    """Lúc tạo lô: dòng trỏ tệp không có trong zip (hay không gửi zip) → ``missing_attachment``; mục khai lớn hơn trần
    một tệp (MOC_FILES_MAX_MB) → ``too_large``. Không đọc byte nào.

    Rồi trần cả lô (``total_max``, MOC_IMPORT_STORE_MAX_MB): tổng cỡ khai của các mục mà các dòng còn lại trỏ tới, mỗi
    lần trỏ tính một lần — vòng nền lưu một bản cho mỗi dòng trỏ tới một mục, nên một zip nhỏ trỏ lặp lại nhiều lần
    vẫn là nhiều byte trong kho. Vượt thì cả tệp bị từ chối (413), không tạo lô. Cỡ khai là trần thật của byte được
    lưu: ``zipfile`` dừng giải nén ở cỡ khai và báo hỏng khi CRC sai."""
    for row in rows:
        if row.failed or not row.files:
            continue
        if entries is None:
            row.fail("missing_attachment", "Dòng có files mà yêu cầu không kèm tệp nén (archive)")
            continue
        missing = [n for n in row.files if n not in entries]
        if missing:
            row.fail("missing_attachment", "Không có trong tệp nén: " + ", ".join(missing[:5]))
            continue
        big = [n for n in row.files if entries[n].file_size > max_bytes]
        if big:
            row.fail("too_large", f"Tệp vượt giới hạn {_mb(max_bytes)} MB: " + ", ".join(big[:5]))
    if not entries:
        return
    total = sum(entries[name].file_size for row in rows if not row.failed for name in row.files)
    if total > total_max:
        raise ParseError(413, "too_large", f"Các dòng trỏ tới tổng {total / (1024 * 1024):.1f} MB tệp đính kèm (một "
                         f"tệp được nhiều dòng trỏ tới thì tính mỗi lần), vượt trần {_mb(total_max)} MB của một lô — "
                         "chia thành nhiều lô")


def read_entry(zf: zipfile.ZipFile, entries: dict[str, zipfile.ZipInfo], name: str, limit: int) -> bytes:
    """Byte của một mục (chạy trong thread). Lỗi → EntryError với mã của dòng."""
    info = entries.get(name)
    if info is None:
        raise EntryError("missing_attachment", f"{name}: không có trong tệp nén")
    if info.flag_bits & 0x1:
        raise EntryError("unscannable", f"{name}: tệp trong zip đặt mật khẩu nên trạm quét mã độc không kiểm được "
                         "bên trong — đã chặn")
    if info.file_size > limit:
        raise EntryError("too_large", f"{name}: tệp vượt giới hạn {_mb(limit)} MB")
    try:
        with zf.open(info) as f:
            data = f.read(limit + 1)
    except (zipfile.BadZipFile, zlib.error, NotImplementedError, RuntimeError, OSError, EOFError) as exc:
        raise EntryError("bad_archive", f"{name}: không giải nén được ({type(exc).__name__})") from None
    if len(data) > limit:
        raise EntryError("too_large", f"{name}: tệp vượt giới hạn {_mb(limit)} MB")
    return data
