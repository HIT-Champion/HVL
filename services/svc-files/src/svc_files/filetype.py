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

"""Nhận loại tệp theo nội dung (byte đầu), không tin tên tệp hay mime trình duyệt khai lúc tải lên.

``detect`` chỉ so ``HEAD`` byte đầu với chữ ký (magic number) — PDF, ảnh, vỏ zip (docx, xlsx, odt…), vỏ OLE (doc,
xls, ppt), tệp nén, âm thanh, video, chương trình chạy được; không khớp chữ ký nào thì xem có phải chữ (không byte NUL,
gần như không ký tự điều khiển), HTML, SVG, XML nhận theo thẻ mở đầu như trình duyệt (WHATWG MIME Sniffing). Không
giải mã gì nên chạy ngay trong svc-files. Đọc văn bản đến (docread/reader.py) cũng nhận loại bằng hàm này.

``check`` — mọi tệp vào kho qua ``app.ingest`` (POST /api/files, tệp trong zip của lô nạp), sau trạm quét ClamAV:

1. Chương trình chạy được (PE ``MZ``, ELF, Mach-O, lớp Java), kịch bản ``#!``, hay đuôi tệp chạy được khi mở trên
   máy người nhận (.exe, .bat, .js, .lnk…): ``type_not_allowed``.
2. Đuôi tệp có trong ``EXTENSIONS``: nội dung phải thuộc một trong các họ của đuôi — tệp tải về mở theo đuôi. Không có
   đuôi hay đuôi lạ: xét mime khai (application/octet-stream không nói gì). Sai họ: ``type_mismatch``.
3. Đuôi lạ và mime khai lạ (bản vẽ .dwg, video…): nhận như trước, chỉ chặn ở bước 1.

Mime lưu vào ``core.files``: theo nội dung; riêng vỏ zip, OLE, chữ (không tự nói là docx hay xlsx, csv hay md) đúng
họ của đuôi thì lấy mime của đuôi (hay mime khai). Không rõ: application/octet-stream.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

HEAD = 8192             # số byte đầu đọc để nhận loại
OCTET = "application/octet-stream"
TEXT_CONTROL = 0.01     # tỉ lệ ký tự điều khiển tối đa trong phần đầu tệp chữ (chữ Việt mã cũ TCVN3, VNI vẫn qua)


@dataclass(frozen=True)
class Kind:
    family: str         # họ nội dung: pdf, jpeg, png, zip, ole, text…; exe, script luôn chặn; "" là nhị phân lạ
    mime: str           # mime theo nội dung
    label: str          # tên đọc được, cho thông điệp lỗi


class Rejected(Exception):
    """Nội dung không nhận: mã cố định (type_mismatch, type_not_allowed), thông điệp tiếng Việt, mime theo nội dung."""

    def __init__(self, code: str, message: str, found: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.found = found


# byte đầu → (họ, mime, tên)
SIGNATURES: tuple[tuple[bytes, str, str, str], ...] = (
    (b"%PDF-", "pdf", "application/pdf", "PDF"),
    (b"\xff\xd8\xff", "jpeg", "image/jpeg", "ảnh JPEG"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png", "ảnh PNG"),
    (b"GIF87a", "gif", "image/gif", "ảnh GIF"),
    (b"GIF89a", "gif", "image/gif", "ảnh GIF"),
    (b"II*\x00", "tiff", "image/tiff", "ảnh TIFF"),
    (b"MM\x00*", "tiff", "image/tiff", "ảnh TIFF"),
    (b"II+\x00", "tiff", "image/tiff", "ảnh TIFF"),         # BigTIFF
    (b"MM\x00+", "tiff", "image/tiff", "ảnh TIFF"),
    (b"PK\x03\x04", "zip", "application/zip", "tệp nén zip"),   # cả docx, xlsx, pptx, odt, epub
    (b"PK\x05\x06", "zip", "application/zip", "tệp nén zip"),   # zip rỗng
    (b"PK\x07\x08", "zip", "application/zip", "tệp nén zip"),   # zip chia phần
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole", "application/x-ole-storage", "tài liệu Office cũ (doc, xls, ppt)"),
    (b"{\\rtf", "rtf", "application/rtf", "RTF"),
    (b"7z\xbc\xaf\x27\x1c", "7z", "application/x-7z-compressed", "tệp nén 7z"),
    (b"Rar!\x1a\x07", "rar", "application/vnd.rar", "tệp nén RAR"),
    (b"\xfd7zXZ\x00", "xz", "application/x-xz", "tệp nén xz"),
    (b"\x1f\x8b", "gzip", "application/gzip", "tệp nén gzip"),
    (b"ID3\x02\x00", "audio", "audio/mpeg", "âm thanh MP3"),     # thẻ ID3v2.2–2.4: phiên bản rồi byte 0
    (b"ID3\x03\x00", "audio", "audio/mpeg", "âm thanh MP3"),
    (b"ID3\x04\x00", "audio", "audio/mpeg", "âm thanh MP3"),
    (b"\xff\xfb", "audio", "audio/mpeg", "âm thanh MP3"),
    (b"\xff\xf3", "audio", "audio/mpeg", "âm thanh MP3"),
    (b"\xff\xf2", "audio", "audio/mpeg", "âm thanh MP3"),
    (b"OggS\x00", "audio", "audio/ogg", "âm thanh Ogg"),
    (b"fLaC\x00", "audio", "audio/flac", "âm thanh FLAC"),
    (b"fLaC\x80", "audio", "audio/flac", "âm thanh FLAC"),
    (b"\x1aE\xdf\xa3", "video", "video/x-matroska", "video Matroska, WebM"),
    (b"\x7fELF", "exe", "application/x-executable", "chương trình chạy được (ELF)"),
    (b"\xfe\xed\xfa\xce", "exe", "application/x-mach-binary", "chương trình chạy được (Mach-O)"),
    (b"\xfe\xed\xfa\xcf", "exe", "application/x-mach-binary", "chương trình chạy được (Mach-O)"),
    (b"\xce\xfa\xed\xfe", "exe", "application/x-mach-binary", "chương trình chạy được (Mach-O)"),
    (b"\xcf\xfa\xed\xfe", "exe", "application/x-mach-binary", "chương trình chạy được (Mach-O)"),
    (b"\xca\xfe\xba\xbe", "exe", "application/java-vm", "chương trình chạy được (lớp Java, Mach-O)"),
)
RIFF = {b"WEBP": ("webp", "image/webp", "ảnh WebP"), b"WAVE": ("audio", "audio/wav", "âm thanh WAV"),
        b"AVI ": ("video", "video/x-msvideo", "video AVI")}
# hộp ftyp của ISO BMFF: nhãn → (mime, tên); nhãn khác coi là video MP4
FTYP = {b"heic": ("image/heic", "ảnh HEIC"), b"heix": ("image/heic", "ảnh HEIC"),
        b"mif1": ("image/heif", "ảnh HEIF"), b"msf1": ("image/heif", "ảnh HEIF"), b"avif": ("image/avif", "ảnh AVIF"),
        b"M4A ": ("audio/mp4", "âm thanh M4A"), b"qt  ": ("video/quicktime", "video QuickTime")}
BMP_HEADERS = {12, 40, 52, 56, 64, 108, 124}       # cỡ phần đầu DIB hợp lệ — "BM" đứng đầu một dòng chữ thì không phải
# WHATWG MIME Sniffing: thẻ mở đầu trang HTML (sau khoảng trắng), theo sau là khoảng trắng hoặc ">"
HTML_TAGS = ("<!doctype html", "<html", "<head", "<script", "<iframe", "<h1", "<div", "<font", "<table", "<a",
             "<style", "<title", "<b", "<body", "<br", "<p", "<!--")

# Đuôi tệp chạy được khi người nhận mở trên máy (Windows, macOS, Linux) hay trên máy chủ web: không nhận dù nội dung gì
RUNNABLE = frozenset({
    "exe", "dll", "com", "scr", "pif", "cpl", "msi", "msp", "mst", "msc", "bat", "cmd", "ps1", "psm1", "vbs", "vbe",
    "js", "jse", "wsf", "wsh", "hta", "lnk", "url", "reg", "jar", "sh", "apk", "php", "phtml", "phar",
})

OOXML = "application/vnd.openxmlformats-officedocument."
ODF = "application/vnd.oasis.opendocument."
TEXT = frozenset({"text", "rtf"})
# ảnh PNG, WebP mang đuôi .jpg (tải về từ web, ứng dụng nhắn tin) hay gặp mà trình xem ảnh nào cũng mở: đuôi ảnh nhận
# mọi loại ảnh, mime lưu theo nội dung
IMAGES = frozenset({"jpeg", "png", "gif", "webp", "tiff", "bmp", "isobmff"})
# họ không tự nói rõ loại (zip là docx hay odt, chữ là csv hay md): mime lưu theo đuôi (hay mime khai)
CONTAINERS = frozenset({"zip", "ole", "text", "rtf"})
# Office: bản có mật khẩu của docx, xlsx, pptx nằm trong vỏ OLE; doc, xls hay là RTF, HTML, XML do phần mềm khác xuất
OFFICE_X = frozenset({"zip", "ole"})
OFFICE_OLD = frozenset({"ole", "zip", "rtf", "text"})
# đuôi → (mime lưu, các họ nội dung nhận). Chỉ đuôi có chữ ký chắc chắn; âm thanh, video không ràng buộc ở đây
EXTENSIONS: dict[str, tuple[str, frozenset[str]]] = {
    "pdf": ("application/pdf", frozenset({"pdf"})),
    **dict.fromkeys(("jpg", "jpeg", "jpe", "jfif"), ("image/jpeg", IMAGES)),
    "png": ("image/png", IMAGES),
    "gif": ("image/gif", IMAGES),
    "webp": ("image/webp", IMAGES),
    **dict.fromkeys(("tif", "tiff"), ("image/tiff", IMAGES)),
    "bmp": ("image/bmp", IMAGES),
    "heic": ("image/heic", IMAGES),
    "heif": ("image/heif", IMAGES),
    "avif": ("image/avif", IMAGES),
    "docx": (OOXML + "wordprocessingml.document", OFFICE_X),
    "dotx": (OOXML + "wordprocessingml.template", OFFICE_X),
    "docm": ("application/vnd.ms-word.document.macroenabled.12", OFFICE_X),
    "xlsx": (OOXML + "spreadsheetml.sheet", OFFICE_X),
    "xltx": (OOXML + "spreadsheetml.template", OFFICE_X),
    "xlsm": ("application/vnd.ms-excel.sheet.macroenabled.12", OFFICE_X),
    "pptx": (OOXML + "presentationml.presentation", OFFICE_X),
    "ppsx": (OOXML + "presentationml.slideshow", OFFICE_X),
    "pptm": ("application/vnd.ms-powerpoint.presentation.macroenabled.12", OFFICE_X),
    "odt": (ODF + "text", frozenset({"zip"})),
    "ods": (ODF + "spreadsheet", frozenset({"zip"})),
    "odp": (ODF + "presentation", frozenset({"zip"})),
    "odg": (ODF + "graphics", frozenset({"zip"})),
    "epub": ("application/epub+zip", frozenset({"zip"})),
    "zip": ("application/zip", frozenset({"zip"})),
    **dict.fromkeys(("doc", "dot"), ("application/msword", OFFICE_OLD)),
    **dict.fromkeys(("xls", "xlt"), ("application/vnd.ms-excel", OFFICE_OLD)),
    **dict.fromkeys(("ppt", "pps", "pot"), ("application/vnd.ms-powerpoint", frozenset({"ole", "zip"}))),
    "msg": ("application/vnd.ms-outlook", frozenset({"ole"})),
    "rtf": ("application/rtf", frozenset({"rtf"})),
    "7z": ("application/x-7z-compressed", frozenset({"7z"})),
    "rar": ("application/vnd.rar", frozenset({"rar"})),
    **dict.fromkeys(("gz", "tgz"), ("application/gzip", frozenset({"gzip"}))),
    "xz": ("application/x-xz", frozenset({"xz"})),
    **dict.fromkeys(("txt", "text", "log"), ("text/plain", TEXT)),
    "csv": ("text/csv", TEXT),
    "tsv": ("text/tab-separated-values", TEXT),
    **dict.fromkeys(("md", "markdown"), ("text/markdown", TEXT)),
    "json": ("application/json", TEXT),
    "xml": ("application/xml", TEXT),
    **dict.fromkeys(("html", "htm"), ("text/html", TEXT)),
    "svg": ("image/svg+xml", TEXT),
}
# mime khai → như EXTENSIONS (khi tên tệp không có đuôi, hay đuôi lạ); tên khác của cùng loại mà trình duyệt, hệ điều
# hành hay gửi
ALIASES = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg", "image/x-png": "image/png",
           "application/x-pdf": "application/pdf", "application/x-zip-compressed": "application/zip",
           "application/x-zip": "application/zip", "application/x-rar-compressed": "application/vnd.rar",
           "application/x-gzip": "application/gzip", "image/x-ms-bmp": "image/bmp", "text/xml": "application/xml",
           "text/x-markdown": "text/markdown"}


def _by_mime() -> dict[str, tuple[str, frozenset[str]]]:
    out: dict[str, tuple[str, frozenset[str]]] = {}
    for mime, families in EXTENSIONS.values():
        out[mime] = (mime, out[mime][1] | families if mime in out else families)
    return out | {alias: out[mime] for alias, mime in ALIASES.items()}


MIMES = _by_mime()


def _text(head: bytes) -> str | None:
    """Phần đầu tệp dạng chữ (đã bỏ BOM), hoặc None khi là dữ liệu nhị phân."""
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):          # UTF-16 có BOM: chữ ASCII mang byte NUL
        text = head[2:].decode("utf-16-le" if head[0] == 0xFF else "utf-16-be", "ignore")
    elif b"\x00" not in head:
        text = head.removeprefix(b"\xef\xbb\xbf").decode("latin-1")    # chỉ dò thẻ ASCII: mã chữ nào cũng được
    elif b"\x00" not in head[0::2]:                             # UTF-16 không BOM: NUL chỉ ở một phía mỗi cặp byte
        text = head.decode("utf-16-le", "ignore")
    elif b"\x00" not in head[1::2]:
        text = head.decode("utf-16-be", "ignore")
    else:
        return None
    controls = sum(1 for ch in text if (ch < " " and ch not in "\t\n\x0c\r\x1b") or ch == "\x7f")
    return text if controls <= len(text) * TEXT_CONTROL else None


def _markup(text: str) -> Kind:
    start = text.lstrip(" \t\n\r\x0c").lower()
    if start.startswith("#!"):
        return Kind("script", "text/x-shellscript", "kịch bản chạy được (#!)")
    if start.startswith("<?xml"):
        if "<svg" in start:
            return Kind("text", "image/svg+xml", "ảnh SVG")
        if "<html" in start:
            return Kind("text", "text/html", "trang HTML")
        return Kind("text", "application/xml", "XML")
    if start.startswith("<svg"):
        return Kind("text", "image/svg+xml", "ảnh SVG")
    for tag in HTML_TAGS:
        if start.startswith(tag) and start[len(tag):len(tag) + 1] in (" ", "\t", "\n", "\r", "\x0c", ">"):
            return Kind("text", "text/html", "trang HTML")
    return Kind("text", "text/plain", "văn bản chữ")


def detect(head: bytes) -> Kind:
    """Loại của tệp có ``head`` là các byte đầu (tối đa HEAD byte là đủ)."""
    for magic, family, mime, label in SIGNATURES:
        if head.startswith(magic):
            return Kind(family, mime, label)
    if head.startswith(b"MZ") and b"\x00" in head[:64]:        # phần đầu DOS của chương trình Windows (PE)
        return Kind("exe", "application/vnd.microsoft.portable-executable", "chương trình Windows (PE)")
    if head.startswith(b"RIFF") and head[8:12] in RIFF:
        return Kind(*RIFF[head[8:12]])
    if head[4:8] == b"ftyp":
        mime, label = FTYP.get(head[8:12], ("video/mp4", "video MP4"))
        return Kind("isobmff", mime, label)
    if head.startswith(b"BM") and len(head) >= 18 and int.from_bytes(head[14:18], "little") in BMP_HEADERS:
        return Kind("bmp", "image/bmp", "ảnh BMP")
    text = _text(head)
    if text is not None:
        return _markup(text)
    return Kind("", OCTET, "dữ liệu nhị phân không rõ loại")


def extension(filename: str) -> str:
    """Đuôi tệp, chữ thường; bỏ dấu chấm, khoảng trắng cuối tên như Windows ("a.exe." mở như "a.exe"). Tên chỉ có đuôi
    (".bat") vẫn có đuôi: Windows mở nó như mọi tệp .bat."""
    _, dot, ext = filename.rstrip(". ").rpartition(".")
    return ext.lower() if dot else ""


def ascii_name(filename: str) -> str:
    """Tên ASCII của tệp — ``filename=`` trong Content-Disposition lúc tải về (app.content_disposition), tên mà trình
    duyệt cũ, ``curl -OJ``, ``wget --content-disposition`` lưu: bỏ dấu, gập chữ toàn độ rộng (NFKD: "x.bát", "x.ｂａｔ"
    đều thành "x.bat"), đ → d, bỏ ký tự không in được và ``"``, ``\\``."""
    folded = unicodedata.normalize("NFKD", filename.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in folded if ch.isascii() and ch.isprintable() and ch not in '"\\').strip()


