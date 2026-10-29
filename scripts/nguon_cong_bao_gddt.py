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

"""Nguồn dữ liệu công khai `cong-bao-gddt` (#424): thông tư của Bộ Giáo dục và Đào tạo về giáo dục đại học đăng Công
báo nước CHXHCN Việt Nam (congbao.chinhphu.vn, Văn phòng Chính phủ).

Danh sách văn bản chọn tay (``VAN_BAN``): mỗi văn bản là một trang trên Công báo. Lệnh lấy đọc trang đó để có số ký
hiệu, cơ quan ban hành, ngày ban hành, trích yếu, số Công báo và liên kết tải PDF, rồi tải PDF (bản Công báo có chữ ký
số). Chỉ đọc trang công khai, không đăng nhập, mỗi lần chạy vài yêu cầu cách nhau ``PAUSE_S`` giây. robots.txt của
congbao.chinhphu.vn cho phép mọi đường; máy tải tệp g7.cdnchinhphu.vn không có robots.txt (đọc 30/10/2026).

Căn cứ dùng lại (``REUSE_BASIS``): khoản 2 Điều 15 Luật Sở hữu trí tuệ — văn bản quy phạm pháp luật không thuộc phạm vi
bảo hộ quyền tác giả (đọc trên văn bản hợp nhất số 160/2026/VBHN-LQ-VPQH, seed/du-lieu-mo/cong-bao-gddt/README.md).
Chân trang Công báo: ghi rõ nguồn "congbao.chinhphu.vn" khi phát hành lại. Không có dữ liệu cá nhân: không lấy tên
người ký.

g7.cdnchinhphu.vn không gửi chứng thư trung gian "GlobalSign RSA OV SSL CA 2018" (30/10/2026): trình duyệt tự tải nó
theo AIA của chứng thư máy chủ, urllib thì không. Lệnh lấy tải đúng chứng thư đó từ địa chỉ AIA (``INTERMEDIATE_URL``),
nạp vào kho tin cậy riêng của lần chạy và tắt ``VERIFY_X509_PARTIAL_CHAIN``: chuỗi vẫn phải đi tới một gốc của hệ
điều hành, nên chứng thư tải qua http có bị tráo cũng không qua được bước kiểm.

Gọi qua lệnh chung ``python3 scripts/du_lieu_mo.py lay cong-bao-gddt`` (hoặc ``moc du-lieu-mo lay``). Chỉ dùng thư viện
chuẩn, không đọc .env.
"""

from __future__ import annotations

import hashlib
import html
import pathlib
import re
import ssl
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any

NGUON = "cong-bao-gddt"
TEN = "Văn bản của Bộ Giáo dục và Đào tạo đăng Công báo"
PUBLISHER = "Văn phòng Chính phủ (Công báo nước CHXHCN Việt Nam)"
HOME_URL = "https://congbao.chinhphu.vn/"
REUSE_BASIS = ("Khoản 2 Điều 15 Luật Sở hữu trí tuệ (văn bản hợp nhất số 160/2026/VBHN-LQ-VPQH): văn bản quy phạm "
               "pháp luật không thuộc phạm vi bảo hộ quyền tác giả. Công báo yêu cầu ghi rõ nguồn "
               "\"congbao.chinhphu.vn\" khi phát hành lại.")
MAX_AGE_DAYS = 400      # danh sách chọn tay: xem lại ít nhất mỗi năm học
ISSUER = "Bộ Giáo dục và Đào tạo"
TYPE_CODE = "TT"        # Thông tư — migration 1792281604000_document_type_tt

# (trang trên Công báo, tên tệp trong bản chụp, số ký hiệu phải thấy trên trang)
VAN_BAN: tuple[tuple[str, str, str], ...] = (
    ("thong-tu-so-26-2026-tt-bgddt-469372", "26-2026-tt-bgddt.pdf", "26/2026/TT-BGDĐT"),
    ("thong-tu-so-49-2026-tt-bgddt-470007", "49-2026-tt-bgddt.pdf", "49/2026/TT-BGDĐT"),
    ("thong-tu-so-58-2026-tt-bgddt-470129", "58-2026-tt-bgddt.pdf", "58/2026/TT-BGDĐT"),
    ("thong-tu-so-06-2026-tt-bgddt-469029", "06-2026-tt-bgddt.pdf", "06/2026/TT-BGDĐT"),
)
PAGE_URL = "https://congbao.chinhphu.vn/van-ban/{slug}.htm"
DOWNLOAD_HOST = "https://g7.cdnchinhphu.vn/api/download/stream?"
INTERMEDIATE_URL = "http://secure.globalsign.com/cacert/gsrsaovsslca2018.crt"
USER_AGENT = "Signet-du-lieu-mo (+https://github.com/HIT-Champion/Signet)"
PAUSE_S = 1.0
MAX_PAGE = 2 * 1024 * 1024
MAX_PDF = 3 * 1024 * 1024
VN = timezone(timedelta(hours=7))

