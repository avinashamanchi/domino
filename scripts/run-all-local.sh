#!/usr/bin/env bash
# Rehearse on one Mac: SuperLink + both hospital SuperNodes + all three screens.
# Everything runs in the background while this script waits, so Ctrl+C (or closing
# the window) always reaches the trap and stops every part cleanly.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cleanup() { trap - EXIT INT TERM HUP; echo; "$DIR/stop.sh"; exit 0; }
trap cleanup EXIT INT TERM HUP
"$DIR/run-hospital.sh" harbor 127.0.0.1 &
"$DIR/run-hospital.sh" riverbend 127.0.0.1 &
"$DIR/run-alder.sh" &
sleep 2
echo "(press Ctrl+C to stop everything)"
wait
