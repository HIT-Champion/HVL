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

"""Đọc tệp dữ liệu (NDJSON, CSV) và zip tệp đính kèm của lô nạp: dòng hỏng thành dòng lỗi, tệp hỏng là lỗi cả tệp,
không tự sửa dữ liệu."""

import hashlib
import io
import json
import os
import time
import unicodedata
import uuid
import warnings
import zipfile

import pytest

from import_fakes import doc, ndjson, zip_bytes
from svc_files.imports.parse import LINE_MAX, ParseError, Row, guess_format, parse
from svc_files.imports.runner import IncomingHandler
from svc_files.imports.spool import ZIP_MAX_ENTRIES, EntryError, Spool, check_rows, index, read_entry

COLUMNS = IncomingHandler(None, None, None, None, max_file_bytes=1, sealing=False).columns
HEADER = "type_code,symbol,issuer_name,issued_on,summary"


def rows(raw: bytes | str, fmt: str = "ndjson", max_rows: int = 1000) -> list[Row]:
    data = raw.encode() if isinstance(raw, str) else raw
    return parse(data, fmt, COLUMNS, max_rows=max_rows)  # type: ignore[arg-type]


def error(raw: bytes | str, fmt: str = "ndjson", max_rows: int = 1000) -> ParseError:
    with pytest.raises(ParseError) as exc:
        rows(raw, fmt, max_rows)
    return exc.value


# --- định dạng ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("explicit", "name", "mime", "fmt"), [
    (None, "lo.ndjson", None, "ndjson"),
    (None, "LO.JSONL", "text/plain", "ndjson"),
    (None, "lo.csv", "application/octet-stream", "csv"),
    (None, "du-lieu", "text/csv; charset=utf-8", "csv"),
    (None, "du-lieu", "application/x-ndjson", "ndjson"),
    ("csv", "lo.ndjson", "application/x-ndjson", "csv"),      # tham số thắng đuôi tệp
])
def test_guess_format(explicit, name, mime, fmt):
    assert guess_format(explicit, name, mime) == fmt


@pytest.mark.parametrize(("explicit", "name", "mime"), [(None, "lo.txt", "text/plain"), (None, None, None),
                                                        ("xlsx", "lo.csv", "text/csv")])
def test_unknown_format(explicit, name, mime):
    with pytest.raises(ParseError) as exc:
        guess_format(explicit, name, mime)
    assert (exc.value.status, exc.value.code) == (400, "unknown_format")


# --- NDJSON --------------------------------------------------------------------------------------------------


def test_ndjson_rows_keep_physical_line_numbers_and_skip_blank_lines():
    got = rows(ndjson(doc(1), "", "   ", doc(2, restricted=True)).replace(b"\n", b"\r\n"))
    assert [(r.line, r.failed) for r in got] == [(1, False), (4, False)]
    assert got[0].data == doc(1) and got[1].data["restricted"] is True and got[0].files == []


def test_ndjson_data_is_passed_through_untouched():
    # không cắt khoảng trắng, không NFC, không bỏ khóa lạ: Action báo theo trường như API
    raw = {"type_code": " CV", "symbol": "1/UB", "issuer_name": "UBND tỉnh", "issued_on": "15/10/2026",
           "summary": unicodedata.normalize("NFD", "Về việc"), "la": 1}
    (row,) = rows(ndjson(raw))
    assert row.data == raw and not row.failed


def test_ndjson_bom_is_ignored():
    (row,) = rows(b"\xef\xbb\xbf" + ndjson(doc(1)))
    assert row.data == doc(1)


