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

"""Máy khách clamd tối giản, nói giao thức INSTREAM qua TCP.

ClamAV chạy như một dịch vụ độc lập (GPL-2.0); ta chỉ gửi byte qua socket, không
liên kết thư viện của nó. Giao thức: https://docs.clamav.net/manual/Usage/Scanning.html
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from collections.abc import AsyncIterable
from dataclasses import dataclass


class ScanError(Exception):
    """clamd không trả lời được. Tệp chưa quét thì không bao giờ được coi là sạch."""


# Mẫu ClamAV báo khi không quét hết được tệp (AlertEncrypted, AlertExceedsMax trong docker-compose.yml): có mật khẩu
# hoặc giải nén vượt giới hạn. Không phải mã độc đã biết, nhưng cũng không biết bên trong có gì
UNSCANNABLE = ("Heuristics.Encrypted.", "Heuristics.Limits.Exceeded")


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    signature: str | None = None

    @property
    def unscannable(self) -> bool:
        return not self.clean and (self.signature or "").startswith(UNSCANNABLE)


def parse_reply(raw: bytes) -> ScanResult:
    """Đọc câu trả lời của clamd, ví dụ ``stream: OK`` hay ``stream: Eicar-Test-Signature FOUND``."""
    text = raw.rstrip(b"\0").decode("utf-8", "replace").strip()
    if text.endswith(" FOUND"):
        _, _, rest = text.partition(": ")
        return ScanResult(clean=False, signature=rest.removesuffix(" FOUND").strip())
    if text.endswith(": OK"):
        return ScanResult(clean=True)
    raise ScanError(f"clamd trả lời không hợp lệ: {text!r}")


class ClamAVClient:
    def __init__(self, host: str, port: int, timeout_s: float = 60.0) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s

    async def ping(self) -> bool:
        try:
            reply = await self._exchange(b"zPING\0", None)
        except ScanError:
            return False
        return reply.rstrip(b"\0") == b"PONG"

    async def scan(self, chunks: AsyncIterable[bytes]) -> ScanResult:
        """Gửi luồng byte cho clamd quét.

        Lỗi do chính ``chunks`` ném ra (ví dụ tệp vượt cỡ) được truyền nguyên vẹn ra ngoài.
        """
        return parse_reply(await self._exchange(b"zINSTREAM\0", chunks))

    async def _exchange(self, command: bytes, chunks: AsyncIterable[bytes] | None) -> bytes:
        try:
            async with asyncio.timeout(self.timeout_s):
                reader, writer = await asyncio.open_connection(self.host, self.port)
                try:
                    writer.write(command)
                    if chunks is not None:
                        async for chunk in chunks:
                            if chunk:
                                writer.write(struct.pack("!I", len(chunk)) + chunk)
                                await writer.drain()
                        writer.write(struct.pack("!I", 0))
                    await writer.drain()
                    return await reader.readuntil(b"\0")
                finally:
                    writer.close()
                    with contextlib.suppress(OSError):
                        await writer.wait_closed()
        except (OSError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
            raise ScanError(f"Không gọi được clamd tại {self.host}:{self.port}: {exc!r}") from exc
