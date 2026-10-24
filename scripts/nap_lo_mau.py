#!/usr/bin/env python3
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

"""Lô văn bản đến mẫu cho API nạp lô (POST /api/imports/incoming, services/svc-files/README.md) và make demo-nap-lo.

200 dòng tất định (random.Random(84)): loại trong danh mục NĐ 30 đã seed, cơ quan ban hành là các phòng của trường
mẫu, ngày ban hành trong năm 2026 không sau 23/10/2026, không có hạn giải quyết (luật "không trước hôm nay" sẽ làm
dòng mẫu hết hạn). Khoảng một phần ba số dòng có tệp đính kèm ``tep/NNNN.pdf``. Một số dòng sai cố ý, ghi trong
``BAD`` để demo và test khẳng định đúng số: dòng không đọc được, trích yếu ngắn, ngày không có thật, loại lạ, tệp
không có trong zip, tệp nhiễm (chuỗi kiểm thử EICAR do người gọi đưa vào — không nằm trong mã hay kho mã), dòng trùng
dòng trước trong cùng tệp.

    python3 scripts/nap_lo_mau.py            ghi seed/nap-lo/van-ban-den.csv (make nap-lo-mau)
    python3 scripts/nap_lo_mau.py --check    không ghi gì: thoát 1 khi tệp đã commit khác bản sinh

Chỉ dùng thư viện chuẩn, không đọc .env.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import random
import sys
import unicodedata
import uuid
import zipfile
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "seed" / "nap-lo" / "van-ban-den.csv"
SEED = 84
COUNT = 200
FIRST_DAY, LAST_DAY = date(2026, 1, 5), date(2026, 10, 23)
COLUMNS = ("type_code", "symbol", "issuer_name", "issued_on", "summary", "urgency", "files")

# (mã loại, tên loại đứng đầu trích yếu; công văn mở đầu bằng "Về việc")
TYPES = (("CV", "Về việc"), ("CV", "Về việc"), ("TB", "Thông báo"), ("KH", "Kế hoạch"), ("GM", "Giấy mời họp về việc"),
         ("BC", "Báo cáo"), ("QĐ", "Quyết định về việc"), ("HD", "Hướng dẫn"), ("TTr", "Tờ trình về việc"))
ISSUERS = (("Phòng Đào tạo", "ĐT-ĐH"), ("Phòng Công tác sinh viên", "CTSV"), ("Phòng Tổ chức – Hành chính", "TCHC"),
           ("Phòng Kế hoạch – Tài chính", "KHTC"), ("Phòng Khoa học và Hợp tác quốc tế", "KHCN"),
           ("Phòng Khảo thí và Đảm bảo chất lượng", "KT&ĐBCL"), ("Trung tâm Thông tin – Thư viện", "TTTV"),
           ("Công ty Cổ phần Công nghệ Mẫu", "CTD"))
SUBJECTS = ("tổ chức thi kết thúc học phần học kỳ I năm học 2026–2027",
            "rà soát chương trình đào tạo ngành Kế toán theo chuẩn đầu ra mới",
            "xét cấp học bổng khuyến khích học tập cho sinh viên khoa Kinh tế",
            "báo cáo số liệu tuyển sinh đại học chính quy năm 2026",
            "cử giảng viên tham gia hội thảo kinh tế số và chuyển đổi xanh",
            "kiểm kê tài sản, thiết bị cuối năm tài chính 2026",
            "đăng ký đề tài nghiên cứu khoa học cấp trường năm 2027",
            "tổ chức hội nghị viên chức, người lao động năm 2026",
            "thanh toán kinh phí giảng dạy vượt giờ học kỳ II",
            "tiếp nhận sinh viên thực tập ngành Quản trị kinh doanh",
            "cập nhật hồ sơ minh chứng kiểm định chất lượng chương trình đào tạo",
            "bổ sung giáo trình, tài liệu tham khảo cho thư viện khoa",
            "triển khai khảo sát ý kiến người học về hoạt động giảng dạy",
            "xây dựng kế hoạch giảng dạy học kỳ hè năm học 2026–2027",
            "tổ chức sinh hoạt công dân đầu khóa cho sinh viên khóa mới",
            "lập dự toán ngân sách năm 2027 của khoa Kinh tế")
URGENCY = ("normal",) * 6 + ("khan", "thuong_khan")

# Dòng sai cố ý — số thứ tự dòng dữ liệu (1-based) → mã lỗi mong đợi (và lỗi theo trường khi Action báo)
BAD_JSON, SHORT, BAD_DATE, BAD_TYPE, MISSING, INFECTED, DUPLICATE = 17, 33, 58, 76, 91, 120, 150
BAD: dict[int, tuple[str, dict[str, str] | None]] = {
    BAD_JSON: ("bad_json", None),                       # CSV: hàng thiếu ô → bad_line
    SHORT: ("invalid", {"summary": "minLength"}),
    BAD_DATE: ("invalid", {"issued_on": "format"}),
    BAD_TYPE: ("invalid", {"type_code": "unknown"}),
    MISSING: ("missing_attachment", None),
    INFECTED: ("infected", None),
    DUPLICATE: ("duplicate", {"symbol": "duplicate"}),
}
EICAR_NAME = "tep/eicar.pdf"
MISSING_NAME = "tep/khong-co.pdf"


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc(v) for v in value]
    return value


def rows(tag: str = "") -> list[dict[str, Any]]:
    """200 dòng; ``tag`` gắn vào số ký hiệu để chạy lại demo vẫn là văn bản mới (rỗng: tệp mẫu đã commit)."""
    rng = random.Random(SEED)
    span = (LAST_DAY - FIRST_DAY).days
    out: list[dict[str, Any]] = []
    for n in range(1, COUNT + 1):
        code, lead = rng.choice(TYPES)
        issuer, abbr = rng.choice(ISSUERS)
        issued = FIRST_DAY + timedelta(days=rng.randrange(span + 1))
        kind = "" if code == "CV" else f"{code}-"
        row: dict[str, Any] = {
            "type_code": code, "symbol": f"{n}{'-' + tag if tag else ''}/{kind}{abbr}", "issuer_name": issuer,
            "issued_on": issued.isoformat(), "summary": f"{lead} {rng.choice(SUBJECTS)}",
            "urgency": rng.choice(URGENCY),
        }
        if rng.random() < 1 / 3:
            row["files"] = [f"tep/{n:04d}.pdf"]
        out.append(row)
    out[SHORT - 1]["summary"] = "Về việc A"
    out[BAD_DATE - 1]["issued_on"] = "2026-02-30"
    out[BAD_TYPE - 1]["type_code"] = "XX"
    out[MISSING - 1]["files"] = [MISSING_NAME]
    out[INFECTED - 1]["files"] = [EICAR_NAME]
    first = out[DUPLICATE - 2]
    out[DUPLICATE - 1].update({k: first[k] for k in ("symbol", "issuer_name", "issued_on")})
    return [{k: _nfc(v) for k, v in row.items()} for row in out]


def expected() -> Counter[str]:
    """Kết quả của lô gửi lần đầu (kèm archive()): số dòng đạt, trùng, lỗi."""
    duplicate = sum(1 for code, _ in BAD.values() if code == "duplicate")
    failed = len(BAD) - duplicate
    return Counter({"ok": COUNT - failed - duplicate, "duplicate": duplicate, "failed": failed})


def ndjson(data: list[dict[str, Any]], *, broken: int | None = BAD_JSON) -> bytes:
    """Mỗi dòng một object; dòng thứ ``broken`` (None: không có) thiếu "}" cuối — JSON hỏng."""
    lines = [json.dumps(row, ensure_ascii=False) for row in data]
    if broken is not None:
        lines[broken - 1] = lines[broken - 1][:-1]
    return ("\n".join(lines) + "\n").encode()


def csv_text(data: list[dict[str, Any]], *, broken: int | None = BAD_JSON, columns: tuple[str, ...] = COLUMNS) -> str:
    """CSV có tiêu đề; ``files`` cách nhau bằng ";"; hàng dữ liệu thứ ``broken`` thiếu ô cuối (bad_line)."""
    buf = io.StringIO()
    out = csv.writer(buf, lineterminator="\n")
    out.writerow(columns)
    for n, row in enumerate(data, 1):
        cells = [";".join(row.get(c) or []) if c == "files" else str(row.get(c, "")) for c in columns]
        out.writerow(cells[:-1] if n == broken else cells)
    return buf.getvalue()


def archive(data: list[dict[str, Any]], *, eicar: bytes, pdf: Callable[[str], bytes]) -> bytes:
    """Zip tệp đính kèm: mỗi tên trong ``files`` một PDF ``pdf(tên)``; riêng EICAR_NAME là ``eicar``; MISSING_NAME
    cố ý không có."""
    buf, seen = io.BytesIO(), set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in data:
            for name in row.get("files") or []:
                if name == MISSING_NAME or name in seen:
                    continue
                seen.add(name)
                info = zipfile.ZipInfo(name, date_time=(2026, 10, 23, 8, 0, 0))
                zf.writestr(info, eicar if name == EICAR_NAME else pdf(name), compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def multipart(parts: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    """Thân multipart/form-data từ các (trường, tên tệp, Content-Type, byte) → (thân, Content-Type của yêu cầu)."""
    boundary = uuid.uuid4().hex
    body = b""
    for field, filename, mime, content in parts:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
                 f"Content-Type: {mime}\r\n\r\n").encode() + content + b"\r\n"
    return body + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nap_lo_mau", description="Sinh lô văn bản đến mẫu seed/nap-lo")
    parser.add_argument("--check", action="store_true", help="không ghi: so với tệp đã commit")
    args = parser.parse_args(argv)
    text = csv_text(rows())
    if args.check:
        current = CSV_PATH.read_text(encoding="utf-8") if CSV_PATH.exists() else ""
        if current != text:
            print(f"{CSV_PATH.relative_to(ROOT)} khác bản sinh — chạy lại make nap-lo-mau", file=sys.stderr)
            return 1
        print(f"{CSV_PATH.relative_to(ROOT)} khớp bản sinh")
        return 0
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_text(text, encoding="utf-8")
    print(f"Đã ghi {CSV_PATH.relative_to(ROOT)}: {COUNT} dòng, {len(BAD)} dòng sai cố ý ({dict(expected())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
