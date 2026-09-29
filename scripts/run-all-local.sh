#!/usr/bin/env bash
# Rehearse on one Mac: SuperLink + both hospital SuperNodes + all three screens.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/run-hospital.sh" harbor 127.0.0.1 &
"$DIR/run-hospital.sh" riverbend 127.0.0.1 &
trap 'kill $(jobs -p) 2>/dev/null' EXIT
"$DIR/run-alder.sh"
