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

"""Mốc neo công khai: kiểm chữ ký Ed25519 bằng Python thuần (scripts/anchor_sig.py) theo vectơ RFC 8032 và vectơ của
svc-files (services/svc-files/tests/test_anchors.py); `moc audit anchor --to` chép mốc kèm chữ ký; `--publish` commit
vào một bản sao git và đẩy lên kho trần tạm, không bao giờ ép; `moc audit verify --anchors` với chữ ký đúng, sai, thiếu
khóa, mốc chưa ký; policy và khóa moc-anchor trong platform/openbao/start.sh; unit systemd; lệnh OpenSSL trong
docs/van-hanh.md kiểm được dòng mốc mẫu. Không cần Docker, không đọc .env (moc_env giả như test_tenants.py).
Chạy: python3 -m unittest discover -s scripts/tests (make test)."""

from __future__ import annotations

import ast
import base64
import contextlib
import hashlib
import importlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from typing import Any
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent

moc: Any = None
anchor_sig: Any = None
_saved: dict[str, Any] = {}

# Khóa của RFC 8032 §7.1 TEST 1; thông điệp, chữ ký, vân tay như trong services/svc-files/tests/test_anchors.py (két ký
# bằng thư viện cryptography) và đã kiểm bằng `openssl pkeyutl -verify -rawin` (OpenSSL 3.0.13)
SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
VECTOR_MESSAGE = ("signet-anchor-v1\n42\n" + "ab" * 32 + "\n2026-10-25T01:15:03Z\nhttps://signet.example\n").encode()
VECTOR_SIG = "6Zd3HmfkSkXWyDilTfzxhSy+lofvdwd0rrAJRzWQ0ckGfon3GIc8VcXlfgOsYs05o3GdSErLU9MKfBUSWieVBA=="
VECTOR_KEY = "sha256:06e3fd8fda29bb60ab59557de61edb0aecdb231134be30e75b455f8e1b792fa9"
VECTOR_PEM = ("-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=\n"
              "-----END PUBLIC KEY-----\n")
