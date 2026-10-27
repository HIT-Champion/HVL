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

"""Nhận dạng chữ (OCR) bản scan, ảnh chụp văn bản đến (F4.1) bằng Tesseract, trong tiến trình con có giới hạn.

Ảnh do người dùng tải lên: bộ giải mã ảnh của Pillow, của pypdf và chính tesseract đều chạy ngoài tiến trình
svc-files. Tiến trình con (``python -I ocr.py``) có RLIMIT_AS, RLIMIT_CPU — tesseract là tiến trình cháu, kế thừa cả
hai giới hạn. Tiến trình con mở phiên riêng (``start_new_session``): quá giờ thì giết cả nhóm (``os.killpg``), không
để tesseract chạy mồ côi. Tệp chỉ dùng thư viện chuẩn, pypdf và Pillow, không cần gói svc_files.

Ảnh: Pillow mở (trần điểm ảnh ``MAX_IMAGE_PIXELS``, cả với ảnh nhúng của PDF), xoay theo EXIF, đổi sang xám, giãn
tương phản, đưa cạnh dài về 2000–3500 px, rồi gửi PNG qua stdin cho ``tesseract stdin stdout -l <ngôn ngữ> --oem 1
--psm 3 tsv``. PDF scan: không rasterize (image không có poppler, pdfium) — lấy ảnh nhúng lớn nhất của mỗi trang, tối
đa ``max_pages`` trang đầu.

Kết quả: ``ok`` kèm TSV từng trang · ``failed`` kèm lý do: ``no_text`` (PDF không có ảnh nào), ``too_many_pixels``,
``password``, ``corrupt``, ``timeout``, ``memory`` — lỗi của tệp, kể cả khi tesseract chết vì tín hiệu (SIGKILL,
SIGABRT: ``memory``; tín hiệu khác: ``corrupt``) hay tự báo hết bộ nhớ; ``no_tesseract``, ``engine_failed`` (thiếu
chương trình; tesseract tự thoát mã dương — thiếu dữ liệu ngôn ngữ) — lỗi của máy chủ.

Dùng chung, không riêng đọc văn bản đến (docread/): chữ bản scan cho tìm kiếm (texts.py, #253); ``kill_group``,
``killed`` cũng dọn tiến trình con của sealed.py, imageclean.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import re
import signal
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

MIN_SIDE = 2000          # cạnh dài của ảnh gửi tesseract: chữ công văn A4 ~ 30 px cao
MAX_SIDE = 3500
TSV_BYTES = 2 * 1024 * 1024   # giữ tối đa từng này byte TSV mỗi trang
MAX_COUNT = 1_000_000
NOTES = {"no_text", "too_many_pixels", "password", "corrupt", "timeout", "memory", "no_tesseract", "engine_failed"}
SERVER_NOTES = {"no_tesseract", "engine_failed"}   # máy chủ thiếu tesseract hoặc dữ liệu ngôn ngữ: 503, không phải 422
STDERR_BYTES = 64 * 1024      # chỉ dò dấu hiệu hết bộ nhớ trong phần cuối stderr của tesseract, không ghi ra đâu
# tesseract (C++, leptonica) tự báo không cấp phát được: chạm RLIMIT_AS, hoặc cgroup của container
MEMORY_RE = re.compile(rb"bad_alloc|out of memory|cannot allocate|alloc\w* fail", re.IGNORECASE)


@dataclass(frozen=True)
class OcrResult:
    status: str                 # ok · failed
    pages: int | None           # số trang của tệp (ảnh: 1)
    tsv: tuple[str, ...]        # TSV của tesseract, mỗi trang đã nhận dạng một chuỗi
    note: str | None = None


def killed(returncode: int) -> str:
    """Lý do khi tiến trình (tesseract, tiến trình con) chết vì tín hiệu — mã trả về âm. Đều là lỗi của tệp (422)."""
    sig = -returncode
    if sig == signal.SIGXCPU:
        return "timeout"        # hết RLIMIT_CPU
    if sig in (signal.SIGKILL, signal.SIGABRT):
        return "memory"         # bộ diệt OOM của hạt nhân, cgroup; std::bad_alloc không bắt → abort
    return "corrupt"            # SIGSEGV, SIGBUS, SIGFPE…: tệp làm bộ giải mã sập


class _Fail(Exception):
    def __init__(self, note: str, pages: int | None = None) -> None:
        super().__init__(note)
        self.note = note
        self.pages = pages


# --- trong tiến trình con ----------------------------------------------------------------------------------


def _check_pixels(width: int, height: int, max_pixels: int) -> None:
    if width < 1 or height < 1:
        raise _Fail("corrupt")
    if width * height > max_pixels:
        raise _Fail("too_many_pixels")


@contextlib.contextmanager
def _pixel_limit(max_pixels: int) -> Iterator[None]:
    """Trần điểm ảnh của Pillow cho mọi lần mở ảnh bên trong; Pillow kiểm kích thước thật ngay khi mở, trước khi giải
    mã. Pillow chỉ cảnh báo khi ảnh vượt trần, tới gấp đôi mới ném lỗi: ở đây vượt trần là dừng, ``too_many_pixels``."""
    import warnings

    from PIL import Image

    Image.MAX_IMAGE_PIXELS = max_pixels
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            yield
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise _Fail("too_many_pixels") from exc


def open_image(data: bytes, max_pixels: int) -> Any:
    """Ảnh (JPEG, PNG, TIFF — trang đầu) đã giải mã; vượt trần điểm ảnh thì ``too_many_pixels``."""
    from PIL import Image

    with _pixel_limit(max_pixels):
        img = Image.open(io.BytesIO(data))
        _check_pixels(img.width, img.height, max_pixels)
        img.load()
    return img


def prepare(img: Any) -> bytes:
    """Xoay theo EXIF, nền trắng cho ảnh trong suốt, xám, giãn tương phản, cạnh dài 2000–3500 px → PNG."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(white, rgba)
    img = ImageOps.autocontrast(img.convert("L"))
    side = max(img.size)
    target = min(max(side, MIN_SIDE), MAX_SIDE)
    if target != side:
        scale = target / side
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "PNG", compress_level=1)
    return out.getvalue()


