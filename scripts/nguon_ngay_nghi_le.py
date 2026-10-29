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

"""Nguồn công khai B (#427): lịch nghỉ lễ, Tết chính thức cho gợi ý hạn của svc-workflow (đề trường mục 3.3).

Không có nguồn chính thức nào phát hành ngày nghỉ dạng đọc được bằng máy, nên nguồn là các văn bản công bố:

- ngày lễ dương lịch cố định của Điều 112 Bộ luật Lao động 2019 và Ngày Văn hóa Việt Nam 24/11 (Nghị quyết
  28/2026/QH16, Điều 2 khoản 1) — ghi thẳng trong ``FIXED`` kèm điều khoản;
- lịch nghỉ Tết, Quốc khánh, nghỉ bù, làm bù hằng năm của cán bộ, công chức, viên chức (Thủ tướng quyết theo Điều
  112 khoản 3, Bộ Nội vụ thông báo) — đọc từ trang Báo Điện tử Chính phủ trong ``PAGES``.

``lay(thu_muc)`` đọc lại từng trang, kiểm **mọi** ngày của bảng có trên trang, ghi câu trích (chỉ các đoạn nêu ngày,
không chép bài) vào ``trich/``, dựng ``ngay-nghi.json`` và trả manifest theo khuôn chung của ``seed/du-lieu-mo/``.
Trang đổi chữ mà ngày không còn, hay trang không tải được thì raise: lệnh chung giữ bản chụp cũ. Năm mới: thêm một mục
vào ``PAGES`` (URL, văn bản, khoảng ngày, chuỗi ngày đúng như trang viết), chạy lại.

Căn cứ dùng lại: Điều 15 khoản 1, 2, 3 Luật Sở hữu trí tuệ — tin tức thời sự thuần túy đưa tin, văn bản quy phạm
pháp luật, văn bản hành chính, số liệu không thuộc phạm vi bảo hộ quyền tác giả (khai REUSE:
``LICENSES/LicenseRef-VN-SHTT-Dieu-15.txt``). Trang báo yêu cầu ghi rõ nguồn khi phát hành lại: câu trích ghi URL.

  python3 scripts/nguon_ngay_nghi_le.py          # lấy mới vào seed/du-lieu-mo/ngay-nghi-le (giữ bản cũ khi lỗi)

Chỉ dùng thư viện chuẩn.
"""

from __future__ import annotations

import gzip
import hashlib
import html.parser
import json
import pathlib
import re
import shutil
import sys
import tempfile
import textwrap
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

NGUON = "ngay-nghi-le"
TEN = "Lịch nghỉ lễ, Tết chính thức"

ROOT = pathlib.Path(__file__).resolve().parent.parent
THU_MUC = ROOT / "seed" / "du-lieu-mo" / NGUON
VN = timezone(timedelta(hours=7))
USER_AGENT = "Signet-du-lieu-mo/1.0 (+https://github.com/HIT-Champion/Signet)"
TIMEOUT_S = 30
MAX_PAGE_BYTES = 2_000_000
DATA_FILE = "ngay-nghi.json"
WIDTH = 120                 # câu trích xuống dòng ở đây (chỉ thêm dấu xuống dòng, chữ giữ nguyên)

MANIFEST = {
    "source": NGUON,
    "name": TEN,
    "publisher": "Bộ Nội vụ, Văn phòng Chính phủ; đăng trên Báo Điện tử Chính phủ (baochinhphu.vn)",
    "home_url": "https://baochinhphu.vn/",
    "reuse_basis": "Điều 15 khoản 1, 2, 3 Luật Sở hữu trí tuệ (VBHN 160/2026/VBHN-LQ-VPQH): tin tức thời sự thuần túy "
                   "đưa tin, văn bản quy phạm pháp luật, văn bản hành chính và số liệu không thuộc phạm vi bảo hộ "
                   "quyền tác giả. Chỉ giữ câu trích nêu ngày nghỉ, ghi rõ nguồn baochinhphu.vn như trang yêu cầu.",
    "licence": None,
    "max_age_days": 400,
}

LUAT = "Điều 112 khoản 1 Bộ luật Lao động 45/2019/QH14"
# Ngày lễ dương lịch cố định, lặp hằng năm (MM-DD)
FIXED = (
    ("01-01", "Tết Dương lịch", f"{LUAT}, điểm a"),
    ("04-30", "Ngày Chiến thắng", f"{LUAT}, điểm c"),
    ("05-01", "Ngày Quốc tế lao động", f"{LUAT}, điểm d"),
    ("09-02", "Quốc khánh", f"{LUAT}, điểm đ"),
    ("11-24", "Ngày Văn hóa Việt Nam", "Nghị quyết 28/2026/QH16, Điều 2 khoản 1 (hiệu lực từ 01/7/2026)"),
)

