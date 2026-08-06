#!/usr/bin/env bash
# ----------------------------------------------------------------
# build.sh — Docker 이미지를 빌드한다.
#
# 사용법:
#   ./deploy/build.sh           # 태그를 생략하면 "latest" 로 빌드
#   ./deploy/build.sh v1.2.3    # 버전 태그를 직접 지정
#
# 실행 위치는 어디서든 상관없다. 스크립트가 프로젝트 루트를 자동으로 찾는다.
# ----------------------------------------------------------------

# set -e: 명령이 하나라도 실패(종료 코드 != 0)하면 스크립트를 즉시 중단한다.
#         이 옵션이 없으면 오류가 발생해도 다음 명령이 계속 실행돼
#         잘못된 이미지가 만들어질 수 있다.
set -e

# ----------------------------------------------------------------
# 변수 설정
# ----------------------------------------------------------------

IMAGE_NAME="discovery-worker"

# ${1:-latest}: 첫 번째 인자($1)가 전달됐으면 그 값을, 없으면 "latest" 를 사용.
TAG="${1:-latest}"

# 이 스크립트 파일의 위치(deploy/)에서 한 단계 위로 올라가면 프로젝트 루트.
#   $0       : 실행된 스크립트의 경로 (예: ./deploy/build.sh)
#   dirname  : 경로에서 디렉토리 부분만 추출 (예: ./deploy)
#   cd .. && pwd : 부모 디렉토리의 절대 경로를 구함
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ----------------------------------------------------------------
# 빌드 실행
# ----------------------------------------------------------------

echo "▶ 빌드 시작: ${IMAGE_NAME}:${TAG}"
echo "  프로젝트 루트: ${PROJECT_ROOT}"

# docker build 옵션 설명:
#   -t "${IMAGE_NAME}:${TAG}" : 만들어질 이미지의 이름과 태그 지정
#   "${PROJECT_ROOT}"         : 빌드 컨텍스트 경로.
#                               이 디렉토리 안의 파일들이 COPY 명령에서 사용된다.
#                               Dockerfile 도 이 경로에서 찾는다.
#   --build-arg APP_UID/APP_GID : 이미지 안 appuser 의 UID/GID. run.sh 의
#                               `docker run --user` 값과 반드시 같아야 한다 —
#                               다르면 컨테이너가 appuser 소유가 아닌 UID로 실행돼
#                               /app 접근 권한 문제가 생긴다. 빌드한 사람의 호스트
#                               UID로 맞추던 방식(`$(id -u)`)은 run.sh 가 1001로
#                               고정된 뒤로는 어긋날 수 있어 여기도 고정값으로 맞춘다.
docker build \
    --build-arg APP_UID=1001 --build-arg APP_GID=1001 \
    -t "${IMAGE_NAME}:${TAG}" \
    "${PROJECT_ROOT}"

echo ""
echo "✓ 빌드 완료: ${IMAGE_NAME}:${TAG}"
echo ""
echo "다음 단계:"
echo "  워커 시작  → ./deploy/run.sh <source> <worker_id>"
echo "  이미지 확인 → docker images ${IMAGE_NAME}"
