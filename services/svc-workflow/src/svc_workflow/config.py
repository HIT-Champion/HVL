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

"""Cấu hình đọc từ biến môi trường — không sửa mã để cấu hình (PoF #4)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

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
    processes_dir: str
    sla_duration: str
    keycloak_url: str
    realm: str
    directory_client_id: str
    directory_client_secret: str
    # 0: tắt vòng nền (test gọi trực tiếp)
    directory_sync_interval_s: float
    reconcile_interval_s: float

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            raise ConfigError("Thiếu biến môi trường: " + ", ".join(missing))
        try:
            return cls(
                hasura_url=env.get("HASURA_URL", "http://hasura:8080").rstrip("/"),
                hasura_admin_secret=env["HASURA_ADMIN_SECRET"],
                hasura_timeout_s=float(env.get("HASURA_TIMEOUT_S", "10")),
                action_secret=env["MOC_ACTION_SECRET"],
                flowable_url=env.get("FLOWABLE_URL", "http://flowable:8080/flowable-rest/service").rstrip("/"),
                flowable_user=env.get("FLOWABLE_ADMIN_USER", "rest-admin"),
                flowable_password=env["FLOWABLE_ADMIN_PASSWORD"],
                processes_dir=env.get("MOC_PROCESSES_DIR", "/app/processes"),
                sla_duration=env.get("MOC_SLA_DURATION", "PT24H"),
                keycloak_url=env.get("MOC_KEYCLOAK_URL", "http://keycloak:8080").rstrip("/"),
                realm=env.get("MOC_REALM", "moc"),
                directory_client_id=env.get("MOC_DIRECTORY_CLIENT_ID", "svc-workflow"),
                directory_client_secret=env["MOC_DIRECTORY_CLIENT_SECRET"],
                directory_sync_interval_s=float(env.get("MOC_DIRECTORY_SYNC_INTERVAL_S", "15")),
                reconcile_interval_s=float(env.get("MOC_RECONCILE_INTERVAL_S", "300")),
            )
        except ValueError as exc:
            raise ConfigError(f"Giá trị số không hợp lệ: {exc}") from exc
