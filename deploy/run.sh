#!/usr/bin/env bash
# run.sh — discovery-worker 컨테이너 실행
#
# 사용법:
#   ./deploy/run.sh <source> <worker_id>
#
# 인자:
#   source     naver_news | daum_news | google_news | naver_stock | all
#   worker_id  컨테이너 고유 이름 (예: disc-naver-1)
#
# 예시:
#   ./deploy/run.sh naver_news disc-naver-1
#   ./deploy/run.sh daum_news  disc-daum-1
#   ./deploy/run.sh all        disc-all-1

set -e

SOURCE="${1}"
WORKER_ID="${2}"

if [[ -z "${SOURCE}" || -z "${WORKER_ID}" ]]; then
    echo "오류: 인자가 부족합니다."
    echo ""
    echo "사용법: $0 <source> <worker_id>"
    echo ""
    echo "  source   : naver_news | daum_news | google_news | naver_stock | all"
    echo "  worker_id: 고유 식별자 (예: disc-naver-1)"
    echo ""
    echo "예시:"
    echo "  $0 naver_news disc-naver-1"
    echo "  $0 all        disc-all-1"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_ENV="${APP_ENV:-dev}"
ENV_FILE="${PROJECT_ROOT}/.env.${APP_ENV}"

LOG_DIR="${HOME}/apps/data/discovery-worker/logs"
OUTPUT_DIR="${HOME}/apps/data/discovery-worker/output"
GOOGLE_CHROME_PROFILE_DIR="${HOME}/apps/data/discovery-worker/chrome_profile_google"
BAIDU_CHROME_PROFILE_DIR="${HOME}/apps/data/discovery-worker/chrome_profile_baidu"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "오류: 환경 설정 파일을 찾을 수 없습니다: ${ENV_FILE}"
    echo "  APP_ENV=${APP_ENV} 로 실행 중입니다."
    exit 1
fi

mkdir -p "${LOG_DIR}"
mkdir -p "${OUTPUT_DIR}"
mkdir -p "${GOOGLE_CHROME_PROFILE_DIR}"
mkdir -p "${BAIDU_CHROME_PROFILE_DIR}"

CONTAINER_NAME="${WORKER_ID}"
IMAGE="discovery-worker:latest"

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "▶ 기존 컨테이너 제거: ${CONTAINER_NAME}"
    docker rm -f "${CONTAINER_NAME}"
fi

echo "▶ 컨테이너 시작: ${CONTAINER_NAME}"
echo "  이미지   : ${IMAGE}"
echo "  소스     : ${SOURCE}"
echo "  환경설정 : ${ENV_FILE}"
echo "  로그     : ${LOG_DIR}"
echo ""

docker run \
    --detach \
    --name "${CONTAINER_NAME}" \
    --user "$(id -u):$(id -g)" \
    --restart unless-stopped \
    --env-file "${ENV_FILE}" \
    -e APP_ENV="${APP_ENV}" \
    -e WORKER_ID="${WORKER_ID}" \
    -v "${LOG_DIR}:/app/logs" \
    -v "${OUTPUT_DIR}:/app/output" \
    -v "${GOOGLE_CHROME_PROFILE_DIR}:/app/chrome_profile_google" \
    -v "${BAIDU_CHROME_PROFILE_DIR}:/app/chrome_profile_baidu" \
    "${IMAGE}" \
    python -m app --source "${SOURCE}"

echo "✓ 시작 완료: ${CONTAINER_NAME}"
echo ""
echo "확인 명령어:"
echo "  실시간 로그   → docker logs -f ${CONTAINER_NAME}"
echo "  상태 확인     → docker ps | grep ${CONTAINER_NAME}"
echo "  컨테이너 중지 → docker stop ${CONTAINER_NAME}"
