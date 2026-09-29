#!/usr/bin/env bash
# Stop every Domino / Flower process on this Mac (bridges, SuperLink, SuperNodes, running apps).
pkill -f "run-all-local.sh|run-alder.sh|run-hospital.sh" 2>/dev/null
pkill -f "bridge/bridge.py" 2>/dev/null
pkill -f "flower-superlink|flower-supernode|flower-superexec|flwr-serverapp|flwr-clientapp" 2>/dev/null
sleep 1
echo "Domino stopped."
