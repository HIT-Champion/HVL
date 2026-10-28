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

"""Form của ứng dụng (apps/forms.py): ca thử dùng chung ``apps/*/forms/*.cases.json`` chạy qua đúng bộ kiểm của API
(FormSchema + x-moc-range), và luật form lúc triển khai."""

from __future__ import annotations

import copy
import json
import re
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app_fakes import DON, DUYET, form_bytes
from svc_workflow.apps import forms as app_forms
from svc_workflow.apps.forms import DRAFT, AppForm, bad_value, check_form, pattern_problem

ROOT = Path(__file__).resolve().parents[3]          # gốc repo: CI chạy pytest trong bản checkout đầy đủ
CASE_FILES = sorted(ROOT.glob("apps/*/forms/*.cases.json"))
# Tệp trình dựng form của Văn phòng sinh ra (#303; tests/formBuilder.test.ts so từng byte với trình dựng)
BUILDER_SAMPLE = ROOT / "apps/office/tests/form-builder.sample.json"
TODAY = date(2026, 10, 26)


def value(v: Any, today: date) -> Any:
    """DSL của tệp ca thử, như schemas/*.cases.json: today±N, $repeat, $nfd."""
    if isinstance(v, dict) and "$repeat" in v:
        return v["$repeat"] * v["times"]
    if isinstance(v, dict) and "$nfd" in v:
        return unicodedata.normalize("NFD", v["$nfd"])
    if isinstance(v, str) and (m := re.fullmatch(r"today([+-]\d+)?", v)):
        return (today + timedelta(days=int(m.group(1) or 0))).isoformat()
    return v


