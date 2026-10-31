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

"""Sinh sơ đồ kiến trúc tổng thể của Signet cho README: SVG có chuyển động và GIF lặp khép kín.

Yêu cầu đi từ trái sang phải: người dùng → cổng APISIX → dịch vụ → dữ liệu; ngoài cùng bên phải là các kênh bên ngoài
mà svc-workflow gửi thông báo tới (tùy chọn). Trên xuống là ba tầng của đề DX-OS: Tầng 3 (ứng dụng ngành, chưa làm, nét
đứt), Tầng 2 là bốn không gian năng lực số H → P → D → I liệt kê màn hình, ứng dụng theo bảng Tầng 2 của README, Tầng 1
là lõi không giao diện. Đường nối chạy nét theo chiều dữ liệu, hai chấm sáng đi theo hai yêu cầu thật (văn bản vào quy
trình BPMN; tệp qua kiểm dịch). Màu theo không gian H-P-D-I, viền đậm là mã của đội, logo đặt trên phần mềm nguồn mở
dùng nguyên bản (docs/anh/logo/, nguồn ở NGUON.md).

    python3 scripts/so_do_kien_truc.py svg [vi|en]    SVG có chuyển động ra stdout
    python3 scripts/so_do_kien_truc.py gif            docs/anh/kien-truc-tong-the.gif và kien-truc-tong-the.en.gif

GIF: sinh từng khung SVG tĩnh, chụp bằng Chromium không giao diện, ghép bằng FFmpeg với một bảng màu chung cho mọi
khung (màu không nhấp nháy) và không khử răng cưa bằng nhiễu (nét và chữ giữ sắc). Cần chromium (hoặc
chromium-browser, google-chrome) và ffmpeg trong PATH; chỉ dùng khi sửa sơ đồ, không thuộc sản phẩm.
"""

from __future__ import annotations

import base64
import pathlib
import queue
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[1]
THU_MUC_LOGO = ROOT / "docs" / "anh" / "logo"

# Bố cục dọc: dải Tầng 3, nền Tầng 2 (dải Văn phòng điện tử rồi bốn cột H-P-D-I), bảy hàng hộp Tầng 1.
T3Y, T3H = 58, 26  # dải nét đứt Tầng 3
P2Y = 96  # mép trên nền Tầng 2
BAND_Y, BAND_H = P2Y + 36, 30  # dải Văn phòng điện tử vắt ngang bốn cột
COL_Y, COL_H = BAND_Y + BAND_H + 14, 136  # bốn cột H-P-D-I
P2_BOT = COL_Y + COL_H + 42  # nền Tầng 2 kết thúc sau hai dòng chú thích
T1Y = P2_BOT + 44  # hàng đầu Tầng 1; nhãn tầng ở trên 16
# ROW[3]…ROW[9] là bảy hàng Tầng 1; ba chỉ số đầu không dùng, giữ số cũ để toạ độ đường nối, chấm sáng không đổi
ROW = [T1Y + (i - 3) * 88 for i in range(10)]
MID = [y + 29 for y in ROW]
UY = (ROW[3] - 28, ROW[3] + 132)  # hai hộp người dùng, ngang Tầng 1
W, H = 1500, ROW[9] + 162  # cột 1280–1480: kênh thông báo bên ngoài
NET, XUNG = 0.8, 6.4  # chu kỳ chạy nét và chu kỳ chấm sáng (giây); 6,4 = 8 vòng nét nên GIF lặp khép kín
BUOC = 0.08  # 8/100 giây một khung (GIF đếm thời gian theo 1/100 giây): 10 khung một vòng nét, 80 khung cả GIF
SO_KHUNG = round(XUNG / BUOC)

