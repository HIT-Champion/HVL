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

"""Wiki nội bộ DokuWiki (#367, profile wiki, tắt mặc định): `moc wiki sync` (make wiki-up cũng gọi).

DokuWiki chạy dưới /wiki/, đăng nhập bằng Keycloak qua plugin oauth + oauthgeneric với client bí mật `wiki`; claim
`groups` của client đó là tenant_id, nên trong DokuWiki mỗi người thuộc đúng một nhóm là đơn vị của mình. Mỗi đơn vị
một không gian `don-vi:<alias>`: chỉ nhóm của đơn vị đó đọc, sửa, tải tệp lên.

Danh sách quyền (conf/acl.auth.php) ghi tường minh từng đơn vị, sinh từ core.tenants. Không dùng chỗ thay %GROUP% của
DokuWiki: nó sinh một không gian cho MỌI nhóm của người đăng nhập, gồm nhóm mặc định `user` và nhóm dịch vụ `generic`
mà plugin oauth gắn cho mọi người — thành chỗ chung mọi đơn vị cùng sửa. Không có dòng nào cho phép hai nhóm đó ghi.
Không gian cha `don-vi` không cấp quyền cho ai: DokuWiki xét quyền từ không gian sâu nhất lên, nên không gian không còn
dòng nào (bỏ lại khi đổi mã đơn vị, hay đơn vị tạo sau chưa chạy lệnh này) rơi về dòng `*` — không ai đọc, không ai tạo
trang được.

Lệnh này:
- thêm client `wiki` vào realm đang chạy, hoặc đặt lại bí mật (MOC_WIKI_CLIENT_SECRET trong .env), đường chuyển hướng
  và mapper `groups` nếu đã có — realm chỉ nạp từ tệp ở lần đầu, nên bản cài nào cũng đi đường này;
- ghi acl.auth.php và trang đầu (danh sách không gian của các đơn vị) vào volume của wiki.

Đơn vị tạo sau (`moc tenant create`) chưa có không gian tới khi chạy lại lệnh này: người của nó chỉ đọc được trang đầu.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

import tenants

CLIENT_ID = "wiki"
SECRET_VAR = "MOC_WIKI_CLIENT_SECRET"
BASE = "/wiki/"
NAMESPACE = "don-vi"
ACL_FILE = "/storage/conf/acl.auth.php"
START_PAGE = "/storage/data/pages/start.txt"
# Nhóm DokuWiki gắn cho mọi người đăng nhập ($conf['defaultgroup']); plugin oauth gắn thêm nhóm dịch vụ `generic`
EVERYONE = "user"
# Quyền DokuWiki: 1 đọc, 2 sửa, 4 tạo trang, 8 tải tệp lên, 16 xóa tệp
READ, DELETE = 1, 16
MAPPER = {
    "name": "wiki-groups",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-usermodel-attribute-mapper",
    # chỉ trong userinfo: plugin oauthgeneric đọc nhóm ở đó; token truy cập không mang thêm claim nào
    "config": {"user.attribute": "tenant_id", "claim.name": "groups", "jsonType.label": "String",
               "multivalued": "true", "userinfo.token.claim": "true", "id.token.claim": "false",
               "access.token.claim": "false", "introspection.token.claim": "false"},
}
# auth_nameencode của DokuWiki (inc/auth.php): ký tự ASCII khác chữ, số thành %<hex thường>
_ENCODE = re.compile(r"[\x00-\x2f\x3a-\x40\x5b-\x60\x7b-\x7f]")


def nameencode(name: str) -> str:
    return _ENCODE.sub(lambda m: f"%{ord(m.group(0)):x}", name)


def group_of(tenant_id: str) -> str:
    """Nhóm DokuWiki của một đơn vị như trong acl.auth.php: tenant_id viết thường, qua cleanGroup (giữ nguyên UUID)
    rồi auth_nameencode, như auth_aclcheck_cb so khớp."""
    return "@" + nameencode(tenant_id.lower())


def namespaces(rows: list[dict[str, Any]]) -> dict[str, str]:
    """tenant_id → không gian `don-vi:<alias>`. Alias như Keycloak Organizations (tenants.alias_for); hai mã ra cùng
    alias (KT và kt) thì đơn vị sau thêm 8 ký tự đầu của id."""
    out: dict[str, str] = {}
    taken: set[str] = set()
    for row in rows:
        alias = tenants.alias_for(row["code"])
        if alias in taken:
            alias = f"{alias}-{row['id'][:8].lower()}"
        taken.add(alias)
        out[row["id"]] = f"{NAMESPACE}:{alias}"
    return out


def acl_text(rows: list[dict[str, Any]]) -> str:
    lines = ["# Sinh bằng `moc wiki sync` (scripts/wiki.py) từ core.tenants — sửa tay sẽ bị ghi đè.",
             "# Không ai đọc được gì ngoài các dòng dưới; mỗi đơn vị chỉ không gian của mình.",
             "*\t@ALL\t0",
             f"start\t@{EVERYONE}\t{READ}",
             f"wiki:*\t@{EVERYONE}\t{READ}"]
    for tenant_id, ns in namespaces(rows).items():
        lines.append(f"{ns}:*\t{group_of(tenant_id)}\t{DELETE}")
    return "\n".join(lines) + "\n"


def _plain(text: str) -> str:
    """Chữ đặt trong liên kết DokuWiki: bỏ ký tự cú pháp ([ ] | { }), gộp khoảng trắng."""
    return " ".join(re.sub(r"[\[\]|{}]", " ", text).split())


def start_page(rows: list[dict[str, Any]]) -> str:
    ns = namespaces(rows)
    units = "\n".join(f"  * [[{ns[r['id']]}:start|{_plain(r['name'])}]] ({_plain(r['code'])})" for r in rows)
    return ("====== Wiki nội bộ ======\n\n"
            "Mỗi đơn vị có một không gian riêng: chỉ người của đơn vị đó đọc, sửa và tải tệp lên được. Mở không gian "
            "của đơn vị mình rồi bấm tạo trang.\n\n"
            "===== Không gian của các đơn vị =====\n\n"
            f"{units or '  * (chưa có đơn vị nào)'}\n\n"
            "Cú pháp viết trang: [[wiki:syntax]]. Trang này do Signet sinh lại mỗi lần chạy `moc wiki sync`; sửa tay "
            "sẽ mất.\n")


def client_rep(public_url: str, secret: str) -> dict[str, Any]:
    """Client bí mật, chỉ luồng code: plugin oauth đổi mã lấy token từ máy chủ wiki, không ở trình duyệt."""
    base = f"{public_url.rstrip('/')}{BASE}"
    return {
        "clientId": CLIENT_ID,
        "name": "Wiki nội bộ (DokuWiki)",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-secret",
        "secret": secret,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "implicitFlowEnabled": False,
        "redirectUris": [f"{base}doku.php"],
        "webOrigins": [],
        "attributes": {"post.logout.redirect.uris": f"{base}*"},
    }


def ensure_client(kc: Any, public_url: str, secret: str, *, dry_run: bool = False) -> str:
    """"created" | "updated": thêm client `wiki`, hoặc đặt lại các trường của client_rep cho client đã có (quản trị
    đổi bí mật trong .env, đổi MOC_PUBLIC_URL). Thiếu mapper `groups` thì thêm."""
    want = client_rep(public_url, secret)
    found = next((c for c in kc.clients() if c.get("clientId") == CLIENT_ID), None)
    if dry_run:
        return "updated" if found else "created"
    if found is None:
        kc.create_client({**want, "protocolMappers": [MAPPER]})
        return "created"
    attributes = {**(found.get("attributes") or {}), **want["attributes"]}
    kc.update_client(found["id"], {**found, **want, "attributes": attributes})
    if not any(m.get("name") == MAPPER["name"] for m in kc.protocol_mappers(found["id"])):
        kc.add_protocol_mapper(found["id"], MAPPER)
    return "updated"


def _exec(path: str, content: str) -> None:
    """Ghi một tệp vào volume của wiki qua container đang chạy (user 33 của image, như DokuWiki tự ghi): ghi tệp tạm
    rồi đổi tên, DokuWiki không bao giờ đọc phải tệp ghi dở."""
    from moc_env import ROOT
    script = 'set -e; mkdir -p "$(dirname "$1")"; cat > "$1.moc"; mv "$1.moc" "$1"'
    cmd = ["docker", "compose", "--profile", "core", "--profile", "app", "--profile", "wiki",
           "exec", "-T", "wiki", "sh", "-c", script, "sh", path]
    try:
        subprocess.run(cmd, cwd=ROOT, input=content.encode(), check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["?"]
        raise tenants.TenantError(f"không ghi được {path} vào container wiki ({detail[0]}) — wiki có đang chạy "
                                  "không? (make wiki-up)") from None


def sync(env: dict[str, str], *, dry_run: bool = False) -> dict[str, Any]:
    secret = env.get(SECRET_VAR, "")
    if not secret or secret == "change_me":
        raise tenants.TenantError(f"{SECRET_VAR} trong .env rỗng hay còn change_me — make wiki-up sinh giá trị "
                                  "ngẫu nhiên")
    rows = tenants.database().query(tenants.TENANTS_SQL)
    client = ensure_client(tenants.connect(), env["MOC_PUBLIC_URL"], secret, dry_run=dry_run)
    if not dry_run:
        _exec(ACL_FILE, acl_text(rows))
        _exec(START_PAGE, start_page(rows))
    ns = namespaces(rows)
    return {"client": client, "namespaces": {r["code"]: ns[r["id"]] for r in rows}}


def describe(result: dict[str, Any], *, dry_run: bool) -> str:
    verb = {"created": "thêm", "updated": "cập nhật"}[result["client"]]
    head = f"Client Keycloak `{CLIENT_ID}`: {'sẽ ' if dry_run else 'đã '}{verb}."
    done = ("Chưa ghi gì (--dry-run)." if dry_run
            else "Đã ghi danh sách quyền và trang đầu: mỗi đơn vị chỉ đọc, sửa được không gian của mình.")
    units = [f"  {code}: {ns}" for code, ns in result["namespaces"].items()]
    return "\n".join([head, done, "Không gian của các đơn vị:", *units])


def cmd_sync(args: argparse.Namespace) -> int:
    import moc_env
    try:
        result = sync(moc_env.ENV, dry_run=args.dry_run)
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


def add_parser(groups: Any) -> None:
    w = groups.add_parser("wiki", help="wiki nội bộ DokuWiki (#367, profile wiki)").add_subparsers(dest="cmd",
                                                                                                required=True)
    ws = w.add_parser("sync", help="client Keycloak `wiki`, danh sách quyền và trang đầu theo các đơn vị hiện có")
    ws.add_argument("--dry-run", action="store_true", help="chỉ in việc sẽ làm, không thay đổi gì")
    ws.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    ws.set_defaults(run=cmd_sync)
