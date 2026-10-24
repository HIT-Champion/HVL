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

"""Đọc tệp dữ liệu của lô nạp: NDJSON hoặc CSV, UTF-8.

Không tự sửa dữ liệu (khoảng trắng, NFC) — như Action và CSDL (schemas/README.md): ứng dụng khác gọi API cũng phải gửi
dữ liệu sạch, dòng sai thành ``failed`` kèm lỗi theo trường ở bước xử lý. Ở đây chỉ bắt điều làm một dòng không đọc
được (JSON sai, thiếu ô…) — thành dòng ``failed`` ngay lúc tạo lô, các dòng khác vẫn chạy — và điều làm cả tệp không
đọc được (không phải UTF-8, CSV hỏng ngoặc kép, tiêu đề sai…) — ``ParseError``, không tạo lô.

- NDJSON: mỗi dòng một object JSON; số dòng là dòng vật lý tính từ 1, dòng trống bỏ qua nhưng vẫn đếm.
- CSV: dấu phẩy, dòng tiêu đề bắt buộc; số dòng như hàng của Excel (tiêu đề là 1, bản ghi đầu là 2, ô nhiều dòng trong
  ngoặc kép vẫn là một hàng). Ô trống thì bỏ khóa (mặc định của schema áp); cột kiểu đúng/sai nhận ``true``/``false``;
  cột danh sách (``files``, ``file_ids``) cách nhau bằng ``;``.
- ``files``: tên tệp trong zip đính kèm, tệp đầu là bản chính; tách khỏi dữ liệu, chuẩn hóa NFC để khớp tên mục zip.
- Cột kiểu đúng/sai (``restricted``) kiểm chặt ngay ở đây, trước khi tệp nào vào kho: giá trị quyết định tệp được lưu mã
  hóa hay bản rõ (F3.7), nên ``"yes"``, ``"1"``, ``"có"``, ``null``… là dòng ``bad_value``, không để Action báo sau
  khi tệp đã nằm trong kho ở dạng bản rõ. Các trường khác vẫn do Action kiểm; dòng bị từ chối thì vòng nền gỡ tệp đã
  lưu cho dòng (runner.py).
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

Format = Literal["ndjson", "csv"]

LINE_MAX = 64 * 1024        # byte của một dòng NDJSON
MAX_FILES = 20              # tệp đính kèm mỗi dòng — bằng maxItems của file_ids (schemas/van-ban-den.json)
NAME_MAX = 255
# cấp lồng tối đa của một dòng: văn bản đến là dữ liệu phẳng; jsonb lồng hàng nghìn cấp làm PostgreSQL báo "stack depth
# limit exceeded" và hỏng cả mutation tạo lô
MAX_DEPTH = 32
LIST_SEP = ";"
FILES = "files"
_SYNTAX = re.compile(r'["\[\]{}]')            # ngoài chuỗi: dấu mở chuỗi, ngoặc
# phần còn lại của một chuỗi JSON sau dấu " mở: ký tự thường hay cặp thoát (\", \\…), tới hết dấu " đóng hoặc hết dòng.
# Lặp chiếm hữu (*+) và chỉ khớp từ đúng một vị trí: không quay lui, tuyến tính theo độ dài chuỗi
_STRING_REST = re.compile(r'(?:[^"\\]|\\.)*+"?', re.DOTALL)
_SURROGATE = re.compile("[\ud800-\udfff]")

EXTENSIONS: dict[str, Format] = {".ndjson": "ndjson", ".jsonl": "ndjson", ".csv": "csv"}
CONTENT_TYPES: dict[str, Format] = {
    "application/x-ndjson": "ndjson", "application/ndjson": "ndjson", "application/jsonl": "ndjson",
    "application/x-jsonlines": "ndjson", "text/csv": "csv", "application/csv": "csv",
}


class ParseError(Exception):
    """Cả tệp không đọc được: trả mã HTTP, mã lỗi, lời nhắn; không tạo lô."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Columns:
    """Đặc tả cột của một loại lô. NDJSON chuyển nguyên mọi khóa (trừ ``files``) để bước ghi báo khóa lạ theo trường;
    CSV kiểm tiêu đề: thiếu cột bắt buộc hay có cột lạ là sai cả tệp."""

    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    booleans: frozenset[str] = frozenset()
    lists: frozenset[str] = frozenset()

    @property
    def allowed(self) -> frozenset[str]:
        return frozenset((*self.required, *self.optional, FILES))


