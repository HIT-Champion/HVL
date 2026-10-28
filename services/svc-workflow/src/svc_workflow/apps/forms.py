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

Lúc triển khai, form phải: là JSON Schema 2020-12 hợp lệ, lồng không quá ``MAX_DEPTH`` tầng; ``type: object``,
``additionalProperties: false`` (mọi biến ghi vào quy trình đều được khai); tên trường dạng camelCase, không trùng biến
hệ thống; giá trị là một giá trị đơn (biến Flowable); ``$ref`` chỉ trỏ trong chính tệp (không tải gì từ ngoài);
``format`` chỉ ``date``, ``uuid`` — hai định dạng cả trình duyệt lẫn máy chủ cùng kiểm; không có ``patternProperties``,
``propertyNames``; ``pattern`` không dễ quay lui bùng nổ, có ``maxLength`` cạnh nó khi thời gian kiểm tăng theo độ dài
chuỗi (``pattern_problem``), cả form cộng lại không quá ``MAX_FORM_STEPS``. Lúc kiểm dữ liệu, chuỗi dài quá
``maxLength`` không chạy ``pattern`` (``AppValidator``). Tệp sai kiểu ở đâu cũng thành câu lỗi, không ném ngoại lệ.

Trình dựng form của Văn phòng điện tử (#303) chép các luật lúc cài sang trình duyệt (``apps/office/app/utils/
formRules.ts``, trừ ``pattern`` và meta-schema); hai bên chạy chung ``tests/app_form_rules.cases.json``, kể cả các
hằng số dưới đây. Sửa luật thì sửa cả hai nơi.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator
from datetime import date
from re import _constants as sre
from re import _parser as sre_parse
from typing import Any
from urllib.parse import unquote

from jsonschema import Draft202012Validator, validators

from ..schemas import FormSchema, SchemaFileError

DRAFT = "https://json-schema.org/draft/2020-12/schema"
# biến hệ thống svc-workflow đặt lúc bắt đầu quy trình, lấy từ token; form không khai được, client không ghi đè được
RESERVED = ("tenantId", "departmentId", "initiator")
# Flowable 8 giải các tên này trong biểu thức của BPMN (điều kiện rẽ nhánh) thành giá trị của động cơ trước khi tìm biến
# (VariableContainerELResolver, ProcessVariableScopeELResolver; task: khi biểu thức chạy trên một việc)
ENGINE_NAMES = ("execution", "task", "authenticatedUserId", "currentTenantId")
VARIABLE = re.compile(r"[a-z][A-Za-z0-9]{0,63}", re.ASCII)
SCALAR_TYPES = {"string", "integer", "number", "boolean", "null"}
FORMATS = {"date", "uuid"}
DATE_RULES = {"not-after-today", "not-before-today"}
MAX_FORM_BYTES = 256 * 1024
# Tầng đối tượng, mảng lồng nhau trong tệp form: form thật chỉ vài tầng. Trần thấp để json.loads và các hàm đi đệ quy
# dưới đây (_walk; _cost, mỗi $ref thêm tối đa MAX_DEPTH khung) không chạm giới hạn đệ quy của Python
MAX_DEPTH = 32
LONG = (-(2**63), 2**63 - 1)    # biến kiểu long của Flowable

# ``pattern`` chạy bằng ``re`` (quay lui) ngay trong vòng sự kiện của svc-workflow lúc kiểm dữ liệu gửi lên, và ``re``
# giữ GIL: một mẫu quay lui bùng nổ (ReDoS, vd ``^(a+)+$``) với vài chục ký tự làm đứng cả dịch vụ, kể cả Action của
# Văn phòng điện tử. Lúc triển khai không nhận mẫu tốn thời gian mũ: lặp lồng trong lặp (trừ lặp đúng n lần như
# ``(,[0-9]{3})*``), lựa chọn ``|`` hay tham chiếu ngược trong phần lặp. Phần lặp nối nhau vẫn tốn thời gian đa thức
# (``^a{0,30}…a{0,30}$``), và jsonschema kiểm bằng re.search: mẫu không neo ``^`` thử lại ở mọi vị trí, ``a+$`` đã tốn
# bình phương độ dài chuỗi. Nên ước lượng số bước quay lui = tích (high - low + 1) của các phần lặp không cố định, số
# nhánh của mỗi ``|``, nhân L cho mỗi phần lặp không chặn trên và thêm L nếu không neo ``^``, với L = ``maxLength`` cạnh
# ``pattern`` (bắt buộc khi số bước tăng theo L), rồi chặn trên MAX_STEPS. Đo với re: 10^7 bước khoảng 30 ms
MAX_PATTERN = 512
MAX_STEPS = 10**7
# Mọi pattern của một form chạy trong cùng một lần gửi: cộng lại cũng có trần, khoảng 100 ms
MAX_FORM_STEPS = 3 * 10**7
REPEATS = (sre.MAX_REPEAT, sre.MIN_REPEAT, sre.POSSESSIVE_REPEAT)
# Chỗ có schema con trong JSON Schema 2020-12, để cộng chi phí pattern theo đúng đường jsonschema đi; $defs chỉ tính
# qua $ref (mỗi chỗ trỏ tới một lần)
SUBSCHEMA = ("not", "if", "then", "else", "items", "contains", "additionalProperties", "propertyNames",
             "unevaluatedItems", "unevaluatedProperties")
SUBSCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
SUBSCHEMA_MAPS = ("properties", "patternProperties", "dependentSchemas")
MAX_REF_DEPTH = 16
# jsonschema đi qua một schema con mất khoảng 7 µs, cỡ 2300 bước của re: tính mỗi nút 3000 bước, để $ref lồng nhau
# (allOf mười $ref tới tầng sau, tầng sau lại thế) không qua được trần dù không có pattern nào
NODE_STEPS = 3000
# Đổi chỗ "#/…" trỏ tới (jsonschema giải $ref theo $id gần nhất) hay đặt tên cho $ref: chỉ khai ở gốc form
ROOT_ONLY = ("$id", "$anchor", "$dynamicAnchor", "$recursiveAnchor")


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float))


def _one_of(value: Any, allowed: set[str]) -> bool:
    """``value`` là một chuỗi trong ``allowed``. Đối tượng, mảng thì sai, không để ``in`` của set ném TypeError."""
    return isinstance(value, str) and value in allowed


def _depth(value: Any) -> int:
    """Số tầng đối tượng, mảng lồng nhau của một giá trị JSON; đi bằng vòng lặp, không đệ quy."""
    deepest, stack = 0, [(value, 1)]
    while stack:
        node, level = stack.pop()
        children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else None
        if children is not None:
            deepest = max(deepest, level)
            stack.extend((child, level + 1) for child in children)
    return deepest


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


def _pattern_within_length(validator: Any, pattern: str, instance: Any, schema: dict[str, Any]) -> Iterator[Any]:
    """``pattern`` của jsonschema, trừ chuỗi dài hơn ``maxLength`` cạnh nó: không chạy mẫu (``maxLength`` đã báo lỗi),
    để L mà ``pattern_problem`` dùng ước lượng cũng là chặn trên của chuỗi thật sự đưa vào re."""
    limit = schema.get("maxLength")
    if isinstance(instance, str) and isinstance(limit, int) and len(instance) > limit:
        return
    yield from Draft202012Validator.VALIDATORS["pattern"](validator, pattern, instance, schema)


AppValidator = validators.extend(Draft202012Validator, {"pattern": _pattern_within_length})


class AppForm:
    """Một form đã kiểm. errors() trả {} khi dữ liệu hợp lệ."""

    def __init__(self, schema: dict[str, Any]) -> None:
        # SchemaFileError nếu không phải JSON Schema 2020-12 hợp lệ
        self._schema = FormSchema(schema, validator=AppValidator)
        self.schema = schema
        self.fields: tuple[str, ...] = tuple(schema.get("properties") or {})
        self.required: frozenset[str] = frozenset(schema.get("required") or ())
        self._ranges = [(pair[0], pair[1]) for pair in schema.get("x-moc-range") or ()]

    def errors(self, data: Any, today: date | None = None) -> dict[str, str]:
        # Giá trị lồng (mảng, đối tượng) không bao giờ ghi được thành biến: báo ``type`` ngay, không đưa vào schema, để
        # items, properties… không chạy pattern một lần cho mỗi phần tử — trần chi phí lúc cài tính cho giá trị đơn
        if not isinstance(data, dict):
            return {"": "type"}
        nested = {name: "type" for name, value in data.items() if isinstance(value, (dict, list))}
        if nested:
            return nested
        found = self._schema.errors(data, today)
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


