#!/usr/bin/env bash
# Macs B and C: this hospital's Flower SuperNode (its agent, reading only its own pod) + its private console.
#   scripts/run-hospital.sh harbor <alder-ip>
#   scripts/run-hospital.sh riverbend <alder-ip>
set -euo pipefail
H="${1:?hospital: harbor or riverbend}"
SUPERLINK_IP="${2:-127.0.0.1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/flower/.venv/bin"
export PATH="$BIN:$PATH"
POD="${DOMINO_POD:-$ROOT/pods/$H}"
case "$H" in harbor) PORT=8766; RT=9094 ;; riverbend) PORT=8767; RT=9095 ;; *) echo "unknown hospital $H"; exit 1 ;; esac
export FLWR_HOME="$ROOT/.flwr-home/$H"
mkdir -p "$FLWR_HOME" "$ROOT/logs"
busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
for p in "$PORT" "$RT"; do
  if busy "$p"; then echo "Port $p is already in use (an earlier Domino run?). Run scripts/stop.sh, then try again."; exit 1; fi
done
"$BIN/python" "$ROOT/web/build.py" >/dev/null
echo "Starting $H SuperNode → SuperLink $SUPERLINK_IP:9092 · pod $POD"
"$BIN/flower-supernode" --insecure --superlink "$SUPERLINK_IP:9092" --port "$RT" \
  --node-config "hospital='$H' pod_dir='$POD' bridge_url='http://127.0.0.1:$PORT'" > "$ROOT/logs/supernode-$H.log" 2>&1 &
NODE=$!
trap 'kill $NODE 2>/dev/null' EXIT
echo "Private console: http://127.0.0.1:$PORT/console.html"
"$BIN/python" "$ROOT/bridge/bridge.py" hospital --hospital "$H" --port "$PORT"
