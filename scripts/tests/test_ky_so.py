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

"""Ký số văn bản đi (F4.5, chỉ minh họa): hàm thuần của scripts/moc_env.py mà smoke.py và make demo-ky-so dùng — cuối
phần đã ký (/ByteRange), lật một bit trong phần đã ký, lệnh kiểm chữ ký trong svc-files, đọc CA trong két, đoạn thêm lớp
sửa bổ sung — trên PDF giả có /ByteRange; hàm phụ của màn demo; tên smoke.py, demo.py nhập từ moc_env có thật; câu kết
luận của CLI (svc_files/signing.py) đúng câu demo, smoke đợi. Không cần Docker, không đọc .env: moc_env thật nạp từ bản
chép kèm .env giả. Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib
import importlib.util
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
SIGNING = ROOT / "services" / "svc-files" / "src" / "svc_files" / "signing.py"
COMPOSE = ["docker", "compose", "--profile", "core", "--profile", "app"]
# Dòng đầu (kết luận) của python -m svc_files.signing verify theo hợp đồng F4.5 §7 — demo.py, smoke.py đợi đúng các
# câu này
VERDICTS = {"valid": "Chữ ký hợp lệ", "modified": "Văn bản đã bị sửa sau khi ký",
            "broken": "Chữ ký không khớp nội dung"}

env: Any = None
demo: Any = None
_saved: dict[str, Any] = {}
_tmp: tempfile.TemporaryDirectory | None = None


def setUpModule() -> None:
    """moc_env thật đọc .env ở thư mục gốc lúc nạp (thiếu thì thoát): nạp bản chép của nó trong thư mục tạm có .env giả
    (tên module riêng, không đụng moc_env của test khác). demo.py nạp với moc_env giả như các test khác — mọi lời gọi
    mạng, Docker đều là lỗi."""
    global env, demo, _tmp
    _tmp = tempfile.TemporaryDirectory()
    root = pathlib.Path(_tmp.name)
    (root / "scripts").mkdir()
    shutil.copy(SCRIPTS / "moc_env.py", root / "scripts" / "moc_env.py")
    (root / ".env").write_text("MOC_PUBLIC_URL=http://localhost:8080\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("moc_env_ky_so", root / "scripts" / "moc_env.py")
    env = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(env)

    for name in ("moc_env", "demo", "seed_documents"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng, Docker")

    stub.ENV = {}
    stub.ROOT = ROOT
    stub.PUBLIC_URL = "http://localhost:8080"
    stub.EICAR = b""
    stub.HTTPError = type("HTTPError", (Exception,), {})
    stub.Session = type("Session", (), {"__init__": no_network})
    for name in ("call_json", "compose", "request", "text_pdf", "user_token"):
        setattr(stub, name, no_network)
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    demo = importlib.import_module("demo")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))
    if _tmp is not None:
        _tmp.cleanup()


def fake_signed(base: bytes, contents_len: int = 64) -> bytes:
    """PDF giả có chữ ký kiểu pyHanko: ghi nối một đối tượng /Sig mà /ByteRange [0 a c d] chừa đúng chuỗi hex /Contents
    <…> (cả hai dấu ngoặc nhọn), số trong /ByteRange đệm dấu cách tới độ rộng cố định như pyHanko."""
    prefix = base + b"9 0 obj\n<</Type/Sig/Filter/Adobe.PPKLite/SubFilter/ETSI.CAdES.detached/ByteRange "
    width, after = 40, b"/Contents "
    a = len(prefix) + width + len(after)
    contents = b"<" + b"0" * contents_len + b">"
    tail = b"/M(D:20261023101245+07'00')>>\nendobj\n%%EOF\n"
    c = a + len(contents)
    byte_range = (b"[0 %d %d %d" % (a, c, len(tail))).ljust(width - 1) + b"]"
    return prefix + byte_range + after + contents + tail


def stream_data_start(pdf: bytes, nth: int = 0) -> int:
    """Byte đầu dữ liệu của stream thứ nth (sau từ khóa stream và dấu xuống dòng)."""
    found = [m.end() for m in re.finditer(rb"(?<!end)stream(?:\r\n|\n)", pdf)]
    return found[nth]


def fake_run(code: int, stdout: bytes, stderr: bytes = b"") -> tuple[Any, list[dict[str, Any]]]:
    """subprocess.run giả cho moc_env.compose (check=True: mã khác 0 thì ném CalledProcessError như thật)."""
    calls: list[dict[str, Any]] = []

    def run(cmd: list[str], *, cwd: Any = None, input: bytes | None = None, check: bool = False,
            capture_output: bool = False) -> subprocess.CompletedProcess:
        calls.append({"cmd": cmd, "cwd": cwd, "input": input})
        if check and code:
            raise subprocess.CalledProcessError(code, cmd, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)

    return run, calls


def pem_of(*ders: bytes, eol: str = "\n") -> str:
    blocks = []
    for der in ders:
        body = textwrap.wrap(base64.b64encode(der).decode(), 64)
        blocks.append(eol.join(["-----BEGIN CERTIFICATE-----", *body, "-----END CERTIFICATE-----"]))
    return eol.join(blocks) + eol


class ByteRangeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = env.text_pdf("Cong van so 141/CNTT-DT", "Ban phat hanh co chu ky so")
        self.signed = fake_signed(self.base)

    def test_signature_covers_whole_file(self) -> None:
        self.assertEqual(env.byte_range_end(self.signed), len(self.signed))

    def test_bytes_appended_after_signing(self) -> None:
        # lớp sửa bổ sung (hay byte rác) nối sau: phần đã ký vẫn là đúng bản phát hành
        edited = self.signed + b"\n% them sau khi ky\n"
        self.assertEqual(env.byte_range_end(edited), len(self.signed))
        self.assertEqual(edited[:env.byte_range_end(edited)], self.signed)

    def test_unsigned_pdf(self) -> None:
        self.assertIsNone(env.byte_range_end(self.base))
        self.assertIsNone(env.byte_range_end(b"khong phai pdf"))

    def test_last_of_several_signatures(self) -> None:
        twice = fake_signed(self.signed)
        self.assertEqual(env.byte_range_end(twice), len(twice))
        self.assertEqual(env.byte_range_end(twice[:len(self.signed)]), len(self.signed))

    def test_malformed_byte_ranges_are_ignored(self) -> None:
        not_from_start = self.signed.replace(b"/ByteRange [0 ", b"/ByteRange [5 ")
        self.assertEqual(len(not_from_start), len(self.signed))
        self.assertIsNone(env.byte_range_end(not_from_start))
        self.assertIsNone(env.byte_range_end(self.signed[:-5]))     # phần sau vượt quá cuối tệp: tệp bị cắt
        broken = self.signed.replace(b"/ByteRange [0 ", b"/ByteRange [0 x")
        self.assertIsNone(env.byte_range_end(broken))


class FlipTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = env.text_pdf("Cong van so 141/CNTT-DT", "Ban phat hanh co chu ky so")
        self.signed = fake_signed(self.base)

    def diff(self, a: bytes, b: bytes) -> list[int]:
        self.assertEqual(len(a), len(b))
        return [i for i in range(len(a)) if a[i] != b[i]]

    def test_flips_one_bit_of_the_eighth_byte_of_the_first_stream(self) -> None:
        flipped = env.flip_in_signed_stream(self.signed)
        changed = self.diff(self.signed, flipped)
        self.assertEqual(changed, [stream_data_start(self.signed) + 7])
        self.assertEqual(self.signed[changed[0]] ^ flipped[changed[0]], 1)
        self.assertLess(changed[0], self.signed.index(b"/Contents <"))      # trong khoảng ký thứ nhất
        self.assertEqual(env.byte_range_end(flipped), len(flipped))         # /ByteRange, chữ ký còn nguyên
        self.assertIn(b"stream\nBT /F1 12 Tf", self.base)                   # đúng stream nội dung của trang

    def test_skips_structure_streams_and_short_streams(self) -> None:
        # đối tượng nén (ObjStm), bảng xref dạng stream, stream ngắn hơn 8 byte: lật ở đó thì tệp không đọc được, hay
        # không có byte thứ 8 — bỏ qua, lật ở stream nội dung sau
        extra = (b"20 0 obj\n<</Type /ObjStm/N 1/First 5/Length 24>>\nstream\n21 0 <</Type/Catalog>>   \nendstream\n"
                 b"endobj\n22 0 obj\n<</Length 3>>\nstream\nabc\nendstream\nendobj\n"
                 b"23 0 obj\n<</Type/XRef/Size 3/W[1 2 1]/Length 12>>\nstream\n000000000000\nendstream\nendobj\n")
        base = self.base.replace(b"1 0 obj\n", extra + b"1 0 obj\n", 1)
        signed = fake_signed(base)
        self.assertEqual(self.diff(signed, env.flip_in_signed_stream(signed)), [stream_data_start(signed, 3) + 7])

    def test_crlf_after_stream_keyword(self) -> None:
        base = self.base.replace(b"stream\nBT", b"stream\r\nBT")
        signed = fake_signed(base)
        self.assertEqual(self.diff(signed, env.flip_in_signed_stream(signed)),
                         [base.index(b"stream\r\nBT") + len(b"stream\r\n") + 7])

    def test_needs_a_signature_and_a_stream_inside_it(self) -> None:
        with self.assertRaises(ValueError):
            env.flip_in_signed_stream(self.base)
        with self.assertRaises(ValueError):
            env.flip_in_signed_stream(fake_signed(b"%PDF-1.7\n1 0 obj\n<</Type/Catalog>>\nendobj\n"))


class IncrementalEditTest(unittest.TestCase):
    def test_snippet_compiles_and_appends(self) -> None:
        compile(env.INCREMENTAL_EDIT, "<INCREMENTAL_EDIT>", "exec")
        self.assertIn("incremental=True", env.INCREMENTAL_EDIT)
        self.assertIn("FreeText", env.INCREMENTAL_EDIT)
        self.assertNotIn("clone_from", env.INCREMENTAL_EDIT)   # pypdf 6: clone_from chép lại cả tệp, không ghi nối

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "cần pypdf (có sẵn trong svc-files)")
    def test_runs_with_pypdf(self) -> None:
        src = env.text_pdf("Cong van so 141/CNTT-DT")
        out = subprocess.run([sys.executable, "-c", env.INCREMENTAL_EDIT], input=src, capture_output=True, check=True)
        self.assertTrue(out.stdout.startswith(src), "phần cũ phải giữ nguyên từng byte")
        self.assertIn(b"/FreeText", out.stdout[len(src):])


class ComposeHelpersTest(unittest.TestCase):
    def test_signature_cli_valid(self) -> None:
        run, calls = fake_run(0, "Chữ ký hợp lệ — PKI nội bộ Signet (MẪU)\nKý bởi: Khoa CNTT\n".encode())
        with mock.patch.object(env.subprocess, "run", run):
            code, lines = env.signature_cli(b"%PDF-1.7 da ky")
        self.assertEqual((code, lines), (0, ["Chữ ký hợp lệ — PKI nội bộ Signet (MẪU)", "Ký bởi: Khoa CNTT"]))
        self.assertEqual(calls, [{"cmd": [*COMPOSE, "exec", "-T", "svc-files", "python", "-m", "svc_files.signing",
                                          "verify"], "cwd": env.ROOT, "input": b"%PDF-1.7 da ky"}])

    def test_signature_cli_passes_exit_code_and_ignores_warnings(self) -> None:
        run, _ = fake_run(1, "Văn bản đã bị sửa sau khi ký: …\n".encode(), b"WARNING pyhanko: SuspiciousModification\n")
        with mock.patch.object(env.subprocess, "run", run):
            self.assertEqual(env.signature_cli(b"x"), (1, ["Văn bản đã bị sửa sau khi ký: …"]))

    def test_signature_cli_error_on_stderr(self) -> None:
        run, _ = fake_run(2, b"", "Không lấy được chứng thư CA nội bộ từ két\n".encode())
        with mock.patch.object(env.subprocess, "run", run):
            self.assertEqual(env.signature_cli(b"x"), (2, ["Không lấy được chứng thư CA nội bộ từ két"]))

    def test_vault_ca_pem(self) -> None:
        pem = pem_of(b"\x30\x03\x02\x01\x01")
        run, calls = fake_run(0, pem.encode())
        with mock.patch.object(env.subprocess, "run", run):
            self.assertEqual(env.vault_ca_pem(), pem)
        self.assertEqual(calls[0]["cmd"], [*COMPOSE, "exec", "-T", "openbao", "wget", "-qO-",
                                           "http://127.0.0.1:8200/v1/pki/ca/pem"])

    def test_vault_without_pki(self) -> None:
        # két khởi tạo trước F4.5: pki/ca/pem trả 403/404 → busybox wget thoát 1; trả gì khác PEM cũng coi như không có
        for code, out in ((1, b""), (0, b'{"errors":["permission denied"]}')):
            run, _ = fake_run(code, out, b"wget: server returned error: HTTP/1.1 403 Forbidden\n")
            with mock.patch.object(env.subprocess, "run", run):
                self.assertIsNone(env.vault_ca_pem())


class DemoHelpersTest(unittest.TestCase):
    def test_pem_fingerprint(self) -> None:
        der, other = bytes(range(256)) * 3, b"chung thu thu hai"
        digest = hashlib.sha256(der).hexdigest().upper()
        want = ":".join(digest[i:i + 2] for i in range(0, 64, 2))
        self.assertEqual(demo.pem_fingerprint(pem_of(der)), want)
        self.assertEqual(demo.pem_fingerprint(pem_of(der, other)), want)          # chuỗi chứng thư: lấy cái đầu
        self.assertEqual(demo.pem_fingerprint(pem_of(der, eol="\r\n")), want)
        self.assertEqual(len(want), 95)

    def test_local_time(self) -> None:
        moment = datetime(2026, 10, 23, 3, 12, 45, tzinfo=timezone.utc).astimezone()
        want = moment.strftime("%H:%M:%S %d/%m/%Y")
        self.assertEqual(demo.local_time("2026-10-23T03:12:45Z"), want)
        self.assertEqual(demo.local_time("2026-10-23T10:12:45+07:00"), want)


def moc_env_imports(tree: ast.AST) -> set[str]:
    return {a.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "moc_env"
            for a in node.names}


def string_constants(tree: ast.AST) -> list[str]:
    """Mọi chuỗi hằng trong mã (chuỗi viết liền nhiều dòng đã được ast ghép; f-string lấy từng phần hằng)."""
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


class WiringTest(unittest.TestCase):
    def test_names_imported_from_moc_env_exist(self) -> None:
        # smoke.py, demo.py chạy cả từ bản cài (make install): mọi tên nhập từ moc_env phải có trong moc_env thật
        for script in ("smoke.py", "demo.py"):
            names = moc_env_imports(ast.parse((SCRIPTS / script).read_text(encoding="utf-8")))
            self.assertTrue(names, script)
            self.assertEqual(sorted(n for n in names if not hasattr(env, n)), [], script)
        ky_so = next(n for n in ast.parse((SCRIPTS / "demo.py").read_text(encoding="utf-8")).body
                     if isinstance(n, ast.FunctionDef) and n.name == "ky_so")
        self.assertLessEqual({"INCREMENTAL_EDIT", "byte_range_end", "flip_in_signed_stream", "signature_cli",
                              "vault_ca_pem"}, moc_env_imports(ky_so))

    def test_demo_expects_the_cli_verdicts(self) -> None:
        for script in ("smoke.py", "demo.py"):
            strings = string_constants(ast.parse((SCRIPTS / script).read_text(encoding="utf-8")))
            for status, prefix in VERDICTS.items():
                self.assertIn(prefix, strings, f"{script} đợi dòng đầu {status} của CLI")

    @unittest.skipUnless(SIGNING.exists(), "chưa có services/svc-files/src/svc_files/signing.py (luồng B)")
    def test_cli_prints_the_verdicts_demo_expects(self) -> None:
        strings = string_constants(ast.parse(SIGNING.read_text(encoding="utf-8")))
        for status, prefix in VERDICTS.items():
            self.assertTrue(any(s.startswith(prefix) for s in strings),
                            f"svc_files/signing.py không có câu {status} bắt đầu bằng \"{prefix}\" (hợp đồng F4.5 §7) —"
                            " smoke.py, demo.py đọc dòng đầu này")

    def test_demo_and_make_target(self) -> None:
        self.assertIs(demo.DEMOS["ky-so"], demo.ky_so)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        phony = re.search(r"^\.PHONY:((?:.*\\\n)*.*)$", makefile, re.M).group(1).replace("\\\n", " ")
        self.assertRegex(makefile, r"(?m)^demo-ky-so: \$\(ENV_FILE\) ## .*chỉ minh họa")
        self.assertRegex(makefile, r"scripts/demo\.py ky-so\b")
        self.assertIn("demo-ky-so", phony.split())
        self.assertRegex(makefile, r"(?m)^e2e: .*## .*ký số")


if __name__ == "__main__":
    unittest.main()
