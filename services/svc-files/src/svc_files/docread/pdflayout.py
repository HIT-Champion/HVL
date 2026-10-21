# Copyright 2026 Mộc Team
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

"""Lớp chữ của PDF giữ bố cục (F4.1): đủ để quy tắc biết dòng nào ở cột trái, cột phải, giữa trang.

Như pdftext.py (F2.7): tệp do người dùng tải lên nên không đọc trong tiến trình của svc-files. Tệp này chạy thành
tiến trình con (``python -I pdflayout.py``) có giới hạn bộ nhớ, CPU, thời gian; chỉ dùng thư viện chuẩn và pypdf,
không cần gói svc_files. Khác pdftext.py: giữ khoảng trắng canh cột của chế độ ``layout`` (tách cột ở chuỗi khoảng
trắng dài — layout.text_lines), chỉ đọc vài trang đầu, trả chữ từng trang.

Kết quả: ``ok`` có chữ · ``empty`` không có lớp chữ (bản scan — reader chuyển sang OCR) · ``failed`` kèm lý do
``password`` (phải nhập mật khẩu mới mở), ``corrupt``, ``timeout``, ``memory``.
"""

from __future__ import annotations

import asyncio
import io
import json
import signal
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any

MAX_PAGES = 3
PAGE_CHARS = 40_000      # mỗi trang giữ tối đa từng này ký tự (chế độ layout thêm nhiều khoảng trắng canh cột)
MAX_COUNT = 1_000_000    # số trang tệp tự khai lớn hơn thế thì không tin, trả null
MEMORY_MB = 1024         # như pdftext.py
TIMEOUT_S = 20.0
NOTES = {"password", "corrupt", "timeout", "memory"}


@dataclass(frozen=True)
class PdfLayout:
    status: str                 # ok · empty · failed
    pages: int | None           # số trang của tệp
    texts: tuple[str, ...]      # chữ từng trang đã đọc (tối đa max_pages trang đầu)
    note: str | None = None     # lý do khi failed
    truncated: bool = False     # có trang bị cắt ở PAGE_CHARS


def clean(text: str) -> str:
    """Bỏ ký tự điều khiển, ký tự ẩn; NFC từng dòng; GIỮ khoảng trắng đầu dòng và giữa chữ (vị trí cột)."""
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        chars = []
        for ch in line:
            cat = unicodedata.category(ch)
            if ch == "\t" or cat == "Zs":
                chars.append(" ")
            elif cat in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"):
                continue
            else:
                chars.append(ch)
        lines.append(unicodedata.normalize("NFC", "".join(chars)).rstrip())
    return "\n".join(lines).strip("\n")


def extract(data: bytes, *, max_pages: int = MAX_PAGES) -> PdfLayout:
    """Đọc ngay trong tiến trình hiện tại — chỉ gọi trong tiến trình con hoặc với tệp tin cậy (test)."""
    from pypdf import PasswordType, PdfReader

    reader = PdfReader(io.BytesIO(data), strict=False)
    # Khóa bằng mật khẩu chủ (cấm sửa, cấm chép) mà mở không cần mật khẩu: đọc được, như pdftext.py
    if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
        return PdfLayout("failed", None, (), "password")
    count = len(reader.pages)
    texts: list[str] = []
    truncated = False
    for i in range(min(count, max_pages)):
        try:
            page = reader.pages[i]
        except IndexError:             # khai nhiều trang hơn số trang thật
            break
        text = clean(_page_text(page))
        if len(text) > PAGE_CHARS:
            text, truncated = text[:PAGE_CHARS], True
        texts.append(text)
    if reader.flattened_pages is not None:   # đã duyệt cây trang: biết số trang thật
        count = len(reader.flattened_pages)
    pages = count if 0 <= count <= MAX_COUNT else None
    status = "ok" if any(t.strip() for t in texts) else "empty"
    return PdfLayout(status, pages, tuple(texts), None, truncated)


def _page_text(page: Any) -> str:
    """Chế độ layout; trang nào layout lỗi (phông lạ, ma trận chữ hỏng) thì đọc thường, vẫn lỗi thì coi như trống."""
    for mode in ("layout", "plain"):
        try:
            return page.extract_text(extraction_mode=mode) or ""
        except MemoryError:
            raise
        except Exception:  # noqa: BLE001 — tệp hỏng kiểu gì cũng chỉ là "trang này không đọc được chữ"
            continue
    return ""


def _failed(note: str) -> PdfLayout:
    return PdfLayout("failed", None, (), note)


async def extract_layout(data: bytes, *, max_pages: int = MAX_PAGES, timeout_s: float = TIMEOUT_S,
                         memory_mb: int = MEMORY_MB) -> PdfLayout:
    """Đọc trong tiến trình con có giới hạn; không bao giờ ném lỗi vì nội dung tệp."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-I", __file__, str(max_pages), str(memory_mb), str(int(timeout_s) + 5),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(data), max(timeout_s, 0.001))
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return _failed("timeout")
    except BaseException:
        # yêu cầu bị hủy (dịch vụ dừng): không để tiến trình con chạy tiếp
        if proc.returncode is None:
            proc.kill()
        raise
    if proc.returncode == -signal.SIGXCPU:       # hết RLIMIT_CPU
        return _failed("timeout")
    if proc.returncode != 0:
        return _failed("corrupt")
    return _parse(out, max_pages)


def _parse(out: bytes, max_pages: int) -> PdfLayout:
    """Kết quả của tiến trình con được kiểm lại trước khi dùng — tiến trình con đọc tệp không tin cậy."""
    try:
        got: dict[str, Any] = json.loads(out)
        status, pages, texts, note = got["status"], got.get("pages"), got.get("texts") or [], got.get("note")
        truncated = got.get("truncated", False)
    except (ValueError, KeyError, TypeError, AttributeError):
        return _failed("corrupt")
    if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts) \
            or not (note is None or isinstance(note, str)):
        return _failed("corrupt")
    ok = (
        status in ("ok", "empty", "failed")
        and (pages is None or (type(pages) is int and 0 <= pages <= MAX_COUNT))
        and len(texts) <= max_pages and all(len(t) <= PAGE_CHARS for t in texts)
        and (note is None if status != "failed" else note in NOTES)
        and type(truncated) is bool
        and (status == "ok") == any(t.strip() for t in texts)
    )
    if not ok:
        return _failed("corrupt")
    return PdfLayout(status, pages, tuple(texts), note, truncated)


def _main(argv: list[str]) -> int:
    import resource

    max_pages, memory_mb, cpu_s = (int(a) for a in argv[1:4])
    memory = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    data = sys.stdin.buffer.read()
    try:
        result = extract(data, max_pages=max_pages)
    except MemoryError:
        result = _failed("memory")
    except Exception:  # noqa: BLE001 — tệp hỏng kiểu gì cũng chỉ là "không đọc được"
        result = _failed("corrupt")
    sys.stdout.write(json.dumps({**result.__dict__, "texts": list(result.texts)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