@pytest.mark.parametrize(("line", "code"), [
    ("{x", "bad_json"),
    ('{"a": NaN}', "bad_json"),
    ('{"a": Infinity}', "bad_json"),
    ('{"a": ' * 33 + "1" + "}" * 33, "bad_value"),      # lồng quá MAX_DEPTH
    ('{"a": [' + "[" * 30_000 + "]" * 30_000 + "]}", "bad_value"),
    ("[1, 2]", "not_object"),
    ('"chuỗi"', "not_object"),
    ('{"files": "a.pdf"}', "bad_files"),
    ('{"files": ["a.pdf", "a.pdf"]}', "bad_files"),
    ('{"files": [""]}', "bad_files"),
    ('{"files": ["a.pdf"], "file_ids": "x"}', "bad_files"),
    ('{"summary": "a\\u0000b"}', "bad_value"),
    ('{"summary": "a\\ud800b"}', "bad_value"),       # ký tự thay thế lẻ: trước đây cả yêu cầu lỗi 500
    ('{"\\udfff": 1}', "bad_value"),
    ('{"files": ["\\ud800.pdf"]}', "bad_value"),
    # số tràn: json.loads cho inf, Hasura không nhận (JSON không có inf) — trước đây cả yêu cầu lỗi 500
    ('{"x": 1e999}', "bad_value"),
    ('{"urgency": -1e999}', "bad_value"),
    ('{"a": {"b": [1, 2e400]}}', "bad_value"),
])
def test_bad_ndjson_lines_fail_alone(line, code):
    got = rows(ndjson(doc(1), line, doc(3)))
    assert [(r.line, r.code) for r in got] == [(1, None), (2, code), (3, None)]
    assert got[1].data is None and got[1].message


def test_nesting_up_to_the_limit_is_kept_for_the_action_to_judge():
    (row,) = rows(ndjson(doc(1, extra=json.loads('{"a": ' * 30 + "1" + "}" * 30))))
    assert not row.failed and row.data["extra"]["a"]["a"]


def test_parser_recursion_error_fails_the_row(monkeypatch):
    real = json.loads

    def deep(text, **kw):
        if text.startswith("[[["):
            raise RecursionError("maximum recursion depth exceeded")
        return real(text, **kw)

    monkeypatch.setattr("svc_files.imports.parse.json.loads", deep)
    got = rows(ndjson(doc(1), "[[[1]]]"))
    assert [(r.line, r.code) for r in got] == [(1, None), (2, "bad_value")]     # như trần MAX_DEPTH
    assert "lồng quá sâu" in got[1].message


@pytest.mark.parametrize("depth", [33, 3_000, 30_000])
def test_deep_lines_are_cut_before_the_json_parser(monkeypatch, depth):
    # bộ đọc JSON đệ quy: 3.13 ném RecursionError ở vài nghìn cấp, 3.14 thì không — dòng sâu không tới json.loads
    # nên mọi bản Python cho cùng một kết quả
    real, seen = json.loads, []

    def spy(text, **kw):
        seen.append(text)
        return real(text, **kw)

    monkeypatch.setattr("svc_files.imports.parse.json.loads", spy)
    line = '{"a": ' + "[" * (depth - 1) + "]" * (depth - 1) + "}"
    got = rows(ndjson(doc(1), line))
    assert [(r.line, r.code) for r in got] == [(1, None), (2, "bad_value")]
    assert got[1].message == "Dòng lồng quá 32 cấp" and len(seen) == 1


def test_brackets_inside_strings_do_not_count_as_nesting():
    text = "[" * 40 + '\\" {{{' + "]" * 3
    (row,) = rows(ndjson(doc(1, summary=text, extra={"a": [[[{"b": "[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[["}]]]})))
    assert not row.failed and row.data["summary"] == text
    (row,) = rows(ndjson(doc(1, extra=json.loads('{"a": ' * 32 + "1" + "}" * 32))))
    assert row.failed and row.code == "bad_value"          # 33 cấp kể cả object ngoài cùng


ESCAPED = '\\"' * 32_000        # 64 000 byte \" — một chuỗi JSON dài toàn dấu nháy đã thoát


@pytest.mark.parametrize(("line", "code"), [
    # chuỗi không đóng sau 33 cấp: trước đây regex bỏ chuỗi thử lại từ từng dấu " tới cuối dòng — bậc hai, 13–17 giây
    # cho dòng 64 KiB, giữ GIL nên cả svc-files đứng (to_thread không cứu)
    ("[" * 33 + '"' + ESCAPED, "bad_value"),
    ('{"a": "' + "[" * 40 + ESCAPED, "bad_json"),                    # chuỗi không đóng ở cấp 1: ngoặc trong chuỗi
    ('{"a": "' + "[" * 40 + ESCAPED + '"}', None),                   # chuỗi đóng: ngoặc trong chuỗi không tính
    ("[" * 33 + '"' + ESCAPED + '"' + "]" * 33, "bad_value"),
    ('{"a": [' + '"\\\\\\"[", ' * 7_000 + "1]}", None),               # nhiều chuỗi ngắn \\\"[ (thoát lồng)
])
def test_depth_scan_is_linear_on_hostile_lines(line, code):
    assert len(line.encode()) <= LINE_MAX and line.count("[") + line.count("{") > 32    # qua đường nhanh, phải quét
    started = time.perf_counter()
    got = rows(ndjson(doc(1), line, doc(3)))
    assert time.perf_counter() - started < 1.0
    assert [(r.line, r.code) for r in got] == [(1, None), (2, code), (3, None)]


