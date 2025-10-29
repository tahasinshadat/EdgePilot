#!/usr/bin/env bash

set -euo pipefail

VERSION="${PROM_VERSION:-2.55.1}"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$ARCH" in
  x86_64|amd64) ARCH="amd64" ;;
  arm64|aarch64) ARCH="arm64" ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 1
    ;;
 esac

case "$OS" in
  darwin) PLATFORM="darwin-$ARCH" ;;
  linux) PLATFORM="linux-$ARCH" ;;
  *)
    echo "Unsupported operating system: $OS" >&2
    exit 1
    ;;
 esac

INSTALL_ROOT="${HOME}/.edgepilot/prometheus"
VERSION_DIR="${INSTALL_ROOT}/prometheus-${VERSION}.${PLATFORM}"
BIN_DIR="${INSTALL_ROOT}/bin"
CONFIG_FILE="${INSTALL_ROOT}/prometheus.yml"

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

if [ ! -d "$VERSION_DIR" ]; then
  TARBALL="prometheus-${VERSION}.${PLATFORM}.tar.gz"
  URL="https://github.com/prometheus/prometheus/releases/download/v${VERSION}/${TARBALL}"
  TMPFILE="$(mktemp)"
  echo "Downloading Prometheus ${VERSION} for ${PLATFORM} ..."
  curl -fsSL "$URL" -o "$TMPFILE"
  tar -xzf "$TMPFILE" -C "$INSTALL_ROOT"
  if [ ! -d "$VERSION_DIR" ]; then
    echo "Extracted directory not found at ${VERSION_DIR}; check archive structure." >&2
    exit 1
  fi
  rm -f "$TMPFILE"
else
  echo "Prometheus ${VERSION} already downloaded in ${VERSION_DIR}"
fi

ln -sf "${VERSION_DIR}/prometheus" "${BIN_DIR}/prometheus"
ln -sf "${VERSION_DIR}/promtool" "${BIN_DIR}/promtool"

if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<'CONF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
CONF
  echo "Created default Prometheus config at ${CONFIG_FILE}"
else
  echo "Using existing Prometheus config at ${CONFIG_FILE}"
fi

echo
echo "Prometheus ready."
echo "Export PATH to include the local bin directory (if desired):"
echo "  export PATH=\"${BIN_DIR}:\$PATH\""
echo
echo "Start Prometheus:"
echo "  ${BIN_DIR}/prometheus --config.file=\"${CONFIG_FILE}\" --storage.tsdb.path=\"${INSTALL_ROOT}/data\" --web.listen-address=\"0.0.0.0:9090\""
echo
echo "Prometheus will be available at: http://localhost:9090"
