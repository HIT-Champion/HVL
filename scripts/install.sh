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
# Cài Signet ra ngoài thư mục mã nguồn (tiêu chí PoF #4): dựng image của đội gắn thẻ phiên bản, chép
# docker-compose.yml cùng mọi tệp cấu hình mà container gắn vào sang PREFIX, rồi kiểm tra bản cài
# không còn trỏ về thư mục mã nguồn. Sau đó xóa cả thư mục mã nguồn đi hệ thống vẫn chạy:
#
#   make install PREFIX=/opt/moc       # = scripts/install.sh install /opt/moc
#   cd /opt/moc && docker compose up -d --wait
#   make uninstall PREFIX=/opt/moc     # gỡ tệp đã cài, giữ .env và dữ liệu
#
# Cài lại vào PREFIX đã có là nâng cấp: thay compose, cấu hình, image; giữ .env của PREFIX, chỉ đổi
# MOC_VERSION. Phiên bản lấy từ tệp VERSION của gói .tar.gz (git archive điền), không thì `git describe`; đặt tay
# bằng MOC_VERSION=0.1.0 (vd. gói cũ chưa có VERSION).
# ---------------------------------------------------------------------------
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
COMPOSE=(docker compose --profile core --profile app)
# Danh sách tệp do bản cài quản lý — lần cài sau và lệnh gỡ chỉ xóa đúng những tệp này
MANIFEST=.moc-install
# Ngoài các bind mount (đọc tự động từ compose): script nạp dữ liệu mẫu, kiểm tra nhanh, mã TOTP mẫu, lệnh moc.py (cả
# sao lưu, thêm đơn vị, client ứng dụng của realm, kiểm chữ ký mốc neo), màn demo (demo.py và lô mẫu nap_lo_mau.py nó
# import, demo_ca_nhan.py, demo_tat_van_phong.py), reconciler GitOps (reconcile.py), cảm biến giả lập của profile iot
# (compose chỉ đọc ở đây profile core, app nên không thấy bind mount của nó), log tập trung của profile logs (cấu hình
# Vector, tệp compose phủ, lệnh chuẩn bị và tra Parseable), cắm ứng dụng bằng manifest (moc app: ung_dung.py, bộ đọc
# YAML, JSON Schema của manifest), cấu hình Jaeger của profile trace (#364). Không chép apps/: gói ứng dụng nằm ngoài
# lõi, nên demo.py cai-ung-dung, quy-trinh chỉ chạy trong thư mục mã nguồn
RUNTIME=(scripts/moc_env.py scripts/seed.py scripts/seed_documents.py scripts/smoke.py scripts/totp.py
         scripts/moc.py scripts/audit_chain.py scripts/anchor_sig.py scripts/backup.py scripts/tenants.py
         scripts/demo.py scripts/nap_lo_mau.py scripts/reconcile.py scripts/realm_clients.py scripts/demo_ca_nhan.py
         scripts/demo_tat_van_phong.py
         seed services/ot-sensor/sensor.py
         platform/logs/vector.yaml platform/logs/docker-compose.logs.yml scripts/log_tap_trung.py
         scripts/ung_dung.py scripts/yaml_nho.py scripts/app-manifest.schema.json
         platform/trace/jaeger.yaml)

die() { echo "install.sh: $*" >&2; exit 1; }