@pytest.mark.parametrize(("line", "code"), [
    # \\ trước dấu nháy: chuỗi đã đóng, 34 cấp sau đó vẫn phải đếm (bộ quét coi \" là thoát thì bỏ sót)
    ('{"k": "\\\\", "x": ' + "[" * 33 + "]" * 33 + "}", "bad_value"),
    ('{"k": "a\\\\\\\\", "x": ' + "[" * 33 + "]" * 33 + "}", "bad_value"),
    # \\\" là \\ rồi \": chuỗi chưa đóng, ngoặc phía sau nằm trong chuỗi
    ('{"k": "\\\\\\"' + "[" * 40 + '"}', None),
    ('{"k": "\\u005c\\"' + "{" * 40 + '"}', None),                   # \ là \ nhưng không thoát ký tự sau
    ('{"k": "\\"", "x": ' + "[" * 31 + "]" * 31 + ', "y": "' + "[" * 9 + '"}', None),     # đúng 32 cấp
])
def test_depth_scan_follows_json_escapes(line, code):
    got = rows(ndjson(line))
    assert [(r.line, r.code) for r in got] == [(1, code)]


def test_finite_numbers_are_kept():
    (row,) = rows(ndjson(doc(1, extra={"a": 1.5e300, "b": -0.0, "c": 12345678901234567890})))
    assert not row.failed and row.data["extra"]["a"] == 1.5e300
    (row,) = rows(b'{"z": 1e-999}\n')          # quá nhỏ thì về 0: vẫn là số hữu hạn
    assert not row.failed and row.data == {"z": 0.0}


def test_too_many_files_in_a_row():
    (row,) = rows(ndjson(doc(1, files=[f"{i}.pdf" for i in range(21)])))
    assert row.code == "bad_files"
    (row,) = rows(ndjson(doc(1, files=[f"{i}.pdf" for i in range(20)])))
    assert not row.failed and len(row.files) == 20


def test_long_line_fails_without_parsing():
    (row,) = rows(ndjson(doc(1, summary="x" * LINE_MAX)))
    assert row.code == "line_too_long"


def test_files_are_split_off_and_nfc_normalized():
    (row,) = rows(ndjson(doc(1, files=[unicodedata.normalize("NFD", "công văn.pdf"), "phụ lục.pdf"])))
    assert row.files == ["công văn.pdf", "phụ lục.pdf"]
    assert "files" not in row.data


@pytest.mark.parametrize(("raw", "status", "code"), [
    (b"", 400, "empty"),
    (b"\n \n\t\n", 400, "empty"),
    (b'{"a": "\xc0"}\n', 400, "bad_encoding"),
    (ndjson(*(doc(i) for i in range(4))), 413, "too_many_rows"),
])
def test_whole_ndjson_file_errors(raw, status, code):
    exc = error(raw, max_rows=3)
    assert (exc.status, exc.code) == (status, code)


def test_row_limit_counts_only_data_lines():
    assert len(rows(ndjson(doc(1), "", doc(2), "", doc(3)), max_rows=3)) == 3


# --- CSV -----------------------------------------------------------------------------------------------------


def test_csv_rows_follow_excel_row_numbers():
    text = (f"﻿{HEADER},files,restricted\r\n"
            'CV,1/UB,UBND tỉnh,2026-10-15,"Về việc A\nnhiều dòng",a.pdf; b.pdf,true\r\n'
            ",,,,,,\r\n"
            "TB,2/UB,UBND tỉnh,2026-10-16,Về việc B,,\r\n")
    got = rows(text, "csv")
    assert [r.line for r in got] == [2, 4]
    assert got[0].data == {"type_code": "CV", "symbol": "1/UB", "issuer_name": "UBND tỉnh", "issued_on": "2026-10-15",
                           "summary": "Về việc A\nnhiều dòng", "restricted": True}
    assert got[0].files == ["a.pdf", "b.pdf"]
    # ô trống: bỏ khóa (mặc định của schema áp)
    assert "restricted" not in got[1].data and got[1].files == []


