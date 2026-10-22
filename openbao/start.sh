#!/bin/sh
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

# F3.2 — két bí mật OpenBao: chạy máy chủ (openbao.hcl) rồi cấu hình két, mỗi lần khởi động.
#
# Container chạy bằng root chỉ để chuẩn bị thư mục và ghi tệp đăng nhập cho từng dịch vụ; máy chủ chạy bằng người
# dùng openbao.
#
#   Lần đầu   init (static seal: két tự mở) → bằng token root: kv-v2 `moc/`, khóa transit `moc-files` (F3.7),
#             AppRole và policy cho từng dịch vụ, PKI nội bộ chỉ minh họa (F4.5, setup_pki), token khởi động
#             `moc-bootstrap` → thu hồi root. Khóa phục hồi và token khởi động nằm trong volume openbao_data (chỉ root
#             đọc).
#   Mỗi lần   bằng token khởi động: ghi bí mật của từng dịch vụ (lấy từ biến môi trường của riêng container này) vào
#             kv; cấp secret_id mới, ghi role_id + secret_id vào volume chỉ dịch vụ đó gắn; hủy secret_id cũ.
#
# Token khởi động không đọc thẳng được bí mật và không sửa được policy, vai trò hay cấu hình két. Nhưng nó cấp được
# secret_id, nên ai cầm nó làm được mọi việc hai dịch vụ làm được (đọc bí mật của chúng, mở khóa dữ liệu bằng
# transit): volume openbao_data phải được giữ như chính két. Đổi cấu hình két về sau (thêm khóa, policy) cần quyền
# quản trị — xem README mục Két bí mật. Vì vậy két khởi tạo trước F4.5 không tự có PKI: ký số tự tắt cho tới khi
# người quản trị nâng cấp tay hoặc dựng lại két.
set -eu

export BAO_ADDR=http://127.0.0.1:8200
DATA=/openbao/file             # volume openbao_data
KEEP=$DATA/moc                 # khóa phục hồi, token khởi động; kết quả init và token root lúc đang khởi tạo
CREDS=/run/moc                 # $CREDS/<dịch vụ>: volume tệp đăng nhập của dịch vụ đó
SERVICES="svc-files svc-workflow"
SERVICE_UID=10001              # người dùng trong image svc-*

log() { echo "moc-openbao: $*" >&2; }
die() { log "$*"; exit 1; }
# Két hỏng cấu hình mà không còn token quản trị: dựng lại từ .env (mọi bí mật dịch vụ nạp lại được; khóa transit
# thì sẽ khác)
REINIT="xóa volume openbao_data rồi khởi động lại để két khởi tạo lại từ .env (khóa transit moc-files sẽ đổi)"

# Lần khởi tạo đầu bị ngắt (container dừng giữa init và lúc có token khởi động): két chưa giữ gì ngoài cấu hình của
# chính script này, chưa dịch vụ nào dùng được → báo run xóa dữ liệu dở dang và khởi tạo lại (mã 3). Chỉ khi có dấu
# `initializing` (đặt ngay trước init, xóa khi cấu hình xong): két đã chạy thật thì không bao giờ tự xóa.
unfinished() {
  [ -e "$KEEP/initializing" ] || return 0
  log "lần khởi tạo trước bị ngắt giữa chừng — khởi tạo lại từ đầu"
  exit 3
}

# Bí mật dịch vụ cần, dạng JSON, đọc từ biến môi trường: TÊN (tên biến trong dịch vụ) hoặc TÊN=BIẾN (tên biến ở đây).
# Giá trị do `make env` sinh chỉ gồm chữ và số; vẫn thoát \ và " cho chắc.
secrets_json() {
  sep='{'
  for pair in "$@"; do
    name=${pair%%=*}
    var=${pair#*=}
    eval "value=\${$var:-}"
    [ -n "$value" ] || die "thiếu biến môi trường $var"
    printf '%s"%s":"%s"' "$sep" "$name" "$(printf %s "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    sep=','
  done
  printf '}'
}

secrets_of() {
  case $1 in
    svc-files) secrets_json SEAWEEDFS_S3_ACCESS_KEY SEAWEEDFS_S3_SECRET_KEY HASURA_ADMIN_SECRET \
                 MEILISEARCH_API_KEY=MEILI_MASTER_KEY ;;
    svc-workflow) secrets_json HASURA_ADMIN_SECRET MOC_ACTION_SECRET FLOWABLE_ADMIN_PASSWORD CENTRIFUGO_API_KEY \
                    MOC_DIRECTORY_CLIENT_SECRET ;;
    *) die "không biết dịch vụ $1" ;;
  esac
}

