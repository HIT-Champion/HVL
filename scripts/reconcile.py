#!/usr/bin/env python3
# Copyright 2026 Mộc Team
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

Chạy trên máy chủ bằng systemd timer mỗi 60 giây (`ops/systemd/`), không gắn socket Docker vào container nào.
Mỗi lượt đưa hệ thống đang chạy về đúng trạng thái khai trong git:

  1. GitOps (khi đặt MOC_GITOPS_DIR — một bản sao git riêng của reconciler, chỉ dùng khi chạy từ bản cài):
     `git fetch` nhánh MOC_GITOPS_BRANCH (mặc định `deploy`). Có commit mới, hoặc tệp đã cài bị sửa tay (khác băm
     lúc cài) → dựng image của commit đó, dừng Mộc, cài lại đúng commit vào thư mục này (`install.sh`), chạy lại.
     Cài hỏng giữa chừng thì cài lại commit cũ. Commit áp lỗi thì không thử lại mỗi phút: đợi commit kế tiếp.
  2. Tự phục hồi: container unhealthy → khởi động lại; dịch vụ khai trong compose mà thiếu container hoặc đã dừng →
     `docker compose up -d` đúng các dịch vụ đó.

Bỏ qua lượt khi đang sao lưu, khôi phục, cài đặt (cùng một khóa với `moc backup` và `install.sh`), khi lần khôi phục
trước dừng giữa chừng (dữ liệu dở dang, không chạy lại Mộc trên đó) hay có dịch vụ đang tạm dừng có chủ ý. Dịch vụ
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
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPOSE = ["docker", "compose", "--profile", "core", "--profile", "app"]
MANIFEST = ".moc-install"           # danh sách tệp do make install quản lý (scripts/install.sh)
STATE = "moc-reconcile.json"        # trong thư mục .git của bản sao: commit đã áp, băm tệp lúc cài
RESTORING = ".moc-restoring"        # scripts/backup.py đặt trước khi dừng Mộc để khôi phục, xóa khi xong
# Dịch vụ `moc backup create` tạm dừng (cùng danh sách WRITERS, DB_WRITERS trong scripts/backup.py)
BACKUP_PAUSES = {"svc-files", "seaweedfs", "openbao", "hasura", "svc-workflow", "flowable", "keycloak"}


class ReconcileError(Exception):
    pass


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


def write_private(path: pathlib.Path, data: str) -> None:
    """Ghi cả tệp một lần (tệp tạm rồi đổi tên), chỉ chủ sở hữu đọc được: bị ngắt giữa chừng thì tệp cũ còn nguyên."""
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


@contextlib.contextmanager
def ops_lock(wait_s: float = 0) -> Iterator[bool]:
    """Khóa chung với `moc backup` và `install.sh` (flock trên thư mục chạy Mộc): False khi lệnh khác giữ quá
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

def containers() -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Dịch vụ khai trong compose và container hiện có của chúng (theo tên dịch vụ)."""
    wanted = _run([*COMPOSE, "config", "--services"]).stdout.split()
    raw = _run([*COMPOSE, "ps", "-a", "--format", "json"]).stdout.strip()
    # Compose cũ in một mảng JSON, bản mới in mỗi container một dòng
    rows = json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines() if line]
    # bỏ container chạy một lần (`docker compose run …`): không phải container của dịch vụ
    rows = [row for row in rows if "com.docker.compose.oneoff=True" not in str(row.get("Labels", ""))]
    return wanted, {row["Service"]: row for row in rows}


def heal(report: dict[str, Any]) -> None:
    wanted, actual = containers()
    paused = sorted(s for s, c in actual.items() if c.get("State") == "paused")
    # đang giữ khóa nên không lượt sao lưu nào đang chạy: dịch vụ sao lưu tạm dừng mà còn đó là do lượt bị giết cứng
    left = [s for s in paused if s in BACKUP_PAUSES]
    for s in left:
        try:
            _run([*COMPOSE, "unpause", s], timeout=60)
            report["actions"].append(f"bỏ tạm dừng {s} (còn lại từ một lần sao lưu bị ngắt)")
        except (ReconcileError, subprocess.TimeoutExpired) as exc:
            report["problems"].append(f"không bỏ tạm dừng được {s}: {exc}")
    paused = [s for s in paused if s not in left]
    if paused:
        report["skipped"] = f"dịch vụ đang tạm dừng có chủ ý: {', '.join(paused)}"
        report["problems"].append(f"{', '.join(paused)} đang tạm dừng — xong việc thì docker compose unpause")
        return
    missing = [s for s in wanted if s not in actual]
    stopped = [s for s in wanted if s in actual and actual[s].get("State") in ("exited", "created", "dead")]
    looping = [s for s in wanted if s in actual and actual[s].get("State") == "restarting"]
    unhealthy = [s for s in wanted if s in actual and actual[s].get("State") == "running"
                 and actual[s].get("Health") == "unhealthy"]
    # unhealthy trước: `up` dừng ngay khi một phụ thuộc service_healthy đang unhealthy
    for s in unhealthy:
        try:
            _run([*COMPOSE, "restart", s], timeout=300)
            report["actions"].append(f"khởi động lại {s} (unhealthy)")
        except (ReconcileError, subprocess.TimeoutExpired) as exc:
            report["problems"].append(f"không khởi động lại được {s}: {exc}")
    if missing or stopped:
        # chỉ đúng các dịch vụ thiếu, đã dừng; --no-recreate: không dựng lại container đang chạy chỉ vì biến môi
        # trường của lượt này khác lúc chúng được tạo
        try:
            _run([*COMPOSE, "up", "-d", "--no-build", "--no-recreate", *missing, *stopped], timeout=900)
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


