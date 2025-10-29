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

BASE_DIR="${HOME}/.edgepilot"
LOG_DIR="${BASE_DIR}/logs"
PROM_INSTALL_ROOT="${BASE_DIR}/prometheus"
PROM_VERSION_DIR="${PROM_INSTALL_ROOT}/prometheus-${VERSION}.${PLATFORM}"
PROM_BIN_DIR="${PROM_INSTALL_ROOT}/bin"
CONFIG_FILE="${PROM_INSTALL_ROOT}/prometheus.yml"
PROM_PID_FILE="${PROM_INSTALL_ROOT}/prometheus.pid"

NODE_VERSION="${NODE_EXPORTER_VERSION:-1.8.1}"
NODE_INSTALL_ROOT="${BASE_DIR}/node_exporter"
NODE_VERSION_DIR="${NODE_INSTALL_ROOT}/node_exporter-${NODE_VERSION}.${PLATFORM}"
NODE_BIN_DIR="${NODE_INSTALL_ROOT}/bin"
NODE_PID_FILE="${NODE_INSTALL_ROOT}/node_exporter.pid"

mkdir -p "$PROM_INSTALL_ROOT" "$PROM_BIN_DIR"

if [ ! -d "$PROM_VERSION_DIR" ]; then
  TARBALL="prometheus-${VERSION}.${PLATFORM}.tar.gz"
  URL="https://github.com/prometheus/prometheus/releases/download/v${VERSION}/${TARBALL}"
  TMPFILE="$(mktemp)"
  echo "Downloading Prometheus ${VERSION} for ${PLATFORM} ..."
  curl -fsSL "$URL" -o "$TMPFILE"
  tar -xzf "$TMPFILE" -C "$PROM_INSTALL_ROOT"
  if [ ! -d "$PROM_VERSION_DIR" ]; then
    echo "Extracted directory not found at ${PROM_VERSION_DIR}; check archive structure." >&2
    exit 1
  fi
  rm -f "$TMPFILE"
else
  echo "Prometheus ${VERSION} already downloaded in ${PROM_VERSION_DIR}"
fi

ln -sf "${PROM_VERSION_DIR}/prometheus" "${PROM_BIN_DIR}/prometheus"
ln -sf "${PROM_VERSION_DIR}/promtool" "${PROM_BIN_DIR}/promtool"

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

ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/env/.env"
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

if ! grep -q '^PROM_URL=' "$ENV_FILE"; then
  echo 'PROM_URL=http://localhost:9090' >> "$ENV_FILE"
  echo "Configured PROM_URL in $ENV_FILE"
fi

if ! grep -q '^PROM_TIMEOUT_SEC=' "$ENV_FILE"; then
  echo 'PROM_TIMEOUT_SEC=15' >> "$ENV_FILE"
  echo "Configured PROM_TIMEOUT_SEC in $ENV_FILE"
fi

mkdir -p "$NODE_INSTALL_ROOT" "$NODE_BIN_DIR" "$LOG_DIR"

if [ ! -d "$NODE_VERSION_DIR" ]; then
  NODE_TARBALL="node_exporter-${NODE_VERSION}.${PLATFORM}.tar.gz"
  NODE_URL="https://github.com/prometheus/node_exporter/releases/download/v${NODE_VERSION}/${NODE_TARBALL}"
  TMPFILE="$(mktemp)"
  echo "Downloading node_exporter ${NODE_VERSION} for ${PLATFORM} ..."
  curl -fsSL "$NODE_URL" -o "$TMPFILE"
  tar -xzf "$TMPFILE" -C "$NODE_INSTALL_ROOT"
  if [ ! -d "$NODE_VERSION_DIR" ]; then
    echo "Extracted directory not found at ${NODE_VERSION_DIR}; check archive structure." >&2
    exit 1
  fi
  rm -f "$TMPFILE"
else
  echo "node_exporter ${NODE_VERSION} already downloaded in ${NODE_VERSION_DIR}"
fi

ln -sf "${NODE_VERSION_DIR}/node_exporter" "${NODE_BIN_DIR}/node_exporter"

if [ -f "$CONFIG_FILE" ]; then
  if ! grep -q "job_name: 'node'" "$CONFIG_FILE"; then
    cat >> "$CONFIG_FILE" <<'CONF'

  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
