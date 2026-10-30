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

"""make demo-wiki — wiki nội bộ (#367, profile wiki; cần make seed, make wiki-up).

Đi đúng đường của trình duyệt, qua cổng APISIX: /wiki/doku.php?do=login → plugin oauth của DokuWiki chuyển sang
Keycloak → mật khẩu (văn thư thêm mã TOTP) → Keycloak chuyển về /wiki/doku.php kèm mã, wiki tự đổi mã lấy token bằng
client bí mật `wiki` rồi đọc nhóm (đơn vị) ở userinfo. Giảng viên Khoa CNTT viết trang trong không gian đơn vị mình;
văn thư Khoa Kinh tế đã đăng nhập vẫn không đọc, không sửa được trang đó, sơ đồ trang của văn thư không liệt kê nó;
chiều ngược lại cũng vậy. Người chưa đăng nhập bị đưa sang trang đăng nhập Keycloak. Tài khoản wiki do plugin tạo ở
lần đăng nhập đầu từ dữ liệu Keycloak, nhóm là mã đơn vị.

--sau-khoi-phuc: chỉ đăng nhập lại và đọc trang của lần chạy trước — bước kiểm sau moc backup restore trong CI.
Thoát 0: đạt; 1: có bước sai hoặc không gọi được Signet.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import uuid

import wiki
from demo_ca_nhan import Browser, DemoFailed, ok, say
from moc_env import ENV, PUBLIC_URL, REALM, ROOT, HTTPError, _otp_counter, request, totp_at

WIKI = f"{PUBLIC_URL}{wiki.BASE}"
WRITER, CLERK = "giangvienktpm", "vanthukt"      # seed/users.csv: giảng viên Khoa CNTT; văn thư Khoa Kinh tế (TOTP)
TENANT_CNTT = "c300d5bb-028f-44cc-ba10-7b5277a4225d"
PAGE = "so-tay"
MARKER = "Trang viết bằng màn demo wiki nội bộ"   # chữ thường, không có cú pháp DokuWiki: hiện y nguyên trong HTML
DENIED = "Không có quyền thực hiện"              # tiêu đề trang từ chối của DokuWiki (inc/lang/vi/denied.txt)


class Page:
    def __init__(self, url: str, body: str) -> None:
        self.url, self.body = url, body
        self.path = urllib.parse.urlsplit(url).path

    @property
    def logged_in(self) -> bool:
        return "do=logout" in self.body                  # liên kết Đăng xuất chỉ có khi đã đăng nhập


def open_page(browser: Browser, url: str, data: dict[str, str] | None = None) -> Page:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        resp = browser.opener.open(url, data=body, timeout=30)
    except urllib.error.HTTPError as exc:
        # đăng nhập hỏng thì wiki và Keycloak chuyển qua lại mãi: urllib dừng ở lần chuyển thứ 10
        raise DemoFailed(f"{url} → HTTP {exc.code} — xem: docker compose --profile wiki logs wiki") from None
    return Page(resp.geturl(), resp.read().decode(errors="replace"))


def login(username: str) -> Browser:
    """Đăng nhập wiki như trình duyệt; mã TOTP (văn thư) tính từ MOC_DEMO_TOTP_SECRET như make seed cài."""
    browser = Browser()
    page = open_page(browser, f"{WIKI}doku.php?do=login")
    otp_sent = 0
    for _ in range(6):
        if page.path.startswith(wiki.BASE):
            break
        form = re.search(r'<form[^>]*\saction="([^"]+)"', page.body)
        if form is None:
            raise DemoFailed(f"{username}: Keycloak không chuyển về wiki, cũng không hỏi đăng nhập ({page.path})")
        if 'name="otp"' in page.body:
            if not ENV.get("MOC_DEMO_TOTP_SECRET") or otp_sent >= 3:
                raise DemoFailed(f"{username}: Keycloak không nhận mã TOTP (MOC_DEMO_TOTP_SECRET khác khóa make seed "
                                 "đã cài?)")
            if otp_sent:
                time.sleep(1.5)        # hai lần sai sát nhau thì Keycloak coi là dò mật khẩu
            fields = {"otp": totp_at(ENV["MOC_DEMO_TOTP_SECRET"], _otp_counter(username))}
            otp_sent += 1
        elif 'name="password"' in page.body:
            fields = {"username": username, "password": ENV["MOC_DEMO_PASSWORD"]}
        else:
            raise DemoFailed(f"{username}: trang Keycloak lạ ở {page.path} (cần đổi mật khẩu, cài TOTP?)")
        page = open_page(browser, urllib.parse.urljoin(page.url, html.unescape(form.group(1))), fields)
    if not page.path.startswith(wiki.BASE) or not page.logged_in:
        raise DemoFailed(f"{username}: chưa đăng nhập được wiki (dừng ở {page.path})")
    return browser


def save(browser: Browser, page_id: str, text: str, summary: str) -> Page:
    """Mở trang sửa, gửi lại đúng các trường ẩn của biểu mẫu (sectok chống CSRF, ngày, phần trước, sau…) cùng nội
    dung."""
    page = open_page(browser, f"{WIKI}{page_id}?do=edit")
    form = re.search(r'<form\b[^>]*\bid="dw__editform"[^>]*>', page.body)
    if form is None:
        raise DemoFailed(f"không mở được trang sửa {page_id}" + (" — không có quyền" if DENIED in page.body else ""))
    action = re.search(r'\baction="([^"]*)"', form.group(0))
    fields = {}
    for tag in re.findall(r"<input\b[^>]*>", page.body[form.end():page.body.index("</form>", form.end())]):
        name, value = re.search(r'\bname="([^"]*)"', tag), re.search(r'\bvalue="([^"]*)"', tag)
        if name and re.search(r'\btype="hidden"', tag):
            fields[html.unescape(name.group(1))] = html.unescape(value.group(1)) if value else ""
    if "sectok" not in fields:
        raise DemoFailed(f"trang sửa {page_id} không có sectok")
    target = urllib.parse.urljoin(page.url, html.unescape(action.group(1)) if action else page.url)
    return open_page(browser, target, {**fields, "wikitext": text, "summary": summary, "do[save]": "1"})


def units() -> dict[str, str]:
    """Mã đơn vị → không gian, theo `moc wiki sync` (chạy lại cũng không đổi gì nếu đơn vị không đổi)."""
    result = wiki.sync(ENV)
    missing = [code for code in ("CNTT", "KT") if code not in result["namespaces"]]
    if missing:
        raise DemoFailed(f"chưa có đơn vị {', '.join(missing)} — chạy make seed trước")
    return result["namespaces"]


def wiki_users() -> dict[str, list[str]]:
    """Tài khoản trong conf/users.auth.php của wiki → nhóm (không đọc ra mật khẩu băm)."""
    out = subprocess.run(["docker", "compose", "--profile", "core", "--profile", "app", "--profile", "wiki", "exec",
                          "-T", "wiki", "cat", "/storage/conf/users.auth.php"],
                         cwd=ROOT, check=True, capture_output=True).stdout.decode()
    users = {}
    for line in out.splitlines():
        if line and not line.startswith("#"):
            fields = line.split(":")
            users[fields[0]] = fields[4].split(",") if len(fields) > 4 else []
    return users


def in_index(browser: Browser, page_id: str) -> bool:
    """Trang có trong sơ đồ trang (?do=index) mở tới không gian của nó không."""
    ns = page_id.rsplit(":", 1)[0]
    page = open_page(browser, f"{WIKI}start?do=index&idx={urllib.parse.quote(ns, safe='')}")
    return f"{wiki.BASE}{page_id}\"" in page.body


def run() -> None:
    print("Wiki nội bộ — DokuWiki dưới /wiki/, đăng nhập Keycloak, mỗi đơn vị một không gian riêng (#367)")
    tag = uuid.uuid4().hex[:6].upper()

    say(1, f"Wiki chạy sau cổng APISIX: {WIKI}health.php; client Keycloak `wiki`, quyền theo đơn vị (moc wiki sync)")
    try:
        status, _, body = request("GET", f"{WIKI}health.php")
    except HTTPError as exc:                     # wiki chưa bật: APISIX không phân giải được upstream, trả 503
        raise DemoFailed(f"/wiki/health.php trả {exc.status} — chạy make wiki-up trước") from None
    if status != 200 or body.decode().strip() != "ok":
        raise DemoFailed(f"/wiki/health.php trả {status} {body[:80]!r} — chạy make wiki-up trước")
    ns = units()
    cntt, kt = ns["CNTT"], ns["KT"]
    ok(f"health.php: ok; không gian Khoa CNTT {cntt}, Khoa Kinh tế {kt}")

    say(2, f"{WRITER} (giảng viên Khoa CNTT) đăng nhập wiki: chuyển sang Keycloak, quay về đã đăng nhập")
    writer = login(WRITER)
    groups = wiki_users().get(WRITER, [])
    if TENANT_CNTT not in groups:
        raise DemoFailed(f"tài khoản wiki {WRITER} không có nhóm đơn vị {TENANT_CNTT}: {groups}")
    ok(f"tài khoản wiki {WRITER} tạo từ dữ liệu Keycloak, nhóm: {', '.join(groups)} — wiki không có biểu mẫu đăng "
       "ký, đăng nhập bằng mật khẩu")

    say(3, f"{WRITER} viết trang {cntt}:{PAGE} trong không gian của đơn vị mình")
    text = f"====== Sổ tay nội bộ ======\n\n{MARKER}, lần {tag}.\n"
    page = save(writer, f"{cntt}:{PAGE}", text, f"demo wiki {tag}")
    if MARKER not in page.body or tag not in page.body:
        raise DemoFailed(f"sau khi lưu, trang {cntt}:{PAGE} không có nội dung vừa viết ({page.path})")
    ok(f"đã lưu, mở lại thấy đúng nội dung (lần {tag})")

    say(4, f"{CLERK} (văn thư Khoa Kinh tế, mật khẩu + TOTP) đăng nhập; không đọc, không sửa được trang của Khoa CNTT")
    clerk = login(CLERK)
    for action in ("", "?do=edit"):
        seen = open_page(clerk, f"{WIKI}{cntt}:{PAGE}{action}")
        if MARKER in seen.body or tag in seen.body or DENIED not in seen.body or 'id="dw__editform"' in seen.body:
            raise DemoFailed(f"{CLERK} mở {cntt}:{PAGE}{action} mà không bị từ chối")
    if in_index(clerk, f"{cntt}:{PAGE}") or not in_index(writer, f"{cntt}:{PAGE}"):
        raise DemoFailed(f"sơ đồ trang: {CLERK} thấy, hoặc {WRITER} không thấy {cntt}:{PAGE}")
    ok(f"xem, sửa trang của Khoa CNTT: \"{DENIED}\"; sơ đồ trang của {CLERK} không liệt kê trang đó")
    save(clerk, f"{kt}:{PAGE}", f"====== Sổ tay Khoa Kinh tế ======\n\nGhi chú lần {tag}.\n", f"demo wiki {tag}")
    seen = open_page(writer, f"{WIKI}{kt}:{PAGE}")
    if tag in seen.body or DENIED not in seen.body:
        raise DemoFailed(f"{WRITER} đọc được {kt}:{PAGE} của Khoa Kinh tế")
    ok(f"{CLERK} viết được trong {kt}; chiều ngược lại {WRITER} cũng bị từ chối ở trang đó")

    say(5, "Người chưa đăng nhập mở trang đó: bị đưa sang trang đăng nhập Keycloak, không thấy nội dung")
    anon = open_page(Browser(), f"{WIKI}{cntt}:{PAGE}")
    if not anon.path.startswith(f"/realms/{REALM}/") or MARKER in anon.body or tag in anon.body:
        raise DemoFailed(f"khách chưa đăng nhập dừng ở {anon.path}")
    ok(f"dừng ở {anon.path} (trang đăng nhập)")
    print(f"\nĐẠT — trang mẫu: {WIKI}{cntt}:{PAGE} (đăng nhập bằng {WRITER})")


def after_restore() -> None:
    print("Wiki nội bộ sau khi khôi phục bản sao lưu (#367): trang viết trước lúc sao lưu còn nguyên")
    cntt = units()["CNTT"]
    page = open_page(login(WRITER), f"{WIKI}{cntt}:{PAGE}")
    if MARKER not in page.body:
        raise DemoFailed(f"{cntt}:{PAGE} không còn nội dung viết trước lúc sao lưu")
    ok(f"{WRITER} đăng nhập lại, đọc được {cntt}:{PAGE}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sau-khoi-phuc", action="store_true", help="chỉ kiểm trang của lần chạy trước còn đó")
    args = parser.parse_args(argv)
    try:
        after_restore() if args.sau_khoi_phuc else run()
    except (DemoFailed, wiki.tenants.TenantError, wiki.tenants.Unavailable, subprocess.CalledProcessError,
            urllib.error.URLError) as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
