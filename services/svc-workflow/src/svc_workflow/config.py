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

"""Cấu hình đọc từ biến môi trường — không sửa mã để cấu hình (PoF #4)."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.utils import parseaddr
from urllib.parse import urlsplit

from .channels import KINDS, SMTP_PORTS, WEBHOOK_FORMATS
from .sla import parse_duration
from .suggest import LEGAL_HOLIDAYS, NO_HOLIDAYS, Holidays, parse_holidays

REQUIRED = (
    "HASURA_ADMIN_SECRET",
    "MOC_ACTION_SECRET",
    "FLOWABLE_ADMIN_PASSWORD",
    "MOC_DIRECTORY_CLIENT_SECRET",
)


class ConfigError(RuntimeError):
    """Thiếu hoặc sai biến môi trường — dịch vụ dừng ngay khi khởi động."""


@dataclass(frozen=True)
class Settings:
    hasura_url: str
    hasura_admin_secret: str
    hasura_timeout_s: float
    action_secret: str
    flowable_url: str
    flowable_user: str
    flowable_password: str
    files_url: str
    processes_dir: str
    # JSON Schema dùng chung với giao diện (schemas/ ở gốc repo) — lớp kiểm thứ hai của poka-yoke (F2.2)
    schemas_dir: str
    sla_duration: str
    keycloak_url: str
    realm: str
    directory_client_id: str
    directory_client_secret: str
    # Centrifugo: API nội bộ để đẩy thông báo; để trống khóa thì chỉ lưu thông báo, không đẩy realtime
    centrifugo_url: str
    centrifugo_api_key: str
    # 0: tắt vòng nền (test gọi trực tiếp)
    directory_sync_interval_s: float
    reconcile_interval_s: float
    sla_poll_interval_s: float
    # F3.10 IT/OT: context broker NGSI-LD (Scorpio, profile iot); để trống thì tắt. Ngưỡng nhiệt độ (°C) dựng báo cáo
    # sự cố; địa chỉ broker gọi lại svc-workflow; chu kỳ kiểm subscription của các đơn vị; số phút không có số đo thì
    # sơ đồ cảm biến gắn cờ mất tín hiệu
    ngsi_url: str = ""
    ot_threshold: float = 35.0
    ot_notify_url: str = "http://svc-workflow:8000"
    ot_interval_s: float = 15.0
    ot_stale_min: int = 10
    # F3.12 liên thông: chu kỳ vòng nền chuyển dòng chờ đến hạn và báo dòng đã chuyển mà chưa báo — ngắn hơn
    # MOC_RECONCILE_INTERVAL_S để lần thử lại (30 giây, 1 phút, 2 phút…) đúng hẹn
    dispatch_interval_s: float = 30.0
    # F4.3 tác tử gợi ý giao việc: false thì worker vẫn nhận việc moc-goi-y nhưng hoàn thành ngay, không gọi svc-files,
    # không ghi gì; chu kỳ nhận việc (0: không chạy, nhánh gợi ý tự hết sau PT10M); hạn gọi svc-files; ngưỡng điểm
    # _rankingScore của một căn cứ; danh tính tác tử (actor_id của sổ, agent_id của bảng gợi ý)
    suggest_enabled: bool = True
    suggest_poll_interval_s: float = 2.0
    suggest_timeout_s: float = 10.0
    suggest_min_score: float = 0.3
    assigner_id: str = "moc-assigner"
    # ngày lễ hạn gợi ý phải tránh, ngoài thứ Bảy, Chủ nhật (MOC_HOLIDAYS, cú pháp ở suggest.parse_holidays)
    holidays: Holidays = NO_HOLIDAYS
    # Định tuyến thông báo đa kênh (channels.py): ngoài chuông trên web, gửi thêm qua email (SMTP) và webhook. Trống máy
    # chủ thư và URL webhook thì tắt, như trước. Cổng 0: theo kiểu TLS (587 starttls, 465 ssl, 25 none). Loại thông báo
    # trống: mọi loại. Mật khẩu SMTP và URL webhook (khóa nằm trong đường dẫn) là bí mật, lấy từ két như các bí mật
    # khác. Địa chỉ công khai để thư, tin webhook dẫn về đúng văn bản
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_tls: str = "starttls"
    smtp_user: str = ""
    smtp_password: str = field(default="", repr=False)
    smtp_from: str = ""
    notify_webhook_url: str = field(default="", repr=False)
    notify_webhook_format: str = "json"
    notify_email_kinds: tuple[str, ...] = ()
    notify_webhook_kinds: tuple[str, ...] = ()
    notify_interval_s: float = 5.0
    public_url: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            raise ConfigError("Thiếu biến môi trường: " + ", ".join(missing))
        try:
            # để trống thì như không đặt, giống docker-compose.yml (${MOC_HOLIDAYS:-…})
            holidays = parse_holidays(env.get("MOC_HOLIDAYS", "").strip() or LEGAL_HOLIDAYS)
        except ValueError as exc:
            raise ConfigError(f"MOC_HOLIDAYS: {exc}") from exc
        try:
            return cls(
                hasura_url=env.get("HASURA_URL", "http://hasura:8080").rstrip("/"),
                hasura_admin_secret=env["HASURA_ADMIN_SECRET"],
                hasura_timeout_s=float(env.get("HASURA_TIMEOUT_S", "10")),
                action_secret=env["MOC_ACTION_SECRET"],
                flowable_url=env.get("FLOWABLE_URL", "http://flowable:8080/flowable-rest/service").rstrip("/"),
                flowable_user=env.get("FLOWABLE_ADMIN_USER", "rest-admin"),
                flowable_password=env["FLOWABLE_ADMIN_PASSWORD"],
                files_url=env.get("MOC_FILES_URL", "http://svc-files:8000").rstrip("/"),
                processes_dir=env.get("MOC_PROCESSES_DIR", "/app/processes"),
                schemas_dir=env.get("MOC_SCHEMAS_DIR", "/app/schemas"),
                sla_duration=env.get("MOC_SLA_DURATION", "PT24H"),
                keycloak_url=env.get("MOC_KEYCLOAK_URL", "http://keycloak:8080").rstrip("/"),
                realm=env.get("MOC_REALM", "moc"),
                directory_client_id=env.get("MOC_DIRECTORY_CLIENT_ID", "svc-workflow"),
                directory_client_secret=env["MOC_DIRECTORY_CLIENT_SECRET"],
                centrifugo_url=env.get("MOC_CENTRIFUGO_URL", "http://centrifugo:9000").rstrip("/"),
                centrifugo_api_key=env.get("CENTRIFUGO_API_KEY", ""),
                directory_sync_interval_s=float(env.get("MOC_DIRECTORY_SYNC_INTERVAL_S", "15")),
                reconcile_interval_s=float(env.get("MOC_RECONCILE_INTERVAL_S", "300")),
                sla_poll_interval_s=float(env.get("MOC_SLA_POLL_INTERVAL_S", "5")),
                ngsi_url=env.get("MOC_NGSI_URL", "").rstrip("/"),
                ot_threshold=float(env.get("MOC_OT_THRESHOLD", "35")),
                ot_notify_url=env.get("MOC_OT_NOTIFY_URL", "http://svc-workflow:8000").rstrip("/"),
                ot_interval_s=float(env.get("MOC_OT_SUBSCRIPTION_INTERVAL_S", "15")),
                ot_stale_min=int(env.get("MOC_OT_STALE_MIN", "10")),
                dispatch_interval_s=float(env.get("MOC_DISPATCH_INTERVAL_S", "30")),
                suggest_enabled=_flag("MOC_SUGGEST_ENABLED", env.get("MOC_SUGGEST_ENABLED", "true")),
                suggest_poll_interval_s=float(env.get("MOC_SUGGEST_POLL_INTERVAL_S", "2")),
                suggest_timeout_s=float(env.get("MOC_SUGGEST_TIMEOUT_S", "10")),
                suggest_min_score=float(env.get("MOC_SUGGEST_MIN_SCORE", "0.3")),
                assigner_id=env.get("MOC_ASSIGNER_ID", "moc-assigner").strip(),
                holidays=holidays,
                smtp_host=env.get("MOC_SMTP_HOST", "").strip(),
                smtp_port=int(env.get("MOC_SMTP_PORT", "").strip() or 0),
                smtp_tls=env.get("MOC_SMTP_TLS", "").strip().lower() or "starttls",
                smtp_user=env.get("MOC_SMTP_USER", "").strip(),
                smtp_password=env.get("MOC_SMTP_PASSWORD", ""),
                smtp_from=env.get("MOC_SMTP_FROM", "").strip(),
                notify_webhook_url=env.get("MOC_NOTIFY_WEBHOOK_URL", "").strip(),
                notify_webhook_format=env.get("MOC_NOTIFY_WEBHOOK_FORMAT", "").strip().lower() or "json",
                notify_email_kinds=_kinds(env.get("MOC_NOTIFY_EMAIL_KINDS", "")),
                notify_webhook_kinds=_kinds(env.get("MOC_NOTIFY_WEBHOOK_KINDS", "")),
                notify_interval_s=float(env.get("MOC_NOTIFY_INTERVAL_S", "5")),
                public_url=env.get("MOC_PUBLIC_URL", "").strip().rstrip("/"),
            )
        except ValueError as exc:
            raise ConfigError(f"Giá trị số không hợp lệ: {exc}") from exc

    def __post_init__(self) -> None:
        # thời hạn sai thì dừng ngay lúc khởi động, không để timer trong Flowable hỏng khi văn bản đã vào sổ
        try:
            parse_duration(self.sla_duration)
        except ValueError as exc:
            raise ConfigError(f"MOC_SLA_DURATION: {exc}") from exc
        if not math.isfinite(self.ot_threshold):
            raise ConfigError("MOC_OT_THRESHOLD phải là một số (°C)")
        if not 1 <= self.ot_stale_min <= 1440:
            raise ConfigError("MOC_OT_STALE_MIN phải là số phút nguyên từ 1 đến 1440")
        if not (math.isfinite(self.suggest_poll_interval_s) and self.suggest_poll_interval_s >= 0):
            raise ConfigError("MOC_SUGGEST_POLL_INTERVAL_S phải ≥ 0 (0: không nhận việc gợi ý giao việc)")
        # cả một việc gợi ý ≤ hạn gọi svc-files + 10 giây, phải xong trước khi khóa việc (PT1M) hết
        if not (math.isfinite(self.suggest_timeout_s) and 0 < self.suggest_timeout_s <= 40):
            raise ConfigError("MOC_SUGGEST_TIMEOUT_S phải trong khoảng (0, 40] giây")
        if not (math.isfinite(self.suggest_min_score) and 0 <= self.suggest_min_score <= 1):
            raise ConfigError("MOC_SUGGEST_MIN_SCORE phải trong khoảng [0, 1] (thang _rankingScore)")
        if not 1 <= len(self.assigner_id) <= 64:
            raise ConfigError("MOC_ASSIGNER_ID phải có 1–64 ký tự")
        self._check_channels()

    def warnings(self) -> list[str]:
        """Cấu hình chạy được nhưng có phần không dùng được: app ghi nhật ký ``config.warning`` một lần lúc khởi động,
        không chặn — bản đang chạy không dừng chỉ vì một kênh phụ cấu hình chưa đúng."""
        out: list[str] = []
        if self.smtp_host and self.smtp_tls == "none" and self.smtp_user:
            out.append("MOC_SMTP_TLS=none mà có MOC_SMTP_USER: svc-workflow không đăng nhập máy chủ thư qua kết nối "
                       "không mã hóa (mật khẩu sẽ đi dạng rõ), nên mọi thư email báo lỗi gửi. Đặt "
                       "MOC_SMTP_TLS=starttls hoặc ssl; máy chủ thư nội bộ không cần đăng nhập thì để trống "
                       "MOC_SMTP_USER")
        return out

    def _check_channels(self) -> None:
        """Cấu hình kênh ngoài sai thì dừng lúc khởi động, không để thư dồn lại rồi hỏng hết lúc gửi."""
        if self.smtp_tls not in SMTP_PORTS:
            raise ConfigError("MOC_SMTP_TLS chỉ nhận starttls, ssl hoặc none")
        if not 0 <= self.smtp_port <= 65535:
            raise ConfigError("MOC_SMTP_PORT phải trong khoảng 1–65535 (để trống: theo MOC_SMTP_TLS)")
        if self.smtp_host and "@" not in parseaddr(self.smtp_from)[1]:
            raise ConfigError("Đặt MOC_SMTP_HOST thì phải có MOC_SMTP_FROM là một địa chỉ email, vd signet@don-vi.vn")
        if self.notify_webhook_url:
            url = urlsplit(self.notify_webhook_url)
            if url.scheme not in ("http", "https") or not url.hostname:
                # không in URL: khóa của webhook nằm trong đường dẫn
                raise ConfigError("MOC_NOTIFY_WEBHOOK_URL phải là địa chỉ http:// hoặc https://")
        if self.notify_webhook_format not in WEBHOOK_FORMATS:
            raise ConfigError("MOC_NOTIFY_WEBHOOK_FORMAT chỉ nhận json hoặc ntfy")
        for name, kinds in (("MOC_NOTIFY_EMAIL_KINDS", self.notify_email_kinds),
                            ("MOC_NOTIFY_WEBHOOK_KINDS", self.notify_webhook_kinds)):
            unknown = sorted(set(kinds) - set(KINDS))
            if unknown:
                raise ConfigError(f"{name}: không có loại thông báo {', '.join(unknown)} (có: {', '.join(KINDS)})")
        if not (math.isfinite(self.notify_interval_s) and self.notify_interval_s >= 0):
            raise ConfigError("MOC_NOTIFY_INTERVAL_S phải ≥ 0 (0: không gửi qua kênh ngoài)")


def _kinds(value: str) -> tuple[str, ...]:
    """Danh sách loại thông báo cách nhau bằng dấu phẩy; trống là mọi loại."""
    return tuple(k.strip() for k in value.split(",") if k.strip())


def _flag(name: str, value: str) -> bool:
    v = value.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} chỉ nhận true hoặc false")
