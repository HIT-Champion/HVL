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
    "MOC_OIDC_ISSUER",
    "MOC_OIDC_JWKS_URL",
    "SEAWEEDFS_S3_ACCESS_KEY",
    "SEAWEEDFS_S3_SECRET_KEY",
    "HASURA_ADMIN_SECRET",
    "MEILISEARCH_API_KEY",
)


class ConfigError(RuntimeError):
    """Thiếu hoặc sai biến môi trường — dịch vụ dừng ngay khi khởi động."""


@dataclass(frozen=True)
class Settings:
    clamav_host: str
    clamav_port: int
    clamav_timeout_s: float
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str
    bucket: str
    max_upload_bytes: int
    oidc_issuer: str
    oidc_jwks_url: str
    oidc_audience: str | None
    hasura_url: str
    hasura_admin_secret: str
    hasura_timeout_s: float
    meili_url: str
    meili_api_key: str
    search_index: str
    search_sync_interval_s: float
    text_interval_s: float          # chu kỳ đọc lớp chữ của PDF mới gắn vào văn bản (F2.7); 0: tắt vòng nền
    public_url: str                 # in vào mã QR của văn bản phát hành: <public_url>/xac-thuc/<mã>
    service_clients: frozenset[str]  # client Keycloak được gọi API nội bộ (/internal/*)
    cold_bucket: str                # bucket lạnh bật khóa ghi (S3 Object Lock): mốc neo sổ kiểm toán
    anchor_interval_s: float        # chu kỳ neo đầu chuỗi sổ kiểm toán; 0: tắt vòng nền
    anchor_retention_days: int      # hạn giữ mỗi mốc neo, trong hạn không ai xóa được

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            raise ConfigError("Thiếu biến môi trường: " + ", ".join(missing))
        try:
            return cls(
                clamav_host=env.get("CLAMAV_HOST", "clamav"),
                clamav_port=int(env.get("CLAMAV_PORT", "3310")),
                clamav_timeout_s=float(env.get("CLAMAV_TIMEOUT_S", "60")),
                s3_endpoint=env.get("SEAWEEDFS_S3_ENDPOINT", "http://seaweedfs:8333"),
                s3_access_key=env["SEAWEEDFS_S3_ACCESS_KEY"],
                s3_secret_key=env["SEAWEEDFS_S3_SECRET_KEY"],
                s3_region=env.get("SEAWEEDFS_S3_REGION", "us-east-1"),
                bucket=env.get("MOC_FILES_BUCKET", "moc-files"),
                max_upload_bytes=int(env.get("MOC_FILES_MAX_MB", "25")) * 1024 * 1024,
                oidc_issuer=env["MOC_OIDC_ISSUER"],
                oidc_jwks_url=env["MOC_OIDC_JWKS_URL"],
                oidc_audience=env.get("MOC_OIDC_AUDIENCE") or None,
                hasura_url=env.get("HASURA_URL", "http://hasura:8080").rstrip("/"),
                hasura_admin_secret=env["HASURA_ADMIN_SECRET"],
                hasura_timeout_s=float(env.get("HASURA_TIMEOUT_S", "10")),
                meili_url=env.get("MEILISEARCH_URL", "http://meilisearch:7700").rstrip("/"),
                meili_api_key=env["MEILISEARCH_API_KEY"],
                search_index=env.get("MOC_SEARCH_INDEX", "documents"),
                # 0: tắt vòng đồng bộ nền (test gọi sync_once trực tiếp)
                search_sync_interval_s=float(env.get("MOC_SEARCH_SYNC_INTERVAL_S", "5")),
                text_interval_s=float(env.get("MOC_TEXT_INTERVAL_S", "10")),
                # mặc định: phần trước /realms/ của issuer, tức URL công khai của cổng
                public_url=(env.get("MOC_PUBLIC_URL") or env["MOC_OIDC_ISSUER"].split("/realms/")[0]).rstrip("/"),
                service_clients=frozenset(
                    c.strip() for c in env.get("MOC_SERVICE_CLIENTS", "svc-workflow").split(",") if c.strip()
                ),
                cold_bucket=env.get("MOC_COLD_BUCKET", "moc-cold"),
                anchor_interval_s=float(env.get("MOC_AUDIT_ANCHOR_INTERVAL_S", "600")),
                anchor_retention_days=int(env.get("MOC_AUDIT_ANCHOR_RETENTION_DAYS", "3650")),
            )
        except ValueError as exc:
            raise ConfigError(f"Giá trị số không hợp lệ: {exc}") from exc

    def __post_init__(self) -> None:
        if self.text_interval_s < 0:
            raise ConfigError("MOC_TEXT_INTERVAL_S phải ≥ 0 (0: tắt vòng đọc chữ của PDF)")
        if self.anchor_interval_s < 0:
            raise ConfigError("MOC_AUDIT_ANCHOR_INTERVAL_S phải ≥ 0 (0: tắt vòng neo)")
        if self.anchor_retention_days < 1:
            raise ConfigError("MOC_AUDIT_ANCHOR_RETENTION_DAYS phải ≥ 1")
        if self.cold_bucket == self.bucket:
            # bucket lạnh khóa ghi, còn bucket tệp thường phải xóa được
            raise ConfigError("MOC_COLD_BUCKET phải khác MOC_FILES_BUCKET")
