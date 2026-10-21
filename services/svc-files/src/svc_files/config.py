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
import re
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


# tên dữ liệu ngôn ngữ của tesseract (đi vào argv, không qua shell): vie, eng, vie+eng
OCR_LANG_RE = re.compile(r"[A-Za-z0-9_]{1,32}(?:\+[A-Za-z0-9_]{1,32}){0,3}")


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
    archive_interval_s: float = 3600.0  # chu kỳ nộp lưu hồ sơ đã đóng (F3.8); 0: tắt vòng nền
    archive_after_days: int = 365   # hồ sơ đóng từ chừng ấy ngày thì nộp lưu (NĐ 30: trong 01 năm)
    openlineage_url: str = ""       # gửi thêm sự kiện phả hệ tới máy chủ OpenLineage (vd Marquez); rỗng: chỉ ghi CSDL
    # F3.7 — két giữ khóa transit bọc khóa dữ liệu của tệp văn bản hạn chế; rỗng: không nhận, không mở tệp mã hóa
    vault_addr: str = ""
    vault_role_id_file: str = "/run/openbao/role_id"
    vault_secret_id_file: str = "/run/openbao/secret_id"
    transit_key: str = "moc-files"
    # F4.1 — tác tử đọc văn bản đến (docread/): lớp chữ của PDF hoặc OCR (Tesseract), quy tắc, mô hình tùy chọn
    read_enabled: bool = True
    read_max_bytes: int = 25 * 1024 * 1024
    read_text_pages: int = 3            # số trang lớp chữ đọc
    ocr_max_pages: int = 1              # số trang OCR: số, ngày, cơ quan, trích yếu đều ở trang 1
    ocr_lang: str = "vie"
    ocr_timeout_s: float = 40.0         # hạn tiến trình con OCR, quá thì giết cả nhóm (cả tesseract)
    ocr_memory_mb: int = 1536           # RLIMIT_AS của tiến trình con OCR (tesseract kế thừa)
    ocr_max_pixels: int = 40_000_000    # trần điểm ảnh: chặn ảnh bom giải nén
    read_concurrency: int = 1           # số lượt đọc cùng lúc (OCR, mô hình tốn CPU)
    read_queue_s: float = 15.0          # chờ lượt quá thì 503 busy
    read_deadline_s: float = 50.0       # hạn tổng một yêu cầu, dưới 60 s mặc định của APISIX
    ai_url: str = ""                    # Ollama trong mạng nội bộ; rỗng: không dùng mô hình
    ai_model: str = "qwen3:1.7b"
    ai_timeout_s: float = 20.0
    ai_max_chars: int = 3000            # số ký tự thân văn bản gửi mô hình
    ai_summary: str = "fallback"        # fallback: chỉ khi quy tắc không ra trích yếu tin cậy cao · always
    agent_id: str = "moc-doc-reader"    # danh tính tác tử trong sổ kiểm toán (X-Hasura-User-Id của vai trò agent)
    tesseract_bin: str = "tesseract"

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
                archive_interval_s=float(env.get("MOC_ARCHIVE_INTERVAL_S", "3600")),
                archive_after_days=int(env.get("MOC_ARCHIVE_AFTER_DAYS", "365")),
                openlineage_url=env.get("MOC_OPENLINEAGE_URL", "").strip(),
                vault_addr=(env.get("MOC_OPENBAO_ADDR") or "").rstrip("/"),
                vault_role_id_file=env.get("MOC_OPENBAO_ROLE_ID_FILE", "/run/openbao/role_id"),
                vault_secret_id_file=env.get("MOC_OPENBAO_SECRET_ID_FILE", "/run/openbao/secret_id"),
                transit_key=env.get("MOC_FILES_TRANSIT_KEY", "moc-files"),
                read_enabled=_flag("MOC_READ_ENABLED", env.get("MOC_READ_ENABLED", "true")),
                read_max_bytes=int(env.get("MOC_READ_MAX_MB") or env.get("MOC_FILES_MAX_MB", "25")) * 1024 * 1024,
                read_text_pages=int(env.get("MOC_READ_TEXT_PAGES", "3")),
                ocr_max_pages=int(env.get("MOC_OCR_MAX_PAGES", "1")),
                ocr_lang=env.get("MOC_OCR_LANG", "vie").strip(),
                ocr_timeout_s=float(env.get("MOC_OCR_TIMEOUT_S", "40")),
                ocr_memory_mb=int(env.get("MOC_OCR_MEMORY_MB", "1536")),
                ocr_max_pixels=int(env.get("MOC_OCR_MAX_PIXELS", "40000000")),
                read_concurrency=int(env.get("MOC_READ_CONCURRENCY", "1")),
                read_queue_s=float(env.get("MOC_READ_QUEUE_S", "15")),
                read_deadline_s=float(env.get("MOC_READ_DEADLINE_S", "50")),
                # mặc định là dịch vụ ollama của profile `ai`; không bật profile thì dò thấy không có, bỏ qua mô hình
                ai_url=env.get("MOC_AI_URL", "http://ollama:11434").strip().rstrip("/"),
                ai_model=env.get("MOC_AI_MODEL", "qwen3:1.7b").strip(),
                ai_timeout_s=float(env.get("MOC_AI_TIMEOUT_S", "20")),
                ai_max_chars=int(env.get("MOC_AI_MAX_CHARS", "3000")),
                ai_summary=env.get("MOC_AI_SUMMARY", "fallback").strip().lower(),
                agent_id=env.get("MOC_AGENT_ID", "moc-doc-reader").strip(),
                tesseract_bin=env.get("MOC_TESSERACT_BIN", "tesseract").strip(),
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
        if self.archive_interval_s < 0:
            raise ConfigError("MOC_ARCHIVE_INTERVAL_S phải ≥ 0 (0: tắt vòng nộp lưu)")
        if self.archive_after_days < 0:
            raise ConfigError("MOC_ARCHIVE_AFTER_DAYS phải ≥ 0")
        if self.cold_bucket == self.bucket:
            # bucket lạnh khóa ghi, còn bucket tệp thường phải xóa được
            raise ConfigError("MOC_COLD_BUCKET phải khác MOC_FILES_BUCKET")
        self._check_reader()

    def _check_reader(self) -> None:
        """Biến của tác tử đọc văn bản đến (F4.1)."""
        if self.read_max_bytes < 1:
            raise ConfigError("MOC_READ_MAX_MB phải ≥ 1")
        if not 1 <= self.read_text_pages <= 200 or not 1 <= self.ocr_max_pages <= 200:
            raise ConfigError("MOC_READ_TEXT_PAGES, MOC_OCR_MAX_PAGES phải trong 1–200")
        if not OCR_LANG_RE.fullmatch(self.ocr_lang):
            raise ConfigError("MOC_OCR_LANG phải là tên dữ liệu ngôn ngữ của tesseract, vd vie hoặc vie+eng")
        if self.ocr_timeout_s <= 0 or self.read_deadline_s <= 0 or self.ai_timeout_s <= 0:
            raise ConfigError("MOC_OCR_TIMEOUT_S, MOC_READ_DEADLINE_S, MOC_AI_TIMEOUT_S phải > 0")
        if self.read_queue_s < 0:
            raise ConfigError("MOC_READ_QUEUE_S phải ≥ 0")
        if self.ocr_memory_mb < 64 or self.ocr_max_pixels < 1:
            raise ConfigError("MOC_OCR_MEMORY_MB phải ≥ 64, MOC_OCR_MAX_PIXELS phải ≥ 1")
        if self.read_concurrency < 1:
            raise ConfigError("MOC_READ_CONCURRENCY phải ≥ 1")
        if self.ai_url and not self.ai_url.startswith(("http://", "https://")):
            raise ConfigError("MOC_AI_URL phải là URL http(s)://…, hoặc rỗng để tắt mô hình")
        if self.ai_url and not self.ai_model:
            raise ConfigError("MOC_AI_MODEL không được rỗng khi có MOC_AI_URL")
        if self.ai_max_chars < 100:
            raise ConfigError("MOC_AI_MAX_CHARS phải ≥ 100")
        if self.ai_summary not in ("fallback", "always"):
            raise ConfigError("MOC_AI_SUMMARY chỉ nhận fallback hoặc always")
        if not 1 <= len(self.agent_id) <= 64:
            raise ConfigError("MOC_AGENT_ID phải dài 1–64 ký tự")
        if not self.tesseract_bin:
            raise ConfigError("MOC_TESSERACT_BIN không được rỗng")


def _flag(name: str, value: str) -> bool:
    v = value.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} chỉ nhận true hoặc false")
