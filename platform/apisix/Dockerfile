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

# Cổng API (F1.2) kèm tường lửa ứng dụng web (F3.15): image APISIX chính thức, thêm bộ lọc coraza-proxy-wasm 0.6.0
# (Coraza v3.3.3 + OWASP CRS v4.14.0 biên dịch sẵn thành WebAssembly) và một script kiểm biến môi trường trước khi
# chạy entrypoint gốc; không sửa mã nào của hai dự án. Cấu hình vẫn gắn từ ngoài (config.yaml, apisix.yaml).
# Dựng: docker build -t moc/apisix platform/apisix (compose tự làm)

# Image của coraza-proxy-wasm chỉ có bản linux/amd64, còn tệp .wasm thì chạy trên mọi kiến trúc: kéo đúng bản đó để
# máy arm64 cũng dựng được
ARG CORAZA_PLATFORM=linux/amd64
FROM --platform=${CORAZA_PLATFORM} \
     ghcr.io/corazawaf/coraza-proxy-wasm:0.6.0@sha256:d66f944831428ea27039207fa4019bea55f9ea0a876d7b0dc8cc7c9e385fa4b1 \
     AS coraza

FROM apache/apisix:3.18.0-debian@sha256:84e6b5e787e9f889ebff88161cb9a16599bafcffa236c6b54c7f779a0655940d

COPY --from=coraza /plugin.wasm /usr/local/apisix/wasm/coraza-proxy-wasm.wasm
# Băm của coraza-proxy-wasm.wasm trong coraza-proxy-wasm-0.6.0.zip trên trang phát hành GitHub: tệp trong image và tệp
# phát hành là một (đường dẫn tính từ WORKDIR /usr/local/apisix của image gốc)
RUN echo "f36e710529167482df820b790981230092da098d26d21aebb16f1d9c8c4e26d5  wasm/coraza-proxy-wasm.wasm" \
    | sha256sum -c -

# MOC_WAF, MOC_APISIX_WORKERS sai giá trị thì dừng ngay lúc khởi động, báo rõ lỗi (không để cổng trả 503 mọi
# yêu cầu), rồi chạy entrypoint, lệnh gốc của image APISIX. Đặt ENTRYPOINT xóa CMD thừa kế nên khai lại
COPY --chmod=0755 kiem-moi-truong.sh /usr/local/bin/moc-kiem-moi-truong
ENTRYPOINT ["/usr/local/bin/moc-kiem-moi-truong"]
CMD ["docker-start"]
