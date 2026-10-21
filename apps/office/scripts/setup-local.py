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

"""Allow FE dev callbacks on the LOCAL demo realm only; never print credentials."""
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from moc_env import KEYCLOAK_ADMIN_URL, PUBLIC_URL, REALM, call_json, wait_for
from seed import admin_token


def main():
    if urlparse(PUBLIC_URL).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Local setup requires a loopback MOC_PUBLIC_URL.")
    wait_for(f"{KEYCLOAK_ADMIN_URL}/realms/{REALM}", "Keycloak", timeout_s=120)
    headers = {"Authorization": f"Bearer {admin_token()}"}
    base = f"{KEYCLOAK_ADMIN_URL}/admin/realms/{REALM}"
    call_json("PUT", base, {"loginTheme": "moc", "displayName": "Signet"}, headers=headers)
    clients, _ = call_json("GET", f"{base}/clients?clientId=app-office", headers=headers)
    client = clients[0]
    client["name"] = "Signet — Văn phòng điện tử"
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    for origin in origins:
        if f"{origin}/*" not in client["redirectUris"]:
            client["redirectUris"].append(f"{origin}/*")
        if origin not in client["webOrigins"]:
            client["webOrigins"].append(origin)
    attrs = client.setdefault("attributes", {})
    values = attrs.get("post.logout.redirect.uris", "").split("##")
    attrs["post.logout.redirect.uris"] = "##".join(dict.fromkeys(values + [f"{origin}/*" for origin in origins]))
    call_json("PUT", f"{base}/clients/{client['id']}", client, headers=headers)
    print("Local SSO callbacks and Signet display name configured.")


if __name__ == "__main__":
    main()