T = {
    "vi": dict(
        users="Người dùng", net="Mạng nội bộ Docker", t3="TẦNG 3 · ỨNG DỤNG NGÀNH — ĐỀ KHÔNG BẮT BUỘC, CHƯA LÀM",
        t2="TẦNG 2 · KHÔNG GIAN NĂNG LỰC SỐ H → P → D → I", t1="TẦNG 1 · LÕI KHÔNG GIAO DIỆN",
        band=("Văn phòng điện tử", "app-office · Nuxt 4 · màn hình ở cả bốn không gian"),
        cols=[("id", "[H] Con người", ["Không gian cá nhân P.A.R.A", "Bảng tin đơn vị ⊕", "trang Ứng dụng",
                                        "DokuWiki (tùy chọn)"]),
              ("proc", "[P] Quy trình", ["tiếp nhận, văn bản đến", "văn bản đi, sổ đăng ký", "hộp việc, Lịch hạn",
                                          "Đơn nghỉ phép ⊕", "Dựng form (quản trị)"]),
              ("data", "[D] Dữ liệu", ["Điều hành, Số đo", "Phả hệ số liệu", "Sơ đồ cảm biến", "Sổ kiểm toán",
                                        "Hồ sơ, kho lạnh, phòng đọc", "Nguồn công khai (Trạng thái)",
                                        "Tài liệu API · Swagger UI"]),
              ("ai", "[I] Trí tuệ", ["Tìm kiếm toàn văn", "Hỏi đáp (từ khóa, nghĩa)", "gợi ý ô khi tiếp nhận",
                                     "gợi ý giao việc"])],
        note=["⊕ cắm bằng manifest (moc app install), không sửa tệp nào của lõi; Không gian cá nhân là ứng dụng riêng, "
              "thêm tay vào cấu hình lõi;", "các màn còn lại thuộc Văn phòng điện tử, trừ Tài liệu API "
              "(app-tai-lieu-api) và DokuWiki (profile wiki); mạng apps chỉ tới được cổng"],
        u1=("Trình duyệt", ["văn thư, lãnh đạo,", "chuyên viên, quản trị"]),
        u2=("Người nhận văn bản", ["kiểm văn bản qua QR,", "không cần đăng nhập"]),
        net_in=["qua Internet, hoặc", "Cloudflare Tunnel (tùy chọn)"],
        gw=("Cổng API", "Apache APISIX", ["cổng duy nhất", "mở ra ngoài", "", "kiểm JWT ở biên", "gắn X-Request-Id",
                                         "giới hạn tốc độ", "tường lửa Coraza", "chặn đường quản trị"]),
        tudong=("Node-RED (tùy chọn)", "kịch bản tự động gọi API"),
        kc=("Keycloak", "đăng nhập một lần, TOTP"), cf=("Centrifugo", "thông báo tức thời"),
        hasura=("Hasura", "GraphQL, quyền từng dòng"), files=("svc-files", "tệp, tìm kiếm, PDF, AI"),
        mon=("Prometheus + Grafana", "giám sát mọi thành phần"), am=("Alertmanager", "cảnh báo tới chuông quản trị"),
        wf=("svc-workflow", "Actions, nhắc hạn"),
        pg=("PostgreSQL", "sổ kiểm toán chuỗi băm"), clam=("ClamAV", "quét mã độc"),
        sw=("SeaweedFS", "kho tệp S3, nộp lưu"), flow=("Flowable", "quy trình BPMN"),
        bao=("OpenBao", "két bí mật, khóa ký"), meili=("Meilisearch", "tìm toàn văn"),
        ollama=("Ollama (tùy chọn)", "mô hình ngôn ngữ cục bộ"),
        scorpio=("Scorpio (tùy chọn)", "NGSI-LD, cảm biến IoT"),
        jaeger=("Jaeger (tùy chọn)", "truy vết cổng → dịch vụ"),
        logs=("Vector + Parseable", "log tập trung (tùy chọn)"), restic=("restic", "sao lưu CSDL và kho tệp"),
        ext="Ngoài hệ thống (tùy chọn)", mail=("Email, webhook chat", "SMTP · Mattermost, Slack, ntfy"),
        sms=("SMS", "điện thoại Android cùng LAN"), zalo=("Zalo", "một bot cho cả bản cài"),
        ext_note=["người dùng tự bật", "SMS, Zalo cho mình"],
        l_metrics="chỉ số", l_alert="cảnh báo", l_sql="SQL", l_actions="Actions", l_push="đẩy thông báo", l_bpmn="BPMN",
        l_secret="bí mật",
        l_meta="siêu dữ liệu", l_scan="kiểm dịch", l_store="lưu tệp", l_index="chỉ mục", l_keys="khóa, bí mật",
        l_span="span", l_ngsi="NGSI-LD", l_notify="gửi thông báo",
        legend=[("app", "Ứng dụng"), ("id", "Định danh [H]"), ("proc", "Quy trình [P]"), ("data", "Dữ liệu [D]"),
                ("ai", "AI [I]"), ("trust", "Tin cậy"), ("ops", "Vận hành")],
        bold="Viền đậm: mã của đội · viền mảnh có logo: phần mềm nguồn mở dùng nguyên bản",
        pulse="Chấm sáng: một yêu cầu đi qua hệ thống", credit="Logo thuộc về từng dự án",
        title="Signet — kiến trúc tổng thể",
    ),
    "en": dict(
        users="Users", net="Internal Docker network",
        t3="TIER 3 · INDUSTRY APPLICATIONS — OPTIONAL IN THE BRIEF, NOT BUILT",
        t2="TIER 2 · DIGITAL CAPABILITY SPACES H → P → D → I", t1="TIER 1 · HEADLESS CORE",
        band=("e-Office", "app-office · Nuxt 4 · screens in all four spaces"),
        cols=[("id", "[H] Human", ["P.A.R.A personal space", "Unit news board ⊕", "Apps page", "DokuWiki (optional)"]),
              ("proc", "[P] Process", ["intake, incoming documents", "outgoing documents, registers",
                                       "task inbox, due calendar", "Leave requests ⊕", "Form builder (admins)"]),
              ("data", "[D] Data", ["Dashboard, metrics", "Data lineage", "Sensor map", "Audit log",
                                    "Case files, cold storage", "Public data sources (Status)",
                                    "API docs · Swagger UI"]),
              ("ai", "[I] Intelligence", ["Full-text search", "Q&A (keyword, semantic)", "Intake field suggestions",
                                          "Assignment suggestions"])],
        note=["⊕ plugged in by manifest (moc app install), no core file changed; the personal space is its own app, "
              "added by hand to the core configuration;", "the other screens belong to the e-Office, except API docs "
              "(app-tai-lieu-api) and DokuWiki (wiki profile); the apps network reaches only the gateway"],
        u1=("Browser", ["clerks, managers,", "staff, administrators"]),
        u2=("Document recipients", ["verify a document by QR,", "no sign-in needed"]),
        net_in=["over the Internet, or a", "Cloudflare Tunnel (optional)"],
        gw=("API gateway", "Apache APISIX", ["the only entry point", "exposed outside", "", "JWT checked at the edge",
                                            "adds X-Request-Id", "rate limiting", "Coraza firewall",
                                            "blocks admin paths"]),
        tudong=("Node-RED (optional)", "automation flows calling the API"),
        kc=("Keycloak", "single sign-on, TOTP"), cf=("Centrifugo", "real-time notifications"),
        hasura=("Hasura", "GraphQL, row-level access"), files=("svc-files", "files, search, PDF, AI"),
        mon=("Prometheus + Grafana", "monitors every component"), am=("Alertmanager", "alerts to the admins' bell"),
        wf=("svc-workflow", "Actions, deadlines"),
        pg=("PostgreSQL", "hash-chained audit log"), clam=("ClamAV", "malware scanning"),
        sw=("SeaweedFS", "S3 file store, archive"), flow=("Flowable", "BPMN workflows"),
        bao=("OpenBao", "secrets vault, signing keys"), meili=("Meilisearch", "full-text search"),
        ollama=("Ollama (optional)", "local language model"),
        scorpio=("Scorpio (optional)", "NGSI-LD, IoT sensors"),
        jaeger=("Jaeger (optional)", "gateway → service tracing"),
        logs=("Vector + Parseable", "central logs (optional)"), restic=("restic", "database and file backup"),
        ext="Outside services (optional)", mail=("Email, chat webhooks", "SMTP · Mattermost, Slack, ntfy"),
        sms=("SMS", "Android phone on the LAN"), zalo=("Zalo", "one bot for the whole install"),
        ext_note=["each user opts in", "to SMS and Zalo"],
        l_metrics="metrics", l_alert="alerts", l_sql="SQL", l_actions="Actions", l_push="push", l_bpmn="BPMN",
        l_secret="secrets",
        l_meta="metadata", l_scan="scan", l_store="store", l_index="index", l_keys="keys, secrets",
        l_span="spans", l_ngsi="NGSI-LD", l_notify="notifications",
        legend=[("app", "Applications"), ("id", "Identity [H]"), ("proc", "Process [P]"), ("data", "Data [D]"),
                ("ai", "AI [I]"), ("trust", "Trust"), ("ops", "Operations")],
        bold="Thick border: written by the team · thin border with logo: upstream open source used as is",
        pulse="Moving dot: one request travelling through the system", credit="Logos belong to their projects",
        title="Signet — architecture overview",
    ),
}