def _risky(items: Any, in_repeat: bool, repeats: list[tuple[int, int]], branches: list[int]) -> str | None:
    """Chỗ dễ quay lui bùng nổ đầu tiên trong mẫu đã phân tích (``re._parser``), không có thì None. ``in_repeat``: đang
    ở trong một phần lặp nhiều hơn một lần; ``repeats`` gom (low, high) của các phần lặp không cố định, ``branches`` số
    nhánh của mỗi ``|``."""
    for op, av in items:
        found = None
        if op in REPEATS:
            low, high, sub = av
            if in_repeat and low != high:
                return "lặp lồng trong một phần lặp"
            if low != high:
                repeats.append((low, high))
            found = _risky(sub, in_repeat or high > 1, repeats, branches)
        elif op == sre.BRANCH:
            if in_repeat:
                return "lựa chọn (|) trong một phần lặp"
            branches.append(len(av[1]))
            found = next((r for alt in av[1] if (r := _risky(alt, in_repeat, repeats, branches))), None)
        elif op in (sre.GROUPREF, sre.GROUPREF_EXISTS):
            return "tham chiếu ngược tới nhóm"
        elif op == sre.SUBPATTERN:
            found = _risky(av[3], in_repeat, repeats, branches)
        elif op in (sre.ASSERT, sre.ASSERT_NOT):
            found = _risky(av[1], in_repeat, repeats, branches)
        elif op == sre.ATOMIC_GROUP:
            found = _risky(av, in_repeat, repeats, branches)
        if found:
            return found
    return None


def _anchored(parsed: Any) -> bool:
    """Mẫu mở đầu bằng ``^`` (không cờ m) hoặc ``\\A``: re.search chỉ thử ở đầu chuỗi."""
    if not len(parsed) or parsed[0][0] != sre.AT:
        return False
    at = parsed[0][1]
    return at == sre.AT_BEGINNING_STRING or (at == sre.AT_BEGINNING and not parsed.state.flags & re.MULTILINE)


def _power(n: int) -> str:
    """12345678 → '1,2·10^7'."""
    e = len(str(n)) - 1
    return f"{n / 10**e:.1f}".replace(".", ",") + f"·10^{e}"


def pattern_problem(pattern: str, max_length: int | None = None) -> str | None:
    """Vì sao không nhận ``pattern`` này lúc triển khai (tiếng Việt), nhận được thì None. ``max_length``: ``maxLength``
    cạnh ``pattern`` trong schema, None nếu không khai."""
    return pattern_cost(pattern, max_length)[0]


def pattern_cost(pattern: str, max_length: int | None = None) -> tuple[str | None, int]:
    """(lý do không nhận hoặc None, số bước quay lui ước lượng) — như ``pattern_problem``, kèm số bước để cộng cả
    form."""
    if len(pattern) > MAX_PATTERN:
        return f"dài quá {MAX_PATTERN} ký tự", 0
    try:
        parsed = sre_parse.parse(pattern)
    except (re.error, RecursionError, OverflowError) as exc:
        return f"không phải biểu thức chính quy hợp lệ ({exc})", 0
    repeats: list[tuple[int, int]] = []
    branches: list[int] = []
    found = _risky(parsed, False, repeats, branches)
    if found:
        return found, 0
    if not repeats and not branches:
        return None, 1          # không có chỗ nào để quay lui: re quét chuỗi một lượt
    steps = math.prod(high - low + 1 for low, high in repeats if high != sre.MAXREPEAT) * math.prod(branches)
    grows = sum(high == sre.MAXREPEAT for _, high in repeats) + (0 if _anchored(parsed) else 1)
    if grows:
        if max_length is None:
            return ("thời gian kiểm tăng theo độ dài chuỗi (không neo ^ hoặc có phần lặp không chặn trên): cần "
                    "maxLength ngay cạnh pattern"), 0
        steps *= max_length**grows
    if steps > MAX_STEPS:
        return (f"ước tính {_power(steps)} bước quay lui" + (f" với chuỗi {max_length} ký tự" if grows else "")
                + f", tối đa {_power(MAX_STEPS)}: bớt phần lặp không cố định hay nhánh |, neo ^"
                + (", giảm maxLength" if grows else "")), steps
    return None, steps


def _bound(max_length: Any) -> int | None:
    return max_length if isinstance(max_length, int) and not isinstance(max_length, bool) else None


def _check_pattern(pattern: Any, where: str, errors: list[str], max_length: Any = None) -> None:
    if not isinstance(pattern, str):
        return
    problem = pattern_problem(pattern, _bound(max_length))
    if problem:
        shown = pattern if len(pattern) <= 60 else pattern[:60] + "…"
        errors.append(f"{where}: pattern {shown!r}: {problem} — máy chủ kiểm bằng re (quay lui), mẫu như vậy có thể "
                      "làm đứng dịch vụ (ReDoS)")


