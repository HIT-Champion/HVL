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
# Dựng PostgreSQL + Hasura tạm để chạy test của db/ — CSDL nằm trong RAM, mỗi lần `up` là CSDL trống,
# migrations và metadata nạp thẳng từ db/ của cây mã nguồn. Chỉ để test: khóa ký token là HS256 cố định,
# không phải cấu hình triển khai (xem db/README.md, mục Compose).
#
#   db/tests/stack.sh up      # dựng, đợi metadata nạp xong và nhất quán
#   db/tests/stack.sh down    # xóa container và mạng
#   db/tests/stack.sh reset   # down rồi up
#
# MOC_IT_JWT_PUBLIC_KEY=<tệp PEM>: Hasura kiểm token RS256 bằng khóa công khai này thay cho HS256 — dùng cho
# test đầu-cuối của svc-files, vốn chỉ nhận RS256 như token Keycloak (services/svc-files/README.md).
# ---------------------------------------------------------------------------
set -euo pipefail

DB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NET=moc-db-it
PG=moc-db-it-postgres
HASURA=moc-db-it-hasura
PG_IMAGE=postgres:16-alpine
HASURA_IMAGE=hasura/graphql-engine:v2.51.0-ce.cli-migrations-v3
PORT="${MOC_IT_HASURA_PORT:-18080}"
ADMIN_SECRET="${MOC_IT_HASURA_ADMIN_SECRET:-it-admin-secret}"
JWT_KEY="${MOC_IT_JWT_KEY:-it-only-hs256-key-not-for-production-0123456789}"
ISSUER="${MOC_IT_ISSUER:-https://moc.example/realms/moc}"

die() { echo "stack.sh: $*" >&2; exit 1; }

jwt_secret() {
  local claims='"issuer":"'"$ISSUER"'","claims_namespace":"https://hasura.io/jwt/claims"'
  if [ -n "${MOC_IT_JWT_PUBLIC_KEY:-}" ]; then
    [ -r "$MOC_IT_JWT_PUBLIC_KEY" ] || die "không đọc được $MOC_IT_JWT_PUBLIC_KEY"
    # PEM nhiều dòng → một chuỗi JSON với \n
    local pem
    pem="$(awk 'NF { printf "%s\\n", $0 }' "$MOC_IT_JWT_PUBLIC_KEY")"
    echo '{"type":"RS256","key":"'"$pem"'",'"$claims"'}'
  else
    echo '{"type":"HS256","key":"'"$JWT_KEY"'",'"$claims"'}'
  fi
}

up() {
  command -v docker >/dev/null || die "thiếu Docker"
  command -v curl >/dev/null || die "thiếu curl"
  docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null

  docker run -d --name "$PG" --network "$NET" \
    -e POSTGRES_USER=moc -e POSTGRES_DB=moc -e POSTGRES_PASSWORD=it-only \
    --tmpfs /var/lib/postgresql/data \
    "$PG_IMAGE" >/dev/null
  # Hỏi qua TCP: lúc khởi tạo, image chạy một máy chủ tạm chỉ nghe socket Unix rồi tắt đi —
  # hỏi qua socket sẽ báo sẵn sàng quá sớm.
  local ready=""
  for _ in $(seq 1 60); do
    if docker exec "$PG" pg_isready -h 127.0.0.1 -U moc -d moc -q 2>/dev/null; then ready=1; break; fi
    sleep 1
  done
  [ -n "$ready" ] || die "PostgreSQL không lên"

  docker run -d --name "$HASURA" --network "$NET" -p "127.0.0.1:${PORT}:8080" \
    -v "$DB_DIR/migrations:/hasura-migrations:ro" \
    -v "$DB_DIR/metadata:/hasura-metadata:ro" \
    -e HASURA_GRAPHQL_DATABASE_URL="postgres://moc:it-only@${PG}:5432/moc" \
    -e HASURA_GRAPHQL_METADATA_DATABASE_URL="postgres://moc:it-only@${PG}:5432/moc" \
    -e HASURA_GRAPHQL_ADMIN_SECRET="$ADMIN_SECRET" \
    -e HASURA_GRAPHQL_JWT_SECRET="$(jwt_secret)" \
    -e HASURA_GRAPHQL_ENABLED_APIS=graphql,metadata \
    -e HASURA_GRAPHQL_ENABLE_CONSOLE=false \
    -e HASURA_GRAPHQL_DEV_MODE=true \
    -e HASURA_GRAPHQL_ENABLE_TELEMETRY=false \
    -e HASURA_GRAPHQL_INFER_FUNCTION_PERMISSIONS=false \
    -e MOC_WORKFLOW_URL="${MOC_IT_WORKFLOW_URL:-http://svc-workflow.invalid:8000}" \
    -e MOC_ACTION_SECRET="${MOC_IT_ACTION_SECRET:-it-action-secret}" \
    "$HASURA_IMAGE" >/dev/null

  for _ in $(seq 1 90); do
    curl -sf "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1 && break
    docker inspect -f '{{.State.Running}}' "$HASURA" 2>/dev/null | grep -q true || break
    sleep 1
  done
  if ! curl -sf "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    docker logs --tail 40 "$HASURA" >&2 || true
    die "Hasura không lên — xem nhật ký ở trên (thường do lỗi SQL trong migration)"
  fi

  local state
  state="$(curl -s "http://127.0.0.1:${PORT}/v1/metadata" -H "X-Hasura-Admin-Secret: ${ADMIN_SECRET}" \
           -d '{"type":"get_inconsistent_metadata","args":{}}')"
  if ! grep -q '"is_consistent":true' <<<"$state"; then
    echo "$state" >&2
    die "metadata không khớp schema"
  fi
  echo "Hasura sẵn sàng ở http://127.0.0.1:${PORT}. Chạy test: MOC_IT=1 .venv/bin/python -m pytest (trong db/tests)"
}

down() {
  docker rm -f "$HASURA" "$PG" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  reset) down; up ;;
  *) echo "Dùng: $0 up|down|reset" >&2; exit 2 ;;
esac
