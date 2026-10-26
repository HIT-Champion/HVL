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

"""make demo-tat-van-phong — lõi đứng được khi tắt phần Văn phòng điện tử (#302, docs/architecture.md §4.7).

Phần máy chủ của Văn phòng điện tử chạy chung tiến trình với lõi trong svc-files, svc-workflow. Màn này dựng lại hai
dịch vụ với MOC_OFFICE_ENABLED=false rồi kiểm: route và Hasura Action của Văn phòng không còn; phần lõi của make smoke
(smoke.py --chi-loi) và ứng dụng thứ hai (make demo-ca-nhan) vẫn đạt. Xong thì dựng lại hai dịch vụ theo cấu hình
thường (.env, mặc định bật), kể cả khi có bước sai, và kiểm Văn phòng trả lời lại.

Cần make seed trước. Thoát 0: đạt; 1: có bước sai hoặc không gọi được Signet.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

from moc_env import PUBLIC_URL, ROOT, HTTPError, Session, call_json

SERVICES = ("svc-files", "svc-workflow")
COMPOSE = ["docker", "compose", "--profile", "core", "--profile", "app"]
SCRIPTS = pathlib.Path(__file__).resolve().parent
# Tra băm không khớp văn bản nào: Văn phòng bật thì 200 kèm kết quả, tắt thì route không có (404)
VERIFY = f"{PUBLIC_URL}/api/verify?sha256={'0' * 64}"
MY_TASKS = "{ myTasks { id } }"


class DemoFailed(Exception):
    pass


def say(n: int, text: str) -> None:
    print(f"\n{n}. {text}")


def ok(text: str) -> None:
    print(f"   ✓ {text}")


def recreate(office: bool | None) -> float:
    """Dựng lại hai dịch vụ; office=None: theo cấu hình thường (.env, mặc định bật)."""
    env = {k: v for k, v in os.environ.items() if k != "MOC_OFFICE_ENABLED"}
    if office is not None:
        env["MOC_OFFICE_ENABLED"] = "true" if office else "false"
    started = time.monotonic()
    subprocess.run([*COMPOSE, "up", "-d", "--wait", "--wait-timeout", "300", *SERVICES], cwd=ROOT, env=env,
                   check=True, capture_output=True)
    return time.monotonic() - started


def office_flag(service: str) -> str:
    out = subprocess.run([*COMPOSE, "exec", "-T", service, "printenv", "MOC_OFFICE_ENABLED"], cwd=ROOT,
                         capture_output=True, text=True)
    return out.stdout.strip() or "(chưa đặt)"


def verify_answers() -> bool:
    try:
        call_json("GET", VERIFY)
        return True
    except HTTPError as exc:
        if exc.status == 404:
            return False
        raise


def my_tasks_errors(clerk: Session) -> list:
    data, _ = call_json("POST", f"{PUBLIC_URL}/v1/graphql", {"query": MY_TASKS}, headers=clerk.auth)
    return data.get("errors") or []


def script(name: str, *args: str) -> None:
    """Chạy một kịch bản khác của Signet, cùng môi trường; in nguyên đầu ra để thấy từng bước."""
    env = {**os.environ, "MOC_OFFICE_ENABLED": "false"}
    done = subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=ROOT, env=env)
    done.returncode == 0 or fail(f"{name} {' '.join(args)} không đạt khi đã tắt Văn phòng (mã thoát {done.returncode})")


def fail(message: str) -> None:
    raise DemoFailed(message)


def run() -> None:
    print("Tắt phần Văn phòng điện tử trong svc-files, svc-workflow — lõi vẫn chạy")
    clerk = Session("vanthu")

    say(1, "Lúc đầu Văn phòng đang bật")
    verify_answers() or fail("cổng xác thực của Văn phòng đã không trả lời từ trước (MOC_OFFICE_ENABLED=false?)")
    not my_tasks_errors(clerk) or fail("Action myTasks của Văn phòng đã lỗi từ trước")
    ok("cổng xác thực trả lời, Action myTasks chạy")

    try:
        say(2, "Dựng lại svc-files, svc-workflow với MOC_OFFICE_ENABLED=false")
        took = recreate(False)
        flags = {s: office_flag(s) for s in SERVICES}
        all(v == "false" for v in flags.values()) or fail(f"biến chưa vào container: {flags}")
        ok(f"hai dịch vụ lên lại, healthy sau {took:.0f} giây")

        say(3, "Phần của Văn phòng không còn")
        not verify_answers() or fail("tắt Văn phòng mà /api/verify vẫn trả lời")
        ok("/api/verify của Văn phòng: 404, route không được gắn")
        errors = my_tasks_errors(clerk)
        errors or fail("tắt Văn phòng mà Action myTasks vẫn chạy")
        ok(f"Hasura Action myTasks báo lỗi: svc-workflow không còn route Actions ({errors[0].get('message', '')})")
        status, _ = call_json("GET", f"{PUBLIC_URL}/api/status")
        status["status"] in ("ok", "degraded") or fail(f"/api/status: {status}")
        ok(f"/api/status vẫn trả lời ({status['status']})")

        say(4, "Phần lõi của make smoke (smoke.py --chi-loi)")
        script("smoke.py", "--chi-loi")

        say(5, "Ứng dụng thứ hai trên lõi (make demo-ca-nhan)")
        script("demo_ca_nhan.py")
    finally:
        say(6, "Dựng lại hai dịch vụ theo cấu hình thường")
        took = recreate(None)
        ok(f"lên lại sau {took:.0f} giây")

    verify_answers() or fail("dựng lại theo cấu hình thường mà cổng xác thực vẫn không trả lời")
    clerk = Session("vanthu")   # token lúc đầu có thể đã hết hạn sau hai kịch bản trên
    not my_tasks_errors(clerk) or fail("dựng lại theo cấu hình thường mà Action myTasks vẫn lỗi")
    ok("Văn phòng trả lời lại: cổng xác thực, Action myTasks")


def main() -> int:
    started = time.monotonic()
    try:
        run()
    except DemoFailed as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    except (HTTPError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f"\n✗ Không chạy được màn demo: {exc}. Signet có đang chạy và đã make seed chưa?", file=sys.stderr)
        return 1
    print(f"\nXong trong {time.monotonic() - started:.0f} giây.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
