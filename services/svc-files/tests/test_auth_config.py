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

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from conftest import ISSUER, TENANT_A, StaticKeys
from svc_files.auth import AuthError, TokenVerifier
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