def check(head: bytes, filename: str, declared: str) -> str:
    """Mime để lưu của tệp tên ``filename`` (đã làm sạch), byte đầu ``head``, mime khai ``declared`` (đã qua
    clean_mime). Không nhận: Rejected."""
    kind, ext = detect(head), extension(filename)
    if kind.family in ("exe", "script"):
        raise Rejected("type_not_allowed", f"Tệp là {kind.label} — không nhận tải lên", kind.mime)
    # tải về có thể lưu theo tên ASCII ("x.bát" → "x.bat"): đuôi chạy được ở tên gốc hay tên gập đều chặn
    for runnable in (ext, extension(ascii_name(filename))):
        if runnable in RUNNABLE:
            raise Rejected("type_not_allowed", f"Không nhận tệp đuôi .{runnable}: chương trình, kịch bản chạy được khi "
                           "mở", kind.mime)
    if ext in EXTENSIONS:                   # tệp tải về mở theo đuôi: đuôi quyết, không xét mime khai
        (mime, families), said = EXTENSIONS[ext], f"đuôi .{ext}"
    elif declared in MIMES:
        (mime, families), said = MIMES[declared], f"kiểu khai {declared}"
    else:
        return kind.mime
    if kind.family not in families:
        raise Rejected("type_mismatch", f"Nội dung tệp là {kind.label}, không khớp {said} — tệp bị đổi đuôi hoặc giả "
                       "dạng nên đã chặn. Lưu lại đúng định dạng rồi tải lên lại", kind.mime)
    return mime if kind.family in CONTAINERS else kind.mime
