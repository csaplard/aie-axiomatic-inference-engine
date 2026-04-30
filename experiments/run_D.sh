#!/usr/bin/env bash
# D kísérlet — 5-karú 2D dizájn (priority × adjacency), confound-free.
set -e
cd "$(dirname "$0")/.."

ARMS=(D_coherent_near D_coherent_far D_random_near D_random_far D_uniform)

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
echo "=== ALL D ARMS COMPLETE ==="
