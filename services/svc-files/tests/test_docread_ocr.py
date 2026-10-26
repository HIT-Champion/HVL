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

"""OCR (F4.1) với tesseract giả: tiền xử lý ảnh, ảnh nhúng của PDF scan, trần điểm ảnh, giết cả nhóm khi quá giờ.

Máy chạy test không cần tesseract: ``fake_tesseract`` (conftest) ghi lại cách được gọi và in TSV cố định.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import signal
import time
from pathlib import Path

import pytest
from PIL import Image

from conftest import SAMPLE_TSV, fake_tesseract, text_pdf
from svc_files.docread.ocr import SERVER_NOTES, OcrResult, _parse, run_ocr


def image(size=(1200, 800), mode="L", fmt="PNG", **save) -> bytes:
    img = Image.new(mode, size, 255 if mode in ("L", "1") else (255, 255, 255) if mode == "RGB" else (0, 0, 0, 0))
    out = io.BytesIO()
    img.save(out, fmt, **save)
    return out.getvalue()


def pdf_of(*images: Image.Image) -> bytes:
    """PDF scan: mỗi trang là một ảnh (Pillow ghi PDF, ảnh nhúng DCTDecode)."""
    out = io.BytesIO()
    images[0].save(out, "PDF", save_all=True, append_images=list(images[1:]), resolution=150)
    return out.getvalue()


def ocr(data: bytes, kind: str, binary: Path, **kw) -> OcrResult:
    return asyncio.run(run_ocr(data, kind, binary=str(binary), **kw))


def received(directory: Path) -> Image.Image:
    return Image.open(directory / "stdin.png")


def test_image_is_prepared_and_sent_to_tesseract(tmp_path):
    binary = fake_tesseract(tmp_path)
    got = ocr(image((1200, 800), "RGB", "JPEG"), "image", binary)
    assert got == OcrResult("ok", 1, (SAMPLE_TSV,))
    call = json.loads((tmp_path / "call.json").read_text())
    assert call["args"] == ["stdin", "stdout", "-l", "vie", "--oem", "1", "--psm", "3", "tsv"]
    assert call["omp"] == "1"
    sent = received(tmp_path)
    assert sent.format == "PNG" and sent.mode == "L" and sent.size == (2000, 1333)   # nhỏ thì phóng lên 2000


def test_language_comes_from_settings(tmp_path):
    binary = fake_tesseract(tmp_path)
    ocr(image(), "image", binary, lang="vie+eng")
    assert json.loads((tmp_path / "call.json").read_text())["args"][3] == "vie+eng"


def test_a_large_image_is_scaled_down(tmp_path):
    binary = fake_tesseract(tmp_path)
    ocr(image((5000, 1000)), "image", binary)
    assert received(tmp_path).size == (3500, 700)


def test_exif_orientation_is_applied(tmp_path):
    # ảnh chụp điện thoại: điểm ảnh nằm ngang, EXIF bảo xoay 90° — tesseract phải nhận ảnh đứng
    exif = Image.Exif()
    exif[0x0112] = 6
    binary = fake_tesseract(tmp_path)
    ocr(image((1500, 1000), "RGB", "JPEG", exif=exif.tobytes()), "image", binary)
    w, h = received(tmp_path).size
    assert h > w and max(w, h) == 2000


def test_transparent_png_is_flattened_on_white(tmp_path):
    binary = fake_tesseract(tmp_path)
    ocr(image((2000, 1000), "RGBA"), "image", binary)
    assert received(tmp_path).getextrema() == (255, 255)       # nền trong suốt thành trắng, không thành đen


def test_tiff_is_read(tmp_path):
    binary = fake_tesseract(tmp_path)
    assert ocr(image((2400, 3300), "1", "TIFF", compression="group4"), "image", binary).status == "ok"


def test_pdf_scan_uses_the_largest_embedded_image_of_each_page(tmp_path):
    from pypdf import PdfReader, PdfWriter

    small, big = Image.new("L", (300, 200), 255), Image.new("L", (2480, 3508), 255)
    # một trang có hai ảnh: ghép trang ảnh nhỏ lên trang ảnh lớn
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_of(big))))
    writer.pages[0].merge_page(PdfReader(io.BytesIO(pdf_of(small))).pages[0])
    out = io.BytesIO()
    writer.write(out)
    assert len(PdfReader(io.BytesIO(out.getvalue())).pages[0].images.keys()) == 2
    binary = fake_tesseract(tmp_path)
    got = ocr(out.getvalue(), "pdf", binary)
    assert got.status == "ok" and got.pages == 1
    assert received(tmp_path).size == (2474, 3500)       # ảnh lớn, thu về cạnh dài 3500


def test_only_the_first_pages_are_recognized(tmp_path):
    binary = fake_tesseract(tmp_path)
    pdf = pdf_of(*(Image.new("L", (1240, 1754), 255) for _ in range(3)))
    assert ocr(pdf, "pdf", binary).tsv == (SAMPLE_TSV,)
    got = ocr(pdf, "pdf", binary, max_pages=2)
    assert got.pages == 3 and got.tsv == (SAMPLE_TSV, SAMPLE_TSV)


def test_a_page_without_images_keeps_its_place(tmp_path):
    # #253: TSV thứ n là của trang n — trang không có ảnh cho chuỗi rỗng chứ không bị bỏ qua
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_of(*(Image.new("L", (1240, 1754), 255) for _ in range(3))))))
    writer.pages[1][NameObject("/Resources")] = DictionaryObject()
    out = io.BytesIO()
    writer.write(out)
    got = ocr(out.getvalue(), "pdf", fake_tesseract(tmp_path), max_pages=3)
    assert got == OcrResult("ok", 3, (SAMPLE_TSV, "", SAMPLE_TSV))


def test_pdf_without_images_has_nothing_to_read(tmp_path):
    binary = fake_tesseract(tmp_path)
    assert ocr(text_pdf(pages=2), "pdf", binary) == OcrResult("failed", 2, (), "no_text")
    assert not (tmp_path / "call.json").exists()


def test_image_over_the_pixel_limit_is_not_decoded(tmp_path):
    binary = fake_tesseract(tmp_path)
    assert ocr(image((300, 300)), "image", binary, max_pixels=10_000).note == "too_many_pixels"
    assert ocr(pdf_of(Image.new("L", (300, 300), 255)), "pdf", binary, max_pixels=10_000).note == "too_many_pixels"
    assert not (tmp_path / "call.json").exists()


def lying_pdf(real: tuple[int, int], declared: tuple[int, int]) -> bytes:
    """PDF scan mà /Width, /Height của ảnh nhúng (JPEG) khai nhỏ hơn ảnh thật."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, NumberObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_of(Image.new("L", real, 255)))))
    xobjects = writer.pages[0]["/Resources"]["/XObject"]
    for name in xobjects:
        obj = xobjects[name].get_object()
        obj[NameObject("/Width")], obj[NameObject("/Height")] = NumberObject(declared[0]), NumberObject(declared[1])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.mark.parametrize("real", [(300, 300), (120, 120)], ids=["quá-gấp-đôi-trần", "vượt-trần-chưa-gấp-đôi"])
