#!/usr/bin/env bash
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

# In ra nội dung .env: chép mẫu, thay mỗi giá trị bắt đầu bằng change_me bằng một chuỗi ngẫu nhiên riêng
# (chỉ chữ thường và số — dùng được trong URL kết nối CSDL và tệp danh tính S3). Biến cùng tên đã đặt sẵn
# trong môi trường thì dùng giá trị đó (CI, hoặc chọn trước mật khẩu tài khoản mẫu).
# Dùng: scripts/gen-env.sh .env.example > .env
set -euo pipefail

random() { od -An -N24 -tx1 /dev/urandom | tr -d ' \n'; }

while IFS= read -r line || [ -n "$line" ]; do
  if [[ "$line" =~ ^([A-Z0-9_]+)=change_me ]]; then
    name="${BASH_REMATCH[1]}"
    printf '%s=%s\n' "$name" "${!name:-$(random)}"
  else
    printf '%s\n' "$line"
  fi
done < "${1:?Thiếu đường dẫn tệp mẫu}"