@dataclass
class Row:
    line: int
    data: dict[str, Any] | None         # None: dòng hỏng lúc đọc
    files: list[str] = field(default_factory=list)
    code: str | None = None
    message: str | None = None

    @property
    def failed(self) -> bool:
        return self.code is not None

    def fail(self, code: str, message: str) -> None:
        self.data, self.code, self.message = None, code, message


def _failed(line: int, code: str, message: str) -> Row:
    return Row(line, None, code=code, message=message)


def guess_format(explicit: str | None, filename: str | None, content_type: str | None) -> Format:
    """Định dạng theo tham số ``format``, không có thì theo đuôi tên tệp, rồi theo Content-Type của phần tệp."""
    if explicit:
        if explicit not in ("ndjson", "csv"):
            raise ParseError(400, "unknown_format", "format chỉ nhận ndjson hoặc csv")
        return explicit  # type: ignore[return-value]
    name = (filename or "").lower()
    for ext, fmt in EXTENSIONS.items():
        if name.endswith(ext):
            return fmt
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in CONTENT_TYPES:
        return CONTENT_TYPES[mime]
    raise ParseError(400, "unknown_format", "Không biết định dạng tệp: đặt đuôi .ndjson, .jsonl, .csv hoặc tham số "
                     "format=ndjson|csv")


