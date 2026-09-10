#!/bin/sh
set -eu

RONIN_UID=65532
RONIN_GID=65532

prepare_data_dir() {
  data_dir=${RONIN_DATA_DIR:-/var/lib/ronin}
  if [ "$(id -u)" -eq 0 ]; then
    install -d -o "$RONIN_UID" -g "$RONIN_GID" "$data_dir"
  fi
}

prepare_workspace_git() {
  workspace=${RONIN_WORKSPACE:-/workspace}
  if [ -d "$workspace/.git" ]; then
    export GIT_CONFIG_COUNT=1
    export GIT_CONFIG_KEY_0=safe.directory
    export GIT_CONFIG_VALUE_0="$workspace"
  fi
}

prepare_docker_socket() {
  socket=/var/run/docker.sock
  if [ ! -S "$socket" ]; then
    echo "error: Docker socket is not available at $socket" >&2
    exit 2
  fi
  if [ "$(id -u)" -eq 0 ]; then
    socket_gid=$(stat -c '%g' "$socket")
    if ! getent group "$socket_gid" >/dev/null 2>&1; then
      groupadd --gid "$socket_gid" ronin-docker
    fi
    usermod --append --groups "$socket_gid" ronin
  fi
}

resolve_worker_image() {
  requested=${RONIN_IMAGE_REF:-${RONIN_IMAGE:-ronin:local}}
  image_id=$(docker image inspect --format '{{.Id}}' "$requested" 2>/dev/null || true)
  case "$image_id" in
    sha256:[0-9a-f][0-9a-f]*) ;;
    *)
      echo "error: cannot resolve RONIN_IMAGE_REF '$requested' to a local immutable image id" >&2
      exit 2
      ;;
  esac
  export RONIN_IMAGE="$image_id"
}

prepare_data_dir
prepare_workspace_git

if [ "${1:-}" = "ronin" ] && [ "${2:-}" = "worker" ]; then
  prepare_docker_socket
  resolve_worker_image
fi

if [ "$(id -u)" -eq 0 ]; then
  exec gosu "$RONIN_UID:$RONIN_GID" "$@"
fi
exec "$@"