_ROW = re.compile(r'<span class="name">\s*([^<]*?)\s*</span>\s*<div class="value">\s*'
                  r'<span class="child-value">\s*([^<]*?)\s*</span>')
_GAZETTE = re.compile(r'title="Công báo số (\d+) ngày (\d{4})-(\d{2})-(\d{2})"')
_PDF = re.compile(r'href="(https://g7\.cdnchinhphu\.vn/api/download/stream\?[^"]+?\.pdf)"', re.I)


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", html.unescape(value)).strip())


def _day(value: str) -> str:
    """dd/mm/yyyy → yyyy-mm-dd (ngày có thật)."""
    d, m, y = value.split("/")
    return date(int(y), int(m), int(d)).isoformat()


def parse(page: str, symbol: str) -> dict[str, Any]:
    """Trang văn bản trên Công báo → meta của bản chụp và liên kết PDF. Trang khác khuôn, khác văn bản: ValueError."""
    rows = {_nfc(k): _nfc(v) for k, v in _ROW.findall(page)}
    if rows.get("Số, ký hiệu") != unicodedata.normalize("NFC", symbol):
        raise ValueError(f"trang không phải văn bản {symbol} (số ký hiệu trên trang: {rows.get('Số, ký hiệu')!r})")
    if rows.get("Loại văn bản") != "Thông tư":
        raise ValueError(f"{symbol}: loại văn bản trên trang là {rows.get('Loại văn bản')!r}, không phải Thông tư")
    if rows.get("Cơ quan ban hành", "").casefold() != ISSUER.casefold():
        raise ValueError(f"{symbol}: cơ quan ban hành trên trang là {rows.get('Cơ quan ban hành')!r}")
    summary = rows.get("Trích yếu", "")
    if len(summary) < 10:
        raise ValueError(f"{symbol}: không đọc được trích yếu")
    gazette = _GAZETTE.search(page)
    pdf = _PDF.search(page)
    if not gazette or not pdf or "Ngày ban hành" not in rows:
        raise ValueError(f"{symbol}: trang thiếu số Công báo, ngày ban hành hoặc liên kết PDF")
    no, y, m, d = gazette.groups()
    return {
        "pdf_url": html.unescape(pdf.group(1)),
        "meta": {
            "symbol": rows["Số, ký hiệu"],
            "issuer_name": ISSUER,
            "issued_on": _day(rows["Ngày ban hành"]),
            "type_code": TYPE_CODE,
            "summary": summary[0].upper() + summary[1:],
            "gazette": f"Công báo số {int(no)} ngày {int(d):02d}/{int(m):02d}/{y}",
        },
    }


def tls_context() -> ssl.SSLContext:
    """Kho tin cậy của hệ điều hành + chứng thư trung gian mà g7.cdnchinhphu.vn không gửi (xem đầu tệp). Không tải được
    chứng thư đó thì vẫn chạy với kho của hệ điều hành (máy chủ có thể đã gửi đủ chuỗi)."""
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    try:
        der = _get(INTERMEDIATE_URL, None, 16 * 1024)
        ctx.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(der))
    except (OSError, ValueError, ssl.SSLError):
        pass
    return ctx


def _get(url: str, ctx: ssl.SSLContext | None, limit: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:  # noqa: S310 — chỉ các URL cố định ở trên
        body = r.read(limit + 1)
    if len(body) > limit:
        raise ValueError(f"{url[:80]}: lớn quá {limit // 1024} KB")
    return body


def lay(thu_muc: pathlib.Path) -> dict[str, Any]:
    """Tải các văn bản trong ``VAN_BAN`` vào ``thu_muc`` (thư mục tạm của lệnh chung), trả manifest. Lỗi thì raise."""
    ctx = tls_context()
    files = []
    for slug, name, symbol in VAN_BAN:
        page_url = PAGE_URL.format(slug=slug)
        got = parse(_get(page_url, ctx, MAX_PAGE).decode("utf-8"), symbol)
        time.sleep(PAUSE_S)
        pdf = _get(got["pdf_url"], ctx, MAX_PDF)
        time.sleep(PAUSE_S)
        if not pdf.startswith(b"%PDF-"):
            raise ValueError(f"{symbol}: tệp tải về không phải PDF")
        (thu_muc / name).write_bytes(pdf)
        files.append({"file": name, "url": got["pdf_url"], "sha256": hashlib.sha256(pdf).hexdigest(),
                      "bytes": len(pdf), "fetched_at": datetime.now(VN).isoformat(timespec="seconds"),
                      "meta": {**got["meta"], "page_url": page_url}})
    return {"source": NGUON, "name": TEN, "publisher": PUBLISHER, "home_url": HOME_URL, "reuse_basis": REUSE_BASIS,
            "licence": None, "fetched_at": datetime.now(VN).isoformat(timespec="seconds"),
            "max_age_days": MAX_AGE_DAYS, "files": files}
