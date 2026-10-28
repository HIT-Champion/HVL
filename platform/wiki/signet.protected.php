<?php
/*
 * Copyright 2026 Signet Team
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * Cấu hình DokuWiki của Signet (#367). docker-compose.yml gắn tệp này đè lên conf/docker.protected.php của image: tệp
 * "protected" nạp sau cùng, trang quản trị của DokuWiki không ghi đè được. Giá trị lấy từ biến môi trường của
 * container, không ghi gì vào volume.
 */

// của image (conf/docker.protected.php gốc): dữ liệu nằm trong volume
$conf['savedir'] = '/storage/data';

$public = rtrim((string) getenv('MOC_PUBLIC_URL'), '/');
$realm = getenv('MOC_REALM') ?: 'moc';
// Keycloak qua APISIX trong mạng apps: container wiki không tới thẳng được Keycloak hay dịch vụ lõi nào
$internal = "http://apisix:9080/realms/$realm/protocol/openid-connect";

$conf['title'] = 'Wiki nội bộ · Signet';
$conf['lang'] = 'vi';
// URL công khai cố định, không suy từ Host; APISIX bỏ tiền tố /wiki trước khi chuyển vào container
$conf['baseurl'] = $public;
$conf['basedir'] = '/wiki/';
$conf['userewrite'] = 1;

// Quyền theo danh sách conf/acl.auth.php do `moc wiki sync` ghi: mỗi đơn vị một không gian don-vi:<mã>
$conf['useacl'] = 1;
$conf['authtype'] = 'oauth';
$conf['defaultgroup'] = 'user';
// Không ai là quản trị DokuWiki: quản trị đọc được mọi không gian, bỏ qua tách theo đơn vị
$conf['superuser'] = '!!not set!!';
$conf['manager'] = '!!not set!!';
// Tài khoản do Keycloak quản: không đăng ký, không đặt lại mật khẩu, không sửa hồ sơ trong wiki
$conf['disableactions'] = 'register,resendpwd,profile,profile_delete';
// Sơ đồ trang liệt kê cả không gian của đơn vị khác (tên của chúng vốn có ở trang đầu), không bao giờ liệt kê trang
// người xem không đọc được. Ẩn hẳn (1) thì không ai mở được không gian của mình trong sơ đồ: không gian cha don-vi
// không cấp quyền đọc cho ai, để không gian bỏ lại khi đổi mã đơn vị rơi về "không ai đọc" (scripts/wiki.py)
$conf['sneaky_index'] = 0;
// Không API từ xa; không gọi update.dokuwiki.org (mạng apps không ra Internet)
$conf['remote'] = 0;
$conf['updatecheck'] = 0;

// Đăng nhập chỉ qua Keycloak (plugin oauth, dịch vụ oauthgeneric); mỗi lần đăng nhập lấy lại nhóm (đơn vị) từ Keycloak
$conf['plugin']['oauth']['singleService'] = 1;
$conf['plugin']['oauth']['register-on-auth'] = 1;
$conf['plugin']['oauth']['overwrite-groups'] = 1;

$conf['plugin']['oauthgeneric']['key'] = 'wiki';
$conf['plugin']['oauthgeneric']['secret'] = (string) getenv('MOC_WIKI_CLIENT_SECRET');
$conf['plugin']['oauthgeneric']['authurl'] = "$public/realms/$realm/protocol/openid-connect/auth";
$conf['plugin']['oauthgeneric']['tokenurl'] = "$internal/token";
$conf['plugin']['oauthgeneric']['userurl'] = "$internal/userinfo";
$conf['plugin']['oauthgeneric']['logouturl'] = "$public/realms/$realm/protocol/openid-connect/logout";
$conf['plugin']['oauthgeneric']['authmethod'] = 1;    // token Bearer khi gọi userinfo
$conf['plugin']['oauthgeneric']['scopes'] = ['openid', 'profile', 'email'];
$conf['plugin']['oauthgeneric']['needs-state'] = 1;
$conf['plugin']['oauthgeneric']['json-user'] = 'preferred_username';
$conf['plugin']['oauthgeneric']['json-name'] = 'name';
$conf['plugin']['oauthgeneric']['json-mail'] = 'email';
// tenant_id của người dùng (mapper wiki-groups của client `wiki`, scripts/wiki.py)
$conf['plugin']['oauthgeneric']['json-grps'] = 'groups';
$conf['plugin']['oauthgeneric']['label'] = 'Signet';
$conf['plugin']['oauthgeneric']['color'] = '#1e5b4f';
