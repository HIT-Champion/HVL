#!/usr/bin/env bash
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

# ---------------------------------------------------------------------------
# Nâng một bản cài Signet lên bản của thư mục mã nguồn chứa tệp này; lùi về bản cũ bằng lượt sao lưu lấy ngay trước
# khi nâng; nâng tay két cũ (docs/van-hanh.md mục Nâng cấp). Người vận hành chạy trên máy chủ, job CI
# .github/workflows/nang-cap.yml chạy đúng các lệnh này trên bản cài của thẻ phát hành trước:
#
#   scripts/nang_cap.sh nang /opt/moc                        # sao lưu, dừng, cài bản này, chạy, đặt realm, kiểm
#   scripts/nang_cap.sh lui /opt/moc ~/signet-1.1.0 <lượt>   # cài lại bản cũ, khôi phục lượt sao lưu, chạy, kiểm
#   scripts/nang_cap.sh ket /opt/moc                         # két chưa có khóa moc-anchor: thêm khóa, PKI, policy
#   scripts/nang_cap.sh kiem /opt/moc                        # chỉ kiểm
#
# Nâng, lùi, nâng két dừng ở lỗi đầu tiên và in việc cần làm tiếp; phần kiểm chạy hết các mục rồi mới báo mục trượt
# (thoát 1). Dừng timer moc-reconcile trước: reconciler đưa tệp đã cài về nhánh deploy, chạy xen thì hai bên giẫm nhau.
# ---------------------------------------------------------------------------
set -Eeuo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# RAM trống tối thiểu: dựng image bản mới khi bản cũ còn chạy, rồi chạy cả hệ thống (lần nâng 1.1.0 ngày 25/10)
MIN_RAM_MB=${MOC_NANG_CAP_RAM_MB:-2000}
DEST=""
PHASE=truoc      # truoc: chưa đổi gì | giua: đã dừng trang hoặc đang cài | kiem: đã chạy, đang kiểm
NEXT=""          # lệnh nên chạy nếu dừng ở giữa
FAILS=()

usage() {
  cat >&2 <<EOF
Dùng: $0 nang <PREFIX>
      $0 lui <PREFIX> <mã nguồn bản cũ> <lượt sao lưu>
      $0 ket <PREFIX>
      $0 kiem <PREFIX>
EOF
  exit 2
}
die() { echo "nang_cap.sh: $*" >&2; exit 1; }
step() { printf '\n== %s  %s\n' "$(date +%T)" "$*"; }

on_error() {
  local rc=$?
  # lỗi trong $(…) hay ( … ) thì báo một lần ở tiến trình chính
  [ "${BASH_SUBSHELL:-0}" -eq 0 ] || exit "$rc"
  printf '\n!! DỪNG ở dòng %s (mã thoát %s), %s\n' "${BASH_LINENO[0]}" "$rc" "$(date '+%F %T')" >&2
  if [ "$PHASE" = truoc ]; then
    echo "!! Chưa dừng trang, chưa đổi gì trên ${DEST:-bản cài}." >&2
  else
    echo "!! Đã qua bước dừng trang. Đọc lỗi ở trên rồi chạy tiếp hoặc lùi:" >&2
    echo "   $NEXT" >&2
  fi
  exit "$rc"
}
trap on_error ERR

# Thư mục cài (make install đã chép vào, có .moc-install) → DEST tuyệt đối
use_install() {
  [ -n "${1:-}" ] || usage
  [ -f "$1/.moc-install" ] || die "$1 không phải bản cài Signet (không có .moc-install) — cài lần đầu: make install"
  DEST="$(cd "$1" && pwd -P)"
}

# Phiên bản make install sẽ gắn cho một thư mục mã nguồn — như src_version của scripts/install.sh (bản cũ không có
# lệnh in nó): dòng thẻ trong tệp VERSION của gói, không thì git describe; MOC_VERSION đặt tay thì lấy nó
version_of() {
  local v=""
  [ ! -f "$1/VERSION" ] || v="$(awk '/^v[0-9][0-9A-Za-z.-]*$/ { print; exit }' "$1/VERSION")"
  [ -n "$v" ] || v="$(git -C "$1" -c safe.directory="$1" describe --tags --always --dirty 2>/dev/null)" || v=dev
  echo "${MOC_VERSION:-${v#v}}"
}

