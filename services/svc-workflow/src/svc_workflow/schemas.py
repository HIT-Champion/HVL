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

"""Kiểm dữ liệu theo JSON Schema dùng chung (schemas/*.json) — lớp thứ hai của poka-yoke (F2.2).

Form trên trình duyệt kiểm trước bằng Ajv theo đúng tệp schema này, CSDL chặn lần cuối bằng ràng buộc CHECK.
Lỗi quy về {trường: mã} giống hệt phía giao diện (apps/office/app/utils/forms.ts), nên hai bên chạy chung bộ
ca thử schemas/*.cases.json. Định dạng date, uuid tự viết cho khớp từng ký tự với phía giao diện, không dùng
bản có sẵn của jsonschema (bản đó nhận cả "20261019", "{…}" quanh UUID).
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from jsonschema.exceptions import SchemaError
from jsonschema.protocols import Validator

VN = timezone(timedelta(hours=7))  # giờ Việt Nam, không đổi theo mùa
DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", re.ASCII)

# Một trường sai nhiều điều thì báo điều đứng trước — cùng thứ tự với giao diện
PRIORITY = ("type", "required", "additionalProperties", "enum", "format", "pattern", "minLength", "maxLength", "not",
            "x-moc-nfc", "uniqueItems", "maxItems", "x-moc-date")

FORMATS = FormatChecker(formats=())


@FORMATS.checks("date")
def _is_date(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if not DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:              # 2026-02-30, năm 0000
        return False
    return True


@FORMATS.checks("uuid")
def _is_uuid(value: object) -> bool:
    return not isinstance(value, str) or UUID.fullmatch(value) is not None


def today_vn() -> date:
    return datetime.now(VN).date()


class SchemaFileError(Exception):
    """Không đọc được tệp schema, hoặc tệp không phải JSON Schema hợp lệ."""


class FormSchema:
    """Một tệp schema đã nạp. errors() trả {} khi dữ liệu hợp lệ."""

    def __init__(self, schema: dict[str, Any], *, validator: type[Validator] = Draft202012Validator) -> None:
        """``validator``: lớp kiểm của jsonschema, mặc định Draft 2020-12; form của ứng dụng truyền bản riêng
        (apps/forms.py)."""
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise SchemaFileError(f"Schema không hợp lệ: {exc.message}") from exc
        self.schema = schema
        self._validator = validator(schema, format_checker=FORMATS)
        self._properties: dict[str, Any] = schema.get("properties", {})
        # Hai từ khóa riêng, JSON Schema không diễn đạt được: x-moc-date so ngày với hôm nay (giờ Việt Nam);
        # x-moc-nfc ở gốc — mọi chuỗi phải ở dạng dựng sẵn (NFC), để "Hưng Yên" gõ và "Hưng Yên" chép từ PDF dạng
        # tổ hợp không thành hai văn bản khác nhau khi chặn trùng
        self._dates = {k: p["x-moc-date"] for k, p in self._properties.items() if "x-moc-date" in p}
        self._nfc = schema.get("x-moc-nfc") is True

    @classmethod
    def load(cls, path: Path) -> FormSchema:
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise SchemaFileError(f"Không đọc được {path}: {exc}") from exc

    def errors(self, data: Any, today: date | None = None) -> dict[str, str]:
        found: dict[str, set[str]] = {}
        for err in self._validator.iter_errors(data):
            for name in self._fields(err):
                found.setdefault(name, set()).add(str(err.validator))
        if isinstance(data, dict):
            if self._nfc:
                for name, value in data.items():
                    if (name in self._properties and isinstance(value, str)
                            and not unicodedata.is_normalized("NFC", value)):
                        found.setdefault(name, set()).add("x-moc-nfc")
            today = today or today_vn()
            for name, rule in self._dates.items():
                value = data.get(name)
                if name in found or not isinstance(value, str):
                    continue
                day = date.fromisoformat(value)
                if (rule == "not-after-today" and day > today) or (rule == "not-before-today" and day < today):
                    found[name] = {"x-moc-date"}
        rank = {code: i for i, code in enumerate(PRIORITY)}
        return {name: min(codes, key=lambda c: rank.get(c, len(PRIORITY))) for name, codes in found.items()}

    def _fields(self, err: ValidationError) -> list[str]:
        if err.validator == "required" and isinstance(err.instance, dict):
            return [k for k in err.validator_value if k not in err.instance]
        if err.validator == "additionalProperties" and isinstance(err.instance, dict):
            return [k for k in err.instance if k not in self._properties]
        return [str(err.absolute_path[0])] if err.absolute_path else [""]