def _xobject(page: Any, key: Any) -> Any:
    """Ảnh nhúng theo khóa của ``page.images`` (tên, hoặc chuỗi tên lồng trong form XObject), chưa giải mã."""
    path = [key] if isinstance(key, str) else list(key)
    obj = page
    for name in path:
        obj = obj["/Resources"]["/XObject"][name].get_object()
    return obj


def pdf_images(data: bytes, max_pages: int, max_pixels: int) -> tuple[int | None, Iterator[Any]]:
    """(số trang, ảnh nhúng lớn nhất của từng trang trong ``max_pages`` trang đầu — giải mã lần lượt). Trang không có
    ảnh nào cho ``None`` để TSV các trang sau vẫn đúng số trang (#253: trợ lý trích "tr. n" từ chữ OCR)."""
    from pypdf import PasswordType, PdfReader

    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
        raise _Fail("password")
    count = len(reader.pages)
    if reader.flattened_pages is not None:
        count = len(reader.flattened_pages)
    pages = count if 0 <= count <= MAX_COUNT else None

    def images() -> Iterator[Any]:
        for i in range(min(count, max_pages)):
            try:
                page = reader.pages[i]
            except IndexError:
                return
            best, size = None, 0
            for key in page.images.keys():
                if isinstance(key, str) and key.startswith("~"):    # ảnh nội tuyến: nhỏ, không phải bản scan
                    continue
                try:
                    obj = _xobject(page, key)
                    w, h = int(obj.get("/Width", 0)), int(obj.get("/Height", 0))
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue
                if w * h > size:
                    best, size = key, w * h
            if best is None:
                yield None
                continue
            obj = _xobject(page, best)
            # kiểm kích thước khai trong PDF TRƯỚC khi giải mã: pypdf giải nén cả ảnh vào bộ nhớ
            _check_pixels(int(obj["/Width"]), int(obj["/Height"]), max_pixels)
            # kích thước khai có thể nói dối: luồng JPEG, JPEG 2000, TIFF mang kích thước riêng, pypdf mở bằng Pillow
            # — cùng trần như ảnh tải lên, ảnh thật vượt trần thì dừng lúc mở chứ không giải mã rồi mới đo
            with _pixel_limit(max_pixels):
                img = page.images[best].image
            if img is None:
                raise _Fail("corrupt")
            _check_pixels(img.width, img.height, max_pixels)
            yield img

    return pages, images()


def tesseract(png: bytes, *, binary: str, lang: str, timeout_s: float) -> str:
    """TSV của tesseract cho một ảnh PNG. Môi trường tối thiểu, một luồng OpenMP."""
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "OMP_THREAD_LIMIT": "1"}
    if os.environ.get("TESSDATA_PREFIX"):        # dữ liệu ngôn ngữ khác bản của gói Debian (vd tessdata_best)
        env["TESSDATA_PREFIX"] = os.environ["TESSDATA_PREFIX"]
    try:
        proc = subprocess.run(
            [binary, "stdin", "stdout", "-l", lang, "--oem", "1", "--psm", "3", "tsv"],
            input=png, capture_output=True, env=env, timeout=timeout_s, check=False,
        )
    except (FileNotFoundError, PermissionError, NotADirectoryError) as exc:
        raise _Fail("no_tesseract") from exc
    except subprocess.TimeoutExpired as exc:
        raise _Fail("timeout") from exc
    if proc.returncode < 0:
        raise _Fail(killed(proc.returncode))
    if proc.returncode != 0:
        # tự thoát với mã dương: thiếu dữ liệu ngôn ngữ, cài hỏng — lỗi của máy chủ (503); trừ khi tự báo hết bộ nhớ
        raise _Fail("memory" if MEMORY_RE.search(proc.stderr[-STDERR_BYTES:]) else "engine_failed")
    return proc.stdout[:TSV_BYTES].decode("utf-8", "replace")