installed_version() { awk '/^Signet / { print $2; exit }' "$DEST/VERSION"; }

in_dest() { (cd "$DEST" && "$@"); }

running() { docker ps -q --filter "label=com.docker.compose.project.working_dir=$DEST"; }

# Đủ RAM, không có reconciler chạy xen — kiểm trước khi đổi gì
preflight() {
  local avail
  avail=$(free -m | awk '/^Mem:/ { print $7 }')
  [ "${avail:-0}" -ge "$MIN_RAM_MB" ] \
    || die "RAM trống ${avail} MiB, dưới ${MIN_RAM_MB} MiB: chưa đổi gì (đặt MOC_NANG_CAP_RAM_MB để đổi ngưỡng)"
  # MOC_OPS_LOCKED=1: chính reconciler gọi (MOC_GITOPS_MODE=nang-cap, đang giữ khóa bản cài), timer chạy là đúng
  if [ "${MOC_OPS_LOCKED:-}" != 1 ] && command -v systemctl >/dev/null \
    && systemctl is-active --quiet moc-reconcile.timer 2>/dev/null; then
    die "moc-reconcile.timer đang chạy: dừng trước (sudo systemctl stop moc-reconcile.timer), xong việc thì bật lại"
  fi
}

# Câu SQL trên CSDL chính; người dùng và tên CSDL lấy trong container postgres ($POSTGRES_* mở rộng trong đó)
sql() {
  # shellcheck disable=SC2016
  in_dest docker compose exec -T postgres \
    sh -c 'psql -X -q -t -A -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<<"$1"
}

# Dấu dữ liệu: số người dùng, văn bản, tệp và dòng cuối sổ kiểm toán (mã:băm)
fingerprint() {
  sql "select (select count(*) from core.users) || ' ' || (select count(*) from office.documents) || ' '
       || (select count(*) from core.files) || ' '
       || coalesce((select id || ':' || encode(hash, 'hex') from core.audit_log order by id desc limit 1), '-');"
}

# Sau khi nâng: không bảng nào ít dòng đi, dòng sổ cuối lúc trước còn nguyên băm (migration không sửa sổ)
data_kept() {
  local users docs files head now_users now_docs now_files now_hash
  read -r users docs files head <<<"$1"
  read -r now_users now_docs now_files _ <<<"$(fingerprint)"
  echo "người dùng $users → $now_users, văn bản $docs → $now_docs, tệp $files → $now_files"
  [ "$now_users" -ge "$users" ] && [ "$now_docs" -ge "$docs" ] && [ "$now_files" -ge "$files" ] || return 1
  [ "$head" != - ] || return 0
  now_hash=$(sql "select encode(hash, 'hex') from core.audit_log where id = ${head%%:*};")
  echo "sổ kiểm toán dòng #${head%%:*}: ${head#*:} → ${now_hash:-mất}"
  [ "$now_hash" = "${head#*:}" ]
}

services() { in_dest docker compose ps --services --status running | sort; }

