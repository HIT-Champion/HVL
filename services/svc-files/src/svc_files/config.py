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
            )
        except ValueError as exc:
            raise ConfigError(f"Giá trị số không hợp lệ: {exc}") from exc
