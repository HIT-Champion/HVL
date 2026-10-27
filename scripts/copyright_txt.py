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

"""Sinh COPYRIGHT.txt từ DEPENDENCIES.md (make copyright, #346).

COPYRIGHT.txt ghi bản quyền của Signet và bảng phần mềm thượng nguồn dùng trực tiếp: tên, phiên bản, giấy phép, mô tả,
trang chủ. Bảng lấy từ các bảng "Thành phần | Phiên bản | Giấy phép | Vai trò" của DEPENDENCIES.md, nên chỉ có một danh
sách phải giữ bằng tay; lý do chọn, chính sách giấy phép và thành phần đã loại vẫn ở DEPENDENCIES.md.
- Tên: ô đầu, trang chủ là các liên kết trong ô đó
- Phiên bản: phần trước ngoặc đầu tiên
- Giấy phép: giữ ghi chú trong ngoặc khi ngắn (giấy phép của gói kèm), bỏ khi là lời giải thích dài
- Mô tả: vế đầu của cột Vai trò, tới dấu ":", ";", " (", " — " hay ". " đầu tiên

Chạy với --check thì chỉ so với COPYRIGHT.txt trong kho, thoát 1 nếu đã cũ (test_copyright_txt.py kiểm như vậy).
"""

from __future__ import annotations

import difflib
import pathlib
import re
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "DEPENDENCIES.md"
OUT = ROOT / "COPYRIGHT.txt"

# Độ rộng cột Tên, Phiên bản, Giấy phép, Mô tả; Trang chủ không ngắt
WIDTHS = (30, 14, 22, 40)
GAP = "  "
LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
CUT = re.compile(r": |; | \(| — |\. ")
NOTE_MAX = 40  # ghi chú giấy phép trong ngoặc dài hơn thế này là lời giải thích, không đưa vào bảng

HEAD = """\
Signet — Lõi DX-OS Open-Core nguồn mở và ứng dụng Văn phòng điện tử
Copyright 2026 Signet Team. Mã nguồn: https://github.com/HIT-Champion/Signet

Signet là phần mềm nguồn mở: bạn được dùng, sửa đổi và phân phối lại theo Giấy phép Apache, phiên bản 2.0 (Apache
License, Version 2.0) do Apache Software Foundation công bố.

Signet được phân phối với mong muốn hữu ích nhưng KHÔNG KÈM BẢO ĐẢM NÀO, kể cả bảo đảm ngầm định về khả năng thương mại
hay sự phù hợp với một mục đích cụ thể. Chi tiết xem Giấy phép Apache.

Toàn văn giấy phép ở tệp LICENSE; thông báo bản quyền và mục đích chọn giấy phép ở tệp NOTICE; bản gốc của giấy phép:
https://www.apache.org/licenses/LICENSE-2.0.

Signet dùng các phần mềm, thư viện, phông chữ và mô hình của bên thứ ba; mỗi thành phần giữ bản quyền và giấy phép
riêng. Signet nạp chúng ở dạng nguyên bản (image Docker chính thức, gói npm và pip ghim phiên bản trong tệp khóa),
không chép mã nguồn của chúng vào kho này. Bảng dưới đây là các thành phần dùng trực tiếp, sinh từ DEPENDENCIES.md
(make copyright). Lý do chọn từng thành phần, chính sách giấy phép, các gói kéo theo có giấy phép cần giải thích và
các thành phần đã cân nhắc nhưng không dùng: xem DEPENDENCIES.md. Mọi gói kể cả gói kéo theo: SBOM
signet-X.Y.Z.cdx.json kèm mỗi bản phát hành.
"""

TAIL = """\
Giấy phép của mọi gói npm, Python và action CI, kể cả gói kéo theo, được kiểm trên mỗi pull request (make sbom,
make license-audit) theo chính sách ở DEPENDENCIES.md, mục "Kiểm tra tương thích giấy phép"; ngoại lệ ghi lý do
trong .github/license-exceptions.json. Danh sách giấy phép được OSI phê duyệt: https://opensource.org/licenses.

Thông tin bản quyền của từng tệp mã nguồn ở phần đầu tệp; tệp không chèn được (JSON, ảnh, tài liệu) khai trong
REUSE.toml.
"""


