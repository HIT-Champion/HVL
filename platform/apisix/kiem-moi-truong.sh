#!/bin/sh
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

# F3.15: kiểm biến môi trường của WAF trước khi APISIX khởi động. MOC_WAF gõ sai trong .env thì Coraza không nạp được
# cấu hình và APISIX trả 503 cho MỌI yêu cầu mà lúc khởi động không báo gì — nên dừng ngay và nói rõ lỗi (container
# thoát mã 64, khởi động lại liên tục, dòng lỗi ở `docker compose logs apisix`). Đúng thì chạy tiếp entrypoint gốc
# của image APISIX. Một nguồn kiểm cho ba chỗ: `make up` (Makefile, mục env-ready) và reconciler GitOps
# (scripts/reconcile.py, trước khi dừng Signet) chạy script này trên máy chủ với `--chi-kiem` và giá trị compose sẽ
# dùng — `docker compose up --wait` không coi container khởi động lại liên tục là lỗi.
set -eu

waf=${MOC_WAF-On}
case $(printf '%s' "$waf" | tr '[:upper:]' '[:lower:]') in
  on | off | detectiononly) ;;
  *)
    echo "Signet: MOC_WAF='$waf' không hợp lệ — chỉ nhận On, DetectionOnly hoặc Off" \
      "(platform/apisix/README.md, mục WAF)" >&2
    exit 64
    ;;
esac

workers=${MOC_APISIX_WORKERS-4}
case $workers in
  auto) ;;
  '' | *[!0-9]* | 0)
    echo "Signet: MOC_APISIX_WORKERS='$workers' không hợp lệ — số worker nguyên dương hoặc auto" >&2
    exit 64
    ;;
esac

# #364: tỉ lệ truy vết 0–1 (0, 1, 0.25…). Giá trị này nằm trong global rule chung với WAF ở apisix.yaml: sai kiểu thì
# APISIX bỏ cả global rule đó — mất luôn WAF, mã yêu cầu — nên cũng dừng ngay
ratio=${MOC_TRACE_RATIO:-0}
if ! printf '%s\n' "$ratio" | grep -Eqx '0(\.[0-9]+)?|1(\.0+)?'; then
  echo "Signet: MOC_TRACE_RATIO='$ratio' không hợp lệ — số từ 0 tới 1, vd 0.1 (0: tắt truy vết)" >&2
  exit 64
fi

if [ "${1-}" = --chi-kiem ]; then
  exit 0
fi

# #211: MOC_TRUSTED_PROXY=auto tin đúng dải của mạng moc, đọc lúc container khởi động: mạng được tạo lại với dải khác
# (make down, nâng cấp, reconciler GitOps) thì giá trị vẫn đúng. moc là mạng duy nhất của APISIX có route mặc định
# (apps là internal). Proxy TLS vào cổng publish 127.0.0.1:8080 tới từ gateway của nó, cloudflared có địa chỉ trong nó;
# container ứng dụng chỉ ở mạng apps nên không giả được X-Forwarded-For. /proc/net/route ghi địa chỉ và mặt nạ bằng hex,
# byte thấp trước. Không đọc được thì dừng, không lùi về một dải rộng
if [ "${MOC_TRUSTED_PROXY-}" = auto ]; then
  dev= net=
  while read -r iface dest gw _ _ _ _ mask _; do
    if [ "$dest" = 00000000 ] && [ "$mask" = 00000000 ] && [ "$gw" != 00000000 ]; then dev=$iface; break; fi
  done < /proc/net/route
  while read -r iface dest gw _ _ _ _ mask _; do
    if [ -n "$dev" ] && [ "$iface" = "$dev" ] && [ "$gw" = 00000000 ] && [ "$mask" != 00000000 ]; then
      d=$((0x$dest)) m=$((0x$mask)) bits=0
      while [ "$m" -ne 0 ]; do bits=$((bits + (m & 1))); m=$((m >> 1)); done
      net="$((d & 255)).$((d >> 8 & 255)).$((d >> 16 & 255)).$((d >> 24 & 255))/$bits"
      break
    fi
  done < /proc/net/route
  if [ -z "$net" ]; then
    echo "Signet: MOC_TRUSTED_PROXY=auto nhưng không thấy route mặc định và dải của nó trong /proc/net/route —" \
      "APISIX phải ở mạng moc (docker-compose.yml), hoặc đặt dải cụ thể (docs/trien-khai.md mục 3)" >&2
    exit 64
  fi
  echo "Signet: MOC_TRUSTED_PROXY=auto → $net (mạng có route mặc định, $dev)" >&2
  export MOC_TRUSTED_PROXY="$net"
fi
exec /docker-entrypoint.sh "$@"
