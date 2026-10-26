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

"""Form của ứng dụng: JSON Schema 2020-12 khai trong manifest, tên trường là tên biến Flowable.

Kiểm dữ liệu bằng đúng ``schemas.FormSchema`` của Văn phòng điện tử (mã lỗi {trường: mã} như ``schemas/README.md``),
cộng một từ khóa riêng chỉ form của ứng dụng dùng: ``"x-moc-range": [["tuNgay", "denNgay"]]`` ở gốc, hai trường
``format: date`` — trường sau không được trước trường trước (so chuỗi YYYY-MM-DD đã qua ``format``), mã
``x-moc-range`` gắn vào trường sau. Kiểm sau mọi từ khóa khác; trường nào đã có lỗi hoặc không phải chuỗi thì không so.
Không thêm vào ``schemas.py`` để form của Văn phòng điện tử (Ajv biên dịch sẵn) không lệch với máy chủ.

Lúc triển khai, form phải: là JSON Schema 2020-12 hợp lệ; ``type: object``, ``additionalProperties: false`` (mọi biến
ghi vào quy trình đều được khai); tên trường dạng camelCase, không trùng biến hệ thống; giá trị là một giá trị đơn
(biến Flowable); ``$ref`` chỉ trỏ trong chính tệp (không tải gì từ ngoài); ``format`` chỉ ``date``, ``uuid`` — hai
định dạng cả trình duyệt lẫn máy chủ cùng kiểm; ``pattern`` (cả khóa của ``patternProperties``) không dễ quay lui bùng
nổ (``pattern_problem``).
"""

from __future__ import annotations

import json
import math
import re
from datetime import date
from re import _constants as sre
from re import _parser as sre_parse
from typing import Any

from ..schemas import FormSchema, SchemaFileError

DRAFT = "https://json-schema.org/draft/2020-12/schema"
# biến hệ thống svc-workflow đặt lúc bắt đầu quy trình, lấy từ token; form không khai được, client không ghi đè được
RESERVED = ("tenantId", "departmentId", "initiator")
VARIABLE = re.compile(r"[a-z][A-Za-z0-9]{0,63}", re.ASCII)
SCALAR_TYPES = {"string", "integer", "number", "boolean", "null"}
FORMATS = {"date", "uuid"}
DATE_RULES = {"not-after-today", "not-before-today"}
MAX_FORM_BYTES = 256 * 1024
LONG = (-(2**63), 2**63 - 1)    # biến kiểu long của Flowable

# ``pattern`` chạy bằng ``re`` (quay lui) ngay trong vòng sự kiện của svc-workflow lúc kiểm dữ liệu gửi lên, và ``re``
# giữ GIL: một mẫu quay lui bùng nổ (ReDoS, vd ``^(a+)+$``) với vài chục ký tự làm đứng cả dịch vụ, kể cả Action của
# Văn phòng điện tử. Lúc triển khai chỉ nhận mẫu không lặp lồng trong lặp (trừ lặp đúng n lần như ``(,[0-9]{3})*``),
# không có lựa chọn ``|`` hay tham chiếu ngược trong phần lặp, nhiều nhất một phần lặp dài (không chặn trên hoặc trên
# ``LONG_REPEAT`` lần). Đủ cho mẫu thường gặp: ``^20[0-9]{2}-``, lớp ký tự cấm, ``^[A-Z]{2,5}$``
MAX_PATTERN = 512
LONG_REPEAT = 32
REPEATS = (sre.MAX_REPEAT, sre.MIN_REPEAT, sre.POSSESSIVE_REPEAT)


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float))


def bad_value(value: Any) -> bool:
    """Giá trị không ghi được thành biến Flowable dù schema nhận: đối tượng, mảng, số không hữu hạn, số nguyên quá
    long."""
    if isinstance(value, (dict, list)):
        return True
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return not LONG[0] <= value <= LONG[1]
    return False


