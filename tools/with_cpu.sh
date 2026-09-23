#!/usr/bin/env bash
# Runs a CPU-heavy job (Blender headless builds, headless Godot smoke) at low priority on a slice of the cores,
# leaving the rest of the machine responsive. The slice rotates per call so parallel jobs spread out.
# Usage: tools/with_cpu.sh [-n CORES] <command...>      (default 8 cores)
N=8
if [[ "${1:-}" == "-n" ]]; then N="$2"; shift 2; fi
TOTAL=$(nproc)
SLOTS=$(( TOTAL / N )); [[ $SLOTS -lt 1 ]] && SLOTS=1
COUNTER=/tmp/krakow-1795-cpu.slot
S=$(( ( $(cat "$COUNTER" 2>/dev/null || echo 0) + 1 ) % SLOTS ))
echo "$S" > "$COUNTER"
FIRST=$(( S * N )); LAST=$(( FIRST + N - 1 )); [[ $LAST -ge $TOTAL ]] && LAST=$(( TOTAL - 1 ))
# Godot loads the whole character roster (several GB): allow at most two Godot processes machine-wide,
# whatever the agents do. Slots are flocks; the wait is up to 30 minutes.
if printf '%s ' "$@" | grep -q 'godot'; then
  for slot in 0 1; do
    exec 9>"/tmp/krakow-1795-godot-$slot.lock"
    if flock -n 9; then
      exec nice -n 10 taskset -c "${FIRST}-${LAST}" "$@"
    fi
    exec 9>&-
  done
  exec flock -w 1800 "/tmp/krakow-1795-godot-0.lock" nice -n 10 taskset -c "${FIRST}-${LAST}" "$@"
fi
exec nice -n 10 taskset -c "${FIRST}-${LAST}" "$@"