C = {  # màu nền, màu viền theo vai trò (bảng màu của draw.io)
    "user": ("#ffffff", "#8c959f"), "gw": ("#e3f4f0", "#3d8b7d"), "app": ("#dae8fc", "#6c8ebf"),
    "id": ("#e1d5e7", "#9673a6"), "proc": ("#ffe6cc", "#d79b00"), "data": ("#fff2cc", "#d6b656"),
    "ai": ("#d5e8d4", "#82b366"), "trust": ("#f8cecc", "#b85450"), "ops": ("#f5f5f5", "#8c959f"),
}

# logo trên từng hộp phần mềm nguồn mở; hộp mã của đội không có logo. Kênh ngoài chỉ gắn logo dự án nguồn mở (ntfy,
# SMS Gateway for Android); Slack, Zalo là dịch vụ đóng, nhãn hiệu Mattermost phải xin phép trước nên chỉ ghi tên
# Alertmanager là một phần của dự án Prometheus nên mang logo Prometheus; DokuWiki nằm trong cột [H], không có hộp riêng
LOGO = dict(gw=["apisix", "coraza"], kc=["keycloak"], cf=["centrifugo"], hasura=["hasura"],
            mon=["prometheus", "grafana"], am=["prometheus"], jaeger=["jaeger"], pg=["postgresql"], clam=["clamav"],
            sw=["seaweedfs"], logs=["vector", "parseable"], scorpio=["scorpio"], flow=["flowable"], bao=["openbao"],
            meili=["meilisearch"], ollama=["ollama"], restic=["restic"], mail=["ntfy"],
            sms=["sms-gateway"], tudong=["node-red"])

