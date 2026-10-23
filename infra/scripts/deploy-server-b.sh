#!/usr/bin/env bash
# 在服务器 B 的 GitHub Runner 上执行构建、迁移、启动和就绪检查。
set -Eeuo pipefail

project_root="${GITHUB_WORKSPACE:?GITHUB_WORKSPACE is required}"
env_file="${RAGMANAGE_SERVER_B_ENV:-/home/opul-242/ragmanage/.env}"
compose_file="$project_root/infra/compose/server-b.yaml"
project_name="${COMPOSE_PROJECT_NAME:-ragmanage}"
image_tag="${GITHUB_SHA:?GITHUB_SHA is required}"
api_image="ragmanage-b-api:${image_tag}"
frontend_image="ragmanage-b-frontend:${image_tag}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing protected server B environment: $env_file" >&2
  exit 1
fi

# Compose 1.x does not support --env-file; export the protected values so both
# legacy and current Compose releases resolve the same service configuration.
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

cd "$project_root"
export API_IMAGE="$api_image"
export FRONTEND_IMAGE="$frontend_image"

# 旧 Docker Engine 使用传统构建器；镜像保留在 B 本机，不依赖外部 Registry。
docker build --tag "$api_image" --file backend/Dockerfile backend
docker build --tag "$frontend_image" --file frontend/Dockerfile .

compose=(docker-compose --project-name "$project_name" --file "$compose_file")
"${compose[@]}" config -q
"${compose[@]}" run --rm api alembic upgrade head
"${compose[@]}" up -d --remove-orphans

for attempt in {1..18}; do
  if curl --fail --silent --show-error --max-time 8 http://127.0.0.1:20001/api/v1/health/ready >/dev/null; then
    "${compose[@]}" ps
    exit 0
  fi
  sleep 5
done

"${compose[@]}" ps
echo "Server B RAGManage did not become ready on port 20001." >&2
exit 1
