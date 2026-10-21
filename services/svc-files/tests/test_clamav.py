# Copyright 2026 Mộc Team
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

"""Kiểm máy khách INSTREAM với một clamd giả nói đúng giao thức."""

import asyncio
import struct

import pytest

from conftest import EICAR
from svc_files.clamav import ClamAVClient, ScanError, parse_reply


async def fake_clamd(reply: bytes | None = None):
    """clamd giả: nhận INSTREAM, trả FOUND nếu có EICAR. ``reply`` ghi đè câu trả lời."""
    received: list[bytes] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        cmd = await reader.readuntil(b"\0")
        if cmd == b"zPING\0":
            writer.write(b"PONG\0")
        else:
            data = b""
            while size := struct.unpack("!I", await reader.readexactly(4))[0]:
                data += await reader.readexactly(size)
            received.append(data)
            if reply is not None:
                writer.write(reply)
            elif b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data:
                writer.write(b"stream: Eicar-Test-Signature FOUND\0")
            else:
                writer.write(b"stream: OK\0")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port, received


async def chunks(*parts: bytes):
    for p in parts:
        yield p


def test_clean_stream():
    async def run():
        server, port, received = await fake_clamd()
        async with server:
            result = await ClamAVClient("127.0.0.1", port).scan(chunks(b"abc", b"", b"def"))
        assert result.clean and result.signature is None
        assert received == [b"abcdef"]

    asyncio.run(run())


def test_infected_stream_reports_signature():
    async def run():
        server, port, _ = await fake_clamd()
        async with server:
            result = await ClamAVClient("127.0.0.1", port).scan(chunks(EICAR[:20], EICAR[20:]))
        assert not result.clean and result.signature == "Eicar-Test-Signature"

    asyncio.run(run())


@pytest.mark.parametrize(("reply", "unscannable"), [
    (b"stream: Heuristics.Encrypted.Zip FOUND", True),
    (b"stream: Heuristics.Encrypted.PDF FOUND", True),
    (b"stream: Heuristics.Limits.Exceeded.MaxRecursion FOUND", True),
    (b"stream: Eicar-Test-Signature FOUND", False),
    (b"stream: Heuristics.Phishing.Email.SpoofedDomain FOUND", False),   # mẫu đáng ngờ: vẫn là nhiễm
    (b"stream: OK", False),
])
def test_unscannable_is_told_apart_from_infected(reply, unscannable):
    assert parse_reply(reply).unscannable is unscannable


def test_ping():
    async def run():
        server, port, _ = await fake_clamd()
        async with server:
            assert await ClamAVClient("127.0.0.1", port).ping()

    asyncio.run(run())


def test_error_reply_is_not_clean():
    async def run():
        server, port, _ = await fake_clamd(b"INSTREAM size limit exceeded. ERROR\0")
        async with server:
            with pytest.raises(ScanError):
                await ClamAVClient("127.0.0.1", port).scan(chunks(b"abc"))

    asyncio.run(run())


def test_connection_refused_raises_scan_error():
    async def run():
        server, port, _ = await fake_clamd()
        server.close()
        await server.wait_closed()
        client = ClamAVClient("127.0.0.1", port, timeout_s=2)
        with pytest.raises(ScanError):
            await client.scan(chunks(b"abc"))
        assert await client.ping() is False

    asyncio.run(run())


def test_errors_from_the_stream_propagate():
    class Boom(Exception):
        pass

    async def exploding():
        yield b"abc"
        raise Boom

    async def run():
        server, port, _ = await fake_clamd()
        async with server:
            with pytest.raises(Boom):
                await ClamAVClient("127.0.0.1", port).scan(exploding())

    asyncio.run(run())


@pytest.mark.parametrize(
    ("raw", "clean", "signature"),
    [
        (b"stream: OK\0", True, None),
        (b"stream: Win.Test.EICAR_HDB-1 FOUND\0", False, "Win.Test.EICAR_HDB-1"),
    ],
)
def test_parse_reply(raw, clean, signature):
    r = parse_reply(raw)
    assert (r.clean, r.signature) == (clean, signature)
