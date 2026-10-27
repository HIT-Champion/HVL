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

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from conftest import ISSUER, TENANT_A, StaticKeys
from svc_files.auth import HASURA_CLAIMS, AuthError, TokenVerifier
from svc_files.config import ConfigError, Settings


def test_valid_token_gives_principal(verifier, make_token):
    p = verifier.verify(make_token(sub="u-1"))
    assert p.user_id == "u-1"
    assert p.tenant_id == TENANT_A
    assert p.roles == ("clerk",)


def test_wrong_issuer(verifier, make_token):
    with pytest.raises(AuthError) as e:
        verifier.verify(make_token(iss="https://ke-gian.example/realms/dxos"))
    assert e.value.status == 401


def test_token_signed_by_another_key(make_token):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    v = TokenVerifier(ISSUER, "http://unused", keys=StaticKeys(other.public_key()))
    with pytest.raises(AuthError) as e:
        v.verify(make_token())
    assert e.value.status == 401


def test_tenant_must_be_uuid(verifier, make_token):
    with pytest.raises(AuthError) as e:
        verifier.verify(make_token(tenant="khoa-cntt"))
    assert e.value.status == 403


def test_audience_checked_when_configured(signing_key, make_token):
    v = TokenVerifier(ISSUER, "http://unused", "moc-api", keys=StaticKeys(signing_key.public_key()))
    with pytest.raises(AuthError):
        v.verify(make_token())
    assert v.verify(make_token(aud="moc-api")).tenant_id == TENANT_A


def test_settings_lists_every_missing_variable():
    with pytest.raises(ConfigError) as e:
        Settings.from_env({})
    for name in ("MOC_OIDC_ISSUER", "MOC_OIDC_JWKS_URL", "SEAWEEDFS_S3_ACCESS_KEY", "SEAWEEDFS_S3_SECRET_KEY",
                 "HASURA_ADMIN_SECRET", "MEILISEARCH_API_KEY"):
        assert name in str(e.value)


def test_settings_defaults(settings):
    assert settings.clamav_host == "clamav" and settings.clamav_port == 3310
    assert settings.bucket == "moc-files"
    assert settings.max_upload_bytes == 1024 * 1024
    assert settings.oidc_audience is None
    assert settings.hasura_url == "http://hasura:8080"


def test_principal_keeps_token_out_of_repr(verifier, make_token):
    token = make_token()
    p = verifier.verify(token)
    assert p.token == token
    assert token not in repr(p)


# --- vai trò người gọi (F4.2: trợ lý hỏi đáp chọn phạm vi theo vai trò) ---------------------------------------


def claims(*, roles: list[str], default: str | None = None, sub: str = "u-1") -> dict:
    ns = {"x-hasura-user-id": sub, "x-hasura-allowed-roles": roles, "x-hasura-tenant-id": str(TENANT_A)}
    if default is not None:
        ns["x-hasura-default-role"] = default
    return {HASURA_CLAIMS: ns}


def test_principal_role_is_the_default_role(verifier, make_token):
    assert verifier.verify(make_token(role="manager")).role == "manager"
    assert verifier.verify(make_token(**claims(roles=["staff", "manager"], default="staff"))).role == "staff"


def test_principal_role_without_default_is_the_only_allowed_role(verifier, make_token):
    assert verifier.verify(make_token(**claims(roles=["director"]))).role == "director"
    assert verifier.verify(make_token(**claims(roles=["staff", "manager"]))).role == ""


def test_principal_role_outside_allowed_roles_is_empty(verifier, make_token):
    # Hasura từ chối token như vậy; svc-files không đoán vai trò
    p = verifier.verify(make_token(**claims(roles=["staff"], default="clerk")))
    assert p.role == "" and p.roles == ("staff",)


# --- biến của trợ lý hỏi đáp (F4.2) -------------------------------------------------------------------------------

BASE = {"MOC_OIDC_ISSUER": ISSUER, "MOC_OIDC_JWKS_URL": "http://unused/jwks", "SEAWEEDFS_S3_ACCESS_KEY": "t",
        "SEAWEEDFS_S3_SECRET_KEY": "t", "HASURA_ADMIN_SECRET": "t", "MEILISEARCH_API_KEY": "t"}