SYSTEM = "https://signet.example"
# RFC 8032 §7.1 TEST 1–3: (khóa công khai, thông điệp, chữ ký)
RFC_VECTORS = [
    ("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


def setUpModule() -> None:
    """moc_env thật đọc .env lúc nạp (thiếu thì thoát): thay bằng bản giả chỉ có những gì moc.py cần."""
    global moc, anchor_sig
    for name in ("moc_env", "moc", "backup", "tenants", "anchor_sig"):
        _saved[name] = sys.modules.pop(name, None)
    stub = types.ModuleType("moc_env")
    stub.ENV = {"MOC_PUBLIC_URL": SYSTEM}
    stub.ROOT = ROOT
    stub.REALM = "moc"
    stub.KEYCLOAK_ADMIN_URL = "http://127.0.0.1:8180"
    stub.PUBLIC_URL = SYSTEM
    stub.HTTPError = RuntimeError

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("test không được gọi mạng")

    stub.call_json = no_network
    sys.modules["moc_env"] = stub
    sys.path.insert(0, str(SCRIPTS))
    anchor_sig = importlib.import_module("anchor_sig")
    moc = importlib.import_module("moc")


def tearDownModule() -> None:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    sys.path.remove(str(SCRIPTS))


# --- ký Ed25519 cho test (RFC 8032 §5.1.6): két ký thật trên máy chủ, ở đây chỉ để dựng mốc có chữ ký ---------------

def _compress(point: tuple[int, int, int, int]) -> bytes:
    p = anchor_sig._P
    zinv = pow(point[2], p - 2, p)
    x, y = point[0] * zinv % p, point[1] * zinv % p
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def ed25519_sign(seed: bytes, message: bytes) -> tuple[bytes, bytes]:
    """→ (khóa công khai 32 byte, chữ ký 64 byte)."""
    h = hashlib.sha512(seed).digest()
    a = (int.from_bytes(h[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    public = _compress(anchor_sig._mul(a, anchor_sig._G))
    r = int.from_bytes(hashlib.sha512(h[32:] + message).digest(), "little") % anchor_sig._L
    big_r = _compress(anchor_sig._mul(r, anchor_sig._G))
    k = int.from_bytes(hashlib.sha512(big_r + public + message).digest(), "little") % anchor_sig._L
    return public, big_r + ((r + k * a) % anchor_sig._L).to_bytes(32, "little")


def pem_of(seed: bytes) -> str:
    public, _ = ed25519_sign(seed, b"")
    der = anchor_sig.SPKI_PREFIX + public
    return f"-----BEGIN PUBLIC KEY-----\n{base64.b64encode(der).decode()}\n-----END PUBLIC KEY-----\n"


def signed_line(audit_id: int, hash_hex: str, at: str = "2026-10-25T01:15:03Z", *, seed: bytes = SEED,
                system: str = SYSTEM) -> dict[str, Any]:
    """Dòng mốc như `moc audit anchor --to` ghi khi két có khóa."""
    public, sig = ed25519_sign(seed, anchor_sig.message(audit_id, hash_hex, at, system))
    return {"v": "signet-anchor-v1", "audit_id": audit_id, "hash": hash_hex, "anchored_at": at, "system": system,
            "key": anchor_sig.fingerprint(public), "sig": base64.b64encode(sig).decode()}


# --- anchor_sig.py --------------------------------------------------------------------------------------------------


class Ed25519Test(unittest.TestCase):
    def test_rfc8032_vectors(self) -> None:
        for public, message, sig in RFC_VECTORS:
            pk, msg, signature = bytes.fromhex(public), bytes.fromhex(message), bytes.fromhex(sig)
            self.assertTrue(anchor_sig.ed25519_verify(pk, msg, signature))
            self.assertFalse(anchor_sig.ed25519_verify(pk, msg + b"x", signature))
            for i in (0, 31, 32, 63):                   # lật một bit ở R, ở S
                bad = bytearray(signature)
                bad[i] ^= 1
                self.assertFalse(anchor_sig.ed25519_verify(pk, msg, bytes(bad)))
            # S + L: cùng điểm nhưng không chuẩn tắc — RFC 8032 bắt từ chối (chống chữ ký biến dạng)
            s = int.from_bytes(signature[32:], "little") + anchor_sig._L
            self.assertFalse(anchor_sig.ed25519_verify(pk, msg, signature[:32] + s.to_bytes(32, "little")))
        self.assertFalse(anchor_sig.ed25519_verify(b"\x00" * 31, b"", bytes(64)))

    def test_test_signer_reproduces_the_rfc_and_vault_signatures(self) -> None:
        public, sig = ed25519_sign(SEED, b"")
        self.assertEqual((public.hex(), sig.hex()), RFC_VECTORS[0][::2])
        self.assertEqual(base64.b64encode(ed25519_sign(SEED, VECTOR_MESSAGE)[1]).decode(), VECTOR_SIG)

    def test_signet_vector_message_key_and_fingerprint(self) -> None:
        self.assertEqual(anchor_sig.message(42, "ab" * 32, "2026-10-25T01:15:03Z", SYSTEM), VECTOR_MESSAGE)
        keys = anchor_sig.public_keys(VECTOR_PEM)
        self.assertEqual(list(keys), [VECTOR_KEY])
        self.assertTrue(anchor_sig.ed25519_verify(keys[VECTOR_KEY], VECTOR_MESSAGE, base64.b64decode(VECTOR_SIG)))
        for bad in ((42, "AB" * 32, "2026-10-25T01:15:03Z", SYSTEM), (42, "ab" * 32, "2026-10-25 01:15:03", SYSTEM),
                    (0, "ab" * 32, "2026-10-25T01:15:03Z", SYSTEM), (42, "ab" * 32, "2026-10-25T01:15:03Z", "a\nb")):
            with self.assertRaises(ValueError):
                anchor_sig.message(*bad)

    def test_public_keys_reads_several_blocks_and_refuses_other_key_types(self) -> None:
        other = pem_of(b"\x01" * 32)
        self.assertEqual(len(anchor_sig.public_keys(VECTOR_PEM + "\n" + other)), 2)
        x25519 = bytes.fromhex("302a300506032b656e032100") + bytes(32)      # OID của X25519, không phải Ed25519
        for text in ("", "không phải PEM",
                     f"-----BEGIN PUBLIC KEY-----\n{base64.b64encode(x25519).decode()}\n-----END PUBLIC KEY-----"):
            with self.assertRaises(ValueError):
                anchor_sig.public_keys(text)

    def test_check_every_field_is_covered(self) -> None:
        keys = anchor_sig.public_keys(VECTOR_PEM)
        line = signed_line(42, "ab" * 32)
        self.assertEqual((line["key"], line["sig"]), (VECTOR_KEY, VECTOR_SIG))
        self.assertEqual(anchor_sig.check(line, keys), "valid")
        for field, value in (("audit_id", 43), ("hash", "ac" + "ab" * 31), ("anchored_at", "2026-10-25T01:15:04Z"),
                             ("system", "https://signet.example/"), ("v", "signet-anchor-v2"), ("sig", "!!")):
            self.assertEqual(anchor_sig.check({**line, field: value}, keys), "invalid", field)
        self.assertEqual(anchor_sig.check({**line, "key": "sha256:" + "0" * 64}, keys), "unknown_key")
        self.assertEqual(anchor_sig.check({"audit_id": 42, "hash": "ab" * 32}, keys), "unsigned")

    def test_unsigned_line_after_a_signed_one_is_a_removed_signature(self) -> None:
        """Gỡ "key", "sig" khỏi một dòng đã ký thì dòng vẫn đúng dạng mốc cũ: chỉ thứ tự trong tệp lộ ra điều đó."""
        keys = anchor_sig.public_keys(VECTOR_PEM)
        old, good = {"audit_id": 7, "hash": "cd" * 32}, signed_line(42, "ab" * 32)
        stripped = {k: v for k, v in signed_line(43, "ef" * 32).items() if k not in ("key", "sig")}
        self.assertEqual(anchor_sig.check(stripped, keys), "unsigned")
        self.assertEqual(anchor_sig.check_all([old, good, stripped, old], keys),
                         ["unsigned", "valid", "unsigned_late", "unsigned_late"])
        # dòng ký sai vẫn là dòng có chữ ký: dòng chưa ký sau nó cũng bị bắt
        bad = {**good, "hash": "ee" * 32}
        self.assertEqual(anchor_sig.check_all([old, bad, stripped], keys), ["unsigned", "invalid", "unsigned_late"])

    def test_command_line_for_outsiders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path, key = pathlib.Path(tmp) / "anchors.jsonl", pathlib.Path(tmp) / "anchor-key.pem"
            key.write_text(VECTOR_PEM, encoding="utf-8")
            good, old = signed_line(42, "ab" * 32), {"audit_id": 7, "hash": "cd" * 32}

            def run(*lines: dict[str, Any]) -> tuple[int, str]:
                path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    code = anchor_sig.main([str(path), str(key)])
                return code, out.getvalue()

            code, out = run(old, good)
            self.assertEqual(code, 0)
            self.assertIn("chữ ký hợp lệ: 1", out)
            self.assertIn("chưa ký: 1", out)
            code, out = run(good, {**good, "anchored_at": "2026-10-25T01:15:04Z"})
            self.assertEqual(code, 1)
            self.assertIn("✗ dòng 2", out)
            self.assertEqual(run(signed_line(42, "ab" * 32, seed=b"\x02" * 32))[0], 2)
            code, out = run(old, good, {"audit_id": 43, "hash": "ef" * 32, "anchored_at": "2026-10-25T02:15:03Z"})
            self.assertEqual(code, 1)
            self.assertIn("✗ dòng 3", out)
            self.assertIn("CHƯA KÝ SAU DÒNG ĐÃ KÝ: 1", out)
            code, out = run(old)
            self.assertEqual(code, 2)                   # không dòng nào có chữ ký: chưa kiểm được gì
            self.assertIn("Không dòng nào có chữ ký", out)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(anchor_sig.main([str(path)]), 2)


# --- moc audit anchor --to / --publish ----------------------------------------------------------------------------


def anchored(audit_id: int = 42, hash_hex: str = "ab" * 32, *, signed: bool = True, new: bool = True) -> dict:
    """Kết quả `python -m svc_files.anchors now` (svc-files trong container)."""
    line = signed_line(audit_id, hash_hex)
    return {"anchored": {
        "audit_id": audit_id, "hash": hash_hex, "location": f"s3://moc-cold/anchors/{audit_id:012d}-{hash_hex}.json",
        "new": new, "anchored_at": line["anchored_at"],
        "signed": {k: line[k] for k in ("anchored_at", "system", "key", "sig")} if signed else None}}


class FakeTool:
    """`anchors_tool` giả: now, key, list; ghi lại lệnh đã gọi."""

    def __init__(self, now: dict | None = None, key: str | Exception | None = VECTOR_PEM,
                 bucket: list[dict] | None = None) -> None:
        self.now, self.key, self.bucket = now or anchored(), key, bucket or []
        self.calls: list[str] = []

    def __call__(self, command: str) -> dict:
        self.calls.append(command)
        if command == "now":
            return self.now
        if command == "key":
            if isinstance(self.key, Exception):
                raise self.key
            return {"key": {"version": 1, "fingerprint": "", "pem": self.key} if self.key else None}
        return {"bucket": "moc-cold", "locked": True, "anchors": self.bucket}


def run_moc(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = moc.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class AnchorToTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = self.tmp / "moc.jsonl"

    def test_signed_line_carries_exactly_the_signed_fields(self) -> None:
        with mock.patch.object(moc, "anchors_tool", FakeTool()):
            code, out, _ = run_moc("audit", "anchor", "--to", str(self.path))
            self.assertEqual(code, 0)
            self.assertIn("két đã ký mốc", out)
            [line] = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(line, signed_line(42, "ab" * 32))
            self.assertEqual(anchor_sig.check(line, anchor_sig.public_keys(VECTOR_PEM)), "valid")
            self.assertEqual(run_moc("audit", "anchor", "--to", str(self.path))[0], 0)
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)       # không ghi trùng

    def test_old_vault_writes_an_unsigned_line_with_the_bucket_time(self) -> None:
        self.path.write_text('{"audit_id": 7, "hash": "' + "cd" * 32 + '"}', encoding="utf-8")   # thiếu \n cuối
        with mock.patch.object(moc, "anchors_tool", FakeTool(now=anchored(signed=False), key=None)):
            code, out, _ = run_moc("audit", "anchor", "--to", str(self.path))
        self.assertEqual(code, 0)
        self.assertIn("không có chữ ký", out)
        old, line = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(line, {"audit_id": 42, "hash": "ab" * 32, "anchored_at": "2026-10-25T01:15:03Z",
                                "system": SYSTEM})

    def test_no_unsigned_line_once_the_vault_has_a_key(self) -> None:
        """Két có khóa mà không ký được (két không trả lời lúc ký): không ghi dòng chưa ký, thoát 2 để lượt sau ghi."""
        unsigned = anchored(43, "cd" * 32, signed=False)
        cases = {
            "két có khóa": (FakeTool(now=unsigned), None),
            "không hỏi được két": (FakeTool(now=unsigned, key=moc.Unavailable("két không trả lời")), None),
            "tệp đã có mốc có chữ ký": (FakeTool(now=unsigned, key=None), signed_line(42, "ab" * 32)),
        }
        for reason, (tool, first) in cases.items():
            with self.subTest(reason):
                self.path.write_text(json.dumps(first) + "\n" if first else "", encoding="utf-8")
                before = self.path.read_text(encoding="utf-8")
                with mock.patch.object(moc, "anchors_tool", tool):
                    code, _, err = run_moc("audit", "anchor", "--to", str(self.path))
                self.assertEqual(code, 2)
                self.assertIn("Không ghi mốc chưa ký", err)
                self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        (self.tmp / "anchor-key.pem").write_text(VECTOR_PEM, encoding="utf-8")
        self.path.unlink()
        with mock.patch.object(moc, "anchors_tool", FakeTool(now=unsigned, key=None)):
            code, _, err = run_moc("audit", "anchor", "--to", str(self.path))
        self.assertEqual(code, 2)
        self.assertIn("đã có khóa ký mốc", err)
        self.assertFalse(self.path.exists())


def git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout.strip()


# git của test không đọc cấu hình của máy (ký commit, hook…); người tạo kho trần là "người khác"
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "Người khác",
           "GIT_AUTHOR_EMAIL": "khac@example.invalid", "GIT_COMMITTER_NAME": "Người khác",
           "GIT_COMMITTER_EMAIL": "khac@example.invalid"}


@unittest.skipUnless(shutil.which("git"), "cần git")
class PublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        env = mock.patch.dict(os.environ, {k: v for k, v in GIT_ENV.items() if k.startswith("GIT_CONFIG")})
        env.start()
        self.addCleanup(env.stop)
        self.remote = self.tmp / "signet-anchors.git"
        git(self.tmp, "init", "--quiet", "--bare", "-b", "main", str(self.remote))
        self.work = self.tmp / "neo-cong-khai"
        git(self.tmp, "clone", "--quiet", str(self.remote), str(self.work))
        git(self.work, "symbolic-ref", "HEAD", "refs/heads/main")     # git cũ: kho rỗng clone về nhánh master
        self.git_calls: list[list[str]] = []
        real = subprocess.run

        def spy(cmd: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(cmd, list) and cmd[:1] == ["git"]:
                self.git_calls.append(cmd)
            return real(cmd, *args, **kwargs)

        patch = mock.patch.object(moc.subprocess, "run", spy)
        patch.start()
        self.addCleanup(patch.stop)

    def publish(self, tool: FakeTool, work: pathlib.Path | None = None) -> tuple[int, str, str]:
        with mock.patch.object(moc, "anchors_tool", tool):
            return run_moc("audit", "anchor", "--publish", str(work or self.work))

    def tearDown(self) -> None:
        # không lần gọi git nào được viết lại lịch sử, ở đây hay trên remote
        for cmd in self.git_calls:
            self.assertFalse({"--force", "-f", "--force-with-lease", "--mirror", "--amend", "--delete", "-d"}
                             & set(cmd), cmd)
            self.assertFalse(any(arg.startswith(("+", ":")) for arg in cmd[3:]), cmd)
            self.assertNotIn(cmd[3] if len(cmd) > 3 else "", {"reset", "rebase", "filter-branch", "update-ref"})

    def test_first_run_commits_line_and_key_with_the_fixed_author_and_pushes(self) -> None:
        code, out, err = self.publish(FakeTool())
        self.assertEqual(code, 0, err)
        self.assertIn("đã đẩy lên origin", out)
        log = git(self.remote, "log", "--format=%an <%ae>|%cn|%s", "main")
        self.assertEqual(log, "Signet anchor <anchor@signet.invalid>|Signet anchor|Anchor #42 abababababababab")
        self.assertEqual(git(self.remote, "ls-tree", "--name-only", "main").split(),
                         ["anchor-key.pem", "anchors.jsonl"])
        self.assertEqual(git(self.remote, "show", "main:anchor-key.pem") + "\n", VECTOR_PEM)
        [line] = git(self.remote, "show", "main:anchors.jsonl").splitlines()
        self.assertEqual(json.loads(line), signed_line(42, "ab" * 32))
        push = [c for c in self.git_calls if "push" in c]
        self.assertEqual([c[3:] for c in push], [["push", "--porcelain", "origin", "HEAD"]])

    def test_same_anchor_adds_no_commit_new_anchor_adds_one(self) -> None:
        self.publish(FakeTool())
        code, out, _ = self.publish(FakeTool(now=anchored(new=False)))
        self.assertEqual(code, 0)
        self.assertIn("không có gì mới", out)
        self.assertEqual(git(self.remote, "rev-list", "--count", "main"), "1")
        self.assertEqual(self.publish(FakeTool(now=anchored(43, "cd" * 32)))[0], 0)
        self.assertEqual(git(self.remote, "log", "--format=%s", "main").splitlines(),
                         ["Anchor #43 cdcdcdcdcdcdcdcd", "Anchor #42 abababababababab"])
        # lần sau chỉ thêm một dòng, không đụng dòng cũ, khóa không đổi
        diff = git(self.remote, "diff", "--numstat", "main~1", "main")
        self.assertEqual(diff, "1\t0\tanchors.jsonl")

    def test_a_new_vault_key_replaces_the_pem_and_history_keeps_the_old_one(self) -> None:
        self.publish(FakeTool())
        other = pem_of(b"\x03" * 32)
        self.publish(FakeTool(now=anchored(43, "cd" * 32), key=other))
        self.assertEqual(git(self.remote, "show", "main:anchor-key.pem") + "\n", other)
        self.assertEqual(git(self.remote, "show", "main~1:anchor-key.pem") + "\n", VECTOR_PEM)

    def test_diverged_remote_is_never_forced(self) -> None:
        """Ai đó đẩy commit khác lên nhánh công khai: push bị từ chối, lệnh báo lỗi, không ép đè lên."""
        self.publish(FakeTool())
        other = self.tmp / "khac"
        git(self.tmp, "clone", "--quiet", str(self.remote), str(other))
        (other / "GHI-CHU.md").write_text("ghi chú của người khác\n", encoding="utf-8")
        git(other, "add", "GHI-CHU.md")
        git(other, "commit", "--quiet", "-m", "Ghi chú")
        git(other, "push", "--quiet", "origin", "HEAD")
        theirs = git(self.remote, "rev-parse", "main")
        code, _, err = self.publish(FakeTool(now=anchored(43, "cd" * 32)))
        self.assertEqual(code, 2)
        self.assertIn("git push origin", err)
        self.assertIn("lần chạy sau đẩy tiếp", err)
        self.assertEqual(git(self.remote, "rev-parse", "main"), theirs)        # remote giữ nguyên
        self.assertEqual(git(self.work, "log", "-1", "--format=%s"), "Anchor #43 cdcdcdcdcdcdcdcd")   # commit còn

    def test_without_a_remote_only_commits_locally(self) -> None:
        local = self.tmp / "chi-o-may"
        git(self.tmp, "init", "--quiet", "-b", "main", str(local))
        code, out, _ = self.publish(FakeTool(), local)
        self.assertEqual(code, 0)
        self.assertIn("chưa có remote", out)
        self.assertEqual(git(local, "log", "--format=%an|%s"), "Signet anchor|Anchor #42 abababababababab")
        self.assertFalse([c for c in self.git_calls if "push" in c])

    def test_refuses_a_directory_that_is_not_a_git_working_copy(self) -> None:
        plain = self.tmp / "khong-phai-git"
        plain.mkdir()
        code, _, err = self.publish(FakeTool(), plain)
        self.assertEqual(code, 2)
        self.assertIn("không phải một bản sao git", err)
        self.assertFalse((plain / "anchors.jsonl").exists())

    def test_unsigned_anchor_without_vault_key_is_still_published(self) -> None:
        code, _, _ = self.publish(FakeTool(now=anchored(signed=False), key=None))
        self.assertEqual(code, 0)
        self.assertEqual(git(self.remote, "ls-tree", "--name-only", "main").split(), ["anchors.jsonl"])

    def test_key_file_is_written_only_with_a_signed_line(self) -> None:
        """Mốc đã ghi chưa ký trước khi két có khóa, đầu chuỗi chưa đổi: không có dòng ký nào nên chưa ghi khóa."""
        self.publish(FakeTool(now=anchored(signed=False), key=None))
        code, _, _ = self.publish(FakeTool(now=anchored(new=False)))
        self.assertEqual(code, 0)
        self.assertEqual(git(self.remote, "ls-tree", "--name-only", "main").split(), ["anchors.jsonl"])
        self.assertEqual(self.publish(FakeTool(now=anchored(43, "cd" * 32)))[0], 0)
        self.assertEqual(git(self.remote, "ls-tree", "--name-only", "main").split(),
                         ["anchor-key.pem", "anchors.jsonl"])

    def test_unsigned_anchor_after_signed_ones_is_never_published(self) -> None:
        self.publish(FakeTool())
        code, _, err = self.publish(FakeTool(now=anchored(43, "cd" * 32, signed=False), key=None))
        self.assertEqual(code, 2)
        self.assertIn("Không ghi mốc chưa ký", err)
        self.assertEqual(git(self.remote, "rev-list", "--count", "main"), "1")
        self.assertEqual(git(self.work, "status", "--porcelain"), "")


# --- moc audit verify --anchors ------------------------------------------------------------------------------------


GENESIS = "00" * 32


def chain(n: int) -> list[dict[str, Any]]:
    """n dòng sổ hợp lệ theo ROWS_SQL: hash = sha256(prev ‖ chuỗi JSON của dòng)."""
    rows, prev = [], GENESIS
    for i in range(1, n + 1):
        text = json.dumps([i, 1761350000 + i, None, "u-1", "user", f"r-{i}", "insert", "office.documents", f"d-{i}",
                           {"status": [None, "draft"]}])
        digest = hashlib.sha256(bytes.fromhex(prev) + text.encode()).hexdigest()
        rows.append({"id": i, "prev": prev, "hash": digest, "payload": text})
        prev = digest
    return rows


class FakeSnapshot:
    rows_data: list[dict[str, Any]] = []

    def __enter__(self) -> FakeSnapshot:
        self.now = 1793000000                       # sau mọi mốc trong test (2026-10-25)
        self.head = {"id": self.rows_data[-1]["id"], "hash": self.rows_data[-1]["hash"]}
        self.recorded: list[dict[str, Any]] = []
        self.documents: list[dict[str, Any]] = []
        return self

    def rows(self):
        yield from self.rows_data

    def __exit__(self, *exc: object) -> None:
        pass


class VerifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.rows = chain(3)
        FakeSnapshot.rows_data = self.rows
        patch = mock.patch.object(moc, "Snapshot", FakeSnapshot)
        patch.start()
        self.addCleanup(patch.stop)
        # bucket có mốc ở đầu chuỗi: lần kiểm đủ bằng chứng, chỉ còn phần tệp mốc để xét
        self.bucket = [{"audit_id": 3, "hash": self.rows[2]["hash"], "anchored_at": "2026-10-25T02:00:00+00:00",
                        "key": "anchors/x", "overwritten": False, "deleted": False}]
        self.path = self.tmp / "anchors.jsonl"

    def verify(self, *lines: dict[str, Any], key: str | None = None, extra: tuple[str, ...] = ()) -> tuple[int, dict]:
        self.path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
        with mock.patch.object(moc, "anchors_tool", FakeTool(key=key, bucket=self.bucket)):
            code, out, err = run_moc("audit", "verify", "--anchors", str(self.path), *extra, "--json")
        return code, json.loads(out) if out else {"stderr": err}

    def test_good_signature_with_the_key_next_to_the_file(self) -> None:
        (self.tmp / "anchor-key.pem").write_text(VECTOR_PEM, encoding="utf-8")
        code, report = self.verify(signed_line(2, self.rows[1]["hash"]))
        self.assertEqual(code, 0, report)
        self.assertEqual(report["signatures"]["anchors.jsonl"],
                         {"valid": 1, "invalid": 0, "unsigned": 0, "unsigned_late": 0, "unknown_key": 0})
        self.assertEqual(report["anchors"]["anchors.jsonl"], {"checked": 1, "matched": 1})

    def test_good_signature_with_the_vault_key_or_key_option(self) -> None:
        code, report = self.verify(signed_line(2, self.rows[1]["hash"]), key=VECTOR_PEM)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["signatures"]["anchors.jsonl"]["valid"], 1)
        key = self.tmp / "khoa.pem"
        key.write_text(VECTOR_PEM, encoding="utf-8")
        code, report = self.verify(signed_line(2, self.rows[1]["hash"]), extra=("--key", str(key)))
        self.assertEqual(code, 0, report)

    def test_bad_signature_is_an_error_and_the_line_is_not_used(self) -> None:
        """Dòng bị sửa sau khi ký: lỗi (thoát 1), và không được dùng để đối chiếu chuỗi."""
        (self.tmp / "anchor-key.pem").write_text(VECTOR_PEM, encoding="utf-8")
        forged = {**signed_line(2, self.rows[1]["hash"]), "hash": "ee" * 32}
        code, report = self.verify(signed_line(1, self.rows[0]["hash"]), forged)
        self.assertEqual(code, 1, report)
        self.assertEqual(report["signatures"]["anchors.jsonl"]["invalid"], 1)
        [problem] = report["problems"]
        self.assertEqual((problem["kind"], problem["audit_id"]), ("anchor_signature", 2))
        self.assertIn("dòng 2", problem["message"])
        self.assertIsNone(report["rewritten"])             # mốc giả không làm báo nhầm "chuỗi bị viết lại"
        self.assertEqual(report["anchors"]["anchors.jsonl"], {"checked": 1, "matched": 1})

    def test_signature_without_any_matching_key_is_not_enough_evidence(self) -> None:
        code, report = self.verify(signed_line(2, self.rows[1]["hash"], seed=b"\x04" * 32), key=VECTOR_PEM)
        self.assertEqual(code, 2, report)
        self.assertTrue(report["ok"])
        self.assertTrue(any("không có khóa công khai nào khớp" in g for g in report["gaps"]))

    def test_unsigned_lines_from_before_signing_still_count(self) -> None:
        code, report = self.verify({"audit_id": 2, "hash": self.rows[1]["hash"], "anchored_at": "2026-10-20T08:00:00"})
        self.assertEqual(code, 0, report)
        self.assertEqual(report["anchors"]["anchors.jsonl"], {"checked": 1, "matched": 1})
        self.assertTrue(any("không có chữ ký" in n for n in report["notes"]))

    def test_unsigned_line_after_a_signed_one_is_an_error_and_is_not_used(self) -> None:
        """Gỡ chữ ký khỏi một dòng để sửa giá trị mà không bị bắt chữ ký sai: lỗi (thoát 1), dòng không được dùng."""
        (self.tmp / "anchor-key.pem").write_text(VECTOR_PEM, encoding="utf-8")
        stripped = {"audit_id": 2, "hash": "ee" * 32, "anchored_at": "2026-10-25T01:15:03Z", "system": SYSTEM}
        code, report = self.verify(signed_line(1, self.rows[0]["hash"]), stripped)
        self.assertEqual(code, 1, report)
        self.assertEqual(report["signatures"]["anchors.jsonl"]["unsigned_late"], 1)
        [problem] = report["problems"]
        self.assertEqual((problem["kind"], problem["audit_id"]), ("anchor_unsigned_late", 2))
        self.assertIn("dòng 2", problem["message"])
        self.assertIsNone(report["rewritten"])
        self.assertEqual(report["anchors"]["anchors.jsonl"], {"checked": 1, "matched": 1})

    def test_key_next_to_a_file_without_any_signed_line_is_an_error(self) -> None:
        """Gỡ chữ ký khỏi mọi dòng: anchor-key.pem cạnh tệp (chỉ ghi cùng mốc có chữ ký) cho thấy điều đó."""
        unsigned = {"audit_id": 2, "hash": self.rows[1]["hash"], "anchored_at": "2026-10-25T01:15:03Z",
                    "system": SYSTEM}
        key = self.tmp / "khoa.pem"
        key.write_text(VECTOR_PEM, encoding="utf-8")
        code, report = self.verify(unsigned, extra=("--key", str(key)))
        self.assertEqual(code, 2, report)             # --key mà không có dòng ký: chưa đủ bằng chứng, chưa phải lỗi
        self.assertTrue(report["ok"])
        self.assertTrue(any("--key chưa kiểm được chữ ký nào" in g for g in report["gaps"]))
        (self.tmp / "anchor-key.pem").write_text(VECTOR_PEM, encoding="utf-8")
        code, report = self.verify(unsigned)
        self.assertEqual(code, 1, report)
        [problem] = report["problems"]
        self.assertEqual((problem["kind"], problem["audit_id"]), ("anchor_unsigned_all", 2))

    def test_signature_order_is_checked_file_by_file(self) -> None:
        """Tệp mốc mới đã ký kiểm cùng tệp mốc cũ chưa ký: thứ tự tính trong từng tệp, không nối các tệp lại."""
        (self.tmp / "anchor-key.pem").write_text(VECTOR_PEM, encoding="utf-8")
        old_dir = self.tmp / "cu"
        old_dir.mkdir()
        (old_dir / "anchors.jsonl").write_text(json.dumps({"audit_id": 2, "hash": self.rows[1]["hash"]}) + "\n",
                                               encoding="utf-8")
        code, report = self.verify(signed_line(1, self.rows[0]["hash"]),
                                   extra=("--anchors", str(old_dir / "anchors.jsonl")))
        self.assertEqual(code, 0, report)
        self.assertEqual(report["signatures"]["anchors.jsonl"],
                         {"valid": 1, "invalid": 0, "unsigned": 1, "unsigned_late": 0, "unknown_key": 0})

    def test_signed_line_that_no_longer_matches_the_chain_still_points_at_the_rewrite(self) -> None:
        """Chữ ký đúng mà hash lệch sổ: két đã ký mốc này, sổ bị viết lại sau đó — lỗi của sổ, không của chữ ký."""
        (self.tmp / "anchor-key.pem").write_text(VECTOR_PEM, encoding="utf-8")
        code, report = self.verify(signed_line(2, "ee" * 32))
        self.assertEqual(code, 1)
        self.assertEqual(report["signatures"]["anchors.jsonl"]["valid"], 1)
        self.assertEqual([p["kind"] for p in report["problems"]], ["anchor"])
        self.assertEqual(report["rewritten"], [1, 2])


# --- két, systemd, tài liệu ---------------------------------------------------------------------------------------


@unittest.skipUnless(shutil.which("sh"), "cần sh")
class VaultSetupTest(unittest.TestCase):
    START = ROOT / "platform" / "openbao" / "start.sh"

    def policy(self, service: str) -> list[str]:
        text = self.START.read_text(encoding="utf-8")
        func = re.search(r"^policy_of\(\) \{\n.*?^\}\n", text, re.M | re.S).group(0)
        out = subprocess.run(["sh", "-c", func + 'policy_of "$1"', "sh", service], check=True, capture_output=True,
                             text=True).stdout
        return out.splitlines()

    def test_only_svc_files_signs_and_reads_the_anchor_key(self) -> None:
        files = self.policy("svc-files")
        self.assertEqual([x for x in files if "moc-anchor" in x], [
            'path "transit/keys/moc-anchor" { capabilities = ["read"] }',
            'path "transit/sign/moc-anchor" { capabilities = ["update"] }'])
        # không glob nào khác phủ được khóa này (tạo, xoay, cấu hình, xuất, sao lưu)
        for line in files:
            path = re.match(r'path "([^"]+)"', line).group(1)
            if path.endswith("*"):
                self.assertFalse("moc-anchor".startswith(path.rstrip("*").rsplit("/", 1)[-1]), line)
            self.assertFalse(path.startswith(("transit/export", "transit/backup")), line)
        self.assertFalse([x for x in self.policy("svc-workflow") if "transit" in x])

    def test_key_created_once_as_non_exportable_ed25519(self) -> None:
        text = self.START.read_text(encoding="utf-8")
        setup = re.search(r"^setup\(\) \{\n.*?^\}\n", text, re.M | re.S).group(0)
        self.assertRegex(setup, r"bao read transit/keys/moc-anchor >/dev/null 2>&1 \\\n\s+\|\| bao write "
                                r"transit/keys/moc-anchor type=ed25519 exportable=false allow_plaintext_backup=false")
        # tạo sau khi bật transit, trước khi ghi policy của dịch vụ
        self.assertLess(setup.index("bao secrets enable transit"), setup.index("transit/keys/moc-anchor"))
        self.assertLess(setup.index("transit/keys/moc-anchor"), setup.index('policy_of "$s"'))


class UnitsAndDocsTest(unittest.TestCase):
    def test_systemd_units_run_publish_as_the_operator(self) -> None:
        unit = (ROOT / "platform" / "systemd" / "moc-anchor-publish.service").read_text(encoding="utf-8")
        timer = (ROOT / "platform" / "systemd" / "moc-anchor-publish.timer").read_text(encoding="utf-8")
        self.assertRegex(unit, r"(?m)^ExecStart=/usr/bin/python3 /opt/moc/scripts/moc\.py audit anchor --publish "
                               r"/var/lib/moc/neo-cong-khai$")
        self.assertRegex(unit, r"(?m)^User=moc$")
        self.assertRegex(unit, r"(?m)^Type=oneshot$")
        self.assertNotIn("--force", unit)
        self.assertRegex(timer, r"(?m)^OnUnitActiveSec=1h$")
        self.assertRegex(timer, r"(?m)^WantedBy=timers\.target$")
        for text in (unit, timer):
            self.assertIn("SPDX-License-Identifier: Apache-2.0", text)

    def test_installed_copy_has_every_script_moc_imports(self) -> None:
        # make install chỉ chép các tệp trong RUNTIME: thiếu anchor_sig.py thì moc.py ở /opt/moc không chạy được
        install = (SCRIPTS / "install.sh").read_text(encoding="utf-8")
        runtime = re.search(r"^RUNTIME=\((.*?)\)", install, re.M | re.S).group(1).split()
        tree = ast.parse((SCRIPTS / "moc.py").read_text(encoding="utf-8"))
        local = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
        local |= {n.module for n in tree.body if isinstance(n, ast.ImportFrom) and n.module}
        imported = sorted(name for name in local if (SCRIPTS / f"{name}.py").exists())
        self.assertIn("anchor_sig", imported)
        self.assertEqual([n for n in imported if f"scripts/{n}.py" not in runtime], [])

    def test_docs_explain_setup_and_outsider_check(self) -> None:
        docs = (ROOT / "docs" / "van-hanh.md").read_text(encoding="utf-8")
        section = docs[docs.index("## Mốc neo công khai"):docs.index("## GitOps và tự phục hồi")]
        for needed in ("cấm đẩy ép", "Deploy keys", "Khóa triển khai", "moc-anchor-publish.timer", "--publish",
                       "signet-anchor-v1", "scripts/anchor_sig.py", "audit verify --anchors"):
            self.assertIn(needed, section, needed)
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("openssl pkeyutl -verify -pubin -inkey\nanchor-key.pem -rawin", security)

    @unittest.skipUnless(shutil.which("openssl") and shutil.which("jq") and shutil.which("bash"), "cần openssl, jq")
    def test_documented_openssl_commands_verify_a_signed_line_and_reject_an_edited_one(self) -> None:
        docs = (ROOT / "docs" / "van-hanh.md").read_text(encoding="utf-8")
        block = next(b for b in re.findall(r"```bash\n(.*?)```", docs, re.S) if "openssl pkeyutl -verify" in b)
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            (work / "anchor-key.pem").write_text(VECTOR_PEM, encoding="utf-8")
            line = signed_line(42, "ab" * 32)
            for edited, verdict in ((line, "Signature Verified Successfully"),
                                    ({**line, "audit_id": 41}, "Signature Verification Failure")):
                (work / "anchors.jsonl").write_text(json.dumps(signed_line(7, "cd" * 32)) + "\n"
                                                    + json.dumps(edited) + "\n", encoding="utf-8")
                proc = subprocess.run(["bash", "-c", block], cwd=work, capture_output=True, text=True)
                self.assertIn(verdict, proc.stdout + proc.stderr)
                self.assertEqual(proc.returncode == 0, edited is line)
            # vân tay in theo tài liệu trùng trường key của dòng mốc
            out = subprocess.run(["bash", "-c", "openssl pkey -pubin -in anchor-key.pem -outform DER | sha256sum"],
                                 cwd=work, capture_output=True, text=True, check=True).stdout
            self.assertEqual("sha256:" + out.split()[0], VECTOR_KEY)


if __name__ == "__main__":
    unittest.main()