# PREFIX tuyệt đối, đã chuẩn hóa; không phải / và không nằm trong thư mục mã nguồn
prefix() {
  local p
  case "${1:-}" in /*) ;; *) die "PREFIX phải là đường dẫn tuyệt đối, vd. PREFIX=/opt/moc (đang là '${1:-}')" ;; esac
  p="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1")"
  [ "$p" != / ] || die "PREFIX không được là /"
  case "$p/" in "$SRC"/*) die "PREFIX nằm trong thư mục mã nguồn — chọn nơi khác" ;; esac
  echo "$p"
}

# Gói .tar.gz mang sẵn phiên bản ở dòng cuối tệp VERSION (git archive điền thẻ, .gitattributes export-subst); bản clone
# git giữ nguyên mẫu ở dòng đó nên lấy bằng git describe
src_version() {
  local v=""
  [ ! -f "$SRC/VERSION" ] || v="$(awk '/^v[0-9][0-9A-Za-z.-]*$/ { print; exit }' "$SRC/VERSION")"
  [ -n "$v" ] || v="$(git -C "$SRC" -c safe.directory="$SRC" describe --tags --always --dirty 2>/dev/null)" || v=dev
  echo "${v#v}"
}

# Đọc cấu hình compose đã phân giải của một thư mục (docker-compose.yml + .env), in mỗi dòng:
#   BUILD <dịch vụ>        dịch vụ còn phải dựng từ mã nguồn
#   BIND <đường dẫn>       bind mount, tương đối với thư mục đó
#   OUTSIDE <đường dẫn>    bind mount trỏ ra ngoài thư mục đó
# Bỏ qua .moc-apps/: tệp chạy của ứng dụng cài bằng moc app (tệp phủ trong COMPOSE_FILE) là trạng thái của từng thư mục
# chạy, không phải cấu hình lõi để chép
inspect_compose() {
  (cd "$1" && "${COMPOSE[@]}" config --format json) | python3 -c '
import json, os, sys
root = os.path.realpath(sys.argv[1])
for name, svc in json.load(sys.stdin)["services"].items():
    if "build" in svc:
        print("BUILD", name)
    for vol in svc.get("volumes", []):
        if vol.get("type") == "bind":
            rel = os.path.relpath(os.path.realpath(vol["source"]), root)
            if rel == ".moc-apps" or rel.startswith(".moc-apps/"):
                continue
            print("OUTSIDE" if rel == ".." or rel.startswith("../") else "BIND", rel)
' "$1"
}

# Mỗi lúc một lệnh vận hành trên một bản cài: reconciler (scripts/reconcile.py) và `moc backup` giữ cùng khóa này
# (flock trên thư mục cài). Reconciler gọi install.sh khi đã giữ khóa thì đặt MOC_OPS_LOCKED=1.
lock_dest() {
  [ "${MOC_OPS_LOCKED:-}" != 1 ] || return 0
  command -v flock >/dev/null || return 0
  exec 9<"$1"
  flock -n 9 || die "đang có lệnh khác trên $1 (reconciler, sao lưu hoặc khôi phục) — đợi xong; bảo trì tay thì dừng timer trước: systemctl stop moc-reconcile.timer"
}

# Container đang chạy mà compose khởi động từ thư mục này
running_from() {
  docker ps -q --filter "label=com.docker.compose.project.working_dir=$1"
}

# Xóa các tệp lần cài trước đã chép (theo MANIFEST); không đụng .env. keep: giữ chính tệp MANIFEST
# Thư mục cha còn rỗng thì bỏ luôn: bản cài theo bố cục cũ (auth/, gateway/… trước khi dời vào platform/) không để
# lại thư mục trống
remove_managed() {
  local dest=$1 keep=${2:-} rel dir
  [ -f "$dest/$MANIFEST" ] || return 0
  while IFS= read -r rel; do
    case "$rel" in "" | . | .env | /* | .. | ../* | */../* | */..) die "đường dẫn lạ trong $dest/$MANIFEST: '$rel'" ;; esac
    rm -rf -- "${dest:?}/$rel"
    dir=$(dirname -- "$rel")
    while [ "$dir" != . ] && rmdir -- "$dest/$dir" 2>/dev/null; do dir=$(dirname -- "$dir"); done
  done < "$dest/$MANIFEST"
  [ -n "$keep" ] || rm -f -- "$dest/$MANIFEST"
}

# Ghi MANIFEST cả tệp một lần (tệp tạm rồi đổi tên)
write_manifest() {
  cat > "$1/$MANIFEST.tmp" && mv -f -- "$1/$MANIFEST.tmp" "$1/$MANIFEST"
}

# Đặt KHÓA=giá trị trong tệp .env: thay dòng đang có, không thì thêm vào cuối. Ghi đè nội dung tại chỗ
# để giữ nguyên quyền của tệp.
set_env() {
  local tmp
  tmp="$(umask 077 && mktemp)"
  awk -v k="$2" -v v="$3" 'index($0, k "=") == 1 { print k "=" v; done = 1; next } { print }
                           END { if (!done) print k "=" v }' "$1" > "$tmp"
  cat "$tmp" > "$1" && rm -f "$tmp"
}