class AppForm:
    """Một form đã kiểm. errors() trả {} khi dữ liệu hợp lệ."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self._schema = FormSchema(schema)           # SchemaFileError nếu không phải JSON Schema 2020-12 hợp lệ
        self.schema = schema
        self.fields: tuple[str, ...] = tuple(schema.get("properties") or {})
        self.required: frozenset[str] = frozenset(schema.get("required") or ())
        self._ranges = [(pair[0], pair[1]) for pair in schema.get("x-moc-range") or ()]

    def errors(self, data: Any, today: date | None = None) -> dict[str, str]:
        found = self._schema.errors(data, today)
        if not isinstance(data, dict):
            return found
        for name, value in data.items():
            if name not in found and bad_value(value):
                found[name] = "type"
        for first, second in self._ranges:
            if first in found or second in found:
                continue
            a, b = data.get(first), data.get(second)
            if isinstance(a, str) and isinstance(b, str) and b < a:
                found[second] = "x-moc-range"
        return found

    def variables(self, data: dict[str, Any]) -> dict[str, Any]:
        """Dữ liệu đã kiểm → biến ghi vào quy trình: chỉ trường đã khai, có mặt và khác null."""
        return {name: data[name] for name in self.fields if data.get(name) is not None}


def _risky(items: Any, in_repeat: bool, long: list[int]) -> str | None:
    """Chỗ dễ quay lui bùng nổ đầu tiên trong mẫu đã phân tích (``re._parser``), không có thì None. ``in_repeat``: đang
    ở trong một phần lặp nhiều hơn một lần; ``long`` đếm phần lặp dài."""
    for op, av in items:
        found = None
        if op in REPEATS:
            low, high, sub = av
            if in_repeat and low != high:
                return "lặp lồng trong một phần lặp"
            if high > LONG_REPEAT:
                long.append(high)
            found = _risky(sub, in_repeat or high > 1, long)
        elif op == sre.BRANCH:
            if in_repeat:
                return "lựa chọn (|) trong một phần lặp"
            found = next((r for alt in av[1] if (r := _risky(alt, in_repeat, long))), None)
        elif op in (sre.GROUPREF, sre.GROUPREF_EXISTS):
            return "tham chiếu ngược tới nhóm"
        elif op == sre.SUBPATTERN:
            found = _risky(av[3], in_repeat, long)
        elif op in (sre.ASSERT, sre.ASSERT_NOT):
            found = _risky(av[1], in_repeat, long)
        elif op == sre.ATOMIC_GROUP:
            found = _risky(av, in_repeat, long)
        if found:
            return found
    return None


def pattern_problem(pattern: str) -> str | None:
    """Vì sao không nhận ``pattern`` này lúc triển khai (tiếng Việt), nhận được thì None."""
    if len(pattern) > MAX_PATTERN:
        return f"dài quá {MAX_PATTERN} ký tự"
    try:
        parsed = sre_parse.parse(pattern)
    except (re.error, RecursionError, OverflowError) as exc:
        return f"không phải biểu thức chính quy hợp lệ ({exc})"
    long: list[int] = []
    found = _risky(parsed, False, long)
    if found:
        return found
    if len(long) > 1:
        return f"có {len(long)} phần lặp dài (không chặn trên hoặc trên {LONG_REPEAT} lần), chỉ nhận một"
    return None


def _check_pattern(pattern: Any, where: str, errors: list[str]) -> None:
    if not isinstance(pattern, str):
        return
    problem = pattern_problem(pattern)
    if problem:
        shown = pattern if len(pattern) <= 60 else pattern[:60] + "…"
        errors.append(f"{where}: pattern {shown!r}: {problem} — máy chủ kiểm bằng re (quay lui), mẫu như vậy có thể "
                      "làm đứng dịch vụ (ReDoS)")


def _walk(node: Any, where: str, errors: list[str], schema: bool = True) -> None:
    """``schema``: đang ở trong schema; dưới ``x-moc-*`` (câu chữ cho giao diện) khóa ``pattern`` là tên lỗi, không phải
    mẫu."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and not value.startswith("#"):
                errors.append(f"{where}: $ref {value!r} trỏ ra ngoài tệp — chỉ được trỏ trong chính form (#/…)")
            elif key in ("$dynamicRef", "$recursiveRef"):
                errors.append(f"{where}: không dùng {key}")
            elif key == "format" and isinstance(value, str) and value not in FORMATS:
                errors.append(f"{where}: format {value!r} chưa hỗ trợ (chỉ {', '.join(sorted(FORMATS))})")
            elif key == "pattern" and schema:
                _check_pattern(value, where, errors)
            elif key == "patternProperties" and schema and isinstance(value, dict):
                for pattern in value:
                    _check_pattern(pattern, where, errors)
            _walk(value, where, errors, schema and not key.startswith("x-moc"))
    elif isinstance(node, list):
        for value in node:
            _walk(value, where, errors, schema)