def _walk(node: Any, where: str, errors: list[str], schema: bool = True, root: bool = True) -> None:
    """``schema``: đang ở trong schema; dưới ``x-moc-*`` (câu chữ cho giao diện) khóa ``pattern`` là tên lỗi, không phải
    mẫu. ``root``: đang ở gốc form."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ROOT_ONLY and schema and not root:
                errors.append(f"{where}: {key} chỉ khai ở gốc form — dưới gốc nó đổi chỗ $ref trỏ tới")
            elif key == "$ref" and isinstance(value, str) and not value.startswith("#"):
                errors.append(f"{where}: $ref {value!r} trỏ ra ngoài tệp — chỉ được trỏ trong chính form (#/…)")
            elif key in ("$dynamicRef", "$recursiveRef"):
                errors.append(f"{where}: không dùng {key}")
            elif key == "format" and isinstance(value, str) and value not in FORMATS:
                errors.append(f"{where}: format {value!r} chưa hỗ trợ (chỉ {', '.join(sorted(FORMATS))})")
            elif key == "pattern" and schema:
                _check_pattern(value, where, errors, node.get("maxLength"))
            elif key in ("patternProperties", "propertyNames") and schema:
                errors.append(f"{where}: không dùng {key} — mẫu chạy trên mọi khóa gửi lên, kể cả khóa thừa; khai từng "
                              "trường trong properties")
            _walk(value, where, errors, schema and not key.startswith("x-moc"), False)
    elif isinstance(node, list):
        for value in node:
            _walk(value, where, errors, schema, False)


class RefProblem(Exception):
    pass


def _resolve(root: dict[str, Any], ref: str) -> Any:
    """``#/…`` (JSON Pointer) trong chính form → schema đích; trỏ không tới đâu thì RefProblem."""
    if ref != "#" and not ref.startswith("#/"):
        raise RefProblem(f"$ref {ref!r}: chỉ nhận JSON Pointer trong chính form (#/…)")
    node: Any = root
    for part in ref[2:].split("/") if ref != "#" else ():
        part = unquote(part).replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            raise RefProblem(f"$ref {ref!r} không trỏ tới schema nào trong form")
    return node


def form_steps(schema: dict[str, Any]) -> int:
    """Số bước ước lượng khi kiểm một lần gửi (giá trị đơn): ``NODE_STEPS`` cho mỗi schema jsonschema đi qua, cộng số
    bước quay lui của pattern ở đó. Đích một ``$ref`` trỏ bao nhiêu chỗ tính bấy nhiêu lần, như jsonschema chạy; lúc cài
    mỗi đích chỉ đi qua một lần. $ref vòng hay lồng quá ``MAX_REF_DEPTH`` tầng → RefProblem."""
    return _cost(schema, schema, (), {})[0]


def _subschemas(node: dict[str, Any]) -> Iterator[Any]:
    for key in SUBSCHEMA:
        yield node.get(key)
    for key in SUBSCHEMA_LISTS:
        yield from node[key] if isinstance(node.get(key), list) else ()
    for key in SUBSCHEMA_MAPS:
        yield from node[key].values() if isinstance(node.get(key), dict) else ()


def _cost(node: Any, root: dict[str, Any], refs: tuple[int, ...], memo: dict[int, tuple[int, int]]) -> tuple[int, int]:
    """(số bước, số tầng $ref sâu nhất bên dưới) của ``node``. ``refs``: các đích $ref đang đi qua, ``memo``: kết quả
    theo đích — khóa là chính đích (id), nên hai cách viết cùng một JSON Pointer không bị tính hai lần."""
    if not isinstance(node, dict):
        return 0, 0
    steps, depth = NODE_STEPS, 0
    if isinstance(node.get("pattern"), str):
        steps += pattern_cost(node["pattern"], _bound(node.get("maxLength")))[1]
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#"):           # trỏ ra ngoài tệp: _walk đã báo
        target = _resolve(root, ref)
        if id(target) in refs or len(refs) >= MAX_REF_DEPTH:
            raise RefProblem(f"$ref {ref!r} trỏ vòng hoặc lồng quá {MAX_REF_DEPTH} tầng")
        if id(target) not in memo:
            memo[id(target)] = _cost(target, root, (*refs, id(target)), memo)
        sub_steps, sub_depth = memo[id(target)]
        if len(refs) + 1 + sub_depth > MAX_REF_DEPTH:      # đích đã tính từ chỗ nông hơn, chỗ này lồng sâu hơn
            raise RefProblem(f"$ref {ref!r} trỏ vòng hoặc lồng quá {MAX_REF_DEPTH} tầng")
        steps, depth = steps + sub_steps, sub_depth + 1
    for sub in _subschemas(node):
        sub_steps, sub_depth = _cost(sub, root, refs, memo)
        steps, depth = steps + sub_steps, max(depth, sub_depth)
    return steps, depth


