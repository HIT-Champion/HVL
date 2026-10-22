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

"""Sao lưu và khôi phục (F3.4) — chỉ dùng thư viện chuẩn; gọi qua `moc backup …` (scripts/moc.py).

Mỗi lần sao lưu là một "lượt": vài snapshot restic cùng thẻ `run-<lượt>`:

- `pg_dump -Fc` của từng CSDL trong máy chủ PostgreSQL (moc, keycloak, flowable…), đẩy thẳng từ container postgres
  sang restic qua ống, không ghi tệp tạm;
- cả volume SeaweedFS: tệp văn bản, bucket lạnh cùng các mốc neo sổ kiểm toán và trạng thái khóa ghi của chúng;
- cả volume két OpenBao (F3.7): khóa transit `moc-files` bọc khóa dữ liệu của từng tệp văn bản hạn chế, chỉ nằm ở
  đây — mất két là mất mọi tệp mã hóa. Két khôi phục mở bằng khóa static seal trong .env đang dùng
  (MOC_OPENBAO_SEAL_KEY): cất một bản .env ở chỗ riêng, KHÔNG để chung với kho sao lưu — thiếu nó thì không khôi
  phục được, có cả hai thì mở được mọi tệp mã hóa;
- manifest.json, ghi sau cùng. Lượt thiếu manifest là lượt hỏng giữa chừng, không dùng để khôi phục.

Từ trước lúc dump CSDL tới lúc chép xong tệp, svc-files (chỗ duy nhất ghi vào SeaweedFS và neo sổ kiểm toán),
SeaweedFS và két tạm dừng (`docker compose pause`): mốc neo trong bucket với bảng mốc trong CSDL, tệp với dòng trỏ tới tệp
là cùng một lúc, nên khôi phục xong `moc audit verify` vẫn khớp. Các dịch vụ còn lại có ghi CSDL (Hasura,
svc-workflow, Flowable, Keycloak) chỉ tạm dừng lúc dump, để các CSDL cùng một lúc. Volume tệp được chép mồi một
lượt trước khi tạm dừng, nên lúc dừng chỉ phải đọc tệp đổi trong vài giây đó.

restic (BSD-2-Clause) chạy trong container `restic` (profile backup, không mạng): mã hóa, khử trùng lặp, các lần
sau chỉ thêm phần đã đổi. Kho ở MOC_BACKUP_DIR, khóa là MOC_BACKUP_PASSWORD — mất khóa là mất bản sao lưu. Chỉ mục
Meilisearch và chữ ký ClamAV không sao lưu: svc-files đồng bộ lại chỉ mục từ CSDL khi khởi động, ClamAV tự tải chữ
ký. Lịch sử cảm biến của màn demo IT/OT (Scorpio, profile iot) cũng không sao lưu. Lượt sao lưu cũ chưa có két thì
khôi phục giữ nguyên két đang có.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import getpass
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from audit_chain import HEAD_SQL, RESTORED_SQL
from moc_env import ENV, ROOT

COMPOSE = ["docker", "compose", "--profile", "core", "--profile", "app"]
WRITERS = ("svc-files", "seaweedfs", "openbao")            # tạm dừng suốt lúc sao lưu
DB_WRITERS = ("hasura", "svc-workflow", "flowable", "keycloak")   # tạm dừng lúc dump CSDL
FILES = "/data/seaweedfs"               # chỗ volume SeaweedFS gắn vào container restic
VAULT = "/data/openbao"                 # chỗ volume két OpenBao gắn vào container restic (F3.7)
HOST = "moc"                            # tên máy ghi vào snapshot: cố định, để restic tìm ra lượt trước và chỉ đọc
TAG = "moc"                             # tệp đã đổi (container mỗi lần một tên khác)
MANIFEST = "manifest.json"
# Đặt trước khi dừng Signet để khôi phục, xóa khi Signet đã chạy lại: còn tệp này thì reconciler (F3.3) không dựng
# lại Signet trên dữ liệu khôi phục dở dang
RESTORING = ROOT / ".moc-restoring"
# Những gì restic tạo trong kho — chỉ trả quyền sở hữu những mục này, không đụng tệp khác trong thư mục
REPO_ENTRIES = "/repo/config /repo/keys /repo/data /repo/index /repo/snapshots /repo/locks"
USER = ENV.get("POSTGRES_USER", "moc")
MAIN_DB = ENV.get("POSTGRES_DB", "moc")


class BackupError(Exception):
    """Không sao lưu, khôi phục được — thông báo viết cho người vận hành đọc."""


def _tail(raw: bytes) -> str:
    lines = [line.strip() for line in raw.decode(errors="replace").splitlines() if line.strip()]
    return " / ".join(lines[-3:]) or "lỗi không rõ"


def _call(cmd: list[str], what: str, **kw: Any) -> bytes:
    if "input" not in kw:
        kw.setdefault("stdin", subprocess.DEVNULL)   # `compose run` mặc định nối stdin của terminal vào container
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, **kw)
    if proc.returncode != 0:
        raise BackupError(f"{what}: {_tail(proc.stderr)}")
    return proc.stdout


def _pipe(source: list[str], sink: list[str]) -> tuple[subprocess.CompletedProcess, int, bytes]:
    """source | sink, không ghi tệp tạm. Trả kết quả của sink, mã thoát và stderr của source."""
    with tempfile.TemporaryFile() as err:   # không đọc stderr của source lúc đang chuyển stdout: khỏi kẹt ống
        producer = subprocess.Popen(source, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err)
        assert producer.stdout is not None
        try:
            done = subprocess.run(sink, cwd=ROOT, stdin=producer.stdout, capture_output=True)
        finally:
            producer.stdout.close()         # sink dừng giữa chừng thì source nhận EPIPE, không treo
            code = producer.wait()
        err.seek(0)
        return done, code, err.read()


def repo_dir() -> pathlib.Path:
    path = pathlib.Path(os.environ.get("MOC_BACKUP_DIR") or ENV.get("MOC_BACKUP_DIR") or "backups").expanduser()
    return path if path.is_absolute() else ROOT / path


def restic(*args: str) -> list[str]:
    """Lệnh restic trong container `restic`, kho gắn vào /repo. Chạy bằng root vì tệp của SeaweedFS chỉ chủ của nó
    đọc được; xong thì trả quyền sở hữu các mục của kho cho người gọi lệnh, để chép, xóa kho không cần sudo."""
    return [*COMPOSE, "--profile", "backup", "run", "--rm", "-T", "--no-deps", "-v", f"{repo_dir()}:/repo",
            "-e", f"OWNER={os.getuid()}:{os.getgid()}", "--entrypoint", "sh", "restic",
            "-c", f'restic --no-cache "$@"; rc=$?; chown -R "$OWNER" {REPO_ENTRIES} 2>/dev/null; exit $rc',
            "restic", *args]


def _ready(*, repo_exists: bool = True) -> pathlib.Path:
    password = os.environ.get("MOC_BACKUP_PASSWORD") or ENV.get("MOC_BACKUP_PASSWORD") or ""
    if not password or password.startswith("change_me"):
        raise BackupError("chưa đặt MOC_BACKUP_PASSWORD trong .env: thêm dòng MOC_BACKUP_PASSWORD=<chuỗi ngẫu nhiên"
                          " dài> (vd. openssl rand -hex 24) rồi chép .env ra ngoài máy chủ — mất khóa là mất bản sao lưu")
    repo = repo_dir()
    if any(c in str(repo) for c in ":,"):
        raise BackupError(f"đường dẫn kho không được có dấu ':' hay ',': {repo}")
    if repo_exists and not (repo / "config").exists():
        raise BackupError(f"chưa có kho sao lưu ở {repo} — tạo lượt đầu: make backup (hoặc kiểm MOC_BACKUP_DIR)")
    return repo


@contextlib.contextmanager
def _guard(repo: pathlib.Path) -> Iterator[None]:
    """Mỗi lúc chỉ một lệnh sao lưu, khôi phục trên một kho (flock trên thư mục kho). SIGTERM, SIGHUP (cron hết giờ,
    rớt SSH) thành exception như Ctrl+C, để các khối finally — bỏ tạm dừng dịch vụ — vẫn chạy."""
    def stop(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    old = {s: signal.signal(s, stop) for s in (signal.SIGTERM, signal.SIGHUP)}
    fd = os.open(repo, os.O_RDONLY)
    ops = os.open(ROOT, os.O_RDONLY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError(f"một lệnh sao lưu hoặc khôi phục khác đang chạy trên kho {repo}") from None
        # F3.3: khóa chung với reconciler (scripts/reconcile.py) trên thư mục chạy Signet — reconciler không dựng lại
        # dịch vụ giữa lúc khôi phục. Reconciler đang áp cấu hình mới thì đợi nó xong (tối đa 30 phút).
        deadline = time.monotonic() + 1800
        while True:
            try:
                fcntl.flock(ops, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise BackupError("reconciler (F3.3) giữ khóa quá 30 phút — xem nhật ký moc-reconcile") from None
                time.sleep(2)
        yield
    finally:
        os.close(ops)
        os.close(fd)
        for s, handler in old.items():
            signal.signal(s, handler)


def _services(status: str) -> set[str]:
    return set(_call([*COMPOSE, "ps", "--status", status, "--services"],
                     "không hỏi được trạng thái dịch vụ").decode().split())


def _unpause(services: list[str]) -> None:
    """Bỏ tạm dừng từng dịch vụ; dịch vụ không còn tạm dừng thì thôi. Lỗi thì báo cách chạy tay."""
    failed = []
    for service in services:
        proc = subprocess.run([*COMPOSE, "unpause", service], cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True)
        if proc.returncode != 0 and b"not paused" not in proc.stderr:
            failed.append(service)
    services.clear()
    if failed:
        raise BackupError(f"CHƯA chạy lại được {', '.join(failed)} — chạy tay: docker compose --profile core unpause"
                          f" {' '.join(failed)}")


def _resume_left_paused() -> None:
    """Lần sao lưu trước bị giết cứng (SIGKILL) giữa lúc tạm dừng: chạy lại các dịch vụ đó trước khi làm gì."""
    left = sorted(_services("paused") & {*WRITERS, *DB_WRITERS})
    if left:
        _unpause(list(left))
        print(f"  ⚠ {', '.join(left)} còn tạm dừng từ một lần sao lưu bị ngắt: đã chạy lại", flush=True)


def _psql(script: str, db: str = MAIN_DB, **variables: str) -> str:
    cmd = [*COMPOSE, "exec", "-T", "postgres", "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", USER,
           "-d", db, *(a for k, v in variables.items() for a in ("-v", f"{k}={v}")), "-f", "-"]
    return _call(cmd, "không chạy được lệnh trên CSDL", input=script.encode()).decode().strip()


def _databases() -> list[str]:
    return _psql("select datname from pg_database where not datistemplate and datname <> 'postgres'"
                 " order by datname;").split()


def _summary(out: bytes) -> dict[str, Any]:
    """Dòng tổng kết trong kết quả `restic backup --json`."""
    for line in reversed(out.decode(errors="replace").splitlines()):
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if isinstance(msg, dict) and msg.get("message_type") == "summary":
            return {"snapshot": msg["snapshot_id"], "bytes": msg.get("total_bytes_processed", 0),
                    "added": msg.get("data_added", 0)}
    raise BackupError("restic không báo snapshot vừa ghi")


def _backup_args(tags: list[str], *more: str) -> list[str]:
    return restic("backup", "--json", "--host", HOST, "--tag", ",".join(tags), *more)


def snapshots() -> list[dict[str, Any]]:
    return json.loads(_call(restic("snapshots", "--json", "--tag", TAG), "không đọc được kho sao lưu") or b"[]") or []


def runs(snaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gom snapshot theo lượt, cũ trước. parts: tên phần ("moc.dump", "data/seaweedfs", MANIFEST) → id snapshot."""
    grouped: dict[str, dict[str, Any]] = {}
    for s in snaps:
        rid = next((t[4:] for t in s.get("tags") or () if t.startswith("run-")), None)
        if rid is None or not s.get("paths"):
            continue
        r = grouped.setdefault(rid, {"run": rid, "parts": {}, "bytes": 0})
        r["parts"][s["paths"][0].lstrip("/")] = s["id"]
        r["bytes"] += (s.get("summary") or {}).get("total_bytes_processed") or 0
    for r in grouped.values():
        r["complete"] = MANIFEST in r["parts"]
    return sorted(grouped.values(), key=lambda r: r["run"])


