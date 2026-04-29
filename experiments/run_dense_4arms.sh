#!/usr/bin/env bash
# B kísérlet: kicsi sűrű regiszter, 4 kar, 30 seed × 10000 lépés.
set -e
cd "$(dirname "$0")/.."

ARMS=(dense_thesis dense_random dense_no_immune dense_random_immune)
REGISTRIES=(
    experiments/registries/dense_thesis.json
    experiments/registries/dense_random.json
    experiments/registries/dense_no_immune.json
    experiments/registries/dense_random_immune.json
)

for i in "${!ARMS[@]}"; do
    name="${ARMS[$i]}"
    reg="${REGISTRIES[$i]}"
    echo "=== [$(date +%H:%M:%S)] start arm: $name (registry=$reg) ==="
    python -m experiments.run_experiment \
        --name "$name" \
        --registry "$reg" \
        --n-seeds 30 \
        --max-steps 10000 \
        --telemetry-every 100 \
        --workers 4
    echo "=== [$(date +%H:%M:%S)] done arm: $name ==="
done
echo "=== ALL ARMS COMPLETE ==="
