#!/usr/bin/env bash
# C kísérlet: priority_weight mechanizmus, 4 kar, strict-immune.
set -e
cd "$(dirname "$0")/.."

ARMS=(priority_thesis priority_uniform priority_random priority_inverted)

for name in "${ARMS[@]}"; do
    reg="experiments/registries/${name}.json"
    echo "=== [$(date +%H:%M:%S)] start arm: $name ==="
    python -m experiments.run_experiment \
        --name "$name" \
        --registry "$reg" \
        --n-seeds 30 \
        --max-steps 10000 \
        --telemetry-every 100 \
        --workers 4 \
        --strict-immune
    echo "=== [$(date +%H:%M:%S)] done: $name ==="
done
echo "=== ALL PRIORITY ARMS COMPLETE ==="
