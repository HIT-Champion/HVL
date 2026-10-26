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

# Dựng: docker build -t moc/keycloak-fonts platform/keycloak/fonts (ở gốc repo; compose tự làm)
# Phông Be Vietnam Pro của theme đăng nhập signet (#305): lấy từ gói npm @fontsource/be-vietnam-pro theo
# package-lock.json lúc dựng, không chép tệp phông vào repo (PoF #5). Keycloak vẫn chạy image chính thức: dịch vụ
# keycloak-fonts của docker-compose.yml chạy image này một lần trước keycloak, chép phông vào volume keycloak_fonts gắn
# vào thư mục phông của theme. Cùng image Node, cùng cách chọn tệp với app-ca-nhan (apps/ca-nhan/Dockerfile).
FROM node:24.20.0-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts
# Bốn độ đậm giao diện dùng (400, 500, 600, 700), kiểu thường. CSS của gói (mỗi độ đậm ba @font-face chia theo
# unicode-range: latin, latin-ext, vietnamese) nối thành be-vietnam-pro.css, giữ nguyên nội dung; tệp woff2, woff nó trỏ
# tới ở files/; giấy phép SIL OFL-1.1 của gói thành OFL.txt
RUN set -eu; p=node_modules/@fontsource/be-vietnam-pro; mkdir -p /fonts/files; cp "$p/LICENSE" /fonts/OFL.txt; \
    for w in 400 500 600 700; do \
      { cat "$p/$w.css"; echo; } >> /fonts/be-vietnam-pro.css; \
      cp "$p"/files/be-vietnam-pro-*-"$w"-normal.woff* /fonts/files/; \
    done

# Chỉ còn tệp phông và lệnh chép, trên cùng image Node đã ghim ở trên: không thêm image thượng nguồn nào
FROM node:24.20.0-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
COPY --from=build /fonts /fonts
COPY copy-fonts.sh /copy-fonts.sh
# Chạy user node, không root: volume keycloak_fonts tạo mới lấy chủ của thư mục gắn trong image ở lần gắn đầu, nên
# /theme-fonts thuộc node thì volume thuộc node
RUN mkdir /theme-fonts && chown node:node /theme-fonts
USER node
ENTRYPOINT ["sh", "/copy-fonts.sh"]
