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

"""Trạng thái hệ thống, công khai: ``GET /api/status`` gom tình trạng các thành phần của Signet cho trang /trang-thai.

Không cần đăng nhập nên mọi chữ trả ra đều cố định hoặc đã lọc: mỗi thành phần chỉ có mã, nhãn tiếng Việt, tên phần
mềm nguồn mở và một trong bốn trạng thái ``ok`` · ``degraded`` · ``down`` · ``off``. Không có tên máy, địa chỉ, URL nội
bộ, phiên bản từng thành phần, thông báo lỗi, số người dùng hay số văn bản. Lỗi chi tiết chỉ vào nhật ký của svc-files
(``core.status.changed``, ghi khi một thành phần đổi trạng thái).

Chống khuếch đại: kết quả gom lưu đệm ``MOC_STATUS_CACHE_S`` giây (mặc định 10) cho mọi người gọi; hết hạn thì chỉ một
lượt dò chạy, ai gọi trong lúc đó chờ chung lượt ấy. Mỗi lần dò một thành phần có hạn ``MOC_STATUS_TIMEOUT_S`` giây
(mặc định 3), quá hạn là ``down``. Lần dò cũ còn treo (kho đối tượng không trả lời: boto3 chạy trong luồng riêng, tự
thử lại) thì lượt sau chờ tiếp chính lần đó chứ không mở lần mới — mỗi thành phần tối đa một lần dò đang chạy. APISIX
còn giới hạn số lần gọi theo địa chỉ IP (``MOC_RATE_STATUS_PER_MIN``).

Thành phần theo thứ tự người dùng → lõi → quy trình → dữ liệu → trí tuệ nhân tạo. Thành phần ``critical`` gián đoạn thì
cả hệ thống ``down``; thành phần khác gián đoạn hoặc suy giảm thì ``degraded``; ``off`` (tắt theo cấu hình, vd chưa bật
mô hình ngôn ngữ) không tính.

Cùng kết quả gom ra dạng chữ của Prometheus ở ``GET /metrics`` (#274): Prometheus thu 15 giây một lần, nên thành
phần chết vẫn bật cảnh báo khi không ai gọi tới (``platform/monitoring/canh-bao.yml``, nhóm ``thanh-phan``). Đường này
chỉ gọi được trong mạng nội bộ: route ``chan`` của APISIX trả 404 cho ``/metrics``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import httpx2

if TYPE_CHECKING:
    from .config import Settings

log = logging.getLogger("svc_files")

State = Literal["ok", "degraded", "down", "off"]
STATES = frozenset({"ok", "degraded", "down", "off"})

# (mã, nhãn) theo thứ tự hiện trên trang
LAYERS: tuple[tuple[str, str], ...] = (
    ("nguoi-dung", "Người dùng"),
    ("loi", "Lõi"),
    ("quy-trinh", "Quy trình"),
    ("du-lieu", "Dữ liệu"),
    ("tri-tue", "Trí tuệ nhân tạo"),
)

# Phiên bản (thẻ image, MOC_VERSION) và tên mô hình: chỉ nhận dạng ngắn quen thuộc, lạ thì không trả
VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}")
MODEL_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._:-]{0,63}")

Check = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class Component:
    id: str
    layer: str
    label: str
    software: str           # phần mềm nguồn mở đảm nhận, không kèm phiên bản
    check: Check            # trả một trong STATES; ném lỗi hay quá hạn là "down"
    critical: bool = True   # gián đoạn thì cả hệ thống gián đoạn


def public_version(value: str | None) -> str:
    value = (value or "").strip()
    return value if VERSION_RE.fullmatch(value) else "dev"


def public_model(name: str | None) -> str | None:
    """Tên mô hình bỏ phần registry / namespace trước dấu '/' cuối (có thể là tên máy nội bộ), vd qwen3:1.7b."""
    base = (name or "").strip().rsplit("/", 1)[-1]
    return base if MODEL_RE.fullmatch(base) else None


def _consume(task: asyncio.Future[Any]) -> None:
    """Lần dò bị bỏ dở (quá hạn) kết thúc sau, kể cả bằng lỗi: lấy kết quả để asyncio không báo lỗi bị bỏ quên."""
    if not task.cancelled():
        task.exception()


class StatusBoard:
    """Gom trạng thái các thành phần, lưu đệm ``ttl_s`` giây, mỗi lần dò tối đa ``timeout_s`` giây."""

    def __init__(self, components: Sequence[Component], *, version: str = "dev",
                 ai_info: Callable[[], dict[str, Any]] | None = None,
                 last_backup: Callable[[], Awaitable[datetime | None]] | None = None,
                 ttl_s: float = 10.0, timeout_s: float = 3.0, clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC),
                 closers: Sequence[Callable[[], Awaitable[None]]] = ()) -> None:
        self.components = list(components)
        self.version = public_version(version)
        self.ttl_s = ttl_s
        self.timeout_s = timeout_s
        self._ai_info = ai_info or (lambda: {"enabled": False, "model": None, "semantic": False})
        self._last_backup = last_backup
        self._clock = clock
        self._now = now
        self._closers = list(closers)
        self._started = clock()
        self._lock = asyncio.Lock()
        self._cached: dict[str, Any] | None = None
        self._at = 0.0
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._last: dict[str, str] = {}
        self.rounds = 0                 # số lượt gom thật đã chạy (test kiểm lưu đệm)

    async def aclose(self) -> None:
        for close in self._closers:
            await close()

    def _fresh(self) -> bool:
        return self._cached is not None and self._clock() - self._at < self.ttl_s

    async def report(self) -> dict[str, Any]:
        """Kết quả gom (lưu đệm) kèm thời gian svc-files đã chạy liên tục."""
        if not self._fresh():
            async with self._lock:
                if not self._fresh():       # người chờ khóa: lượt vừa xong của người trước đã đủ mới
                    self._cached = await self._collect()
                    self._at = self._clock()
        assert self._cached is not None
        return {**self._cached, "uptime_s": int(self._clock() - self._started)}

    async def metrics(self) -> str:
        """Kết quả gom (cùng lưu đệm với ``report``) ở dạng chữ của Prometheus."""
        return render_metrics(await self.report(), {c.id: c.critical for c in self.components})

    def _changed(self, key: str, state: str, reason: str | None = None) -> None:
        if self._last.get(key) == state:
            return
        self._last[key] = state
        record: dict[str, Any] = {"event": "core.status.changed", "component": key, "state": state}
        if reason:
            record["reason"] = reason
        log.log(logging.INFO if state in ("ok", "off") else logging.WARNING, json.dumps(record, ensure_ascii=False))

    async def _bounded(self, key: str, start: Callable[[], Awaitable[Any]]) -> Any:
        """Chờ lần dò của ``key`` tối đa ``timeout_s`` giây; lần trước còn chạy thì chờ tiếp nó, không mở lần mới."""
        task = self._pending.get(key)
        if task is None or task.done():
            task = asyncio.ensure_future(start())
            task.add_done_callback(_consume)
            self._pending[key] = task
        return await asyncio.wait_for(asyncio.shield(task), self.timeout_s)

    async def _probe(self, component: Component) -> str:
        try:
            state = await self._bounded(component.id, component.check)
        except TimeoutError:
            self._changed(component.id, "down", f"quá {self.timeout_s:g} giây")
            return "down"
        except Exception as exc:  # noqa: BLE001 — lỗi chi tiết chỉ vào nhật ký, không ra trang công khai
            self._changed(component.id, "down", f"{type(exc).__name__}: {exc}")
            return "down"
        if state not in STATES:
            self._changed(component.id, "down", f"trạng thái lạ {state!r}")
            return "down"
        self._changed(component.id, state)
        return state

    async def _backup(self) -> datetime | None:
        if self._last_backup is None:
            return None
        try:
            at = await self._bounded("sao-luu", self._last_backup)
        except Exception as exc:  # noqa: BLE001 — TimeoutError, HasuraError…: trang chỉ không có giờ sao lưu
            self._changed("sao-luu", "down", f"{type(exc).__name__}: {exc}")
            return None
        self._changed("sao-luu", "ok")
        return at if isinstance(at, datetime) else None

    async def _collect(self) -> dict[str, Any]:
        self.rounds += 1
        *states, backup = await asyncio.gather(*(self._probe(c) for c in self.components), self._backup())
        rows = list(zip(self.components, states, strict=True))
        if any(c.critical and s == "down" for c, s in rows):
            overall = "down"
        elif any(s in ("down", "degraded") for _, s in rows):
            overall = "degraded"
        else:
            overall = "ok"
        info = self._ai_info()
        return {
            "status": overall,
            "checked_at": self._now().isoformat(timespec="seconds"),
            "version": self.version,
            "last_backup_at": backup.isoformat(timespec="seconds") if backup else None,
            "ai": {"enabled": bool(info.get("enabled")), "model": public_model(info.get("model")),
                   "semantic": bool(info.get("semantic"))},
            "layers": [{"id": key, "label": label} for key, label in LAYERS],
            "components": [{"id": c.id, "layer": c.layer, "label": c.label, "software": c.software, "status": s}
                           for c, s in rows],
        }


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_metrics(report: dict[str, Any], critical: dict[str, bool]) -> str:
    """``moc_component_up{component, critical}``: 1 khi thành phần ok hoặc suy giảm, 0 khi gián đoạn; thành phần tắt
    theo cấu hình (``off``) không có dòng. Nhãn chỉ có mã thành phần như trang công khai, không URL hay tên máy."""
    out = ["# HELP moc_component_up Thành phần trả lời được: 1 khi ok hoặc suy giảm, 0 khi gián đoạn.",
           "# TYPE moc_component_up gauge"]
    for c in report["components"]:
        if c["status"] != "off":
            flag = "true" if critical.get(c["id"], True) else "false"
            labels = f'component="{_label(c["id"])}",critical="{flag}"'
            out.append(f"moc_component_up{{{labels}}} {int(c['status'] != 'down')}")
    return "\n".join(out) + "\n"


# --- các lần dò của bản chạy thật -------------------------------------------------------------------------------


def from_bool(ping: Callable[[], Awaitable[bool]]) -> Check:
    async def check() -> str:
        return "ok" if await ping() else "down"
    return check


def http_check(http: httpx2.AsyncClient, url: str, judge: Callable[[httpx2.Response], str]) -> Check:
    """GET ``url`` (không theo chuyển hướng); không có URL thì thành phần tắt theo cấu hình."""
    async def check() -> str:
        if not url:
            return "off"
        return judge(await http.get(url))
    return check


def judge_gateway(r: httpx2.Response) -> str:
    # /status/ready của APISIX: 503 khi còn worker chưa nạp xong cấu hình route
    return "ok" if r.status_code == 200 else "degraded" if r.status_code == 503 else "down"


def judge_jwks(r: httpx2.Response) -> str:
    # realm trả được khóa công khai: đăng nhập và kiểm token đều được
    if r.status_code != 200:
        return "down"
    keys = r.json().get("keys")
    return "ok" if isinstance(keys, list) and keys else "down"


def judge_workflow(r: httpx2.Response) -> str:
    # /readyz của svc-workflow: Flowable và Hasura; Flowable còn mà Hasura mất thì quy trình chỉ chạy được một phần
    if r.status_code == 200:
        return "ok"
    if r.status_code == 503:
        checks = r.json().get("checks") or {}
        return "degraded" if checks.get("flowable") is True else "down"
    return "down"


def default_board(settings: Settings, *, scanner: Any, store: Any, hasura: Any, meili: Any, vault: Any, ai: Any,
                  transport: httpx2.AsyncBaseTransport | None = None) -> StatusBoard:
    """Bảng trạng thái nối với các client sẵn có của svc-files; ``transport`` thay mạng thật trong test."""
    http = httpx2.AsyncClient(timeout=settings.status_timeout_s, transport=transport, follow_redirects=False)
    ai_on = bool(settings.ai_url) and settings.ask_enabled

    async def storage() -> str:
        return "ok" if await asyncio.to_thread(store.ping) else "down"

    async def vault_check() -> str:
        return "off" if vault is None else "ok" if await vault.ping() else "down"

    async def ai_check() -> str:
        # Mô hình viết câu trả lời sẵn sàng: bật. Chỉ còn mô hình nhúng (tìm theo nghĩa): suy giảm. Không có mô hình
        # nào (chưa bật profile ai, hoặc Ollama không trả lời — không phân biệt được): tắt, trợ lý vẫn tìm theo từ khóa
        if ai_on and ai.chat_available:
            return "ok"
        return "degraded" if ai_on and ai.embed_available else "off"

    def ai_info() -> dict[str, Any]:
        enabled = ai_on and bool(ai.chat_available)
        return {"enabled": enabled, "model": ai.chat_model if enabled else None,
                "semantic": ai_on and bool(ai.embed_available)}

    workflow = f"{settings.workflow_url}/readyz" if settings.workflow_url else ""
    components = [
        Component("cong-api", "nguoi-dung", "Cổng API", "Apache APISIX",
                  http_check(http, settings.gateway_status_url, judge_gateway)),
        Component("dang-nhap", "nguoi-dung", "Đăng nhập một lần", "Keycloak",
                  http_check(http, settings.oidc_jwks_url, judge_jwks)),
        Component("csdl", "loi", "CSDL", "PostgreSQL · Hasura", from_bool(hasura.ping)),
        Component("ket-khoa", "loi", "Két khóa", "OpenBao", vault_check, critical=False),
        Component("quet-ma-doc", "loi", "Quét mã độc", "ClamAV", from_bool(scanner.ping)),
        Component("quy-trinh", "quy-trinh", "Quy trình", "Flowable", http_check(http, workflow, judge_workflow)),
        Component("luu-tru", "du-lieu", "Lưu trữ tệp", "SeaweedFS", storage),
        Component("tim-kiem", "du-lieu", "Tìm kiếm", "Meilisearch", from_bool(meili.ping), critical=False),
        Component("tro-ly-ai", "tri-tue", "Trợ lý AI", "Ollama", ai_check, critical=False),
    ]
    return StatusBoard(components, version=settings.version, ai_info=ai_info, last_backup=hasura.last_backup,
                       ttl_s=settings.status_cache_s, timeout_s=settings.status_timeout_s, closers=[http.aclose])