def test_csv_values_are_not_cleaned():
    (row,) = rows(f"{HEADER},restricted,file_ids\nCV , 1/UB,UB,2026-10-15,Về việc,FALSE,a;b\n", "csv")
    assert row.data["type_code"] == "CV " and row.data["symbol"] == " 1/UB"
    assert row.data["restricted"] is False
    assert row.data["file_ids"] == ["a", "b"]


# --- cột đúng/sai: quyết định tệp lưu mã hóa hay bản rõ (F3.7), nên kiểm chặt trước khi có lô -------------------------


@pytest.mark.parametrize("value", ["yes", "1", "có", "x", "true", "false", "", 1, 0, None, [], {"v": True}])
def test_ndjson_restricted_must_be_a_json_boolean(value):
    got = rows(ndjson(doc(1, restricted=True), doc(2, restricted=value, files=["mat.pdf"]), doc(3, restricted=False)))
    assert [(r.line, r.code) for r in got] == [(1, None), (2, "bad_value"), (3, None)]
    assert got[1].message.startswith("restricted chỉ nhận true hoặc false") and got[1].files == []
    assert got[0].data["restricted"] is True and got[2].data["restricted"] is False


@pytest.mark.parametrize("cell", ["1", "0", "có", "yes", "x", " true", "true ", "đúng"])
def test_csv_restricted_takes_only_true_or_false(cell):
    text = (f"{HEADER},restricted,files\n"
            f"CV,1/UB,UB,2026-10-15,Về việc A,{cell},mat.pdf\n"
            "CV,2/UB,UB,2026-10-15,Về việc B,TRUE,mat.pdf\n"
            "CV,3/UB,UB,2026-10-15,Về việc C,False,\n")
    got = rows(text, "csv")
    assert [(r.line, r.code) for r in got] == [(2, "bad_value"), (3, None), (4, None)]
    assert "restricted chỉ nhận true hoặc false" in got[0].message
    assert got[1].data["restricted"] is True and got[2].data["restricted"] is False


def test_csv_row_with_wrong_cell_count_fails_alone():
    got = rows(f"{HEADER}\nCV,1/UB,UB,2026-10-15\nCV,2/UB,UB,2026-10-15,Về việc mẫu\n", "csv")
    assert [(r.line, r.code) for r in got] == [(2, "bad_line"), (3, None)]


@pytest.mark.parametrize(("text", "code", "hint"), [
    ("type_code,symbol\nCV,1\n", "bad_header", "thiếu cột issuer_name, issued_on, summary"),
    (f"{HEADER},ghi_chu\nCV,1,UB,2026-10-15,Về việc,x\n", "bad_header", "cột lạ 'ghi_chu'"),
    (f"{HEADER},symbol\n", "bad_header", "cột lặp lại symbol"),
    (f'{HEADER}\nCV,"1/UB\n', "bad_format", "CSV hỏng"),
    ("", "empty", ""),
    (f"{HEADER}\n,,,,\n", "empty", ""),
])
def test_whole_csv_file_errors(text, code, hint):
    exc = error(text, "csv")
    assert (exc.status, exc.code) == (400, code)
    assert hint in exc.message


def test_csv_row_limit():
    text = HEADER + "\n" + "".join(f"CV,{i}/UB,UB,2026-10-15,Về việc mẫu\n" for i in range(3))
    assert len(rows(text, "csv", max_rows=3)) == 3
    assert error(text + "CV,9/UB,UB,2026-10-15,Về việc\n", "csv", max_rows=3).code == "too_many_rows"


# --- zip ------------------------------------------------------------------------------------------------------


def spool_with(tmp_path, data: bytes, limit: int = 1 << 20) -> tuple[Spool, uuid.UUID]:
    spool, job = Spool(str(tmp_path / "spool"), 1 << 20), uuid.uuid4()
    spool.receive(io.BytesIO(data), job, limit)
    return spool, job


