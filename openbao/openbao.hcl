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

# F3.2 — cấu hình máy chủ OpenBao (một nút). openbao/start.sh chạy máy chủ với tệp này rồi tự cấu hình két.

# OpenBao 2.x bỏ storage "file": raft một nút, dữ liệu trong volume openbao_data
storage "raft" {
  path    = "/openbao/file/raft"
  node_id = "moc"
}

# Chỉ trong mạng nội bộ của compose, không mở cổng ra ngoài. Chưa có TLS: token đi rõ trên mạng nội bộ đó.
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

# Static seal: khóa AES-256 (start.sh suy từ MOC_OPENBAO_SEAL_KEY) → khởi động lại là tự mở khóa, không cần người
# nhập khóa. Đổi lại: ai có khóa này (trong .env) là mở được két.
seal "static" {
  current_key_id = "moc-1"
  current_key    = "env://MOC_SEAL_KEY_HEX"
}

# Sổ truy cập két (ai đăng nhập, đọc đường nào) ra stdout — `docker compose logs openbao`. Giá trị bí mật được băm
# HMAC, không ghi rõ. OpenBao 2.x chỉ cho khai báo thiết bị audit trong tệp cấu hình, không qua API.
audit "file" "stdout" {
  options {
    file_path = "stdout"
  }
}

api_addr     = "http://openbao:8200"
cluster_addr = "http://127.0.0.1:8201"