policy_of() {
  printf 'path "moc/data/%s" { capabilities = ["read"] }\n' "$1"
  if [ "$1" = svc-files ]; then
    # F3.7: khóa dữ liệu bọc bằng transit — chỉ xin được khóa mới và mở khóa đã bọc, không lấy được khóa gốc
    printf 'path "transit/datakey/plaintext/moc-files" { capabilities = ["update"] }\n'
    printf 'path "transit/decrypt/moc-files" { capabilities = ["update"] }\n'
    # F4.5: khóa ký văn bản của từng đơn vị — tạo, đọc, xin CSR, gắn chứng thư, ký. Không có transit/export hay
    # transit/backup nên khóa riêng không ra khỏi két. Glob cũng phủ keys/<k>/{config,rotate} (README, rủi ro)
    printf 'path "transit/keys/moc-ky-so-*" { capabilities = ["create", "read", "update"] }\n'
    printf 'path "transit/sign/moc-ky-so-*" { capabilities = ["update"] }\n'
    printf 'path "pki/sign/moc-van-thu" { capabilities = ["update"] }\n'
  fi
}

policy_bootstrap() {
  for s in $SERVICES; do
    printf 'path "moc/data/%s" { capabilities = ["create", "update"] }\n' "$s"
    printf 'path "auth/approle/role/%s/role-id" { capabilities = ["read"] }\n' "$s"
    printf 'path "auth/approle/role/%s/secret-id" { capabilities = ["update", "list"] }\n' "$s"
    printf 'path "auth/approle/role/%s/secret-id-accessor/destroy" { capabilities = ["update"] }\n' "$s"
  done
}

# bao status: 0 = mở, 2 = khóa hoặc chưa khởi tạo, 1 = chưa trả lời
status() { bao status >/dev/null 2>&1 && echo 0 || echo $?; }

wait_for() {  # $1 = "up" (trả lời) hoặc "unsealed"
  i=0
  while [ $i -lt 60 ]; do
    rc=$(status)
    if [ "$1" = up ] && [ "$rc" != 1 ]; then return 0; fi
    if [ "$rc" = 0 ]; then return 0; fi
    i=$((i + 1))
    sleep 1
  done
  [ "$1" = up ] && die "máy chủ OpenBao không trả lời sau 60 giây"
  die "két không tự mở khóa — MOC_OPENBAO_SEAL_KEY khác lúc khởi tạo két?"
}

has() { grep -q "^$1 " ; }   # dòng trong `bao secrets list` / `bao auth list` bắt đầu bằng đường gắn