def check_form(where: str, raw: bytes) -> tuple[AppForm | None, list[str]]:
    """Nội dung một tệp form → (form, []) hoặc (None, lỗi tiếng Việt, mỗi lỗi mở đầu bằng ``where``)."""
    if len(raw) > MAX_FORM_BYTES:
        return None, [f"{where}: tệp lớn quá {MAX_FORM_BYTES // 1024} KB"]
    try:
        schema = json.loads(raw.decode("utf-8"))
    except RecursionError:
        return None, [f"{where}: JSON lồng quá {MAX_DEPTH} tầng"]
    except (UnicodeDecodeError, ValueError) as exc:
        return None, [f"{where}: không phải JSON UTF-8 ({exc})"]
    if _depth(schema) > MAX_DEPTH:
        return None, [f"{where}: JSON lồng quá {MAX_DEPTH} tầng"]
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
        elif name in ENGINE_NAMES:
            errors.append(f"{where}: trường {name} trùng tên Flowable dành sẵn trong biểu thức "
                          f"({', '.join(ENGINE_NAMES)}) — điều kiện của BPMN không đọc được giá trị gửi lên")
        elif not VARIABLE.fullmatch(name):
            errors.append(f"{where}: tên trường {name!r} phải dạng camelCase (chữ thường đầu, chỉ chữ và số, "
                          "≤ 64 ký tự) — là tên biến Flowable")
        if not isinstance(prop, dict):
            errors.append(f"{where}: trường {name} phải là một schema (đối tượng)")
            continue
        types = prop.get("type", [])
        if not all(_one_of(t, SCALAR_TYPES) for t in (types if isinstance(types, list) else [types])):
            errors.append(f"{where}: trường {name}: chỉ nhận giá trị đơn (string, integer, number, boolean) — biến "
                          "Flowable không chứa đối tượng, mảng")
        if isinstance(prop.get("enum"), list) and not all(_scalar(v) for v in prop["enum"]):
            errors.append(f"{where}: trường {name}: enum chỉ gồm giá trị đơn")
        if "x-moc-date" in prop and not _one_of(prop["x-moc-date"], DATE_RULES):
            errors.append(f"{where}: trường {name}: x-moc-date chỉ nhận {', '.join(sorted(DATE_RULES))}")
    required = schema.get("required", [])
    if not isinstance(required, list):
        errors.append(f"{where}: required phải là danh sách tên trường")
    elif missing := [r for r in required if not (isinstance(r, str) and r in props)]:
        errors.append(f"{where}: required có trường không khai trong properties: {', '.join(map(str, missing))}")
    ranges = schema.get("x-moc-range", [])
    dates = {name for name, prop in props.items() if isinstance(prop, dict) and prop.get("format") == "date"}
    if not isinstance(ranges, list) or not all(
            isinstance(p, list) and len(p) == 2 and p[0] != p[1] and all(_one_of(f, dates) for f in p) for p in ranges):
        errors.append(f"{where}: x-moc-range phải là danh sách cặp [trường trước, trường sau], hai trường đã khai "
                      "trong properties với format: date (như bộ kiểm form trên trình duyệt)")
    _walk(schema, where, errors)
    try:
        steps = form_steps(schema)
    except RefProblem as exc:
        errors.append(f"{where}: {exc}")
    else:
        if steps > MAX_FORM_STEPS:
            errors.append(f"{where}: kiểm một lần gửi ước tính {_power(steps)} bước (pattern cộng mỗi schema con "
                          f"{NODE_STEPS} bước, mỗi chỗ $ref tính một lần), tối đa {_power(MAX_FORM_STEPS)}")
    if errors:
        return None, errors
    try:
        return AppForm(schema), []
    except SchemaFileError as exc:
        return None, [f"{where}: {exc}"]
