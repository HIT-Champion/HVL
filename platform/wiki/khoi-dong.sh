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

# Wiki nội bộ (#367): tạo hai tệp cấu hình DokuWiki cần mà image không tạo (bình thường trình cài đặt tạo, ở đây đã bỏ),
# rồi chạy entrypoint gốc của image. Chỉ tạo khi chưa có, không đụng tệp đã có.
# - users.auth.php: tài khoản plugin oauth tự thêm ở lần đăng nhập đầu. Thiếu tệp thì authplain coi như hỏng, không ai
#   đăng nhập được.
# - acl.auth.php: chưa chạy `moc wiki sync` thì không ai đọc được gì.
set -eu
mkdir -p /storage/conf
[ -e /storage/conf/users.auth.php ] \
  || printf '# Tài khoản do plugin oauth thêm khi đăng nhập bằng Keycloak (#367)\n' > /storage/conf/users.auth.php
[ -e /storage/conf/acl.auth.php ] \
  || printf '# Chưa chạy moc wiki sync: không ai đọc được gì\n*\t@ALL\t0\n' > /storage/conf/acl.auth.php
exec /dokuwiki-entrypoint.sh "$@"