def test_assistant_settings_defaults():
    s = Settings.from_env(BASE)
    assert s.ask_enabled is True and s.ask_index == "chunks" and s.ask_sync_interval_s == 5
    assert (s.ask_top_k, s.ask_candidates, s.ask_per_doc) == (5, 24, 2)
    assert (s.ask_min_score, s.ask_min_score_semantic, s.ask_semantic_ratio) == (0.0, 0.75, 0.5)
    assert (s.ask_deadline_s, s.ask_model_timeout_s, s.ask_context_chars) == (50, 40, 2800)
    assert (s.ask_concurrency, s.ask_queue_s) == (1, 20)
    assert s.ask_model == "qwen3:1.7b" and s.ai_embed_model == "qwen3-embedding:0.6b"
    assert (s.ai_embed_dims, s.ai_embed_batch, s.assistant_id) == (1024, 8, "moc-assistant")


def test_assistant_model_falls_back_to_the_summary_model():
    assert Settings.from_env({**BASE, "MOC_AI_MODEL": "qwen3:4b"}).ask_model == "qwen3:4b"
    assert Settings.from_env({**BASE, "MOC_AI_MODEL": "qwen3:4b", "MOC_ASK_MODEL": " "}).ask_model == "qwen3:4b"
    assert Settings.from_env({**BASE, "MOC_ASK_MODEL": "qwen3:0.6b"}).ask_model == "qwen3:0.6b"


def test_empty_embedding_model_turns_semantic_search_off():
    s = Settings.from_env({**BASE, "MOC_AI_EMBED_MODEL": "", "MOC_ASK_ENABLED": "false"})
    assert s.ai_embed_model == "" and s.ask_enabled is False


@pytest.mark.parametrize("env", [
    {"MOC_ASK_INDEX": "chunks!"}, {"MOC_ASK_INDEX": ""}, {"MOC_ASK_INDEX": "x" * 65},
    {"MOC_ASK_INDEX": "documents", "MOC_SEARCH_INDEX": "documents"},
    {"MOC_ASK_SYNC_INTERVAL_S": "-1"}, {"MOC_ASK_MIN_SCORE": "1.5"}, {"MOC_ASK_MIN_SCORE_SEMANTIC": "-0.1"},
    {"MOC_ASK_SEMANTIC_RATIO": "2"}, {"MOC_ASK_DEADLINE_S": "56"}, {"MOC_ASK_DEADLINE_S": "0"},
    {"MOC_ASK_MODEL_TIMEOUT_S": "0"}, {"MOC_ASK_QUEUE_S": "-1"}, {"MOC_ASK_TOP_K": "0"},
    {"MOC_ASK_CANDIDATES": "0"}, {"MOC_ASK_PER_DOC": "0"}, {"MOC_ASK_CONTEXT_CHARS": "0"},
    {"MOC_ASK_CONCURRENCY": "0"}, {"MOC_AI_EMBED_DIMS": "0"}, {"MOC_AI_EMBED_BATCH": "0"},
    {"MOC_ASSISTANT_ID": ""}, {"MOC_ASSISTANT_ID": "a" * 65}, {"MOC_ASK_ENABLED": "co"},
    {"MOC_AI_URL": "http://ollama:11434", "MOC_AI_MODEL": " ", "MOC_ASK_MODEL": ""},
])
def test_bad_assistant_settings_stop_startup(env):
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE, **env})


def test_assistant_needs_its_index_loop():
    """Trợ lý bật mà tắt vòng nền thì chỉ mục đoạn không bao giờ được tạo, mọi câu hỏi 503 — dừng ngay, chỉ cách tắt."""
    with pytest.raises(ConfigError, match="MOC_ASK_ENABLED=false"):
        Settings.from_env({**BASE, "MOC_ASK_SYNC_INTERVAL_S": "0"})
    s = Settings.from_env({**BASE, "MOC_ASK_SYNC_INTERVAL_S": "0", "MOC_ASK_ENABLED": "false"})
    assert s.ask_sync_interval_s == 0 and s.ask_enabled is False