TB_2026 = "Thông báo 9441/TB-BNV của Bộ Nội vụ (lịch nghỉ Tết Âm lịch, Quốc khánh năm 2026)"
VPCP_10065 = "Văn bản 10065/VPCP-KGVX ngày 02/10/2026 của Văn phòng Chính phủ (phương án nghỉ 2026, 2027)"

# Mỗi trang: URL, tệp câu trích, ngày đăng, và các mục lấy từ trang. Mục: (loại, từ, đến, tên, căn cứ, chuỗi phải có
# trên trang). Loại "off" là ngày nghỉ (cả khoảng), "work" là thứ Bảy làm bù (ngày làm việc)
PAGES = (
    {
        "file": "trich/2026-tet-quoc-khanh.txt",
        "url": "https://baochinhphu.vn/bo-noi-vu-thong-bao-lich-nghi-tet-am-lich-va-nghi-le-quoc-khanh-nam-2026-"
               "102251017095507785.htm",
        "published": "2025-10-17",
        "items": (
            ("off", "2026-02-16", "2026-02-20", "Tết Âm lịch Bính Ngọ", TB_2026, ("16/02/2026", "20/02/2026")),
        ),
    },
    {
        "file": "trich/2026-quoc-khanh.txt",
        "url": "https://baochinhphu.vn/quoc-khanh-2026-cong-chuc-vien-chuc-nghi-5-ngay-lien-tiep-lam-bu-vao-thu-bay-"
               "22-8-102260728182643819.htm",
        "published": "2026-07-28",
        "items": (
            ("off", "2026-08-31", "2026-09-02", "Quốc khánh (nghỉ thứ Hai 31/8 hoán đổi)", TB_2026,
             ("9441/TB-BNV", "31/8/2026")),
            ("work", "2026-08-22", "2026-08-22", "Làm bù cho thứ Hai 31/8/2026", TB_2026, ("22/8/2026",)),
        ),
    },
    {
        "file": "trich/2026-gio-to.txt",
        "url": "https://baochinhphu.vn/bo-noi-vu-khong-co-chu-truong-hoan-doi-de-nghi-9-ngay-dip-gio-to-30-41-5-"
               "102260403124126624.htm",
        "published": "2026-04-03",
        "items": (
            ("off", "2026-04-27", "2026-04-27", "Nghỉ bù Giỗ Tổ Hùng Vương (10/3 âm lịch là Chủ nhật 26/4)",
             f"{LUAT}, điểm e; Bộ Nội vụ trả lời họp báo 03/4/2026", ("Chủ nhật (26/4)", "thứ Hai (27/4)")),
        ),
    },
    {
        "file": "trich/2026-2027-vpcp-10065.txt",
        "url": "https://baochinhphu.vn/pho-thu-tuong-quyet-dinh-phuong-an-nghi-ngay-van-hoa-tet-am-lich-quoc-khanh-"
               "10226100217552059.htm",
        "published": "2026-10-02",
        "items": (
            ("off", "2026-11-24", "2026-11-24", "Ngày Văn hóa Việt Nam", VPCP_10065, ("10065/VPCP-KGVX", "24/11/2026")),
            ("off", "2027-02-04", "2027-02-10", "Tết Âm lịch Đinh Mùi", VPCP_10065, ("4/2/2027", "10/2/2027")),
            ("off", "2027-09-02", "2027-09-05", "Quốc khánh", VPCP_10065, ("2/9/2027", "5/9/2027")),
        ),
    },
)

Fetch = Callable[[str], bytes]


