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

"""Tự động hóa bằng Node-RED (#366, profile tu-dong, tắt mặc định): `moc tu-dong` (make tu-dong-up gọi sync).

Node-RED chạy dưới /tu-dong/ và tự đăng nhập bằng Keycloak (platform/tu-dong/settings.js): client công khai `tu-dong`,
luồng code + PKCE S256 do Node-RED làm ở phía máy chủ. Chỉ người có vai trò client `operator` của `tu-dong` vào được
trình soạn. Node-RED là MỘT không gian flow chung, không tách theo đơn vị, và flow gọi được mọi API qua cổng: vai trò
này dành cho người vận hành nền tảng, không cấp theo đơn vị, không ai có sẵn — kể cả quản trị đơn vị.

- `moc tu-dong sync`: thêm client `tu-dong`, vai trò `operator` và mapper `tu-dong-roles` vào realm đang chạy, hoặc
  đặt lại đường chuyển hướng nếu client đã có (đổi MOC_PUBLIC_URL). Realm chỉ nạp từ tệp ở lần đầu, nên bản cài nào cũng
  đi đường này; không bật profile thì realm không có gì của Node-RED.
- `moc tu-dong operator add|remove <tên đăng nhập>`, `moc tu-dong operator list`: cấp, gỡ, liệt kê vai trò. Gỡ có
  hiệu lực ở lần đăng nhập sau: token của trình soạn còn hạn (8 giờ) vẫn dùng được tới khi hết hạn hay Node-RED khởi
  động lại.

Mapper `tu-dong-roles` đưa vai trò client vào ID token: settings.js chỉ tin claim của ID token, thứ openid-client đã
kiểm chữ ký, iss, aud.

Robot của flow (`moc tu-dong robot add|list|rotate|remove <mã đơn vị>`): flow gọi API của lõi bằng danh tính riêng của
một đơn vị, không mượn tài khoản người. Mỗi đơn vị một client confidential `tu-dong-robot-<alias>` chỉ có luồng
client_credentials; mapper claim cố định đưa vào access token vai trò Hasura `tu_dong` (chỉ đọc văn bản không hạn chế
của đơn vị, gọi Action notifyFromFlow — db/metadata), x-hasura-tenant-id của đơn vị và x-hasura-user-id là chính
clientId (nhật ký, khóa thông báo ghi tên robot). Không đặt full scope: token không mang vai trò nào khác của realm.
Tài khoản dịch vụ của client không có tenant_id, moc_role nên không vào danh bạ core.users. Bí mật do Keycloak sinh,
`robot add` in ra để dán vào biến ROBOT_SECRET của flow mẫu (platform/tu-dong/flow-mau.json); lộ thì `robot rotate`.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import tenants

CLIENT_ID = "tu-dong"
ROLE = "operator"
SECRET_VAR = "MOC_TU_DONG_SECRET"
BASE = "/tu-dong/"
ROLE_REP = {"name": ROLE, "description": "Vào trình soạn Node-RED (/tu-dong/): người vận hành nền tảng, mọi đơn vị"}
MAPPER = {
    "name": "tu-dong-roles",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-usermodel-client-role-mapper",
    "config": {"usermodel.clientRoleMapping.clientId": CLIENT_ID, "claim.name": "resource_access.${client_id}.roles",
               "jsonType.label": "String", "multivalued": "true", "id.token.claim": "true",
               "access.token.claim": "false", "userinfo.token.claim": "false", "introspection.token.claim": "false"},
}


def client_rep(public_url: str) -> dict[str, Any]:
    """Client công khai, chỉ luồng code + PKCE: Node-RED đổi mã lấy token từ máy chủ, trình duyệt chỉ qua Keycloak."""
    base = f"{public_url.rstrip('/')}{BASE}"
    return {
        "clientId": CLIENT_ID,
        "name": "Tự động hóa (Node-RED)",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": True,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "implicitFlowEnabled": False,
        "redirectUris": [f"{base}auth/strategy/callback"],
        "webOrigins": [],
        "attributes": {"pkce.code.challenge.method": "S256"},
    }


def _client(kc: Any) -> dict[str, Any] | None:
    return next((c for c in kc.clients() if c.get("clientId") == CLIENT_ID), None)


def ensure_client(kc: Any, public_url: str, *, dry_run: bool = False) -> str:
    """"created" | "updated": thêm client `tu-dong`, hoặc đặt lại các trường của client_rep cho client đã có. Thiếu vai
    trò `operator`, mapper `tu-dong-roles` thì thêm."""
    want = client_rep(public_url)
    found = _client(kc)
    if dry_run:
        return "updated" if found else "created"
    if found is None:
        kc.create_client({**want, "protocolMappers": [MAPPER]})
        found = _client(kc)
        if found is None:
            raise tenants.TenantError(f"Keycloak tạo client {CLIENT_ID} xong nhưng không đọc lại được")
        action = "created"
    else:
        attributes = {**(found.get("attributes") or {}), **want["attributes"]}
        kc.update_client(found["id"], {**found, **want, "attributes": attributes})
        if not any(m.get("name") == MAPPER["name"] for m in kc.protocol_mappers(found["id"])):
            kc.add_protocol_mapper(found["id"], MAPPER)
        action = "updated"
    if not any(r.get("name") == ROLE for r in kc.client_roles(found["id"])):
        kc.create_client_role(found["id"], ROLE_REP)
    return action


def _role(kc: Any) -> tuple[str, dict[str, Any]]:
    found = _client(kc)
    role = next((r for r in kc.client_roles(found["id"]) if r.get("name") == ROLE), None) if found else None
    if found is None or role is None:
        raise tenants.TenantError(f"realm chưa có client {CLIENT_ID} hay vai trò {ROLE} — chạy make tu-dong-up (hoặc "
                                  "python3 scripts/moc.py tu-dong sync) trước")
    return found["id"], role


def operators(kc: Any) -> list[str]:
    cid, _ = _role(kc)
    return sorted(u.get("username", "") for u in kc.client_role_users(cid, ROLE))


def set_operator(kc: Any, username: str, *, revoke: bool = False) -> str:
    """"added" | "removed" | "unchanged": cấp hay gỡ vai trò `operator` cho một tài khoản đã có."""
    cid, role = _role(kc)
    user = kc.find_user(username)
    if user is None:
        raise tenants.TenantError(f"không có tài khoản {username} trong realm {kc.realm_name}")
    has = username in operators(kc)
    if has != revoke:
        return "unchanged"
    kc.grant_client_roles(user["id"], cid, [role], revoke=revoke)
    return "removed" if revoke else "added"


# --- robot của flow -----------------------------------------------------------------------------------------------

ROBOT_PREFIX = "tu-dong-robot-"
ROBOT_ROLE = "tu_dong"
CLAIMS = "https://hasura\\.io/jwt/claims"     # như mapper của client trong moc-realm.json: dấu chấm của tên miền thoát


def robot_id(code: str) -> str:
    return ROBOT_PREFIX + tenants.alias_for(code)


def _claim(name: str, value: str, json_type: str = "String") -> dict[str, Any]:
    return {"name": f"hasura-{name}", "protocol": "openid-connect", "protocolMapper": "oidc-hardcoded-claim-mapper",
            "config": {"claim.name": f"{CLAIMS}.x-hasura-{name}", "claim.value": value, "jsonType.label": json_type,
                       "access.token.claim": "true", "id.token.claim": "false", "userinfo.token.claim": "false",
                       "introspection.token.claim": "true"}}


def robot_mappers(code: str, tenant_id: str) -> list[dict[str, Any]]:
    return [_claim("user-id", robot_id(code)), _claim("tenant-id", tenant_id),
            _claim("default-role", ROBOT_ROLE), _claim("allowed-roles", json.dumps([ROBOT_ROLE]), "JSON")]


def robot_rep(code: str) -> dict[str, Any]:
    """Client confidential chỉ có luồng client_credentials, không đường chuyển hướng, không full scope."""
    return {
        "clientId": robot_id(code),
        "name": f"Robot tự động hóa — {code}",
        "description": f"Flow Node-RED (#366) gọi API của lõi thay mặt đơn vị {code}: vai trò Hasura {ROBOT_ROLE}",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-secret",
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": True,
        "fullScopeAllowed": False,
        "redirectUris": [],
        "webOrigins": [],
    }


def _unit(code: str, db: Any = None) -> dict[str, Any]:
    rows = (db or tenants.database()).query(tenants.TENANTS_SQL) or []
    unit = next((r for r in rows if r["code"] == code), None)
    if unit is None:
        raise tenants.TenantError(f"không có đơn vị mã {code} (python3 scripts/moc.py tenant list)")
    return unit


def _robot(kc: Any, code: str) -> dict[str, Any] | None:
    return next((c for c in kc.clients() if c.get("clientId") == robot_id(code)), None)


def add_robot(kc: Any, code: str, *, db: Any = None) -> dict[str, Any]:
    """Thêm robot của đơn vị, hoặc đặt lại các trường, mapper của robot đã có (chạy lại được) → clientId, bí mật."""
    unit = _unit(code, db)
    found = _robot(kc, code)
    want = robot_rep(code)
    mappers = robot_mappers(code, unit["id"])
    if found is None:
        kc.create_client({**want, "protocolMappers": mappers})
        found = _robot(kc, code)
        if found is None:
            raise tenants.TenantError(f"Keycloak tạo client {want['clientId']} xong nhưng không đọc lại được")
        action = "created"
    else:
        kc.update_client(found["id"], {**found, **want})
        have = {m.get("name"): m for m in kc.protocol_mappers(found["id"])}
        for mapper in mappers:
            old = have.get(mapper["name"])
            if old is None:
                kc.add_protocol_mapper(found["id"], mapper)
            elif old.get("protocolMapper") != mapper["protocolMapper"] or old.get("config") != mapper["config"]:
                kc.update_protocol_mapper(found["id"], old["id"], {**mapper, "id": old["id"]})
        action = "updated"
    return {"client_id": want["clientId"], "code": code, "tenant_id": unit["id"], "result": action,
            "secret": kc.client_secret(found["id"])}


def rotate_robot(kc: Any, code: str) -> dict[str, Any]:
    found = _robot(kc, code)
    if found is None:
        raise tenants.TenantError(f"đơn vị {code} chưa có robot — python3 scripts/moc.py tu-dong robot add {code}")
    return {"client_id": found["clientId"], "code": code, "result": "rotated",
            "secret": kc.client_secret(found["id"], regenerate=True)}


def remove_robot(kc: Any, code: str) -> str:
    """"removed" | "unchanged": gỡ client của robot; token đã cấp còn hạn (mặc định 5 phút) tới khi hết hạn."""
    found = _robot(kc, code)
    if found is None:
        return "unchanged"
    kc.delete_client(found["id"])
    return "removed"


def robots(kc: Any) -> list[dict[str, Any]]:
    """Robot đang có: clientId, đơn vị (claim tenant-id cố định), bật hay tắt."""
    out = []
    for c in sorted((c for c in kc.clients() if str(c.get("clientId", "")).startswith(ROBOT_PREFIX)),
                    key=lambda c: c["clientId"]):
        tenant = next((m["config"].get("claim.value") for m in kc.protocol_mappers(c["id"])
                       if m.get("name") == "hasura-tenant-id"), None)
        out.append({"client_id": c["clientId"], "tenant_id": tenant, "enabled": bool(c.get("enabled"))})
    return out


def check_secret(env: dict[str, str]) -> None:
    """Khóa mã hóa thông tin đăng nhập trong flow (credentialSecret): container dừng nếu thiếu, ở đây báo sớm hơn."""
    if len(env.get(SECRET_VAR, "")) < 32 or env.get(SECRET_VAR) == "change_me":
        raise tenants.TenantError(f"{SECRET_VAR} trong .env thiếu, ngắn hơn 32 ký tự hay còn change_me — make "
                                  "tu-dong-up sinh giá trị ngẫu nhiên")


def sync(env: dict[str, str], *, dry_run: bool = False, kc: Any = None) -> dict[str, Any]:
    check_secret(env)
    kc = kc or tenants.connect()
    client = ensure_client(kc, env["MOC_PUBLIC_URL"], dry_run=dry_run)
    return {"client": client, "operators": [] if dry_run and client == "created" else operators(kc)}


def describe(result: dict[str, Any], *, dry_run: bool) -> str:
    verb = {"created": "thêm", "updated": "cập nhật"}[result["client"]]
    who = ", ".join(result["operators"]) or "chưa ai — cấp bằng: python3 scripts/moc.py tu-dong operator add <tên>"
    return (f"Client Keycloak `{CLIENT_ID}`, vai trò `{ROLE}`: {'sẽ ' if dry_run else 'đã '}{verb}."
            f"\nNgười vào được trình soạn /tu-dong/: {who}")


def _run(work: Any) -> int:
    try:
        return work()
    except tenants.Unavailable as exc:
        print(f"{exc}. Signet có đang chạy không? (make ps)", file=sys.stderr)
        return 2
    except tenants.TenantError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_sync(args: argparse.Namespace) -> int:
    import moc_env

    def work() -> int:
        result = sync(moc_env.ENV, dry_run=args.dry_run)
        print(json.dumps({**result, "dry_run": args.dry_run}, ensure_ascii=False) if args.json
              else describe(result, dry_run=args.dry_run))
        return 0
    return _run(work)


def cmd_operator(args: argparse.Namespace) -> int:
    def work() -> int:
        kc = tenants.connect()
        if args.action == "list":
            names = operators(kc)
            print(json.dumps(names, ensure_ascii=False) if args.json else "\n".join(names) or "(chưa ai)")
            return 0
        if not args.username:
            raise tenants.TenantError(f"cần tên đăng nhập: moc tu-dong operator {args.action} <tên>")
        done = set_operator(kc, args.username, revoke=args.action == "remove")
        text = {"added": "đã cấp", "removed": "đã gỡ", "unchanged": "không đổi (đã như vậy)"}[done]
        print(json.dumps({"username": args.username, "result": done}) if args.json
              else f"{args.username}: vai trò {ROLE} của {CLIENT_ID} {text}")
        return 0
    return _run(work)


def cmd_robot(args: argparse.Namespace) -> int:
    def work() -> int:
        kc = tenants.connect()
        if args.action == "list":
            rows = robots(kc)
            lines = [f"{r['client_id']}  đơn vị {r['tenant_id'] or '?'}" + ("" if r["enabled"] else "  (đang tắt)")
                     for r in rows]
            print(json.dumps(rows, ensure_ascii=False) if args.json else "\n".join(lines) or "(chưa có robot nào)")
            return 0
        if not args.code:
            raise tenants.TenantError(f"cần mã đơn vị: moc tu-dong robot {args.action} <mã>")
        if args.action == "remove":
            done = remove_robot(kc, args.code)
            print(json.dumps({"client_id": robot_id(args.code), "result": done}) if args.json
                  else f"{robot_id(args.code)}: {'đã gỡ' if done == 'removed' else 'không có, không đổi'}")
            return 0
        out = add_robot(kc, args.code) if args.action == "add" else rotate_robot(kc, args.code)
        if args.json:
            print(json.dumps(out, ensure_ascii=False))
            return 0
        text = {"created": "đã tạo", "updated": "đã có, đặt lại cấu hình", "rotated": "đã đổi bí mật"}[out["result"]]
        print(f"{out['client_id']} (đơn vị {args.code}): {text}\n"
              f"  ROBOT_ID={out['client_id']}\n  ROBOT_SECRET={out['secret']}\n"
              "Dán hai giá trị vào biến của tab flow mẫu trong /tu-dong/ (ROBOT_SECRET là biến bí mật, Node-RED mã hóa "
              f"bằng {SECRET_VAR}); lộ thì: moc tu-dong robot rotate {args.code}")
        return 0
    return _run(work)


def add_parser(groups: Any) -> None:
    t = groups.add_parser("tu-dong", help="tự động hóa bằng Node-RED (#366, profile tu-dong)").add_subparsers(
        dest="cmd", required=True)
    ts = t.add_parser("sync", help="client Keycloak `tu-dong`, vai trò operator, mapper vai trò vào ID token")
    ts.add_argument("--dry-run", action="store_true", help="chỉ in việc sẽ làm, không thay đổi gì")
    ts.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    ts.set_defaults(run=cmd_sync)
    to = t.add_parser("operator", help="cấp, gỡ, liệt kê vai trò operator (vào được trình soạn /tu-dong/)")
    to.add_argument("action", choices=["add", "remove", "list"])
    to.add_argument("username", nargs="?", type=tenants.username_arg, help="tên đăng nhập (add, remove)")
    to.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    to.set_defaults(run=cmd_operator)
    tr = t.add_parser("robot", help="robot của flow theo đơn vị: client_credentials, vai trò Hasura tu_dong (chỉ đọc)")
    tr.add_argument("action", choices=["add", "list", "rotate", "remove"])
    tr.add_argument("code", nargs="?", type=tenants.code_arg, help="mã đơn vị (add, rotate, remove), vd CNTT")
    tr.add_argument("--json", action="store_true", help="in kết quả dạng JSON (add, rotate: có cả bí mật)")
    tr.set_defaults(run=cmd_robot)