do_install() {
  local dest ver mounts check rel img
  dest="$(prefix "${1:-}")"
  [ -f "$SRC/.env" ] || die "chưa có $SRC/.env — chạy: make env"
  [ -d "$dest" ] || mkdir -p "$dest"
  lock_dest "$dest"
  # .env và kho sao lưu (backups/) được giữ lại khi gỡ: cài lại vào đó vẫn được
  local leftover='\.env|backups|\.moc-install\.tmp|\.moc-apps'
  if [ ! -f "$dest/$MANIFEST" ] && [ -n "$(ls -A "$dest" | grep -vxE "$leftover" || true)" ]; then
    die "$dest đã có tệp nhưng không phải bản cài Signet — chọn thư mục trống hoặc chưa có"
  fi
  # Thay thư mục cấu hình dưới container đang chạy thì container còn giữ thư mục cũ đã xóa
  if [ -n "$(running_from "$dest")" ]; then
    die "Signet đang chạy từ $dest — dừng trước (cd $dest && docker compose down), cài lại rồi chạy lại"
  fi
  ver="${MOC_VERSION:-$(src_version)}"
  [[ "$ver" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || die "phiên bản '$ver' không dùng làm thẻ image được"

  mounts="$(inspect_compose "$SRC")" || die "docker-compose.yml trong $SRC không hợp lệ"
  if grep '^OUTSIDE' <<<"$mounts" >&2; then die "có bind mount trỏ ra ngoài thư mục mã nguồn"; fi

  echo "==> Dựng image của đội, thẻ $ver"
  (cd "$SRC" && MOC_VERSION="$ver" "${COMPOSE[@]}" build)

  local files=()
  while IFS= read -r rel; do files+=("$rel"); done \
    < <({ awk '$1 == "BIND" { print $2 }' <<<"$mounts"; printf '%s\n' "${RUNTIME[@]}"; } | sort -u)
  # Kiểm hết trước khi xóa gì ở bản cài
  for rel in "${files[@]}"; do
    [ "$rel" != . ] || die "không chép cả thư mục mã nguồn"
    [ -e "$SRC/$rel" ] || die "thiếu $SRC/$rel (bind mount trong compose hoặc tệp chạy) — tệp có trong git chưa?"
  done

  echo "==> Chép compose và cấu hình vào $dest"
  # Bị ngắt giữa chừng (mất điện, hết đĩa) thì MANIFEST vẫn liệt kê đủ tệp cũ lẫn mới: cài lại là dọn và chép lại
  { [ ! -f "$dest/$MANIFEST" ] || cat "$dest/$MANIFEST"
    printf '%s\n' docker-compose.yml VERSION scripts/__pycache__ "${files[@]}"; } | sort -u | write_manifest "$dest"
  remove_managed "$dest" keep
  for rel in "${files[@]}"; do
    mkdir -p "$dest/$(dirname "$rel")"
    rm -rf -- "${dest:?}/$rel"
    cp -R -- "$SRC/$rel" "$dest/$rel"
  done
  # Image của đội đã dựng ở trên: bỏ `build:` và cấm tải, để thiếu image thì báo lỗi chứ không kéo nhầm
  # một image cùng tên trên registry
  { echo "# Sinh bởi make install (Signet $ver) — đừng sửa tay: sửa trong mã nguồn rồi cài lại."
    sed -E 's#^( +)build: .+$#\1pull_policy: never#' "$SRC/docker-compose.yml"
  } > "$dest/docker-compose.yml"
  printf 'Signet %s\nmã nguồn: %s\ncài lúc: %s\n' "$ver" \
    "$(git -C "$SRC" -c safe.directory="$SRC" rev-parse --short HEAD 2>/dev/null || echo không-rõ)" \
    "$(date +%Y-%m-%dT%H:%M:%S%z)" > "$dest/VERSION"
  # __pycache__: do python3 scripts/seed.py tạo ra khi chạy từ bản cài
  printf '%s\n' docker-compose.yml VERSION scripts/__pycache__ "${files[@]}" | write_manifest "$dest"

  if [ -f "$dest/.env" ]; then
    echo "    .env: giữ bản đang có trong $dest"
  else
    (umask 077 && cp "$SRC/.env" "$dest/.env")
    echo "    .env: chép từ thư mục mã nguồn (chỉ chủ sở hữu đọc được)"
  fi
  grep -q '^MOC_VERSION=' "$dest/.env" || printf '\n# Do make install đặt: thẻ image của đội và profile chạy mặc định\n' >> "$dest/.env"
  set_env "$dest/.env" MOC_VERSION "$ver"
  # profile thêm (MOC_EXTRA_PROFILES của bản cài, vd tunnel) chạy cùng mỗi lần docker compose up trong bản cài
  extra="$(sed -n 's/^MOC_EXTRA_PROFILES=//p' "$dest/.env" | tail -n 1 | tr -d ' ')"
  set_env "$dest/.env" COMPOSE_PROFILES "core,app${extra:+,$extra}"
  # Log tập trung (F3.14, profile logs): tệp phủ đổi driver log của 9 dịch vụ. docker compose đọc COMPOSE_FILE trong
  # .env của bản cài (reconciler, lệnh gõ tay); bỏ logs thì trả về chỉ docker-compose.yml
  if [[ ",$extra," == *,logs,* ]]; then
    set_env "$dest/.env" COMPOSE_FILE docker-compose.yml:platform/logs/docker-compose.logs.yml
  elif grep -q '^COMPOSE_FILE=' "$dest/.env"; then
    set_env "$dest/.env" COMPOSE_FILE docker-compose.yml
  fi
  # Ứng dụng cài bằng moc app (docs/them-ung-dung.md): dựng lại tệp chạy từ lõi vừa chép và bản ghi trong .moc-apps/ của
  # bản cài (không cần CSDL), thêm lại tệp phủ vào COMPOSE_FILE. Đang giữ khóa của bản cài: MOC_OPS_LOCKED
  if [ -d "$dest/.moc-apps/apps" ]; then
    echo "==> Dựng lại tệp chạy của ứng dụng cài thêm (.moc-apps)"
    (cd "$dest" && MOC_OPS_LOCKED=1 python3 scripts/moc.py app sync --files) \
      || die "không dựng lại được tệp của ứng dụng cài thêm — xem lỗi ở trên"
  fi

  echo "==> Kiểm tra bản cài không cần thư mục mã nguồn"
  check="$(inspect_compose "$dest")" || die "compose trong $dest không hợp lệ"
  if grep '^BUILD' <<<"$check" >&2; then die "còn dịch vụ phải dựng từ mã nguồn"; fi
  if grep '^OUTSIDE' <<<"$check" >&2; then die "có bind mount trỏ ra ngoài $dest"; fi
  while read -r _ rel; do
    [ -e "$dest/$rel" ] || die "thiếu $dest/$rel"
  done < <(grep '^BIND' <<<"$check")
  # Thẻ image đúng như lúc chạy từ bản cài (MOC_VERSION trong .env vừa ghi). Đặt lại biến: make install truyền
  # MOC_VERSION rỗng, mà compose ưu tiên biến môi trường đã đặt — kể cả rỗng — hơn .env, nên sẽ tìm thẻ dev (#186)
  while read -r img; do
    case "$img" in moc/*) docker image inspect "$img" >/dev/null 2>&1 || die "thiếu image $img" ;; esac
  done < <(cd "$dest" && MOC_VERSION="$ver" "${COMPOSE[@]}" config --images)

  cat <<EOF
Đã cài Signet $ver vào $dest. Chạy từ đó:
  cd $dest && docker compose up -d --wait
  python3 scripts/seed.py     # dữ liệu mẫu, lần đầu
  python3 scripts/smoke.py    # kiểm tra nhanh
  python3 scripts/moc.py audit verify   # kiểm sổ kiểm toán
  python3 scripts/demo.py kiem-dich     # màn demo kiểm dịch (docs/demo-script.md)
  python3 scripts/moc.py backup create  # sao lưu CSDL và tệp vào MOC_BACKUP_DIR (mặc định $dest/backups)
  python3 scripts/reconcile.py         # một lượt GitOps + tự phục hồi (timer mẫu: platform/systemd/)
Bản cài dùng chung tên project và dữ liệu "moc" với bản chạy trong thư mục mã nguồn: dừng bản đó trước (make down).
EOF
}

do_uninstall() {
  local dest
  dest="$(prefix "${1:-}")"
  [ -f "$dest/$MANIFEST" ] || die "$dest không phải bản cài Signet (không có $MANIFEST)"
  lock_dest "$dest"
  if [ -n "$(running_from "$dest")" ]; then
    die "Signet đang chạy từ $dest — dừng trước: cd $dest && docker compose down"
  fi
  remove_managed "$dest"
  find "$dest" -mindepth 1 -type d -empty -delete
  echo "Đã gỡ Signet khỏi $dest. Giữ lại $dest/.env (mật khẩu), kho sao lưu (nếu có), ứng dụng cài thêm" \
    "(.moc-apps, nếu có) và dữ liệu trong các volume Docker của project moc."
  echo "Xóa cả dữ liệu: docker volume rm \$(docker volume ls -q --filter label=com.docker.compose.project=moc)"
}

case "${1:-}" in
  install) do_install "${2:-}" ;;
  uninstall) do_uninstall "${2:-}" ;;
  *) echo "Dùng: $0 install|uninstall <PREFIX>" >&2; exit 2 ;;
esac
