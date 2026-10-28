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

# Wiki nội bộ (#367, profile wiki): image chính thức của DokuWiki ghim digest cộng nguyên bản hai plugin đăng nhập
# OAuth của CosmoCode (GPL-2.0) ghim commit và băm, không sửa mã của dự án nào. Plugin chép vào lib/plugins.core: image
# coi như plugin đi kèm, mỗi lần khởi động gắn lại vào volume nên không bao giờ cũ (README của image).
# oauth b709c33 (21/10/2026) theo ngoại lệ vá bảo mật của DEPENDENCIES.md: bản trước 18/10 cho ai biết email của một
# người làm được cookie đăng nhập thay người đó.
FROM dokuwiki/dokuwiki:2026-07-14c@sha256:8f77037a8a643ee0bf5545d3127d49e5e5ff7ea6d942b864d8fa0d15ea4c8cdd

ARG OAUTH=b709c33bbca80ca4eccb1c761c53386bcaa80c14
ARG OAUTH_SHA256=063e57c2fb3f8b1821309babdcc9c350e8b12c1bd1d6a3fc68c60008a8098856
ARG OAUTHGENERIC=b5a56539fa613753e7163ae291ba7b759033040f
ARG OAUTHGENERIC_SHA256=a52e7f5ac0ac92ee9fc5ca76bd94f171e7e62658383b96d817f6f9966709acec

# Sau hai plugin: bỏ install.php (trình cài đặt đặt được tài khoản quản trị; bản cài này cấu hình bằng tệp); đổi chủ
# /storage sang user 33 (www-data) để container chạy hẳn bằng user đó, không qua root — volume mới lấy chủ của thư mục
# trong image (BuildKit giữ thay đổi sau VOLUME của image gốc)
RUN set -eu; cd /tmp; \
    for p in "oauth $OAUTH $OAUTH_SHA256" "oauthgeneric $OAUTHGENERIC $OAUTHGENERIC_SHA256"; do \
      set -- $p; \
      curl -fsSL --retry 5 -o "$1.tgz" "https://github.com/cosmocode/dokuwiki-plugin-$1/archive/$2.tar.gz"; \
      echo "$3  $1.tgz" | sha256sum -c -; \
      mkdir "/var/www/html/lib/plugins.core/$1"; \
      tar xzf "$1.tgz" --strip-components 1 -C "/var/www/html/lib/plugins.core/$1"; \
      rm "$1.tgz"; \
    done; \
    rm /var/www/html/install.php; \
    chown 33:33 /storage

COPY --chmod=0755 khoi-dong.sh /usr/local/bin/moc-wiki-khoi-dong
USER 33:33
ENTRYPOINT ["/usr/local/bin/moc-wiki-khoi-dong"]
