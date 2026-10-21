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
# tên chỉ mục đoạn của trợ lý hỏi đáp (F4.2): đi vào đường dẫn API của Meilisearch
ASK_INDEX_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


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
    # F4.2 — trợ lý hỏi đáp trên kho văn bản (assist/): chỉ mục đoạn Meilisearch, câu trích, mô hình tùy chọn
    ask_enabled: bool = True
    ask_index: str = "chunks"           # chỉ mục đoạn, khác MOC_SEARCH_INDEX
    ask_sync_interval_s: float = 5.0    # chu kỳ đồng bộ chỉ mục đoạn; 0 chỉ khi tắt trợ lý
    ask_top_k: int = 5                  # số nguồn trả về
    ask_candidates: int = 24            # số đoạn lấy từ Meilisearch trước hậu kiểm
    ask_per_doc: int = 2                # số đoạn tối đa mỗi văn bản
    # ngưỡng _rankingScore khi tìm theo từ khóa: 0 — chiến lược "frequency" đã buộc đoạn chứa từ hiếm nhất của câu
    # hỏi, còn điểm "words" là số từ khớp / số từ của câu hỏi nên nguồn đúng mà dùng chữ khác vẫn điểm thấp (đo
    # 21/10 trên kho mẫu: 88/CTSV đúng 0,12; đoạn lạc đề tới 0,41)
    ask_min_score: float = 0.0
    # ngưỡng khi tìm lai (từ khóa + nghĩa, tỷ trọng 0,5): đo 21/10 trên kho mẫu với Qwen3-Embedding-0.6B — nguồn đúng
    # đứng đầu ≥ 0,88 ở cả 16 câu có đáp án, câu không có đáp án điểm cao nhất ≤ 0,70
    ask_min_score_semantic: float = 0.75
    ask_semantic_ratio: float = 0.5     # tỷ trọng tìm theo nghĩa
    ask_deadline_s: float = 50.0        # hạn tổng một yêu cầu (dưới 60 giây của APISIX)
    ask_model: str = "qwen3:1.7b"       # mô hình viết câu trả lời; MOC_ASK_MODEL rỗng thì bằng MOC_AI_MODEL
    ask_model_timeout_s: float = 40.0
    ask_context_chars: int = 2800       # tổng ký tự nguồn gửi mô hình
    ask_concurrency: int = 1            # số lượt sinh câu trả lời cùng lúc
    ask_queue_s: float = 20.0           # chờ lượt sinh quá thì 503 busy
    ai_embed_model: str = "qwen3-embedding:0.6b"    # rỗng: không nhúng, chỉ tìm từ khóa
    ai_embed_dims: int = 1024
    ai_embed_batch: int = 8             # số đoạn mỗi lô nhúng nền
    assistant_id: str = "moc-assistant"  # danh tính trợ lý trong sổ kiểm toán (X-Hasura-User-Id của vai trò agent)

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
                ask_enabled=_flag("MOC_ASK_ENABLED", env.get("MOC_ASK_ENABLED", "true")),
                ask_index=env.get("MOC_ASK_INDEX", "chunks").strip(),
                ask_sync_interval_s=float(env.get("MOC_ASK_SYNC_INTERVAL_S", "5")),
                ask_top_k=int(env.get("MOC_ASK_TOP_K", "5")),
                ask_candidates=int(env.get("MOC_ASK_CANDIDATES", "24")),
                ask_per_doc=int(env.get("MOC_ASK_PER_DOC", "2")),
                ask_min_score=float(env.get("MOC_ASK_MIN_SCORE", "0")),
                ask_min_score_semantic=float(env.get("MOC_ASK_MIN_SCORE_SEMANTIC", "0.75")),
                ask_semantic_ratio=float(env.get("MOC_ASK_SEMANTIC_RATIO", "0.5")),
                ask_deadline_s=float(env.get("MOC_ASK_DEADLINE_S", "50")),
                ask_model=(env.get("MOC_ASK_MODEL") or "").strip() or env.get("MOC_AI_MODEL", "qwen3:1.7b").strip(),
                ask_model_timeout_s=float(env.get("MOC_ASK_MODEL_TIMEOUT_S", "40")),
                ask_context_chars=int(env.get("MOC_ASK_CONTEXT_CHARS", "2800")),
                ask_concurrency=int(env.get("MOC_ASK_CONCURRENCY", "1")),
                ask_queue_s=float(env.get("MOC_ASK_QUEUE_S", "20")),
                # biến có mà rỗng: tắt nhúng (compose truyền ${MOC_AI_EMBED_MODEL-…}); không có biến: mặc định
                ai_embed_model=env.get("MOC_AI_EMBED_MODEL", "qwen3-embedding:0.6b").strip(),
                ai_embed_dims=int(env.get("MOC_AI_EMBED_DIMS", "1024")),
                ai_embed_batch=int(env.get("MOC_AI_EMBED_BATCH", "8")),
                assistant_id=env.get("MOC_ASSISTANT_ID", "moc-assistant").strip(),
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
        self._check_assistant()

    def _check_assistant(self) -> None:
        """Biến của trợ lý hỏi đáp (F4.2)."""
        if not ASK_INDEX_RE.fullmatch(self.ask_index):
            raise ConfigError("MOC_ASK_INDEX chỉ gồm chữ, số, '_', '-' (1–64 ký tự)")
        if self.ask_index == self.search_index:
            raise ConfigError("MOC_ASK_INDEX phải khác MOC_SEARCH_INDEX (chỉ mục đoạn khác chỉ mục văn bản)")
        if self.ask_sync_interval_s < 0:
            raise ConfigError("MOC_ASK_SYNC_INTERVAL_S phải ≥ 0 (0 chỉ khi MOC_ASK_ENABLED=false)")
        if self.ask_enabled and self.ask_sync_interval_s == 0:
            # Không có vòng nền thì chỉ mục đoạn không bao giờ được tạo (mọi câu hỏi 503), không nhận văn bản mới,
            # không xóa đoạn của văn bản vừa hạn chế hay bị hủy. Không có cách dùng đúng nào nên dừng ngay, chỉ rõ cách
            # tắt trợ lý. Test cần trợ lý mà không cần vòng nền thì tiêm chunk_indexer giả vào create_app.
            raise ConfigError("MOC_ASK_SYNC_INTERVAL_S = 0 tắt vòng giữ chỉ mục đoạn, trợ lý hỏi đáp sẽ không có gì để "
                              "tìm — đặt > 0, hoặc tắt trợ lý bằng MOC_ASK_ENABLED=false")
        for name, value in (("MOC_ASK_MIN_SCORE", self.ask_min_score),
                            ("MOC_ASK_MIN_SCORE_SEMANTIC", self.ask_min_score_semantic),
                            ("MOC_ASK_SEMANTIC_RATIO", self.ask_semantic_ratio)):
            if not 0 <= value <= 1:
                raise ConfigError(f"{name} phải trong khoảng 0–1")
        if not 0 < self.ask_deadline_s <= 55:
            raise ConfigError("MOC_ASK_DEADLINE_S phải trong khoảng (0, 55] — dưới 60 giây của APISIX")
        if self.ask_model_timeout_s <= 0:
            raise ConfigError("MOC_ASK_MODEL_TIMEOUT_S phải > 0")
        if self.ask_queue_s < 0:
            raise ConfigError("MOC_ASK_QUEUE_S phải ≥ 0")
        for name, count in (("MOC_ASK_TOP_K", self.ask_top_k), ("MOC_ASK_CANDIDATES", self.ask_candidates),
                            ("MOC_ASK_PER_DOC", self.ask_per_doc), ("MOC_ASK_CONTEXT_CHARS", self.ask_context_chars),
                            ("MOC_ASK_CONCURRENCY", self.ask_concurrency), ("MOC_AI_EMBED_DIMS", self.ai_embed_dims),
                            ("MOC_AI_EMBED_BATCH", self.ai_embed_batch)):
            if count < 1:
                raise ConfigError(f"{name} phải ≥ 1")
        if self.ai_url and not self.ask_model:
            raise ConfigError("MOC_ASK_MODEL (hoặc MOC_AI_MODEL) không được rỗng khi có MOC_AI_URL")
        if not 1 <= len(self.assistant_id) <= 64:
            raise ConfigError("MOC_ASSISTANT_ID phải dài 1–64 ký tự")

    def warnings(self) -> list[str]:
        """Cấu hình chạy được nhưng dễ chậm: app ghi nhật ký ``config.warning`` lúc khởi động, không chặn."""
        out: list[str] = []
        if self.ai_url and self.ask_enabled:
            # Ollama của compose giữ tối đa 2 mô hình (OLLAMA_MAX_LOADED_MODELS): trích yếu F4.1 (MOC_AI_MODEL) dò và
            # nạp trước kể cả khi chỉ hỏi đáp, thêm mô hình sinh và mô hình nhúng F4.2
            models = {self.ai_model, self.ask_model} | ({self.ai_embed_model} if self.ai_embed_model else set())
            if len(models) > 2:
                out.append(f"MOC_ASK_MODEL ({self.ask_model}) khác MOC_AI_MODEL ({self.ai_model}): Ollama phải giữ "
                           f"{len(models)} mô hình nhưng compose chỉ cho 2 (OLLAMA_MAX_LOADED_MODELS) — mô hình bị nạp "
                           "đi nạp lại, câu trả lời và đọc văn bản đến dễ quá giờ. Để trống MOC_ASK_MODEL và đặt mô "
                           "hình muốn dùng vào MOC_AI_MODEL (dùng chung cho trích yếu và câu trả lời)")
        return out

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