# hai yêu cầu có chấm sáng: (màu, đường đi chỉ gồm M/H/V, lệch pha so với chấm đầu)
XUNG_SANG = [
    # văn bản: trình duyệt → cổng → Hasura → svc-workflow → Flowable
    ("#d79b00", f"M210,{UY[0] + 37} H345 V{MID[5]} H740 V{ROW[4] + 44} H865 V{MID[4]} H1115", 0.0),
    # tệp: trình duyệt → cổng → svc-files → ClamAV
    ("#b85450", f"M210,{UY[0] + 37} H345 V{MID[6]} H865", XUNG / 2),
]


def vi_tri(path: str, p: float) -> tuple[float, float]:
    """Toạ độ tại tỉ lệ p (0..1) độ dài đường gấp khúc M/H/V, đi đều như animateMotion (calcMode paced)."""
    pts: list[tuple[float, float]] = []
    for tok in path.split():
        if tok[0] == "M":
            x, y = tok[1:].split(",")
            pts.append((float(x), float(y)))
        elif tok[0] == "H":
            pts.append((float(tok[1:]), pts[-1][1]))
        else:
            pts.append((pts[-1][0], float(tok[1:])))
    seg = [abs(x1 - x0) + abs(y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:])]
    con = p * sum(seg)
    for (x0, y0), (x1, y1), d in zip(pts, pts[1:], seg):
        if con <= d:
            return x0 + (x1 - x0) * con / d, y0 + (y1 - y0) * con / d
        con -= d
    return pts[-1]


def do_mo(p: float, vals=(0, 1, 1, 0), keys=(0, 0.05, 0.9, 1)) -> float:
    """Độ mờ của chấm sáng tại tỉ lệ p, nội suy tuyến tính như animate values/keyTimes."""
    for k0, k1, v0, v1 in zip(keys, keys[1:], vals, vals[1:]):
        if p <= k1:
            return v0 + (v1 - v0) * (p - k0) / (k1 - k0)
    return vals[-1]


def pha(t: float, chu_ky: float) -> float:
    """Phần lẻ của t / chu_ky trong [0, 1); làm tròn để khung cuối và khung đầu của vòng lặp ra cùng một ảnh."""
    return round(t / chu_ky, 9) % 1