# F4.5: CA nội bộ một tầng, chỉ minh họa. Khóa ký của từng đơn vị là khóa transit moc-ky-so-<đơn vị> do svc-files tạo
# khi cần; role moc-van-thu cấp chứng thư cho khóa đó, CN do svc-files đặt (tên đơn vị, cơ quan chủ quản). Không CRL,
# không OCSP (pki/config/urls để trống). Tham số gửi dạng JSON qua stdin: trường danh sách của PKI (organization…)
# tách chuỗi theo dấu phẩy, mà O có dấu phẩy. CN không phải tên miền nên không đưa vào SAN (exclude_cn_from_sans).
# Gọi sau `if` nên `set -e` không có hiệu lực ở đây: mỗi lệnh tự `|| return 1`
setup_pki() {
  bao secrets list | has pki/ || bao secrets enable pki >/dev/null || return 1
  bao secrets tune -max-lease-ttl=87600h pki/ >/dev/null || return 1
  # CA gốc tạo một lần, tên issuer cố định: có rồi thì giữ nguyên (tạo lại là đổi CA, chứng thư đã cấp thành lạ)
  bao read pki/issuer/moc-root >/dev/null 2>&1 \
    || bao write pki/root/generate/internal - >/dev/null <<'EOF' || return 1
{"issuer_name": "moc-root", "common_name": "CA nội bộ Mộc - MẪU, chỉ minh họa",
 "organization": ["Mộc - PKI nội bộ, chỉ minh họa"], "country": ["VN"],
 "key_type": "rsa", "key_bits": 4096, "ttl": "87600h", "exclude_cn_from_sans": true}
EOF
  # ghi đè cả role mỗi lần (POST thay toàn bộ, trường bỏ trống về mặc định). EKU 1.3.6.1.4.1.311.10.3.12 là Document
  # Signing (Adobe nhận ra); KU ContentCommitment (non-repudiation) là mức pyHanko đòi mặc định
  bao write pki/roles/moc-van-thu - >/dev/null <<'EOF' || return 1
{"allow_any_name": true, "enforce_hostnames": false, "cn_validations": ["disabled"],
 "use_csr_common_name": false, "use_csr_sans": false, "allow_ip_sans": false,
 "server_flag": false, "client_flag": false, "code_signing_flag": false, "email_protection_flag": false,
 "key_usage": ["DigitalSignature", "ContentCommitment"], "ext_key_usage_oids": ["1.3.6.1.4.1.311.10.3.12"],
 "organization": ["Mộc - PKI nội bộ, chỉ minh họa"], "country": ["VN"], "key_type": "rsa", "key_bits": 3072,
 "ttl": "8760h", "max_ttl": "8760h"}
EOF
}

# Lần đầu (hoặc lần trước dừng giữa chừng — token root còn lưu): cấu hình bằng token root, idempotent
setup() {
  BAO_TOKEN=$(cat "$KEEP/root-token")
  export BAO_TOKEN
  if ! bao token lookup >/dev/null 2>&1; then
    # token root đã thu hồi nhưng tệp còn (lần trước dừng ngay sau khi thu hồi)
    [ -s "$KEEP/bootstrap-token" ] \
      || { unfinished; die "token root đã mất hiệu lực trước khi cấu hình xong két: $REINIT"; }
    rm -f "$KEEP/root-token"
    unset BAO_TOKEN
    return 0
  fi
  bao secrets list | has moc/ || bao secrets enable -path=moc -version=2 kv >/dev/null
  bao write moc/config max_versions=3 >/dev/null
  bao secrets list | has transit/ || bao secrets enable transit >/dev/null
  bao read transit/keys/moc-files >/dev/null 2>&1 || bao write -f transit/keys/moc-files type=aes256-gcm96 >/dev/null
  bao auth list | has approle/ || bao auth enable approle >/dev/null
  for s in $SERVICES; do
    policy_of "$s" | bao policy write "$s" - >/dev/null
    # token dịch vụ sống 1 giờ; secret_id không hết hạn — két cấp cái mới và hủy cái cũ mỗi lần khởi động
    bao write "auth/approle/role/$s" token_policies="$s" token_ttl=1h token_max_ttl=4h secret_id_ttl=0 >/dev/null
  done
  # ký số chỉ ở mức Could: PKI lỗi thì két vẫn chạy như trước, svc-files phát hành không ký (ghi cảnh báo). Không
  # thử lại lần sau — setup chỉ chạy khi còn token root (README mục Két bí mật, nâng cấp tay)
  if setup_pki; then
    log "đã dựng PKI nội bộ (CA moc-root, role moc-van-thu) — ký số chỉ minh họa"
  else
    log "chưa dựng được PKI nội bộ — két vẫn chạy, văn bản phát hành không có chữ ký số (README mục Két bí mật)"
  fi
  policy_bootstrap | bao policy write moc-bootstrap - >/dev/null
  # token định kỳ: không hết hạn nếu được gia hạn trong một năm (mỗi lần khởi động và mỗi ngày, xem run). Chu kỳ
  # bị chặn bởi thời hạn tối đa của token/ (mặc định 32 ngày) nên nâng lên trước
  bao auth tune -max-lease-ttl=87600h token/ >/dev/null
  if [ ! -s "$KEEP/bootstrap-token" ] \
     || ! BAO_TOKEN=$(cat "$KEEP/bootstrap-token") bao token lookup >/dev/null 2>&1; then
    bao token create -orphan -policy=moc-bootstrap -period=8760h -display-name=moc-bootstrap -field=token \
      > "$KEEP/bootstrap-token.new"
    mv -f "$KEEP/bootstrap-token.new" "$KEEP/bootstrap-token"
  fi
  rm -f "$KEEP/initializing"
  # xóa tệp trước rồi mới thu hồi: dừng giữa hai bước thì chỉ còn một token root không ai cầm, không kẹt lần sau
  rm -f "$KEEP/root-token"
  bao token revoke -self >/dev/null
  unset BAO_TOKEN
  log "đã cấu hình két; token root đã thu hồi"
}