class _Text(html.parser.HTMLParser):
    """Chữ của trang theo đoạn: mỗi thẻ khối mở một đoạn mới, bỏ script, style."""

    BLOCKS = frozenset({"p", "div", "li", "h1", "h2", "h3", "td", "br", "section", "article"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def paragraphs(page: bytes) -> list[str]:
    """Các đoạn chữ của trang HTML (UTF-8), đã gộp khoảng trắng, khử trùng, giữ thứ tự."""
    parser = _Text()
    parser.feed(page.decode("utf-8", errors="replace"))
    out: list[str] = []
    for line in "".join(parser.parts).split("\n"):
        line = " ".join(line.replace("\xa0", " ").split())
        if line and line not in out:
            out.append(line)
    return out


def quote(page: bytes, needles: list[str]) -> str:
    """Câu trích: các đoạn có ít nhất một chuỗi cần kiểm. Thiếu chuỗi nào trên trang thì ValueError."""
    paras = paragraphs(page)
    missing = [n for n in needles if not any(n in p for p in paras)]
    if missing:
        raise ValueError("trang không còn " + ", ".join(repr(m) for m in missing))
    # đoạn ngắn hơn thế này là tiêu đề, chú thích ảnh lặp lại câu dài hơn
    kept = [p for p in paras if len(p) >= 40 and any(n in p for n in needles)]
    return "\n\n".join(textwrap.fill(p, WIDTH, break_long_words=False, break_on_hyphens=False) for p in kept)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:     # noqa: S310 (URL cố định trong PAGES)
        data = resp.read(MAX_PAGE_BYTES + 1)
    if len(data) > MAX_PAGE_BYTES:
        raise ValueError(f"{url}: trang lớn quá {MAX_PAGE_BYTES} byte")
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(VN).replace(microsecond=0).isoformat()


def _write(folder: pathlib.Path, name: str, data: bytes, url: str, at: str,
           meta: dict[str, object]) -> dict[str, object]:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"file": name, "url": url, "sha256": _sha256(data), "bytes": len(data), "fetched_at": at, "meta": meta}


def build(pages: dict[str, bytes], at: str) -> tuple[dict[str, object], dict[str, bytes]]:
    """Từ chữ các trang (URL → byte) ra (``ngay-nghi.json``, câu trích theo tệp). Kiểm ngày như ``quote``."""
    days_off: list[dict[str, str]] = []
    workdays: list[dict[str, str]] = []
    quotes: dict[str, bytes] = {}
    for spec in PAGES:
        needles = [n for item in spec["items"] for n in item[5]]
        try:
            text = quote(pages[spec["url"]], needles)
        except ValueError as exc:
            raise ValueError(f"{spec['url']}: {exc}") from None
        header = f"Nguồn: Báo Điện tử Chính phủ (baochinhphu.vn)\n{spec['url']}\nĐăng {spec['published']}, lấy {at}\n\n"
        quotes[spec["file"]] = (header + text + "\n").encode("utf-8")
        for kind, first, last, name, basis, _ in spec["items"]:
            if date.fromisoformat(first) > date.fromisoformat(last):
                raise ValueError(f"{name}: {first} sau {last}")
            if kind == "off":
                days_off.append({"from": first, "to": last, "name": name, "basis": basis, "quote": spec["file"]})
            else:
                workdays.append({"date": first, "name": name, "basis": basis, "quote": spec["file"]})
    data = {
        "source": NGUON,
        "note": "Lịch nghỉ của cán bộ, công chức, viên chức; workdays: thứ Bảy làm bù",
        "fixed": [{"date": d, "name": n, "basis": b} for d, n, b in FIXED],
        "days_off": sorted(days_off, key=lambda e: e["from"]),
        "workdays": sorted(workdays, key=lambda e: e["date"]),
    }
    return data, quotes


def lay(thu_muc: pathlib.Path, fetch: Fetch = fetch) -> dict[str, object]:
    """Lấy mới vào ``thu_muc`` (thư mục tạm): câu trích, ``ngay-nghi.json``; trả manifest. Lỗi thì raise."""
    at = _now()
    pages: dict[str, bytes] = {}
    files: list[dict[str, object]] = []
    for spec in PAGES:
        pages[spec["url"]] = fetch(spec["url"])
    data, quotes = build(pages, at)
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    files.append(_write(thu_muc, DATA_FILE, raw, MANIFEST["home_url"], at, {"kind": "data"}))
    for spec in PAGES:
        files.append(_write(thu_muc, spec["file"], quotes[spec["file"]], spec["url"], at, {
            "kind": "quote", "published": spec["published"], "page_sha256": _sha256(pages[spec["url"]]),
            "documents": sorted({item[4] for item in spec["items"]}),
        }))
    return {**MANIFEST, "fetched_at": at, "files": files}


def main(argv: list[str]) -> int:
    """Lấy mới rồi mới thay bản chụp: lỗi giữa chừng thì bản cũ còn nguyên."""
    target = pathlib.Path(argv[0]) if argv else THU_MUC
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / NGUON
        work.mkdir()
        try:
            manifest = lay(work)
        except (OSError, ValueError) as exc:
            print(f"Không lấy được {NGUON}: {exc}. Giữ bản chụp cũ.", file=sys.stderr)
            return 1
        (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(work, target)
    print(f"{NGUON}: {len(manifest['files'])} tệp, lấy {manifest['fetched_at']} → {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