def test_receive_keeps_a_private_part_file_with_its_digest(tmp_path):
    archive = zip_bytes({"a.pdf": b"%PDF"})
    spool, job = Spool(str(tmp_path / "spool"), 1 << 20), uuid.uuid4()
    sha, size = spool.receive(io.BytesIO(archive), job, 1 << 20)
    assert (sha, size) == (hashlib.sha256(archive).hexdigest(), len(archive))
    part = tmp_path / "spool" / f"{job}.zip.part"
    assert part.read_bytes() == archive and oct(part.stat().st_mode & 0o777) == "0o600"
    assert oct((tmp_path / "spool").stat().st_mode & 0o777) == "0o700"
    assert spool.used() == size
    spool.commit(job)
    assert not part.exists() and spool.path(job).read_bytes() == archive
    with spool.open(str(job), size) as zf:
        assert zf.read("a.pdf") == b"%PDF"
    assert spool.open(str(job), size + 1) is None           # khác cỡ lúc nhận: coi như mất
    spool.drop(job)
    assert spool.open(str(job), size) is None and spool.used() == 0


def test_receive_over_limit_or_empty(tmp_path):
    spool = Spool(str(tmp_path / "spool"), 1 << 20)
    with pytest.raises(ParseError) as exc:
        spool.receive(io.BytesIO(b"x" * 101), uuid.uuid4(), 100)
    assert (exc.value.status, exc.value.code) == (413, "too_large")
    with pytest.raises(ParseError) as exc:
        spool.receive(io.BytesIO(b""), uuid.uuid4(), 100)
    assert (exc.value.status, exc.value.code) == (400, "bad_archive")
    assert list((tmp_path / "spool").iterdir()) == []