def gitops(report: dict[str, Any]) -> None:
    src_setting = setting("MOC_GITOPS_DIR")
    if not src_setting:
        return
    src = pathlib.Path(src_setting).expanduser().resolve()
    branch = setting("MOC_GITOPS_BRANCH", "deploy")
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

    _run([*git, "fetch", "-q", "origin", branch], timeout=300)
    target = _run([*git, "rev-parse", f"origin/{branch}^{{commit}}"]).stdout.strip()
    report["commit"] = target
    changed = drift(state.get("files", {}), installed_files()) if state.get("commit") == target else []
    if state.get("commit") == target and not changed:
        return
    # áp lỗi (kể cả lần đưa tệp sửa tay về) thì chỉ thử lại khi có commit mới: không dừng Mộc mỗi phút
    if state.get("failed") == target:
        report["problems"].append(f"commit {target[:12]} áp lỗi lần trước — sửa trên nhánh {branch} rồi đẩy commit mới")
        return
    if state.get("commit") != target:
        reason = f"nhánh {branch}: {str(state.get('commit', 'chưa áp'))[:12]} → {target[:12]}"
    else:
        reason = f"tệp đã cài bị sửa tay, đưa về commit {target[:12]}: {', '.join(changed[:5])}"
        reason += f" (+{len(changed) - 5} tệp)" if len(changed) > 5 else ""
    print(f"· áp cấu hình — {reason}", flush=True)
    try:
        apply(git, src, target, state.get("commit"))
    except (ReconcileError, subprocess.TimeoutExpired, OSError) as exc:
        state["failed"] = target
        write_private(state_path, json.dumps(state, indent=2))
        raise ReconcileError(f"không áp được commit {target[:12]}: {exc}") from None
    state = {"commit": target, "files": installed_files(), "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    write_private(state_path, json.dumps(state, indent=2))
    report["applied"] = reason
    report["actions"].append(f"áp commit {target[:12]} ({reason})")


def checkout(git: list[str], src: pathlib.Path, commit: str) -> dict[str, str]:
    """Đưa bản sao về đúng commit; trả biến môi trường để dựng, cài commit đó (MOC_VERSION theo `git describe`)."""
    _run([*git, "checkout", "-q", "-f", "--detach", commit])
    _run([*git, "clean", "-q", "-fd"])                 # giữ tệp đã ignore, gồm .env của bản sao
    # install.sh đọc compose của mã nguồn cùng .env: chép lại mỗi lần từ bản cài (bản cài giữ .env của nó)
    write_private(src / ".env", (ROOT / ".env").read_text(encoding="utf-8"))
    version = _run([*git, "describe", "--tags", "--always"]).stdout.strip().removeprefix("v")
    # đã giữ khóa thư mục cài: install.sh không lấy khóa lần nữa
    return {**os.environ, "MOC_VERSION": version, "MOC_OPS_LOCKED": "1"}


def install(src: pathlib.Path, env: dict[str, str]) -> None:
    _run(["bash", str(src / "scripts" / "install.sh"), "install", str(ROOT)], cwd=src, env=env, timeout=1800)
    _run([*COMPOSE, "up", "-d", "--wait", "--wait-timeout", "600"], env=env, timeout=900)


def apply(git: list[str], src: pathlib.Path, target: str, previous: str | None) -> None:
    env = checkout(git, src, target)
    if not (src / "scripts" / "install.sh").is_file():
        raise ReconcileError("commit không có scripts/install.sh")
    # dựng image trước khi dừng Mộc: lỗi dựng thì hệ thống cũ vẫn chạy; install.sh dựng lại sau đó trúng bộ nhớ đệm
    _run([*COMPOSE, "build"], cwd=src, env=env, timeout=1800)
    _run([*COMPOSE, "down"], timeout=300)
    try:
        install(src, env)
    except (ReconcileError, subprocess.TimeoutExpired, OSError) as exc:
        if not previous:
            raise
        # Mộc đang dừng, tệp đã cài có thể dở dang: cài lại commit đang chạy trước đó (image của nó vẫn còn)
        try:
            install(src, checkout(git, src, previous))
        except (ReconcileError, subprocess.TimeoutExpired, OSError) as again:
            raise ReconcileError(f"{exc}; cài lại commit cũ {previous[:12]} cũng lỗi: {again}") from None
        raise ReconcileError(f"{exc} — đã cài lại commit cũ {previous[:12]}") from None


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
            report["problems"].append("dữ liệu có thể dở dang, không chạy lại Mộc trên đó — chạy lại: python3"
                                      " scripts/moc.py backup restore")
            return report
        if not heal_only:
            try:
                gitops(report)
            except (ReconcileError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
                # lỗi GitOps (mạng, repo, tệp trạng thái) không được chặn phần tự phục hồi
                report["problems"].append(f"GitOps: {exc}")
        heal(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reconcile", description="Một lượt reconciler GitOps + tự phục hồi của Mộc")
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
