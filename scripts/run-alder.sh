#!/usr/bin/env bash
# Mac A (Alder, coordinator): Flower SuperLink + the projector bridge.
# The coordinator ServerApp is launched by the bridge when someone clicks "Find an exchange".
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/flower/.venv/bin"
export PATH="$BIN:$PATH"
export FLWR_HOME="$ROOT/.flwr-home/alder"
mkdir -p "$FLWR_HOME" "$ROOT/logs"
busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
for p in 8765 8000 9092 9096; do
  if busy "$p"; then echo "Port $p is already in use (an earlier Domino run?). Run scripts/stop.sh, then try again."; exit 1; fi
done
cat > "$FLWR_HOME/config.toml" <<TOML
[superlink]
default = "domino-local"

[superlink.domino-local]
address = "127.0.0.1:8000"
insecure = true
TOML
"$BIN/python" "$ROOT/web/build.py" >/dev/null
echo "Starting Flower SuperLink (Fleet API :9092 for the hospitals, Control API 127.0.0.1:8000)…"
"$BIN/flower-superlink" --insecure --disable-runtime-dependency-installation --database "$FLWR_HOME/state.db" > "$ROOT/logs/superlink.log" 2>&1 &
SUPERLINK=$!
sleep 3
echo "Starting Alder's own hospital agent (SuperNode, pod pods/alder)…"
"$BIN/flower-supernode" --insecure --superlink 127.0.0.1:9092 --port 9096 \
  --node-config "hospital='alder' pod_dir='${DOMINO_POD:-$ROOT/pods/alder}' bridge_url='http://127.0.0.1:8765'" > "$ROOT/logs/supernode-alder.log" 2>&1 &
ALDERNODE=$!
trap 'kill $SUPERLINK $ALDERNODE 2>/dev/null' EXIT
IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)
echo "Hospitals connect with:  scripts/run-hospital.sh harbor $IP   /   scripts/run-hospital.sh riverbend $IP"
echo "Projector: http://127.0.0.1:8765/projector.html"
FLWR_HOME="$FLWR_HOME" "$BIN/python" "$ROOT/bridge/bridge.py" coordinator --port 8765 --federation domino-local --pace "${DOMINO_PACE:-2.0}"