def _forget(ids: list[str], *, prune: bool) -> None:
    if ids:
        _call(restic("forget", *(["--prune"] if prune else []), *ids), "không xóa được lượt cũ trong kho")


def keep_latest(keep: int) -> list[str]:
    """Giữ `keep` lượt đủ mới nhất, xóa mọi lượt khác (kể cả lượt hỏng giữa chừng) rồi dọn kho. Trả các lượt đã xóa."""
    all_runs = runs(snapshots())
    kept = {r["run"] for r in [r for r in all_runs if r["complete"]][-keep:]}
    drop = [r for r in all_runs if r["run"] not in kept]
    _forget([sid for r in drop for sid in r["parts"].values()], prune=True)
    return [r["run"] for r in drop]


def _init_repo(repo: pathlib.Path) -> None:
    if (repo / "config").exists():
        return
    if repo.exists() and any(repo.iterdir()):
        raise BackupError(f"{repo} đã có tệp nhưng không phải kho sao lưu — chọn thư mục trống (MOC_BACKUP_DIR)")
    repo.mkdir(mode=0o700, parents=True, exist_ok=True)     # tạo trước, để docker không tạo bằng root
    _call(restic("init"), f"không tạo được kho sao lưu ở {repo}")
    print(f"Đã tạo kho sao lưu {repo}", flush=True)


