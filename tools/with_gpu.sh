#!/usr/bin/env bash
# Runs a command that needs the GPU (windowed Godot, Blender Eevee/Cycles-GPU renders) under a machine-wide lock,
# so parallel agents and builds do not fight for VRAM or stall each other's frame captures.
# Usage: tools/with_gpu.sh <command...>      (waits up to 30 min for the lock)
LOCK=/tmp/krakow-1795-gpu.lock
exec flock -w 1800 "$LOCK" "$@"