provision() {
  BAO_TOKEN=$(cat "$KEEP/bootstrap-token")
  export BAO_TOKEN
  bao token renew >/dev/null || die "token khởi động không gia hạn được (hết hạn hoặc bị thu hồi): $REINIT"
  for s in $SERVICES; do
    body=$(secrets_of "$s")
    printf '%s' "$body" | bao kv put "moc/$s" - >/dev/null
    dir=$CREDS/$s
    [ -d "$dir" ] || die "thiếu volume tệp đăng nhập $dir"
    bao read -field=role_id "auth/approle/role/$s/role-id" > "$dir/.role_id"
    new=$(bao write -f -format=json "auth/approle/role/$s/secret-id")
    printf '%s\n' "$new" | sed -n 's/.*"secret_id": *"\([^"]*\)".*/\1/p' > "$dir/.secret_id"
    accessor=$(printf '%s\n' "$new" | sed -n 's/.*"secret_id_accessor": *"\([^"]*\)".*/\1/p')
    [ -s "$dir/.role_id" ] && [ -s "$dir/.secret_id" ] && [ -n "$accessor" ] || die "không cấp được AppRole cho $s"
    chown "$SERVICE_UID" "$dir/.role_id" "$dir/.secret_id"
    chmod 400 "$dir/.role_id" "$dir/.secret_id"
    mv -f "$dir/.role_id" "$dir/role_id"
    mv -f "$dir/.secret_id" "$dir/secret_id"
    # liệt kê sau khi cấp: danh sách phải có secret_id vừa cấp — không có tức là đọc danh sách lỗi (vd mất quyền),
    # khi đó dừng thay vì để secret_id cũ (không hết hạn) tồn lại mà không ai biết
    all=$(bao list "auth/approle/role/$s/secret-id" | tail -n +3)
    printf '%s\n' "$all" | grep -qx "$accessor" || die "không đọc được danh sách secret_id của $s"
    for a in $all; do
      [ "$a" = "$accessor" ] \
        || bao write "auth/approle/role/$s/secret-id-accessor/destroy" secret_id_accessor="$a" >/dev/null
    done
  done
  unset BAO_TOKEN body new
}

