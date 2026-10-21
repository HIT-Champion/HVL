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

"""Đọc lớp chữ của tệp PDF (F2.7) để tìm theo nội dung.

Tệp do người dùng tải lên, ClamAV chỉ biết nó không chứa mã độc đã biết: một PDF dựng có ý đồ vẫn có thể làm
bộ đọc chạy mãi hoặc ăn hết bộ nhớ. Vì vậy svc-files không đọc PDF trong tiến trình của mình mà chạy tệp này
thành tiến trình con (``extract_pdf``), giới hạn bộ nhớ, thời gian CPU và thời gian chờ; quá hạn thì giết.
Tệp này chỉ dùng thư viện chuẩn và pypdf, chạy được bằng ``python -I pdftext.py`` không cần gói svc_files.

PDF chỉ có ảnh (bản scan) không có lớp chữ: trạng thái ``empty``, để dành cho OCR (F4.1).

Ranh giới trang (F4.2): ``clean()`` từng trang rồi nối bằng ``\n``; ``page_starts`` là vị trí ký tự đầu mỗi trang
trong ``content`` — trợ lý hỏi đáp cắt đoạn theo trang và trích dẫn "tr. n" (assist/chunks.py).
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any

MAX_PAGES = 200          # đọc tối đa từng này trang đầu (cũng là số phần tử tối đa của page_starts trong CSDL)
MAX_COUNT = 2**31 - 1    # số trang tệp tự khai (/Count) lớn hơn thế không vừa cột int: ghi null
MAX_CHARS = 50_000       # giữ tối đa từng này ký tự (khớp ràng buộc của core.file_texts)
MEMORY_MB = 1024         # giới hạn bộ nhớ ảo của tiến trình con
TIMEOUT_S = 60.0         # quá thời gian này thì giết tiến trình con


@dataclass(frozen=True)
class PdfText:
    status: str                 # ok: có chữ · empty: không có lớp chữ (bản scan) · failed: không đọc được
    pages: int | None
    content: str
    note: str | None = None     # lý do khi failed: encrypted, timeout, PdfReadError…
    # vị trí đầu trang 1..n trong content (F4.2); trang trống mang cùng vị trí với trang sau; None khi không ok
    page_starts: list[int] | None = None


def clean(text: str) -> str:
    """Bỏ ký tự điều khiển và ký tự ẩn (PostgreSQL không nhận NUL), NFC, gộp khoảng trắng, bỏ dòng trống thừa.

    NFC sau khi bỏ ký tự ẩn: dấu thanh đứng sau một ký tự ẩn chỉ ghép được vào chữ khi ký tự ẩn đã bị bỏ.
    """
    chars = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch == "\n" or cat in ("Zl", "Zp"):
            chars.append("\n")
        elif ch == "\t" or cat == "Zs":
            chars.append(" ")
        elif cat in ("Cc", "Cf", "Cs", "Co", "Cn"):
            continue
        else:
            chars.append(ch)
    text = unicodedata.normalize("NFC", "".join(chars))
    lines = [re.sub(" {2,}", " ", line).strip() for line in text.split("\n")]
    return re.sub("\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract(data: bytes, *, max_pages: int = MAX_PAGES, max_chars: int = MAX_CHARS) -> PdfText:
    """Đọc ngay trong tiến trình hiện tại — chỉ gọi trong tiến trình con hoặc với tệp tin cậy (test)."""
    from pypdf import PdfReader
    from pypdf import PasswordType

    reader = PdfReader(io.BytesIO(data), strict=False)
    # Nhiều văn bản hành chính khóa bằng mật khẩu chủ (cấm sửa, cấm chép) nhưng mở không cần mật khẩu: đọc được.
    if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
        return PdfText("failed", None, "", "encrypted")
    # Tệp mã hóa: pypdf trả nguyên /Count tệp tự khai, không tin được — tệp dựng có ý đồ khai hàng tỉ trang.
    count = len(reader.pages)
    parts: list[str] = []
    size = 0
    for i in range(min(count, max_pages)):
        try:
            page = reader.pages[i]
        except IndexError:             # khai nhiều trang hơn số trang thật
            break
        part = page.extract_text() or ""
        parts.append(clean(part))
        size += len(part)
        if size >= max_chars * 2:      # đủ chữ rồi, không đọc thêm trang
            break
    if reader.flattened_pages is not None:   # đã duyệt cây trang: biết số trang thật
        count = len(reader.flattened_pages)
    pages = count if 0 <= count <= MAX_COUNT else None
    full, starts = join_pages(parts)
    content = full[:max_chars].rstrip()
    if not content:
        return PdfText("empty", pages, "")
    # trang bắt đầu sau điểm cắt thì bỏ
    return PdfText("ok", pages, content, page_starts=[s for s in starts if s <= len(content)])


def join_pages(parts: list[str]) -> tuple[str, list[int]]:
    """Nối chữ các trang (đã clean) bằng ``\n``; trả về (nội dung, vị trí đầu từng trang).

    Trang trống không thêm gì vào nội dung và mang cùng vị trí với trang có chữ kế sau (cuối tệp: độ dài nội dung).
    """
    content = ""
    starts: list[int | None] = []
    for part in parts:
        if part:
            if content:
                content += "\n"
            starts.append(len(content))
            content += part
        else:
            starts.append(None)
    following = len(content)
    for i in range(len(starts) - 1, -1, -1):
        if starts[i] is None:
            starts[i] = following
        else:
            following = starts[i]
    return content, [int(s) for s in starts if s is not None]


def _failed(note: str) -> PdfText:
    return PdfText("failed", None, "", note[:200])


async def extract_pdf(data: bytes, *, timeout_s: float = TIMEOUT_S, max_pages: int = MAX_PAGES,
                      max_chars: int = MAX_CHARS, memory_mb: int = MEMORY_MB) -> PdfText:
    """Đọc lớp chữ trong tiến trình con có giới hạn; không bao giờ ném lỗi vì nội dung tệp."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-I", __file__, str(max_pages), str(max_chars), str(memory_mb), str(int(timeout_s) + 5),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(data), timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return _failed("timeout")
    if proc.returncode != 0:
        return _failed(f"exit {proc.returncode}")      # vd bị giết vì quá giới hạn bộ nhớ, CPU
    return _parse(out, max_chars)


