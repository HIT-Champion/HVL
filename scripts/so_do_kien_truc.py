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

Yêu cầu đi từ trái sang phải: người dùng → cổng APISIX → dịch vụ → dữ liệu. Đường nối chạy nét theo chiều dữ liệu, hai
chấm sáng đi theo hai yêu cầu thật (văn bản vào quy trình BPMN; tệp qua kiểm dịch). Màu theo không gian H-P-D-I, viền
đậm là mã của đội, logo đặt trên phần mềm nguồn mở dùng nguyên bản (docs/anh/logo/, nguồn ở NGUON.md).

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

W, H = 1280, 770
NET, XUNG = 0.8, 6.4  # chu kỳ chạy nét và chu kỳ chấm sáng (giây); 6,4 = 8 vòng nét nên GIF lặp khép kín
BUOC = 0.08  # 8/100 giây một khung (GIF đếm thời gian theo 1/100 giây): 10 khung một vòng nét, 80 khung cả GIF
SO_KHUNG = round(XUNG / BUOC)

T = {
    "vi": dict(
        users="Người dùng", net="Mạng nội bộ Docker", t2="TẦNG 2 · ỨNG DỤNG CÓ GIAO DIỆN",
        t1="TẦNG 1 · LÕI KHÔNG GIAO DIỆN", note=["Ứng dụng mới cắm vào lõi qua cổng,", "không sửa dòng mã nào của lõi"],
        u1=("Trình duyệt", ["văn thư, lãnh đạo,", "chuyên viên, quản trị"]),
        u2=("Người nhận văn bản", ["kiểm văn bản qua QR,", "không cần đăng nhập"]),
        gw=("Cổng API", "Apache APISIX", ["cổng duy nhất", "mở ra ngoài", "", "kiểm JWT ở biên", "gắn X-Request-Id",
                                         "giới hạn tốc độ", "chặn đường quản trị"]),
        office=("Văn phòng điện tử", "app-office · Nuxt 4"), canhan=("Không gian cá nhân", "app-ca-nhan · P.A.R.A"),
        kc=("Keycloak", "đăng nhập một lần, TOTP"), cf=("Centrifugo", "thông báo tức thời"),
        hasura=("Hasura", "GraphQL, quyền từng dòng"), files=("svc-files", "tệp, tìm kiếm, PDF, AI"),
        mon=("Prometheus + Grafana", "giám sát cổng API"), wf=("svc-workflow", "Actions, nhắc hạn"),
        pg=("PostgreSQL", "sổ kiểm toán chuỗi băm"), clam=("ClamAV", "quét mã độc"),
        sw=("SeaweedFS", "kho tệp S3, nộp lưu"), flow=("Flowable", "quy trình BPMN"),
        bao=("OpenBao", "két bí mật, khóa ký"), meili=("Meilisearch", "tìm toàn văn"),
        ollama=("Ollama (tùy chọn)", "mô hình ngôn ngữ cục bộ"),
        l_metrics="chỉ số", l_sql="SQL", l_actions="Actions", l_push="đẩy thông báo", l_bpmn="BPMN", l_secret="bí mật",
        l_meta="siêu dữ liệu", l_scan="kiểm dịch", l_store="lưu tệp", l_index="chỉ mục", l_keys="khóa, bí mật",
        legend=[("app", "Ứng dụng"), ("id", "Định danh [H]"), ("proc", "Quy trình [P]"), ("data", "Dữ liệu [D]"),
                ("ai", "AI [I]"), ("trust", "Tin cậy"), ("ops", "Vận hành")],
        bold="Viền đậm: mã của đội · viền mảnh có logo: phần mềm nguồn mở dùng nguyên bản",
        pulse="Chấm sáng: một yêu cầu đi qua hệ thống", credit="Logo thuộc về từng dự án",
        title="Signet — kiến trúc tổng thể",
    ),
    "en": dict(
        users="Users", net="Internal Docker network", t2="TIER 2 · APPLICATIONS WITH A UI", t1="TIER 1 · HEADLESS CORE",
        note=["New apps plug into the core through the gateway,", "without changing a line of the core"],
        u1=("Browser", ["clerks, managers,", "staff, administrators"]),
        u2=("Document recipients", ["verify a document by QR,", "no sign-in needed"]),
        gw=("API gateway", "Apache APISIX", ["the only entry point", "exposed outside", "", "JWT checked at the edge",
                                            "adds X-Request-Id", "rate limiting", "blocks admin paths"]),
        office=("e-Office", "app-office · Nuxt 4"), canhan=("Personal space", "app-ca-nhan · P.A.R.A"),
        kc=("Keycloak", "single sign-on, TOTP"), cf=("Centrifugo", "real-time notifications"),
        hasura=("Hasura", "GraphQL, row-level access"), files=("svc-files", "files, search, PDF, AI"),
        mon=("Prometheus + Grafana", "API gateway monitoring"), wf=("svc-workflow", "Actions, deadlines"),
        pg=("PostgreSQL", "hash-chained audit log"), clam=("ClamAV", "malware scanning"),
        sw=("SeaweedFS", "S3 file store, archive"), flow=("Flowable", "BPMN workflows"),
        bao=("OpenBao", "secrets vault, signing keys"), meili=("Meilisearch", "full-text search"),
        ollama=("Ollama (optional)", "local language model"),
        l_metrics="metrics", l_sql="SQL", l_actions="Actions", l_push="push", l_bpmn="BPMN", l_secret="secrets",
        l_meta="metadata", l_scan="scan", l_store="store", l_index="index", l_keys="keys, secrets",
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

# logo trên từng hộp phần mềm nguồn mở; hộp mã của đội không có logo
LOGO = dict(gw=["apisix"], kc=["keycloak"], cf=["centrifugo"], hasura=["hasura"], mon=["prometheus", "grafana"],
            pg=["postgresql"], clam=["clamav"], sw=["seaweedfs"], flow=["flowable"], bao=["openbao"],
            meili=["meilisearch"], ollama=["ollama"])

# hai yêu cầu có chấm sáng: (màu, đường đi chỉ gồm M/H/V, lệch pha so với chấm đầu)
XUNG_SANG = [
    # văn bản: trình duyệt → cổng → Hasura → svc-workflow → Flowable
    ("#d79b00", "M210,277 H345 V441 H740 V368 H865 V353 H1115", 0.0),
    # tệp: trình duyệt → cổng → svc-files → ClamAV
    ("#b85450", "M210,277 H345 V529 H865", XUNG / 2),
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

    # vùng: người dùng ở ngoài, mạng nội bộ chứa hai tầng
    a('<rect x="20" y="200" width="210" height="320" rx="24" fill="none" stroke="#8c959f" stroke-dasharray="4 4"/>')
    text(36, 222, tx["users"], 11.5, 400, "#57606a", "start")
    a('<rect x="460" y="22" width="800" height="662" rx="32" fill="none" stroke="#8c959f" stroke-dasharray="4 4"/>')
    text(484, 44, tx["net"], 11.5, 400, "#57606a", "start")
    a('<rect x="472" y="54" width="776" height="164" rx="18" fill="#f6f9ff"/>')
    text(1236, 76, tx["t2"], 10.5, 600, "#6c8ebf", "end", ' letter-spacing="0.6"')
    text(1236, 246, tx["t1"], 10.5, 600, "#8c959f", "end", ' letter-spacing="0.6"')
    for i, s in enumerate(tx["note"]):
        text(1236, 160 + i * 16, s, 11, 400, "#57606a", "end", ' font-style="italic"')

    # hàng của cột 2 (lối vào từ cổng); cột 3, 4 là dịch vụ và dữ liệu phía sau
    row = {i: 60 + i * 88 for i in range(7)}
    mid = {i: row[i] + 29 for i in range(7)}
    x2, x3, x4, bw, bh = 530, 780, 1030, 170, 58

    # đường nối vẽ trước, nằm dưới hộp; nhãn từ cổng là đường dẫn thật trong cấu hình APISIX
    edge([(210, 277), (270, 277)])
    edge([(210, 437), (270, 437)])
    routes = ["/", "/ca-nhan/", "/realms/moc", "/realtime", "/v1/graphql", "/api/…", tx["l_metrics"]]
    for i, r in enumerate(routes):
        edge([(420, mid[i]), (x2, mid[i])], r, 475, mid[i] - 6, mono=r.startswith("/"))
    edge([(700, 441), (780, 441)], tx["l_sql"], 740, 435)
    edge([(700, 425), (740, 425), (740, 368), (780, 368)], tx["l_actions"], 746, 400, "start")
    edge([(780, 345), (700, 345)], tx["l_push"], 740, 339)
    edge([(950, 353), (1030, 353)], tx["l_bpmn"], 990, 347)
    edge([(950, 370), (990, 370), (990, 428), (1030, 428)], tx["l_secret"], 996, 404, "start")
    edge([(615, 500), (615, 470)], tx["l_meta"], 622, 489, "start")
    edge([(700, 529), (780, 529)], tx["l_scan"], 740, 523)
    edge([(700, 543), (740, 543), (740, 617), (780, 617)], tx["l_store"], 746, 584, "start")
    edge([(700, 551), (755, 551), (755, 573), (1005, 573), (1005, 529), (1030, 529)], tx["l_index"], 998, 548, "end")
    edge([(700, 551), (755, 551), (755, 573), (1005, 573), (1005, 617), (1030, 617)])
    edge([(700, 512), (765, 512), (765, 485), (1015, 485), (1015, 455), (1030, 455)], tx["l_keys"], 890, 481)

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
    for key, y in (("u1", 240), ("u2", 400)):
        t, sub = tx[key]
        a(f'<rect x="40" y="{y}" width="170" height="74" rx="8" fill="#ffffff" stroke="#8c959f"/>')
        text(125, y + 24, t, 12.5, 600)
        for i, s in enumerate(sub):
            text(125, y + 44 + i * 15, s, 10.5, 400, "#57606a")
    f, s = C["gw"]
    a(f'<rect x="270" y="50" width="150" height="610" rx="12" fill="{f}" stroke="{s}" stroke-width="1.2"/>')
    gt, gs, gl = tx["gw"]
    text(345, 300, gt, 14, 600)
    text(345, 318, gs, 11, 400, "#3d8b7d")
    for i, s in enumerate(gl):
        if s:
            text(345, 346 + i * 16, s, 10.5, 400, "#57606a")
    huy_hieu(420, 50, LOGO["gw"], C["gw"][1])
    col2 = [("office", "app", True), ("canhan", "app", True), ("kc", "id", False), ("cf", "proc", False),
            ("hasura", "data", False), ("files", "trust", True), ("mon", "ops", False)]
    for i, (k, kind, team) in enumerate(col2):
        box(x2, row[i], bw, bh, kind, *tx[k], team=team, logo=LOGO.get(k, ()))
    for x, r, k, kind, team in ((x3, 3, "wf", "proc", True), (x3, 4, "pg", "data", False),
                                (x3, 5, "clam", "trust", False), (x3, 6, "sw", "data", False),
                                (x4, 3, "flow", "proc", False), (x4, 4, "bao", "trust", False),
                                (x4, 5, "meili", "data", False), (x4, 6, "ollama", "ai", False)):
        box(x, row[r], bw, bh, kind, *tx[k], team=team, logo=LOGO.get(k, ()))

    # chú giải
    lx = 24
    for kind, label in tx["legend"]:
        f, s = C[kind]
        a(f'<rect x="{lx}" y="703" width="16" height="12" rx="3" fill="{f}" stroke="{s}"/>')
        text(lx + 22, 713, label, 11, 400, "#57606a", "start")
        lx += 22 + len(label) * 6.4 + 22
    text(24, 742, tx["bold"], 11, 400, "#57606a", "start")
    a('<circle cx="760" cy="738" r="4.5" fill="#d79b00" stroke="#ffffff" stroke-width="1.5"/>')
    text(772, 742, tx["pulse"], 11, 400, "#57606a", "start")
    text(1256, 742, tx["credit"], 10, 400, "#8c959f", "end")
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
