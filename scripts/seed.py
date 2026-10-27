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

"""make seed — nạp dữ liệu mẫu (F2.10). Chạy lại nhiều lần được.

1. Đơn vị và phòng ban: seed/tenants.sql (id cố định).
2. Tài khoản: seed/users.csv → Keycloak Admin REST qua cổng quản trị nội bộ (127.0.0.1).
   Client của ứng dụng trên trình duyệt còn thiếu so với moc-realm.json (realm nạp trước khi có ứng dụng đó) được
   thêm trước — `moc realm clients` (realm_clients.py).
3. Mỗi đơn vị mẫu một Organization trong Keycloak, tài khoản mẫu là thành viên (F3.12) — cùng các hàm của
   `moc tenant create` (tenants.py).
4. Văn bản: chạy kịch bản nghiệp vụ qua API như người dùng thật (seed_documents.py) — không chèn thẳng
   vào CSDL, để quy trình trong Flowable khớp với dữ liệu.
"""

from __future__ import annotations

import json
import sys
import time

import realm_clients
import tenants
from moc_env import ENV, KEYCLOAK_ADMIN_URL, PUBLIC_URL, REALM, ROOT, HTTPError, Session, call_json, compose, wait_for
from tenants import admin_token


def seed_tenants() -> None:
    sql = (ROOT / "seed" / "tenants.sql").read_bytes()
    compose("exec", "-T", "postgres", "psql", "-q", "-v", "ON_ERROR_STOP=1",
            "-U", ENV.get("POSTGRES_USER", "moc"), "-d", ENV.get("POSTGRES_DB", "moc"), stdin=sql)
    print("  đơn vị, phòng ban: xong")


# Khớp authenticatorConfig "moc-vai-tro-bat-buoc-otp" trong platform/keycloak/realm/moc-realm.json
MFA_ROLES = {"clerk", "manager", "director", "tenant_admin"}


def otp_credential(secret: str) -> dict:
    """TOTP với khóa cho trước (MOC_DEMO_TOTP_SECRET), cùng thông số với otpPolicy* của realm."""
    return {
        "type": "otp",
        "userLabel": "Signet — tài khoản mẫu",
        "secretData": json.dumps({"value": secret}),
        "credentialData": json.dumps({"subType": "totp", "digits": 6, "counter": 0, "period": 30,
                                      "algorithm": "HmacSHA1"}),
    }


