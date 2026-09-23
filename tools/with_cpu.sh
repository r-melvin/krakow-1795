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
exec nice -n 10 taskset -c "${FIRST}-${LAST}" "$@"