def check_form(where: str, raw: bytes) -> tuple[AppForm | None, list[str]]:
    """Nội dung một tệp form → (form, []) hoặc (None, lỗi tiếng Việt, mỗi lỗi mở đầu bằng ``where``)."""
    if len(raw) > MAX_FORM_BYTES:
        return None, [f"{where}: tệp lớn quá {MAX_FORM_BYTES // 1024} KB"]
    try:
        schema = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return None, [f"{where}: không phải JSON UTF-8 ({exc})"]
    if not isinstance(schema, dict):
        return None, [f"{where}: cần một đối tượng JSON Schema ở gốc"]
    errors: list[str] = []
    if schema.get("$schema") != DRAFT:
        errors.append(f"{where}: $schema phải là {DRAFT}")
    if schema.get("type") != "object":
        errors.append(f"{where}: type ở gốc phải là object")
    if schema.get("additionalProperties") is not False:
        errors.append(f"{where}: cần additionalProperties: false — mọi biến ghi vào quy trình phải được khai")
    props = schema.get("properties")
    if not isinstance(props, dict) or not props:
        return None, [*errors, f"{where}: cần properties (ít nhất một trường)"]
    for name, prop in props.items():
        if name in RESERVED:
            errors.append(f"{where}: trường {name} trùng biến hệ thống ({', '.join(RESERVED)}) — lõi tự đặt từ token")
        elif not VARIABLE.fullmatch(name):
            errors.append(f"{where}: tên trường {name!r} phải dạng camelCase (chữ thường đầu, chỉ chữ và số, "
                          "≤ 64 ký tự) — là tên biến Flowable")
        if not isinstance(prop, dict):
            errors.append(f"{where}: trường {name} phải là một schema (đối tượng)")
            continue
        types = prop.get("type", [])
        if not set(types if isinstance(types, list) else [types]) <= SCALAR_TYPES:
            errors.append(f"{where}: trường {name}: chỉ nhận giá trị đơn (string, integer, number, boolean) — biến "
                          "Flowable không chứa đối tượng, mảng")
        if isinstance(prop.get("enum"), list) and not all(_scalar(v) for v in prop["enum"]):
            errors.append(f"{where}: trường {name}: enum chỉ gồm giá trị đơn")
        if "x-moc-date" in prop and prop["x-moc-date"] not in DATE_RULES:
            errors.append(f"{where}: trường {name}: x-moc-date chỉ nhận {', '.join(sorted(DATE_RULES))}")
    missing = [r for r in schema.get("required") or [] if r not in props]
    if missing:
        errors.append(f"{where}: required có trường không khai trong properties: {', '.join(map(str, missing))}")
    ranges = schema.get("x-moc-range", [])
    if not isinstance(ranges, list) or not all(
            isinstance(p, list) and len(p) == 2 and p[0] != p[1]
            and all(isinstance(props.get(f), dict) and props[f].get("format") == "date" for f in p) for p in ranges):
        errors.append(f"{where}: x-moc-range phải là danh sách cặp [trường trước, trường sau], hai trường đã khai "
                      "trong properties với format: date (như bộ kiểm form trên trình duyệt)")
    _walk(schema, where, errors)
    if errors:
        return None, errors
    try:
        return AppForm(schema), []
    except SchemaFileError as exc:
        return None, [f"{where}: {exc}"]