def plain(text: str) -> str:
    """Bỏ định dạng Markdown của một ô bảng: liên kết còn chữ, bỏ `, **, *."""
    text = LINK.sub(r"\1", text)
    return re.sub(r"\s+", " ", text.replace("`", "").replace("**", "").replace("*", "")).strip()


def cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def components(source: str) -> list[tuple[str, list[dict[str, str]]]]:
    """Các bảng thành phần dùng trực tiếp của DEPENDENCIES.md, theo nhóm (tiêu đề ## hoặc ###)."""
    groups: list[tuple[str, list[dict[str, str]]]] = []
    group, header = "", None
    for line in source.splitlines():
        if line.startswith(("## ", "### ")):
            group, header = plain(line.lstrip("#")), None
            continue
        if not line.startswith("|"):
            header = None
            continue
        row = cells(line)
        if header is None:
            header = row
            continue
        if set(line) <= set("|-: ") or header[0] != "Thành phần" or "Giấy phép" not in header \
                or not any(h.startswith("Phiên bản") for h in header):
            continue
        values = dict(zip(header, row))
        if not groups or groups[-1][0] != group:
            groups.append((group, []))
        groups[-1][1].append({
            "ten": plain(values["Thành phần"]),
            "trang_chu": " ".join(url for _, url in LINK.findall(values["Thành phần"])),
            "phien_ban": version(values.get("Phiên bản") or values.get("Phiên bản ghim") or ""),
            "giay_phep": license_text(values["Giấy phép"]),
            "mo_ta": description(values.get("Vai trò", "")),
            "cach_nap": plain(values.get("Cách nạp", "")),
            "vai_tro": plain(values.get("Vai trò", "")),
        })
    return groups


def version(cell: str) -> str:
    return plain(cell).split(" (")[0]


def license_text(cell: str) -> str:
    text = plain(cell)
    base, _, note = text.partition(" (")
    return text if note and len(note) <= NOTE_MAX else base


def description(cell: str) -> str:
    return CUT.split(plain(cell), maxsplit=1)[0].rstrip(".")


def table(rows: list[dict[str, str]]) -> list[str]:
    out = []
    for r in rows:
        columns = [textwrap.wrap(r[key], width, break_on_hyphens=False) or [""]
                   for key, width in zip(("ten", "phien_ban", "giay_phep", "mo_ta"), WIDTHS)]
        columns.append(r["trang_chu"].split())
        for i in range(max(len(c) for c in columns)):
            parts = [(c[i] if i < len(c) else "").ljust(w) for c, w in zip(columns, WIDTHS)]
            url = columns[4][i] if i < len(columns[4]) else ""
            out.append(GAP.join(parts + [url]).rstrip())
    return out


def render(source: str) -> str:
    groups = components(source)
    width = sum(WIDTHS) + len(GAP) * len(WIDTHS) + max(len(r["trang_chu"].split()[0]) for _, rows in groups
                                                     for r in rows if r["trang_chu"])
    rule = "=" * width
    head = GAP.join(h.ljust(w) for h, w in zip(("Tên", "Phiên bản", "Giấy phép", "Mô tả"), WIDTHS)) + GAP + "Trang chủ"
    out = [HEAD, "", head, rule]
    for group, rows in groups:
        name, paren, rest = group.partition(" (")
        out += ["", name.upper() + paren + rest, rule, *table(rows)]
    out += [rule, "", TAIL]
    return "\n".join(out)


def main() -> None:
    check = "--check" in sys.argv[1:]
    content = render(SOURCE.read_text(encoding="utf-8"))
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if old == content:
        print("COPYRIGHT.txt khớp DEPENDENCIES.md.")
        return
    if not check:
        OUT.write_text(content, encoding="utf-8")
        print("Đã ghi COPYRIGHT.txt từ DEPENDENCIES.md.")
        return
    diff = list(difflib.unified_diff(old.splitlines(), content.splitlines(), "COPYRIGHT.txt (trong kho)",
                                     "COPYRIGHT.txt (sinh từ DEPENDENCIES.md)", lineterm="", n=1))
    print("\n".join(diff[:30]) + ("\n…" if len(diff) > 30 else ""))
    print("\n✗ COPYRIGHT.txt đã cũ so với DEPENDENCIES.md: chạy make copyright rồi commit.")
    sys.exit(1)


if __name__ == "__main__":
    main()