def test_entries_by_nfc_name_without_directories(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tep/", b"")
        zf.writestr(unicodedata.normalize("NFD", "tep/công văn.pdf"), b"%PDF")
    spool, job = spool_with(tmp_path, buf.getvalue())
    assert list(spool.entries(job)) == ["tep/công văn.pdf"]


@pytest.mark.parametrize("second", ["á.pdf", unicodedata.normalize("NFD", "á.pdf")])
def test_duplicate_names_after_nfc_are_rejected(tmp_path, second):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf, warnings.catch_warnings():
        warnings.simplefilter("ignore")         # zipfile cảnh báo khi tên trùng y hệt
        zf.writestr("á.pdf", b"x")
        zf.writestr(second, b"y")
    spool, job = spool_with(tmp_path, buf.getvalue())
    with pytest.raises(ParseError) as exc:
        spool.entries(job)
    assert exc.value.code == "bad_archive" and "NFC" in exc.value.message


def test_broken_zip_is_bad_archive(tmp_path):
    spool, job = spool_with(tmp_path, b"PK\x03\x04 khong phai zip")
    with pytest.raises(ParseError) as exc:
        spool.entries(job)
    assert (exc.value.status, exc.value.code) == (400, "bad_archive")


def test_too_many_entries(monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(4):
            zf.writestr(f"{i}.txt", b"")
    monkeypatch.setattr("svc_files.imports.spool.ZIP_MAX_ENTRIES", 3)
    with zipfile.ZipFile(buf) as zf, pytest.raises(ParseError) as exc:
        index(zf)
    assert exc.value.code == "bad_archive" and "tối đa 3" in exc.value.message
    assert ZIP_MAX_ENTRIES == 5000


def test_check_rows_marks_missing_and_oversized_attachments():
    entries = {"a.pdf": zipfile.ZipInfo("a.pdf"), "to.pdf": zipfile.ZipInfo("to.pdf")}
    entries["a.pdf"].file_size, entries["to.pdf"].file_size = 10, 101
    got = [Row(2, {"x": 1}, ["a.pdf"]), Row(3, {"x": 1}, ["a.pdf", "khong-co.pdf"]), Row(4, {"x": 1}, ["to.pdf"]),
           Row(5, {"x": 1}), Row(6, None, ["khong-co.pdf"], "bad_json", "x")]
    check_rows(got, entries, 100, 1000)
    assert [(r.line, r.code) for r in got] == [(2, None), (3, "missing_attachment"), (4, "too_large"), (5, None),
                                               (6, "bad_json")]
    assert "khong-co.pdf" in got[1].message and got[1].data is None
    no_zip = [Row(2, {"x": 1}, ["a.pdf"]), Row(3, {"x": 1})]
    check_rows(no_zip, None, 100, 1000)
    assert [r.code for r in no_zip] == ["missing_attachment", None]


def test_check_rows_caps_the_bytes_a_batch_may_store_counting_every_reference():
    # một mục zip được nhiều dòng trỏ tới thì được lưu một bản cho mỗi dòng: tính mỗi lần trỏ
    entries = {"a.pdf": zipfile.ZipInfo("a.pdf"), "b.pdf": zipfile.ZipInfo("b.pdf")}
    entries["a.pdf"].file_size, entries["b.pdf"].file_size = 400, 300
    ok = [Row(n, {"x": n}, ["a.pdf"]) for n in (1, 2)] + [Row(3, {"x": 3}, ["b.pdf"])]
    check_rows(ok, entries, 500, 1100)                  # 400 + 400 + 300 = 1100: vừa trần
    assert not any(r.failed for r in ok)
    over = [Row(n, {"x": n}, ["a.pdf"]) for n in (1, 2, 3)]
    with pytest.raises(ParseError) as exc:
        check_rows(over, entries, 500, 1100)            # 1200
    assert (exc.value.status, exc.value.code) == (413, "too_large") and "chia thành nhiều lô" in exc.value.message
    # dòng đã hỏng (thiếu tệp, quá trần một tệp) không được lưu gì nên không tính
    mixed = [*(Row(n, {"x": n}, ["a.pdf"]) for n in (1, 2)), Row(3, {"x": 3}, ["a.pdf", "khong-co.pdf"]),
             Row(4, None, ["a.pdf"], "bad_json", "x")]
    check_rows(mixed, entries, 500, 1100)
    assert [r.code for r in mixed] == [None, None, "missing_attachment", "bad_json"]


def test_read_entry():
    archive = zip_bytes({"a.pdf": b"%PDF-1.7 a", "to.pdf": b"x" * 200, "khoa.pdf": b"%PDF"}, encrypted={"khoa.pdf"})
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        entries = index(zf)
        assert read_entry(zf, entries, "a.pdf", 100) == b"%PDF-1.7 a"
        for name, code in (("to.pdf", "too_large"), ("khoa.pdf", "unscannable"), ("khong.pdf", "missing_attachment")):
            with pytest.raises(EntryError) as exc:
                read_entry(zf, entries, name, 100)
            assert exc.value.code == code, name


def test_read_entry_stops_at_the_limit_whatever_the_header_says():
    # bom zip: kích thước khai trong zip nhỏ hơn thật — đọc dừng ở trần, không bung cả mục vào bộ nhớ
    archive = zip_bytes({"bom.pdf": b"\0" * 5000})
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        entries = index(zf)
        entries["bom.pdf"].file_size = 10
        with pytest.raises(EntryError) as exc:
            read_entry(zf, entries, "bom.pdf", 100)
    assert exc.value.code in ("too_large", "bad_archive")


def test_prepare_removes_only_old_leftovers(tmp_path):
    spool = Spool(str(tmp_path / "spool"), 1 << 20)
    spool._ensure()
    keep, gone, part, fresh = (str(uuid.uuid4()) for _ in range(4))
    for name in (f"{keep}.zip", f"{gone}.zip", f"{part}.zip.part"):
        (tmp_path / "spool" / name).write_bytes(b"x")
        os.utime(tmp_path / "spool" / name, (time.time() - 60, time.time() - 60))
    (tmp_path / "spool" / f"{fresh}.zip").write_bytes(b"x")     # lô vừa tạo trong lúc dọn
    before = time.time() - 1
    assert spool.prepare({keep}, before=before) == 2
    assert sorted(p.name for p in (tmp_path / "spool").iterdir()) == sorted([f"{keep}.zip", f"{fresh}.zip"])
    # chưa đọc được CSDL: chỉ xóa phần nhận dở
    (tmp_path / "spool" / f"{part}.zip.part").write_bytes(b"x")
    os.utime(tmp_path / "spool" / f"{part}.zip.part", (time.time() - 60, time.time() - 60))
    assert spool.prepare(None, before=before) == 1
    assert len(list((tmp_path / "spool").iterdir())) == 2
