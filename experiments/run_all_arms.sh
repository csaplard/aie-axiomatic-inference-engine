#!/usr/bin/env bash
# 30 seed × 3 kar × 10000 lépés. Sorban futtatja a karokat (egyenként 4 worker),
# hogy ne legyen Windowson 12 párhuzamos NumPy folyamat.
set -e
cd "$(dirname "$0")/.."

ARMS=(timeless random symmetric)
REGISTRIES=(
    axioms_registry_timeless.json
    experiments/registries/random_48.json
    experiments/registries/timeless_sym.json
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
