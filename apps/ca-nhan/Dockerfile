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

# Dựng: docker build -t moc/app-ca-nhan apps/ca-nhan (ở gốc repo; compose tự làm)
# Bước 1: lấy bản dựng sẵn cho trình duyệt của oidc-client-ts và phông Be Vietnam Pro (#305) từ npm theo
# package-lock.json (không chép vào repo — PoF #5). Cùng image Node, cùng phiên bản thư viện với app-office; ứng dụng
# không có bước biên dịch nào khác.
FROM node:24.20.0-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts
# Phông: bốn độ đậm giao diện dùng (400, 500, 600, 700), kiểu thường, như theme đăng nhập (platform/keycloak/fonts/).
# CSS của gói (mỗi độ đậm ba @font-face chia theo unicode-range: latin, latin-ext, vietnamese) nối thành
# be-vietnam-pro.css, giữ nguyên nội dung; tệp woff2, woff nó trỏ tới ở files/; giấy phép SIL OFL-1.1 của gói thành
# OFL.txt. Phục vụ ở /ca-nhan/fonts/be-vietnam-pro/, index.html nạp CSS này trước style.css
RUN set -eu; p=node_modules/@fontsource/be-vietnam-pro; mkdir -p fonts/files; cp "$p/LICENSE" fonts/OFL.txt; \
    for w in 400 500 600 700; do \
      { cat "$p/$w.css"; echo; } >> fonts/be-vietnam-pro.css; \
      cp "$p"/files/be-vietnam-pro-*-"$w"-normal.woff* fonts/files/; \
    done

# Bước 2: chỉ giữ tệp tĩnh dưới /ca-nhan/, phục vụ bằng nginx không chạy quyền root (cùng image với app-office)
FROM nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/security-headers.conf /etc/nginx/security-headers.conf
COPY public/ /usr/share/nginx/html/ca-nhan/
COPY --from=build /src/node_modules/oidc-client-ts/dist/browser/oidc-client-ts.min.js /usr/share/nginx/html/ca-nhan/lib/
COPY --from=build /src/fonts/ /usr/share/nginx/html/ca-nhan/fonts/be-vietnam-pro/
ENV MOC_REALM=moc
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/ca-nhan/config.json || exit 1