def ve(lang: str = "vi", khung: float | None = None) -> str:
    """SVG của sơ đồ. khung=None: có chuyển động (CSS + SMIL); khung=t giây: ảnh tĩnh tại thời điểm t, để ghép GIF."""
    tx = T[lang]
    out: list[str] = []
    a = out.append

    def text(x, y, s, size=11, weight=400, fill="#24292f", anchor="middle", extra=""):
        a(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"'
          f'{extra}>{escape(s)}</text>')

    def huy_hieu(x, y, names, stroke):
        # huy hiệu tròn ngồi trên mép trên, góc phải hộp; nhiều logo thì xếp chồng sang trái
        for i, n in reversed(list(enumerate(names))):
            cx = x - 18 - i * 18
            b64 = base64.b64encode((THU_MUC_LOGO / f"{n}.png").read_bytes()).decode()
            a(f'<circle cx="{cx}" cy="{y}" r="12" fill="#ffffff" stroke="{stroke}"/>')
            a(f'<image x="{cx - 11}" y="{y - 11}" width="22" height="22" clip-path="url(#tron)" '
              f'href="data:image/png;base64,{b64}"><title>{n}</title></image>')

    def box(x, y, w, h, kind, title, sub, team=False, logo=()):
        f, s = C[kind]
        a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{f}" stroke="{s}" '
          f'stroke-width="{2.2 if team else 1}"/>')
        text(x + w / 2, y + h / 2 - 3, title, 12.5, 600)
        text(x + w / 2, y + h / 2 + 14, sub, 10.5, 400, "#57606a")
        if logo:
            huy_hieu(x + w, y, logo, s)

    def edge(pts, label=None, lx=None, ly=None, anchor="middle", mono=False):
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        a(f'<path class="flow" d="{d}" fill="none" stroke="#57606a" stroke-width="1.3" marker-end="url(#mui)"/>')
        if label:
            font = ' font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"' if mono else ""
            text(lx, ly, label, 10, 400, "#57606a", anchor, font)

    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'font-family="Segoe UI, Roboto, Helvetica Neue, Arial, Noto Sans, sans-serif" role="img">')
    a(f"<title>{escape(tx['title'])}</title>")
    a('<defs>\n<marker id="mui" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
      'orient="auto-start-reverse">\n<path d="M0,0 L10,5 L0,10 z" fill="#57606a"/></marker>\n'
      '<clipPath id="tron" clipPathUnits="objectBoundingBox"><circle cx=".5" cy=".5" r=".5"/></clipPath>\n<style>')
    if khung is None:
        a(f".flow{{stroke-dasharray:6 4;animation:chay {NET}s linear infinite}}\n"
          "@keyframes chay{to{stroke-dashoffset:-10}}\n"
          "@media (prefers-reduced-motion:reduce){.flow{animation:none}.xung{display:none}}")
    else:
        a(f".flow{{stroke-dasharray:6 4;stroke-dashoffset:{-10 * pha(khung, NET):.3f}}}")
    a("</style>\n</defs>")
    a(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="#ffffff" stroke="#d0d7de"/>')

    R, M = ROW, MID
    x2, x3, x4, bw, bh = 530, 780, 1030, 170, 58  # cột 2 là lối vào từ cổng; cột 3, 4 là dịch vụ, dữ liệu phía sau

    # vùng: người dùng ở ngoài, mạng nội bộ chứa hai tầng
    a(f'<rect x="20" y="{R[3] - 68}" width="210" height="340" rx="24" fill="none" stroke="#8c959f" '
      'stroke-dasharray="4 4"/>')
    text(36, R[3] - 46, tx["users"], 11.5, 400, "#57606a", "start")
    for i, s in enumerate(tx["net_in"]):
        text(125, R[3] + 236 + i * 15, s, 10.5, 400, "#57606a", extra=' font-style="italic"')
    a(f'<rect x="460" y="22" width="800" height="{R[9] + bh + 18 - 22}" rx="32" fill="none" stroke="#8c959f" '
      'stroke-dasharray="4 4"/>')
    text(484, 44, tx["net"], 11.5, 400, "#57606a", "start")
    # Tầng 3: chưa có gì, chỉ một dải nét đứt
    a(f'<rect x="472" y="{T3Y}" width="776" height="{T3H}" rx="10" fill="none" stroke="#8c959f" '
      'stroke-dasharray="4 4"/>')
    text(860, T3Y + 17, tx["t3"], 10.5, 600, "#8c959f", extra=' letter-spacing="0.6"')
    # Tầng 2: nền, nhãn, dải Văn phòng điện tử, bốn cột H-P-D-I, hai dòng chú thích
    a(f'<rect x="472" y="{P2Y}" width="776" height="{P2_BOT - P2Y}" rx="18" fill="#f6f9ff"/>')
    text(1236, P2Y + 22, tx["t2"], 10.5, 600, "#6c8ebf", "end", ' letter-spacing="0.6"')
    f, s = C["app"]
    a(f'<rect x="{x2}" y="{BAND_Y}" width="{x4 + bw - x2}" height="{BAND_H}" rx="8" fill="{f}" stroke="{s}" '
      'stroke-width="2.2"/>')
    text((x2 + x4 + bw) / 2 - 4, BAND_Y + 19, tx["band"][0], 12.5, 600, anchor="end")
    text((x2 + x4 + bw) / 2 + 4, BAND_Y + 19, tx["band"][1], 10.5, 400, "#57606a", "start")
    cw, cg = 154, (x4 + bw - x2 - 4 * 154) / 3  # bốn cột chia đều bề rộng từ cột 2 tới hết cột 4
    for i, (kind, head, items) in enumerate(tx["cols"]):
        cx = x2 + i * (cw + cg)
        f, s = C[kind]
        a(f'<rect x="{cx:.0f}" y="{COL_Y}" width="{cw}" height="{COL_H}" rx="8" fill="{f}" stroke="{s}"/>')
        text(cx + cw / 2, COL_Y + 18, head, 11.5, 600)
        for j, item in enumerate(items):
            text(cx + 10, COL_Y + 37 + j * 14, item, 10, 400, "#24292f", "start")
    for i, s in enumerate(tx["note"]):
        text(1236, COL_Y + COL_H + 16 + i * 14, s, 10, 400, "#57606a", "end", ' font-style="italic"')
    text(1236, R[3] - 16, tx["t1"], 10.5, 600, "#8c959f", "end", ' letter-spacing="0.6"')
    # kênh bên ngoài, ngang hàng Scorpio, Flowable, OpenBao: svc-workflow gọi ra, không có gì gọi vào
    # nhãn khung nằm trên huy hiệu logo của hộp đầu (huy hiệu nhô 12 lên trên mép hộp)
    a(f'<rect x="1280" y="{R[3] - 44}" width="200" height="328" rx="24" fill="none" stroke="#8c959f" '
      'stroke-dasharray="4 4"/>')
    text(1296, R[3] - 22, tx["ext"], 11.5, 400, "#57606a", "start")
    for i, s in enumerate(tx["ext_note"]):
        text(1380, R[3] + 256 + i * 15, s, 10.5, 400, "#57606a", extra=' font-style="italic"')

    # đường nối vẽ trước, nằm dưới hộp; nhãn từ cổng là đường dẫn thật trong cấu hình APISIX
    for y in UY:
        edge([(210, y + 37), (270, y + 37)])
    # Tầng 2: một lối vào dải Văn phòng điện tử ("/"), một lối vào các cột cho ba ứng dụng kia và ứng dụng cắm thêm
    # (route thêm lúc cài); nhãn là đường dẫn thật, xếp dọc phía trên
    edge([(420, BAND_Y + BAND_H / 2), (x2, BAND_Y + BAND_H / 2)], "/", 475, BAND_Y + BAND_H / 2 - 6, mono=True)
    y_apps = COL_Y + 62
    edge([(420, y_apps), (x2, y_apps)])
    for i, r in enumerate(("/ca-nhan/", "/tai-lieu-api/", "/bang-tin/ …", "/wiki/")):
        text(475, y_apps - 6 - (3 - i) * 12, r, 10, 400, "#57606a",
             extra=' font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"')
    # Tầng 1: mỗi hàng của cột 2 một đường dẫn; quy trình của ứng dụng cắm thêm tới thẳng svc-workflow, đi giữa hai hàng
    routes = [tx["l_metrics"], "/realtime", "/v1/graphql", "/api/…", "/realms/moc", tx["l_span"], "/tu-dong/"]
    for i, r in zip(range(3, 10), routes):
        edge([(420, M[i]), (x2, M[i])], r, 475, M[i] - 6, mono=r.startswith("/"))
    edge([(420, R[4] - 15), (800, R[4] - 15), (800, R[4])], "/api/workflow/", 475, R[4] - 21, mono=True)
    # Prometheus → Alertmanager → svc-workflow (/ops/alerts, mạng alerts) → chuông của quản trị đơn vị
    edge([(700, M[3]), (x3, M[3])], tx["l_alert"], 740, M[3] - 6)
    edge([(830, R[3] + bh), (830, R[4])], "/ops/alerts", 838, R[4] - 9, "start", mono=True)
    edge([(950, R[4] + 8), (990, R[4] + 8), (990, M[3]), (x4, M[3])], tx["l_ngsi"], 1010, M[3] - 6)
    edge([(700, M[5]), (780, M[5])], tx["l_sql"], 740, M[5] - 6)
    edge([(700, M[5] - 16), (740, M[5] - 16), (740, R[4] + 44), (780, R[4] + 44)], tx["l_actions"], 746, R[5] - 12,
         "start")
    edge([(780, R[4] + 21), (700, R[4] + 21)], tx["l_push"], 740, R[4] + 15)
    edge([(950, M[4]), (1030, M[4])], tx["l_bpmn"], 990, M[4] - 6)
    edge([(950, R[4] + 46), (990, R[4] + 46), (990, R[5] + 16), (1030, R[5] + 16)], tx["l_secret"], 996, R[5] - 8,
         "start")
    edge([(615, R[6]), (615, R[5] + bh)], tx["l_meta"], 622, R[6] - 11, "start")
    edge([(700, M[6]), (780, M[6])], tx["l_scan"], 740, M[6] - 6)
    edge([(700, R[6] + 43), (740, R[6] + 43), (740, M[7]), (780, M[7])], tx["l_store"], 746, R[7] - 4, "start")
    nhanh = [(700, R[6] + 51), (755, R[6] + 51), (755, R[6] + 73), (1005, R[6] + 73)]
    edge([*nhanh, (1005, M[6]), (1030, M[6])], tx["l_index"], 998, R[6] + 48, "end")
    edge([*nhanh, (1005, M[7]), (1030, M[7])])
    edge([(700, R[6] + 12), (765, R[6] + 12), (765, R[6] - 15), (1015, R[6] - 15), (1015, R[5] + 43),
          (1030, R[5] + 43)], tx["l_keys"], 890, R[6] - 19)
    # thông báo ra ngoài: từ đỉnh svc-workflow, qua khe giữa hàng Scorpio và Flowable, rẽ tới từng kênh
    for k in (3, 4, 5):
        edge([(935, R[4]), (935, R[3] + bh + 7), (1275, R[3] + bh + 7), (1275, M[k]), (1295, M[k])])
    text(1100, R[3] + bh + 23, tx["l_notify"], 10, 400, "#57606a")

    # chấm sáng đi theo luồng, vẽ dưới hộp: vào hộp thì khuất, ra hộp thì hiện
    for color, path, begin in XUNG_SANG:
        if khung is None:
            a(f'<circle class="xung" r="4.5" fill="{color}" stroke="#ffffff" stroke-width="1.5" opacity="0">'
              f'<animateMotion dur="{XUNG}s" begin="{begin}s" repeatCount="indefinite" path="{path}"/>'
              f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.05;0.9;1" dur="{XUNG}s" '
              f'begin="{begin}s" repeatCount="indefinite"/></circle>')
        else:
            p = pha(khung - begin, XUNG)  # trạng thái ổn định: chấm thứ hai đã chạy từ vòng trước
            x, y = vi_tri(path, p)
            a(f'<circle r="4.5" cx="{x:.1f}" cy="{y:.1f}" fill="{color}" stroke="#ffffff" stroke-width="1.5" '
              f'opacity="{do_mo(p):.2f}"/>')

    # hộp
    for key, y in zip(("u1", "u2"), UY):
        t, sub = tx[key]
        a(f'<rect x="40" y="{y}" width="170" height="74" rx="8" fill="#ffffff" stroke="#8c959f"/>')
        text(125, y + 24, t, 12.5, 600)
        for i, s in enumerate(sub):
            text(125, y + 44 + i * 15, s, 10.5, 400, "#57606a")
    f, s = C["gw"]
    a(f'<rect x="270" y="50" width="150" height="{R[9] + bh - 50}" rx="12" fill="{f}" stroke="{s}" '
      'stroke-width="1.2"/>')
    gt, gs, gl = tx["gw"]
    gy = (50 + R[9] + bh) / 2 - 72  # khối chữ giữa cổng
    text(345, gy, gt, 14, 600)
    text(345, gy + 18, gs, 11, 400, "#3d8b7d")
    for i, s in enumerate(gl):
        if s:
            text(345, gy + 46 + i * 16, s, 10.5, 400, "#57606a")
    huy_hieu(420, 50, LOGO["gw"], C["gw"][1])
    col2 = [("mon", "ops", False), ("cf", "proc", False), ("hasura", "data", False), ("files", "trust", True),
            ("kc", "id", False), ("jaeger", "ops", False), ("tudong", "ops", False)]
    for i, (k, kind, team) in zip(range(3, 10), col2):
        box(x2, R[i], bw, bh, kind, *tx[k], team=team, logo=LOGO.get(k, ()))
    for x, r, k, kind, team in ((x3, 3, "am", "ops", False),
                                (x3, 4, "wf", "proc", True), (x3, 5, "pg", "data", False),
                                (x3, 6, "clam", "trust", False), (x3, 7, "sw", "data", False),
                                (x3, 8, "logs", "ops", False), (x4, 3, "scorpio", "data", False),
                                (x4, 4, "flow", "proc", False), (x4, 5, "bao", "trust", False),
                                (x4, 6, "meili", "data", False), (x4, 7, "ollama", "ai", False),
                                (x4, 8, "restic", "ops", False)):
        box(x, R[r], bw, bh, kind, *tx[k], team=team, logo=LOGO.get(k, ()))
    for r, k in ((3, "mail"), (4, "sms"), (5, "zalo")):
        box(1295, R[r], bw, bh, "user", *tx[k], logo=LOGO.get(k, ()))

    # chú giải
    ly = R[9] + 95
    lx = 24
    for kind, label in tx["legend"]:
        f, s = C[kind]
        a(f'<rect x="{lx}" y="{ly}" width="16" height="12" rx="3" fill="{f}" stroke="{s}"/>')
        text(lx + 22, ly + 10, label, 11, 400, "#57606a", "start")
        lx += 22 + len(label) * 6.4 + 22
    text(24, ly + 39, tx["bold"], 11, 400, "#57606a", "start")
    a(f'<circle cx="760" cy="{ly + 35}" r="4.5" fill="#d79b00" stroke="#ffffff" stroke-width="1.5"/>')
    text(772, ly + 39, tx["pulse"], 11, 400, "#57606a", "start")
    text(1256, ly + 39, tx["credit"], 10, 400, "#8c959f", "end")
    a("</svg>")
    return "\n".join(out) + "\n"


def tim_lenh(*names: str) -> str:
    for n in names:
        if path := shutil.which(n):
            return path
    sys.exit(f"Thiếu {names[0]} trong PATH (cần để ghép GIF).")


def quay_gif() -> None:
    """Ghép docs/anh/kien-truc-tong-the.gif (tiếng Việt) và .en.gif (tiếng Anh)."""
    trinh_duyet = tim_lenh("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
    ffmpeg = tim_lenh("ffmpeg")
    for lang in ("vi", "en"):
        ra = ROOT / "docs" / "anh" / f"kien-truc-tong-the{'' if lang == 'vi' else '.' + lang}.gif"
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            for i in range(SO_KHUNG):
                (d / f"{i:03d}.svg").write_text(ve(lang, i * BUOC), encoding="utf-8")
            # bốn trình duyệt chạy song song, mỗi cái một hồ sơ riêng (hồ sơ dùng chung thì bị khóa)
            ho_so: queue.Queue[pathlib.Path] = queue.Queue()
            for k in range(4):
                ho_so.put(d / f"ho-so-{k}")

            def chup(i: int) -> None:
                hs = ho_so.get()
                try:
                    subprocess.run([trinh_duyet, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                    "--no-first-run", f"--user-data-dir={hs}", f"--window-size={W},{H}",
                                    f"--screenshot={d / f'{i:03d}.png'}", (d / f"{i:03d}.svg").as_uri()],
                                   check=True, capture_output=True, timeout=120)
                finally:
                    ho_so.put(hs)

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(chup, range(SO_KHUNG)))
            fps = str(1 / BUOC)
            subprocess.run([ffmpeg, "-v", "error", "-y", "-framerate", fps, "-i", str(d / "%03d.png"),
                            "-vf", "palettegen=stats_mode=full", str(d / "bang-mau.png")], check=True)
            subprocess.run([ffmpeg, "-v", "error", "-y", "-framerate", fps, "-i", str(d / "%03d.png"),
                            "-i", str(d / "bang-mau.png"), "-lavfi", "[0][1]paletteuse=dither=none:diff_mode=rectangle",
                            "-loop", "0", str(ra)], check=True)
        print(f"{ra.relative_to(ROOT)}: {ra.stat().st_size // 1024} KB, {SO_KHUNG} khung, {XUNG} giây")


def main(argv: list[str]) -> None:
    if argv[:1] == ["svg"] and argv[1:2] in ([], ["vi"], ["en"]):
        sys.stdout.write(ve(argv[1] if len(argv) > 1 else "vi"))
    elif argv == ["gif"]:
        quay_gif()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