def create(keep: int | None = None) -> dict[str, Any]:
    repo = _ready(repo_exists=False)
    _init_repo(repo)
    with _guard(repo):
        _resume_left_paused()
        running = _services("running")
        if "postgres" not in running:
            raise BackupError("PostgreSQL chưa chạy — khởi động trước: make up")
        existing = {r["run"] for r in runs(snapshots())}
        rid = datetime.now().strftime("%Y%m%d-%H%M%S")
        while rid in existing:
            time.sleep(1)
            rid = datetime.now().strftime("%Y%m%d-%H%M%S")
        tags = [TAG, f"run-{rid}"]
        manifest: dict[str, Any] = {"run": rid, "version": ENV.get("MOC_VERSION") or "dev",
                                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                    "databases": {}}
        print(f"Sao lưu lượt {rid} vào {repo}", flush=True)
        # Mồi: chép volume tệp khi chưa dừng gì; lượt chính lúc tạm dừng lấy mồi làm lượt trước, chỉ đọc tệp đã đổi
        prime = _summary(_call(_backup_args(["moc-prime"], FILES), "restic không chép được volume SeaweedFS"))
        paused: list[str] = []
        held: list[str] = []
        try:
            try:
                for group, into in ((WRITERS, paused), (DB_WRITERS, held)):
                    for service in group:
                        if service in running:
                            into.append(service)    # ghi trước: bị ngắt ngay lúc pause vẫn được bỏ tạm dừng
                            _call([*COMPOSE, "pause", service], f"không tạm dừng được {service}")
                started = time.monotonic()
                manifest["audit"] = json.loads(_psql(HEAD_SQL + ";"))
                for db in _databases():
                    # -Z 0: không nén — restic tự nén, và bản dump không nén mới khử trùng lặp được giữa các lượt
                    done, code, err = _pipe(
                        [*COMPOSE, "exec", "-T", "postgres", "pg_dump", "-U", USER, "-Fc", "-Z", "0", "-d", db],
                        _backup_args(tags, "--stdin", "--stdin-filename", f"{db}.dump"))
                    if done.returncode != 0:
                        raise BackupError(f"restic không ghi được {db}.dump: {_tail(done.stderr)}")
                    if code != 0:
                        raise BackupError(f"pg_dump {db} lỗi: {_tail(err)}")
                    manifest["databases"][db] = part = _summary(done.stdout)
                    print(f"  ✓ CSDL {db}: {_size(part['bytes'])} (thêm vào kho {_size(part['added'])})", flush=True)
                manifest["db_paused_s"] = round(time.monotonic() - started, 1)
                _unpause(held)
                part = _summary(_call(_backup_args(tags, FILES), "restic không chép được volume SeaweedFS"))
                manifest["files"] = part
                print(f"  ✓ Tệp (volume SeaweedFS): {_size(part['bytes'])}"
                      f" (thêm vào kho {_size(prime['added'] + part['added'])})", flush=True)
                manifest["vault"] = part = _summary(_call(_backup_args(tags, VAULT),
                                                          "restic không chép được volume két OpenBao"))
                manifest["paused_s"] = round(time.monotonic() - started, 1)
                print(f"  ✓ Két (volume OpenBao): {_size(part['bytes'])}", flush=True)
            finally:
                _unpause(held + paused)
            _call(_backup_args(tags, "--stdin", "--stdin-filename", MANIFEST), "restic không ghi được manifest",
                  input=json.dumps(manifest, ensure_ascii=False, indent=1).encode())
        except BaseException:
            with contextlib.suppress(BackupError):    # lượt dở dang: bỏ snapshot đã ghi (dữ liệu dọn ở lần --keep sau)
                _forget([sid for r in runs(snapshots()) if r["run"] == rid for sid in r["parts"].values()],
                        prune=False)
            raise
        finally:
            with contextlib.suppress(BackupError):
                _forget([prime["snapshot"]], prune=False)
        head = manifest["audit"]
        if head["id"]:
            print(f"  ✓ Sổ kiểm toán tới dòng #{head['id']} ({head['hash'][:12]}…)")
        print(f"  · tạm dừng ghi CSDL {_seconds(manifest['db_paused_s'])}, tải tệp {_seconds(manifest['paused_s'])}")
        if keep:
            dropped = keep_latest(keep)
            print(f"  · giữ {keep} lượt mới nhất" + (f", đã xóa: {', '.join(dropped)}" if dropped else ""))
    return manifest