def test_three_models_for_two_ollama_slots_is_a_warning_not_an_error():
    ai = {**BASE, "MOC_AI_URL": "http://ollama:11434"}
    assert Settings.from_env(ai).warnings() == []                                     # một mô hình sinh + nhúng
    assert Settings.from_env({**ai, "MOC_ASK_MODEL": "qwen3:1.7b"}).warnings() == []    # bằng MOC_AI_MODEL
    assert Settings.from_env({**ai, "MOC_ASK_MODEL": "qwen3:4b", "MOC_AI_EMBED_MODEL": ""}).warnings() == []
    assert Settings.from_env({**ai, "MOC_ASK_MODEL": "qwen3:4b", "MOC_ASK_ENABLED": "false",
                              "MOC_ASK_SYNC_INTERVAL_S": "0"}).warnings() == []
    assert Settings.from_env({**ai, "MOC_AI_URL": "", "MOC_ASK_MODEL": "qwen3:4b"}).warnings() == []
    (warning,) = Settings.from_env({**ai, "MOC_ASK_MODEL": "qwen3:4b"}).warnings()
    assert "qwen3:4b" in warning and "qwen3:1.7b" in warning and "OLLAMA_MAX_LOADED_MODELS" in warning


# --- biến của lô nạp văn bản đến (imports/) -------------------------------------------------------------------------

def test_import_settings_defaults():
    s = Settings.from_env(BASE)
    assert (s.import_interval_s, s.import_chunk, s.import_max_open) == (2.0, 20, 3)
    assert (s.import_max_rows, s.import_register_max_rows) == (1000, 200)
    assert (s.import_data_max_bytes, s.import_zip_max_bytes) == (5 * 1024 * 1024, 50 * 1024 * 1024)
    assert (s.import_spool_dir, s.import_spool_bytes) == ("/tmp/moc-nap-lo", 200 * 1024 * 1024)
    assert s.import_store_max_bytes == 200 * 1024 * 1024
    assert Settings.from_env({**BASE, "MOC_IMPORT_STORE_MAX_MB": "30"}).import_store_max_bytes == 30 * 1024 * 1024
    assert s.warnings() == []


@pytest.mark.parametrize("env", [
    {"MOC_IMPORT_INTERVAL_S": "-1"}, {"MOC_IMPORT_CHUNK": "0"}, {"MOC_IMPORT_CHUNK": "201"},
    {"MOC_IMPORT_MAX_ROWS": "0"}, {"MOC_IMPORT_MAX_ROWS": "100001"},
    {"MOC_IMPORT_REGISTER_MAX_ROWS": "0"}, {"MOC_IMPORT_MAX_ROWS": "100", "MOC_IMPORT_REGISTER_MAX_ROWS": "101"},
    {"MOC_IMPORT_DATA_MAX_MB": "0"}, {"MOC_IMPORT_ZIP_MAX_MB": "0"}, {"MOC_IMPORT_SPOOL_MB": "0"},
    {"MOC_IMPORT_ZIP_MAX_MB": "60", "MOC_IMPORT_SPOOL_MB": "50"}, {"MOC_IMPORT_MAX_OPEN": "0"},
    {"MOC_IMPORT_SPOOL_DIR": "nap-lo"}, {"MOC_IMPORT_MAX_ROWS": "nhieu"},
    {"MOC_IMPORT_STORE_MAX_MB": "0"}, {"MOC_IMPORT_STORE_MAX_MB": "-5"}, {"MOC_IMPORT_STORE_MAX_MB": "200MB"},
])
def test_bad_import_settings_stop_startup(env):
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE, **env})


def test_import_interval_zero_turns_imports_off():
    s = Settings.from_env({**BASE, "MOC_IMPORT_INTERVAL_S": "0", "MOC_IMPORT_REGISTER_MAX_ROWS": "1000"})
    assert s.import_interval_s == 0 and s.import_register_max_rows == 1000


def test_import_request_over_the_gateway_limit_is_a_warning():
    assert Settings.from_env({**BASE, "MOC_IMPORT_DATA_MAX_MB": "13", "MOC_IMPORT_ZIP_MAX_MB": "50"}).warnings() == []
    (warning,) = Settings.from_env({**BASE, "MOC_IMPORT_DATA_MAX_MB": "14", "MOC_IMPORT_ZIP_MAX_MB": "50"}).warnings()
    assert "63 MB" in warning and "client_max_body_size" in warning


# --- OCR bản scan ở vòng đọc chữ (#253) ---------------------------------------------------------------------------


def test_scan_ocr_pages_default_and_bounds():
    # .env cũ không có biến này vẫn chạy: mặc định OCR 3 trang đầu; 0 tắt
    assert Settings.from_env(BASE).text_ocr_pages == 3
    assert Settings.from_env({**BASE, "MOC_TEXT_OCR_PAGES": "0"}).text_ocr_pages == 0
    for bad in ("-1", "201", "ba"):
        with pytest.raises(ConfigError):
            Settings.from_env({**BASE, "MOC_TEXT_OCR_PAGES": bad})
