#!/usr/bin/env bash
set -euo pipefail

IMAGE="${KALIBR_IMAGE:-vimas-kalibr:ros1_20_04}"
REPO="${KALIBR_REPO:-https://github.com/ethz-asl/kalibr.git}"
WORKDIR_HOST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

build_image() {
  if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "using existing image: $IMAGE"
    return
  fi
  echo "building Kalibr Docker image: $IMAGE"
  docker build -t "$IMAGE" -f Dockerfile_ros1_20_04 "$REPO"
}

run_shell() {
  build_image
  xhost +local:"$(id -un)" >/dev/null 2>&1 || true
  docker run --rm -it \
    --user "${HOST_UID}:${HOST_GID}" \
    -e DISPLAY="${DISPLAY:-}" \
    -e HOME=/tmp \
    -e QT_X11_NO_MITSHM=1 \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "$WORKDIR_HOST:/data" \
    -w /catkin_ws \
    "$IMAGE"
}

case "${1:-shell}" in
  build)
    build_image
    ;;
  shell)
    run_shell
    ;;
  *)
    echo "usage: $0 [build|shell]" >&2
    exit 2
    ;;
esac