def test_pdf_image_larger_than_declared_stops_before_decoding(tmp_path, monkeypatch, real):
    from PIL import ImageFile

    from svc_files.docread.ocr import _Fail, pdf_images

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", Image.MAX_IMAGE_PIXELS)     # trả lại trần mặc định sau test
    decoded: list[tuple[int, int]] = []
    load = ImageFile.ImageFile.load
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: decoded.append(self.size) or load(self))
    data = lying_pdf(real, (50, 50))                 # khai 2 500 điểm ảnh, qua được bước kiểm kích thước khai
    _, images = pdf_images(data, 1, 10_000)
    with pytest.raises(_Fail) as exc:
        next(images)
    # dừng ở bước Pillow mở ảnh (DecompressionBombError, hoặc cảnh báo thành lỗi), không phải đo sau khi giải mã
    assert exc.value.note == "too_many_pixels"
    assert type(exc.value.__cause__).__name__ in ("DecompressionBombError", "DecompressionBombWarning")
    assert decoded == []
    # cả đường thật: tiến trình con, không gọi tesseract
    binary = fake_tesseract(tmp_path)
    assert ocr(data, "pdf", binary, max_pixels=10_000).note == "too_many_pixels"
    assert not (tmp_path / "call.json").exists()


@pytest.mark.parametrize("data", [b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, b"\xff\xd8\xff" + b"rac" * 100, b""],
                         ids=["png-hong", "jpeg-hong", "rong"])
def test_broken_images_never_raise(tmp_path, data):
    assert ocr(data, "image", fake_tesseract(tmp_path)).note == "corrupt"


