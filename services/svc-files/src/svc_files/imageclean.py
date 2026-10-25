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

"""Bỏ siêu dữ liệu của ảnh JPEG, PNG tải lên trước khi lưu: EXIF (tọa độ GPS, máy chụp, giờ chụp), XMP, IPTC, chú
thích, chữ trong PNG — tệp tải về không lộ người chụp đứng ở đâu, lúc nào.

Pillow giải mã rồi mã hóa lại ảnh. Xoay theo hướng EXIF trước (ảnh chụp dọc không nằm ngang khi mất EXIF), giữ hồ sơ
màu ICC và DPI. JPEG giữ bảng lượng tử, cách lấy mẫu màu của tệp gốc (chất lượng như cũ, không mờ thêm một lượt nén),
mã Huffman tối ưu (cỡ tệp như cũ); PNG không mất dữ liệu, giữ màu trong suốt, ảnh động APNG giữ đủ khung (không xoay).
Byte nối thêm sau ảnh (tệp đa hình ảnh + HTML, zip) cũng rơi mất.

Như ocr.py: ảnh do người dùng tải lên chỉ giải mã trong tiến trình con (``python -I imageclean.py``) có RLIMIT_AS,
RLIMIT_CPU, hạn thời gian; quá hạn thì giết cả nhóm. Trần ``MAX_PIXELS`` chặn ảnh bom giải nén. Tệp chỉ dùng thư viện
chuẩn và Pillow, không cần gói svc_files. Không làm được: CleanError mang ``reason`` — corrupt, too_many_pixels,
timeout, memory.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from typing import Any

FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG"}     # mime theo nội dung (filetype.py) → định dạng của Pillow
SIGNATURES = {"JPEG": b"\xff\xd8\xff", "PNG": b"\x89PNG\r\n\x1a\n"}
MAX_PIXELS = 100_000_000     # ảnh 108 MP của điện thoại vượt; ảnh 48–64 MP, bản scan A4 600 dpi (35 MP) đều dưới
MEMORY_MB = 2048             # RLIMIT_AS: ảnh 100 MP giải mã (RGB 300 MB, CMYK 400 MB) cộng bộ đệm mã hóa lại
TIMEOUT_S = 30.0
EXIT_MEMORY = 3              # hết bộ nhớ cả lúc ghi kết quả (không ghi nổi dòng JSON)
REASONS = {
    "corrupt": "ảnh hỏng hoặc sai định dạng",
    "too_many_pixels": f"ảnh quá lớn (quá {MAX_PIXELS // 1_000_000} triệu điểm ảnh) — thu nhỏ rồi tải lên lại",
    "timeout": "ảnh quá nặng để xử lý trong thời gian cho phép — thu nhỏ rồi tải lên lại",
    "memory": "ảnh cần quá nhiều bộ nhớ để xử lý — thu nhỏ rồi tải lên lại",
}


class CleanError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(REASONS[reason])
        self.reason = reason


def clean(data: bytes, fmt: str, max_pixels: int = MAX_PIXELS) -> bytes:
    """Ảnh đã bỏ siêu dữ liệu, cùng định dạng ``fmt`` (JPEG, PNG). Chạy ngay trong tiến trình hiện tại — chỉ gọi trong
    tiến trình con hoặc với tệp tin cậy (test)."""
    import warnings

    from PIL import Image, ImageOps, JpegImagePlugin

    # Pillow kiểm kích thước thật ngay khi mở, trước khi giải mã; vượt trần chỉ cảnh báo, gấp đôi mới ném lỗi
    Image.MAX_IMAGE_PIXELS = max_pixels
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            img = Image.open(io.BytesIO(data), formats=[fmt])
            if img.width < 1 or img.height < 1:
                raise CleanError("corrupt")
            if img.width * img.height > max_pixels:
                raise CleanError("too_many_pixels")
            img.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise CleanError("too_many_pixels") from exc
    animated = getattr(img, "is_animated", False)
    opts: dict[str, Any] = {k: img.info[k] for k in ("icc_profile", "transparency") if k in img.info}
    dpi = img.info.get("dpi")
    if isinstance(dpi, tuple) and len(dpi) == 2 and all(isinstance(v, int | float) and 1 <= v <= 65535 for v in dpi):
        opts["dpi"] = dpi           # DPI lạ (0, quá lớn) thì bỏ: JFIF chỉ ghi được số 16 bit
    if fmt == "JPEG":
        opts.update(qtables=img.quantization, subsampling=JpegImagePlugin.get_sampling(img), optimize=True)
    if animated:
        opts.update(save_all=True, loop=img.info.get("loop", 0), default_image=img.info.get("default_image", False))
    else:
        size = img.size
        ImageOps.exif_transpose(img, in_place=True)
        if img.size != size and "dpi" in opts:
            opts["dpi"] = tuple(reversed(opts["dpi"]))
    img.info = {}       # EXIF, XMP, chú thích, chữ PNG…: Pillow ghi lại những gì còn trong info (vd chú thích JPEG)
    out = io.BytesIO()
    img.save(out, fmt, **opts)
    return out.getvalue()


# --- tiến trình con -------------------------------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    """``python -I imageclean.py <JPEG|PNG> <max_pixels> <memory_mb> <cpu_s>``; ảnh qua stdin. Ra stdout: một dòng
    JSON (``status`` ok · failed kèm ``reason``), ok thì sau dòng đó là ảnh đã làm sạch."""
    import resource

    fmt = argv[1]
    max_pixels, memory_mb, cpu_s = (int(a) for a in argv[2:5])
    memory = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    body = b""
    try:  # mọi việc sau khi đặt trần đều trong try: MemoryError không lọt ra thành mã thoát 1 ("corrupt")
        body = clean(sys.stdin.buffer.read(), fmt, max_pixels)
        head: dict[str, Any] = {"status": "ok"}
    except CleanError as exc:
        head = {"status": "failed", "reason": exc.reason}
    except MemoryError:
        head = {"status": "failed", "reason": "memory"}
    except Exception:  # noqa: BLE001 — ảnh hỏng kiểu gì cũng chỉ là "không xử lý được"
        head = {"status": "failed", "reason": "corrupt"}
    sys.stdout.buffer.write(json.dumps(head).encode() + b"\n")
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()
    return 0


# --- trong svc-files ------------------------------------------------------------------------------------------------

async def run_clean(data: bytes, mime: str, *, max_pixels: int = MAX_PIXELS, timeout_s: float = TIMEOUT_S,
                    memory_mb: int = MEMORY_MB) -> bytes:
    """clean trong tiến trình con có giới hạn; ``mime`` là khóa của FORMATS. Không làm được: CleanError."""
    # nhập ở đây, không ở đầu tệp: tiến trình con chạy tệp này như script, không có gói svc_files
    from .docread.ocr import _kill_group, _killed

    fmt = FORMATS[mime]
    timeout_s = max(timeout_s, 0.001)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-I", __file__, fmt, str(max_pixels), str(memory_mb), str(int(timeout_s) + 5),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(data), timeout_s)
    except TimeoutError:
        _kill_group(proc)
        await proc.wait()
        raise CleanError("timeout") from None
    finally:
        # hết giờ, yêu cầu bị hủy, hay xong bình thường: không để tiến trình con chạy tiếp
        _kill_group(proc)
    rc = proc.returncode
    if rc is not None and rc < 0:
        raise CleanError(_killed(rc))      # SIGXCPU → timeout; SIGKILL, SIGABRT → memory; tín hiệu khác → corrupt
    if rc != 0:
        raise CleanError("memory" if rc == EXIT_MEMORY else "corrupt")
    # kết quả của tiến trình con đọc tệp không tin cậy: kiểm dạng trước khi dùng
    line, _, body = out.partition(b"\n")
    try:
        head: dict[str, Any] = json.loads(line)
        status, reason = head["status"], head.get("reason")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CleanError("corrupt") from None
    if status == "failed" and isinstance(reason, str) and reason in REASONS:
        raise CleanError(reason)
    if status != "ok" or not body.startswith(SIGNATURES[fmt]):
        raise CleanError("corrupt")
    return body


if __name__ == "__main__":
    try:
        sys.exit(_main(sys.argv))
    except MemoryError:  # hết bộ nhớ cả lúc ghi kết quả: báo bằng mã thoát, việc này không cần cấp phát
        sys.exit(EXIT_MEMORY)