def _size(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.0f} B" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    raise AssertionError


def _seconds(s: float) -> str:
    return f"{s:.1f} giây".replace(".", ",")


def _when(rid: str) -> str:
    try:
        return datetime.strptime(rid, "%Y%m%d-%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return rid


def pick(all_runs: list[dict[str, Any]], rid: str | None) -> dict[str, Any]:
    if rid in (None, "latest"):
        complete = [r for r in all_runs if r["complete"]]
        if not complete:
            raise BackupError("kho chưa có lượt sao lưu nào đủ để khôi phục")
        return complete[-1]
    for r in all_runs:
        if r["run"] == rid:
            if not r["complete"]:
                raise BackupError(f"lượt {rid} hỏng giữa chừng (thiếu {MANIFEST}) — chọn lượt khác: moc backup list")
            return r
    raise BackupError(f"không có lượt {rid} — xem các lượt: python3 scripts/moc.py backup list")


def _restore_db(db: str, snapshot: str) -> None:
    """pg_restore --clean --create: bỏ CSDL đang có, tạo lại đúng như lúc dump (cả chủ sở hữu, quyền, cấu hình)."""
    for attempt in range(3):
        done, code, err = _pipe(restic("dump", snapshot, f"/{db}.dump"),
                                [*COMPOSE, "exec", "-T", "postgres", "pg_restore", "-U", USER, "--clean", "--if-exists",
                                 "--create", "--exit-on-error", "-d", "postgres"])
        if done.returncode == 0 and code == 0:
            return
        if done.returncode != 0:
            # healthcheck của postgres nối vào đúng lúc DROP DATABASE: lỗi ở câu đầu, chưa đổi gì — đợi rồi thử lại
            if b"is being accessed by other users" in done.stderr and attempt < 2:
                time.sleep(2)
                continue
            raise BackupError(f"không khôi phục được CSDL {db}: {_tail(done.stderr)}")
        raise BackupError(f"không đọc được {db}.dump trong kho: {_tail(err)}")


def _check_readable(target: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Trước khi dừng Signet: lượt còn đủ mọi phần ghi trong manifest, kho không hỏng, bản dump đọc được trọn vẹn
    (restic kiểm hash từng khối khi đọc). Hỏng thì dừng ở đây, chưa đụng tới dữ liệu đang có."""
    wanted = {f"{db}.dump": part["snapshot"] for db, part in manifest["databases"].items()}
    wanted[FILES.lstrip("/")] = manifest["files"]["snapshot"]
    if "vault" in manifest:                 # lượt sao lưu trước F3.7 chưa có két
        wanted[VAULT.lstrip("/")] = manifest["vault"]["snapshot"]
    missing = [name for name, sid in wanted.items() if target["parts"].get(name) != sid]
    if missing:
        raise BackupError(f"lượt {manifest['run']} không còn đủ phần trong kho ({', '.join(missing)}) — chọn lượt khác")
    _call(restic("check"), "kho sao lưu có lỗi, không khôi phục")
    for db, part in manifest["databases"].items():
        proc = subprocess.run(restic("dump", part["snapshot"], f"/{db}.dump"), cwd=ROOT, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise BackupError(f"không đọc được {db}.dump trong kho, không khôi phục: {_tail(proc.stderr)}")


def restore(rid: str | None, *, yes: bool = False) -> dict[str, Any] | None:
    repo = _ready()
    with _guard(repo):
        _resume_left_paused()
        target = pick(runs(snapshots()), rid)
        manifest = json.loads(_call(restic("dump", target["parts"][MANIFEST], f"/{MANIFEST}"),
                                    "không đọc được manifest"))
        head = manifest["audit"]
        print(f"Lượt {manifest['run']}, sao lưu lúc {_when(manifest['run'])} (Signet {manifest['version']}):"
              f" CSDL {', '.join(manifest['databases'])}; tệp {_size(manifest['files']['bytes'])};"
              f" {'két' if 'vault' in manifest else 'chưa có két (giữ két đang có)'};"
              f" sổ kiểm toán tới dòng #{head['id']}.")
        current = ENV.get("MOC_VERSION") or "dev"
        if manifest["version"] != current:
            print(f"  · đang chạy Signet {current}: bản mới hơn thì Hasura tự chạy migration còn thiếu khi khởi động;"
                  f" bản cũ hơn bản sao lưu thì nên cài đúng Signet {manifest['version']} trước")
        if "postgres" in _services("running"):
            extra = sorted(set(_databases()) - set(manifest["databases"]))
            if extra:
                print(f"  · CSDL không có trong bản sao lưu, giữ nguyên: {', '.join(extra)}")
        if not yes:
            if not sys.stdin.isatty():
                raise BackupError("không hỏi lại được (không chạy trên terminal): thêm --yes")
            answer = input("Signet sẽ DỪNG; CSDL và tệp hiện có bị THAY bằng bản sao lưu, mọi thay đổi sau lúc sao"
                           " lưu sẽ mất (muốn giữ trạng thái hiện tại thì make backup trước). Khôi phục? [y/N] ")
            if answer.strip().lower() not in ("y", "yes", "c", "co", "có"):
                print("Không khôi phục.")
                return None
        _check_readable(target, manifest)
        print("  ✓ Bản sao lưu đọc được trọn vẹn", flush=True)
        started = time.monotonic()
        try:
            RESTORING.write_text(f"{manifest['run']}\n", encoding="utf-8")
            _call([*COMPOSE, "down"], "không dừng được Signet")
            _call([*COMPOSE, "up", "-d", "--wait", "--wait-timeout", "300", "postgres"], "PostgreSQL không lên")
            print("  ✓ Đã dừng Signet, chỉ chạy PostgreSQL", flush=True)
            for db, part in manifest["databases"].items():
                _restore_db(db, part["snapshot"])
                print(f"  ✓ CSDL {db}", flush=True)
            if head["id"]:
                got = _psql("select encode(hash, 'hex') from core.audit_log where id = :'id';", id=str(head["id"]))
                if got != head["hash"]:
                    raise BackupError(f"CSDL vừa khôi phục không khớp manifest: dòng sổ #{head['id']} khác hash lúc"
                                      " sao lưu")
                print(f"  ✓ Sổ kiểm toán: dòng #{head['id']} khớp hash lúc sao lưu", flush=True)
            _call(restic("restore", f"{manifest['files']['snapshot']}:{FILES}", "--target", FILES, "--delete"),
                  "không khôi phục được tệp")
            print("  ✓ Tệp (volume SeaweedFS)", flush=True)
            if "vault" in manifest:
                _call(restic("restore", f"{manifest['vault']['snapshot']}:{VAULT}", "--target", VAULT, "--delete"),
                      "không khôi phục được két")
                print("  ✓ Két (volume OpenBao)", flush=True)
            try:
                actor = f"os:{getpass.getuser()}"
            except (KeyError, OSError):
                actor = "os:?"
            diff = {"run": manifest["run"], "backed_up_at": manifest["created_at"], "audit_id": head["id"],
                    "version": manifest["version"]}
            event = _psql(RESTORED_SQL, actor=actor, run=manifest["run"], diff=json.dumps(diff, ensure_ascii=False))
            print(f"  ✓ Lần khôi phục ghi vào sổ kiểm toán: dòng #{event}", flush=True)
            _call([*COMPOSE, "up", "-d", "--wait", "--wait-timeout", "600"],
                  "Signet chưa chạy lại được — xem: make logs")
            RESTORING.unlink(missing_ok=True)
        except BaseException:
            print(f"✗ Khôi phục dừng giữa chừng; Signet có thể đang dừng. Sửa lỗi bên dưới rồi chạy lại: python3"
                  f" scripts/moc.py backup restore {manifest['run']}", file=sys.stderr)
            raise
        print(f"  ✓ Signet chạy lại. Xong trong {_seconds(time.monotonic() - started)}.")
    print("Kiểm lại cả chuỗi sổ kiểm toán và mốc neo: make audit")
    return {**manifest, "restored_event": int(event)}


# --- lệnh (scripts/moc.py) -----------------------------------------------------------------------------------------

def _run(fn: Any, *args: Any, **kw: Any) -> int:
    try:
        fn(*args, **kw)
    except BackupError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\n✗ Đã dừng.", file=sys.stderr)
        return 130
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    code = _run(create, args.keep)
    if code == 0:
        print("Đã sao lưu. Xem các lượt: python3 scripts/moc.py backup list; khôi phục: make restore")
    return code


def cmd_list(args: argparse.Namespace) -> int:
    def show() -> None:
        repo = _ready()
        all_runs = runs(snapshots())
        if args.json:
            print(json.dumps({"repository": str(repo), "runs": [
                {"run": r["run"], "bytes": r["bytes"], "complete": r["complete"]} for r in all_runs]}))
            return
        print(f"Kho sao lưu {repo}: {len(all_runs)} lượt")
        for r in reversed(all_runs):
            state = "đủ" if r["complete"] else "hỏng giữa chừng, không dùng được"
            print(f"  {r['run']}  {_when(r['run'])}  {_size(r['bytes']):>10}  {state}")
    return _run(show)


def cmd_check(args: argparse.Namespace) -> int:
    def check() -> None:
        _ready()
        out = _call(restic("check"), "kho sao lưu có lỗi").decode().strip().splitlines()
        print(f"✓ Kho {repo_dir()}: {out[-1] if out else 'không thấy lỗi'}")
    return _run(check)


def cmd_restore(args: argparse.Namespace) -> int:
    return _run(restore, args.run_id, yes=args.yes)