def test_password_pdf(tmp_path):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_of(Image.new("L", (600, 800), 255)))))
    writer.encrypt(user_password="bi-mat", owner_password="chu", algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    assert ocr(out.getvalue(), "pdf", fake_tesseract(tmp_path)).note == "password"


def test_missing_tesseract_and_engine_failure_are_server_errors(tmp_path):
    assert ocr(image(), "image", tmp_path / "khong-co").note == "no_tesseract"
    assert ocr(image(), "image", fake_tesseract(tmp_path, exit_code=1)).note == "engine_failed"


@pytest.mark.parametrize(("sig", "note"), [
    (signal.SIGKILL, "memory"),          # bộ diệt OOM, cgroup của container
    (signal.SIGABRT, "memory"),          # std::bad_alloc không bắt
    (signal.SIGXCPU, "timeout"),         # hết RLIMIT_CPU
    (signal.SIGSEGV, "corrupt"),         # ảnh làm bộ giải mã sập
], ids=["SIGKILL", "SIGABRT", "SIGXCPU", "SIGSEGV"])
def test_tesseract_killed_by_a_signal_is_a_file_error(tmp_path, sig, note):
    got = ocr(image(), "image", fake_tesseract(tmp_path, kill=sig))
    assert got.status == "failed" and got.note == note and note not in SERVER_NOTES


def test_tesseract_reporting_out_of_memory_is_memory_not_a_server_error(tmp_path):
    for i, stderr in enumerate(("Error in pixCreateNoInit: pix_malloc fail for data\nError during processing.\n",
                                "terminate called after throwing an instance of 'std::bad_alloc'\n")):
        (tmp_path / str(i)).mkdir()
        assert ocr(image(), "image", fake_tesseract(tmp_path / str(i), exit_code=1, stderr=stderr)).note == "memory"
    # thiếu dữ liệu ngôn ngữ: vẫn là lỗi máy chủ
    (tmp_path / "vie").mkdir()
    binary = fake_tesseract(tmp_path / "vie", exit_code=1,
                            stderr="Failed loading language 'vie'\nTesseract couldn't load any languages!\n")
    assert ocr(image(), "image", binary).note == "engine_failed"


def _gone(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0]
    except FileNotFoundError:
        return True
    return state in ("Z", "X")       # đã chết, chờ được dọn


def test_timeout_kills_the_whole_process_group(tmp_path):
    binary = fake_tesseract(tmp_path, sleep_s=10)
    start = time.monotonic()
    got = ocr(image(), "image", binary, timeout_s=2)
    assert got == OcrResult("failed", None, (), "timeout")
    assert time.monotonic() - start < 5
    pid = int((tmp_path / "pid").read_text())        # tesseract (tiến trình cháu) đã chạy tới lúc ngủ
    for _ in range(50):
        if _gone(pid):
            break
        time.sleep(0.05)
    assert _gone(pid), "tesseract còn chạy sau khi hết giờ"


def test_cancelled_request_kills_the_group_too(tmp_path):
    binary = fake_tesseract(tmp_path, sleep_s=10)

    async def cancel_midway() -> None:
        task = asyncio.create_task(run_ocr(image(), "image", binary=str(binary), timeout_s=30))
        for _ in range(100):
            if (tmp_path / "pid").exists():
                break
            await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_midway())
    pid = int((tmp_path / "pid").read_text())
    for _ in range(50):
        if _gone(pid):
            break
        time.sleep(0.05)
    assert _gone(pid)


@pytest.mark.parametrize("out", [
    b'{"status": "ok", "pages": 1, "tsv": []}',
    b'{"status": "ok", "pages": 1, "tsv": ["a"], "note": "timeout"}',
    b'{"status": "failed", "pages": 1, "tsv": ["a"], "note": "timeout"}',
    b'{"status": "failed", "pages": 1, "tsv": [], "note": "la"}',
    b'{"status": "failed", "pages": 1, "tsv": [], "note": {}}',
    b'{"status": "ok", "pages": -2, "tsv": ["a"]}',
    b'{"status": "ok", "pages": 1, "tsv": ["a", "b"]}',             # nhiều trang hơn đã xin
    b'{"status": "ok", "pages": 1, "tsv": [3]}',
    b'{"status": "ok", "pages": 1, "tsv": "a"}',
    b'null', b'khong phai json',
])
def test_child_output_is_checked(out):
    assert _parse(out, max_pages=1) == OcrResult("failed", None, (), "corrupt")


def test_child_output_that_fits_is_kept():
    assert _parse(b'{"status": "ok", "pages": 2, "tsv": ["a"], "note": null}', 1) == OcrResult("ok", 2, ("a",))
    assert _parse(b'{"status": "failed", "pages": null, "tsv": [], "note": "no_text"}', 1).note == "no_text"


def test_child_runs_isolated_from_the_service_environment(tmp_path, monkeypatch):
    # tesseract chỉ nhận PATH, OMP_THREAD_LIMIT (và TESSDATA_PREFIX nếu có): bí mật của svc-files không lọt sang
    monkeypatch.setenv("HASURA_ADMIN_SECRET", "bi-mat")
    directory = tmp_path
    path = directory / "tesseract"
    path.write_text(f"#!{os.sys.executable}\nimport json, os, sys\n"
                    f"json.dump(dict(os.environ), open({str(directory / 'env.json')!r}, 'w'))\n"
                    "sys.stdin.buffer.read(); sys.stdout.write('level\\n')\n", encoding="utf-8")
    path.chmod(0o755)
    assert ocr(image(), "image", path).status == "ok"
    env = json.loads((directory / "env.json").read_text())
    assert "HASURA_ADMIN_SECRET" not in env and env["OMP_THREAD_LIMIT"] == "1"