def seed_users() -> None:
    token = admin_token()
    auth = {"Authorization": f"Bearer {token}"}
    base = f"{KEYCLOAK_ADMIN_URL}/admin/realms/{REALM}"
    domain = {"c300d5bb-028f-44cc-ba10-7b5277a4225d": "cntt", "318da474-60d6-4a90-aa7f-928b31b8fc59": "kt"}
    secret = ENV.get("MOC_DEMO_TOTP_SECRET", "")
    count = with_otp = 0
    for line in (ROOT / "seed" / "users.csv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        username, first, last, role, tenant, department = line.split(",")
        attrs = {"tenant_id": [tenant], "moc_role": [role]}
        if department != "-":
            attrs["department_id"] = [department]
        user = {
            "username": username,
            "enabled": True,
            "emailVerified": True,
            "firstName": first,
            "lastName": last,
            "email": f"{username}@{domain.get(tenant, 'demo')}.moc.example",
            "attributes": attrs,
        }
        needs_otp = role in MFA_ROLES and bool(secret)
        found, _ = call_json("GET", f"{base}/users?exact=true&username={username}", headers=auth)
        if found:
            user_id = found[0]["id"]
            # Chạy lại seed: chỉ thêm TOTP khi chưa có, không sinh thiết bị trùng
            creds, _ = call_json("GET", f"{base}/users/{user_id}/credentials", headers=auth)
            if needs_otp and not any(c["type"] == "otp" for c in creds):
                user["credentials"] = [otp_credential(secret)]
            call_json("PUT", f"{base}/users/{user_id}", user, headers=auth)
        else:
            if needs_otp:
                user["credentials"] = [otp_credential(secret)]
            _, headers = call_json("POST", f"{base}/users", user, headers=auth)
            user_id = headers["Location"].rsplit("/", 1)[-1]
        call_json("PUT", f"{base}/users/{user_id}/reset-password",
                  {"type": "password", "value": ENV["MOC_DEMO_PASSWORD"], "temporary": False}, headers=auth)
        count += 1
        with_otp += needs_otp
    print(f"  tài khoản Keycloak: {count}, trong đó {with_otp} tài khoản đã cài sẵn TOTP")
    if not secret:
        print("  (chưa có MOC_DEMO_TOTP_SECRET trong .env: văn thư, lãnh đạo sẽ phải tự cài TOTP ở lần đăng nhập đầu)")


def seed_organizations() -> None:
    """Organization của các đơn vị mẫu, tài khoản mẫu là thành viên: tạo nếu chưa có, chạy lại thì giữ nguyên."""
    wanted = {line.split(",")[4] for line in (ROOT / "seed" / "users.csv").read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")}
    rows = [t for t in tenants.database().query(tenants.TENANTS_SQL) if t["id"] in wanted]
    enabled, done = tenants.organize(tenants.connect(), rows)
    added = sum(len(d["added"]) for d in done)
    print(f"  Keycloak Organizations: {', '.join(d['alias'] for d in done)} — {sum(d['members'] for d in done)} "
          f"thành viên" + (f", vừa thêm {added}" if added else "")
          + ("; vừa bật Organizations cho realm" if enabled else ""))


def wait_directory(timeout_s: int = 90) -> None:
    """svc-workflow chép danh bạ Keycloak sang core.users theo chu kỳ; đợi tài khoản mẫu có mặt."""
    wanted = sum(1 for line in (ROOT / "seed" / "users.csv").read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#") and ",c300d5bb-" in line)
    clerk = Session("vanthu")
    deadline = time.time() + timeout_s
    while len(clerk.gql("{ core_users(where: {enabled: {_eq: true}}) { id } }")["core_users"]) < wanted:
        if time.time() > deadline:
            sys.exit("svc-workflow chưa đồng bộ danh bạ từ Keycloak — xem: docker compose logs svc-workflow")
        time.sleep(2)
    print("  danh bạ (core.users): đã đồng bộ")


def main() -> None:
    if len(ENV.get("MOC_DEMO_PASSWORD", "")) < 10:
        sys.exit("MOC_DEMO_PASSWORD trong .env phải có ít nhất 10 ký tự (chính sách mật khẩu của realm)")
    print("Đợi Keycloak và cổng APISIX…")
    wait_for(f"{KEYCLOAK_ADMIN_URL}/realms/{REALM}", "Keycloak")
    wait_for(f"{PUBLIC_URL}/realms/{REALM}", "APISIX")
    print("Nạp dữ liệu mẫu:")
    seed_tenants()
    try:
        print("  " + realm_clients.describe(realm_clients.run(ENV)))
        print("  " + realm_clients.describe_profile(realm_clients.run_profile(ENV)))
        seed_users()
        seed_organizations()
    except HTTPError as exc:
        sys.exit(f"Keycloak từ chối: {exc}")
    except (tenants.TenantError, tenants.Unavailable) as exc:
        sys.exit(str(exc))
    if "--no-documents" not in sys.argv:
        if not ENV.get("MOC_DEMO_TOTP_SECRET"):
            # văn bản mẫu dựng bằng tài khoản văn thư, lãnh đạo qua client moc-cli — client này hỏi mã TOTP như trình duyệt
            sys.exit("Thiếu MOC_DEMO_TOTP_SECRET trong .env nên không đăng nhập được tài khoản mẫu văn thư, lãnh đạo để "
                     "dựng văn bản mẫu — thêm một chuỗi ngẫu nhiên rồi chạy lại make seed")
        wait_directory()
        import seed_documents
        seed_documents.run()
    print(f"Xong. Mở {PUBLIC_URL} — đăng nhập vanthu, truongkhoa, totruongdt, chuyenviendt, giamkhao… "
          "(mật khẩu: MOC_DEMO_PASSWORD trong .env)")
    print("Văn thư, lãnh đạo, tổ trưởng, quản trị còn phải nhập mã TOTP: make totp (bản cài: python3 scripts/totp.py) "
          "in mã hiện tại và khóa để thêm vào ứng dụng xác thực trên điện thoại.")


if __name__ == "__main__":
    main()
