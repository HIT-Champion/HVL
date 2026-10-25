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

"""Bộ đọc một TẬP CON của YAML, chỉ dùng thư viện chuẩn — cho manifest ứng dụng (`apps/<thư mục>/app.yaml`, `moc app
install`) và tệp bảng của `db/metadata`. Lệnh vận hành chạy ngay trong thư mục cài, nơi không có PyYAML.

Nhận: ánh xạ và danh sách khối (thụt lề bằng dấu cách), danh sách lồng ánh xạ (`- khóa: giá trị`), chuỗi không nháy,
nháy đơn ('' là một dấu nháy), nháy kép (\\" \\\\ \\n \\t \\uXXXX), số nguyên, số thực, true/false, null/~, ánh xạ và
danh sách dạng ngoặc (`{a: b, c: [d]}`, kéo sang nhiều dòng được), chú thích `#`, neo `&tên` và tham chiếu `*tên`.
Không nhận (báo lỗi kèm số dòng, không đoán): chuỗi nhiều dòng `|` `>`, thẻ `!…`, khóa gộp `<<`, nhiều tài liệu, tab
thụt lề, khóa trùng, yes/no/on/off (YAML 1.1 hiểu là bool, YAML 1.2 là chuỗi: viết true/false hoặc đặt trong nháy),
số có số 0 đứng đầu (YAML 1.1 hiểu là bát phân). Ngày giờ giữ là chuỗi (PyYAML đổi sang date).

    yaml_nho.loads(text) -> dict | list | giá trị
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

INT = re.compile(r"[-+]?[0-9]+")
FLOAT = re.compile(r"[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?")
AMBIGUOUS = {"yes", "no", "on", "off", "y", "n"}
NAME = re.compile(r"[A-Za-z0-9_-]+")
# Tham chiếu neo chép lại cả cây đã neo: neo lồng neo nở theo cấp số nhân ("YAML bomb"). Giới hạn tổng số nút sinh ra
# từ mọi tham chiếu trong một tài liệu — manifest thật chỉ vài chục
MAX_ALIAS_NODES = 10_000


class YamlError(ValueError):
    pass


def _size(value: Any) -> int:
    n, todo = 0, [value]
    while todo:
        v = todo.pop()
        n += 1
        if isinstance(v, dict):
            todo.extend(v.values())
        elif isinstance(v, list):
            todo.extend(v)
    return n


class _Anchors(dict):
    """Neo đã gặp; use() trả bản chép, trừ dần ngân sách nút."""

    budget = MAX_ALIAS_NODES

    def use(self, name: str, no: int) -> Any:
        self.budget -= _size(self[name])
        if self.budget < 0:
            raise YamlError(f"dòng {no}: tham chiếu neo sinh quá {MAX_ALIAS_NODES} nút (neo lồng neo?)")
        return copy.deepcopy(self[name])


@dataclass
class _Line:
    no: int
    indent: int
    text: str


def _strip_comment(raw: str, no: int) -> str:
    """Bỏ chú thích (# ở đầu hoặc sau khoảng trắng, ngoài nháy) và khoảng trắng cuối dòng."""
    quote = None
    i = 0
    while i < len(raw):
        c = raw[i]
        if quote == '"':
            if c == "\\":
                i += 1
            elif c == '"':
                quote = None
        elif quote == "'":
            if c == "'":
                if raw[i + 1:i + 2] == "'":
                    i += 1
                else:
                    quote = None
        elif c in "\"'" and (i == 0 or raw[i - 1] in " \t[{,:-"):
            quote = c
        elif c == "#" and (i == 0 or raw[i - 1] in " \t"):
            return raw[:i].rstrip()
        i += 1
    if quote:
        raise YamlError(f"dòng {no}: thiếu dấu {quote} đóng chuỗi (chuỗi nhiều dòng không được hỗ trợ)")
    return raw.rstrip()


def _balance(text: str) -> int:
    """Số ngoặc [ { còn mở (ngoài nháy) của một giá trị dạng một dòng."""
    depth, i, quote = 0, 0, None
    while i < len(text):
        c = text[i]
        if quote:
            if quote == '"' and c == "\\":
                i += 1
            elif c == quote:
                if quote == "'" and text[i + 1:i + 2] == "'":
                    i += 1
                else:
                    quote = None
        elif c in "\"'":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        i += 1
    return depth


def _flow_value(text: str) -> str | None:
    """Phần giá trị của dòng nếu nó mở đầu bằng [ hoặc { (sau `khóa:`, `-`, neo)."""
    rest = text
    while True:
        if rest == "-" or rest.startswith("- "):
            rest = rest[1:].strip()
            continue
        split = _split_key(rest) if rest else None
        if split is None:
            break
        rest = split[1]
    rest = re.sub(r"^&[A-Za-z0-9_-]+\s*", "", rest)
    return rest if rest[:1] in ("[", "{") else None


def _lines(text: str) -> list[_Line]:
    lines = _raw_lines(text)
    out: list[_Line] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        value = _flow_value(line.text)
        depth = _balance(value) if value else 0
        # […] hoặc {…} viết trên nhiều dòng (db/metadata có): nối các dòng sau vào cho tới khi đóng đủ ngoặc
        while depth > 0:
            i += 1
            if i >= len(lines):
                raise YamlError(f"dòng {line.no}: ngoặc [ hoặc {{ không đóng")
            line = _Line(line.no, line.indent, f"{line.text} {lines[i].text.strip()}")
            depth = _balance(_flow_value(line.text) or "")
        out.append(line)
        i += 1
    return out


def _raw_lines(text: str) -> list[_Line]:
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        if no == 1 and raw.startswith("﻿"):
            raw = raw[1:]
        body = raw.lstrip(" ")
        if body.startswith("\t") or (body and "\t" in raw[:len(raw) - len(body)]):
            raise YamlError(f"dòng {no}: thụt lề bằng tab — dùng dấu cách")
        text_ = _strip_comment(body, no)
        if not text_:
            continue
        if text_ in ("---", "...") and not out:
            continue
        if text_ in ("---", "..."):
            raise YamlError(f"dòng {no}: chỉ nhận một tài liệu YAML")
        out.append(_Line(no, len(raw) - len(body), text_))
    return out


def _split_key(text: str) -> tuple[str, str] | None:
    """`khóa: phần còn lại` ở ngữ cảnh khối → (khóa, phần còn lại); không phải dòng khóa thì None."""
    if text[0] in "\"'":
        end = _quoted_end(text, 0)
        if end is None:
            return None
        rest = text[end:]
        if rest == ":" or rest.startswith(": "):
            return _scalar_quoted(text[:end]), rest[1:].strip()
        return None
    if text[0] in "[{&*!|>%@`":
        return None
    for m in re.finditer(r":(?: |$)", text):
        key = text[:m.start()].strip()
        if key:
            return key, text[m.end():].strip()
    return None


def _quoted_end(text: str, start: int) -> int | None:
    q = text[start]
    i = start + 1
    while i < len(text):
        if q == '"' and text[i] == "\\":
            i += 2
            continue
        if text[i] == q:
            if q == "'" and text[i + 1:i + 2] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return None


def _scalar_quoted(token: str) -> str:
    if token[0] == "'":
        return token[1:-1].replace("''", "'")
    out, i, body = [], 0, token[1:-1]
    escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/", "r": "\r", "0": "\0", " ": " "}
    while i < len(body):
        c = body[i]
        if c == "\\":
            e = body[i + 1:i + 2]
            if e in escapes:
                out.append(escapes[e])
                i += 2
            elif e == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", body[i + 2:i + 6]):
                out.append(chr(int(body[i + 2:i + 6], 16)))
                i += 6
            else:
                raise YamlError(f"chuỗi nháy kép có thoát lạ \\{e}")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _plain(token: str, no: int) -> Any:
    t = token.strip()
    if t in ("", "~", "null", "Null", "NULL"):
        return None
    if t in ("true", "True", "TRUE"):
        return True
    if t in ("false", "False", "FALSE"):
        return False
    if t.lower() in AMBIGUOUS:
        raise YamlError(f"dòng {no}: {t!r} mập mờ (YAML 1.1 là bool) — viết true/false hoặc đặt trong nháy")
    if t[0] in "!|>%@`":
        raise YamlError(f"dòng {no}: cú pháp {t[0]!r} không được hỗ trợ")
    if t.startswith("<<"):
        raise YamlError(f"dòng {no}: khóa gộp << không được hỗ trợ")
    if INT.fullmatch(t):
        if len(t.lstrip("+-")) > 1 and t.lstrip("+-").startswith("0"):
            raise YamlError(f"dòng {no}: {t!r} có số 0 đứng đầu (YAML 1.1 hiểu là bát phân) — đặt trong nháy")
        return int(t)
    if FLOAT.fullmatch(t):
        return float(t)
    return t


class _Flow:
    """{…} và […] trên một dòng."""

    def __init__(self, text: str, no: int, anchors: _Anchors):
        self.s, self.i, self.no, self.anchors = text, 0, no, anchors

    def error(self, what: str) -> YamlError:
        return YamlError(f"dòng {self.no}: {what} (cột {self.i + 1})")

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i] == " ":
            self.i += 1

    def value(self, *, stop: str) -> Any:
        self.ws()
        if self.i >= len(self.s):
            raise self.error("thiếu giá trị")
        c = self.s[self.i]
        if c == "{":
            return self.mapping()
        if c == "[":
            return self.sequence()
        if c in "\"'":
            end = _quoted_end(self.s, self.i)
            if end is None:
                raise self.error("thiếu dấu nháy đóng")
            token, self.i = self.s[self.i:end], end
            return _scalar_quoted(token)
        if c == "*":
            m = NAME.match(self.s, self.i + 1)
            if not m or m.group() not in self.anchors:
                raise self.error("tham chiếu tới neo chưa có")
            self.i = m.end()
            return self.anchors.use(m.group(), self.no)
        start = self.i
        while self.i < len(self.s) and self.s[self.i] not in stop:
            if self.s[self.i] == ":" and stop == ",}" and self.s[self.i + 1:self.i + 2] in (" ", ",", "}", ""):
                break
            self.i += 1
        return _plain(self.s[start:self.i], self.no)

    def mapping(self) -> dict[str, Any]:
        self.i += 1
        out: dict[str, Any] = {}
        self.ws()
        if self.s[self.i:self.i + 1] == "}":
            self.i += 1
            return out
        while True:
            key = self.value(stop=",}")
            self.ws()
            if self.s[self.i:self.i + 1] != ":":
                raise self.error("thiếu ':' sau khóa trong {…}")
            self.i += 1
            if not isinstance(key, str):
                key = str(key) if key is not None else "null"
            if key in out:
                raise self.error(f"khóa trùng {key!r}")
            out[key] = self.value(stop=",}")
            self.ws()
            c = self.s[self.i:self.i + 1]
            self.i += 1
            if c == "}":
                return out
            if c != ",":
                raise self.error("cần ',' hoặc '}' (không được kéo {…} sang dòng sau)")

    def sequence(self) -> list[Any]:
        self.i += 1
        out: list[Any] = []
        self.ws()
        if self.s[self.i:self.i + 1] == "]":
            self.i += 1
            return out
        while True:
            out.append(self.value(stop=",]"))
            self.ws()
            c = self.s[self.i:self.i + 1]
            self.i += 1
            if c == "]":
                return out
            if c != ",":
                raise self.error("cần ',' hoặc ']' (không được kéo […] sang dòng sau)")