def decode(raw: bytes) -> str:
    """UTF-8; BOM ở đầu tệp (Excel lưu CSV UTF-8 hay có) thì bỏ."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError(400, "bad_encoding", f"Tệp không phải UTF-8 (byte thứ {exc.start + 1}) — lưu lại tệp với "
                         "bảng mã UTF-8") from None
    return text.removeprefix("\ufeff")


def parse(raw: bytes, fmt: Format, columns: Columns, *, max_rows: int) -> list[Row]:
    text = decode(raw)
    rows = _ndjson(text, columns, max_rows) if fmt == "ndjson" else _csv(text, columns, max_rows)
    if not rows:
        raise ParseError(400, "empty", "Tệp không có dòng dữ liệu nào")
    return rows


def _too_many(max_rows: int) -> ParseError:
    return ParseError(413, "too_many_rows", f"Tệp có hơn {max_rows} dòng dữ liệu — chia thành nhiều lô")


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} không phải giá trị JSON")


def _has_text(value: Any, pattern: re.Pattern[str]) -> bool:
    """Có chuỗi (khóa hay giá trị, mọi cấp) khớp ``pattern`` — gọi sau ``_too_deep`` nên đệ quy không quá MAX_DEPTH."""
    if isinstance(value, str):
        return pattern.search(value) is not None
    if isinstance(value, dict):
        return any(_has_text(k, pattern) or _has_text(v, pattern) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_text(v, pattern) for v in value)
    return False


_NUL = re.compile("\x00")


def _has_nul(value: Any) -> bool:
    """PostgreSQL không lưu được U+0000 trong jsonb: một dòng như vậy làm hỏng cả mutation tạo lô."""
    return _has_text(value, _NUL)


def _has_nonfinite(value: Any) -> bool:
    """Số tràn (``1e999`` → ``inf``): ``json.loads`` nhận nhưng JSON không có inf — HasuraClient (httpx2,
    ``allow_nan=False``) không gửi được mutation tạo lô, cả yêu cầu lỗi 500. Gọi sau ``_too_deep`` như ``_has_text``."""
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_has_nonfinite(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_nonfinite(v) for v in value)
    return False


def _nests_deeper(text: str, limit: int) -> bool:
    """Một dòng JSON lồng ``[``/``{`` quá ``limit`` cấp — đếm ngoặc ngoài chuỗi, trước khi ``json.loads``.

    Bộ đọc JSON của Python đệ quy theo cấp lồng: dòng lồng vài nghìn cấp làm Python 3.13 ném RecursionError (3.14 thì
    đọc được), nên kiểm ở đây để kết quả như nhau trên mọi bản Python. Dòng có ít ngoặc (gần như mọi dòng) không phải
    duyệt.

    Duyệt một lượt từ trái sang phải, nhảy qua nội dung từng chuỗi (kể cả ``\\"``, ``\\\\``): thời gian tuyến tính
    theo độ dài dòng với mọi đầu vào. Không dùng regex xóa chuỗi trên cả dòng: với chuỗi không đóng chứa nhiều ``\\"``,
    regex đó thử lại từ từng dấu nháy tới cuối dòng (bậc hai — dòng 64 KiB mất hơn 10 giây, giữ GIL nên cả svc-files
    đứng). Chuỗi không đóng thì phần sau nó không đếm: ``json.loads`` dừng ở chính chuỗi đó, không đệ quy sâu hơn."""
    if text.count("[") + text.count("{") <= limit:
        return False
    depth, pos = 0, 0
    while (found := _SYNTAX.search(text, pos)) is not None:
        char, pos = found.group(), found.end()
        if char == '"':
            rest = _STRING_REST.match(text, pos)        # luôn khớp: lặp có thể rỗng
            pos = rest.end() if rest else pos
        elif char in "[{":
            depth += 1
            if depth > limit:
                return True
        else:
            depth -= 1
    return False


def _too_deep(value: Any) -> bool:
    """Lồng quá MAX_DEPTH cấp — duyệt bằng ngăn xếp, không đệ quy."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, dict | list):
            if depth > MAX_DEPTH:
                return True
            stack.extend((child, depth + 1) for child in (item.values() if isinstance(item, dict) else item))
    return False


def _files(value: Any) -> list[str] | str:
    """Tên tệp trong zip của một dòng (chuẩn hóa NFC); sai thì trả lời nhắn."""
    if not isinstance(value, list) or not all(isinstance(v, str) and 0 < len(v) <= NAME_MAX for v in value):
        return f"{FILES} phải là danh sách tên tệp trong tệp nén, mỗi tên 1–{NAME_MAX} ký tự"
    names = [unicodedata.normalize("NFC", v) for v in value]
    if len(names) > MAX_FILES:
        return f"Mỗi dòng tối đa {MAX_FILES} tệp đính kèm"
    if len(set(names)) != len(names):
        return f"{FILES} có tên tệp lặp lại"
    if any("\x00" in n for n in names):
        return f"{FILES} có ký tự NUL"
    return names


def _row(line: int, obj: dict[str, Any], columns: Columns) -> Row:
    if _too_deep(obj):
        return _failed(line, "bad_value", f"Dòng lồng quá {MAX_DEPTH} cấp")
    if _has_text(obj, _SURROGATE):
        # "\ud800" lẻ: json.loads nhận nhưng không mã hóa lại được thành UTF-8 — không chặn ở đây thì cả yêu cầu lỗi 500
        return _failed(line, "bad_value", "Dòng có ký tự thay thế lẻ (\\ud800–\\udfff) — không phải văn bản Unicode "
                       "hợp lệ, không lưu được")
    if _has_nonfinite(obj):
        return _failed(line, "bad_value", "Dòng có số vượt giới hạn số thực (vd 1e999) — không lưu được")
    data = dict(obj)
    files: list[str] = []
    if FILES in data:
        got = _files(data.pop(FILES))
        if isinstance(got, str):
            return _failed(line, "bad_files", got)
        files = got
    if files and "file_ids" in data and not isinstance(data["file_ids"], list):
        return _failed(line, "bad_files", "file_ids phải là danh sách khi dòng có files")
    if _has_nul(data):
        return _failed(line, "bad_value", "Dòng có ký tự NUL (U+0000) — không lưu được")
    for name in sorted(columns.booleans):
        if name in data and not isinstance(data[name], bool):
            return _failed(line, "bad_value", f"{name} chỉ nhận true hoặc false, nhận {_shown(data[name])} — dòng chưa "
                           "ghi, chưa lưu tệp nào")
    return Row(line, data, files)


def _shown(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 40 else text[:39] + "…"


def _ndjson(text: str, columns: Columns, max_rows: int) -> list[Row]:
    rows: list[Row] = []
    for line, raw in enumerate(text.split("\n"), 1):
        if not raw.strip(" \t\r"):
            continue
        if len(rows) == max_rows:
            raise _too_many(max_rows)
        if len(raw.encode()) > LINE_MAX:
            rows.append(_failed(line, "line_too_long", f"Dòng dài hơn {LINE_MAX // 1024} KiB"))
            continue
        if _nests_deeper(raw, MAX_DEPTH):
            rows.append(_failed(line, "bad_value", f"Dòng lồng quá {MAX_DEPTH} cấp"))
            continue
        try:
            obj = json.loads(raw, parse_constant=_reject_constant)
        except json.JSONDecodeError as exc:
            rows.append(_failed(line, "bad_json", f"Không phải JSON hợp lệ: {exc.msg} (cột {exc.colno})"))
            continue
        except ValueError as exc:       # NaN, Infinity
            rows.append(_failed(line, "bad_json", f"Không phải JSON hợp lệ: {exc}"))
            continue
        except RecursionError:      # đã kiểm cấp lồng ở trên; còn sót thì vẫn là lỗi giá trị như trần MAX_DEPTH
            rows.append(_failed(line, "bad_value", f"Dòng lồng quá sâu (quá {MAX_DEPTH} cấp)"))
            continue
        if not isinstance(obj, dict):
            rows.append(_failed(line, "not_object", "Mỗi dòng phải là một object JSON {…}"))
            continue
        rows.append(_row(line, obj, columns))
    return rows


def _header(record: list[str], columns: Columns) -> list[str]:
    names = [cell.strip() for cell in record]
    problems: list[str] = []
    missing = [c for c in columns.required if c not in names]
    if missing:
        problems.append("thiếu cột " + ", ".join(missing))
    unknown = [n for n in names if n not in columns.allowed]
    if unknown:
        problems.append("cột lạ " + ", ".join(repr(n) for n in unknown[:10]))
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        problems.append("cột lặp lại " + ", ".join(repeated))
    if problems:
        raise ParseError(400, "bad_header", "Dòng tiêu đề CSV sai: " + "; ".join(problems) + ". Cột dùng được: "
                         + ", ".join(sorted(columns.allowed)))
    return names


def _cell(name: str, value: str, columns: Columns) -> Any:
    if name in columns.booleans:
        return {"true": True, "false": False}.get(value.lower(), value)    # giá trị khác: _row báo bad_value
    if name == FILES or name in columns.lists:
        return [item.strip() for item in value.split(LIST_SEP) if item.strip()]
    return value


def _csv(text: str, columns: Columns, max_rows: int) -> list[Row]:
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    rows: list[Row] = []
    try:
        header = next(reader, None)
        if header is None:
            raise ParseError(400, "empty", "Tệp không có dòng dữ liệu nào")
        names = _header(header, columns)
        for line, record in enumerate(reader, 2):
            if not any(cell.strip() for cell in record):       # hàng trống (Excel hay để ở cuối)
                continue
            if len(rows) == max_rows:
                raise _too_many(max_rows)
            if len(record) != len(names):
                rows.append(_failed(line, "bad_line", f"Hàng có {len(record)} ô, tiêu đề có {len(names)} cột"))
                continue
            obj = {name: _cell(name, value, columns) for name, value in zip(names, record, strict=True) if value != ""}
            rows.append(_row(line, obj, columns))
    except csv.Error as exc:
        raise ParseError(400, "bad_format", f"CSV hỏng cấu trúc quanh dòng {reader.line_num}: {exc}") from None
    return rows
