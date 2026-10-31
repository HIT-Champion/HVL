#!/usr/bin/env python3
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

"""Reconciler GitOps và tự phục hồi (F3.3) — một lượt mỗi lần gọi, chỉ dùng thư viện chuẩn.

Chạy trên máy chủ bằng systemd timer mỗi 60 giây (`platform/systemd/`), không gắn socket Docker vào container nào.
Mỗi lượt đưa hệ thống đang chạy về đúng trạng thái khai trong git:

  1. GitOps (khi đặt MOC_GITOPS_DIR — một bản sao git riêng của reconciler, chỉ dùng khi chạy từ bản cài):
     `git fetch` nhánh MOC_GITOPS_BRANCH (mặc định `deploy`). Có commit mới, hoặc tệp đã cài bị sửa tay (khác băm
     lúc cài) → dựng image của commit đó, dừng Signet, cài lại đúng commit vào thư mục này (`install.sh`), chạy lại.
     Cài hỏng giữa chừng thì cài lại commit cũ. Commit áp lỗi thì không thử lại mỗi phút: đợi commit kế tiếp.
     MOC_GITOPS_MODE=nang-cap (bản thật, #344): áp bằng đường nâng tay `scripts/nang_cap.sh nang` của commit đó (sao
     lưu, cài, realm, kiểm); lỗi sau khi đã sao lưu thì tự `nang_cap.sh lui` về commit cũ, khôi phục lượt vừa lấy.
     MOC_GITOPS_FOLLOW=release: áp thẻ phát hành vX.Y.Z mới nhất trên nhánh (vd. `main`) thay cho đầu nhánh.
  2. Tự phục hồi: container unhealthy → khởi động lại; dịch vụ khai trong compose mà thiếu container hoặc đã dừng →
     `docker compose up -d` đúng các dịch vụ đó. Dịch vụ chạy một lần (keycloak-fonts) đã xong, thoát 0, không tính
     là đã dừng.
  Giữa hai bước: ứng dụng cài bằng `moc app install` (nếu có) — dựng lại tệp chạy khi lõi đổi; không tự cài, gỡ ứng
  dụng nào (apps()).

Bỏ qua lượt khi đang sao lưu, khôi phục, cài đặt (cùng một khóa với `moc backup` và `install.sh`), khi lần khôi phục
trước dừng giữa chừng (dữ liệu dở dang, không chạy lại Signet trên đó) hay có dịch vụ đang tạm dừng có chủ ý. Dịch vụ
còn tạm dừng từ một lần sao lưu bị giết cứng thì chạy lại. Bảo trì tay thì tắt timer trước.

    python3 scripts/reconcile.py                          # một lượt, in từng việc đã làm
    python3 scripts/reconcile.py --json                   # dòng cuối là kết quả JSON
    python3 scripts/reconcile.py --heal-only --wait 120   # chỉ tự phục hồi; đợi lượt khác xong (smoke, demo)

Thoát 0 khi hệ thống đã khớp (kể cả sau khi sửa), 1 khi còn việc chưa làm được, 2 khi lỗi cấu hình.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ".moc-install"           # danh sách tệp do make install quản lý (scripts/install.sh)
STATE = "moc-reconcile.json"        # trong thư mục .git của bản sao: commit đã áp, băm tệp lúc cài
UPGRADE_LOG = "moc-nang-cap.log"    # cũng trong thư mục .git: đầu ra lần nâng, lùi gần nhất (chế độ nang-cap)
MODES = ("", "nang-cap")            # MOC_GITOPS_MODE: để trống là cài lại bằng install.sh như trước
FOLLOWS = ("", "release")           # MOC_GITOPS_FOLLOW: để trống là theo đầu nhánh như trước
RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")  # thẻ phát hành; bản thử (-rc…) không tự lên
BACKUP_RUN = re.compile(r"lượt sao lưu (\S+);")  # dòng nang_cap.sh nang in sau khi sao lưu xong
RESTORING = ".moc-restoring"        # scripts/backup.py đặt trước khi dừng Signet để khôi phục, xóa khi xong
APPS = ".moc-apps/apps"             # bản ghi ứng dụng cài bằng moc app install (scripts/ung_dung.py)
# Dịch vụ `moc backup create` tạm dừng (cùng danh sách WRITERS, DB_WRITERS trong scripts/backup.py)
BACKUP_PAUSES = {"svc-files", "seaweedfs", "openbao", "hasura", "svc-workflow", "flowable", "keycloak"}


class ReconcileError(Exception):
    pass


class ConfigError(ReconcileError):
    """Lỗi ở .env của bản cài, không phải của commit: sửa .env thì lượt sau áp được, không cần commit mới."""


def _run(cmd: list[str], *, cwd: pathlib.Path = ROOT, env: dict[str, str] | None = None,
         timeout: float | None = 600, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          timeout=timeout)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
        raise ReconcileError(f"{' '.join(cmd[:4])}… thoát {proc.returncode}: " + " / ".join(detail))
    return proc


def dotenv() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                env[key.strip()] = value.strip()
    return env


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name) or dotenv().get(name) or default


def compose() -> list[str]:
    """`docker compose` với đúng các profile của bản này: core, app cùng MOC_EXTRA_PROFILES (như Makefile, như
    COMPOSE_PROFILES install.sh ghi vào bản cài). Cờ --profile đè COMPOSE_PROFILES của .env: chỉ có core, app thì
    `down` để sót container của profile thêm (cloudflared của tunnel…) còn chạy từ thư mục cài, install.sh từ chối cài
    lại, `up` không chạy lại chúng."""
    extra = [p.strip() for p in setting("MOC_EXTRA_PROFILES").split(",") if p.strip()]
    return ["docker", "compose", *(arg for p in dict.fromkeys(["core", "app", *extra]) for arg in ("--profile", p))]


def write_private(path: pathlib.Path, data: str) -> None:
    """Ghi cả tệp một lần (tệp tạm rồi đổi tên), chỉ chủ sở hữu đọc được: bị ngắt giữa chừng thì tệp cũ còn nguyên."""
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


@contextlib.contextmanager
def ops_lock(wait_s: float = 0) -> Iterator[bool]:
    """Khóa chung với `moc backup` và `install.sh` (flock trên thư mục chạy Signet): False khi lệnh khác giữ quá
    `wait_s` giây."""
    fd = os.open(ROOT, os.O_RDONLY)
    deadline = time.monotonic() + wait_s
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(1)
        yield True
    finally:
        os.close(fd)


# ----------------------------------------------------------------------------------------------- tự phục hồi

def containers() -> tuple[list[str], set[str], dict[str, dict[str, Any]]]:
    """Dịch vụ khai trong compose, các dịch vụ chạy một lần trong số đó và container hiện có của chúng (theo tên dịch
    vụ). Dịch vụ chạy một lần: dịch vụ khác chờ nó chạy xong (service_completed_successfully), như keycloak-fonts."""
    services = json.loads(_run([*compose(), "config", "--format", "json"]).stdout).get("services") or {}
    once = {dep for svc in services.values() for dep, cond in (svc.get("depends_on") or {}).items()
            if cond.get("condition") == "service_completed_successfully"}
    raw = _run([*compose(), "ps", "-a", "--format", "json"]).stdout.strip()
    # Compose cũ in một mảng JSON, bản mới in mỗi container một dòng
    rows = json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines() if line]
    # bỏ container chạy một lần (`docker compose run …`): không phải container của dịch vụ
    rows = [row for row in rows if "com.docker.compose.oneoff=True" not in str(row.get("Labels", ""))]
    return list(services), once, {row["Service"]: row for row in rows}


def heal(report: dict[str, Any]) -> None:
    wanted, once, actual = containers()
    paused = sorted(s for s, c in actual.items() if c.get("State") == "paused")
    # đang giữ khóa nên không lượt sao lưu nào đang chạy: dịch vụ sao lưu tạm dừng mà còn đó là do lượt bị giết cứng
    left = [s for s in paused if s in BACKUP_PAUSES]
    for s in left:
        try:
            _run([*compose(), "unpause", s], timeout=60)
            report["actions"].append(f"bỏ tạm dừng {s} (còn lại từ một lần sao lưu bị ngắt)")
        except (ReconcileError, subprocess.TimeoutExpired) as exc:
            report["problems"].append(f"không bỏ tạm dừng được {s}: {exc}")
    paused = [s for s in paused if s not in left]
    if paused:
        report["skipped"] = f"dịch vụ đang tạm dừng có chủ ý: {', '.join(paused)}"
        report["problems"].append(f"{', '.join(paused)} đang tạm dừng — xong việc thì docker compose unpause")
        return
    missing = [s for s in wanted if s not in actual]
    # dịch vụ chạy một lần đã xong, thoát 0, là đúng trạng thái khai báo: không chạy lại mỗi lượt. Thoát lỗi thì chạy
    # lại như mọi dịch vụ đã dừng
    done = {s for s in once if s in actual and actual[s].get("State") == "exited" and actual[s].get("ExitCode") == 0}
    stopped = [s for s in wanted if s in actual and s not in done
               and actual[s].get("State") in ("exited", "created", "dead")]
    # chạy lại thì có thể qua (lỗi thoáng qua), nhưng lượt nào cũng thoát lỗi thì chỉ nằm trong actions, không ai thấy
    for s in sorted(once & set(stopped)):
        if actual[s].get("State") == "exited" and actual[s].get("ExitCode") != 0:
            report["problems"].append(f"{s} chạy một lần mà thoát lỗi ({actual[s].get('Status', '')}) — xem nhật ký: "
                                      f"docker compose logs {s}")
    looping = [s for s in wanted if s in actual and actual[s].get("State") == "restarting"]
    unhealthy = [s for s in wanted if s in actual and actual[s].get("State") == "running"
                 and actual[s].get("Health") == "unhealthy"]
    # unhealthy trước: `up` dừng ngay khi một phụ thuộc service_healthy đang unhealthy
    for s in unhealthy:
        try:
            _run([*compose(), "restart", s], timeout=300)
            report["actions"].append(f"khởi động lại {s} (unhealthy)")
        except (ReconcileError, subprocess.TimeoutExpired) as exc:
            report["problems"].append(f"không khởi động lại được {s}: {exc}")
    if missing or stopped:
        # chỉ đúng các dịch vụ thiếu, đã dừng; --no-recreate: không dựng lại container đang chạy chỉ vì biến môi
        # trường của lượt này khác lúc chúng được tạo
        try:
            _run([*compose(), "up", "-d", "--no-build", "--no-recreate", *missing, *stopped], timeout=900)
            report["actions"] += [f"dựng lại {s} (không còn container)" for s in missing]
            report["actions"] += [f"chạy lại {s} (đã dừng: {actual[s].get('Status', '')})" for s in stopped]
        except (ReconcileError, subprocess.TimeoutExpired) as exc:
            report["problems"].append(f"không dựng lại được {', '.join(missing + stopped)}: {exc}")
    for s in looping:
        report["problems"].append(f"{s} đang tự khởi động lại liên tục ({actual[s].get('Status', '')}) — xem nhật ký")


# ----------------------------------------------------------------------------------------------- GitOps

def installed_files() -> dict[str, str]:
    """SHA-256 từng tệp do make install chép vào thư mục này (trừ VERSION ghi giờ cài và __pycache__)."""
    out: dict[str, str] = {}
    for rel in (ROOT / MANIFEST).read_text(encoding="utf-8").split("\n"):
        if not rel or rel == "VERSION" or "__pycache__" in rel:
            continue
        path = ROOT / rel
        if not path.exists():
            out[rel] = ""                               # tệp đã cài bị xóa
            continue
        for f in sorted(path.rglob("*")) if path.is_dir() else [path]:
            if f.is_file() and "__pycache__" not in f.parts:
                out[str(f.relative_to(ROOT))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def drift(recorded: dict[str, str], now: dict[str, str]) -> list[str]:
    return sorted(f for f in set(recorded) | set(now) if recorded.get(f) != now.get(f))


def verify_signature(git: list[str], commit: str, signers: str, *, tag: bool = False) -> None:
    """MOC_GITOPS_ALLOWED_SIGNERS: chỉ áp commit ký bằng khóa SSH có trong tệp allowed_signers (định dạng của
    `ssh-keygen -Y`, như `gpg.ssh.allowedSignersFile` của git). Chữ ký OpenPGP, X.509 không được nhận dù khóa có trong
    keyring của người chạy reconciler: chỉ danh sách này quyết định ai được đưa mã lên máy chủ. `tag`
    (MOC_GITOPS_FOLLOW=release): kiểm chữ ký của thẻ (`git tag -s`), vì commit gộp trên main do GitHub ký OpenPGP."""
    path = pathlib.Path(signers).expanduser().resolve()
    if not path.is_file():
        raise ReconcileError(f"MOC_GITOPS_ALLOWED_SIGNERS: không có tệp {path}")
    proc = _run([*git, "-c", f"gpg.ssh.allowedSignersFile={path}", "-c", "gpg.openpgp.program=false",
                 "-c", "gpg.x509.program=false", "verify-tag" if tag else "verify-commit", "--raw", commit],
                check=False)
    if proc.returncode != 0:
        detail = " ".join((proc.stderr or proc.stdout).split())[:200] or "không có chữ ký"
        raise ReconcileError(f"commit {commit[:12]} không ký bằng khóa trong {path}, không áp ({detail})")


def gitops(report: dict[str, Any]) -> None:
    src_setting = setting("MOC_GITOPS_DIR")
    if not src_setting:
        return
    src = pathlib.Path(src_setting).expanduser().resolve()
    branch = setting("MOC_GITOPS_BRANCH", "deploy")
    mode, follow = setting("MOC_GITOPS_MODE"), setting("MOC_GITOPS_FOLLOW")
    if mode not in MODES:
        raise ReconcileError(f"MOC_GITOPS_MODE={mode}: chỉ nhận để trống hoặc nang-cap")
    if follow not in FOLLOWS:
        raise ReconcileError(f"MOC_GITOPS_FOLLOW={follow}: chỉ nhận để trống hoặc release")
    if not (ROOT / MANIFEST).exists():
        raise ReconcileError("GitOps chỉ chạy từ bản cài (make install PREFIX=…), không chạy trong thư mục mã nguồn")
    if src == ROOT or ROOT in src.parents or src in ROOT.parents:
        raise ReconcileError(f"MOC_GITOPS_DIR ({src}) không được chồng lên thư mục cài {ROOT}")
    git = ["git", "-C", str(src), "-c", f"safe.directory={src}"]
    gitdir = pathlib.Path(_run([*git, "rev-parse", "--absolute-git-dir"]).stdout.strip())
    state_path = gitdir / STATE
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    # reconciler `checkout -f` + `clean -fd` bản sao này: lần đầu mà có thay đổi chưa commit thì đây là bản làm việc
    # của ai đó chứ không phải bản sao riêng — dừng, không xóa việc của người ta
    if not state and _run([*git, "status", "--porcelain"]).stdout.strip():
        raise ReconcileError(f"{src} có thay đổi chưa commit — MOC_GITOPS_DIR phải là bản sao riêng của reconciler"
                             f" (git clone -b {branch} <repo> <thư mục mới>)")

    # nang-cap, release: kéo cả thẻ — chọn bản phát hành, nhận bản đang chạy (adopt), phiên bản ghi vào bản cài
    _run([*git, "fetch", "-q", *(["--tags"] if mode or follow else []), "origin", branch], timeout=300)
    tag = latest_release(git, branch) if follow else None
    target = _run([*git, "rev-parse", f"{tag or 'origin/' + branch}^{{commit}}"]).stdout.strip()
    report["commit"] = target
    changed = drift(state.get("files", {}), installed_files()) if state.get("commit") == target else []
    if state.get("commit") == target and not changed:
        return
    # áp lỗi (kể cả lần đưa tệp sửa tay về) thì chỉ thử lại khi có commit mới: không dừng Signet mỗi phút
    if state.get("failed") == target:
        report["problems"].append(f"commit {target[:12]} áp lỗi lần trước — sửa trên nhánh {branch} rồi đẩy commit mới")
        return
    # kiểm trước khi dừng Signet. Không ghi "failed": thêm khóa vào danh sách thì lượt sau áp được, không cần commit mới
    signers = setting("MOC_GITOPS_ALLOWED_SIGNERS")
    if signers:
        verify_signature(git, tag or target, signers, tag=bool(tag))
    adopted = adopt(git, target) if (mode or follow) and not state else None
    if adopted:
        state = {"commit": target, "files": installed_files(), "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                 "adopted": adopted}
        write_private(state_path, json.dumps(state, indent=2))
        report["actions"].append(f"nhận bản đang chạy (Signet {adopted}, cùng cây với commit {target[:12]}),"
                                 " không cài lại")
        return
    if state.get("commit") != target:
        reason = f"nhánh {branch}: {str(state.get('commit', 'chưa áp'))[:12]} → {target[:12]}"
        reason += f" (thẻ {tag})" if tag else ""
    else:
        reason = f"tệp đã cài bị sửa tay, đưa về commit {target[:12]}: {', '.join(changed[:5])}"
        reason += f" (+{len(changed) - 5} tệp)" if len(changed) > 5 else ""
    print(f"· áp cấu hình — {reason}", flush=True)
    try:
        (upgrade if mode else apply)(git, src, target, state.get("commit"))
    except ConfigError as exc:
        # chưa dừng Signet; không ghi "failed": sửa .env thì lượt sau áp được, không cần commit mới
        raise ReconcileError(f"không áp được commit {target[:12]}: {exc}") from None
    except (ReconcileError, subprocess.TimeoutExpired, OSError) as exc:
        state["failed"] = target
        write_private(state_path, json.dumps(state, indent=2))
        raise ReconcileError(f"không áp được commit {target[:12]}: {exc}") from None
    state = {"commit": target, "files": installed_files(), "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    write_private(state_path, json.dumps(state, indent=2))
    report["applied"] = reason
    report["actions"].append(f"áp commit {target[:12]} ({reason})")


def checkout(git: list[str], src: pathlib.Path, commit: str, *, release: bool = False) -> dict[str, str]:
    """Đưa bản sao về đúng commit; trả biến môi trường để dựng, cài commit đó (MOC_VERSION theo `git describe`, hay
    theo thẻ phát hành khi `release`: xem release_version())."""
    _run([*git, "checkout", "-q", "-f", "--detach", commit])
    _run([*git, "clean", "-q", "-fd"])                 # giữ tệp đã ignore, gồm .env của bản sao
    # install.sh đọc compose của mã nguồn cùng .env: chép lại mỗi lần từ bản cài (bản cài giữ .env của nó)
    write_private(src / ".env", (ROOT / ".env").read_text(encoding="utf-8"))
    version = release_version(git, commit) if release else \
        _run([*git, "describe", "--tags", "--always"]).stdout.strip().removeprefix("v")
    # đã giữ khóa thư mục cài: install.sh không lấy khóa lần nữa
    return {**os.environ, "MOC_VERSION": version, "MOC_OPS_LOCKED": "1"}


def check_gateway_env(src: pathlib.Path, env: dict[str, str]) -> None:
    """F3.15: MOC_WAF, MOC_APISIX_WORKERS (#364: cả MOC_TRACE_RATIO) sai thì APISIX thoát ngay lúc khởi động rồi khởi
    động lại liên tục, mà `up --wait` vẫn báo xong (apisix không có healthcheck). Kiểm trước khi dừng Signet, bằng chính
    script entrypoint của image — cùng nguồn với `make up` (Makefile, env-ready) — với giá trị compose của commit sắp
    áp sẽ dùng."""
    script = src / "platform" / "apisix" / "kiem-moi-truong.sh"
    if not script.is_file():                            # commit chưa có WAF
        return
    resolved = json.loads(_run([*compose(), "config", "--format", "json", "apisix"], cwd=src, env=env).stdout)
    values = resolved["services"]["apisix"].get("environment") or {}
    check = {"PATH": env.get("PATH", os.defpath)}
    check.update({k: str(values[k]) for k in ("MOC_WAF", "MOC_APISIX_WORKERS", "MOC_TRACE_RATIO")
                  if values.get(k) is not None})
    proc = _run(["sh", str(script), "--chi-kiem"], cwd=src, env=check, check=False)
    if proc.returncode != 0:
        detail = " ".join((proc.stderr or proc.stdout).split()) or f"thoát {proc.returncode}"
        raise ConfigError(f"{detail} — sửa {ROOT / '.env'}, Signet vẫn chạy bản cũ")


def install(src: pathlib.Path, env: dict[str, str]) -> None:
    _run(["bash", str(src / "scripts" / "install.sh"), "install", str(ROOT)], cwd=src, env=env, timeout=1800)
    _run([*compose(), "up", "-d", "--wait", "--wait-timeout", "600"], env=env, timeout=900)


def apply(git: list[str], src: pathlib.Path, target: str, previous: str | None) -> None:
    env = checkout(git, src, target)
    if not (src / "scripts" / "install.sh").is_file():
        raise ReconcileError("commit không có scripts/install.sh")
    check_gateway_env(src, env)
    # dựng image trước khi dừng Signet: lỗi dựng thì hệ thống cũ vẫn chạy; install.sh dựng lại sau đó trúng bộ nhớ đệm
    _run([*compose(), "build"], cwd=src, env=env, timeout=1800)
    _run([*compose(), "down"], timeout=300)
    try:
        install(src, env)
    except (ReconcileError, subprocess.TimeoutExpired, OSError) as exc:
        if not previous:
            raise
        # Signet đang dừng, tệp đã cài có thể dở dang: cài lại commit đang chạy trước đó (image của nó vẫn còn)
        try:
            install(src, checkout(git, src, previous))
        except (ReconcileError, subprocess.TimeoutExpired, OSError) as again:
            raise ReconcileError(f"{exc}; cài lại commit cũ {previous[:12]} cũng lỗi: {again}") from None
        raise ReconcileError(f"{exc} — đã cài lại commit cũ {previous[:12]}") from None


def tree(git: list[str], ref: str) -> str:
    return _run([*git, "rev-parse", "--verify", "-q", f"{ref}^{{tree}}"], check=False).stdout.strip()


def release_version(git: list[str], commit: str) -> str:
    """Phiên bản ghi vào bản cài ở chế độ nang-cap. Đầu nhánh deploy là commit gộp `deploy vX.Y.Z` (cùng cây với thẻ):
    `git describe` ra X.Y.Z-1-g…, thậm chí thẻ cũ hơn (đi theo cha thứ nhất là lần deploy trước), /api/status sẽ báo
    sai bản. Thẻ trong lịch sử của commit mà cây trùng cây commit thì lấy thẻ đó (mới nhất trước)."""
    want = tree(git, commit)
    tags = _run([*git, "for-each-ref", "--sort=-v:refname", f"--merged={commit}",
                 "--format=%(refname:short) %(tree) %(*tree)", "refs/tags"]).stdout.splitlines()
    for line in tags:
        name, *trees = line.split()
        if want and want in trees:                      # thẻ nhẹ: %(tree); thẻ có chú thích: %(*tree)
            return name.removeprefix("v")
    return _run([*git, "describe", "--tags", "--always", commit]).stdout.strip().removeprefix("v")


def latest_release(git: list[str], branch: str) -> str:
    """MOC_GITOPS_FOLLOW=release: thẻ phát hành vX.Y.Z mới nhất (theo số phiên bản) mà commit của nó nằm trên nhánh.
    Commit mới trên nhánh mà chưa gắn thẻ thì chưa áp: bản online chỉ đổi khi có bản phát hành."""
    tags = _run([*git, "for-each-ref", "--sort=-v:refname", f"--merged=origin/{branch}", "--format=%(refname:short)",
                 "refs/tags/v*"]).stdout.split()
    found = next((t for t in tags if RELEASE_TAG.fullmatch(t)), None)
    if not found:
        raise ReconcileError(f"nhánh {branch} chưa có thẻ phát hành vX.Y.Z — MOC_GITOPS_FOLLOW=release chưa áp gì")
    return found


def adopt(git: list[str], target: str) -> str | None:
    """Lượt đầu ở chế độ nang-cap (chưa có tệp trạng thái): bản cài đang chạy đúng thẻ mà commit deploy mang (cây
    của commit trùng cây thẻ v<phiên bản trong VERSION>) thì nhận nó làm commit đã áp, không dừng trang cài lại. Trả
    phiên bản đã nhận, None khi không khớp (khi đó nâng như mọi commit mới)."""
    path = ROOT / "VERSION"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    installed = next((line.split()[1] for line in lines if line.startswith("Signet ") and len(line.split()) > 1), "")
    if not installed:
        return None
    want = tree(git, target)
    return installed if want and want == tree(git, f"v{installed}") else None


def upgrade(git: list[str], src: pathlib.Path, target: str, previous: str | None) -> None:
    """MOC_GITOPS_MODE=nang-cap: áp commit bằng đúng đường nâng tay — `scripts/nang_cap.sh nang` của chính commit đó
    (dựng khi trang còn chạy, sao lưu, dừng, cài, realm, kiểm dữ liệu, dịch vụ, smoke). Lỗi trước khi sao lưu thì bản
    cũ vẫn chạy. Lỗi sau đó (đã dừng trang, hay kiểm trượt) thì tự lùi: `nang_cap.sh lui` cài lại commit cũ (lấy bằng
    `git archive` ra .git/moc-lui của bản sao — chỗ người chạy reconciler chắc chắn ghi được) với .env lúc trước, khôi
    phục lượt sao lưu vừa lấy. Đầu ra cả hai lệnh ghi vào UPGRADE_LOG, cũng trong thư mục .git."""
    gitdir = pathlib.Path(_run([*git, "rev-parse", "--absolute-git-dir"]).stdout.strip())
    log = gitdir / UPGRADE_LOG
    env = checkout(git, src, target, release=True)
    script = src / "scripts" / "nang_cap.sh"
    if not script.is_file():
        raise ReconcileError("commit không có scripts/nang_cap.sh, không nâng được ở chế độ nang-cap")
    check_gateway_env(src, env)
    env_before = (ROOT / ".env").read_text(encoding="utf-8")   # lùi thì cài lại bản cũ với đúng .env này
    proc = _run(["bash", str(script), "nang", str(ROOT)], cwd=src, env=env, timeout=7200, check=False)
    write_private(log, f"$ nang_cap.sh nang {ROOT}   # {target}\n{proc.stdout}{proc.stderr}")
    if proc.returncode == 0:
        return
    detail = " / ".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])
    found = BACKUP_RUN.search(proc.stdout)
    if not found:
        raise ReconcileError(f"nang_cap.sh nang thoát {proc.returncode} trước khi sao lưu, bản cũ vẫn chạy: {detail}")
    run = found.group(1)
    if not previous:
        raise ReconcileError(f"nang_cap.sh nang thoát {proc.returncode} sau khi sao lưu lượt {run}, chưa có commit cũ"
                             f" để tự lùi — xem {log}: {detail}")
    old, archive = gitdir / "moc-lui", gitdir / "moc-lui.tar"
    try:
        shutil.rmtree(old, ignore_errors=True)
        old.mkdir(mode=0o700)
        _run([*git, "archive", "--format=tar", "-o", str(archive), previous])
        _run(["tar", "-xf", str(archive), "-C", str(old)])
        write_private(old / ".env", env_before)
        back_env = {**os.environ, "MOC_VERSION": release_version(git, previous), "MOC_OPS_LOCKED": "1"}
    except (ReconcileError, subprocess.TimeoutExpired, OSError) as exc:
        raise ReconcileError(f"nâng {target[:12]} lỗi ({detail}); không lấy được mã nguồn {previous[:12]} để tự lùi"
                             f" ({exc}) — lùi tay: nang_cap.sh lui {ROOT} <mã nguồn bản cũ> {run}") from None
    finally:
        archive.unlink(missing_ok=True)
    back = _run(["bash", str(script), "lui", str(ROOT), str(old), run], cwd=src, env=back_env, timeout=7200,
                check=False)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n$ nang_cap.sh lui {ROOT} {old} {run}   # {previous}\n{back.stdout}{back.stderr}")
    if back.returncode != 0:
        again = " / ".join((back.stderr or back.stdout).strip().splitlines()[-3:])
        raise ReconcileError(f"nâng {target[:12]} lỗi ({detail}); lùi về {previous[:12]} cũng lỗi ({again})"
                             f" — xem {log}")
    raise ReconcileError(f"nâng {target[:12]} lỗi ({detail}) — đã lùi về {previous[:12]}, khôi phục lượt sao lưu {run}")


# ----------------------------------------------------------------------------------------------- ứng dụng cài thêm

def apps(report: dict[str, Any]) -> None:
    """Ứng dụng cài bằng `moc app install` (scripts/ung_dung.py): trạng thái vận hành ngoài git, như đơn vị hay tài
    khoản. Reconciler KHÔNG cài, gỡ hay kéo mã ứng dụng nào; chỉ dựng lại tệp chạy (APISIX, metadata Hasura trộn, tệp
    phủ compose) khi lõi vừa đổi hoặc tệp bị sửa, rồi áp lại phần còn thiếu. Container ứng dụng mất thì heal() dựng lại
    như mọi dịch vụ khác (tệp phủ nằm trong COMPOSE_FILE của .env)."""
    if not (ROOT / APPS).is_dir():
        return
    moc = [sys.executable, str(ROOT / "scripts" / "moc.py"), "app", "sync", "--json"]
    env = {**os.environ, "MOC_OPS_LOCKED": "1"}     # đang giữ khóa của thư mục này
    out = _run([*moc, "--files"], env=env, timeout=120).stdout.strip().splitlines()
    changed = json.loads(out[-1]).get("changed", []) if out else []
    if not changed:
        return
    report["actions"].append(f"dựng lại {len(changed)} tệp của ứng dụng cài thêm (lõi đổi hoặc tệp bị sửa)")
    out = _run(moc, env=env, timeout=900).stdout.strip().splitlines()
    report["actions"] += [f"ứng dụng: {a}" for a in (json.loads(out[-1]).get("actions", []) if out else [])]


# -----------------------------------------------------------------------------------------------

def reconcile(*, heal_only: bool = False, wait_s: float = 0) -> dict[str, Any]:
    report: dict[str, Any] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "skipped": None, "commit": None,
                              "applied": None, "actions": [], "problems": []}
    with ops_lock(wait_s) as locked:
        if not locked:
            report["skipped"] = "đang sao lưu, khôi phục, cài đặt hoặc một lượt khác đang chạy"
            return report
        if (ROOT / RESTORING).exists():
            report["skipped"] = "lần khôi phục trước dừng giữa chừng"
            report["problems"].append("dữ liệu có thể dở dang, không chạy lại Signet trên đó — chạy lại: python3"
                                      " scripts/moc.py backup restore")
            return report
        if not heal_only:
            try:
                gitops(report)
            except (ReconcileError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
                # lỗi GitOps (mạng, repo, tệp trạng thái) không được chặn phần tự phục hồi
                report["problems"].append(f"GitOps: {exc}")
        try:
            apps(report)
        except (ReconcileError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
            report["problems"].append(f"ứng dụng cài thêm: {exc}")
        heal(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reconcile",
                                     description="Một lượt reconciler GitOps + tự phục hồi của Signet")
    parser.add_argument("--json", action="store_true", help="in kết quả JSON ở dòng cuối")
    parser.add_argument("--heal-only", action="store_true", help="chỉ tự phục hồi, không kéo commit từ git")
    parser.add_argument("--wait", type=float, default=0, metavar="GIÂY",
                        help="lệnh khác đang giữ khóa thì đợi tối đa chừng ấy giây thay vì bỏ qua lượt")
    args = parser.parse_args(argv)
    try:
        report = reconcile(heal_only=args.heal_only, wait_s=args.wait)
    except (ReconcileError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    if report["skipped"]:
        print(f"· bỏ qua lượt này: {report['skipped']}")
    for action in report["actions"]:
        print(f"✓ {action}")
    for problem in report["problems"]:
        print(f"✗ {problem}")
    if not (report["skipped"] or report["actions"] or report["problems"]):
        commit = f" (commit {report['commit'][:12]})" if report["commit"] else ""
        print(f"✓ đã khớp trạng thái khai báo{commit}, không có gì phải làm")
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