class _Parser:
    def __init__(self, text: str):
        self.lines = _lines(text)
        self.anchors = _Anchors()

    def anchor(self, rest: str, no: int) -> tuple[str | None, str]:
        if not rest.startswith("&"):
            return None, rest
        m = NAME.match(rest, 1)
        if not m:
            raise YamlError(f"dòng {no}: tên neo không hợp lệ")
        return m.group(), rest[m.end():].strip()

    def inline(self, rest: str, no: int) -> Any:
        if rest[0] in "{[":
            flow = _Flow(rest, no, self.anchors)
            value = flow.value(stop="")
            flow.ws()
            if flow.i != len(rest):
                raise YamlError(f"dòng {no}: còn chữ sau {rest[0]}…{'}' if rest[0] == '{' else ']'}")
            return value
        if rest[0] in "\"'":
            end = _quoted_end(rest, 0)
            if end != len(rest):
                raise YamlError(f"dòng {no}: chuỗi trong nháy phải đứng một mình")
            return _scalar_quoted(rest)
        if rest[0] == "*":
            name = rest[1:]
            if name not in self.anchors:
                raise YamlError(f"dòng {no}: tham chiếu tới neo chưa có *{name}")
            return self.anchors.use(name, no)
        if re.search(r":(?: |$)", rest):
            raise YamlError(f"dòng {no}: chuỗi có ': ' phải đặt trong nháy")
        return _plain(rest, no)

    def node(self, i: int, indent: int) -> tuple[Any, int]:
        line = self.lines[i]
        if line.indent != indent:
            raise YamlError(f"dòng {line.no}: thụt lề không khớp")
        if line.text == "-" or line.text.startswith("- "):
            return self.sequence(i, indent)
        if _split_key(line.text) is not None:
            return self.mapping(i, indent)
        raise YamlError(f"dòng {line.no}: cần 'khóa: giá trị' hoặc '- phần tử'")

    def value_after(self, i: int, indent: int, rest: str, no: int, *, seq_same_indent: bool) -> tuple[Any, int]:
        """Giá trị sau 'khóa:' hoặc '-' (rest đã bỏ neo): cùng dòng, hoặc khối thụt sâu hơn ở các dòng sau."""
        if rest:
            return self.inline(rest, no), i + 1
        nxt = self.lines[i + 1] if i + 1 < len(self.lines) else None
        if nxt and nxt.indent > indent:
            return self.node(i + 1, nxt.indent)
        if seq_same_indent and nxt and nxt.indent == indent and (nxt.text == "-" or nxt.text.startswith("- ")):
            return self.sequence(i + 1, indent)
        return None, i + 1

    def mapping(self, i: int, indent: int, first: _Line | None = None) -> tuple[dict[str, Any], int]:
        out: dict[str, Any] = {}
        while i < len(self.lines):
            line = first if first is not None and not out else self.lines[i]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise YamlError(f"dòng {line.no}: thụt lề lạ")
            if line.text == "-" or line.text.startswith("- "):
                break
            split = _split_key(line.text)
            if split is None:
                raise YamlError(f"dòng {line.no}: cần 'khóa: giá trị'")
            key, rest = split
            if key.startswith("<<"):
                raise YamlError(f"dòng {line.no}: khóa gộp << không được hỗ trợ")
            if key[0] in "!&*":
                raise YamlError(f"dòng {line.no}: khóa không hợp lệ {key!r}")
            if key in out:
                raise YamlError(f"dòng {line.no}: khóa trùng {key!r}")
            name, rest = self.anchor(rest, line.no)
            value, i = self.value_after(i, indent, rest, line.no, seq_same_indent=True)
            if name:
                self.anchors[name] = copy.deepcopy(value)
            out[key] = value
        return out, i

    def sequence(self, i: int, indent: int) -> tuple[list[Any], int]:
        out: list[Any] = []
        while i < len(self.lines):
            line = self.lines[i]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise YamlError(f"dòng {line.no}: thụt lề lạ")
            if not (line.text == "-" or line.text.startswith("- ")):
                break
            rest = line.text[1:].lstrip(" ")
            column = indent + len(line.text) - len(rest)
            name, rest = self.anchor(rest, line.no)
            if rest and _split_key(rest) is not None:
                value, i = self.mapping(i, column, first=_Line(line.no, column, rest))
            else:
                value, i = self.value_after(i, indent, rest, line.no, seq_same_indent=False)
            if name:
                self.anchors[name] = copy.deepcopy(value)
            out.append(value)
        return out, i

    def parse(self) -> Any:
        if not self.lines:
            return None
        first = self.lines[0]
        if first.indent != 0:
            raise YamlError(f"dòng {first.no}: tài liệu phải bắt đầu ở cột 1")
        if _split_key(first.text) is None and not (first.text == "-" or first.text.startswith("- ")):
            if len(self.lines) > 1:
                raise YamlError(f"dòng {self.lines[1].no}: chỉ một giá trị ở gốc")
            return self.inline(first.text, first.no)
        value, i = self.node(0, 0)
        if i != len(self.lines):
            raise YamlError(f"dòng {self.lines[i].no}: thụt lề không khớp")
        return value


def loads(text: str) -> Any:
    return _Parser(text).parse()
