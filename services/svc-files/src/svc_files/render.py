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

"""Dựng PDF văn bản đi theo thể thức NĐ 30/2020/NĐ-CP (Phụ lục I) bằng WeasyPrint.

Hai dạng: bản phát hành (có số, ngày, mã QR và mã tra cứu dẫn tới cổng xác thực) và bản xem trước của dự thảo
(để trống số và ngày, in chữ "DỰ THẢO" chìm). Dữ liệu lấy từ CSDL, không từ người gọi; mọi chữ người dùng nhập
đều được thoát HTML trước khi đưa vào khuôn.

Ngôn ngữ (F2.9, #398): cột `language` của văn bản ('vi' mặc định, 'en'). Văn bản tiếng Anh giữ thể thức NĐ 30, đổi
phần cố định theo cách dịch thường dùng (quốc hiệu, tiêu ngữ, "No.", ngày, "To", nơi nhận, khối xác thực, tên loại
theo mã). Chữ người dùng nhập (tên đơn vị, địa danh, chức danh người ký, trích yếu, nơi nhận) giữ nguyên.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

import segno

VN = ZoneInfo("Asia/Ho_Chi_Minh")

# Tên tiếng Anh của loại văn bản NĐ 30 (migration 1792281600300_document_types), theo mã; bản tiếng Anh của sổ đăng ký
# và của văn bản đi dùng chung (F2.9, #398). Loại đơn vị tự thêm không có ở đây thì giữ tên đã khai
TYPE_NAMES_EN = {
    "CV": "Official letter", "NQ": "Resolution", "QĐ": "Decision", "CT": "Directive", "QC": "Regulations",
    "QYĐ": "Rules", "TC": "Communiqué", "TB": "Notice", "HD": "Guidance", "CTr": "Programme", "KH": "Plan",
    "PA": "Option plan", "ĐA": "Scheme", "DA": "Project", "BC": "Report", "BB": "Minutes", "TTr": "Submission",
    "HĐ": "Contract", "CĐ": "Official telegram", "BGN": "Memorandum of understanding", "BTT": "Agreement",
    "GUQ": "Power of attorney", "GM": "Invitation", "GGT": "Letter of introduction", "GNP": "Leave permit",
    "PG": "Dispatch slip", "PC": "Transfer slip", "PB": "Notification slip",
}


def type_name(document_type: dict, lang: str = "vi") -> str:
    """Tên loại văn bản theo ngôn ngữ: tiếng Anh theo mã nếu biết, không thì tên trong CSDL."""
    return (lang == "en" and TYPE_NAMES_EN.get(document_type.get("code") or "")) or document_type["name"]


# Phần cố định của văn bản đi theo ngôn ngữ, cùng khóa ở hai bên (test kiểm). {} là chỗ điền
TEXT = {
    "vi": {
        "nation": "Cộng hòa xã hội chủ nghĩa Việt Nam", "motto": "Độc lập - Tự do - Hạnh phúc", "number": "Số:",
        "re": "V/v", "to": "Kính gửi:", "recipients": "Nơi nhận:", "as_above": "Như trên", "archive": "Lưu: VT",
        "head": "Thủ trưởng đơn vị", "draft_stamp": "Dự thảo — chưa ký duyệt",
        "approved": "Đã duyệt trên hệ thống Signet",
        "draft_note": "Bản xem trước của dự thảo: chưa có số, chưa có mã xác thực, chưa có giá trị phát hành.",
        "qr_alt": "Mã QR xác thực", "verify_page": "trang xác thực",
        "verify": "Văn bản phát hành trên hệ thống Signet. Kiểm tra văn bản còn nguyên vẹn: quét mã QR, hoặc mở\n{}"
                  " và nhập mã",
        "hash": "Tệp PDF bị sửa dù một ký tự sẽ không còn khớp mã băm SHA-256 đã lưu khi phát hành.",
        "watermark": "DỰ THẢO", "draft_title": "(dự thảo)",
    },
    "en": {
        "nation": "Socialist Republic of Vietnam", "motto": "Independence - Freedom - Happiness", "number": "No.:",
        "re": "Re:", "to": "To:", "recipients": "Recipients:", "as_above": "As above",
        "archive": "Archived: Records office",
        "head": "Head of unit", "draft_stamp": "Draft — not yet approved",
        "approved": "Approved in the Signet system",
        "draft_note": "Preview of a draft: no number, no verification code, not valid as an issued document.",
        "qr_alt": "Verification QR code", "verify_page": "the verification page",
        "verify": "Issued in the Signet system. To check that this document is intact, scan the QR code, or open\n{}"
                  " and enter the code",
        "hash": "Changing even one character of the PDF file breaks the match with the SHA-256 hash stored at issue.",
        "watermark": "DRAFT", "draft_title": "(draft)",
    },
}
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December")


@dataclass(frozen=True)
class Letter:
    org_name: str                   # tên đơn vị ban hành: 'Khoa Công nghệ thông tin'
    org_code: str                   # viết tắt trong ký hiệu: 'CNTT'
    type_code: str                  # 'TB', 'CV'…
    type_name: str                  # 'Thông báo'
    in_symbol: bool                 # tên loại có trong ký hiệu (công văn: không)
    summary: str                    # trích yếu
    body: str
    recipients: list[str] = field(default_factory=list)
    parent_name: str | None = None  # cơ quan chủ quản
    place_name: str | None = None   # địa danh
    dept_code: str | None = None    # phòng soạn thảo, dùng trong ký hiệu công văn
    symbol: str | None = None       # None: dự thảo, chưa có số
    issued_on: date | None = None
    signer_title: str | None = None
    signer_name: str | None = None
    approved_at: datetime | None = None
    verify_code: str | None = None
    verify_url: str | None = None
    lang: str = "vi"                # ngôn ngữ của phần cố định: 'vi', 'en'

    @property
    def draft(self) -> bool:
        return self.symbol is None


def _e(text: str | None) -> str:
    return html.escape(text or "", quote=True)


def vn_date(d: date | None, place: str | None) -> str:
    """'Hà Nội, ngày 05 tháng 02 năm 2026': ngày dưới 10 và tháng 1, 2 viết thêm số 0 (NĐ 30, Phụ lục I)."""
    prefix = f"{_e(place)}, " if place else ""
    if d is None:
        return f"{prefix}ngày&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; tháng&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; năm {datetime.now(VN).year}"
    month = f"{d.month:02d}" if d.month <= 2 else str(d.month)
    return f"{prefix}ngày {d.day:02d} tháng {month} năm {d.year}"


def en_date(d: date | None, place: str | None) -> str:
    """'Hà Nội, February 5, 2026' — địa danh giữ như đơn vị khai."""
    prefix = f"{_e(place)}, " if place else ""
    if d is None:
        return f"{prefix}{'&nbsp;' * 16}, {datetime.now(VN).year}"
    return f"{prefix}{MONTHS_EN[d.month - 1]} {d.day}, {d.year}"


def _approved_at(at: datetime, lang: str) -> str:
    """Giờ ký duyệt trên con dấu: '09:30 ngày 19/10/2026'; tiếng Anh viết tên tháng như dòng ngày (khỏi đọc
    nhầm ngày với tháng): '09:30 on October 19, 2026'."""
    at = at.astimezone(VN)
    if lang == "en":
        return f"{at:%H:%M} on {MONTHS_EN[at.month - 1]} {at.day}, {at.year}"
    return at.strftime("%H:%M ngày %d/%m/%Y")


def display_code(code: str) -> str:
    """Mã tra cứu in trên văn bản, chia hai nhóm cho dễ đọc: ABCDE-23456."""
    return f"{code[:5]}-{code[5:]}"


def _paragraphs(text: str) -> str:
    """Mỗi dòng người soạn gõ là một đoạn, thụt đầu dòng như văn bản hành chính; dòng trống bỏ qua."""
    return "".join(f"<p>{_e(line.strip())}</p>" for line in text.splitlines() if line.strip())


def _number(letter: Letter) -> str:
    if letter.symbol:
        return _e(letter.symbol)
    tail = f"{letter.type_code}-{letter.org_code}" if letter.in_symbol \
        else f"{letter.org_code}" + (f"-{letter.dept_code}" if letter.dept_code else "")
    return f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;/{_e(tail)}"


CSS = """
@page { size: A4; margin: 20mm 15mm 20mm 30mm;
        @bottom-right { content: counter(page) "/" counter(pages); font-size: 10pt; color: #555; } }
html { font-family: "Liberation Serif", "Times New Roman", serif; font-size: 14pt; line-height: 1.3; color: #000; }
table.head { width: 100%; border-collapse: collapse; }
table.head td { vertical-align: top; text-align: center; padding: 0; }
td.org { width: 40%; font-size: 12pt; }
td.nation { width: 60%; font-size: 12pt; white-space: nowrap; }
.upper { text-transform: uppercase; }
.bold { font-weight: bold; }
.rule { width: 35%; margin: 1pt auto 6pt; border-top: 0.8pt solid #000; }
.rule.wide { width: 55%; }
.motto { font-size: 13pt; font-weight: bold; }
.place { font-style: italic; font-size: 13pt; margin-top: 6pt; }
.vv { font-size: 12pt; margin-top: 4pt; }
.title { text-align: center; font-weight: bold; margin-top: 18pt; }
.title .name { font-size: 14pt; text-transform: uppercase; }
.title .rule { width: 25%; }
.kinhgui { margin: 14pt 0 6pt 15mm; }
.kinhgui ul { margin: 0; padding-left: 22mm; list-style: none; }
.body { margin-top: 10pt; text-align: justify; }
.body p { text-indent: 12.7mm; margin: 0 0 6pt; }
table.foot { width: 100%; margin-top: 14pt; border-collapse: collapse; page-break-inside: avoid; }
table.foot td { vertical-align: top; padding: 0; }
td.recipients { width: 45%; font-size: 11pt; }
td.recipients .label { font-size: 12pt; font-weight: bold; font-style: italic; }
td.recipients ul { margin: 0; padding: 0; list-style: none; }
td.sign { width: 55%; text-align: center; }
.sign .who { font-weight: bold; text-transform: uppercase; }
.sign .stamp { margin: 10pt auto; width: 70%; border: 1pt solid #b00; color: #b00; font-size: 10.5pt; padding: 4pt; }
.sign .name { font-weight: bold; margin-top: 6pt; }
.verify { margin-top: 18pt; border-top: 0.6pt solid #888; padding-top: 6pt; font-size: 10pt; color: #333;
          page-break-inside: avoid; display: flex; }
.verify img { width: 24mm; height: 24mm; margin-right: 5mm; }
.verify .code { font-family: "Liberation Mono", monospace; font-size: 12pt; font-weight: bold; letter-spacing: 1pt; }
.watermark { position: fixed; top: 45%; left: 0; width: 100%; text-align: center; transform: rotate(-30deg);
             font-size: 90pt; font-weight: bold; color: rgba(200, 0, 0, 0.12); }
"""


def letter_html(letter: Letter) -> str:
    text = TEXT[letter.lang]
    when = vn_date if letter.lang == "vi" else en_date
    letter_type = "" if letter.in_symbol \
        else f'<div class="vv">{text["re"]} {_e(_strip_vv(letter.summary, letter.lang))}</div>'
    head = f"""
<table class="head"><tr>
  <td class="org">
    {f'<div class="upper">{_e(letter.parent_name)}</div>' if letter.parent_name else ''}
    <div class="upper bold">{_e(letter.org_name)}</div>
    <div class="rule"></div>
    <div>{text["number"]} {_number(letter)}</div>
    {letter_type}
  </td>
  <td class="nation">
    <div class="upper bold">{text["nation"]}</div>
    <div class="motto">{text["motto"]}</div>
    <div class="rule wide"></div>
    <div class="place">{when(letter.issued_on, letter.place_name)}</div>
  </td>
</tr></table>"""

    if letter.in_symbol:
        intro = f"""
<div class="title"><div class="name">{_e(letter.type_name)}</div><div>{_e(letter.summary)}</div>
<div class="rule"></div></div>"""
        recipients = "".join(f"<li>- {_e(r)};</li>" for r in letter.recipients)
    else:
        if len(letter.recipients) == 1:
            intro = f'<div class="kinhgui">{text["to"]} {_e(letter.recipients[0])}.</div>'
        else:
            last = len(letter.recipients) - 1
            items = "".join(f"<li>- {_e(r)}{'.' if i == last else ';'}</li>" for i, r in enumerate(letter.recipients))
            intro = f'<div class="kinhgui">{text["to"]}<ul>{items}</ul></div>'
        recipients = f"<li>- {text['as_above']};</li>"
    archive = text["archive"] + (f", {_e(letter.dept_code)}" if letter.dept_code else "")
    recipients += f"<li>- {archive}.</li>"

    if letter.draft:
        stamp = f'<div class="stamp">{text["draft_stamp"]}</div>'
    else:
        approved = _approved_at(letter.approved_at, letter.lang) if letter.approved_at else ""
        stamp = f'<div class="stamp">{text["approved"]}<br>{approved}</div>'
    sign = f"""
  <td class="sign">
    <div class="who">{_e(letter.signer_title or text['head'])}</div>
    {stamp}
    <div class="name">{_e(letter.signer_name)}</div>
  </td>"""

    if letter.draft or not letter.verify_code:
        verify = f'<div class="verify">{text["draft_note"]}</div>'
    else:
        qr = segno.make(letter.verify_url or letter.verify_code, error="m").svg_data_uri(scale=4, border=0)
        page = _e(letter.verify_url.rsplit('/', 1)[0] if letter.verify_url else text["verify_page"])
        verify = f"""
<div class="verify"><img src="{qr}" alt="{text['qr_alt']}">
<div>{text["verify"].format(page)}
<div class="code">{display_code(letter.verify_code)}</div>
{text["hash"]}</div></div>"""

    watermark = f'<div class="watermark">{text["watermark"]}</div>' if letter.draft else ""
    return f"""<!doctype html>
<html lang="{letter.lang}"><head><meta charset="utf-8">
<title>{_e(letter.type_name)} {_e(letter.symbol or text['draft_title'])} — {_e(letter.summary)}</title>
<meta name="author" content="{_e(letter.org_name)}">
<meta name="generator" content="Signet">
<style>{CSS}</style></head>
<body>{watermark}{head}{intro}
<div class="body">{_paragraphs(letter.body)}</div>
<table class="foot"><tr>
  <td class="recipients"><div class="label">{text["recipients"]}</div><ul>{recipients}</ul></td>{sign}
</tr></table>
{verify}
</body></html>"""


def _strip_vv(summary: str, lang: str = "vi") -> str:
    """Trích yếu công văn in sau "V/v" ("Re:"); bỏ "V/v", "Về việc" (tiếng Anh thêm "Re:") nếu người soạn đã gõ sẵn."""
    lead = r"v/v|về việc|re:" if lang == "en" else r"v/v|về việc"
    return re.sub(rf"^\s*({lead})\s*", "", summary, flags=re.IGNORECASE)


def render_pdf(letter: Letter) -> bytes:
    # Nạp WeasyPrint khi cần: thư viện nặng, và test của các phần khác không phải cài Pango
    from weasyprint import HTML

    return HTML(string=letter_html(letter)).write_pdf()


def letter_from(row: dict, *, verify_base: str | None = None, draft: bool = False) -> Letter:
    """Văn bản từ dữ liệu CSDL (office/hasura.py LETTER). draft: bản xem trước — bỏ số, ngày, mã dù văn bản đã có."""
    tenant = row["tenant"]
    issued = not draft and bool(row.get("symbol"))
    approved = (row.get("events") or [{}])[0].get("created_at")
    code = row.get("verify_code") if issued else None
    lang = row.get("language") if row.get("language") in TEXT else "vi"
    return Letter(
        org_name=tenant["name"],
        org_code=tenant["code"],
        parent_name=tenant.get("parent_name"),
        place_name=tenant.get("place_name"),
        type_code=row["type_code"],
        type_name=type_name({**row["document_type"], "code": row["type_code"]}, lang),
        in_symbol=row["document_type"]["in_symbol"],
        summary=row["summary"],
        body=row.get("body") or "",
        recipients=list(row.get("recipients") or []),
        dept_code=(row.get("department") or {}).get("code"),
        symbol=row["symbol"] if issued else None,
        issued_on=date.fromisoformat(row["issued_on"]) if issued and row.get("issued_on") else None,
        signer_title=tenant.get("head_title"),
        signer_name=(row.get("signer") or {}).get("full_name"),
        approved_at=datetime.fromisoformat(approved) if issued and approved else None,
        verify_code=code,
        verify_url=f"{verify_base}/{code}" if code and verify_base else None,
        lang=lang,
    )

