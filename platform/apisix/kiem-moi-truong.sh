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

if [ "${1-}" = --chi-kiem ]; then
  exit 0
fi
exec /docker-entrypoint.sh "$@"