def _parse(out: bytes, max_chars: int) -> PdfText:
    """Kết quả của tiến trình con, chỉ nhận cái core.file_texts nhận được: dòng bị CSDL từ chối thì tệp nằm lại
    hàng đợi."""
    try:
        got: dict[str, Any] = json.loads(out)
        text = PdfText(str(got["status"]), got.get("pages"), str(got.get("content") or ""), got.get("note"),
                       got.get("page_starts"))
    except (ValueError, KeyError, TypeError, AttributeError):
        return _failed("bad output")
    pages_ok = text.pages is None or (type(text.pages) is int and 0 <= text.pages <= MAX_COUNT)
    if (text.status not in ("ok", "empty", "failed") or (text.status == "ok") != bool(text.content)
            or len(text.content) > max_chars or not pages_ok or not isinstance(text.note, str | None)
            or not _starts_ok(text.page_starts, text.status, len(text.content))):
        return _failed("bad output")
    return PdfText(text.status, text.pages, text.content, text.note[:200] if text.note else None, text.page_starts)


def _starts_ok(starts: Any, status: str, length: int) -> bool:
    """Như ràng buộc file_texts_page_starts: null, hoặc (chỉ khi ok) 1..200 số nguyên không giảm, đầu 0, ≤ độ dài."""
    if starts is None:
        return True
    if status != "ok" or not isinstance(starts, list) or not 1 <= len(starts) <= MAX_PAGES:
        return False
    if any(type(s) is not int for s in starts) or starts[0] != 0 or starts[-1] > length:
        return False
    return all(a <= b for a, b in zip(starts, starts[1:], strict=False))


def _main(argv: list[str]) -> int:
    import resource

    max_pages, max_chars, memory_mb, cpu_s = (int(a) for a in argv[1:5])
    memory = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    data = sys.stdin.buffer.read()
    try:
        result = extract(data, max_pages=max_pages, max_chars=max_chars)
    except MemoryError:
        result = _failed("memory")
    except Exception as exc:  # noqa: BLE001 — tệp hỏng kiểu gì cũng chỉ là "không đọc được"
        result = _failed(type(exc).__name__)
    sys.stdout.write(json.dumps(result.__dict__, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