CONF
    echo "Updated Prometheus config at ${CONFIG_FILE} with node_exporter scrape job. Restart Prometheus to apply."
  else
    echo "Prometheus config already contains a 'node' scrape job."
  fi
else
  echo "Prometheus config not found at ${CONFIG_FILE}; skipping scrape job update." >&2
fi

start_services() {
  mkdir -p "$LOG_DIR"

  if [ -f "$PROM_PID_FILE" ] && ps -p "$(cat "$PROM_PID_FILE")" >/dev/null 2>&1; then
    echo "Prometheus already running (pid $(cat "$PROM_PID_FILE"))."
  else
    nohup "${PROM_BIN_DIR}/prometheus" \
      --config.file="${CONFIG_FILE}" \
      --storage.tsdb.path="${PROM_INSTALL_ROOT}/data" \
      --web.listen-address="0.0.0.0:9090" \
      > "${LOG_DIR}/prometheus.log" 2>&1 &
    echo $! > "$PROM_PID_FILE"
    echo "Started Prometheus (pid $(cat "$PROM_PID_FILE"), log ${LOG_DIR}/prometheus.log)."
  fi

  if [ -f "$NODE_PID_FILE" ] && ps -p "$(cat "$NODE_PID_FILE")" >/dev/null 2>&1; then
    echo "node_exporter already running (pid $(cat "$NODE_PID_FILE"))."
  else
    nohup "${NODE_BIN_DIR}/node_exporter" \
      --web.listen-address=":9100" \
      > "${LOG_DIR}/node_exporter.log" 2>&1 &
    echo $! > "$NODE_PID_FILE"
    echo "Started node_exporter (pid $(cat "$NODE_PID_FILE"), log ${LOG_DIR}/node_exporter.log)."
  fi
}

stop_services() {
  if [ -f "$PROM_PID_FILE" ]; then
    if kill "$(cat "$PROM_PID_FILE")" >/dev/null 2>&1; then
      echo "Stopped Prometheus."
    fi
    rm -f "$PROM_PID_FILE"
  fi

  if [ -f "$NODE_PID_FILE" ]; then
    if kill "$(cat "$NODE_PID_FILE")" >/dev/null 2>&1; then
      echo "Stopped node_exporter."
    fi
    rm -f "$NODE_PID_FILE"
  fi
}

status_services() {
  if [ -f "$PROM_PID_FILE" ] && ps -p "$(cat "$PROM_PID_FILE")" >/dev/null 2>&1; then
    echo "Prometheus running (pid $(cat "$PROM_PID_FILE"), log ${LOG_DIR}/prometheus.log)."
  else
    echo "Prometheus not running."
  fi

  if [ -f "$NODE_PID_FILE" ] && ps -p "$(cat "$NODE_PID_FILE")" >/dev/null 2>&1; then
    echo "node_exporter running (pid $(cat "$NODE_PID_FILE"), log ${LOG_DIR}/node_exporter.log)."
  else
    echo "node_exporter not running."
  fi
}

ACTION=${1:-}
case "$ACTION" in
  start)
    start_services
    echo "EdgePilot environment updated. Restart the backend to pick up PROM_URL if it's already running."
    exit 0
    ;;
  stop)
    stop_services
    exit 0
    ;;
  status)
    status_services
    exit 0
    ;;
esac

echo
echo "Prometheus and node_exporter are ready."
echo "Export PATH to include the local bin directory (if desired):"
echo "  export PATH=\"${PROM_BIN_DIR}:\$PATH\""
echo
echo "Start them manually with:"
echo "  ${PROM_BIN_DIR}/prometheus --config.file=\"${CONFIG_FILE}\" --storage.tsdb.path=\"${PROM_INSTALL_ROOT}/data\" --web.listen-address=\"0.0.0.0:9090\""
echo "  ${NODE_BIN_DIR}/node_exporter --web.listen-address=\":9100\""
echo
echo "Or run:"
echo "  ./scripts/bootstrap_prometheus.sh start"
echo "to launch both in the background (logs in ${LOG_DIR})."
echo
echo "Prometheus will be available at: http://localhost:9090"
echo "Restart the EdgePilot backend after starting services so it picks up the metrics environment variables."