def build(cases: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    data = {k: value(v, TODAY) for k, v in cases["base"].items()}
    data.update({k: value(v, TODAY) for k, v in case.get("set", {}).items()})
    for k in case.get("unset", []):
        data.pop(k, None)
    return data


def shared_cases() -> list[Any]:
    out = []
    for path in CASE_FILES:
        cases = json.loads(path.read_text(encoding="utf-8"))
        form = path.with_name(path.name.removesuffix(".cases.json") + ".json")
        rel = path.relative_to(ROOT).as_posix()
        for kind in ("valid", "invalid"):
            for case in cases.get(kind, []):
                out.append(pytest.param(form, cases, case, id=f"{rel}: {case['name']}"))
    return out


SHARED = shared_cases()
needs_cases = pytest.mark.skipif(not CASE_FILES, reason="chưa có apps/*/forms/*.cases.json (form của ứng dụng mẫu)")


# --- ca thử dùng chung với trình duyệt (apps/nghi-phep/tests/schema-form.test.js) -------------------------


@needs_cases
@pytest.mark.parametrize("form_path, cases, case", SHARED or [pytest.param(None, None, None, id="none")])
def test_shared_cases_give_the_same_answer_as_the_browser(form_path, cases, case):
    form, problems = check_form(form_path.name, form_path.read_bytes())
    assert problems == [] and form is not None
    assert form.errors(build(cases, case), TODAY) == case.get("error", {})


@needs_cases
def test_shared_cases_cover_the_range_rule():
    """Hai ca đã chốt với nhóm giao diện: x-moc-range gắn vào trường sau; trường trước sai định dạng thì không so."""
    names = {c.values[2]["name"]: c.values[2].get("error") for c in SHARED}
    assert names.get("đến ngày trước từ ngày") == {"denNgay": "x-moc-range"}
    assert names.get("từ ngày sai thì không so khoảng") == {"tuNgay": "format"}


@needs_cases
def test_every_app_form_next_to_cases_passes_deploy_rules():
    for path in CASE_FILES:
        form = path.with_name(path.name.removesuffix(".cases.json") + ".json")
        assert check_form(form.name, form.read_bytes())[1] == [], form


# --- x-moc-range và giá trị ghi được thành biến -----------------------------------------------------------


def test_range_equal_dates_pass_and_reversed_dates_name_the_second_field():
    form = AppForm(DON)
    base = {"loai": "om", "tuNgay": "2026-10-27", "denNgay": "2026-10-27"}
    assert form.errors(base, TODAY) == {}
    assert form.errors({**base, "denNgay": "2026-10-26"}, TODAY) == {"denNgay": "x-moc-range"}


def test_range_is_skipped_when_a_side_already_failed_or_is_missing():
    form = AppForm(DON)
    assert form.errors({"loai": "om", "tuNgay": "2026-13-40", "denNgay": "2026-01-01"}, TODAY) == {"tuNgay": "format"}
    assert form.errors({"loai": "om", "denNgay": "2026-01-01"}, TODAY) == {"tuNgay": "required"}


def test_values_flowable_cannot_hold_are_type_errors():
    loose = {"$schema": DON["$schema"], "type": "object", "additionalProperties": False,
             "properties": {"soNgay": {"type": "integer"}, "tien": {"type": "number"}}}
    form = AppForm(loose)
    assert form.errors({"soNgay": 2**63}, TODAY) == {"soNgay": "type"}
    assert form.errors({"soNgay": 2**63 - 1, "tien": 1.5}, TODAY) == {}
    assert bad_value(float("inf")) and bad_value(float("nan")) and bad_value({"a": 1}) and bad_value([1])
    assert not bad_value(True) and not bad_value("x") and not bad_value(None)


def test_variables_keep_only_declared_present_non_null_fields():
    form = AppForm(DON)
    assert form.variables({"loai": "om", "lyDo": None, "khac": "x", "soNgay": 2, "khanCap": False}) == {
        "loai": "om", "soNgay": 2, "khanCap": False}


# --- luật form lúc triển khai ------------------------------------------------------------------------------


def problems(schema: Any) -> list[str]:
    raw = schema if isinstance(schema, bytes) else form_bytes(schema)
    form, errors = check_form("workflow.forms.nghi-phep.don (forms/don.json)", raw)
    assert (form is None) == bool(errors)
    return errors


def changed(**edits: Any) -> dict[str, Any]:
    schema = copy.deepcopy(DON)
    for key, val in edits.items():
        if val is None:
            schema.pop(key, None)
        else:
            schema[key] = val
    return schema


def with_prop(name: str, prop: Any) -> dict[str, Any]:
    schema = copy.deepcopy(DON)
    schema["properties"][name] = prop
    return schema


def test_sample_forms_pass():
    assert problems(DON) == [] and problems(DUYET) == []


def test_form_builder_output_passes_the_server_only_rules():
    # trình duyệt không kiểm được pattern (ước lượng quay lui) và meta-schema: tệp mẫu có đủ kiểu ô và cả hai $defs mà
    # trình dựng sinh ra, nên form dựng bằng nó không bị từ chối lúc cài vì hai luật đó
    form, errors = check_form(BUILDER_SAMPLE.name, BUILDER_SAMPLE.read_bytes())
    assert errors == [] and form is not None
    ok = {"tenHang": "Giấy A4", "soLuong": 10, "loai": "thiet-bi", "mucDo": "gap", "ngayDeNghi": "2026-10-26",
          "canTruocNgay": "2026-10-27", "daCoBaoGia": False, "lyDo": "Hết giấy\nin"}
    assert form.errors(ok, TODAY) == {}
    bad = {**ok, "tenHang": "Giấy\nA4", "soLuong": 2.5, "canTruocNgay": "2026-10-25"}
    assert form.errors(bad, TODAY) == {"tenHang": "not", "soLuong": "type", "canTruocNgay": "x-moc-date"}


@pytest.mark.parametrize("schema, needle", [
    (changed(additionalProperties=None), "additionalProperties: false"),
    (changed(additionalProperties=True), "additionalProperties: false"),
    (changed(**{"$schema": "http://json-schema.org/draft-07/schema#"}), "$schema phải là"),
    (changed(type="array"), "type ở gốc phải là object"),
    (changed(properties={}), "cần properties"),
    (with_prop("tenantId", {"type": "string"}), "trùng biến hệ thống"),
    (with_prop("initiator", {"type": "string"}), "trùng biến hệ thống"),
    (with_prop("execution", {"type": "string"}), "trùng tên Flowable dành sẵn"),
    (with_prop("task", {"type": "string"}), "trùng tên Flowable dành sẵn"),
    (with_prop("currentTenantId", {"type": "string"}), "trùng tên Flowable dành sẵn"),
    (with_prop("ly_do", {"type": "string"}), "camelCase"),
    (with_prop("LyDo", {"type": "string"}), "camelCase"),
    (with_prop("tep", {"type": "array", "items": {"type": "string"}}), "chỉ nhận giá trị đơn"),
    (with_prop("diaChi", {"type": "object"}), "chỉ nhận giá trị đơn"),
    (with_prop("loai2", {"enum": [{"a": 1}]}), "enum chỉ gồm giá trị đơn"),
    (with_prop("ngay", {"type": "string", "x-moc-date": "sau-ngay-mai"}), "x-moc-date chỉ nhận"),
    (with_prop("thu", {"type": "string", "format": "email"}), "format 'email' chưa hỗ trợ"),
    (with_prop("xa", {"$ref": "https://example.com/schema.json"}), "trỏ ra ngoài tệp"),
    (with_prop("xa", {"$ref": "other.json#/x"}), "trỏ ra ngoài tệp"),
    (with_prop("dong", {"$dynamicRef": "#meta"}), "không dùng $dynamicRef"),
    (with_prop("sai", "khong-phai-schema"), "phải là một schema"),
    (changed(required=["loai", "khongCo"]), "required có trường không khai"),
    (changed(**{"x-moc-range": [["loai", "denNgay"]]}), "x-moc-range"),
    (changed(**{"x-moc-range": [["tuNgay", "tuNgay"]]}), "x-moc-range"),
    (changed(**{"x-moc-range": [["tuNgay", "khongCo"]]}), "x-moc-range"),
    (changed(**{"x-moc-range": [["tuNgay", "denNgay", "lyDo"]]}), "x-moc-range"),
    (changed(**{"x-moc-range": "tuNgay"}), "x-moc-range"),
    (with_prop("soNgay", {"type": "khong-co-kieu-nay"}), "chỉ nhận giá trị đơn"),
    (with_prop("ma", {"type": "string", "pattern": "^(a+)+$"}), "lặp lồng trong một phần lặp"),
    (with_prop("ma", {"type": "string", "pattern": "^(a|aa)+$"}), "lựa chọn (|) trong một phần lặp"),
    (with_prop("ma", {"type": "string", "pattern": "^a*a*$"}), "cần maxLength"),
    (with_prop("ma", {"type": "string", "maxLength": 1000, "pattern": "a*a*a*$"}), "bước quay lui"),
    (with_prop("ma", {"type": "string", "pattern": "^(a)\\1$"}), "tham chiếu ngược"),
    (with_prop("ma", {"type": "string", "pattern": "(" * 2}), "không phải biểu thức chính quy hợp lệ"),
    (with_prop("ma", {"type": "string", "pattern": "a" * 513}), "dài quá 512"),
    (with_prop("ma", {"type": "string", "not": {"pattern": "^(\\w+\\s?)*$"}}), "ReDoS"),
    (changed(patternProperties={"^x$": {"type": "string"}}), "không dùng patternProperties"),
    # thời gian kiểm tăng theo độ dài chuỗi mà không có maxLength chặn, ở mọi chỗ có schema con
    (with_prop("ma", {"type": "string", "pattern": "^\\S.*$"}), "cần maxLength"),
    (with_prop("ma", {"type": "string", "pattern": "[0-9]{9,11}"}), "cần maxLength"),
    (with_prop("ma", {"type": "string", "maxLength": 20, "allOf": [{"pattern": "a+$"}]}), "cần maxLength"),
    (changed(propertyNames={"maxLength": 20, "pattern": "^[a-z]+$"}), "không dùng propertyNames"),
    (changed(**{"$defs": {"ma": {"type": "string", "pattern": "^a+"}}}), "cần maxLength"),
    # tốn quá MAX_STEPS bước
    (with_prop("ma", {"type": "string", "maxLength": 30000, "pattern": "a+$"}), "bước quay lui với chuỗi 30000"),
    (with_prop("ma", {"type": "string", "pattern": "^" + "a{0,30}" * 5 + "$"}), "bước quay lui"),
    (with_prop("ma", {"type": "string", "maxLength": 256, "pattern": "a{0,30}" * 4 + "$"}), "bước quay lui"),
    (with_prop("ma", {"type": "string", "pattern": "^" + "a{0,30}" * 4 + "(a|aa)" * 4 + "$"}), "bước quay lui"),
], ids=lambda v: v if isinstance(v, str) else "")
def test_form_rules_at_deploy(schema, needle):
    errors = problems(schema)
    assert any(needle in e for e in errors), errors
    assert all(e.startswith("workflow.forms.nghi-phep.don (forms/don.json): ") for e in errors)


@pytest.mark.parametrize("pattern", ["^20[0-9]{2}-", "^(19|20)[0-9]{2}-", "^[A-Z]{2,5}$", "^[^<>]{0,200}$",
                                     "^[0-9a-f]{64}-[0-9a-f]{40}$", "[\\u0000-\\u001f]",
                                     "^[^@\\s]{1,64}@[^@\\s]{1,63}\\.[a-z]{2,10}$", "^" + "a{0,30}" * 4 + "$"])
def test_patterns_whose_cost_does_not_grow_with_the_string_need_no_max_length(pattern):
    assert problems(with_prop("ma", {"type": "string", "pattern": pattern})) == []


@pytest.mark.parametrize("pattern", ["^[0-9]{1,3}(,[0-9]{3})*$", "^(a|b)+$", "^\\S.*$", "^\\S(.*\\S)?$",
                                     "[0-9]{9,11}", "a+$", "a+a{0,30}$"])
def test_patterns_with_max_length_pass(pattern):
    assert problems(with_prop("ma", {"type": "string", "maxLength": 200, "pattern": pattern})) == []


def test_patterns_of_one_form_share_one_step_budget():
    # mỗi mẫu 9,2·10^5 bước, dưới trần riêng; 33 trường như thế cộng lại quá 3·10^7 thì cả form không nhận
    near = {"type": "string", "pattern": "^" + "a{0,30}" * 4 + "$"}
    schema = copy.deepcopy(DON)
    for i in range(32):
        schema["properties"][f"ma{i}"] = near
    assert problems(schema) == []
    schema["properties"]["ma32"] = near
    errors = problems(schema)
    assert len(errors) == 1 and "kiểm một lần gửi ước tính 3,1·10^7 bước" in errors[0], errors


def test_each_ref_counts_where_it_is_used():
    # cùng mẫu viết một lần ở $defs, bốn trường trỏ tới: jsonschema chạy bốn lần, nên tính bốn lần (4 × 9·10^6)
    text = {"type": "string", "maxLength": 3000, "pattern": "a+$"}
    direct = copy.deepcopy(DON)
    by_ref = copy.deepcopy(DON)
    by_ref.setdefault("$defs", {})["dai"] = text
    for i in range(4):
        direct["properties"][f"ma{i}"] = text
        by_ref["properties"][f"ma{i}"] = {"$ref": "#/$defs/dai"}
    for schema in (direct, by_ref):
        errors = problems(schema)
        assert len(errors) == 1 and "kiểm một lần gửi ước tính 3,6·10^7 bước" in errors[0], errors
    del by_ref["properties"]["ma3"]
    assert problems(by_ref) == []


@pytest.mark.parametrize("ref, needle", [
    ("#/$defs/khongCo", "không trỏ tới schema nào"),
    ("#ten", "chỉ nhận JSON Pointer"),
    ("#/$defs/vong", "trỏ vòng"),
])
def test_refs_must_resolve_without_a_loop(ref, needle):
    schema = with_prop("ma", {"$ref": ref})
    schema.setdefault("$defs", {})["vong"] = {"$ref": "#/$defs/vong"}
    assert any(needle in e for e in problems(schema)), problems(schema)


def dag(depth: int, fan: int = 10) -> dict[str, Any]:
    """Mỗi tầng allOf ``fan`` $ref tới tầng sau: không pattern nào, jsonschema vẫn đi qua fan^depth schema."""
    defs: dict[str, Any] = {f"t{depth}": {"type": "string"}}
    for d in range(depth - 1, -1, -1):
        defs[f"t{d}"] = {"allOf": [{"$ref": f"#/$defs/t{d + 1}"}] * fan}
    schema = with_prop("ma", {"$ref": "#/$defs/t0"})
    schema.setdefault("$defs", {}).update(defs)
    return schema


def test_nested_refs_count_every_schema_they_reach():
    # sâu 3 × 10: cỡ 2·10^3 schema mỗi lần gửi, nhận; sâu 4 × 10: 2·10^4 schema (~140 ms), không nhận; sâu 7 × 10
    # (cả chục giây mỗi lần gửi) cũng bị từ chối ngay, vì lúc cài mỗi đích $ref chỉ tính một lần
    assert problems(dag(3)) == []
    assert any("kiểm một lần gửi ước tính 6,7·10^7 bước" in e for e in problems(dag(4))), problems(dag(4))
    started = time.perf_counter()
    assert any("kiểm một lần gửi ước tính" in e for e in problems(dag(7))), problems(dag(7))
    assert time.perf_counter() - started < 1


def test_ref_depth_is_counted_through_shared_targets():
    # t0 → t1 → … → t16: tính t8 trước từ chỗ nông (9 tầng), trỏ lại qua t0 thì sâu 17 tầng — vẫn bị chặn
    chain = {f"t{i}": {"$ref": f"#/$defs/t{i + 1}"} for i in range(16)}
    chain["t16"] = {"type": "string"}
    schema = with_prop("ma", {"$ref": "#/$defs/t8"})
    schema["properties"]["maCu"] = {"$ref": "#/$defs/t0"}
    schema.setdefault("$defs", {}).update(chain)
    assert any("lồng quá 16 tầng" in e for e in problems(schema)), problems(schema)
    del schema["properties"]["maCu"]
    assert problems(schema) == []


@pytest.mark.parametrize("key", ["$id", "$anchor", "$dynamicAnchor"])
def test_ids_and_anchors_only_at_the_root(key):
    # $id dưới gốc đổi chỗ "#/…" trỏ tới: lúc cài tính theo gốc tệp, jsonschema lại giải theo $id gần nhất
    schema = with_prop("ma", {key: "https://signet.local/khac" if key == "$id" else "khac", "type": "string"})
    assert any(f"{key} chỉ khai ở gốc form" in e for e in problems(schema)), problems(schema)
    assert all(key not in e for e in problems(with_prop("ma", {"type": "string"})))


def test_nested_values_never_reach_the_schema():
    # mảng, đối tượng không ghi được thành biến: báo type ngay, items… không chạy pattern trên từng phần tử
    form = AppForm({"$schema": DRAFT, "type": "object", "additionalProperties": False,
                    "properties": {"ma": {"items": {"pattern": "^(a+)+$"}}, "ten": {"type": "string"}}})
    started = time.perf_counter()
    assert form.errors({"ma": ["a" * 40 + "!"] * 100, "ten": 1}) == {"ma": "type"}
    assert form.errors(["a" * 40 + "!"]) == {"": "type"}
    assert time.perf_counter() - started < 0.05
    assert form.errors({"ma": "x", "ten": 1}) == {"ten": "type"}


def test_step_estimate_follows_re():
    # cùng bốn phần {0,30}: neo ^ thì 9,2·10^5 bước, nhận; không neo với chuỗi 96 ký tự thì re.search thử lại ở mọi vị
    # trí, ước lượng 8,9·10^7 bước, từ chối — và re chạy chậm hơn hẳn thật
    anchored, loose = "^" + "a{0,30}" * 4 + "$", "a{0,30}" * 4 + "$"
    assert pattern_problem(anchored) is None
    assert "8,9·10^7 bước quay lui với chuỗi 96 ký tự" in (pattern_problem(loose, 96) or "")

    def took(pattern: str) -> float:
        started = time.perf_counter()
        re.search(pattern, "a" * 96 + "!")
        return time.perf_counter() - started

    assert took(loose) > 10 * took(anchored)


def test_string_longer_than_max_length_never_reaches_the_pattern():
    # mẫu này đứng hàng giờ với vài chục ký tự; bị chặn lúc triển khai, ở đây dựng AppForm thẳng để chắc re không chạy
    form = AppForm({"$schema": DRAFT, "type": "object", "additionalProperties": False,
                    "properties": {"ma": {"type": "string", "maxLength": 10, "pattern": "^(a+)+$"}}})
    started = time.perf_counter()
    assert form.errors({"ma": "a" * 100_000 + "!"}) == {"ma": "maxLength"}
    assert time.perf_counter() - started < 0.05
    assert form.errors({"ma": "a" * 8 + "!"}) == {"ma": "pattern"}
    assert form.errors({"ma": "a" * 10}) == {}


def test_redos_pattern_would_stall_re_and_is_refused_before_deploy():
    # mẫu bị từ chối thật sự quay lui bùng nổ với re: mỗi ký tự thêm vào gấp đôi thời gian (đo với chuỗi ngắn)
    slow = re.compile("^(a+)+$")
    took = []
    for n in (14, 20):
        started = time.perf_counter()
        slow.match("a" * n + "!")
        took.append(time.perf_counter() - started)
    assert took[1] > 4 * took[0]
    assert any("ReDoS" in e for e in problems(with_prop("ma", {"type": "string", "pattern": "^(a+)+$"})))


def test_ui_text_named_pattern_is_not_a_pattern():
    # x-moc-ui.errors.pattern là câu báo lỗi cho giao diện, không phải mẫu
    prop = {"type": "string", "x-moc-ui": {"errors": {"pattern": "(((("}}}
    assert problems(with_prop("ma", prop)) == []


def test_invalid_json_schema_is_reported():
    errors = problems(changed(required="loai"))         # required phải là mảng: metaschema 2020-12 từ chối
    assert len(errors) == 1 and "forms/don.json" in errors[0]


def test_not_json_or_too_big_is_reported():
    assert "không phải JSON UTF-8" in problems(b"{khong phai json")[0]
    assert "không phải JSON UTF-8" in problems("{}".encode("utf-16"))[0]
    assert "cần một đối tượng JSON Schema" in problems(b"[]")[0]
    assert "lớn quá" in problems(b" " * (256 * 1024 + 1))[0]


# --- luật lúc cài, chạy chung với trình duyệt (apps/office/app/utils/formRules.ts, #303) ------------------


RULES = json.loads(Path(__file__).with_name("app_form_rules.cases.json").read_text(encoding="utf-8"))
# Câu lỗi của check_form → mã luật mà bản trên trình duyệt trả. Mỗi câu phải khớp đúng một mẫu: máy chủ thêm luật mà
# chưa có mã ở đây, trong tệp ca thử và formRules.ts thì test đỏ
RULE_MESSAGES = {
    "size": r"^tệp lớn quá",
    "json": r"^không phải JSON UTF-8",
    "depth": r"^(JSON|schema) lồng quá",
    "root": r"^cần một đối tượng JSON Schema ở gốc",
    "draft": r"^\$schema phải là",
    "root-type": r"^type ở gốc phải là object",
    "additional-properties": r"^cần additionalProperties: false",
    "properties": r"^cần properties",
    "reserved": r"trùng biến hệ thống",
    "engine-name": r"trùng tên Flowable",
    "el-keyword": r"trùng từ khóa của biểu thức",
    "field-name": r"^tên trường .* phải dạng camelCase",
    "field-schema": r"phải là một schema \(đối tượng\)$",
    "scalar": r": chỉ nhận giá trị đơn",
    "enum": r": enum chỉ gồm giá trị đơn$",
    "x-moc-date": r": x-moc-date chỉ nhận",
    "required": r"^required ",
    "x-moc-range": r"^x-moc-range phải là",
    "root-only": r" chỉ khai ở gốc form",
    "ref-external": r" trỏ ra ngoài tệp",
    "dynamic-ref": r"^không dùng \$(dynamicRef|recursiveRef)$",
    "format": r"^format .* chưa hỗ trợ",
    "pattern-properties": r"^không dùng (patternProperties|propertyNames) ",
    "ref-target": r"chỉ nhận JSON Pointer|không trỏ tới schema nào",
    "ref-loop": r"trỏ vòng hoặc lồng quá",
    "steps": r"^kiểm một lần gửi ước tính",
    "pattern": r"\(ReDoS\)$",
    "schema": r"^Schema không hợp lệ",
}


def rule_value(v: Any) -> Any:
    """DSL của tệp ca thử: {"$repeat": s, "times": n} và {"$nest": k, "times": n, "leaf": v}."""
    if isinstance(v, dict) and "$repeat" in v:
        return v["$repeat"] * v["times"]
    if isinstance(v, dict) and "$nest" in v:
        node = v["leaf"]
        for _ in range(v["times"]):
            node = {v["$nest"]: node}
        return node
    return v


def rule_file(case: dict[str, Any]) -> bytes:
    """Nội dung tệp form của một ca: text ghép lại, hoặc base sửa theo set, unset (JSON Pointer, "" là cả tệp)."""
    if "text" in case:
        return "".join(rule_value(part) for part in case["text"]).encode()
    form: Any = copy.deepcopy(RULES["base"])

    def parent(pointer: str) -> tuple[Any, str]:
        *path, last = pointer[1:].split("/")
        node = form
        for part in path:
            node = node[part]
        return node, last

    for pointer, v in case.get("set", {}).items():
        if pointer == "":
            form = rule_value(v)
        else:
            node, key = parent(pointer)
            node[key] = rule_value(v)
    for pointer in case.get("unset", []):
        node, key = parent(pointer)
        del node[key]
    # gọn như JSON.stringify, để luật cỡ tệp so cùng số byte với trình duyệt
    return json.dumps(form, ensure_ascii=False, separators=(",", ":")).encode()


def rule_of(message: str) -> str:
    found = [rule for rule, pattern in RULE_MESSAGES.items() if re.search(pattern, message)]
    assert len(found) == 1, f"{message!r} khớp {found}"
    return found[0]


@pytest.mark.parametrize("case", [pytest.param(c, id=c["name"]) for kind in ("valid", "invalid") for c in RULES[kind]])
def test_rule_cases_give_the_rules_the_browser_reports(case):
    form, errors = check_form("f.json", rule_file(case))
    assert (form is None) == bool(errors)
    assert sorted(rule_of(e.removeprefix("f.json: ")) for e in errors) == sorted(case.get("errors", []))


def test_rule_cases_cover_every_rule_and_match_the_constants():
    assert list(RULE_MESSAGES) == RULES["rules"]
    assert {r for c in RULES["invalid"] for r in c["errors"]} == set(RULES["rules"])
    for name, expected in RULES["constants"].items():
        value = getattr(app_forms, name)
        if isinstance(value, re.Pattern):
            value = value.pattern
        elif isinstance(value, (set, frozenset)):
            value = sorted(value)
        elif isinstance(value, tuple):
            value = list(value)
        assert value == expected, name
