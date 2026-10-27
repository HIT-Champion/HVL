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

"""Client Keycloak của ứng dụng trên trình duyệt: `moc realm clients` (make seed cũng gọi).

Keycloak chỉ nạp platform/keycloak/realm/moc-realm.json ở lần khởi động đầu (--import-realm bỏ qua realm đã có), nên
bản cài dựng trước khi có một ứng dụng mới — vd Không gian cá nhân `app-ca-nhan` (docs/them-ung-dung.md) — không tự có
client của ứng dụng đó, đăng nhập báo "Client not found". Lệnh này đọc tệp realm, thay `${BIẾN}` bằng giá trị trong
.env như Keycloak thay lúc nạp, rồi THÊM vào realm đang chạy những client còn thiếu.

Chỉ client của ứng dụng trên trình duyệt (công khai, Authorization Code, không luồng mật khẩu, không tài khoản dịch
vụ): không sửa client đã có (quản trị có thể đã chỉnh trên trang quản trị), không dựng lại client dòng lệnh `moc-cli`
hay client dịch vụ `svc-workflow` mà quản trị đã cố ý gỡ. Gọi Keycloak qua cổng quản trị nội bộ như `moc tenant`.

Cùng lý do, `moc realm theme` áp `loginTheme` của tệp realm (theme đăng nhập Signet, platform/keycloak/themes/) cho
realm nạp từ trước khi có theme: chỉ đặt khi realm còn dùng theme mặc định của Keycloak, không đổi theme quản trị đã
chọn; Keycloak chưa thấy thư mục theme (container dựng từ docker-compose.yml cũ) thì báo, không đặt.

`moc realm profile` thêm vào user profile của realm đang chạy các thuộc tính của tệp realm còn thiếu (vd `phone_number`
cho kênh SMS, #365): realm khai user profile tường minh, thuộc tính chưa khai thì Keycloak không lưu. Không sửa thuộc
tính đã có (quản trị có thể đã đổi quyền, kiểm tra), không xóa thuộc tính quản trị tự thêm.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

import tenants

REALM_FILE = pathlib.Path(__file__).resolve().parent.parent / "platform" / "keycloak" / "realm" / "moc-realm.json"
# ${TÊN} hoặc ${TÊN:mặc định} — cú pháp thay biến của Keycloak khi nạp realm
PLACEHOLDER = re.compile(r"\$\{([A-Za-z0-9_]+)(?::([^}]*))?\}")


def realm_from_text(text: str, env: dict[str, str]) -> dict[str, Any]:
    """Tệp realm sau khi thay biến. Giá trị được thoát như trong chuỗi JSON; biến không có trong env và không có mặc
    định thì giữ nguyên `${TÊN}` (client nào còn dấu đó thì không tạo — browser_apps báo)."""
    def value(m: re.Match[str]) -> str:
        found = env.get(m.group(1), m.group(2))
        return m.group(0) if found is None else json.dumps(found)[1:-1]
    return json.loads(PLACEHOLDER.sub(value, text))


def browser_app(client: dict[str, Any]) -> bool:
    return (client.get("publicClient") is True and client.get("standardFlowEnabled", True) is True
            and not client.get("directAccessGrantsEnabled") and not client.get("serviceAccountsEnabled")
            and not client.get("implicitFlowEnabled"))


def browser_apps(realm: dict[str, Any]) -> list[dict[str, Any]]:
    apps = [c for c in realm.get("clients", []) if browser_app(c)]
    for client in apps:
        left = PLACEHOLDER.findall(json.dumps(client))
        if left:
            raise tenants.TenantError(f"client {client['clientId']}: thiếu biến {', '.join(n for n, _ in left)} trong "
                                      ".env — Keycloak cần giá trị này để dựng client")
    return apps


def sync(kc: Any, realm: dict[str, Any], *, dry_run: bool = False) -> dict[str, list[str]]:
    """{"present": client đã có, "created": client vừa thêm (hoặc sẽ thêm, với dry_run)}."""
    have = {c.get("clientId") for c in kc.clients()}
    out: dict[str, list[str]] = {"present": [], "created": []}
    for client in browser_apps(realm):
        if client["clientId"] in have:
            out["present"].append(client["clientId"])
            continue
        if not dry_run:
            kc.create_client(client)
        out["created"].append(client["clientId"])
    return out


def run(env: dict[str, str], *, dry_run: bool = False, kc: Any = None) -> dict[str, list[str]]:
    realm = realm_from_text(REALM_FILE.read_text(encoding="utf-8"), env)
    return sync(kc or tenants.connect(), realm, dry_run=dry_run)


def describe(result: dict[str, list[str]], *, dry_run: bool = False) -> str:
    done = ", ".join(result["created"])
    if not done:
        return f"client ứng dụng trên trình duyệt: {', '.join(result['present'])} — đã có đủ"
    return f"client ứng dụng trên trình duyệt: {'sẽ thêm' if dry_run else 'vừa thêm'} {done}" + (
        f"; đã có {', '.join(result['present'])}" if result["present"] else "")


def cmd_clients(args: argparse.Namespace) -> int:
    import moc_env
    try:
        result = run(moc_env.ENV, dry_run=args.dry_run)
    except tenants.Unavailable as exc:
        print(f"{exc}. Signet có đang chạy không? (make ps)", file=sys.stderr)
        return 2
    except tenants.TenantError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({**result, "dry_run": args.dry_run}, ensure_ascii=False))
    else:
        print(describe(result, dry_run=args.dry_run))
    return 0


# --- theme đăng nhập: moc realm theme -------------------------------------------------------------------------------

def sync_theme(kc: Any, realm: dict[str, Any], *, dry_run: bool = False) -> dict[str, str]:
    """{"theme": loginTheme của tệp realm, "current": theme realm đang dùng ("" là mặc định của Keycloak), "action":
    "present" đã dùng | "set" vừa đặt (sẽ đặt, với dry_run) | "kept" quản trị đã chọn theme khác, giữ nguyên}."""
    want = realm.get("loginTheme")
    if not want:
        raise tenants.TenantError(f"{REALM_FILE.name} không đặt loginTheme — không có gì để áp")
    if want not in kc.login_themes():
        # đặt tên theme Keycloak không có thì trang đăng nhập vẫn chạy bằng theme mặc định, chỉ có dòng WARN trong log
        raise tenants.TenantError(
            f"Keycloak chưa có theme đăng nhập {want}: container keycloak dựng từ docker-compose.yml cũ chưa gắn "
            f"platform/keycloak/themes/{want}. Chạy docker compose up -d --wait keycloak trong thư mục cài rồi "
            "chạy lại lệnh này")
    rep = kc.realm()
    current = rep.get("loginTheme") or ""
    if current == want:
        return {"theme": want, "current": current, "action": "present"}
    if current:
        return {"theme": want, "current": current, "action": "kept"}
    if not dry_run:
        kc.update_realm({**rep, "loginTheme": want})
        if kc.realm().get("loginTheme") != want:
            raise tenants.TenantError(f"Keycloak không nhận loginTheme {want} cho realm {kc.realm_name}")
    return {"theme": want, "current": current, "action": "set"}


def run_theme(env: dict[str, str], *, dry_run: bool = False, kc: Any = None) -> dict[str, str]:
    realm = realm_from_text(REALM_FILE.read_text(encoding="utf-8"), env)
    return sync_theme(kc or tenants.connect(), realm, dry_run=dry_run)


def describe_theme(result: dict[str, str], *, dry_run: bool = False) -> str:
    theme, current = result["theme"], result["current"]
    if result["action"] == "present":
        return f"theme đăng nhập: realm đã dùng {theme}"
    if result["action"] == "kept":
        return (f"theme đăng nhập: realm đang dùng {current} do quản trị chọn — giữ nguyên; muốn dùng {theme} thì mở "
                "trang quản trị Keycloak → Realm settings → Themes → Login theme")
    return f"theme đăng nhập: {'sẽ đặt' if dry_run else 'vừa đặt'} {theme} (trước đó: theme mặc định của Keycloak)"


def cmd_theme(args: argparse.Namespace) -> int:
    import moc_env
    try:
        result = run_theme(moc_env.ENV, dry_run=args.dry_run)
    except tenants.Unavailable as exc:
        print(f"{exc}. Signet có đang chạy không? (make ps)", file=sys.stderr)
        return 2
    except tenants.TenantError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({**result, "dry_run": args.dry_run}, ensure_ascii=False))
    else:
        print(describe_theme(result, dry_run=args.dry_run))
    return 0


# --- user profile: moc realm profile -------------------------------------------------------------------------------

PROFILE = "org.keycloak.userprofile.UserProfileProvider"


def file_profile(realm: dict[str, Any]) -> dict[str, Any]:
    """Cấu hình user profile khai trong tệp realm (chuỗi JSON trong components)."""
    try:
        return json.loads(realm["components"][PROFILE][0]["config"]["kc.user.profile.config"][0])
    except (KeyError, IndexError, ValueError) as exc:
        raise tenants.TenantError(f"{REALM_FILE.name} không khai user profile ({PROFILE})") from exc


def sync_profile(kc: Any, realm: dict[str, Any], *, dry_run: bool = False) -> dict[str, list[str]]:
    """{"present": thuộc tính đã có, "added": thuộc tính vừa thêm (sẽ thêm, với dry_run)}; nhóm thuộc tính mà thuộc
    tính mới dùng cũng được thêm nếu realm chưa có."""
    want = file_profile(realm)
    rep = kc.user_profile()
    have = {a.get("name") for a in rep.get("attributes") or []}
    missing = [a for a in want.get("attributes") or [] if a["name"] not in have]
    out = {"present": [a["name"] for a in want.get("attributes") or [] if a["name"] in have],
           "added": [a["name"] for a in missing]}
    if not missing or dry_run:
        return out
    groups = {g.get("name") for g in rep.get("groups") or []}
    used = {a.get("group") for a in missing} - {None}
    new_groups = [g for g in want.get("groups") or [] if g["name"] in used - groups]
    kc.update_user_profile({**rep, "attributes": [*(rep.get("attributes") or []), *missing],
                            "groups": [*(rep.get("groups") or []), *new_groups]})
    now = {a.get("name") for a in kc.user_profile().get("attributes") or []}
    if not set(out["added"]) <= now:
        raise tenants.TenantError(f"Keycloak không nhận thuộc tính {', '.join(sorted(set(out['added']) - now))} cho "
                                  f"user profile của realm {kc.realm_name}")
    return out


def run_profile(env: dict[str, str], *, dry_run: bool = False, kc: Any = None) -> dict[str, list[str]]:
    realm = realm_from_text(REALM_FILE.read_text(encoding="utf-8"), env)
    return sync_profile(kc or tenants.connect(), realm, dry_run=dry_run)


def describe_profile(result: dict[str, list[str]], *, dry_run: bool = False) -> str:
    if not result["added"]:
        return "user profile: đã có đủ thuộc tính của moc-realm.json"
    return f"user profile: {'sẽ thêm' if dry_run else 'vừa thêm'} thuộc tính {', '.join(result['added'])}"


def cmd_profile(args: argparse.Namespace) -> int:
    import moc_env
    try:
        result = run_profile(moc_env.ENV, dry_run=args.dry_run)
    except tenants.Unavailable as exc:
        print(f"{exc}. Signet có đang chạy không? (make ps)", file=sys.stderr)
        return 2
    except tenants.TenantError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({**result, "dry_run": args.dry_run}, ensure_ascii=False))
    else:
        print(describe_profile(result, dry_run=args.dry_run))
    return 0