# Image dựng sẵn bản mới cần (postgres, hasura, … và image của profile thêm đang bật như tunnel, iot) mà máy chưa có:
# kéo trước khi dừng trang để lúc dừng không phải chờ tải, lỗi mạng thì dừng ở đây khi chưa đổi gì. Danh sách theo
# profile và .env của bản cài như lúc docker compose up ở đó; bỏ moc/* (vừa dựng, hoặc ot-sensor dùng lại image đó)
pull_missing() {
  local profiles images img
  profiles=$(sed -n 's/^COMPOSE_PROFILES=//p' "$DEST/.env" | tail -n 1)
  images=$(cd "$SRC" && MOC_VERSION="$1" COMPOSE_PROFILES="${profiles:-core,app}" COMPOSE_FILE=docker-compose.yml \
    docker compose --env-file "$DEST/.env" config --images)
  while read -r img; do
    case "$img" in "" | moc/*) continue ;; esac
    docker image inspect "$img" >/dev/null 2>&1 || docker pull -q "$img"
  done <<<"$images"
}

# Dịch vụ chạy trước khi nâng vẫn chạy (bản mới thêm dịch vụ thì chỉ in ra)
same_services() {
  local now missing added
  now=$(services)
  missing=$(comm -23 <(echo "$1") <(echo "$now"))
  added=$(comm -13 <(echo "$1") <(echo "$now"))
  echo "$(wc -l <<<"$now") dịch vụ chạy${added:+; thêm: $(echo "$added" | paste -sd ' ')}"
  [ -z "$missing" ] || { echo "không còn chạy: $(echo "$missing" | paste -sd ' ')"; return 1; }
}

public_url() {
  in_dest python3 -c 'import sys; sys.path.insert(0, "scripts"); from moc_env import PUBLIC_URL; print(PUBLIC_URL)'
}

check_status() {
  curl -fsS --max-time 30 "$(public_url)/api/status" | python3 -c '
import json, sys
s = json.load(sys.stdin)
print("/api/status: Signet", s.get("version"), "|", s.get("status"))
sys.exit(0 if s.get("version") == sys.argv[1] and s.get("status") in ("ok", "degraded") else 1)' "$1"
}

check_health() {
  local bad
  bad=$(in_dest docker compose ps --format '{{.Service}} {{.Health}}' | awk '$2 != "" && $2 != "healthy"')
  [ -z "$bad" ] || { echo "$bad"; return 1; }
  echo "$(running | wc -l) container chạy, không cái nào chưa khỏe"
}

check_realm() {
  in_dest python3 scripts/moc.py realm clients --dry-run --json | python3 -c '
import json, sys
r = json.load(sys.stdin)
print("client đã có:", ", ".join(r["present"]) or "không", "| còn thiếu:", ", ".join(r["created"]) or "không")
sys.exit(1 if r["created"] else 0)' || return 1
  # moc realm theme có từ 1.2.0 (#165)
  in_dest python3 scripts/moc.py realm theme --help >/dev/null 2>&1 || return 0
  in_dest python3 scripts/moc.py realm theme --dry-run --json | python3 -c '
import json, sys
r = json.load(sys.stdin)
print("theme đăng nhập:", r["current"] or "mặc định của Keycloak")
sys.exit(1 if r["action"] == "set" else 0)' || return 1
  # moc realm profile có từ bản thêm kênh SMS, Zalo (#365)
  in_dest python3 scripts/moc.py realm profile --help >/dev/null 2>&1 || return 0
  in_dest python3 scripts/moc.py realm profile --dry-run --json | python3 -c '
import json, sys
r = json.load(sys.stdin)
print("user profile còn thiếu:", ", ".join(r["added"]) or "không")
sys.exit(1 if r["added"] else 0)'
}

# smoke trượt ở bước hỏi đáp khi máy quá tải: chữ của PDF chưa kịp vào chỉ mục trong hạn chờ (lần nâng 1.1.0 ngày
# 25/10). Thử lại MỘT lần, chỉ khi đúng lỗi đó, và in rõ đây là lần thử lại
check_smoke() {
  local log rc=0
  log=$(mktemp)
  in_dest python3 scripts/smoke.py 2>&1 | tee "$log" || rc=$?
  if [ "$rc" -ne 0 ] && grep -q '✗ .*trợ lý chưa trả câu trích' "$log"; then
    echo "smoke trượt ở bước hỏi đáp (chữ chưa kịp vào chỉ mục) — THỬ LẠI một lần"
    rc=0
    in_dest python3 scripts/smoke.py || rc=$?
  fi
  rm -f "$log"
  return "$rc"
}

check() {
  local name=$1
  shift
  step "Kiểm: $name"
  if "$@"; then echo "-> đạt"; else echo "-> TRƯỢT"; FAILS+=("$name"); fi
}

kiem_all() {
  check "phiên bản $1 trên trang trạng thái" check_status "$1"
  check "dịch vụ khỏe" check_health
  check "client, theme, user profile của realm" check_realm
  check "sổ kiểm toán, mốc neo" in_dest python3 scripts/moc.py audit verify
  check "smoke" check_smoke
}

report() {
  printf '\n== %s  ' "$(date +%T)"
  if [ ${#FAILS[@]} -eq 0 ]; then
    echo "Mọi mục kiểm đều đạt."
  else
    echo "Trượt: $(printf '%s; ' "${FAILS[@]}")"
    [ -z "$NEXT" ] || echo "Muốn lùi: $NEXT"
    return 1
  fi
}

anchor_key() {
  local pem
  pem=$(curl -fsS --max-time 30 "$(public_url)/api/verify/anchor-key.pem" 2>/dev/null) || return 1
  [[ $pem == *"BEGIN PUBLIC KEY"* ]]
}

do_nang() {
  use_install "${1:-}"
  local old new run before svcs
  old=$(installed_version)
  new=$(version_of "$SRC")
  [ "$new" != dev ] || die "không biết phiên bản của $SRC (không có tệp VERSION, không phải git): đặt MOC_VERSION"
  [ -n "$(running)" ] || die "Signet không chạy từ $DEST: cần bản đang chạy để sao lưu bằng chính nó"
  preflight
  step "Nâng $DEST: Signet $old → $new (mã nguồn $SRC)"

  step "Dựng image $new, kéo image dựng sẵn máy chưa có, khi trang còn chạy"
  [ -f "$SRC/.env" ] || (cd "$SRC" && make env)
  (cd "$SRC" && MOC_VERSION="$new" docker compose --profile core --profile app build)
  pull_missing "$new"

  step "Sao lưu bằng bản đang chạy ($old)"
  before=$(fingerprint)
  svcs=$(services)
  in_dest python3 scripts/moc.py backup create
  in_dest python3 scripts/moc.py backup check
  run=$(in_dest python3 scripts/moc.py backup list --json | python3 -c '
import json, sys
print(max(r["run"] for r in json.load(sys.stdin)["runs"] if r["complete"]))')
  install -m 600 "$DEST/.env" "$DEST/.env.truoc-$run"
  echo "lượt sao lưu $run; .env lúc trước: $DEST/.env.truoc-$run"

  PHASE=giua
  NEXT="$0 lui $DEST <mã nguồn Signet $old> $run"
  step "Dừng trang"
  in_dest docker compose down
  step "Cài $new"
  (cd "$SRC" && MOC_VERSION="$new" make install PREFIX="$DEST")
  step "Chạy (Hasura áp migration mới)"
  in_dest docker compose up -d --wait --wait-timeout 900
  step "Client ứng dụng, theme đăng nhập, user profile của realm"
  in_dest python3 scripts/moc.py realm clients
  in_dest python3 scripts/moc.py realm theme
  in_dest python3 scripts/moc.py realm profile

  PHASE=kiem
  trap - ERR
  check "dữ liệu còn đủ" data_kept "$before"
  check "dịch vụ chạy như trước" same_services "$svcs"
  kiem_all "$new"
  anchor_key || echo "Két khởi tạo trước khi có khóa ký mốc neo: mốc neo chưa có chữ ký. Nâng két (dừng timer" \
    "reconciler trước): $0 ket $DEST"
  report
  echo "$DEST/.env.truoc-$run là bản sao .env cũ, có bí mật: không cần lùi nữa thì xóa."
}

do_lui() {
  use_install "${1:-}"
  [ -n "${2:-}" ] && [ -n "${3:-}" ] || usage
  [ -f "$2/scripts/install.sh" ] || die "$2 không phải thư mục mã nguồn Signet (thiếu scripts/install.sh)"
  local old_src run=$3 ver
  old_src="$(cd "$2" && pwd -P)"
  ver=$(version_of "$old_src")
  [ "$ver" != dev ] || die "không biết phiên bản của $old_src (gói cũ chưa có tệp VERSION): đặt MOC_VERSION," \
    "vd. MOC_VERSION=1.1.0 $0 lui $*"
  in_dest python3 scripts/moc.py backup list --json | python3 -c '
import json, sys
sys.exit(0 if any(r["run"] == sys.argv[1] and r["complete"] for r in json.load(sys.stdin)["runs"]) else 1)' "$run" \
    || die "kho sao lưu của $DEST không có lượt $run trọn vẹn (python3 scripts/moc.py backup list)"
  preflight
  step "Lùi $DEST: Signet $(installed_version) → $ver, khôi phục lượt $run"

  PHASE=giua
  NEXT="$0 lui $DEST $old_src $run   # chạy lại được"
  [ -f "$old_src/.env" ] || (cd "$old_src" && make env)
  step "Dừng trang"
  in_dest docker compose down
  step "Cài lại $ver"
  (cd "$old_src" && MOC_VERSION="$ver" make install PREFIX="$DEST")
  step "Khôi phục lượt $run: dừng, thay CSDL, tệp, két rồi chạy lại"
  in_dest python3 scripts/moc.py backup restore "$run" --yes

  PHASE=kiem
  NEXT=""
  trap - ERR
  kiem_all "$ver"
  report
}

# Listener tạm chỉ nghe trong container, bật lại endpoint tạo token root bằng khóa phục hồi (OpenBao tắt mặc định từ
# 2.5.3; `bao operator generate-root` từ 2.6 cần sẵn token nên không dùng được)
LISTENER='
# tạm cho scripts/nang_cap.sh ket — gỡ ngay sau khi tạo xong token root
listener "tcp" {
  address                                  = "127.0.0.1:8210"
  tls_disable                              = true
  disable_unauthed_generate_root_endpoints = false
}'

# Chạy trong container openbao: tạo token root bằng khóa phục hồi, ghi vào root-token cạnh khóa phục hồi. Khóa phục
# hồi, mã OTP, token chỉ đi qua tệp tạm (quyền 600) và stdin, không qua tham số dòng lệnh (ps nhìn thấy); bước nào
# không ra giá trị thì dừng, không ghi root-token rỗng
# shellcheck disable=SC2016
GEN_ROOT='
set -eu; umask 077
A=http://127.0.0.1:8210/v1/sys/generate-root; K=/openbao/file/moc
get() { sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p"; }
init=$(wget -qO- --post-data "{}" $A/attempt)
otp=$(echo "$init" | get otp); nonce=$(echo "$init" | get nonce)
[ -n "$otp" ] && [ -n "$nonce" ] || { echo "không mở được lượt tạo token root (đang có lượt dở?)"; exit 1; }
printf "{\"key\":\"%s\",\"nonce\":\"%s\"}" "$(cat $K/recovery-key)" "$nonce" > $K/.generate-root
enc=$(wget -qO- --post-file $K/.generate-root $A/update | get encoded_token); rm -f $K/.generate-root
[ -n "$enc" ] || { echo "két không nhận khóa phục hồi"; exit 1; }
printf "{\"encoded_token\":\"%s\",\"otp\":\"%s\"}" "$enc" "$otp" |
  bao write -field=token sys/decode-token - > $K/root-token.new
[ -s $K/root-token.new ] && mv $K/root-token.new $K/root-token'

# Két không tự cấu hình xong thì token root vừa tạo nằm lại trong volume. Lệnh thu hồi và xóa, chạy trong thư mục bản
# cài; cùng thứ tự với start.sh: xóa tệp trước rồi mới thu hồi (dừng giữa hai bước thì chỉ còn token không ai cầm)
ROOT_TOKEN=/openbao/file/moc/root-token
DROP_ROOT="docker compose exec openbao sh -c 't=\$(cat $ROOT_TOKEN) && rm $ROOT_TOKEN"
DROP_ROOT+=" && BAO_TOKEN=\$t bao token revoke -self'"

HCL=""
HCL_SAVED=""

# Gỡ listener tạm (trả openbao.hcl về đúng bản đã cài) và khởi động lại két. Lỗi giữa chừng thì hủy lượt tạo token
# root còn dở trước, để chạy lại được
restore_hcl() {
  [ -n "$HCL_SAVED" ] || return 0
  if [ "${1:-}" = loi ]; then
    in_dest docker compose exec -T -e BAO_ADDR=http://127.0.0.1:8210 openbao \
      bao delete sys/generate-root/attempt >/dev/null 2>&1 || true
  fi
  cat "$HCL_SAVED" > "$HCL"
  rm -f "$HCL_SAVED"
  HCL_SAVED=""
  in_dest docker compose restart openbao
  in_dest docker compose up -d --wait --wait-timeout 300
}

do_ket() {
  use_install "${1:-}"
  [ -n "$(running)" ] || die "Signet không chạy từ $DEST"
  preflight
  if anchor_key; then
    echo "Két đã có khóa moc-anchor (/api/verify/anchor-key.pem trả khóa công khai): không cần nâng."
    return 0
  fi
  step "Nâng két của $DEST: khóa ký mốc neo moc-anchor, PKI nội bộ, policy mới của svc-files"
  HCL="$DEST/platform/openbao/openbao.hcl"
  HCL_SAVED=$(mktemp)
  cp "$HCL" "$HCL_SAVED"
  PHASE=giua
  NEXT="$0 ket $DEST   # lúc thoát đã gỡ listener tạm, hủy lượt tạo token root còn dở"
  trap 'restore_hcl loi' EXIT

  step "Thêm listener tạm, khởi động lại két"
  printf '%s\n' "$LISTENER" >> "$HCL"
  in_dest docker compose restart openbao
  in_dest docker compose up -d --wait --wait-timeout 300 openbao

  step "Tạo token root bằng khóa phục hồi"
  in_dest docker compose exec -T openbao sh -c "$GEN_ROOT"

  step "Gỡ listener tạm; két thấy token root thì cấu hình lại rồi thu hồi token"
  local since logs
  since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  restore_hcl
  trap - EXIT
  # đọc hết nhật ký rồi mới tìm: `logs | grep -q` dưới pipefail hỏng khi grep thoát sớm (docker nhận SIGPIPE)
  logs=$(in_dest docker compose logs --since "$since" openbao 2>/dev/null) || true
  grep 'moc-openbao:' <<<"$logs" || true
  grep -q 'token root đã thu hồi' <<<"$logs" || die "két chưa báo cấu hình xong (docker compose logs openbao)." \
    "Token root vừa tạo còn trong két: sửa lỗi rồi chạy lại ket; dừng hẳn thì thu hồi và xóa, trong $DEST: $DROP_ROOT"
  in_dest docker compose exec -T openbao sh -c "test ! -e $ROOT_TOKEN" \
    || die "tệp root-token vẫn còn trong két; thu hồi và xóa, trong $DEST: $DROP_ROOT"

  step "svc-files đọc lại khóa ký mốc neo"
  in_dest docker compose restart svc-files
  in_dest docker compose up -d --wait --wait-timeout 300
  local i
  for i in $(seq 1 30); do anchor_key && break; sleep 2; done
  anchor_key || die "/api/verify/anchor-key.pem chưa trả khóa công khai sau $((i * 2)) giây"
  PHASE=kiem
  echo "Đã nâng két: /api/verify/anchor-key.pem ra khóa công khai; svc-files ký mốc neo từ lượt neo kế tiếp."
}

do_kiem() {
  use_install "${1:-}"
  [ -n "$(running)" ] || die "Signet không chạy từ $DEST"
  trap - ERR
  kiem_all "$(installed_version)"
  report
}

case "${1:-}" in
  nang) do_nang "${2:-}" ;;
  lui) shift; do_lui "$@" ;;
  ket) do_ket "${2:-}" ;;
  kiem) do_kiem "${2:-}" ;;
  *) usage ;;
esac