def recognize(data: bytes, kind: str, *, binary: str, lang: str, max_pages: int, max_pixels: int,
              timeout_s: float) -> OcrResult:
    """Đọc ngay trong tiến trình hiện tại — chỉ gọi trong tiến trình con hoặc với tệp tin cậy (test)."""
    try:
        if kind == "pdf":
            pages, images = pdf_images(data, max_pages, max_pixels)
        else:
            pages, images = 1, iter([open_image(data, max_pixels)])
        # trang không có ảnh: TSV rỗng, giữ chỗ của trang
        tsv = ["" if img is None else tesseract(prepare(img), binary=binary, lang=lang, timeout_s=timeout_s)
               for img in images]
    except _Fail as exc:
        return OcrResult("failed", exc.pages, (), exc.note)
    if not any(tsv):
        return OcrResult("failed", pages, (), "no_text")
    return OcrResult("ok", pages, tuple(tsv))


def _main(argv: list[str]) -> int:
    import resource

    kind, binary, lang = argv[1:4]
    max_pages, max_pixels, memory_mb, cpu_s = (int(a) for a in argv[4:8])
    timeout_s = float(argv[8])
    memory = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    data = sys.stdin.buffer.read()
    try:
        result = recognize(data, kind, binary=binary, lang=lang, max_pages=max_pages, max_pixels=max_pixels,
                           timeout_s=timeout_s)
    except MemoryError:
        result = OcrResult("failed", None, (), "memory")
    except Exception:  # noqa: BLE001 — ảnh hỏng kiểu gì cũng chỉ là "không đọc được"
        result = OcrResult("failed", None, (), "corrupt")
    sys.stdout.write(json.dumps({**result.__dict__, "tsv": list(result.tsv)}, ensure_ascii=False))
    return 0


# --- trong svc-files ----------------------------------------------------------------------------------------


def kill_group(proc: asyncio.subprocess.Process) -> None:
    """Giết cả nhóm tiến trình (tiến trình con + tesseract). Nhóm còn thành viên thì mã nhóm chưa bị cấp lại."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


async def run_ocr(data: bytes, kind: str, *, binary: str = "tesseract", lang: str = "vie", max_pages: int = 1,
                  max_pixels: int = 40_000_000, timeout_s: float = 40.0, memory_mb: int = 1536) -> OcrResult:
    """OCR trong tiến trình con có giới hạn; ``kind``: pdf hoặc image. Không bao giờ ném lỗi vì nội dung tệp."""
    timeout_s = max(timeout_s, 0.001)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-I", __file__, kind, binary, lang, str(max_pages), str(max_pixels), str(memory_mb),
        str(int(timeout_s) + 5), f"{timeout_s:.3f}",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(data), timeout_s)
    except TimeoutError:
        kill_group(proc)
        await proc.wait()
        return OcrResult("failed", None, (), "timeout")
    finally:
        # hết giờ, yêu cầu bị hủy, hay xong bình thường: nhóm không còn ai chạy tiếp
        kill_group(proc)
    if proc.returncode is not None and proc.returncode < 0:
        return OcrResult("failed", None, (), killed(proc.returncode))
    if proc.returncode != 0:
        return OcrResult("failed", None, (), "corrupt")
    return _parse(out, max_pages)


def _parse(out: bytes, max_pages: int) -> OcrResult:
    try:
        got: dict[str, Any] = json.loads(out)
        status, pages, tsv, note = got["status"], got.get("pages"), got.get("tsv") or [], got.get("note")
    except (ValueError, KeyError, TypeError, AttributeError):
        return OcrResult("failed", None, (), "corrupt")
    if not isinstance(tsv, list) or not (note is None or isinstance(note, str)):
        return OcrResult("failed", None, (), "corrupt")
    ok = (
        ((status == "ok" and note is None and len(tsv) > 0) or (status == "failed" and note in NOTES and not tsv))
        and (pages is None or (type(pages) is int and 0 <= pages <= MAX_COUNT))
        and len(tsv) <= max_pages
        and all(isinstance(t, str) and len(t) <= TSV_BYTES for t in tsv)
    )
    if not ok:
        return OcrResult("failed", None, (), "corrupt")
    return OcrResult(status, pages, tuple(tsv), note)


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
