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

"""Sổ đăng ký văn bản đến / đi theo năm (F2.8).

NĐ 30/2020/NĐ-CP, Điều 16 và 22: văn bản đăng ký bằng hệ thống phải in ra giấy đủ các trường theo mẫu sổ đăng ký
(Phụ lục IV), ký nhận và đóng sổ. Cột theo mẫu sổ; ô "Ký nhận" để trống cho người nhận ký tay trên bản in.

Sổ phải liền số từ 01 đến hết năm, kể cả văn bản hạn chế người in không được đọc: dòng đó chỉ có số, ngày, số
ký hiệu và chữ "Hạn chế"; trích yếu, tác giả, người ký, nơi gửi, nơi nhận, độ khẩn đều bị che. Ai được đọc gì vẫn
do Hasura quyết (app.py hỏi lại bằng token người in), ở đây không viết lại quy tắc. Bản JSON cho giao diện và bản
PDF dựng từ cùng các ô đã định dạng.

Chân mỗi trang PDF in mốc neo sổ kiểm toán mới nhất lúc in (anchors.py): ``Mốc neo #<id> · <16 chữ hex đầu của hash> ·
<giờ>``. Sổ giấy đã ký nhận vì thế trỏ được vào một mốc trong tệp mốc chép ra ngoài máy chủ: đối chiếu mốc đó là biết
sổ kiểm toán lúc in chưa bị viết lại về sau. Chưa neo lần nào thì không in gì.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .anchors import Mark
from .render import display_code

VN = ZoneInfo("Asia/Ho_Chi_Minh")

COLUMNS = {
    "in": ("Ngày đến", "Số đến", "Tác giả", "Số, ký hiệu", "Ngày tháng", "Tên loại và trích yếu nội dung",
           "Đơn vị hoặc người nhận", "Ký nhận", "Ghi chú"),
    "out": ("Số, ký hiệu văn bản", "Ngày tháng văn bản", "Tên loại và trích yếu nội dung văn bản", "Người ký",
            "Nơi nhận văn bản", "Đơn vị, người nhận bản lưu", "Số lượng bản", "Ngày chuyển", "Ký nhận", "Ghi chú"),
}
# Độ rộng cột (mm) trên A4 ngang, vùng in rộng 267 mm; cột ngày vừa "dd/mm/yyyy" cỡ 10pt trên một dòng
WIDTHS = {
    "in": (21, 13, 34, 28, 21, 68, 34, 22, 26),
    "out": (26, 21, 56, 27, 34, 25, 13, 21, 20, 24),
}
TITLES = {"in": "Sổ đăng ký văn bản đến", "out": "Sổ đăng ký văn bản đi"}
HIDDEN = "Văn bản hạn chế — chỉ người được giao xem trên hệ thống"
SENT = {"issued", "archived"}       # văn bản đi đã phát hành; "approved" có số rồi vẫn có thể chưa phát hành
URGENCY = {"khan": "Khẩn", "thuong_khan": "Thượng khẩn", "hoa_toc": "Hỏa tốc"}


@dataclass(frozen=True)
class Entry:
    number: int
    document_id: str | None     # None khi dòng bị che: người in không mở được văn bản đó
    hidden: bool
    cells: tuple[str, ...]      # đúng thứ tự COLUMNS[direction]


@dataclass(frozen=True)
class Register:
    direction: str
    year: int
    org_name: str
    parent_name: str | None
    entries: tuple[Entry, ...]
    last_number: int            # số cuối đã cấp trong năm (office.registers)
    printed_at: datetime
    anchor: Mark | None = None  # mốc neo sổ kiểm toán mới nhất lúc in, in ở chân trang

    @property
    def anchor_note(self) -> str:
        """Chữ ở chân trang; chưa có mốc thì rỗng."""
        if self.anchor is None:
            return ""
        a = self.anchor
        return f"Mốc neo #{a.audit_id} · {a.hash[:16]} · {a.anchored_at.astimezone(VN).strftime('%H:%M %d/%m/%Y')}"

    @property
    def title(self) -> str:
        return TITLES[self.direction]

    @property
    def columns(self) -> tuple[str, ...]:
        return COLUMNS[self.direction]

    @property
    def missing(self) -> list[int]:
        """Số đã cấp mà không có dòng nào — sổ phải liền số (NĐ 30, Điều 15, 22); bình thường là rỗng."""
        have = {e.number for e in self.entries}
        return [n for n in range(1, self.last + 1) if n not in have]

    @property
    def last(self) -> int:
        """Số cuối của sổ để in "đến số …": số cuối đã cấp, hoặc số lớn nhất có dòng nếu dòng đọc sau khi cấp số."""
        return max([self.last_number, *(e.number for e in self.entries)])

    @property
    def date_range(self) -> tuple[str, str] | None:
        """Ngày của dòng đầu, dòng cuối (ngày đến với sổ đến, ngày văn bản với sổ đi)."""
        days = [e.cells[0 if self.direction == "in" else 1] for e in self.entries]
        days = [d for d in days if d]
        return (days[0], days[-1]) if days else None


def _day(value: str | None) -> str:
    """'2026-10-05' hoặc thời điểm có múi giờ → '05/10/2026' theo giờ Việt Nam."""
    if not value:
        return ""
    if len(value) == 10:
        d = date.fromisoformat(value)
    else:
        d = datetime.fromisoformat(value).astimezone(VN).date()
    return d.strftime("%d/%m/%Y")


def _notes(doc: dict[str, Any], hidden: bool, *parts: str) -> str:
    if hidden:
        return "Hạn chế"          # người in không đọc được văn bản: không lộ cả độ khẩn, trạng thái
    notes = [URGENCY[doc["urgency"]]] if doc.get("urgency") in URGENCY else []
    if doc.get("restricted"):
        notes.append("Hạn chế")
    if doc.get("status") == "cancelled":
        notes.append("Đã hủy")
    notes.extend(p for p in parts if p)
    return "; ".join(notes)


def _incoming(doc: dict[str, Any], hidden: bool, users: dict[str, str], head_title: str | None) -> tuple[str, ...]:
    lead = (doc.get("assignments") or [None])[0]
    if lead:
        receiver = (lead.get("department") or {}).get("name") or users.get(lead.get("user_id") or "", "")
    elif doc.get("status") == "registered":
        receiver = head_title or "Lãnh đạo đơn vị"      # đã vào sổ, đang chờ lãnh đạo chỉ đạo
    elif doc.get("status") in ("done", "archived"):
        receiver = "Lưu (không giao xử lý)"
    else:
        receiver = ""
    summary = f'{doc["document_type"]["name"]}: {doc["summary"]}'
    due = f'Hạn giải quyết {_day(doc["due_on"])}' if doc.get("due_on") else ""
    return (
        _day(doc.get("registered_at")),
        str(doc["register_number"]),
        "" if hidden else doc.get("issuer_name") or "",
        doc.get("symbol") or "",
        _day(doc.get("issued_on")),
        HIDDEN if hidden else summary,
        "" if hidden else receiver,
        "",
        _notes(doc, hidden, due),
    )


def _outgoing(doc: dict[str, Any], hidden: bool) -> tuple[str, ...]:
    sent = doc.get("status") in SENT
    issued = (doc.get("events") or [{}])[0].get("created_at")
    archive = "Văn thư" + (f'; {doc["department"]["name"]}' if doc.get("department") and not hidden else "")
    summary = f'{doc["document_type"]["name"]}: {doc["summary"]}'
    # mã xác thực chỉ tra được ở cổng khi đã phát hành; cấp số rồi mà dựng bản phát hành lỗi thì còn "approved"
    code = f'Mã xác thực {display_code(doc["verify_code"])}' if doc.get("verify_code") and sent else ""
    pending = "Đã cấp số, chưa phát hành" if doc.get("status") == "approved" else ""
    return (
        doc.get("symbol") or "",
        _day(doc.get("issued_on")),
        HIDDEN if hidden else summary,
        "" if hidden else (doc.get("signer") or {}).get("full_name") or "",
        "" if hidden else "; ".join(doc.get("recipients") or []),
        archive,
        "",                                       # bản giấy: văn thư ghi tay khi in ra để gửi
        (_day(issued) or _day(doc.get("issued_on"))) if sent else "",
        "",
        _notes(doc, hidden, pending, code),
    )


def build_register(data: dict[str, Any], visible: set[str], *, direction: str, year: int,
                   printed_at: datetime, anchor: Mark | None = None) -> Register:
    """Sổ từ dữ liệu hasura.REGISTER; visible: id các văn bản người in được đọc (Hasura trả theo token của họ)."""
    tenant = data.get("core_tenants_by_pk") or {}
    users = {u["id"]: u["full_name"] for u in data.get("core_users") or []}
    registers = data.get("office_registers") or []
    entries = []
    for doc in data.get("office_documents") or []:
        hidden = doc["id"] not in visible
        cells = _incoming(doc, hidden, users, tenant.get("head_title")) if direction == "in" else _outgoing(doc, hidden)
        entries.append(Entry(number=doc["register_number"], document_id=None if hidden else doc["id"], hidden=hidden,
                             cells=cells))
    return Register(
        direction=direction, year=year, org_name=tenant.get("name") or "", parent_name=tenant.get("parent_name"),
        entries=tuple(entries), last_number=registers[0]["last_number"] if registers else 0, printed_at=printed_at,
        anchor=anchor,
    )


def _e(text: str | None) -> str:
    return html.escape(text or "", quote=True)


CSS = """
@page { size: A4 landscape; margin: 14mm 12mm 16mm 18mm;
        @bottom-center { content: "Trang " counter(page) "/" counter(pages); font-size: 9pt; color: #555; } }
@page cover { @bottom-center { content: none; } }
html { font-family: "Liberation Serif", "Times New Roman", serif; font-size: 11pt; line-height: 1.25; color: #000; }
.cover { page: cover; page-break-after: always; text-align: center; padding-top: 14mm; }
.cover .org { font-size: 13pt; text-transform: uppercase; }
.cover .org b { display: block; }
.cover .rule { width: 60mm; margin: 2pt auto 0; border-top: 0.8pt solid #000; }
.cover h1 { font-size: 24pt; text-transform: uppercase; margin: 36mm 0 10mm; letter-spacing: 1pt; }
.cover .meta { font-size: 15pt; line-height: 1.9; }
.cover .note { margin: 34mm auto 0; width: 170mm; font-size: 10pt; font-style: italic; color: #333; }
table.so { width: 100%; border-collapse: collapse; table-layout: fixed; }
table.so th, table.so td { border: 0.6pt solid #000; padding: 2pt 3pt; vertical-align: top; word-wrap: break-word; }
table.so th { font-weight: bold; text-align: center; vertical-align: middle; font-size: 10pt; }
table.so td { font-size: 10pt; }
table.so td.note { font-size: 9pt; }
table.so thead tr.num th { font-weight: normal; font-style: italic; font-size: 9.5pt; }
table.so tbody tr { page-break-inside: avoid; height: 11mm; }
td.c { text-align: center; }
td.hidden { font-style: italic; color: #444; }
.closing { margin-top: 8mm; page-break-inside: avoid; }
.closing .sign { float: right; width: 90mm; text-align: center; }
.closing .sign .who { font-weight: bold; }
.closing .sign .hint { font-style: italic; font-size: 10pt; }
"""

CENTERED = {"in": {0, 1, 4}, "out": {1, 6, 7}}


def _css_string(text: str) -> str:
    """Chuỗi CSS trong ngoặc kép (thuộc tính content)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def register_html(reg: Register) -> str:
    cols = reg.columns
    widths = "".join(f'<col style="width:{w}mm">' for w in WIDTHS[reg.direction])
    head = "".join(f"<th>{_e(c)}</th>" for c in cols)
    numbers = "".join(f"<th>({i})</th>" for i in range(1, len(cols) + 1))
    rows = []
    summary_col = cols.index("Tên loại và trích yếu nội dung" if reg.direction == "in"
                             else "Tên loại và trích yếu nội dung văn bản")
    for entry in reg.entries:
        cells = []
        for i, text in enumerate(entry.cells):
            cls = ("c" if i in CENTERED[reg.direction] else "hidden" if entry.hidden and i == summary_col
                   else "note" if i == len(cols) - 1 else "")
            cells.append(f'<td class="{cls}">{_e(text)}</td>' if cls else f"<td>{_e(text)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    if not rows:
        rows.append(f'<tr><td colspan="{len(cols)}" class="c">Chưa có văn bản nào trong sổ năm {reg.year}.</td></tr>')

    span = reg.date_range
    printed = reg.printed_at.astimezone(VN).strftime("%H:%M ngày %d/%m/%Y")
    meta = [f"Năm: {reg.year}"]
    if span:
        meta.append(f"Từ ngày {span[0]} đến ngày {span[1]}")
    if reg.last:
        meta.append(f"Từ số 01 đến số {reg.last:02d}")
    missing = reg.missing
    check = (f"Sổ thiếu dòng của số: {', '.join(str(n) for n in missing)}." if missing
             else f"Sổ liền số, đủ {len(reg.entries)} văn bản." if reg.entries else "")
    hidden = sum(e.hidden for e in reg.entries)
    hidden_note = (f" {hidden} dòng là văn bản hạn chế người in không được đọc: chỉ in số, ngày, số ký hiệu."
                   if hidden else "")
    # mốc neo ở góc trái chân mọi trang, kể cả bìa; WeasyPrint không đọc HTML trong <style> nên chỉ cần thoát kiểu CSS
    footer = (f"<style>@page {{ @bottom-left {{ content: {_css_string(reg.anchor_note)}; font-size: 8pt;"
              f" color: #555; }} }}</style>" if reg.anchor_note else "")
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>{_e(reg.title)} năm {reg.year} — {_e(reg.org_name)}</title>
<meta name="author" content="{_e(reg.org_name)}">
<meta name="generator" content="Signet">
<style>{CSS}</style>{footer}</head>
<body>
<section class="cover">
  <div class="org">{f'<div>{_e(reg.parent_name)}</div>' if reg.parent_name else ''}<b>{_e(reg.org_name)}</b></div>
  <div class="rule"></div>
  <h1>{_e(reg.title)}</h1>
  <div class="meta">{''.join(f'<div>{_e(m)}</div>' for m in meta)}</div>
  <div class="note">In từ hệ thống Signet lúc {printed}. Văn bản đăng ký trên hệ thống; bản in đủ các trường theo mẫu sổ
  đăng ký (Nghị định 30/2020/NĐ-CP, Điều 16, Điều 22, Phụ lục IV) để ký nhận và đóng sổ. {_e(check)}{_e(hidden_note)}
  </div>
</section>
<table class="so">
  <colgroup>{widths}</colgroup>
  <thead><tr>{head}</tr><tr class="num">{numbers}</tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
<div class="closing">
  <div class="sign"><div class="who">Văn thư cơ quan</div><div class="hint">(Ký, ghi rõ họ tên)</div></div>
</div>
</body></html>"""


def render_register_pdf(reg: Register) -> bytes:
    from weasyprint import HTML    # nạp khi cần, như render.py

    return HTML(string=register_html(reg)).write_pdf()
