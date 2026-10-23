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
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
import json
import time

ROOT = Path(__file__).resolve().parents[3]
ENV = dict(line.split('=', 1) for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines()
           if line.strip() and not line.lstrip().startswith('#') and '=' in line)
PUBLIC_URL = ENV.get('MOC_PUBLIC_URL', 'http://localhost:8080').rstrip('/')
KEYCLOAK_ADMIN_URL = 'http://127.0.0.1:' + ENV.get('KEYCLOAK_ADMIN_PORT', '8180')
REALM = ENV.get('MOC_REALM', 'moc')

def call_json(method, url, body=None, *, headers=None, form=None):
    request_headers = dict(headers or {})
    payload = None
    if form is not None:
        payload = urlencode(form).encode()
        request_headers['Content-Type'] = 'application/x-www-form-urlencoded'
    elif body is not None:
        payload = json.dumps(body).encode()
        request_headers['Content-Type'] = 'application/json'
    request_headers['User-Agent'] = 'Signet-FE-local-setup'
    with urlopen(Request(url, data=payload, headers=request_headers, method=method), timeout=20) as response:
        data = response.read()
        return (json.loads(data) if data else None), response.status

def wait_for(url, label, timeout_s=120):
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            call_json('GET', url)
            return
        except OSError:
            if time.monotonic() >= deadline: raise RuntimeError(label + ' unavailable') from None
            time.sleep(1)

def admin_token():
    data, _ = call_json('POST', KEYCLOAK_ADMIN_URL + '/realms/master/protocol/openid-connect/token',
        form={'grant_type': 'password', 'client_id': 'admin-cli',
              'username': ENV.get('KEYCLOAK_ADMIN_USER', 'admin'), 'password': ENV['KEYCLOAK_ADMIN_PASSWORD']})
    return data['access_token']


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