configure() {
  wait_for up
  if ! bao status -format=json 2>/dev/null | grep -q '"initialized": *true'; then
    log "khởi tạo két lần đầu"
    # ghi thẳng ra tệp (umask 077): dừng ngay sau init thì lần sau vẫn đọc được token root và khóa phục hồi
    touch "$KEEP/initializing"
    bao operator init -recovery-shares=1 -recovery-threshold=1 -format=json > "$KEEP/init.json"
  fi
  if [ -s "$KEEP/init.json" ]; then
    grep -A1 '"recovery_keys_b64"' "$KEEP/init.json" | tail -n 1 | tr -d ' ",' > "$KEEP/recovery-key"
    sed -n 's/.*"root_token": *"\([^"]*\)".*/\1/p' "$KEEP/init.json" > "$KEEP/root-token"
    [ -s "$KEEP/recovery-key" ] && [ -s "$KEEP/root-token" ] \
      || { unfinished; die "không đọc được kết quả khởi tạo két"; }
    rm -f "$KEEP/init.json"
  fi
  wait_for unsealed
  [ ! -s "$KEEP/root-token" ] || setup
  [ -s "$KEEP/bootstrap-token" ] || { unfinished; die "két đã khởi tạo nhưng không có token khởi động: $REINIT"; }
  provision
  log "đã nạp bí mật và cấp AppRole cho: $SERVICES"
}

run() {
  rm -f /tmp/moc-ready
  [ -n "${MOC_OPENBAO_SEAL_KEY:-}" ] || die "thiếu MOC_OPENBAO_SEAL_KEY"
  # static seal cần đúng 32 byte: suy từ chuỗi trong .env bằng SHA-256 (64 ký tự hex)
  MOC_SEAL_KEY_HEX=$(printf %s "$MOC_OPENBAO_SEAL_KEY" | sha256sum | cut -c1-64)
  export MOC_SEAL_KEY_HEX
  umask 077
  mkdir -p "$DATA/raft" "$KEEP"
  chown openbao "$DATA" "$DATA/raft"
  chmod 700 "$KEEP"

  # PID 1 không có trap thì bỏ qua SIGTERM: đặt trap trước mọi thứ, chuyển tín hiệu cho cả máy chủ lẫn bước cấu hình
  server=
  cfg=
  stopping=
  trap 'stopping=1; for p in $cfg $server; do kill -TERM "$p" 2>/dev/null; done' TERM INT
  retried=
  while :; do
    su-exec openbao bao server -config=/moc/openbao.hcl &
    server=$!
    # tiến trình riêng: `set -e` có hiệu lực trọn vẹn bên trong (gọi hàm trong `if !` thì sh tắt -e); chạy nền để
    # tín hiệu dừng tới được ngay cả lúc đang cấu hình (sh hoãn trap tới khi lệnh chạy trước mặt xong)
    sh "$0" configure &
    cfg=$!
    set +e
    wait "$cfg"
    code=$?
    if [ -n "$stopping" ]; then
      wait "$cfg"
      wait "$server"
      exit 143
    fi
    cfg=
    [ "$code" = 3 ] && [ -z "$retried" ] || break
    # mã 3: lần khởi tạo trước bị ngắt (xem unfinished) — dừng máy chủ, xóa dữ liệu dở dang, khởi tạo lại một lần
    retried=1
    kill -TERM "$server" 2>/dev/null
    wait "$server"
    [ -z "$stopping" ] || exit 143
    set -e
    rm -rf "$DATA/raft" "$KEEP/init.json" "$KEEP/root-token" "$KEEP/recovery-key" "$KEEP/bootstrap-token" \
      "$KEEP/initializing"
    mkdir -p "$DATA/raft"
    chown openbao "$DATA/raft"
  done
  if [ "$code" != 0 ]; then
    kill -TERM "$server" 2>/dev/null
    wait "$server"
    exit 1
  fi
  touch /tmp/moc-ready
  ( while sleep 86400; do
      BAO_TOKEN=$(cat "$KEEP/bootstrap-token") bao token renew >/dev/null || log "không gia hạn được token khởi động"
    done ) &
  wait "$server"
  code=$?
  # tín hiệu dừng làm `wait` trở về sớm: trap đã chuyển TERM cho máy chủ, chờ nó tắt hẳn
  if kill -0 "$server" 2>/dev/null; then
    wait "$server"
    code=$?
  fi
  exit "$code"
}

case "${1:-run}" in
  run) run ;;
  configure) configure ;;
  *) die "dùng: start.sh [run|configure]" ;;
esac
